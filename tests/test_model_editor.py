from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmfgen_viewer.model_editor import (
    ConcurrentModelEditError,
    MODEL_EDITOR_BACKUP_DIR,
    MODEL_INPUT_MODIFIED_MARKER,
    ModelEditorError,
    list_model_parameter_checkpoints,
    list_model_parameter_files,
    load_model_parameter_checkpoint,
    load_model_parameter_file,
    model_inputs_modified_since_solution,
    review_model_parameter_edit,
    save_model_parameter_edit,
)


def _write_model(model: Path, *, newline: str = "\n") -> None:
    model.mkdir(parents=True)
    (model / "MODEL_SPEC").write_bytes(f"10 [ND]{newline}".encode("utf-8"))
    (model / "VADAT").write_bytes(
        f"1.0 [LSTAR] ! luminosity{newline}F [DO_HYDRO]{newline}".encode("utf-8")
    )
    (model / "IN_ITS").write_bytes(f"10 [NUM_ITS]{newline}".encode("utf-8"))
    (model / "batch.sh").write_text("#!/bin/sh\n", encoding="utf-8")


def test_model_parameter_policy_lists_only_allowlisted_controls(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    (model / "HYDRO_DEFAULTS").write_text("2 [N_ITS]\n", encoding="utf-8")

    listing = list_model_parameter_files(str(tmp_path), model_relpath="model_a")
    by_path = {str(item["file_relpath"]): item for item in listing["files"]}

    assert by_path["VADAT"]["editable"] is True
    assert by_path["HYDRO_DEFAULTS"]["editable"] is True
    assert by_path["obs/CMF_FLUX_PARAM"]["exists"] is False
    assert "batch.sh" not in by_path


def test_model_parameter_review_and_save_preserve_format_and_create_backup(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model, newline="\r\n")
    target = model / "VADAT"
    target.chmod(0o640)
    loaded = load_model_parameter_file(str(tmp_path), model_relpath="model_a", file_relpath="VADAT")
    proposed = str(loaded["contents"]).replace("1.0 [LSTAR]", "2.0 [LSTAR]")

    review = review_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="VADAT",
        expected_digest=str(loaded["digest"]),
        contents=proposed,
    )
    assert review["changed"] is True
    assert any(line["kind"] == "added" for line in review["diff_lines"])

    saved = save_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="VADAT",
        expected_digest=str(loaded["digest"]),
        contents=proposed,
    )

    assert target.read_bytes() == b"2.0 [LSTAR] ! luminosity\r\nF [DO_HYDRO]\r\n"
    assert target.stat().st_mode & 0o777 == 0o640
    backup = model / str(saved["backup_relpath"])
    assert backup.read_bytes() == b"1.0 [LSTAR] ! luminosity\r\nF [DO_HYDRO]\r\n"
    assert MODEL_EDITOR_BACKUP_DIR in backup.parts
    assert (model / MODEL_INPUT_MODIFIED_MARKER).is_file()
    assert model_inputs_modified_since_solution(model) is True
    checkpoints = list_model_parameter_checkpoints(
        str(tmp_path), model_relpath="model_a", file_relpath="VADAT"
    )
    assert [item["name"] for item in checkpoints] == [backup.name]
    checkpoint = load_model_parameter_checkpoint(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="VADAT",
        checkpoint_name=backup.name,
    )
    assert checkpoint["contents"] == "1.0 [LSTAR] ! luminosity\r\nF [DO_HYDRO]\r\n"


def test_model_parameter_editor_rejects_symlinks_and_concurrent_changes(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    loaded = load_model_parameter_file(str(tmp_path), model_relpath="model_a", file_relpath="VADAT")
    (model / "VADAT").write_text("3.0 [LSTAR]\n", encoding="utf-8")

    with pytest.raises(ConcurrentModelEditError, match="changed"):
        review_model_parameter_edit(
            str(tmp_path),
            model_relpath="model_a",
            file_relpath="VADAT",
            expected_digest=str(loaded["digest"]),
            contents="2.0 [LSTAR]\n",
        )

    shared = tmp_path / "shared-vadat"
    shared.write_text("4.0 [LSTAR]\n", encoding="utf-8")
    (model / "VADAT").unlink()
    (model / "VADAT").symlink_to(shared)
    with pytest.raises(ModelEditorError, match="non-symlinked"):
        load_model_parameter_file(str(tmp_path), model_relpath="model_a", file_relpath="VADAT")


def test_model_parameter_editor_rejects_unreviewed_or_unchanged_payload(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    loaded = load_model_parameter_file(str(tmp_path), model_relpath="model_a", file_relpath="IN_ITS")

    with pytest.raises(ModelEditorError, match="No changes"):
        save_model_parameter_edit(
            str(tmp_path),
            model_relpath="model_a",
            file_relpath="IN_ITS",
            expected_digest=str(loaded["digest"]),
            contents=str(loaded["contents"]),
        )
    assert hashlib.sha256((model / "IN_ITS").read_bytes()).hexdigest() == loaded["digest"]
    with pytest.raises(ModelEditorError, match="invalid"):
        load_model_parameter_checkpoint(
            str(tmp_path),
            model_relpath="model_a",
            file_relpath="IN_ITS",
            checkpoint_name="../IN_ITS.bak",
        )
