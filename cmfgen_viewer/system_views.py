"""Runtime information and guarded application-maintenance routes."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import platform
from threading import Thread

from flask import abort, current_app, jsonify, redirect, render_template, request, url_for

from .cache_jobs import (
    CACHE_MAINTENANCE_ACTIONS,
    cache_maintenance_job_create,
    cache_maintenance_job_snapshot,
    cache_maintenance_latest_job,
    cache_maintenance_running_job_snapshots,
    run_cache_maintenance_job,
)
from .grid_jobs import _grid_search_running_job_snapshots
from .observed_spectrum import list_upload_manifests
from .summary_cache import (
    delete_model_summary_namespace,
    delete_model_summary_namespaces_except,
    list_model_summary_namespaces,
)
from .view_common import _spectrum_lambda_bounds, _tlusty_root, _upload_root, _viewer_config, bp


def _package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return ""


def _format_size(total_bytes: int) -> str:
    value = float(max(0, total_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{total_bytes} B"


def _cache_namespaces(summary_cache_db: str, *, current_basepath: str) -> list[dict[str, object]]:
    namespaces = list_model_summary_namespaces(summary_cache_db)
    for item in namespaces:
        basepath = str(item.get("basepath", ""))
        item["is_current"] = basepath == current_basepath
        item["exists"] = bool(basepath) and Path(basepath).expanduser().is_dir()
    namespaces.sort(key=lambda item: (not bool(item.get("is_current")), str(item.get("basepath", "")).lower()))
    return namespaces


def _maintenance_job_payload(snapshot: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(snapshot, dict):
        return None
    processed = int(snapshot.get("processed", 0) or 0)
    total = int(snapshot.get("total", 0) or 0)
    status = str(snapshot.get("status", ""))
    progress = 100.0 if status == "completed" else (100.0 * processed / total if total > 0 else 0.0)
    return {
        **snapshot,
        "processed": processed,
        "total": total,
        "progress_percent": min(100.0, max(0.0, progress)),
    }


@bp.route("/system/")
def system_status():
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    upload_root = _upload_root(config)
    namespaces = _cache_namespaces(summary_cache_db, current_basepath=basepath)
    current_namespace = next((item for item in namespaces if item.get("is_current")), None)

    requested_job_id = str(request.args.get("job", "")).strip()
    maintenance_job = cache_maintenance_job_snapshot(requested_job_id) if requested_job_id else None
    if maintenance_job is None:
        maintenance_job = cache_maintenance_latest_job(basepath=basepath)
    maintenance_job_payload = _maintenance_job_payload(maintenance_job)

    uploads = list_upload_manifests(upload_root)
    upload_bytes = sum(int(item.get("size", 0) or 0) for item in uploads)
    lambda_min, lambda_max = _spectrum_lambda_bounds(config)
    cache_path = Path(summary_cache_db).expanduser()
    cache_size = cache_path.stat().st_size if cache_path.is_file() else 0
    active_grid_jobs = len(_grid_search_running_job_snapshots())
    active_cache_jobs = len(cache_maintenance_running_job_snapshots())
    fit_pool_size = int(config.get("fit_pool_size_max", 0) or 0)
    read_write_enabled = bool(config.get("read_write_enabled", False))
    runtime_rows = [
        ["Model base directory", basepath],
        ["Model directory access", "Read-write" if read_write_enabled else "Read-only"],
        ["Summary cache database", summary_cache_db],
        ["Summary cache size", _format_size(cache_size)],
        ["Upload storage", str(upload_root)],
        ["Managed uploads", f"{len(uploads)} ({_format_size(upload_bytes)})"],
        ["TLUSTY root", str(_tlusty_root(config))],
        ["Spectrum wavelength range", f"{lambda_min:g} .. {lambda_max:g} Å"],
        ["Fit worker limit", str(fit_pool_size) if fit_pool_size > 0 else "Automatic"],
        ["Show hidden files", "Yes" if bool(config.get("show_all", False)) else "No"],
        ["HTTP authentication", "Enabled" if bool(config.get("auth_enabled", False)) else "Disabled"],
        ["Debug mode", "Enabled" if current_app.debug else "Disabled"],
        ["Python", platform.python_version()],
        ["Flask", _package_version("flask")],
    ]

    return render_template(
        "system.html",
        runtime_rows=runtime_rows,
        namespaces=namespaces,
        current_basepath=basepath,
        current_entry_count=int(current_namespace.get("entry_count", 0) or 0) if current_namespace else 0,
        summary_cache_db=summary_cache_db,
        maintenance_job=maintenance_job_payload,
        upload_root=upload_root,
        upload_count=len(uploads),
        upload_size=_format_size(upload_bytes),
        active_grid_jobs=active_grid_jobs,
        active_cache_jobs=active_cache_jobs,
        active_task_count=active_grid_jobs + active_cache_jobs,
        read_write_enabled=read_write_enabled,
        message=str(request.args.get("message", "")).strip(),
        error=str(request.args.get("error", "")).strip(),
    )


@bp.route("/system/cache/maintain", methods=["POST"])
def system_cache_maintain():
    action = str(request.form.get("action", "")).strip()
    if action not in CACHE_MAINTENANCE_ACTIONS:
        abort(400)
    config = _viewer_config()
    basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    job_id, existing = cache_maintenance_job_create(action=action, basepath=basepath)
    if not existing:
        worker = Thread(
            target=run_cache_maintenance_job,
            kwargs={"job_id": job_id, "summary_cache_db": summary_cache_db, "basepath": basepath},
            daemon=True,
        )
        worker.start()
    if existing:
        return redirect(
            url_for(
                "viewer.system_status",
                job=job_id,
                error="Another cache maintenance job is already running; the requested action was not started.",
                _anchor="model-cache",
            )
        )
    return redirect(
        url_for("viewer.system_status", job=job_id, message="Cache maintenance started.", _anchor="model-cache")
    )


@bp.route("/system/cache/job/<job_id>")
def system_cache_job_status(job_id: str):
    snapshot = cache_maintenance_job_snapshot(job_id)
    if snapshot is None:
        return jsonify({"ok": False, "error": "Cache maintenance job is not available."}), 404
    response = jsonify({"ok": True, "job": _maintenance_job_payload(snapshot)})
    response.headers["Cache-Control"] = "no-store"
    return response


def _known_cache_namespaces(summary_cache_db: str) -> set[str]:
    return {str(item.get("basepath", "")) for item in list_model_summary_namespaces(summary_cache_db)}


def _reject_cleanup_while_maintenance_runs():
    if not cache_maintenance_running_job_snapshots():
        return None
    return redirect(
        url_for(
            "viewer.system_status",
            error="Wait for cache maintenance to finish before deleting cache entries.",
            _anchor="model-cache",
        )
    )


@bp.route("/system/cache/delete-base", methods=["POST"])
def system_cache_delete_base():
    blocked = _reject_cleanup_while_maintenance_runs()
    if blocked is not None:
        return blocked
    config = _viewer_config()
    current_basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    target = str(request.form.get("basepath", ""))
    if not target or target not in _known_cache_namespaces(summary_cache_db):
        abort(404)
    deleted = delete_model_summary_namespace(summary_cache_db, basepath=target)
    label = "current base" if target == current_basepath else target
    return redirect(
        url_for("viewer.system_status", message=f"Removed {deleted} cached model(s) for {label}.", _anchor="model-cache")
    )


@bp.route("/system/cache/delete-unavailable", methods=["POST"])
def system_cache_delete_unavailable():
    blocked = _reject_cleanup_while_maintenance_runs()
    if blocked is not None:
        return blocked
    config = _viewer_config()
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    unavailable = [
        str(item.get("basepath", ""))
        for item in list_model_summary_namespaces(summary_cache_db)
        if not Path(str(item.get("basepath", ""))).expanduser().is_dir()
    ]
    deleted = sum(delete_model_summary_namespace(summary_cache_db, basepath=item) for item in unavailable)
    return redirect(
        url_for(
            "viewer.system_status",
            message=f"Removed {deleted} cached model(s) from {len(unavailable)} unavailable base(s).",
            _anchor="model-cache",
        )
    )


@bp.route("/system/cache/delete-noncurrent", methods=["POST"])
def system_cache_delete_noncurrent():
    blocked = _reject_cleanup_while_maintenance_runs()
    if blocked is not None:
        return blocked
    config = _viewer_config()
    current_basepath = str(config.get("basepath", "."))
    summary_cache_db = str(config.get("summary_cache_db", "model_summary_cache.sqlite"))
    deleted = delete_model_summary_namespaces_except(summary_cache_db, basepath=current_basepath)
    return redirect(
        url_for(
            "viewer.system_status",
            message=f"Removed {deleted} cached model(s) outside the current base.",
            _anchor="model-cache",
        )
    )
