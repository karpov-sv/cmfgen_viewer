from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for
from markupsafe import Markup
from pygments.formatters import HtmlFormatter

from .browser import describe_file, is_model_context_path, list_directory, make_breadcrumb, resolve_path
from .final_spectrum import (
    build_both_plot,
    build_model_summary_sections,
    build_normalized_plot,
    discover_final_spectrum_files,
    fin_file_label,
    load_obs_spectrum,
    read_model,
    spectrum_data_rows,
)
from .syntax import highlight_text, syntax_css

try:
    import markdown as md
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    md = None

bp = Blueprint("viewer", __name__)
DOCS_DIR = Path(__file__).resolve().parent.parent / "doc"
QUICK_LINK_FILES = (
    "VADAT",
    "MODEL_SPEC",
    "IN_ITS",
    "MOD_SUM",
    "RVTJ",
    "OBSFLUX",
    "MEANOPAC",
    "HYDRO",
    "GAMMAS",
    "OUTGEN",
    "WARNINGS",
)
QUICK_LINK_GLOBS = (
    "obs_fin*",
    "obs_cont*",
    "obs/obs_fin*",
    "obs/obs_cont*",
)

_MD_FENCE_RE = re.compile(r"^\s*```")
_MD_LIST_RE = re.compile(r"^(\s*)(?:[-*+]\s+|\d+[.)]\s+)")
_MD_ORDERED_PAREN_RE = re.compile(r"^(\s*)(\d+)\)\s+(.*)$")
_MD_ATX_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_MD_SETEXT_RE = re.compile(r"^\s*[=-]{3,}\s*$")
_MD_QUOTE_RE = re.compile(r"^\s*>")


def _normalize_markdown_lists(source: str) -> str:
    """
    Normalize legacy investigation-note list style into markdown-friendly form.

    The source docs use many `1)` markers and list starts directly after text
    lines. Python-Markdown does not reliably recognize those as lists without
    canonical markers and a separating blank line.
    """
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


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


def _join_relpath(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent.rstrip('/')}/{child}"


def _collect_quick_links(basepath: str, directory_relpath: str) -> list[dict[str, str]]:
    try:
        directory = resolve_path(basepath, directory_relpath)
    except (FileNotFoundError, NotADirectoryError):
        return []
    if not directory.is_dir():
        return []

    links: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    def add_link(path_obj: Path, *, label: str | None = None) -> None:
        rel = _join_relpath(directory_relpath, path_obj.relative_to(directory).as_posix())
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        links.append(
            {
                "name": label or path_obj.name,
                "path": rel,
            }
        )

    for name in QUICK_LINK_FILES:
        candidate = directory / name
        if candidate.is_file():
            add_link(candidate, label=name)

    for pattern in QUICK_LINK_GLOBS:
        for candidate in sorted(directory.glob(pattern), key=lambda p: p.name.lower()):
            if candidate.is_file():
                add_link(candidate)
    return links


def _model_root_relpath(relpath: str) -> str | None:
    parts = [part for part in Path(relpath).parts if part not in ("", ".")]
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered.startswith("model") and lowered != "models":
            return "/".join(parts[: index + 1])
    return None


def _spectrum_link_context(basepath: str, relpath: str) -> dict[str, object] | None:
    model_root = _model_root_relpath(relpath)
    if not model_root:
        return None
    try:
        model_dir = resolve_path(basepath, model_root)
    except (FileNotFoundError, NotADirectoryError):
        return None
    files = discover_final_spectrum_files(model_dir)
    if files is None:
        return None
    return {
        "model_path": model_root,
        "fin_count": len(files["fin_files"]),
    }


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
        normalized_source = _normalize_markdown_lists(source)
        doc_html = md.markdown(
            normalized_source,
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


@bp.route("/spectrum/<path:path>")
def spectrum(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))

    try:
        target = resolve_path(basepath, path)
    except FileNotFoundError:
        abort(404)
    if not target.is_dir():
        abort(404)

    model_root = _model_root_relpath(path)
    if not model_root:
        abort(404)
    model_dir = resolve_path(basepath, model_root)

    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        abort(404)

    fin_files = [entry.name for entry in spectrum_files["fin_files"]]
    if not fin_files:
        abort(404)

    selected_fin = request.args.get("fin", "").strip()
    if selected_fin not in fin_files:
        selected_fin = fin_files[0]

    view_mode = request.args.get("mode", "both").strip().lower()
    if view_mode not in {"both", "normalized"}:
        view_mode = "both"

    continuum = load_obs_spectrum(Path(spectrum_files["obs_cont"]))
    final = load_obs_spectrum(Path(spectrum_files["obs_dir"]) / selected_fin)
    plot_data = build_both_plot(continuum, final) if view_mode == "both" else build_normalized_plot(continuum, final)

    warnings: list[str] = []
    if plot_data is None:
        warnings.append("Plot generation failed: insufficient overlapping spectrum points.")

    breadcrumb = make_breadcrumb(model_root)
    if breadcrumb:
        breadcrumb[-1]["path"] = model_root
        breadcrumb.append({"name": "Final Spectrum", "path": None})

    model_summary_sections = build_model_summary_sections(read_model(model_dir))
    fin_options = [{"name": name, "label": fin_file_label(name)} for name in fin_files]

    context = {
        "path": model_root,
        "breadcrumb": breadcrumb,
        "basepath": basepath,
        "show_all": bool(config.get("show_all", False)),
        "view_query": {},
        "quick_links": _collect_quick_links(basepath, model_root),
        "spectrum_view": _spectrum_link_context(basepath, model_root),
    }
    return render_template(
        "spectrum_view.html",
        model_name=model_dir.name,
        selected_fin=selected_fin,
        fin_options=fin_options,
        mode=view_mode,
        plot_data=plot_data,
        model_summary_sections=model_summary_sections,
        spectrum_summary_rows=spectrum_data_rows(continuum, final),
        warnings=warnings,
        **context,
    )


@bp.route("/view/", defaults={"path": ""})
@bp.route("/view/<path:path>")
def view(path: str):
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    symlink_mode = request.args.get("symlinks", "").strip().lower()
    hide_symlink_files = symlink_mode == "hide"
    view_query: dict[str, str] = {"symlinks": "hide"} if hide_symlink_files else {}

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
        "view_query": view_query,
        "spectrum_view": _spectrum_link_context(basepath, path),
    }

    if target.is_dir():
        current_dir_name = target.name.lower()
        current_dir_is_model = current_dir_name.startswith("model") and current_dir_name != "models"
        model_context = is_model_context_path(path) or is_model_context_path(str(target)) or current_dir_is_model
        show_symlink_toggle = model_context
        show_symlinks = (not hide_symlink_files) or (not show_symlink_toggle)
        symlink_toggle_query: dict[str, str] = {}
        if show_symlink_toggle and show_symlinks:
            symlink_toggle_query = {"symlinks": "hide"}

        files = list_directory(
            basepath,
            path,
            show_all=bool(config.get("show_all", False)),
            show_symlinks=show_symlinks,
        )
        context["show_symlink_toggle"] = show_symlink_toggle
        context["show_symlinks"] = show_symlinks
        context["symlink_toggle_query"] = symlink_toggle_query
        context["quick_links"] = _collect_quick_links(basepath, path)
        return render_template("files_list.html", files=files, **context)

    if target.is_file():
        details = describe_file(basepath, path)
        parent_path = Path(path).parent.as_posix()
        context["show_role_badges"] = is_model_context_path(parent_path)
        context["quick_links"] = _collect_quick_links(basepath, parent_path)
        context["spectrum_view"] = _spectrum_link_context(basepath, parent_path)
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
