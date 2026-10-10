"""Server-pushed snapshots preserve job and external runtime lifecycle state."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.live_events import ChangeSignal
from cmfgen_viewer.job_store import JobStore
from cmfgen_viewer.model_runtime import inspect_workflow_runtime


@pytest.fixture
def app(tmp_path, monkeypatch):
    model = tmp_path / "model_a"
    model.mkdir()
    (model / "MODEL_SPEC").write_text("2 [ND]\n")
    (model / "VADAT").write_text("1 [RSTAR]\n")
    (model / "lte").mkdir()
    app = create_app(basepath=str(tmp_path), read_write_enabled=True,
                     upload_root=str(tmp_path / "uploads"))
    app.testing = True
    clock = [0.0]

    def advance(seconds):
        clock[0] += seconds

    # Exercise stream scheduling without real five-second waits.
    monkeypatch.setattr("cmfgen_viewer.live_event_views.time", SimpleNamespace(
        monotonic=lambda: clock[0], sleep=advance))
    signal = app.extensions["cmfgen_changes"]
    monkeypatch.setattr(signal, "wait", lambda version, timeout: advance(timeout))
    return app


def frame(response):
    text = next(response.response).decode()
    event, data = text.strip().split("\n", 1)
    return event.removeprefix("event: "), json.loads(data.removeprefix("data: "))


def test_tasks_stream_reports_start_progress_cancel_finish_and_reload(app):
    client = app.test_client()
    response = client.get("/tasks/events", buffered=False)
    assert response.mimetype == "text/event-stream"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert frame(response) == ("tasks", {"ok": True, "tasks": [], "running_count": 0})
    store = app.extensions["cmfgen_jobs"]["grid"]
    store.insert({"job_id": "fit", "status": "running", "total": 10, "processed": 0})
    assert frame(response)[1]["running_count"] == 1
    store.update("fit", processed=5)
    assert frame(response)[1]["tasks"][0]["progress_percent"] == 50
    store.request_cancel("fit")
    assert frame(response)[1]["tasks"][0]["status_label"] == "Stopping"
    response.close()
    reloaded = client.get("/tasks/events", buffered=False)
    assert frame(reloaded)[1]["running_count"] == 1
    store.update("fit", status="completed")
    assert frame(reloaded)[1]["running_count"] == 0
    reloaded.close()


def test_runtime_stream_detects_external_start_progress_phase_and_completion(app, monkeypatch):
    state = {"kind": "main", "active": False, "phase": "main", "progress": None,
             "diagnostics": [], "checked_at": "00:00:00"}
    monkeypatch.setattr("cmfgen_viewer.live_event_views.inspect_workflow_runtime",
                        lambda target, kind: dict(state))
    response = app.test_client().get("/tasks/events?runtime=main:model_a", buffered=False)
    assert frame(response)[0] == "tasks"
    assert frame(response)[1]["runtime"]["active"] is False
    state.update(active=True, progress={"percent": 10})
    assert frame(response)[1]["runtime"]["progress"]["percent"] == 10
    state.update(phase="flux", progress={"percent": 50})
    assert frame(response)[1]["runtime"]["phase"] == "flux"
    state.update(active=False, diagnostics=[{"status": "succeeded"}])
    finished = frame(response)[1]
    assert finished["key"] == "main:model_a"
    assert finished["runtime"]["active"] is False
    assert finished["runtime"]["diagnostics"][0]["status"] == "succeeded"
    response.close()


def test_runtime_stream_uses_output_progress_and_final_diagnostics(app, monkeypatch):
    model = Path(app.config["CMFGEN_VIEWER"]["basepath"]) / "model_a"
    (model / "IN_ITS").write_text("10 [NUM_ITS]\n")
    active = [False]
    monkeypatch.setattr("cmfgen_viewer.model_runtime.find_workflow_processes",
                        lambda target, kind, **kw: [{"pid": 123, "start_epoch": 1}]
                        if active[0] and kind == "main" else [])
    monkeypatch.setattr("cmfgen_viewer.live_event_views.inspect_workflow_runtime",
                        inspect_workflow_runtime)
    response = app.test_client().get("/tasks/events?runtime=main:model_a", buffered=False)
    frame(response)
    assert frame(response)[1]["runtime"]["active"] is False
    active[0] = True
    (model / "OUTGEN").write_text(
        "Model started on: now\nCurrent great iteration count is 1\nCurrent great iteration count is 2\n")
    runtime = frame(response)[1]["runtime"]
    assert runtime["active"] is True
    assert runtime["progress"]["percent"] == 20
    (model / "OUTGEN").write_text(
        "Model started on: now\n" + "".join(
            f"Current great iteration count is {index}\n" for index in range(1, 9))
        + "Program finished on: now\n")
    (model / "MOD_SUM").write_text("Model Finalized on: 09-Aug-2026 01:00:00\n")
    (model / "RVTJ").write_text("restart\n")
    active[0] = False
    runtime = frame(response)[1]["runtime"]
    assert runtime["active"] is False
    assert runtime["recorded_progress"][0]["progress"]["percent"] == 80
    assert runtime["diagnostics"][0]["status"] == "succeeded"
    response.close()


def test_runtime_stream_suppresses_timestamp_only_updates_and_supports_both_lte_panels(app, monkeypatch):
    calls = []

    def inspect(target, kind):
        calls.append(kind)
        return {"kind": kind, "active": False, "checked_at": str(len(calls))}

    monkeypatch.setattr("cmfgen_viewer.live_event_views.inspect_workflow_runtime", inspect)
    response = app.test_client().get(
        "/tasks/events?runtime=lte:model_a&runtime=hydro:model_a", buffered=False)
    assert frame(response)[0] == "tasks"
    assert frame(response)[1]["key"] == "lte:model_a"
    assert frame(response)[1]["key"] == "hydro:model_a"
    assert next(response.response) == b": keepalive\n\n"
    assert len(calls) >= 6
    response.close()


@pytest.mark.parametrize("subscription, code", [
    ("invalid", 400), ("flux:model_a", 404), ("main:missing", 404),
    ("main:../escape", 404),
])
def test_stream_validates_runtime_paths_before_starting(app, subscription, code):
    assert app.test_client().get("/tasks/events", query_string={"runtime": subscription}).status_code == code


def test_read_only_stream_cannot_access_runtime(tmp_path):
    client = create_app(basepath=str(tmp_path)).test_client()
    assert client.get("/tasks/events?runtime=main:model_a").status_code == 403


def test_stream_requires_configured_authentication(tmp_path):
    app = create_app(basepath=str(tmp_path), auth_username="viewer", auth_password="secret")
    assert app.test_client().get("/tasks/events").status_code == 401


def test_runtime_stream_recovers_after_inspection_error(app, monkeypatch):
    broken = [False]

    def inspect(target, kind):
        if broken[0]:
            raise OSError("Temporarily unreadable")
        return {"kind": kind, "active": False}

    monkeypatch.setattr("cmfgen_viewer.live_event_views.inspect_workflow_runtime", inspect)
    response = app.test_client().get("/tasks/events?runtime=main:model_a", buffered=False)
    frame(response)
    assert frame(response)[0] == "runtime"
    broken[0] = True
    assert frame(response)[0] == "runtime-error"
    broken[0] = False
    assert frame(response)[0] == "runtime"
    response.close()


def test_job_store_notifies_for_append_and_ignores_missing_jobs():
    signal = ChangeSignal()
    store = JobStore(max_jobs=3, on_change=signal.notify)
    version = signal.version
    store.insert({"job_id": "summary", "status": "running", "rows": []})
    assert signal.wait(version, 0) > version
    version = signal.version
    store.append("summary", "rows", {"model": "a"}, processed=1)
    assert signal.version > version
    version = signal.version
    store.update("missing", status="completed")
    assert signal.version == version
