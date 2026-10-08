"""Short POSTs and stable summary pages, including failure/cancel/retry flows."""

from pathlib import Path
from threading import Event, Thread

import pytest

from cmfgen_viewer import summary_jobs
from cmfgen_viewer.app import create_app
from cmfgen_viewer.summary_cache import list_model_summaries


@pytest.fixture
def setup(tmp_path, monkeypatch):
    base = tmp_path / "models"
    base.mkdir()
    for name in ("model_a", "model_b", "model_c"):
        model = base / name
        model.mkdir()
        (model / "VADAT").write_text("1 [LSTAR]\n", encoding="utf-8")
        (model / "MOD_SUM").write_text("summary\n", encoding="utf-8")
    app = create_app(basepath=str(base), upload_root=str(tmp_path / "uploads"), secret_key="test")
    app.testing = True
    db = str(tmp_path / "summary.sqlite")
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = db
    threads = []

    class DeferredThread:
        def __init__(self, *, target, kwargs, daemon):
            assert daemon
            self.target, self.kwargs = target, kwargs
            threads.append(self)

        def start(self):
            pass

        def run(self):
            self.target(**self.kwargs)

    monkeypatch.setattr("cmfgen_viewer.model_views.Thread", DeferredThread)
    return app, app.test_client(), threads, db


def post(client, paths):
    response = client.post("/bulk/summarize/", data={"selected_models": paths})
    assert response.status_code == 303
    return response.headers["Location"]


def test_post_starts_once_redirects_immediately_and_get_restores_results(setup):
    app, client, threads, db = setup
    url = post(client, ["model_a", "model_b"])
    assert len(threads) == 1
    assert not Path(db).exists()  # The POST performs no model/SQLite work.
    initial = client.get(url)
    assert initial.status_code == 200
    assert b"summary_job.js" in initial.data
    assert b"0/2 folders" in initial.data
    duplicate = post(client, ["model_b", "model_a"])
    assert duplicate == url
    assert len(threads) == 1
    different = post(client, ["model_c"])
    assert "notice=" in different
    assert len(threads) == 1
    task = client.get("/tasks/status").get_json()["tasks"][0]
    assert task["kind"] == "bulk-summary"
    assert task["href"] == url
    status = client.get(url + "/status")
    assert status.headers["Cache-Control"] == "no-store"
    payload = status.get_json()["job"]
    assert all(key not in payload for key in summary_jobs.SUMMARY_JOB_DETAILS)
    threads[0].run()
    finished = client.get(url)
    assert b"2/2 folders" in finished.data
    assert b"summary_table.js" in finished.data
    assert b"summary-scatter-plot" in finished.data
    assert b"summary_job.js" not in finished.data
    assert b"model_a" in finished.data and b"model_b" in finished.data
    assert client.get("/tasks/status").get_json()["running_count"] == 0
    history = client.get("/models/")
    assert b"Recent bulk summary jobs (1)" in history.data
    assert url.encode() in history.data
    assert len(list_model_summaries(db, basepath=app.config["CMFGEN_VIEWER"]["basepath"])) == 2


def test_failure_details_escape_html_and_retry_only_failed_models(setup, monkeypatch):
    app, client, threads, db = setup
    original = summary_jobs.read_model

    def read(path):
        if path.name == "model_b":
            raise ValueError("<script>bad metadata</script>")
        return original(path)

    monkeypatch.setattr(summary_jobs, "read_model", read)
    url = post(client, ["model_a", "model_b"])
    threads[0].run()
    page = client.get(url)
    assert b"Completed with errors" in page.data
    assert b"&lt;script&gt;bad metadata&lt;/script&gt;" in page.data
    assert b"Retry failed folders (1)" in page.data
    monkeypatch.setattr(summary_jobs, "read_model", original)
    retry = client.post(url + "/retry")
    assert retry.status_code == 303
    job_id = threads[1].kwargs["job_id"]
    snapshot = app.extensions["cmfgen_jobs"]["cache"].snapshot(job_id)
    assert snapshot["selected_paths"] == ["model_b"]
    assert snapshot["parent_job_id"] == threads[0].kwargs["job_id"]
    threads[1].run()
    assert b"Previous attempt and results" in client.get(retry.headers["Location"]).data
    assert len(list_model_summaries(db, basepath=app.config["CMFGEN_VIEWER"]["basepath"])) == 2


def test_cancel_before_start_and_retry_unfinished_selection(setup):
    app, client, threads, db = setup
    url = post(client, ["model_a", "model_b"])
    assert client.post(url + "/retry").status_code == 409
    response = client.post(url + "/cancel")
    assert response.status_code == 303
    assert client.get(url + "/status").get_json()["job"]["status_label"] == "Stopping"
    threads[0].run()
    assert b"Canceled" in client.get(url).data
    assert not Path(db).exists()
    assert client.post(url + "/retry").status_code == 303
    snapshot = app.extensions["cmfgen_jobs"]["cache"].snapshot(threads[1].kwargs["job_id"])
    assert snapshot["selected_paths"] == ["model_a", "model_b"]


def test_summary_and_maintenance_block_each_other_and_guard_cleanup(setup, monkeypatch):
    app, client, threads, db = setup
    url = post(client, ["model_a"])
    for endpoint in ("delete-base", "delete-unavailable", "delete-noncurrent"):
        response = client.post("/system/cache/" + endpoint, data={"basepath": app.config["CMFGEN_VIEWER"]["basepath"]})
        assert response.status_code == 302
        assert "Wait+for" in response.headers["Location"]
    maintenance = client.post("/system/cache/maintain", data={"action": "check"})
    assert maintenance.status_code == 303
    assert url in maintenance.headers["Location"]
    assert b"Bulk summarization: 1" in client.get("/system/").data
    assert client.get("/system/?job=" + threads[0].kwargs["job_id"]).headers["Location"] == url
    threads[0].run()
    monkeypatch.setattr("cmfgen_viewer.system_views.Thread", type(threads[0]))
    assert client.post("/system/cache/maintain", data={"action": "check"}).status_code == 302
    blocked = client.post("/bulk/summarize/", data={"selected_models": ["model_b"]})
    assert blocked.status_code == 303
    assert "/system/" in blocked.headers["Location"]
    assert len(threads) == 2


def test_force_refresh_checkbox_and_worker_start_failure_are_visible(setup, monkeypatch):
    app, client, threads, db = setup
    assert b'name="force_refresh"' in client.get("/view/").data

    class BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("worker unavailable")

    monkeypatch.setattr("cmfgen_viewer.model_views.Thread", BrokenThread)
    response = client.post("/bulk/summarize/", data={"selected_models": ["model_a"], "force_refresh": "1"})
    assert response.status_code == 303
    page = client.get(response.headers["Location"])
    assert b"worker unavailable" in page.data
    assert b"Retry failed and unfinished folders (1)" in page.data
    snapshot = app.extensions["cmfgen_jobs"]["cache"].latest()
    assert snapshot["status"] == "failed" and snapshot["force_refresh"] is True


def test_missing_jobs_and_changed_base_do_not_expose_old_selection(setup):
    app, client, threads, db = setup
    for suffix in ("", "/status"):
        assert client.get("/bulk/summary/missing" + suffix).status_code == 404
    for suffix in ("/cancel", "/retry"):
        assert client.post("/bulk/summary/missing" + suffix).status_code == 404
    assert client.post("/bulk/summarize/", data={}).status_code == 302
    assert client.post("/bulk/summarize/model_a", data={"selected_models": ["model_a"]}).status_code == 400
    url = post(client, ["model_a"])
    app.config["CMFGEN_VIEWER"]["basepath"] = "/other-model-base"
    assert client.get(url).status_code == 404
    assert client.get(url + "/status").status_code == 404


def test_real_worker_is_independent_of_request_and_cancel_preserves_current_model(setup, monkeypatch):
    app, client, deferred, db = setup
    ready, release = Event(), Event()
    workers = []
    original = summary_jobs.read_model

    class RealThread(Thread):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            workers.append(self)

    def read(path):
        ready.set()
        assert release.wait(5)
        return original(path)

    monkeypatch.setattr("cmfgen_viewer.model_views.Thread", RealThread)
    monkeypatch.setattr(summary_jobs, "read_model", read)
    try:
        url = post(client, ["model_a", "model_b"])
        assert ready.wait(5)
        progress = client.get(url + "/status").get_json()["job"]
        assert progress["status"] == "running"
        assert progress["current_entry"] == "model_a"
        assert progress["processed"] == 0
        assert client.post(url + "/cancel").status_code == 303
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=5)
            assert not worker.is_alive()
    final = client.get(url + "/status").get_json()["job"]
    assert final["status"] == "canceled"
    assert final["successful"] == final["processed"] == 1
    assert b"model_a" in client.get(url).data


def test_job_results_remain_accessible_if_the_source_folder_disappears(setup):
    app, client, threads, db = setup
    base = Path(app.config["CMFGEN_VIEWER"]["basepath"])
    folder = base / "grid"
    folder.mkdir()
    response = client.post("/bulk/summarize/grid", data={"selected_models": ["grid/missing"]})
    url = response.headers["Location"]
    threads[0].run()
    folder.rmdir()  # Empty test fixture only.
    assert client.get(url).status_code == 200
    assert b"Skipped folders" in client.get(url).data


def test_failed_cache_maintenance_start_does_not_leave_summary_slot_blocked(setup, monkeypatch):
    app, client, threads, db = setup

    class BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("no worker")

    monkeypatch.setattr("cmfgen_viewer.system_views.Thread", BrokenThread)
    response = client.post("/system/cache/maintain", data={"action": "check"})
    assert response.status_code == 302
    assert app.extensions["cmfgen_jobs"]["cache"].latest()["status"] == "failed"
    post(client, ["model_a"])
    assert len(threads) == 1


def test_expired_job_is_reported_but_successful_summary_stays_in_database(setup):
    app, client, threads, db = setup
    url = post(client, ["model_a"])
    threads[0].run()
    store = app.extensions["cmfgen_jobs"]["cache"]
    store.update(threads[0].kwargs["job_id"], finished_at=1.)
    response = client.get(url + "/status")
    assert response.status_code == 404
    assert "expired" in response.get_json()["error"]
    assert len(list_model_summaries(db, basepath=app.config["CMFGEN_VIEWER"]["basepath"])) == 1
