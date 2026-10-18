"""GeoTIFF adapter: metadata inspection and windowed feature extraction.

Rasters are never loaded whole. For each site/target region the adapter reads
only the analysis window (a box of side 2·radius centred on the subject),
decimating on read if the window would exceed MAX_WINDOW_PIXELS, and derives
terrain or scalar statistics from it.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ...services import units as U

MAX_WINDOW_PIXELS = 4_000_000
MIN_VALID_FRACTION = 0.5
BODY_RADII_M = {"earth": 6_378_137.0, "moon": 1_737_400.0, "mars": 3_396_190.0}

RASTER_KINDS = {
    "elevation": {
        "label": "Digital elevation model (DEM)",
        "produces": ["mean_elevation_m", "local_relief_m", "mean_slope_deg", "slope_std_deg"],
        "unit_kind": "m",
    },
    "scalar": {
        "label": "Single-variable raster (window mean), e.g. surface temperature, precipitation, vegetation fraction",
        "produces": ["<chosen variable>"],
        "unit_kind": None,
    },
}


class RasterError(ValueError):
    pass


def _rasterio():
    try:
        import rasterio  # noqa: F401
        return rasterio
    except ImportError as e:  # pragma: no cover - environment dependent
        raise RasterError("Raster processing requires the 'rasterio' package on the server (pip install rasterio).") from e


def _pyproj_crs(crs_like):
    from pyproj import CRS
    return CRS.from_user_input(crs_like)


def body_of_crs(pcrs) -> str | None:
    a = pcrs.ellipsoid.semi_major_metre if pcrs.ellipsoid else None
    if a is None:
        return None
    for body, r in BODY_RADII_M.items():
        if abs(a - r) / r < 0.02:
            return body
    return None


def inspect(path: Path) -> dict:
    rio = _rasterio()
    try:
        with rio.open(path) as ds:
            info = {
                "driver": ds.driver, "width": ds.width, "height": ds.height, "count": ds.count,
                "dtypes": list(ds.dtypes), "nodata": ds.nodata,
                "crs": ds.crs.to_string() if ds.crs else None,
                "crs_wkt": ds.crs.to_wkt() if ds.crs else None,
                "bounds": list(ds.bounds), "resolution": list(ds.res),
                "scales": list(ds.scales), "offsets": list(ds.offsets),
                "units": list(ds.units) if ds.units else [],
                "tags": {k: v for k, v in list(ds.tags().items())[:40]},
                "band_descriptions": list(ds.descriptions),
                "overviews": ds.overviews(1) if ds.count else [],
            }
            if ds.crs:
                p = _pyproj_crs(ds.crs.to_wkt())
                info["crs_name"] = p.name
                info["is_geographic"] = p.is_geographic
                info["detected_body"] = body_of_crs(p)
                info["semi_major_m"] = p.ellipsoid.semi_major_metre if p.ellipsoid else None
                if not p.is_geographic:
                    info["linear_unit"] = p.axis_info[0].unit_name if p.axis_info else None
            return info
    except RasterError:
        raise
    except Exception as e:  # rasterio raises many error types for corrupt input
        raise RasterError(f"Could not read GeoTIFF: {e}") from e


def _window_bounds(pcrs, lat, lon, radius_m, R, bounds):
    from pyproj import Transformer

    if pcrs.is_geographic:
        x = lon
        if bounds[2] > 180.5 and lon < 0:   # raster uses 0..360 longitudes
            x = lon + 360
        dlat = math.degrees(radius_m / R)
        coslat = max(math.cos(math.radians(lat)), 1e-6)
        dlon = min(180.0, dlat / coslat)
        return (x - dlon, lat - dlat, x + dlon, lat + dlat), (x, lat)
    t = Transformer.from_crs(pcrs.geodetic_crs, pcrs, always_xy=True)
    x, y = t.transform(lon, lat)
    if not (math.isfinite(x) and math.isfinite(y)):
        return None, None
    return (x - radius_m, y - radius_m, x + radius_m, y + radius_m), (x, y)


def extract(path: Path, body: str, kind: str, unit: str, subjects: list[dict], variable_key: str | None = None,
            declared_crs: str | None = None, log=lambda m: None) -> tuple[list[dict], list[dict]]:
    """Return (features, issues). Each feature: {subject_type, subject_id, variable_key, value, unit, spatial_support, method}."""
    rio = _rasterio()
    from rasterio.windows import Window, from_bounds
    from rasterio.enums import Resampling

    if kind not in RASTER_KINDS:
        raise RasterError(f"Unknown raster kind '{kind}'")
    features, issues = [], []
    with rio.open(path) as ds:
        if ds.crs is None and not declared_crs:
            raise RasterError("The GeoTIFF has no embedded CRS. Provide the CRS explicitly in the metadata step "
                              "(e.g. EPSG:4326, IAU_2015:30100 for the Moon, IAU_2015:49900 for Mars).")
        if ds.crs is not None and declared_crs:
            a, b = _pyproj_crs(ds.crs.to_wkt()), _pyproj_crs(declared_crs)
            if not a.equals(b, ignore_axis_order=True):
                raise RasterError(f"Declared CRS '{declared_crs}' does not match the CRS embedded in the file "
                                  f"('{a.name}'). Remove the declared CRS or fix the file.")
        pcrs = _pyproj_crs(ds.crs.to_wkt() if ds.crs else declared_crs)
        detected = body_of_crs(pcrs)
        if detected is None:
            raise RasterError(f"Cannot determine the planetary body from CRS '{pcrs.name}' (unrecognised ellipsoid radius).")
        if detected != body:
            raise RasterError(f"Dataset declared as {body} but the raster CRS ellipsoid belongs to {detected}. "
                              "Planetary coordinates are never mixed with another body.")
        R = pcrs.ellipsoid.semi_major_metre
        lin_factor = 1.0
        if not pcrs.is_geographic:
            ax = pcrs.axis_info[0]
            if ax.unit_name not in ("metre", "meter"):
                lin_factor = ax.unit_conversion_factor or 1.0
                if not ax.unit_conversion_factor:
                    raise RasterError(f"Unsupported projected CRS linear unit '{ax.unit_name}'")
        scale = ds.scales[0] if ds.scales and ds.scales[0] not in (None, 0) else 1.0
        offset = ds.offsets[0] if ds.offsets and ds.offsets[0] is not None else 0.0
        canonical = "m" if kind == "elevation" else None
        if kind == "scalar":
            from ...services.vocabulary import VARIABLE_BY_KEY
            v = VARIABLE_BY_KEY.get(variable_key or "")
            if not v or v.value_type != "numeric" or not v.unit_kind:
                raise RasterError("Scalar rasters must be mapped to a numeric EarthTwin variable")
            canonical = v.unit_kind
        U.normalize(1.0, unit, canonical)  # validates the unit up front
        log(f"CRS {pcrs.name}; body {body}; {ds.width}×{ds.height} px; res {ds.res}; scale {scale}, offset {offset}")

        for s in subjects:
            radius_m = float(s.get("analysis_radius_km") or 10) * 1000.0
            wb, centre = _window_bounds(pcrs, s["lat"], s["lon"], radius_m / lin_factor, R, ds.bounds)
            label = f"{s['subject_type']}:{s['id']}"
            if wb is None:
                issues.append({"level": "warning", "subject": label, "message": "Subject cannot be projected into the raster CRS"})
                continue
            l, b, r, t = ds.bounds
            if centre[0] < l or centre[0] > r or centre[1] < b or centre[1] > t:
                continue  # outside coverage: silently skipped subjects are reported in the summary count
            win = from_bounds(*wb, transform=ds.transform).round_offsets().round_lengths()
            win = win.intersection(Window(0, 0, ds.width, ds.height))
            if win.width < 3 or win.height < 3:
                issues.append({"level": "warning", "subject": label, "message": "Analysis window smaller than 3×3 pixels; no features derived"})
                continue
            npx = win.width * win.height
            f = math.sqrt(npx / MAX_WINDOW_PIXELS) if npx > MAX_WINDOW_PIXELS else 1.0
            shape = (max(3, int(win.height / f)), max(3, int(win.width / f)))
            arr = ds.read(1, window=win, out_shape=shape, masked=True,
                          resampling=Resampling.average if f > 1 else Resampling.nearest).astype("float64")
            data = arr.filled(np.nan) * scale + offset
            valid = np.isfinite(data)
            frac = float(valid.mean())
            if frac < MIN_VALID_FRACTION:
                issues.append({"level": "warning", "subject": label,
                               "message": f"Only {frac:.0%} valid pixels in window (< {MIN_VALID_FRACTION:.0%}); no features derived"})
                continue
            res_x, res_y = abs(ds.res[0]) * win.width / shape[1], abs(ds.res[1]) * win.height / shape[0]
            if pcrs.is_geographic:
                dy = math.radians(res_y) * R
                dx = math.radians(res_x) * R * max(math.cos(math.radians(s["lat"])), 1e-6)
            else:
                dx, dy = res_x * lin_factor, res_y * lin_factor
            support = (f"{2 * radius_m / 1000:g} km box window, ~{(dx + dy) / 2:.0f} m/px effective"
                       f"{' (decimated ×%.1f)' % f if f > 1 else ''}, {frac:.0%} valid")
            if kind == "elevation":
                cf, _ = U.normalize(1.0, unit, "m")
                z = data * cf
                gy, gx = np.gradient(z, dy, dx)
                slope = np.degrees(np.arctan(np.hypot(gx, gy)))
                slope = slope[np.isfinite(slope)]
                zz = z[np.isfinite(z)]
                method = "EarthTwin DEM pipeline v1: window statistics; slope by central differences (numpy.gradient)"
                for key, val in (("mean_elevation_m", float(np.mean(zz))),
                                 ("local_relief_m", float(np.percentile(zz, 95) - np.percentile(zz, 5))),
                                 ("mean_slope_deg", float(np.mean(slope)) if slope.size else None),
                                 ("slope_std_deg", float(np.std(slope)) if slope.size else None)):
                    if val is not None and math.isfinite(val):
                        features.append({"subject_type": s["subject_type"], "subject_id": s["id"], "variable_key": key,
                                         "value": val, "unit": "m" if key.endswith("_m") else "deg",
                                         "spatial_support": support, "method": method})
            else:
                vals = data[valid]
                if unit and U._clean(unit) == "percent_grade":
                    vals = np.degrees(np.arctan(vals / 100.0))
                    mean, cu = float(np.mean(vals)), "deg"
                else:
                    mean, cu = U.normalize(float(np.mean(vals)), unit, canonical)
                features.append({"subject_type": s["subject_type"], "subject_id": s["id"], "variable_key": variable_key,
                                 "value": mean, "unit": cu, "spatial_support": support,
                                 "method": "EarthTwin scalar raster pipeline v1: window mean of valid pixels"})
    return features, issues
