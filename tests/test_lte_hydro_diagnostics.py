from __future__ import annotations

import os
from pathlib import Path

from cmfgen_viewer.lte_hydro_diagnostics import (
    inspect_lte_diagnostics,
    inspect_wind_hyd_diagnostics,
)
from cmfgen_viewer.parsers.lte_hydro_logs import parse_outlte, parse_wind_hyd


def _write_lte_inputs(lte: Path) -> None:
    lte.mkdir()
    for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS"):
        (lte / name).write_text(f"input {name}\n", encoding="utf-8")


def _make_newer(path: Path, dependencies: tuple[Path, ...]) -> None:
    newest = max(item.stat().st_mtime_ns for item in dependencies)
    os.utime(path, ns=(newest + 1_000_000, newest + 1_000_000))


def test_lte_summary_combines_progress_results_timing_and_diagnostics(tmp_path: Path) -> None:
    lte = tmp_path / "lte"
    _write_lte_inputs(lte)
    (lte / "OUTLTE").write_text(
        "Warning in GENOSC_V9 -- bad oscillator strengths?\n"
        "Warning from SET_FREQUENCY_GRID\n"
        "DELTA_ED= 7.5D-01\n"
        "DELTA_T= 1.25D-01\n"
        "Beginning loop over frequencies for all grid points.\n"
        "Number of frequencies is 2000\n",
        encoding="utf-8",
    )
    (lte / "ML_COUNTER").write_text("ML= 500\nML= 1500\n", encoding="utf-8")
    (lte / "ltebat.log").write_text(
        "Program started on:\n01-Jan-2026 10:00:00\n"
        "Note: The following floating-point exceptions are signalling: IEEE_UNDERFLOW_FLAG\n"
        "Program finished on:\n01-Jan-2026 10:02:00\n",
        encoding="utf-8",
    )
    (lte / "TIMING").write_text("GIT 120.0 480.0\n", encoding="utf-8")
    result = lte / "ROSSELAND_LTE_TAB"
    result.write_text("result\n", encoding="utf-8")
    _make_newer(
        result,
        tuple(lte / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh")),
    )

    state = inspect_lte_diagnostics(lte)

    assert state["status"] == "ready"
    assert state["frequency_current"] == 1500
    assert state["frequency_total"] == 2000
    assert state["frequency_percent"] == 75.0
    assert state["delta_ed"] == 0.75
    assert state["delta_t"] == 0.125
    cards = {card["label"]: card for card in state["cards"]}
    assert cards["Frequency integration"]["value"] == "1,500 / 2,000"
    assert cards["Batch markers"]["value"] == "Finished"
    assert cards["Recorded LTE timing"]["value"] == "120 s elapsed"
    diagnostics = {item["label"]: item for item in state["diagnostics"]}
    assert diagnostics["Atomic-data notices"]["level"] == "warning"
    assert diagnostics["Frequency-grid notices"]["level"] == "info"
    assert diagnostics["Floating-point flags"]["path"] == "ltebat.log"

    parsed = parse_outlte(lte / "OUTLTE")
    assert parsed["parser"] == "OUTLTE"
    assert dict(parsed["summary_table"]["rows"])["frequency_percent"] == "75.0"
    assert {table["title"] for table in parsed["tables"]} == {
        "Run overview",
        "Grouped diagnostics",
    }


def test_current_fatal_outlte_blocks_an_apparently_current_result(tmp_path: Path) -> None:
    lte = tmp_path / "lte"
    _write_lte_inputs(lte)
    result = lte / "ROSSELAND_LTE_TAB"
    result.write_text("previous result\n", encoding="utf-8")
    _make_newer(
        result,
        tuple(lte / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh")),
    )
    outlte = lte / "OUTLTE"
    outlte.write_text(
        "Beginning loop over frequencies\nFortran runtime error: End of file\nBacktrace for this error:\n",
        encoding="utf-8",
    )
    _make_newer(
        outlte,
        tuple(lte / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh")),
    )

    state = inspect_lte_diagnostics(lte)

    assert state["result_current"] is True
    assert state["fatal"] is True
    assert state["status"] == "failed"
    assert state["diagnostics"][0]["level"] == "danger"


def test_wind_hyd_summary_extracts_final_quantities_and_failure_state(tmp_path: Path) -> None:
    lte = tmp_path / "lte"
    _write_lte_inputs(lte)
    (lte / "ROSSELAND_LTE_TAB").write_text("lte result\n", encoding="utf-8")
    log = lte / "WIND_HYD"
    log.write_text(
        "Transition radius is 128.88\n"
        "Transition velocity is 11.47\n"
        "Mass of star is: 48.73\n"
        "New effective temperature is: 3.9\n"
        "Eddington parameter is: 0.313\n"
        "Old reference radius is 127.4621\n"
        "Desired reference radius is 127.4619\n",
        encoding="utf-8",
    )
    result = lte / "RVSIG_COL_NEW"
    result.write_text("new structure\n", encoding="utf-8")
    dependencies = (lte / "ROSSELAND_LTE_TAB", lte / "HYDRO_PARAMS")
    _make_newer(log, dependencies)
    _make_newer(result, dependencies)

    state = inspect_wind_hyd_diagnostics(lte)

    assert state["status"] == "ready"
    cards = {card["label"]: card for card in state["cards"]}
    assert cards["Final reference-radius difference"]["value"] == "+0.0001569%"
    assert cards["Wind transition"]["value"] == "R 128.88 / V 11.47 km/s"
    scalars = {item["label"]: item["value"] for item in state["scalars"]}
    assert scalars["Eddington parameter"] == "0.313"

    parsed = parse_wind_hyd(log)
    assert parsed["parser"] == "WIND_HYD"
    assert "Latest reported quantities" in {table["title"] for table in parsed["tables"]}

    log.write_text("Fortran runtime error: bad input\n", encoding="utf-8")
    _make_newer(log, dependencies)
    failed = inspect_wind_hyd_diagnostics(lte)
    assert failed["status"] == "failed"
    assert failed["fatal"] is True


def test_missing_wind_hyd_log_explains_legacy_result(tmp_path: Path) -> None:
    lte = tmp_path / "lte"
    _write_lte_inputs(lte)
    (lte / "RVSIG_COL_NEW").write_text("legacy result\n", encoding="utf-8")

    state = inspect_wind_hyd_diagnostics(lte)

    assert state["available"] is False
    assert state["links"] == ["RVSIG_COL_NEW"]
    assert "older runs" in state["message"]
