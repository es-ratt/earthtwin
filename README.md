# EarthTwin

**Finding Earth's best analogs for the Moon and Mars.**

Team **PLANEX** · NASA Space Apps Challenge 2026 · Challenge: *Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars*

EarthTwin is a scientific decision-support web application. It compares measured characteristics of Earth locations with
lunar and Martian target regions, shows the evidence behind every match, makes the differences and data gaps explicit,
and lets the team add NASA, ESA, USGS or other verified datasets through a Data Center, with no code changes or rebuilds.

> **Demonstration data.** The application ships with a curated catalogue (17 Earth sites, 9 Moon/Mars targets) and
> *illustrative placeholder measurements*, all labelled **DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT**. Results only
> become scientific once verified datasets are imported. See [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Quick start
```bash
git clone https://github.com/es-ratt/earthtwin.git && cd earthtwin
python3 -m venv .venv && source .venv/bin/activate      # Python 3.11+ (tested on 3.13)
pip install -r requirements-dev.txt
python run.py                                            # → http://127.0.0.1:8000
```
The first start creates `data/`, applies database migrations, imports the seed bundles through the normal import
pipeline, and prints the **Data Center admin token**. Run the tests with `cd backend && ../.venv/bin/python -m pytest -q`.

## What's inside
| Page | What it does |
|---|---|
| **Home** | Mission, challenge statement, how analog comparison works, live data-transparency counts |
| **Explorer** | Choose a Moon/Mars target and weighting profile, filter candidates; the map, ranking and evidence panel stay in sync |
| **Targets** | Moon and Mars explorers on their own planetocentric maps (NASA Trek imagery), name/coordinate search, target profiles |
| **Catalogue** | Searchable Earth analog catalogue by category with data-completeness indicators |
| **Site profile** | Context, every measurement with source/method/class, similarity breakdown, differences, applications, citations |
| **Compare** | Up to three sites against one target: dot plot, contribution bars, metrics table, CSV/PDF export |
| **Data Center** | Dataset catalogue, upload → inspect → field mapping → validation report → processing log → activation, versions, templates, providers (NASA CMR search) |
| **Reports** | Candidate CSV, comparison CSV, PDF scientific report |
| **Methodology** | Criteria, formulas, weights, missing-data rules, coordinate handling, limitations, sources from the database |
| **About** | Purpose, approach, acknowledgments, independence statement |

## How it works
```
Dataset import → format detection → validation → metadata & field mapping → normalisation
→ scientific processing (e.g. DEM → relief/slope/roughness) → feature extraction → similarity assessment
→ database update (+ revision bump) → every open page refreshes automatically
```
* **Similarity engine** (`backend/app/services/similarity.py`): per-criterion similarity (Gaussian, log-ratio, Jaccard,
  agreement), weight-normalised index, **coverage reported separately**, *Insufficient data* below threshold, and the
  input data classes carried through. Missing data are never treated as matches.
* **Planetary-aware**: Earth = WGS 84; Moon/Mars = planetocentric, east-positive on IAU 2015 spheres. Longitude
  conventions and latitude types must be declared on import; raster CRSs are checked against the declared body.
* **Provenance**: every value has its dataset, version, method, spatial support and class (`verified` / `derived` / `demo`).

## Repository layout
```
backend/app/
  main.py                API + static hosting        config.py   environment settings
  db.py, migrations/     SQLite + SQL migrations     seed.py     first-run seeding
  services/              vocabulary, units, similarity, catalog, analysis, exports, providers
  ingest/                detect.py, mapping.py, pipeline.py, adapters/{tabular,raster}.py
backend/seed/            curated catalogue + demo-measurement bundles (and their generator)
backend/tests/           pytest suite (engine, pipeline, API, rasters, exports, persistence)
frontend/                index.html, css/, js/{api,store,ui,charts,maps,components}.js, js/pages/*.js, vendor/leaflet
templates/               import templates (CSV, GeoJSON, bundle)
docs/                    DATA_DICTIONARY, METHODOLOGY, API, DEPLOYMENT, IMPLEMENTATION_STATUS
legacy/prototype.html    the original single-file prototype (kept for reference)
```

## Adding your datasets
1. Open **Data Center**, enter the admin token, choose **Import data**.
2. Upload a CSV/JSON/GeoJSON/GeoTIFF/bundle (templates under *Formats & templates*).
3. Pick what it contains, review the proposed field mapping, and confirm units and coordinate conventions.
4. Fill in provenance (verified data need publisher + source URL/identifier; add the citation).
5. **Validate** (a dry run with a full report) → **Process**. The dataset is versioned and activated, and every page updates.
6. When verified data cover your needs, deactivate *EarthTwin demonstration measurements*.

New *kinds* of measurement need a variable definition (and optionally a criterion) in
`backend/app/services/vocabulary.py`; new file types or processing need an adapter in `backend/app/ingest/adapters/`.
See [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Documentation
* [Data dictionary & import formats](docs/DATA_DICTIONARY.md)
* [Methodology](docs/METHODOLOGY.md) (full version in the app)
* [API](docs/API.md) (interactive at `/api/docs`)
* [Deployment](docs/DEPLOYMENT.md) (local, Docker, hosted; needs a persistent volume)
* [Implementation status, tests, limitations](docs/IMPLEMENTATION_STATUS.md)

## Tech stack
Python · FastAPI · SQLite · rasterio · pyproj · numpy · reportlab — vanilla JavaScript modules · Leaflet 1.9.4 (vendored) ·
inline SVG charts. No frontend build step.

## Acknowledgments
Imagery: NASA Solar System Treks (LRO WAC, LRO LOLA, Viking MDIM 2.1, MGS MOLA) and NASA GIBS Blue Marble. Land
outlines: Natural Earth. Metadata search: NASA CMR. Mapping: Leaflet (BSD-2-Clause).

## Team PLANEX
*(Add team member names here.)*

**Disclaimer:** EarthTwin is an independent project created for the NASA Space Apps Challenge and is not affiliated with
or endorsed by NASA. Similarity indices are prototype values, not probabilities of mission success or proof of
environmental equivalence.
