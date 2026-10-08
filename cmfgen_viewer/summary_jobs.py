"""Background bulk summaries; independent of request and browser lifetimes."""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from dataclasses import replace

from .browser import resolve_path
from .job_store import JobStore
from .model_metadata import read_model
from .model_summary import summary_from_model, summary_from_payload, summary_table_row
from .summary_cache import _connect, _upsert_model_summary

SUMMARY_JOB_KIND = "bulk-summary"
SUMMARY_JOB_DETAILS = ("rows", "skipped", "failures", "selected_paths")


def summary_job_create(
    store: JobStore, *, basepath: str, path: str, selected_paths: list[str],
    force_refresh: bool = False, parent_job_id: str = "",
) -> tuple[str, bool]:
    now = time.time()
    return store.insert({
        "job_id": secrets.token_urlsafe(12), "kind": SUMMARY_JOB_KIND,
        "basepath": basepath, "path": path, "selected_paths": list(selected_paths),
        "force_refresh": force_refresh, "parent_job_id": parent_job_id,
        "status": "running", "phase": "Starting", "total": len(selected_paths),
        "processed": 0, "successful": 0, "updated": 0, "reused": 0,
        "skipped_count": 0, "failed_count": 0, "current_entry": "",
        "created_at": now, "started_at": now, "updated_at": now, "finished_at": 0.,
        "cancel_requested": False, "cancel_requested_at": 0.,
        "rows": [], "skipped": [], "failures": [], "error": "",
    }, singleton=True)


def summary_job_progress(snapshot: dict[str, object]) -> dict[str, object]:
    """Small polling payload: never send selections or summary tables."""
    result = {key: value for key, value in snapshot.items() if key not in SUMMARY_JOB_DETAILS}
    processed, total = int(result["processed"]), int(result["total"])
    result["progress_percent"] = min(100., 100. * processed / total) if total else 0.
    finished = float(result["finished_at"] or time.time())
    result["elapsed_seconds"] = max(0., finished - float(result["started_at"]))
    result["remaining_count"] = max(0, total - processed)
    result["status_label"] = (
        "Stopping" if result["status"] == "running" and result["cancel_requested"]
        else "Completed with errors" if result["status"] == "completed" and result["failed_count"]
        else str(result["status"]).capitalize()
    )
    return result


def summary_job_retry_paths(snapshot: dict[str, object]) -> list[str]:
    """Retry data failures plus unfinished entries after cancellation/fatal error."""
    failed = [str(item["relpath"]) for item in snapshot["failures"]]
    pending = snapshot["selected_paths"][int(snapshot["processed"]):]
    return list(dict.fromkeys(failed + pending))


def run_summary_job(store: JobStore, job_id: str, *, summary_cache_db: str) -> None:
    snapshot = store.snapshot(job_id)
    if snapshot is None or snapshot.get("kind") != SUMMARY_JOB_KIND or snapshot["status"] != "running":
        return
    basepath, path = str(snapshot["basepath"]), str(snapshot["path"])
    updated = reused = skipped = failed = 0

    def finish(status: str, error: str = "") -> None:
        store.update(job_id, status=status, phase=status.capitalize(), error=error,
                     current_entry="", finished_at=time.time(), updated_at=time.time())

    try:
        if store.cancel_requested(job_id):
            finish("canceled")
            return
        directory = resolve_path(basepath, path)
        store.update(job_id, phase="Opening summary cache", updated_at=time.time())
        with _connect(summary_cache_db) as connection:
            for index, rel in enumerate(snapshot["selected_paths"]):
                if store.cancel_requested(job_id):
                    finish("canceled")
                    return
                stage = "read"
                store.update(job_id, phase="Reading models", current_entry=rel, updated_at=time.time())
                try:
                    try:
                        target = resolve_path(basepath, rel)
                    except FileNotFoundError:
                        target = None
                    reason = ""
                    if target is None:
                        reason = "Not found or unsafe path"
                    elif not target.is_dir():
                        reason = "Not a directory"
                    else:
                        try:
                            target.relative_to(directory)
                        except ValueError:
                            reason = "Outside current folder"
                    if not reason and (not (target / "VADAT").is_file() or not (target / "MOD_SUM").is_file()):
                        reason = "Missing VADAT or MOD_SUM"
                    if reason:
                        skipped += 1
                        store.append(job_id, "skipped", {"relpath": rel, "reason": reason},
                                     skipped_count=skipped, processed=index + 1, updated_at=time.time())
                        continue

                    vadat, mod_sum = target / "VADAT", target / "MOD_SUM"
                    vstat, mstat = vadat.stat(), mod_sum.stat()
                    stage = "cache-read"
                    store.update(job_id, phase="Checking cached summary", updated_at=time.time())
                    cached = connection.execute(
                        "SELECT * FROM model_summary_cache WHERE basepath = ? AND relpath = ?",
                        (basepath, rel),
                    ).fetchone()
                    summary = None
                    if (not snapshot["force_refresh"] and cached is not None
                        and cached["model_key"] == str(target.resolve())
                        and cached["vadat_mtime"] == vstat.st_mtime
                        and cached["mod_sum_mtime"] == mstat.st_mtime):
                        try:
                            summary = summary_from_payload(json.loads(cached["summary_json"]))
                            if not summary.name:
                                summary = replace(summary, name=str(cached["model_name"] or target.name))
                        except (TypeError, ValueError):
                            pass  # Invalid cache data is rebuilt, not reused.
                    if summary is None:
                        stage = "read"
                        store.update(job_id, phase="Reading model metadata", updated_at=time.time())
                        model = read_model(target)
                        summary = summary_from_model(model)
                        after_vstat, after_mstat = vadat.stat(), mod_sum.stat()
                        if ((after_vstat.st_mtime_ns, after_vstat.st_size) != (vstat.st_mtime_ns, vstat.st_size)
                            or (after_mstat.st_mtime_ns, after_mstat.st_size) != (mstat.st_mtime_ns, mstat.st_size)):
                            raise RuntimeError("Model files changed while reading; retry when they are stable.")
                        values = summary_table_row(summary, mod_sum_mtime=mstat.st_mtime)
                        stage = "cache-write"
                        store.update(job_id, phase="Saving summary", updated_at=time.time())
                        _upsert_model_summary(
                            connection, basepath=basepath, relpath=rel, model_dir=target,
                            model_name=str(model.get("name", target.name)), summary=summary,
                            vadat_mtime=vstat.st_mtime, mod_sum_mtime=mstat.st_mtime,
                        )
                        updated += 1
                    else:
                        values = summary_table_row(summary, mod_sum_mtime=mstat.st_mtime)
                        reused += 1
                    store.append(job_id, "rows", {
                        "path": rel, "values": values,
                    }, successful=updated + reused, updated=updated, reused=reused,
                                 processed=index + 1, updated_at=time.time())
                except Exception as exc:
                    failed += 1
                    store.append(job_id, "failures", {"relpath": rel, "stage": stage, "error": str(exc)},
                                 failed_count=failed, processed=index + 1, updated_at=time.time())
                    if isinstance(exc, sqlite3.DatabaseError) and not isinstance(exc, sqlite3.IntegrityError):
                        raise  # Stop on systemic DB failure rather than repeat it for every model.
        finish("canceled" if store.cancel_requested(job_id) else "completed")
    except Exception as exc:
        finish("failed", f"Bulk summarization stopped: {exc}")
