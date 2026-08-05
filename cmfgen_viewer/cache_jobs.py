"""Background model-summary cache inspection and maintenance jobs."""

from __future__ import annotations

import copy
from pathlib import Path
import secrets
from threading import Lock
import time

from .final_spectrum import read_model
from .summary_cache import (
    delete_model_summary_entries,
    inspect_model_summary_cache,
    upsert_model_summary,
)
from .view_common import _build_summary_row


CACHE_MAINTENANCE_JOB_TTL_SECONDS = 6 * 60 * 60
CACHE_MAINTENANCE_MAX_JOBS = 16
CACHE_MAINTENANCE_ACTIONS = {"check", "refresh_stale", "remove_missing"}
CACHE_MAINTENANCE_JOBS: dict[str, dict[str, object]] = {}
CACHE_MAINTENANCE_JOBS_LOCK = Lock()


def cache_maintenance_action_label(action: str) -> str:
    labels = {
        "check": "Check model cache",
        "refresh_stale": "Refresh stale model summaries",
        "remove_missing": "Remove missing model summaries",
    }
    return labels.get(str(action), "Model cache maintenance")


def _cache_maintenance_prune_locked(now: float) -> None:
    expired = []
    for job_id, job in CACHE_MAINTENANCE_JOBS.items():
        if str(job.get("status", "")) == "running":
            continue
        try:
            finished_at = float(job.get("finished_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            finished_at = 0.0
        if finished_at > 0 and now - finished_at > CACHE_MAINTENANCE_JOB_TTL_SECONDS:
            expired.append(job_id)
    for job_id in expired:
        CACHE_MAINTENANCE_JOBS.pop(job_id, None)

    if len(CACHE_MAINTENANCE_JOBS) <= CACHE_MAINTENANCE_MAX_JOBS:
        return
    finished = sorted(
        (
            (job_id, float(job.get("finished_at", job.get("created_at", 0.0)) or 0.0))
            for job_id, job in CACHE_MAINTENANCE_JOBS.items()
            if str(job.get("status", "")) != "running"
        ),
        key=lambda item: item[1],
    )
    while len(CACHE_MAINTENANCE_JOBS) > CACHE_MAINTENANCE_MAX_JOBS and finished:
        job_id, _timestamp = finished.pop(0)
        CACHE_MAINTENANCE_JOBS.pop(job_id, None)


def cache_maintenance_job_create(*, action: str, basepath: str) -> tuple[str, bool]:
    if action not in CACHE_MAINTENANCE_ACTIONS:
        raise ValueError(f"Unsupported cache maintenance action: {action}")
    now = time.time()
    with CACHE_MAINTENANCE_JOBS_LOCK:
        _cache_maintenance_prune_locked(now)
        for job_id, job in CACHE_MAINTENANCE_JOBS.items():
            if str(job.get("status", "")) == "running":
                return job_id, True
        job_id = secrets.token_urlsafe(12)
        CACHE_MAINTENANCE_JOBS[job_id] = {
            "job_id": job_id,
            "kind": "cache-maintenance",
            "action": action,
            "action_label": cache_maintenance_action_label(action),
            "basepath": str(basepath),
            "status": "running",
            "phase": "Starting",
            "processed": 0,
            "total": 0,
            "current_entry": "",
            "created_at": now,
            "started_at": now,
            "finished_at": 0.0,
            "result": {},
            "error": "",
        }
    return job_id, False


def _cache_maintenance_job_update(job_id: str, **fields: object) -> bool:
    with CACHE_MAINTENANCE_JOBS_LOCK:
        job = CACHE_MAINTENANCE_JOBS.get(job_id)
        if not isinstance(job, dict):
            return False
        job.update(fields)
    return True


def cache_maintenance_job_snapshot(job_id: str) -> dict[str, object] | None:
    with CACHE_MAINTENANCE_JOBS_LOCK:
        job = CACHE_MAINTENANCE_JOBS.get(job_id)
        return copy.deepcopy(job) if isinstance(job, dict) else None


def cache_maintenance_latest_job(*, basepath: str) -> dict[str, object] | None:
    with CACHE_MAINTENANCE_JOBS_LOCK:
        latest: dict[str, object] | None = None
        latest_created = -1.0
        for job in CACHE_MAINTENANCE_JOBS.values():
            if not isinstance(job, dict) or str(job.get("basepath", "")) != str(basepath):
                continue
            try:
                created_at = float(job.get("created_at", 0.0) or 0.0)
            except (TypeError, ValueError):
                created_at = 0.0
            if latest is None or created_at > latest_created:
                latest = copy.deepcopy(job)
                latest_created = created_at
        return latest


def cache_maintenance_running_job_snapshots() -> list[dict[str, object]]:
    with CACHE_MAINTENANCE_JOBS_LOCK:
        _cache_maintenance_prune_locked(time.time())
        jobs = [
            copy.deepcopy(job)
            for job in CACHE_MAINTENANCE_JOBS.values()
            if isinstance(job, dict) and str(job.get("status", "")) == "running"
        ]
    jobs.sort(key=lambda job: float(job.get("created_at", 0.0) or 0.0), reverse=True)
    return jobs


def run_cache_maintenance_job(
    job_id: str,
    *,
    summary_cache_db: str,
    basepath: str,
) -> None:
    snapshot = cache_maintenance_job_snapshot(job_id)
    if snapshot is None:
        return
    action = str(snapshot.get("action", ""))

    def inspection_progress(processed: int, total: int, relpath: str) -> None:
        _cache_maintenance_job_update(
            job_id,
            phase="Checking cached models",
            processed=processed,
            total=total,
            current_entry=relpath,
        )

    try:
        inspection = inspect_model_summary_cache(
            summary_cache_db,
            basepath=basepath,
            progress_callback=inspection_progress,
        )
        result = _inspection_result_payload(inspection)
        if action == "refresh_stale":
            _refresh_stale_entries(
                job_id,
                summary_cache_db=summary_cache_db,
                basepath=basepath,
                inspection=inspection,
                result=result,
            )
            final_inspection = inspect_model_summary_cache(summary_cache_db, basepath=basepath)
            result["counts"] = final_inspection["counts"]
            result["total"] = final_inspection["total"]
            result["issues"] = _inspection_issues(final_inspection)
        elif action == "remove_missing":
            missing_relpaths = [
                str(entry.get("relpath", ""))
                for entry in inspection.get("entries", [])
                if isinstance(entry, dict) and str(entry.get("status", "")) == "missing"
            ]
            removed = delete_model_summary_entries(
                summary_cache_db,
                basepath=basepath,
                relpaths=missing_relpaths,
            )
            result["removed"] = removed
            final_inspection = inspect_model_summary_cache(summary_cache_db, basepath=basepath)
            result["counts"] = final_inspection["counts"]
            result["total"] = final_inspection["total"]
            result["issues"] = _inspection_issues(final_inspection)

        _cache_maintenance_job_update(
            job_id,
            status="completed",
            phase="Completed",
            current_entry="",
            processed=int(result.get("total", 0) or 0),
            total=int(result.get("total", 0) or 0),
            result=result,
            finished_at=time.time(),
        )
    except Exception as exc:
        _cache_maintenance_job_update(
            job_id,
            status="failed",
            phase="Failed",
            current_entry="",
            error=f"Cache maintenance failed: {exc}",
            finished_at=time.time(),
        )


def _inspection_result_payload(inspection: dict[str, object]) -> dict[str, object]:
    return {
        "basepath": str(inspection.get("basepath", "")),
        "total": int(inspection.get("total", 0) or 0),
        "counts": dict(inspection.get("counts", {})) if isinstance(inspection.get("counts"), dict) else {},
        "issues": _inspection_issues(inspection),
        "refreshed": 0,
        "removed": 0,
        "failed": 0,
        "failures": [],
    }


def _inspection_issues(inspection: dict[str, object], *, limit: int = 50) -> list[dict[str, str]]:
    entries = inspection.get("entries")
    if not isinstance(entries, list):
        return []
    issues: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("status", "")) == "valid":
            continue
        issues.append(
            {
                "relpath": str(entry.get("relpath", "")),
                "status": str(entry.get("status", "error")),
                "reason": str(entry.get("reason", "")),
            }
        )
        if len(issues) >= limit:
            break
    return issues


def _refresh_stale_entries(
    job_id: str,
    *,
    summary_cache_db: str,
    basepath: str,
    inspection: dict[str, object],
    result: dict[str, object],
) -> None:
    entries_raw = inspection.get("entries")
    entries = entries_raw if isinstance(entries_raw, list) else []
    stale_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict) and str(entry.get("status", "")) in {"stale", "path_changed"}
    ]
    checked_total = int(inspection.get("total", 0) or 0)
    total = checked_total + len(stale_entries)
    failures: list[dict[str, str]] = []
    refreshed = 0
    base = Path(basepath).expanduser()
    for index, entry in enumerate(stale_entries, start=1):
        relpath = str(entry.get("relpath", ""))
        _cache_maintenance_job_update(
            job_id,
            phase="Refreshing stale summaries",
            processed=checked_total + index - 1,
            total=total,
            current_entry=relpath,
        )
        target = base / relpath
        try:
            vadat = target / "VADAT"
            mod_sum = target / "MOD_SUM"
            model = read_model(target)
            mod_sum_mtime = mod_sum.stat().st_mtime
            values = _build_summary_row(model, mod_sum_mtime=mod_sum_mtime)
            upsert_model_summary(
                summary_cache_db,
                basepath=basepath,
                relpath=relpath,
                model_dir=target,
                model_name=str(model.get("name", target.name)),
                values=values,
                vadat_mtime=vadat.stat().st_mtime,
                mod_sum_mtime=mod_sum_mtime,
            )
            refreshed += 1
        except Exception as exc:
            failures.append({"relpath": relpath, "error": str(exc)})
        _cache_maintenance_job_update(job_id, processed=checked_total + index)

    result["refreshed"] = refreshed
    result["failed"] = len(failures)
    result["failures"] = failures[:50]
