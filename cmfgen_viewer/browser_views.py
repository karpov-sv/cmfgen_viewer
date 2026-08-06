"""Rooted file-browser and documentation routes."""

from __future__ import annotations

from pathlib import Path

from flask import abort, current_app, redirect, render_template, request, send_file, url_for

from .browser import describe_file, is_model_context_path, list_directory, make_breadcrumb, resolve_path
from .documentation import discover_docs as _discover_docs, render_document
from .final_spectrum import read_model
from .summary_cache import inspect_model_summary_entry, upsert_model_summary
from .view_common import (
    _build_summary_row,
    _collect_quick_links,
    _spectrum_link_context,
    _viewer_config,
    bp,
)


def _cache_model_summary_on_visit(
    *,
    config: dict[str, object],
    basepath: str,
    relpath: str,
    model_dir: Path,
) -> str:
    """Add or refresh the summary cache entry for a visited model folder."""
    vadat = model_dir / "VADAT"
    mod_sum = model_dir / "MOD_SUM"
    if not vadat.is_file() or not mod_sum.is_file():
        return "ineligible"

    normalized_relpath = str(relpath).strip().strip("/") or "."
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    cached = inspect_model_summary_entry(
        summary_cache_db,
        basepath=basepath,
        relpath=normalized_relpath,
    )
    cached_status = str(cached.get("status", "error"))
    if cached_status == "valid":
        return "valid"

    model = read_model(model_dir)
    mod_sum_mtime = mod_sum.stat().st_mtime
    values = _build_summary_row(model, mod_sum_mtime=mod_sum_mtime)
    upsert_model_summary(
        summary_cache_db,
        basepath=basepath,
        relpath=normalized_relpath,
        model_dir=model_dir,
        model_name=str(model.get("name", model_dir.name)),
        values=values,
        vadat_mtime=vadat.stat().st_mtime,
        mod_sum_mtime=mod_sum_mtime,
    )
    return "added" if cached_status == "absent" else "refreshed"


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
            doc_html="",
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
    doc_html, doc_highlight_css = render_document(doc_path)
    return render_template(
        "documentation.html",
        docs=docs,
        active_doc=active_doc,
        doc_html=doc_html,
        doc_highlight_css=doc_highlight_css,
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
        current_path_in_model = is_model_context_path(path) or is_model_context_path(str(target)) or current_dir_is_model
        context["show_role_badges"] = current_path_in_model
        model_context = current_path_in_model
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
        context["enable_multi_model_ops"] = not current_path_in_model
        try:
            context["model_cache_status"] = _cache_model_summary_on_visit(
                config=config,
                basepath=basepath,
                relpath=path,
                model_dir=target,
            )
        except Exception:
            context["model_cache_status"] = "error"
            current_app.logger.warning(
                "Failed to update the model summary cache while visiting %s",
                target,
                exc_info=True,
            )
        return render_template("files_list.html", files=files, **context)

    if target.is_file():
        details = describe_file(basepath, path)
        parent_path = Path(path).parent.as_posix()
        context["show_role_badges"] = is_model_context_path(str(target.parent))
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
