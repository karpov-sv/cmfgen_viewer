from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import RegexLexer, bygroups
from pygments.lexers import TextLexer, get_lexer_for_filename, get_lexer_for_mimetype, guess_lexer
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String, Text, Whitespace
from pygments.util import ClassNotFound

PREVIEW_GUESS_BYTES = 8192
_FORMATTER = HtmlFormatter(cssclass="cmf-codehilite")
_CMFGEN_INPUT_SUFFIXES = {"", ".dat", ".txt", ".in"}
_CMFGEN_CONTROL_FILES = {"MODEL_SPEC", "VADAT", "IN_ITS"}
_CMFGEN_CONTROL_STYLE_ROLES = {"input_control", "input_hydro_iteration"}
_CMFGEN_KEY_PATTERN = re.compile(r"\[[^\]\n]+\]")


class CmfgenInputLexer(RegexLexer):
    name = "CMFGEN Input"
    aliases = ["cmfgen-input"]
    flags = re.IGNORECASE | re.MULTILINE
    tokens = {
        "root": [
            (r"\s+", Whitespace),
            (r"\[[^\]\n]+\]", Name.Attribute),
            (r"!.*$", Comment.Single),
            (r"#.*$", Comment.Single),
            (r"'[^'\n]*'", String.Single),
            (r'"[^"\n]*"', String.Double),
            (r"\.(TRUE|FALSE)\.", Keyword.Constant),
            (r"\b(TRUE|FALSE|YES|NO|ON|OFF|T|F)\b", Keyword.Constant),
            (r"([A-Za-z_][A-Za-z0-9_]*)(\s*)(=)", bygroups(Name.Attribute, Whitespace, Operator)),
            (r"[+-]?(?:\d+\.\d*|\.\d+|\d+)[ED][+-]?\d+", Number.Float),
            (r"[+-]?(?:\d+\.\d*|\.\d+)", Number.Float),
            (r"[+-]?\d+", Number.Integer),
            (r"[(),:/\[\]]", Punctuation),
            (r"[A-Z_][A-Z0-9_]*", Name.Constant),
            (r"[A-Za-z_][A-Za-z0-9_]*", Name),
            (r".", Text),
        ]
    }


@lru_cache(maxsize=1)
def syntax_css() -> str:
    base_css = _FORMATTER.get_style_defs(".cmf-codehilite")
    number_override = """
.cmf-codehilite .m,
.cmf-codehilite .mb,
.cmf-codehilite .mf,
.cmf-codehilite .mh,
.cmf-codehilite .mi,
.cmf-codehilite .mo,
.cmf-codehilite .il {
    color: #c00000 !important;
}
""".strip()
    return f"{base_css}\n{number_override}"


def _should_use_cmfgen_input_lexer(filename: str, role: str | None = None) -> bool:
    suffix = Path(filename).suffix.lower()
    if role in _CMFGEN_CONTROL_STYLE_ROLES and suffix in _CMFGEN_INPUT_SUFFIXES:
        return True
    if Path(filename).name.upper() in _CMFGEN_CONTROL_FILES:
        return True
    return False


def _detect_lexer(contents: str, *, filename: str, mime: str | None = None, role: str | None = None):
    if _should_use_cmfgen_input_lexer(filename, role=role):
        return CmfgenInputLexer(stripall=False)

    try:
        return get_lexer_for_filename(filename, contents)
    except ClassNotFound:
        pass

    if mime:
        try:
            return get_lexer_for_mimetype(mime)
        except ClassNotFound:
            pass

    try:
        return guess_lexer(contents[:PREVIEW_GUESS_BYTES])
    except ClassNotFound:
        return TextLexer(stripall=False)


def _align_cmfgen_columns(contents: str) -> str:
    """
    Normalize CMFGEN control-file lines into aligned value/key/comment columns for
    easier visual scanning in the HTML preview. This only affects rendered preview
    text and never modifies files on disk.
    """
    lines = contents.splitlines()
    keep_trailing_newline = contents.endswith("\n")

    parsed_rows: list[tuple[str, str, str | None, bool]] = []
    value_width = 0
    key_part_width = 0

    for raw_line in lines:
        line = raw_line.expandtabs(8).rstrip()
        stripped = line.lstrip()

        if not stripped or stripped.startswith(("!", "#")):
            parsed_rows.append((line, "", None, False))
            continue

        comment_idx = line.find("!")
        head = line if comment_idx < 0 else line[:comment_idx]
        comment = None if comment_idx < 0 else line[comment_idx:].lstrip()

        key_match = _CMFGEN_KEY_PATTERN.search(head)
        if not key_match:
            parsed_rows.append((line, "", comment, False))
            continue

        value_part = head[: key_match.start()].rstrip()
        key_part = key_match.group(0)
        tail = head[key_match.end() :].strip()
        if tail:
            key_part = f"{key_part} {tail}"

        value_width = max(value_width, len(value_part))
        key_part_width = max(key_part_width, len(key_part))
        parsed_rows.append((value_part, key_part, comment, True))

    if value_width == 0 or key_part_width == 0:
        return contents

    comment_col = value_width + 2 + key_part_width + 2
    rendered: list[str] = []

    for value_part, key_part, comment, is_key_row in parsed_rows:
        if not is_key_row:
            rendered.append(value_part)
            continue

        aligned = f"{value_part.ljust(value_width)}  {key_part}"
        if comment:
            if len(aligned) < comment_col:
                aligned = aligned.ljust(comment_col)
            else:
                aligned = f"{aligned}  "
            aligned = f"{aligned}{comment}"
        rendered.append(aligned)

    result = "\n".join(rendered)
    if keep_trailing_newline:
        result = f"{result}\n"
    return result


def highlight_text(
    contents: str,
    *,
    filename: str,
    mime: str | None = None,
    role: str | None = None,
) -> tuple[str, str]:
    lexer = _detect_lexer(contents, filename=filename, mime=mime, role=role)
    source = _align_cmfgen_columns(contents) if isinstance(lexer, CmfgenInputLexer) else contents
    highlighted = highlight(source, lexer, _FORMATTER)
    return highlighted, lexer.name
