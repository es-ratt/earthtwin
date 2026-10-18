"""Unit tests for the similarity engine, units and mapping helpers (no database)."""
import math

import pytest

from app.ingest import mapping as M
from app.services import units as U
from app.services.similarity import Value, assess, compare, input_hash
from app.services.vocabulary import CRITERIA, CRITERION_BY_KEY, PROFILES


def V(x, c="verified", oid="o"):
    return Value(x, c, oid)


def test_gaussian_identical_is_one_and_decays():
    c = CRITERION_BY_KEY["slope"]
    assert compare(c, V(5.0), V(5.0))["similarity"] == pytest.approx(1.0)
    s = compare(c, V(10.0), V(5.0))["similarity"]
    assert s == pytest.approx(math.exp(-0.5))


def test_missing_values_are_never_matches():
    c = CRITERION_BY_KEY["slope"]
    assert compare(c, None, V(5.0)) == {"similarity": None, "status": "missing_site", "detail": "No Earth-site value"}
    assert compare(c, V(5.0), None)["similarity"] is None
    assert compare(CRITERION_BY_KEY["lithology"], V([]), V(["basalt"]))["similarity"] is None


def test_jaccard_and_boolean_and_log_ratio():
    assert compare(CRITERION_BY_KEY["lithology"], V(["basalt", "tephra"]), V(["basalt", "regolith_fine"]))["similarity"] == pytest.approx(1 / 3)
    assert compare(CRITERION_BY_KEY["ground_ice"], V(True), V(False))["similarity"] == 0
    assert compare(CRITERION_BY_KEY["relief"], V(200.0), V(200.0))["similarity"] == pytest.approx(1)
    a = compare(CRITERION_BY_KEY["relief"], V(400.0), V(200.0))["similarity"]
    b = compare(CRITERION_BY_KEY["relief"], V(100.0), V(200.0))["similarity"]
    assert a == pytest.approx(b)  # symmetric in ratio


def test_insufficient_data_when_coverage_low():
    w = {k: 0 for k in CRITERION_BY_KEY}
    w.update(slope=10, relief=10, temperature=10, aridity=10)
    site = {"mean_slope_deg": V(3.0)}
    tgt = {"mean_slope_deg": V(3.0), "local_relief_m": V(100.0), "mean_surface_temp_k": V(200.0), "annual_precip_mm": V(0.0)}
    r = assess(CRITERIA, w, site, tgt, "mars")
    assert r["status"] == "insufficient_data" and r["score"] is None
    assert r["coverage"] == pytest.approx(0.25)
    assert set(r["missing"]) == {"relief", "temperature", "aridity"}


def test_score_is_weighted_mean_and_weights_matter():
    site = {"mean_slope_deg": V(5.0), "local_relief_m": V(100.0), "annual_precip_mm": V(0.0)}
    tgt = {"mean_slope_deg": V(10.0), "local_relief_m": V(100.0), "annual_precip_mm": V(0.0)}
    w = {k: 0 for k in CRITERION_BY_KEY}
    w.update(slope=10, relief=10, aridity=10)
    r1 = assess(CRITERIA, w, site, tgt, "mars")
    expected = 100 * (math.exp(-0.5) + 1 + 1) / 3
    assert r1["status"] == "scored" and r1["score"] == pytest.approx(expected, abs=0.01)
    w2 = dict(w, slope=40)
    r2 = assess(CRITERIA, w2, site, tgt, "mars")
    assert r2["score"] < r1["score"]  # more weight on the weakest criterion lowers the index
    assert sum(c["contribution"] for c in r1["criteria"] if c["contribution"]) == pytest.approx(r1["score"], abs=0.01)


def test_demo_inputs_are_labelled():
    site = {"mean_slope_deg": V(5.0, "demo"), "local_relief_m": V(100.0), "annual_precip_mm": V(0.0)}
    tgt = {"mean_slope_deg": V(5.0), "local_relief_m": V(100.0), "annual_precip_mm": V(0.0)}
    w = {k: 0 for k in CRITERION_BY_KEY}
    w.update(slope=10, relief=10, aridity=10)
    r = assess(CRITERIA, w, site, tgt, "moon")
    assert r["is_demo"] and r["lowest_data_class"] == "demo"


def test_input_hash_is_deterministic_and_sensitive():
    w = PROFILES["general"]["weights"]
    s, t = {"mean_slope_deg": V(5.0)}, {"mean_slope_deg": V(6.0)}
    th = {"min_coverage": 0.6, "min_criteria": 3}
    h1 = input_hash(CRITERIA, w, s, t, th)
    assert h1 == input_hash(CRITERIA, dict(w), {"mean_slope_deg": V(5.0)}, {"mean_slope_deg": V(6.0)}, th)
    assert h1 != input_hash(CRITERIA, dict(w, slope=1), s, t, th)
    assert h1 != input_hash(CRITERIA, w, {"mean_slope_deg": V(5.1)}, t, th)


def test_negative_weight_rejected():
    with pytest.raises(ValueError):
        assess(CRITERIA, {"slope": -1}, {}, {}, "moon")


def test_units():
    assert U.normalize(1.5, "km", "m")[0] == 1500
    assert U.normalize(20, "°C", "K")[0] == pytest.approx(293.15)
    assert U.normalize(20, "°C", "K_diff")[0] == pytest.approx(20)  # ranges have no offset
    assert U.normalize(32, "F", "K")[0] == pytest.approx(273.15)
    assert U.normalize(100, "percent_grade", "deg")[0] == pytest.approx(45)
    assert U.normalize(50, "%", "fraction")[0] == pytest.approx(0.5)
    with pytest.raises(U.UnitError):
        U.normalize(1, None, "m")
    with pytest.raises(U.UnitError):
        U.normalize(1, "furlong", "m")
    assert U.unit_hint_from_header("Temp (°C)") == "°c"
    assert U.unit_hint_from_header("slope_deg") == "deg"


def test_coordinate_conventions():
    assert M.convert_coords(10, 350, "mars", "east_360", "planetocentric") == (10, -10)
    assert M.convert_coords(10, 10, "mars", "west_360", "planetocentric") == (10, -10)
    assert M.convert_coords(10, 190, "mars", "west_360", "planetocentric") == (10, 170)
    lat, _ = M.convert_coords(45, 0, "mars", "east_180", "planetographic")
    assert 44.6 < lat < 45  # planetocentric latitude is slightly smaller
    with pytest.raises(ValueError):
        M.convert_coords(10, 200, "mars", "east_180", "planetocentric")
    with pytest.raises(ValueError):
        M.convert_coords(95, 0, "moon", "east_180", "planetocentric")
    with pytest.raises(ValueError):
        M.convert_coords(10, 0, "moon", "east_180", "planetographic")


def test_propose_mapping_marks_units_for_review():
    p = M.propose("earth_sites", ["Name", "Latitude", "Longitude", "slope_deg", "Temp (C)", "notes_x"], [])
    assert p["fields"]["name"] == "Name" and p["fields"]["lat"] == "Latitude"
    vs = {v["column"]: v for v in p["variables"]}
    assert vs["slope_deg"]["variable"] == "mean_slope_deg" and vs["slope_deg"]["unit"] == "deg"
    assert vs["Temp (C)"]["variable"] == "mean_surface_temp_k" and vs["Temp (C)"]["unit_source"] == "header"
    assert p["needs_review"] is True
    assert "notes_x" in p["unmapped_columns"]
