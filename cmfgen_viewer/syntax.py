from __future__ import annotations

from functools import lru_cache

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename, get_lexer_for_mimetype, guess_lexer
from pygments.util import ClassNotFound

PREVIEW_GUESS_BYTES = 8192
_FORMATTER = HtmlFormatter(cssclass="cmf-codehilite")


@lru_cache(maxsize=1)
def syntax_css() -> str:
    return _FORMATTER.get_style_defs(".cmf-codehilite")


def _detect_lexer(contents: str, *, filename: str, mime: str | None = None):
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


def highlight_text(contents: str, *, filename: str, mime: str | None = None) -> tuple[str, str]:
    lexer = _detect_lexer(contents, filename=filename, mime=mime)
    highlighted = highlight(contents, lexer, _FORMATTER)
    return highlighted, lexer.name
