from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_promotion import build_promotion_plan
from cmfgen_viewer.runner_recipe import RunnerError


GENERATED_RVSIG = (
    "! Ratio of inner to outer radius is: 2.0\n"
    "2 ! Number of depth points\n"
    "2.0 3.0 4.0 5.0 1\n"
    "1.0 2.0 3.0 4.0 2\n"
)


@pytest.fixture
def promotable_model(tmp_path: Path) -> Path:
    model = tmp_path / "model"
    lte = model / "lte"
    lte.mkdir(parents=True)
    root_files = {
        "VADAT": "3.5 [LOGG]\n3.0D0 [TEFF]\nF [CHK_NG]\n",
        "MODEL_SPEC": "2 [ND]\n1 [NC]\n3 [NP]\n",
        "clean.sh": "#!/bin/sh\n",
        "batch.sh": "#!/bin/sh\n",
        "IN_ITS": "2 [NUM_ITS]\n",
        "RVSIG_COL": "previous structure\n",
        "POINT1": "previous checkpoint\n",
        "MOD_SUM": "previous solution\n",
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
    hydro.write_text(GENERATED_RVSIG, encoding="utf-8")
    os.utime(hydro, ns=(latest_input + 2_000_000, latest_input + 2_000_000))
    return model


def test_promotion_plan_needs_no_executable_configuration(promotable_model: Path) -> None:
    plan = build_promotion_plan(promotable_model)

    assert plan["ready"] is True
    assert plan["stage"] == "promote"
    assert plan["kind"] == "filesystem"
    assert plan["synchronized_rmax"] == 2.0
    assert plan["timeout"] is None
    assert "POINT1" in plan["invalidates"]
    assert "executable" not in plan


def test_runner_promotes_with_backup_and_invalidates_old_main_state(
    promotable_model: Path,
) -> None:
    events: list[dict[str, object]] = []

    result = run_plan(build_promotion_plan(promotable_model), events.append)

    assert result["status"] == "succeeded"
    assert [item["event"] for item in events] == [
        "stage_started",
        "stage_finished",
        "run_finished",
    ]
    promotion = result["promotion"]
    assert promotion["synchronized_rmax"] == 2.0
    assert set(promotion["invalidated_files"]) == {"POINT1", "MOD_SUM"}
    assert Path(promotion["backup_path"]).is_dir()
    assert (promotable_model / "RVSIG_COL").read_text() == GENERATED_RVSIG
    assert (promotable_model / "RVSIG_COL_NEW").read_text() == GENERATED_RVSIG
    assert not (promotable_model / "POINT1").exists()
    assert not (promotable_model / "MOD_SUM").exists()
    report = Path(result["journal"]) / "result.json"
    assert json.loads(report.read_text())["status"] == "succeeded"

    repeated = build_promotion_plan(promotable_model)
    assert repeated["ready"] is False
    assert "already match" in repeated["errors"][0]


def test_promotion_plan_blocks_stale_lte_result(promotable_model: Path) -> None:
    output = promotable_model / "lte" / "ROSSELAND_LTE_TAB"
    os.utime(output, ns=(1, 1))

    plan = build_promotion_plan(promotable_model)

    assert plan["ready"] is False
    assert "Fresh lte/ROSSELAND_LTE_TAB" in plan["errors"][0]
    with pytest.raises(RunnerError, match="Preflight failed"):
        run_plan(plan)


def test_promotion_rechecks_destination_snapshots(promotable_model: Path) -> None:
    plan = build_promotion_plan(promotable_model)
    (promotable_model / "RVSIG_COL").write_text("changed after plan\n", encoding="utf-8")

    with pytest.raises(RunnerError, match="Input changed since preflight"):
        run_plan(plan)


def test_promotion_cli_bypasses_cmfgen_configuration(
    promotable_model: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        runner,
        "resolve_runner_config",
        lambda **kwargs: pytest.fail("promotion must not resolve CMFDIST/ATOMIC"),
    )

    assert runner.main([str(promotable_model), "--plan", "--stage", "promote"]) == 0

    captured = capsys.readouterr()
    assert "Promotion preflight passed" in captured.out
    assert "no native executable" in captured.out


def test_promotion_rejects_execution_only_options(
    promotable_model: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert runner.main(
        [str(promotable_model), "--plan", "--stage", "promote", "--timeout", "60"]
    ) == 2

    assert "do not apply to promotion" in capsys.readouterr().err
