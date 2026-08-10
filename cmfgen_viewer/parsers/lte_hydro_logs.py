from __future__ import annotations

from pathlib import Path


def _diagnostic_tables(state: dict[str, object]) -> list[dict[str, object]]:
    tables: list[dict[str, object]] = []
    cards = state.get("cards", [])
    if cards:
        tables.append(
            {
                "title": "Run overview",
                "columns": ["Metric", "Value", "Context"],
                "rows": [
                    [str(card["label"]), str(card["value"]), str(card["detail"])]
                    for card in cards
                ],
            }
        )
    scalars = state.get("scalars", [])
    if scalars:
        tables.append(
            {
                "title": "Latest reported quantities",
                "columns": ["Quantity", "Value", "Unit"],
                "rows": [
                    [str(item["label"]), str(item["value"]), str(item["unit"])]
                    for item in scalars
                ],
            }
        )
    diagnostics = state.get("diagnostics", [])
    if diagnostics:
        tables.append(
            {
                "title": "Grouped diagnostics",
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
    return tables


def _parser_warnings(state: dict[str, object]) -> list[str]:
    warnings: list[str] = []
    message = str(state.get("message") or "")
    if message:
        warnings.append(message)
    if state.get("source_truncated"):
        warnings.append("The structured view uses bounded head/tail reads; use Raw mode for intervening output.")
    return warnings


def _display(value: object, fallback: str = "n/a") -> str:
    return str(value) if value is not None else fallback


def parse_outlte(path: Path) -> dict[str, object]:
    from ..lte_hydro_diagnostics import inspect_lte_diagnostics

    state = inspect_lte_diagnostics(path.parent)
    summary_rows = [
        ["status", str(state.get("status_label") or "unknown")],
        ["frequency_current", _display(state.get("frequency_current"))],
        ["frequency_total", _display(state.get("frequency_total"))],
        ["frequency_percent", _display(state.get("frequency_percent"))],
        ["batch_started", str(state.get("started_at") or "not recorded")],
        ["batch_finished", str(state.get("finished_at") or "not recorded")],
        ["rosseland_result", "current" if state.get("result_current") else "stale or missing"],
    ]
    return {
        "parser": "OUTLTE",
        "title": "OUTLTE LTE run diagnostics",
        "summary_table": {
            "title": "LTE run summary",
            "columns": ["Field", "Value"],
            "rows": summary_rows,
        },
        "tables": _diagnostic_tables(state),
        "plots": [],
        "warnings": _parser_warnings(state),
    }


def parse_wind_hyd(path: Path) -> dict[str, object]:
    from ..lte_hydro_diagnostics import inspect_wind_hyd_diagnostics

    state = inspect_wind_hyd_diagnostics(path.parent)
    return {
        "parser": "WIND_HYD",
        "title": "WIND_HYD captured hydro run diagnostics",
        "summary_table": {
            "title": "Hydro run summary",
            "columns": ["Field", "Value"],
            "rows": [
                ["status", str(state.get("status_label") or "unknown")],
                ["generated_structure", "current" if state.get("result_current") else "stale or missing"],
            ],
        },
        "tables": _diagnostic_tables(state),
        "plots": [],
        "warnings": _parser_warnings(state),
    }
