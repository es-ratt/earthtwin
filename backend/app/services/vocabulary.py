"""Scientific vocabulary: variables, similarity criteria, controlled terms and
mission weighting profiles.

This module is the single source of truth. On startup it is synchronised into
the `variable` and `similarity_criterion` tables so the API, the importers and
the methodology page all describe the same definitions. Adding a genuinely new
measurement means adding a Variable here (and, if it should affect ranking, a
Criterion); no frontend component needs editing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

LITHOLOGY_TERMS = [
    "basalt", "anorthosite", "regolith_fine", "impact_breccia", "impact_melt", "tephra",
    "sedimentary_clastic", "evaporite", "clay_minerals", "sulfates", "carbonate", "iron_oxides",
    "granitic", "gravel", "sand_dunes", "glacial_till", "ice", "permafrost",
]

SITE_CATEGORIES = {
    "arid": "Arid and desert environments",
    "volcanic": "Volcanic landscapes",
    "polar": "Polar and glacial environments",
    "impact": "Impact craters",
    "cave": "Caves and subsurface environments",
    "highland": "Highlands and rugged terrain",
    "hydrothermal": "Hydrothermal and acidic environments",
}

ACCESS_LEVELS = {"high": 1.0, "medium": 0.6, "low": 0.3}


@dataclass(frozen=True)
class Variable:
    key: str
    name: str
    family: str
    value_type: str          # numeric | categorical_set | boolean | ordinal
    canonical_unit: str | None
    description: str
    allowed_values: list[str] = field(default_factory=list)
    # canonical unit vocabulary for units.normalize (K_diff = temperature difference)
    unit_kind: str | None = None
    aliases: list[str] = field(default_factory=list)


VARIABLES: list[Variable] = [
    Variable("mean_elevation_m", "Mean elevation", "terrain", "numeric", "m",
             "Mean elevation within the analysis window, relative to the body's reference surface "
             "(geoid/ellipsoid on Earth, reference sphere on the Moon and Mars). Informational only: "
             "absolute elevation is not comparable between bodies and is not used in scoring.",
             unit_kind="m", aliases=["elevation", "elev", "mean_elevation", "altitude", "height"]),
    Variable("local_relief_m", "Local relief", "terrain", "numeric", "m",
             "Robust elevation range within the analysis window (95th minus 5th percentile).",
             unit_kind="m", aliases=["relief", "local_relief", "elevation_range", "relief_m"]),
    Variable("mean_slope_deg", "Mean slope", "terrain", "numeric", "deg",
             "Mean terrain slope within the analysis window. Depends on DEM resolution; record it.",
             unit_kind="deg", aliases=["slope", "mean_slope", "avg_slope", "slope_mean"]),
    Variable("slope_std_deg", "Slope variability (roughness proxy)", "terrain", "numeric", "deg",
             "Standard deviation of slope within the analysis window; a simple ruggedness proxy.",
             unit_kind="deg", aliases=["slope_std", "roughness", "slope_sd", "ruggedness"]),
    Variable("lithology", "Dominant surface lithology", "geology", "categorical_set", None,
             "Set of dominant surface materials from the controlled EarthTwin lithology vocabulary.",
             allowed_values=LITHOLOGY_TERMS, aliases=["lithology", "geology", "rock_type", "surface_material", "materials"]),
    Variable("impact_structure", "Impact structure present", "geology", "boolean", None,
             "Whether the analysis window contains a confirmed impact structure.",
             aliases=["impact", "impact_crater", "crater", "impact_structure"]),
    Variable("lava_tube", "Lava tubes / volcanic caves present", "geology", "boolean", None,
             "Whether accessible lava tubes or volcanic caves are documented in the window.",
             aliases=["lava_tube", "lava_tubes", "cave", "caves", "skylight"]),
    Variable("mean_surface_temp_k", "Mean surface temperature", "environment", "numeric", "K",
             "Mean annual surface (skin) temperature. For Earth sites, land-surface temperature "
             "products such as MODIS LST; for the Moon, Diviner; for Mars, THEMIS/MCS-derived values.",
             unit_kind="K", aliases=["temperature", "temp", "mean_temp", "lst", "surface_temperature", "mean_temperature"]),
    Variable("surface_temp_range_k", "Surface temperature range", "environment", "numeric", "K",
             "Typical diurnal surface temperature amplitude (max minus min). A temperature difference: "
             "°C and K ranges are numerically equal.",
             unit_kind="K_diff", aliases=["temp_range", "temperature_range", "diurnal_range", "thermal_range"]),
    Variable("annual_precip_mm", "Annual precipitation", "environment", "numeric", "mm/yr",
             "Mean annual liquid-water-equivalent precipitation. Zero for airless bodies and effectively "
             "zero for present-day Mars.",
             unit_kind="mm/yr", aliases=["precipitation", "precip", "rainfall", "annual_precipitation", "annual_precip", "precip_mm"]),
    Variable("vegetation_fraction", "Vegetation cover fraction", "environment", "numeric", "fraction",
             "Fraction of the window covered by vegetation (0-1). NDVI is not a cover fraction and must "
             "be converted with a documented method before import.",
             unit_kind="fraction", aliases=["vegetation", "veg_cover", "vegetation_cover", "fcover"]),
    Variable("ground_ice", "Ground ice present", "resources", "boolean", None,
             "Whether ground ice / ice-cemented regolith / permafrost or (for targets) indicated "
             "subsurface ice is documented in the window.",
             aliases=["ground_ice", "ice", "permafrost", "subsurface_ice", "water_ice"]),
    Variable("accessibility", "Field accessibility", "operational", "ordinal", None,
             "Practical access for field campaigns (high / medium / low). Earth-only attribute.",
             allowed_values=list(ACCESS_LEVELS), aliases=["access", "accessibility"]),
    Variable("analog_heritage", "Documented analog-research heritage", "operational", "boolean", None,
             "Whether the site has documented prior use as a planetary analog. Earth-only attribute.",
             aliases=["heritage", "analog_heritage", "prior_analog_use"]),
]
VARIABLE_BY_KEY = {v.key: v for v in VARIABLES}


@dataclass(frozen=True)
class Criterion:
    key: str
    name: str
    family: str
    variable_key: str
    method: str
    scale: float | None
    applies_to: list[str]
    description: str
    rationale: str


CRITERIA: list[Criterion] = [
    Criterion("relief", "Local relief", "terrain", "local_relief_m", "log_ratio", 0.35, ["moon", "mars"],
              "Similarity of local relief compared on a log scale: s = exp(-½·(log10(a/b)/0.35)²).",
              "Relief spans orders of magnitude; a factor of ~2.2 difference halves similarity."),
    Criterion("slope", "Mean slope", "terrain", "mean_slope_deg", "gaussian", 5.0, ["moon", "mars"],
              "s = exp(-½·(Δslope/5°)²).",
              "Slope governs landing safety and rover trafficability; 5° differences are operationally meaningful."),
    Criterion("roughness", "Slope variability", "terrain", "slope_std_deg", "gaussian", 4.0, ["moon", "mars"],
              "s = exp(-½·(Δσslope/4°)²).", "Proxy for terrain ruggedness at the DEM resolution used."),
    Criterion("lithology", "Surface lithology", "geology", "lithology", "jaccard", None, ["moon", "mars"],
              "Jaccard index |A∩B| / |A∪B| of controlled lithology terms.",
              "Categorical geology cannot be averaged numerically; set overlap is transparent."),
    Criterion("impact", "Impact structure", "geology", "impact_structure", "boolean", None, ["moon", "mars"],
              "1 if both agree, 0 otherwise.", "Impact morphology and shocked materials are key lunar/Martian analog features."),
    Criterion("lava_tube", "Lava tubes / caves", "geology", "lava_tube", "boolean", None, ["moon", "mars"],
              "1 if both agree, 0 otherwise.", "Lava tubes are candidate shelter/habitat locations."),
    Criterion("temperature", "Mean surface temperature", "environment", "mean_surface_temp_k", "gaussian", 35.0, ["moon", "mars"],
              "s = exp(-½·(ΔT/35 K)²).",
              "No Earth site reaches lunar cold-trap temperatures; this criterion makes that gap visible."),
    Criterion("thermal_range", "Thermal range", "environment", "surface_temp_range_k", "log_ratio", 0.3, ["moon", "mars"],
              "s = exp(-½·(log10(a/b)/0.3)²).", "Thermal cycling stresses equipment and materials."),
    Criterion("aridity", "Aridity (precipitation)", "environment", "annual_precip_mm", "log1p_gaussian", 0.6, ["moon", "mars"],
              "s = exp(-½·((log10(1+a) - log10(1+b))/0.6)²).",
              "Precipitation is compared in orders of magnitude; hyper-arid sites score highest."),
    Criterion("vegetation", "Absence of vegetation", "environment", "vegetation_fraction", "gaussian", 0.15, ["moon", "mars"],
              "s = exp(-½·(Δcover/0.15)²).", "Vegetation is absent on the Moon and Mars and changes surface properties."),
    Criterion("ground_ice", "Ground ice", "resources", "ground_ice", "boolean", None, ["moon", "mars"],
              "1 if both agree, 0 otherwise.", "Volatile access is central to permanent-base ISRU studies."),
    Criterion("accessibility", "Field accessibility", "operational", "accessibility", "earth_attribute", None, ["moon", "mars"],
              "Earth-only suitability: high = 1, medium = 0.6, low = 0.3. NOT a similarity measure.",
              "Optional operational factor; weight 0 by default so it never inflates similarity silently."),
    Criterion("heritage", "Analog-research heritage", "operational", "analog_heritage", "earth_attribute", None, ["moon", "mars"],
              "Earth-only suitability: documented prior analog use = 1, none = 0. NOT a similarity measure.",
              "Optional operational factor; weight 0 by default."),
]
CRITERION_BY_KEY = {c.key: c for c in CRITERIA}

PROFILES: dict[str, dict] = {
    "general": {
        "name": "General analog survey",
        "description": "Balanced comparison across terrain, geology and environment.",
        "weights": {"relief": 8, "slope": 10, "roughness": 6, "lithology": 16, "impact": 6, "lava_tube": 4,
                    "temperature": 12, "thermal_range": 6, "aridity": 12, "vegetation": 10, "ground_ice": 10,
                    "accessibility": 0, "heritage": 0},
    },
    "permanent_base": {
        "name": "Permanent base (ice & ISRU)",
        "description": "Prioritises ground ice, cold conditions and shelter-relevant geology.",
        "weights": {"relief": 4, "slope": 10, "roughness": 4, "lithology": 10, "impact": 4, "lava_tube": 8,
                    "temperature": 16, "thermal_range": 6, "aridity": 10, "vegetation": 6, "ground_ice": 22,
                    "accessibility": 0, "heritage": 0},
    },
    "landing_site": {
        "name": "Landing site",
        "description": "Prioritises low, uniform slopes and limited relief.",
        "weights": {"relief": 18, "slope": 26, "roughness": 20, "lithology": 10, "impact": 2, "lava_tube": 0,
                    "temperature": 4, "thermal_range": 2, "aridity": 6, "vegetation": 12, "ground_ice": 0,
                    "accessibility": 0, "heritage": 0},
    },
    "rover_testing": {
        "name": "Rover & mobility testing",
        "description": "Prioritises realistic slopes, roughness and loose surface materials.",
        "weights": {"relief": 14, "slope": 20, "roughness": 20, "lithology": 18, "impact": 4, "lava_tube": 2,
                    "temperature": 4, "thermal_range": 2, "aridity": 6, "vegetation": 10, "ground_ice": 0,
                    "accessibility": 0, "heritage": 0},
    },
    "geology_research": {
        "name": "Geology & habitat-materials research",
        "description": "Prioritises lithology, impact and volcanic features.",
        "weights": {"relief": 4, "slope": 4, "roughness": 4, "lithology": 30, "impact": 14, "lava_tube": 14,
                    "temperature": 8, "thermal_range": 4, "aridity": 8, "vegetation": 4, "ground_ice": 6,
                    "accessibility": 0, "heritage": 0},
    },
}
DEFAULT_PROFILE = "general"


def as_dicts():
    return {
        "variables": [asdict(v) for v in VARIABLES],
        "criteria": [asdict(c) for c in CRITERIA],
        "profiles": PROFILES,
        "lithology_terms": LITHOLOGY_TERMS,
        "site_categories": SITE_CATEGORIES,
        "access_levels": ACCESS_LEVELS,
    }


def sync_to_db(conn) -> None:
    import json

    for v in VARIABLES:
        conn.execute(
            """INSERT INTO variable(key, name, family, value_type, canonical_unit, description, allowed_values)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET name=excluded.name, family=excluded.family,
                 value_type=excluded.value_type, canonical_unit=excluded.canonical_unit,
                 description=excluded.description, allowed_values=excluded.allowed_values""",
            (v.key, v.name, v.family, v.value_type, v.canonical_unit, v.description, json.dumps(v.allowed_values)),
        )
    for c in CRITERIA:
        conn.execute(
            """INSERT INTO similarity_criterion(key, name, family, variable_key, method, scale, applies_to, description, rationale)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET name=excluded.name, family=excluded.family, variable_key=excluded.variable_key,
                 method=excluded.method, scale=excluded.scale, applies_to=excluded.applies_to,
                 description=excluded.description, rationale=excluded.rationale""",
            (c.key, c.name, c.family, c.variable_key, c.method, c.scale, json.dumps(c.applies_to), c.description, c.rationale),
        )
