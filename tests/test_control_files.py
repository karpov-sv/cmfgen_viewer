from cmfgen_viewer.control_files import control_occurrences, tokenize_control
from cmfgen_viewer.model_editor import control_file_warnings


def test_control_tokens_preserve_source_spans_and_normalize_keys():
    contents = (
        "! 0 [LSTAR]\r\n  1.0D+5   [lstar] ! luminosity\r\n# 2 [LSTAR]\r\n3 [LSTAR]\r\n"
    )
    rows = tokenize_control(contents)
    assert [row.key for row in rows] == ["LSTAR", "LSTAR"]
    assert len(control_occurrences(contents)["LSTAR"]) == 2
    lines = contents.splitlines(keepends=True)
    row = rows[0]
    line = lines[row.line_index]
    lines[row.line_index] = line[: row.value_start] + "2.0D+5" + line[row.value_end :]
    assert "".join(lines) == contents.replace("1.0D+5", "2.0D+5")
    assert any(
        "Duplicate control keys: LSTAR (2/4)" in warning
        for warning in control_file_warnings(contents)
    )
