"""First-run seeding.

1. Target worlds (Earth, Moon, Mars) with their reference CRSs.
2. Catalogue entries for datasets the pipeline is designed for, with status
   'planned' (not integrated — shown honestly as such in the Data Center).
3. Online planetary basemaps (NASA Solar System Treks WMTS) as reference tile layers.
4. The curated catalogue bundle and the demonstration-measurements bundle,
   imported *through the same pipeline the Data Center uses*.
"""
from __future__ import annotations

from pathlib import Path

from .db import dumps, new_id, now, session
from .ingest.pipeline import import_file

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"

WORLDS = [
    ("earth", "Earth", 6371.0, "EPSG:4326", "east_180", 9.81, "WGS 84 geographic coordinates."),
    ("moon", "Moon", 1737.4, "IAU_2015:30100", "east_180", 1.62,
     "Planetocentric latitude, east-positive longitude on the IAU 2015 lunar reference sphere (R = 1737.4 km)."),
    ("mars", "Mars", 3389.5, "IAU_2015:49900", "east_180", 3.71,
     "Planetocentric latitude, east-positive longitude on the IAU 2015 Mars reference sphere (R = 3396.19 km)."),
]

PLANNED = [
    dict(name="NASADEM Merged DEM Global 1 arc second", identifier="NASADEM_HGT v001", publisher="NASA / JPL; distributed by LP DAAC",
         source_url="https://lpdaac.usgs.gov/products/nasadem_hgtv001/", body="earth", spatial_resolution="1 arc-second (~30 m)",
         crs="EPSG:4326", license="Public domain (NASA)", data_type="raster", units={"elevation": "m"},
         description="Planned input for Earth-site terrain statistics (relief, slope, roughness) via the GeoTIFF DEM pipeline.",
         citation=("Farr, T. G., Rosen, P. A., et al. (2007). The Shuttle Radar Topography Mission. Reviews of Geophysics, 45(2).",
                   "10.1029/2005RG000183")),
    dict(name="MODIS Land Surface Temperature 8-day 1 km (MOD11A2 v061)", identifier="MOD11A2 v061", publisher="NASA LP DAAC",
         source_url="https://lpdaac.usgs.gov/products/mod11a2v061/", body="earth", spatial_resolution="1 km", crs="MODIS sinusoidal",
         license="Public domain (NASA)", data_type="raster", units={"LST": "K (scale factor 0.02)"},
         description="Planned input for Earth-site mean surface temperature and thermal range (scalar raster pipeline after compositing)."),
    dict(name="GPM IMERG precipitation", identifier="GPM IMERG", publisher="NASA GES DISC", source_url="https://gpm.nasa.gov/data/imerg",
         body="earth", spatial_resolution="0.1°", crs="EPSG:4326", license="Public domain (NASA)", data_type="raster",
         units={"precipitation": "mm/hr (climatology must be aggregated to mm/yr)"},
         description="Planned input for annual precipitation (aridity criterion) after aggregation to an annual climatology GeoTIFF."),
    dict(name="LRO LOLA gridded topography", identifier="LRO-L-LOLA-4-GDR", publisher="NASA PDS Geosciences Node",
         source_url="https://pds-geosciences.wustl.edu/missions/lro/lola.htm", body="moon", spatial_resolution="Product dependent (e.g. 5–118 m/px polar)",
         crs="IAU lunar sphere (polar stereographic or simple cylindrical)", license="Public domain (NASA PDS)", data_type="raster",
         units={"elevation": "m or km relative to 1737.4 km sphere (product dependent)"},
         description="Planned input for lunar target terrain statistics via the DEM pipeline (convert PDS IMG to GeoTIFF first).",
         citation=("Smith, D. E., Zuber, M. T., et al. (2010). The Lunar Orbiter Laser Altimeter investigation on the Lunar Reconnaissance "
                   "Orbiter mission. Space Science Reviews, 150, 209–241.", "10.1007/s11214-009-9512-y")),
    dict(name="LRO Diviner Lunar Radiometer derived temperatures", identifier="LRO Diviner", publisher="NASA PDS Geosciences Node / UCLA",
         source_url="https://pds-geosciences.wustl.edu/missions/lro/diviner.htm", body="moon", spatial_resolution="Product dependent",
         crs="IAU lunar sphere", license="Public domain (NASA PDS)", data_type="raster", units={"temperature": "K"},
         description="Planned input for lunar surface temperature and thermal range.",
         citation=("Paige, D. A., Siegler, M. A., et al. (2010). Diviner Lunar Radiometer observations of cold traps in the Moon's "
                   "south polar region. Science, 330(6003), 479–482.", "10.1126/science.1187726")),
    dict(name="MGS MOLA gridded topography (MEGDR)", identifier="MGS-M-MOLA-5-MEGDR", publisher="NASA PDS Geosciences Node",
         source_url="https://pds-geosciences.wustl.edu/missions/mgs/mola.html", body="mars", spatial_resolution="Up to 128 px/deg (~463 m)",
         crs="IAU Mars sphere", license="Public domain (NASA PDS)", data_type="raster", units={"elevation": "m relative to areoid"},
         description="Planned input for Martian target terrain statistics via the DEM pipeline.",
         citation=("Smith, D. E., Zuber, M. T., et al. (2001). Mars Orbiter Laser Altimeter: Experiment summary after the first year "
                   "of global mapping of Mars. Journal of Geophysical Research: Planets, 106(E10), 23689–23722.", "10.1029/2000JE001364")),
    dict(name="Mars Odyssey THEMIS thermal products", identifier="THEMIS", publisher="Arizona State University / NASA PDS",
         source_url="https://themis.asu.edu/", body="mars", spatial_resolution="100 m/px (IR)", crs="IAU Mars sphere",
         license="Public domain (NASA PDS)", data_type="raster", units={"temperature": "K"},
         description="Planned input for Martian surface temperature context."),
    dict(name="USGS Astrogeology planetary map catalogue", identifier="USGS Astrogeology", publisher="U.S. Geological Survey",
         source_url="https://astrogeology.usgs.gov/search", body="mixed", spatial_resolution="Product dependent", crs="Product dependent",
         license="Public domain (USGS)", data_type="reference", units={},
         description="Source for planetary geologic maps (map-layer import as GeoJSON after conversion)."),
]

TILE_LAYERS = [
    ("moon", "LRO WAC global mosaic (NASA Trek)",
     "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
     "NASA/GSFC/ASU LROC WAC mosaic via NASA Solar System Treks"),
    ("moon", "LOLA colour shaded relief (NASA Trek)",
     "https://trek.nasa.gov/tiles/Moon/EQ/LRO_LOLA_ClrShade_Global_128ppd_v04/1.0.0/default/default028mm/{z}/{y}/{x}.png",
     "NASA LRO LOLA via NASA Solar System Treks"),
    ("mars", "Viking MDIM 2.1 colour mosaic (NASA Trek)",
     "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
     "NASA/USGS Viking MDIM 2.1 via NASA Solar System Treks"),
    ("mars", "MOLA colour shaded relief (NASA Trek)",
     "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
     "NASA MGS MOLA via NASA Solar System Treks"),
    ("earth", "Blue Marble shaded relief (NASA GIBS)",
     "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
     "NASA Earth Observatory Blue Marble via NASA GIBS"),
]


def seed_static(conn) -> None:
    for w in WORLDS:
        conn.execute("""INSERT OR IGNORE INTO target_world(id, name, mean_radius_km, default_crs, longitude_convention, gravity_m_s2, description)
                        VALUES (?,?,?,?,?,?,?)""", w)
    if conn.execute("SELECT COUNT(*) FROM dataset WHERE status = 'planned'").fetchone()[0] == 0:
        ts = now()
        for p in PLANNED:
            did = new_id()
            conn.execute("""INSERT INTO dataset(id, name, identifier, publisher, source_url, file_format, data_type, body, crs, spatial_resolution,
                            license, units, description, provenance, data_class, status, active, created_at, updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (did, p["name"], p["identifier"], p["publisher"], p["source_url"], "none", p["data_type"], p["body"], p["crs"],
                          p["spatial_resolution"], p["license"], dumps(p["units"]), p["description"],
                          "Catalogue entry only. Not yet downloaded, processed or used in any score.", "reference", "planned", 0, ts, ts))
            if p.get("citation"):
                text, doi = p["citation"]
                conn.execute("INSERT INTO citation(id, dataset_id, text, url, doi, kind, verification, created_at) VALUES (?,?,?,?,?,?,?,?)",
                             (new_id(), did, text, f"https://doi.org/{doi}", doi, "dataset", "link_checked", ts))
    if conn.execute("SELECT COUNT(*) FROM map_layer WHERE kind = 'tiles'").fetchone()[0] == 0:
        ts = now()
        did = new_id()
        conn.execute("""INSERT INTO dataset(id, name, publisher, source_url, file_format, data_type, body, description, provenance,
                        license, data_class, status, active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (did, "Online basemaps (NASA Solar System Treks & GIBS)", "NASA", "https://trek.nasa.gov", "none", "map_layer", "mixed",
                      "Imagery tiles streamed from public NASA WMTS services for visual context only; never used in scoring.",
                      "Remote tiles; the app remains usable offline with vector outlines/graticules.", "NASA imagery usage guidelines",
                      "reference", "ready", 1, ts, ts))
        for body, name, url, attr in TILE_LAYERS:
            conn.execute("""INSERT INTO map_layer(id, dataset_id, name, body, kind, tile_url, legend, attribution, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""", (new_id(), did, name, body, "tiles", url, "{}", attr, ts))


def seed_bundles() -> list[str]:
    """Import seed bundles through the public pipeline (only if not already present)."""
    done = []
    with session() as conn:
        have = {r[0] for r in conn.execute("SELECT name FROM dataset")}
    for fname in ("catalogue.json", "demo_measurements.json"):
        import json
        meta = json.loads((SEED_DIR / fname).read_text(encoding="utf-8"))["dataset"]
        if meta["name"] in have:
            continue
        import_file(SEED_DIR / fname, "bundle", {"kind": "bundle"}, {})
        done.append(fname)
    return done
