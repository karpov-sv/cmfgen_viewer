from __future__ import annotations

from pathlib import Path

import pytest

import cmfgen_viewer.parsers as parsers


def _write_file(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clear_parser_cache() -> None:
    parsers._parse_cached.cache_clear()


def test_parse_known_file_resolves_obs_alias(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "obs_fin.test",
        """Continuum Frequencies (2)
1.0 0.5
Observed intensity (Janskys)
5.0 3.0
""",
    )

    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    assert parsed["parser"] == "OBSFLUX"


def test_parse_known_file_resolves_pop_and_out_families(tmp_path: Path) -> None:
    pop_path = _write_file(tmp_path, "POPH", "1 2\n2 3\n")
    out_path = _write_file(tmp_path, "HE2OUT", "1 2\n2 3\n")

    pop_parsed = parsers.parse_known_file(pop_path)
    out_parsed = parsers.parse_known_file(out_path)

    assert pop_parsed is not None and pop_parsed["parser"] == "POP*"
    assert out_parsed is not None and out_parsed["parser"] == "*OUT"


def test_parse_known_file_resolves_rvsig_alias(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "RVSIG_COL_extra",
        """2 Number of depth points
1 10 0.1 0.01 1
2 20 0.2 0.02 2
""",
    )
    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    assert parsed["parser"] == "RVSIG_COL"


def test_parse_known_file_returns_none_for_unknown_file(tmp_path: Path) -> None:
    path = _write_file(tmp_path, "notes.abc", "plain text\n")
    assert parsers.parse_known_file(path) is None


def test_parse_known_file_uses_size_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parsers, "MAX_PARSE_FILE_BYTES", 8)
    path = _write_file(
        tmp_path,
        "RVTJ",
        """ND: 3
Radius
1 2 3
""",
    )

    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    assert parsed["parser"] == "RVTJ"

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["status"] == "skipped"
    assert summary_rows["reason"] == "file is larger than 8 bytes"
