from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_editor import MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.model_workflow import (
    ModelWorkflowError,
    inspect_lte_hydro_workflow,
    prepare_lte_hydro_workspace,
    promote_lte_hydro_results,
    save_lte_quick_controls,
)


def _write_model(root: Path, name: str = "model_a") -> Path:
    model = root / name
    model.mkdir(parents=True)
    (model / "VADAT").write_text(
        "3.5 [LOGG]\n3.0D0 [TEFF]\nF [CHK_NG]\n",
        encoding="utf-8",
    )
    (model / "MODEL_SPEC").write_text("70 [ND]\n15 [NC]\n85 [NP]\n", encoding="utf-8")
    for filename in ("clean.sh", "RVSIG_COL", "batch.sh", "IN_ITS"):
        (model / filename).write_text(f"original {filename}\n", encoding="utf-8")
    return model


def _write_templates(root: Path) -> None:
    examples = root / "examples"
    (examples / "lte2").mkdir(parents=True)
    (examples / "lte2" / "GRID_PARAMS").write_text("grid\n", encoding="utf-8")
    (examples / "lte2" / "ltebat.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (examples / "HYDRO_PARAMS").write_text("hydro\n", encoding="utf-8")


def _make_outputs_fresh(model: Path) -> None:
    lte = model / "lte"
    latest_input = max(
        (lte / name).stat().st_mtime_ns
        for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS")
    )
    (lte / "ROSSELAND_LTE_TAB").write_text("rosseland new\n", encoding="utf-8")
    os.utime(lte / "ROSSELAND_LTE_TAB", ns=(latest_input + 1_000_000, latest_input + 1_000_000))
    (lte / "RVSIG_COL_NEW").write_text("structure new\n", encoding="utf-8")
    os.utime(lte / "RVSIG_COL_NEW", ns=(latest_input + 2_000_000, latest_input + 2_000_000))


def test_prepare_workspace_and_guard_successive_steps(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)

    initial = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert initial["prepare_allowed"] is True
    assert initial["lte_ready"] is False
    assert initial["hydro_ready"] is False

    prepared = prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    assert prepared["prepared"] is True
    assert prepared["lte_ready"] is True
    assert prepared["hydro_ready"] is False
    assert (model / "RVSIG_COL_OLD").read_text(encoding="utf-8") == "original RVSIG_COL\n"
    for name in ("VADAT", "MODEL_SPEC", "clean.sh", "GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS"):
        assert (model / "lte" / name).is_file()
    assert "$cmfdist/exe/wind_hyd.exe" in str(prepared["commands"]["hydro"])


def test_partial_workspace_is_not_merged_or_overwritten(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    (model / "lte").mkdir()
    (model / "lte" / "keep-me").write_text("partial\n", encoding="utf-8")

    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["prepare_allowed"] is False
    assert "incomplete" in str(state["prepare_reason"])
    with pytest.raises(ModelWorkflowError, match="incomplete"):
        prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    assert (model / "lte" / "keep-me").read_text(encoding="utf-8") == "partial\n"


def test_missing_old_rvsig_structure_does_not_block_preparation(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    (model / "RVSIG_COL").unlink()
    _write_templates(tmp_path)

    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["prepare_allowed"] is True
    optional = next(item for item in state["root_files"] if item["name"] == "RVSIG_COL")
    assert optional["required"] is False

    prepared = prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    assert prepared["prepared"] is True
    assert prepared["lte_ready"] is True
    assert not (model / "RVSIG_COL_OLD").exists()


def test_lte_run_waits_for_required_control_keys(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    (model / "VADAT").write_text("model without LTE controls\n", encoding="utf-8")
    _write_templates(tmp_path)

    prepared = prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    assert prepared["prepared"] is True
    assert prepared["lte_ready"] is False
    assert prepared["missing_lte_control_keys"] == [
        "VADAT [TEFF]",
        "VADAT [LOGG]",
        "VADAT [CHK_NG]",
    ]

    card = next(
        item for item in prepared["lte_quick_control_cards"] if item["file_relpath"] == "VADAT"
    )
    chk_ng = next(field for field in card["fields"] if field["key"] == "CHK_NG")
    assert chk_ng["exists"] is False
    assert chk_ng["value"] == "F"
    saved = save_lte_quick_controls(
        str(tmp_path),
        model_relpath="model_a",
        filename="VADAT",
        expected_digest=str(card["digest"]),
        values={"TEFF": "3.9D0", "LOGG": "3.55", "CHK_NG": "F"},
    )
    assert saved["backup_relpath"]
    contents = (model / "lte" / "VADAT").read_text(encoding="utf-8")
    assert "3.9D0" in contents and "[TEFF]" in contents
    assert "3.55" in contents and "[LOGG]" in contents
    assert "F" in contents and "[CHK_NG]" in contents
    assert inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")["lte_ready"] is True


def test_lte_quick_grid_controls_enforce_np_sum(tmp_path: Path) -> None:
    _write_model(tmp_path)
    _write_templates(tmp_path)
    state = prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    card = next(
        item
        for item in state["lte_quick_control_cards"]
        if item["file_relpath"] == "MODEL_SPEC"
    )
    with pytest.raises(ModelWorkflowError, match=r"\[NP\] must equal"):
        save_lte_quick_controls(
            str(tmp_path),
            model_relpath="model_a",
            filename="MODEL_SPEC",
            expected_digest=str(card["digest"]),
            values={"ND": "925", "NC": "15", "NP": "939"},
        )


def test_result_review_links_and_quick_controls_preserve_workflow_state(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    _make_outputs_fresh(model)
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["promotion_ready"] is True
    vadat_mtime = (model / "lte" / "VADAT").stat().st_mtime_ns

    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    client = app.test_client()
    page = client.get("/model-actions/lte-hydro/model_a")
    assert page.status_code == 200
    assert b"Open RVSIG_COL_NEW" in page.data
    assert b"Open ROSSELAND_LTE_TAB" in page.data
    assert b"Save REF_R" in page.data
    assert b"Save RMAX" in page.data

    vadat_card = next(
        item
        for item in state["result_quick_control_cards"]
        if item["file_relpath"] == "VADAT"
    )
    saved_rmax = client.post(
        "/model-actions/lte-hydro/model_a",
        data={
            "action": "configure_results",
            "control_file": "VADAT",
            "expected_digest": vadat_card["digest"],
            "result_value:RMAX": "109.7956",
        },
        follow_redirects=True,
    )
    assert saved_rmax.status_code == 200
    assert b"Saved result-review control in VADAT" in saved_rmax.data
    assert (model / "lte" / "VADAT").stat().st_mtime_ns == vadat_mtime
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["promotion_ready"] is True

    hydro_card = next(
        item
        for item in state["result_quick_control_cards"]
        if item["file_relpath"] == "HYDRO_PARAMS"
    )
    saved_ref_r = client.post(
        "/model-actions/lte-hydro/model_a",
        data={
            "action": "configure_results",
            "control_file": "HYDRO_PARAMS",
            "expected_digest": hydro_card["digest"],
            "result_value:REF_R": "127.55",
        },
        follow_redirects=True,
    )
    assert saved_ref_r.status_code == 200
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["hydro_output"]["stale"] is True
    assert state["promotion_ready"] is False


def test_result_summary_parses_generated_and_configured_quantities(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    lte = model / "lte"
    (lte / "HYDRO_PARAMS").write_text(
        "1.1500D+04 [LSTAR]\n2.5 [TEFF]\n3.7 [LOG_G]\n39.760 [REF_R]\n"
        "5.97 [MASS]\n2.0D-08 [MDOT]\n",
        encoding="utf-8",
    )
    with (lte / "VADAT").open("a", encoding="utf-8") as handle:
        handle.write("100.0 [RMAX]\n")
    _make_outputs_fresh(model)
    (lte / "RVSIG_COL_NEW").write_text(
        "! Effective temperature (10^4 K) is: 2.500000E+00\n"
        "! Log surface gravity (cgs) is: 3.700000E+00\n"
        "! Core radius (10^10 cm) is: 3.892304E+01\n"
        "! Reference radius (10^10 cm) is: 3.976000E+01\n"
        "! Luminosity (Lsun) is: 1.150121E+04\n"
        "! Mass (Msun) of star is: 5.969851E+00\n"
        "! Mass loss rate (Msun/yr) is: 2.000000E-08\n"
        "! Mean atomic mass (amu) is: 1.295200E+00\n"
        "! Eddington parameter is: 4.558149E-02\n"
        "! Atom density is: 1.000000E+08\n"
        "! Ratio of inner to outer radius is: 115.61275930\n"
        "115 !Number of depth points\n",
        encoding="utf-8",
    )

    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    summary = state["result_summary"]
    assert summary is not None
    by_label = {item["label"]: item for item in summary["comparisons"]}
    assert by_label["Luminosity"]["generated"] == "11501.21"
    assert by_label["Luminosity"]["configured"] == "11500"
    assert by_label["Luminosity"]["status"] == "success"
    assert by_label["Radius ratio (RMAX)"]["generated"] == "115.6128"
    assert by_label["Radius ratio (RMAX)"]["configured"] == "100"
    diagnostics = {item["label"]: item["value"] for item in summary["diagnostics"]}
    assert diagnostics["Eddington parameter"] == "0.04558149"
    assert diagnostics["Depth points"] == "115"

    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    page = app.test_client().get("/model-actions/lte-hydro/model_a")
    assert b"Generated quantities and configured values" in page.data
    assert b"Additional generated diagnostics" in page.data
    assert b"11501.21" in page.data


def test_stale_outputs_are_blocked_and_fresh_results_are_promoted_with_backups(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    lte = model / "lte"
    (lte / "ROSSELAND_LTE_TAB").write_text("stale\n", encoding="utf-8")
    os.utime(lte / "ROSSELAND_LTE_TAB", ns=(1, 1))
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["lte_output"]["stale"] is True
    assert state["hydro_ready"] is False
    with pytest.raises(ModelWorkflowError, match="Fresh"):
        promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")

    _make_outputs_fresh(model)
    (model / "ROSSELAND_LTE_TAB").write_text("old table\n", encoding="utf-8")
    promoted = promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")
    assert promoted["promoted"] is True
    assert (model / "ROSSELAND_LTE_TAB").read_text(encoding="utf-8") == "rosseland new\n"
    assert (model / "RVSIG_COL").read_text(encoding="utf-8") == "structure new\n"
    assert (model / "RVSIG_COL_NEW").read_text(encoding="utf-8") == "structure new\n"
    backup = model / str(promoted["backup_relpath"])
    assert (backup / "RVSIG_COL").read_text(encoding="utf-8") == "original RVSIG_COL\n"
    assert (backup / "ROSSELAND_LTE_TAB").read_text(encoding="utf-8") == "old table\n"
    assert (model / MODEL_INPUT_MODIFIED_MARKER).is_file()
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    handoff = app.test_client().get("/model-actions/lte-hydro/model_a")
    assert b"Continue to Main Computation" in handoff.data
    assert b'/model-actions/main-computation/model_a' in handoff.data


def test_workflow_page_never_runs_processes_and_guards_read_only_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_model(tmp_path)
    _write_templates(tmp_path)
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    client = app.test_client()

    def forbidden(*args, **kwargs):
        raise AssertionError("process execution is forbidden")

    monkeypatch.setattr(os, "system", forbidden)
    page = client.get("/model-actions/lte-hydro/model_a")
    assert page.status_code == 200
    assert b"never starts a CMFGEN process" in page.data
    assert b"Prepare LTE Workspace" in page.data
    response = client.post(
        "/model-actions/lte-hydro/model_a", data={"action": "prepare"}, follow_redirects=True
    )
    assert response.status_code == 200
    assert b"No calculation was started" in response.data
    assert b"./ltebat.sh" in response.data
    assert b"Required controls:" in response.data
    assert b"Save VADAT Controls" in response.data
    assert b'/model-actions/runtime/lte/model_a' in response.data
    assert b'/model-actions/runtime/hydro/model_a' in response.data
    assert response.data.count(b"model_runtime.js") == 1
    assert client.get("/model-actions/runtime/lte/model_a").status_code == 200
    assert client.get("/model-actions/runtime/hydro/model_a").status_code == 200
    configured = client.post(
        "/model-actions/lte-hydro/model_a",
        data={
            "action": "configure_lte",
            "control_file": "VADAT",
            "expected_digest": inspect_lte_hydro_workflow(
                str(tmp_path), model_relpath="model_a"
            )["lte_quick_control_cards"][0]["digest"],
            "lte_value:TEFF": "4.1D0",
            "lte_value:LOGG": "3.7",
            "lte_value:CHK_NG": "F",
        },
        follow_redirects=True,
    )
    assert configured.status_code == 200
    assert b"Saved LTE controls in VADAT" in configured.data
    assert "4.1D0" in (tmp_path / "model_a" / "lte" / "VADAT").read_text(encoding="utf-8")
    assert client.get("/model-actions/edit/model_a/lte?file=HYDRO_PARAMS").status_code == 200
    assert client.get("/model-actions/edit/model_a/lte?file=GRID_PARAMS").status_code == 200

    read_only = create_app(basepath=str(tmp_path), read_write_enabled=False, secret_key="test")
    read_only.testing = True
    assert read_only.test_client().get("/model-actions/lte-hydro/model_a").status_code == 403
