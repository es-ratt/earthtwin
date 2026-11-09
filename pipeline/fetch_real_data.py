#!/usr/bin/env python3
"""Fetch REAL values for EarthTwin from open NASA/USGS (and ESA) archives. No login needed.

    python pipeline/fetch_real_data.py moon      # LOLA 240 m south-polar DEM → target slope/roughness
    python pipeline/fetch_real_data.py earth     # NASADEM / Copernicus DEM + MODIS LST → Earth features
    python pipeline/fetch_real_data.py all
    python pipeline/fetch_real_data.py earth --only haughton-crater,mauna-kea   # just some sites

Needs: numpy, rasterio, certifi  (all in the project's .venv).

What it writes
  datasets/target_measurements.csv  — Moon/Mars target values measured here (merged over targets.json)
  datasets/earth_features.csv       — replaces SAMPLE rows for the features it measures

Data used
  Moon : LRO LOLA polar DEM LDEM_75S_240M (PDS Geosciences Node). 240 m/pixel, 75°S–90°S.
  Earth: NASADEM HGT v001 (NASA/JPL/USGS, 1 arc-second, 60°N–56°S) via Microsoft Planetary Computer;
         Copernicus DEM GLO-30 (ESA) for sites outside NASADEM coverage;
         MODIS MOD11A2 v061 8-day LST day/night 1 km (NASA LP DAAC) via Planetary Computer, year 2025.

Same variable, same scale: lunar slope/roughness come from a 240 m DEM, so the Earth DEM is block-averaged
to 240 m for the *_240m features (used by Artemis IV). The 30 m features (slope_deg, roughness_m) are
kept for SkyFall, whose limit is defined at 1–5 m (still a scale mismatch; stated in the app).
"""
from __future__ import annotations

import csv
import json
import math
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import certifi
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"
CACHE = ROOT / "datasets" / "cache"
WEB_DATA = ROOT / "web" / "data"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
LOLA_URL = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/ldem_75s_240m.img"
LOLA_N, LOLA_SCALE, LOLA_OFFSET_PX, LOLA_DN = 3812, 240.0, 1905.5, 0.5
R_MOON = 1737400.0

MOON_RADIUS_M = 5000.0     # window radius for target-site statistics
EARTH_RADIUS_240 = 5000.0  # same window on Earth for the 240 m features
EARTH_RADIUS_30 = 1000.0   # window for the 30 m features
LST_YEAR = "2025"

FIELDS = ["candidate_id", "feature", "value", "unit", "status", "source_id", "confidence", "note"]
TFIELDS = ["site_id", "feature", "value", "unit", "status", "source_id", "confidence", "note"]


# ------------------------------------------------------------------ helpers
def http_json(url: str, body: dict | None = None, tries: int = 6) -> dict:
    """GET/POST JSON with polite back-off on HTTP 429 (rate limit) and 5xx."""
    import time
    import urllib.error

    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "EarthTwin-student-prototype"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or min(60, 5 * 2 ** attempt)
            print(f"    HTTP {e.code}, waiting {wait}s …", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url.rsplit('/', 1)[-1]} …")
    req = urllib.request.Request(url, headers={"User-Agent": "EarthTwin-student-prototype"})
    with urllib.request.urlopen(req, timeout=300, context=SSL_CTX) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest


def slope_roughness(z: np.ndarray, dx: float, dy: float) -> tuple[np.ndarray, np.ndarray]:
    """Slope (deg) and roughness (std-dev of the 3×3 window after removing the local tilt), same as extract_features.py."""
    dzdy, dzdx = np.gradient(z, dy, dx)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    pad = np.pad(z, 1, mode="edge")
    resid = []
    for i in range(3):
        for j in range(3):
            plane = z + dzdy * (i - 1) * dy + dzdx * (j - 1) * dx
            resid.append(pad[i:i + z.shape[0], j:j + z.shape[1]] - plane)
    rough = np.nanstd(np.stack(resid), axis=0)
    return slope, rough


def block_mean(z: np.ndarray, f: int) -> np.ndarray:
    h, w = (z.shape[0] // f) * f, (z.shape[1] // f) * f
    return np.nanmean(z[:h, :w].reshape(h // f, f, w // f, f), axis=(1, 3))


# ------------------------------------------------------------------ MOON
def moon_xy(lat: float, lon: float) -> tuple[float, float]:
    phi, lam = math.radians(lat), math.radians(lon)
    rho = 2 * R_MOON * math.tan(math.pi / 4 + phi / 2)
    return rho * math.sin(lam), rho * math.cos(lam)


def run_moon() -> list[dict]:
    img = download(LOLA_URL, CACHE / "ldem_75s_240m.img")
    dem = np.fromfile(img, dtype="<i2").reshape(LOLA_N, LOLA_N).astype("float64") * LOLA_DN
    targets = json.loads((WEB_DATA / "targets.json").read_text())
    rows = []
    r = int(round(MOON_RADIUS_M / LOLA_SCALE))
    for s in targets["sites"]:
        p = s.get("position") or {}
        if s["body"] != "moon" or p.get("lat") is None:
            continue
        x, y = moon_xy(p["lat"], p["lon"])
        col = int(round(x / LOLA_SCALE + LOLA_OFFSET_PX - 0.5))
        row = int(round(-y / LOLA_SCALE + LOLA_OFFSET_PX - 0.5))
        win = dem[max(0, row - r): row + r + 1, max(0, col - r): col + r + 1]
        slope, rough = slope_roughness(win, LOLA_SCALE, LOLA_SCALE)
        note = (f"LOLA LDEM_75S_240M, median within {int(MOON_RADIUS_M / 1000)} km of {p['lat']}, {p['lon']} "
                f"({p.get('note') or 'site position'}). Elevation there: {np.median(win):.0f} m.")
        rows.append({"site_id": s["id"], "feature": "slope_240m_deg", "value": round(float(np.median(slope)), 2), "unit": "°",
                     "status": "measured", "source_id": "pds-lola-ldem-75s-240m", "confidence": "medium", "note": note})
        rows.append({"site_id": s["id"], "feature": "roughness_240m_m", "value": round(float(np.median(rough)), 2), "unit": "m",
                     "status": "measured", "source_id": "pds-lola-ldem-75s-240m", "confidence": "medium", "note": note})
        print(f"  {s['name']:32s} slope {rows[-2]['value']:6.2f}°  roughness {rows[-1]['value']:6.2f} m")
    write_csv(DATASETS / "target_measurements.csv", TFIELDS, rows, key=("site_id", "feature"))
    return rows


# ------------------------------------------------------------------ EARTH
_tokens: dict[str, str] = {}


def signed(href: str, collection: str) -> str:
    """Append an anonymous read token. Tokens are per storage account + container (taken from the file URL)."""
    from urllib.parse import urlparse

    u = urlparse(href)
    account = u.netloc.split(".")[0]
    container = u.path.lstrip("/").split("/")[0]
    key = f"{account}/{container}"
    if key not in _tokens:
        _tokens[key] = http_json(PC_TOKEN.format(collection=key))["token"]
    return href + ("&" if "?" in href else "?") + _tokens[key]


def stac_items(collection: str, lon: float, lat: float, datetime: str | None = None, limit: int = 100) -> list[dict]:
    body = {"collections": [collection], "intersects": {"type": "Point", "coordinates": [lon, lat]}, "limit": limit}
    if datetime:
        body["datetime"] = datetime
    return http_json(PC_STAC, body).get("features", [])


def dem_window(href: str, lon: float, lat: float, radius_m: float):
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(href) as ds:
        row, col = ds.index(lon, lat)
        res = abs(ds.transform.a)
        dx = res * 111320.0 * math.cos(math.radians(lat))
        dy = abs(ds.transform.e) * 110574.0
        rx, ry = int(math.ceil(radius_m / dx)), int(math.ceil(radius_m / dy))
        arr = ds.read(1, window=Window(col - rx, row - ry, 2 * rx + 1, 2 * ry + 1), boundless=True, masked=True).astype("float64")
        return arr.filled(np.nan), dx, dy


def earth_dem(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    if -56 <= lat <= 60:
        coll, asset, src = "nasadem", "elevation", "pc-nasadem"
    else:
        coll, asset, src = "cop-dem-glo-30", "data", "pc-cop-dem-glo-30"
    items = stac_items(coll, lon, lat)
    if not items:
        print(f"  {c['id']}: no {coll} tile", file=sys.stderr)
        return []
    href = signed(items[0]["assets"][asset]["href"], coll)
    z, dx, dy = dem_window(href, lon, lat, EARTH_RADIUS_240)
    if np.isnan(z).all():
        return []
    # 30 m features in the inner window
    cy, cx = z.shape[0] // 2, z.shape[1] // 2
    ry, rx = int(EARTH_RADIUS_30 / dy), int(EARTH_RADIUS_30 / dx)
    inner = z[cy - ry: cy + ry + 1, cx - rx: cx + rx + 1]
    s30, r30 = slope_roughness(inner, dx, dy)
    # 240 m features: block-average to ~240 m
    f = max(1, int(round(240.0 / ((dx + dy) / 2))))
    z240 = block_mean(z, f)
    s240, r240 = slope_roughness(z240, dx * f, dy * f)
    name = {"nasadem": "NASADEM", "cop-dem-glo-30": "Copernicus DEM GLO-30 (outside NASADEM coverage)"}[coll]
    tile = items[0]["id"]
    out = []
    for fid, val, unit, note in [
        ("slope_deg", np.nanmedian(s30), "°", f"{name} tile {tile}, median within {int(EARTH_RADIUS_30)} m, ~{dx:.0f}×{dy:.0f} m pixels"),
        ("roughness_m", np.nanmedian(r30), "m", f"{name} tile {tile}, median within {int(EARTH_RADIUS_30)} m, ~{dx:.0f}×{dy:.0f} m pixels"),
        ("slope_240m_deg", np.nanmedian(s240), "°", f"{name} block-averaged {f}×{f} to ~{dx * f:.0f} m, median within {int(EARTH_RADIUS_240 / 1000)} km"),
        ("roughness_240m_m", np.nanmedian(r240), "m", f"{name} block-averaged {f}×{f} to ~{dx * f:.0f} m, median within {int(EARTH_RADIUS_240 / 1000)} km"),
    ]:
        out.append({"candidate_id": c["id"], "feature": fid, "value": round(float(val), 2), "unit": unit, "status": "measured",
                    "source_id": src, "confidence": "high" if coll == "nasadem" else "medium", "note": note})
    return out


def lst_value(item: dict, lon: float, lat: float) -> tuple[float | None, float | None]:
    import rasterio
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window

    vals = []
    for asset in ("LST_Day_1km", "LST_Night_1km"):
        href = signed(item["assets"][asset]["href"], "modis-11A2-061")
        try:
            with rasterio.open(href) as ds:
                xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
                row, col = ds.index(xs[0], ys[0])
                a = ds.read(1, window=Window(col - 1, row - 1, 3, 3), boundless=True, fill_value=0).astype("float64")
                a = a[a > 0] * 0.02  # scale factor 0.02 K, 0 = no data
                vals.append(float(np.median(a)) if a.size else None)
        except Exception:
            vals.append(None)
    return vals[0], vals[1]


def earth_lst(c: dict) -> list[dict]:
    lat, lon = float(c["lat"]), float(c["lon"])
    # Terra (MOD11A2) and Aqua (MYD11A2) composites together
    items = stac_items("modis-11A2-061", lon, lat, datetime=f"{LST_YEAR}-01-01/{LST_YEAR}-12-31", limit=200)
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=12) as ex:
        pairs = list(ex.map(lambda it: lst_value(it, lon, lat), items))
    days = [d for d, _ in pairs if d]
    nights = [n for _, n in pairs if n]
    both = [(d, n) for d, n in pairs if d and n]
    out = []
    base = f"MODIS MOD11A2+MYD11A2 v061 8-day LST, {LST_YEAR}, {len(items)} composites ({len(days)} day / {len(nights)} night valid), 3×3 px median"
    if both:
        polar = abs(lat) > 60
        conf = "low" if polar or len(both) < 20 else "high"
        caveat = ("; LOW CONFIDENCE: above 60° latitude MODIS 'night' passes are often sunlit in summer and polar night/cloud "
                  "removes many composites, so day − night underestimates the real swing") if polar else ""
        out.append({"candidate_id": c["id"], "feature": "temp_range_K", "value": round(float(np.mean([d - n for d, n in both])), 1), "unit": "K",
                    "status": "measured", "source_id": "pc-modis-11a2", "confidence": conf,
                    "note": base + f"; mean of day − night over {len(both)} composites with both" + caveat})
    if days or nights:
        out.append({"candidate_id": c["id"], "feature": "annual_min_lst_K", "value": round(float(min(days + nights)), 1), "unit": "K",
                    "status": "measured", "source_id": "pc-modis-11a2", "confidence": "medium",
                    "note": base + "; lowest 8-day mean (day or night)"})
    return out


def run_earth(only: list[str] | None = None) -> list[dict]:
    import time

    with open(DATASETS / "earth_candidates.csv", encoding="utf-8") as f:
        cands = [c for c in csv.DictReader(f) if not only or c["id"] in only]
    rows = []
    for c in cands:
        got = None
        for attempt in range(3):
            try:
                got = earth_dem(c) + earth_lst(c)
                break
            except Exception as e:  # network hiccup: wait, retry, then keep the old rows
                print(f"  {c['id']}: attempt {attempt + 1} failed ({e})", file=sys.stderr)
                time.sleep(20 * (attempt + 1))
        if got is None:
            continue
        rows += got
        summary = ", ".join(f"{r['feature']}={r['value']}" for r in got)
        print(f"  {c['name'][:34]:34s} {summary}")
    write_csv(DATASETS / "earth_features.csv", FIELDS, rows, key=("candidate_id", "feature"))
    return rows


# ------------------------------------------------------------------ csv merge
def write_csv(path: Path, fields: list[str], rows: list[dict], key: tuple[str, str]) -> None:
    existing = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    new_keys = {(r[key[0]], r[key[1]]) for r in rows}
    kept = [r for r in existing if (r[key[0]], r[key[1]]) not in new_keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept + rows)
    print(f"→ {path.relative_to(ROOT)}: {len(rows)} rows written/updated")


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    if what in ("moon", "all"):
        print("MOON · LOLA LDEM_75S_240M")
        run_moon()
    if what in ("earth", "all"):
        print("EARTH · NASADEM / Copernicus DEM + MODIS LST (Planetary Computer)")
        run_earth(only)
    print("Now run: python3 pipeline/compute_scores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
