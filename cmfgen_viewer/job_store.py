"""Thread-safe in-memory job lifecycle, owned by one application instance."""

from __future__ import annotations

import copy
import time
from contextlib import contextmanager
from threading import RLock
from typing import Callable


class JobStore:
    def __init__(
        self, *, max_jobs: int, ttl_seconds: float = 6 * 60 * 60,
        on_change: Callable[[], None] | None = None,
    ):
        self._on_change = on_change or (lambda: None)
        self.max_jobs = max_jobs
        self.ttl_seconds = ttl_seconds
        self._lock = RLock()
        self._jobs: dict[str, dict[str, object]] = {}

    def _prune(self, now: float) -> None:
        finished = sorted(
            (float(job.get("finished_at") or job.get("created_at") or 0), job_id)
            for job_id, job in self._jobs.items()
            if job.get("status") != "running"
        )
        for finished_at, job_id in finished:
            if (finished_at > 0 and now - finished_at > self.ttl_seconds) or len(
                self._jobs
            ) > self.max_jobs:
                self._jobs.pop(job_id, None)

    def insert(
        self, payload: dict[str, object], *, singleton: bool = False
    ) -> tuple[str, bool]:
        with self._lock:
            self._prune(time.time())
            if singleton:
                running = self.latest(status="running")
                if running is not None:
                    return str(running["job_id"]), True
            job_id = str(payload["job_id"])
            self._jobs[job_id] = copy.deepcopy(payload)
            self._prune(time.time())
            self._on_change()
            return job_id, False

    def update(self, job_id: str, **fields: object) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.update(copy.deepcopy(fields))
            self._on_change()
            return True

    @contextmanager
    def exclusive(self):
        """Coordinate short foreground operations with atomic job creation."""
        with self._lock:
            yield

    def append(self, job_id: str, field: str, item: object, **fields: object) -> bool:
        """Append one result without copying an ever-growing result collection."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job[field].append(copy.deepcopy(item))
            job.update(copy.deepcopy(fields))
            self._on_change()
            return True

    def snapshot(self, job_id: str, *, exclude: tuple[str, ...] = ()) -> dict[str, object] | None:
        with self._lock:
            self._prune(time.time())
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return copy.deepcopy({key: value for key, value in job.items() if key not in exclude})

    def snapshots(self, *, exclude: tuple[str, ...] = (), **filters: object) -> list[dict[str, object]]:
        with self._lock:
            self._prune(time.time())
            snapshots = [
                copy.deepcopy({key: value for key, value in job.items() if key not in exclude})
                for job in self._jobs.values()
                if all(job.get(key) == value for key, value in filters.items())
            ]
        return sorted(
            snapshots, key=lambda job: float(job.get("created_at") or 0), reverse=True
        )

    def latest(self, **filters: object) -> dict[str, object] | None:
        snapshots = self.snapshots(**filters)
        return snapshots[0] if snapshots else None

    def request_cancel(self, job_id: str) -> dict[str, object] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.get("status") == "running":
                job.update(cancel_requested=True, cancel_requested_at=time.time())
                self._on_change()
            return copy.deepcopy(job)

    def cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            return bool(self._jobs.get(job_id, {}).get("cancel_requested", False))
