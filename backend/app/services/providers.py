"""Provider adapters.

A provider either retrieves data/metadata directly (where a reliable public API
exists) or documents the manual-import route. The application never depends on
a remote provider being reachable: failures return a clear error and the rest
of the app keeps working.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ..config import get_settings

PROVIDERS = [
    {"id": "manual_upload", "name": "Manual upload (Data Center)", "mode": "manual", "status": "available",
     "description": "Upload CSV, JSON, GeoJSON, EarthTwin bundles or GeoTIFF files; review mapping; validate; process."},
    {"id": "nasa_cmr", "name": "NASA Earthdata CMR collection search", "mode": "metadata_api", "status": "available",
     "url": "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html",
     "description": "Searches NASA's Common Metadata Repository for collections and pre-fills dataset metadata "
                    "(name, short name, provider, links). Data files themselves require Earthdata Login and are imported manually."},
    {"id": "pds_geosciences", "name": "NASA PDS Geosciences Node (LOLA, MOLA, Diviner)", "mode": "manual", "status": "manual_only",
     "url": "https://pds-geosciences.wustl.edu/",
     "description": "Download gridded products, convert PDS IMG to GeoTIFF with GDAL keeping the planetary CRS, then upload as a raster."},
    {"id": "usgs_astrogeology", "name": "USGS Astrogeology", "mode": "manual", "status": "manual_only",
     "url": "https://astrogeology.usgs.gov/search",
     "description": "Planetary mosaics, DEMs and geologic maps; convert to GeoTIFF / GeoJSON and upload."},
    {"id": "esa_psa", "name": "ESA Planetary Science Archive", "mode": "manual", "status": "manual_only",
     "url": "https://psa.esa.int/",
     "description": "Mars Express / ExoMars products; convert to GeoTIFF and upload."},
]


class ProviderError(RuntimeError):
    pass


def cmr_search(q: str, page_size: int = 10) -> list[dict]:
    if not get_settings().enable_remote_providers:
        raise ProviderError("Remote providers are disabled on this server (EARTHTWIN_REMOTE_PROVIDERS=0).")
    q = (q or "").strip()
    if len(q) < 2:
        raise ProviderError("Enter at least two characters.")
    url = "https://cmr.earthdata.nasa.gov/search/collections.json?" + urllib.parse.urlencode(
        {"keyword": q[:100], "page_size": max(1, min(page_size, 25))})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EarthTwin/1.0 (NASA Space Apps prototype)"})
        with urllib.request.urlopen(req, timeout=12) as r:
            doc = json.loads(r.read(5_000_000).decode("utf-8"))
    except Exception as e:  # network errors, timeouts, bad JSON
        raise ProviderError(f"NASA CMR is unreachable right now ({type(e).__name__}). Manual import still works.") from e
    out = []
    for e in doc.get("feed", {}).get("entry", []):
        links = [l.get("href") for l in e.get("links", []) if l.get("href", "").startswith("http")][:5]
        out.append({
            "title": e.get("title"), "short_name": e.get("short_name"), "version": e.get("version_id"),
            "data_center": e.get("data_center"), "organizations": e.get("organizations", []),
            "summary": (e.get("summary") or "")[:600], "time_start": e.get("time_start"), "time_end": e.get("time_end"),
            "boxes": e.get("boxes"), "links": links, "concept_id": e.get("id"),
            "metadata_prefill": {
                "name": e.get("title"), "identifier": f"{e.get('short_name')} v{e.get('version_id')} ({e.get('id')})",
                "publisher": ", ".join(e.get("organizations", [])) or e.get("data_center"),
                "source_url": f"https://cmr.earthdata.nasa.gov/search/concepts/{e.get('id')}.html",
                "temporal_coverage": f"{e.get('time_start') or ''} – {e.get('time_end') or 'present'}",
                "description": (e.get("summary") or "")[:600],
            },
        })
    return out
