# Implementation status — EarthTwin by PLANEX

Status as of 2026-10-19. "Tested" means covered by the automated suite (`backend/tests`, 32 tests) and/or exercised in a
headless-Chrome run of the real UI (every route loaded with zero JavaScript errors; full Data Center import flow
driven through the browser: upload → inspect → map → validate → process → new site visible in Catalogue and Explorer).

## Phase 1 — audit of the original prototype (`legacy/prototype.html`)
| Weakness | Resolution |
|---|---|
| All 12 sites' factor scores were hard-coded "illustrative" numbers, then shifted by arbitrary 0–1 indices (`(ice-0.5)·w·24`) | Replaced by an engine that compares *measurements* of the same variable on both sides with documented methods |
| "Confidence" heuristic (`c − 0.3·spread`) mixed data quality with similarity | Replaced by explicit **weight coverage**, data-class labels and an *Insufficient data* state |
| Seasonal curves were generated from sine functions — charts of invented values | **Removed.** No chart now plots a value that is not in the database. A seasonal view can return once monthly time-series datasets are imported (see Future work) |
| Schematic polygon world map, coordinates approximate | Leaflet map with Natural Earth outlines (offline) and NASA GIBS imagery; separate planetocentric maps for Moon/Mars with NASA Trek imagery |
| Placeholder gradient "imagery" | Removed; real NASA imagery tiles with attribution, and informative fallbacks when offline |
| No data ingestion, persistence or provenance | Data Center, import pipeline, SQLite persistence, versioning, citations |
| Single 200-line HTML file | Modular backend (`app/ingest`, `app/services`) and frontend (`js/pages`, shared services) |
| Preserved | Mission-type weighting presets (now 5 criterion-level profiles), explainable "why this score", ranked list + map, 3-site comparison, report export, dark research look |

## Deliverables
| # | Deliverable | Status |
|---|---|---|
| 1 | Complete frontend (10 pages) | ✅ Done, browser-checked desktop + 390 px mobile, no horizontal overflow |
| 2 | Backend | ✅ FastAPI, documented at `/api/docs` |
| 3 | Persistent storage | ✅ SQLite + files in `EARTHTWIN_DATA_DIR`; persistence across restart tested |
| 4 | Interactive Earth explorer | ✅ Map ↔ ranking ↔ details synchronised; search, category and insufficient-data filters |
| 5 | Moon & Mars target selection | ✅ Separate planetary maps, name/coordinate search (great-circle distance on each body's radius) |
| 6 | Earth analog catalogue | ✅ 17 curated candidates, categories, completeness, grows with imports (tested) |
| 7 | Candidate detail pages | ✅ Context, measurements with provenance, similarity breakdown, differences, applications, limitations, citations, preserved extra fields |
| 8 | Similarity engine | ✅ 11 criteria + 2 optional Earth-only factors; unit-tested |
| 9 | Comparison laboratory | ✅ Up to 3 sites, dot plot, contribution bars, metrics table, CSV/PDF |
| 10 | Data Center & import pipeline | ✅ Upload, detection, inspection, field mapping, metadata editor, validation report, processing log, activation, versions, deletion |
| 11 | Validation & normalisation | ✅ Units, coordinates, planetary conventions, value plausibility, controlled vocabularies |
| 12 | Provenance & citations | ✅ Per value; DOIs/URLs in the seed were checked to resolve (Crossref / HTTP) on 2026-10-19 |
| 13 | Honest demonstration mode | ✅ Mode badge, demo banner, per-value badges, demo labels in CSV/PDF, include-demo toggle |
| 14 | Methodology documentation | ✅ `/#/methodology` (live from the DB) and `docs/METHODOLOGY.md` |
| 15 | PDF & CSV exports | ✅ Tested |
| 16 | Sample templates | ✅ `templates/` (all parse; bundle template imports successfully) |
| 17 | Schema & migrations | ✅ `backend/app/migrations`, `docs/DATA_DICTIONARY.md` |
| 18 | Automated tests | ✅ 32 passing |
| 19 | README | ✅ |
| 20 | Deployment instructions | ✅ `docs/DEPLOYMENT.md`, Dockerfile |
| 21 | This status report | ✅ |
| 22 | Limitations & future work | ✅ below |

## What is tested (automated)
Seeding through the pipeline · catalogue/target listing · reproducible assessments (same input hash/ID) · weights change
results · unknown weights/targets rejected · deactivating demo data → every result *Insufficient data* · admin token
required (missing/wrong) · CSV site import with measurements → visible in site page, dataset list, ranking (with verified
class), mode switch, CSV export · row-level rejection of invalid latitude · unmapped columns preserved · missing unit
blocks validation · verified data require publisher + source · unsupported/malformed files (xlsx, fake tif, bad JSON,
binary CSV, empty) rejected with guidance · long-format import with unit conversion (cm/yr → mm/yr), unknown subjects
reported · verified beats demo · new dataset version replaces values · target import requires longitude convention and
latitude type, converts 0–360 → −180…180 · synthetic UTM DEM → slope 10.0° ± 0.05, relief as expected, spatial support
recorded · lunar raster on an Earth dataset rejected (body mismatch) · lunar scalar raster → derived target value, only
covered targets processed · failed processing rolls back and is reported as failed · map layer import (body-scoped) ·
bundle template import; reference bundles cannot carry measurements · all templates parse · exports (CSV row counts,
PDF magic bytes) and export history · persistence and idempotent re-seeding after restart · delete protection ·
metadata edit. Engine unit tests: Gaussian/log-ratio/Jaccard/boolean, missing ≠ match, coverage threshold, weighted
mean and contribution sum, demo labelling, hash determinism, negative weights, unit conversions (incl. temperature
differences and % grade), longitude conventions, Mars planetographic latitude, mapping proposals.

## Not implemented / known limitations
* **No verified scientific data are bundled.** All measurements shipped are demo placeholders. Results are not findings.
* No direct download from NASA data archives: CMR is used for metadata search only; files are downloaded manually
  (Earthdata Login) and uploaded. PDS IMG / ISIS / NetCDF / HDF / shapefiles must be converted to GeoTIFF/GeoJSON first.
* Raster windows are square boxes, not circles; only band 1 is processed; no reprojection/mosaicking of several tiles.
* No illumination, radiation, gravity, regolith geotechnics or dust criteria (would need new variables + adapters).
* Planetary maps are equirectangular; polar targets are distorted on screen (computations are unaffected).
* Single shared admin token (no per-user accounts or audit log beyond processing history).
* Seasonal analysis from the prototype is removed until real time-series data can drive it.
* Light theme from the prototype is not carried over (dark research workspace only).
* Similarity scales are design choices not yet validated against expert analog assessments.

## Suggested next steps for PLANEX
1. Import NASADEM tiles for each Earth site (GeoTIFF, elevation, unit m) → terrain criteria become `derived`.
2. Import LOLA south-pole and MOLA MEGDR GeoTIFFs for the targets.
3. Build MODIS LST and GPM IMERG climatologies as GeoTIFFs (scalar rasters) or CSVs.
4. Deactivate *EarthTwin demonstration measurements* in the Data Center → the app switches to verified mode.
5. Have a planetary scientist review criterion scales and profiles; record changes in `vocabulary.py` (engine version bump).
