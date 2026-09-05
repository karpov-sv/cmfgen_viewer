"""Background model-summary cache inspection and maintenance jobs."""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from .job_store import JobStore
from .model_metadata import read_model
from .model_summary import summary_from_model
from .summary_cache import (
    delete_model_summary_entries,
    inspect_model_summary_cache,
    upsert_model_summary,
)

CACHE_MAINTENANCE_ACTIONS = {"check", "refresh_stale", "remove_missing"}


def cache_maintenance_action_label(action: str) -> str:
    labels = {
        "check": "Check model cache",
        "refresh_stale": "Refresh stale model summaries",
        "remove_missing": "Remove missing model summaries",
    }
    return labels.get(str(action), "Model cache maintenance")


def cache_maintenance_job_create(
    store: JobStore, *, action: str, basepath: str
) -> tuple[str, bool]:
    if action not in CACHE_MAINTENANCE_ACTIONS:
        raise ValueError(f"Unsupported cache maintenance action: {action}")
    now = time.time()
    return store.insert(
        {
            "job_id": secrets.token_urlsafe(12),
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
        },
        singleton=True,
    )


def run_cache_maintenance_job(
    store: JobStore,
    job_id: str,
    *,
    summary_cache_db: str,
    basepath: str,
) -> None:
    snapshot = store.snapshot(job_id)
    if snapshot is None:
        return
    action = str(snapshot.get("action", ""))

    def inspection_progress(processed: int, total: int, relpath: str) -> None:
        store.update(
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
                store,
                job_id,
                summary_cache_db=summary_cache_db,
                basepath=basepath,
                inspection=inspection,
                result=result,
            )
            final_inspection = inspect_model_summary_cache(
                summary_cache_db, basepath=basepath
            )
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
            final_inspection = inspect_model_summary_cache(
                summary_cache_db, basepath=basepath
            )
            result["counts"] = final_inspection["counts"]
            result["total"] = final_inspection["total"]
            result["issues"] = _inspection_issues(final_inspection)

        store.update(
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
        store.update(
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
    store: JobStore,
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
        if isinstance(entry, dict)
        and str(entry.get("status", "")) in {"stale", "path_changed"}
    ]
    checked_total = int(inspection.get("total", 0) or 0)
    total = checked_total + len(stale_entries)
    failures: list[dict[str, str]] = []
    refreshed = 0
    base = Path(basepath).expanduser()
    for index, entry in enumerate(stale_entries, start=1):
        relpath = str(entry.get("relpath", ""))
        store.update(
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
            upsert_model_summary(
                summary_cache_db,
                basepath=basepath,
                relpath=relpath,
                model_dir=target,
                model_name=str(model.get("name", target.name)),
                summary=summary_from_model(model),
                vadat_mtime=vadat.stat().st_mtime,
                mod_sum_mtime=mod_sum_mtime,
            )
            refreshed += 1
        except Exception as exc:
            failures.append({"relpath": relpath, "error": str(exc)})
        store.update(job_id, processed=checked_total + index)

    result["refreshed"] = refreshed
    result["failed"] = len(failures)
    result["failures"] = failures[:50]
