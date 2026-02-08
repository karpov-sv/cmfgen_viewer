from __future__ import annotations

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


def build_plotly_line_plot(
    x_values: Iterable[float],
    y_values: Iterable[float],
    *,
    x_label: str,
    y_label: str,
    max_points: int = 1200,
    color: str = "#0b7285",
    default_x_scale: str = "linear",
    default_y_scale: str = "linear",
) -> dict[str, object] | None:
    sampled_x, sampled_y = downsample_xy(x_values, y_values, max_points=max_points)
    if len(sampled_x) < 2:
        return None

    return {
        "data": [
            {
                # Use SVG scatter to avoid browser WebGL-context limits when a page
                # contains many plots (e.g., full-column MEANOPAC rendering).
                "type": "scatter",
                "mode": "lines",
                "x": sampled_x,
                "y": sampled_y,
                "line": {"color": color, "width": 1.6},
                "hovertemplate": f"{x_label}=%{{x:.6g}}<br>{y_label}=%{{y:.6g}}<extra></extra>",
            }
        ],
        "layout": {
            "template": "plotly_white",
            "margin": {"l": 60, "r": 24, "t": 14, "b": 52},
            "height": 320,
            "xaxis": {
                "title": {"text": x_label},
                "showgrid": True,
                "zeroline": False,
                "type": default_x_scale,
            },
            "yaxis": {
                "title": {"text": y_label},
                "showgrid": True,
                "zeroline": False,
                "type": default_y_scale,
            },
            "showlegend": False,
            "hovermode": "closest",
        },
        "config": {
            "responsive": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
        },
        "default_x_scale": default_x_scale,
        "default_y_scale": default_y_scale,
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
