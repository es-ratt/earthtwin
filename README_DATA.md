# EarthTwin static prototype — data guide

Team PLANEX · NASA Space Apps 2026 (14–15 Nov 2026)

The app is in `web/`, the scoring and data scripts in `pipeline/`, and the inputs in `datasets/`.
Every value in the app is either **measured** (with its dataset, product ID, version, date range,
resolution, processing steps and URL), **derived** by a written rule, or **TODO** with the reason.
Nothing is estimated by hand. Data checked and fetched on **2026-11-10**; target positions, Diviner temperatures,
USGS geologic units and SkyFall constraints added on **2026-11-11** (following *EarthTwin Data Still Needed*).

## Run it

```bash
.venv/bin/python pipeline/fetch_context_data.py coords        # 1. check coordinates (writes the coordinate table)
.venv/bin/python pipeline/fetch_real_data.py all              # 2. terrain (Moon, Mars, Earth) + MODIS temperature (~20 min)
.venv/bin/python pipeline/fetch_context_data.py all           # 3. soil, rock type, permafrost, logistics (~15 min)
.venv/bin/python pipeline/fetch_earthdata.py ati              # 4. OPTIONAL, needs Earthdata login (see below)
.venv/bin/python pipeline/fetch_earthdata.py aster-dem        # 5. OPTIONAL, needs Earthdata login
.venv/bin/python pipeline/fetch_target_context.py all         # 6. Moon/Mars target context: Diviner PRP + USGS map units (~3 min)
python3 pipeline/compute_scores.py                            # 7. scores → web/data/results/*.json
cd web && python3 -m http.server 8000                         # open http://localhost:8000
.venv/bin/python -m pytest pipeline/tests -q -c pipeline/pytest.ini   # 55 tests
```

Step 1 must run before step 2, because the terrain and temperature are read at the checked positions.
Add `--only id1,id2` to any fetch command to redo some sites. The fetch scripts need `numpy`,
`rasterio`, `certifi`, `h5py` and `pyshp` (all in `.venv`); `compute_scores.py` needs only the standard library.

## What is real now (no login needed)

| Feature | Moon / Mars side | Earth side | Status |
|---|---|---|---|
| Slope, roughness at **240 m** (Artemis IV) | LRO LOLA `LDEM_75S_240M` (PDS) | NASADEM v001 / Copernicus GLO-30, resampled to 240 m | measured |
| Slope, roughness at **200 m** (SkyFall) | **HRSC-MOLA blended DEM 200 m v2** (USGS), AP-105, Deuteronilus, Erebus | NASADEM v001 / Copernicus GLO-30, resampled to 200 m | measured · *coarse-scale screening* |
| Temperature swing, coldest temperature | — | MODIS MOD11A2 + MYD11A2 v061, 2025 | measured (low confidence above 60°) |
| Regolith / soil type | team docs | USDA SSURGO/STATSGO (US) or ISRIC SoilGrids 2.0 (elsewhere, **non-NASA**) → category rule | verify |
| Rock type / geology | team docs | Macrostrat map units (compiles USGS and other survey maps; **third-party service**) → category rule | verify |
| Ground ice level, depth to ice | team docs | **ESA CCI Permafrost v5, 2023** (non-NASA, driven by NASA MODIS) + MODIS coldest temperature | verify |
| Logistics (access) | always 1 (Earth-only factor) | OurAirports + OpenStreetMap roads (**non-NASA**) → index rule | derived for 6 of 18 sites; **TODO for 12** (the OpenStreetMap Overpass servers were overloaded on 2026-11-10 and again on 2026-11-11). Airport distance is filled for all 18. Re-run `fetch_context_data.py logistics` later. Until then, logistics is left out of those sites' scores, so their weights are renormalised. |
| Coordinates | Moon: LROC NAC ROI mosaic centres (5 targets). Mars: USGS Gazetteer region centres (Arcadia, Utopia, Phlegra; **not sampled**) | USGS GNIS, Smithsonian GVP, Wikidata | verify; see the coordinate table |
| Annual max / mean temperature, ice-stability area and depth (**context, not scored**) | **LRO Diviner Polar Resource Product** `LRO-L-DLRE-5-PRP-V2.0` (PDS, thermal model) | — | measured (model output) |
| Geologic map unit (**context, not scored**) | USGS Unified Geologic Map of the Moon 1:5M (2020); USGS SIM 3292 Mars 1:20M (Tanaka et al. 2014) | — | measured (a unit is not a rock type) |

Same variable, same scale, same unit on both sides: both terrain comparisons use **one function**
(`common.resample_local`) that average-resamples any DEM onto a local metric grid centred on the
site, so the Moon/Mars and Earth values are measured identically.

### Deliberately left empty (null / TODO), and why

| Feature | Why it is empty | What it would take |
|---|---|---|
| **Earth rock cover (%)** | No dataset gives rock abundance in % on Earth. Texture proxies (DEM roughness, ASTER GED emissivity, Landsat texture) are not percentages, and converting them needs field calibration. | Boulder counts on high-resolution imagery for each site, or published field surveys with a citation. |
| **Earth thermal inertia (J m⁻² K⁻¹ s⁻½)** | The ATI proxy is in K⁻¹, a different variable. Your rule says same variable and unit, so it is not compared with Mars. | A calibrated thermal model plus field data, or published thermal-inertia studies of the site. |
| **ATI proxy** (context only) | Needs MCD43A3 albedo, which needs an Earthdata login. Planetary Computer has no MCD43A3. I did not use MCD43A4 reflectance with conversion coefficients that I could not check in the source paper. | Run `fetch_earthdata.py ati` after setting up the login (below). |
| Mars rock cover, thermal inertia, geology per region | Not in the team docs; SkyFall-wide limits are used. | THEMIS thermal inertia and TES rock abundance per region. |
| Fine-scale (1–5 m) Mars slope at AP-105 | No HiRISE DTM covering AP-105 was found. The nearest listed DTM (Feb 2026 PDS release, "candidate Starship site", ~39.1°N 189.8°E) is ~4° away. | Check the HiRISE DTM index (uahirise.org/dtm) or CTX stereo coverage; add a DTM with `extract_features.py dem`. |
| Slope at Arcadia, Utopia, Phlegra (Mars) | Their positions are USGS Gazetteer centres of regions 1,350–3,560 km across (Arcadia and Utopia lie north of the 30–45°N band). Marked `"kind": "region_centre"` and **not sampled**. | Team decision 3: define sample boxes inside 30–45°N, then rerun `fetch_real_data.py mars`. |
| Slater Plain position | LPSC 2025 abstract 2401 names only Slater crater (88°S, 111°E); no LROC ROI named for the plain was found. | A centre with its source in `web/data/targets.json`, then rerun `moon` and `fetch_target_context.py`. |
| Moon temperature **swing** | The Diviner PRP has annual maximum and annual mean, **no minimum**, so max − min cannot be computed. | Diviner seasonal polar products (PCP, 24 × 6 bins) give a minimum; not loaded yet. |

## Manual downloads (Earthdata login)

These NASA products need a free **NASA Earthdata login**. I cannot create accounts or enter
passwords for you, so these steps are yours.

**One-time setup**

1. Create an account: <https://urs.earthdata.nasa.gov/users/new>.
2. In your home folder, create `~/.netrc` with one line, then `chmod 600 ~/.netrc`:
   `machine urs.earthdata.nasa.gov login YOUR_USERNAME password YOUR_PASSWORD`
3. For AppEEARS and LP DAAC there is nothing else to approve. For NSIDC and SEDAC data, the first
   download in the browser asks you to authorise the application: click "Authorize".
4. `.venv/bin/pip install earthaccess` (only for step B).

| # | Product (ID · version, checked in NASA CMR) | Gives | How | Put files in |
|---|---|---|---|---|
| A | **MYD11A1 · 061** (Aqua LST daily 1 km, `C1748046084-LPCLOUD`) + **MCD43A3 · 061** (albedo 500 m, `C2278860820-LPCLOUD`) | ATI proxy | `fetch_earthdata.py ati` submits an AppEEARS point request and downloads the CSVs itself. **Or** in the AppEEARS web app: *Extract → Point Sample*, upload the 18 positions from `datasets/earth_candidates.csv`, dates 01-01-2025 to 12-31-2025, layers `LST_Day_1km`, `LST_Night_1km`, `QC_Day`, `QC_Night` (MYD11A1.061) and `Albedo_WSA_shortwave`, `BRDF_Albedo_Band_Mandatory_Quality_shortwave` (MCD43A3.061), then run `fetch_earthdata.py ati --from-csv FOLDER` | `datasets/manual/appeears/<task id>/` |
| B | **ASTGTM · 003** (ASTER GDEM v3, `C1711961296-LPCLOUD`) | NASA terrain above 60°N (replaces Copernicus for Haughton, Axel Heiberg, Svalbard, Duvanny Yar, Iceland) and Antarctica | `fetch_earthdata.py aster-dem` (earthaccess downloads the tiles) | `datasets/manual/astgtm/` |
| C | **GGD318 · v2** — Circum-Arctic Map of Permafrost and Ground-Ice Conditions (NSIDC) | Cross-check of the ESA CCI permafrost values | <https://nsidc.org/data/ggd318/versions/2> → download the shapefile or EASE-Grid files; compare the permafrost class at each Arctic site by hand in QGIS and note it in `earth_features.csv` | `datasets/manual/ggd318/` |
| D | **CIESIN_SEDAC_GROADS_V1 · 1.0** (gROADS) and **CIESIN_SEDAC_GPWv4_POPDENS_R11 · 4.11** (GPW) | NASA road and population data for logistics | Earthdata Search → product → download the global GeoTIFF/shapefile. A loader is not written yet: measure distance to the nearest gROADS road in QGIS and replace `road_distance_km` (source_id `sedac-groads-gpw`) | `datasets/manual/sedac/` |
| E | **VNP46A4 · 2** (VIIRS Black Marble annual night lights) | Infrastructure / power proxy | Earthdata Search or LAADS DAAC; not used yet | `datasets/manual/blackmarble/` |
| F | **SPL3FTP · 004** (SMAP freeze/thaw) | Seasonal frost check | Optional; not used yet | `datasets/manual/smap/` |

`datasets/manual/` and `datasets/cache/` are in `.gitignore`.

**Notes on the brief's product names**

- **"NSIDC-0068"** does not exist at NSIDC (`nsidc.org/data/nsidc-0068` returns "Page Not Found"). The
  circum-Arctic permafrost and ground-ice map is **GGD318, version 2**.
- **gSSURGO/STATSGO** are USDA NRCS products, not USGS. They are used through USDA Soil Data Access
  and labelled "other agency".
- **SMAP** has no soil-type product. Soil type comes from SSURGO (US) and SoilGrids (elsewhere).
- **USGS SGMC** covers the conterminous US only. Macrostrat is used for all 18 sites. For US sites
  it draws on USGS and state maps, and the map behind each value is named in its `lithology` text.
- The **Earth Impact Database** (passc.net) did not serve the database when checked; craters were
  checked with Wikidata instead.

## Coordinate verification (deliverable 4)

`datasets/coordinate_verification.csv`; also shown in the app under **Sources → Coordinate check**,
with a NASA Worldview link per site for a visual check. Tolerance: 1 km.

| Candidate | Old (lat, lon) | Verified (lat, lon) | Moved | Status | Source |
|---|---|---|---|---|---|
| Haughton Crater, Devon Island | 75.3800, -89.6700 | 75.3833, -89.6667 | 0.38 km | verified | [Wikidata Q1589279](https://www.wikidata.org/wiki/Q1589279) |
| San Francisco Volcanic Field | 35.3500, -111.5000 | 35.3197, -111.5171 | 3.71 km | updated | [USGS GNIS 5:27656](https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/5/query?where=gaz_id%3D27656&outFields=gaz_id&returnGeometry=true&outSR=4326&f=json) |
| Mauna Kea | 19.8200, -155.4700 | 19.8200, -155.4700 | 0.0 km | verified | [Smithsonian GVP 332030](https://volcano.si.edu/volcano.cfm?vn=332030) |
| Holuhraun lava field | 64.8700, -16.8300 | 64.8744, -16.7400 | 4.28 km | updated | [Wikidata Q17663620](https://www.wikidata.org/wiki/Q17663620) |
| Atacama Desert (Yungay) | -24.0800, -70.0100 | — | — | unverified | — (no reference found) |
| McMurdo Dry Valleys | -77.5000, 161.8000 | -77.5000, 162.0000 | 4.81 km | updated | [USGS GNIS 8:2821383](https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/8/query?where=gaz_id%3D2821383&outFields=gaz_id%2Clatitude%2Clongitude&returnGeometry=false&outSR=4326&f=json) |
| Mojave Desert | 35.0000, -116.0000 | 35.0083, -115.4750 | 47.83 km | updated | [Wikidata Q184355](https://www.wikidata.org/wiki/Q184355) |
| Death Valley | 36.5000, -116.9000 | 36.4569, -116.8653 | 5.71 km | updated | [Wikidata Q118388](https://www.wikidata.org/wiki/Q118388) |
| Nain Plutonic Suite, Labrador | 56.5000, -61.8000 | — | — | unverified | — (no reference found) |
| Marcy Anorthosite, Adirondacks | 44.1000, -73.9000 | 44.1128, -73.9237 | 2.37 km | updated | [USGS GNIS 5:973357](https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/5/query?where=gaz_id%3D973357&outFields=gaz_id&returnGeometry=true&outSR=4326&f=json) |
| Beacon Valley | -77.8200, 160.6500 | -77.8482, 160.5973 | 3.37 km | updated | [USGS GNIS 8:2814864](https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer/8/query?where=gaz_id%3D2814864&outFields=gaz_id%2Clatitude%2Clongitude&returnGeometry=false&outSR=4326&f=json) |
| Duvanny Yar (Kolyma) | 68.6300, 159.1500 | — | — | unverified | — (no reference found) |
| Expedition Fiord, Axel Heiberg Island | 79.4300, -90.8000 | 79.4333, -90.7667 | 0.77 km | verified | [Wikidata Q24190335](https://www.wikidata.org/wiki/Q24190335) |
| Bockfjorden volcanics, Svalbard | 79.4300, 13.3300 | 79.4317, 13.3050 | 0.54 km | verified | [Wikidata Q16897331](https://www.wikidata.org/wiki/Q16897331) |
| Tso Kar, Changthang Plateau (Ladakh) | 33.3000, 78.0000 | 33.3111, 77.9897 | 1.56 km | updated | [Wikidata Q1030718](https://www.wikidata.org/wiki/Q1030718) |
| Lonar Crater | 19.9800, 76.5100 | 19.9750, 76.5075 | 0.61 km | verified | [Wikidata Q2572189](https://www.wikidata.org/wiki/Q2572189) |
| Qaidam Basin | 37.5000, 94.0000 | 37.2667, 94.4500 | 47.48 km | updated | [Wikidata Q34709](https://www.wikidata.org/wiki/Q34709) |
| Sudbury Impact Structure | 46.6000, -81.2000 | 46.6000, -81.1833 | 1.27 km | updated | [Wikidata Q281965](https://www.wikidata.org/wiki/Q281965) |

What the statuses mean, and what to fix:

- **San Francisco Volcanic Field**: the Smithsonian GVP reference point (volcano 329020) is on San
  Francisco Mountain, a dacite/andesite volcano. The analog is the basaltic cinder terrain used for
  Apollo training, so the USGS GNIS "Cinder Lake" flat is used instead.
- **Tso Kar** and **Lonar**: the reference points are lake centres. Terrain there is flat water and
  the temperature is the lake's. The team should pick a shore or rim point.
- **Mojave, Qaidam, McMurdo Dry Valleys**: these are regions, so one reference point stands in for
  each. Mojave and Qaidam moved about 48 km.
- **Atacama (Yungay), Nain, Duvanny Yar**: no reference found. They keep the old assistant-typed
  position, marked `unverified`. Take positions from cited field papers.

## File formats

`datasets/earth_features.csv` (one row per site × feature):

`candidate_id, feature, value, unit, status, source_id, confidence, dataset, product_id, version,
date_range, resolution, processing, source_url, note`

- `status`: `measured`, `derived`, `verify` (real data, but the mapping or model needs a team check), or `TODO`.
- `source_id`: required whenever `value` is filled; must exist in `web/data/sources.json`.
- The provenance columns are copied into `web/data/earth_candidates.json` and shown in the app tooltips.

`datasets/target_measurements.csv`: the same columns, keyed by `site_id`.

`pipeline/context_rules.json` holds the **method choices**: soil class → regolith category,
lithology → geology category, permafrost → ice level, and distances → access index. All are
**provisional** (proposed by the assistant), so please review them.

## Decisions the team must make

1. **Scales** and **category similarity tables** (`pipeline/config.json`). Provisional.
2. **Weights** (team doc numbers) and the new 200 m slope/roughness scales (5° and 5 m, the same as for 240 m).
3. **Mapping rules** in `context_rules.json`. For example: are Cryosols an "ice-rich mantle"? Is ≥10%
   permafrost enough for level 2?
4. **Massive ice (level 3)**: Duvanny Yar (yedoma) and Beacon Valley (buried glacier ice) are known
   for it. A level 3 value needs a cited paper, so they stay at 2 for now.
5. **Rock-cover and thermal-inertia filters** for SkyFall are listed but **not applied to Earth**. No
   Earth data exists in the same unit, so applying them would make every Earth site "Cannot be
   evaluated". Agree on this or supply cited values.
6. Artemis HLS slope limit is still TODO. SkyFall `tbd_by_nasa` now follows the NASA package: the 100 m slope
   limit and the southern latitude limit are TBD; elevation, rock cover, thermal inertia and ellipse are not.
7. **SkyFall GPR depth conflict**: the team value is 0.5–3 m; the NASA package (section IV.a) says the radar is
   expected to reach ~3–5 m in low-loss materials. The scored target is unchanged until the team decides.
8. **Coordinate convention** for the nine Artemis targets (crater centre vs LROC ROI centre vs polygon). Haworth and
   de Gerlache still use crater centres; five targets use LROC ROI centres; the LROC values for Haworth and de
   Gerlache are recorded in their notes.
9. **Nobile Rim 1 and Mons Mouton** share one LROC mosaic (`NAC_ROI_MTMOUTONLOE`), so they have identical values.
   Merge them, or find separate centres (LPSC 2025 abstracts 2742 and 2655).
10. **Ice stability as depth to ice?** The Diviner ice-stability depth is shown as context. Using it as the scored
    `ice_depth_m` would compare a model of where ice *could* survive with measured Earth permafrost depth.

## Flags carried from the team documents (shown in the app, not used as facts)

- Shackleton temperatures differ between sections → `inconsistent_in_docs`, not scored.
- Shackleton crater count, boulder count and radiation dose have no specific source.
- de Gerlache depth: 7.5 km vs ~1.6 km → both shown. Rim 2 data mostly from "Site 011".
- Haworth PSR temperature: ~60–80 K (Diviner paper, used) vs <40 K (Wikipedia). The Diviner PRP gives 50–273 K
  annual maximum within 5 km of the crater centre (median 123 K): the window includes sunlit wall terrain.
- The PSR mean annual maxima (`psr_mean_annual_max_K`) are the team document's Hayne et al. 2015 values; the paper
  could not be re-opened (its server's TLS certificate chain is incomplete), so they stay `verify`.
- Slater Plain elevation sign is inconsistent in the source → not used.
- The 1.54° lunar tilt for "highest sun angle" was added from the NASA Moon fact sheet; please confirm.

## Map layers (checked 2026-11-09)

Unchanged from the first release: all Trek, GIBS and USGS layers returned HTTP 200 with CORS and
non-blank pixels; each base layer is re-checked in the browser and replaced by a bundled image if
blank. See the Sources tab for the live status.
