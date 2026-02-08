from __future__ import annotations

import re
from pathlib import Path

from .common import build_plotly_line_plot, format_number, parse_float_token, parse_key_value_pairs, parse_numeric_tokens

MAX_TABLE_ROWS = 220
MAX_SCALAR_ROWS = 40
MAX_LOG_ROWS = 180
WARN_RE = re.compile(r"\b(warn|error|fatal|stop|fail|exception)\b", re.IGNORECASE)
COLON_SCALAR_RE = re.compile(r"^\s*([^:#=][^:=#]{0,80})\s*:\s*(\S.*)$")
GAMMAS_DEPTH_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?)\s*!?\s*Number of depth points\b", re.IGNORECASE)
GAMMAS_SPECIES_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?)\s+([A-Za-z][A-Za-z0-9_+-]*)\b")
RVSIG_DEPTH_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d*)?)\s*!?\s*Number of depth points\b", re.IGNORECASE)
RVSIG_SCALAR_RE = re.compile(r"^\s*!+\s*(.+?)\s*(?:is:|=)\s*([^\s!`]+)\s*$", re.IGNORECASE)
HYDRO_PARAMS_KV_RE = re.compile(r"^\s*(\S.*?)\s+\[([A-Za-z0-9_./+=-]+)\]\s*$")


def _bool_text(value: bool) -> str:
    return "yes" if value else "no"


def _all_positive(values: list[float]) -> bool:
    return bool(values) and all(value > 0 for value in values)


def _auto_log_scale(values: list[float]) -> str:
    if not _all_positive(values):
        return "linear"
    min_value = min(values)
    max_value = max(values)
    if min_value <= 0:
        return "linear"
    return "log" if (max_value / min_value) >= 1.0e3 else "linear"


def _extract_scalars(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if len(rows) >= MAX_SCALAR_ROWS:
            break

        stripped = line.strip()
        if not stripped:
            continue

        parsed_equal = parse_key_value_pairs(stripped)
        if parsed_equal:
            for key, raw in parsed_equal[:4]:
                rows.append([key, format_number(parse_float_token(raw) if parse_float_token(raw) is not None else raw)])
                if len(rows) >= MAX_SCALAR_ROWS:
                    break
            continue

        colon = COLON_SCALAR_RE.match(stripped)
        if colon:
            key = colon.group(1).strip()
            raw = colon.group(2).strip()
            numeric = parse_float_token(raw)
            rows.append([key, format_number(numeric) if numeric is not None else raw])
    return rows


def _collect_numeric_blocks(lines: list[str]) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []

    current_rows: list[list[float]] = []
    current_cols: int | None = None
    current_start = 0

    def flush() -> None:
        nonlocal current_rows, current_cols, current_start
        if current_rows and current_cols and current_cols >= 2:
            blocks.append(
                {
                    "rows": current_rows,
                    "cols": current_cols,
                    "start_line": current_start,
                }
            )
        current_rows = []
        current_cols = None
        current_start = 0

    for idx, raw in enumerate(lines, start=1):
        values = parse_numeric_tokens(raw.strip())
        if values and len(values) >= 2:
            cols = len(values)
            if current_cols is None:
                current_cols = cols
                current_start = idx
                current_rows = [values]
                continue
            if cols == current_cols:
                current_rows.append(values)
                continue
            flush()
            current_cols = cols
            current_start = idx
            current_rows = [values]
            continue
        flush()
    flush()
    return blocks


def _choose_block(blocks: list[dict[str, object]]) -> dict[str, object] | None:
    if not blocks:
        return None
    return max(blocks, key=lambda block: (len(block["rows"]) * int(block["cols"]), len(block["rows"])))


def _build_numeric_table(
    rows: list[list[float]],
    *,
    column_labels: list[str] | None = None,
) -> tuple[list[str], list[list[str]], bool]:
    if not rows:
        return [], [], False

    col_count = len(rows[0])
    labels = [f"col_{index + 1}" for index in range(col_count)]
    if column_labels:
        for idx, label in enumerate(column_labels[:col_count]):
            labels[idx] = label

    truncated = len(rows) > MAX_TABLE_ROWS
    subset = rows[:MAX_TABLE_ROWS]
    body = [[format_number(value) for value in row] for row in subset]
    return labels, body, truncated


def _make_unique_labels(labels: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    output: list[str] = []
    for label in labels:
        key = label
        count = seen.get(key, 0) + 1
        seen[key] = count
        if count == 1:
            output.append(label)
        else:
            output.append(f"{label}_{count}")
    return output


def _detect_header_labels(lines: list[str], *, start_line: int, col_count: int) -> list[str] | None:
    # Search a few lines above the numeric block for a non-numeric token row that
    # matches the numeric column count (common in CMFGEN tables like MEANOPAC).
    search_start = max(0, start_line - 5)
    for index in range(start_line - 2, search_start - 1, -1):
        candidate = lines[index].strip()
        if not candidate:
            continue
        tokens = candidate.split()
        if len(tokens) != col_count:
            continue
        if all(parse_float_token(token) is not None for token in tokens):
            continue
        return _make_unique_labels(tokens)
    return None


def parse_numeric_diagnostic(
    path: Path,
    *,
    parser_name: str,
    title: str,
    column_labels: list[str] | None = None,
    prefer_log_x: bool = False,
    prefer_log_y: bool = False,
) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    scalars = _extract_scalars(lines)
    blocks = _collect_numeric_blocks(lines)
    selected = _choose_block(blocks)

    summary_rows: list[list[str]] = [
        ["file", path.name],
        ["total_lines", str(len(lines))],
        ["numeric_blocks", str(len(blocks))],
    ]
    if scalars:
        summary_rows.append(["scalar_fields_detected", str(len(scalars))])

    tables: list[dict[str, object]] = []
    plots: list[dict[str, object]] = []
    warnings: list[str] = []

    if scalars:
        tables.append(
            {
                "title": "Detected scalars",
                "columns": ["Field", "Value"],
                "rows": scalars,
            }
        )

    if selected:
        data_rows = selected["rows"]
        col_count = int(selected["cols"])
        start_line = int(selected["start_line"])
        summary_rows.append(["selected_block_start_line", str(start_line)])
        summary_rows.append(["selected_block_rows", str(len(data_rows))])
        summary_rows.append(["selected_block_columns", str(col_count)])

        headers, body, table_truncated = _build_numeric_table(data_rows, column_labels=column_labels)
        if headers and body:
            tables.append(
                {
                    "title": "Main numeric block",
                    "columns": headers,
                    "rows": body,
                }
            )
        if table_truncated:
            warnings.append(f"Numeric table truncated to first {MAX_TABLE_ROWS} rows.")

        x = [row[0] for row in data_rows]
        x_label = headers[0] if headers else "col_1"
        log_x = _all_positive(x) and (prefer_log_x or _auto_log_scale(x) == "log")
        y_series_limit = min(col_count, 4)
        for col_index in range(1, y_series_limit):
            y = [row[col_index] for row in data_rows]
            y_label = headers[col_index] if headers else f"col_{col_index + 1}"
            log_y = _all_positive(y) and (prefer_log_y or _auto_log_scale(y) == "log")
            plotly = build_plotly_line_plot(
                x,
                y,
                x_label=x_label,
                y_label=y_label,
                default_x_scale="log" if log_x else "linear",
                default_y_scale="log" if log_y else "linear",
                max_points=1200,
            )
            if plotly:
                plots.append({"title": f"{y_label} vs {x_label}", **plotly})
    else:
        summary_rows.append(["selected_block_rows", "0"])
        warnings.append("No numeric data block with at least two columns was detected.")
        preview_rows = [[str(index), line] for index, line in enumerate(lines[:MAX_LOG_ROWS], start=1)]
        if preview_rows:
            tables.append(
                {
                    "title": "Text preview",
                    "columns": ["Line", "Content"],
                    "rows": preview_rows,
                }
            )
            if len(lines) > MAX_LOG_ROWS:
                warnings.append(f"Text preview truncated to first {MAX_LOG_ROWS} lines.")

    return {
        "parser": parser_name,
        "title": title,
        "summary_table": {
            "title": "Parsed summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }


def parse_log_diagnostic(path: Path, *, parser_name: str, title: str) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    warning_rows: list[list[str]] = []
    error_rows: list[list[str]] = []

    for index, line in enumerate(lines, start=1):
        lower = line.lower()
        if "error" in lower or "fatal" in lower:
            error_rows.append([str(index), line.strip()])
        if WARN_RE.search(line):
            warning_rows.append([str(index), line.strip()])

    recent_rows = [[str(index), line] for index, line in enumerate(lines[-MAX_LOG_ROWS:], start=max(1, len(lines) - MAX_LOG_ROWS + 1))]
    summary_rows = [
        ["file", path.name],
        ["total_lines", str(len(lines))],
        ["warning_like_lines", str(len(warning_rows))],
        ["error_like_lines", str(len(error_rows))],
        ["tail_lines_shown", str(len(recent_rows))],
    ]

    tables: list[dict[str, object]] = []
    if warning_rows:
        tables.append(
            {
                "title": "Warnings / errors",
                "columns": ["Line", "Content"],
                "rows": warning_rows[:MAX_LOG_ROWS],
            }
        )
    if recent_rows:
        tables.append(
            {
                "title": "Recent lines",
                "columns": ["Line", "Content"],
                "rows": recent_rows,
            }
        )

    warnings: list[str] = []
    if len(warning_rows) > MAX_LOG_ROWS:
        warnings.append(f"Warnings table truncated to first {MAX_LOG_ROWS} rows.")
    if not tables:
        warnings.append("Log is empty.")

    return {
        "parser": parser_name,
        "title": title,
        "summary_table": {
            "title": "Log summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": [],
        "warnings": warnings,
    }


def parse_meanopac(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks = _collect_numeric_blocks(lines)
    selected = _choose_block(blocks)

    summary_rows: list[list[str]] = [
        ["file", path.name],
        ["total_lines", str(len(lines))],
        ["numeric_blocks", str(len(blocks))],
    ]

    tables: list[dict[str, object]] = []
    plots: list[dict[str, object]] = []
    warnings: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        if "NB:" not in stripped:
            continue
        for chunk in re.split(r"(?=NB:)", stripped):
            text = chunk.strip()
            if text.startswith("NB:"):
                warnings.append(text[3:].strip())

    if not selected:
        summary_rows.append(["selected_block_rows", "0"])
        warnings.append("No numeric data block with at least two columns was detected.")
        preview_rows = [[str(index), line] for index, line in enumerate(lines[:MAX_LOG_ROWS], start=1)]
        if preview_rows:
            tables.append(
                {
                    "title": "Text preview",
                    "columns": ["Line", "Content"],
                    "rows": preview_rows,
                }
            )
        return {
            "parser": "MEANOPAC",
            "title": "MEANOPAC opacity diagnostics",
            "summary_table": {
                "title": "Parsed summary",
                "columns": ["Field", "Value"],
                "rows": summary_rows,
            },
            "tables": tables,
            "plots": plots,
            "warnings": warnings,
        }

    data_rows = selected["rows"]
    col_count = int(selected["cols"])
    start_line = int(selected["start_line"])
    header_labels = _detect_header_labels(lines, start_line=start_line, col_count=col_count)

    summary_rows.append(["selected_block_start_line", str(start_line)])
    summary_rows.append(["selected_block_rows", str(len(data_rows))])
    summary_rows.append(["selected_block_columns", str(col_count)])
    summary_rows.append(["header_labels_detected", _bool_text(bool(header_labels))])

    headers, body, table_truncated = _build_numeric_table(data_rows, column_labels=header_labels)
    tables.append(
        {
            "title": "Main numeric block",
            "columns": headers,
            "rows": body,
        }
    )
    if table_truncated:
        warnings.append(f"Numeric table truncated to first {MAX_TABLE_ROWS} rows.")

    x_index = 0
    x = [row[x_index] for row in data_rows]
    x_label = headers[x_index] if headers else "col_1"
    x_log = _all_positive(x) and _auto_log_scale(x) == "log"

    # Plot every data column (except the x-axis) by default so users get full
    # visibility into the complete MEANOPAC table without manual selection.
    # Keep original column order and case-sensitive labels exactly as read.
    selected_indices = [
        index
        for index in range(col_count)
        if index != x_index and (not headers or headers[index].strip().upper() != "I")
    ]
    summary_rows.append(["plotted_series_count", str(len(selected_indices))])

    for col_index in selected_indices:
        y = [row[col_index] for row in data_rows]
        y_label = headers[col_index] if headers else f"col_{col_index + 1}"
        y_log = _all_positive(y) and _auto_log_scale(y) == "log"
        plotly = build_plotly_line_plot(
            x,
            y,
            x_label=x_label,
            y_label=y_label,
            default_x_scale="log" if x_log else "linear",
            default_y_scale="log" if y_log else "linear",
            max_points=1200,
        )
        if plotly:
            plots.append({"title": f"{y_label} vs {x_label}", **plotly})

    return {
        "parser": "MEANOPAC",
        "title": "MEANOPAC opacity diagnostics",
        "summary_table": {
            "title": "Parsed summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }


def parse_hydro(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="HYDRO", title="HYDRO momentum diagnostics")


def parse_obsframe(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(
        path,
        parser_name="OBSFRAME",
        title="OBSFRAME observer-frame spectrum",
        prefer_log_x=True,
    )


def parse_out_flux(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name="OUT_FLUX", title="OUT_FLUX run log")


def parse_outlte(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name="OUTLTE", title="OUTLTE LTE run log")


def parse_rosseland_lte_tab(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(
        path,
        parser_name="ROSSELAND_LTE_TAB",
        title="ROSSELAND_LTE_TAB LTE opacity grid",
        column_labels=[
            "T",
            "Density",
            "Atom population",
            "Ne",
            "Chi(Ross)",
            "Chi(es)",
            "Kap(Ross)",
            "Kap(es)",
        ],
        prefer_log_x=True,
        prefer_log_y=True,
    )


def parse_hydro_params(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = HYDRO_PARAMS_KV_RE.match(stripped)
        if not match:
            continue
        value_raw = match.group(1).strip()
        key = match.group(2).strip()
        numeric = parse_float_token(value_raw)
        value = format_number(numeric) if numeric is not None else value_raw
        rows.append([key, value])

    if not rows:
        return parse_log_diagnostic(path, parser_name="HYDRO_PARAMS", title="HYDRO_PARAMS setup values")

    return {
        "parser": "HYDRO_PARAMS",
        "title": "HYDRO_PARAMS setup values",
        "summary_table": {
            "title": "Parameter summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["parameter_count", str(len(rows))]],
        },
        "tables": [
            {
                "title": "Input parameters",
                "columns": ["Key", "Value"],
                "rows": rows,
            }
        ],
        "plots": [],
        "warnings": [],
    }


def parse_ml_counter(path: Path) -> dict[str, object]:
    values: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        for token in line.split():
            parsed = parse_float_token(token)
            if parsed is not None:
                values.append(parsed)

    if not values:
        return parse_log_diagnostic(path, parser_name="ML_COUNTER", title="ML_COUNTER iteration counters")

    rows = [[str(index + 1), format_number(value)] for index, value in enumerate(values[:MAX_TABLE_ROWS])]
    warnings: list[str] = []
    if len(values) > MAX_TABLE_ROWS:
        warnings.append(f"Counter table truncated to first {MAX_TABLE_ROWS} rows.")

    x_values = [float(index + 1) for index in range(len(values))]
    plot = build_plotly_line_plot(
        x_values,
        values,
        x_label="Sample index",
        y_label="Counter value",
        max_points=1200,
        default_x_scale="linear",
        default_y_scale="linear",
    )
    plots = [{"title": "Counter progression", **plot}] if plot else []

    return {
        "parser": "ML_COUNTER",
        "title": "ML_COUNTER iteration counters",
        "summary_table": {
            "title": "Counter summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["samples", str(len(values))]],
        },
        "tables": [
            {
                "title": "Counter values",
                "columns": ["Index", "Value"],
                "rows": rows,
            }
        ],
        "plots": plots,
        "warnings": warnings,
    }


def parse_lte_diagnostic_est(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name=path.name.upper(), title=f"{path.name} wind_hyd diagnostics")


def parse_time_pointer(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name=path.name.upper(), title=f"{path.name} time-sequence pointer")


def parse_rvsig_col(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    warnings: list[str] = []

    depth_points: int | None = None
    for line in lines[:80]:
        match = RVSIG_DEPTH_RE.match(line)
        if not match:
            continue
        parsed_depth = parse_float_token(match.group(1))
        if parsed_depth is not None and parsed_depth > 0:
            depth_points = int(parsed_depth)
            break

    scalar_rows: list[list[str]] = []
    seen_scalar_keys: set[str] = set()
    for line in lines:
        match = RVSIG_SCALAR_RE.match(line)
        if not match:
            continue
        key = re.sub(r"\s+", " ", match.group(1)).strip()
        value_token = match.group(2).strip()
        if not key or key in seen_scalar_keys:
            continue
        seen_scalar_keys.add(key)
        numeric_value = parse_float_token(value_token)
        scalar_rows.append([key, format_number(numeric_value) if numeric_value is not None else value_token])

    blocks = [block for block in _collect_numeric_blocks(lines) if int(block["cols"]) in {4, 5}]
    selected = _choose_block(blocks)
    if not selected:
        return parse_numeric_diagnostic(path, parser_name="RVSIG_COL", title=f"{path.name} velocity-grid profile")

    data_rows = selected["rows"]
    col_count = int(selected["cols"])
    row_count = len(data_rows)
    start_line = int(selected["start_line"])

    if depth_points is not None:
        if row_count > depth_points:
            extra_rows = row_count - depth_points
            data_rows = data_rows[:depth_points]
            row_count = depth_points
            warnings.append(f"Trimmed {extra_rows} trailing row(s) beyond declared depth points ({depth_points}).")
        elif row_count < depth_points:
            warnings.append(f"Depth points declared={depth_points} while parsed rows={row_count}.")

    if col_count == 5:
        columns = ["Radius (10^10 cm)", "Velocity (km/s)", "Sigma", "Tau", "Index"]
        y_specs = [(1, "Velocity (km/s)"), (2, "Sigma"), (3, "Tau")]
    else:
        columns = ["Radius (10^10 cm)", "Velocity (km/s)", "Sigma", "Depth index"]
        y_specs = [(1, "Velocity (km/s)"), (2, "Sigma")]

    table_truncated = row_count > MAX_TABLE_ROWS
    if table_truncated:
        warnings.append(f"Main table truncated to first {MAX_TABLE_ROWS} rows.")
    table_rows = [[format_number(value) for value in row] for row in data_rows[:MAX_TABLE_ROWS]]

    summary_rows: list[list[str]] = [
        ["file", path.name],
        ["depth_points_declared", str(depth_points) if depth_points is not None else "n/a"],
        ["parsed_rows", str(row_count)],
        ["parsed_columns", str(col_count)],
        ["data_start_line", str(start_line)],
    ]

    x_values = [row[0] for row in data_rows]
    x_log = _all_positive(x_values) and _auto_log_scale(x_values) == "log"
    plots: list[dict[str, object]] = []
    for index, label in y_specs:
        y_values = [row[index] for row in data_rows]
        y_log = _all_positive(y_values) and _auto_log_scale(y_values) == "log"
        plotly = build_plotly_line_plot(
            x_values,
            y_values,
            x_label="Radius (10^10 cm)",
            y_label=label,
            default_x_scale="log" if x_log else "linear",
            default_y_scale="log" if y_log else "linear",
            max_points=1400,
        )
        if plotly:
            plots.append({"title": f"{label} vs Radius", **plotly})

    tables: list[dict[str, object]] = [
        {
            "title": "RVSIG_COL depth table",
            "columns": columns,
            "rows": table_rows,
        }
    ]
    if scalar_rows:
        tables.insert(
            0,
            {
                "title": "Velocity-law scalars",
                "columns": ["Field", "Value"],
                "rows": scalar_rows[:MAX_SCALAR_ROWS],
            },
        )
        if len(scalar_rows) > MAX_SCALAR_ROWS:
            warnings.append(f"Scalars table truncated to first {MAX_SCALAR_ROWS} rows.")

    return {
        "parser": "RVSIG_COL",
        "title": f"{path.name} velocity-grid profile",
        "summary_table": {
            "title": "Parsed summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }


def parse_gammas(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    warnings: list[str] = []

    depth_points: int | None = None
    for line in lines[:40]:
        match = GAMMAS_DEPTH_RE.match(line)
        if not match:
            continue
        parsed_depth = parse_float_token(match.group(1))
        if parsed_depth is not None and parsed_depth > 0:
            depth_points = int(parsed_depth)
            break

    def collect_values(start_index: int, expected_count: int | None) -> tuple[list[float], int]:
        values: list[float] = []
        index = start_index
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped:
                index += 1
                continue
            if stripped.startswith("!") or GAMMAS_SPECIES_RE.match(stripped):
                break
            numeric = parse_numeric_tokens(stripped)
            if numeric:
                values.extend(numeric)
                if expected_count is not None and len(values) >= expected_count:
                    return values[:expected_count], index + 1
                index += 1
                continue
            if values:
                break
            index += 1
        return values, index

    electron_density: list[float] = []
    radius: list[float] = []
    temperature: list[float] = []
    species_rows: list[dict[str, object]] = []

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("!"):
            heading = stripped.lstrip("!").strip().lower()
            if heading.startswith("electron density"):
                electron_density, index = collect_values(index + 1, depth_points)
                continue
            if heading.startswith("radius"):
                radius, index = collect_values(index + 1, depth_points)
                continue
            if heading.startswith("temperature"):
                temperature, index = collect_values(index + 1, depth_points)
                continue

        species_match = GAMMAS_SPECIES_RE.match(stripped)
        if species_match:
            atomic_number = parse_float_token(species_match.group(1))
            species_label = species_match.group(2).strip()
            values, index = collect_values(index + 1, depth_points)
            species_rows.append(
                {
                    "atomic_number": int(atomic_number) if atomic_number is not None else None,
                    "label": species_label,
                    "values": values,
                }
            )
            continue

        index += 1

    row_count = depth_points
    if row_count is None or row_count <= 0:
        candidate_sizes = [len(electron_density), len(radius), len(temperature)] + [len(species["values"]) for species in species_rows]
        row_count = max(candidate_sizes, default=0)

    if row_count <= 0:
        return parse_numeric_diagnostic(path, parser_name="GAMMAS", title="GAMMAS mean ionic charge profiles")

    summary_rows: list[list[str]] = [
        ["file", path.name],
        ["depth_points_declared", str(depth_points) if depth_points is not None else "n/a"],
        ["depth_points_used", str(row_count)],
        ["species_count", str(len(species_rows))],
    ]

    for title, values in [
        ("electron_density_points", electron_density),
        ("radius_points", radius),
        ("temperature_points", temperature),
    ]:
        if values:
            summary_rows.append([title, str(len(values))])
        else:
            warnings.append(f"{title.replace('_', ' ')} block not found.")

    for block_label, values in [
        ("electron density", electron_density),
        ("radius", radius),
        ("temperature", temperature),
    ]:
        if values and len(values) != row_count:
            warnings.append(f"{block_label} has {len(values)} values while expected {row_count}.")

    species_table_rows: list[list[str]] = []
    for species in species_rows:
        values = species["values"]
        species_table_rows.append(
            [
                str(species["atomic_number"]) if species["atomic_number"] is not None else "?",
                str(species["label"]),
                str(len(values)),
            ]
        )
        if len(values) != row_count:
            warnings.append(f"{species['label']} has {len(values)} values while expected {row_count}.")

    columns = [
        "Depth",
        "Radius (10^10 cm)",
        "Temperature (10^4 K)",
        "Electron density (cm^-3)",
    ] + [str(species["label"]) for species in species_rows]
    data_rows: list[list[str]] = []
    for depth_index in range(row_count):
        row = [
            str(depth_index + 1),
            format_number(radius[depth_index]) if depth_index < len(radius) else "",
            format_number(temperature[depth_index]) if depth_index < len(temperature) else "",
            format_number(electron_density[depth_index]) if depth_index < len(electron_density) else "",
        ]
        for species in species_rows:
            values = species["values"]
            row.append(format_number(values[depth_index]) if depth_index < len(values) else "")
        data_rows.append(row)

    table_truncated = len(data_rows) > MAX_TABLE_ROWS
    if table_truncated:
        warnings.append(f"Main table truncated to first {MAX_TABLE_ROWS} rows.")
    main_table_rows = data_rows[:MAX_TABLE_ROWS]

    x_values = radius[:row_count] if len(radius) == row_count and len(radius) >= 2 else [float(index + 1) for index in range(row_count)]
    x_label = "Radius (10^10 cm)" if len(radius) == row_count and len(radius) >= 2 else "Depth index"
    x_log = _all_positive(x_values) and _auto_log_scale(x_values) == "log"

    plots: list[dict[str, object]] = []
    for species in species_rows:
        values = species["values"]
        if len(values) < 2:
            continue
        y_values = values[:row_count] if len(values) >= row_count else values
        x_plot = x_values
        x_plot_label = x_label
        if len(y_values) != len(x_plot):
            x_plot = [float(index + 1) for index in range(len(y_values))]
            x_plot_label = "Depth index"
        y_log = _all_positive(y_values) and _auto_log_scale(y_values) == "log"
        plotly = build_plotly_line_plot(
            x_plot,
            y_values,
            x_label=x_plot_label,
            y_label="Mean ionic charge",
            default_x_scale="log" if x_log else "linear",
            default_y_scale="log" if y_log else "linear",
            max_points=1200,
        )
        if plotly:
            plots.append({"title": f"{species['label']} mean ionic charge", **plotly})

    tables: list[dict[str, object]] = [
        {
            "title": "GAMMAS depth table",
            "columns": columns,
            "rows": main_table_rows,
        }
    ]
    if species_table_rows:
        tables.append(
            {
                "title": "Species blocks",
                "columns": ["Atomic number", "Species", "Values"],
                "rows": species_table_rows,
            }
        )

    if not species_rows:
        warnings.append("No species blocks were detected.")

    return {
        "parser": "GAMMAS",
        "title": "GAMMAS mean ionic charge profiles",
        "summary_table": {
            "title": "Parsed summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": plots,
        "warnings": warnings,
    }


def parse_pop_family(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="POP*", title=f"{path.name} species population profile")


def parse_departure_out_family(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="*OUT", title=f"{path.name} departure coefficients")


def parse_j_comp(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="J_COMP", title="J_COMP boundary consistency diagnostics")


def parse_rate_file(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name=path.name.upper(), title=f"{path.name} rate diagnostics")


def parse_trans_info(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name="TRANS_INFO", title="TRANS_INFO transfer diagnostics")


def parse_sob_force_mult(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="SOB_FORCE_MULT", title="SOB_FORCE_MULT diagnostics")


def parse_gamflux(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="GAMFLUX", title="GAMFLUX gamma spectrum", prefer_log_x=True)


def parse_gamray_energy_dep(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="GAMRAY_ENERGY_DEP", title="GAMRAY_ENERGY_DEP deposition profile")


def parse_out_params(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name="OUT_PARAMS", title="OUT_PARAMS setup summary")


def parse_cfdat_out(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="CFDAT_OUT", title="CFDAT_OUT continuum frequencies")


def parse_cont_freq(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="CONT_FREQ", title="CONT_FREQ mapping diagnostics")


def parse_obs_freq(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(path, parser_name="OBS_FREQ", title="OBS_FREQ observer-frame frequency grid")
