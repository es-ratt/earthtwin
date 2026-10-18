# EarthTwin methodology (summary)

The full, live methodology — including the criteria table, weights and the datasets/citations actually present in the
database — is rendered at **`/#/methodology`** from `/api/vocabulary`. This file summarises it for reviewers.

## What the index is — and is not
EarthTwin reports a **prototype similarity index** (0–100) between an Earth site and a Moon/Mars target region, computed
from the variables both have data for. It is *not* a probability of mission success, not a validated ranking, and not a
statement that two environments are equivalent. Gravity, vacuum/atmosphere and radiation can never be matched on Earth.

## Criteria and comparison methods
| Criterion | Variable | Method | Scale |
|---|---|---|---|
| Local relief | `local_relief_m` | Gaussian on log10 ratio | σ = 0.35 |
| Mean slope | `mean_slope_deg` | Gaussian on difference | σ = 5° |
| Slope variability | `slope_std_deg` | Gaussian on difference | σ = 4° |
| Surface lithology | `lithology` | Jaccard index of controlled terms | — |
| Impact structure | `impact_structure` | agreement | — |
| Lava tubes / caves | `lava_tube` | agreement | — |
| Mean surface temperature | `mean_surface_temp_k` | Gaussian on difference | σ = 35 K |
| Thermal range | `surface_temp_range_k` | Gaussian on log10 ratio | σ = 0.3 |
| Aridity | `annual_precip_mm` | Gaussian on log10(1+x) difference | σ = 0.6 |
| Absence of vegetation | `vegetation_fraction` | Gaussian on difference | σ = 0.15 |
| Ground ice | `ground_ice` | agreement | — |
| Accessibility *(Earth-only, weight 0 by default)* | `accessibility` | high 1 / medium 0.6 / low 0.3 | — |
| Analog heritage *(Earth-only, weight 0 by default)* | `analog_heritage` | yes 1 / no 0 | — |

Scales are documented design choices, not fitted values; validating them against expert site assessments is future work.

## Aggregation
`index = 100 · Σ wᵢ sᵢ / Σ wᵢ` over criteria with data on **both** sides; `coverage = Σ w(available) / Σ w(requested)`.
Missing values are excluded (never a match, never zero). Below 60% coverage or with fewer than 3 criteria the result is
**Insufficient data** (thresholds configurable). Contributions `100·wᵢsᵢ/Σw` sum to the index.

## Provenance and data classes
Each value carries dataset, version, method, spatial support and class (`verified`, `derived`, `demo`). Each result carries
the lowest class among its inputs; anything touching demo data is labelled
**DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT** in the UI, CSVs and PDFs.

## Raster processing (DEM / scalar)
* Window: square of side 2 × analysis radius (default 10 km) around each subject, read with rasterio windowed I/O;
  averaged decimation above 4 Mpx. ≥ 50% valid pixels required.
* The raster CRS ellipsoid must match the declared body (Earth/Moon/Mars radius check) — planetary data are never
  applied to the wrong body.
* Slope: central differences (`numpy.gradient`) with pixel spacing in metres (projected CRS units, or body radius ×
  angular resolution × cos φ for geographic rasters). Relief = P95 − P5 of elevation.
* Products: `mean_elevation_m`, `local_relief_m`, `mean_slope_deg`, `slope_std_deg` (elevation); window mean of a chosen
  numeric variable (scalar). Values are `derived` if the raster is `verified`, else `demo`.

## Reproducibility
Assessments store weights, thresholds, engine version, criterion results and a SHA-256 input hash over the exact
observation IDs and values used.

## Known methodological limitations
* Criteria omit radiation, gravity, pressure, regolith geotechnics, illumination geometry, dust.
* Window means hide extremes (e.g. cold traps vs illuminated rims).
* Terrain statistics depend on DEM resolution and window size; compare like with like.
* Polar targets are distorted in the equirectangular planetary map (display only; calculations use proper CRSs).
