#!/usr/bin/env python3
"""Fetch REAL terrain and temperature values for EarthTwin. No login needed.

    python pipeline/fetch_real_data.py moon        # LOLA 240 m south-polar DEM → Moon target slope/roughness
    python pipeline/fetch_real_data.py mars        # HRSC-MOLA blended DEM 200 m → SkyFall target slope/roughness
    python pipeline/fetch_real_data.py earth       # NASADEM / Copernicus DEM + MODIS LST → Earth features
    python pipeline/fetch_real_data.py earth --parts dem          # only terrain (fast)
    python pipeline/fetch_real_data.py earth --only haughton-crater,mauna-kea
    python pipeline/fetch_real_data.py all

Needs numpy, rasterio, certifi (all in the project's .venv). Use the .venv python.

Same variable, same scale, same units
  Artemis IV: slope/roughness on a 240 m grid on BOTH sides (LOLA LDEM_75S_240M ↔ Earth DEM resampled to 240 m).
  SkyFall   : slope/roughness on a 200 m grid on BOTH sides (HRSC-MOLA blend 200 m ↔ Earth DEM resampled to 200 m).
              This is COARSE-SCALE SCREENING. NASA's slope limit (<15°) is defined at 1–5 m (HiRISE/CTX DTMs).
  Both sides use the same code path: average-resample onto a local azimuthal-equidistant grid centred on the
  site, then slope = arctan|∇z| and roughness = std-dev of the 3×3 window after removing the local plane.

Elevation for Earth: NASADEM covers 60°N–56°S. Outside it this script uses Copernicus DEM GLO-30 (ESA,
non-NASA, labelled). ASTER GDEM v3 (NASA/METI) needs an Earthdata login: run pipeline/fetch_earthdata.py
aster-dem to replace those rows.
"""
from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from common import (CACHE, DATASETS, EARTH_FIELDS, TARGET_FIELDS, WEB_DATA, R_MOON_M, download, load_candidates,
                    parse_only, provenance, resample_local, row, signed, slope_roughness, stac_items, terrain_stats,
                    write_csv)

# ---------------------------------------------------------------- settings
LOLA_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_75s_240m.img"
LOLA_N, LOLA_SCALE, LOLA_OFFSET_PX, LOLA_DN = 3812, 240.0, 1905.5, 0.5
MARS_DEM_URL = ("https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/"
                "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif")
MARS_DEM_PAGE = "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m"

WINDOW_RADIUS_M = 5000.0      # same window on every body for the 200 m / 240 m features
EARTH_RADIUS_30 = 1000.0      # window for the native ~30 m Earth features
GRID_240, GRID_200 = 240.0, 200.0
LST_YEAR = "2025"
NASADEM_LAT_RANGE = (-56.0, 60.0)

PROV_LOLA = provenance(
    "LRO LOLA polar gridded DEM LDEM_75S_240M (NASA PDS Geosciences Node)", "LRO-L-LOLA-4-GDR-V1.0 / LDEM_75S_240M",
    "V2.0 (product), created 2017-06-15", "2009-07-13 to 2017-02-02 (LOLA observations)", "240 m/pixel, polar stereographic",
    "", LOLA_URL)
PROV_MARS = provenance(
    "Mars MGS MOLA – MEX HRSC Blended DEM Global 200 m v2 (USGS Astrogeology; Fergason et al. 2018)",
    "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2", "v2",
    "MGS MOLA (1997–2001) + Mars Express HRSC strips; exact HRSC dates: see product page", "200 m/pixel at the equator",
    "", MARS_DEM_PAGE)


def _with(prov: dict, **kw) -> dict:
    return {**prov, **kw}


# ------------------------------------------------------------------ MOON
def moon_xy(lat: float, lon: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    rho = 2 * R_MOON_M * math.tan(math.pi / 4 + phi / 2)
    return rho * math.sin(lam), rho * math.cos(lam)


def run_moon() -> list[dict]:
    img = download(LOLA_URL, CACHE / "ldem_75s_240m.img")
    dem = np.fromfile(img, dtype="<i2").reshape(LOLA_N, LOLA_N).astype("float64") * LOLA_DN
    targets = json.loads((WEB_DATA / "targets.json").read_text())
    rows, r = [], int(round(WINDOW_RADIUS_M / LOLA_SCALE))
    for s in targets["sites"]:
        p = s.get("position") or {}
        if s["body"] != "moon" or p.get("lat") is None:
            continue
        x, y = moon_xy(p["lat"], p["lon"])
        col = int(round(x / LOLA_SCALE + LOLA_OFFSET_PX - 0.5))
        row_i = int(round(-y / LOLA_SCALE + LOLA_OFFSET_PX - 0.5))
        win = dem[max(0, row_i - r): row_i + r + 1, max(0, col - r): col + r + 1]
        slope, rough = slope_roughness(win, LOLA_SCALE, LOLA_SCALE)
        steps = (f"Read LDEM_75S_240M (int16 × 0.5 m); window ±{int(WINDOW_RADIUS_M)} m around {p['lat']}, {p['lon']}; "
                 "slope = arctan|∇z|; roughness = std of 3×3 residuals after removing the local plane; median of window")
        prov = _with(PROV_LOLA, processing=steps)
        note = f"{p.get('note') or 'site position'} Elevation there: {np.median(win):.0f} m."
        rows += [row("site_id", s["id"], "slope_240m_deg", round(float(np.median(slope)), 2), "°", "pds-lola-ldem-75s-240m", "medium", prov, note),
                 row("site_id", s["id"], "roughness_240m_m", round(float(np.median(rough)), 2), "m", "pds-lola-ldem-75s-240m", "medium", prov, note)]
        print(f"  {s['name']:32s} slope {rows[-2]['value']:6.2f}°  roughness {rows[-1]['value']:6.2f} m")
    write_csv(DATASETS / "target_measurements.csv", TARGET_FIELDS, rows, key=("site_id", "feature"))
    return rows


# ------------------------------------------------------------------ MARS
def run_mars() -> list[dict]:
    import rasterio

    targets = json.loads((WEB_DATA / "targets.json").read_text())
    rows = []
    env = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MULTIRANGE="YES", CPL_VSIL_CURL_CHUNK_SIZE="1048576")
    with rasterio.Env(**env), rasterio.open("/vsicurl/" + MARS_DEM_URL) as ds:
        for s in targets["sites"]:
            p = s.get("position") or {}
            if s["body"] != "mars":
                continue
            if p.get("lat") is None:
                reason = "No coordinates for this region in the team docs, so the DEM cannot be sampled."
                rows += [row("site_id", s["id"], f, None, u, "", "", PROV_MARS, reason)
                         for f, u in (("slope_200m_deg", "°"), ("roughness_200m_m", "m"))]
                print(f"  {s['name']:32s} TODO (no coordinates)")
                continue
            grid = resample_local(ds, p["lat"], p["lon"], WINDOW_RADIUS_M, GRID_200, body="mars")
            slope, rough = terrain_stats(grid, GRID_200)
            steps = (f"Windowed read of the global 200 m blend; average-resampled to a 200 m local azimuthal-equidistant grid "
                     f"(Mars sphere R=3396190 m) ±{int(WINDOW_RADIUS_M)} m around {p['lat']}, {p['lon']}; slope = arctan|∇z|; "
                     "roughness = std of 3×3 residuals after removing the local plane; median of window")
            prov = _with(PROV_MARS, processing=steps)
            note = (f"COARSE-SCALE SCREENING (~200 m), not landing safety: NASA's <15° limit is at 1–5 m. "
                    f"Median elevation {np.nanmedian(grid):.0f} m. {p.get('note') or ''} "
                    "The DEM stores whole metres, so roughness below ~0.5 m is near the quantisation limit.")
            rows += [row("site_id", s["id"], "slope_200m_deg", round(slope, 2), "°", "usgs-hrsc-mola-blend-200m", "medium", prov, note),
                     row("site_id", s["id"], "roughness_200m_m", round(rough, 2), "m", "usgs-hrsc-mola-blend-200m", "medium", prov, note)]
            print(f"  {s['name']:32s} slope {slope:6.2f}°  roughness {rough:6.2f} m  (elev {np.nanmedian(grid):.0f} m)")
    write_csv(DATASETS / "target_measurements.csv", TARGET_FIELDS, rows, key=("site_id", "feature"))
    return rows


# ------------------------------------------------------------------ EARTH DEM
def dem_source(lat: float) -> tuple[str, str, str, str]:
    """(collection, asset, source_id, label) — NASADEM inside its coverage, Copernicus GLO-30 outside."""
    if NASADEM_LAT_RANGE[0] <= lat <= NASADEM_LAT_RANGE[1]:
        return "nasadem", "elevation", "pc-nasadem", "NASADEM HGT v001 (NASA/JPL)"
    return "cop-dem-glo-30", "data", "pc-cop-dem-glo-30", "Copernicus DEM GLO-30 (ESA; NON-NASA, used because NASADEM stops at 60°N)"


def dem_prov(coll: str, item: dict, steps: str) -> dict:
    props = item.get("properties", {})
    if coll == "nasadem":
        return provenance("NASADEM HGT (NASA/JPL) via Microsoft Planetary Computer", f"NASADEM_HGT tile {item['id']}", "001",
                          f"SRTM mission Feb 2000 (item datetime {props.get('datetime', '?')[:10]})", "1 arc-second (~30 m)",
                          steps, "https://planetarycomputer.microsoft.com/dataset/nasadem")
    return provenance("Copernicus DEM GLO-30 (ESA, TanDEM-X) via Microsoft Planetary Computer", f"COP-DEM GLO-30 tile {item['id']}",
                      f"PC item {props.get('datetime', '?')[:10]}", f"platform {props.get('platform', '?')}", "1 arc-second (~30 m)",
                      steps, "https://planetarycomputer.microsoft.com/dataset/cop-dem-glo-30")


def native_window(ds, lon: float, lat: float, radius_m: float) -> tuple[np.ndarray, float, float]:
    from rasterio.windows import Window

    r_, c_ = ds.index(lon, lat)
    dx = abs(ds.transform.a) * 111320.0 * math.cos(math.radians(lat))
    dy = abs(ds.transform.e) * 110574.0
    rx, ry = int(math.ceil(radius_m / dx)), int(math.ceil(radius_m / dy))
    arr = ds.read(1, window=Window(c_ - rx, r_ - ry, 2 * rx + 1, 2 * ry + 1), boundless=True, masked=True)
    return arr.astype("float64").filled(np.nan), dx, dy


TERRAIN_FEATURES = (("slope_deg", "°"), ("roughness_m", "m"), ("slope_240m_deg", "°"), ("roughness_240m_m", "m"),
                    ("slope_200m_deg", "°"), ("roughness_200m_m", "m"))


def terrain_rows(c: dict, ds, src: str, conf: str, label: str, prov_for) -> list[dict]:
    """All six Earth terrain features from an open DEM dataset. prov_for(steps) builds the provenance dict."""
    lat, lon = float(c["lat"]), float(c["lon"])
    z, dx, dy = native_window(ds, lon, lat, EARTH_RADIUS_30)
    s30, r30 = slope_roughness(z, dx, dy)
    steps30 = (f"Native ~{dx:.0f}×{dy:.0f} m pixels, window ±{int(EARTH_RADIUS_30)} m; slope = arctan|∇z|; "
               "roughness = std of 3×3 residuals after removing the local plane; median of window")
    p30 = prov_for(steps30)
    out = [row("candidate_id", c["id"], "slope_deg", round(float(np.nanmedian(s30)), 2), "°", src, conf, p30, label),
           row("candidate_id", c["id"], "roughness_m", round(float(np.nanmedian(r30)), 2), "m", src, conf, p30, label)]
    for grid, suffix in ((GRID_240, "240m"), (GRID_200, "200m")):
        g = resample_local(ds, lat, lon, WINDOW_RADIUS_M, grid, body="earth")
        slope, rough = terrain_stats(g, grid)
        steps = (f"Average-resampled to a {grid:.0f} m local azimuthal-equidistant grid (WGS84) ±{int(WINDOW_RADIUS_M)} m "
                 "around the site — the SAME procedure used for the Moon/Mars DEM; slope = arctan|∇z|; roughness = std of "
                 "3×3 residuals after removing the local plane; median of window")
        p = prov_for(steps)
        out += [row("candidate_id", c["id"], f"slope_{suffix}_deg", round(slope, 2), "°", src, conf, p, label),
                row("candidate_id", c["id"], f"roughness_{suffix}_m", round(rough, 2), "m", src, conf, p, label)]
    return out


def earth_dem(c: dict) -> list[dict]:
    import rasterio

    lat, lon = float(c["lat"]), float(c["lon"])
    coll, asset, src, label = dem_source(lat)
    items = stac_items(coll, lon, lat)
    if not items:
        return [row("candidate_id", c["id"], f, None, u, "", "", {}, f"No {coll} tile at this position.") for f, u in TERRAIN_FEATURES]
    conf = "high" if coll == "nasadem" else "medium"
    with rasterio.open(signed(items[0]["assets"][asset]["href"])) as ds:
        return terrain_rows(c, ds, src, conf, label, lambda steps: dem_prov(coll, items[0], steps))


# ------------------------------------------------------------------ EARTH LST
def lst_value(item: dict, lon: float, lat: float) -> tuple[float | None, float | None]:
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window

    vals: list[float | None] = []
    for asset in ("LST_Day_1km", "LST_Night_1km"):
        try:
            with rasterio.open(signed(item["assets"][asset]["href"])) as ds:
                xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
                r_, c_ = ds.index(xs[0], ys[0])
                a = ds.read(1, window=Window(c_ - 1, r_ - 1, 3, 3), boundless=True, fill_value=0).astype("float64")
                a = a[a > 0] * 0.02  # scale factor 0.02 K; 0 = no data
                vals.append(float(np.median(a)) if a.size else None)
        except Exception as e:  # one unreadable composite is skipped, never filled in
            print(f"    skipped {item['id']} {asset}: {e}", file=sys.stderr)
            vals.append(None)
    return vals[0], vals[1]


def earth_lst(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    items = stac_items("modis-11A2-061", lon, lat, datetime=f"{LST_YEAR}-01-01/{LST_YEAR}-12-31", limit=200)
    prov = provenance("MODIS Land Surface Temperature 8-day (Terra MOD11A2 + Aqua MYD11A2) via Microsoft Planetary Computer",
                      "MOD11A2 + MYD11A2", "061", f"{LST_YEAR}-01-01 to {LST_YEAR}-12-31", "1 km, 8-day composites", "",
                      "https://planetarycomputer.microsoft.com/dataset/modis-11A2-061")
    if not items:
        return [row("candidate_id", c["id"], "temp_range_K", None, "K", "", "", prov, "No MODIS composites found.")]
    with ThreadPoolExecutor(max_workers=12) as ex:
        pairs = list(ex.map(lambda it: lst_value(it, lon, lat), items))
    days = [d for d, _ in pairs if d]
    nights = [n for _, n in pairs if n]
    both = [(d, n) for d, n in pairs if d and n]
    base = f"{len(items)} composites ({len(days)} day / {len(nights)} night valid); 3×3 pixel median per composite (scale 0.02 K, 0 = no data)"
    out = []
    if both:
        polar = abs(lat) > 60
        conf = "low" if polar or len(both) < 20 else "high"
        caveat = ("LOW CONFIDENCE: above 60° latitude MODIS 'night' passes are often sunlit in summer and polar night/cloud "
                  "removes many composites, so day − night underestimates the real swing.") if polar else ""
        out.append(row("candidate_id", c["id"], "temp_range_K", round(float(np.mean([d - n for d, n in both])), 1), "K",
                       "pc-modis-11a2", conf, {**prov, "processing": base + f"; mean of (day − night) over {len(both)} composites with both"}, caveat))
    if days or nights:
        out.append(row("candidate_id", c["id"], "annual_min_lst_K", round(float(min(days + nights)), 1), "K", "pc-modis-11a2",
                       "medium", {**prov, "processing": base + "; lowest 8-day mean (day or night)"}))
    return out


def run_earth(only: list[str] | None, parts: set[str]) -> list[dict]:
    rows = []
    for c in load_candidates(only):
        got = None
        for attempt in range(3):
            try:
                got = (earth_dem(c) if "dem" in parts else []) + (earth_lst(c) if "lst" in parts else [])
                break
            except Exception as e:  # network hiccup: wait, retry, then keep the old rows
                print(f"  {c['id']}: attempt {attempt + 1} failed ({e})", file=sys.stderr)
                time.sleep(20 * (attempt + 1))
        if got is None:
            print(f"  {c['id']}: gave up; previous rows kept", file=sys.stderr)
            continue
        rows += got
        print(f"  {c['name'][:34]:34s} " + ", ".join(f"{r['feature']}={r['value']}" for r in got))
    write_csv(DATASETS / "earth_features.csv", EARTH_FIELDS, rows, key=("candidate_id", "feature"))
    return rows


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    only = parse_only(argv)
    parts = set(argv[argv.index("--parts") + 1].split(",")) if "--parts" in argv else {"dem", "lst"}
    if what in ("moon", "all"):
        print("MOON · LOLA LDEM_75S_240M")
        run_moon()
    if what in ("mars", "all"):
        print("MARS · HRSC-MOLA blended DEM 200 m")
        run_mars()
    if what in ("earth", "all"):
        print(f"EARTH · {', '.join(sorted(parts))}")
        run_earth(only, parts)
    print("Now run: python3 pipeline/compute_scores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
