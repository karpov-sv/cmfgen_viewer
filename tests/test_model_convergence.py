from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmfgen_viewer.model_convergence import inspect_model_convergence
from cmfgen_viewer.parsers.outgen import parse_outgen


def _write_run(model: Path) -> None:
    model.mkdir()
    (model / "IN_ITS").write_text("3 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Model started on: 01-Jan-2026 00:00:00\n"
        "Current great iteration count is 10\n"
        "Maximm changes as returned by SOLVEBA_V9 is 9.0E-01\n"
        "Model started on: 02-Jan-2026 00:00:00\n"
        "Current great iteration count is 20\n"
        "Luminosity of star (d=1,ND)(iteration 20) is: 9.0E+04 1.0E+05\n"
        "Spectrum convergence information -- % changes\n"
        "Largest % change in spectrum for last 5 full iterations - last listed first\n"
        " 4.0E-01 3.0E-01 2.0E-01\n"
        "BA matrix computed\n"
        "Maximum % increase at depth 4 is 2.0E-01 (BA computed) --- iteration 20\n"
        "Maximum % decrease at depth 5 is 3.0E-01 (BA computed) --- iteration 20\n"
        "Maximm changes as returned by SOLVEBA_V13 is 4.0E-01\n"
        "Current great iteration count is 21\n"
        "LAMBDA iteration used\n"
        "Temperature held fixed at all depths.\n"
        "Maximum % increase at depth 6 is 3.0E+00 (LAMBDA) --- iteration 21\n"
        "Maximum % decrease at depth 7 is 2.0E+00 (LAMBDA) --- iteration 21\n"
        "Maximm changes as returned by SOLVEBA_V13 is 1.0E+00\n"
        "Current great iteration count is 23\n"
        "Luminosity of star (d=1,ND)(iteration 23) is: 9.8E+04 1.0E+05\n"
        "BA matrix **NOT** computed\n"
        "Maximum % increase at depth 8 is 8.0E-02 (BA not computed) --- iteration 23\n"
        "Maximum % decrease at depth 9 is 7.0E-02 (BA not computed) --- iteration 23\n"
        "Maximm changes as returned by SOLVEBA_V13 is 2.0E-01\n"
        "Error --- J(mom) and J(ray) differ by more than 20% for last frequency\n",
        encoding="utf-8",
    )
    (model / "CORRECTION_SUM").write_text(
        "Summary of changes at each depth\n"
        "NT= 100\n"
        "Depth 100.0% 10.0% 1.0% 0.1% 0.01% 0.001% 0.0001%\n"
        "1 0 0 0 0 2 10 90\n"
        "2 0 0 1 3 5 20 95\n",
        encoding="utf-8",
    )
    (model / "WARNINGS").write_text(
        "***Warning**** --- 12 weak transitions cut in GENOSC_V9 --- FeIV_F_OSCDAT\n"
        "Max. cont. freq may be too small in in SET_X_FREQ_V2\n"
        "FeVIII may need to be included in the model (IF ~ 1.0E-03)\n"
        "Warning -- FORMAT Date not found in oscilator file:HI_F_OSCDAT\n",
        encoding="utf-8",
    )
    (model / "TIMING").write_text(
        "GIT 100.0 350.0\nGIT 125.0 400.0\n",
        encoding="utf-8",
    )


def test_latest_outgen_run_builds_convergence_cards_and_plots(tmp_path: Path) -> None:
    model = tmp_path / "model"
    _write_run(model)

    state = inspect_model_convergence(model)

    assert state["available"] is True
    assert state["has_iterations"] is True
    assert state["run_count"] == 2
    assert state["started_at"] == "02-Jan-2026 00:00:00"
    assert [record["global_iteration"] for record in state["iterations"]] == [20, 21, 23]
    assert [record["run_iteration"] for record in state["iterations"]] == [1, 2, 3]
    assert state["iterations"][1]["lambda_iteration"] is True
    assert state["iterations"][1]["temperature_fixed"] is True
    assert state["iterations"][2]["ba_computed"] is False

    cards = {card["label"]: card for card in state["cards"]}
    assert cards["Iterations recorded"]["value"] == "3 / 3"
    assert cards["Latest solver maximum change"]["value"] == "0.2"
    assert "Decreasing across the last 2 non-lambda iterations" in cards[
        "Latest solver maximum change"
    ]["detail"]
    assert cards["Latest luminosity difference"]["value"] == "-2%"
    assert cards["Latest population corrections"]["value"] == "+0.08% / −0.07%"
    assert cards["Latest full-spectrum change"]["value"] == "0.4%"
    assert cards["Recorded runtime"]["value"] == "00:02:05"
    assert cards["Recorded runtime"]["detail"] == "Accumulated CPU time 00:06:40."

    assert [plot["title"] for plot in state["plots"]] == [
        "Iteration correction history",
        "Luminosity difference history",
    ]
    correction_plot = state["plots"][0]
    solver_trace = next(
        trace for trace in correction_plot["data"] if trace["name"] == "Solver maximum change"
    )
    assert solver_trace["x"] == [20, 21, 23]
    assert solver_trace["y"] == [0.4, 1.0, 0.2]
    assert any(trace["name"] == "Lambda iteration" for trace in correction_plot["data"])


def test_outgen_parser_exposes_shared_convergence_analysis(tmp_path: Path) -> None:
    model = tmp_path / "model"
    _write_run(model)

    parsed = parse_outgen(model / "OUTGEN")

    assert parsed["parser"] == "OUTGEN"
    summary = dict(parsed["summary_table"]["rows"])
    assert summary["latest_run_started"] == "02-Jan-2026 00:00:00"
    assert summary["iteration_records"] == "3"
    assert summary["requested_iterations"] == "3"
    assert summary["global_iteration_range"] == "20 .. 23"
    assert [plot["title"] for plot in parsed["plots"]] == [
        "Iteration correction history",
        "Luminosity difference history",
    ]
    assert parsed["default_plot_mode"] == "separate"
    assert parsed["plots"][0]["default_y_scale"] == "log"
    assert parsed["plots"][1]["default_y_scale"] == "linear"

    tables = {table["title"]: table for table in parsed["tables"]}
    overview = tables["Latest-run convergence overview"]
    overview_rows = {row[0]: row[1:] for row in overview["rows"]}
    assert overview_rows["Latest solver maximum change"][0] == "0.2"
    assert overview_rows["Latest luminosity difference"][0] == "-2%"

    iterations = tables["Latest-run iteration diagnostics"]
    assert len(iterations["rows"]) == 3
    assert iterations["rows"][1][0:2] == ["2", "21"]
    assert "lambda" in iterations["rows"][1][-1]
    assert tables["Current CORRECTION_SUM thresholds"]["rows"][0] == [
        "1.0%",
        "1",
        "2",
        "1",
    ]
    assert any(
        row[1] == "Potentially omitted ion stages"
        for row in tables["Grouped run diagnostics"]["rows"]
    )


def test_correction_and_warning_summaries_are_compact_and_grouped(tmp_path: Path) -> None:
    model = tmp_path / "model"
    _write_run(model)

    state = inspect_model_convergence(model)

    correction = state["correction_summary"]
    assert correction["current"] is True
    assert correction["nt"] == 100
    assert correction["depth_rows"] == 2
    by_threshold = {item["threshold"]: item for item in correction["thresholds"]}
    assert by_threshold["1.0%"]["maximum_count"] == 1
    assert by_threshold["1.0%"]["depth"] == 2
    assert by_threshold["0.1%"]["maximum_count"] == 3

    warnings = {item["label"]: item for item in state["warnings"]}
    assert warnings["Outer-boundary radiation discrepancy"]["path"] == "OUTGEN"
    assert warnings["Continuum frequency range"]["path"] == "WARNINGS"
    assert "FeVIII" in warnings["Potentially omitted ion stages"]["detail"]
    assert warnings["Weak transitions cut"]["detail"] == (
        "12 transitions across 1 oscillator file."
    )
    assert "HI_F_OSCDAT" in warnings["Atomic-data format metadata"]["detail"]


def test_auxiliary_diagnostics_are_ignored_when_they_predate_latest_run(
    tmp_path: Path,
) -> None:
    model = tmp_path / "model"
    _write_run(model)
    (model / "OUTGEN").write_text(
        "Model started on: 02-Jan-2035 00:00:00\n"
        "Current great iteration count is 1\n"
        "Maximm changes as returned by SOLVEBA_V13 is 5.0E-01\n",
        encoding="utf-8",
    )
    old_epoch = 1_700_000_000
    for name in ("CORRECTION_SUM", "WARNINGS", "TIMING"):
        os.utime(model / name, (old_epoch, old_epoch))

    state = inspect_model_convergence(model)

    assert state["correction_summary"] == {
        "available": True,
        "current": False,
        "path": "CORRECTION_SUM",
    }
    assert state["warnings"] == []
    assert "Recorded runtime" not in {card["label"] for card in state["cards"]}


@pytest.mark.parametrize(
    ("contents", "available", "has_iterations"),
    [
        (None, False, None),
        ("", True, False),
        ("Current great iteration count is 4\n", True, True),
    ],
)
def test_missing_empty_and_markerless_outgen_are_handled(
    tmp_path: Path,
    contents: str | None,
    available: bool,
    has_iterations: bool | None,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    if contents is not None:
        (model / "OUTGEN").write_text(contents, encoding="utf-8")

    state = inspect_model_convergence(model)

    assert state["available"] is available
    if has_iterations is not None:
        assert state["has_iterations"] is has_iterations
    if contents == "Current great iteration count is 4\n":
        assert state["run_count"] == 1
        assert state["iterations"][0]["global_iteration"] == 4
