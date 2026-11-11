"""Tests for pipeline/fetch_target_context.py and the target-context output of compute_scores. No network.

Run: .venv/bin/python -m pytest pipeline/tests -q -c pipeline/pytest.ini
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import common  # noqa: E402
import compute_scores as cs  # noqa: E402
import fetch_target_context as ft  # noqa: E402


# ------------------------------------------------------------------ Diviner PRP mesh indexing
@pytest.mark.unit
def test_prp_cell_matches_first_and_last_rows_of_the_real_file():
    # Row 0 of DLRE_PRP_SOUTH.TAB: centre −75.905°, −45.016° → first cell; row 2,879,998: −75.905°, 135.016° → last cell.
    # The mesh is not an exact planar grid: the estimate may be a few cells off (prp_window checks coverage).
    for (ix, iy), (ex, ey) in ((ft.prp_cell(-75.905227661, -45.015949249), (0, 0)),
                               (ft.prp_cell(-75.905227661, 135.015945435), (ft.PRP_CELLS - 1, ft.PRP_CELLS - 1))):
        assert abs(ix - ex) <= 3 and abs(iy - ey) <= 3


@pytest.mark.unit
def test_prp_cell_of_row_1440000_is_the_middle_column():
    # Row 1,440,000: x ≈ 0 km, y ≈ −300.9 km (centre −80.006°, −90.064°) → ix = 600, iy = 0.
    ix, iy = ft.prp_cell(-80.005546570, -90.063697815)
    assert abs(ix - 600) <= 3 and abs(iy - 0) <= 3


@pytest.mark.unit
def test_diviner_rows_outside_the_mesh_are_todo_not_guessed():
    site = {"id": "x", "name": "X", "position": {"lat": -70.0, "lon": 0.0}}
    rows = ft.diviner_rows(site)
    assert {r["feature"] for r in rows} == {f for f, _ in ft.DIVINER_FEATURES}
    assert all(r["status"] == "TODO" and r["value"] == "" for r in rows)


@pytest.mark.unit
def test_prp_window_grows_until_the_circle_is_not_clipped(monkeypatch):
    import numpy as np
    calls = []

    def fake_box(ix0, iy0, pad):
        calls.append(pad)
        # one triangle at the target, one 3 km away that sits on the box edge until pad ≥ 20
        edge = 1.0 if pad < 20 else 0.0
        return np.array([[0.0, -85.0, 100, 200, -999, 0.0], [0.0, -85.0 + 3 / 30.32, 100, 200, -999, edge]])

    monkeypatch.setattr(ft, "prp_box", fake_box)
    win, d = ft.prp_window(-85.0, 0.0)
    assert len(win) == 2 and calls == [13, 19, 25]


# ------------------------------------------------------------------ geologic units
@pytest.mark.unit
def test_point_in_polygon_handles_holes():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
    pts, parts = outer + hole, [0, len(outer)]
    assert ft.point_in_polygon(2, 2, pts, parts)
    assert not ft.point_in_polygon(5, 5, pts, parts)
    assert not ft.point_in_polygon(12, 5, pts, parts)


@pytest.mark.unit
def test_describe_units_drops_units_under_ten_percent_and_sorts():
    assert ft.describe_units({"Ec": 88, "Nc": 9, "pNc": 3}) == "Ec 88%"
    assert ft.describe_units({"A": 30, "B": 70}) == "B 70%; A 30%"


@pytest.mark.unit
def test_mars_unit_counts_on_a_single_polygon():
    square = ((-10, -10, 10, 10), [(-10, -10), (10, -10), (10, 10), (-10, 10)], [0], "Av Amazonian volcanic unit")
    counts = ft.mars_unit_counts([square], 0.0, 0.0)
    assert list(counts) == ["Av Amazonian volcanic unit"] and sum(counts.values()) > 50


# ------------------------------------------------------------------ which targets are sampled
@pytest.mark.unit
def test_region_centres_and_missing_positions_are_skipped(tmp_path, monkeypatch):
    targets = {"sites": [
        {"id": "a", "body": "mars", "position": {"lat": 43.3, "lon": -161.5}},
        {"id": "b", "body": "mars", "position": {"lat": 49.0, "lon": -171.9, "kind": "region_centre"}},
        {"id": "c", "body": "mars", "position": {"lat": None, "lon": None}},
        {"id": "d", "body": "moon", "position": {"lat": -85.0, "lon": 0.0}},
    ]}
    (tmp_path / "targets.json").write_text(json.dumps(targets))
    monkeypatch.setattr(ft, "WEB_DATA", tmp_path)
    use, skip = ft.sampled_sites("mars")
    assert [s["id"] for s in use] == ["a"]
    assert {k["site"]["id"]: ("region" in k["reason"]) for k in skip} == {"b": True, "c": False}


# ------------------------------------------------------------------ compute_scores
@pytest.mark.unit
def test_text_target_measurements_are_kept_as_text(tmp_path):
    p = tmp_path / "tm.csv"
    p.write_text("site_id,feature,value,unit,status,source_id,confidence,note\n"
                 "haworth,geologic_unit,pNc Crater Unit (Pre-Nectarian) 100%,,measured,usgs-moon-unified-geology,medium,\n"
                 "haworth,annual_max_temp_K,123.0,K,measured,pds-diviner-prp,medium,\n", encoding="utf-8")
    fdefs = {"geologic_unit": {"kind": "text"}, "annual_max_temp_K": {"kind": "numeric"}}
    meas = cs.load_target_measurements(p, fdefs)["haworth"]
    assert meas["geologic_unit"]["value"].startswith("pNc")
    assert meas["annual_max_temp_K"]["value"] == 123.0


@pytest.mark.unit
def test_target_context_only_lists_target_side_context_features():
    fdefs = {"slope_240m_deg": {"unit": "°"}, "annual_max_temp_K": {"unit": "K", "context_only": True, "context_side": "target"},
             "soil_class": {"context_only": True}}
    feats = {"slope_240m_deg": {"value": 10.0}, "annual_max_temp_K": {"value": 123.0}, "soil_class": {"value": "x"}}
    out = cs.target_context(feats, fdefs)
    assert list(out) == ["annual_max_temp_K"] and out["annual_max_temp_K"]["display"] == "123 K"


@pytest.mark.unit
def test_every_new_target_position_cites_a_known_source():
    targets = json.loads((common.WEB_DATA / "targets.json").read_text(encoding="utf-8"))
    sources = {s["id"] for s in json.loads((common.WEB_DATA / "sources.json").read_text(encoding="utf-8"))["sources"]}
    for s in targets["sites"]:
        p = s["position"]
        if p.get("lat") is not None:
            assert p.get("source_id") in sources, s["id"]
        else:
            assert p["status"] == "TODO", s["id"]
