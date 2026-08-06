from __future__ import annotations

from pathlib import Path

import pytest

from cmfgen_viewer import browser


def _write_file(path: Path, contents: str) -> None:
    path.write_text(contents, encoding="utf-8")


def test_resolve_path_accepts_safe_relative_targets(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    resolved = browser.resolve_path(str(tmp_path), "nested")
    assert resolved == nested.resolve()


def test_resolve_path_rejects_absolute_and_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        browser.resolve_path(str(tmp_path), "/etc/passwd")
    with pytest.raises(FileNotFoundError):
        browser.resolve_path(str(tmp_path), "../outside")


def test_classify_cmfgen_role_covers_key_categories() -> None:
    assert browser.classify_cmfgen_role("MODEL_SPEC") == "input_control"
    assert browser.classify_cmfgen_role("RVTJ") == "core_viewer"
    assert browser.classify_cmfgen_role("HYDRO_PARAMS") == "input_hydro_iteration"
    assert browser.classify_cmfgen_role("OBS_FIN_001") == "optional_diagnostic"
    assert browser.classify_cmfgen_role("BAMAT") == "restart_internal"
    assert browser.classify_cmfgen_role("run.sh", relpath="runs/model_x/run.sh") == "script"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("C2PRRR", "optional_diagnostic"),
        ("GAMRAY_E_DEP", "optional_diagnostic"),
        ("GAMFLUX_NEW", "optional_diagnostic"),
        ("hydro_cont", "optional_diagnostic"),
        ("ewdata_fin", "optional_diagnostic"),
        ("cmf.sed", "optional_diagnostic"),
        ("model.uv", "optional_diagnostic"),
        ("ETA_ISO_001.dat", "optional_diagnostic"),
        ("CFDAT__IN", "input_grid_profile"),
        ("GAMRAY_PARAMS", "input_control"),
        ("IP_DATA_NEW", "restart_internal"),
        ("MnSEV_F_OSCDA", "input_atomic_core"),
        ("MnSEV_F_TO_", "input_atomic_core"),
    ],
)
def test_classify_cmfgen_role_covers_extended_model_families(name: str, expected: str) -> None:
    assert browser.classify_cmfgen_role(name, model_context=True) == expected


def test_save_and_editor_artifacts_are_not_promoted_by_their_stems() -> None:
    assert browser.classify_cmfgen_role("GAMFLUX_NEW.sve", model_context=True) == "other"
    assert browser.classify_cmfgen_role("MODEL_SPEC~", model_context=True) == "other"


def test_model_context_detects_cmfgen_markers_without_model_prefix(tmp_path: Path) -> None:
    model = tmp_path / "CMF1770005901JULIKAS3"
    model.mkdir()
    _write_file(model / "MODEL_SPEC", "settings")
    _write_file(model / "RVTJ", "results")
    obs = model / "obs"
    obs.mkdir()

    assert browser.is_model_context_path(str(model))
    assert browser.is_model_context_path(str(obs))


def test_marker_detected_model_assigns_script_role(tmp_path: Path) -> None:
    model = tmp_path / "CMF1770005901JULIKAS3"
    model.mkdir()
    _write_file(model / "MODEL_SPEC", "settings")
    _write_file(model / "VADAT", "settings")
    _write_file(model / "batch.sh", "#!/bin/sh")

    entries = browser.list_directory(str(model))
    batch = next(entry for entry in entries if entry["name"] == "batch.sh")
    assert batch["cmfgen_role"] == "script"


def test_model_context_does_not_accept_model_spec_alone(tmp_path: Path) -> None:
    candidate = tmp_path / "inputs"
    candidate.mkdir()
    _write_file(candidate / "MODEL_SPEC", "settings")

    assert not browser.is_model_context_path(str(candidate))


def test_make_breadcrumb_marks_only_last_item_as_current() -> None:
    breadcrumb = browser.make_breadcrumb("models/model_a")
    assert breadcrumb[0] == {"name": "ROOT", "path": ""}
    assert breadcrumb[1] == {"name": "models", "path": "models"}
    assert breadcrumb[2] == {"name": "model_a", "path": None}


def test_list_directory_filters_hidden_and_sorts_dirs_first(tmp_path: Path) -> None:
    (tmp_path / "b_dir").mkdir()
    _write_file(tmp_path / "a_file.txt", "hello")
    _write_file(tmp_path / ".hidden.txt", "hidden")

    visible = browser.list_directory(str(tmp_path), show_all=False)
    assert [entry["name"] for entry in visible] == ["b_dir", "a_file.txt"]

    all_entries = browser.list_directory(str(tmp_path), show_all=True)
    assert {entry["name"] for entry in all_entries} == {"b_dir", "a_file.txt", ".hidden.txt"}


def test_describe_file_returns_parsed_payload_for_known_text_file(tmp_path: Path) -> None:
    _write_file(
        tmp_path / "RVTJ",
        """ND: 2
Radius
1 2
Velocity
10 20
""",
    )

    context = browser.describe_file(str(tmp_path), "RVTJ")

    assert context["mode"] == "text"
    assert context["cmfgen_role"] == "core_viewer"
    parsed = context.get("parsed")
    assert isinstance(parsed, dict)
    assert parsed["parser"] == "RVTJ"


def test_describe_file_returns_metadata_payload_for_known_binary_file(tmp_path: Path) -> None:
    (tmp_path / "IP_DATA_NEW").write_bytes(b"\0" * 32)
    _write_file(tmp_path / "IP_DATA_NEW_INFO", "2 16 8 1 4 T\n")

    context = browser.describe_file(str(tmp_path), "IP_DATA_NEW")

    assert context["mode"] == "download"
    assert context["cmfgen_role"] == "restart_internal"
    assert context["parsed"]["parser"] == "DIRECT_ACCESS_INFO"
