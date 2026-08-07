from __future__ import annotations

import errno
from pathlib import Path
import shutil

import pytest

from cmfgen_viewer.model_staging import (
    ModelStagingError,
    cleanup_model_directory,
    create_model_from_solution,
    plan_model_cleanup,
    plan_model_from_solution,
    rename_model_directory,
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
        "clean.sh": "#!/bin/sh\nrm -f BAMAT\n",
        "RVSIG_COL": "structure\n",
        "MOD_SUM": "old summary\n",
        "POINT1": "restart pointer\n",
        "SCRTEMP": "restart state\n",
        "HeI_IN": "old input\n",
    }
    for name, content in files.items():
        (source / name).write_text(content, encoding="utf-8")
    (source / "batch.sh").chmod(0o750)
    (source / "clean.sh").chmod(0o750)
    observer = source / "obs"
    observer.mkdir(mode=0o710)
    observer_files = {
        "batobs.sh": "#!/bin/sh\n",
        "bat_ins.sh": "# observer sweep\n",
        "CMF_FLUX_PARAM_INIT": "F [FLUX_CAL_ONLY]\n",
        "IN_FILE": "../RVTJ [RVTJ]\n",
        "CFDAT_IN": "frequency input\n",
        "TWO_PHOT_DATA": "atomic support\n",
        "clean.sh": "#!/bin/sh\nrm -f fort.*\n",
        "batobs.log": "old log\n",
        "CMF_FLUX_PARAM": "generated controls\n",
        "obs_fin": "old spectrum\n",
        "fort.8": "scratch\n",
    }
    for name, content in observer_files.items():
        (observer / name).write_text(content, encoding="utf-8")
    (observer / "batobs.sh").chmod(0o740)
    (observer / "clean.sh").chmod(0o750)


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
    assert mappings["clean.sh"] == "clean.sh"
    assert mappings["obs/batobs.sh"] == "obs/batobs.sh"
    assert mappings["obs/CMF_FLUX_PARAM_INIT"] == "obs/CMF_FLUX_PARAM_INIT"
    assert mappings["obs/clean.sh"] == "obs/clean.sh"
    assert "MOD_SUM" not in mappings
    assert "POINT1" not in mappings
    assert "SCRTEMP" not in mappings
    assert "HeI_IN" not in mappings
    assert "obs/batobs.log" not in mappings
    assert "obs/CMF_FLUX_PARAM" not in mappings
    assert "obs/obs_fin" not in mappings
    assert "obs/fort.8" not in mappings
    assert plan["observer_setup"] is True
    assert plan["warnings"] == []

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
    assert (destination / "clean.sh").stat().st_mode & 0o777 == 0o750
    assert (destination / "obs").stat().st_mode & 0o777 == 0o710
    assert (destination / "obs" / "batobs.sh").stat().st_mode & 0o777 == 0o740
    assert (destination / "obs" / "CMF_FLUX_PARAM_INIT").is_file()
    assert (destination / "obs" / "CFDAT_IN").is_file()
    assert not (destination / "obs" / "batobs.log").exists()
    assert not (destination / "obs" / "CMF_FLUX_PARAM").exists()
    assert not (destination / "obs" / "obs_fin").exists()
    assert destination.stat().st_mode & 0o777 == 0o750
    assert not (destination / "MOD_SUM").exists()


def test_model_creation_uses_root_clean_script_as_observer_fallback(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    (source / "obs" / "clean.sh").unlink()

    plan = plan_model_from_solution(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="model_b",
    )
    observer_clean = next(
        item for item in plan["entries"] if item["destination_name"] == "obs/clean.sh"
    )
    assert observer_clean["source_name"] == "clean.sh"

    create_model_from_solution(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="model_b",
    )
    assert (tmp_path / "model_b" / "obs" / "clean.sh").read_text(encoding="utf-8") == (
        source / "clean.sh"
    ).read_text(encoding="utf-8")


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


def test_rename_model_directory_moves_model_without_changing_contents(tmp_path: Path) -> None:
    source = tmp_path / "grid" / "model_a"
    _write_solution(source)
    (source / "SN_HYDRO_DATA").write_text("sn marker\n", encoding="utf-8")
    (tmp_path / "archive").mkdir()

    renamed = rename_model_directory(
        str(tmp_path),
        source_relpath="grid/model_a",
        destination_relpath="archive/model_b",
    )

    destination = tmp_path / "archive" / "model_b"
    assert renamed["source_relpath"] == "grid/model_a"
    assert renamed["destination_relpath"] == "archive/model_b"
    assert not source.exists()
    assert (destination / "MODEL_SPEC").is_file()
    assert (destination / "SN_HYDRO_DATA").read_text(encoding="utf-8") == "sn marker\n"


def test_rename_model_directory_allows_destination_below_symlink(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    archive = tmp_path / "external-archive"
    archive.mkdir()
    (tmp_path / "archive").symlink_to(archive, target_is_directory=True)

    renamed = rename_model_directory(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="archive/model_b",
    )

    assert renamed["destination_relpath"] == "archive/model_b"
    assert renamed["resolved_destination_path"] == str(archive / "model_b")
    assert (archive / "model_b" / "MODEL_SPEC").is_file()


@pytest.mark.parametrize("destination", ["", ".", "..", "../model_b", "/model_b", "model_a", "model_a/child"])
def test_rename_model_directory_rejects_invalid_destinations(tmp_path: Path, destination: str) -> None:
    _write_solution(tmp_path / "model_a")
    with pytest.raises(ModelStagingError):
        rename_model_directory(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath=destination,
        )


def test_rename_model_directory_does_not_overwrite_existing_entry(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    destination = tmp_path / "model_b"
    destination.mkdir()

    with pytest.raises(ModelStagingError, match="already exists"):
        rename_model_directory(
            str(tmp_path),
            source_relpath="model_a",
            destination_relpath="model_b",
        )

    assert source.is_dir()
    assert destination.is_dir()


def test_rename_model_directory_falls_back_to_cross_filesystem_move(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)

    def fail_cross_device(_source, _destination):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr("cmfgen_viewer.model_staging.os.rename", fail_cross_device)
    renamed = rename_model_directory(
        str(tmp_path),
        source_relpath="model_a",
        destination_relpath="model_b",
    )

    assert renamed["destination_relpath"] == "model_b"
    assert not source.exists()
    assert (tmp_path / "model_b" / "MODEL_SPEC").is_file()


def test_model_cleanup_plans_and_removes_only_canonical_top_level_candidates(tmp_path: Path) -> None:
    source = tmp_path / "model_a"
    _write_solution(source)
    for name in ("BAION", "BAMAT", "BA_ASCI_N_D7", "RUN_SCRATCH_1", "fort.63", "EDDFACTOR"):
        (source / name).write_text(name, encoding="utf-8")
    nested = source / "obs"
    (nested / "BAMAT").write_text("nested", encoding="utf-8")
    link_target = tmp_path / "atomic-data"
    link_target.write_text("shared", encoding="utf-8")
    (source / "atomic_link").symlink_to(link_target)

    plan = plan_model_cleanup(str(tmp_path), model_relpath="model_a")
    names = {str(item["name"]) for item in plan["entries"]}

    assert {"BAION", "BAMAT", "BA_ASCI_N_D7", "RUN_SCRATCH_1", "fort.63", "atomic_link"} <= names
    assert "EDDFACTOR" not in names
    assert "SCRTEMP" not in names
    assert "obs" not in names

    result = cleanup_model_directory(
        str(tmp_path),
        model_relpath="model_a",
        selected_names=sorted(names) + ["MODEL_SPEC"],
    )

    assert result["removed_count"] == len(names)
    assert result["skipped"] == ["MODEL_SPEC"]
    assert all(not (source / name).exists() for name in names)
    assert (source / "EDDFACTOR").is_file()
    assert (source / "SCRTEMP").is_file()
    assert (nested / "BAMAT").is_file()
    assert (source / "MODEL_SPEC").is_file()
    assert link_target.is_file()


def test_model_cleanup_requires_a_valid_explicit_selection(tmp_path: Path) -> None:
    _write_solution(tmp_path / "model_a")

    with pytest.raises(ModelStagingError, match="Select at least one"):
        cleanup_model_directory(str(tmp_path), model_relpath="model_a", selected_names=[])
    with pytest.raises(ModelStagingError, match="invalid file name"):
        cleanup_model_directory(
            str(tmp_path),
            model_relpath="model_a",
            selected_names=["obs/BAMAT"],
        )
