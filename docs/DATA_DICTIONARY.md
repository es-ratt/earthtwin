# EarthTwin data dictionary

The schema lives in `backend/app/migrations/*.sql` (applied automatically at start-up, recorded in `schema_migrations`).
Scientific definitions (variables, criteria, profiles, controlled vocabularies) live in `backend/app/services/vocabulary.py`
and are synchronised into the `variable` and `similarity_criterion` tables on every start.

## Conventions

* IDs are text: slugs for curated/imported records (`atacama-yungay`), 32-char hex UUIDs for generated rows.
* JSON columns hold JSON text. Timestamps are ISO-8601 UTC.
* **`data_class`** — one of:
  * `verified` – value from an identified dataset imported by the team (publisher **and** source URL or identifier required)
  * `derived` – calculated by the EarthTwin pipeline from a verified input (e.g. slope from a DEM)
  * `demo` – illustrative value used to exercise the application (**DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT**)
  * `reference` – catalogue/context records or imagery without measurements
* Coordinates: Earth = WGS 84 (EPSG:4326). Moon/Mars = planetocentric latitude, east-positive longitude −180…180 on the
  IAU 2015 spheres (`IAU_2015:30100` Moon, `IAU_2015:49900` Mars).

## Entities

| Entity (table) | Purpose | Key fields |
|---|---|---|
| **TargetWorld** (`target_world`) | Earth, Moon, Mars | `id`, `mean_radius_km`, `default_crs`, `longitude_convention`, `gravity_m_s2` |
| **TargetRegion** (`target_region`) | A lunar/Martian region to find analogs for | `world_id`, `lat`, `lon`, `crs`, `analysis_radius_km`, `region_type`, `description`, `geologic_context`, `mission_relevance`, `tags[]`, `extra{}`, `source_dataset_id`, `data_class` |
| **EarthAnalogSite** (`earth_site`) | Candidate terrestrial analog | `lat`, `lon` (WGS 84), `categories[]`, `terrain_type`, `description`, `geologic_context`, `analog_heritage`, `applications[]`, `limitations[]`, `future_work[]`, `extra{}`, `source_dataset_id`, `analysis_radius_km` |
| **Dataset** (`dataset`) | A source of records/values/imagery | `name`, `identifier`, `publisher`, `source_url`, `file_format`, `data_type`, `body`, `crs`, `spatial_coverage`, `temporal_coverage`, `units{}`, `spatial_resolution`, `license`, `provenance`, `data_class`, `status` (planned/processing/ready/failed), `active`, `current_version_id` |
| **DatasetVersion** (`dataset_version`) | One imported file | `version`, `original_filename`, `stored_path`, `sha256`, `size_bytes`, `field_mapping{}`, `processing_history[]` |
| **Observation** (`observation`) | One value of one variable for one subject | `dataset_version_id`, `subject_type` (earth_site/target_region), `subject_id`, `variable_key`, `value_num` or `value_text` (JSON), `unit` (canonical), `original_value`, `original_unit`, `data_class`, `method`, `uncertainty`, `spatial_support`, `observed_start/end`, `notes` |
| **TerrainFeature / GeologicalFeature / EnvironmentalFeature** | SQL views over `observation` by variable family | `terrain_feature`, `geological_feature`, `environmental_feature` |
| **Variable** (`variable`) | Definition of a measurable characteristic | `key`, `family`, `value_type` (numeric/categorical_set/boolean/ordinal), `canonical_unit`, `allowed_values[]` |
| **SimilarityCriterion** (`similarity_criterion`) | How a variable is compared | `variable_key`, `method`, `scale`, `applies_to[]`, `description`, `rationale` |
| **SimilarityAssessment** (`similarity_assessment`) | A reproducible site × target result | `weights{}`, `profile`, `status` (scored/insufficient_data), `score`, `coverage`, `n_criteria_used`, `criteria_results[]`, `data_classes[]`, `input_hash`, `engine_version` |
| **DataQualityAssessment** (`data_quality_assessment`) | Validation outcome per version | `n_records`, `n_valid`, `n_rejected`, `completeness`, `issues[]`, `summary` |
| **Citation** (`citation`) | Reference for a dataset or subject | `dataset_id` or `subject_type`+`subject_id`, `text`, `url`, `doi`, `kind` (dataset/reference/context), `verification` (team_verified/link_checked/unverified) |
| **AnalysisJob** (`analysis_job`) | Background processing run | `kind`, `status`, `log[]`, `error`, `result{}` |
| **ImportSession** (`import_session`) | Upload awaiting mapping/processing | `detected_format`, `import_kind`, `structure{}`, `proposed_mapping{}`, `confirmed_mapping{}`, `metadata{}`, `validation{}`, `status` |
| **MapLayer** (`map_layer`) | Vector overlay or tile basemap | `body`, `kind` (vector/tiles), `geojson_path` / `tile_url`, `legend{}`, `attribution` |
| **ExportedReport** (`exported_report`) | Record of every export | `kind`, `target_region_id`, `params{}`, `assessment_ids[]`, `file_path` |

### Value resolution
For each (subject, variable) the engine uses one value from **active** datasets' **current** versions:
`verified` > `derived` > `demo`, then the most recent.

## Variables

| Key | Family | Type | Canonical unit | Accepted input units / values |
|---|---|---|---|---|
| `mean_elevation_m` | terrain | numeric | m | m, km, ft (informational; never scored) |
| `local_relief_m` | terrain | numeric | m | m, km, ft |
| `mean_slope_deg` | terrain | numeric | deg | deg, rad, percent_grade |
| `slope_std_deg` | terrain | numeric | deg | deg, rad |
| `lithology` | geology | categorical_set | — | basalt, anorthosite, regolith_fine, impact_breccia, impact_melt, tephra, sedimentary_clastic, evaporite, clay_minerals, sulfates, carbonate, iron_oxides, granitic, gravel, sand_dunes, glacial_till, ice, permafrost |
| `impact_structure` | geology | boolean | — | yes/no, true/false, 1/0, present/absent |
| `lava_tube` | geology | boolean | — | as above |
| `mean_surface_temp_k` | environment | numeric | K | K, °C/C, °F/F |
| `surface_temp_range_k` | environment | numeric | K (difference) | K, °C, °F (no offset applied) |
| `annual_precip_mm` | environment | numeric | mm/yr | mm/yr, cm/yr, m/yr, in/yr |
| `vegetation_fraction` | environment | numeric | fraction | fraction, % (NDVI is **not** accepted) |
| `ground_ice` | resources | boolean | — | yes/no … |
| `accessibility` | operational | ordinal | — | high, medium, low (Earth only) |
| `analog_heritage` | operational | boolean | — | yes/no (Earth only) |

Site categories: `arid`, `volcanic`, `polar`, `impact`, `cave`, `highland`, `hydrothermal`.

## Import formats

| Kind | Formats | Required |
|---|---|---|
| `earth_sites` | CSV, JSON records, GeoJSON points | name, lat, lon (WGS 84) |
| `target_regions` | CSV, JSON, GeoJSON points | name, lat, lon, body (column or metadata), **longitude convention**, **latitude type** |
| `observations` (wide) | CSV, JSON, GeoJSON | subject column, subject type, match-by (id/name), ≥1 variable column with unit |
| `observations_long` | CSV, JSON | subject, variable, value (+ unit for numeric) |
| `raster` | GeoTIFF | body, raster kind (elevation/scalar), pixel unit, CRS (embedded or declared) |
| `map_layer` | GeoJSON (any geometry) | body, name |
| `bundle` | EarthTwin bundle JSON | see below |

Every dataset needs a name and a data class; `verified` additionally needs a publisher and a source URL or identifier.

### EarthTwin bundle (v1.0)
```json
{
  "earthtwin_bundle": "1.0",
  "dataset": {"name": "...", "publisher": "...", "source_url": "...", "identifier": "...", "license": "...",
              "data_class": "verified|demo|reference", "version": "v1", "body": "earth|moon|mars|mixed",
              "description": "...", "provenance": "...", "citation": {"text": "...", "doi": "..."}},
  "options": {"lon_convention": "east_180|east_360|west_360", "lat_type": "planetocentric|planetographic"},
  "earth_sites": [{"id": "...", "name": "...", "lat": 0, "lon": 0, "categories": ["arid"], "...": "..."}],
  "target_regions": [{"id": "...", "name": "...", "body": "moon", "lat": 0, "lon": 0, "...": "..."}],
  "observations": [{"subject_type": "earth_site", "subject_id": "...", "variable": "mean_slope_deg", "value": 3.1,
                    "unit": "deg", "method": "...", "uncertainty": 0.2, "observed_start": "...", "notes": "..."}],
  "citations": [{"text": "...", "url": "...", "doi": "...", "kind": "reference", "subject_type": "...", "subject_id": "..."}]
}
```
Templates for every kind are in `templates/` and downloadable from the Data Center.

## Adding a new kind of measurement
1. Add a `Variable` (and, if it should affect ranking, a `Criterion` with a documented method and scale) in `vocabulary.py`.
2. If it needs a new unit dimension, add it to `services/units.py`.
3. If it comes from a new file type or needs new processing (e.g. illumination from horizon maps), add an adapter in
   `backend/app/ingest/adapters/` and register it in `ingest/detect.py` / `ingest/pipeline.py`.
No frontend change is needed: pages render variables and criteria from `/api/vocabulary`.
