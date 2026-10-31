"""Native process discovery shared by runtime panels and model write guards."""

import os
from pathlib import Path
import re
import time

try:
    import psutil
except ImportError:  # Missing dependencies must never imply an idle workspace.
    psutil = None

PROGRAM_RE = re.compile(r"^(?:cmfgen[\w.-]*|cmf_flux[\w.-]*|main_lte[\w.-]*|wind_hyd[\w.-]*|rev_rvsig[\w.-]*|"
                        r"(?:batch|batch_ins|batobs|bat_ins|ltebat)\.sh)$", re.I)
SHELL_NAMES = {"sh", "bash", "zsh", "csh", "tcsh", "dash", "ksh"}


def scan_model_processes(target_dir: Path, *, recursive=False, tokens=None, now_epoch=None):
    """Return matching processes and uncertainty; never infer idle from denied reads."""
    records, uncertainties = [], []
    target = target_dir.expanduser().resolve()
    if psutil is None:
        return [], ["Process visibility is unavailable; install the psutil dependency."]
    now = time.time() if now_epoch is None else now_epoch
    try:
        for process in psutil.process_iter(["name", "cmdline", "status"], ad_value=None):
            if process.pid == os.getpid():
                continue
            info = process.info
            if info.get("status") in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}:
                continue
            name, arguments = info.get("name"), info.get("cmdline")
            # Paths passed as data (e.g. --working-dir cmfgen_viewer) are not executables.
            candidates = [name, (arguments or [None])[0]]
            if name in SHELL_NAMES and arguments:
                script = next((arg for arg in arguments[1:] if not arg.startswith("-")), None)
                candidates.append(script)
            names = [Path(arg).name for arg in candidates if arg]
            if not any(PROGRAM_RE.fullmatch(arg) for arg in names):
                if (name is None and arguments is None) or (name in SHELL_NAMES and arguments is None):
                    try:
                        # Empty cached fields can describe a process that exited
                        # during enumeration, rather than denied visibility.
                        if not process.is_running():
                            continue
                        if info.get("status") is None and process.status() in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}:
                            continue
                    except psutil.NoSuchProcess:
                        continue
                    except (psutil.AccessDenied, OSError, ValueError):
                        pass  # A still-unidentified process remains unsafe.
                    uncertainties.append(f"Cannot identify process {process.pid}; model activity is uncertain.")
                continue
            if tokens and not any(token in arg.lower() for arg in names for token in tokens):
                continue
            if info.get("status") in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}:
                continue
            try:
                # Check PID identity before using a cached process_iter object.
                if not process.is_running():
                    continue
                data = process.as_dict(attrs=["cwd", "create_time", "cpu_times", "memory_info",
                                              "num_threads", "ppid"], ad_value=None)
                if not data.get("cwd"):
                    uncertainties.append(f"Cannot inspect working directory of process {process.pid}; model activity is uncertain.")
                    continue
                cwd = Path(data["cwd"]).resolve()
                if cwd != target and not (recursive and target in cwd.parents):
                    continue
                if info.get("status") is None:
                    uncertainties.append(f"Cannot inspect state of process {process.pid}; model activity is uncertain.")
                cpu = data.get("cpu_times")
                memory = data.get("memory_info")
                start = data.get("create_time")
                records.append({
                    "pid": process.pid, "ppid": data.get("ppid"),
                    "name": name or names[0], "arguments": arguments or [],
                    "command": " ".join(arguments or [name or names[0]]), "cwd": str(cwd),
                    "state": info.get("status") or "unknown",
                    "start_epoch": start, "elapsed_seconds": max(0, now - start) if start else None,
                    "cpu_seconds": cpu.user + cpu.system if cpu else None,
                    "rss_bytes": memory.rss if memory else None, "threads": data.get("num_threads"),
                })
            except psutil.NoSuchProcess:
                continue  # Exited during inspection (includes ZombieProcess).
            except (psutil.AccessDenied, OSError, ValueError):
                uncertainties.append(f"Cannot inspect process {process.pid}; model activity is uncertain.")
    except (psutil.Error, OSError):
        uncertainties.append("Process visibility is unavailable; cannot establish that the model is idle.")
    return records, list(dict.fromkeys(uncertainties))
