from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner_cleanup import build_cleanup_plan
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def cleanup_model(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "model"
    model.mkdir()
    for name, contents in {
        "VADAT": "1 [RSTAR]\n",
        "MODEL_SPEC": "2 [ND]\n1 [NC]\n3 [NP]\n",
        "BAMAT": "matrix state\n",
        "fort.63": "scratch state\n",
        "EDDFACTOR": "retained radiation state\n",
        "SCRTEMP": "retained restart state\n",
    }.items():
        (model / name).write_text(contents, encoding="utf-8")
    external = tmp_path / "atomic-data"
    external.write_text("must remain untouched\n", encoding="utf-8")
    (model / "atomic_link").symlink_to(external)
    return model, external


def test_cleanup_plan_uses_conservative_top_level_candidates(
    cleanup_model: tuple[Path, Path],
) -> None:
    model, _external = cleanup_model

    plan = build_cleanup_plan(model)

    assert plan["ready"] is True
    assert plan["stage"] == "cleanup"
    assert plan["kind"] == "filesystem"
    assert plan["timeout"] is None
    assert {item["name"] for item in plan["entries"]} == {
        "atomic_link",
        "BAMAT",
        "fort.63",
    }
    assert "EDDFACTOR" not in plan["selected_names"]
    assert "SCRTEMP" not in plan["selected_names"]
    assert "executable" not in plan


def test_cleanup_run_archives_files_and_symlink_without_touching_target(
    cleanup_model: tuple[Path, Path],
) -> None:
    model, external = cleanup_model
    events: list[dict[str, object]] = []

    result = run_plan(build_cleanup_plan(model), events.append)

    assert result["status"] == "succeeded"
    assert [item["event"] for item in events] == [
        "stage_started",
        "stage_finished",
        "run_finished",
    ]
    assert result["cleanup"]["removed_count"] == 3
    assert external.read_text(encoding="utf-8") == "must remain untouched\n"
    assert not (model / "BAMAT").exists()
    assert not (model / "fort.63").exists()
    assert not (model / "atomic_link").exists()
    assert (model / "EDDFACTOR").is_file()
    assert (model / "SCRTEMP").is_file()

    archive = Path(result["cleanup"]["archive_path"])
    assert (archive / "BAMAT").read_text(encoding="utf-8") == "matrix state\n"
    assert (archive / "fort.63").is_file()
    assert (archive / "atomic_link").is_symlink()
    assert (archive / "atomic_link").resolve() == external
    report = json.loads((Path(result["journal"]) / "result.json").read_text())
    assert report["status"] == "succeeded"

    repeated = build_cleanup_plan(model)
    assert repeated["ready"] is False
    assert repeated["errors"] == ["No model cleanup candidates were found."]


def test_cleanup_can_be_restricted_to_named_candidates(
    cleanup_model: tuple[Path, Path],
) -> None:
    model, _external = cleanup_model

    result = run_plan(build_cleanup_plan(model, selected_names=["BAMAT"]))

    assert result["status"] == "succeeded"
    assert result["cleanup"]["removed_files"] == ["BAMAT"]
    assert not (model / "BAMAT").exists()
    assert (model / "fort.63").is_file()
    assert (model / "atomic_link").is_symlink()


def test_cleanup_rechecks_candidate_metadata_before_moving_anything(
    cleanup_model: tuple[Path, Path],
) -> None:
    model, _external = cleanup_model
    plan = build_cleanup_plan(model)
    (model / "BAMAT").write_text("changed after preflight and longer\n", encoding="utf-8")

    result = run_plan(plan)

    assert result["status"] == "failed"
    assert result["passes"][0]["problems"] == [
        "Cleanup candidate changed since preflight: BAMAT"
    ]
    assert (model / "BAMAT").is_file()
    assert (model / "fort.63").is_file()
    assert (model / "atomic_link").is_symlink()
    assert not any((Path(result["journal"]) / "removed").iterdir())


def test_cleanup_plan_rejects_unknown_selection(
    cleanup_model: tuple[Path, Path],
) -> None:
    model, _external = cleanup_model

    plan = build_cleanup_plan(model, selected_names=["MOD_SUM"])

    assert plan["ready"] is False
    assert any("Not a current cleanup candidate: MOD_SUM" in error for error in plan["errors"])
    with pytest.raises(RunnerError, match="Preflight failed"):
        run_plan(plan)


def test_cleanup_cli_bypasses_cmfgen_configuration(
    cleanup_model: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model, _external = cleanup_model
    monkeypatch.setattr(
        runner,
        "resolve_runner_config",
        lambda **kwargs: pytest.fail("cleanup must not resolve CMFDIST/ATOMIC"),
    )

    assert runner.main(
        [str(model), "--plan", "--stage", "cleanup", "--cleanup-file", "BAMAT"]
    ) == 0

    captured = capsys.readouterr()
    assert "Cleanup preflight passed" in captured.out
    assert "1 candidate(s)" in captured.out
    assert "BAMAT" in captured.out


def test_cleanup_rejects_execution_only_options(
    cleanup_model: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    model, _external = cleanup_model

    assert runner.main(
        [str(model), "--plan", "--stage", "cleanup", "--threads", "2"]
    ) == 2

    assert "do not apply to cleanup" in capsys.readouterr().err
