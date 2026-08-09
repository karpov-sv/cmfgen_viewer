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


def test_parse_known_file_resolves_outgen_and_tracks_auxiliary_cache_inputs(
    tmp_path: Path,
) -> None:
    path = _write_file(
        tmp_path,
        "OUTGEN",
        "Model started on: 01-Jan-2026 00:00:00\n"
        "Current great iteration count is 1\n"
        "Maximm changes as returned by SOLVEBA_V13 is 5.0E-01\n",
    )
    _write_file(tmp_path, "IN_ITS", "2 [NUM_ITS]\n")

    first = parsers.parse_known_file(path)
    assert first is not None and first["parser"] == "OUTGEN"
    assert dict(first["summary_table"]["rows"])["requested_iterations"] == "2"

    _write_file(tmp_path, "IN_ITS", "5 [NUM_ITS]\n")
    second = parsers.parse_known_file(path)

    assert second is not None
    assert dict(second["summary_table"]["rows"])["requested_iterations"] == "5"


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


@pytest.mark.parametrize(
    ("name", "expected_parser"),
    [
        ("hydro_cont", "HYDRO"),
        ("hydro_fin", "HYDRO"),
        ("meanopac_fin", "MEANOPAC"),
        ("GAMFLUX_NEW", "GAMFLUX"),
        ("GAMRAY_E_DEP", "GAMRAY_ENERGY_DEP"),
        ("GAMRAY_E_DEP_MOD", "GAMRAY_ENERGY_DEP"),
        ("C2PRRR", "*PRRR"),
        ("cmf.sed", "CMF_SPECTRUM"),
        ("ETA_ISO_001.dat", "ETA_ISO_001.DAT"),
        ("cont_timing", "CONT_TIMING"),
    ],
)
def test_parse_known_file_resolves_extended_aliases(tmp_path: Path, name: str, expected_parser: str) -> None:
    path = _write_file(tmp_path, name, "Radius\n1 2 3\nTemperature\n4 5 6\n")
    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    assert parsed["parser"] == expected_parser


def test_parse_known_file_resolves_direct_access_binary(tmp_path: Path) -> None:
    path = tmp_path / "IP_DATA_NEW"
    path.write_bytes(b"\0" * 32)
    _write_file(
        tmp_path,
        "IP_DATA_NEW_INFO",
        """12-Apr-2017 !INFO format date
2 16 8 1 4 T
ND RECL WORD_SIZE UNIT_SIZE INT_SIZE LIT_END
""",
    )
    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    assert parsed["parser"] == "DIRECT_ACCESS_INFO"
    assert dict(parsed["summary_table"]["rows"])["complete_records_from_size"] == "2"


def test_parse_known_file_accepts_legacy_direct_access_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "JH_AT_OLD_TIME"
    path.write_bytes(b"\0" * 32)
    _write_file(tmp_path, "JH_AT_OLD_TIME_INFO", "2 16 8 1\nND RECL WORD_SIZE UNIT_SIZE\n")
    parsed = parsers.parse_known_file(path)
    assert parsed is not None
    summary = dict(parsed["summary_table"]["rows"])
    assert summary["complete_records_from_size"] == "2"
    assert summary["byte_order"] == "not recorded"


def test_parse_known_file_returns_none_for_unknown_file(tmp_path: Path) -> None:
    path = _write_file(tmp_path, "notes.abc", "plain text\n")
    assert parsers.parse_known_file(path) is None


def test_parse_known_file_ignores_save_and_editor_artifacts(tmp_path: Path) -> None:
    save = _write_file(tmp_path, "GAMFLUX_NEW.sve", "saved plotting state\n")
    backup = _write_file(tmp_path, "OBSFLUX~", "saved editor backup\n")
    assert parsers.parse_known_file(save) is None
    assert parsers.parse_known_file(backup) is None


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


def test_outgen_bounded_tail_parser_is_not_blocked_by_generic_size_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsers, "MAX_PARSE_FILE_BYTES", 8)
    path = _write_file(
        tmp_path,
        "OUTGEN",
        "Model started on: 01-Jan-2026 00:00:00\n"
        "Current great iteration count is 1\n",
    )

    parsed = parsers.parse_known_file(path)

    assert parsed is not None
    assert parsed["parser"] == "OUTGEN"
    assert dict(parsed["summary_table"]["rows"])["iteration_records"] == "1"
