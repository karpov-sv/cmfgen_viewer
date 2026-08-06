from __future__ import annotations

from pathlib import Path
import re

from .common import build_plotly_line_plot, format_number, normalize_space, parse_float_token, parse_numeric_tokens
from .diagnostic_text import MAX_TABLE_ROWS, parse_log_diagnostic, parse_numeric_diagnostic

KEYWORD_ROW_RE = re.compile(r"^\s*(.*?)\s+\[([A-Za-z0-9_./+=-]+)\](?:\s*!\s*(.*))?\s*$")
SIMPLE_CONTROL_RE = re.compile(r"^\s*(\S+)\s+([A-Z][A-Z0-9_]+)\s*(?:!\s*(.*))?$")
AUTO_CHECK_ROW_RE = re.compile(r"^\s*(\d+)\s+(\S+)\s+([+\-0-9.EeDd]+)\s*$")
STEQ_CHUNK_RE = re.compile(r"^\s*(\d+)(?:\(\s*(\d+)\))?\s*([&%*]+)?\s+(.*)$")


def _scale(values: list[float]) -> str:
    positive = [value for value in values if value > 0]
    if len(positive) != len(values) or not positive:
        return "linear"
    return "log" if max(positive) / min(positive) >= 1.0e3 else "linear"


def _numeric_prefix(line: str) -> tuple[list[float], list[str]]:
    values: list[float] = []
    tokens = line.split()
    index = 0
    for index, token in enumerate(tokens):
        parsed = parse_float_token(token)
        if parsed is None:
            return values, tokens[index:]
        values.append(parsed)
    return values, []


def parse_cmf_spectrum(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(
        path,
        parser_name="CMF_SPECTRUM",
        title=f"{path.name} post-processed CMF spectrum",
        column_labels=["Wavelength (Angstrom)", "Flux"],
        prefer_log_x=True,
        prefer_log_y=True,
    )


def parse_ewdata(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    parsed_rows: list[tuple[list[float], str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        values, tail = _numeric_prefix(stripped)
        if len(values) >= 2:
            parsed_rows.append((values, " ".join(tail)))

    if not parsed_rows:
        return parse_log_diagnostic(path, parser_name="EWDATA", title=f"{path.name} equivalent-width diagnostics")

    numeric_columns = max(len(values) for values, _tail in parsed_rows)
    if numeric_columns == 3:
        columns = ["Wavelength (Angstrom)", "Continuum flux", "Equivalent width (Angstrom)"]
    elif numeric_columns >= 6:
        columns = [
            "Wavelength (Angstrom)",
            "Reference wavelength (Angstrom)",
            "Continuum ratio",
            "Equivalent width",
            "Absolute equivalent width",
            "Line flux",
        ]
    else:
        columns = [f"col_{index + 1}" for index in range(numeric_columns)]
    columns.extend(f"col_{index + 1}" for index in range(len(columns), numeric_columns))
    columns.append("Flags / transition")

    table_rows = [
        [format_number(value) for value in values]
        + [""] * (numeric_columns - len(values))
        + [tail]
        for values, tail in parsed_rows[:MAX_TABLE_ROWS]
    ]
    warnings: list[str] = []
    if len(parsed_rows) > MAX_TABLE_ROWS:
        warnings.append(f"Equivalent-width table truncated to first {MAX_TABLE_ROWS} rows.")

    x = [values[0] for values, _tail in parsed_rows]
    plots: list[dict[str, object]] = []
    for column_index in range(1, min(numeric_columns, 4)):
        points = [(values[0], values[column_index]) for values, _tail in parsed_rows if len(values) > column_index]
        if len(points) < 2:
            continue
        plot = build_plotly_line_plot(
            [point[0] for point in points],
            [point[1] for point in points],
            x_label=columns[0],
            y_label=columns[column_index],
            default_x_scale=_scale(x),
            default_y_scale=_scale([point[1] for point in points]),
        )
        if plot:
            plots.append({"title": f"{columns[column_index]} vs wavelength", **plot})

    return {
        "parser": "EWDATA",
        "title": f"{path.name} equivalent-width diagnostics",
        "summary_table": {
            "title": "Equivalent-width summary",
            "columns": ["Field", "Value"],
            "rows": [
                ["file", path.name],
                ["transitions", str(len(parsed_rows))],
                ["numeric_columns", str(numeric_columns)],
            ],
        },
        "tables": [{"title": "Transitions", "columns": columns, "rows": table_rows}],
        "plots": plots,
        "warnings": warnings,
    }


def parse_keyword_control(path: Path) -> dict[str, object]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match:
            value_raw, key, comment = match.groups()
        else:
            simple = SIMPLE_CONTROL_RE.match(line)
            if not simple:
                continue
            value_raw, key, comment = simple.groups()
        numeric = parse_float_token(value_raw.strip())
        rows.append([key, format_number(numeric) if numeric is not None else value_raw.strip(), (comment or "").strip()])

    if not rows:
        return parse_log_diagnostic(path, parser_name="CMFGEN_CONTROL", title=f"{path.name} control parameters")
    return {
        "parser": path.name.upper(),
        "title": f"{path.name} control parameters",
        "summary_table": {
            "title": "Control summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["parameters", str(len(rows))]],
        },
        "tables": [{"title": "Parameters", "columns": ["Key", "Value", "Comment"], "rows": rows}],
        "plots": [],
        "warnings": [],
    }


def parse_species_masses(path: Path) -> dict[str, object]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        tokens = line.split()
        if len(tokens) < 2 or parse_float_token(tokens[0]) is not None:
            continue
        numbers = [parse_float_token(token) for token in tokens[1:]]
        numeric = [value for value in numbers if value is not None]
        if not numeric:
            continue
        rows.append([tokens[0], *[format_number(value) for value in numeric]])

    if not rows:
        return parse_log_diagnostic(path, parser_name="SPECIES_MASSES", title="SPECIES_MASSES composition summary")
    max_values = max(len(row) - 1 for row in rows)
    columns = ["Species", "Mass (Msun)", "Boundary number", "Mass fraction (outer)", "Mass fraction (inner)"]
    columns = columns[: max_values + 1]
    columns.extend(f"value_{index}" for index in range(len(columns), max_values + 1))
    body = [row + [""] * (max_values + 1 - len(row)) for row in rows[:MAX_TABLE_ROWS]]
    return {
        "parser": "SPECIES_MASSES",
        "title": "SPECIES_MASSES composition summary",
        "summary_table": {
            "title": "Composition summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["species", str(len(rows))]],
        },
        "tables": [{"title": "Species masses", "columns": columns, "rows": body}],
        "plots": [],
        "warnings": [f"Species table truncated to first {MAX_TABLE_ROWS} rows."] if len(rows) > MAX_TABLE_ROWS else [],
    }


def parse_auto_check(path: Path) -> dict[str, object]:
    rows: list[list[str]] = []
    x_values: list[float] = []
    rates: list[float] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = AUTO_CHECK_ROW_RE.match(line)
        if not match:
            continue
        index_raw, level, rate_raw = match.groups()
        rate = parse_float_token(rate_raw)
        if rate is None:
            continue
        rows.append([index_raw, level, format_number(rate)])
        x_values.append(float(index_raw))
        rates.append(rate)
    if not rows:
        return parse_log_diagnostic(path, parser_name="AUTO_CHK_*", title=f"{path.name} autoionization audit")
    plot = build_plotly_line_plot(x_values, rates, x_label="Level index", y_label="Utilized rate")
    return {
        "parser": "AUTO_CHK_*",
        "title": f"{path.name} autoionization audit",
        "summary_table": {
            "title": "Audit summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["levels", str(len(rows))], ["nonzero_rates", str(sum(rate != 0 for rate in rates))]],
        },
        "tables": [{"title": "Autoionization levels", "columns": ["Index", "Level", "Rate"], "rows": rows[:MAX_TABLE_ROWS]}],
        "plots": [{"title": "Utilized autoionization rates", **plot}] if plot else [],
        "warnings": [f"Level table truncated to first {MAX_TABLE_ROWS} rows."] if len(rows) > MAX_TABLE_ROWS else [],
    }


def parse_steq_vals(path: Path) -> dict[str, object]:
    series: dict[str, list[float]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STEQ_CHUNK_RE.match(line)
        if not match:
            continue
        equation, _offset, marker, payload = match.groups()
        values = parse_numeric_tokens(payload)
        if not values:
            continue
        key = f"Equation {equation} {marker or ''}".strip()
        series.setdefault(key, []).extend(values)
    if not series:
        return parse_log_diagnostic(path, parser_name="STEQ_VALS", title="STEQ_VALS equation diagnostics")
    plots: list[dict[str, object]] = []
    for label, values in list(series.items())[:16]:
        plot = build_plotly_line_plot(
            [float(index + 1) for index in range(len(values))],
            values,
            x_label="Depth/sample index",
            y_label=label,
        )
        if plot:
            plots.append({"title": label, **plot})
    return {
        "parser": "STEQ_VALS",
        "title": "STEQ_VALS equation diagnostics",
        "summary_table": {
            "title": "Equation summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["series", str(len(series))]],
        },
        "tables": [{"title": "Detected series", "columns": ["Series", "Values"], "rows": [[label, str(len(values))] for label, values in series.items()]}],
        "plots": plots,
        "warnings": ["Plots limited to the first 16 series."] if len(series) > 16 else [],
    }


def parse_vector_diagnostic(path: Path, *, parser_name: str | None = None, title: str | None = None) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    vectors: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        heading = normalize_space(lines[index].strip().strip("!#*:"))
        if not heading or not re.search(r"[A-Za-z]", heading) or parse_numeric_tokens(lines[index].strip()):
            index += 1
            continue
        probe = index + 1
        while probe < len(lines) and not lines[probe].strip():
            probe += 1
        if probe >= len(lines) or not parse_numeric_tokens(lines[probe].strip()):
            index += 1
            continue
        values: list[float] = []
        while probe < len(lines):
            stripped = lines[probe].strip()
            if not stripped:
                probe += 1
                continue
            numeric = parse_numeric_tokens(stripped)
            if not numeric:
                break
            values.extend(numeric)
            probe += 1
        if len(values) >= 2:
            vectors.append({"heading": heading[:120], "values": values})
        index = max(index + 1, probe)

    resolved_parser = parser_name or path.name.upper()
    resolved_title = title or f"{path.name} vector diagnostics"
    if not vectors:
        return parse_numeric_diagnostic(path, parser_name=resolved_parser, title=resolved_title, detect_header_labels=True)

    radius = next((item for item in vectors if str(item["heading"]).lower().startswith("radius")), None)
    plots: list[dict[str, object]] = []
    for item in vectors[:16]:
        values = item["values"]
        if not isinstance(values, list) or len(values) < 2:
            continue
        if radius is not None and isinstance(radius["values"], list) and len(radius["values"]) == len(values):
            x_values = radius["values"]
            x_label = str(radius["heading"])
        else:
            x_values = [float(point + 1) for point in range(len(values))]
            x_label = "Sample index"
        plot = build_plotly_line_plot(
            x_values,
            values,
            x_label=x_label,
            y_label=str(item["heading"]),
            default_x_scale=_scale(x_values),
            default_y_scale=_scale(values),
        )
        if plot:
            plots.append({"title": str(item["heading"]), **plot})

    warnings: list[str] = []
    if len(vectors) > 16:
        warnings.append("Plots limited to the first 16 detected vectors; all vectors remain listed below.")
    return {
        "parser": resolved_parser,
        "title": resolved_title,
        "summary_table": {
            "title": "Vector summary",
            "columns": ["Field", "Value"],
            "rows": [["file", path.name], ["vectors", str(len(vectors))]],
        },
        "tables": [
            {
                "title": "Detected vectors",
                "columns": ["Vector", "Values"],
                "rows": [[str(item["heading"]), str(len(item["values"]))] for item in vectors[:MAX_TABLE_ROWS]],
            }
        ],
        "plots": plots,
        "warnings": warnings,
    }


def parse_prrr(path: Path) -> dict[str, object]:
    return parse_vector_diagnostic(path, parser_name="*PRRR", title=f"{path.name} recombination/photoionization diagnostics")


def parse_gencool(path: Path) -> dict[str, object]:
    return parse_vector_diagnostic(path, parser_name="GENCOOL", title="GENCOOL heating/cooling diagnostics")


def parse_two_phot_sum(path: Path) -> dict[str, object]:
    return parse_vector_diagnostic(path, parser_name="TWO_PHOT_SUM", title="TWO_PHOT_SUM transition-rate diagnostics")


def parse_named_numeric(path: Path) -> dict[str, object]:
    return parse_numeric_diagnostic(
        path,
        parser_name=path.name.upper(),
        title=f"{path.name} diagnostics",
        detect_header_labels=True,
    )


def parse_named_log(path: Path) -> dict[str, object]:
    return parse_log_diagnostic(path, parser_name=path.name.upper(), title=f"{path.name} diagnostics")
