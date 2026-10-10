"""Site-wide status API for background work."""

from __future__ import annotations

import math
from pathlib import Path

from flask import jsonify, url_for

from .grid_config import _grid_fit_source_label, _normalize_grid_fit_source
from .observed_spectrum import is_valid_upload_token, list_upload_manifests
from .summary_jobs import SUMMARY_JOB_DETAILS, SUMMARY_JOB_KIND, summary_job_progress
from .view_common import _cache_jobs, _grid_jobs, _upload_root, _viewer_config, bp


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


def _cache_maintenance_background_task(snapshot: dict[str, object]) -> dict[str, object]:
    job_id = str(snapshot.get("job_id", "")).strip()
    basepath = str(snapshot.get("basepath", "")).strip()
    processed = int(snapshot.get("processed", 0) or 0)
    total = int(snapshot.get("total", 0) or 0)
    progress_percent = 100.0 * processed / total if total > 0 else 0.0
    if not math.isfinite(progress_percent):
        progress_percent = 0.0
    target = Path(basepath).name or basepath or "current model base"
    return {
        "id": job_id,
        "kind": "cache-maintenance",
        "status": "running",
        "status_label": "Running",
        "title": str(snapshot.get("action_label", "Model cache maintenance")),
        "target": target,
        "href": url_for("viewer.system_status", job=job_id, _anchor="model-cache"),
        "return_label": "Return to System",
        "processed": processed,
        "total": total,
        "progress_percent": min(100.0, max(0.0, progress_percent)),
        "progress_label": f"{processed}/{total} entries" if total > 0 else f"{processed} entries",
        "current_model": str(snapshot.get("current_entry", "")).strip(),
        "cancel_requested": False,
    }


def _summary_background_task(snapshot: dict[str, object]) -> dict[str, object]:
    progress = summary_job_progress(snapshot)
    return {
        "id": snapshot["job_id"], "kind": SUMMARY_JOB_KIND, "status": "running",
        "status_label": progress["status_label"], "title": "Bulk model summary",
        "target": str(snapshot.get("path") or "Model root"),
        "href": url_for("viewer.bulk_summary_job", job_id=snapshot["job_id"]),
        "return_label": "Return to model summaries", "processed": progress["processed"],
        "total": progress["total"], "progress_percent": progress["progress_percent"],
        "progress_label": f"{progress['processed']}/{progress['total']} folders",
        "current_model": str(snapshot.get("current_entry", "")),
        "cancel_requested": bool(snapshot.get("cancel_requested")),
    }


def background_tasks_payload():
    upload_root = _upload_root(_viewer_config())
    upload_names = {
        str(entry.get("token", "")): str(entry.get("filename", "")).strip()
        for entry in list_upload_manifests(upload_root)
    }
    grid_tasks = [
        _grid_fit_background_task(snapshot, upload_names=upload_names)
        for snapshot in _grid_jobs().snapshots(status="running")
    ]
    cache_tasks = [
        _summary_background_task(snapshot) if snapshot.get("kind") == SUMMARY_JOB_KIND
        else _cache_maintenance_background_task(snapshot)
        for snapshot in _cache_jobs().snapshots(status="running", exclude=SUMMARY_JOB_DETAILS)
    ]
    tasks = grid_tasks + cache_tasks
    return {"ok": True, "running_count": len(tasks), "tasks": tasks}


@bp.route("/tasks/status")
def background_tasks_status():
    response = jsonify(background_tasks_payload())
    response.headers["Cache-Control"] = "no-store"
    return response
