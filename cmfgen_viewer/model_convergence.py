"""Run-level convergence and diagnostic summaries for CMFGEN models."""

from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import re

from .parsers.common import format_number, parse_float_token, parse_numeric_tokens


MAX_OUTGEN_BYTES = 32 * 1024 * 1024
RUN_MARKER_RE = re.compile(r"^\s*Model started on:\s*(.*?)\s*$", re.MULTILINE)
ITERATION_RE = re.compile(r"Current great iteration count is\s+(\d+)", re.IGNORECASE)
LUMINOSITY_RE = re.compile(
    r"Luminosity of star .*?\(iteration\s+(\d+)\) is:\s*(\S+)\s+(\S+)",
    re.IGNORECASE,
)
POPULATION_CHANGE_RE = re.compile(
    r"Maximum % (increase|decrease) at depth\s+(\d+) is\s+(\S+)\s+\(([^)]*)\).*?iteration\s+(\d+)",
    re.IGNORECASE,
)
SOLVER_CHANGE_RE = re.compile(r"Maximm changes .*? is\s+(\S+)", re.IGNORECASE)
SCALE_RE = re.compile(r"minimum value of scale for Major species is:\s*(\S+)", re.IGNORECASE)
FG_CALLS_RE = re.compile(r"Average number of calls to FG_J_CMF is\s+(\S+)", re.IGNORECASE)
NUM_ITS_RE = re.compile(r"^\s*(\d+)\s+\[NUM_ITS\]", re.MULTILINE)
NT_RE = re.compile(r"\bNT\s*=\s*(\d+)", re.IGNORECASE)
CORRECTION_HEADER_RE = re.compile(r"^\s*Depth\s+(.+)$", re.IGNORECASE)
TIMING_GIT_RE = re.compile(r"^\s*GIT\s+(\S+)\s+(\S+)\s*$", re.MULTILINE)


def _read_limited_tail(path: Path, limit: int) -> tuple[str, bool]:
    try:
        size = path.stat().st_size
        truncated = size > limit
        with path.open("rb") as handle:
            if truncated:
                handle.seek(size - limit)
                handle.readline()
            payload = handle.read(limit)
    except OSError:
        return "", False
    return payload.decode("utf-8", errors="replace"), truncated


def _read_text(path: Path, limit: int = 4 * 1024 * 1024) -> str:
    return _read_limited_tail(path, limit)[0]


def _finite(token: str) -> float | None:
    parsed = parse_float_token(token)
    return parsed if parsed is not None and math.isfinite(parsed) else None


def _run_segments(text: str) -> list[tuple[str | None, str]]:
    markers = list(RUN_MARKER_RE.finditer(text))
    if not markers:
        return [(None, text)] if text.strip() else []
    return [
        (
            marker.group(1).strip() or None,
            text[marker.start() : markers[index + 1].start() if index + 1 < len(markers) else len(text)],
        )
        for index, marker in enumerate(markers)
    ]


def _record_for_iteration(
    records: list[dict[str, object]],
    by_global: dict[int, dict[str, object]],
    iteration: int | None,
) -> dict[str, object] | None:
    if iteration is not None and iteration in by_global:
        return by_global[iteration]
    return records[-1] if records else None


def _parse_iteration_records(run_text: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    by_global: dict[int, dict[str, object]] = {}
    pending_spectrum_values = False
    current: dict[str, object] | None = None

    for line in run_text.splitlines():
        iteration_match = ITERATION_RE.search(line)
        if iteration_match:
            global_iteration = int(iteration_match.group(1))
            current = {
                "run_iteration": len(records) + 1,
                "global_iteration": global_iteration,
                "lambda_iteration": False,
                "temperature_fixed": False,
                "grey_solution": False,
            }
            records.append(current)
            by_global[global_iteration] = current
            pending_spectrum_values = False
            continue

        luminosity_match = LUMINOSITY_RE.search(line)
        if luminosity_match:
            record = _record_for_iteration(records, by_global, int(luminosity_match.group(1)))
            generated = _finite(luminosity_match.group(2))
            target = _finite(luminosity_match.group(3))
            if record is not None and generated is not None and target is not None:
                record["luminosity_generated"] = generated
                record["luminosity_target"] = target
                if target != 0:
                    record["luminosity_difference_percent"] = (
                        100.0 * (generated - target) / abs(target)
                    )
            continue

        population_match = POPULATION_CHANGE_RE.search(line)
        if population_match:
            record = _record_for_iteration(records, by_global, int(population_match.group(5)))
            value = _finite(population_match.group(3))
            if record is not None and value is not None:
                direction = population_match.group(1).lower()
                record[f"maximum_{direction}_percent"] = value
                record[f"maximum_{direction}_depth"] = int(population_match.group(2))
                record[f"maximum_{direction}_mode"] = population_match.group(4).strip()
            continue

        solver_match = SOLVER_CHANGE_RE.search(line)
        if solver_match and current is not None:
            value = _finite(solver_match.group(1))
            if value is not None:
                current["solver_maximum_change"] = value
            continue

        if "Largest % change in spectrum for last 5 full iterations" in line:
            pending_spectrum_values = True
            continue
        if pending_spectrum_values:
            values = parse_numeric_tokens(line.strip())
            if current is not None and values:
                current["spectrum_change_history_percent"] = values[:5]
                current["spectrum_latest_change_percent"] = values[0]
            if line.strip():
                pending_spectrum_values = False
            continue

        scale_match = SCALE_RE.search(line)
        if scale_match and current is not None:
            value = _finite(scale_match.group(1))
            if value is not None:
                current["major_species_minimum_scale"] = value
            continue
        fg_match = FG_CALLS_RE.search(line)
        if fg_match and current is not None:
            value = _finite(fg_match.group(1))
            if value is not None:
                current["average_fg_calls"] = value
            continue

        normalized = line.strip().lower()
        if current is not None:
            if "lambda iteration used" in normalized:
                current["lambda_iteration"] = True
            elif "temperature held fixed" in normalized:
                current["temperature_fixed"] = True
            elif "ba matrix **not** computed" in normalized:
                current["ba_computed"] = False
            elif normalized == "ba matrix computed":
                current["ba_computed"] = True
            elif "grey solution was successfully computed" in normalized:
                current["grey_solution"] = True
    return records


def _requested_iterations(model_dir: Path) -> int | None:
    text = _read_text(model_dir / "IN_ITS", limit=256 * 1024)
    match = NUM_ITS_RE.search(text)
    return int(match.group(1)) if match else None


def _format_signed_percent(value: float) -> str:
    return f"{value:+.4g}%"


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _solver_direction(records: list[dict[str, object]]) -> str:
    comparable = [
        float(record["solver_maximum_change"])
        for record in records
        if "solver_maximum_change" in record and not record.get("lambda_iteration")
    ][-5:]
    if len(comparable) < 2:
        return "Not enough comparable iterations for a recent direction."
    decreases = [right < left for left, right in zip(comparable, comparable[1:])]
    increases = [right > left for left, right in zip(comparable, comparable[1:])]
    if all(decreases):
        return f"Decreasing across the last {len(comparable)} non-lambda iterations."
    if all(increases):
        return f"Increasing across the last {len(comparable)} non-lambda iterations."
    ratio = comparable[-1] / comparable[0] if comparable[0] != 0 else 1.0
    if ratio <= 0.8:
        return f"Lower overall but non-monotonic across the last {len(comparable)} comparable iterations."
    if ratio >= 1.25:
        return f"Higher overall and non-monotonic across the last {len(comparable)} comparable iterations."
    return f"Mixed across the last {len(comparable)} comparable iterations."


def _latest_with(records: list[dict[str, object]], key: str) -> dict[str, object] | None:
    return next((record for record in reversed(records) if key in record), None)


def _timing_summary(model_dir: Path, run_started_epoch: float | None) -> dict[str, object] | None:
    path = model_dir / "TIMING"
    if not _current_for_run(path, run_started_epoch):
        return None
    matches = TIMING_GIT_RE.findall(_read_text(path))
    if not matches:
        return None
    elapsed = _finite(matches[-1][0])
    cpu = _finite(matches[-1][1])
    if elapsed is None or cpu is None:
        return None
    return {
        "elapsed_seconds": elapsed,
        "cpu_seconds": cpu,
        "elapsed": _format_duration(elapsed),
        "cpu": _format_duration(cpu),
    }


def _summary_cards(
    model_dir: Path,
    records: list[dict[str, object]],
    requested: int | None,
    run_started_epoch: float | None,
) -> list[dict[str, str]]:
    if not records:
        return []
    cards: list[dict[str, str]] = []
    last = records[-1]
    iteration_value = str(len(records))
    if requested is not None:
        iteration_value = f"{len(records)} / {requested}"
    cards.append(
        {
            "label": "Iterations recorded",
            "value": iteration_value,
            "detail": f"Global iteration {records[0]['global_iteration']} → {last['global_iteration']}",
        }
    )

    solver_record = _latest_with(records, "solver_maximum_change")
    if solver_record is not None:
        solver_values = [
            float(record["solver_maximum_change"])
            for record in records
            if "solver_maximum_change" in record
        ]
        cards.append(
            {
                "label": "Latest solver maximum change",
                "value": format_number(solver_record["solver_maximum_change"]),
                "detail": (
                    f"Best in this run: {format_number(min(solver_values))}. "
                    f"{_solver_direction(records)}"
                ),
            }
        )

    luminosity_record = _latest_with(records, "luminosity_difference_percent")
    if luminosity_record is not None:
        cards.append(
            {
                "label": "Latest luminosity difference",
                "value": _format_signed_percent(
                    float(luminosity_record["luminosity_difference_percent"])
                ),
                "detail": (
                    f"Generated {format_number(luminosity_record['luminosity_generated'])}; "
                    f"target {format_number(luminosity_record['luminosity_target'])}."
                ),
            }
        )

    increase_record = _latest_with(records, "maximum_increase_percent")
    decrease_record = _latest_with(records, "maximum_decrease_percent")
    if increase_record is not None or decrease_record is not None:
        values: list[str] = []
        details: list[str] = []
        if increase_record is not None:
            values.append(f"+{format_number(increase_record['maximum_increase_percent'])}%")
            details.append(f"increase at depth {increase_record['maximum_increase_depth']}")
        if decrease_record is not None:
            values.append(f"−{format_number(decrease_record['maximum_decrease_percent'])}%")
            details.append(f"decrease at depth {decrease_record['maximum_decrease_depth']}")
        cards.append(
            {
                "label": "Latest population corrections",
                "value": " / ".join(values),
                "detail": "; ".join(details).capitalize() + ".",
            }
        )

    spectrum_record = _latest_with(records, "spectrum_latest_change_percent")
    if spectrum_record is not None:
        cards.append(
            {
                "label": "Latest full-spectrum change",
                "value": f"{format_number(spectrum_record['spectrum_latest_change_percent'])}%",
                "detail": f"Recorded at global iteration {spectrum_record['global_iteration']}.",
            }
        )

    timing = _timing_summary(model_dir, run_started_epoch)
    if timing is not None:
        cards.append(
            {
                "label": "Recorded runtime",
                "value": str(timing["elapsed"]),
                "detail": f"Accumulated CPU time {timing['cpu']}.",
            }
        )
    return cards


def _trace(
    records: list[dict[str, object]],
    key: str,
    name: str,
    color: str,
    *,
    dash: str | None = None,
) -> dict[str, object] | None:
    selected = [
        record
        for record in records
        if key in record and float(record[key]) > 0 and math.isfinite(float(record[key]))
    ]
    if not selected:
        return None
    line: dict[str, object] = {"color": color, "width": 2}
    if dash:
        line["dash"] = dash
    return {
        "type": "scatter",
        "mode": "lines+markers",
        "name": name,
        "x": [record["global_iteration"] for record in selected],
        "y": [record[key] for record in selected],
        "customdata": [record["run_iteration"] for record in selected],
        "line": line,
        "marker": {"size": 6},
        "hovertemplate": (
            "Global iteration %{x}<br>Run iteration %{customdata}<br>"
            + name
            + "=%{y:.6g}<extra></extra>"
        ),
    }


def _convergence_plots(records: list[dict[str, object]]) -> list[dict[str, object]]:
    plots: list[dict[str, object]] = []
    correction_traces = [
        trace
        for trace in (
            _trace(records, "solver_maximum_change", "Solver maximum change", "#0b7285"),
            _trace(records, "maximum_increase_percent", "Maximum increase (%)", "#d94801"),
            _trace(records, "maximum_decrease_percent", "Maximum decrease (%)", "#6741d9"),
            _trace(
                records,
                "spectrum_latest_change_percent",
                "Full-spectrum change (%)",
                "#2b8a3e",
                dash="dot",
            ),
        )
        if trace is not None
    ]
    lambda_records = [
        record
        for record in records
        if record.get("lambda_iteration") and "solver_maximum_change" in record
    ]
    if lambda_records:
        correction_traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "name": "Lambda iteration",
                "x": [record["global_iteration"] for record in lambda_records],
                "y": [record["solver_maximum_change"] for record in lambda_records],
                "marker": {"symbol": "diamond", "size": 11, "color": "#e03131"},
                "hovertemplate": "Lambda iteration %{x}<br>Solver change=%{y:.6g}<extra></extra>",
            }
        )
    if correction_traces and any(len(trace.get("x", [])) >= 2 for trace in correction_traces):
        plots.append(
            {
                "title": "Iteration correction history",
                "data": correction_traces,
                "layout": {
                    "template": "plotly_white",
                    "height": 370,
                    "margin": {"l": 66, "r": 24, "t": 18, "b": 54},
                    "xaxis": {"title": {"text": "Global iteration"}, "showgrid": True},
                    "yaxis": {
                        "title": {"text": "Reported change magnitude"},
                        "type": "log",
                        "showgrid": True,
                    },
                    "legend": {"orientation": "h", "y": -0.24},
                    "hovermode": "closest",
                },
                "config": {
                    "responsive": True,
                    "displaylogo": False,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                },
                "default_x_scale": "linear",
                "default_y_scale": "log",
            }
        )

    luminosity_records = [
        record for record in records if "luminosity_difference_percent" in record
    ]
    if len(luminosity_records) >= 2:
        plots.append(
            {
                "title": "Luminosity difference history",
                "data": [
                    {
                        "type": "scatter",
                        "mode": "lines+markers",
                        "name": "Luminosity difference",
                        "x": [record["global_iteration"] for record in luminosity_records],
                        "y": [record["luminosity_difference_percent"] for record in luminosity_records],
                        "customdata": [record["run_iteration"] for record in luminosity_records],
                        "line": {"color": "#c2255c", "width": 2},
                        "marker": {"size": 6},
                        "hovertemplate": (
                            "Global iteration %{x}<br>Run iteration %{customdata}<br>"
                            "Difference=%{y:+.6g}%<extra></extra>"
                        ),
                    }
                ],
                "layout": {
                    "template": "plotly_white",
                    "height": 370,
                    "margin": {"l": 66, "r": 24, "t": 18, "b": 54},
                    "xaxis": {"title": {"text": "Global iteration"}, "showgrid": True},
                    "yaxis": {
                        "title": {"text": "Generated − target (%)"},
                        "showgrid": True,
                        "zeroline": True,
                        "zerolinecolor": "#495057",
                    },
                    "showlegend": False,
                    "hovermode": "closest",
                },
                "config": {
                    "responsive": True,
                    "displaylogo": False,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                },
                "default_x_scale": "linear",
                "default_y_scale": "linear",
            }
        )
    return plots


def _parse_run_started_epoch(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        return datetime.strptime(started_at, "%d-%b-%Y %H:%M:%S").astimezone().timestamp()
    except ValueError:
        return None


def _current_for_run(path: Path, run_started_epoch: float | None) -> bool:
    if not path.is_file():
        return False
    if run_started_epoch is None:
        return True
    try:
        return path.stat().st_mtime + 2.0 >= run_started_epoch
    except OSError:
        return False


def _correction_summary(
    model_dir: Path,
    run_started_epoch: float | None,
) -> dict[str, object]:
    path = model_dir / "CORRECTION_SUM"
    if not path.is_file():
        return {"available": False}
    current = _current_for_run(path, run_started_epoch)
    result: dict[str, object] = {"available": True, "current": current, "path": "CORRECTION_SUM"}
    if not current:
        return result
    lines = _read_text(path).splitlines()
    nt = next(
        (int(match.group(1)) for line in lines if (match := NT_RE.search(line))),
        None,
    )
    header_index: int | None = None
    labels: list[str] = []
    for index, line in enumerate(lines):
        match = CORRECTION_HEADER_RE.match(line)
        if match:
            header_index = index
            labels = match.group(1).split()
            break
    rows: list[tuple[int, list[int]]] = []
    if header_index is not None:
        for line in lines[header_index + 1 :]:
            tokens = line.split()
            if len(tokens) != len(labels) + 1 or not all(token.isdigit() for token in tokens):
                continue
            rows.append((int(tokens[0]), [int(token) for token in tokens[1:]]))
    selected: list[dict[str, object]] = []
    for wanted in ("1.0%", "0.1%", "0.01%"):
        if wanted not in labels or not rows:
            continue
        column = labels.index(wanted)
        maximum = max(values[column] for _depth, values in rows)
        depths = [depth for depth, values in rows if values[column] == maximum and maximum > 0]
        selected.append(
            {
                "threshold": wanted,
                "maximum_count": maximum,
                "depth": depths[0] if depths else None,
                "nonzero_depths": sum(values[column] > 0 for _depth, values in rows),
            }
        )
    result.update({"nt": nt, "depth_rows": len(rows), "thresholds": selected})
    return result


def _warning_summary(
    model_dir: Path,
    run_text: str,
    run_started_epoch: float | None,
) -> list[dict[str, object]]:
    groups: list[dict[str, object]] = []
    boundary_matches = re.findall(
        r"J\(mom\) and J\(ray\) differ by more than\s+(\d+)%",
        run_text,
        flags=re.IGNORECASE,
    )
    if boundary_matches:
        groups.append(
            {
                "label": "Outer-boundary radiation discrepancy",
                "detail": (
                    f"Reported in {len(boundary_matches)} iteration(s); largest stated threshold "
                    f"was {max(int(value) for value in boundary_matches)}%."
                ),
                "path": "OUTGEN",
                "level": "warning",
            }
        )
    if re.search(r"bad oscillator strengths", run_text, flags=re.IGNORECASE):
        groups.append(
            {
                "label": "Oscillator-strength warning",
                "detail": "OUTGEN reports at least one suspect oscillator-strength entry.",
                "path": "OUTGEN",
                "level": "warning",
            }
        )

    warnings_path = model_dir / "WARNINGS"
    if not _current_for_run(warnings_path, run_started_epoch):
        return groups
    warnings = _read_text(warnings_path)
    if "Max. cont. freq may be too small" in warnings:
        groups.append(
            {
                "label": "Continuum frequency range",
                "detail": "WARNINGS says the maximum continuum frequency may be too small while X-rays are present.",
                "path": "WARNINGS",
                "level": "warning",
            }
        )
    ion_matches = re.findall(
        r"^\s*(\S+)\s+may need to be included in the model\s*\(IF\s*~\s*([^)]*)\)",
        warnings,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if ion_matches:
        ions: dict[str, str] = {}
        for ion, fraction in ion_matches:
            ions[ion] = fraction.strip()
        groups.append(
            {
                "label": "Potentially omitted ion stages",
                "detail": ", ".join(f"{ion} (IF ~ {fraction})" for ion, fraction in ions.items()),
                "path": "WARNINGS",
                "level": "warning",
            }
        )
    weak_matches = re.findall(
        r"Warning\*+\s*---\s*(\d+) weak transitions cut .*?---\s*(\S+)",
        warnings,
        flags=re.IGNORECASE,
    )
    if weak_matches:
        total = sum(int(count) for count, _source in weak_matches)
        source_label = "oscillator file" if len(weak_matches) == 1 else "oscillator files"
        groups.append(
            {
                "label": "Weak transitions cut",
                "detail": f"{total:,} transitions across {len(weak_matches)} {source_label}.",
                "path": "WARNINGS",
                "level": "info",
            }
        )
    format_warnings = set(
        re.findall(r"Warning -- FORMAT Date not found in oscilator file:(\S+)", warnings)
    )
    if format_warnings:
        groups.append(
            {
                "label": "Atomic-data format metadata",
                "detail": "Missing FORMAT dates: " + ", ".join(sorted(format_warnings)) + ".",
                "path": "WARNINGS",
                "level": "info",
            }
        )
    return groups


def inspect_model_convergence(
    model_dir: Path,
    *,
    outgen_path: Path | None = None,
) -> dict[str, object]:
    """Summarize the latest appended OUTGEN run and its current diagnostics."""
    outgen = outgen_path if outgen_path is not None else model_dir / "OUTGEN"
    if not outgen.is_file():
        return {
            "available": False,
            "source_path": "OUTGEN",
            "diagnostic_links": [],
        }
    text, truncated = _read_limited_tail(outgen, MAX_OUTGEN_BYTES)
    runs = _run_segments(text)
    if not runs:
        return {
            "available": True,
            "has_iterations": False,
            "source_path": "OUTGEN",
            "message": "OUTGEN is empty or has no readable run data.",
            "diagnostic_links": ["OUTGEN"],
        }
    started_at, run_text = runs[-1]
    records = _parse_iteration_records(run_text)
    started_epoch = _parse_run_started_epoch(started_at)
    requested = _requested_iterations(model_dir)
    return {
        "available": True,
        "has_iterations": bool(records),
        "source_path": "OUTGEN",
        "started_at": started_at,
        "run_count": len(runs),
        "run_count_is_lower_bound": truncated,
        "requested_iterations": requested,
        "iterations": records,
        "cards": _summary_cards(model_dir, records, requested, started_epoch),
        "plots": _convergence_plots(records),
        "correction_summary": _correction_summary(model_dir, started_epoch),
        "warnings": _warning_summary(model_dir, run_text, started_epoch),
        "diagnostic_links": [
            name
            for name in ("OUTGEN", "CORRECTION_SUM", "WARNINGS", "TIMING")
            if (model_dir / name).is_file()
        ],
        "message": (
            "No iteration markers have been recorded in the latest OUTGEN run yet."
            if not records
            else ""
        ),
    }
