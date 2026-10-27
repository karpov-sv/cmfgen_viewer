"""Independent runner owner; never imports Flask or relies on its lifetime."""
import os
from pathlib import Path
import signal
import sys
import time

from .workflow_permissions import open_readable
from . import model_activity
from .detached_jobs import read_json, write_json
from .runner import run_plan


def main(directory, descriptor):
    directory = Path(directory).resolve()
    request = read_json(directory / "request.json")
    model = Path(request["model"])
    info = os.fstat(descriptor)
    expected = (model / model_activity.RUN_LOCK_NAME).stat()
    if (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino):
        raise ValueError("Invalid runner reservation")
    model_activity._OWNED_RUN_MODEL = model.resolve()
    state = {"status": "starting", "stage": request["stages"][0], "progress": {}}

    def stop(*_):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        write_json(directory / "state.json", state)
        deadline = time.monotonic() + 15
        while not (directory / "start").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Launcher did not complete its handoff")
            time.sleep(0.05)
        if (directory / "cancel").exists():
            raise KeyboardInterrupt()
        state["status"] = "running"
        write_json(directory / "state.json", state)

        def emit(event):
            with open_readable(directory / "events.jsonl", "a") as stream:
                import json
                stream.write(json.dumps(event, allow_nan=False) + "\n")
            if event["event"] == "sequence_stage_preflight" and event.get('stage') == 'flux':
                state.pop('auto_attempt', None)
                state.pop('auto_phase', None)
                state['progress'] = {}
            if event["event"] == "auto_attempt":
                state.update(auto_attempt=event['attempt'], auto_phase=event['phase'], progress={})
            if event["event"] == "auto_action":
                state['auto_action'] = event['action']['reason']
            if event["event"] == "auto_performance_trial":
                state['auto_action'] = f"Performance trial {event['outcome']}: {event['reason']}"
            if event["event"] == "auto_decision":
                state['auto_reason'] = event['decision']['reason']
            if event["event"] == "progress":
                state["progress"] = {key: value for key, value in event.items()
                                     if key not in {"event", "run_id", "time"}}
            if event.get("stage"):
                state["stage"] = event["stage"]
            if event.get("run_id"):
                state["journal"] = str(model / ".cmfgen-runs" / event["run_id"])
            if event["event"] == "stage_started" and event.get("stage") in {"main", "test", "lte", "hydro", "flux-15", "flux-10", "flux-20", "continuum"}:
                state["native_log"] = str(model / ".cmfgen-runs" / event["run_id"] / event["stage"] / "process.log")
            if event.get("journal"):
                state["journal"] = event["journal"]
            write_json(directory / "state.json", state)

        result = run_plan(read_json(directory / "plan.json"), emit,
                          stop_requested=lambda: (directory / "stop-after-iteration").exists())
        write_json(directory / "result.json", result)
        state.update(status=result["status"], journal=result.get("journal"))
    except KeyboardInterrupt:
        state["status"] = "cancelled"
    except Exception as exc:
        state.update(status="runner_error", error=f"{type(exc).__name__}: {exc}")
    finally:
        write_json(directory / "state.json", state)
        os.close(descriptor)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
