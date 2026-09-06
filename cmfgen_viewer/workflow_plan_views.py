"""Read-only HTML and JSON dry-run previews; no execution endpoint."""

from flask import abort, jsonify, make_response, render_template, request

from .view_common import _viewer_config, bp
from .workflow_plan import build_workflow_plan


@bp.route("/model-actions/plan/<scope>/<path:source_path>")
def model_workflow_plan(scope: str, source_path: str):
    config = _viewer_config()
    if not config.get("read_write_enabled", False):
        abort(403)
    try:
        plan = build_workflow_plan(str(config.get("basepath", ".")), model_relpath=source_path,
                                   scope=scope, config=config)
    except ValueError:
        abort(404)
    if request.args.get("format") == "json":
        response = jsonify(plan)
    else:
        response = make_response(render_template("workflow_plan.html", plan=plan, source_path=source_path))
    response.headers["Cache-Control"] = "no-store"
    return response
