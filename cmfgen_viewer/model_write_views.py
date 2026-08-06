"""Guarded routes for operations that create or modify CMFGEN models."""

from __future__ import annotations

from pathlib import Path

from flask import abort, current_app, redirect, render_template, request, url_for

from .browser import is_model_directory, make_breadcrumb, resolve_path
from .model_staging import (
    ModelStagingError,
    create_model_from_solution,
    is_sn_model_directory,
    plan_model_from_solution,
)
from .summary_cache import delete_model_summary_entries
from .view_common import _viewer_config, bp


def _default_model_destination(basepath: str, source_relpath: str) -> str:
    source_rel = Path(source_relpath)
    parent = source_rel.parent
    base = Path(basepath).expanduser().resolve()
    for index in range(1, 1000):
        suffix = "_new" if index == 1 else f"_new_{index}"
        candidate = parent / f"{source_rel.name}{suffix}"
        target = base.joinpath(*candidate.parts)
        if not target.exists() and not target.is_symlink():
            return candidate.as_posix()
    return (parent / f"{source_rel.name}_new").as_posix()


def _create_model_breadcrumb(source_relpath: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_relpath)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_relpath
    breadcrumb.append({"name": "Create new model", "path": None})
    return breadcrumb


@bp.route("/model-actions/create/<path:source_path>", methods=["GET", "POST"])
def model_create_from_solution(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        source = resolve_path(basepath, source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(source):
        abort(404)

    source_error = ""
    if is_sn_model_directory(source):
        source_error = "Creating a model from an SN solution is not supported yet."

    destination_relpath = str(
        request.form.get("destination_relpath", "")
        if request.method == "POST"
        else request.args.get("destination", "")
    ).strip()
    if not destination_relpath:
        destination_relpath = _default_model_destination(basepath, source_path)

    action = str(request.form.get("action", "preview")).strip().lower()
    if request.method == "POST" and action not in {"preview", "create"}:
        abort(400)

    plan: dict[str, object] | None = None
    error = source_error
    if not error:
        try:
            plan = plan_model_from_solution(
                basepath,
                source_relpath=source_path,
                destination_relpath=destination_relpath,
            )
            if request.method == "POST" and action == "create":
                created = create_model_from_solution(
                    basepath,
                    source_relpath=source_path,
                    destination_relpath=destination_relpath,
                )
                created_relpath = str(created["destination_relpath"])
                try:
                    delete_model_summary_entries(
                        str(config.get("summary_cache_db", "model_summary_cache.sqlite")),
                        basepath=basepath,
                        relpaths=[created_relpath],
                    )
                except Exception:
                    current_app.logger.warning(
                        "Failed to invalidate the model summary cache after creating %s",
                        created_relpath,
                        exc_info=True,
                    )
                return redirect(url_for("viewer.view", path=created_relpath, created="1"))
        except ModelStagingError as exc:
            error = str(exc)

    return render_template(
        "model_create.html",
        source_path=source_path,
        destination_relpath=destination_relpath,
        plan=plan,
        error=error,
        breadcrumb=_create_model_breadcrumb(source_path),
    )
