from pathlib import Path
import os

import pytest

from cmfgen_viewer.native_diagnostics import analyze_main_diagnostics
from cmfgen_viewer.model_run_diagnostics import diagnose_main_run


OPTICAL = (
    "This model does not extend sufficiently deeply to guarantee the accuracy of\n"
    " the inner boundary condition. You need to adjust you model so that the\n"
    " minimum optical depth is 50, and preferably 100\n"
)
FLUX = (
    "You have poor flux accuracy in the inner region of the model\n"
    "You should restart you model changing the input options or input files\n"
    "Some normalized luminosities are out by a factor of 2\n"
    "You should check OBSFLUX\n"
)


@pytest.mark.parametrize("text,code", [(OPTICAL, "inner_optical_depth"), (FLUX, "inner_flux_accuracy")])
def test_known_stops_explain_zero_exit_and_recovery(tmp_path, text, code):
    (tmp_path / "VADAT").write_text("F [IT_ON_T]\n")
    findings = analyze_main_diagnostics(tmp_path, {"OUTGEN": text, "process.log": text})
    assert len(findings) == 1
    finding = findings[0]
    assert finding["code"] == code and finding["severity"] == "error"
    assert "exit code 0" in finding["message"]
    assert "native default" in finding["message"]
    assert finding["evidence"] and finding["suggestions"]
    assert finding["links"] == ["VADAT"]
    if code == "inner_flux_accuracy":
        assert any("IT_ON_T=T" in hint for hint in finding["suggestions"])


@pytest.mark.parametrize("controls,completed", [
    ("F [STOP_IF_MW]\n", False), ("T [STOP_IF_MW]\n", True),
    ("T [STOP_IF_MW]\nF [STOP_IF_MW]\n", False),
])
def test_disabled_ambiguous_or_completed_safeguards_are_warnings(tmp_path, controls, completed):
    (tmp_path / "VADAT").write_text(controls)
    assert analyze_main_diagnostics(tmp_path, {"OUTGEN": FLUX}, completed=completed)[0]["severity"] == "warning"


def test_ordinary_warnings_and_25_percent_warning_do_not_become_stops(tmp_path):
    assert analyze_main_diagnostics(tmp_path, {"OUTGEN": "Warning - core radius not identical in REGRIDWSC\nError opening POINT1 in SCR_READ\n"}) == []
    findings = analyze_main_diagnostics(tmp_path, {"OUTGEN": "You have poor flux accuracy in the inner region of the model\nSome normalized luminosities are out by 25%\n"})
    assert len(findings) == 1 and findings[0]["severity"] == "warning"
    assert "does not stop" in findings[0]["message"]


def test_optical_depth_uses_current_meanopac_and_ignores_stale_table(tmp_path):
    (tmp_path / "OUTGEN").write_text(OPTICAL)
    meanopac = tmp_path / "MEANOPAC"
    meanopac.write_text("R I Tau(Ross)\n1 1 3.749D0 " + "0 " * 12 + "\n")
    finding = analyze_main_diagnostics(tmp_path, {"OUTGEN": OPTICAL})[0]
    assert "3.749" in finding["message"] and "MEANOPAC" in finding["links"]
    os.utime(meanopac, (1, 1))
    assert "3.749" not in analyze_main_diagnostics(tmp_path, {"OUTGEN": OPTICAL})[0]["message"]


def test_web_classifies_native_stop_instead_of_generic_missing_outputs(tmp_path):
    (tmp_path / "VADAT").write_text("T [IT_ON_T]\n")
    (tmp_path / "OUTGEN").write_text(FLUX + "\n" + "Later bookkeeping\n" * 30)
    result = diagnose_main_run(tmp_path)
    assert result["status"] == "failed"
    assert result["findings"][0]["code"] == "inner_flux_accuracy"
    assert "luminosity" in result["summary"]
    assert any("current value: T" in suggestion for suggestion in result["findings"][0]["suggestions"])
    assert diagnose_main_run(tmp_path, active=True)["status"] == "running"


def test_web_does_not_use_older_wrapper_failure_or_completed_warning(tmp_path):
    log = tmp_path / "batch.log"
    log.write_text(FLUX)
    os.utime(log, (1, 1))
    (tmp_path / "OUTGEN").write_text("new successful invocation\n")
    (tmp_path / "MOD_SUM").write_text("Model Finalized on: today\n")
    (tmp_path / "RVTJ").write_text("current vectors\n")
    assert diagnose_main_run(tmp_path)["status"] == "succeeded"
    assert diagnose_main_run(tmp_path)["findings"] == []
    (tmp_path / "OUTGEN").write_text(FLUX)
    (tmp_path / "MOD_SUM").write_text("Model Finalized on: today\n")
    (tmp_path / "RVTJ").write_text("current vectors\n")
    result = diagnose_main_run(tmp_path)
    assert result["status"] == "succeeded" and result["findings"][0]["severity"] == "warning"


def test_appended_native_logs_only_diagnose_latest_invocation(tmp_path):
    text = "Model started on: yesterday\n" + FLUX + "Fortran runtime error: old failure\n"
    text += "Model started on: today\nNo current failure\n"
    (tmp_path / "OUTGEN").write_text(text)
    assert analyze_main_diagnostics(tmp_path, {"OUTGEN": text}) == []
    result = diagnose_main_run(tmp_path)
    assert result["status"] == "incomplete" and not result["findings"]
