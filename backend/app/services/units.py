"""Unit normalisation.

Units are never guessed silently. `normalize()` only converts units it knows
exactly; anything else raises `UnitError` so the import is stopped and the user
is asked to confirm the unit in the field-mapping step.
"""
from __future__ import annotations

import math
import re


class UnitError(ValueError):
    pass


# dimension -> canonical unit -> {alias: (factor, offset)}; value_canonical = value * factor + offset
_DIMENSIONS: dict[str, dict] = {
    "length": {
        "canonical": "m",
        "aliases": {
            "m": (1.0, 0.0), "meter": (1.0, 0.0), "meters": (1.0, 0.0), "metre": (1.0, 0.0), "metres": (1.0, 0.0),
            "km": (1000.0, 0.0), "kilometer": (1000.0, 0.0), "kilometers": (1000.0, 0.0), "kilometre": (1000.0, 0.0),
            "ft": (0.3048, 0.0), "feet": (0.3048, 0.0), "foot": (0.3048, 0.0),
        },
    },
    "angle": {
        "canonical": "deg",
        "aliases": {
            "deg": (1.0, 0.0), "degree": (1.0, 0.0), "degrees": (1.0, 0.0), "°": (1.0, 0.0),
            "rad": (180.0 / math.pi, 0.0), "radian": (180.0 / math.pi, 0.0), "radians": (180.0 / math.pi, 0.0),
            # percent grade is non-linear: handled specially in normalize()
            "percent_grade": (None, None),
        },
    },
    "temperature": {
        "canonical": "K",
        "aliases": {
            "k": (1.0, 0.0), "kelvin": (1.0, 0.0),
            "c": (1.0, 273.15), "°c": (1.0, 273.15), "degc": (1.0, 273.15), "celsius": (1.0, 273.15), "deg_c": (1.0, 273.15),
            "f": (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0), "°f": (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0),
            "degf": (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0), "fahrenheit": (5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0),
        },
    },
    # A temperature *difference* has no offset: 10 °C of range == 10 K of range.
    "temperature_difference": {
        "canonical": "K",
        "aliases": {
            "k": (1.0, 0.0), "kelvin": (1.0, 0.0),
            "c": (1.0, 0.0), "°c": (1.0, 0.0), "degc": (1.0, 0.0), "celsius": (1.0, 0.0), "deg_c": (1.0, 0.0),
            "f": (5.0 / 9.0, 0.0), "°f": (5.0 / 9.0, 0.0), "degf": (5.0 / 9.0, 0.0), "fahrenheit": (5.0 / 9.0, 0.0),
        },
    },
    "precipitation_rate": {
        "canonical": "mm/yr",
        "aliases": {
            "mm/yr": (1.0, 0.0), "mm/year": (1.0, 0.0), "mm yr-1": (1.0, 0.0), "mm a-1": (1.0, 0.0), "mm/a": (1.0, 0.0),
            "cm/yr": (10.0, 0.0), "cm/year": (10.0, 0.0),
            "m/yr": (1000.0, 0.0), "m/year": (1000.0, 0.0),
            "in/yr": (25.4, 0.0), "in/year": (25.4, 0.0), "inches/year": (25.4, 0.0),
        },
    },
    "fraction": {
        "canonical": "fraction",
        "aliases": {
            "fraction": (1.0, 0.0), "ratio": (1.0, 0.0), "0-1": (1.0, 0.0), "1": (1.0, 0.0),
            "%": (0.01, 0.0), "percent": (0.01, 0.0), "pct": (0.01, 0.0),
        },
    },
}

DIMENSION_OF_CANONICAL = {
    "m": "length", "deg": "angle", "K": "temperature", "K_diff": "temperature_difference",
    "mm/yr": "precipitation_rate", "fraction": "fraction",
}


def _clean(unit: str) -> str:
    u = unit.strip().lower()
    u = re.sub(r"\s+", " ", u)
    return u.replace("deg c", "degc").replace("deg f", "degf").replace("º", "°")


def accepted_units(canonical: str) -> list[str]:
    dim = DIMENSION_OF_CANONICAL.get(canonical)
    if not dim:
        return []
    return sorted(_DIMENSIONS[dim]["aliases"].keys())


def normalize(value: float, unit: str | None, canonical: str) -> tuple[float, str]:
    """Convert `value` in `unit` to the variable's canonical unit.

    `canonical` uses the variable registry vocabulary ("m", "deg", "K", "K_diff",
    "mm/yr", "fraction"). Returns (value, canonical_display_unit).
    """
    dim = DIMENSION_OF_CANONICAL.get(canonical)
    if dim is None:
        raise UnitError(f"No unit conversion defined for canonical unit '{canonical}'")
    if unit is None or str(unit).strip() == "":
        raise UnitError(f"Unit is required (expected one of: {', '.join(accepted_units(canonical))})")
    u = _clean(str(unit))
    aliases = _DIMENSIONS[dim]["aliases"]
    if u not in aliases:
        raise UnitError(
            f"Unit '{unit}' is not recognised for this variable "
            f"(accepted: {', '.join(accepted_units(canonical))})"
        )
    display = _DIMENSIONS[dim]["canonical"]
    if dim == "angle" and u == "percent_grade":
        return math.degrees(math.atan(value / 100.0)), display
    factor, offset = aliases[u]
    return value * factor + offset, display


def unit_hint_from_header(header: str) -> str | None:
    """Suggest a unit from a column header such as 'slope_deg' or 'Temp (°C)'.

    The suggestion is always shown to the user for confirmation; it is never
    applied without review.
    """
    h = header.strip().lower()
    m = re.search(r"\(([^)]+)\)|\[([^\]]+)\]", h)
    if m:
        return (m.group(1) or m.group(2)).strip()
    suffixes = [
        ("_mm_per_yr", "mm/yr"), ("_mm_yr", "mm/yr"), ("_mmyr", "mm/yr"), ("_cm_yr", "cm/yr"),
        ("_deg_c", "°C"), ("_degc", "°C"), ("_celsius", "°C"), ("_c", "°C"), ("_f", "°F"),
        ("_kelvin", "K"), ("_k", "K"), ("_deg", "deg"), ("_degrees", "deg"), ("_rad", "rad"),
        ("_km", "km"), ("_m", "m"), ("_ft", "ft"), ("_pct", "%"), ("_percent", "%"), ("_fraction", "fraction"),
    ]
    for suf, unit in suffixes:
        if h.endswith(suf):
            return unit
    return None
