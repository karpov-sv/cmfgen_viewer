from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from cmfgen_viewer.model_staging import (
    ModelStagingError,
    create_model_from_solution,
    plan_model_from_solution,
)


def _write_solution(source: Path) -> None:
    source.mkdir(parents=True)
    files = {
        "batch.sh": "#!/bin/sh\n",
        "IN_ITS": "1 [NUM_ITS]\n",
        "VADAT": "1 [LSTAR]\n",
        "MODEL_SPEC": "10 [ND]\n",
        "GAMMAS": "gamma-state\n",
        "HeIOUT": "helium-state\n",
        "GREY_SCL_FACOUT": "grey-state\n",
        "batch_ins.sh": "#!/bin/sh\n",
        "RVSIG_COL": "structure\n",
        "MOD_SUM": "old summary\n",
        "POINT1": "restart pointer\n",
        "SCRTEMP": "restart state\n",
        "HeI_IN": "old input\n",
    }
    for name, content in files.items():
        (source / name).write_text(content, encoding="utf-8")
    (source / "batch.sh").chmod(0o750)


def test_plan_and_create_model_from_solution(tmp_path: Path) -> None:
    source = tmp_path / "grid" / "model_a"
    _write_solution(source)
    source.chmod(0o750)

    plan = plan_model_from_solution(
        str(tmp_path),
        source_relpath="grid/model_a",
        destination_relpath="grid/model_b",
    )

    assert plan["ready"] is True
    assert plan["missing_required"] == []
    mappings = {item["source_name"]: item["destination_name"] for item in plan["entries"]}
    assert mappings["GAMMAS"] == "GAMMAS_IN"
    assert mappings["HeIOUT"] == "HeI_IN"
    assert mappings["GREY_SCL_FACOUT"] == "GREY_SCL_FAC_IN"
    assert mappings["batch_ins.sh"] == "batch_ins.sh"
    assert "MOD_SUM" not in mappings
    assert "POINT1" not in mappings
    assert "SCRTEMP" not in mappings
    assert "HeI_IN" not in mappings

    created = create_model_from_solution(
        str(tmp_path),
        source_relpath="grid/model_a",
        destination_relpath="grid/model_b",
    )
    destination = tmp_path / "grid" / "model_b"
    assert created["destination_relpath"] == "grid/model_b"
    assert (destination / "GAMMAS_IN").read_text(encoding="utf-8") == "gamma-state\n"
    assert (destination / "HeI_IN").read_text(encoding="utf-8") == "helium-state\n"
    assert (destination / "GREY_SCL_FAC_IN").is_file()
    assert (destination / "batch.sh").stat().st_mode & 0o777 == 0o750
    assert destination.stat().st_mode & 0o777 == 0o750
    assert not (destination / "MOD_SUM").exists()


def test_model_creation_rejects_missing_inputs_existing_targets_and_sn(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    (source / "GAMMAS").unlink()

    plan = plan_model_from_solution(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="model_b",
    )
    assert plan["ready"] is False
    assert plan["missing_required"] == ["GAMMAS"]
    with pytest.raises(ModelStagingError, match="missing required files"):
        create_model_from_solution(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath="model_b",
        )

    (source / "GAMMAS").write_text("gamma\n", encoding="utf-8")
    (tmp_path / "model_b").mkdir()
    with pytest.raises(ModelStagingError, match="already exists"):
        plan_model_from_solution(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath="model_b",
        )

    (source / "SN_HYDRO_DATA").write_text("sn\n", encoding="utf-8")
    with pytest.raises(ModelStagingError, match="SN solution"):
        plan_model_from_solution(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath="model_c",
        )


def test_model_creation_requires_at_least_one_solution_output(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    for entry in source.iterdir():
        if entry.name.endswith("OUT"):
            entry.unlink()

    plan = plan_model_from_solution(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="model_b",
    )

    assert plan["ready"] is False
    assert plan["missing_required"] == ["*OUT"]


@pytest.mark.parametrize("destination", ["../model_b", "/tmp/model_b", "model_a/child", "model_a"])
def test_model_creation_rejects_invalid_destinations(tmp_path: Path, destination: str) -> None:
    _write_solution(tmp_path / "model_a")
    with pytest.raises(ModelStagingError):
        plan_model_from_solution(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath=destination,
        )


def test_model_creation_allows_destination_below_external_symlink(tmp_path: Path) -> None:
    _write_solution(tmp_path / "model_a")
    archive = tmp_path / "external-archive"
    archive.mkdir()
    (tmp_path / "archive").symlink_to(archive, target_is_directory=True)

    plan = create_model_from_solution(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="archive/model_b",
    )

    assert (archive / "model_b" / "MODEL_SPEC").is_file()
    assert plan["resolved_destination_path"] == str(archive / "model_b")


def test_model_creation_removes_staging_directory_after_copy_failure(tmp_path: Path, monkeypatch) -> None:
    _write_solution(tmp_path / "model_a")
    real_copy2 = shutil.copy2
    copied = 0

    def failing_copy2(source, destination, *, follow_symlinks=True):
        nonlocal copied
        copied += 1
        if copied == 2:
            raise OSError("simulated copy failure")
        return real_copy2(source, destination, follow_symlinks=follow_symlinks)

    monkeypatch.setattr("cmfgen_viewer.model_staging.shutil.copy2", failing_copy2)
    with pytest.raises(ModelStagingError, match="simulated copy failure"):
        create_model_from_solution(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath="model_b",
        )

    assert not (tmp_path / "model_b").exists()
    assert list(tmp_path.glob(".cmfgen-create-*")) == []
