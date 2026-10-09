from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner_recipe import RunnerError


def _sequence(model: Path, stages: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "profile": "ostar-v1",
        "kind": "sequence",
        "stage": "sequence",
        "model": str(model),
        "cwd": str(model),
        "stages": stages,
        "stage_options": {
            "native_config": {},
            "timeout": None,
            "memory_mib": 4096,
            "iterations": None,
            "fresh_start": False,
            "fresh_start_stage": None,
            "cleanup_files": None,
        },
        "configuration_sources": {},
        "warnings": [],
        "errors": [],
        "ready": True,
    }


def _ready_stage(stage: str) -> dict[str, object]:
    return {
        "stage": stage,
        "ready": True,
        "errors": [],
        "warnings": [],
    }


def _stage_result(stage: str, status: str = "succeeded") -> dict[str, object]:
    return {
        "stage": stage,
        "status": status,
        "passes": [
            {
                "id": stage,
                "status": "succeeded" if status == "initialized" else status,
                "problems": [] if status in {"initialized", "succeeded"} else ["native failure"],
            }
        ],
    }


def test_sequence_build_is_serializable_and_only_preflights_first_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    built: list[tuple[str, bool]] = []

    def build(_model, stage, **options):
        built.append((stage, options["fresh_start"]))
        return {**_ready_stage(stage), "model": str(model)}

    monkeypatch.setattr(runner, "_build_requested_stage_plan", build)

    plan = runner.build_sequence_plan(
        model,
        ["lte", "hydro", "promote", "init", "main"],
        native_config={
            "cmfgen_root": tmp_path / "cmf",
            "atomic_root": tmp_path / "atomic",
            "threads": 2,
        },
        configuration_sources={"threads": "cli"},
        timeout=60,
        memory_mib=2048,
        iterations=2,
        fresh_start=True,
        cleanup_files=None,
    )

    assert built == [("lte", False)]
    assert plan["stage_options"]["fresh_start_stage"] == "init"
    assert plan["initial_plan"]["stage"] == "lte"
    assert json.loads(json.dumps(plan))["stages"][-1] == "main"


def test_sequence_rebuilds_each_preflight_after_predecessor_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    stages = ["lte", "hydro", "promote"]
    built: list[str] = []
    executed: list[str] = []

    def build(_sequence, stage, **_options):
        index = stages.index(stage)
        if index:
            assert (model / f"{stages[index - 1]}.done").is_file()
        built.append(stage)
        return _ready_stage(stage)

    def execute(plan, emit=None):
        stage = plan["stage"]
        executed.append(stage)
        (model / f"{stage}.done").write_text("accepted\n", encoding="utf-8")
        return _stage_result(stage)

    monkeypatch.setattr(runner, "_sequence_stage_plan", build)
    monkeypatch.setattr(runner, "run_plan", execute)

    result = runner._run_sequence_plan(_sequence(model, stages))

    assert result["status"] == "succeeded"
    assert result["completed_stages"] == stages
    assert result["remaining_stages"] == []
    assert built == stages
    assert executed == stages
    assert Path(result["journal"]).joinpath("stage-03-promote-plan.json").is_file()


@pytest.mark.parametrize("resource_options", [{}, {"memory_mib": 2048, "no_core_dumps": True}])
def test_sequence_preserves_opt_in_resource_settings_after_serialization(tmp_path, monkeypatch, resource_options):
    def build(model, *, stage, **options):
        return {**_ready_stage(stage), "model": str(model), **options}

    monkeypatch.setattr(runner, "build_run_plan", build)
    sequence = runner.build_sequence_plan(
        tmp_path,
        ["init", "main"],
        native_config={"threads": None},
        configuration_sources={},
        timeout=None,
        iterations=None,
        fresh_start=False,
        cleanup_files=None,
        **resource_options,
    )
    restored = json.loads(json.dumps(sequence))
    later = runner._sequence_stage_plan(restored, "main", timeout=None)
    for plan in (restored["initial_plan"], later):
        assert plan["threads"] is None
        assert plan["timeout"] is None
        assert plan["memory_mib"] == resource_options.get("memory_mib")
        assert plan["no_core_dumps"] == resource_options.get("no_core_dumps", False)


def test_real_filesystem_sequence_runs_cleanup_then_promotion(tmp_path: Path) -> None:
    model = tmp_path / "model"
    lte = model / "lte"
    lte.mkdir(parents=True)
    root_files = {
        "VADAT": "3.5 [LOGG]\n3.0D0 [TEFF]\nF [CHK_NG]\n",
        "MODEL_SPEC": "2 [ND]\n1 [NC]\n3 [NP]\n",
        "clean.sh": "#!/bin/sh\n",
        "BAMAT": "cleanup candidate\n",
    }
    for name, contents in root_files.items():
        (model / name).write_text(contents, encoding="utf-8")
    lte_files = {
        "VADAT": root_files["VADAT"],
        "MODEL_SPEC": root_files["MODEL_SPEC"],
        "clean.sh": root_files["clean.sh"],
        "GRID_PARAMS": "grid\n",
        "ltebat.sh": "#!/bin/sh\n",
        "HYDRO_PARAMS": "hydro\n",
    }
    for name, contents in lte_files.items():
        (lte / name).write_text(contents, encoding="utf-8")
    latest_input = max((lte / name).stat().st_mtime_ns for name in lte_files)
    rosseland = lte / "ROSSELAND_LTE_TAB"
    rosseland.write_text("rosseland output\n", encoding="utf-8")
    os.utime(rosseland, ns=(latest_input + 1_000_000, latest_input + 1_000_000))
    hydro = lte / "RVSIG_COL_NEW"
    hydro.write_text(
        "! Ratio of inner to outer radius is: 2.0\n"
        "2 ! Number of depth points\n"
        "2.0 3.0 4.0 5.0 1\n"
        "1.0 2.0 3.0 4.0 2\n",
        encoding="utf-8",
    )
    os.utime(hydro, ns=(latest_input + 2_000_000, latest_input + 2_000_000))
    plan = runner.build_sequence_plan(
        model,
        ["cleanup", "promote"],
        native_config={},
        configuration_sources={},
        timeout=None,
        memory_mib=4096,
        iterations=None,
        fresh_start=False,
        cleanup_files=["BAMAT"],
    )

    result = runner.run_plan(plan)

    assert result["status"] == "succeeded"
    assert result["completed_stages"] == ["cleanup", "promote"]
    assert result["scientific_acceptance"] == "not applicable"
    assert not (model / "BAMAT").exists()
    assert (model / "RVSIG_COL").is_file()
    cleanup_result, promotion_result = result["stage_results"]
    assert Path(cleanup_result["cleanup"]["archive_path"], "BAMAT").is_file()
    assert promotion_result["promotion"]["synchronized_rmax"] == 2.0


def test_sequence_stops_before_next_stage_after_execution_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    built: list[str] = []
    executed: list[str] = []

    def build(_sequence, stage, **_options):
        built.append(stage)
        return _ready_stage(stage)

    def execute(plan, emit=None):
        executed.append(plan["stage"])
        return _stage_result(plan["stage"], "invalid_output")

    monkeypatch.setattr(runner, "_sequence_stage_plan", build)
    monkeypatch.setattr(runner, "run_plan", execute)

    result = runner._run_sequence_plan(_sequence(model, ["init", "main", "flux"]))

    assert result["status"] == "invalid_output"
    assert result["failed_stage"] == "init"
    assert result["completed_stages"] == []
    assert result["remaining_stages"] == ["main", "flux"]
    assert built == ["init"]
    assert executed == ["init"]


def test_sequence_stops_on_just_in_time_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    built: list[str] = []
    executed: list[str] = []

    def build(_sequence, stage, **_options):
        built.append(stage)
        if stage == "hydro":
            return {
                "stage": stage,
                "ready": False,
                "errors": ["Rosseland table is invalid"],
                "warnings": [],
            }
        return _ready_stage(stage)

    def execute(plan, emit=None):
        executed.append(plan["stage"])
        return _stage_result(plan["stage"])

    monkeypatch.setattr(runner, "_sequence_stage_plan", build)
    monkeypatch.setattr(runner, "run_plan", execute)

    result = runner._run_sequence_plan(_sequence(model, ["lte", "hydro", "promote"]))

    assert result["status"] == "preflight_failed"
    assert result["failed_stage"] == "hydro"
    assert result["completed_stages"] == ["lte"]
    assert result["remaining_stages"] == ["promote"]
    assert result["stage_results"][1]["problems"] == ["Rosseland table is invalid"]
    assert built == ["lte", "hydro"]
    assert executed == ["lte"]


def test_fresh_start_applies_only_to_first_cmfgen_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    plan = _sequence(model, ["init", "main"])
    plan["stage_options"]["fresh_start"] = True
    plan["stage_options"]["fresh_start_stage"] = "init"
    observed: list[tuple[str, bool]] = []

    def build(_model, stage, **options):
        observed.append((stage, options["fresh_start"]))
        return _ready_stage(stage)

    monkeypatch.setattr(runner, "_build_requested_stage_plan", build)

    runner._sequence_stage_plan(plan, "init", timeout=None)
    runner._sequence_stage_plan(plan, "main", timeout=None)

    assert observed == [("init", True), ("main", False)]


def test_timeout_budget_is_reduced_before_next_native_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = tmp_path / "model"
    model.mkdir()
    plan = _sequence(model, ["init", "main"])
    plan["stage_options"]["timeout"] = 10.0
    observed: list[tuple[str, float | None]] = []
    clock = iter((100.0, 103.0, 104.0, 106.5))

    def build(_sequence, stage, *, timeout):
        observed.append((stage, timeout))
        return _ready_stage(stage)

    def execute(stage_plan, emit=None):
        status = "initialized" if stage_plan["stage"] == "init" else "succeeded"
        return _stage_result(stage_plan["stage"], status)

    monkeypatch.setattr(runner, "_sequence_stage_plan", build)
    monkeypatch.setattr(runner, "run_plan", execute)
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))

    result = runner._run_sequence_plan(plan)

    assert result["status"] == "succeeded"
    assert observed == [("init", 10.0), ("main", 7.0)]


def test_sequence_rejects_duplicate_stages(tmp_path: Path) -> None:
    with pytest.raises(RunnerError, match="duplicate stages"):
        runner.build_sequence_plan(
            tmp_path,
            ["main", "main"],
            native_config={},
            configuration_sources={},
            timeout=None,
            memory_mib=4096,
            iterations=None,
            fresh_start=False,
            cleanup_files=None,
        )
