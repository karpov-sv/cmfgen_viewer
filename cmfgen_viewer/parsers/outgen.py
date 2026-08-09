from __future__ import annotations

from pathlib import Path

from .common import format_number


def _record_value(record: dict[str, object], key: str, *, suffix: str = "") -> str:
    value = record.get(key)
    if value is None:
        return ""
    return f"{format_number(value)}{suffix}"


def _record_state(record: dict[str, object]) -> str:
    states: list[str] = []
    if record.get("lambda_iteration"):
        states.append("lambda")
    if record.get("temperature_fixed"):
        states.append("temperature fixed")
    if record.get("ba_computed") is True:
        states.append("BA computed")
    elif record.get("ba_computed") is False:
        states.append("BA reused")
    if record.get("grey_solution"):
        states.append("grey solution")
    return ", ".join(states)


def _iteration_rows(records: list[dict[str, object]]) -> list[list[str]]:
    return [
        [
            str(record["run_iteration"]),
            str(record["global_iteration"]),
            _record_value(record, "solver_maximum_change"),
            _record_value(record, "luminosity_difference_percent", suffix="%"),
            _record_value(record, "maximum_increase_percent", suffix="%"),
            _record_value(record, "maximum_increase_depth"),
            _record_value(record, "maximum_decrease_percent", suffix="%"),
            _record_value(record, "maximum_decrease_depth"),
            _record_value(record, "spectrum_latest_change_percent", suffix="%"),
            _record_value(record, "minimum_species_scale"),
            _record_value(record, "average_fg_calls"),
            _record_state(record),
        ]
        for record in records
    ]


def parse_outgen(path: Path) -> dict[str, object]:
    """Build a structured view of the latest appended CMFGEN run."""
    # Imported lazily to keep the parser registry independent from the workflow
    # module while both views share exactly the same convergence analysis.
    from ..model_convergence import inspect_model_convergence

    state = inspect_model_convergence(path.parent, outgen_path=path)
    records = state.get("iterations", [])
    cards = state.get("cards", [])

    summary_rows: list[list[str]] = [
        ["latest_run_started", str(state.get("started_at") or "not recorded")],
        ["visible_run_boundaries", str(state.get("run_count", 0))],
        ["iteration_records", str(len(records))],
    ]
    requested = state.get("requested_iterations")
    if requested is not None:
        summary_rows.append(["requested_iterations", str(requested)])
    if records:
        summary_rows.append(
            [
                "global_iteration_range",
                f"{records[0]['global_iteration']} .. {records[-1]['global_iteration']}",
            ]
        )

    tables: list[dict[str, object]] = []
    if cards:
        tables.append(
            {
                "title": "Latest-run convergence overview",
                "columns": ["Metric", "Value", "Context"],
                "rows": [
                    [str(card["label"]), str(card["value"]), str(card["detail"])]
                    for card in cards
                ],
            }
        )
    if records:
        tables.append(
            {
                "title": "Latest-run iteration diagnostics",
                "columns": [
                    "Run iteration",
                    "Global iteration",
                    "Solver max change",
                    "Luminosity difference",
                    "Max increase",
                    "Increase depth",
                    "Max decrease",
                    "Decrease depth",
                    "Spectrum change",
                    "Min species scale",
                    "Average FG calls",
                    "State",
                ],
                "rows": _iteration_rows(records),
            }
        )

    correction = state.get("correction_summary", {})
    if correction.get("available") and correction.get("current") and correction.get("thresholds"):
        tables.append(
            {
                "title": "Current CORRECTION_SUM thresholds",
                "columns": ["Threshold", "Maximum count", "Depth", "Affected depths"],
                "rows": [
                    [
                        str(item["threshold"]),
                        str(item["maximum_count"]),
                        str(item["depth"] or "-"),
                        str(item["nonzero_depths"]),
                    ]
                    for item in correction["thresholds"]
                ],
            }
        )

    diagnostics = state.get("warnings", [])
    if diagnostics:
        tables.append(
            {
                "title": "Grouped run diagnostics",
                "columns": ["Level", "Diagnostic", "Source", "Detail"],
                "rows": [
                    [
                        str(item["level"]),
                        str(item["label"]),
                        str(item["path"]),
                        str(item["detail"]),
                    ]
                    for item in diagnostics
                ],
            }
        )

    parser_warnings: list[str] = []
    message = str(state.get("message") or "")
    if message:
        parser_warnings.append(message)
    if state.get("run_count_is_lower_bound"):
        parser_warnings.append(
            "Only the retained OUTGEN tail was parsed; the visible run-boundary count is a lower bound."
        )
    if correction.get("available") and not correction.get("current"):
        parser_warnings.append("CORRECTION_SUM predates the latest recorded run and was not summarized.")

    return {
        "parser": "OUTGEN",
        "title": "OUTGEN latest-run convergence diagnostics",
        "summary_table": {
            "title": "Latest appended run",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": tables,
        "plots": state.get("plots", []),
        "default_plot_mode": "separate",
        "warnings": parser_warnings,
    }
