"""Tests for the data scripts (common, fetch_context_data, fetch_earthdata) and the new scoring rules. No network.

Run: .venv/bin/python -m pytest pipeline/tests -q -c pipeline/pytest.ini
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import compute_scores as cs  # noqa: E402
import fetch_context_data as fc  # noqa: E402
import fetch_earthdata as fe  # noqa: E402


# ------------------------------------------------------------------ terrain
def _plane_dataset(lat0: float, lon0: float, slope_deg: float):
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    res, n = 1 / 3600, 900
    lats = lat0 + n / 2 * res - np.arange(n)[:, None] * res - res / 2
    z = (lats - lat0) * 111132.0 * np.tan(np.radians(slope_deg)) * np.ones((1, n))
    mem = MemoryFile()
    with mem.open(driver="GTiff", height=n, width=n, count=1, dtype="float64", crs="EPSG:4326",
                  transform=from_origin(lon0 - n / 2 * res, lat0 + n / 2 * res, res, res)) as d:
        d.write(z, 1)
    return mem


@pytest.mark.unit
def test_resampled_plane_keeps_its_slope_and_has_no_roughness():
    # Arrange
    mem = _plane_dataset(45.0, 10.0, 10.0)
    # Act
    with mem.open() as ds:
        grid = common.resample_local(ds, 45.0, 10.0, 3000, 200)
    slope, rough = common.terrain_stats(grid, 200)
    # Assert
    assert slope == pytest.approx(10.0, abs=0.2)
    assert rough < 0.5


@pytest.mark.unit
def test_row_without_value_becomes_todo_and_drops_source():
    r = common.row("candidate_id", "x", "slope_deg", None, "°", "pc-nasadem", "high", {}, "no tile")
    assert r["status"] == "TODO" and r["value"] == "" and r["source_id"] == "" and r["confidence"] == ""


# ------------------------------------------------------------------ geology / soil rules
@pytest.mark.unit
@pytest.mark.parametrize("text,expected", [
    ("Basalt, Holocene: basalt", "basalt"),
    ("Metanorthosite and anorthositic gneiss", "anorthosite"),
    ("impact breccia, impact melt rock, crater fill", "impact_breccia"),
    ("local glacier till: till, gravel", "sedimentary"),
    ("Holocene to middle Pliocene volcanic rocks: rhyolite, dacite", None),
    ("basalt flows interbedded with sandstone", "mixed"),
])
def test_map_lithology(text, expected):
    assert fc.map_lithology(text) == expected


@pytest.mark.unit
def test_pick_geology_uses_most_detailed_scale_with_a_match():
    units = [
        {"scale": "large", "name": "Scoria cones", "lith": "", "descrip": ""},
        {"scale": "medium", "name": "Laupahoehoe Volcanics", "lith": "basaltic volcanic rocks", "descrip": ""},
        {"scale": "tiny", "name": "Cenozoic sedimentary rocks", "lith": "sedimentary rocks", "descrip": ""},
    ]
    unit, cat, used = fc.pick_geology(units)
    assert cat == "basalt" and unit["scale"] == "medium" and len(used) == 1


@pytest.mark.unit
def test_pick_geology_returns_mixed_when_same_scale_disagrees():
    units = [{"scale": "small", "name": "A", "lith": "sedimentary"}, {"scale": "small", "name": "B", "lith": "impact breccia"}]
    assert fc.pick_geology(units)[1] == "mixed"


@pytest.mark.unit
@pytest.mark.parametrize("comp,expected", [
    ({"compname": "Cinder land", "taxorder": None}, "volcanic_ash_cinder"),
    ({"compname": "Rock outcrop", "taxorder": None}, "bare_rock"),
    ({"compname": "Gilman", "taxorder": "Entisols", "taxsuborder": "Orthents", "taxgrtgroup": "Torriorthents"}, "desert_soil"),
    ({"compname": "X", "taxorder": "Mollisols", "taxsuborder": "Ustolls", "taxgrtgroup": "Argiustolls"}, None),
])
def test_map_usda(comp, expected):
    assert fc.map_usda(comp)[0] == expected


@pytest.mark.unit
def test_unlisted_wrb_class_is_not_forced_into_a_category():
    assert fc.map_soil("wrb", "Luvisols") == (None, "")
    assert fc.map_soil("wrb", "Cryosols") == ("ice_rich_mantle", "low")


# ------------------------------------------------------------------ coordinates
@pytest.mark.unit
def test_candidate_without_reference_stays_unverified_with_old_position():
    c = {"id": "x", "name": "X", "lat": "10.0", "lon": "20.0"}
    v = fc.verify_one(c, {"source": "none", "note": "no entry"}, None, 1.0)
    assert v["status"] == "unverified" and v["verified_lat"] == "" and v["old_lat"] == 10.0
    assert "worldview.earthdata.nasa.gov" in v["worldview_url"]


@pytest.mark.unit
def test_verification_keeps_the_original_old_position_on_rerun(monkeypatch):
    monkeypatch.setattr(fc, "lookup_reference", lambda s, r: (10.0, 20.5, "https://example.test"))
    c = {"id": "x", "name": "X", "lat": "10.0", "lon": "20.5"}          # already moved by an earlier run
    prev = {"old_lat": "10.0", "old_lon": "20.0"}
    v = fc.verify_one(c, {"source": "wikidata", "ref_id": "Q1"}, prev, 1.0)
    assert v["old_lon"] == 20.0 and v["status"] == "updated" and v["distance_km"] > 50


# ------------------------------------------------------------------ ATI proxy
def _lst(day, night, qc=0):
    return {"MYD11A1_061_LST_Day_1km": str(day), "MYD11A1_061_LST_Night_1km": str(night),
            "MYD11A1_061_QC_Day": str(qc), "MYD11A1_061_QC_Night": str(qc)}


def _alb(a, qa=0):
    return {"MCD43A3_061_Albedo_WSA_shortwave": str(a), "MCD43A3_061_BRDF_Albedo_Band_Mandatory_Quality_shortwave": str(qa)}


@pytest.mark.unit
def test_ati_is_median_of_good_days_only():
    lst = {"d1": _lst(300, 280), "d2": _lst(310, 290), "d3": _lst(300, 280, qc=2), "d4": _lst(300, 299.5)}
    alb = {"d1": _alb(0.2), "d2": _alb(0.2), "d3": _alb(0.2), "d4": _alb(0.2)}
    ati, n = fe.ati_for_site(lst, alb)
    assert n == 2 and ati == pytest.approx(0.8 / 20)


@pytest.mark.unit
def test_scaled_handles_raw_and_fill_values():
    assert fe.scaled(15000, fe.LST_SCALE, fe.LST_FILL) == pytest.approx(300.0)
    assert fe.scaled(300.0, fe.LST_SCALE, fe.LST_FILL) == 300.0
    assert fe.scaled(32.767, fe.ALBEDO_SCALE, fe.ALBEDO_FILL) is None
    assert fe.scaled(250, fe.ALBEDO_SCALE, fe.ALBEDO_FILL) == pytest.approx(0.25)


# ------------------------------------------------------------------ scoring rules
@pytest.mark.unit
def test_filters_without_earth_data_are_not_applied():
    mission = {"constraints": [
        {"id": "slope", "feature_id": "slope_200m_deg", "op": "<", "limit": 15, "hard_filter": True},
        {"id": "rock", "feature_id": "rock_cover_pct", "op": "<", "limit": 5, "hard_filter": True, "earth_applicable": False},
    ]}
    assert [c["id"] for c in cs.hard_filters(mission)] == ["slope"]


@pytest.mark.unit
def test_renormalised_weights_drop_features_without_target_value():
    weights = {"a": 0.5, "b": 0.25, "c": 0.25}
    target = {"a": {"value": 1.0}, "b": {"value": None}, "c": {"min": 0, "max": 5}}
    cands = [{"features": {"a": {"value": 2.0}}}, {"features": {}}]
    out = cs.renormalised_weights(weights, target, cands)
    assert out["b"]["weight"] == 0.0 and not out["b"]["has_target"]
    assert out["a"]["weight"] == pytest.approx(2 / 3, abs=1e-4) and out["a"]["earth_sites_with_data"] == 1


@pytest.mark.unit
def test_provenance_columns_are_carried_into_json():
    p = cs.provenance_of({"dataset": "NASADEM", "product_id": "NASADEM_HGT", "version": "001", "processing": " ", "source_url": "u"})
    assert p == {"provenance": {"dataset": "NASADEM", "product_id": "NASADEM_HGT", "version": "001", "source_url": "u"}}


@pytest.mark.unit
def test_skyfall_slope_filter_is_labelled_coarse_screening():
    missions = cs.load_json(cs.WEB_DATA / "missions.json")["missions"]
    slope = next(c for m in missions if m["id"] == "skyfall" for c in m["constraints"] if c["id"] == "slope")
    assert slope["feature_id"] == "slope_200m_deg" and "coarse-scale screening (~200 m)" in slope["label"]


@pytest.mark.unit
@pytest.mark.parametrize("level,expected", [(0, 0.0), (1, 0.0), (2, None)])
def test_depth_to_ice_is_a_mismatch_without_perennial_ice(level, expected):
    ctx = {"config": {"special_rules": {"no_ice_means_depth_mismatch": True}},
           "earth_features": {"ice_presence": {"value": level}}}
    sim, missing = cs.similarity("ice_depth_m", "numeric", {"min": 0.5, "max": 3}, None, ctx)
    assert sim == expected
    assert (missing is None) == (expected is not None)
