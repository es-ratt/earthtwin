# EarthTwin static prototype — data checklist

Team PLANEX · NASA Space Apps 2026 (14–15 Nov 2026) · branch `static-prototype`

The static app lives in `web/`, the scoring in `pipeline/`, and the Earth inputs in `datasets/`.
The older FastAPI app in `backend/` + `frontend/` is untouched.

## Run it

```bash
python3 pipeline/compute_scores.py          # recompute scores → web/data/results/*.json
cd web && python3 -m http.server 8000       # open http://localhost:8000
python3 -m pytest pipeline/tests -q -c pipeline/pytest.ini   # 16 tests (needs pytest)
```

The scoring script uses only the Python standard library. It must be served over HTTP; opening
`index.html` from disk will not load the JSON. To deploy, publish the `web/` folder to GitHub Pages
or Netlify as is (no build step); `.github/workflows/pages.yml` does this automatically once Pages
is set to "GitHub Actions" in the repo settings.

### Real data already in (fetched 2026-11-09, no login needed)

```bash
.venv/bin/python pipeline/fetch_real_data.py all          # re-fetch everything (~15 min, needs numpy+rasterio)
.venv/bin/python pipeline/fetch_real_data.py earth --only mauna-kea,lonar-crater   # just some sites
```

| Side | Feature | Data | Sites |
|---|---|---|---|
| Moon | `slope_240m_deg`, `roughness_240m_m` | LRO LOLA `LDEM_75S_240M` (PDS), 5 km window | the 5 sites with coordinates |
| Earth | `slope_deg`, `roughness_m` (30 m, 1 km window) | NASADEM; Copernicus DEM GLO-30 (ESA) above 60°N / below 56°S | all 18 |
| Earth | `slope_240m_deg`, `roughness_240m_m` | same DEM block-averaged to ~240 m, 5 km window | all 18 |
| Earth | `temp_range_K`, `annual_min_lst_K` | MODIS MOD11A2 + MYD11A2 v061 LST, year 2025 | all 18 |

Artemis IV now compares slope/roughness at **240 m on both sides** (the only full-coverage lunar
DEM used here). SkyFall keeps the 30 m Earth values.

Caveat shown in the app: above 60° latitude MODIS "night" overpasses are often sunlit in summer and
polar night/cloud removes composites, so `temp_range_K` there is flagged **low confidence**.

**Still SAMPLE on the Earth side:** rock cover, regolith type, geology, thermal inertia, ground
ice presence/depth, logistics. The app lists these in a banner on every result.

---

## 1. Earth data you must collect (most important)

File: `datasets/earth_features.csv` (one row per place × feature). Replace each `SAMPLE` row.

| column | what to put |
|---|---|
| `candidate_id` | id from `datasets/earth_candidates.csv` |
| `feature` | one of the ids below |
| `value` | number (or category word) — leave empty if unknown |
| `status` | `measured` (from data), `verify` (from literature, not yet checked), `TODO` |
| `source_id` | id from `web/data/sources.json` — **required whenever value is filled** (the script refuses otherwise) |
| `confidence` | `high` / `medium` / `low` |
| `note` | how you got it (file name, window size, date range) |

Rows marked `measured` came from `fetch_real_data.py` — leave them. Replace the `SAMPLE` rows:

| feature id | unit | where to get it | how |
|---|---|---|---|
| `slope_deg`, `roughness_m`, `*_240m_*` | ° / m | ✅ already measured | re-run `fetch_real_data.py earth`, or use your own DEM: `extract_features.py dem <dem.tif> --source-id nasadem` |
| `rock_cover_pct` | % | **proxy** — boulder maps or Landsat/ASTER texture | by hand per site; say "proxy" in the note |
| `regolith_type` | category | geological maps / papers | one of: `fine_impact_regolith`, `volcanic_ash_cinder`, `ice_rich_mantle`, `debris_over_ice`, `glacial_till`, `desert_soil`, `bare_rock` |
| `geology_type` | category | geological maps / papers | one of: `anorthosite`, `basalt`, `impact_breccia`, `sedimentary`, `ice_dominated`, `granitic`, `mixed` |
| `temp_range_K`, `annual_min_lst_K` | K | ✅ already measured (MODIS 2025) | for the polar sites, consider ASTER L2 day/night pairs to improve the low-confidence swing |
| `thermal_inertia_tiu` | J m⁻² K⁻¹ s⁻½ | **proxy** from day/night LST + albedo through a thermal model | must be in SI units like the Mars value. Raw ΔT is NOT thermal inertia |
| `ice_presence` | 0–3 | permafrost / ground-ice maps (NSIDC circum-Arctic map — external, verify) + papers | 0 none · 1 seasonal frost · 2 permafrost / ice in soil · 3 massive ice / buried glacier |
| `ice_depth_m` | m | active-layer thickness / depth to ground ice from papers | leave empty if there is no ice |
| `logistics_index` | 0–1 | team rubric | suggestion: access (0.4) + permits/safety (0.3) + comms (0.3) |

`max_sun_elev_deg` and `cold_index` are **derived by the script**. Do not type them in.

Coverage limits from the team doc: NASADEM/SRTM only reaches 60°N–56°S; ECOSTRESS only 54°N–54°S.

**Candidate coordinates** in `earth_candidates.csv` were typed by the assistant from general
knowledge and are marked `verify`. Check each one. Add new candidates as new rows; any place on
Earth works.

## 2. Target-site values still missing (from the team documents)

Edit `web/data/targets.json`. Fill `value` (or `min`/`max` for a range), set `status`, `source_id`
and `confidence`. Never fill a value without a source; the script stops with an error if you do.
Measured values go in `datasets/target_measurements.csv` and override `targets.json`.

**Done since the first version:** 240 m slope and roughness from LOLA for Haworth (14.5°, 3.5 m),
de Gerlache crater centre (6.6°, 3.9 m), Malapert summit (17.0°, 4.4 m), Nobile Rim 2 (13.3°, 4.5 m)
and Shackleton Connecting Ridge (9.6°, 5.2 m). These are 5 km medians around the position in the
team docs. For de Gerlache that is the crater centre, not Rim 2. The other four Artemis regions
need coordinates first. The slope ranges in the docs (e.g. Mons Mouton 0–7°) are at an unknown
scale and are kept as notes, not scored.

The table below is the original gap list; "Slope" for the five sites above is now covered at 240 m.

| Site | Missing |
|---|---|
| Haworth | Slope, Surface roughness, Rock cover, Geology / composition, Temperature swing, Depth to ice |
| de Gerlache Rim 2 | Slope, Surface roughness, Rock cover, Temperature swing, Ground ice |
| Malapert Massif | Surface roughness, Rock cover, Temperature swing, Ground ice, Depth to ice |
| Mons Mouton Plateau | Slope, Surface roughness, Rock cover, Temperature swing, Highest sun angle, Ground ice, Depth to ice + coordinates |
| Mons Mouton | Surface roughness, Rock cover, Temperature swing, Highest sun angle, Ground ice, Depth to ice + coordinates |
| Nobile Rim 1 | Slope, Surface roughness, Rock cover, Temperature swing, Highest sun angle, Ground ice, Depth to ice + coordinates |
| Nobile Rim 2 | Surface roughness, Rock cover, Geology / composition, Temperature swing, Ground ice, Depth to ice |
| Peak near Cabeus B | Slope, Surface roughness, Rock cover, Geology / composition, Temperature swing, Highest sun angle, Ground ice, Depth to ice + coordinates |
| Slater Plain | Slope, Surface roughness, Rock cover, Geology / composition, Temperature swing, Highest sun angle, Ground ice, Depth to ice + coordinates |
| Shackleton Connecting Ridge (reference) | Surface roughness, Rock cover, Temperature swing, Ground ice, Depth to ice |
| AP-105 | Surface roughness, Geology / composition, Temperature swing |
| Arcadia Planitia | Surface roughness, Geology / composition, Temperature swing + coordinates/outline |
| Deuteronilus Mensae | Surface roughness, Temperature swing |
| Utopia Planitia | Surface roughness, Geology / composition, Temperature swing + coordinates/outline |
| Phlegra Montes | Surface roughness, Temperature swing + coordinates/outline |
| Erebus Montes | Surface roughness, Geology / composition, Temperature swing |

"Highest sun angle" fills itself once a site has a latitude. Best sources for the Moon gaps: LOLA
slope/roughness maps (PGDA product 78, Moon Trek), Diviner temperatures (PDS), LROC boulder maps.
For Mars: HiRISE/CTX for slope and rocks, THEMIS for thermal inertia, SHARAD/SWIM for ice.

Coordinates for the six Artemis regions without positions: NASA's Moon Trek has an "Artemis III
Candidate Landing Regions" layer (2022 list, 13 regions) — useful for checking, but it is the older
list.

## 3. Decisions the team must make

All in `pipeline/config.json`, all shown in the app's METHOD tab:

1. **Scales** (`scales`) — provisional values chosen by the assistant.
2. **Category similarity tables** (`categorical_similarity`) — provisional.
3. **Weights** — the provisional numbers from the team doc.
4. **Artemis IV "relative cold"** — Earth cannot reach PSR temperatures, so the Moon temperature
   target is "the coldest Earth candidate" (`cold_index` = 1). Agree on this or replace it.
5. **Artemis HLS slope limit** — not in the team docs, so there is no Artemis hard filter
   (`missions.json` → `hls-slope-limit`, status TODO).
6. **SkyFall `tbd_by_nasa`** — the team doc says some constraints are TBD by NASA but not which. All
   are `null` until someone checks the SkyFall package.
7. **Ground-ice ordinal for the Moon** — only Haworth has a value (2). Other sites have conflicting or
   indirect evidence and are left empty on purpose.

## 4. Flags carried from the team documents (shown in the app, not used as facts)

- Shackleton temperatures differ between sections → `inconsistent_in_docs`, not scored.
- Shackleton crater count (~238,000), boulder count (~2,973) and radiation dose (200–400 mSv/yr)
  have no specific source → `no_specific_source`.
- de Gerlache depth: 7.5 km vs ~1.6 km → both shown.
- Haworth PSR temperature: ~60–80 K (Diviner paper, used) vs <40 K (Wikipedia).
- Slater Plain elevation: sign inconsistent in the source → not used.
- de Gerlache Rim 2 data mostly comes from "Site 011", which may not be the same place.
- Several papers were read as abstract only (`access` in `sources.json`).
- The 1.54° lunar tilt used for "highest sun angle" was added by the assistant from the NASA Moon fact
  sheet; please confirm.

## 5. Map layers (checked 2026-11-09)

Every layer below returned HTTP 200 with `Access-Control-Allow-Origin: *` and non-blank pixels.
**Note:** the brief said Trek tiles "reportedly have no CORS headers". On 2026-11-09 they did send
CORS headers. The app still uses Leaflet with raster tiles plus a per-layer blank-tile check and
fallback, as requested.

| Map | Layer | Service | Result |
|---|---|---|---|
| Moon | `LRO_LOLA_ClrShade_SPole75_30mp_v04` (default) | Moon Trek `/Moon/SP/` WMTS | ✅ data 75°S–90°S |
| Moon | `LRO_LOLA_Shade_SPole75_30mp_v04` | Moon Trek | ✅ |
| Moon | `LRO_LOLA_Illumination_SPole65S_240m` (PSR overlay) | Moon Trek | ✅ (black shapes on transparent) |
| Moon | `LRO_LOLA_ClrSlope_SPole75S_120m` (overlay) | Moon Trek | ✅ |
| Moon | `LRO_WAC_south`, `LOLA_south` | USGS Astrogeology WMS `moon_spole.map`, **SRS EPSG:32761** | ✅ matches Trek pixel for pixel |
| Moon | `LRO_LOLA_Shade_SPole875_5mp_v04` | Moon Trek | ⚠ works but covers only 87.5°S–90°S (Haworth is outside) — not used |
| Moon | USGS WMS with `IAU_2015:30120` | USGS | ❌ returns blank 200 images — not used |
| Mars | `Mars_Viking_MDIM21_ClrMosaic_global_232m` (default) | Mars Trek EQ WMTS | ✅ |
| Mars | `Mars_MGS_MOLA_ClrShade_merge_global_463m` | Mars Trek | ✅ |
| Mars | `THEMIS`, `MOLA_color` | USGS WMS `mars_simp_cyl.map`, EPSG:4326 | ✅ |
| Earth | `BlueMarble_ShadedRelief_Bathymetry` (default) | NASA GIBS EPSG:3857 | ✅ |
| Earth | `ASTER_GDEM_Color_Shaded_Relief` | GIBS | ✅ |
| Earth | `MODIS_Terra_L3_Land_Surface_Temp_8Day_Day` (2026-07-04) | GIBS | ✅ |
| Earth | USGS Earth tiles | — | not used (no global USGS basemap found) |
| Moon | Moon Trek `A3_Named_regions` vector layer | Trek | ❌ could not find a download URL |

The south-polar projection was checked by placing Shackleton, de Gerlache and Haworth markers on the
LOLA tiles. Static fallback images (bundled in `web/img/fallback/`) were made from these same
services.

## 6. Not done / known gaps

- Earth rock cover, regolith, geology, thermal inertia, ground ice and logistics are still SAMPLE (section 1).
  They need literature or proxy work by the team; the assistant did not fill them from memory.
- Mars target slope/roughness are not measured (HiRISE/CTX DEMs exist only for small areas).
- AP-105 is drawn as a point: the ellipse orientation is not in the team docs.
- Broad Mars regions without coordinates (Arcadia, Utopia, Phlegra) are listed under the map, not drawn.
- `extract_features.py` was tested on a synthetic DEM (10° plane → slope 10.0°, roughness 0.0 m),
  not on real NASADEM tiles yet.
- Browser testing: Chrome desktop and 390 px wide. Not yet tested in Safari/Firefox or on a projector.
