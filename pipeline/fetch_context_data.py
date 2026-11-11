#!/usr/bin/env python3
"""Coordinates, soil, rock type, permafrost and logistics for the Earth candidates. No login needed.

    python pipeline/fetch_context_data.py coords      # verify candidate coordinates (run FIRST, then re-run fetch_real_data.py earth)
    python pipeline/fetch_context_data.py soil        # SoilGrids WRB (global, non-NASA) + USDA SSURGO/STATSGO (US)
    python pipeline/fetch_context_data.py geology     # Macrostrat map units (aggregates USGS and other geological surveys)
    python pipeline/fetch_context_data.py permafrost  # ESA CCI Permafrost v5 (2023) + MODIS annual minimum LST
    python pipeline/fetch_context_data.py logistics   # OurAirports + OpenStreetMap roads (both non-NASA)
    python pipeline/fetch_context_data.py all         # soil, geology, permafrost, logistics (not coords)
    add --only id1,id2 to limit the candidates

All mapping rules (soil class → regolith category, lithology → geology category, permafrost → ice level,
distances → access index) live in pipeline/context_rules.json and are PROVISIONAL team decisions.

NASA/USGS products that need an Earthdata login (GGD318 permafrost map, SEDAC gROADS/GPW, VIIRS Black
Marble) are NOT used here; see README_DATA.md for the manual steps. The open datasets used instead are
labelled non-NASA in the source list.
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from common import (CACHE, DATASETS, EARTH_FIELDS, ROOT, WEB_DATA, download, haversine_km, http_form, http_json,
                    load_candidates, load_feature_rows, parse_only, provenance, row, write_csv)

RULES = json.loads((Path(__file__).parent / "context_rules.json").read_text())
TODAY = date.today().isoformat()
POLITE_PAUSE_S = 2.0

GVP_WFS = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?service=WFS&version=1.0.0&request=GetFeature"
           "&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=application/json&CQL_FILTER=Volcano_Number={vn}")
GVP_PAGE = "https://volcano.si.edu/volcano.cfm?vn={vn}"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIDATA_PAGE = "https://www.wikidata.org/wiki/{qid}"
GNIS_SERVICE = "https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer"
WORLDVIEW = "https://worldview.earthdata.nasa.gov/?v={w},{s},{e},{n}&l=VIIRS_SNPP_CorrectedReflectance_TrueColor,Coastlines_15m"
SOILGRIDS = "https://rest.isric.org/soilgrids/v2.0/classification/query?lon={lon}&lat={lat}&number_classes=3"
SDA = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"
MACROSTRAT = "https://macrostrat.org/api/v2/geologic_units/map?lat={lat}&lng={lon}"
MACROSTRAT_SOURCE = "https://macrostrat.org/api/v2/defs/sources?source_id={sid}"
OURAIRPORTS = "https://davidmegginson.github.io/ourairports-data/airports.csv"
OVERPASS = "https://overpass-api.de/api/interpreter"
OVERPASS_MIRRORS = [OVERPASS, "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CCI_BASE = "https://dap.ceda.ac.uk/neodc/esacci/permafrost/data"
CCI_FILES = {
    ("PFR", "north"): "permafrost_extent/L4/area4/pp/v05.0/northern_hemisphere/2023/ESACCI-PERMAFROST-L4-PFR-MODISLST_CRYOGRID-AREA4_PP-2023-fv05.0.nc",
    ("PFR", "south"): "permafrost_extent/L4/area4/pp/v05.0/Antarctica/2023/ESACCI-PERMAFROST-L4-PFR-MODISLST_CRYOGRID-AREA27_PP-2023-fv05.0.nc",
    ("ALT", "north"): "active_layer_thickness/L4/area4/pp/v05.0/northern_hemisphere/2023/ESACCI-PERMAFROST-L4-ALT-MODISLST_CRYOGRID-AREA4_PP-2023-fv05.0.nc",
    ("ALT", "south"): "active_layer_thickness/L4/area4/pp/v05.0/Antarctica/2023/ESACCI-PERMAFROST-L4-ALT-MODISLST_CRYOGRID-AREA27_PP-2023-fv05.0.nc",
}
VERIFY_FIELDS = ["candidate_id", "name", "old_lat", "old_lon", "verified_lat", "verified_lon", "distance_km", "status", "source",
                 "ref_id", "ref_label", "source_url", "point_type", "worldview_url", "checked_on", "note"]


# =================================================================== COORDINATES
def lookup_reference(src: str, ref_id: str) -> tuple[float, float, str]:
    """(lat, lon, url) from the Smithsonian GVP web feature service or a Wikidata entity (P625)."""
    if src == "gvp":
        feats = http_json(GVP_WFS.format(vn=ref_id))["features"]
        if not feats:
            raise ValueError(f"GVP volcano {ref_id} not found")
        lon, lat = feats[0]["geometry"]["coordinates"][:2]
        return float(lat), float(lon), GVP_PAGE.format(vn=ref_id)
    if src == "wikidata":
        ent = http_json(WIKIDATA_ENTITY.format(qid=ref_id))["entities"][ref_id]
        val = ent["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"]
        return float(val["latitude"]), float(val["longitude"]), WIKIDATA_PAGE.format(qid=ref_id)
    if src == "gnis":
        return gnis_lookup(ref_id)
    raise ValueError(f"unknown coordinate source '{src}'")


def gnis_lookup(ref_id: str) -> tuple[float, float, str]:
    """USGS GNIS via The National Map geonames service. ref_id = '<layer>:<gaz_id>' (layer 5 landforms, 8 Antarctica)."""
    from urllib.parse import urlencode

    layer, gaz_id = ref_id.split(":")
    antarctic = layer == "8"
    q = {"where": f"gaz_id={int(gaz_id)}", "outFields": "gaz_id,latitude,longitude" if antarctic else "gaz_id",
         "returnGeometry": "false" if antarctic else "true", "outSR": "4326", "f": "json"}
    url = f"{GNIS_SERVICE}/{layer}/query?{urlencode(q)}"
    feats = http_json(url).get("features") or []
    if not feats:
        raise ValueError(f"GNIS {ref_id} not found")
    if antarctic:
        a = feats[0]["attributes"]
        return float(a["latitude"]), float(a["longitude"]), url
    lon, lat = feats[0]["geometry"]["points"][0]
    return float(lat), float(lon), url


def worldview_link(lat: float, lon: float, half_deg: float = 0.15) -> str:
    return WORLDVIEW.format(w=round(lon - half_deg, 3), s=round(lat - half_deg, 3), e=round(lon + half_deg, 3), n=round(lat + half_deg, 3))


def verify_one(c: dict, ref: dict, previous: dict | None, tol_km: float) -> dict:
    old_lat = float(previous["old_lat"]) if previous else float(c["lat"])
    old_lon = float(previous["old_lon"]) if previous else float(c["lon"])
    base = {"candidate_id": c["id"], "name": c["name"], "old_lat": old_lat, "old_lon": old_lon, "source": ref.get("source", "none"),
            "ref_id": ref.get("ref_id", ""), "ref_label": ref.get("ref_label", ""), "point_type": ref.get("point_type", ""),
            "checked_on": TODAY, "note": ref.get("note", "")}
    if not ref or ref.get("source") in ("", "none"):
        return {**base, "verified_lat": "", "verified_lon": "", "distance_km": "", "status": "unverified", "source_url": "",
                "worldview_url": worldview_link(old_lat, old_lon)}
    lat, lon, url = lookup_reference(ref["source"], ref["ref_id"])
    d = haversine_km(old_lat, old_lon, lat, lon)
    status = "verified" if d <= tol_km else "updated"
    return {**base, "verified_lat": round(lat, 5), "verified_lon": round(lon, 5), "distance_km": round(d, 2), "status": status,
            "source_url": url, "worldview_url": worldview_link(lat, lon)}


def run_coords(only: list[str] | None) -> list[dict]:
    with open(DATASETS / "coordinate_sources.csv", encoding="utf-8") as f:
        refs = {r["candidate_id"]: r for r in csv.DictReader(f)}
    vpath = DATASETS / "coordinate_verification.csv"
    previous = {}
    if vpath.exists():
        with open(vpath, encoding="utf-8") as f:
            previous = {r["candidate_id"]: r for r in csv.DictReader(f)}
    with open(DATASETS / "earth_candidates.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, cands = reader.fieldnames, list(reader)
    results, new_cands = [], []
    for c in cands:
        if only and c["id"] not in only:
            results.append(previous.get(c["id"])) if c["id"] in previous else None
            new_cands.append(c)
            continue
        v = verify_one(c, refs.get(c["id"], {}), previous.get(c["id"]), RULES["coordinate_tolerance_km"])
        results.append(v)
        time.sleep(POLITE_PAUSE_S)
        if v["status"] in ("verified", "updated"):
            src_name = {"gvp": "Smithsonian GVP", "wikidata": "Wikidata", "gnis": "USGS GNIS"}[v["source"]]
            note = (f"{src_name} {v['ref_id']} ({v['ref_label']}, {v['point_type']}), checked {TODAY}. "
                    f"Old assistant-typed position was {v['distance_km']} km away.")
            new_cands.append({**c, "lat": v["verified_lat"], "lon": v["verified_lon"], "position_status": v["status"], "position_note": note})
        else:
            new_cands.append({**c, "position_status": "unverified",
                              "position_note": "Assistant-typed position; no reference found. " + v["note"]})
        print(f"  {c['name'][:40]:40s} {v['status']:10s} {v['distance_km']!s:>6} km  {v['source']} {v['ref_id']}")
    with open(DATASETS / "earth_candidates.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(new_cands)
    results = [r for r in results if r]
    with open(vpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=VERIFY_FIELDS)
        w.writeheader()
        w.writerows(results)
    (WEB_DATA / "coordinate_verification.json").write_text(
        json.dumps({"checked_on": TODAY, "tolerance_km": RULES["coordinate_tolerance_km"], "rows": results}, indent=1, ensure_ascii=False) + "\n")
    print(f"→ {vpath.relative_to(ROOT)} and web/data/coordinate_verification.json. "
          "Positions changed: re-run `fetch_real_data.py earth` for the updated sites.")
    return results


# =================================================================== SOIL
def soilgrids_class(lat: float, lon: float) -> tuple[str | None, list]:
    r = http_json(SOILGRIDS.format(lat=lat, lon=lon), timeout=90)
    return r.get("wrb_class_name"), r.get("wrb_class_probability") or []


def sda_component(lat: float, lon: float) -> dict | None:
    """Dominant soil component at a point from USDA NRCS Soil Data Access (SSURGO, STATSGO where SSURGO is missing)."""
    sql = ("SELECT TOP 1 mu.mukey, mu.muname, c.compname, c.comppct_r, c.taxorder, c.taxsuborder, c.taxgrtgroup "
           "FROM mapunit mu INNER JOIN component c ON c.mukey = mu.mukey "
           f"WHERE mu.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('POINT({lon} {lat})')) "
           "ORDER BY c.comppct_r DESC")
    r = http_json(SDA, {"format": "JSON+COLUMNNAME", "query": sql}, timeout=90)
    table = r.get("Table") or []
    if len(table) < 2:
        return None
    return dict(zip(table[0], table[1]))


def map_soil(scheme: str, cls: str | None, sub: str | None = None) -> tuple[str | None, str]:
    table = RULES["soil_to_regolith"][scheme]
    for key in (sub, cls):
        if key and table.get(key):
            conf = "low" if key in RULES["soil_to_regolith"]["low_confidence_classes"] else "medium"
            return table[key], conf
    return None, ""


def map_usda(comp: dict) -> tuple[str | None, str]:
    """Miscellaneous-area name first, then 'Torri-' great groups, then suborder/order."""
    rules = RULES["soil_to_regolith"]
    misc = {k: v for k, v in rules["usda_miscellaneous_areas"].items() if not k.startswith("_")}
    if comp.get("compname") in misc:
        return misc[comp["compname"]], "medium"
    group = comp.get("taxgrtgroup") or ""
    for prefix, cat in rules["usda_great_group_prefixes"].items():
        if not prefix.startswith("_") and group.startswith(prefix):
            return cat, "medium"
    return map_soil("usda", comp.get("taxorder"), comp.get("taxsuborder"))


def soil_rows(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    if c.get("country") == "USA":
        comp = sda_component(lat, lon)
        if comp:
            cat, conf = map_usda(comp)
            raw = f"{comp.get('taxorder')} / {comp.get('taxsuborder')} / {comp.get('taxgrtgroup')} ({comp.get('compname')}, {comp.get('comppct_r')}% of map unit {comp.get('mukey')})"
            prov = provenance("USDA NRCS Soil Data Access (SSURGO, STATSGO where SSURGO is missing)", f"map unit {comp.get('mukey')}",
                              "current SDA release", f"queried {TODAY}", "SSURGO 1:12,000–1:63,360 survey polygons",
                              "Point-in-polygon query; dominant component (highest comppct_r); miscellaneous-area name, great group or order mapped to "
                              "a regolith category with pipeline/context_rules.json (provisional)", SDA)
            return [row("candidate_id", c["id"], "soil_class", raw, "", "usda-sda", "high", prov, "US government (USDA), not NASA/USGS.", status="measured"),
                    row("candidate_id", c["id"], "regolith_type", cat, "", "usda-sda", conf or "", prov,
                        "" if cat else f"USDA class '{comp.get('taxorder')} / {comp.get('taxsuborder')} / {comp.get('taxgrtgroup')}' has no match in the regolith categories.",
                        status="verify")]
    cls, probs = soilgrids_class(lat, lon)
    prov = provenance("ISRIC SoilGrids 2.0 WRB reference soil group (NON-NASA, modelled)", "SoilGrids v2.0 MostProbable WRB", "2.0",
                      "model trained on soil profiles up to ~2020", "250 m",
                      "REST point query; most probable WRB group; mapped to a regolith category with pipeline/context_rules.json (provisional)",
                      "https://rest.isric.org/soilgrids/v2.0/docs")
    if not cls:
        reason = "SoilGrids returns no class here (SoilGrids does not map Antarctica or ice/water/rock-only cells)."
        return [row("candidate_id", c["id"], "soil_class", None, "", "", "", prov, reason),
                row("candidate_id", c["id"], "regolith_type", None, "", "", "", prov, reason)]
    cat, conf = map_soil("wrb", cls)
    raw = f"{cls} (top classes: " + ", ".join(f"{n} {p}%" for n, p in probs) + ")"
    return [row("candidate_id", c["id"], "soil_class", raw, "", "isric-soilgrids", "low", prov, "Modelled 250 m soil map, third-party.", status="measured"),
            row("candidate_id", c["id"], "regolith_type", cat, "", "isric-soilgrids", "low" if cat else "", prov,
                "" if cat else f"WRB class '{cls}' has no match in the regolith categories (left empty, not forced).", status="verify")]


# =================================================================== GEOLOGY
SCALE_ORDER = {"large": 0, "medium": 1, "small": 2, "tiny": 3}


def map_lithology(text: str) -> str | None:
    t = text.lower()
    hits = {cat for cat, words in RULES["lithology_to_geology"].items() if not cat.startswith("_")
            and any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in words)}
    if not hits:
        return None
    return hits.pop() if len(hits) == 1 else "mixed"


def pick_geology(units: list[dict]) -> tuple[dict, str | None, list[dict]]:
    """Walk map scales from most to least detailed; return (first unit used, category, units at that scale)."""
    tiers: dict[int, list[dict]] = {}
    for u in units:
        tiers.setdefault(SCALE_ORDER.get(u.get("scale"), 9), []).append(u)
    for k in sorted(tiers):
        cats = {map_lithology(" ".join(filter(None, [u.get("name"), u.get("lith"), u.get("descrip")]))) for u in tiers[k]} - {None}
        if cats:
            return tiers[k][0], (cats.pop() if len(cats) == 1 else "mixed"), tiers[k]
    first = tiers[min(tiers)]
    return first[0], None, first


def geology_rows(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    units = (http_json(MACROSTRAT.format(lat=lat, lon=lon)).get("success") or {}).get("data") or []
    base = provenance("Macrostrat geologic map compilation (aggregates USGS, GSC and other survey maps; third-party service)",
                      "", "API v2", f"queried {TODAY}", "", "", "https://macrostrat.org/api/v2/geologic_units/map")
    if not units:
        reason = "Macrostrat has no mapped unit at this point."
        return [row("candidate_id", c["id"], "lithology", None, "", "", "", base, reason),
                row("candidate_id", c["id"], "geology_type", None, "", "", "", base, reason)]
    u, cat, used = pick_geology(units)
    src_ref = ""
    try:
        srcs = (http_json(MACROSTRAT_SOURCE.format(sid=u["source_id"])).get("success") or {}).get("data") or []
        src_ref = (srcs[0].get("ref_title") or srcs[0].get("name") or "") if srcs else ""
    except Exception as e:  # source lookup is optional context
        print(f"    source lookup failed for {u.get('source_id')}: {e}", file=sys.stderr)
    prov = {**base, "product_id": "; ".join(f"map_id {x.get('map_id')} (source {x.get('source_id')})" for x in used),
            "resolution": f"map scale class '{u.get('scale')}'",
            "processing": "Point query; units grouped by map scale; the most detailed scale whose lithology matches a category "
                          "is used; more than one category at that scale → 'mixed'; rules in pipeline/context_rules.json (provisional)"}
    conf = "low" if cat in (None, "mixed") or u.get("scale") in ("small", "tiny") else "medium"
    raw = " | ".join(f"{x.get('name')}: {x.get('lith')}" for x in used) + (f" [map: {src_ref}]" if src_ref else "")
    return [row("candidate_id", c["id"], "lithology", raw[:300], "", "macrostrat", conf, prov, "Third-party compilation of survey maps.", status="measured"),
            row("candidate_id", c["id"], "geology_type", cat, "", "macrostrat", conf if cat else "", prov,
                "" if cat else f"Lithology '{u.get('lith')}' has no match in the geology categories.", status="verify")]


# =================================================================== PERMAFROST
def cci_path(var: str, hemi: str) -> Path:
    rel = CCI_FILES[(var, hemi)]
    return download(f"{CCI_BASE}/{rel}", CACHE / "cci" / rel.rsplit("/", 1)[-1])


def cci_sample(var: str, lat: float, lon: float, r: int = 1) -> tuple[float | None, str]:
    """Median of a (2r+1)² window of the 0.01° CCI grid. Returns (value, 'outside'|'nodata'|'ok')."""
    import h5py

    hemi = "north" if lat >= 0 else "south"
    with h5py.File(cci_path(var, hemi)) as h:
        la, lo = h["lat"][:], h["lon"][:]
        if not (la.min() - 0.005 <= lat <= la.max() + 0.005):
            return None, "outside"
        step = float(la[1] - la[0])
        i = int(round((lat - float(la[0])) / step))
        j = int(round((lon - float(lo[0])) / float(lo[1] - lo[0])))
        a = h[var][0, max(i - r, 0): i + r + 1, max(j - r, 0): j + r + 1].astype("float64")
        fill = float(np.asarray(h[var].attrs["_FillValue"]).ravel()[0])
        scale = float(np.asarray(h[var].attrs.get("scale_factor", 1.0)).ravel()[0])
        a[a == fill] = np.nan
        a *= scale
    if np.isnan(a).all():
        return None, "nodata"
    return float(np.nanmedian(a)), "ok"


def cci_prov(var: str, steps: str) -> dict:
    name = {"PFR": "permafrost extent (permafrost fraction PFR, %)", "ALT": "active layer thickness (ALT, m)"}[var]
    return provenance(f"ESA CCI Permafrost {name} — NON-NASA (ESA), driven by NASA MODIS LST + CryoGrid model",
                      f"ESACCI-PERMAFROST-L4-{var}-MODISLST_CRYOGRID", "v5.0", "2023 (annual)", "0.01° (~1 km)", steps,
                      "https://catalogue.ceda.ac.uk/uuid/d235665772ec4b558e9a89ac85595e71")


def permafrost_rows(c: dict, feats: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    ir = RULES["ice_rules"]
    pfr, pfr_state = cci_sample("PFR", lat, lon)
    alt, _ = cci_sample("ALT", lat, lon)
    min_lst = (feats.get((c["id"], "annual_min_lst_K")) or {}).get("value")
    min_lst = float(min_lst) if min_lst not in (None, "") else None
    steps = "Median of the 3×3 cells (0.01°) around the site; ice level from pipeline/context_rules.json ice_rules (provisional)"
    out = [row("candidate_id", c["id"], "permafrost_fraction_pct", None if pfr is None else round(pfr, 0), "%", "esa-cci-permafrost-v5",
               "medium", cci_prov("PFR", steps), "" if pfr is not None else f"CCI has no value here ({pfr_state}).", status="measured")]
    notes, conf = [], "medium"
    if pfr is not None and pfr >= ir["pfr_sporadic_min_pct"]:
        level = 2
        conf = "medium" if pfr >= ir["pfr_permafrost_min_pct"] else "low"
        notes.append(f"CCI permafrost fraction {pfr:.0f}% in this 1 km cell.")
        notes.append(ir["massive_ice_note"])
    elif min_lst is not None:
        level = 1 if min_lst < ir["seasonal_frost_max_lst_K"] else 0
        notes.append(("CCI: " + ("no permafrost modelled here" if pfr is not None else f"site {pfr_state} of the CCI permafrost grid")) +
                     f"; coldest MODIS 8-day surface temperature {min_lst:.1f} K → " + ("seasonal frost." if level else "never freezes."))
        conf = "medium" if level == 0 else "low"
    else:
        level = None
        notes.append("No permafrost value and no MODIS minimum temperature: cannot classify.")
    prov_level = {**cci_prov("PFR", steps), "dataset": cci_prov("PFR", steps)["dataset"] + " + MODIS MOD11A2/MYD11A2 annual minimum LST"}
    out.append(row("candidate_id", c["id"], "ice_presence", level, "0-3", "esa-cci-permafrost-v5", conf, prov_level, " ".join(notes), status="verify"))
    if level == 2:
        depth_note = ("Depth to the permafrost table = CCI active-layer thickness (modelled). In dry permafrost the ground below "
                      "the active layer can be ice-poor, so this is the depth where ice CAN exist, not confirmed ice.")
        if alt is not None and alt < 0.05:
            depth_note += " ALT ≈ 0 m: the model reports almost no summer thaw in this cell (very cold or ice-covered); verify."
        out.append(row("candidate_id", c["id"], "ice_depth_m", None if alt is None else round(alt, 2), "m", "esa-cci-permafrost-v5", "low",
                       cci_prov("ALT", "Median of the 3×3 cells (0.01°) around the site"), depth_note if alt is not None else "CCI ALT has no value here.",
                       status="verify"))
    else:
        out.append(row("candidate_id", c["id"], "ice_depth_m", None, "m", "", "", {},
                       "No permafrost at this site, so depth to ice is not applicable (scored as a mismatch when the level is 0)."))
    return out


# =================================================================== LOGISTICS
def nearest_airport(lat: float, lon: float, rule: dict) -> tuple[float, dict]:
    path = download(OURAIRPORTS, CACHE / "ourairports_airports.csv")
    best, best_row = math.inf, {}
    with open(path, encoding="utf-8") as f:
        for a in csv.DictReader(f):
            if a["type"] not in rule["airport_types"]:
                continue
            if rule["airport_requires_scheduled_service"] and a.get("scheduled_service") != "yes":
                continue
            d = haversine_km(lat, lon, float(a["latitude_deg"]), float(a["longitude_deg"]))
            if d < best:
                best, best_row = d, a
    return best, best_row


_overpass_failures = {"in_a_row": 0}
OVERPASS_GIVE_UP_AFTER = 2   # consecutive all-server failures before the rest of the run skips road queries


def overpass_query(q: str) -> dict:
    """Try the main Overpass server, then public mirrors (the main one often returns 502/504 under load)."""
    if _overpass_failures["in_a_row"] >= OVERPASS_GIVE_UP_AFTER:
        raise RuntimeError("Overpass servers unavailable earlier in this run; skipped")
    last: Exception | None = None
    for url in OVERPASS_MIRRORS:
        try:
            res = http_form(url, {"data": q}, tries=1, timeout=45)
            _overpass_failures["in_a_row"] = 0
            return res
        except Exception as e:  # try the next mirror
            last = e
            print(f"    Overpass {url.split('/')[2]} failed ({e}); trying next", file=sys.stderr)
    _overpass_failures["in_a_row"] += 1
    raise RuntimeError(f"all Overpass servers failed: {last}")


def nearest_road_bucket(lat: float, lon: float, rule: dict) -> tuple[float, bool]:
    """Smallest search box (half-width r km) with at least one OSM road → (r, found). None within the last box → (fallback, False).

    A bounding box is used instead of a circle because large 'around' queries time out on the public servers; a road
    found in the box can be up to r·√2 km away, so the band is approximate."""
    for r_km in rule["road_search_radii_km"]:
        dlat = r_km / 111.0
        dlon = dlat / max(math.cos(math.radians(lat)), 0.05)
        bbox = f"{lat - dlat:.5f},{lon - dlon:.5f},{lat + dlat:.5f},{lon + dlon:.5f}"
        q = f'[out:json][timeout:60];way["highway"~"{rule["road_highway_regex"]}"]({bbox});out ids 1;'
        res = overpass_query(q)
        time.sleep(POLITE_PAUSE_S)
        if res.get("elements"):
            return float(r_km), True
    return float(rule["road_beyond_last_radius_km"]), False


def airport_row(c: dict, d_air: float, ap: dict, rule: dict) -> dict:
    p_air = provenance("OurAirports open data (NON-NASA)", "airports.csv", f"downloaded {TODAY}", "current", "point list",
                       f"Great-circle distance to the nearest {'/'.join(rule['airport_types'])} with scheduled service", OURAIRPORTS)
    return row("candidate_id", c["id"], "airport_distance_km", round(d_air, 1), "km", "ourairports", "high", p_air,
               f"Nearest: {ap.get('name')} ({ap.get('ident')}).", status="measured")


def logistics_rows_without_roads(c: dict, d_air: float, ap: dict, rule: dict, err: Exception) -> list[dict]:
    reason = (f"OpenStreetMap Overpass servers did not answer on {TODAY} ({str(err)[:80]}). Re-run "
              "`fetch_context_data.py logistics --only {id}` later. Not estimated.").replace("{id}", c["id"])
    return [airport_row(c, d_air, ap, rule),
            row("candidate_id", c["id"], "road_distance_km", None, "km", "", "", {}, reason),
            row("candidate_id", c["id"], "logistics_index", None, "0-1", "", "", {}, "Needs the road distance. " + reason)]


def logistics_rows(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    rule = RULES["logistics_rule"]
    d_air, ap = nearest_airport(lat, lon, rule)
    try:
        d_road, found = nearest_road_bucket(lat, lon, rule)
    except Exception as e:  # OSM servers overloaded: keep the airport value, leave road + index TODO with the reason
        return logistics_rows_without_roads(c, d_air, ap, rule, e)
    air_term = math.exp(-d_air / rule["airport_scale_km"])
    road_term = math.exp(-d_road / rule["road_scale_km"])
    index = round((air_term + road_term) / 2, 3)
    p_road = provenance("OpenStreetMap roads via Overpass API (NON-NASA)", "highway ways", f"queried {TODAY}", "current", "vector",
                        f"Smallest square search box (half-width {rule['road_search_radii_km']} km) containing any road/track; band, up to r·√2 km", OVERPASS)
    p_idx = provenance("Derived from OurAirports + OpenStreetMap (NON-NASA)", "logistics_index", "context_rules.json", TODAY, "site",
                       f"mean(exp(−airport_km/{rule['airport_scale_km']}), exp(−road_km/{rule['road_scale_km']})); scales are provisional team choices",
                       "")
    road_note = f"Road/track within {d_road:g} km." if found else f"No road within {rule['road_search_radii_km'][-1]} km (counted as {d_road:g} km)."
    return [
        airport_row(c, d_air, ap, rule),
        row("candidate_id", c["id"], "road_distance_km", d_road, "km", "osm-overpass", "medium", p_road, road_note, status="measured"),
        row("candidate_id", c["id"], "logistics_index", index, "0-1", "osm-overpass", "medium", p_idx,
            "Access only. Communications, permits (e.g. Antarctic Treaty) and safety are NOT captured. NASA SEDAC gROADS / "
            "GPW and VIIRS Black Marble need an Earthdata login (see README_DATA.md).", status="derived"),
    ]


# =================================================================== main
def run_part(name: str, fn, only: list[str] | None) -> None:
    rows = []
    feats = load_feature_rows()
    for c in load_candidates(only):
        try:
            got = fn(c, feats) if name == "permafrost" else fn(c)
        except Exception as e:  # keep previous rows for this site; never fill in
            print(f"  {c['id']}: {name} failed ({e}); previous rows kept", file=sys.stderr)
            continue
        write_csv(DATASETS / "earth_features.csv", EARTH_FIELDS, got, key=("candidate_id", "feature"))  # save per site
        rows += got
        print(f"  {c['name'][:36]:36s} " + "; ".join(f"{r['feature']}={str(r['value'])[:40] or 'TODO'}" for r in got), flush=True)
        time.sleep(POLITE_PAUSE_S if name in ("soil", "geology") else 0)
    print(f"{name}: {len(rows)} rows for {len({r['candidate_id'] for r in rows})} sites")


PARTS = {"soil": soil_rows, "geology": geology_rows, "permafrost": permafrost_rows, "logistics": logistics_rows}


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    only = parse_only(argv)
    if what == "coords":
        run_coords(only)
        return 0
    for name in (PARTS if what == "all" else [what]):
        print(f"== {name}")
        run_part(name, PARTS[name], only)
    print("Now run: python3 pipeline/compute_scores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
