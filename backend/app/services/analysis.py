"""Runs the similarity engine against the database and persists reproducible
SimilarityAssessment records."""
from __future__ import annotations

from ..config import get_settings
from ..db import dumps, loads, new_id, now, row
from . import catalog
from .similarity import ENGINE_VERSION, assess, input_hash
from .vocabulary import CRITERIA, CRITERION_BY_KEY, DEFAULT_PROFILE, PROFILES


class AnalysisError(ValueError):
    pass


def resolve_weights(profile: str | None, weights: dict | None) -> tuple[str, dict]:
    if weights:
        unknown = set(weights) - set(CRITERION_BY_KEY)
        if unknown:
            raise AnalysisError(f"Unknown criteria in weights: {', '.join(sorted(unknown))}")
        base = dict(PROFILES[profile]["weights"]) if profile in PROFILES else {c.key: 0 for c in CRITERIA}
        base.update({k: float(v) for k, v in weights.items()})
        return (profile or "custom") if profile in PROFILES and base == PROFILES[profile]["weights"] else "custom", base
    p = profile or DEFAULT_PROFILE
    if p not in PROFILES:
        raise AnalysisError(f"Unknown weighting profile '{p}'")
    return p, dict(PROFILES[p]["weights"])


def run(conn, target_id: str, profile: str | None = None, weights: dict | None = None,
        site_ids: list[str] | None = None, include_demo: bool = True, persist: bool = True) -> dict:
    s = get_settings()
    target = catalog.get_target(conn, target_id, include_demo)
    if not target:
        raise AnalysisError(f"Target region '{target_id}' not found or its dataset is inactive")
    prof, w = resolve_weights(profile, weights)
    sites = catalog.list_sites(conn, include_demo=include_demo)
    if site_ids is not None:
        wanted = set(site_ids)
        sites = [x for x in sites if x["id"] in wanted]
        missing = wanted - {x["id"] for x in sites}
        if missing:
            raise AnalysisError(f"Unknown or inactive Earth sites: {', '.join(sorted(missing))}")
    tvals = catalog.resolve_values(target["observations"]).get(target_id, {})
    svals_all = catalog.resolve_values(catalog.active_observations(conn, "earth_site", [x["id"] for x in sites], include_demo))
    thresholds = {"min_coverage": s.min_weight_coverage, "min_criteria": s.min_criteria}
    results = []
    for site in sites:
        sv = svals_all.get(site["id"], {})
        r = assess(CRITERIA, w, sv, tvals, target["world_id"], **thresholds)
        h = input_hash(CRITERIA, w, sv, tvals, thresholds)
        aid = None
        if persist:
            existing = conn.execute(
                "SELECT id FROM similarity_assessment WHERE target_region_id=? AND earth_site_id=? AND input_hash=?",
                (target_id, site["id"], h)).fetchone()
            if existing:
                aid = existing[0]
            else:
                aid = new_id()
                conn.execute(
                    """INSERT INTO similarity_assessment(id, target_region_id, earth_site_id, weights, profile, status, score,
                       coverage, n_criteria_used, criteria_results, data_classes, input_hash, engine_version, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (aid, target_id, site["id"], dumps(w), prof, r["status"], r["score"], r["coverage"],
                     r["n_criteria_used"], dumps(r["criteria"]), dumps(r["data_classes"]), h, ENGINE_VERSION, now()))
        results.append({
            "assessment_id": aid, "input_hash": h,
            "site": {k: site[k] for k in ("id", "name", "country", "lat", "lon", "categories", "terrain_type", "completeness", "data_class")},
            **r,
        })
    results.sort(key=lambda x: (x["status"] != "scored", -(x["score"] or 0), -x["coverage"]))
    rank = 0
    for x in results:
        if x["status"] == "scored":
            rank += 1
            x["rank"] = rank
        else:
            x["rank"] = None
    return {
        "target": {k: target[k] for k in ("id", "name", "world_id", "lat", "lon", "region_type", "completeness", "data_class")},
        "profile": prof, "profile_name": PROFILES.get(prof, {}).get("name", "Custom weights"),
        "weights": w, "include_demo": include_demo, "thresholds": thresholds, "engine_version": ENGINE_VERSION,
        "results": results,
        "n_scored": rank, "n_insufficient": len(results) - rank,
        "is_demo": any(x["is_demo"] for x in results),
    }


def get_assessment(conn, assessment_id: str) -> dict | None:
    a = row(conn.execute("SELECT * FROM similarity_assessment WHERE id = ?", (assessment_id,)).fetchone())
    if not a:
        return None
    for k in ("weights", "criteria_results", "data_classes"):
        a[k] = loads(a[k])
    return a
