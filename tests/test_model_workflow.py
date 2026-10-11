from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from cmfgen_viewer import model_activity, model_workflow

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_editor import MODEL_INPUT_MODIFIED_MARKER
from cmfgen_viewer.model_workflow import (
    ModelWorkflowError,
    align_hydro_parameters,
    inspect_lte_hydro_workflow,
    prepare_lte_hydro_workspace,
    promote_lte_hydro_results,
    save_lte_quick_controls,
)


GENERATED_RVSIG = (
    "! Ratio of inner to outer radius is: 2.0\n"
    "2 ! Number of depth points\n"
    "2.0 3.0 4.0 5.0 1\n"
    "1.0 2.0 3.0 4.0 2\n"
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
    templates = root / "templates" / "lte"
    templates.mkdir(parents=True)
    (templates / "GRID_PARAMS").write_text("grid\n", encoding="utf-8")
    (templates / "ltebat.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (templates / "ltebat.sh").chmod(0o755)
    (templates / "HYDRO_PARAMS").write_text("hydro\n", encoding="utf-8")


def test_unprepared_workspace_does_not_subscribe_to_runtime(tmp_path):
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    app = create_app(basepath=str(tmp_path), read_write_enabled=True,
                     upload_root=str(tmp_path / "uploads"))
    client = app.test_client()
    page = client.get("/model-actions/lte-hydro/model_a")
    assert page.status_code == 200
    assert b"Workspace not prepared" in page.data
    assert b"data-model-runtime-url" not in page.data
    assert b"data-runtime-key" not in page.data
    (model / "lte").mkdir()
    page = client.get("/model-actions/lte-hydro/model_a")
    assert page.status_code == 200
    assert page.data.count(b"data-model-runtime-url") == 2
    assert client.get("/model-actions/runtime/lte/model_a").status_code == 200
    assert client.get("/model-actions/runtime/hydro/model_a").status_code == 200


def _make_outputs_fresh(model: Path) -> None:
    lte = model / "lte"
    hydro = lte / "HYDRO_PARAMS"
    if "[MU_ATOM]" not in hydro.read_text():
        hydro.write_text(hydro.read_text() + "\n1.30563 [MU_ATOM]\n")
    latest_input = max(
        (lte / name).stat().st_mtime_ns
        for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS")
    )
    (lte / "ROSSELAND_LTE_TAB").write_text("! Mean atomic weight (atoms/ions only) 1.30563\n1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n", encoding="utf-8")
    os.utime(lte / "ROSSELAND_LTE_TAB", ns=(latest_input, latest_input))
    (lte / "RVSIG_COL_NEW").write_text(GENERATED_RVSIG, encoding="utf-8")
    os.utime(lte / "RVSIG_COL_NEW", ns=(latest_input, latest_input))


@pytest.mark.parametrize("state", ["active", "unknown"])
def test_preparation_and_promotion_refuse_non_idle_models(tmp_path, monkeypatch, state):
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    refused = lambda _: {"safe_to_modify": False, "reason": state}
    with monkeypatch.context() as patch:
        patch.setattr(model_activity, "inspect_model_activity", refused)
        with pytest.raises(ModelWorkflowError, match=state):
            prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    assert not (model / "lte").exists()
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    _make_outputs_fresh(model)
    original = (model / "VADAT").read_bytes()
    monkeypatch.setattr(model_activity, "inspect_model_activity", refused)
    monkeypatch.setattr(model_workflow, "inspect_model_activity", refused)
    result = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert not any(result[key] for key in ("lte_ready", "hydro_ready", "promotion_ready", "main_ready"))
    with pytest.raises(ModelWorkflowError, match=state):
        promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")
    assert (model / "VADAT").read_bytes() == original


@pytest.mark.parametrize("running_stage", ["lte", "hydro"])
def test_running_stage_blocks_fresh_output_handoff(tmp_path, monkeypatch, running_stage):
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    _make_outputs_fresh(model)
    inspect_runtime = model_workflow.inspect_workflow_runtime
    def runtime(path, kind):
        result = inspect_runtime(path, kind)
        result["active"] = kind == running_stage
        return result
    monkeypatch.setattr(model_workflow, "inspect_workflow_runtime", runtime)
    result = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert not result["promotion_ready"]
    if running_stage == "lte":
        assert not result["hydro_ready"]


def test_nonexecutable_lte_script_blocks_run_but_not_finished_output_promotion(tmp_path):
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    _make_outputs_fresh(model)
    (model / "lte/ltebat.sh").chmod(0o644)
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert not state["lte_ready"]
    assert state["promotion_ready"]


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
    hydro_command = str(prepared["commands"]["hydro"])
    assert "$cmfdist/exe/wind_hyd.exe" in hydro_command
    assert "set -o pipefail" in hydro_command
    assert "2>&1 | tee WIND_HYD" in hydro_command


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

    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    client = app.test_client()
    page = client.get("/model-actions/lte-hydro/model_a")
    assert page.status_code == 200
    assert b"Open RVSIG_COL_NEW" in page.data
    assert b"Open ROSSELAND_LTE_TAB" in page.data
    assert b"Save REF_R" in page.data
    assert b"Save RMAX" not in page.data

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
    (lte / "VADAT").write_text(
        "2.5 [TEFF]\n3.7 [LOGG]\n11500 [LSTAR]\n5.97 [MASS]\n"
        "2e-8 [MDOT]\n38.92304 [RSTAR]\n100 [RMAX]\n", encoding="utf-8",
    )
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


def _write_misaligned_hydro_model(tmp_path: Path) -> Path:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    (model / "lte/VADAT").write_text(
        "2.5D0 [TEFF]\n3.7 [LOGG]\n11500 [LSTAR]\n2D-8 [MDOT]\n"
        "2277.344 [VINF]\n1 [BETA]\n38.93921809 [RSTAR]\n100 [RMAX]\nF [CHK_NG]\n",
    )
    (model / "lte/HYDRO_PARAMS").write_text(
        "! Keep this comment\n3.9 [TEFF] ! temperature\n3.55 [LOG_G]\n1.8e-6 [MDOT]\n"
        "2277.344 [VINF]\n1 [BETA]\n127.55 [REF_R]\n135 [CON_R]\n"
        "F [OLD_MOD]\nF [OLD_V]\nT [WIND_PRES]\n100 [MAX_R]\n700000 [LSTAR]\n",
    )
    _make_outputs_fresh(model)
    return model


def test_hydro_alignment_preview_and_apply_with_backup(tmp_path):
    model = _write_misaligned_hydro_model(tmp_path)
    hydro = model / "lte/HYDRO_PARAMS"
    original = hydro.read_bytes()
    vadat = (model / "lte/VADAT").read_bytes()
    root_vadat = (model / "VADAT").read_bytes()
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    preview = state["hydro_alignment"]
    assert preview["ready"] and preview["has_mismatch"]
    rows = {row["label"]: row for row in preview["rows"]}
    reference = float(preview["values"]["REF_R"])
    assert reference == pytest.approx(39.757908, abs=0.00001)
    assert (reference / 6.9599) ** 2 * (2.5 / 0.5770) ** 4 == pytest.approx(11500)
    assert float(preview["values"]["CON_R"]) / reference == pytest.approx(135 / 127.55)
    assert rows["MDOT"]["status"] == "danger"
    assert hydro.read_bytes() == original

    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    client = app.test_client()
    page = client.get("/model-actions/lte-hydro/model_a")
    assert b"HYDRO_PARAMS differs from the intended LTE/VADAT model" in page.data
    assert b"Use VADAT parameters" in page.data
    payload = {"action": "align_hydro", "expected_digest": preview["digest"]}
    denied = client.post("/model-actions/lte-hydro/model_a", data=payload)
    assert b"Review the proposed hydro parameters" in denied.data
    assert hydro.read_bytes() == original
    payload["alignment_checked"] = "1"
    response = client.post("/model-actions/lte-hydro/model_a", data=payload, follow_redirects=True)
    assert b"HYDRO_PARAMS aligned with LTE/VADAT" in response.data
    values = model_workflow._control_numeric_values(hydro)
    assert values["LOG_G"] == 3.7 and values["TEFF"] == 2.5
    assert values["MDOT"] == 2e-8
    assert values["REF_R"] == pytest.approx(reference)
    assert values["LSTAR"] == 700000  # ignored metadata is preserved
    assert "! Keep this comment" in hydro.read_text() and "! temperature" in hydro.read_text()
    assert (model / "lte/VADAT").read_bytes() == vadat
    assert (model / "VADAT").read_bytes() == root_vadat
    backups = list((model / ".cmfgen-viewer-backups/hydro-alignment").glob("*/HYDRO_PARAMS"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["lte_output"]["fresh"] and state["hydro_output"]["stale"]
    assert not state["promotion_ready"]


@pytest.mark.parametrize("changed_file", ["VADAT", "HYDRO_PARAMS"])
def test_hydro_alignment_rejects_changed_source_or_target(tmp_path, changed_file):
    model = _write_misaligned_hydro_model(tmp_path)
    preview = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")["hydro_alignment"]
    path = model / "lte" / changed_file
    path.write_text(path.read_text() + "! An external edit\n")
    current = (model / "lte/HYDRO_PARAMS").read_bytes()
    with pytest.raises(ModelWorkflowError, match="changed since the preview"):
        align_hydro_parameters(str(tmp_path), model_relpath="model_a", expected_digest=preview["digest"])
    assert (model / "lte/HYDRO_PARAMS").read_bytes() == current


@pytest.mark.parametrize("activity", ["active", "unknown"])
def test_hydro_alignment_refuses_non_idle_workspaces(tmp_path, monkeypatch, activity):
    model = _write_misaligned_hydro_model(tmp_path)
    preview = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")["hydro_alignment"]
    current = (model / "lte/HYDRO_PARAMS").read_bytes()
    monkeypatch.setattr(model_activity, "inspect_model_activity", lambda _: {"safe_to_modify": False, "reason": activity})
    with pytest.raises(ModelWorkflowError, match=activity):
        align_hydro_parameters(str(tmp_path), model_relpath="model_a", expected_digest=preview["digest"])
    assert (model / "lte/HYDRO_PARAMS").read_bytes() == current


def test_hydro_alignment_route_refuses_read_only_mode(tmp_path):
    model = _write_misaligned_hydro_model(tmp_path)
    current = (model / "lte/HYDRO_PARAMS").read_bytes()
    app = create_app(basepath=str(tmp_path), read_write_enabled=False, secret_key="test")
    response = app.test_client().post("/model-actions/lte-hydro/model_a", data={"action": "align_hydro", "alignment_checked": "1"})
    assert response.status_code == 403
    assert (model / "lte/HYDRO_PARAMS").read_bytes() == current


@pytest.mark.parametrize("filename,old,new", [
    ("VADAT", "11500 [LSTAR]", "NaN [LSTAR]"),
    ("VADAT", "11500 [LSTAR]", "-1 [LSTAR]"),
    ("VADAT", "11500 [LSTAR]", "11500 [LSTAR]\n12 [LSTAR]"),
    ("HYDRO_PARAMS", "127.55 [REF_R]", "0 [REF_R]"),
    ("HYDRO_PARAMS", "F [OLD_V]", "T [OLD_V]"),
    ("HYDRO_PARAMS", "135 [CON_R]", "135 [CON_R]\n140 [CON_R]"),
])
def test_hydro_alignment_requires_unambiguous_supported_inputs(tmp_path, filename, old, new):
    model = _write_misaligned_hydro_model(tmp_path)
    path = model / "lte" / filename
    path.write_text(path.read_text().replace(old, new))
    preview = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")["hydro_alignment"]
    assert not preview["ready"] and preview["issues"]
    with pytest.raises(ModelWorkflowError):
        align_hydro_parameters(str(tmp_path), model_relpath="model_a", expected_digest=preview["digest"])


def test_generated_summary_compares_to_vadat_despite_matching_hydro_template(tmp_path):
    model = _write_misaligned_hydro_model(tmp_path)
    result = model / "lte/RVSIG_COL_NEW"
    result.write_text(GENERATED_RVSIG + "! Effective temperature (10^4 K) is: 3.9\n"
                      "! Log surface gravity (cgs) is: 3.55\n"
                      "! Luminosity (Lsun) is: 700000\n"
                      "! Mass loss rate (Msun/yr) is: 1.8e-6\n")
    summary = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")["result_summary"]
    rows = {row["label"]: row for row in summary["comparisons"]}
    assert summary["has_mismatch"]
    assert rows["Luminosity"]["configured"] == "11500"
    assert rows["Luminosity"]["status"] == "danger"
    assert rows["Effective temperature"]["configured_source"] == "VADAT [TEFF]"


def test_promotion_preserves_generated_core_radius_and_lte_freshness(tmp_path):
    model = _write_misaligned_hydro_model(tmp_path)
    output = model / "lte/RVSIG_COL_NEW"
    output.write_text(GENERATED_RVSIG + "! Core radius (10^10 cm) is: 38.92304\n")
    rosseland_mtime = (model / "lte/ROSSELAND_LTE_TAB").stat().st_mtime_ns
    os.utime(output, ns=(rosseland_mtime + 1_000_000, rosseland_mtime + 1_000_000))
    vadat = model / "lte/VADAT"
    previous = vadat.read_bytes()
    mtime = vadat.stat().st_mtime_ns
    result = promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")
    assert result["synchronized_rstar"] == 38.92304
    assert result["synchronized_rmax"] == 2
    assert vadat.stat().st_mtime_ns == mtime
    assert result["promotion_ready"] and result["promoted"]
    for path in (vadat, model / "VADAT"):
        values = model_workflow._control_numeric_values(path)
        assert values["RSTAR"] == 38.92304 and values["RMAX"] == 2
    assert (model / result["backup_relpath"] / "lte/VADAT").read_bytes() == previous


def test_lte_and_captured_hydro_diagnostics_render_and_guard_failures(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    lte = model / "lte"
    _make_outputs_fresh(model)
    (lte / "OUTLTE").write_text(
        "Number of frequencies is 1000\nDELTA_ED= 0.5\nDELTA_T= 0.1\n",
        encoding="utf-8",
    )
    (lte / "ML_COUNTER").write_text("1000\n", encoding="utf-8")
    (lte / "WIND_HYD").write_text(
        "Transition radius is 12.5\nTransition velocity is 20.0\n"
        "Old reference radius is 40.01\nDesired reference radius is 40.0\n",
        encoding="utf-8",
    )

    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["lte_diagnostics"]["frequency_percent"] == 100.0
    assert state["hydro_diagnostics"]["status"] == "ready"
    page = create_app(
        basepath=str(tmp_path), read_write_enabled=True, secret_key="test"
    ).test_client().get("/model-actions/lte-hydro/model_a")
    assert b"LTE run diagnostics" in page.data
    assert b"Captured wind_hyd diagnostics" in page.data
    assert b"Final reference-radius difference" in page.data
    assert b"tee WIND_HYD" in page.data

    (lte / "OUTLTE").write_text(
        "Fortran runtime error: invalid input\nBacktrace for this error:\n",
        encoding="utf-8",
    )
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state["lte_diagnostics"]["fatal"] is True
    assert state["hydro_ready"] is False


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
    stale_state = {
        "POINT1": "old pointer\n",
        "SCRTEMP": "old scratch\n",
        "MODEL": "old model\n",
        "RVTJ": "old atmosphere\n",
        "MOD_SUM": "old summary\n",
        "EDDFACTOR_INFO": "old 70-point cache metadata\n",
    }
    for name, contents in stale_state.items():
        (model / name).write_text(contents, encoding="utf-8")
    promoted = promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")
    assert promoted["promoted"] is True
    page = create_app(basepath=str(tmp_path), read_write_enabled=True).test_client().get(
        '/model-actions/lte-hydro/model_a').get_data(as_text=True)
    assert 'Awaiting promotion' not in page
    assert 'Continue to Main Computation</a>' in page
    assert 'The current results have been promoted' in page
    assert 'Promote Results</button>' not in page
    assert promoted["synchronized_rmax"] == 2.0
    assert set(promoted["invalidated_files"]) == set(stale_state)
    assert (model / "ROSSELAND_LTE_TAB").read_text(encoding="utf-8") == (lte / "ROSSELAND_LTE_TAB").read_text(encoding="utf-8")
    assert (model / "RVSIG_COL").read_text(encoding="utf-8") == GENERATED_RVSIG
    assert (model / "RVSIG_COL_NEW").read_text(encoding="utf-8") == GENERATED_RVSIG
    assert "2" in (model / "VADAT").read_text(encoding="utf-8").split("[RMAX]")[0].splitlines()[-1]
    assert (model / "VADAT").read_bytes() == (model / "lte" / "VADAT").read_bytes()
    assert not any((model / name).exists() for name in stale_state)
    backup = model / str(promoted["backup_relpath"])
    assert (backup / "RVSIG_COL").read_text(encoding="utf-8") == "original RVSIG_COL\n"
    assert (backup / "ROSSELAND_LTE_TAB").read_text(encoding="utf-8") == "old table\n"
    for name, contents in stale_state.items():
        assert (backup / name).read_text(encoding="utf-8") == contents
    assert "[RMAX]" not in (backup / "lte" / "VADAT").read_text(encoding="utf-8")
    assert (model / MODEL_INPUT_MODIFIED_MARKER).is_file()
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    handoff = app.test_client().get("/model-actions/lte-hydro/model_a")
    assert b"Continue to Main Computation" in handoff.data
    assert b'/model-actions/main-computation/model_a' in handoff.data


def test_promotion_requires_generated_radius_ratio(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath="model_a")
    _make_outputs_fresh(model)
    (model / "lte" / "RVSIG_COL_NEW").write_text("structure without header\n", encoding="utf-8")

    with pytest.raises(ModelWorkflowError, match="radius ratio"):
        promote_lte_hydro_results(str(tmp_path), model_relpath="model_a")


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
    assert b"run commands in your terminal" in page.data
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


def test_prepared_workflow_focuses_next_stage_and_distinguishes_existing_root(tmp_path):
    model = _write_misaligned_hydro_model(tmp_path)
    (model / "lte/ROSSELAND_LTE_TAB").unlink()
    (model / "lte/RVSIG_COL_NEW").unlink()
    (model / "ROSSELAND_LTE_TAB").write_text("existing root structure\n")
    with (model / "lte/ltebat.sh").open("a") as script:
        script.write("ln -sf /missing/atomic/oxygen.dat OVIII_F_TO_S\n")
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    client = app.test_client()
    page = client.get("/model-actions/lte-hydro/model_a").get_data(as_text=True)
    assert re.search(r'id="hydro-run"\s*>', page)
    assert re.search(r'id="lte-run"\s+open', page)
    assert '>Run LTE</a>' in page
    assert 'Waiting for LTE' in page
    assert 'Parameter mismatch' in page
    assert 'Awaiting promotion' in page
    assert 'Handoff ready' not in page
    assert 'Review and promote the current LTE/hydro results first' in page
    assert 'No blockers' in page and '1 warning' in page
    assert '1 missing atomic / restart link target' in page
    assert 'Full target path' in page
    assert '/missing/atomic/oxygen.dat' in page
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath="model_a")
    assert state['hydro_preflight']['blocking']
    assert not state['hydro_ready']
    _make_outputs_fresh(model)
    page = client.get("/model-actions/lte-hydro/model_a").get_data(as_text=True)
    assert re.search(r'id="hydro-run"\s+open', page)
    assert '>Review hydro parameters</a>' in page
    assert 'How the proposed values are calculated' in page


def _write_initializable_workspace_inputs(tmp_path):
    model = _write_model(tmp_path)
    _write_templates(tmp_path)
    (model / 'VADAT').write_text(
        '2.5D0 [TEFF]\n3.7 [LOGG]\n11500 [LSTAR]\n2D-8 [MDOT]\n'
        '1800 [VINF]\n2 [BETA]\nF [CHK_NG]\n',
    )
    (tmp_path / 'templates/lte/HYDRO_PARAMS').write_text(
        '! Keep template comment\n3.9 [TEFF] ! temperature\n3.55 [LOG_G]\n'
        '1.8e-6 [MDOT]\n2277.344 [VINF]\n1 [BETA]\n127.55 [REF_R]\n135 [CON_R]\n'
        'F [OLD_MOD]\nF [OLD_V]\nT [WIND_PRES]\n100 [MAX_R]\n',
    )
    return model


def test_prepare_initializes_hydro_and_preserves_sources(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    template = tmp_path / 'templates/lte/HYDRO_PARAMS'
    template.chmod(0o640)
    original_template = template.read_bytes()
    original_vadat = (model / 'VADAT').read_bytes()
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key='test')
    response = app.test_client().post('/model-actions/lte-hydro/model_a',
                                      data={'action': 'prepare'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'HYDRO_PARAMS initialized from VADAT' in response.data
    assert b'review the connection radius' in response.data.lower()
    assert b'retained its template values' not in response.data
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath='model_a')
    alignment = state['hydro_alignment']
    assert alignment['ready'] and not alignment['has_changes'] and not alignment['has_mismatch']
    values = model_workflow._control_numeric_values(model / 'lte/HYDRO_PARAMS')
    assert values['TEFF'] == 2.5 and values['LOG_G'] == 3.7
    assert values['MDOT'] == 2e-8 and values['VINF'] == 1800 and values['BETA'] == 2
    assert (values['REF_R'] / 6.9599) ** 2 * (2.5 / 0.5770) ** 4 == pytest.approx(11500)
    assert values['CON_R'] / values['REF_R'] == pytest.approx(135 / 127.55)
    contents = (model / 'lte/HYDRO_PARAMS').read_text()
    assert '! Keep template comment' in contents and '! temperature' in contents
    assert '100 [MAX_R]' in contents and 'F [OLD_MOD]' in contents
    assert (model / 'lte/HYDRO_PARAMS').stat().st_mode & 0o777 == 0o640
    assert template.read_bytes() == original_template
    assert (model / 'VADAT').read_bytes() == original_vadat
    assert not state['hydro_ready']  # Preparation has not produced any LTE result.
    with pytest.raises(ModelWorkflowError):
        prepare_lte_hydro_workspace(str(tmp_path), model_relpath='model_a')
    assert (model / 'lte/HYDRO_PARAMS').read_text() == contents


@pytest.mark.parametrize('filename,old,new', [
    ('VADAT', '11500 [LSTAR]', 'NaN [LSTAR]'),
    ('VADAT', '3.7 [LOGG]', '3.7 [LOGG]\n4 [LOGG]'),
    ('HYDRO_PARAMS', 'F [OLD_V]', 'T [OLD_V]'),
])
def test_prepare_reports_unsupported_hydro_initialization_without_partial_changes(tmp_path, filename, old, new):
    model = _write_initializable_workspace_inputs(tmp_path)
    target = model / filename if filename == 'VADAT' else tmp_path / 'templates/lte/HYDRO_PARAMS'
    target.write_text(target.read_text().replace(old, new))
    original = (tmp_path / 'templates/lte/HYDRO_PARAMS').read_bytes()
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key='test')
    response = app.test_client().post('/model-actions/lte-hydro/model_a',
                                      data={'action': 'prepare'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'HYDRO_PARAMS retained its template values' in response.data
    assert b'Initialization issues' in response.data
    assert (model / 'lte/HYDRO_PARAMS').read_bytes() == original
    assert not inspect_lte_hydro_workflow(str(tmp_path), model_relpath='model_a')['hydro_alignment']['ready']


def test_prepare_does_not_publish_workspace_if_hydro_initialization_write_fails(tmp_path, monkeypatch):
    model = _write_initializable_workspace_inputs(tmp_path)
    monkeypatch.setattr(model_workflow, '_atomic_write',
                        lambda *args: (_ for _ in ()).throw(OSError('write failed')))
    with pytest.raises(ModelWorkflowError, match='write failed'):
        prepare_lte_hydro_workspace(str(tmp_path), model_relpath='model_a')
    assert not (model / 'lte').exists()
    assert not (model / 'RVSIG_COL_OLD').exists()
    assert not list(model.glob('.cmfgen-lte-*'))


def test_result_review_distinguishes_synchronized_radii_from_parameter_mismatches(tmp_path):
    model = _write_initializable_workspace_inputs(tmp_path)
    prepare_lte_hydro_workspace(str(tmp_path), model_relpath=model.name)
    _make_outputs_fresh(model)
    rvsig = model / 'lte/RVSIG_COL_NEW'
    header = ('! Luminosity (Lsun) is: 11500\n'
              '! Effective temperature (10^4 K) is: 2.5\n'
              '! Log surface gravity (cgs) is: 3.7\n'
              '! Core radius (10^10 cm) is: 40\n')
    rvsig.write_text(header + rvsig.read_text())
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath=model.name)
    summary = state['result_summary']
    radii = [row for row in summary['comparisons'] if row['synchronized_on_promotion']]
    assert len(radii) == 2 and all(row['status'] == 'info' for row in radii)
    assert not summary['has_mismatch']
    assert state['promotion_ready']
    app = create_app(basepath=str(tmp_path), read_write_enabled=True)
    page = app.test_client().get('/model-actions/lte-hydro/model_a').get_data(as_text=True)
    assert page.count('Output ready · not running') == 2
    assert 'Generated structure differs' not in page
    assert 'Will be synchronized during promotion' in page
    assert 'no manual radius edit is needed' in page
    assert 'Awaiting promotion' in page
    assert 'Continue to Main Computation</a>' not in page
    assert re.search(r'id="result-corrections"\s*>', page)
    assert page.index('Promote Results</button>') < page.index('Adjust parameters and rerun')
    assert 'Save RMAX' not in page
    rvsig.write_text(rvsig.read_text().replace('11500', '20000'))
    state = inspect_lte_hydro_workflow(str(tmp_path), model_relpath=model.name)
    assert state['result_summary']['has_mismatch']
    page = app.test_client().get('/model-actions/lte-hydro/model_a').get_data(as_text=True)
    assert 'Generated structure differs' in page
    assert 'no manual radius edit is needed' not in page
