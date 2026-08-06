from __future__ import annotations

from cmfgen_viewer.syntax import _align_cmfgen_columns, highlight_text


def test_highlight_text_uses_cmfgen_input_lexer_for_control_role() -> None:
    html, lexer_name = highlight_text(
        "10 [TEFF] ! target temperature\n",
        filename="MODEL",
        role="input_control",
    )
    assert lexer_name == "CMFGEN Input"
    assert "TEFF" in html


def test_align_cmfgen_columns_aligns_comment_column() -> None:
    aligned = _align_cmfgen_columns(
        "1 [A] ! first\n1000 [B] ! second\n",
    )
    line1, line2 = aligned.splitlines()
    assert line1.index("!") == line2.index("!")


def test_align_cmfgen_columns_leaves_non_control_brackets_unchanged() -> None:
    original = "Fo[7/2] term label\n"
    assert _align_cmfgen_columns(original) == original


def test_gamma_ray_params_uses_cmfgen_control_lexer() -> None:
    _html, lexer_name = highlight_text("30000 [NU_GRID_MAX]\n", filename="GAMRAY_PARAMS", role="input_control")
    assert lexer_name == "CMFGEN Input"
