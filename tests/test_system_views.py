from __future__ import annotations

import os
from pathlib import Path

from cmfgen_viewer.app import create_app
from cmfgen_viewer.cache_jobs import (
    CACHE_MAINTENANCE_JOBS,
    CACHE_MAINTENANCE_JOBS_LOCK,
    cache_maintenance_job_create,
    cache_maintenance_job_snapshot,
    run_cache_maintenance_job,
)
from cmfgen_viewer.summary_cache import (
    inspect_model_summary_cache,
    list_model_summary_namespaces,
    upsert_model_summary,
)


def _make_app(tmp_path: Path):
    base = tmp_path / "models"
    base.mkdir()
    app = create_app(basepath=str(base), upload_root=str(tmp_path / "uploads"), secret_key="test-secret")
    app.testing = True
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str((tmp_path / "summary.sqlite").resolve())
    return app


def _cache_entry(db_path: str, *, basepath: str, relpath: str, model_dir: Path) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    upsert_model_summary(
        db_path,
        basepath=basepath,
        relpath=relpath,
        model_dir=model_dir,
        model_name=model_dir.name,
        values=[model_dir.name],
        vadat_mtime=1.0,
        mod_sum_mtime=2.0,
    )


def test_system_page_lists_runtime_cache_namespaces_and_guarded_cleanup(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    config = app.config["CMFGEN_VIEWER"]
    basepath = str(config["basepath"])
    db_path = str(config["summary_cache_db"])
    old_base = str(tmp_path / "unavailable-archive")
    _cache_entry(db_path, basepath=basepath, relpath="current", model_dir=Path(basepath) / "current")
    _cache_entry(db_path, basepath=old_base, relpath="old", model_dir=tmp_path / "physical-old")

    response = client.get("/system/")
    assert response.status_code == 200
    assert b"Runtime Configuration" in response.data
    assert b"Upload Storage" in response.data
    assert b"Background Tasks" in response.data
    assert b"Model Summary Cache" in response.data
    assert b"Read-only mode is active" in response.data
    assert basepath.encode() in response.data
    assert old_base.encode() in response.data
    assert b"Remove Unavailable Bases" in response.data

    models_response = client.get("/models/")
    assert models_response.status_code == 200
    assert b'href="/system/#model-cache"' in models_response.data

    unknown = client.post("/system/cache/delete-base", data={"basepath": "/unknown"})
    assert unknown.status_code == 404

    cleanup = client.post("/system/cache/delete-unavailable")
    assert cleanup.status_code == 302
    assert [item["basepath"] for item in list_model_summary_namespaces(db_path)] == [basepath]

    clear_current = client.post("/system/cache/delete-base", data={"basepath": basepath})
    assert clear_current.status_code == 302
    assert list_model_summary_namespaces(db_path) == []


def test_system_page_reports_read_write_mode(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    app.config["CMFGEN_VIEWER"]["read_write_enabled"] = True

    response = app.test_client().get("/system/")

    assert response.status_code == 200
    assert b"Read-write mode is enabled" in response.data
    assert b"Model directory access" in response.data
    assert b"Read-write" in response.data


def test_cache_maintenance_refreshes_stale_entries(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    config = app.config["CMFGEN_VIEWER"]
    basepath = str(config["basepath"])
    db_path = str(config["summary_cache_db"])
    model = Path(basepath) / "stale"
    model.mkdir()
    (model / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
    (model / "MOD_SUM").write_text("summary\n", encoding="utf-8")
    _cache_entry(db_path, basepath=basepath, relpath="stale", model_dir=model)
    new_mtime = (model / "VADAT").stat().st_mtime + 10.0
    os.utime(model / "VADAT", (new_mtime, new_mtime))

    with CACHE_MAINTENANCE_JOBS_LOCK:
        CACHE_MAINTENANCE_JOBS.clear()
    try:
        job_id, existing = cache_maintenance_job_create(action="refresh_stale", basepath=basepath)
        assert existing is False
        run_cache_maintenance_job(job_id, summary_cache_db=db_path, basepath=basepath)
        snapshot = cache_maintenance_job_snapshot(job_id)
        assert snapshot is not None
        assert snapshot["status"] == "completed"
        assert snapshot["result"]["refreshed"] == 1
        assert snapshot["result"]["failed"] == 0
        assert inspect_model_summary_cache(db_path, basepath=basepath)["counts"]["valid"] == 1
    finally:
        with CACHE_MAINTENANCE_JOBS_LOCK:
            CACHE_MAINTENANCE_JOBS.clear()


def test_system_starts_cache_job_and_exposes_status(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    started: list[dict[str, object]] = []

    class DummyThread:
        def __init__(self, *, target, kwargs, daemon):
            started.append({"target": target, "kwargs": kwargs, "daemon": daemon})

        def start(self) -> None:
            return None

    monkeypatch.setattr("cmfgen_viewer.system_views.Thread", DummyThread)
    with CACHE_MAINTENANCE_JOBS_LOCK:
        CACHE_MAINTENANCE_JOBS.clear()
    try:
        invalid = client.post("/system/cache/maintain", data={"action": "invalid"})
        assert invalid.status_code == 400
        response = client.post("/system/cache/maintain", data={"action": "check"})
        assert response.status_code == 302
        assert len(started) == 1
        job_id = str(started[0]["kwargs"]["job_id"])

        status = client.get(f"/system/cache/job/{job_id}")
        assert status.status_code == 200
        assert status.get_json()["job"]["status"] == "running"
        assert status.headers["Cache-Control"] == "no-store"
        assert client.get("/system/cache/job/not-present").status_code == 404

        blocked_cleanup = client.post(
            "/system/cache/delete-base",
            data={"basepath": str(app.config["CMFGEN_VIEWER"]["basepath"])},
        )
        assert blocked_cleanup.status_code == 302
        assert "Wait+for+cache+maintenance" in blocked_cleanup.headers["Location"]
    finally:
        with CACHE_MAINTENANCE_JOBS_LOCK:
            CACHE_MAINTENANCE_JOBS.clear()
