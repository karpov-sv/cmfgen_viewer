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
