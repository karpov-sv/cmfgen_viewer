"""Bulk summarization progress, failure isolation, cancellation, and reuse."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from cmfgen_viewer import summary_jobs
from cmfgen_viewer.cache_jobs import cache_maintenance_job_create
from cmfgen_viewer.job_store import JobStore
from cmfgen_viewer.summary_cache import list_model_summaries


def make_model(base, name):
    model = base / name
    model.mkdir(parents=True)
    (model / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
    (model / "MOD_SUM").write_text("Model summary\n", encoding="utf-8")
    return model


def start(store, base, paths, **kwargs):
    job, existing = summary_jobs.summary_job_create(store, basepath=str(base), path="", selected_paths=paths, **kwargs)
    assert not existing
    return job


def test_summary_worker_continues_after_data_errors_and_reports_progress(tmp_path, monkeypatch):
    base = tmp_path / "models"
    for name in ("first", "broken", "last"):
        make_model(base, name)
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    job = start(store, base, ["first", "broken", "missing", "../outside", "last"])
    original = summary_jobs.read_model
    seen = []

    def read(path):
        progress = store.snapshot(job, exclude=summary_jobs.SUMMARY_JOB_DETAILS)
        seen.append(progress["current_entry"])
        assert progress["status"] == "running"
        if path.name == "broken":
            raise ValueError("Bad model metadata")
        return original(path)

    monkeypatch.setattr(summary_jobs, "read_model", read)
    summary_jobs.run_summary_job(store, job, summary_cache_db=db)
    result = store.snapshot(job)
    assert seen == ["first", "broken", "last"]
    assert result["status"] == "completed"
    assert result["processed"] == 5
    assert (result["successful"], result["failed_count"], result["skipped_count"]) == (2, 1, 2)
    assert result["failures"] == [{"relpath": "broken", "stage": "read", "error": "Bad model metadata"}]
    assert summary_jobs.summary_job_retry_paths(result) == ["broken"]
    progress = summary_jobs.summary_job_progress(result)
    assert progress["status_label"] == "Completed with errors"
    assert progress["progress_percent"] == 100
    assert not any(key in progress for key in summary_jobs.SUMMARY_JOB_DETAILS)
    assert [row["path"] for row in list_model_summaries(db, basepath=str(base))] == ["first", "last"]


def test_cancel_after_current_model_preserves_saved_results(tmp_path, monkeypatch):
    for name in ("first", "second"):
        make_model(tmp_path, name)
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    job = start(store, tmp_path, ["first", "second"])
    original = summary_jobs.read_model

    def read(path):
        store.request_cancel(job)
        return original(path)

    monkeypatch.setattr(summary_jobs, "read_model", read)
    summary_jobs.run_summary_job(store, job, summary_cache_db=db)
    snapshot = store.snapshot(job)
    assert snapshot["status"] == "canceled"
    assert snapshot["processed"] == snapshot["successful"] == 1
    assert snapshot["rows"][0]["path"] == "first"
    assert summary_jobs.summary_job_retry_paths(snapshot) == ["second"]
    assert len(list_model_summaries(db, basepath=str(tmp_path))) == 1


def test_cancel_before_work_does_not_open_database(tmp_path, monkeypatch):
    store = JobStore(max_jobs=16)
    job = start(store, tmp_path, ["first"])
    store.request_cancel(job)

    def unexpected(*args):
        raise AssertionError("Canceled job should not access SQLite")

    monkeypatch.setattr(summary_jobs, "_connect", unexpected)
    summary_jobs.run_summary_job(store, job, summary_cache_db="unused")
    assert store.snapshot(job)["status"] == "canceled"
    assert store.snapshot(job)["processed"] == 0


def test_database_failure_stops_job_and_keeps_previously_committed_rows(tmp_path, monkeypatch):
    for name in ("first", "second", "third"):
        make_model(tmp_path, name)
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    job = start(store, tmp_path, ["first", "second", "third"])
    original = summary_jobs._upsert_model_summary

    def write(connection, **kwargs):
        if kwargs["relpath"] == "second":
            raise sqlite3.OperationalError("disk full")
        original(connection, **kwargs)

    monkeypatch.setattr(summary_jobs, "_upsert_model_summary", write)
    summary_jobs.run_summary_job(store, job, summary_cache_db=db)
    snapshot = store.snapshot(job)
    assert snapshot["status"] == "failed"
    assert snapshot["processed"] == 2
    assert snapshot["successful"] == snapshot["failed_count"] == 1
    assert snapshot["failures"][0]["stage"] == "cache-write"
    assert "disk full" in snapshot["error"]
    assert summary_jobs.summary_job_retry_paths(snapshot) == ["second", "third"]
    assert [row["path"] for row in list_model_summaries(db, basepath=str(tmp_path))] == ["first"]


def test_database_open_failure_keeps_all_paths_retryable(tmp_path):
    store = JobStore(max_jobs=16)
    job = start(store, tmp_path, ["first", "second"])
    summary_jobs.run_summary_job(store, job, summary_cache_db=str(tmp_path / "missing" / "db.sqlite"))
    snapshot = store.snapshot(job)
    assert snapshot["status"] == "failed"
    assert snapshot["processed"] == 0
    assert summary_jobs.summary_job_retry_paths(snapshot) == ["first", "second"]


def test_unchanged_summaries_are_reused_and_force_refresh_reads_models(tmp_path, monkeypatch):
    make_model(tmp_path, "first")
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    job = start(store, tmp_path, ["first"])
    summary_jobs.run_summary_job(store, job, summary_cache_db=db)
    before = list_model_summaries(db, basepath=str(tmp_path))[0]["summarized_at"]
    original = summary_jobs.read_model
    reads = []

    def tracked(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(summary_jobs, "read_model", tracked)
    reused = start(store, tmp_path, ["first"])
    summary_jobs.run_summary_job(store, reused, summary_cache_db=db)
    assert not reads
    assert store.snapshot(reused)["reused"] == 1
    assert store.snapshot(reused)["updated"] == 0
    assert list_model_summaries(db, basepath=str(tmp_path))[0]["summarized_at"] == before
    refreshed = start(store, tmp_path, ["first"], force_refresh=True)
    summary_jobs.run_summary_job(store, refreshed, summary_cache_db=db)
    assert len(reads) == 1
    assert store.snapshot(refreshed)["updated"] == 1
    assert store.snapshot(refreshed)["reused"] == 0


def test_invalid_cached_payload_is_rebuilt(tmp_path):
    make_model(tmp_path, "first")
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    first = start(store, tmp_path, ["first"])
    summary_jobs.run_summary_job(store, first, summary_cache_db=db)
    with sqlite3.connect(db) as connection:
        connection.execute("UPDATE model_summary_cache SET summary_json = 'not-json'")
    rebuilt = start(store, tmp_path, ["first"])
    summary_jobs.run_summary_job(store, rebuilt, summary_cache_db=db)
    assert store.snapshot(rebuilt)["updated"] == 1
    assert len(list_model_summaries(db, basepath=str(tmp_path))) == 1


def test_model_changed_during_read_is_failed_without_caching(tmp_path, monkeypatch):
    model = make_model(tmp_path, "first")
    store, db = JobStore(max_jobs=16), str(tmp_path / "summary.sqlite")
    job = start(store, tmp_path, ["first"])
    original = summary_jobs.read_model

    def read(path):
        result = original(path)
        (model / "VADAT").write_text("12345 [LSTAR]\n", encoding="utf-8")
        return result

    monkeypatch.setattr(summary_jobs, "read_model", read)
    summary_jobs.run_summary_job(store, job, summary_cache_db=db)
    assert store.snapshot(job)["failed_count"] == 1
    assert "changed while reading" in store.snapshot(job)["failures"][0]["error"]
    assert list_model_summaries(db, basepath=str(tmp_path)) == []


def test_bulk_summary_and_cache_maintenance_creation_are_mutually_exclusive(tmp_path):
    store = JobStore(max_jobs=16)

    def create(i):
        if i % 2:
            return cache_maintenance_job_create(store, action="check", basepath=str(tmp_path))
        return summary_jobs.summary_job_create(store, basepath=str(tmp_path), path="", selected_paths=["first"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        jobs = list(executor.map(create, range(24)))
    assert len({job for job, _ in jobs}) == 1
    assert sum(not existing for _, existing in jobs) == 1


def test_one_sqlite_connection_is_reused_for_the_whole_job(tmp_path, monkeypatch):
    for name in ("first", "second", "third"):
        make_model(tmp_path, name)
    store = JobStore(max_jobs=16)
    job = start(store, tmp_path, ["first", "second", "third"])
    connections = []
    original = summary_jobs._connect

    def connect(db):
        connections.append(db)
        return original(db)

    monkeypatch.setattr(summary_jobs, "_connect", connect)
    summary_jobs.run_summary_job(store, job, summary_cache_db=str(tmp_path / "db.sqlite"))
    assert len(connections) == 1
    assert store.snapshot(job)["successful"] == 3
