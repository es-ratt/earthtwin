"""Context values for the Moon and Mars TARGET sites (shown in the app, never scored).

  python pipeline/fetch_target_context.py diviner     # Moon: Diviner Polar Resource Product (PDS), no login
  python pipeline/fetch_target_context.py geology     # Moon + Mars: USGS global geologic map units, no login
  python pipeline/fetch_target_context.py all

Writes rows to datasets/target_measurements.csv. Rules (same as the rest of the pipeline):
  * every value carries dataset / product / version / resolution / processing / URL;
  * nothing is estimated: if a value cannot be read it is written as TODO with the reason;
  * a position marked "kind": "region_centre" (USGS Gazetteer centre of a huge region) is NOT sampled,
    because a value there says nothing about where a lander would go (team decision 3 in the PDF).

Diviner PRP (LRO-L-DLRE-5-PRP-V2.0, DLRE_PRP_SOUTH.TAB, 605 MB ASCII): fixed 210-byte rows, one per triangle of a
Kaguya polar mesh. The mesh is a 1200 × 1200 grid of 0.5 km cells (two triangles each) on x = R cosφ cosλ,
y = R cosφ sinλ, ordered x from +300 km down, then y from −300 km up. Only the rows near each target are fetched
with HTTP range requests, then triangles are kept by their own centre latitude/longitude (≤ 5 km).
"""
from __future__ import annotations

import csv
import json
import math
import sys

import numpy as np

from common import (CACHE, DATASETS, TARGET_FIELDS, WEB_DATA, R_MARS_SPHERE_M, R_MOON_M, _request,
                    download, provenance, row, write_csv)

WINDOW_KM = 5.0                    # same ±5 km window as the 200 m / 240 m terrain features
UNIT_MIN_SHARE = 0.10              # list geologic units covering at least 10% of the window

PRP_URL = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_prp/dlre_prp_south.tab"
PRP_ROW_BYTES, PRP_CELLS, PRP_CELL_KM, PRP_HALF_KM = 210, 1200, 0.5, 300.0
PRP_ICE_EXCLUDED, PRP_ICE_MAX_M = -999.0, 2.8738
PRP_MAX_LAT = -80.0                # mesh covers the pole to 80°S
PRP_GROW_CELLS, PRP_MAX_GROW = 6, 4  # widen the fetched box when it clips the circle

MOON_GEO_ZIP = "https://asc-astropedia.s3.us-west-2.amazonaws.com/Moon/Geology/Ancillary/unified_geologic_map_of_the_moon_raster.zip"
MOON_GEO_DIR = CACHE / "usgs_moon_geology" / "Unified_Geologic_Map_of_the_Moon_RASTER"
MOON_GEO_TIF = MOON_GEO_DIR / "numerical_versions" / "Unified_Geologic_Map_of_the_Moon_64ppd.tif"
MOON_GEO_CSV = MOON_GEO_DIR / "Dn_GeologicUnit_RGBcolor.csv"
MARS_GEO_SHP = CACHE / "usgs_mars_geology" / "SIM3292_Global_Geology"
MARS_GEO_ZIP = "https://pubs.usgs.gov/sim/3292/downloads/sim3292_database.zip"
MARS_GRID_KM = 1.0                 # sample points every 1 km inside the window (map scale is 1:20M)

PROV_PRP = provenance(
    "LRO Diviner Polar Resource Product (south)", "LRO-L-DLRE-5-PRP-V2.0 / DLRE_PRP_SOUTH.TAB", "2.0 (created 2018-02-21)",
    "first year of LRO mapping orbit (thermal-model fit)", "Kaguya polar mesh, 0.5 km cells (2 triangles each)", "", PRP_URL)
PROV_MOON_GEO = provenance(
    "USGS Unified Geologic Map of the Moon, 1:5M (Fortezzo, Spudis & Harrel 2020)", "Unified_Geologic_Map_of_the_Moon_64ppd.tif",
    "GIS v2 (March 2020)", "n/a (map)", "64 pixels per degree (~474 m along a meridian)", "", MOON_GEO_ZIP)
PROV_MARS_GEO = provenance(
    "USGS SIM 3292 Geologic Map of Mars, 1:20M (Tanaka et al. 2014)", "SIM3292_Global_Geology.shp", "2014",
    "n/a (map)", "1:20,000,000 polygons", "", MARS_GEO_ZIP)


# ------------------------------------------------------------------ helpers
def great_circle_km(lat1, lon1, lat2, lon2, radius_km: float):
    """Vectorised haversine distance (inputs in degrees)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * radius_km * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def sampled_sites(body: str) -> tuple[list[dict], list[dict]]:
    """(sites to sample, TODO reasons for sites that are skipped) for one body."""
    targets = json.loads((WEB_DATA / "targets.json").read_text(encoding="utf-8"))
    use, skip = [], []
    for s in targets["sites"]:
        if s["body"] != body:
            continue
        p = s.get("position") or {}
        if p.get("lat") is None:
            skip.append({"site": s, "reason": "No coordinates for this target yet, so the map cannot be sampled."})
        elif p.get("kind") == "region_centre":
            skip.append({"site": s, "reason": "Position is the USGS Gazetteer centre of a very large region; "
                                              "not sampled (team decision 3: sample boxes inside 30–45°N instead)."})
        else:
            use.append(s)
    return use, skip


def todo_rows(skipped: list[dict], features: list[tuple[str, str]], prov: dict) -> list[dict]:
    return [row("site_id", k["site"]["id"], f, None, u, "", "", prov, k["reason"]) for k in skipped for f, u in features]


# ------------------------------------------------------------------ Diviner PRP
def prp_cell(lat: float, lon: float) -> tuple[int, int]:
    """Approximate (ix, iy) mesh cell. The Kaguya mesh is not an exact planar grid, so this can be off by a few cells;
    prp_window() therefore checks that its box really contains the whole circle."""
    r = R_MOON_M / 1000 * math.cos(math.radians(lat))
    x, y = r * math.cos(math.radians(lon)), r * math.sin(math.radians(lon))
    return int((PRP_HALF_KM - x) / PRP_CELL_KM), int((y + PRP_HALF_KM) / PRP_CELL_KM)


def prp_box(ix0: int, iy0: int, pad: int) -> np.ndarray:
    """Rows (clon, clat, temp_avg, temp_max, ice_depth, on_box_edge) of every triangle in a (2·pad+1)² cell box."""
    out = []
    ix_lo, ix_hi = max(0, ix0 - pad), min(PRP_CELLS - 1, ix0 + pad)
    lo, hi = max(0, iy0 - pad), min(PRP_CELLS - 1, iy0 + pad)
    for ix in range(ix_lo, ix_hi + 1):
        first, last = (ix * PRP_CELLS + lo) * 2, (ix * PRP_CELLS + hi) * 2 + 1
        start = (first + 1) * PRP_ROW_BYTES                      # +1: the header record
        raw = _request(PRP_URL, None, {"Range": f"bytes={start}-{(last + 2) * PRP_ROW_BYTES - 1}"}, tries=5, timeout=120)
        lines = [l for l in raw.decode("ascii").splitlines() if l.count(",") == 14]
        for k, line in enumerate(lines):
            parts = line.split(",")
            edge = ix in (ix_lo, ix_hi) or k < 2 or k >= len(lines) - 2
            out.append([float(parts[i]) for i in (9, 10, 12, 13, 14)] + [float(edge)])
    return np.array(out)


def prp_window(lat: float, lon: float) -> tuple[np.ndarray, np.ndarray]:
    """(triangles within WINDOW_KM, their distances). Grows the box until no in-window triangle touches its edge."""
    ix0, iy0 = prp_cell(lat, lon)
    pad = int(math.ceil(WINDOW_KM / PRP_CELL_KM)) + 3
    for _ in range(PRP_MAX_GROW):
        box = prp_box(ix0, iy0, pad)
        d = great_circle_km(lat, lon, box[:, 1], box[:, 0], R_MOON_M / 1000)
        if d.min() > PRP_CELL_KM:
            raise RuntimeError(f"nearest PRP triangle to {lat}, {lon} is {d.min():.2f} km away; mesh indexing is wrong")
        inside = d <= WINDOW_KM
        if not (box[inside, 5] > 0).any():
            return box[inside, :5], d[inside]
        pad += PRP_GROW_CELLS
    raise RuntimeError(f"PRP box around {lat}, {lon} still clips the {WINDOW_KM} km circle after {PRP_MAX_GROW} tries")


def diviner_rows(site: dict) -> list[dict]:
    p = site["position"]
    if p["lat"] > PRP_MAX_LAT:
        reason = "Outside the Diviner PRP mesh (80–90°S)."
        return [row("site_id", site["id"], f, None, u, "", "", PROV_PRP, reason) for f, u in DIVINER_FEATURES]
    win, _ = prp_window(p["lat"], p["lon"])
    avg, tmax, ice = win[:, 2], win[:, 3], win[:, 4]
    stable = ice[(ice >= 0) & (ice <= PRP_ICE_MAX_M + 1e-6)]
    steps = (f"HTTP range reads of DLRE_PRP_SOUTH.TAB around {p['lat']}, {p['lon']}; kept the {len(win)} triangles whose centre "
             f"lies within {WINDOW_KM:g} km (great circle, R=1737.4 km); median of temp_max / temp_avg; ice_depth −999 means "
             f"ice is not stable within {PRP_ICE_MAX_M} m")
    prov = {**PROV_PRP, "processing": steps}
    model = "Thermal-model output fitted to Diviner data, not a direct measurement."
    pct = round(100 * len(stable) / len(win), 1)
    out = [
        row("site_id", site["id"], "annual_max_temp_K", round(float(np.median(tmax)), 1), "K", "pds-diviner-prp", "medium", prov,
            f"{model} Range in window {tmax.min():.0f}–{tmax.max():.0f} K."),
        row("site_id", site["id"], "annual_avg_temp_K", round(float(np.median(avg)), 1), "K", "pds-diviner-prp", "medium", prov,
            f"{model} Range in window {avg.min():.0f}–{avg.max():.0f} K."),
        row("site_id", site["id"], "ice_stable_area_pct", pct, "%", "pds-diviner-prp", "medium", prov,
            f"{model} Where ice COULD survive in the top ~2.9 m, not where ice has been detected."),
        row("site_id", site["id"], "ice_stable_depth_m",
            round(float(np.median(stable)), 2) if len(stable) else None, "m", "pds-diviner-prp", "medium", prov,
            f"{model} Median over the {pct}% of the window where ice is stable." if len(stable) else
            f"Ice is not stable within {PRP_ICE_MAX_M} m anywhere in the ±{WINDOW_KM:g} km window, so there is no depth to report."),
    ]
    print(f"  {site['name']:32s} Tmax {out[0]['value']:6.1f} K  Tavg {out[1]['value']:6.1f} K  ice-stable {pct:5.1f}%")
    return out


DIVINER_FEATURES = [("annual_max_temp_K", "K"), ("annual_avg_temp_K", "K"), ("ice_stable_area_pct", "%"), ("ice_stable_depth_m", "m")]


def run_diviner() -> list[dict]:
    use, skip = sampled_sites("moon")
    rows = todo_rows(skip, DIVINER_FEATURES, PROV_PRP)
    for s in use:
        rows += diviner_rows(s)
    write_csv(DATASETS / "target_measurements.csv", TARGET_FIELDS, rows, key=("site_id", "feature"))
    return rows


# ------------------------------------------------------------------ geologic units
def describe_units(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    parts = [(k, v / total) for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v / total >= UNIT_MIN_SHARE]
    return "; ".join(f"{k} {round(share * 100)}%" for k, share in parts)


def moon_units_table() -> dict[int, str]:
    with open(MOON_GEO_CSV, encoding="utf-8") as f:
        return {int(r["DN"]): f"{r['Unit']} {r['Unit_Name']} ({r['Unit_Age']})" for r in csv.DictReader(f)}


def ensure_moon_map() -> None:
    if MOON_GEO_TIF.exists():
        return
    import zipfile
    z = download(MOON_GEO_ZIP, CACHE / "usgs_moon_geology" / "raster.zip")
    with zipfile.ZipFile(z) as zf:
        for name in zf.namelist():
            if "/numerical_versions/" in name or name.endswith("Dn_GeologicUnit_RGBcolor.csv"):
                zf.extract(name, CACHE / "usgs_moon_geology")


def moon_unit_counts(ds, lat: float, lon: float, names: dict[int, str]) -> dict[str, int]:
    from rasterio.windows import Window
    km_per_deg = math.pi * R_MOON_M / 1000 / 180
    dlat = WINDOW_KM / km_per_deg + 0.05
    dlon = min(180.0, WINDOW_KM / (km_per_deg * max(math.cos(math.radians(lat)), 1e-3)) + 0.05)
    inv = ~ds.transform
    c0, r0 = inv * (lon - dlon, min(90, lat + dlat))
    c1, r1 = inv * (lon + dlon, max(-90, lat - dlat))
    r0, r1 = max(0, int(r0)), min(ds.height, int(math.ceil(r1)))
    cols = np.arange(int(math.floor(c0)), int(math.ceil(c1)) + 1) % ds.width          # wraps the date line
    block = ds.read(1, window=Window(0, r0, ds.width, r1 - r0))[:, cols]
    rows_lat = ds.transform.f + (np.arange(r0, r1) + 0.5) * ds.transform.e
    cols_lon = ds.transform.c + (cols + 0.5) * ds.transform.a
    glat, glon = np.meshgrid(rows_lat, cols_lon, indexing="ij")
    inside = great_circle_km(lat, lon, glat, glon, R_MOON_M / 1000) <= WINDOW_KM
    vals = block[inside & (block != ds.nodata)]
    counts: dict[str, int] = {}
    for dn, n in zip(*np.unique(vals, return_counts=True)):
        key = names.get(int(dn), f"DN {int(dn)} (not in the unit table)")
        counts[key] = counts.get(key, 0) + int(n)
    return counts


def point_in_polygon(x: float, y: float, points: list, parts: list) -> bool:
    """Even-odd rule over every ring, so holes are handled."""
    inside = False
    bounds = list(parts) + [len(points)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        ring = points[a:b]
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def mars_unit_counts(shapes: list, lat: float, lon: float) -> dict[str, int]:
    km_per_deg = math.pi * R_MARS_SPHERE_M / 1000 / 180
    n = int(WINDOW_KM // MARS_GRID_KM)
    counts: dict[str, int] = {}
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            if math.hypot(i, j) * MARS_GRID_KM > WINDOW_KM:
                continue
            py = lat + i * MARS_GRID_KM / km_per_deg
            px = (lon + j * MARS_GRID_KM / (km_per_deg * math.cos(math.radians(lat))) + 180) % 360 - 180
            hit = next((label for bbox, pts, parts, label in shapes
                        if bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3] and point_in_polygon(px, py, pts, parts)), None)
            key = hit or "no unit (gap in the map)"
            counts[key] = counts.get(key, 0) + 1
    return counts


def load_mars_shapes() -> list:
    import shapefile
    if not MARS_GEO_SHP.with_suffix(".shp").exists():
        raise FileNotFoundError(
            f"{MARS_GEO_SHP}.shp missing. Extract SIM3292_Shapefiles/SIM3292_Global_Geology.(shp,shx,dbf,prj) from {MARS_GEO_ZIP} into "
            f"{MARS_GEO_SHP.parent} (see README_DATA.md).")
    r = shapefile.Reader(str(MARS_GEO_SHP))
    out = []
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        out.append((sr.shape.bbox, [tuple(p) for p in sr.shape.points], list(sr.shape.parts), f"{rec['Unit']} {rec['UnitDesc']}"))
    return out


def geology_row(site: dict, counts: dict[str, int], base_prov: dict, source_id: str, method: str) -> dict:
    p = site["position"]
    text = describe_units(counts)
    prov = {**base_prov, "processing": f"{method} within {WINDOW_KM:g} km of {p['lat']}, {p['lon']}; units with ≥{round(UNIT_MIN_SHARE * 100)}% of the samples, largest first"}
    note = "Geologic map unit (age + landform), NOT a rock type; geology_type stays empty until the team maps units to rock types."
    print(f"  {site['name']:32s} {text}")
    return row("site_id", site["id"], "geologic_unit", text or None, "", source_id, "medium", prov, note)


def run_geology() -> list[dict]:
    import rasterio
    rows = []
    ensure_moon_map()
    names = moon_units_table()
    use, skip = sampled_sites("moon")
    rows += todo_rows(skip, [("geologic_unit", "")], PROV_MOON_GEO)
    with rasterio.open(MOON_GEO_TIF) as ds:
        for s in use:
            counts = moon_unit_counts(ds, s["position"]["lat"], s["position"]["lon"], names)
            rows.append(geology_row(s, counts, PROV_MOON_GEO, "usgs-moon-unified-geology", "Raster pixels (centre)"))
    use, skip = sampled_sites("mars")
    rows += todo_rows(skip, [("geologic_unit", "")], PROV_MARS_GEO)
    shapes = load_mars_shapes()
    for s in use:
        counts = mars_unit_counts(shapes, s["position"]["lat"], s["position"]["lon"])
        rows.append(geology_row(s, counts, PROV_MARS_GEO, "usgs-mars-sim3292", f"Point-in-polygon on a {MARS_GRID_KM:g} km grid"))
    write_csv(DATASETS / "target_measurements.csv", TARGET_FIELDS, rows, key=("site_id", "feature"))
    return rows


PARTS = {"diviner": run_diviner, "geology": run_geology}


def main(argv: list[str]) -> int:
    names = argv[1:] or ["all"]
    if names == ["all"]:
        names = list(PARTS)
    unknown = [n for n in names if n not in PARTS]
    if unknown:
        print(f"unknown part(s): {', '.join(unknown)}. Use: {', '.join(PARTS)} or all", file=sys.stderr)
        return 2
    for n in names:
        print(f"== {n}")
        PARTS[n]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
