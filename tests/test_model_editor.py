from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmfgen_viewer import model_activity

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
from cmfgen_viewer.model_quick_editor import (
    load_quick_model_parameter_cards,
    review_quick_model_parameter_edit,
    save_quick_model_parameter_edit,
)


def _write_model(model: Path, *, newline: str = "\n") -> None:
    model.mkdir(parents=True)
    (model / "MODEL_SPEC").write_bytes(f"10 [ND]{newline}".encode("utf-8"))
    (model / "VADAT").write_bytes(
        f"1.0 [LSTAR] ! luminosity{newline}F [DO_HYDRO]{newline}".encode("utf-8")
    )
    (model / "IN_ITS").write_bytes(f"10 [NUM_ITS]{newline}".encode("utf-8"))
    (model / "batch.sh").write_text("#!/bin/sh\n", encoding="utf-8")


@pytest.mark.parametrize("state", ["active", "unknown"])
def test_editor_refuses_non_idle_models(tmp_path, monkeypatch, state):
    model = tmp_path / "model_a"
    _write_model(model)
    record = load_model_parameter_file(str(tmp_path), model_relpath="model_a", file_relpath="VADAT")
    monkeypatch.setattr(model_activity, "inspect_model_activity", lambda _: {"safe_to_modify": False, "reason": state})
    with pytest.raises(ModelEditorError, match=state):
        save_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                  expected_digest=record["digest"], contents="2 [LSTAR]\n")
    assert (model / "VADAT").read_text() == record["contents"]
    assert not (model / MODEL_EDITOR_BACKUP_DIR).exists()


def test_model_parameter_policy_lists_only_allowlisted_controls(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    (model / "HYDRO_DEFAULTS").write_text("2 [N_ITS]\n", encoding="utf-8")

    listing = list_model_parameter_files(str(tmp_path), model_relpath="model_a")
    by_path = {str(item["file_relpath"]): item for item in listing["files"]}

    assert by_path["VADAT"]["editable"] is True
    assert by_path["HYDRO_DEFAULTS"]["editable"] is True
    assert by_path["obs/CMF_FLUX_PARAM"]["exists"] is False
    assert by_path["obs/CMF_FLUX_PARAM_INIT"]["exists"] is False
    assert "batch.sh" not in by_path


def test_cmf_flux_parameter_template_is_allowlisted_for_full_editor(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    obs = model / "obs"
    obs.mkdir()
    target = obs / "CMF_FLUX_PARAM_INIT"
    target.write_text("15.0 [VTURB_FIX]\n", encoding="utf-8")

    listing = list_model_parameter_files(str(tmp_path), model_relpath="model_a")
    record = next(
        item
        for item in listing["files"]
        if item["file_relpath"] == "obs/CMF_FLUX_PARAM_INIT"
    )
    loaded = load_model_parameter_file(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="obs/CMF_FLUX_PARAM_INIT",
    )

    assert record["exists"] is True
    assert record["editable"] is True
    assert loaded["contents"] == "15.0 [VTURB_FIX]\n"


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


def test_quick_model_parameters_preserve_control_file_structure(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model, newline="\r\n")
    original = (
        "  1.0D+05   [LSTAR] ! luminosity\r\n"
        "2.0D-06     [MDOT] ! mass loss\r\n"
        "3.0         [TEFF] ! intentionally not a quick parameter\r\n"
        "3.5         [LOGG] ! hydro rebuild required\r\n"
        "T           [DO_CL] ! clumping\r\n"
        "EXPO        [CL_LAW]\r\n"
        "0.1         [CL_PAR_1]\r\n"
        "1.0         [HYD/X] ! reference abundance\r\n"
        "2.0D-3      [NIT/X]\r\n"
        "-6.8D-4     [SIL/X] ! negative means mass fraction here\r\n"
    )
    (model / "VADAT").write_bytes(original.encode("utf-8"))

    cards = load_quick_model_parameter_cards(str(tmp_path), model_relpath="model_a")
    vadat = next(card for card in cards if card["file_relpath"] == "VADAT")
    fields = {str(field["key"]): field for field in vadat["fields"]}
    assert "TEFF" not in fields
    assert fields["LSTAR"]["value"] == "1.0D+05"
    assert "LTE/hydro" in str(fields["LOGG"]["notice"])
    assert fields["SIL/X"]["group"] == "Additional abundances"
    assert next(group for group in vadat["groups"] if group["name"] == "Additional abundances")[
        "collapsed"
    ] is True

    values = {key: str(field["value"]) for key, field in fields.items()}
    values.update({"LSTAR": "2.5D+05", "DO_CL": "F", "NIT/X": "3.0D-3"})
    review = review_quick_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="VADAT",
        expected_digest=str(vadat["digest"]),
        values=values,
    )
    proposed = original.replace("1.0D+05", "2.5D+05").replace(
        "T           [DO_CL]", "F           [DO_CL]"
    ).replace("2.0D-3      [NIT/X]", "3.0D-3      [NIT/X]")
    assert review["contents"] == proposed

    saved = save_quick_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="VADAT",
        expected_digest=str(vadat["digest"]),
        reviewed_digest=str(review["proposed_digest"]),
        values=values,
    )
    assert (model / "VADAT").read_bytes() == proposed.encode("utf-8")
    assert (model / str(saved["backup_relpath"])).read_bytes() == original.encode("utf-8")


def test_quick_model_parameters_reject_invalid_or_incomplete_values(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    cards = load_quick_model_parameter_cards(str(tmp_path), model_relpath="model_a")
    vadat = next(card for card in cards if card["file_relpath"] == "VADAT")
    values = {str(field["key"]): str(field["value"]) for field in vadat["fields"]}

    with pytest.raises(ModelEditorError, match="finite number"):
        review_quick_model_parameter_edit(
            str(tmp_path),
            model_relpath="model_a",
            file_relpath="VADAT",
            expected_digest=str(vadat["digest"]),
            values={**values, "LSTAR": "not-a-number"},
        )
    with pytest.raises(ModelEditorError, match="does not match"):
        review_quick_model_parameter_edit(
            str(tmp_path),
            model_relpath="model_a",
            file_relpath="VADAT",
            expected_digest=str(vadat["digest"]),
            values={},
        )
    assert (model / "VADAT").read_text(encoding="utf-8").startswith("1.0 [LSTAR]")


def test_quick_model_parameters_edit_iteration_controls(tmp_path: Path) -> None:
    model = tmp_path / "model_a"
    _write_model(model)
    original = "10 [NUM_ITS] ! iterations\nF [DO_LAM_IT]\nT [DO_T_AUTO]\n"
    proposed = "25 [NUM_ITS] ! iterations\nT [DO_LAM_IT]\nT [DO_T_AUTO]\n"
    (model / "IN_ITS").write_text(original, encoding="utf-8")
    cards = load_quick_model_parameter_cards(str(tmp_path), model_relpath="model_a")
    controls = next(card for card in cards if card["file_relpath"] == "IN_ITS")
    values = {str(field["key"]): str(field["value"]) for field in controls["fields"]}
    values.update({"NUM_ITS": "25", "DO_LAM_IT": "T"})

    review = review_quick_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="IN_ITS",
        expected_digest=str(controls["digest"]),
        values=values,
    )
    assert review["contents"] == proposed

    save_quick_model_parameter_edit(
        str(tmp_path),
        model_relpath="model_a",
        file_relpath="IN_ITS",
        expected_digest=str(controls["digest"]),
        reviewed_digest=str(review["proposed_digest"]),
        values=values,
    )
    assert (model / "IN_ITS").read_text(encoding="utf-8") == proposed


def _scaling_model(tmp_path):
    model = tmp_path / "model_a"
    _write_model(model, newline="\r\n")
    contents = (
        "1.0D5 [LSTAR] ! luminosity\r\n"
        "70.0 [RSTAR] ! core radius\r\n"
        "10.0 [MASS] ! stellar mass\r\n"
        "3.0 [TEFF] ! fixed temperature\r\n"
        "3.50D0 [LOGG] ! fixed gravity\r\n"
        "2D-6 [MDOT] ! unchanged wind\r\n"
    )
    (model / "VADAT").write_bytes(contents.encode())
    card = load_quick_model_parameter_cards(str(tmp_path), model_relpath="model_a")[0]
    values = {field["key"]: field["value"] for field in card["fields"]}
    return model, contents, card, values


def test_luminosity_scaling_preserves_temperature_gravity_and_file_layout(tmp_path):
    model, original, card, values = _scaling_model(tmp_path)
    values.update(LSTAR="4D5", RSTAR="999", MASS="999", LOGG="3.5")
    kwargs = dict(model_relpath="model_a", file_relpath="VADAT", expected_digest=card["digest"],
                  values=values, keep_temperature_logg=True)
    review = review_quick_model_parameter_edit(str(tmp_path), **kwargs)
    proposed = original.replace("1.0D5", "4D5").replace("70.0", "140").replace("10.0", "40")
    assert review["contents"] == proposed
    assert review["card"]["keep_temperature_logg"]
    assert any("Scaling preserves this discrepancy" in warning for warning in review["warnings"])
    assert (model / "VADAT").read_bytes() == original.encode()
    # The save form posts the derived values; recomputation still uses the saved baseline.
    kwargs["values"] = {field["key"]: field["value"] for field in review["card"]["fields"]}
    repeated = review_quick_model_parameter_edit(str(tmp_path), **kwargs)
    assert repeated["proposed_digest"] == review["proposed_digest"]
    saved = save_quick_model_parameter_edit(str(tmp_path), reviewed_digest=review["proposed_digest"], **kwargs)
    assert (model / "VADAT").read_bytes() == proposed.encode()
    assert (model / saved["backup_relpath"]).read_bytes() == original.encode()


@pytest.mark.parametrize("luminosity", ["0", "-1", "NaN", "1e309", "1e-320"])
def test_luminosity_scaling_rejects_invalid_and_unrepresentable_values(tmp_path, luminosity):
    model, original, card, values = _scaling_model(tmp_path)
    values["LSTAR"] = luminosity
    with pytest.raises(ModelEditorError):
        review_quick_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                         expected_digest=card["digest"], values=values, keep_temperature_logg=True)
    assert (model / "VADAT").read_bytes() == original.encode()


def test_luminosity_scaling_rejects_gravity_edits_and_missing_controls(tmp_path):
    model, original, card, values = _scaling_model(tmp_path)
    values["LOGG"] = "4"
    with pytest.raises(ModelEditorError, match="LOGG.*unchanged"):
        review_quick_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                         expected_digest=card["digest"], values=values, keep_temperature_logg=True)
    (model / "VADAT").write_text(original.replace("3.0 [TEFF]", "3.0 [OTHER]"))
    card = load_quick_model_parameter_cards(str(tmp_path), model_relpath="model_a")[0]
    assert not card["luminosity_scaling"]["available"]
    with pytest.raises(ModelEditorError, match="TEFF"):
        review_quick_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                         expected_digest=card["digest"], values=values, keep_temperature_logg=True)


def test_luminosity_scaling_noop_preserves_original_notation_and_requires_review(tmp_path):
    model, original, card, values = _scaling_model(tmp_path)
    kwargs = dict(model_relpath="model_a", file_relpath="VADAT", expected_digest=card["digest"],
                  values=values, keep_temperature_logg=True)
    assert not review_quick_model_parameter_edit(str(tmp_path), **kwargs)["changed"]
    values["LSTAR"] = "4D5"
    review = review_quick_model_parameter_edit(str(tmp_path), **kwargs)
    values["LSTAR"] = "9D5"
    with pytest.raises(ModelEditorError, match="changed after review"):
        save_quick_model_parameter_edit(str(tmp_path), reviewed_digest=review["proposed_digest"], **kwargs)
    assert (model / "VADAT").read_bytes() == original.encode()


@pytest.mark.parametrize("factor", [2, 0.25])
def test_luminosity_scaling_preserves_stefan_boltzmann_and_gravity_ratios(tmp_path, factor):
    _, _, card, values = _scaling_model(tmp_path)
    values["LSTAR"] = str(1e5 * factor)
    review = review_quick_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                             expected_digest=card["digest"], values=values, keep_temperature_logg=True)
    result = review["values"]
    luminosity, radius, mass = (float(result[key]) for key in ("LSTAR", "RSTAR", "MASS"))
    assert luminosity / radius ** 2 == pytest.approx(1e5 / 70 ** 2)
    assert mass / radius ** 2 == pytest.approx(10 / 70 ** 2)


def test_luminosity_scaling_unchecked_allows_independent_radius_mass_and_gravity_edits(tmp_path):
    _, _, card, values = _scaling_model(tmp_path)
    values.update(LSTAR="4D5", RSTAR="80", MASS="15", LOGG="4")
    review = review_quick_model_parameter_edit(str(tmp_path), model_relpath="model_a", file_relpath="VADAT",
                                             expected_digest=card["digest"], values=values)
    assert review["values"] == values
    assert not review["keep_temperature_logg"]
