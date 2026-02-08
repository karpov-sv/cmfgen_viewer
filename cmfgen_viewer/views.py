from __future__ import annotations

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for

from .browser import describe_file, list_directory, make_breadcrumb, resolve_path

bp = Blueprint("viewer", __name__)


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


@bp.route("/")
def index():
    return redirect(url_for("viewer.view", path=""))


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
    }

    if target.is_dir():
        files = list_directory(basepath, path, show_all=bool(config.get("show_all", False)))
        return render_template("files_list.html", files=files, **context)

    if target.is_file():
        details = describe_file(basepath, path)
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
