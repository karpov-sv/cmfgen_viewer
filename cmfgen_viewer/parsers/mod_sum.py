from __future__ import annotations

import re
from pathlib import Path

from .common import DIMENSION_RE, format_number, maybe_number, parse_float_token, parse_key_value_pairs

DATE_PREFIXES = {
    "Model Started on": "model_started_on",
    "Model Finalized on": "model_finalized_on",
    "Main program last changed on": "main_program_last_changed_on",
}

SPECIES_ROW_RE = re.compile(
    r"^\s*([A-Za-z0-9]+)\s+([+\-0-9.EeDd]+)\s+([+\-0-9.EeDd]+)\s+([+\-0-9.EeDd]+)\s+([+\-0-9.EeDd]+)\s*$"
)
CLUMPING_MODEL_RE = re.compile(r"^\s*Running clumped model:\s*(.+?)\s*$")
FILLING_FACTOR_RE = re.compile(r"^\s*Filling factor at boundary is:\s*([+\-0-9.EeDd]+)\s*$")
MAX_CORRECTION_RE = re.compile(r"^\s*Maximum correcion \(%\) on last iteration:\s*([+\-0-9.EeDd]+)\s*$")


def _normalize_key(key: str) -> str:
    normalized = re.sub(r"\s*/\s*", "/", key.strip())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def parse_mod_sum(path: Path) -> dict[str, object]:
    metadata: dict[str, str] = {}
    dimensions: dict[str, int] = {}
    scalars: dict[str, object] = {}
    tau_rows: list[dict[str, object]] = []
    warnings: list[str] = []

    species_rows: list[list[str]] = []
    in_species_table = False

    clumping_model: str | None = None
    filling_factor_boundary: float | None = None
    max_correction_pct: float | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.rstrip("\n")
            text = stripped.strip()
            if not text:
                if in_species_table:
                    in_species_table = False
                continue

            matched_date = False
            for prefix, key in DATE_PREFIXES.items():
                marker = f"{prefix}:"
                if text.startswith(marker):
                    metadata[key] = text[len(marker) :].strip()
                    matched_date = True
                    break
            if matched_date:
                continue

            for dimension_name, value in DIMENSION_RE.findall(text):
                try:
                    dimensions[dimension_name] = int(value)
                except ValueError:
                    warnings.append(f"Failed to parse dimension: {dimension_name}[{value}]")

            if "SPECIES" in text and "Mass Fraction" in text:
                in_species_table = True
                continue

            if in_species_table:
                species_match = SPECIES_ROW_RE.match(text)
                if species_match:
                    species = species_match.group(1)
                    parsed_values = [parse_float_token(species_match.group(i)) for i in range(2, 6)]
                    if any(value is None for value in parsed_values):
                        continue
                    row = [
                        species,
                        format_number(parsed_values[0]),
                        format_number(parsed_values[1]),
                        format_number(parsed_values[2]),
                        format_number(parsed_values[3]),
                    ]
                    species_rows.append(row)
                    continue
                in_species_table = False

            clumping_match = CLUMPING_MODEL_RE.match(text)
            if clumping_match:
                clumping_model = clumping_match.group(1).strip()
                continue

            filling_match = FILLING_FACTOR_RE.match(text)
            if filling_match:
                parsed = parse_float_token(filling_match.group(1))
                if parsed is not None:
                    filling_factor_boundary = parsed
                continue

            correction_match = MAX_CORRECTION_RE.match(text)
            if correction_match:
                parsed = parse_float_token(correction_match.group(1))
                if parsed is not None:
                    max_correction_pct = parsed
                continue

            if text.startswith("Tau="):
                kv_pairs = parse_key_value_pairs(text)
                if kv_pairs:
                    tau_row: dict[str, object] = {}
                    for key, raw in kv_pairs:
                        tau_row[_normalize_key(key)] = maybe_number(raw)
                    tau_rows.append(tau_row)
                continue

            if "=" in text:
                for key, raw in parse_key_value_pairs(text):
                    scalars[_normalize_key(key)] = maybe_number(raw)

    summary_rows: list[list[str]] = []
    for key in ["model_started_on", "model_finalized_on", "main_program_last_changed_on"]:
        if key in metadata:
            summary_rows.append([key, metadata[key]])

    dimension_rows = [[key, str(value)] for key, value in sorted(dimensions.items())]

    scalar_rows = [[key, format_number(value)] for key, value in scalars.items()]
    scalar_rows = scalar_rows[:30]

    tau_table_rows: list[list[str]] = []
    tau_columns: list[str] = []
    if tau_rows:
        seen_columns: list[str] = []
        for row in tau_rows:
            for key in row:
                if key not in seen_columns:
                    seen_columns.append(key)
        tau_columns = seen_columns
        for row in tau_rows:
            tau_table_rows.append([format_number(row.get(column, "")) for column in tau_columns])

    clumping_rows: list[list[str]] = []
    if clumping_model is not None:
        clumping_rows.append(["model", clumping_model])
    if filling_factor_boundary is not None:
        clumping_rows.append(["filling_factor_boundary", format_number(filling_factor_boundary)])
    if max_correction_pct is not None:
        clumping_rows.append(["max_correction_percent_last_iteration", format_number(max_correction_pct)])

    tables: list[dict[str, object]] = [
        {
            "title": "Dimensions",
            "columns": ["Name", "Value"],
            "rows": dimension_rows,
        }
    ]
    if scalar_rows:
        tables.append(
            {
                "title": "Key scalars",
                "columns": ["Name", "Value"],
                "rows": scalar_rows,
            }
        )
    if tau_table_rows and tau_columns:
        tables.append(
            {
                "title": "Tau diagnostics",
                "columns": tau_columns,
                "rows": tau_table_rows,
            }
        )
    if species_rows:
        tables.append(
            {
                "title": "Abundance table",
                "columns": ["Species", "Rel. # Fraction", "Mass Fraction", "Z/Z(sun)", "Z(sun)"],
                "rows": species_rows,
            }
        )
    if clumping_rows:
        tables.append(
            {
                "title": "Clumping",
                "columns": ["Field", "Value"],
                "rows": clumping_rows,
            }
        )

    return {
        "parser": "MOD_SUM",
        "title": "MOD_SUM model summary",
        "summary_table": {
            "title": "Run metadata",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": [],
        "warnings": warnings,
    }
