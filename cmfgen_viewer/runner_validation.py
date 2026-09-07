"""Strict structural checks shared by preflight and output acceptance."""

import math
import re

from .control_files import control_occurrences
from .parsers.common import parse_float_token


def validate_rvtj_core(path, model_spec, *, finite_all=False):
    """Validate core vectors, not convergence or uncomputed diagnostics."""
    text = path.read_text()
    match = re.search(r"^\s*ND:\s*(\d+)", text, re.M)
    if not match:
        raise ValueError("Missing ND header (only text RVTJ is supported)")
    nd = int(match[1])
    rows = control_occurrences(model_spec.read_text()).get("ND", [])
    if len(rows) != 1 or nd < 1 or nd != int(rows[0]["value"]):
        raise ValueError("RVTJ depth count differs from MODEL_SPEC")
    if finite_all and any(re.fullmatch(r"[+-]?(?:nan|inf(?:inity)?|\*{3,})", token, re.I) for token in text.split()):
        raise ValueError("Nonfinite/overflow values in RVTJ")
    for heading in ("Radius", "Velocity", "Temperature", "Electron density"):
        matches = list(re.finditer(r"^\s*" + heading + r"(?:[ \t][^\n]*)?\n", text, re.M | re.I))
        if len(matches) != 1:
            raise ValueError(f"Missing or duplicate RVTJ {heading} vector")
        values = []
        for token in text[matches[0].end():].split():
            number = parse_float_token(token)
            if number is None:
                break
            values.append(number)
        if len(values) != nd or not all(math.isfinite(v) for v in values):
            raise ValueError(f"Incomplete/nonfinite RVTJ {heading} vector")
        if heading != "Velocity" and any(v <= 0 for v in values):
            raise ValueError(f"Nonpositive RVTJ {heading} vector")


def validate_rosseland_table(path):
    """Require the complete finite, nonnegative table written by main_lte."""
    text = path.read_text()
    temperatures = re.search(r"(\d+)\s+!Number of temperatures", text)
    densities = re.search(r"(\d+)\s+!Number of densities", text)
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 8:
            continue
        values = [parse_float_token(token) for token in parts]
        if all(value is not None for value in values):
            rows.append(values)
    if not temperatures or not densities:
        raise ValueError("Missing Rosseland table dimensions")
    expected = int(temperatures[1]) * int(densities[1])
    if len(rows) != expected:
        raise ValueError(f"Rosseland table dimensions require {expected} complete rows, found {len(rows)}")
    if not rows or not all(math.isfinite(value) and value >= 0 for row in rows for value in row):
        raise ValueError("Rosseland table contains invalid values")


def validate_rvsig_structure(path, model_spec):
    """Validate the generated hydro grid needed for an explicit handoff."""
    controls = control_occurrences(model_spec.read_text()).get("ND", [])
    if len(controls) != 1:
        raise ValueError("MODEL_SPEC must contain exactly one [ND]")
    try:
        expected = int(controls[0]["value"])
    except ValueError as exc:
        raise ValueError("MODEL_SPEC [ND] must be an integer") from exc
    if expected < 1:
        raise ValueError("MODEL_SPEC [ND] must be positive")

    text = path.read_text()
    declarations = re.findall(r"^\s*(\d+)\s*!\s*Number of depth points\s*$", text, re.I | re.M)
    if len(declarations) != 1:
        raise ValueError("Missing or duplicate hydro depth-count declaration")
    declared = int(declarations[0])
    if declared != expected:
        raise ValueError(f"Generated hydro depth count {declared} differs from MODEL_SPEC {expected}")

    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 5 or not re.fullmatch(r"[+-]?\d+", parts[-1]):
            continue
        values = [parse_float_token(token) for token in parts[:4]]
        if all(value is not None for value in values):
            rows.append((*values, int(parts[-1])))
    if len(rows) != declared:
        raise ValueError(f"Hydro grid declares {declared} points but contains {len(rows)} rows")
    if [row[-1] for row in rows] != list(range(1, declared + 1)):
        raise ValueError("Hydro grid row indices are incomplete or out of order")
    if not all(math.isfinite(value) for row in rows for value in row[:4]):
        raise ValueError("Hydro grid contains nonfinite values")
    if any(row[0] <= 0 or row[1] < 0 or row[3] <= 0 for row in rows):
        raise ValueError("Hydro grid contains nonpositive radius/optical depth or negative velocity")
