"""Persistent launch records for independently running CMFGEN workers."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid

import psutil

from .workflow_permissions import make_readable, mkdir_readable, open_readable
from .model_activity import model_mutation_guard, RUN_LOCK_NAME, fcntl
from .runner_recipe import RunnerError

JOB_DIR = ".cmfgen-runner-jobs"
ACTIVE = {"starting", "running", "stopping", "unknown", "orphaned"}
STATUS_LABELS = {"starting": "Starting", "running": "Running", "stopping": "Stopping",
    "unknown": "Monitoring unavailable", "orphaned": "Native process still active",
    "interrupted": "Interrupted", "tested": "Startup tested", "succeeded": "Succeeded",
    "cancelled": "Cancelled", "runner_error": "Runner failed", "failed": "Execution failed",
    "invalid_output": "Output validation failed", "preflight_failed": "Preflight blocked", "timeout": "Timed out"}
STAGE_LABELS = {"prepare-lte": "Prepare LTE", "lte": "LTE", "hydro": "Hydro",
    "promote-hydro": "Promote hydro", "main": "Main computation", "flux": "Spectra",
    "cleanup": "Cleanup", "test": "Startup test", "sequence": "Stage sequence",
    "flux-15": "Spectra (15 km/s)", "flux-10": "Spectra (10 km/s)",
    "flux-20": "Spectra (20 km/s)", "continuum": "Continuum"}


def timestamp_label(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError):
        return value or "—"
STATUS_CLASSES = {status: css for statuses, css in [
    (('succeeded', 'tested', 'running'), 'bg-success'),
    (('failed', 'runner_error', 'invalid_output', 'preflight_failed', 'timeout'), 'bg-danger'),
    (('starting', 'stopping', 'unknown', 'orphaned'), 'bg-warning text-dark'),
] for status in statuses}
_CHILDREN = {}
_CHILDREN_LOCK = threading.Lock()


def write_json(path, data):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with open_readable(temporary, "x") as stream:
            json.dump(data, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    if path.is_symlink():
        raise RunnerError("Refusing symlinked job metadata")
    return json.loads(path.read_text())


def job_directory(base, job_id):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise RunnerError("Unknown runner job")
    root = Path(base).resolve() / JOB_DIR
    directory = root / job_id
    if root.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise RunnerError("Unknown runner job")
    return directory


def fingerprint(plan):
    initial = plan.get("initial_plan", plan)
    evidence = {key: initial.get(key) for key in ("inputs", "executable_snapshot", "copies", "entries", "hydro_alignment", "lte_composition_alignment")}
    evidence["options"] = plan.get("stage_options")
    evidence["passes"] = initial.get("passes")
    evidence["initialization"] = initial.get("initialization")
    evidence["configuration"] = plan.get("configuration_sources")
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest()


def _worker_process(directory, identity):
    try:
        process = psutil.Process(identity["pid"])
        if abs(process.create_time() - identity["create_time"]) > 0.001:
            return None
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        args = process.cmdline()
        if "cmfgen_viewer.detached_worker" not in args or str(directory) not in args:
            return None
        return process
    except (psutil.NoSuchProcess, KeyError):
        return None
    except psutil.AccessDenied as exc:
        raise RunnerError("Runner process visibility is unavailable") from exc


def snapshot_job(base, job_id, *, include_result=True):
    directory = job_directory(base, job_id)
    request = read_json(directory / "request.json")
    model = Path(request["model"])
    if not model.is_relative_to(Path(base).resolve()):
        raise RunnerError("Job model is outside the configured model tree")
    state = read_json(directory / "state.json") if (directory / "state.json").exists() else {"status": "starting"}
    identity = read_json(directory / "process.json") if (directory / "process.json").exists() else None
    status = state["status"]
    process = None
    if status in ACTIVE:
        try:
            process = _worker_process(directory, identity) if identity else None
            if process:
                status = "stopping" if (directory / "cancel").exists() else status
            elif time.time() - request["created_epoch"] < 15 and not identity:
                status = "starting"
            else:
                from .process_monitor import scan_model_processes
                native, uncertainties = scan_model_processes(model, recursive=True)
                status = "orphaned" if native else "unknown" if uncertainties else "interrupted"
        except RunnerError:
            status = "unknown"
    result = read_json(directory / "result.json") if include_result and (directory / "result.json").exists() else None
    progress = state.get("progress", {})
    progress_label = "Waiting for native progress"
    if "current" in progress:
        progress_label = f"{progress.get('phase', 'Progress')}: {progress['current']}"
        if progress.get("total"):
            progress_label += f" / {progress['total']}"
    return {**request, **state, "status": status, "active": status in ACTIVE,
            "status_label": STATUS_LABELS.get(status, status.replace("_", " ").capitalize()),
            "status_class": STATUS_CLASSES.get(status, "bg-secondary"),
            "progress_label": progress_label, "can_cancel": process is not None,
            "sequence_label": " → ".join(STAGE_LABELS.get(stage, stage) for stage in request["stages"]),
            "stage_label": STAGE_LABELS.get(state.get("stage"), state.get("stage", "Starting")),
            "created_label": timestamp_label(request["created_at"]),
            "job_id": job_id, "result": result}


def list_jobs(base, *, active_only=False):
    root = Path(base).resolve() / JOB_DIR
    if not root.is_dir() or root.is_symlink():
        return []
    with _CHILDREN_LOCK:
        for job_id, child in list(_CHILDREN.items()):
            if child.poll() is not None:
                del _CHILDREN[job_id]
    jobs = []
    for directory in sorted(root.iterdir(), reverse=True):
        try:
            if active_only and (directory / "state.json").exists():
                if read_json(directory / "state.json")["status"] not in ACTIVE:
                    continue
            job = snapshot_job(base, directory.name, include_result=not active_only)
            if not active_only or job["active"]:
                jobs.append(job)
        except (OSError, ValueError, RunnerError):
            continue
    return sorted(jobs, key=lambda item: item["created_epoch"], reverse=True)


def launch_job(base, model, options, build_plan, expected_fingerprint):
    """Recheck a reviewed plan, reserve the model, and hand execution to a worker."""
    if fcntl is None:
        raise RunnerError("Detached jobs require POSIX model locking")
    base, model = Path(base).resolve(), Path(model).resolve()
    if not model.is_relative_to(base):
        raise RunnerError("Model is outside the configured model tree")
    child = None
    with model_mutation_guard(model, RunnerError):
        plan = build_plan()
        if not plan["ready"]:
            raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
        if fingerprint(plan) != expected_fingerprint:
            raise RunnerError("Inputs or configuration changed since preview; preview the run again.")
        lock_fd = os.open(model / RUN_LOCK_NAME, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(lock_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RunnerError("Unsafe runner reservation lock")
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RunnerError("Another runner job owns this model") from exc
            root = base / JOB_DIR
            if root.is_symlink():
                raise RunnerError("Refusing symlinked job archive")
            mkdir_readable(root, exist_ok=True)
            job_id = uuid.uuid4().hex
            directory = root / job_id
            mkdir_readable(directory)
            write_json(directory / "request.json", {"model": str(model), "model_relpath": model.relative_to(base).as_posix(),
                "stages": options["stages"], "options": options,
                "created_epoch": time.time(), "created_at": datetime.now(timezone.utc).isoformat()})
            write_json(directory / "plan.json", plan)
            with open_readable(directory / "worker.log", "xb") as output:
                child = subprocess.Popen([sys.executable, "-m", "cmfgen_viewer.detached_worker", str(directory), str(lock_fd)],
                    cwd=Path(__file__).resolve().parent.parent, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(lock_fd,), umask=0o022)
            identity = {"pid": child.pid, "create_time": psutil.Process(child.pid).create_time()}
            write_json(directory / "process.json", identity)
            with _CHILDREN_LOCK:
                _CHILDREN[job_id] = child
        except Exception:
            if child is not None:
                child.terminate()
                child.wait(timeout=5)
            raise
        finally:
            os.close(lock_fd)
    # The worker must not acquire the stage write lock before this launcher releases it.
    (directory / "start").touch()
    make_readable(directory / "start")
    return job_id


def cancel_job(base, job_id):
    directory = job_directory(base, job_id)
    job = snapshot_job(base, job_id)
    if not job["active"]:
        raise RunnerError("This runner job is no longer active")
    if not (directory / "process.json").exists():
        raise RunnerError("Runner is still starting; retry shortly")
    process = _worker_process(directory, read_json(directory / "process.json"))
    if process is None:
        raise RunnerError("Runner is absent; inspect surviving native processes before recovery")
    if (directory / "cancel").exists():
        return  # Repeated requests must not interrupt the runner's cleanup.
    (directory / "cancel").touch()
    make_readable(directory / "cancel")
    if not (directory / "state.json").exists():
        return  # The worker observes this marker before launching anything.
    # psutil guards against PID reuse when signalling.
    process.send_signal(signal.SIGTERM)
