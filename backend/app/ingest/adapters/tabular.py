"""Adapters that turn CSV / JSON / GeoJSON files into a uniform row table."""
from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

MAX_ROWS = 200_000
MAX_COLUMNS = 500
GEOM_LAT, GEOM_LON = "_geometry_lat", "_geometry_lon"


class AdapterError(ValueError):
    pass


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise AdapterError("File must be UTF-8 encoded") from e


def read_csv(path: Path) -> tuple[list[str], list[dict], dict]:
    text = _read_text(path)
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration as e:
        raise AdapterError("CSV file is empty") from e
    header = [h.strip() for h in header]
    if not any(header):
        raise AdapterError("CSV header row is empty")
    if len(header) > MAX_COLUMNS:
        raise AdapterError(f"Too many columns ({len(header)} > {MAX_COLUMNS})")
    dupes = {h for h in header if header.count(h) > 1 and h}
    if dupes:
        raise AdapterError(f"Duplicate column names: {', '.join(sorted(dupes))}")
    out, ragged = [], 0
    for i, r in enumerate(reader):
        if not any(c.strip() for c in r):
            continue
        if len(out) >= MAX_ROWS:
            raise AdapterError(f"Too many rows (> {MAX_ROWS}); split the file")
        if len(r) != len(header):
            ragged += 1
        out.append({h: (r[j].strip() if j < len(r) else "") for j, h in enumerate(header) if h})
    return [h for h in header if h], out, {"delimiter": delim, "ragged_rows": ragged}


def read_json_records(path: Path) -> tuple[list[str], list[dict], dict]:
    doc = json.loads(_read_text(path))
    recs = doc if isinstance(doc, list) else doc.get("records")
    if not isinstance(recs, list):
        raise AdapterError("Expected a JSON array of objects or {\"records\": [...]}")
    if len(recs) > MAX_ROWS:
        raise AdapterError(f"Too many records (> {MAX_ROWS})")
    cols: list[str] = []
    rows = []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            raise AdapterError(f"Record {i} is not an object")
        flat = {}
        for k, v in r.items():
            flat[str(k)] = ";".join(map(str, v)) if isinstance(v, list) else ("" if v is None else v if isinstance(v, (int, float, bool)) else str(v))
            if str(k) not in cols:
                cols.append(str(k))
        rows.append(flat)
    if len(cols) > MAX_COLUMNS:
        raise AdapterError(f"Too many fields ({len(cols)} > {MAX_COLUMNS})")
    return cols, rows, {}


_GEOM_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"}


def _check_coords(c, depth=0):
    if depth > 6:
        raise AdapterError("Geometry nesting too deep")
    if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
        if len(c) < 2 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in c[:2]):
            raise AdapterError("Invalid coordinate position")
        return 1
    if not isinstance(c, (list, tuple)):
        raise AdapterError("Invalid coordinates array")
    return sum(_check_coords(x, depth + 1) for x in c)


def read_geojson(path: Path) -> tuple[list[str], list[dict], dict]:
    doc = json.loads(_read_text(path))
    feats = doc.get("features")
    if not isinstance(feats, list):
        raise AdapterError("FeatureCollection has no 'features' array")
    if len(feats) > MAX_ROWS:
        raise AdapterError(f"Too many features (> {MAX_ROWS})")
    cols: list[str] = []
    rows, gtypes, positions = [], {}, 0
    for i, f in enumerate(feats):
        if not isinstance(f, dict) or f.get("type") != "Feature":
            raise AdapterError(f"Feature {i} is not a GeoJSON Feature")
        g = f.get("geometry")
        props = f.get("properties") or {}
        if not isinstance(props, dict):
            raise AdapterError(f"Feature {i} properties must be an object")
        r = {}
        for k, v in props.items():
            r[str(k)] = ";".join(map(str, v)) if isinstance(v, list) else ("" if v is None else v if isinstance(v, (int, float, bool)) else str(v))
            if str(k) not in cols:
                cols.append(str(k))
        if g is not None:
            t = g.get("type")
            if t not in _GEOM_TYPES:
                raise AdapterError(f"Feature {i} has unsupported geometry type {t!r}")
            gtypes[t] = gtypes.get(t, 0) + 1
            if t != "GeometryCollection":
                positions += _check_coords(g.get("coordinates"))
            if t == "Point":
                lon, lat = g["coordinates"][:2]
                r[GEOM_LON], r[GEOM_LAT] = lon, lat
        rows.append(r)
    if any(GEOM_LAT in r for r in rows):
        cols += [GEOM_LAT, GEOM_LON]
    crs_member = doc.get("crs")
    return cols, rows, {"geometry_types": gtypes, "positions": positions, "legacy_crs_member": crs_member}


def read(path: Path, fmt: str):
    if fmt == "csv":
        return read_csv(path)
    if fmt == "json":
        return read_json_records(path)
    if fmt == "geojson":
        return read_geojson(path)
    raise AdapterError(f"No tabular adapter for format {fmt}")
