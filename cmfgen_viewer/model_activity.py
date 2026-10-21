"""Read-only run visibility and cooperative, cross-process model write guards.

External shell jobs do not honor our lock: detection is a safety check, not a
claim that launching an external process concurrently can be made race-free.
"""

from contextlib import contextmanager
from contextvars import ContextVar
import os
from pathlib import Path
import stat

from .process_monitor import PROGRAM_RE, scan_model_processes

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX systems fail closed for writes
    fcntl = None

LOCK_NAME = ".cmfgen-viewer-write.lock"
RUN_LOCK_NAME = ".cmfgen-runner-job.lock"
# Set only inside the independent, single-threaded runner worker.
_OWNED_RUN_MODEL = None
_RESERVED_MODEL = ContextVar("cmfgen_reserved_model", default=None)


def model_workspace_root(path: Path) -> Path:
    """Editors in lte/ and obs/ share the enclosing model's lock and activity."""
    root = path.resolve()
    while (root.parent / "VADAT").is_file() and (root.parent / "MODEL_SPEC").is_file():
        root = root.parent
    return root


def inspect_model_activity(model_dir: Path, *, proc_root: Path | None = None) -> dict:
    root = model_workspace_root(model_dir)
    if root not in (_OWNED_RUN_MODEL, _RESERVED_MODEL.get()) and ((root / RUN_LOCK_NAME).exists() or (root / RUN_LOCK_NAME).is_symlink()):
        descriptor = None
        try:
            if fcntl is None:
                raise OSError("Runner reservation visibility is unavailable")
            descriptor = os.open(root / RUN_LOCK_NAME, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise OSError("Unsafe runner reservation lock")
            # A shared probe detects the runner's exclusive reservation while
            # keeping inspection read-only. Exclusive locks need a writable
            # descriptor on NFS, even when the file is otherwise readable.
            fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"state": "active", "safe_to_modify": False,
                    "reason": "A runner owns this model; wait for the run to finish.",
                    "processes": [], "uncertainties": [], "model_path": str(root)}
        except OSError as exc:
            return _activity_payload(root, [], [str(exc)])
        finally:
            if descriptor is not None:
                os.close(descriptor)
    if proc_root is None:
        processes, uncertainties = scan_model_processes(root, recursive=True)
        return _activity_payload(root, processes, uncertainties)
    processes, uncertainties = [], []
    try:
        # A missing/hidden procfs must not become a false "idle" result.
        (proc_root / "self" / "stat").read_text()
        entries = list(proc_root.iterdir())
    except OSError:
        entries = []
        uncertainties.append("Process visibility is unavailable; cannot establish that the model is idle.")
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            arguments = entry.joinpath("cmdline").read_bytes().decode(errors="replace").split("\0")
            comm = entry.joinpath("comm").read_text().strip()
            if not any(PROGRAM_RE.fullmatch(Path(arg).name) for arg in [comm, *arguments] if arg):
                continue
            status = entry.joinpath("stat").read_text().rsplit(") ", 1)[1].split()
            if status[0] in {"Z", "X"}:
                continue
            cwd = Path(os.readlink(entry / "cwd")).resolve()
            if cwd == root or root in cwd.parents:
                processes.append({"pid": int(entry.name), "command": " ".join(arguments).strip(),
                                  "cwd": str(cwd), "start_ticks": status[19]})
        except FileNotFoundError:
            continue  # Process exited while being inspected.
        except PermissionError:
            uncertainties.append(f"Cannot inspect process {entry.name}; model activity is uncertain.")
        except (OSError, ValueError, IndexError):
            uncertainties.append(f"Incomplete process information for PID {entry.name}.")
    return _activity_payload(root, processes, uncertainties)


def _activity_payload(root, processes, uncertainties):
    state = "active" if processes else "unknown" if uncertainties else "idle"
    reason = ("A model calculation is active; wait for it to finish before changing this workspace."
              if processes else " ".join(uncertainties))
    return {"state": state, "safe_to_modify": state == "idle", "reason": reason,
            "processes": processes, "uncertainties": uncertainties, "model_path": str(root)}


def validate_lock_inode(descriptor, path):
    """Reject a lock opened before full cleanup removed/replaced its inode."""
    held = os.fstat(descriptor)
    current = Path(path).lstat()
    if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
        raise OSError("Model lock changed; retry the operation.")


@contextmanager
def model_run_reservation(model_dir: Path, error_type=ValueError):
    """Reserve a complete automatic run, including gaps between native children."""
    root = model_workspace_root(model_dir)
    if root in (_OWNED_RUN_MODEL, _RESERVED_MODEL.get()):
        yield
        return
    descriptor = None
    token = None
    try:
        with model_mutation_guard(root, error_type):
            descriptor = os.open(root / RUN_LOCK_NAME,
                                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise error_type("Unsafe model reservation lock")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise error_type("Another runner owns this model") from exc
            validate_lock_inode(descriptor, root / RUN_LOCK_NAME)
            token = _RESERVED_MODEL.set(root)
        yield
    finally:
        if token is not None:
            _RESERVED_MODEL.reset(token)
        if descriptor is not None:
            os.close(descriptor)


@contextmanager
def model_mutation_guard(model_dir: Path, error_type=ValueError):
    """Lock cooperating writers and recheck external activity before mutation."""
    root = model_workspace_root(model_dir)
    activity = inspect_model_activity(root)
    if not activity["safe_to_modify"]:
        raise error_type(activity["reason"])
    if fcntl is None:
        raise error_type("Cross-process model locking is unavailable on this platform.")
    descriptor = None
    try:
        descriptor = os.open(root / LOCK_NAME, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise error_type("Model lock must be an unshared regular file.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise error_type("Another viewer process is changing this model; retry after it finishes.") from exc
        validate_lock_inode(descriptor, root / LOCK_NAME)
        activity = inspect_model_activity(root)
        if not activity["safe_to_modify"]:
            raise error_type(activity["reason"])
        yield descriptor
    except OSError as exc:
        raise error_type(f"Could not safely lock or update the model: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        # Ordinary writes retain the inode. Full cleanup removes it only after
        # its last mutation; later writers validate the inode after locking.
