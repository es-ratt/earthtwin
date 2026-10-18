"""Dataset import pipeline.

Dataset Import → Format Detection → Validation → Metadata & Field Mapping →
Normalisation → Scientific Processing → Feature Extraction → Database Update →
(revision bump) → Automatic UI refresh.

Sessions persist in `import_session`; processing runs as an `analysis_job`
(background thread) whose log and errors are stored, so failures are never
presented as successful imports.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import threading
import traceback
from pathlib import Path
from typing import BinaryIO

from ..config import get_settings
from ..db import bump_revision, dumps, loads, new_id, now, row, session
from ..services.vocabulary import VARIABLE_BY_KEY
from . import detect as D
from . import mapping as M
from .adapters import raster as R
from .adapters import tabular as T

PREVIEW_ROWS = 12


class ImportError_(ValueError):
    pass


# --------------------------------------------------------------------------- helpers
def _existing_subjects(conn) -> dict:
    return {
        "earth_site": {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM earth_site")},
        "target_region": {r["id"]: (r["name"], r["world_id"]) for r in conn.execute("SELECT id, name, world_id FROM target_region")},
    }


def _suggest_kinds(fmt: str, columns: list[str], info: dict) -> list[str]:
    if fmt == "geotiff":
        return ["raster"]
    if fmt == "bundle":
        return ["bundle"]
    n = {M.norm(c) for c in columns}
    out = []
    if fmt == "geojson":
        gt = info.get("geometry_types", {})
        if any(k != "Point" for k in gt):
            return ["map_layer"]
        out.append("map_layer")
    if {"variable", "value"} <= n or {"variable_key", "value"} <= n:
        out.insert(0, "observations_long")
    has_coords = bool(n & {"lat", "latitude", "_geometry_lat"}) and bool(n & {"lon", "long", "longitude", "_geometry_lon"})
    if has_coords:
        out.insert(0, "target_regions" if "body" in n or "world" in n else "earth_sites")
        out.append("target_regions" if "target_regions" not in out else "earth_sites")
    out.append("observations")
    seen, res = set(), []
    for k in out:
        if k not in seen:
            seen.add(k)
            res.append(k)
    return res


def _load_table(path: Path, fmt: str):
    return T.read(path, fmt)


def _session(conn, sid: str) -> dict:
    s = row(conn.execute("SELECT * FROM import_session WHERE id = ?", (sid,)).fetchone())
    if not s:
        raise ImportError_(f"Import session {sid} not found")
    for k in ("structure", "proposed_mapping", "confirmed_mapping", "metadata", "validation"):
        s[k] = loads(s[k], {} if k != "confirmed_mapping" else None)
    return s


def public_session(s: dict) -> dict:
    out = {k: v for k, v in s.items() if k != "stored_path"}
    return out


# --------------------------------------------------------------------------- 1. upload + inspect
def create_session(stream: BinaryIO, filename: str, kind_hint: str | None = None) -> dict:
    st = get_settings()
    st.ensure_dirs()
    safe_name = Path(filename or "upload").name[:200]
    ext = Path(safe_name).suffix.lower()
    limit = st.max_raster_bytes if ext in (".tif", ".tiff") else st.max_table_bytes
    sid = new_id()
    dest = st.upload_dir / f"{sid}{ext if ext in ('.csv', '.txt', '.json', '.geojson', '.tif', '.tiff') else '.bin'}"
    h, size = hashlib.sha256(), 0
    with open(dest, "wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise ImportError_(f"File exceeds the {limit // (1024 * 1024)} MB limit for this format.")
            h.update(chunk)
            out.write(chunk)
    if size == 0:
        dest.unlink(missing_ok=True)
        raise ImportError_("The uploaded file is empty.")
    try:
        fmt = D.detect(dest, safe_name)
        structure = inspect_file(dest, fmt)
    except (D.DetectionError, T.AdapterError, R.RasterError, ValueError) as e:
        dest.unlink(missing_ok=True)
        raise ImportError_(str(e)) from e
    kinds = structure["suggested_kinds"]
    kind = kind_hint if kind_hint in kinds else kinds[0]
    proposed = propose_for(kind, structure)
    ts = now()
    with session() as conn:
        conn.execute(
            """INSERT INTO import_session(id, original_filename, stored_path, size_bytes, sha256, detected_format, import_kind,
               structure, proposed_mapping, metadata, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (sid, safe_name, str(dest), size, h.hexdigest(), fmt, kind, dumps(structure), dumps(proposed),
             dumps(default_metadata(fmt, structure, safe_name)), "inspected", ts, ts))
        dup = conn.execute("SELECT d.name FROM dataset_version dv JOIN dataset d ON d.id = dv.dataset_id WHERE dv.sha256 = ?",
                           (h.hexdigest(),)).fetchone()
        s = _session(conn, sid)
    if dup:
        s["duplicate_of"] = dup[0]
    return public_session(s)


def inspect_file(path: Path, fmt: str) -> dict:
    if fmt == "geotiff":
        info = R.inspect(path)
        return {"format": fmt, "raster": info, "suggested_kinds": ["raster"], "columns": [], "n_rows": 0, "preview": []}
    if fmt == "bundle":
        doc = json.loads(path.read_bytes().decode("utf-8-sig"))
        counts = {k: len(doc.get(k) or []) for k in ("earth_sites", "target_regions", "observations", "citations")}
        return {"format": fmt, "bundle_version": doc.get("earthtwin_bundle"), "counts": counts,
                "dataset": doc.get("dataset", {}), "suggested_kinds": ["bundle"], "columns": [], "n_rows": sum(counts.values()),
                "preview": (doc.get("earth_sites") or doc.get("target_regions") or doc.get("observations") or [])[:PREVIEW_ROWS]}
    cols, rows, info = _load_table(path, fmt)
    types = {}
    for c in cols:
        vals = [r.get(c) for r in rows[:500] if not M.is_missing(r.get(c))]
        num = 0
        for v in vals:
            try:
                M.parse_float(v)
                num += 1
            except (ValueError, TypeError):
                pass
        types[c] = {"non_empty": len(vals), "numeric_fraction": round(num / len(vals), 2) if vals else 0,
                    "examples": [str(v)[:40] for v in vals[:3]]}
    return {"format": fmt, "columns": cols, "column_profile": types, "n_rows": len(rows), "info": info,
            "preview": rows[:PREVIEW_ROWS], "suggested_kinds": _suggest_kinds(fmt, cols, info)}


def propose_for(kind: str, structure: dict) -> dict:
    if kind == "raster":
        r = structure.get("raster", {})
        guess_unit = (r.get("units") or [None])[0] or None
        return {"kind": "raster", "raster": {"raster_kind": None, "unit": guess_unit, "unit_source": "file" if guess_unit else None,
                                             "variable": None, "declared_crs": None},
                "detected_body": r.get("detected_body"), "needs_review": True}
    if kind == "map_layer":
        return {"kind": "map_layer", "layer": {"name": None, "label_property": None, "color": "#38bdf8"}, "needs_review": True}
    if kind == "bundle":
        return {"kind": "bundle", "needs_review": False}
    p = M.propose(kind, structure["columns"], structure.get("preview", []))
    p["options"] = {"list_separator": None}
    if kind in ("observations", "observations_long"):
        p["options"].update({"subject_type": None, "match_by": None})
    if kind == "target_regions":
        p["options"].update({"lon_convention": None, "lat_type": None})
    return p


def default_metadata(fmt: str, structure: dict, filename: str) -> dict:
    md = {"name": Path(filename).stem.replace("_", " ").strip(), "publisher": "", "source_url": "", "identifier": "",
          "license": "", "description": "", "data_class": None, "body": None, "crs": None, "spatial_resolution": "",
          "temporal_coverage": "", "provenance": "", "version": "", "citation_text": "", "citation_doi": "",
          "method": "", "dataset_id": None, "activate": True}
    if fmt == "bundle":
        d = structure.get("dataset", {})
        md.update({k: d.get(k, md.get(k)) for k in md if k in d})
        c = d.get("citation") or {}
        md["citation_text"], md["citation_doi"] = c.get("text", ""), c.get("doi", "")
    if fmt == "geotiff":
        r = structure.get("raster", {})
        md["body"] = r.get("detected_body")
        md["crs"] = r.get("crs")
        res = r.get("resolution")
        if res:
            md["spatial_resolution"] = f"{res[0]:g} × {res[1]:g} {'deg' if r.get('is_geographic') else (r.get('linear_unit') or 'units')}/px"
    return md


# --------------------------------------------------------------------------- 2. mapping + validation (dry run)
def set_mapping(sid: str, kind: str, mapping: dict, metadata: dict) -> dict:
    with session() as conn:
        s = _session(conn, sid)
        if s["status"] in ("processing", "completed"):
            raise ImportError_(f"Import is already {s['status']}")
        if kind not in s["structure"]["suggested_kinds"] and not (kind in ("earth_sites", "target_regions", "observations", "observations_long")
                                                                  and s["detected_format"] in ("csv", "json", "geojson")):
            raise ImportError_(f"Import kind '{kind}' is not available for a {s['detected_format']} file")
        md = {**s["metadata"], **(metadata or {})}
        mapping = {**(mapping or {}), "kind": kind}
        report = run_validation(conn, s, kind, mapping, md)
        summary = {k: v for k, v in report.items() if k != "records"}
        summary["preview_records"] = {k: v[:PREVIEW_ROWS] for k, v in report.get("records", {}).items()}
        summary["issues"] = report["issues"][:500]
        summary["n_issues_total"] = len(report["issues"])
        conn.execute("UPDATE import_session SET import_kind=?, confirmed_mapping=?, metadata=?, validation=?, status=?, updated_at=? WHERE id=?",
                     (kind, dumps(mapping), dumps(md), dumps(summary), "validated" if report["ok"] else "invalid", now(), sid))
        return public_session(_session(conn, sid))


def run_validation(conn, s: dict, kind: str, mapping: dict, md: dict) -> dict:
    path = Path(s["stored_path"])
    if not path.exists():
        raise ImportError_("Stored upload is missing; upload the file again.")
    if md.get("dataset_id"):
        if not conn.execute("SELECT 1 FROM dataset WHERE id = ?", (md["dataset_id"],)).fetchone():
            return {"ok": False, "kind": kind, "n_records": 0, "n_valid": 0, "n_rejected": 0,
                    "issues": [{"level": "error", "message": f"Dataset {md['dataset_id']} (new version target) does not exist"}], "records": {}}
    if kind == "raster":
        return _validate_raster(conn, s, mapping, md)
    if kind == "map_layer":
        return _validate_layer(s, mapping, md)
    if kind == "bundle":
        return _validate_bundle(conn, path, md)
    cols, rows, _ = _load_table(path, s["detected_format"])
    return M.validate(kind, rows, cols, mapping, md, _existing_subjects(conn))


def _base_md_issues(md: dict, need_body: bool) -> list[dict]:
    issues = []
    if md.get("data_class") not in ("verified", "demo", "reference"):
        issues.append({"level": "error", "message": "Choose a data class: 'verified', 'demo' or 'reference'."})
    if md.get("data_class") == "verified" and not ((md.get("publisher") or "").strip() and
                                                   ((md.get("source_url") or "").strip() or (md.get("identifier") or "").strip())):
        issues.append({"level": "error", "message": "Verified datasets need a publisher and a source URL or identifier."})
    if not (md.get("name") or "").strip():
        issues.append({"level": "error", "message": "Dataset name is required."})
    if need_body and md.get("body") not in ("earth", "moon", "mars"):
        issues.append({"level": "error", "message": "Choose the body the data describe (earth, moon or mars)."})
    return issues


def _report(kind, issues, n_records=0, n_valid=0, extra=None):
    ok = not any(i["level"] == "error" for i in issues)
    return {"kind": kind, "ok": ok, "n_records": n_records, "n_valid": n_valid if ok else 0, "n_rejected": 0,
            "issues": issues, "records": {}, "completeness": 1.0 if ok else 0, **(extra or {})}


def _validate_raster(conn, s, mapping, md):
    rm = mapping.get("raster") or {}
    issues = _base_md_issues(md, True)
    info = s["structure"]["raster"]
    if md.get("data_class") == "reference":
        issues.append({"level": "error", "message": "Rasters produce measurements; choose 'verified' or 'demo'."})
    if rm.get("raster_kind") not in R.RASTER_KINDS:
        issues.append({"level": "error", "message": "Choose what the raster contains: 'elevation' (DEM) or 'scalar' (single variable)."})
    canonical = "m"
    if rm.get("raster_kind") == "scalar":
        v = VARIABLE_BY_KEY.get(rm.get("variable") or "")
        if not v or v.value_type != "numeric" or v.family == "operational":
            issues.append({"level": "error", "message": "Scalar rasters must be mapped to a numeric EarthTwin variable."})
        else:
            canonical = v.unit_kind
    from ..services import units as U
    try:
        U.normalize(1.0, rm.get("unit"), canonical)
    except U.UnitError as e:
        issues.append({"level": "error", "message": f"Raster unit: {e}"})
    if not info.get("crs") and not rm.get("declared_crs"):
        issues.append({"level": "error", "message": "The GeoTIFF has no embedded CRS: declare it (e.g. EPSG:4326, IAU_2015:30100, IAU_2015:49900)."})
    crs_body = info.get("detected_body")
    if rm.get("declared_crs") and not info.get("crs"):
        try:
            crs_body = R.body_of_crs(R._pyproj_crs(rm["declared_crs"]))
        except Exception as e:
            issues.append({"level": "error", "message": f"Declared CRS is not valid: {e}"})
    if md.get("body") and crs_body and crs_body != md["body"]:
        issues.append({"level": "error", "message": f"Raster CRS belongs to {crs_body}, but the dataset is declared as {md['body']}."})
    if info.get("count", 0) > 1:
        issues.append({"level": "warning", "message": f"Raster has {info['count']} bands; only band 1 is processed."})
    n_in = 0
    if md.get("body") in ("earth", "moon", "mars") and info.get("crs"):
        n_in = len(_subjects_for_body(conn, md["body"]))
    return _report("raster", issues, n_records=n_in, n_valid=n_in,
                   extra={"note": f"{n_in} {'Earth sites' if md.get('body') == 'earth' else 'target regions'} will be checked against the raster coverage."})


def _validate_layer(s, mapping, md):
    lm = mapping.get("layer") or {}
    issues = _base_md_issues(md, True)
    if not (lm.get("name") or md.get("name")):
        issues.append({"level": "error", "message": "Layer name is required."})
    try:
        _, rows, info = _load_table(Path(s["stored_path"]), "geojson")
    except T.AdapterError as e:
        issues.append({"level": "error", "message": str(e)})
        return _report("map_layer", issues)
    lc = info.get("legacy_crs_member")
    if lc:
        issues.append({"level": "warning", "message": "The legacy GeoJSON 'crs' member is ignored; coordinates must be lon/lat in the body's geographic CRS (RFC 7946)."})
    return _report("map_layer", issues, n_records=len(rows), n_valid=len(rows),
                   extra={"geometry_types": info.get("geometry_types")})


def _validate_bundle(conn, path: Path, md: dict):
    doc = json.loads(path.read_bytes().decode("utf-8-sig"))
    issues = []
    if str(doc.get("earthtwin_bundle")) != "1.0":
        issues.append({"level": "error", "message": f"Unsupported bundle version {doc.get('earthtwin_bundle')!r} (expected '1.0')."})
    opts = doc.get("options") or {}
    existing = _existing_subjects(conn)
    records = {"earth_sites": [], "target_regions": [], "observations": []}
    reports = []
    for kind, key, fields in (("earth_sites", "earth_sites", list(M.FIELDS["earth_sites"])),
                              ("target_regions", "target_regions", list(M.FIELDS["target_regions"]))):
        items = doc.get(key) or []
        if not items:
            continue
        cols = sorted({k for it in items for k in it})
        mp = {"fields": {f: f for f in fields if f in cols}, "variables": [], "options": {**opts}}
        rep = M.validate(kind, items, cols, mp, md, existing)
        for i in rep["issues"]:
            i["section"] = key
        reports.append(rep)
        records[key] = rep["records"][key]
        st = "earth_site" if kind == "earth_sites" else "target_region"
        for r in records[key]:
            existing[st][r["id"]] = r["name"] if st == "earth_site" else (r["name"], r["world_id"])
    obs = doc.get("observations") or []
    for st in ("earth_site", "target_region"):
        items = [o for o in obs if o.get("subject_type") == st]
        if not items:
            continue
        cols = sorted({k for it in items for k in it})
        mp = {"fields": {"subject": "subject_id", "variable": "variable", "value": "value",
                         **{f: f for f in ("unit", "method", "uncertainty", "observed_start", "observed_end", "notes") if f in cols}},
              "options": {"subject_type": st, "match_by": "id"}}
        rep = M.validate("observations_long", items, cols, mp, md, existing)
        for i in rep["issues"]:
            i["section"] = f"observations ({st})"
        reports.append(rep)
        records["observations"] += rep["records"]["observations"]
    bad_st = [o for o in obs if o.get("subject_type") not in ("earth_site", "target_region")]
    if bad_st:
        issues.append({"level": "error", "message": f"{len(bad_st)} observations have an invalid subject_type (use earth_site or target_region)."})
    cits = doc.get("citations") or []
    for c in cits:
        if not isinstance(c, dict) or not str(c.get("text", "")).strip():
            issues.append({"level": "error", "message": "Every citation needs a non-empty 'text'."})
            break
    if not reports and not cits:
        issues.append({"level": "error", "message": "Bundle contains no records."})
    if md.get("data_class") == "reference" and obs:
        issues.append({"level": "error", "message": "'reference' datasets hold catalogue records only; measurements must be 'verified' or 'demo'."})
    for rep in reports:
        issues += rep["issues"]
    n_records = sum(r["n_records"] for r in reports)
    n_rejected = sum(r["n_rejected"] for r in reports)
    blocking = any(i["level"] == "error" and "row" not in i for i in issues)
    return {"kind": "bundle", "ok": not blocking and (n_records - n_rejected > 0 or bool(cits)), "n_records": n_records,
            "n_valid": 0 if blocking else n_records - n_rejected, "n_rejected": n_rejected, "issues": issues,
            "completeness": round((n_records - n_rejected) / n_records, 3) if n_records else 1.0,
            "observations_by_variable": {k: sum(1 for o in records["observations"] if o["variable_key"] == k)
                                         for k in {o["variable_key"] for o in records["observations"]}},
            "records": records, "citations": cits, "unused_columns": []}


# --------------------------------------------------------------------------- 3. processing
def start_processing(sid: str, wait: bool = False) -> dict:
    with session() as conn:
        s = _session(conn, sid)
        if s["status"] != "validated":
            raise ImportError_("The import must pass validation before processing (current status: %s)." % s["status"])
        jid = new_id()
        conn.execute("INSERT INTO analysis_job(id, kind, status, import_id, log, created_at) VALUES (?,?,?,?,?,?)",
                     (jid, "import", "queued", sid, "[]", now()))
        conn.execute("UPDATE import_session SET status='processing', job_id=?, updated_at=? WHERE id=?", (jid, now(), sid))
    t = threading.Thread(target=_run_job, args=(jid, sid), daemon=True)
    t.start()
    if wait:
        t.join()
    with session() as conn:
        return job(conn, jid)


def job(conn, jid: str) -> dict:
    j = row(conn.execute("SELECT * FROM analysis_job WHERE id = ?", (jid,)).fetchone())
    if not j:
        raise ImportError_(f"Job {jid} not found")
    j["log"] = LIVE_LOGS.get(jid) or loads(j["log"], [])
    j["result"] = loads(j["result"])
    return j


LIVE_LOGS: dict[str, list[dict]] = {}


def _run_job(jid: str, sid: str) -> None:
    # The log is kept in memory while the data transaction is open (a second
    # writer would block on SQLite's lock) and exposed live via LIVE_LOGS.
    log: list[dict] = LIVE_LOGS.setdefault(jid, [])

    def L(step, detail=""):
        log.append({"at": now(), "step": step, "detail": detail})

    with session() as c:
        c.execute("UPDATE analysis_job SET status='running', started_at=? WHERE id=?", (now(), jid))
    try:
        L("start", "Processing started")
        with session() as conn:
            s = _session(conn, sid)
            result = _process(conn, s, L)
            conn.execute("UPDATE analysis_job SET status='succeeded', dataset_id=?, result=?, log=?, finished_at=? WHERE id=?",
                         (result["dataset_id"], dumps(result), dumps(log + [{"at": now(), "step": "done", "detail": "Committed"}]), now(), jid))
            conn.execute("UPDATE import_session SET status='completed', dataset_id=?, updated_at=? WHERE id=?", (result["dataset_id"], now(), sid))
            bump_revision(conn)
    except Exception as e:  # any failure rolls back the data transaction above
        detail = str(e) if isinstance(e, (ValueError, R.RasterError)) else f"{type(e).__name__}: {e}"
        log.append({"at": now(), "step": "failed", "detail": detail})
        log.append({"at": now(), "step": "trace", "detail": traceback.format_exc(limit=3)[-1500:]})
        with session() as c:
            c.execute("UPDATE analysis_job SET status='failed', error=?, log=?, finished_at=? WHERE id=?", (detail, dumps(log), now(), jid))
            c.execute("UPDATE import_session SET status='failed', updated_at=? WHERE id=?", (now(), sid))
            bump_revision(c)
    finally:
        LIVE_LOGS.pop(jid, None)


def _subjects_for_body(conn, body: str) -> list[dict]:
    if body == "earth":
        return [dict(r, subject_type="earth_site") for r in conn.execute("SELECT id, name, lat, lon, analysis_radius_km FROM earth_site")]
    return [dict(r, subject_type="target_region") for r in conn.execute(
        "SELECT id, name, lat, lon, analysis_radius_km FROM target_region WHERE world_id = ?", (body,))]


def _upsert_dataset(conn, s: dict, md: dict, data_type: str, file_format: str, extra_units: dict | None = None) -> tuple[str, str, str]:
    ts = now()
    did = md.get("dataset_id")
    fields = dict(name=md["name"].strip()[:200], identifier=md.get("identifier") or None, publisher=md.get("publisher") or None,
                  source_url=md.get("source_url") or None, file_format=file_format, data_type=data_type, body=md.get("body") or None,
                  crs=md.get("crs") or None, temporal_coverage=md.get("temporal_coverage") or None,
                  spatial_resolution=md.get("spatial_resolution") or None, license=md.get("license") or None,
                  provenance=md.get("provenance") or None, description=md.get("description") or None, data_class=md["data_class"],
                  units=dumps(extra_units or {}))
    if did:
        conn.execute(f"UPDATE dataset SET {', '.join(f'{k}=?' for k in fields)}, status='processing', updated_at=? WHERE id=?",
                     (*fields.values(), ts, did))
        n = conn.execute("SELECT COUNT(*) FROM dataset_version WHERE dataset_id = ?", (did,)).fetchone()[0]
        version = md.get("version") or f"v{n + 1}"
    else:
        did = new_id()
        conn.execute(f"INSERT INTO dataset(id, {', '.join(fields)}, status, active, created_at, updated_at) "
                     f"VALUES (?, {', '.join('?' * len(fields))}, 'processing', 0, ?, ?)", (did, *fields.values(), ts, ts))
        version = md.get("version") or "v1"
    vid = new_id()
    st = get_settings()
    keep = st.upload_dir / "datasets" / did
    keep.mkdir(parents=True, exist_ok=True)
    stored = keep / f"{vid}{Path(s['stored_path']).suffix}"
    shutil.copyfile(s["stored_path"], stored)
    conn.execute("""INSERT INTO dataset_version(id, dataset_id, version, original_filename, stored_path, sha256, size_bytes,
                    field_mapping, processing_history, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (vid, did, version, s["original_filename"], str(stored), s["sha256"], s["size_bytes"],
                  dumps(s["confirmed_mapping"] or {}), "[]", ts))
    return did, vid, version


def _insert_observations(conn, vid: str, obs: list[dict], data_class: str, md: dict) -> int:
    ts = now()
    for o in obs:
        v = VARIABLE_BY_KEY[o["variable_key"]]
        num = o["value"] if v.value_type == "numeric" else None
        txt = None if v.value_type == "numeric" else dumps(o["value"])
        conn.execute("""INSERT INTO observation(id, dataset_version_id, subject_type, subject_id, variable_key, value_num, value_text,
                        unit, original_value, original_unit, data_class, method, uncertainty, spatial_support, observed_start,
                        observed_end, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (new_id(), vid, o["subject_type"], o["subject_id"], o["variable_key"], num, txt, o.get("unit"),
                      o.get("original_value"), o.get("original_unit"), o.get("data_class", data_class),
                      o.get("method") or md.get("method") or f"Imported from '{md['name']}'", o.get("uncertainty"),
                      o.get("spatial_support"), o.get("observed_start") or None, o.get("observed_end") or None, o.get("notes"), ts))
    return len(obs)


def _upsert_records(conn, did: str, kind: str, recs: list[dict], data_class: str) -> tuple[int, int]:
    created = updated = 0
    ts = now()
    table = "earth_site" if kind == "earth_sites" else "target_region"
    list_fields = {"categories", "applications", "limitations", "future_work", "tags"}
    for r in recs:
        r = dict(r)
        rid = r.pop("id")
        cols = {k: (dumps(v) if k in list_fields or k == "extra" else v) for k, v in r.items()}
        if table == "target_region":
            cols["crs"] = "IAU_2015:30100" if r["world_id"] == "moon" else "IAU_2015:49900"
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (rid,)).fetchone()
        if exists:
            conn.execute(f"UPDATE {table} SET {', '.join(f'{k}=?' for k in cols)}, updated_at=? WHERE id=?", (*cols.values(), ts, rid))
            updated += 1
        else:
            cols.update(source_dataset_id=did, data_class=data_class)
            conn.execute(f"INSERT INTO {table}(id, {', '.join(cols)}, created_at, updated_at) VALUES (?, {', '.join('?' * len(cols))}, ?, ?)",
                         (rid, *cols.values(), ts, ts))
            created += 1
    return created, updated


def _process(conn, s: dict, L) -> dict:
    kind, md, mapping = s["import_kind"], s["metadata"], s["confirmed_mapping"] or {}
    L("revalidate", "Re-running validation against current database state")
    report = run_validation(conn, s, kind, mapping, md)
    if not report["ok"]:
        errs = [i["message"] for i in report["issues"] if i["level"] == "error"][:5]
        raise ValueError("Validation failed: " + "; ".join(errs))
    data_class = md["data_class"]
    result: dict = {"kind": kind}
    fmt = s["detected_format"]
    if kind == "raster":
        did, vid, version = _upsert_dataset(conn, s, md, "raster", "geotiff")
        rm = mapping["raster"]
        subjects = _subjects_for_body(conn, md["body"])
        L("feature_extraction", f"{rm['raster_kind']} raster; {len(subjects)} candidate subjects on {md['body']}")
        feats, issues = R.extract(Path(s["stored_path"]), md["body"], rm["raster_kind"], rm["unit"], subjects,
                                  variable_key=rm.get("variable"), declared_crs=rm.get("declared_crs"), log=lambda m: L("raster", m))
        derived_class = "derived" if data_class == "verified" else "demo"
        for f in feats:
            f["data_class"] = derived_class
            f["original_value"] = None
            f["original_unit"] = rm["unit"]
        n = _insert_observations(conn, vid, feats, derived_class, md)
        covered = len({(f["subject_type"], f["subject_id"]) for f in feats})
        L("features", f"{n} derived values for {covered} subjects; {len(issues)} warnings")
        report["issues"] = issues
        report["n_records"], report["n_valid"] = len(subjects), covered
        report["completeness"] = round(covered / len(subjects), 3) if subjects else 0
        result.update(observations=n, subjects_covered=covered, subjects_checked=len(subjects))
        if covered == 0:
            L("warning", "No subject falls inside the raster coverage with sufficient valid pixels")
    elif kind == "map_layer":
        did, vid, version = _upsert_dataset(conn, s, md, "map_layer", "geojson")
        lm = mapping.get("layer") or {}
        dest = get_settings().layer_dir / f"{vid}.geojson"
        doc = json.loads(Path(s["stored_path"]).read_bytes().decode("utf-8-sig"))
        doc.pop("crs", None)
        dest.write_text(json.dumps(doc), encoding="utf-8")
        conn.execute("""INSERT INTO map_layer(id, dataset_id, name, body, kind, geojson_path, legend, attribution, feature_count, created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     (new_id(), did, (lm.get("name") or md["name"])[:200], md["body"], "vector", str(dest),
                      dumps({"color": lm.get("color") or "#38bdf8", "label_property": lm.get("label_property")}),
                      md.get("publisher") or md["name"], len(doc.get("features", [])), now()))
        L("layer", f"Map layer stored with {len(doc.get('features', []))} features")
        result.update(features=len(doc.get("features", [])))
    else:
        dtype = {"earth_sites": "site_records", "target_regions": "target_records"}.get(kind, "observations")
        did, vid, version = _upsert_dataset(conn, s, md, dtype if kind != "bundle" else "bundle", fmt)
        recs = report["records"]
        c1, u1 = _upsert_records(conn, did, "earth_sites", recs.get("earth_sites", []), data_class)
        c2, u2 = _upsert_records(conn, did, "target_regions", recs.get("target_regions", []), data_class)
        L("records", f"Earth sites: {c1} created, {u1} updated; target regions: {c2} created, {u2} updated")
        n = _insert_observations(conn, vid, recs.get("observations", []), data_class, md)
        L("observations", f"{n} measurements stored ({data_class})")
        for c in report.get("citations", []) or []:
            conn.execute("""INSERT INTO citation(id, dataset_id, subject_type, subject_id, text, url, doi, kind, verification, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (new_id(), did, c.get("subject_type"), c.get("subject_id"), str(c["text"])[:2000], c.get("url"), c.get("doi"),
                          c.get("kind") or "reference", c.get("verification") or "unverified", now()))
        result.update(sites_created=c1, sites_updated=u1, targets_created=c2, targets_updated=u2, observations=n)
    if (md.get("citation_text") or "").strip():
        conn.execute("DELETE FROM citation WHERE dataset_id = ? AND kind = 'dataset'", (did,))
        conn.execute("INSERT INTO citation(id, dataset_id, text, url, doi, kind, verification, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (new_id(), did, md["citation_text"].strip()[:2000], md.get("source_url") or None, md.get("citation_doi") or None,
                      "dataset", "team_verified" if data_class == "verified" else "unverified", now()))
    issues = report.get("issues", [])
    conn.execute("""INSERT INTO data_quality_assessment(id, dataset_version_id, import_id, n_records, n_valid, n_rejected, completeness,
                    issues, summary, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (new_id(), vid, s["id"], report.get("n_records"), report.get("n_valid"), report.get("n_rejected", 0),
                  report.get("completeness"), dumps(issues[:1000]),
                  f"{report.get('n_valid')} of {report.get('n_records')} records valid; "
                  f"{sum(1 for i in issues if i['level'] == 'warning')} warnings; "
                  f"{sum(1 for i in issues if i['level'] == 'error')} rejected values/rows", now()))
    history = [{"at": now(), "step": "import", "detail": f"{kind} from {s['original_filename']} (sha256 {s['sha256'][:12]}…)"},
               {"at": now(), "step": "validated", "detail": f"{report.get('n_valid')} valid / {report.get('n_records')}"},
               {"at": now(), "step": "processed", "detail": json.dumps(result)}]
    conn.execute("UPDATE dataset_version SET processing_history=? WHERE id=?", (dumps(history), vid))
    active = 1 if md.get("activate", True) else 0
    conn.execute("UPDATE dataset SET status='ready', active=?, current_version_id=?, updated_at=? WHERE id=?", (active, vid, now(), did))
    L("activate", "Dataset activated" if active else "Dataset stored but left inactive")
    result.update(dataset_id=did, version_id=vid, version=version, active=bool(active))
    return result


# --------------------------------------------------------------------------- programmatic import (seed, tests)
def import_file(path: Path, kind: str | None, mapping: dict | None, metadata: dict) -> dict:
    with open(path, "rb") as f:
        s = create_session(f, path.name, kind)
    s = set_mapping(s["id"], kind or s["import_kind"], mapping or s["proposed_mapping"], metadata)
    if s["status"] != "validated":
        raise ImportError_(f"Validation failed for {path.name}: " +
                           "; ".join(i["message"] for i in s["validation"]["issues"] if i["level"] == "error"))
    j = start_processing(s["id"], wait=True)
    if j["status"] != "succeeded":
        raise ImportError_(f"Processing failed for {path.name}: {j['error']}")
    return j
