from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from markupsafe import Markup
from pygments.formatters import HtmlFormatter

from .syntax import highlight_text, syntax_css

try:
    import markdown as md
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    md = None


DOCS_DIR = Path(__file__).resolve().parent.parent / "doc"

_MD_FENCE_RE = re.compile(r"^\s*```")
_MD_LIST_RE = re.compile(r"^(\s*)(?:[-*+]\s+|\d+[.)]\s+)")
_MD_ORDERED_PAREN_RE = re.compile(r"^(\s*)(\d+)\)\s+(.*)$")
_MD_ATX_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_MD_SETEXT_RE = re.compile(r"^\s*[=-]{3,}\s*$")
_MD_QUOTE_RE = re.compile(r"^\s*>")


def normalize_markdown_lists(source: str) -> str:
    """Normalize legacy investigation-note list style for Python-Markdown."""
    lines = source.splitlines()
    out: list[str] = []
    in_fence = False

    for line in lines:
        if _MD_FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue

        normalized = line
        if not in_fence:
            ordered_match = _MD_ORDERED_PAREN_RE.match(normalized)
            if ordered_match:
                normalized = f"{ordered_match.group(1)}{ordered_match.group(2)}. {ordered_match.group(3)}"

            if _MD_LIST_RE.match(normalized):
                prev = out[-1] if out else ""
                prev_is_blank = not prev.strip()
                prev_is_list = bool(_MD_LIST_RE.match(prev))
                prev_is_heading = bool(_MD_ATX_HEADING_RE.match(prev))
                prev_is_setext = bool(_MD_SETEXT_RE.match(prev))
                prev_is_quote = bool(_MD_QUOTE_RE.match(prev))
                if not (prev_is_blank or prev_is_list or prev_is_heading or prev_is_setext or prev_is_quote):
                    out.append("")

        out.append(normalized)

    normalized_source = "\n".join(out)
    if source.endswith("\n"):
        normalized_source += "\n"
    return normalized_source


def _doc_title(path: Path) -> str:
    fallback = path.stem.replace("-", " ").replace("_", " ").title()
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if line.startswith("#"):
                    title = line.lstrip("#").strip()
                    if title:
                        return title
    except OSError:
        return fallback
    return fallback


def discover_docs(docs_dir: Path = DOCS_DIR) -> list[dict[str, object]]:
    if not docs_dir.is_dir():
        return []

    return [
        {
            "slug": path.stem,
            "title": _doc_title(path),
            "path": path,
        }
        for path in sorted(docs_dir.glob("*.md"))
    ]


@lru_cache(maxsize=1)
def _markdown_css() -> str:
    formatter = HtmlFormatter(cssclass="codehilite")
    return formatter.get_style_defs(".doc-content .codehilite")


def render_document(path: Path) -> tuple[Markup, str]:
    source = path.read_text(encoding="utf-8", errors="replace")
    if md is not None:
        html = md.markdown(
            normalize_markdown_lists(source),
            extensions=["fenced_code", "tables", "sane_lists", "codehilite"],
            extension_configs={
                "codehilite": {
                    "guess_lang": False,
                    "css_class": "codehilite",
                }
            },
        )
        return Markup(html), _markdown_css()

    highlighted_html, _lexer = highlight_text(
        source,
        filename=path.name,
        mime="text/markdown",
    )
    return Markup(f'<div class="syntax-preview">{highlighted_html}</div>'), syntax_css()
