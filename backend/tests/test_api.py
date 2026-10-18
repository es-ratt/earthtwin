"""End-to-end tests through the HTTP API: seeding, import pipeline, automatic
integration, scoring, persistence, rasters, layers, exports and security."""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import do_import

ROOT = Path(__file__).resolve().parents[2]
VERIFIED = {"data_class": "verified", "publisher": "Test Agency", "source_url": "https://example.org/data", "name": "Test dataset"}


def test_seed_and_catalogue(client):
    st = client.get("/api/state").json()
    assert st["mode"] == "demo" and st["sites"] == 17 and st["targets"] == 9
    sites = client.get("/api/sites").json()
    assert {"atacama-yungay", "haughton-impact-structure", "mcmurdo-dry-valleys", "death-valley"} <= {s["id"] for s in sites}
    s = client.get("/api/sites/atacama-yungay").json()
    assert s["observations"] and all(o["data_class"] == "demo" for o in s["observations"])
    assert any(c["doi"] == "10.1126/science.1089143" for c in s["citations"])
    ds = client.get("/api/datasets").json()
    assert any(d["status"] == "planned" and d["active"] == 0 for d in ds)
    assert client.get("/api/targets?world=mars").json()[0]["world_id"] == "mars"


def test_rank_is_reproducible_and_weights_change_results(client):
    a = client.post("/api/analysis/rank", json={"target_id": "arcadia-planitia"}).json()
    b = client.post("/api/analysis/rank", json={"target_id": "arcadia-planitia"}).json()
    assert [r["input_hash"] for r in a["results"]] == [r["input_hash"] for r in b["results"]]
    assert [r["assessment_id"] for r in a["results"]] == [r["assessment_id"] for r in b["results"]]
    assert a["is_demo"]
    c = client.post("/api/analysis/rank", json={"target_id": "arcadia-planitia", "weights": {"ground_ice": 0, "slope": 40}}).json()
    assert c["profile"] == "custom"
    assert [r["score"] for r in a["results"]] != [r["score"] for r in c["results"]]
    aid = a["results"][0]["assessment_id"]
    stored = client.get(f"/api/assessments/{aid}").json()
    assert stored["score"] == a["results"][0]["score"] and stored["engine_version"] == "1.0.0"
    assert client.post("/api/analysis/rank", json={"target_id": "nope"}).status_code == 400
    assert client.post("/api/analysis/rank", json={"target_id": "gale-crater", "weights": {"bogus": 1}}).status_code == 400


def test_deactivating_demo_yields_insufficient_data(client):
    demo = next(d for d in client.get("/api/datasets").json() if d["data_class"] == "demo")
    r = client.post(f"/api/datasets/{demo['id']}/activate?active=false", headers=client.admin)
    assert r.status_code == 200
    res = client.post("/api/analysis/rank", json={"target_id": "gale-crater"}).json()
    assert res["n_scored"] == 0 and all(x["status"] == "insufficient_data" and x["score"] is None for x in res["results"])
    assert client.get("/api/state").json()["mode"] == "empty"
    # sites (reference catalogue) remain visible
    assert len(client.get("/api/sites").json()) == 17


def test_admin_required(client):
    assert client.post("/api/imports", files={"file": ("a.csv", b"name,lat,lon\nx,1,2\n")}).status_code == 401
    assert client.post("/api/imports", files={"file": ("a.csv", b"name,lat,lon\nx,1,2\n")}, headers={"X-Admin-Token": "wrong"}).status_code == 401
    ds = client.get("/api/datasets").json()[0]["id"]
    assert client.delete(f"/api/datasets/{ds}").status_code == 401


def test_import_sites_with_measurements_integrates_everywhere(client):
    csv = ("site_id,Name,Country,Latitude,Longitude,categories,slope_deg,relief_m,Temp (C),annual_precip_mm_per_yr,lithology,ground_ice,extra_note\n"
           "test-polar-desert,Test Polar Desert,Testland,-75.0,160.0,polar;arid,4,150,-25,5,basalt;regolith_fine;ice,yes,keep me\n"
           "bad-row,Bad Row,Testland,120,0,polar,4,150,-25,5,basalt,yes,\n").encode()
    r = client.post("/api/imports", files={"file": ("sites.csv", csv)}, data={"kind": "earth_sites"}, headers=client.admin).json()
    m = r["proposed_mapping"]
    # Temperature unit comes from the header and must be confirmed; it is proposed, not applied.
    tv = next(v for v in m["variables"] if v["column"] == "Temp (C)")
    assert tv["variable"] == "mean_surface_temp_k" and tv["unit_source"] == "header"
    s, job = do_import(client, csv, "sites.csv", "earth_sites", mapping=m, metadata=VERIFIED)
    assert job["status"] == "succeeded", job
    assert s["validation"]["n_rejected"] == 1  # latitude 120 rejected, not silently dropped
    assert any("latitude 120" in i["message"] for i in s["validation"]["issues"])
    # 1. site appears in catalogue with verified measurements and preserved extra field
    site = client.get("/api/sites/test-polar-desert").json()
    obs = {o["variable_key"]: o for o in site["observations"]}
    assert obs["mean_surface_temp_k"]["value"] == pytest.approx(248.15)  # °C → K
    assert obs["mean_surface_temp_k"]["original_unit"] == "°c" or obs["mean_surface_temp_k"]["original_value"] == "-25"
    assert obs["lithology"]["value"] == ["basalt", "ice", "regolith_fine"]
    assert obs["ground_ice"]["value"] is True and obs["mean_slope_deg"]["data_class"] == "verified"
    assert site["extra"]["extra_note"] == "keep me"
    assert site["completeness"]["variables_available"] == 6
    # 2. dataset listed with provenance
    d = next(x for x in client.get("/api/datasets").json() if x["name"] == "Test dataset")
    assert d["active"] == 1 and d["status"] == "ready" and d["n_observations"] == 6 and d["n_records"] == 1
    # 3. ranking includes it with verified data class mix
    res = client.post("/api/analysis/rank", json={"target_id": "arcadia-planitia"}).json()
    row = next(x for x in res["results"] if x["site"]["id"] == "test-polar-desert")
    assert row["status"] == "scored"
    assert any(c["site_class"] == "verified" for c in row["criteria"])
    # 4. revision bumped → UI refresh signal
    assert client.get("/api/state").json()["mode"] == "mixed"
    # 5. exports include it
    text = client.get("/api/export/candidates.csv?target_id=arcadia-planitia").text
    assert "test-polar-desert" in text and "DEMO DATA" in text


def test_missing_unit_blocks_validation(client):
    csv = b"site_id,mean_slope\natacama-yungay,3\n"
    r = client.post("/api/imports", files={"file": ("o.csv", csv)}, data={"kind": "observations"}, headers=client.admin).json()
    m = r["proposed_mapping"]
    m["options"] = {"subject_type": "earth_site", "match_by": "id"}
    for v in m["variables"]:
        v["unit"] = None
    s, _ = do_import(client, csv, "o.csv", "observations", mapping=m, metadata=VERIFIED, expect_ok=False)
    assert s["status"] == "invalid"
    assert any("unit is required" in i["message"] for i in s["validation"]["issues"])


def test_verified_requires_provenance(client):
    csv = b"name,lat,lon\nX,1,2\n"
    s, _ = do_import(client, csv, "x.csv", "earth_sites", metadata={"data_class": "verified", "name": "X"}, expect_ok=False)
    assert s["status"] == "invalid"
    msgs = " ".join(i["message"] for i in s["validation"]["issues"])
    assert "publishing organisation" in msgs and "source URL" in msgs


def test_unsupported_and_malformed_files(client):
    r = client.post("/api/imports", files={"file": ("book.xlsx", b"PK\x03\x04....")}, headers=client.admin)
    assert r.status_code == 422 and "CSV" in r.json()["detail"]
    r = client.post("/api/imports", files={"file": ("fake.tif", b"not a tiff")}, headers=client.admin)
    assert r.status_code == 422 and "magic" in r.json()["detail"]
    r = client.post("/api/imports", files={"file": ("bad.json", b"{not json")}, headers=client.admin)
    assert r.status_code == 422 and "Invalid JSON" in r.json()["detail"]
    r = client.post("/api/imports", files={"file": ("bin.csv", b"a,b\n\x00\x01\x02")}, headers=client.admin)
    assert r.status_code == 422
    r = client.post("/api/imports", files={"file": ("empty.csv", b"")}, headers=client.admin)
    assert r.status_code == 422


def test_long_format_and_new_version_replaces_values(client):
    csv1 = b"subject_id,variable,value,unit\natacama-yungay,mean_slope_deg,2.0,deg\natacama-yungay,annual_precip_mm,0.1,cm/yr\nnobody,mean_slope_deg,1,deg\n"
    r = client.post("/api/imports", files={"file": ("l.csv", csv1)}, data={"kind": "observations_long"}, headers=client.admin).json()
    m = r["proposed_mapping"]
    m["options"] = {"subject_type": "earth_site", "match_by": "id"}
    s, job = do_import(client, csv1, "l.csv", "observations_long", mapping=m, metadata={**VERIFIED, "name": "Long"})
    assert job["status"] == "succeeded"
    assert any("no earth site with id 'nobody'" in i["message"] for i in s["validation"]["issues"])
    site = client.get("/api/sites/atacama-yungay").json()
    pre = [o for o in site["observations"] if o["variable_key"] == "annual_precip_mm"]
    assert any(o["data_class"] == "verified" and o["value"] == pytest.approx(1.0) for o in pre)  # 0.1 cm/yr → 1 mm/yr
    # verified beats demo in resolution
    res = client.post("/api/analysis/rank", json={"target_id": "gale-crater", "site_ids": ["atacama-yungay"]}).json()
    c = next(c for c in res["results"][0]["criteria"] if c["criterion"] == "slope")
    assert c["site_value"] == 2.0 and c["site_class"] == "verified"
    # new version of the same dataset
    did = job["result"]["dataset_id"]
    csv2 = b"subject_id,variable,value,unit\natacama-yungay,mean_slope_deg,7.5,deg\n"
    s2, job2 = do_import(client, csv2, "l2.csv", "observations_long", mapping=m, metadata={**VERIFIED, "name": "Long", "dataset_id": did})
    assert job2["status"] == "succeeded" and job2["result"]["version"] == "v2"
    res = client.post("/api/analysis/rank", json={"target_id": "gale-crater", "site_ids": ["atacama-yungay"]}).json()
    c = next(c for c in res["results"][0]["criteria"] if c["criterion"] == "slope")
    assert c["site_value"] == 7.5
    d = client.get(f"/api/datasets/{did}").json()
    assert len(d["versions"]) == 2


def test_target_import_requires_conventions_and_converts(client):
    csv = b"target_id,name,body,lat,lon,mean_slope_deg\nnew-mars,New Mars Plain,mars,10,200,2\n"
    r = client.post("/api/imports", files={"file": ("t.csv", csv)}, data={"kind": "target_regions"}, headers=client.admin).json()
    m = r["proposed_mapping"]
    for v in m["variables"]:
        v["unit"] = "deg"
    s, _ = do_import(client, csv, "t.csv", "target_regions", mapping=m, metadata={**VERIFIED, "name": "T"}, expect_ok=False)
    assert s["status"] == "invalid" and any("longitude convention" in i["message"] for i in s["validation"]["issues"])
    m["options"] = {"lon_convention": "east_360", "lat_type": "planetocentric"}
    s, job = do_import(client, csv, "t.csv", "target_regions", mapping=m, metadata={**VERIFIED, "name": "T"})
    assert job["status"] == "succeeded"
    t = client.get("/api/targets/new-mars").json()
    assert t["lon"] == -160 and t["world_id"] == "mars" and t["crs"] == "IAU_2015:49900"


def _write_tif(path, arr, crs, transform):
    import rasterio
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                       crs=crs, transform=transform, nodata=-9999) as ds:
        ds.write(arr.astype("float32"), 1)


def test_earth_dem_raster_produces_derived_terrain(client, tmp_path):
    from rasterio.transform import from_origin
    # Test fixture: a synthetic inclined plane around the Atacama site in UTM 19S (metres).
    from pyproj import Transformer
    x0, y0 = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True).transform(-70.02, -24.10)
    n, res = 400, 100.0
    yy, xx = np.mgrid[0:n, 0:n]
    slope = np.tan(np.radians(10))
    arr = (xx * res) * slope  # rises 10° to the east
    tif = tmp_path / "dem.tif"
    _write_tif(tif, arr, "EPSG:32719", from_origin(x0 - n * res / 2, y0 + n * res / 2, res, res))
    r = client.post("/api/imports", files={"file": ("dem.tif", tif.read_bytes())}, data={"kind": "raster"}, headers=client.admin).json()
    assert r["detected_format"] == "geotiff" and r["structure"]["raster"]["detected_body"] == "earth"
    mapping = {"kind": "raster", "raster": {"raster_kind": "elevation", "unit": "m"}}
    s, job = do_import(client, tif, "dem.tif", "raster", mapping=mapping, metadata={**VERIFIED, "name": "Synthetic DEM", "body": "earth"})
    assert job["status"] == "succeeded", job
    assert job["result"]["subjects_covered"] == 1
    obs = {o["variable_key"]: o for o in client.get("/api/sites/atacama-yungay").json()["observations"] if o["data_class"] == "derived"}
    assert obs["mean_slope_deg"]["value"] == pytest.approx(10, abs=0.05)
    assert obs["slope_std_deg"]["value"] < 0.05
    assert obs["local_relief_m"]["value"] == pytest.approx(0.9 * 200 * 100 * slope, rel=0.03)
    assert "km box window" in obs["mean_slope_deg"]["spatial_support"]


def test_planetary_raster_body_mismatch_rejected(client, tmp_path):
    from rasterio.transform import from_origin
    tif = tmp_path / "moon.tif"
    _write_tif(tif, np.zeros((50, 50)), "IAU_2015:30100", from_origin(-10, 10, 0.4, 0.4))
    s, _ = do_import(client, tif, "moon.tif", "raster", mapping={"kind": "raster", "raster": {"raster_kind": "elevation", "unit": "m"}},
                     metadata={**VERIFIED, "name": "Lunar DEM", "body": "earth"}, expect_ok=False)
    assert s["status"] == "invalid"
    assert any("belongs to moon" in i["message"] for i in s["validation"]["issues"])


def test_lunar_raster_scalar_temperature(client, tmp_path):
    from rasterio.transform import from_origin
    tif = tmp_path / "moon_t.tif"
    # Synthetic test fixture: uniform 0 °C field covering Mare Tranquillitatis (23.47E, 0.67N) in lunar lon/lat.
    _write_tif(tif, np.zeros((100, 100)), "IAU_2015:30100", from_origin(20, 4, 0.07, 0.07))
    s, job = do_import(client, tif, "moon_t.tif", "raster",
                       mapping={"kind": "raster", "raster": {"raster_kind": "scalar", "unit": "°C", "variable": "mean_surface_temp_k"}},
                       metadata={**VERIFIED, "name": "Lunar T", "body": "moon"})
    assert job["status"] == "succeeded", job
    t = client.get("/api/targets/mare-tranquillitatis-apollo11").json()
    o = next(o for o in t["observations"] if o["data_class"] == "derived")
    assert o["value"] == pytest.approx(273.15)
    assert job["result"]["subjects_covered"] == 1  # other lunar targets are outside coverage


def test_failed_processing_is_not_success(client, tmp_path, monkeypatch):
    from app.ingest.adapters import raster as R
    from rasterio.transform import from_origin
    tif = tmp_path / "e.tif"
    _write_tif(tif, np.zeros((50, 50)), "EPSG:4326", from_origin(-71, -23, 0.05, 0.05))

    def boom(*a, **k):
        raise R.RasterError("simulated read failure")
    monkeypatch.setattr(R, "extract", boom)
    before = len(client.get("/api/datasets").json())
    s, job = do_import(client, tif, "e.tif", "raster", mapping={"kind": "raster", "raster": {"raster_kind": "elevation", "unit": "m"}},
                       metadata={**VERIFIED, "name": "Will fail", "body": "earth"})
    assert job["status"] == "failed" and "simulated read failure" in job["error"]
    assert len(client.get("/api/datasets").json()) == before  # rolled back
    imp = next(i for i in client.get("/api/imports").json() if i["id"] == s["id"])
    assert imp["status"] == "failed" and "simulated" in imp["job_error"]


def test_map_layer_import(client):
    gj = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"name": "Zone <b>A</b>"},
                     "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]}).encode()
    s, job = do_import(client, gj, "zones.geojson", "map_layer", mapping={"kind": "map_layer", "layer": {"name": "Zones"}},
                       metadata={**VERIFIED, "name": "Zones", "body": "mars"})
    assert job["status"] == "succeeded"
    layers = client.get("/api/layers?body=mars").json()
    lid = next(l["id"] for l in layers if l["name"] == "Zones")
    assert client.get(f"/api/layers/{lid}/geojson").json()["features"][0]["properties"]["name"] == "Zone <b>A</b>"
    assert not any(l["name"] == "Zones" for l in client.get("/api/layers?body=earth").json())


def test_bundle_template_and_reference_rules(client):
    s, job = do_import(client, ROOT / "templates" / "bundle_template.json", "bundle_template.json", "bundle")
    assert job["status"] == "succeeded"
    bad = json.dumps({"earthtwin_bundle": "1.0", "dataset": {"name": "R", "data_class": "reference"},
                      "observations": [{"subject_type": "earth_site", "subject_id": "atacama-yungay", "variable": "mean_slope_deg", "value": 1, "unit": "deg"}]}).encode()
    s, _ = do_import(client, bad, "r.json", "bundle", expect_ok=False)
    assert s["status"] == "invalid"


def test_templates_validate(client):
    """Every shipped template parses and gets a sensible proposal."""
    for name, kind in [("earth_sites_template.csv", "earth_sites"), ("target_regions_template.csv", "target_regions"),
                       ("observations_wide_template.csv", "observations"), ("observations_long_template.csv", "observations_long"),
                       ("map_layer_template.geojson", "map_layer")]:
        r = client.post("/api/imports", files={"file": (name, (ROOT / "templates" / name).read_bytes())}, data={"kind": kind}, headers=client.admin)
        assert r.status_code == 200, (name, r.text)
        assert r.json()["import_kind"] == kind
    assert client.get("/templates/earth_sites_template.csv").status_code == 200


def test_exports(client):
    r = client.get("/api/export/candidates.csv?target_id=jezero-crater&profile=landing_site")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = [l for l in r.text.splitlines() if not l.startswith("#")]
    assert lines[0].startswith("rank,site_id") and len(lines) == 18
    r = client.get("/api/export/comparison.csv?target_id=jezero-crater&site_ids=atacama-yungay,mdrs-utah")
    assert r.status_code == 200 and "mdrs-utah" in r.text and "criterion" in r.text
    r = client.get("/api/export/report.pdf?target_id=jezero-crater&site_ids=atacama-yungay,mdrs-utah")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 5000
    kinds = {e["kind"] for e in client.get("/api/exports").json()}
    assert kinds == {"candidates_csv", "comparison_csv", "report_pdf"}


def test_persistence_across_restart(client):
    csv = b"site_id,name,lat,lon\npersist-me,Persist Me,10,10\n"
    s, job = do_import(client, csv, "p.csv", "earth_sites", metadata={**VERIFIED, "name": "Persist"})
    assert job["status"] == "succeeded"
    # simulate a restart: run startup again against the same data directory (idempotent seeding)
    from app.main import init_app_state
    init_app_state()
    assert client.get("/api/sites/persist-me").status_code == 200
    names = [d["name"] for d in client.get("/api/datasets").json()]
    assert names.count("EarthTwin demonstration measurements") == 1
    # and the database file really lives on disk
    assert (client.data_dir / "earthtwin.sqlite3").exists()


def test_delete_protection_and_delete(client):
    cat = next(d for d in client.get("/api/datasets").json() if d["name"] == "EarthTwin curated analog catalogue")
    assert client.delete(f"/api/datasets/{cat['id']}", headers=client.admin).status_code == 409
    demo = next(d for d in client.get("/api/datasets").json() if d["data_class"] == "demo")
    assert client.delete(f"/api/datasets/{demo['id']}", headers=client.admin).status_code == 200
    assert not client.get("/api/sites/atacama-yungay").json()["observations"]


def test_metadata_edit(client):
    demo = next(d for d in client.get("/api/datasets").json() if d["data_class"] == "demo")
    r = client.patch(f"/api/datasets/{demo['id']}", json={"license": "CC0-1.0"}, headers=client.admin)
    assert r.status_code == 200 and r.json()["license"] == "CC0-1.0"
