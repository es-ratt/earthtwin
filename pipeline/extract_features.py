#!/usr/bin/env python3
"""Turn Earth rasters into rows for datasets/earth_features.csv.

Optional helper (needs numpy + rasterio). It samples a window around each Earth
candidate and appends long-format rows the scoring pipeline understands.

    python3 pipeline/extract_features.py dem   path/to/dem.tif   --source-id nasadem
    python3 pipeline/extract_features.py lst   path/to/min_lst.tif --feature annual_min_lst_K --source-id nasa-lst-tools
    python3 pipeline/extract_features.py lst   path/to/day_minus_night.tif --feature temp_range_K --source-id nasa-lst-tools

Modes
  dem : computes slope_deg (median) and roughness_m (median of 3×3 elevation std-dev)
        within --radius-m of each site. DEM must be in a projected CRS with metres
        (reproject a geographic DEM first, e.g. `gdalwarp -t_srs EPSG:3413` for the Arctic).
  lst : takes the median raster value within --radius-m and writes it as --feature.

Rows are written with status 'measured' and confidence 'medium'. Edit them by hand if
the data quality is lower. Existing rows for the same candidate+feature are replaced.
Use --dry-run to print rows without writing.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "datasets" / "earth_candidates.csv"
FEATURES = ROOT / "datasets" / "earth_features.csv"
FIELDS = ["candidate_id", "feature", "value", "unit", "status", "source_id", "confidence", "note"]


def load_candidates(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def window_around(ds, lat: float, lon: float, radius_m: float):
    """Return (array, pixel_size_m) of the raster window around a lat/lon, or (None, None) if outside."""
    import numpy as np
    from rasterio.warp import transform as warp_transform
    from rasterio.windows import Window

    xs, ys = warp_transform("EPSG:4326", ds.crs, [lon], [lat])
    row, col = ds.index(xs[0], ys[0])
    px = abs(ds.transform.a)
    if not ds.crs.is_projected:
        raise SystemExit("DEM/raster must be in a projected CRS with metre units. Reproject it first (see docstring).")
    r = max(1, int(round(radius_m / px)))
    win = Window(col - r, row - r, 2 * r + 1, 2 * r + 1)
    if col + r < 0 or row + r < 0 or col - r >= ds.width or row - r >= ds.height:
        return None, None
    arr = ds.read(1, window=win, boundless=True, masked=True).astype("float64")
    if np.ma.count(arr) == 0:
        return None, None
    return arr, px


def dem_features(arr, px: float) -> tuple[float, float]:
    import numpy as np

    z = arr.filled(np.nan)
    dzdy, dzdx = np.gradient(z, px)
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # Roughness: 3×3 standard deviation of elevation AFTER removing the local tilt,
    # so a smooth slope has roughness ~0 (slope is measured separately).
    pad = np.pad(z, 1, mode="edge")
    resid = []
    for i in range(3):
        for j in range(3):
            plane = z + dzdy * (i - 1) * px + dzdx * (j - 1) * px
            resid.append(pad[i:i + z.shape[0], j:j + z.shape[1]] - plane)
    rough = np.nanstd(np.stack(resid), axis=0)
    return float(np.nanmedian(slope)), float(np.nanmedian(rough))


def run(args: argparse.Namespace) -> list[dict]:
    import numpy as np
    import rasterio

    rows: list[dict] = []
    with rasterio.open(args.raster) as ds:
        for c in load_candidates(CANDIDATES):
            arr, px = window_around(ds, float(c["lat"]), float(c["lon"]), args.radius_m)
            if arr is None:
                print(f"  {c['id']}: outside raster or no data, skipped", file=sys.stderr)
                continue
            note = f"{Path(args.raster).name}, median within {int(args.radius_m)} m, pixel {px:.0f} m"
            if args.mode == "dem":
                slope, rough = dem_features(arr, px)
                rows.append({"candidate_id": c["id"], "feature": "slope_deg", "value": round(slope, 2), "unit": "°"})
                rows.append({"candidate_id": c["id"], "feature": "roughness_m", "value": round(rough, 2), "unit": "m"})
            else:
                rows.append({"candidate_id": c["id"], "feature": args.feature, "value": round(float(np.ma.median(arr)), 2), "unit": args.unit})
            for r in rows[-2 if args.mode == "dem" else -1:]:
                r.update({"status": "measured", "source_id": args.source_id, "confidence": "medium", "note": note})
    return rows


def merge(rows: list[dict], path: Path) -> None:
    with open(path, encoding="utf-8") as f:
        existing = list(csv.DictReader(f))
    keys = {(r["candidate_id"], r["feature"]) for r in rows}
    kept = [r for r in existing if (r["candidate_id"], r["feature"]) not in keys]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(kept + rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["dem", "lst"])
    p.add_argument("raster")
    p.add_argument("--source-id", required=True, help="id from web/data/sources.json")
    p.add_argument("--feature", default="annual_min_lst_K", help="lst mode: feature id to write")
    p.add_argument("--unit", default="K")
    p.add_argument("--radius-m", type=float, default=1000.0)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    try:
        import numpy  # noqa: F401
        import rasterio  # noqa: F401
    except ImportError:
        print("This helper needs numpy and rasterio: pip install numpy rasterio", file=sys.stderr)
        return 2
    rows = run(args)
    if args.dry_run:
        w = csv.DictWriter(sys.stdout, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    else:
        merge(rows, FEATURES)
        print(f"Wrote {len(rows)} rows to {FEATURES.relative_to(ROOT)}. Now run: python3 pipeline/compute_scores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
