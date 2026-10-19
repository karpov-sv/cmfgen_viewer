import os

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_convergence import inspect_model_convergence
from cmfgen_viewer.parsers.outgen import parse_outgen
from cmfgen_viewer.parsers import parse_known_file


def _model(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "VADAT").write_text("1 [RSTAR]\n")
    (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n3 [NP]\n")
    (model / "IN_ITS").write_text("3 [NUM_ITS]\n")
    (model / "OUTGEN").write_text(
        "Model started on: 01-Jan-2026 00:00:00\n"
        "Current great iteration count is 44\n"
        "LAMBDA iteration used\n"
        "Maximm changes as returned by SOLVEBA_V13 is 50\n"
        "Current great iteration count is 45\n"
        "Largest % change in spectrum for last 5 full iterations\n"
        "2.52 0.2\n"
        "Maximm changes as returned by SOLVEBA_V13 is 9.48\n"
        "Current great iteration count is 46\n"
        "Luminosity of star (iteration 46) is: 98.46 100\n"
        "Maximum % increase at depth 81 is 3.59 (BA not computed) --- iteration 46\n"
        "Maximum % decrease at depth 65 is 4.21 (BA not computed) --- iteration 46\n"
        "Maximm changes as returned by SOLVEBA_V13 is 4.07\n"
        "Possible error with hydrostatic structure --- large error in photosphere\n"
        "Mean error is 1.72\nRoot mean squared error is 5.18\nMaximum error is 26.3\n"
        "*********************\n"
    )
    (model / "J_COMP").write_text(
        "Indx Nu J(mom) J(ray) %Diff HBC_CMF J(mom) J(ray) %Diff\n"
        "1 3.49897D-3 1 1 -59.38 1 1 1 0\n"
        "2 0.6872 1 1 0.90 1 1 1 0\n"
        "3 3.104 1 1 7.17 1 1 1 0\n"
    )
    (model / "OBSFLUX").write_text(
        "Normalized luminosity check (normalized by L[ND])\n\n 0.98129 1.0\n\nNext section\n")
    (model / "MEANOPAC").write_text("R I Tau(Ross)\n2 1 0.1\n1 2 99.62\n")
    return model


def _checks(model):
    return {c["code"]: c for c in inspect_model_convergence(model)["quality"]["checks"]}


def test_quality_exposes_actual_measurements_and_separate_spectrum_iteration(tmp_path):
    model = _model(tmp_path)
    state = inspect_model_convergence(model)
    checks = _checks(model)
    assert state["quality"]["needs_review"]
    assert not state["quality"]["incomplete"]
    assert "4.07% at global iteration 46" in checks["solver_maximum_change"]["detail"]
    assert "2.52% at global iteration 45" in checks["spectrum_latest_change_percent"]["detail"]
    assert "Only 2 iteration(s)" in checks["late_lambda"]["detail"]
    assert "RMS 5.18%, maximum 26.3%" in checks["hydrostatic_balance"]["detail"]
    boundary = checks["boundary_radiation"]
    assert boundary["level"] == "warning"
    assert "59.38% at 85.68 μm" in boundary["detail"]
    assert "Optical (0.3–1 μm): 0.9%" in boundary["detail"]
    assert "not direct emergent-flux errors" in boundary["action"]
    assert "1.871% at depth 1" in checks["luminosity_depth"]["detail"]
    assert checks["luminosity_depth"]["level"] == "info"
    assert checks["inner_optical_depth"]["level"] == "info"
    assert "99.62" in checks["inner_optical_depth"]["detail"]
    assert {"J_COMP", "OBSFLUX", "MEANOPAC"} <= set(state["diagnostic_links"])
    tables = {t["title"]: t for t in parse_outgen(model / "OUTGEN")["tables"]}
    assert "Convergence and numerical quality checks (advisory)" in tables


def test_quality_auxiliary_files_are_unassessed_when_stale(tmp_path):
    model = _model(tmp_path)
    for name in ("J_COMP", "OBSFLUX", "MEANOPAC"):
        os.utime(model / name, (1_000_000_000, 1_000_000_000))
    checks = _checks(model)
    for code in ("boundary_radiation", "luminosity_depth", "inner_optical_depth"):
        assert checks[code]["level"] == "unknown"
        assert "59.38" not in checks[code]["detail"]


def test_boundary_cache_refreshes_after_file_change(tmp_path):
    model = _model(tmp_path)
    assert _checks(model)["boundary_radiation"]["level"] == "warning"
    path = model / "J_COMP"
    path.write_text(path.read_text().replace("-59.38", "-0.5"))
    assert _checks(model)["boundary_radiation"]["level"] == "info"


def test_parsed_outgen_cache_follows_new_quality_sources(tmp_path):
    model = _model(tmp_path)

    def boundary_detail():
        parsed = parse_known_file(model / "OUTGEN")
        table = next(t for t in parsed["tables"] if t["title"].startswith("Convergence and numerical"))
        return next(row[2] for row in table["rows"] if row[1].startswith("Measured outer-boundary"))

    assert "59.38%" in boundary_detail()
    path = model / "J_COMP"
    path.write_text(path.read_text().replace("-59.38", "-0.5"))
    assert "59.38%" not in boundary_detail()


@pytest.mark.parametrize("vector", ["NaN 1.0", "Infinity 1.0", "broken 1.0", "1.0"])
def test_nonfinite_and_malformed_luminosity_are_not_accepted(tmp_path, vector):
    model = _model(tmp_path)
    (model / "OBSFLUX").write_text(f"Normalized luminosity check\n\n{vector}\n\n")
    assert _checks(model)["luminosity_depth"]["level"] == "unknown"


def test_malformed_boundary_row_does_not_report_partial_band_maxima(tmp_path):
    model = _model(tmp_path)
    with (model / "J_COMP").open("a") as stream:
        stream.write("4 0.01 1 1 ***** 1 1 1 0\n")
    assert _checks(model)["boundary_radiation"]["level"] == "unknown"


def test_small_corrections_do_not_create_an_affirmative_convergence_verdict(tmp_path):
    model = _model(tmp_path)
    (model / "OUTGEN").write_text(
        "Current great iteration count is 1\n"
        "Luminosity of star (iteration 1) is: 100 100\n"
        "Maximum % increase at depth 1 is 0.05 (BA computed) --- iteration 1\n"
        "Maximum % decrease at depth 2 is 0.04 (BA computed) --- iteration 1\n"
        "Largest % change in spectrum for last 5 full iterations\n0.02\n"
        "Maximm changes as returned by SOLVEBA_V13 is 0.05\n")
    (model / "J_COMP").unlink()
    quality = inspect_model_convergence(model)["quality"]
    assert not quality["needs_review"]
    assert quality["incomplete"]
    assert all(c["level"] != "success" for c in quality["checks"])


def test_latest_run_excludes_old_hydro_warnings_and_fixed_temperature_is_flagged(tmp_path):
    model = _model(tmp_path)
    with (model / "OUTGEN").open("a") as stream:
        stream.write("Model started on: 02-Jan-2026 00:00:00\n"
                     "Current great iteration count is 50\n"
                     "Temperature held fixed at all depths.\n"
                     "The minimum value of scale for Major species is: 0.5\n"
                     "Maximm changes as returned by SOLVEBA_V13 is 0.05\n")
    checks = _checks(model)
    assert "hydrostatic_balance" not in checks
    assert "late_lambda" not in checks
    assert checks["fixed_temperature"]["level"] == "warning"
    assert checks["scaled_corrections"]["level"] == "warning"


def test_results_page_expands_quality_review_and_renders_source_links(tmp_path):
    _model(tmp_path)
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    response = app.test_client().get("/model-actions/main-computation/model")
    assert response.status_code == 200
    page = response.data.decode()
    assert "Results need review" in page
    assert 'p-2 mb-3" open>' in page
    assert "Photospheric hydrostatic balance" in page
    assert "59.38%" in page
    assert '/view/model/J_COMP' in page
    assert "Screening thresholds below are advisory" in page


def test_workflow_and_outgen_show_large_correction_counts(tmp_path):
    model = _model(tmp_path)
    (model / "CORRECTION_SUM").write_text(
        "NT= 2233\n"
        "Depth 100.0% 10.0% 1.0% 0.1% 0.01%\n"
        "1 2 511 1959 2202 2228\n"
        "2 3 622 1972 2206 2231\n"
        "3 12 800 2046 2213 2232\n")
    thresholds = inspect_model_convergence(model)["correction_summary"]["thresholds"]
    assert thresholds[:2] == [
        {"threshold": "100.0%", "maximum_count": 12, "depth": 3, "nonzero_depths": 3},
        {"threshold": "10.0%", "maximum_count": 800, "depth": 3, "nonzero_depths": 3},
    ]
    table = next(t for t in parse_outgen(model / "OUTGEN")["tables"]
                 if t["title"] == "Current CORRECTION_SUM thresholds")
    assert table["rows"][:2] == [["100.0%", "12", "3", "3"], ["10.0%", "800", "3", "3"]]
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    page = app.test_client().get("/model-actions/main-computation/model")
    assert page.status_code == 200
    text = page.data.decode()
    assert "Above 100.0%:" in text
    assert "Above 10.0%:" in text
    assert "<code>12</code> max" in text
    assert "<code>800</code> max" in text
