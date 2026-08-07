from __future__ import annotations

import os
from pathlib import Path

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_run_workflow import inspect_main_model_workflow


def _write_model(root: Path) -> Path:
    model = root / "model_a"
    model.mkdir()
    for name in ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS", "GAMMAS_IN", "HI_IN"):
        (model / name).write_text(f"{name}\n", encoding="utf-8")
    return model


def test_main_computation_state_tracks_missing_stale_and_current_results(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    state = inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")
    assert state["ready"] is True
    assert state["result_status"] == "missing"
    assert state["command"].endswith("/model_a && ./batch.sh")

    (model / "MOD_SUM").write_text("old result\n", encoding="utf-8")
    os.utime(model / "MOD_SUM", ns=(1, 1))
    assert inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")["result_status"] == "stale"

    newest_input = max(path.stat().st_mtime_ns for path in model.iterdir() if path.name != "MOD_SUM")
    os.utime(model / "MOD_SUM", ns=(newest_input + 1_000_000, newest_input + 1_000_000))
    current = inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")
    assert current["result_status"] == "current"
    assert current["mod_sum_fresh"] is True


def test_main_computation_page_is_external_only_and_read_write_gated(tmp_path: Path) -> None:
    _write_model(tmp_path)
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True
    client = app.test_client()

    model_page = client.get("/view/model_a")
    assert model_page.status_code == 200
    assert b"Main Computation" in model_page.data
    assert b'/model-actions/main-computation/model_a' in model_page.data

    page = client.get("/model-actions/main-computation/model_a")
    assert page.status_code == 200
    assert b"Main model computation" in page.data
    assert b"never starts CMFGEN" in page.data
    assert b"./batch.sh" in page.data
    assert b"Waiting for" in page.data

    read_only = create_app(basepath=str(tmp_path), read_write_enabled=False, secret_key="test")
    read_only.testing = True
    assert read_only.test_client().get("/model-actions/main-computation/model_a").status_code == 403


def test_main_computation_requires_promoted_structure_when_lte_workspace_exists(
    tmp_path: Path,
) -> None:
    model = _write_model(tmp_path)
    (model / "lte").mkdir()
    blocked = inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")
    assert blocked["ready"] is False
    assert blocked["lte_handoff_required"] is True
    assert blocked["missing"][-2:] == ["RVSIG_COL", "ROSSELAND_LTE_TAB"]

    (model / "RVSIG_COL").write_text("structure\n", encoding="utf-8")
    (model / "ROSSELAND_LTE_TAB").write_text("opacity\n", encoding="utf-8")
    assert inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")["ready"] is True
