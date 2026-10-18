# EarthTwin import templates

| File | Import kind | Notes |
|---|---|---|
| `earth_sites_template.csv` | earth_sites | WGS 84 lat/lon. Lists use `;` (or `|` for applications/limitations). Measurement columns need units (confirm in the mapping step). |
| `target_regions_template.csv` | target_regions | You must choose the longitude convention and latitude type when importing. |
| `observations_wide_template.csv` | observations | One row per existing site/target, one column per variable. |
| `observations_long_template.csv` | observations_long | One row per value: subject, variable key, value, unit. |
| `map_layer_template.geojson` | map_layer | Any geometry; coordinates lon/lat of the declared body. |
| `bundle_template.json` | bundle | Self-describing dataset with metadata, records, observations and citations. |

Replace example values with real data — template rows are not data. Variable keys and accepted units are listed in the Data Center ("Formats & templates") and in `docs/DATA_DICTIONARY.md`.
