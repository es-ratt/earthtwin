-- EarthTwin standard internal data model, v1.
-- See docs/DATA_DICTIONARY.md for field-level documentation.
-- Conventions:
--   * ids are text (slugs for curated records, uuid4 hex for generated ones)
--   * JSON columns are TEXT holding JSON
--   * timestamps are ISO-8601 UTC strings
--   * data_class is one of: verified | derived | demo | reference
--       verified  = value taken from an identified dataset supplied by the team
--       derived   = value calculated by the EarthTwin pipeline from documented inputs
--       demo      = illustrative value used to exercise the application
--       reference = catalogue/metadata entry only (no values used in scoring)

CREATE TABLE target_world (
    id                    TEXT PRIMARY KEY,           -- earth | moon | mars
    name                  TEXT NOT NULL,
    mean_radius_km        REAL NOT NULL,
    default_crs           TEXT NOT NULL,              -- e.g. IAU_2015:30100
    longitude_convention  TEXT NOT NULL,              -- stored values are always east-positive, -180..180
    gravity_m_s2          REAL,
    description           TEXT
);

CREATE TABLE dataset (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    identifier          TEXT,                          -- DOI, short name, product id
    publisher           TEXT,
    source_url          TEXT,
    file_format         TEXT,                          -- csv | json | geojson | geotiff | bundle | none
    data_type           TEXT NOT NULL,                 -- site_records | target_records | observations | raster | map_layer | reference
    body                TEXT,                          -- earth | moon | mars | mixed
    crs                 TEXT,
    spatial_coverage    TEXT,                          -- JSON {"bbox":[minlon,minlat,maxlon,maxlat]} or free text
    temporal_coverage   TEXT,
    units               TEXT DEFAULT '{}',             -- JSON {variable_key: unit}
    spatial_resolution  TEXT,
    license             TEXT,
    provenance          TEXT,
    description         TEXT,
    data_class          TEXT NOT NULL,
    status              TEXT NOT NULL,                 -- planned | awaiting_mapping | processing | ready | failed
    active              INTEGER NOT NULL DEFAULT 0,
    current_version_id  TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE dataset_version (
    id                  TEXT PRIMARY KEY,
    dataset_id          TEXT NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    version             TEXT NOT NULL,
    original_filename   TEXT,
    stored_path         TEXT,
    sha256              TEXT,
    size_bytes          INTEGER,
    field_mapping       TEXT DEFAULT '{}',
    processing_history  TEXT DEFAULT '[]',              -- JSON list of {at, step, detail}
    created_at          TEXT NOT NULL
);

CREATE TABLE target_region (
    id                  TEXT PRIMARY KEY,
    world_id            TEXT NOT NULL REFERENCES target_world(id),
    name                TEXT NOT NULL,
    lat                 REAL NOT NULL,                  -- planetocentric latitude, degrees
    lon                 REAL NOT NULL,                  -- east-positive longitude, -180..180
    crs                 TEXT NOT NULL,
    analysis_radius_km  REAL NOT NULL DEFAULT 10,
    region_type         TEXT,
    description         TEXT,
    geologic_context    TEXT,
    mission_relevance   TEXT,
    tags                TEXT DEFAULT '[]',
    extra               TEXT DEFAULT '{}',               -- unmapped imported fields, preserved
    source_dataset_id   TEXT REFERENCES dataset(id) ON DELETE SET NULL,
    data_class          TEXT NOT NULL DEFAULT 'demo',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE earth_site (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    country             TEXT,
    region              TEXT,
    lat                 REAL NOT NULL,                  -- WGS 84 (EPSG:4326)
    lon                 REAL NOT NULL,
    crs                 TEXT NOT NULL DEFAULT 'EPSG:4326',
    analysis_radius_km  REAL NOT NULL DEFAULT 10,
    categories          TEXT NOT NULL DEFAULT '[]',
    terrain_type        TEXT,
    description         TEXT,
    geologic_context    TEXT,
    analog_heritage     TEXT,
    applications        TEXT DEFAULT '[]',
    limitations         TEXT DEFAULT '[]',
    future_work         TEXT DEFAULT '[]',
    extra               TEXT DEFAULT '{}',
    source_dataset_id   TEXT REFERENCES dataset(id) ON DELETE SET NULL,
    data_class          TEXT NOT NULL DEFAULT 'demo',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Measurable characteristics. Terrain/geological/environmental features are
-- observations of variables in the corresponding family (see views below).
CREATE TABLE variable (
    key             TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    family          TEXT NOT NULL,                      -- terrain | geology | environment | resources | operational
    value_type      TEXT NOT NULL,                      -- numeric | categorical_set | boolean | ordinal
    canonical_unit  TEXT,
    description     TEXT,
    allowed_values  TEXT DEFAULT '[]'
);

CREATE TABLE observation (
    id                  TEXT PRIMARY KEY,
    dataset_version_id  TEXT NOT NULL REFERENCES dataset_version(id) ON DELETE CASCADE,
    subject_type        TEXT NOT NULL CHECK (subject_type IN ('earth_site', 'target_region')),
    subject_id          TEXT NOT NULL,
    variable_key        TEXT NOT NULL REFERENCES variable(key),
    value_num           REAL,
    value_text          TEXT,                            -- JSON for categorical sets / booleans / ordinals
    unit                TEXT,                            -- canonical unit after normalisation
    original_value      TEXT,
    original_unit       TEXT,
    data_class          TEXT NOT NULL,
    method              TEXT,
    uncertainty         REAL,
    spatial_support     TEXT,                            -- e.g. "10 km radius window, 30 m/px"
    observed_start      TEXT,
    observed_end        TEXT,
    notes               TEXT,
    created_at          TEXT NOT NULL
);
CREATE INDEX idx_obs_subject ON observation(subject_type, subject_id);
CREATE INDEX idx_obs_version ON observation(dataset_version_id);

CREATE VIEW terrain_feature AS
    SELECT o.* FROM observation o JOIN variable v ON v.key = o.variable_key WHERE v.family = 'terrain';
CREATE VIEW geological_feature AS
    SELECT o.* FROM observation o JOIN variable v ON v.key = o.variable_key WHERE v.family = 'geology';
CREATE VIEW environmental_feature AS
    SELECT o.* FROM observation o JOIN variable v ON v.key = o.variable_key WHERE v.family IN ('environment', 'resources');

CREATE TABLE similarity_criterion (
    key             TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    family          TEXT NOT NULL,
    variable_key    TEXT NOT NULL REFERENCES variable(key),
    method          TEXT NOT NULL,                      -- gaussian | log_ratio | log1p_gaussian | jaccard | boolean | earth_attribute
    scale           REAL,
    applies_to      TEXT NOT NULL DEFAULT '["moon","mars"]',
    description     TEXT,
    rationale       TEXT,
    active          INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE similarity_assessment (
    id                  TEXT PRIMARY KEY,
    target_region_id    TEXT NOT NULL REFERENCES target_region(id) ON DELETE CASCADE,
    earth_site_id       TEXT NOT NULL REFERENCES earth_site(id) ON DELETE CASCADE,
    weights             TEXT NOT NULL,
    profile             TEXT,
    status              TEXT NOT NULL,                  -- scored | insufficient_data
    score               REAL,
    coverage            REAL NOT NULL,
    n_criteria_used     INTEGER NOT NULL,
    criteria_results    TEXT NOT NULL,
    data_classes        TEXT NOT NULL,
    input_hash          TEXT NOT NULL,
    engine_version      TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    UNIQUE (target_region_id, earth_site_id, input_hash)
);

CREATE TABLE data_quality_assessment (
    id                  TEXT PRIMARY KEY,
    dataset_version_id  TEXT REFERENCES dataset_version(id) ON DELETE CASCADE,
    import_id           TEXT,
    n_records           INTEGER,
    n_valid             INTEGER,
    n_rejected          INTEGER,
    completeness        REAL,
    issues              TEXT DEFAULT '[]',
    summary             TEXT,
    created_at          TEXT NOT NULL
);

CREATE TABLE citation (
    id              TEXT PRIMARY KEY,
    dataset_id      TEXT REFERENCES dataset(id) ON DELETE CASCADE,
    subject_type    TEXT,
    subject_id      TEXT,
    text            TEXT NOT NULL,
    url             TEXT,
    doi             TEXT,
    kind            TEXT NOT NULL DEFAULT 'dataset',    -- dataset | reference | context
    verification    TEXT NOT NULL DEFAULT 'unverified', -- team_verified | unverified
    created_at      TEXT NOT NULL
);

CREATE TABLE import_session (
    id                  TEXT PRIMARY KEY,
    original_filename   TEXT NOT NULL,
    stored_path         TEXT NOT NULL,
    size_bytes          INTEGER NOT NULL,
    sha256              TEXT NOT NULL,
    detected_format     TEXT NOT NULL,
    import_kind         TEXT,
    structure           TEXT DEFAULT '{}',
    proposed_mapping    TEXT DEFAULT '{}',
    confirmed_mapping   TEXT,
    metadata            TEXT DEFAULT '{}',
    validation          TEXT,
    status              TEXT NOT NULL,                  -- inspected | validated | invalid | processing | completed | failed
    dataset_id          TEXT,
    job_id              TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE analysis_job (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,                      -- import | raster_features | rescore
    status          TEXT NOT NULL,                      -- queued | running | succeeded | failed
    dataset_id      TEXT,
    import_id       TEXT,
    log             TEXT DEFAULT '[]',
    error           TEXT,
    result          TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);

CREATE TABLE map_layer (
    id              TEXT PRIMARY KEY,
    dataset_id      TEXT REFERENCES dataset(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    body            TEXT NOT NULL,
    kind            TEXT NOT NULL,                      -- vector | tiles
    geojson_path    TEXT,
    tile_url        TEXT,
    legend          TEXT DEFAULT '{}',
    attribution     TEXT,
    feature_count   INTEGER,
    created_at      TEXT NOT NULL
);

CREATE TABLE exported_report (
    id                  TEXT PRIMARY KEY,
    kind                TEXT NOT NULL,                  -- candidates_csv | comparison_csv | report_pdf
    target_region_id    TEXT,
    params              TEXT,
    assessment_ids      TEXT,
    file_path           TEXT,
    created_at          TEXT NOT NULL
);

CREATE TABLE app_state (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);
INSERT INTO app_state(key, value) VALUES ('revision', '1');
