from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.parsers import diagnostic_text as dt


def _write_file(tmp_path: Path, name: str, contents: str) -> Path:
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def _table_by_title(parsed: dict[str, object], title: str) -> dict[str, object]:
    tables = parsed.get("tables")
    assert isinstance(tables, list)
    for table in tables:
        if isinstance(table, dict) and table.get("title") == title:
            return table
    raise AssertionError(f"Missing table: {title}")


def test_parse_numeric_diagnostic_detects_scalars_headers_and_plots(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "HYDRO",
        """alpha = 1 beta = 2
! Radius Velocity Density
1 10 100
2 20 200
3 30 300
""",
    )
    parsed = dt.parse_numeric_diagnostic(
        path,
        parser_name="TEST",
        title="test",
        detect_header_labels=True,
    )
    assert parsed["parser"] == "TEST"
    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["header_labels_detected"] == "yes"
    scalar_table = _table_by_title(parsed, "Detected scalars")
    assert ["alpha", "1"] in scalar_table["rows"]
    main = _table_by_title(parsed, "Main numeric block")
    assert main["columns"] == ["Radius", "Velocity", "Density"]
    assert len(parsed["plots"]) >= 1


def test_parse_numeric_diagnostic_without_numeric_block_returns_preview(tmp_path: Path) -> None:
    path = _write_file(tmp_path, "EMPTY", "hello\nworld\n")
    parsed = dt.parse_numeric_diagnostic(path, parser_name="EMPTY", title="empty")
    assert any("No numeric data block with at least two columns was detected." in w for w in parsed["warnings"])
    preview = _table_by_title(parsed, "Text preview")
    assert preview["rows"][0] == ["1", "hello"]


def test_parse_log_diagnostic_counts_warning_and_error_like_lines(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "OUTLTE",
        """line 1
WARNING: something odd
fatal: stop now
""",
    )
    parsed = dt.parse_log_diagnostic(path, parser_name="OUTLTE", title="x")
    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["warning_like_lines"] == "1"
    assert summary_rows["error_like_lines"] == "1"
    warn_table = _table_by_title(parsed, "Warnings / errors")
    assert len(warn_table["rows"]) == 1


def test_parse_hydro_params_uses_structured_mode_or_log_fallback(tmp_path: Path) -> None:
    structured = _write_file(
        tmp_path,
        "HYDRO_PARAMS",
        """1.0 [ALPHA]
2.5 [BETA]
""",
    )
    parsed_structured = dt.parse_hydro_params(structured)
    assert parsed_structured["parser"] == "HYDRO_PARAMS"
    table = _table_by_title(parsed_structured, "Input parameters")
    assert ["ALPHA", "1"] in table["rows"]
    assert ["BETA", "2.5"] in table["rows"]

    fallback = _write_file(tmp_path, "HYDRO_PARAMS_FALLBACK", "just text\n")
    parsed_fallback = dt.parse_hydro_params(fallback)
    assert parsed_fallback["parser"] == "HYDRO_PARAMS"
    summary_rows = dict(parsed_fallback["summary_table"]["rows"])
    assert summary_rows["total_lines"] == "1"


def test_parse_ml_counter_truncates_large_table(tmp_path: Path) -> None:
    values = " ".join(str(i) for i in range(300))
    path = _write_file(tmp_path, "ML_COUNTER", values)
    parsed = dt.parse_ml_counter(path)
    table = _table_by_title(parsed, "Counter values")
    assert len(table["rows"]) == dt.MAX_TABLE_ROWS
    assert any("Counter table truncated to first" in w for w in parsed["warnings"])


def test_parse_rvsig_col_parses_scalars_and_trims_to_declared_depth(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "RVSIG_COL",
        """3 Number of depth points
!!! Vinf is: 1000
1 10 0.1 0.01 1
2 20 0.2 0.02 2
3 30 0.3 0.03 3
4 40 0.4 0.04 4
""",
    )
    parsed = dt.parse_rvsig_col(path)
    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["depth_points_declared"] == "3"
    assert summary_rows["parsed_rows"] == "3"
    assert any("Trimmed 1 trailing row(s)" in w for w in parsed["warnings"])
    scalars = _table_by_title(parsed, "Velocity-law scalars")
    assert ["Vinf", "1000"] in scalars["rows"]


def test_parse_gammas_parses_species_blocks_and_profile_plot(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "GAMMAS",
        """3 ! Number of depth points
! Electron density
1 2 3
! Radius
10 20 30
! Temperature
4 5 6
26 Fe
0.1 0.2 0.3
""",
    )
    parsed = dt.parse_gammas(path)
    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["species_count"] == "1"
    depth_table = _table_by_title(parsed, "GAMMAS depth table")
    assert "Fe" in depth_table["columns"]
    assert len(parsed["plots"]) == 1


def test_parse_meanopac_collects_nb_warnings(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "MEANOPAC",
        """NB: first note
! R KAPPA
1 10
2 20
""",
    )
    parsed = dt.parse_meanopac(path)
    assert parsed["parser"] == "MEANOPAC"
    assert "first note" in parsed["warnings"][0]
    assert len(parsed["plots"]) == 1
