from __future__ import annotations

import math
import re
from typing import Iterable

FLOAT_TOKEN_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
FORTRAN_MISSING_E_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$")
DIMENSION_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]")


def parse_float_token(token: str) -> float | None:
    """Parse numeric token, including Fortran forms like 3.9241-115."""
    value = token.strip().rstrip(",;")
    if not value:
        return None

    value = value.replace("D", "E").replace("d", "e")
    if FLOAT_TOKEN_RE.match(value):
        try:
            return float(value)
        except ValueError:
            return None

    match = FORTRAN_MISSING_E_RE.match(value)
    if match:
        try:
            return float(f"{match.group(1)}E{match.group(2)}")
        except ValueError:
            return None

    return None


def parse_numeric_tokens(line: str) -> list[float]:
    values: list[float] = []
    for token in line.split():
        parsed = parse_float_token(token)
        if parsed is None:
            return []
        values.append(parsed)
    return values


def parse_key_value_pairs(line: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    pattern = r"([A-Za-z0-9*()./%+-][A-Za-z0-9*()./%+\- ]*?)\s*=\s*([^\s]+)"
    for match in re.finditer(pattern, line):
        key = normalize_space(match.group(1))
        pairs.append((key, match.group(2)))
    return pairs


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def maybe_number(value: str) -> int | float | str:
    parsed = parse_float_token(value)
    if parsed is None:
        return value.strip()
    if float(parsed).is_integer():
        return int(parsed)
    return parsed


def downsample_xy(x_values: Iterable[float], y_values: Iterable[float], max_points: int = 1200) -> tuple[list[float], list[float]]:
    x = list(x_values)
    y = list(y_values)
    size = min(len(x), len(y))
    if size == 0:
        return [], []

    x = x[:size]
    y = y[:size]
    if size <= max_points:
        return x, y

    step = size / max_points
    sampled_x: list[float] = []
    sampled_y: list[float] = []
    for index in range(max_points):
        source_index = min(size - 1, int(round(index * step)))
        sampled_x.append(x[source_index])
        sampled_y.append(y[source_index])
    if sampled_x[-1] != x[-1] or sampled_y[-1] != y[-1]:
        sampled_x[-1] = x[-1]
        sampled_y[-1] = y[-1]
    return sampled_x, sampled_y


def _safe_bounds(values: list[float]) -> tuple[float, float]:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0, 1.0
    minimum = min(finite)
    maximum = max(finite)
    if minimum == maximum:
        minimum -= 1.0
        maximum += 1.0
    return minimum, maximum


def build_svg_line_plot(
    x_values: Iterable[float],
    y_values: Iterable[float],
    *,
    max_points: int = 1200,
    width: int = 880,
    height: int = 260,
    pad_x: int = 44,
    pad_y: int = 24,
) -> dict[str, object] | None:
    sampled_x, sampled_y = downsample_xy(x_values, y_values, max_points=max_points)
    if len(sampled_x) < 2:
        return None

    x_min, x_max = _safe_bounds(sampled_x)
    y_min, y_max = _safe_bounds(sampled_y)
    inner_w = max(width - 2 * pad_x, 10)
    inner_h = max(height - 2 * pad_y, 10)

    def sx(value: float) -> float:
        return pad_x + (value - x_min) * inner_w / (x_max - x_min)

    def sy(value: float) -> float:
        return height - pad_y - (value - y_min) * inner_h / (y_max - y_min)

    points = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(sampled_x, sampled_y))

    return {
        "width": width,
        "height": height,
        "pad_x": pad_x,
        "pad_y": pad_y,
        "points": points,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "point_count": len(sampled_x),
    }


def format_number(value: object) -> str:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric == 0.0:
            return "0"
        if abs(numeric) >= 1.0e4 or abs(numeric) < 1.0e-3:
            return f"{numeric:.4e}"
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.6g}"
    return str(value)
