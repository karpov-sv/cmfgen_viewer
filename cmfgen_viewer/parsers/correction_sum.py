from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

from .common import format_number, parse_float_token, parse_numeric_tokens

NT_RE = re.compile(r"\bNT\s*=\s*([+\-0-9.EeDd]+)\b", re.IGNORECASE)
HEADER_RE = re.compile(r"^\s*Depth\b", re.IGNORECASE)

INTEGER_TOL = 1.0e-6
MAX_DEPTH_TABLE_ROWS = 320


def _parse_nt(line: str) -> int | None:
    matched = NT_RE.search(line)
    if not matched:
        return None
    parsed = parse_float_token(matched.group(1))
    if parsed is None:
        return None
    rounded = int(round(parsed))
    if abs(parsed - rounded) > INTEGER_TOL:
        return None
    return rounded


def _safe_depth(value: float) -> int:
    rounded = int(round(value))
    return rounded


def _extract_table_rows(
    lines: list[str],
    *,
    header_line_index: int | None,
    threshold_labels: list[str],
) -> tuple[list[tuple[int, list[float]]], int, int]:
    rows: list[tuple[int, list[float]]] = []
    length_mismatch_count = 0
    non_integer_depth_count = 0

    if header_line_index is None:
        return rows, length_mismatch_count, non_integer_depth_count

    expected_cols = 1 + len(threshold_labels) if threshold_labels else 0
    for raw in lines[header_line_index + 1 :]:
        stripped = raw.strip()
        if not stripped:
            continue
        numeric = parse_numeric_tokens(stripped)
        if len(numeric) < 2:
            continue

        if expected_cols and len(numeric) != expected_cols:
            length_mismatch_count += 1
            continue

        depth_raw = numeric[0]
        if abs(depth_raw - round(depth_raw)) > INTEGER_TOL:
            non_integer_depth_count += 1
        depth = _safe_depth(depth_raw)

        values = numeric[1:]
        if not threshold_labels:
            threshold_labels.extend(f"col_{index + 2}" for index in range(len(values)))
            expected_cols = 1 + len(threshold_labels)

        rows.append((depth, values))

    return rows, length_mismatch_count, non_integer_depth_count


def _fallback_numeric_block(lines: list[str]) -> tuple[list[tuple[int, list[float]]], int]:
    candidates: list[tuple[int, list[float]]] = []
    non_integer_depth_count = 0
    for raw in lines:
        numeric = parse_numeric_tokens(raw.strip())
        if len(numeric) < 2:
            continue
        depth_raw = numeric[0]
        if abs(depth_raw - round(depth_raw)) > INTEGER_TOL:
            non_integer_depth_count += 1
        depth = _safe_depth(depth_raw)
        candidates.append((depth, numeric[1:]))

    if not candidates:
        return [], non_integer_depth_count

    col_counts = Counter(len(values) for _, values in candidates)
    target_col_count = max(col_counts.items(), key=lambda item: (item[1], item[0]))[0]
    rows = [(depth, values) for depth, values in candidates if len(values) == target_col_count]
    return rows, non_integer_depth_count


def _build_overview_rows(
    rows: list[tuple[int, list[float]]],
    threshold_labels: list[str],
    nt: int | None,
) -> list[list[str]]:
    if not rows:
        return []

    column_count = len(rows[0][1])
    overview: list[list[str]] = []
    depths = [depth for depth, _ in rows]

    for index in range(column_count):
        label = threshold_labels[index] if index < len(threshold_labels) else f"col_{index + 2}"
        series = [values[index] for _, values in rows]
        non_zero_depths = [depth for depth, values in rows if values[index] > 0]
        final_value = series[-1]
        final_pct = ""
        if nt and nt > 0:
            final_pct = f"{format_number((final_value / nt) * 100.0)}%"

        overview.append(
            [
                label,
                format_number(min(series)),
                format_number(max(series)),
                format_number(final_value),
                str(len(non_zero_depths)),
                str(non_zero_depths[-1]) if non_zero_depths else "-",
                final_pct,
            ]
        )

    if depths != sorted(depths):
        overview.append(["depth_order", "", "", "", "", "non-monotonic", ""])

    return overview


def _build_plot(rows: list[tuple[int, list[float]]], threshold_labels: list[str]) -> dict[str, object] | None:
    if len(rows) < 2 or not threshold_labels:
        return None

    depths = [depth for depth, _ in rows]
    traces: list[dict[str, object]] = []
    for index, label in enumerate(threshold_labels):
        series = [values[index] for _, values in rows]
        traces.append(
            {
                "type": "scatter",
                "mode": "lines",
                "name": label,
                "x": depths,
                "y": series,
                "line": {"width": 1.6},
                "hovertemplate": f"Depth=%{{x}}<br>{label}=%{{y:.6g}}<extra></extra>",
            }
        )

    return {
        "title": "Corrections above threshold by depth",
        "data": traces,
        "layout": {
            "template": "plotly_white",
            "margin": {"l": 60, "r": 24, "t": 14, "b": 52},
            "height": 360,
            "xaxis": {
                "title": {"text": "Depth index"},
                "showgrid": True,
                "zeroline": False,
                "type": "linear",
            },
            "yaxis": {
                "title": {"text": "Count"},
                "showgrid": True,
                "zeroline": False,
                "type": "linear",
            },
            "showlegend": True,
            "hovermode": "closest",
        },
        "config": {
            "responsive": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
        },
        "default_x_scale": "linear",
        "default_y_scale": "linear",
        "point_count": len(depths),
    }


def parse_correction_sum(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    warnings: list[str] = []

    nt: int | None = None
    threshold_labels: list[str] = []
    header_line_index: int | None = None
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        if nt is None:
            nt = _parse_nt(stripped)
        if header_line_index is None and HEADER_RE.match(stripped):
            tokens = stripped.split()
            if len(tokens) >= 2:
                threshold_labels = [token.strip() for token in tokens[1:]]
                header_line_index = index

    rows, length_mismatch_count, non_integer_depth_count = _extract_table_rows(
        lines,
        header_line_index=header_line_index,
        threshold_labels=threshold_labels,
    )

    if not rows:
        fallback_rows, fallback_non_integer_depth_count = _fallback_numeric_block(lines)
        if fallback_rows:
            rows = fallback_rows
            if not threshold_labels:
                threshold_labels = [f"col_{index + 2}" for index in range(len(rows[0][1]))]
            warnings.append("Header table not detected cleanly; used fallback numeric-block parsing.")
        non_integer_depth_count += fallback_non_integer_depth_count

    if rows:
        value_columns = len(rows[0][1])
        if len(threshold_labels) != value_columns:
            if threshold_labels:
                warnings.append(
                    f"Header columns ({len(threshold_labels)}) do not match parsed data columns ({value_columns}); adjusted labels."
                )
            threshold_labels = threshold_labels[:value_columns]
            if len(threshold_labels) < value_columns:
                threshold_labels.extend(
                    f"col_{index + 2}" for index in range(len(threshold_labels), value_columns)
                )

    if length_mismatch_count > 0:
        warnings.append(f"Skipped {length_mismatch_count} row(s) with unexpected column counts.")
    if non_integer_depth_count > 0:
        warnings.append(f"Found {non_integer_depth_count} row(s) with non-integer depth values; rounded for plotting.")
    if nt is None:
        warnings.append("NT value was not detected.")

    summary_rows: list[list[str]] = []
    if nt is not None:
        summary_rows.append(["NT", str(nt)])
    summary_rows.append(["depth_rows", str(len(rows))])
    summary_rows.append(["threshold_columns", str(len(threshold_labels))])
    if rows:
        depths = [depth for depth, _ in rows]
        summary_rows.append(["depth_range", f"{min(depths)} .. {max(depths)}"])
        summary_rows.append(["first_depth", str(rows[0][0])])
        summary_rows.append(["last_depth", str(rows[-1][0])])

    overview_rows = _build_overview_rows(rows, threshold_labels, nt)

    depth_rows = rows
    if len(depth_rows) > MAX_DEPTH_TABLE_ROWS:
        warnings.append(f"Depth table truncated to first {MAX_DEPTH_TABLE_ROWS} rows.")
        depth_rows = depth_rows[:MAX_DEPTH_TABLE_ROWS]

    depth_table_rows = [[str(depth)] + [format_number(value) for value in values] for depth, values in depth_rows]
    depth_table_columns = ["Depth"] + threshold_labels

    plots: list[dict[str, object]] = []
    plot = _build_plot(rows, threshold_labels)
    if plot is not None:
        plots.append(plot)

    tables: list[dict[str, object]] = []
    if overview_rows:
        tables.append(
            {
                "title": "Threshold overview",
                "columns": [
                    "Threshold",
                    "Min",
                    "Max",
                    "Final depth",
                    "Non-zero depths",
                    "Last non-zero depth",
                    "Final / NT",
                ],
                "rows": overview_rows,
            }
        )
    if depth_table_rows and depth_table_columns:
        tables.append(
            {
                "title": "Depth correction table",
                "columns": depth_table_columns,
                "rows": depth_table_rows,
            }
        )

    return {
        "parser": "CORRECTION_SUM",
        "title": "CORRECTION_SUM nonlinear solver correction summary",
        "summary_table": {
            "title": "CORRECTION_SUM summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }
