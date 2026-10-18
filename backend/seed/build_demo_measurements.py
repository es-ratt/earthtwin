"""Generates demo_measurements.json — ILLUSTRATIVE values used to exercise the
application before verified datasets are imported.

DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT.

Values are rough, order-of-magnitude placeholders chosen by the team so that the
scoring, charts and reports can be demonstrated. They are not measurements and
must be replaced by importing verified datasets (or rasters processed by the
EarthTwin pipeline) through the Data Center. Where the team had no basis for
even a placeholder, the value is omitted so the app shows the gap.

Run:  python backend/seed/build_demo_measurements.py
"""
import json
from pathlib import Path

COLS = ["local_relief_m", "mean_slope_deg", "slope_std_deg", "lithology", "impact_structure", "lava_tube",
        "mean_surface_temp_k", "surface_temp_range_k", "annual_precip_mm", "vegetation_fraction", "ground_ice",
        "accessibility", "analog_heritage"]
UNITS = {"local_relief_m": "m", "mean_slope_deg": "deg", "slope_std_deg": "deg", "mean_surface_temp_k": "K",
         "surface_temp_range_k": "K", "annual_precip_mm": "mm/yr", "vegetation_fraction": "fraction"}
N = None  # no placeholder — left missing on purpose

SITES = {
    "mcmurdo-dry-valleys":       [900, 12, 8, "granitic;sedimentary_clastic;gravel;permafrost;ice", False, False, 253, 25, 50, 0.0, True, "low", True],
    "haughton-impact-structure": [200, 5, 4, "impact_breccia;carbonate;gravel;permafrost", True, False, 257, 15, 150, 0.03, True, "low", True],
    "bockfjorden-svalbard":      [600, 14, 9, "basalt;glacial_till;carbonate;permafrost", False, False, 265, 10, 300, 0.1, True, "low", True],
    "icelandic-highlands":       [300, 6, 5, "basalt;tephra;glacial_till", False, False, 271, 10, 450, 0.05, False, "medium", True],
    "icelandic-lava-tubes":      [60, 3, 2, "basalt", False, True, 277, 8, 1200, 0.4, N, "high", N],
    "mauna-kea":                 [700, 10, 6, "basalt;tephra;regolith_fine", False, False, 278, 20, 300, 0.02, False, "medium", True],
    "craters-of-the-moon":       [150, 5, 5, "basalt;tephra", False, True, 280, 25, 380, 0.1, False, "high", True],
    "lava-beds":                 [120, 4, 3, "basalt", False, True, 283, 20, 380, 0.3, True, "high", True],
    "atacama-yungay":            [250, 4, 3, "evaporite;sulfates;sedimentary_clastic;gravel;iron_oxides", False, False, 292, 30, 2, 0.0, False, "medium", True],
    "mdrs-utah":                 [200, 6, 6, "sedimentary_clastic;clay_minerals;evaporite;sand_dunes", False, False, 285, 25, 150, 0.05, False, "high", True],
    "death-valley":              [400, 4, 4, "evaporite;sedimentary_clastic;gravel", False, False, 302, 25, 60, 0.03, False, "high", N],
    "meteor-crater":             [170, 6, 7, "impact_breccia;sedimentary_clastic;carbonate", True, False, 288, 25, 250, 0.1, False, "high", True],
    "lonar-crater":              [150, 7, 7, "basalt;impact_breccia;impact_melt", True, False, 300, 15, 750, 0.35, False, "high", N],
    "rio-tinto":                 [200, 8, 6, "sulfates;iron_oxides;clay_minerals", False, False, 292, 18, 600, 0.3, False, "high", True],
    "teide-tenerife":            [500, 9, 7, "basalt;tephra", False, False, 283, 15, 400, 0.05, False, "high", N],
    "namib-gravel-plains":       [80, 2, 1.5, "gravel;sand_dunes;granitic", False, False, 295, 20, 20, 0.02, False, "medium", N],
    "dallol-danakil":            [60, 3, 3, "evaporite;sulfates;iron_oxides", False, False, 308, 12, 150, 0.0, False, "low", N],
}
TARGETS = {
    "lunar-south-pole-shackleton":  [3000, 15, 9, "anorthosite;regolith_fine;impact_breccia;ice", True, False, 110, 150, 0, 0.0, True],
    "mare-tranquillitatis-apollo11": [150, 3, 2.5, "basalt;regolith_fine", True, False, 250, 280, 0, 0.0, False],
    "marius-hills-pit":             [300, 6, 5, "basalt;regolith_fine", N, True, 250, 280, 0, 0.0, False],
    "hadley-rille-apollo15":        [1200, 10, 8, "basalt;regolith_fine;anorthosite", False, True, 245, 270, 0, 0.0, False],
    "jezero-crater":                [600, 5, 5, "basalt;clay_minerals;carbonate;sedimentary_clastic", True, False, 215, 80, 0, 0.0, False],
    "gale-crater":                  [2000, 8, 7, "sedimentary_clastic;clay_minerals;sulfates;basalt", True, False, 220, 85, 0, 0.0, False],
    "arcadia-planitia":             [100, 1.5, 1.5, "basalt;regolith_fine;ice", False, False, 190, 70, 0, 0.0, True],
    "elysium-insight":              [50, 1, 1, "basalt;regolith_fine", False, False, 215, 80, 0, 0.0, False],
    "utopia-zhurong":               [80, 1.5, 1.5, "basalt;regolith_fine;sedimentary_clastic", False, False, 210, 75, 0, 0.0, N],
}


def obs(subject_type, sid, values):
    out = []
    for col, v in zip(COLS, values):
        if v is None:
            continue
        o = {"subject_type": subject_type, "subject_id": sid, "variable": col, "value": v,
             "method": "Illustrative placeholder (DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT)"}
        if col in UNITS:
            o["unit"] = UNITS[col]
        out.append(o)
    return out


bundle = {
    "earthtwin_bundle": "1.0",
    "dataset": {
        "name": "EarthTwin demonstration measurements",
        "publisher": "PLANEX (EarthTwin team)",
        "description": "DEMO DATA — NOT A VERIFIED SCIENTIFIC RESULT. Illustrative placeholder values used to demonstrate "
                       "scoring, charts and reports before verified datasets are imported. Deactivate this dataset in the "
                       "Data Center once verified data are available.",
        "data_class": "demo",
        "version": "2026.1",
        "provenance": "Team-chosen order-of-magnitude placeholders; see backend/seed/build_demo_measurements.py.",
        "license": "CC0 (illustrative values)",
        "body": "mixed",
    },
    "observations": [o for sid, v in SITES.items() for o in obs("earth_site", sid, v)]
                    + [o for sid, v in TARGETS.items() for o in obs("target_region", sid, v)],
}
Path(__file__).with_name("demo_measurements.json").write_text(json.dumps(bundle, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"wrote {len(bundle['observations'])} demo observations")
