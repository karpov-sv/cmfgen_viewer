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
