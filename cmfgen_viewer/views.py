from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from markupsafe import Markup
from pygments.formatters import HtmlFormatter

from .browser import describe_file, is_model_context_path, list_directory, make_breadcrumb, resolve_path
from .syntax import highlight_text, syntax_css

try:
    import markdown as md
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    md = None

bp = Blueprint("viewer", __name__)
DOCS_DIR = Path(__file__).resolve().parent.parent / "doc"


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


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


def _discover_docs() -> list[dict[str, object]]:
    if not DOCS_DIR.is_dir():
        return []

    docs: list[dict[str, object]] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        docs.append(
            {
                "slug": path.stem,
                "title": _doc_title(path),
                "path": path,
            }
        )
    return docs


@bp.app_context_processor
def inject_docs_nav():
    docs = _discover_docs()
    return {
        "docs_nav": [
            {
                "slug": str(item["slug"]),
                "title": str(item["title"]),
            }
            for item in docs
        ]
    }


@lru_cache(maxsize=1)
def _docs_markdown_css() -> str:
    formatter = HtmlFormatter(cssclass="codehilite")
    return formatter.get_style_defs(".doc-content .codehilite")


@bp.route("/")
def index():
    return redirect(url_for("viewer.view", path=""))


@bp.route("/documentation/", defaults={"slug": None})
@bp.route("/documentation/<slug>")
def documentation(slug: str | None):
    docs = _discover_docs()
    if not docs:
        return render_template(
            "documentation.html",
            docs=[],
            active_doc=None,
            doc_html=Markup(""),
            doc_highlight_css="",
        )

    docs_by_slug = {str(item["slug"]): item for item in docs}
    if slug is None:
        first = str(docs[0]["slug"])
        return redirect(url_for("viewer.documentation", slug=first))

    active_doc = docs_by_slug.get(slug)
    if active_doc is None:
        abort(404)

    doc_path = Path(active_doc["path"])
    source = doc_path.read_text(encoding="utf-8", errors="replace")
    if md is not None:
        doc_html = md.markdown(
            source,
            extensions=["fenced_code", "tables", "sane_lists", "codehilite"],
            extension_configs={
                "codehilite": {
                    "guess_lang": False,
                    "css_class": "codehilite",
                }
            },
        )
        doc_highlight_css = _docs_markdown_css()
    else:
        highlighted_html, _lexer = highlight_text(
            source,
            filename=doc_path.name,
            mime="text/markdown",
        )
        doc_html = f"<div class=\"syntax-preview\">{highlighted_html}</div>"
        doc_highlight_css = syntax_css()
    return render_template(
        "documentation.html",
        docs=docs,
        active_doc=active_doc,
        doc_html=Markup(doc_html),
        doc_highlight_css=doc_highlight_css,
    )


@bp.route("/view/", defaults={"path": ""})
@bp.route("/view/<path:path>")
def view(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)

    context = {
        "path": path,
        "breadcrumb": make_breadcrumb(path),
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "show_role_badges": is_model_context_path(path),
    }

    if target.is_dir():
        files = list_directory(basepath, path, show_all=bool(config.get("show_all", False)))
        return render_template("files_list.html", files=files, **context)

    if target.is_file():
        details = describe_file(basepath, path)
        parent_path = Path(path).parent.as_posix()
        context["show_role_badges"] = is_model_context_path(parent_path)
        has_parsed = bool(details.get("parsed"))
        requested_display = request.args.get("display", "").strip().lower()
        if has_parsed:
            if requested_display in {"raw", "parsed"}:
                display_mode = requested_display
            else:
                display_mode = "parsed"
        else:
            display_mode = "raw"
        details["has_parsed"] = has_parsed
        details["display_mode"] = display_mode
        return render_template("file_view.html", **details, **context)

    abort(404)


def _send(path: str, *, attachment: bool):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)

    if not target.is_file():
        abort(404)

    return send_file(
        target,
        as_attachment=attachment,
        download_name=target.name,
    )


@bp.route("/raw/<path:path>")
def raw_file(path: str):
    return _send(path, attachment=False)


@bp.route("/download/<path:path>")
def download_file(path: str):
    return _send(path, attachment=True)
