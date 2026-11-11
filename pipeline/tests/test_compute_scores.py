"""Tests for pipeline/compute_scores.py. Run: python3 -m pytest pipeline/tests -q"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compute_scores as cs  # noqa: E402


@pytest.fixture(scope="module")
def ctx() -> dict:
    c = cs.load_inputs()
    c["cat"] = cs.categorical_table(c["config"])
    return c


def write_earth(tmp_path: Path, rows: dict[str, dict], lat: float = 70.0) -> tuple[Path, Path]:
    cpath, fpath = tmp_path / "c.csv", tmp_path / "f.csv"
    with open(cpath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "lat", "lon", "country", "is_baseline", "why_candidate", "position_status", "position_note"])
        for cid in rows:
            w.writerow([cid, cid.title(), lat, 0, "X", 0, "", "verify", ""])
    with open(fpath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["candidate_id", "feature", "value", "unit", "status", "source_id", "confidence", "note"])
        for cid, feats in rows.items():
            for fid, v in feats.items():
                if v is None:
                    w.writerow([cid, fid, "", "", "TODO", "", "", ""])
                else:
                    w.writerow([cid, fid, v, "", "SAMPLE", "sample", "low", ""])
    return cpath, fpath


# ---------------------------------------------------------------- similarity
@pytest.mark.unit
def test_numeric_similarity_is_exp_of_scaled_distance(ctx):
    sim, missing = cs.similarity("slope_deg", "numeric", {"value": 5}, {"value": 15}, {**ctx, "earth_features": {}})
    assert missing is None
    assert sim == pytest.approx(math.exp(-10 / ctx["config"]["scales"]["slope_deg"]))


@pytest.mark.unit
def test_range_target_is_perfect_inside_and_decays_outside(ctx):
    t = {"min": 0, "max": 15}
    inside, _ = cs.similarity("slope_deg", "numeric", t, {"value": 7}, {**ctx, "earth_features": {}})
    outside, _ = cs.similarity("slope_deg", "numeric", t, {"value": 25}, {**ctx, "earth_features": {}})
    assert inside == 1.0
    assert outside == pytest.approx(math.exp(-10 / ctx["config"]["scales"]["slope_deg"]))


@pytest.mark.unit
def test_categorical_similarity_uses_symmetric_table(ctx):
    a, _ = cs.similarity("geology_type", "categorical", {"value": "anorthosite"}, {"value": "impact_breccia"}, {**ctx, "earth_features": {}})
    b, _ = cs.similarity("geology_type", "categorical", {"value": "impact_breccia"}, {"value": "anorthosite"}, {**ctx, "earth_features": {}})
    none, _ = cs.similarity("geology_type", "categorical", {"value": "anorthosite"}, {"value": "sedimentary"}, {**ctx, "earth_features": {}})
    assert a == b == 0.5
    assert none == 0.0


@pytest.mark.unit
def test_missing_values_are_never_guessed(ctx):
    assert cs.similarity("slope_deg", "numeric", {"value": None}, {"value": 3}, {**ctx, "earth_features": {}}) == (None, "no_target_data")
    assert cs.similarity("slope_deg", "numeric", {"value": 3}, {"value": None}, {**ctx, "earth_features": {}}) == (None, "no_earth_data")


@pytest.mark.unit
def test_no_ground_ice_counts_as_depth_mismatch(ctx):
    sim, missing = cs.similarity("ice_depth_m", "numeric", {"min": 0.5, "max": 3}, {"value": None},
                                 {**ctx, "earth_features": {"ice_presence": {"value": 0}}})
    assert (sim, missing) == (0.0, None)


# ------------------------------------------------------------------- weights
@pytest.mark.unit
@pytest.mark.parametrize("mission_id", ["artemis-iv", "skyfall"])
def test_nominal_weights_sum_to_one_and_follow_categories(ctx, mission_id):
    w = cs.nominal_feature_weights(mission_id, ctx)
    assert sum(w.values()) == pytest.approx(1.0)
    pct = ctx["config"]["weights_pct"][mission_id]
    for cat in ("terrain", "temperature", "light", "ice", "logistics"):
        cat_sum = sum(v for f, v in w.items() if ctx["fdefs"][f]["category"] == cat)
        assert cat_sum == pytest.approx(pct[cat] / 100.0)


@pytest.mark.unit
def test_renormalised_weights_sum_to_one_over_available_features(ctx, tmp_path):
    c, f = write_earth(tmp_path, {"a": {"slope_deg": 5, "rock_cover_pct": 2, "thermal_inertia_tiu": 200, "logistics_index": 0.5}})
    cands = cs.load_earth(ctx["fdefs"], c, f)
    site = next(s for s in ctx["targets"]["sites"] if s["id"] == "ap-105")
    target = cs.resolve_target(site, ctx["targets"]["defaults"])
    r = cs.score_candidate(cands[0], target, cs.nominal_feature_weights("skyfall", ctx), ctx)
    used = [p["weight_used"] for p in r["per_feature"].values() if p["similarity"] is not None]
    assert sum(used) == pytest.approx(1.0)
    assert all(p["weight_used"] == 0 for p in r["per_feature"].values() if p["similarity"] is None)


# ---------------------------------------------------------- filters + cards
@pytest.mark.unit
def test_hard_filter_rejects_and_explains(ctx, tmp_path):
    good = {"slope_200m_deg": 5, "rock_cover_pct": 2, "thermal_inertia_tiu": 200, "ice_presence": 3, "ice_depth_m": 1,
            "regolith_type": "ice_rich_mantle", "logistics_index": 0.5}
    steep = {**good, "slope_200m_deg": 22}
    c, f = write_earth(tmp_path, {"good": good, "steep": steep, "good2": {**good, "logistics_index": 0.9}})
    cands = cs.load_earth(ctx["fdefs"], c, f)
    mission = next(m for m in ctx["missions"] if m["id"] == "skyfall")
    site = next(s for s in ctx["targets"]["sites"] if s["id"] == "ap-105")
    out = cs.run_site(mission, site, ctx["targets"]["defaults"], cands, ctx)
    steep_e = next(e for e in out["candidates"] if e["id"] == "steep")
    assert steep_e["status"] == "rejected"
    card = steep_e["card"]
    assert card["verdict"] == "Rejected" and card["reason_type"] == "hard-filter fail"
    assert card["numbers"][0]["earth"].startswith("22") and card["numbers"][0]["limit"].startswith("< 15")
    assert "slope (200 m) limit allowed 22" in card["what_would_change"]
    assert card["confidence"] == "low"  # SAMPLE data


@pytest.mark.unit
def test_unknown_hard_filter_value_means_cannot_evaluate(ctx, tmp_path):
    # slope_200m_deg missing → the (applied) slope filter cannot be checked
    c, f = write_earth(tmp_path, {"x": {"slope_deg": 5, "rock_cover_pct": None, "thermal_inertia_tiu": 200, "logistics_index": 0.5}})
    cands = cs.load_earth(ctx["fdefs"], c, f)
    mission = next(m for m in ctx["missions"] if m["id"] == "skyfall")
    site = next(s for s in ctx["targets"]["sites"] if s["id"] == "ap-105")
    out = cs.run_site(mission, site, ctx["targets"]["defaults"], cands, ctx)
    e = out["candidates"][0]
    assert e["status"] == "cannot_evaluate"
    assert e["card"]["verdict"] == "Cannot be evaluated"
    assert "slope" in e["card"]["what_would_change"].lower()


@pytest.mark.unit
def test_artemis_has_no_slope_filter_until_limit_is_known(ctx):
    mission = next(m for m in ctx["missions"] if m["id"] == "artemis-iv")
    assert cs.hard_filters(mission) == []
    hls = next(c for c in mission["constraints"] if c["id"] == "hls-slope-limit")
    assert hls["limit"] is None and hls["status"] == "TODO"


# ------------------------------------------------------------ derived values
@pytest.mark.unit
def test_derived_sun_elevation_and_cold_index(ctx, tmp_path):
    c, f = write_earth(tmp_path, {"warm": {"annual_min_lst_K": 280}, "cold": {"annual_min_lst_K": 220}}, lat=75.0)
    cands = {x["id"]: x for x in cs.load_earth(ctx["fdefs"], c, f)}
    assert cands["warm"]["features"]["max_sun_elev_deg"]["value"] == pytest.approx(38.44)
    assert cands["cold"]["features"]["cold_index"]["value"] == 1.0
    assert cands["warm"]["features"]["cold_index"]["value"] == 0.0


# ---------------------------------------------------------- data honesty
@pytest.mark.unit
def test_every_target_value_cites_a_known_source(ctx):
    assert cs.check_target_sources(ctx["targets"], ctx["sources"]) == []


@pytest.mark.unit
def test_measured_target_values_override_hand_entered_ones(ctx, tmp_path):
    p = tmp_path / "tm.csv"
    p.write_text("site_id,feature,value,unit,status,source_id,confidence,note\n"
                 "haworth,slope_240m_deg,12.5,°,measured,pds-lola-ldem-75s-240m,medium,test\n")
    meas = cs.load_target_measurements(p)
    site = next(s for s in ctx["targets"]["sites"] if s["id"] == "haworth")
    t = cs.resolve_target(site, ctx["targets"]["defaults"], meas)
    assert t["slope_240m_deg"]["value"] == 12.5 and t["slope_240m_deg"]["status"] == "measured"
    assert t["ice_presence"]["value"] == 2  # hand-entered value still there


@pytest.mark.unit
def test_target_measurement_without_source_is_refused(tmp_path):
    p = tmp_path / "tm.csv"
    p.write_text("site_id,feature,value,unit,status,source_id,confidence,note\nhaworth,slope_240m_deg,12.5,°,measured,,,\n")
    with pytest.raises(ValueError, match="no source_id"):
        cs.load_target_measurements(p)


@pytest.mark.unit
def test_earth_value_without_source_is_refused(ctx, tmp_path):
    c, f = write_earth(tmp_path, {"a": {"slope_deg": 5}})
    text = f.read_text().replace(",SAMPLE,sample,", ",measured,,")
    f.write_text(text)
    with pytest.raises(ValueError, match="no source_id"):
        cs.load_earth(ctx["fdefs"], c, f)


@pytest.mark.unit
def test_sensitivity_covers_each_used_category_both_ways(ctx):
    cands = cs.load_earth(ctx["fdefs"], cs.DATASETS / "earth_candidates.csv", cs.DATASETS / "earth_features.csv")
    mission = next(m for m in ctx["missions"] if m["id"] == "skyfall")
    site = next(s for s in ctx["targets"]["sites"] if s["id"] == "ap-105")
    out = cs.run_site(mission, site, ctx["targets"]["defaults"], cands, ctx)
    cats = {(s["category"], s["delta_pp"]) for s in out["sensitivity"]["scenarios"]}
    for cat in ("terrain", "temperature", "ice", "logistics"):
        assert (cat, 10) in cats and (cat, -10) in cats
    for s in out["sensitivity"]["scenarios"]:
        assert sum(s["weights_pct"].values()) == pytest.approx(100, abs=0.5)


@pytest.mark.integration
def test_full_run_writes_results(tmp_path, monkeypatch):
    assert cs.main([]) == 0
    assert (cs.WEB_DATA / "results" / "artemis-iv.json").exists()
    assert (cs.WEB_DATA / "results" / "skyfall.json").exists()
