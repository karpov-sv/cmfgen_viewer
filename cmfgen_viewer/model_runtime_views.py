"""Read-only external CMFGEN process monitoring."""

from __future__ import annotations

from pathlib import Path

from flask import abort, jsonify

from .browser import is_model_directory, resolve_path
from .model_runtime import inspect_workflow_runtime
from .view_common import _viewer_config, bp


def resolve_runtime_target(kind: str, source_path: str) -> Path:
    if kind not in {"main", "lte", "hydro"}:
        abort(404)
    config = _viewer_config()
    if not bool(config.get("read_write_enabled", False)):
        abort(403)
    basepath = str(config.get("basepath", "."))
    try:
        model_dir = resolve_path(basepath, source_path)
    except FileNotFoundError:
        abort(404)
    if not is_model_directory(model_dir):
        abort(404)
    target_dir = model_dir if kind == "main" else model_dir / "lte"
    if not target_dir.is_dir():
        abort(404)
    return Path(target_dir)


@bp.route("/model-actions/runtime/<kind>/<path:source_path>")
def model_workflow_runtime(kind: str, source_path: str):
    target_dir = resolve_runtime_target(kind, source_path)
    response = jsonify(inspect_workflow_runtime(target_dir, kind))
    response.headers["Cache-Control"] = "no-store"
    return response
