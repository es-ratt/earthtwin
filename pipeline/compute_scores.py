#!/usr/bin/env python3
"""EarthTwin scoring pipeline (Team PLANEX, NASA Space Apps 2026).

Reads
  web/data/missions.json, targets.json, features.json, sources.json
  pipeline/config.json
  datasets/earth_candidates.csv, datasets/earth_features.csv
Writes
  web/data/earth_candidates.json
  web/data/results/<mission-id>.json

Method (also shown in the app's METHOD tab)
  Stage A  hard filters  : mission constraints with hard_filter=true and a known limit.
  Stage B  score         : Score = Σ wᵢ · simᵢ, simᵢ = exp(-|Earth − target| / scaleᵢ),
                           over features that have data on BOTH sides; weights are
                           renormalised over those features and both versions are kept.
  Extras                 : 'Why not others?' cards, ±10 pp weight sensitivity,
                           validation ranks of known analogs.

Only the Python standard library is used, so students can run it anywhere:
    python3 pipeline/compute_scores.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB_DATA = ROOT / "web" / "data"
DATASETS = ROOT / "datasets"
CONFIG_PATH = ROOT / "pipeline" / "config.json"

EARTH_AXIAL_TILT_DEG = 23.44  # used only to derive max_sun_elev_deg from latitude
CONF_ORDER = {"low": 0, "medium": 1, "high": 2}
CONF_NAMES = {v: k for k, v in CONF_ORDER.items()}


# --------------------------------------------------------------------------- io
def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")


def parse_value(raw: str, kind: str):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if kind == "categorical":
        return raw
    return float(raw)


# ------------------------------------------------------------------ formatting
def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fmt_num(x: float) -> str:
    if x is None:
        return "No data"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_measure(m: dict | None, unit: str | None) -> str:
    """Human-readable target/earth value, e.g. '0–15 °', '4.64 °', 'anorthosite', 'No data'."""
    if not m:
        return "No data"
    u = f" {unit}" if unit and unit not in ("0–1", "0–3") else ""
    if m.get("min") is not None or m.get("max") is not None:
        return f"{fmt_num(m.get('min'))}–{fmt_num(m.get('max'))}{u}"
    v = m.get("value")
    if v is None:
        return "No data"
    if isinstance(v, str):
        return v.replace("_", " ")
    return f"{fmt_num(v)}{u}"


def has_value(m: dict | None) -> bool:
    if not m:
        return False
    if m.get("min") is not None or m.get("max") is not None:
        return True
    return m.get("value") is not None


# ------------------------------------------------------------------- loading
def load_inputs() -> dict:
    features = load_json(WEB_DATA / "features.json")
    fdefs = {f["id"]: f for f in features["features"]}
    return {
        "missions": load_json(WEB_DATA / "missions.json")["missions"],
        "targets": load_json(WEB_DATA / "targets.json"),
        "features": features,
        "fdefs": fdefs,
        "sources": {s["id"]: s for s in load_json(WEB_DATA / "sources.json")["sources"]},
        "config": load_json(CONFIG_PATH),
        "target_meas": load_target_measurements(DATASETS / "target_measurements.csv"),
    }


def load_earth(fdefs: dict, candidates_csv: Path, features_csv: Path) -> list[dict]:
    """Load Earth candidates (metadata + long-format feature table)."""
    cands: dict[str, dict] = {}
    with open(candidates_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cands[row["id"]] = {
                "id": row["id"],
                "name": row["name"],
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "country": row.get("country", ""),
                "is_baseline": row.get("is_baseline", "0").strip() in ("1", "true", "yes"),
                "why_candidate": row.get("why_candidate", ""),
                "position": {"status": row.get("position_status") or "verify", "note": row.get("position_note", "")},
                "features": {},
            }
    raw_kinds = {"annual_min_lst_K": "numeric"}
    with open(features_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cid, fid = row["candidate_id"], row["feature"]
            if cid not in cands:
                raise ValueError(f"earth_features.csv: unknown candidate_id '{cid}'")
            kind = fdefs[fid]["kind"] if fid in fdefs else raw_kinds.get(fid)
            if kind is None:
                raise ValueError(f"earth_features.csv: unknown feature '{fid}'")
            value = parse_value(row["value"], kind)
            status = (row.get("status") or "").strip() or ("TODO" if value is None else "SAMPLE")
            if value is not None and not (row.get("source_id") or "").strip():
                raise ValueError(f"earth_features.csv: {cid}/{fid} has a value but no source_id")
            cands[cid]["features"][fid] = {
                "value": value,
                "unit": row.get("unit") or None,
                "status": status,
                "source_id": (row.get("source_id") or "").strip() or None,
                "confidence": (row.get("confidence") or "").strip() or None,
                "note": row.get("note", ""),
            }
    derive_earth_features(list(cands.values()))
    return list(cands.values())


def derive_earth_features(cands: list[dict]) -> None:
    """Compute derived features. Never typed in by hand."""
    for c in cands:
        elev = min(90.0, 90.0 - abs(c["lat"]) + EARTH_AXIAL_TILT_DEG)
        c["features"]["max_sun_elev_deg"] = {
            "value": round(elev, 2), "unit": "°", "status": "derived", "source_id": "method",
            "confidence": "medium" if c["position"]["status"] != "verified" else "high",
            "note": "90° − |latitude| + 23.44° (from the site latitude).",
        }
    # cold_index: percentile of annual minimum LST among candidates (1 = coldest)
    with_t = [c for c in cands if has_value(c["features"].get("annual_min_lst_K"))]
    ordered = sorted(with_t, key=lambda c: c["features"]["annual_min_lst_K"]["value"])
    n = len(ordered)
    for i, c in enumerate(ordered):
        src = c["features"]["annual_min_lst_K"]
        c["features"]["cold_index"] = {
            "value": round(1.0 - i / (n - 1), 3) if n > 1 else 1.0,
            "unit": "0–1",
            "status": "SAMPLE" if src["status"] == "SAMPLE" else "derived",
            "source_id": src["source_id"],
            "confidence": src.get("confidence"),
            "note": f"Rank {i + 1} of {n} by annual minimum surface temperature ({fmt_num(src['value'])} K).",
        }
    for c in cands:
        c["features"].setdefault("cold_index", {"value": None, "status": "TODO", "note": "Needs annual_min_lst_K."})


def load_target_measurements(path: Path) -> dict[str, dict[str, dict]]:
    """datasets/target_measurements.csv: values measured by pipeline/fetch_real_data.py (e.g. LOLA slope)."""
    out: dict[str, dict[str, dict]] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("value") or "").strip():
                continue
            if not (row.get("source_id") or "").strip():
                raise ValueError(f"target_measurements.csv: {row['site_id']}/{row['feature']} has a value but no source_id")
            out.setdefault(row["site_id"], {})[row["feature"]] = {
                "value": float(row["value"]), "unit": row.get("unit") or None, "status": row.get("status") or "measured",
                "source_id": row["source_id"], "confidence": row.get("confidence") or None, "note": row.get("note", ""),
            }
    return out


def resolve_target(site: dict, defaults: dict, measurements: dict | None = None) -> dict:
    """Mission defaults < hand-entered targets.json values < measured values."""
    merged = {}
    if site.get("inherits"):
        merged.update({k: v for k, v in defaults[site["inherits"]].items() if not k.startswith("_")})
    merged.update(site.get("features", {}))
    merged.update((measurements or {}).get(site["id"], {}))
    return merged


# --------------------------------------------------------------- similarity
def categorical_table(config: dict) -> dict:
    table: dict[str, dict[tuple, float]] = {}
    for fid, pairs in config.get("categorical_similarity", {}).items():
        if fid.startswith("_"):
            continue
        t = {}
        for a, b, s in pairs:
            t[(a, b)] = s
            t[(b, a)] = s
        table[fid] = t
    return table


def similarity(fid: str, kind: str, target: dict | None, earth: dict | None, ctx: dict) -> tuple[float | None, str | None]:
    """Return (similarity 0..1 or None, missing_reason)."""
    if not has_value(target):
        return None, "no_target_data"
    # special rule: no ground ice -> depth is a full mismatch, not missing
    if fid == "ice_depth_m" and not has_value(earth) and ctx["config"]["special_rules"].get("no_ice_means_depth_mismatch"):
        presence = ctx["earth_features"].get("ice_presence")
        if presence and presence.get("value") == 0:
            return 0.0, None
    if not has_value(earth):
        return None, "no_earth_data"
    ev = earth["value"]
    if kind == "categorical":
        tv = target["value"]
        if ev == tv:
            return 1.0, None
        return ctx["cat"].get(fid, {}).get((tv, ev), 0.0), None
    scale = ctx["config"]["scales"][fid]
    if target.get("min") is not None or target.get("max") is not None:
        lo = target.get("min", -math.inf)
        hi = target.get("max", math.inf)
        d = 0.0 if lo <= ev <= hi else min(abs(ev - lo), abs(ev - hi))
    else:
        d = abs(ev - target["value"])
    return math.exp(-d / scale), None


def nominal_feature_weights(mission_id: str, ctx: dict) -> dict[str, float]:
    """Category weight split equally between the mission's features in that category (fractions summing to 1)."""
    cfg = ctx["config"]
    weights_pct = {k: v for k, v in cfg["weights_pct"][mission_id].items() if not k.startswith("_")}
    feats = cfg["mission_features"][mission_id]
    by_cat: dict[str, list[str]] = {}
    for fid in feats:
        by_cat.setdefault(ctx["fdefs"][fid]["category"], []).append(fid)
    out = {}
    for cat, fids in by_cat.items():
        for fid in fids:
            out[fid] = weights_pct.get(cat, 0) / 100.0 / len(fids)
    total = sum(out.values())
    return {k: v / total for k, v in out.items()} if total else out


# -------------------------------------------------------------- hard filters
def hard_filters(mission: dict) -> list[dict]:
    return [c for c in mission.get("constraints", []) if c.get("hard_filter") and c.get("feature_id") and c.get("limit") is not None]


def check_filter(constraint: dict, earth_m: dict | None) -> str:
    """'pass' | 'fail' | 'unknown'."""
    if not has_value(earth_m):
        return "unknown"
    v, lim, op = earth_m["value"], constraint["limit"], constraint["op"]
    ok = {"<": v < lim, "<=": v <= lim, ">": v > lim, ">=": v >= lim}[op]
    return "pass" if ok else "fail"


# ----------------------------------------------------------------- scoring
def score_candidate(cand: dict, target_feats: dict, weights: dict, ctx: dict) -> dict:
    per = {}
    for fid, w in weights.items():
        fdef = ctx["fdefs"][fid]
        t, e = target_feats.get(fid), cand["features"].get(fid)
        sim, missing = similarity(fid, fdef["kind"], t, e, {**ctx, "earth_features": cand["features"]})
        per[fid] = {"similarity": sim, "missing": missing, "weight_nominal": w}
    target_avail = sum(w for fid, w in weights.items() if per[fid]["missing"] != "no_target_data")
    used = sum(w for fid, w in weights.items() if per[fid]["similarity"] is not None)
    for fid in per:
        per[fid]["weight_used"] = (per[fid]["weight_nominal"] / used) if (used and per[fid]["similarity"] is not None) else 0.0
    score = sum(per[f]["weight_used"] * per[f]["similarity"] for f in per if per[f]["similarity"] is not None) if used else None
    return {
        "score": score,
        "per_feature": per,
        "target_coverage": target_avail,
        "earth_coverage": (used / target_avail) if target_avail else 0.0,
    }


def classify(cands: list[dict], mission: dict, target_feats: dict, weights: dict, ctx: dict, filters_override: dict | None = None) -> dict:
    """Run stage A + B. Returns dict id -> result, plus ordered ranking."""
    filters = hard_filters(mission)
    min_cov = ctx["config"]["thresholds"]["min_earth_coverage"]
    results = {}
    for c in cands:
        checks = []
        for fc in filters:
            lim_fc = dict(fc)
            if filters_override and fc["id"] in filters_override:
                lim_fc["limit"] = filters_override[fc["id"]]
            checks.append({"constraint": lim_fc, "result": check_filter(lim_fc, c["features"].get(fc["feature_id"]))})
        s = score_candidate(c, target_feats, weights, ctx)
        if any(ch["result"] == "fail" for ch in checks):
            status = "rejected"
        elif any(ch["result"] == "unknown" for ch in checks) or s["score"] is None or s["earth_coverage"] < min_cov:
            status = "cannot_evaluate"
        else:
            status = "ranked"
        results[c["id"]] = {"status": status, "filters": checks, **s}
    ranking = sorted((cid for cid, r in results.items() if r["status"] == "ranked"), key=lambda cid: (-results[cid]["score"], cid))
    for i, cid in enumerate(ranking):
        results[cid]["rank"] = i + 1
    return {"results": results, "ranking": ranking}


# ------------------------------------------------------------- confidence
def confidence(cand: dict, r: dict, ctx: dict) -> tuple[str, list[str]]:
    th = ctx["config"]["thresholds"]
    cov = r["target_coverage"] * r["earth_coverage"]
    level = 2 if cov >= th["confidence_high"] else 1 if cov >= th["confidence_medium"] else 0
    reasons = [f"{round(cov * 100)}% of the planned weight has data on both sides"]
    used = [fid for fid, p in r["per_feature"].items() if p["similarity"] is not None]
    if any(cand["features"].get(f, {}).get("status") == "SAMPLE" for f in used):
        level = 0
        reasons.append("Earth values are SAMPLE placeholders")
    low_conf = [f for f in used if cand["features"].get(f, {}).get("confidence") == "low" and cand["features"].get(f, {}).get("status") != "SAMPLE"]
    if low_conf and level > 0:
        level -= 1
        reasons.append("some Earth values have low confidence")
    proxies = [f for f in used if ctx["fdefs"][f].get("proxy")]
    if proxies:
        reasons.append("uses proxy values (" + ", ".join(ctx["fdefs"][f]["label"] for f in proxies) + ")")
    if r["target_coverage"] < th["confidence_medium"]:
        level = 0
        reasons.append(f"target site has data for only {round(r['target_coverage'] * 100)}% of the weight")
    return CONF_NAMES[level], reasons


# -------------------------------------------------------------------- cards
def feature_row(fid: str, cand: dict, target_feats: dict, ctx: dict, per: dict | None = None, limit: str | None = None) -> dict:
    fdef = ctx["fdefs"][fid]
    t, e = target_feats.get(fid), cand["features"].get(fid)
    row = {
        "feature_id": fid,
        "label": fdef["label"],
        "unit": fdef.get("unit"),
        "target": fmt_measure(t, fdef.get("unit")),
        "earth": fmt_measure(e, fdef.get("unit")),
        "target_source_id": (t or {}).get("source_id"),
        "earth_source_id": (e or {}).get("source_id"),
        "earth_status": (e or {}).get("status", "TODO"),
        "target_status": (t or {}).get("status", "TODO"),
    }
    if limit is not None:
        row["limit"] = limit
    if fid == "ice_depth_m" and not has_value(e) and (cand["features"].get("ice_presence") or {}).get("value") == 0:
        row["earth"] = "none (no ground ice)"
        row["earth_status"] = cand["features"]["ice_presence"].get("status", "TODO")
    if per is not None:
        row["similarity"] = None if per["similarity"] is None else round(per["similarity"], 3)
        if per["missing"]:
            row["missing"] = per["missing"]
    return row


def what_if_rank(cands, mission, target_feats, weights, ctx, cid, filters_override=None, force_sim=None) -> int | None:
    """Rank of cid if filters are relaxed or one feature is forced to a perfect match."""
    if force_sim is None:
        out = classify(cands, mission, target_feats, weights, ctx, filters_override)
        r = out["results"][cid]
        return r.get("rank") if r["status"] == "ranked" else None
    base = classify(cands, mission, target_feats, weights, ctx, filters_override)
    scores = {k: v["score"] for k, v in base["results"].items() if v["status"] == "ranked"}
    r = base["results"][cid]
    if cid not in scores:
        return None
    per = r["per_feature"]
    new = scores[cid] + per[force_sim]["weight_used"] * (1.0 - per[force_sim]["similarity"])
    return 1 + sum(1 for k, s in scores.items() if k != cid and s > new)


def build_card(cand, r, ranking_len, mission, target_feats, weights, cands, ctx, ranked_scores: list[float]) -> dict:
    fdefs = ctx["fdefs"]
    conf, conf_reasons = r["confidence"], r["confidence_reasons"]
    card = {"confidence": conf, "confidence_reason": "; ".join(conf_reasons)}
    if r["status"] == "rejected":
        failed = [ch for ch in r["filters"] if ch["result"] == "fail"]
        card["verdict"] = "Rejected"
        card["reason_type"] = "hard-filter fail"
        card["numbers"] = []
        parts = []
        for ch in failed:
            fc = ch["constraint"]
            fid = fc["feature_id"]
            unit = fdefs[fid].get("unit")
            lim_txt = f"{fc['op']} {fmt_num(fc['limit'])} {unit}".strip()
            card["numbers"].append(feature_row(fid, cand, target_feats, ctx, limit=lim_txt))
            ev = cand["features"][fid]["value"]
            parts.append(f"{fdefs[fid]['label'].lower()} {fmt_num(ev)} {unit} is not {lim_txt}")
        card["headline"] = "Fails the mission limit: " + "; ".join(parts) + "."
        # Relax the limit for THIS site only and slot its score into the current ranking.
        new_rank = None
        if r["score"] is not None and r["earth_coverage"] >= ctx["config"]["thresholds"]["min_earth_coverage"] \
                and not any(ch["result"] == "unknown" for ch in r["filters"]):
            new_rank = 1 + sum(1 for s in ranked_scores if s > r["score"])
        limits = " and ".join(
            f"the {fdefs[ch['constraint']['feature_id']]['label'].lower()} limit allowed "
            f"{fmt_num(cand['features'][ch['constraint']['feature_id']]['value'])} {fdefs[ch['constraint']['feature_id']].get('unit')} "
            f"(now {ch['constraint']['op']} {fmt_num(ch['constraint']['limit'])} {fdefs[ch['constraint']['feature_id']].get('unit')})"
            for ch in failed)
        if new_rank:
            card["what_would_change"] = f"Would rank {ordinal(new_rank)} if {limits}."
        else:
            card["what_would_change"] = f"Even if {limits}, it could not be scored (missing data)."
        card["weakest"] = []
    elif r["status"] == "cannot_evaluate":
        card["verdict"] = "Cannot be evaluated"
        card["reason_type"] = "missing data"
        unknown = [ch for ch in r["filters"] if ch["result"] == "unknown"]
        missing = [fid for fid, p in r["per_feature"].items() if p["missing"] == "no_earth_data"]
        card["numbers"] = [feature_row(ch["constraint"]["feature_id"], cand, target_feats, ctx,
                                       limit=f"{ch['constraint']['op']} {fmt_num(ch['constraint']['limit'])} {fdefs[ch['constraint']['feature_id']].get('unit')}")
                           for ch in unknown]
        card["numbers"] += [feature_row(fid, cand, target_feats, ctx, per=r["per_feature"][fid]) for fid in missing if fid not in [c["constraint"]["feature_id"] for c in unknown]]
        bits = []
        if unknown:
            bits.append("the mission limit on " + ", ".join(fdefs[ch["constraint"]["feature_id"]]["label"].lower() for ch in unknown) + " cannot be checked")
        if r["earth_coverage"] < ctx["config"]["thresholds"]["min_earth_coverage"]:
            bits.append(f"only {round(r['earth_coverage'] * 100)}% of the usable weight has Earth data (minimum {round(ctx['config']['thresholds']['min_earth_coverage'] * 100)}%)")
        card["headline"] = "Not scored: " + "; ".join(bits) + "." if bits else "Not scored: missing data."
        need = [fdefs[f]["label"].lower() for f in missing]
        card["what_would_change"] = "Would be scored once these are measured: " + (", ".join(need) if need else ", ".join(fdefs[ch["constraint"]["feature_id"]]["label"].lower() for ch in unknown)) + "."
        card["weakest"] = []
    else:
        card["verdict"] = "Low match"
        card["reason_type"] = "low score"
        avail = [(fid, p) for fid, p in r["per_feature"].items() if p["similarity"] is not None]
        weakest = sorted(avail, key=lambda fp: (fp[1]["similarity"], -fp[1]["weight_used"]))[:3]
        card["weakest"] = [feature_row(fid, cand, target_feats, ctx, per=p) for fid, p in weakest]
        card["numbers"] = card["weakest"]
        top_n = ctx["config"]["thresholds"]["top_n_analogs"]
        card["headline"] = f"Scores {round(r['score'] * 100)}% and ranks {ordinal(r['rank'])} of {ranking_len}; the top {top_n} are shown as analogs."
        best = None
        for fid, p in avail:
            if p["similarity"] >= 0.999:
                continue
            nr = what_if_rank(cands, mission, target_feats, weights, ctx, cand["id"], force_sim=fid)
            if best is None or nr < best[1]:
                best = (fid, nr)
        if best:
            fid, nr = best
            if nr <= top_n:
                card["what_would_change"] = f"Would rank {ordinal(nr)} if its {fdefs[fid]['label'].lower()} matched the target."
            else:
                card["what_would_change"] = f"Even a perfect {fdefs[fid]['label'].lower()} match would only lift it to {ordinal(nr)}."
        else:
            card["what_would_change"] = "All available features already match; more data could change the rank."
    return card


def analog_limitations(r: dict, ctx: dict) -> dict:
    rep, part, fail, nodata = [], [], [], []
    for fid, p in r["per_feature"].items():
        lab = ctx["fdefs"][fid]["label"]
        if p["similarity"] is None:
            nodata.append(lab)
        elif p["similarity"] >= 0.7:
            rep.append(lab)
        elif p["similarity"] >= 0.4:
            part.append(lab)
        else:
            fail.append(lab)
    return {"reproduces": rep, "partly": part, "fails": fail, "no_data": nodata}


# ------------------------------------------------------------- sensitivity
def sensitivity(mission_id, mission, target_feats, cands, ctx, base: dict) -> dict:
    cfg = ctx["config"]
    pp = cfg["thresholds"]["sensitivity_pp"]
    top_n = cfg["thresholds"]["top_n_analogs"]
    base_pct = {k: v for k, v in cfg["weights_pct"][mission_id].items() if not k.startswith("_")}
    cats_with_features = {ctx["fdefs"][f]["category"] for f in cfg["mission_features"][mission_id]}
    base_rank = {cid: i + 1 for i, cid in enumerate(base["ranking"])}
    base_top = base["ranking"][:top_n]
    scenarios = []
    rank_ranges = {cid: [r, r] for cid, r in base_rank.items()}
    for cat in sorted(cats_with_features):
        for delta in (+pp, -pp):
            new = dict(base_pct)
            new[cat] = max(0.0, base_pct.get(cat, 0) + delta)
            if new[cat] == base_pct.get(cat, 0):
                continue
            others = [k for k in new if k != cat and k in cats_with_features]
            rest_old = sum(base_pct[k] for k in others)
            rest_new = 100.0 - new[cat]
            for k in others:
                new[k] = base_pct[k] * rest_new / rest_old if rest_old else 0.0
            for k in new:
                if k not in cats_with_features and k != cat:
                    new[k] = 0.0
            ctx2 = {**ctx, "config": {**cfg, "weights_pct": {**cfg["weights_pct"], mission_id: new}}}
            w = nominal_feature_weights(mission_id, ctx2)
            out = classify(cands, mission, target_feats, w, ctx2)
            ranks = {cid: i + 1 for i, cid in enumerate(out["ranking"])}
            shifts = {cid: ranks[cid] - base_rank[cid] for cid in base_rank if cid in ranks}
            for cid, rk in ranks.items():
                if cid in rank_ranges:
                    rank_ranges[cid] = [min(rank_ranges[cid][0], rk), max(rank_ranges[cid][1], rk)]
            top = out["ranking"][:top_n]
            scenarios.append({
                "category": cat,
                "delta_pp": delta,
                "weights_pct": {k: round(v, 1) for k, v in new.items()},
                "top1_same": bool(top and base_top and top[0] == base_top[0]),
                "top1": top[0] if top else None,
                "topn_changes": sorted(set(top) ^ set(base_top)),
                "max_rank_shift": max((abs(s) for s in shifts.values()), default=0),
                "moved": {cid: s for cid, s in shifts.items() if s != 0},
            })
    stable = all(s["top1_same"] for s in scenarios)
    return {"delta_pp": pp, "scenarios": scenarios, "rank_ranges": rank_ranges, "top1_stable": stable}


# -------------------------------------------------------------------- main
def run_site(mission, site, defaults, cands, ctx) -> dict:
    mission_id = mission["id"]
    target_feats = resolve_target(site, defaults, ctx.get("target_meas"))
    weights = nominal_feature_weights(mission_id, ctx)
    base = classify(cands, mission, target_feats, weights, ctx)
    top_n = ctx["config"]["thresholds"]["top_n_analogs"]
    sens = sensitivity(mission_id, mission, target_feats, cands, ctx, base)

    entries = []
    for c in cands:
        r = base["results"][c["id"]]
        conf, reasons = confidence(c, r, ctx)
        r["confidence"], r["confidence_reasons"] = conf, reasons
        entry = {
            "id": c["id"],
            "status": r["status"],
            "rank": r.get("rank"),
            "score": None if r["score"] is None else round(r["score"], 4),
            "score_pct": None if r["score"] is None else round(r["score"] * 100),
            "confidence": conf,
            "confidence_reasons": reasons,
            "coverage": {"target": round(r["target_coverage"], 3), "earth": round(r["earth_coverage"], 3)},
            "rank_range": sens["rank_ranges"].get(c["id"]),
            "filters": [{"id": ch["constraint"]["id"], "feature_id": ch["constraint"]["feature_id"], "op": ch["constraint"]["op"],
                         "limit": ch["constraint"]["limit"], "result": ch["result"]} for ch in r["filters"]],
            "features": [
                {**feature_row(fid, c, target_feats, ctx, per=p),
                 "weight_nominal": round(p["weight_nominal"], 4), "weight_used": round(p["weight_used"], 4)}
                for fid, p in r["per_feature"].items()
            ],
            "limitations": analog_limitations(r, ctx),
        }
        is_analog = r["status"] == "ranked" and r["rank"] <= top_n
        entry["group"] = "analog" if is_analog else ("low_match" if r["status"] == "ranked" else r["status"])
        ranked_scores = [base["results"][cid]["score"] for cid in base["ranking"]]
        entry["card"] = None if is_analog else build_card(c, r, len(base["ranking"]), mission, target_feats, weights, cands, ctx, ranked_scores)
        entries.append(entry)
    entries.sort(key=lambda e: (e["rank"] is None, e["rank"] or 0, {"rejected": 0, "cannot_evaluate": 1}.get(e["status"], 2), e["id"]))

    target_cov = next(iter(base["results"].values()))["target_coverage"] if base["results"] else 0
    validation = []
    for vid in ctx["config"].get("validation_ids", []):
        r = base["results"].get(vid)
        if r:
            validation.append({"id": vid, "status": r["status"], "rank": r.get("rank"), "of": len(base["ranking"]),
                               "score_pct": None if r["score"] is None else round(r["score"] * 100)})
    return {
        "site_id": site["id"],
        "target_coverage": round(target_cov, 3),
        "target_features": {fid: {**(target_feats.get(fid) or {"value": None, "status": "TODO"}),
                                  "display": fmt_measure(target_feats.get(fid), ctx["fdefs"][fid].get("unit"))}
                            for fid in weights},
        "weights_nominal": {k: round(v, 4) for k, v in weights.items()},
        "counts": {
            "analog": sum(1 for e in entries if e["group"] == "analog"),
            "low_match": sum(1 for e in entries if e["group"] == "low_match"),
            "rejected": sum(1 for e in entries if e["group"] == "rejected"),
            "cannot_evaluate": sum(1 for e in entries if e["group"] == "cannot_evaluate"),
        },
        "candidates": entries,
        "validation": validation,
        "sensitivity": sens,
    }


def check_target_sources(targets: dict, sources: dict) -> list[str]:
    """Every non-null target value must cite a known source."""
    problems = []
    blocks = [(s["id"], s.get("features", {})) for s in targets["sites"]]
    blocks += [(k, v) for k, v in targets.get("defaults", {}).items()]
    for sid, feats in blocks:
        for fid, m in feats.items():
            if fid.startswith("_"):
                continue
            if has_value(m):
                if not m.get("source_id"):
                    problems.append(f"{sid}/{fid}: value without source_id")
                elif m["source_id"] not in sources:
                    problems.append(f"{sid}/{fid}: unknown source_id '{m['source_id']}'")
    return problems


def main(argv: list[str] | None = None) -> int:
    ctx = load_inputs()
    ctx["cat"] = categorical_table(ctx["config"])
    problems = check_target_sources(ctx["targets"], ctx["sources"])
    problems += [f"target_measurements.csv {sid}/{fid}: unknown source_id '{m['source_id']}'"
                 for sid, feats in ctx["target_meas"].items() for fid, m in feats.items() if m["source_id"] not in ctx["sources"]]
    if problems:
        print("Source check failed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    cands = load_earth(ctx["fdefs"], DATASETS / "earth_candidates.csv", DATASETS / "earth_features.csv")
    for c in cands:
        for fid, m in c["features"].items():
            if m.get("source_id") and m["source_id"] not in ctx["sources"]:
                print(f"Unknown source_id '{m['source_id']}' for {c['id']}/{fid}", file=sys.stderr)
                return 1
    sample = any(m.get("status") == "SAMPLE" for c in cands for m in c["features"].values())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    write_json(WEB_DATA / "earth_candidates.json", {"schema_version": 1, "generated_at": now, "contains_sample": sample, "candidates": cands})

    sites = {s["id"]: s for s in ctx["targets"]["sites"]}
    for mission in ctx["missions"]:
        if mission["id"] not in ctx["config"]["mission_features"]:
            continue
        site_ids = mission["target_site_ids"] + mission.get("reference_site_ids", [])
        out = {
            "schema_version": 1,
            "generated_at": now,
            "mission_id": mission["id"],
            "contains_sample": sample,
            "method": {
                "weights_pct": {k: v for k, v in ctx["config"]["weights_pct"][mission["id"]].items() if not k.startswith("_")},
                "features": ctx["config"]["mission_features"][mission["id"]],
                "scales": {k: v for k, v in ctx["config"]["scales"].items() if not k.startswith("_")},
                "categorical_similarity": {k: v for k, v in ctx["config"]["categorical_similarity"].items() if not k.startswith("_")},
                "thresholds": ctx["config"]["thresholds"],
                "hard_filters": [c["id"] for c in hard_filters(mission)],
                "special_rules": ctx["config"]["special_rules"],
            },
            "sites": {sid: run_site(mission, sites[sid], ctx["targets"].get("defaults", {}), cands, ctx) for sid in site_ids},
        }
        write_json(WEB_DATA / "results" / f"{mission['id']}.json", out, compact=True)
        top = out["sites"][mission["default_site_id"]]
        names = {c["id"]: c["name"] for c in cands}
        print(f"{mission['name']}: {len(site_ids)} sites scored. Default site '{mission['default_site_id']}' "
              f"(target coverage {round(top['target_coverage'] * 100)}%) top: "
              + ", ".join(f"{names[e['id']]} {e['score_pct']}%" for e in top["candidates"] if e["group"] == "analog"))
    if sample:
        print("NOTE: Earth data contains SAMPLE placeholders. Results are not scientific yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
