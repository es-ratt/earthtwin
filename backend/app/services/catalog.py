"""Shared read services. Every page of the website reads through these
functions, so a newly imported and activated dataset is reflected everywhere."""
from __future__ import annotations

import sqlite3
from collections import defaultdict

from ..db import loads, row, rows
from .similarity import CLASS_RANK, Value
from .vocabulary import CRITERIA, VARIABLE_BY_KEY

SCORING_VARIABLES = sorted({c.variable_key for c in CRITERIA if c.family != "operational"})

_SITE_JSON = ("categories", "applications", "limitations", "future_work", "extra")
_TARGET_JSON = ("tags", "extra")


def _decode(rec: dict, keys) -> dict:
    for k in keys:
        rec[k] = loads(rec.get(k), [] if k != "extra" else {})
    return rec


def decode_value(o: dict):
    v = VARIABLE_BY_KEY.get(o["variable_key"])
    if v is None:
        return None
    if v.value_type == "numeric":
        return o["value_num"]
    return loads(o["value_text"])


def active_observations(conn: sqlite3.Connection, subject_type: str, subject_ids: list[str] | None = None,
                        include_demo: bool = True) -> list[dict]:
    q = """SELECT o.*, d.id AS dataset_id, d.name AS dataset_name, d.publisher AS dataset_publisher,
                  dv.version AS dataset_version
           FROM observation o
           JOIN dataset_version dv ON dv.id = o.dataset_version_id
           JOIN dataset d ON d.id = dv.dataset_id
           WHERE d.active = 1 AND d.current_version_id = dv.id AND o.subject_type = ?"""
    args: list = [subject_type]
    if subject_ids is not None:
        if not subject_ids:
            return []
        q += f" AND o.subject_id IN ({','.join('?' * len(subject_ids))})"
        args += subject_ids
    if not include_demo:
        q += " AND o.data_class != 'demo'"
    out = rows(conn.execute(q, args))
    for o in out:
        o["value"] = decode_value(o)
    return out


def resolve_values(observations: list[dict]) -> dict[str, dict[str, Value]]:
    """Pick one value per (subject, variable): verified > derived > demo, then newest."""
    best: dict[tuple, dict] = {}
    for o in observations:
        k = (o["subject_id"], o["variable_key"])
        cur = best.get(k)
        rank = (CLASS_RANK.get(o["data_class"], -1), o["created_at"])
        if cur is None or rank > (CLASS_RANK.get(cur["data_class"], -1), cur["created_at"]):
            best[k] = o
    out: dict[str, dict[str, Value]] = defaultdict(dict)
    for (sid, var), o in best.items():
        out[sid][var] = Value(o["value"], o["data_class"], o["id"], o["unit"], o["dataset_id"], o["method"])
    return out


def _active_source_clause(alias: str) -> str:
    return (f"({alias}.source_dataset_id IS NULL OR EXISTS (SELECT 1 FROM dataset ds "
            f"WHERE ds.id = {alias}.source_dataset_id AND ds.active = 1))")


def list_sites(conn, q: str | None = None, category: str | None = None, include_demo: bool = True) -> list[dict]:
    sql = f"SELECT s.* FROM earth_site s WHERE {_active_source_clause('s')}"
    args: list = []
    if q:
        sql += " AND (s.name LIKE ? OR s.country LIKE ? OR s.region LIKE ? OR s.description LIKE ?)"
        args += [f"%{q}%"] * 4
    sql += " ORDER BY s.name"
    sites = [_decode(s, _SITE_JSON) for s in rows(conn.execute(sql, args))]
    if category:
        sites = [s for s in sites if category in s["categories"]]
    obs = active_observations(conn, "earth_site", [s["id"] for s in sites], include_demo)
    by = defaultdict(list)
    for o in obs:
        by[o["subject_id"]].append(o)
    for s in sites:
        s["completeness"] = completeness(by.get(s["id"], []))
    return sites


def completeness(obs: list[dict]) -> dict:
    have = {o["variable_key"] for o in obs if o["variable_key"] in SCORING_VARIABLES}
    classes = defaultdict(int)
    for o in obs:
        classes[o["data_class"]] += 1
    return {
        "variables_available": len(have),
        "variables_total": len(SCORING_VARIABLES),
        "fraction": round(len(have) / len(SCORING_VARIABLES), 3) if SCORING_VARIABLES else 0,
        "missing": [v for v in SCORING_VARIABLES if v not in have],
        "by_class": dict(classes),
    }


def get_site(conn, site_id: str, include_demo: bool = True) -> dict | None:
    s = row(conn.execute(f"SELECT s.* FROM earth_site s WHERE s.id = ? AND {_active_source_clause('s')}", (site_id,)).fetchone())
    if not s:
        return None
    _decode(s, _SITE_JSON)
    obs = active_observations(conn, "earth_site", [site_id], include_demo)
    s["observations"] = obs
    s["completeness"] = completeness(obs)
    s["citations"] = citations_for(conn, "earth_site", site_id, {o["dataset_id"] for o in obs} | {s["source_dataset_id"]})
    return s


def list_targets(conn, world: str | None = None, q: str | None = None, include_demo: bool = True) -> list[dict]:
    sql = f"SELECT t.* FROM target_region t WHERE {_active_source_clause('t')}"
    args: list = []
    if world:
        sql += " AND t.world_id = ?"
        args.append(world)
    if q:
        sql += " AND (t.name LIKE ? OR t.description LIKE ? OR t.region_type LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY t.world_id, t.name"
    ts = [_decode(t, _TARGET_JSON) for t in rows(conn.execute(sql, args))]
    obs = active_observations(conn, "target_region", [t["id"] for t in ts], include_demo)
    by = defaultdict(list)
    for o in obs:
        by[o["subject_id"]].append(o)
    for t in ts:
        t["completeness"] = completeness(by.get(t["id"], []))
    return ts


def get_target(conn, target_id: str, include_demo: bool = True) -> dict | None:
    t = row(conn.execute(f"SELECT t.* FROM target_region t WHERE t.id = ? AND {_active_source_clause('t')}", (target_id,)).fetchone())
    if not t:
        return None
    _decode(t, _TARGET_JSON)
    obs = active_observations(conn, "target_region", [target_id], include_demo)
    t["observations"] = obs
    t["completeness"] = completeness(obs)
    t["world"] = row(conn.execute("SELECT * FROM target_world WHERE id = ?", (t["world_id"],)).fetchone())
    t["citations"] = citations_for(conn, "target_region", target_id, {o["dataset_id"] for o in obs} | {t["source_dataset_id"]})
    return t


def citations_for(conn, subject_type: str, subject_id: str, dataset_ids: set) -> list[dict]:
    ids = [d for d in dataset_ids if d]
    sql = "SELECT c.*, d.name AS dataset_name FROM citation c LEFT JOIN dataset d ON d.id = c.dataset_id WHERE (c.subject_type = ? AND c.subject_id = ?)"
    args: list = [subject_type, subject_id]
    if ids:
        sql += f" OR c.dataset_id IN ({','.join('?' * len(ids))})"
        args += ids
    return rows(conn.execute(sql + " ORDER BY c.kind, c.text", args))


def list_datasets(conn) -> list[dict]:
    ds = rows(conn.execute("SELECT * FROM dataset ORDER BY active DESC, data_type, name"))
    counts = {r["dataset_id"]: r for r in rows(conn.execute(
        """SELECT dv.dataset_id, COUNT(o.id) AS n_observations, COUNT(DISTINCT o.subject_id) AS n_subjects,
                  COUNT(DISTINCT o.variable_key) AS n_variables
           FROM dataset_version dv JOIN dataset d ON d.current_version_id = dv.id
           LEFT JOIN observation o ON o.dataset_version_id = dv.id GROUP BY dv.dataset_id"""))}
    recs = {r["sid"]: r["n"] for r in rows(conn.execute(
        "SELECT source_dataset_id AS sid, COUNT(*) AS n FROM (SELECT source_dataset_id FROM earth_site "
        "UNION ALL SELECT source_dataset_id FROM target_region) GROUP BY source_dataset_id"))}
    layers = {r["dataset_id"]: r["n"] for r in rows(conn.execute("SELECT dataset_id, COUNT(*) AS n FROM map_layer GROUP BY dataset_id"))}
    for d in ds:
        d["units"] = loads(d["units"], {})
        d["spatial_coverage"] = loads(d["spatial_coverage"], d["spatial_coverage"])
        c = counts.get(d["id"], {})
        d["n_observations"] = c.get("n_observations", 0)
        d["n_subjects"] = c.get("n_subjects", 0)
        d["n_variables"] = c.get("n_variables", 0)
        d["n_records"] = recs.get(d["id"], 0)
        d["n_layers"] = layers.get(d["id"], 0)
    return ds


def get_dataset(conn, dataset_id: str) -> dict | None:
    d = next((x for x in list_datasets(conn) if x["id"] == dataset_id), None)
    if not d:
        return None
    d["versions"] = rows(conn.execute("SELECT * FROM dataset_version WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)))
    for v in d["versions"]:
        v["field_mapping"] = loads(v["field_mapping"], {})
        v["processing_history"] = loads(v["processing_history"], [])
        v.pop("stored_path", None)
    d["quality"] = rows(conn.execute(
        "SELECT q.* FROM data_quality_assessment q JOIN dataset_version dv ON dv.id = q.dataset_version_id "
        "WHERE dv.dataset_id = ? ORDER BY q.created_at DESC", (dataset_id,)))
    for q in d["quality"]:
        q["issues"] = loads(q["issues"], [])
    d["jobs"] = rows(conn.execute("SELECT id, kind, status, error, created_at, finished_at FROM analysis_job WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)))
    d["citations"] = rows(conn.execute("SELECT * FROM citation WHERE dataset_id = ?", (dataset_id,)))
    d["layers"] = rows(conn.execute("SELECT id, name, body, kind, feature_count FROM map_layer WHERE dataset_id = ?", (dataset_id,)))
    d["variables"] = rows(conn.execute(
        "SELECT o.variable_key, o.subject_type, COUNT(*) AS n FROM observation o WHERE o.dataset_version_id = ? "
        "GROUP BY o.variable_key, o.subject_type", (d["current_version_id"],)))
    return d


def state(conn) -> dict:
    from ..db import revision

    ds = rows(conn.execute("SELECT data_class, active, data_type FROM dataset"))
    active = [d for d in ds if d["active"]]
    demo_active = any(d["data_class"] == "demo" and d["data_type"] != "reference" for d in active)
    verified_active = any(d["data_class"] in ("verified", "derived") for d in active)
    mode = "demo" if demo_active and not verified_active else ("mixed" if demo_active else ("verified" if verified_active else "empty"))
    return {
        "revision": revision(conn),
        "mode": mode,
        "datasets_active": len(active),
        "datasets_total": len(ds),
        "demo_active": demo_active,
        "verified_active": verified_active,
        "sites": conn.execute(f"SELECT COUNT(*) FROM earth_site s WHERE {_active_source_clause('s')}").fetchone()[0],
        "targets": conn.execute(f"SELECT COUNT(*) FROM target_region t WHERE {_active_source_clause('t')}").fetchone()[0],
    }
