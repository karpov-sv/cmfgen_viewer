"""Site-wide status API for background work."""

from __future__ import annotations

import math

from flask import jsonify, url_for

from .grid_jobs import _grid_search_running_job_snapshots
from .observed_spectrum import is_valid_upload_token, list_upload_manifests
from .view_common import _grid_fit_source_label, _normalize_grid_fit_source, _upload_root, _viewer_config, bp


def _grid_fit_background_task(
    snapshot: dict[str, object],
    *,
    upload_names: dict[str, str],
) -> dict[str, object]:
    job_id = str(snapshot.get("job_id", "")).strip()
    upload_token = str(snapshot.get("upload_token", "")).strip()
    fit_source = _normalize_grid_fit_source(snapshot.get("fit_source"))
    fit_source_label = str(snapshot.get("fit_source_label", _grid_fit_source_label(fit_source))).strip()
    upload_name = upload_names.get(upload_token, "")
    target_label = upload_name or (f"upload {upload_token[:8]}" if upload_token else "upload")

    processed = int(snapshot.get("processed", 0) or 0)
    total = int(snapshot.get("total", 0) or 0)
    progress_percent = 0.0
    if total > 0:
        progress_percent = min(100.0, max(0.0, 100.0 * processed / total))
    if not math.isfinite(progress_percent):
        progress_percent = 0.0

    if is_valid_upload_token(upload_token):
        href = url_for("viewer.upload_view", token=upload_token, _anchor="grid-fit")
    else:
        href = url_for("viewer.uploads")

    cancel_requested = bool(snapshot.get("cancel_requested", False))
    return {
        "id": job_id,
        "kind": "grid-fit",
        "status": "running",
        "status_label": "Stopping" if cancel_requested else "Running",
        "title": f"{fit_source_label} fit",
        "target": target_label,
        "href": href,
        "return_label": f"Return to {target_label}",
        "processed": processed,
        "total": total,
        "progress_percent": progress_percent,
        "progress_label": f"{processed}/{total} models" if total > 0 else f"{processed} models",
        "current_model": str(snapshot.get("current_model", "")).strip(),
        "cancel_requested": cancel_requested,
    }


@bp.route("/tasks/status")
def background_tasks_status():
    upload_root = _upload_root(_viewer_config())
    upload_names = {
        str(entry.get("token", "")): str(entry.get("filename", "")).strip()
        for entry in list_upload_manifests(upload_root)
    }
    tasks = [
        _grid_fit_background_task(snapshot, upload_names=upload_names)
        for snapshot in _grid_search_running_job_snapshots()
    ]
    response = jsonify({"ok": True, "running_count": len(tasks), "tasks": tasks})
    response.headers["Cache-Control"] = "no-store"
    return response
