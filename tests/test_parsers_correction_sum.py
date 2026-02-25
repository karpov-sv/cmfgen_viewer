from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.parsers.correction_sum import parse_correction_sum


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


def test_parse_correction_sum_with_header_and_warnings(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "CORRECTION_SUM",
        """NT = 10
Depth 1e-2 1e-3
1 0 2
2.4 1 3
3 5
4 2 4
""",
    )
    parsed = parse_correction_sum(path)

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["NT"] == "10"
    assert summary_rows["depth_rows"] == "3"
    assert summary_rows["threshold_columns"] == "2"

    warnings = parsed["warnings"]
    assert any("Skipped 1 row(s) with unexpected column counts." in w for w in warnings)
    assert any("Found 1 row(s) with non-integer depth values" in w for w in warnings)

    overview = _table_by_title(parsed, "Threshold overview")
    assert overview["columns"][0] == "Threshold"
    assert len(overview["rows"]) >= 2
    assert len(parsed["plots"]) == 1


def test_parse_correction_sum_fallback_when_header_missing(tmp_path: Path) -> None:
    path = _write_file(
        tmp_path,
        "CORRECTION_SUM",
        """1 2 3
2 4 5
noise
""",
    )
    parsed = parse_correction_sum(path)

    summary_rows = dict(parsed["summary_table"]["rows"])
    assert summary_rows["depth_rows"] == "2"
    assert summary_rows["threshold_columns"] == "2"

    warnings = parsed["warnings"]
    assert any("Header table not detected cleanly; used fallback numeric-block parsing." in w for w in warnings)
    assert any("NT value was not detected." in w for w in warnings)
