"""In-memory grid-search job state and worker orchestration."""

from __future__ import annotations

import copy
import math
import multiprocessing as mp
import secrets
import time

from .grid_catalog import (
    _empty_tlusty_confidence_profiles,
    _summarize_tlusty_confidence_profiles,
    _update_tlusty_confidence_profiles,
)
from .grid_fitting import (
    _fit_bounds_payload,
    _fit_single_grid_candidate,
    _fit_wavelength_range_payload,
    _grid_fit_worker_init,
    _grid_fit_worker_task,
    _resolve_grid_fit_pool_size,
)
from .view_common import (
    GRID_FIT_SOURCE_TLUSTY,
    GRID_SEARCH_JOBS,
    GRID_SEARCH_JOBS_LOCK,
    GRID_SEARCH_JOB_TTL_SECONDS,
    GRID_SEARCH_MAX_JOBS,
    GRID_SEARCH_TOP_RESULTS,
    _grid_fit_source_label,
    _normalize_grid_fit_source,
)

def _grid_search_prune_locked(now: float) -> None:
    expired_ids: list[str] = []
    for job_id, job in GRID_SEARCH_JOBS.items():
        if str(job.get("status", "")) == "running":
            continue
        finished_at_raw = job.get("finished_at", job.get("created_at", 0.0))
        try:
            finished_at = float(finished_at_raw)
        except (TypeError, ValueError):
            finished_at = 0.0
        if finished_at > 0 and (now - finished_at) > GRID_SEARCH_JOB_TTL_SECONDS:
            expired_ids.append(job_id)
    for job_id in expired_ids:
        GRID_SEARCH_JOBS.pop(job_id, None)

    if len(GRID_SEARCH_JOBS) <= GRID_SEARCH_MAX_JOBS:
        return

    finished_jobs = [
        (
            job_id,
            float(job.get("finished_at", job.get("created_at", 0.0)) or 0.0),
        )
        for job_id, job in GRID_SEARCH_JOBS.items()
        if str(job.get("status", "")) != "running"
    ]
    finished_jobs.sort(key=lambda item: item[1])
    while len(GRID_SEARCH_JOBS) > GRID_SEARCH_MAX_JOBS and finished_jobs:
        job_id, _timestamp = finished_jobs.pop(0)
        GRID_SEARCH_JOBS.pop(job_id, None)


def _grid_search_job_update(job_id: str, **fields: object) -> bool:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return False
        for key, value in fields.items():
            job[key] = value
    return True


def _grid_search_job_cancel_requested(job_id: str) -> bool:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return False
        return bool(job.get("cancel_requested", False))


def _grid_search_job_snapshot(job_id: str) -> dict[str, object] | None:
    with GRID_SEARCH_JOBS_LOCK:
        job = GRID_SEARCH_JOBS.get(job_id)
        if not isinstance(job, dict):
            return None
        return copy.deepcopy(job)


def _grid_search_running_job_snapshots() -> list[dict[str, object]]:
    with GRID_SEARCH_JOBS_LOCK:
        _grid_search_prune_locked(time.time())
        snapshots: list[dict[str, object]] = []
        for job_id, job in GRID_SEARCH_JOBS.items():
            if not isinstance(job, dict) or str(job.get("status", "")) != "running":
                continue
            snapshot = copy.deepcopy(job)
            snapshot["job_id"] = job_id
            snapshots.append(snapshot)

    def created_at(snapshot: dict[str, object]) -> float:
        try:
            return float(snapshot.get("created_at", 0.0))
        except (TypeError, ValueError):
            return 0.0

    snapshots.sort(key=created_at, reverse=True)
    return snapshots


def _grid_search_active_job_for_upload(upload_token: str) -> dict[str, object] | None:
    with GRID_SEARCH_JOBS_LOCK:
        latest: tuple[str, dict[str, object]] | None = None
        latest_created = -1.0
        for job_id, job in GRID_SEARCH_JOBS.items():
            if not isinstance(job, dict):
                continue
            if str(job.get("upload_token", "")) != upload_token:
                continue
            if str(job.get("status", "")) != "running":
                continue
            try:
                created_at = float(job.get("created_at", 0.0))
            except (TypeError, ValueError):
                created_at = 0.0
            if latest is None or created_at > latest_created:
                latest = (job_id, copy.deepcopy(job))
                latest_created = created_at

    if latest is None:
        return None
    job_id, payload = latest
    payload["job_id"] = job_id
    return payload


def _grid_search_job_create(
    *,
    upload_token: str,
    fit_source: str,
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    fit_wavelength_range: tuple[float, float] | None,
    model_name_pattern: str,
    total_models: int,
) -> str:
    normalized_source = _normalize_grid_fit_source(fit_source)
    job_id = secrets.token_urlsafe(12)
    now = time.time()
    payload: dict[str, object] = {
        "job_id": job_id,
        "status": "running",
        "upload_token": upload_token,
        "fit_source": normalized_source,
        "fit_source_label": _grid_fit_source_label(normalized_source),
        "mode": mode,
        "model_name_pattern": str(model_name_pattern or "").strip(),
        "fit_bounds": _fit_bounds_payload(fit_bounds),
        "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
        "total": int(total_models),
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "current_model": "",
        "best_so_far": {},
        "created_at": now,
        "started_at": now,
        "finished_at": 0.0,
        "cancel_requested": False,
        "cancel_requested_at": 0.0,
        "error": "",
        "result": {},
    }
    with GRID_SEARCH_JOBS_LOCK:
        _grid_search_prune_locked(now)
        GRID_SEARCH_JOBS[job_id] = payload
    return job_id


def _run_upload_grid_search_job(
    job_id: str,
    *,
    upload_token: str,
    fit_source: str,
    mode: str,
    observed: dict[str, object],
    fit_bounds: dict[str, tuple[float, float]],
    fit_wavelength_range: tuple[float, float] | None,
    model_name_pattern: str,
    model_candidates: list[dict[str, object]],
    lambda_min: float,
    lambda_max: float,
    max_pool_size: int,
) -> None:
    try:
        normalized_source = _normalize_grid_fit_source(fit_source)
        fit_source_label = _grid_fit_source_label(normalized_source)

        def update_iteration_progress(processed: int, *, current_model: str | None = None) -> None:
            fields: dict[str, object] = {
                "processed": processed,
                "successful": successful,
                "failed": failed,
                "best_so_far": copy.deepcopy(best_model) if best_model is not None else {},
            }
            if current_model is not None:
                fields["current_model"] = current_model
            _grid_search_job_update(job_id, **fields)

        def finish_canceled(
            *,
            processed: int,
            successful: int,
            failed: int,
            elapsed_seconds: float,
            top_models: list[dict[str, object]],
            best_model: dict[str, object] | None,
        ) -> None:
            tlusty_confidence = _summarize_tlusty_confidence_profiles(
                best_model=best_model,
                profiles=tlusty_confidence_profiles,
                mode=mode,
            )
            result_payload: dict[str, object] = {
                "fit_source": normalized_source,
                "fit_source_label": fit_source_label,
                "mode": mode,
                "upload_token": upload_token,
                "model_name_pattern": str(model_name_pattern or "").strip(),
                "fit_bounds": _fit_bounds_payload(fit_bounds),
                "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
                "elapsed_seconds": elapsed_seconds,
                "best_model": best_model,
                "top_models": top_models,
            }
            if tlusty_confidence:
                result_payload["tlusty_confidence"] = tlusty_confidence
            _grid_search_job_update(
                job_id,
                status="canceled",
                processed=processed,
                successful=successful,
                failed=failed,
                current_model="",
                best_so_far=copy.deepcopy(best_model) if best_model is not None else {},
                result=result_payload,
                finished_at=time.time(),
                error="Grid search canceled by user.",
            )

        total = len(model_candidates)
        successful = 0
        failed = 0
        best_model: dict[str, object] | None = None
        top_models: list[dict[str, object]] = []
        tlusty_confidence_profiles: dict[str, dict[int | float, dict[str, object]]] | None = None
        if normalized_source == GRID_FIT_SOURCE_TLUSTY:
            tlusty_confidence_profiles = _empty_tlusty_confidence_profiles()
        started_at = time.time()
        worker_count = _resolve_grid_fit_pool_size(max_pool_size, total)

        def apply_candidate_result(candidate_result: dict[str, object], *, processed: int) -> bool:
            nonlocal successful, failed, best_model, top_models
            status = str(candidate_result.get("status", "failed"))
            if status == "canceled":
                finish_canceled(
                    processed=max(0, processed - 1),
                    successful=successful,
                    failed=failed,
                    elapsed_seconds=max(0.0, time.time() - started_at),
                    top_models=top_models,
                    best_model=best_model,
                )
                return True

            item = candidate_result.get("item")
            if status != "success" or not isinstance(item, dict):
                failed += 1
                update_iteration_progress(processed, current_model="")
                return False

            successful += 1
            top_models.append(item)
            top_models.sort(key=lambda candidate: float(candidate.get("rmse", math.inf)))
            if len(top_models) > GRID_SEARCH_TOP_RESULTS:
                top_models = top_models[:GRID_SEARCH_TOP_RESULTS]

            _update_tlusty_confidence_profiles(tlusty_confidence_profiles, item)

            if best_model is None or float(item["rmse"]) < float(best_model.get("rmse", math.inf)):
                best_model = dict(item)
            update_iteration_progress(processed, current_model="")
            return False

        if worker_count <= 1:
            for index, model_candidate in enumerate(model_candidates, start=1):
                model_name = str(model_candidate.get("model_name", "")).strip()
                model_path = str(model_candidate.get("model_path", model_candidate.get("model_relpath", ""))).strip()
                progress_model = model_name
                if model_path and model_path != model_name:
                    progress_model = f"{model_name} ({model_path})" if model_name else model_path
                _grid_search_job_update(
                    job_id,
                    current_model=progress_model,
                    processed=index - 1,
                    successful=successful,
                    failed=failed,
                )
                if _grid_search_job_cancel_requested(job_id):
                    finish_canceled(
                        processed=index - 1,
                        successful=successful,
                        failed=failed,
                        elapsed_seconds=max(0.0, time.time() - started_at),
                        top_models=top_models,
                        best_model=best_model,
                    )
                    return

                candidate_result = _fit_single_grid_candidate(
                    fit_source=normalized_source,
                    candidate=model_candidate,
                    observed=observed,
                    mode=mode,
                    fit_bounds=fit_bounds,
                    lambda_min=lambda_min,
                    lambda_max=lambda_max,
                    should_cancel=lambda: _grid_search_job_cancel_requested(job_id),
                )
                was_canceled = apply_candidate_result(candidate_result, processed=index)
                if was_canceled:
                    return
        else:
            _grid_search_job_update(
                job_id,
                current_model=f"Parallel fitting across {worker_count} workers ({fit_source_label}).",
                processed=0,
                successful=successful,
                failed=failed,
            )
            pool: object | None = None
            try:
                context = mp.get_context("spawn")
                pool = context.Pool(
                    processes=worker_count,
                    initializer=_grid_fit_worker_init,
                    initargs=(observed, mode, fit_bounds, lambda_min, lambda_max, normalized_source),
                )
                iterator = pool.imap_unordered(_grid_fit_worker_task, model_candidates, chunksize=1)
                processed = 0
                while processed < total:
                    if _grid_search_job_cancel_requested(job_id):
                        pool.terminate()
                        pool.join()
                        pool = None
                        finish_canceled(
                            processed=processed,
                            successful=successful,
                            failed=failed,
                            elapsed_seconds=max(0.0, time.time() - started_at),
                            top_models=top_models,
                            best_model=best_model,
                        )
                        return
                    try:
                        candidate_result = iterator.next(timeout=0.25)
                    except mp.TimeoutError:
                        continue
                    except StopIteration:
                        break
                    processed += 1
                    was_canceled = apply_candidate_result(candidate_result, processed=processed)
                    if was_canceled:
                        pool.terminate()
                        pool.join()
                        pool = None
                        return
                pool.close()
                pool.join()
                pool = None
            finally:
                if pool is not None:
                    pool.terminate()
                    pool.join()

        if _grid_search_job_cancel_requested(job_id):
            finish_canceled(
                processed=total,
                successful=successful,
                failed=failed,
                elapsed_seconds=max(0.0, time.time() - started_at),
                top_models=top_models,
                best_model=best_model,
            )
            return

        elapsed_seconds = max(0.0, time.time() - started_at)
        result_payload: dict[str, object] = {
            "fit_source": normalized_source,
            "fit_source_label": fit_source_label,
            "mode": mode,
            "upload_token": upload_token,
            "model_name_pattern": str(model_name_pattern or "").strip(),
            "fit_bounds": _fit_bounds_payload(fit_bounds),
            "fit_wavelength_range": _fit_wavelength_range_payload(fit_wavelength_range),
            "elapsed_seconds": elapsed_seconds,
            "best_model": best_model,
            "top_models": top_models,
        }
        tlusty_confidence = _summarize_tlusty_confidence_profiles(
            best_model=best_model,
            profiles=tlusty_confidence_profiles,
            mode=mode,
        )
        if tlusty_confidence:
            result_payload["tlusty_confidence"] = tlusty_confidence

        _grid_search_job_update(
            job_id,
            status="completed",
            processed=total,
            successful=successful,
            failed=failed,
            current_model="",
            best_so_far=copy.deepcopy(best_model) if best_model is not None else {},
            result=result_payload,
            finished_at=time.time(),
            error="",
        )
    except Exception as exc:
        _grid_search_job_update(
            job_id,
            status="failed",
            finished_at=time.time(),
            error=f"Grid search failed: {exc}",
        )

