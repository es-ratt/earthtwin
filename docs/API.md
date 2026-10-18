# EarthTwin API

Interactive OpenAPI documentation: **`/api/docs`** (machine-readable: `/api/openapi.json`).
Endpoints marked 🔒 require the header `X-Admin-Token: <EARTHTWIN_ADMIN_TOKEN>`.

## Read
| Method & path | Description |
|---|---|
| `GET /api/health` | Liveness, engine version, data revision |
| `GET /api/state` | Data revision (polled by the UI for auto-refresh), mode (demo/mixed/verified/empty), counts |
| `GET /api/vocabulary` | Variables, criteria, profiles, controlled terms, thresholds |
| `GET /api/formats` | Supported formats, import kinds, accepted units, templates, limits |
| `GET /api/worlds` | Earth, Moon, Mars with reference CRS |
| `GET /api/targets?world=&q=&include_demo=` | Target regions with completeness |
| `GET /api/targets/{id}` | Target with observations, citations |
| `GET /api/sites?q=&category=&include_demo=` | Earth sites with completeness |
| `GET /api/sites/{id}` | Site with observations (value, unit, class, method, dataset, version), citations |
| `GET /api/datasets`, `GET /api/datasets/{id}` | Dataset catalogue / detail (versions, quality, jobs, citations, layers) |
| `GET /api/layers?body=` · `GET /api/layers/{id}/geojson` | Map layers |
| `GET /api/citations` | All citations |
| `GET /api/imports`, `GET /api/imports/{id}`, `GET /api/jobs/{id}` | Import sessions and job logs |
| `GET /api/providers` · `GET /api/providers/nasa_cmr/search?q=` | Provider adapters; NASA CMR metadata search |

## Analysis
`POST /api/analysis/rank`
```json
{"target_id": "jezero-crater", "profile": "landing_site", "weights": {"slope": 30}, "site_ids": ["atacama-yungay"], "include_demo": true}
```
Returns ranked results; each has `status` (`scored`/`insufficient_data`), `score`, `coverage`, per-criterion results,
`data_classes`, `is_demo`, `assessment_id` and `input_hash`. `GET /api/assessments/{id}` returns a stored assessment.

## Exports
| Path | Output |
|---|---|
| `GET /api/export/candidates.csv?target_id=&profile=|weights=&include_demo=` | Ranked candidate list |
| `GET /api/export/comparison.csv?target_id=&site_ids=a,b,c` | Long-format criterion comparison |
| `GET /api/export/report.pdf?target_id=&site_ids=` | Scientific comparison report |
| `GET /api/exports` | Export history |

## Data Center 🔒
| Method & path | Description |
|---|---|
| `POST /api/admin/check` | Verify token |
| `POST /api/imports` (multipart `file`, optional `kind`) | Upload + detect + inspect + propose mapping |
| `POST /api/imports/{id}/propose?kind=` | Re-propose mapping for another kind |
| `PUT /api/imports/{id}/mapping` `{kind, mapping, metadata}` | Validate (dry run) → status `validated`/`invalid` + report |
| `POST /api/imports/{id}/process` | Start processing job |
| `PATCH /api/datasets/{id}` | Edit metadata |
| `POST /api/datasets/{id}/activate?active=true|false` | Activate / deactivate |
| `POST /api/datasets/{id}/versions/{vid}/current` | Switch current version |
| `DELETE /api/datasets/{id}` | Delete (refused if the dataset created site/target records) |

### Example: scripted import
```bash
TOKEN=...; BASE=http://127.0.0.1:8000
SID=$(curl -s -H "X-Admin-Token: $TOKEN" -F file=@templates/observations_long_template.csv -F kind=observations_long $BASE/api/imports | jq -r .id)
curl -s -X PUT -H "X-Admin-Token: $TOKEN" -H 'Content-Type: application/json' $BASE/api/imports/$SID/mapping -d '{
  "kind":"observations_long",
  "mapping":{"fields":{"subject":"subject_id","variable":"variable","value":"value","unit":"unit","method":"method"},
             "options":{"subject_type":"earth_site","match_by":"id"}},
  "metadata":{"name":"My values","data_class":"verified","publisher":"NASA LP DAAC","source_url":"https://lpdaac.usgs.gov/"}}' | jq .status
curl -s -X POST -H "X-Admin-Token: $TOKEN" $BASE/api/imports/$SID/process | jq .id
```
