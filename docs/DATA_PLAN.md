# Data plan: replacing the SAMPLE values (2026-11-10)

Deliverable 1. Every product ID and version below was checked in NASA CMR or on the provider portal on 2026-11-10.

## Downloaded or read automatically (no login)

| Item | Dataset (ID · version) | Agency | Script |
|---|---|---|---|
| 7 · Mars slope at ~200 m | Mars MGS MOLA – MEX HRSC Blended DEM Global 200 m **v2** (USGS Astrogeology), windowed reads from the public S3 copy | USGS/NASA | `fetch_real_data.py mars` |
| 7 · Earth slope at 200 m (same grid) | NASADEM_HGT **001** (Planetary Computer); Copernicus DEM GLO-30 above 60°N / below 56°S | NASA; **ESA (non-NASA)** | `fetch_real_data.py earth` |
| Temperature swing | MOD11A2 + MYD11A2 **061**, 2025 (Planetary Computer) | NASA | `fetch_real_data.py earth` |
| 2 · Soil type | USDA SSURGO/STATSGO via Soil Data Access (US sites); ISRIC SoilGrids **2.0** WRB (elsewhere) | **USDA; ISRIC (non-NASA)** | `fetch_context_data.py soil` |
| 3 · Rock type | Macrostrat map API **v2** (compiles USGS, GSC and other survey maps) | **third-party service** | `fetch_context_data.py geology` |
| 5 · Permafrost presence and depth | ESA Permafrost CCI **v5.0**, 2023: PFR and ALT, 0.01° (NH + Antarctica) | **ESA (non-NASA)**, driven by NASA MODIS LST | `fetch_context_data.py permafrost` |
| 6 · Logistics | OurAirports; OpenStreetMap roads via Overpass | **third-party** | `fetch_context_data.py logistics` |
| 8 · Coordinates | USGS GNIS (National Map geonames); Smithsonian GVP WFS; Wikidata P625 | USGS; third-party | `fetch_context_data.py coords` |

## Cannot be accessed from this environment (Earthdata login needed)

| Item | Dataset (ID · version) | What you must do |
|---|---|---|
| 4 · Thermal inertia proxy (ATI) | MYD11A1 **061** + MCD43A3 **061** via AppEEARS | Create `~/.netrc`, run `fetch_earthdata.py ati` (README_DATA.md, step A) |
| Arctic DEM (NASA) | ASTGTM **003** (ASTER GDEM v3) | `fetch_earthdata.py aster-dem` (step B) |
| 5 · Permafrost cross-check | NSIDC **GGD318 v2** (the brief's "NSIDC-0068" ID does not exist) | Manual download and comparison (step C) |
| 6 · NASA logistics data | SEDAC gROADS **v1**, GPWv4 **4.11**, VIIRS Black Marble VNP46A4 **v2** | Manual download (steps D, E) |
| Freeze/thaw check | SMAP SPL3FTP **004** | Optional (step F) |
| ORNL active-layer thickness | ABoVE ALT products (Alaska/Canada only) | Not useful for most candidates. ESA CCI ALT is used instead |

## Not computable without inventing numbers (left null / TODO)

- **1 · Rock cover (%)**: no Earth rock-abundance dataset exists, and the proxies cannot be turned into % without calibration.
- **4 · Thermal inertia in J m⁻² K⁻¹ s⁻½**: ATI is in K⁻¹. It is shown as context and never compared with Mars.
- **Fine-scale (1–5 m) slope at AP-105**: no HiRISE DTM found there.

## Assumptions made without asking

1. A filter with no same-unit Earth data (rock cover, thermal inertia) is **listed but not applied to Earth**. The alternative is that every Earth site becomes "Cannot be evaluated".
2. Open non-NASA datasets (ESA CCI, SoilGrids, Macrostrat, OSM) are used **now** and labelled. They will be replaced when the login-gated NASA products are added.
3. Category mappings (soil → regolith, lithology → geology, permafrost → ice level) and the logistics formula are written in `pipeline/context_rules.json` as **provisional team decisions**.
