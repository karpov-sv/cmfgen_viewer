from __future__ import annotations

import os
from pathlib import Path

from cmfgen_viewer.model_preflight import inspect_model_preflight


def _write_valid_model(root: Path) -> Path:
    model = root / "model_a"
    model.mkdir()
    (model / "batch.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (model / "batch.sh").chmod(0o755)
    (model / "VADAT").write_text(
        "1.0 [RSTAR]\n"
        "2.0 [RMAX]\n"
        "3.0 [VINF]\n"
        "1.0E+05 [LSTAR]\n"
        "20.0 [MASS]\n"
        "3.0 [TEFF]\n"
        "RVSIG_COL [VEL_OPT]\n"
        "T [DO_CL]\n"
        "2 [N_CL_PAR]\n"
        "0.1 [CL_PAR_1]\n"
        "100.0 [CL_PAR_2]\n",
        encoding="utf-8",
    )
    (model / "MODEL_SPEC").write_text(
        "2 [ND]\n1 [NC]\n3 [NP]\n",
        encoding="utf-8",
    )
    (model / "IN_ITS").write_text(
        "10 [NUM_ITS]\nT [DO_LAM_AUTO]\n",
        encoding="utf-8",
    )
    (model / "GAMMAS_IN").write_text("gamma input\n", encoding="utf-8")
    (model / "RVSIG_COL").write_text(
        "2 ! Number of depth points\n"
        "2.0 3.0 4.0 5.0 1\n"
        "1.0 2.0 3.0 4.0 2\n",
        encoding="utf-8",
    )
    return model


def _codes(report: dict[str, object]) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_valid_model_passes_preflight(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)

    report = inspect_model_preflight(model)

    assert report["passed"] is True
    assert report["blocking"] is False
    assert report["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_grid_controls_and_booleans_are_validated_without_requiring_np_equality(
    tmp_path: Path,
) -> None:
    model = _write_valid_model(tmp_path)
    (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n4 [NP]\n", encoding="utf-8")

    extra_ray_report = inspect_model_preflight(model)

    assert extra_ray_report["blocking"] is False
    assert _codes(extra_ray_report) == {"additional-impact-rays"}

    (model / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n2 [NP]\n", encoding="utf-8")
    (model / "IN_ITS").write_text(
        "0 [NUM_ITS]\nMAYBE [DO_LAM_AUTO]\n",
        encoding="utf-8",
    )

    invalid_report = inspect_model_preflight(model)

    assert invalid_report["blocking"] is True
    assert {
        "impact-grid-too-small",
        "integer-out-of-range",
        "invalid-boolean",
    }.issubset(_codes(invalid_report))


def test_selected_rvsig_grid_must_match_model_spec_and_rows(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "RVSIG_COL").write_text(
        "3 ! Number of depth points\n"
        "2.0 3.0 4.0 5.0 1\n"
        "1.0 2.0 3.0 4.0 3\n",
        encoding="utf-8",
    )

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert {"structure-grid-mismatch", "structure-row-count"}.issubset(_codes(report))


def test_selected_rvsig_radius_ratio_must_match_vadat(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    contents = (model / "VADAT").read_text(encoding="utf-8")
    (model / "VADAT").write_text(contents.replace("2.0 [RMAX]", "10.0 [RMAX]"), encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert "structure-radius-ratio-mismatch" in _codes(report)


def test_selected_rvsig_outer_velocity_must_match_vinf(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    contents = (model / "VADAT").read_text(encoding="utf-8")
    (model / "VADAT").write_text(contents.replace("3.0 [VINF]", "1000.0 [VINF]"), encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert "structure-terminal-velocity-mismatch" in _codes(report)


def test_spectrum_control_ranges_are_checked_and_file_is_editable(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    obs = model / "obs"
    obs.mkdir()
    (obs / "CMF_FLUX_PARAM_INIT").write_text(
        "30.0 [VTURB_FIX]\n"
        "50.0 [VTURB_MIN]\n"
        "20.0 [VTURB_MAX]\n"
        "5000.0 [F_LAM_BEG]\n"
        "1000.0 [F_LAM_END]\n"
        "0.8 [OBS_EXT_RAT]\n",
        encoding="utf-8",
    )

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert {"turbulence-order", "wavelength-order", "small-observer-extent"}.issubset(
        _codes(report)
    )
    spectrum_issues = [
        issue
        for issue in report["issues"]
        if issue["file"] == "obs/CMF_FLUX_PARAM_INIT"
    ]
    assert spectrum_issues
    assert all(issue["editable"] is True for issue in spectrum_issues)


def test_only_newer_fresh_unpromoted_lte_results_block_preflight(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    lte = model / "lte"
    lte.mkdir()
    for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS"):
        (lte / name).write_text("input\n", encoding="utf-8")
    generated = lte / "ROSSELAND_LTE_TAB"
    generated.write_text("new opacity\n", encoding="utf-8")
    promoted = model / "ROSSELAND_LTE_TAB"
    promoted.write_text("old opacity\n", encoding="utf-8")
    input_time = max((lte / name).stat().st_mtime_ns for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS"))
    os.utime(generated, ns=(input_time + 2_000_000, input_time + 2_000_000))
    os.utime(promoted, ns=(input_time + 1_000_000, input_time + 1_000_000))

    unpromoted = inspect_model_preflight(model)

    assert "unpromoted-lte-result" in _codes(unpromoted)
    assert unpromoted["blocking"] is True

    promoted.write_text("locally newer opacity\n", encoding="utf-8")
    os.utime(promoted, ns=(input_time + 3_000_000, input_time + 3_000_000))

    newer_root = inspect_model_preflight(model)

    assert "unpromoted-lte-result" not in _codes(newer_root)


def test_displayed_batch_command_requires_executable_script(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "batch.sh").chmod(0o644)

    report = inspect_model_preflight(model)

    assert report["blocking"] is True
    assert "script-not-executable" in _codes(report)


def test_advisory_warning_does_not_block_external_run(tmp_path: Path) -> None:
    model = _write_valid_model(tmp_path)
    (model / "batch.sh").write_text("#!/bin/sh\ncd obs\n", encoding="utf-8")

    report = inspect_model_preflight(model)

    assert report["blocking"] is False
    assert report["counts"]["warning"] == 1
    assert _codes(report) == {"missing-spectrum-controls"}
