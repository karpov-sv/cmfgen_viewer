"""Explicit observed-frame diagnostic windows and exclusion intervals."""

from __future__ import annotations

import math

def parse_fit_regions(windows: str = "", exclusions: str = "") -> dict:
    """Parse one ``[label,] min, max`` interval per nonempty line."""
    result = {}
    for key, text in (("windows", windows), ("exclusions", exclusions)):
        if len(text) > 16000:
            raise ValueError("Diagnostic region text is too long.")
        rows = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            fields = [part.strip() for part in line.split(",")]
            if len(fields) not in (2, 3):
                raise ValueError(f"{key.title()} line {number}: use [label,] min, max.")
            label = fields[0] if len(fields) == 3 else f"{fields[-2]}–{fields[-1]} Å"
            try:
                lower, upper = map(float, fields[-2:])
            except ValueError:
                raise ValueError(f"{key.title()} line {number}: bounds must be numbers.") from None
            if not (math.isfinite(lower) and math.isfinite(upper) and 0 < lower < upper):
                raise ValueError(f"{key.title()} line {number}: require 0 < min < max.")
            if not label or len(label) > 80:
                raise ValueError(f"{key.title()} line {number}: use a label of 1–80 characters.")
            rows.append({"label": label, "min": lower, "max": upper})
        if len(rows) > 64:
            raise ValueError("Use at most 64 intervals per region field.")
        if key == "windows":
            ordered = sorted(rows, key=lambda row: row["min"])
            if any(left["max"] >= right["min"] for left, right in zip(ordered, ordered[1:])):
                raise ValueError("Diagnostic windows must not overlap or share endpoints.")
        result[key] = rows
    return result


def format_fit_regions(regions: dict, key: str) -> str:
    return "\n".join(
        f"{row['label']}, {row['min']:.15g}, {row['max']:.15g}"
        for row in regions.get(key, [])
    )


def fit_region_mask(wavelength, regions: dict):
    """Return the union of windows minus exclusions; empty windows mean all."""
    import numpy as np

    wavelength = np.asarray(wavelength)
    windows = regions.get("windows", [])
    selected = np.zeros(wavelength.shape, dtype=bool) if windows else np.ones(wavelength.shape, dtype=bool)
    for row in windows:
        selected |= (wavelength >= row["min"]) & (wavelength <= row["max"])
    for row in regions.get("exclusions", []):
        selected &= ~((wavelength >= row["min"]) & (wavelength <= row["max"]))
    return selected


def validate_fit_region_samples(wavelength, regions: dict) -> None:
    import numpy as np

    selected = fit_region_mask(wavelength, regions)
    if np.count_nonzero(selected) < 30:
        raise ValueError("Diagnostic selection requires at least 30 usable spectral samples.")
    wavelength = np.asarray(wavelength)
    for row in regions.get("windows", []):
        inside = selected & (wavelength >= row["min"]) & (wavelength <= row["max"])
        if np.count_nonzero(inside) < 2:
            raise ValueError(f"Diagnostic window '{row['label']}' needs at least two unmasked samples.")
