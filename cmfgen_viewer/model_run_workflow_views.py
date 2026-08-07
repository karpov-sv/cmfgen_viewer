"""Routes for the externally executed main CMFGEN model workflow."""

from __future__ import annotations

from flask import abort, render_template

from .browser import make_breadcrumb
from .model_run_workflow import ModelRunWorkflowError, inspect_main_model_workflow
from .view_common import _viewer_config, bp


def _breadcrumb(source_path: str) -> list[dict[str, str | None]]:
    breadcrumb = make_breadcrumb(source_path)
    if breadcrumb:
        breadcrumb[-1]["path"] = source_path
    breadcrumb.append({"name": "Main model computation", "path": None})
    return breadcrumb


@bp.route("/model-actions/main-computation/<path:source_path>")
def model_main_computation(source_path: str):
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    try:
        state = inspect_main_model_workflow(
            str(config.get("basepath", ".")),
            model_relpath=source_path,
        )
    except ModelRunWorkflowError:
        abort(404)
    return render_template(
        "model_main_computation.html",
        source_path=source_path,
        state=state,
        breadcrumb=_breadcrumb(source_path),
    )
