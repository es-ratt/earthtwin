"""EarthTwin Analog Similarity Index (prototype) — pure scoring functions.

Design rules (see docs/METHODOLOGY.md):
  * Every criterion compares one Earth-site value with one target-region value of
    the same variable, after unit normalisation, and yields a similarity s ∈ [0, 1].
  * A missing value on either side yields *no* similarity; it is never a match.
  * The index is the weight-normalised mean of the available criteria, reported
    together with weight coverage (share of requested weight that had data).
  * If coverage or the number of usable criteria is below threshold the result is
    "insufficient_data" and no index is produced.
  * The data classes of all inputs are carried through, so a result built on
    demonstration values is always labelled as such.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable

from .vocabulary import ACCESS_LEVELS, Criterion

ENGINE_VERSION = "1.0.0"
CLASS_RANK = {"demo": 0, "derived": 1, "verified": 2}


@dataclass
class Value:
    value: Any                 # float | list[str] | bool | str
    data_class: str
    observation_id: str | None = None
    unit: str | None = None
    dataset_id: str | None = None
    method: str | None = None


def _gauss(d: float, scale: float) -> float:
    return math.exp(-0.5 * (d / scale) ** 2)


def compare(c: Criterion, site: Value | None, target: Value | None) -> dict:
    """Return {'similarity': float|None, 'status': str, 'detail': str}."""
    if c.method == "earth_attribute":
        if site is None:
            return {"similarity": None, "status": "missing_site", "detail": "No Earth-site value"}
        if c.variable_key == "accessibility":
            s = ACCESS_LEVELS.get(str(site.value).lower())
            if s is None:
                return {"similarity": None, "status": "invalid", "detail": f"Unknown access level '{site.value}'"}
            return {"similarity": s, "status": "ok", "detail": f"Access '{site.value}' → {s:.2f} (Earth-only suitability)"}
        s = 1.0 if bool(site.value) else 0.0
        return {"similarity": s, "status": "ok", "detail": "Earth-only suitability attribute"}

    if site is None and target is None:
        return {"similarity": None, "status": "missing_both", "detail": "No value for site or target"}
    if site is None:
        return {"similarity": None, "status": "missing_site", "detail": "No Earth-site value"}
    if target is None:
        return {"similarity": None, "status": "missing_target", "detail": "No target-region value"}

    a, b = site.value, target.value
    m = c.method
    if m == "gaussian":
        d = float(a) - float(b)
        return {"similarity": _gauss(d, c.scale), "status": "ok", "detail": f"Δ = {d:+.3g} (scale {c.scale:g})"}
    if m == "log_ratio":
        a, b = float(a), float(b)
        if a <= 0 or b <= 0:
            # A zero relief/range cannot be compared on a log scale; fall back to exact-match semantics.
            s = 1.0 if a == b else 0.0
            return {"similarity": s, "status": "ok", "detail": "Non-positive value: exact-match comparison"}
        d = math.log10(a / b)
        return {"similarity": _gauss(d, c.scale), "status": "ok", "detail": f"ratio = {a / b:.3g}× (log10 {d:+.2f})"}
    if m == "log1p_gaussian":
        a, b = max(0.0, float(a)), max(0.0, float(b))
        d = math.log10(1 + a) - math.log10(1 + b)
        return {"similarity": _gauss(d, c.scale), "status": "ok", "detail": f"Δlog10(1+x) = {d:+.2f}"}
    if m == "jaccard":
        A, B = set(a or []), set(b or [])
        if not A or not B:
            return {"similarity": None, "status": "missing_site" if not A else "missing_target", "detail": "Empty term set"}
        inter, union = A & B, A | B
        return {"similarity": len(inter) / len(union), "status": "ok",
                "detail": f"shared: {', '.join(sorted(inter)) or 'none'}; site-only: {', '.join(sorted(A - B)) or 'none'}; "
                          f"target-only: {', '.join(sorted(B - A)) or 'none'}"}
    if m == "boolean":
        s = 1.0 if bool(a) == bool(b) else 0.0
        return {"similarity": s, "status": "ok", "detail": f"site {'yes' if a else 'no'} / target {'yes' if b else 'no'}"}
    raise ValueError(f"Unknown comparison method {m}")


def normalise_weights(weights: dict[str, float], criteria: Iterable[Criterion]) -> dict[str, float]:
    out = {}
    for c in criteria:
        w = float(weights.get(c.key, 0) or 0)
        if w < 0 or not math.isfinite(w):
            raise ValueError(f"Weight for {c.key} must be a non-negative number")
        out[c.key] = w
    return out


def assess(
    criteria: list[Criterion],
    weights: dict[str, float],
    site_values: dict[str, Value],
    target_values: dict[str, Value],
    world: str,
    min_coverage: float = 0.6,
    min_criteria: int = 3,
) -> dict:
    crit = [c for c in criteria if world in c.applies_to]
    w = normalise_weights(weights, crit)
    total_w = sum(w.values())
    results, used_w, acc = [], 0.0, 0.0
    classes: set[str] = set()
    for c in crit:
        sv, tv = site_values.get(c.variable_key), target_values.get(c.variable_key)
        r = compare(c, sv, tv)
        weight = w[c.key]
        entry = {
            "criterion": c.key, "name": c.name, "family": c.family, "method": c.method, "weight": weight,
            "similarity": r["similarity"], "status": r["status"], "detail": r["detail"],
            "site_value": None if sv is None else sv.value, "site_unit": None if sv is None else sv.unit,
            "site_class": None if sv is None else sv.data_class, "site_observation": None if sv is None else sv.observation_id,
            "target_value": None if tv is None else tv.value, "target_unit": None if tv is None else tv.unit,
            "target_class": None if tv is None else tv.data_class,
            "target_observation": None if tv is None else tv.observation_id,
            "contribution": None, "data_class": None,
        }
        if r["similarity"] is not None:
            involved = [v.data_class for v in (sv, tv) if v is not None and not (c.method == "earth_attribute" and v is tv)]
            entry["data_class"] = min(involved, key=lambda k: CLASS_RANK.get(k, 0)) if involved else None
            if weight > 0:
                used_w += weight
                acc += weight * r["similarity"]
                if entry["data_class"]:
                    classes.add(entry["data_class"])
        results.append(entry)

    n_used = sum(1 for r in results if r["similarity"] is not None and r["weight"] > 0)
    coverage = (used_w / total_w) if total_w > 0 else 0.0
    if total_w <= 0:
        status, reason, score = "insufficient_data", "All criterion weights are zero.", None
    elif n_used < min_criteria:
        status, reason, score = "insufficient_data", f"Only {n_used} weighted criteria have data on both sides (minimum {min_criteria}).", None
    elif coverage < min_coverage:
        status, reason, score = "insufficient_data", f"Weight coverage {coverage:.0%} is below the {min_coverage:.0%} threshold.", None
    else:
        status, reason, score = "scored", None, 100.0 * acc / used_w
    if score is not None:
        for e in results:
            if e["similarity"] is not None and e["weight"] > 0:
                e["contribution"] = 100.0 * e["weight"] * e["similarity"] / used_w

    lowest = min(classes, key=lambda k: CLASS_RANK.get(k, 0)) if classes else None
    return {
        "status": status,
        "reason": reason,
        "score": None if score is None else round(score, 2),
        "coverage": round(coverage, 4),
        "n_criteria_used": n_used,
        "n_criteria_weighted": sum(1 for c in crit if w[c.key] > 0),
        "criteria": results,
        "data_classes": sorted(classes),
        "lowest_data_class": lowest,
        "is_demo": lowest == "demo",
        "strengths": [r["criterion"] for r in results if r["similarity"] is not None and r["weight"] > 0 and r["similarity"] >= 0.8],
        "mismatches": [r["criterion"] for r in results if r["similarity"] is not None and r["weight"] > 0 and r["similarity"] < 0.4],
        "missing": [r["criterion"] for r in results if r["similarity"] is None and r["weight"] > 0],
        "engine_version": ENGINE_VERSION,
        "thresholds": {"min_coverage": min_coverage, "min_criteria": min_criteria},
    }


def input_hash(criteria: list[Criterion], weights: dict, site_values: dict, target_values: dict, thresholds: dict) -> str:
    """Deterministic fingerprint of everything that determines a result."""
    payload = {
        "engine": ENGINE_VERSION,
        "criteria": [[c.key, c.method, c.scale, c.variable_key] for c in criteria],
        "weights": {k: weights[k] for k in sorted(weights)},
        "site": {k: [v.observation_id, v.value, v.data_class] for k, v in sorted(site_values.items())},
        "target": {k: [v.observation_id, v.value, v.data_class] for k, v in sorted(target_values.items())},
        "thresholds": thresholds,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
