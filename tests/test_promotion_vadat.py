import os

import pytest

from cmfgen_viewer import model_workflow
from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_editor import ModelEditorError
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_recipe import RunnerError
from cmfgen_viewer.runner_promotion import build_promotion_plan
from test_runner_promotion import promotable_model


def _fresh_outputs(model):
    lte = model / "lte"
    stamp = max((lte / name).stat().st_mtime_ns for name in ("VADAT", "HYDRO_PARAMS", "MODEL_SPEC"))
    os.utime(lte / "ROSSELAND_LTE_TAB", ns=(stamp + 1_000_000, stamp + 1_000_000))
    os.utime(lte / "RVSIG_COL_NEW", ns=(stamp + 2_000_000, stamp + 2_000_000))


@pytest.mark.parametrize("reports_core", [False, True])
def test_promotion_patches_root_radii_and_preserves_manual_controls(promotable_model, reports_core):
    model = promotable_model
    root = model / "VADAT"
    extra = "! Manual initialization and custom controls\nLTE  [DC_METH] !keep this comment\n0.8 [T_EXC]\nMY_VALUE [CUSTOM_SETTING]\n"
    root.write_text(root.read_text() + "100 [RMAX] !root radius\n999 [RSTAR] !root core\n" + extra)
    original_root = root.read_bytes()
    lte_vadat = model / "lte/VADAT"
    original_lte = lte_vadat.read_bytes()
    if reports_core:
        with (model / "lte/RVSIG_COL_NEW").open("a") as stream:
            stream.write("! Core radius (10^10 cm) is: 38.92304\n")
        _fresh_outputs(model)
    result = model_workflow.promote_lte_hydro_results(str(model.parent), model_relpath=model.name)
    assert result["promoted"]
    contents = root.read_text()
    assert extra in contents
    assert "2 [RMAX] !root radius" in contents
    assert ("38.92304" if reports_core else "999") + " [RSTAR] !root core" in contents
    assert root.read_bytes() != lte_vadat.read_bytes()
    backup = model / result["backup_relpath"]
    assert (backup / "VADAT").read_bytes() == original_root
    assert (backup / "lte/VADAT").read_bytes() == original_lte
    repeated = build_promotion_plan(model)
    assert not repeated["ready"] and "already match" in repeated["errors"][0]


def test_physics_difference_is_preserved_and_exposed_for_review(promotable_model):
    model = promotable_model
    with (model / "VADAT").open("a") as stream:
        stream.write("3e-8 [MDOT] !new intended mass loss\n")
    with (model / "lte/VADAT").open("a") as stream:
        stream.write("1e-8 [MDOT]\n")
    _fresh_outputs(model)
    plan = build_promotion_plan(model)
    assert plan["ready"], plan["errors"]
    assert any("MDOT: root=3e-08, LTE=1e-08" in warning for warning in plan["warnings"])
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key="test")
    page = app.test_client().get("/model-actions/lte-hydro/model").data
    assert b"Promotion preserves these root values" in page
    result = run_plan(plan)
    assert result["status"] == "succeeded", result
    assert model_workflow._control_numeric_values(model / "VADAT")["MDOT"] == 3e-8


def test_promotion_preserves_root_line_endings(promotable_model):
    model = promotable_model
    root = model / "VADAT"
    original = root.read_bytes().replace(b"\n", b"\r\n") + b"100 [RMAX] !keep formatting\r\nLTE [DC_METH]\r\n"
    root.write_bytes(original)
    model_workflow.promote_lte_hydro_results(str(model.parent), model_relpath=model.name)
    assert root.read_bytes() == original.replace(b"100 [RMAX]", b"2 [RMAX]")


def test_root_edit_invalidates_reviewed_promotion_plan(promotable_model):
    model = promotable_model
    plan = build_promotion_plan(model)
    with (model / "VADAT").open("a") as stream:
        stream.write("LTE [DC_METH]\n")
    before = (model / "VADAT").read_bytes()
    with pytest.raises(RunnerError, match="changed since preflight"):
        run_plan(plan)
    assert (model / "VADAT").read_bytes() == before


def test_failed_promotion_restores_both_distinct_vadat_files(promotable_model, monkeypatch):
    model = promotable_model
    with (model / "VADAT").open("a") as stream:
        stream.write("LTE [DC_METH]\n1 [T_EXC]\n")
    root_before = (model / "VADAT").read_bytes()
    lte_before = (model / "lte/VADAT").read_bytes()

    def fail(*args, **kwargs):
        raise ModelEditorError("injected finalization failure")

    monkeypatch.setattr(model_workflow, "mark_model_inputs_modified", fail)
    with pytest.raises(model_workflow.ModelWorkflowError, match="injected finalization failure"):
        model_workflow.promote_lte_hydro_results(str(model.parent), model_relpath=model.name)
    assert (model / "VADAT").read_bytes() == root_before
    assert (model / "lte/VADAT").read_bytes() == lte_before
