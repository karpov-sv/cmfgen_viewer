from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.app import create_app
from cmfgen_viewer.observed_spectrum import write_upload_manifest
from cmfgen_viewer.view_common import GRID_SEARCH_JOBS, GRID_SEARCH_JOBS_LOCK


def _make_app(tmp_path: Path):
    app = create_app(basepath=str(tmp_path), secret_key="test-secret")
    app.testing = True
    config = app.config["CMFGEN_VIEWER"]
    config["upload_root"] = str((tmp_path / "uploads").resolve())
    config["summary_cache_db"] = str((tmp_path / "summary.sqlite").resolve())
    return app


def test_background_task_status_and_global_navigation(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])
    upload_token = "TaskToken_123"
    write_upload_manifest(
        upload_root,
        upload_token,
        {
            "token": upload_token,
            "filename": "observed-spectrum.fits",
            "stored_name": "source.fits",
            "created_at": 1.0,
        },
    )
    (upload_root / upload_token / "source.fits").write_bytes(b"placeholder")

    with GRID_SEARCH_JOBS_LOCK:
        GRID_SEARCH_JOBS.clear()

    try:
        empty_response = client.get("/tasks/status")
        assert empty_response.status_code == 200
        assert empty_response.get_json() == {"ok": True, "running_count": 0, "tasks": []}
        assert empty_response.headers["Cache-Control"] == "no-store"

        with GRID_SEARCH_JOBS_LOCK:
            GRID_SEARCH_JOBS["running-job"] = {
                "status": "running",
                "upload_token": upload_token,
                "fit_source": "tlusty",
                "processed": 5,
                "total": 20,
                "current_model": "BSTAR2006/BG25000g400v2",
                "created_at": 20.0,
                "cancel_requested": False,
            }
            GRID_SEARCH_JOBS["completed-job"] = {
                "status": "completed",
                "upload_token": upload_token,
                "fit_source": "cmfgen",
                "processed": 10,
                "total": 10,
                "created_at": 10.0,
                "finished_at": 11.0,
            }

        response = client.get("/tasks/status")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["running_count"] == 1
        assert len(payload["tasks"]) == 1
        task = payload["tasks"][0]
        assert task["id"] == "running-job"
        assert task["title"] == "TLUSTY Grid fit"
        assert task["target"] == "observed-spectrum.fits"
        assert task["progress_percent"] == 25.0
        assert task["progress_label"] == "5/20 models"
        assert task["current_model"] == "BSTAR2006/BG25000g400v2"
        assert task["href"] == f"/uploads/view/{upload_token}#grid-fit"

        uploads_page = client.get("/uploads/")
        assert uploads_page.status_code == 200
        assert b'id="background-task-nav"' in uploads_page.data
        assert b'data-status-url="/tasks/status"' in uploads_page.data
        assert b'background_tasks.js' in uploads_page.data
    finally:
        with GRID_SEARCH_JOBS_LOCK:
            GRID_SEARCH_JOBS.clear()
