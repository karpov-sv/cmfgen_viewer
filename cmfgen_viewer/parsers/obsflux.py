from __future__ import annotations

import re
from pathlib import Path

from .common import build_svg_line_plot, format_number, parse_float_token, parse_numeric_tokens

OBSFLUX_VECTOR_HEADINGS: list[tuple[str, str]] = [
    ("Continuum Frequencies", "continuum_frequencies"),
    ("Observed intensity (Janskys)", "observed_intensity_janskys"),
    ("Luminosity", "luminosity"),
    ("Mechanical Luminosity", "mechanical_luminosity"),
    ("Departure from Rad Equilibrium Correction", "departure_from_rad_equilibrium_correction"),
    ("Total Radiative Luminosity", "total_radiative_luminosity"),
    ("Total Shock Luminosity (Lsun)", "total_shock_luminosity_lsun"),
    ("Luminosity Check (not observed luminosity)", "luminosity_check"),
    ("Normalized luminosity check", "normalized_luminosity_check"),
    ("Consistency check (include dep. from rad. equil.)", "consistency_check_with_correction"),
]

SCALAR_RE = re.compile(r"^\s*([^:]+):\s+(.+)$")
COUNT_RE = re.compile(r"\((\s*\d+)\)")


def _detect_heading(line: str) -> tuple[str, str] | None:
    text = " ".join(line.strip().split())
    for heading, key in OBSFLUX_VECTOR_HEADINGS:
        if text.startswith(heading):
            return heading, key
    return None


def parse_obsflux(path: Path) -> dict[str, object]:
    vectors: dict[str, list[float]] = {}
    heading_titles: dict[str, str] = {}
    summary_scalars: list[list[str]] = []
    warnings: list[str] = []
    expected_ncf: int | None = None

    active_key: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue

            heading = _detect_heading(stripped)
            if heading is not None:
                title, key = heading
                active_key = key
                vectors.setdefault(key, [])
                heading_titles[key] = title
                if key == "continuum_frequencies":
                    count_match = COUNT_RE.search(stripped)
                    if count_match:
                        expected_ncf = int(count_match.group(1))
                continue

            numeric_values = parse_numeric_tokens(stripped)
            if active_key and numeric_values:
                vectors[active_key].extend(numeric_values)
                continue
            active_key = None

            scalar_match = SCALAR_RE.match(stripped)
            if scalar_match:
                name = scalar_match.group(1).strip()
                raw_values = scalar_match.group(2).strip()
                tokens = raw_values.split()
                parsed_values = [parse_float_token(token) for token in tokens]
                if parsed_values and parsed_values[0] is not None:
                    numbers = [value for value in parsed_values if value is not None]
                    if len(numbers) == 1:
                        summary_scalars.append([name, format_number(numbers[0])])
                    else:
                        summary_scalars.append([name, ", ".join(format_number(number) for number in numbers)])
                else:
                    summary_scalars.append([name, raw_values])

    if expected_ncf is not None:
        actual_ncf = len(vectors.get("continuum_frequencies", []))
        if actual_ncf != expected_ncf:
            warnings.append(
                f"Continuum frequencies parsed={actual_ncf}, expected={expected_ncf}"
            )

    vectors_table_rows: list[list[str]] = []
    for _, key in OBSFLUX_VECTOR_HEADINGS:
        if key in vectors and vectors[key]:
            vectors_table_rows.append(
                [heading_titles.get(key, key), str(len(vectors[key]))]
            )

    plots: list[dict[str, object]] = []
    freq = vectors.get("continuum_frequencies", [])
    intensity = vectors.get("observed_intensity_janskys", [])
    if freq and intensity:
        size = min(len(freq), len(intensity))
        svg = build_svg_line_plot(freq[:size], intensity[:size], max_points=1400)
        if svg:
            plots.append(
                {
                    "title": "Observed spectrum",
                    "x_label": "Frequency",
                    "y_label": "Intensity (Janskys)",
                    "svg": svg,
                }
            )

    for key, title in [
        ("luminosity", "Luminosity"),
        ("mechanical_luminosity", "Mechanical luminosity"),
        ("normalized_luminosity_check", "Normalized luminosity check"),
    ]:
        values = vectors.get(key, [])
        if len(values) >= 2:
            x_values = list(range(1, len(values) + 1))
            svg = build_svg_line_plot(x_values, values, max_points=800)
            if svg:
                plots.append(
                    {
                        "title": title,
                        "x_label": "Depth index",
                        "y_label": "Value",
                        "svg": svg,
                    }
                )

    summary_rows: list[list[str]] = []
    if expected_ncf is not None:
        summary_rows.append(["Expected NCF", str(expected_ncf)])
    if "continuum_frequencies" in vectors:
        summary_rows.append(["Parsed continuum points", str(len(vectors["continuum_frequencies"]))])
    if "observed_intensity_janskys" in vectors:
        summary_rows.append(["Parsed observed-intensity points", str(len(vectors["observed_intensity_janskys"]))])

    tables: list[dict[str, object]] = [
        {
            "title": "Parsed vectors",
            "columns": ["Vector", "Count"],
            "rows": vectors_table_rows,
        }
    ]
    if summary_scalars:
        tables.append(
            {
                "title": "Summary diagnostics",
                "columns": ["Quantity", "Value"],
                "rows": summary_scalars,
            }
        )

    return {
        "parser": "OBSFLUX",
        "title": "OBSFLUX spectrum and luminosity vectors",
        "summary_table": {
            "title": "OBSFLUX summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }
