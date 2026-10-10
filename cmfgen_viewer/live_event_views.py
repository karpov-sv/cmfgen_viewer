"""One server-sent event stream for task navigation and model runtime status."""

import json
import time

from flask import Response, abort, current_app, request, stream_with_context

from .model_runtime import inspect_workflow_runtime
from .model_runtime_views import resolve_runtime_target
from .task_views import background_tasks_payload
from .view_common import bp


def event_frame(event: str, payload: object) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, allow_nan=False)}\n\n"


@bp.route("/tasks/events")
def live_events():
    # Validate subscriptions before streaming so permissions/path errors retain
    # their normal HTTP status. Runtime access uses the same rules as the JSON API.
    keys = list(dict.fromkeys(request.args.getlist("runtime")))
    if len(keys) > 3:
        abort(400)
    targets = []
    for key in keys:
        kind, separator, path = key.partition(":")
        if not separator or not path:
            abort(400)
        targets.append((key, kind, resolve_runtime_target(kind, path)))
    signal = current_app.extensions["cmfgen_changes"]

    @stream_with_context
    def generate():
        version = signal.version
        last_tasks = None
        last_runtime = {}
        next_runtime = 0.0
        next_tasks = 0.0
        heartbeat = time.monotonic() + 15.0
        first = True
        while True:
            now = time.monotonic()
            if first or (signal.version != version and now >= next_tasks):
                # Read the version before snapshots: a concurrent write remains
                # visible as a subsequent notification instead of being lost.
                version = signal.version
                tasks = background_tasks_payload()
                if tasks != last_tasks:
                    yield event_frame("tasks", tasks)
                    last_tasks = tasks
                next_tasks = now + 1.0
            if targets and now >= next_runtime:
                for key, kind, target in targets:
                    try:
                        runtime = inspect_workflow_runtime(target, kind)
                    except OSError:
                        last_runtime.pop(key, None)
                        yield event_frame("runtime-error", {"key": key})
                        continue
                    # The check timestamp alone is not a status change.
                    comparable = {k: v for k, v in runtime.items() if k != "checked_at"}
                    if comparable != last_runtime.get(key):
                        yield event_frame("runtime", {"key": key, "runtime": runtime})
                        last_runtime[key] = comparable
                next_runtime = now + 5.0
            first = False
            now = time.monotonic()
            if now >= heartbeat:
                yield ": keepalive\n\n"
                heartbeat = now + 15.0
            deadline = min(heartbeat, next_runtime) if targets else heartbeat
            if signal.version != version:
                # Coalesce rapid progress writes into at most one task update/s.
                time.sleep(max(0.0, min(deadline, next_tasks) - now))
            else:
                signal.wait(version, max(0.0, deadline - now))

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache, no-store",
        "X-Accel-Buffering": "no",
    })
