"""Read-only run visibility and cooperative, cross-process model write guards.

External shell jobs do not honor our lock: detection is a safety check, not a
claim that launching an external process concurrently can be made race-free.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import stat

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX systems fail closed for writes
    fcntl = None

LOCK_NAME = ".cmfgen-viewer-write.lock"
PROGRAM_RE = re.compile(r"^(?:cmfgen[\w.-]*|cmf_flux[\w.-]*|main_lte[\w.-]*|wind_hyd[\w.-]*|"
                        r"(?:batch|batch_ins|batobs|bat_ins|ltebat)\.sh)$", re.I)


def model_workspace_root(path: Path) -> Path:
    """Editors in lte/ and obs/ share the enclosing model's lock and activity."""
    root = path.resolve()
    while (root.parent / "VADAT").is_file() and (root.parent / "MODEL_SPEC").is_file():
        root = root.parent
    return root


def inspect_model_activity(model_dir: Path, *, proc_root: Path = Path("/proc")) -> dict:
    root = model_workspace_root(model_dir)
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
    state = "active" if processes else "unknown" if uncertainties else "idle"
    reason = ("A model calculation is active; wait for it to finish before changing this workspace."
              if processes else " ".join(uncertainties))
    return {"state": state, "safe_to_modify": state == "idle", "reason": reason,
            "processes": processes, "uncertainties": uncertainties, "model_path": str(root)}


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
        activity = inspect_model_activity(root)
        if not activity["safe_to_modify"]:
            raise error_type(activity["reason"])
        yield descriptor
    except OSError as exc:
        raise error_type(f"Could not safely lock or update the model: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        # Never unlink: removing an advisory lock file can create two lock inodes.
