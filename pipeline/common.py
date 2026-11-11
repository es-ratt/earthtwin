"""Shared helpers for the EarthTwin data scripts (fetch_real_data, fetch_context_data, fetch_earthdata).

Every measured value written by these scripts is one CSV row with full provenance:
dataset name, product ID, version, date range, resolution, processing steps and source URL.
"""
from __future__ import annotations

import csv
import json
import math
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import certifi
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "datasets"
CACHE = DATASETS / "cache"
MANUAL = DATASETS / "manual"          # files the user downloads by hand (Earthdata login)
WEB_DATA = ROOT / "web" / "data"
SSL_CTX = ssl.create_default_context(cafile=certifi.where())
USER_AGENT = "EarthTwin-student-prototype/0.2 (NASA Space Apps 2026 hackathon)"

PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"

R_EARTH_WGS84 = "+datum=WGS84"
R_MARS_SPHERE_M = 3396190.0   # Mars 2000 sphere, as in the HRSC-MOLA blend header
R_MOON_M = 1737400.0

PROVENANCE = ["dataset", "product_id", "version", "date_range", "resolution", "processing", "source_url"]
EARTH_FIELDS = ["candidate_id", "feature", "value", "unit", "status", "source_id", "confidence", *PROVENANCE, "note"]
TARGET_FIELDS = ["site_id", "feature", "value", "unit", "status", "source_id", "confidence", *PROVENANCE, "note"]
RETRY_CODES = (429, 500, 502, 503, 504)


# ------------------------------------------------------------------ HTTP
def _request(url: str, data: bytes | None, headers: dict, tries: int, timeout: int) -> bytes:
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or attempt == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or min(60, 5 * 2 ** attempt)
            print(f"    HTTP {e.code} from {urlparse(url).netloc}, waiting {wait}s …", file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == tries - 1:
                raise
            print(f"    network error ({e}), retrying …", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable")


def http_json(url: str, body: dict | None = None, tries: int = 6, timeout: int = 60, headers: dict | None = None) -> dict:
    """GET (or POST when body is given) JSON, with back-off on rate limits and server errors."""
    data = json.dumps(body).encode() if body is not None else None
    raw = _request(url, data, {"Content-Type": "application/json", **(headers or {})}, tries, timeout)
    return json.loads(raw)


def http_form(url: str, form: dict, tries: int = 4, timeout: int = 120) -> dict:
    """POST a urlencoded form, expect JSON (used for the Overpass API)."""
    from urllib.parse import urlencode

    raw = _request(url, urlencode(form).encode(), {"Content-Type": "application/x-www-form-urlencoded"}, tries, timeout)
    return json.loads(raw)


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url.rsplit('/', 1)[-1]} …")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=600, context=SSL_CTX) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    return dest


# ------------------------------------------------------- Planetary Computer
_tokens: dict[str, str] = {}


def signed(href: str) -> str:
    """Append an anonymous read token. Tokens are per storage account + container (taken from the file URL)."""
    u = urlparse(href)
    key = f"{u.netloc.split('.')[0]}/{u.path.lstrip('/').split('/')[0]}"
    if key not in _tokens:
        _tokens[key] = http_json(PC_TOKEN.format(collection=key))["token"]
    return href + ("&" if "?" in href else "?") + _tokens[key]


def stac_items(collection: str, lon: float, lat: float, datetime: str | None = None, limit: int = 100) -> list[dict]:
    body = {"collections": [collection], "intersects": {"type": "Point", "coordinates": [lon, lat]}, "limit": limit}
    if datetime:
        body["datetime"] = datetime
    return http_json(PC_STAC, body).get("features", [])


# ------------------------------------------------------------- terrain
def slope_roughness(z: np.ndarray, dx: float, dy: float) -> tuple[np.ndarray, np.ndarray]:
    """Slope (deg) and roughness (std-dev of the 3×3 window after removing the local tilt)."""
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


def aeqd_crs(lat: float, lon: float, body: str) -> str:
    """Local azimuthal-equidistant projection centred on the site, in metres (Earth WGS84 or Mars sphere)."""
    shape = R_EARTH_WGS84 if body == "earth" else f"+R={R_MARS_SPHERE_M:.0f}"
    return f"+proj=aeqd +lat_0={lat} +lon_0={lon} {shape} +units=m +no_defs"


def resample_local(ds, lat: float, lon: float, radius_m: float, res_m: float, body: str = "earth") -> np.ndarray:
    """Average-resample an open rasterio DEM onto a square local metric grid (res_m pixels, ±radius_m) around the site.

    Same function for Earth and Mars, so both sides are measured on the same grid spacing.
    """
    from rasterio.crs import CRS
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import Window

    radius_body = 6371000.0 if body == "earth" else R_MARS_SPHERE_M
    margin = 1.5 * radius_m + 3 * res_m
    dlat = math.degrees(margin / radius_body)
    dlon = dlat / max(math.cos(math.radians(min(abs(lat) + dlat, 89.9))), 1e-3)
    inv = ~ds.transform
    c0, r0 = inv @ (lon - dlon, lat + dlat)
    c1, r1 = inv @ (lon + dlon, lat - dlat)
    win = Window(int(math.floor(min(c0, c1))), int(math.floor(min(r0, r1))),
                 int(math.ceil(abs(c1 - c0))) + 1, int(math.ceil(abs(r1 - r0))) + 1)
    src = ds.read(1, window=win, boundless=True, masked=True).astype("float64").filled(np.nan)
    src_transform = ds.window_transform(win)
    n = int(round(2 * radius_m / res_m)) + 1
    dst = np.full((n, n), np.nan)
    half = n * res_m / 2.0
    src_crs = ds.crs if ds.crs else CRS.from_epsg(4326)
    reproject(src, dst, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=from_origin(-half, half, res_m, res_m), dst_crs=CRS.from_proj4(aeqd_crs(lat, lon, body)),
              dst_nodata=np.nan, resampling=Resampling.average)
    return dst


def terrain_stats(z: np.ndarray, res_m: float) -> tuple[float, float]:
    """Median slope and median detrended roughness of a resampled grid (edges dropped)."""
    s, r = slope_roughness(z, res_m, res_m)
    inner = (slice(1, -1), slice(1, -1))
    return float(np.nanmedian(s[inner])), float(np.nanmedian(r[inner]))


# --------------------------------------------------------------- rows / CSV
def provenance(dataset: str, product_id: str, version: str, date_range: str, resolution: str, processing: str, source_url: str) -> dict:
    return {"dataset": dataset, "product_id": product_id, "version": version, "date_range": date_range,
            "resolution": resolution, "processing": processing, "source_url": source_url}


def row(key_name: str, key: str, feature: str, value, unit: str, source_id: str, confidence: str, prov: dict,
        note: str = "", status: str = "measured") -> dict:
    """One measured value. Missing value → status TODO with the reason in note (never estimated)."""
    if value is None:
        status, confidence = "TODO", ""
    return {key_name: key, "feature": feature, "value": "" if value is None else value, "unit": unit, "status": status,
            "source_id": source_id if value is not None else "", "confidence": confidence, **prov, "note": note}


def write_csv(path: Path, fields: list[str], rows: Iterable[dict], key: tuple[str, str]) -> None:
    """Merge rows into a long-format CSV, replacing rows with the same (id, feature) key."""
    rows = list(rows)
    existing = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = list(csv.DictReader(f))
    new_keys = {(r[key[0]], r[key[1]]) for r in rows}
    kept = [r for r in existing if (r[key[0]], r[key[1]]) not in new_keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in kept + rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"→ {path.relative_to(ROOT)}: {len(rows)} rows written/updated")


def load_candidates(only: list[str] | None = None) -> list[dict]:
    with open(DATASETS / "earth_candidates.csv", encoding="utf-8") as f:
        return [c for c in csv.DictReader(f) if not only or c["id"] in only]


def load_feature_rows() -> dict[tuple[str, str], dict]:
    path = DATASETS / "earth_features.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {(r["candidate_id"], r["feature"]): r for r in csv.DictReader(f)}


def parse_only(argv: list[str]) -> list[str] | None:
    return argv[argv.index("--only") + 1].split(",") if "--only" in argv else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))
