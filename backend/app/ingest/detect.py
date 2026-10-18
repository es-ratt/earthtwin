"""Format detection by content sniffing (never by extension alone)."""
from __future__ import annotations

import json
from pathlib import Path

SUPPORTED = {
    "csv": {"extensions": [".csv", ".txt"], "label": "CSV (comma/semicolon/tab-delimited, UTF-8)",
            "kinds": ["earth_sites", "target_regions", "observations", "observations_long"]},
    "json": {"extensions": [".json"], "label": "JSON array of records, or {\"records\": [...]}",
             "kinds": ["earth_sites", "target_regions", "observations", "observations_long"]},
    "bundle": {"extensions": [".json"], "label": "EarthTwin bundle JSON (self-describing dataset)",
               "kinds": ["bundle"]},
    "geojson": {"extensions": [".geojson", ".json"], "label": "GeoJSON FeatureCollection (RFC 7946)",
                "kinds": ["earth_sites", "target_regions", "observations", "map_layer"]},
    "geotiff": {"extensions": [".tif", ".tiff"], "label": "GeoTIFF / Cloud-Optimised GeoTIFF raster",
                "kinds": ["raster"]},
}

UNSUPPORTED_GUIDANCE = {
    ".zip": "Archives are not unpacked automatically. Extract the archive and upload the CSV, GeoJSON or GeoTIFF inside.",
    ".shp": "Shapefiles are not supported directly. Convert to GeoJSON (e.g. `ogr2ogr -f GeoJSON out.geojson in.shp`).",
    ".img": "PDS .IMG rasters are not read directly. Convert to GeoTIFF with GDAL (`gdal_translate in.IMG out.tif`) "
            "keeping the label (.LBL) so the planetary CRS is preserved.",
    ".cub": "ISIS cubes are not read directly. Export to GeoTIFF with ISIS `isis2std` or GDAL.",
    ".nc": "NetCDF is not yet supported. Extract a variable to GeoTIFF (`gdal_translate NETCDF:file.nc:var out.tif`).",
    ".hdf": "HDF4/5 is not yet supported. Extract a subdataset to GeoTIFF with GDAL.",
    ".h5": "HDF5 is not yet supported. Extract a subdataset to GeoTIFF with GDAL.",
    ".xlsx": "Excel workbooks are not supported. Save the sheet as UTF-8 CSV.",
    ".xls": "Excel workbooks are not supported. Save the sheet as UTF-8 CSV.",
    ".kml": "KML is not supported. Convert to GeoJSON (`ogr2ogr -f GeoJSON out.geojson in.kml`).",
}

TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


class DetectionError(ValueError):
    pass


def detect(path: Path, original_name: str) -> str:
    ext = Path(original_name).suffix.lower()
    if ext in UNSUPPORTED_GUIDANCE:
        raise DetectionError(UNSUPPORTED_GUIDANCE[ext])
    with open(path, "rb") as f:
        head = f.read(8192)
    if head[:4] in TIFF_MAGIC:
        if ext not in (".tif", ".tiff"):
            raise DetectionError("File content is TIFF but the extension is not .tif/.tiff; rename it to confirm.")
        return "geotiff"
    if ext in (".tif", ".tiff"):
        raise DetectionError("The file has a .tif extension but is not a valid TIFF (bad magic bytes).")
    if b"\x00" in head:
        raise DetectionError("Binary content detected in a file declared as text. Only UTF-8 CSV/JSON/GeoJSON are accepted.")
    stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped[:1] in (b"{", b"["):
        if ext not in (".json", ".geojson"):
            raise DetectionError("File content looks like JSON; use a .json or .geojson extension.")
        try:
            with open(path, "rb") as f:
                doc = json.loads(f.read().decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError) as e:
            raise DetectionError(f"Invalid JSON: {e}") from e
        if isinstance(doc, dict) and doc.get("type") == "FeatureCollection":
            return "geojson"
        if isinstance(doc, dict) and "earthtwin_bundle" in doc:
            return "bundle"
        if isinstance(doc, list) or (isinstance(doc, dict) and isinstance(doc.get("records"), list)):
            return "json"
        raise DetectionError("JSON is not a FeatureCollection, an EarthTwin bundle, a record array or {\"records\": [...]}.")
    if ext in (".csv", ".txt"):
        try:
            head.decode("utf-8-sig")
        except UnicodeDecodeError:
            # head may cut a multibyte char; check the whole file once
            try:
                path.read_bytes().decode("utf-8-sig")
            except UnicodeDecodeError as e:
                raise DetectionError("CSV must be UTF-8 encoded.") from e
        return "csv"
    raise DetectionError(
        f"Unsupported file type '{ext or 'no extension'}'. Supported: CSV, JSON, GeoJSON, EarthTwin bundle, GeoTIFF. "
        "Download a template from the Data Center for the expected structure."
    )
