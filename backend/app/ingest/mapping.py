"""Field-mapping proposal and record validation/normalisation.

`propose()` suggests how source columns map onto the EarthTwin data model and
marks every suggestion with a confidence. Units and coordinate conventions are
only *suggested* from headers; validation refuses to proceed until a unit is
confirmed for every numeric variable column.

`validate()` turns rows + a confirmed mapping into normalised records and a
data-quality report. It never writes to the database.
"""
from __future__ import annotations

import math
import re
from typing import Any

from ..services import units as U
from ..services.vocabulary import ACCESS_LEVELS, LITHOLOGY_TERMS, SITE_CATEGORIES, VARIABLE_BY_KEY, VARIABLES
from .adapters.tabular import GEOM_LAT, GEOM_LON

KINDS = {
    "earth_sites": "Earth analog site records (optionally with measurement columns)",
    "target_regions": "Moon / Mars target-region records (optionally with measurement columns)",
    "observations": "Measurements for existing sites or targets, one row per subject, one column per variable",
    "observations_long": "Measurements in long format: subject, variable, value, unit",
    "map_layer": "GeoJSON overlay shown on the Earth or planetary map",
    "raster": "GeoTIFF raster processed into features for sites/targets within its coverage",
    "bundle": "EarthTwin bundle JSON",
}

FIELDS = {
    "earth_sites": {
        "id": ["id", "site_id", "code", "slug"], "name": ["name", "site", "site_name", "location", "title"],
        "lat": ["lat", "latitude", "y", GEOM_LAT], "lon": ["lon", "long", "lng", "longitude", "x", GEOM_LON],
        "country": ["country", "nation"], "region": ["region", "state", "province", "area"],
        "categories": ["categories", "category", "analog_type", "environment", "type"],
        "terrain_type": ["terrain_type", "terrain", "landform"], "description": ["description", "summary", "desc", "notes"],
        "geologic_context": ["geologic_context", "geology_context", "geological_context", "geology_notes"],
        "analog_heritage": ["analog_heritage_text", "heritage_notes", "analog_history"],
        "applications": ["applications", "uses", "research_applications"], "limitations": ["limitations", "constraints"],
        "future_work": ["future_work", "future_investigations"], "analysis_radius_km": ["analysis_radius_km", "radius_km", "window_km"],
    },
    "target_regions": {
        "id": ["id", "target_id", "region_id", "code", "slug"], "name": ["name", "target", "region", "site", "title"],
        "body": ["body", "world", "planet"], "lat": ["lat", "latitude", GEOM_LAT], "lon": ["lon", "long", "longitude", GEOM_LON],
        "region_type": ["region_type", "type", "terrain"], "description": ["description", "summary"],
        "geologic_context": ["geologic_context", "geology", "geological_context"], "mission_relevance": ["mission_relevance", "relevance"],
        "tags": ["tags", "keywords"], "analysis_radius_km": ["analysis_radius_km", "radius_km", "window_km"],
    },
    "observations": {"subject": ["site_id", "target_id", "id", "subject_id", "name", "site", "site_name"]},
    "observations_long": {
        "subject": ["subject_id", "site_id", "target_id", "id", "name"], "variable": ["variable", "variable_key", "parameter", "quantity"],
        "value": ["value", "val", "measurement"], "unit": ["unit", "units", "uom"],
        "method": ["method", "instrument", "algorithm"], "uncertainty": ["uncertainty", "error", "sigma", "std_error"],
        "observed_start": ["observed_start", "start", "date_start", "date"], "observed_end": ["observed_end", "end", "date_end"],
        "notes": ["notes", "comment", "remarks"], "subject_type": ["subject_type"],
    },
}
REQUIRED = {
    "earth_sites": ["name", "lat", "lon"], "target_regions": ["name", "lat", "lon"],
    "observations": ["subject"], "observations_long": ["subject", "variable", "value"],
}
LON_CONVENTIONS = {
    "east_180": "East-positive, −180…180 (WGS 84 / IAU planetocentric standard)",
    "east_360": "East-positive, 0…360",
    "west_360": "West-positive, 0…360 (older Mars products)",
}
LAT_TYPES = {"planetocentric": "Planetocentric", "planetographic": "Planetographic (Mars only; converted using IAU 2000 ellipsoid)"}
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--", "missing", "?"}
TRUE_TOKENS = {"true", "yes", "y", "1", "present", "confirmed", "t"}
FALSE_TOKENS = {"false", "no", "n", "0", "absent", "none_observed", "f"}
MARS_A, MARS_B = 3396.19, 3376.20  # km, IAU 2000 Mars ellipsoid


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:80] or "record"


def is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip().lower() in MISSING_TOKENS)


def parse_float(v) -> float:
    if isinstance(v, bool):
        raise ValueError("boolean is not a number")
    if isinstance(v, (int, float)):
        f = float(v)
    else:
        f = float(str(v).strip().replace("−", "-"))
    if not math.isfinite(f):
        raise ValueError("not finite")
    return f


def parse_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in TRUE_TOKENS:
        return True
    if t in FALSE_TOKENS:
        return False
    raise ValueError(f"'{v}' is not a recognised yes/no value")


def parse_list(v, sep: str | None = None) -> list[str]:
    if isinstance(v, list):
        items = v
    else:
        items = re.split(sep if sep else r"[;|,]", str(v))
    return [i.strip() for i in items if str(i).strip()]


def _strip_unit_suffix(h: str) -> str:
    h = re.sub(r"\(.*?\)|\[.*?\]", "", h)
    h = norm(h)
    for suf in ("_mm_per_yr", "_mm_yr", "_mmyr", "_cm_yr", "_deg_c", "_degc", "_celsius", "_kelvin", "_degrees",
                "_deg", "_rad", "_km", "_m", "_ft", "_pct", "_percent", "_fraction", "_k", "_c", "_f"):
        if h.endswith(suf) and len(h) > len(suf):
            return h[: -len(suf)]
    return h


def match_variable(header: str) -> tuple[str | None, str]:
    h = norm(header)
    if h in VARIABLE_BY_KEY:
        return h, "high"
    base = _strip_unit_suffix(header)
    for v in VARIABLES:
        if base == v.key or base in v.aliases or h in v.aliases:
            return v.key, "medium"
    for v in VARIABLES:
        if any(a in base for a in v.aliases if len(a) > 4):
            return v.key, "low"
    return None, "none"


def propose(kind: str, columns: list[str], rows: list[dict]) -> dict:
    """Suggest a mapping. Every entry carries a confidence; nothing is auto-confirmed."""
    fields = FIELDS.get(kind, {})
    used: set[str] = set()
    fmap, fconf = {}, {}
    ncols = {c: norm(c) for c in columns}
    for f, aliases in fields.items():
        for a in aliases:
            hit = next((c for c in columns if c not in used and (c == a or ncols[c] == norm(a))), None)
            if hit:
                fmap[f], fconf[f] = hit, "high" if ncols[hit] == f or hit == f else "medium"
                used.add(hit)
                break
    variables = []
    if kind in ("earth_sites", "target_regions", "observations"):
        for c in columns:
            if c in used:
                continue
            key, conf = match_variable(c)
            if key:
                v = VARIABLE_BY_KEY[key]
                hint = U.unit_hint_from_header(c) if v.value_type == "numeric" else None
                variables.append({"column": c, "variable": key, "confidence": conf,
                                  "unit": hint, "unit_source": "header" if hint else None,
                                  "unit_required": v.value_type == "numeric"})
                used.add(c)
    unmapped = [c for c in columns if c not in used]
    missing_required = [f for f in REQUIRED.get(kind, []) if f not in fmap]
    return {"kind": kind, "fields": fmap, "field_confidence": fconf, "variables": variables,
            "unmapped_columns": unmapped, "missing_required": missing_required,
            "needs_review": bool(missing_required or any(v["confidence"] != "high" or (v["unit_required"] and not v["unit"]) for v in variables)
                                 or any(c != "high" for c in fconf.values()))}


def convert_coords(lat: float, lon: float, body: str, lon_conv: str, lat_type: str) -> tuple[float, float]:
    if not -90 <= lat <= 90:
        raise ValueError(f"latitude {lat} outside −90…90")
    if lon_conv == "east_180":
        if not -180 <= lon <= 180:
            raise ValueError(f"longitude {lon} outside −180…180 (declared convention east_180)")
    elif lon_conv == "east_360":
        if not 0 <= lon <= 360:
            raise ValueError(f"longitude {lon} outside 0…360 (declared convention east_360)")
        lon = lon - 360 if lon > 180 else lon
    elif lon_conv == "west_360":
        if not 0 <= lon <= 360:
            raise ValueError(f"longitude {lon} outside 0…360 (declared convention west_360)")
        lon = -lon
        lon = lon + 360 if lon < -180 else lon
    else:
        raise ValueError(f"unknown longitude convention {lon_conv}")
    if lat_type == "planetographic":
        if body != "mars":
            raise ValueError("planetographic latitude conversion is only defined here for Mars")
        if abs(lat) < 90:
            lat = math.degrees(math.atan((MARS_B / MARS_A) ** 2 * math.tan(math.radians(lat))))
    elif lat_type != "planetocentric":
        raise ValueError(f"unknown latitude type {lat_type}")
    return round(lat, 6), round(lon, 6)


def parse_variable_value(key: str, raw: Any, unit: str | None, sep: str | None, issues: list, ctx: dict):
    """Return (value, canonical_unit) or raise ValueError."""
    v = VARIABLE_BY_KEY[key]
    if v.value_type == "numeric":
        num = parse_float(raw)
        val, cu = U.normalize(num, unit, v.unit_kind)
        if key == "vegetation_fraction" and not 0 <= val <= 1:
            raise ValueError(f"vegetation fraction {val:g} outside 0…1 after unit conversion")
        if key in ("mean_slope_deg", "slope_std_deg") and not 0 <= val <= 90:
            raise ValueError(f"slope {val:g}° outside 0…90")
        if key == "mean_surface_temp_k" and not 0 < val < 1000:
            raise ValueError(f"temperature {val:g} K is not physically plausible")
        if key in ("local_relief_m", "annual_precip_mm", "surface_temp_range_k") and val < 0:
            raise ValueError("value cannot be negative")
        return val, cu
    if v.value_type == "boolean":
        return parse_bool(raw), None
    if v.value_type == "ordinal":
        t = str(raw).strip().lower()
        if t not in v.allowed_values:
            raise ValueError(f"'{raw}' not in allowed values {v.allowed_values}")
        return t, None
    if v.value_type == "categorical_set":
        terms = [norm(x) for x in parse_list(raw, sep)]
        unknown = [t for t in terms if t not in LITHOLOGY_TERMS]
        if unknown:
            issues.append({"level": "warning", **ctx, "message": f"Lithology terms not in the controlled vocabulary were kept "
                           f"but cannot match target terms: {', '.join(unknown)}"})
        if not terms:
            raise ValueError("empty term list")
        return sorted(set(terms)), None
    raise ValueError(f"unsupported value type {v.value_type}")


def validate(kind: str, rows: list[dict], columns: list[str], mapping: dict, metadata: dict, existing: dict) -> dict:
    """Validate rows against a mapping.

    existing = {"earth_site": {id: name}, "target_region": {id: (name, world)}} for subject resolution.
    Returns a report with normalised `records`.
    """
    issues: list[dict] = []
    fields = mapping.get("fields", {}) or {}
    variables = [v for v in (mapping.get("variables") or []) if v.get("variable")]
    options = mapping.get("options", {}) or {}
    sep = options.get("list_separator") or None
    data_class = metadata.get("data_class")
    body = metadata.get("body")

    def err(msg, **ctx):
        issues.append({"level": "error", **ctx, "message": msg})

    # ---- metadata checks (provenance) ------------------------------------
    if data_class not in ("verified", "demo", "reference"):
        err("Choose a data class: 'verified' (from an identified source dataset), 'demo' (illustrative test values) "
            "or 'reference' (catalogue records without measurements).")
    if data_class == "reference" and (variables or kind in ("observations", "observations_long")):
        err("'reference' datasets hold catalogue records only; measurements must be 'verified' or 'demo'.")
    if data_class == "verified":
        if not (metadata.get("publisher") or "").strip():
            err("Verified datasets need a publishing organisation.")
        if not ((metadata.get("source_url") or "").strip() or (metadata.get("identifier") or "").strip()):
            err("Verified datasets need a source URL or a dataset identifier/DOI.")
    if not (metadata.get("name") or "").strip():
        err("Dataset name is required.")

    # ---- mapping checks ----------------------------------------------------
    for f in REQUIRED.get(kind, []):
        if f not in fields or fields[f] not in columns:
            if not (kind == "target_regions" and f == "body"):
                err(f"Required field '{f}' is not mapped to a column.")
    seen_cols = {}
    for f, c in fields.items():
        if c and c not in columns:
            err(f"Mapped column '{c}' (for {f}) does not exist in the file.")
        if c:
            seen_cols.setdefault(c, []).append(f)
    for v in variables:
        if v["column"] not in columns:
            err(f"Mapped column '{v['column']}' does not exist in the file.")
        if v["variable"] not in VARIABLE_BY_KEY:
            err(f"Unknown variable '{v['variable']}' for column '{v['column']}'.")
            continue
        var = VARIABLE_BY_KEY[v["variable"]]
        if var.value_type == "numeric":
            if not v.get("unit"):
                err(f"Column '{v['column']}' → {var.name}: unit is required (accepted: {', '.join(U.accepted_units(var.unit_kind))}).",
                    column=v["column"])
            else:
                try:
                    U.normalize(1.0, v["unit"], var.unit_kind)
                except U.UnitError as e:
                    err(f"Column '{v['column']}': {e}", column=v["column"])
        seen_cols.setdefault(v["column"], []).append(v["variable"])
    for c, targets in seen_cols.items():
        if len(targets) > 1:
            err(f"Column '{c}' is mapped more than once ({', '.join(targets)}).")
    var_keys = [v["variable"] for v in variables]
    for k in {k for k in var_keys if var_keys.count(k) > 1}:
        err(f"Variable '{k}' is mapped from more than one column.")

    if kind == "target_regions":
        if not body and "body" not in fields:
            err("Target regions need a body: set it in the dataset metadata (moon/mars) or map a 'body' column.")
        if options.get("lon_convention") not in LON_CONVENTIONS:
            err("Choose the longitude convention used in the file (east_180, east_360 or west_360). It is never assumed.")
        if options.get("lat_type") not in LAT_TYPES:
            err("Choose the latitude type (planetocentric or planetographic). It is never assumed.")
    if kind == "earth_sites":
        crs = (metadata.get("crs") or "EPSG:4326").upper().replace(" ", "")
        if crs not in ("EPSG:4326", "WGS84", "OGC:CRS84", "CRS84"):
            err(f"Earth site coordinates must be WGS 84 geographic (EPSG:4326); '{metadata.get('crs')}' is not supported. "
                "Reproject the coordinates first.")
    if kind == "observations" and not variables:
        err("No measurement columns are mapped to EarthTwin variables.")
    if kind in ("observations", "observations_long"):
        st = options.get("subject_type")
        if st not in ("earth_site", "target_region"):
            err("Choose whether the rows describe Earth sites or target regions (subject type).")
        if options.get("match_by") not in ("id", "name"):
            err("Choose how rows are matched to existing records: by id or by exact name.")

    report = {"kind": kind, "n_records": len(rows), "issues": issues}
    if any(i["level"] == "error" for i in issues):
        return _finish(report, [], [], [], columns, fields, variables)

    sites, targets, obs = [], [], []
    ids_seen: set[str] = set()
    lon_conv = options.get("lon_convention", "east_180")
    lat_type = options.get("lat_type", "planetocentric")
    for i, r in enumerate(rows, start=1):
        ctx = {"row": i}
        rec: dict[str, Any] = {}
        subject = None
        try:
            if kind in ("earth_sites", "target_regions"):
                name = r.get(fields.get("name"), "")
                if is_missing(name):
                    raise ValueError("name is empty")
                rec["name"] = str(name).strip()[:200]
                rid = r.get(fields["id"]) if fields.get("id") else None
                rec["id"] = slug(rid) if not is_missing(rid) else slug(rec["name"])
                if rec["id"] in ids_seen:
                    raise ValueError(f"duplicate id '{rec['id']}' in file")
                lat_raw, lon_raw = r.get(fields["lat"]), r.get(fields["lon"])
                if is_missing(lat_raw) or is_missing(lon_raw):
                    raise ValueError("latitude/longitude missing")
                lat, lon = parse_float(lat_raw), parse_float(lon_raw)
                if kind == "earth_sites":
                    rec["lat"], rec["lon"] = convert_coords(lat, lon, "earth", "east_180", "planetocentric")
                    for f in ("country", "region", "terrain_type", "description", "geologic_context", "analog_heritage"):
                        if fields.get(f) and not is_missing(r.get(fields[f])):
                            rec[f] = str(r[fields[f]]).strip()[:4000]
                    for f in ("applications", "limitations", "future_work"):
                        if fields.get(f) and not is_missing(r.get(fields[f])):
                            rec[f] = parse_list(r[fields[f]], sep or r"[;|]")
                    if fields.get("categories") and not is_missing(r.get(fields["categories"])):
                        cats = [norm(c) for c in parse_list(r[fields["categories"]], sep)]
                        bad = [c for c in cats if c not in SITE_CATEGORIES]
                        if bad:
                            issues.append({"level": "warning", **ctx, "message": f"Unknown categories kept: {', '.join(bad)} "
                                           f"(known: {', '.join(SITE_CATEGORIES)})"})
                        rec["categories"] = cats
                else:
                    b = (str(r.get(fields["body"], "")).strip().lower() if fields.get("body") else "") or (body or "")
                    if b not in ("moon", "mars"):
                        raise ValueError(f"body '{b}' must be 'moon' or 'mars'")
                    rec["world_id"] = b
                    rec["lat"], rec["lon"] = convert_coords(lat, lon, b, lon_conv, lat_type)
                    for f in ("region_type", "description", "geologic_context", "mission_relevance"):
                        if fields.get(f) and not is_missing(r.get(fields[f])):
                            rec[f] = str(r[fields[f]]).strip()[:4000]
                    if fields.get("tags") and not is_missing(r.get(fields["tags"])):
                        rec["tags"] = parse_list(r[fields["tags"]], sep)
                if fields.get("analysis_radius_km") and not is_missing(r.get(fields["analysis_radius_km"])):
                    rk = parse_float(r[fields["analysis_radius_km"]])
                    if not 0.05 <= rk <= 500:
                        raise ValueError("analysis_radius_km must be between 0.05 and 500")
                    rec["analysis_radius_km"] = rk
                mapped = set(fields.values()) | {v["column"] for v in variables}
                rec["extra"] = {c: r[c] for c in columns if c not in mapped and not is_missing(r.get(c)) and not c.startswith("_geometry")}
                subject = ("earth_site" if kind == "earth_sites" else "target_region", rec["id"])
                ids_seen.add(rec["id"])
            elif kind in ("observations", "observations_long"):
                st = options["subject_type"]
                ref = r.get(fields["subject"])
                if is_missing(ref):
                    raise ValueError("subject reference is empty")
                subject = (st, _resolve_subject(st, str(ref).strip(), options["match_by"], existing))
        except ValueError as e:
            issues.append({"level": "error", **ctx, "message": f"Row rejected: {e}"})
            continue

        row_obs = []
        if kind == "observations_long":
            try:
                key = norm(r.get(fields["variable"], ""))
                if key not in VARIABLE_BY_KEY:
                    k2, conf = match_variable(key)
                    if not k2 or conf == "low":
                        raise ValueError(f"unknown variable '{r.get(fields['variable'])}'")
                    key = k2
                raw = r.get(fields["value"])
                if is_missing(raw):
                    issues.append({"level": "info", **ctx, "message": "Missing value skipped (not treated as a match)"})
                    continue
                unit = r.get(fields["unit"]) if fields.get("unit") else None
                val, cu = parse_variable_value(key, raw, None if is_missing(unit) else str(unit), sep, issues, ctx)
                o = {"variable_key": key, "value": val, "unit": cu, "original_value": str(raw),
                     "original_unit": None if is_missing(unit) else str(unit)}
                for f in ("method", "observed_start", "observed_end", "notes"):
                    if fields.get(f) and not is_missing(r.get(fields[f])):
                        o[f] = str(r[fields[f]])[:1000]
                if fields.get("uncertainty") and not is_missing(r.get(fields["uncertainty"])):
                    o["uncertainty"] = parse_float(r[fields["uncertainty"]])
                row_obs.append(o)
            except (ValueError, U.UnitError) as e:
                issues.append({"level": "error", **ctx, "message": f"Row rejected: {e}"})
                continue
        else:
            for v in variables:
                raw = r.get(v["column"])
                if is_missing(raw):
                    continue
                try:
                    val, cu = parse_variable_value(v["variable"], raw, v.get("unit"), sep, issues, {**ctx, "column": v["column"]})
                    row_obs.append({"variable_key": v["variable"], "value": val, "unit": cu,
                                    "original_value": str(raw), "original_unit": v.get("unit")})
                except (ValueError, U.UnitError) as e:
                    issues.append({"level": "error", **ctx, "column": v["column"], "message": f"Value rejected: {e}"})
        for o in row_obs:
            o["subject_type"], o["subject_id"] = subject
            if VARIABLE_BY_KEY[o["variable_key"]].family == "operational" and o["subject_type"] == "target_region":
                issues.append({"level": "warning", **ctx, "message": f"{o['variable_key']} is an Earth-only attribute; ignored for target regions"})
                continue
            obs.append(o)
        if kind == "earth_sites":
            sites.append(rec)
        elif kind == "target_regions":
            targets.append(rec)

    return _finish(report, sites, targets, obs, columns, fields, variables)


def _resolve_subject(st: str, ref: str, match_by: str, existing: dict) -> str:
    pool = existing.get(st, {})
    if match_by == "id":
        sid = slug(ref)
        if sid in pool:
            return sid
        if ref in pool:
            return ref
        raise ValueError(f"no {st.replace('_', ' ')} with id '{ref}'")
    hits = [k for k, v in pool.items() if (v[0] if isinstance(v, tuple) else v).strip().lower() == ref.lower()]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"no {st.replace('_', ' ')} named '{ref}'")
    raise ValueError(f"name '{ref}' is ambiguous ({len(hits)} matches)")


def _finish(report, sites, targets, obs, columns, fields, variables):
    issues = report["issues"]
    rejected_rows = {i["row"] for i in issues if i["level"] == "error" and "row" in i and i["message"].startswith("Row rejected")}
    errors = [i for i in issues if i["level"] == "error"]
    blocking = [i for i in errors if "row" not in i]
    mapped = set(fields.values()) | {v["column"] for v in variables}
    unused = [c for c in columns if c not in mapped and not c.startswith("_geometry")]
    n_valid = report["n_records"] - len(rejected_rows) if not blocking else 0
    by_var: dict[str, int] = {}
    for o in obs:
        by_var[o["variable_key"]] = by_var.get(o["variable_key"], 0) + 1
    report.update({
        "ok": not blocking and n_valid > 0,
        "blocking_errors": len(blocking),
        "n_valid": n_valid, "n_rejected": len(rejected_rows),
        "n_value_errors": sum(1 for i in errors if "row" in i and not i["message"].startswith("Row rejected")),
        "n_warnings": sum(1 for i in issues if i["level"] == "warning"),
        "completeness": round(n_valid / report["n_records"], 3) if report["n_records"] else 0,
        "observations_by_variable": by_var,
        "unused_columns": unused,
        "unused_columns_note": ("Unmapped columns are preserved in each record's 'extra' field." if report["kind"] in ("earth_sites", "target_regions")
                                else "Unmapped columns are not imported as measurements; they remain in the stored original file."),
        "records": {"earth_sites": sites, "target_regions": targets, "observations": obs},
    })
    if not report["ok"] and not blocking and n_valid == 0:
        report["issues"].append({"level": "error", "message": "No valid records remain after validation."})
    return report
