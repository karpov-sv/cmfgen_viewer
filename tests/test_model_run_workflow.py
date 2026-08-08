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


def test_generated_gammas_does_not_stale_result_when_gammas_in_exists(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    (model / "MOD_SUM").write_text("result\n", encoding="utf-8")
    newest_input = max(path.stat().st_mtime_ns for path in model.iterdir())
    result_mtime = newest_input + 1_000_000
    os.utime(model / "MOD_SUM", ns=(result_mtime, result_mtime))
    (model / "GAMMAS").write_text("generated output\n", encoding="utf-8")
    os.utime(model / "GAMMAS", ns=(result_mtime + 1_000_000, result_mtime + 1_000_000))

    state = inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")

    assert state["result_status"] == "current"
    gamma = next(item for item in state["prerequisites"] if item["name"] == "GAMMAS_IN or GAMMAS")
    assert gamma["modified_ns"] == (model / "GAMMAS_IN").stat().st_mtime_ns


def test_gammas_fallback_remains_a_freshness_dependency(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    (model / "GAMMAS_IN").unlink()
    (model / "GAMMAS").write_text("fallback input\n", encoding="utf-8")
    (model / "MOD_SUM").write_text("result\n", encoding="utf-8")
    input_mtime = (model / "GAMMAS").stat().st_mtime_ns
    os.utime(model / "MOD_SUM", ns=(input_mtime + 1_000_000, input_mtime + 1_000_000))
    assert (
        inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")["result_status"]
        == "current"
    )

    os.utime(model / "GAMMAS", ns=(input_mtime + 2_000_000, input_mtime + 2_000_000))
    assert (
        inspect_main_model_workflow(str(tmp_path), model_relpath="model_a")["result_status"]
        == "stale"
    )


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
    assert b"Process and progress" in page.data
    assert b"Latest run diagnostics" in page.data
    assert b"CMFGEN \xc2\xb7 Unknown" in page.data
    assert b"CMF_FLUX \xc2\xb7 Unknown" in page.data
    assert b'/model-actions/runtime/main/model_a' in page.data
    assert b"model_runtime.js" in page.data

    runtime = client.get("/model-actions/runtime/main/model_a")
    assert runtime.status_code == 200
    assert runtime.json["kind"] == "main"
    assert runtime.json["active"] is False
    assert [item["status"] for item in runtime.json["diagnostics"]] == [
        "unknown",
        "unknown",
    ]
    assert runtime.headers["Cache-Control"] == "no-store"

    read_only = create_app(basepath=str(tmp_path), read_write_enabled=False, secret_key="test")
    read_only.testing = True
    assert read_only.test_client().get("/model-actions/main-computation/model_a").status_code == 403
    assert read_only.test_client().get("/model-actions/runtime/main/model_a").status_code == 403


def test_main_computation_page_shows_recorded_cmfgen_and_flux_progress(tmp_path: Path) -> None:
    model = _write_model(tmp_path)
    (model / "IN_ITS").write_text("1 [NUM_ITS]\n", encoding="utf-8")
    (model / "OUTGEN").write_text(
        "Model started on: now\nCurrent great iteration count is 1\n",
        encoding="utf-8",
    )
    obs = model / "obs"
    obs.mkdir()
    (obs / "batobs.sh").write_text(
        "$PROG_CMF_OBS < IN_FILE >>& batobs.log\n",
        encoding="utf-8",
    )
    (obs / "batobs.log").write_text(
        "PID of /opt/cmfgen/exe/cmf_flux.exe is: 123\nProgram finished on: now\n",
        encoding="utf-8",
    )
    app = create_app(basepath=str(tmp_path), read_write_enabled=True, secret_key="test")
    app.testing = True

    page = app.test_client().get("/model-actions/main-computation/model_a")

    assert page.status_code == 200
    assert b"Last recorded CMFGEN progress" in page.data
    assert b"Last recorded CMF_FLUX progress" in page.data


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
