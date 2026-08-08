"""Read-only process and file-progress monitoring for external CMFGEN runs."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import time

from .parsers.common import parse_float_token
from .model_run_diagnostics import diagnose_flux_run, diagnose_main_run


PROCESS_TOKENS = {
    "main": ("cmfgen", "batch.sh"),
    "flux": ("cmf_flux", "batobs.sh", "bat_ins.sh", "batch.sh"),
    "lte": ("main_lte", "ltebat"),
    "hydro": ("wind_hyd",),
}
PROCESS_LABELS = {
    "main": "CMFGEN",
    "flux": "CMF_FLUX",
    "lte": "LTE",
    "hydro": "Hydro structure",
}
PROCESS_STATES = {
    "R": "running",
    "S": "sleeping",
    "D": "waiting for I/O",
    "T": "stopped",
    "t": "tracing stop",
    "Z": "zombie",
    "X": "dead",
    "I": "idle",
}


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_memory(size_bytes: int) -> str:
    value = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"


def _read_tail(path: Path, limit: int = 2 * 1024 * 1024) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > limit:
                handle.seek(size - limit)
                handle.readline()
            payload = handle.read(limit)
    except OSError:
        return ""
    return payload.decode("utf-8", errors="replace")


def _read_from_latest_marker(path: Path, marker: bytes) -> tuple[str, bool]:
    """Read the latest appended run, locating its boundary without loading old runs."""
    chunk_size = 256 * 1024
    try:
        size = path.stat().st_size
        marker_offset: int | None = None
        with path.open("rb") as handle:
            end = size
            right_prefix = b""
            while end > 0:
                start = max(0, end - chunk_size)
                handle.seek(start)
                chunk = handle.read(end - start)
                combined = chunk + right_prefix
                index = combined.rfind(marker)
                if index >= 0:
                    marker_offset = start + index
                    break
                right_prefix = chunk[: max(0, len(marker) - 1)]
                end = start
            if marker_offset is None:
                return _read_tail(path), False
            handle.seek(marker_offset)
            payload = handle.read()
    except OSError:
        return "", False
    return payload.decode("utf-8", errors="replace"), True


def _proc_uptime(proc_root: Path) -> float:
    try:
        return float((proc_root / "uptime").read_text(encoding="ascii").split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _process_record(
    process_dir: Path,
    *,
    target_dir: Path,
    tokens: tuple[str, ...],
    uptime: float,
    now_epoch: float,
    clock_ticks: int,
) -> dict[str, object] | None:
    try:
        cwd = Path(os.readlink(process_dir / "cwd")).resolve()
        if cwd != target_dir:
            return None
        command_bytes = (process_dir / "cmdline").read_bytes()
        command = command_bytes.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
        comm = (process_dir / "comm").read_text(encoding="utf-8", errors="replace").strip()
        searchable = f"{comm} {command}".lower()
        if not any(token in searchable for token in tokens):
            return None
        stat_text = (process_dir / "stat").read_text(encoding="ascii", errors="replace")
        stat_fields = stat_text.rsplit(") ", 1)[1].split()
        state_code = stat_fields[0]
        ppid = int(stat_fields[1])
        cpu_seconds = (int(stat_fields[11]) + int(stat_fields[12])) / clock_ticks
        start_ticks = int(stat_fields[19])
        elapsed = max(0.0, uptime - start_ticks / clock_ticks)
        start_epoch = now_epoch - elapsed
        rss_bytes = 0
        threads = 0
        for line in (process_dir / "status").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            if line.startswith("VmRSS:"):
                rss_bytes = int(line.split()[1]) * 1024
            elif line.startswith("Threads:"):
                threads = int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return {
        "pid": int(process_dir.name),
        "ppid": ppid,
        "name": comm,
        "command": command or comm,
        "state": PROCESS_STATES.get(state_code, state_code),
        "state_code": state_code,
        "elapsed_seconds": elapsed,
        "elapsed": _format_duration(elapsed),
        "cpu_seconds": cpu_seconds,
        "cpu_time": _format_duration(cpu_seconds),
        "cpu_percent": round(100.0 * cpu_seconds / elapsed, 1) if elapsed > 0 else 0.0,
        "rss_bytes": rss_bytes,
        "rss": _format_memory(rss_bytes),
        "threads": threads,
        "started_at": datetime.fromtimestamp(start_epoch).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        ),
        "start_epoch": start_epoch,
    }


def find_workflow_processes(
    target_dir: Path,
    kind: str,
    *,
    proc_root: Path = Path("/proc"),
    now_epoch: float | None = None,
) -> list[dict[str, object]]:
    tokens = PROCESS_TOKENS.get(kind)
    if tokens is None:
        return []
    target = target_dir.expanduser().resolve()
    uptime = _proc_uptime(proc_root)
    now = time.time() if now_epoch is None else now_epoch
    try:
        clock_ticks = int(os.sysconf("SC_CLK_TCK"))
    except (OSError, ValueError):
        clock_ticks = 100
    try:
        process_dirs = [path for path in proc_root.iterdir() if path.name.isdigit()]
    except OSError:
        return []
    records = [
        record
        for path in process_dirs
        if (
            record := _process_record(
                path,
                target_dir=target,
                tokens=tokens,
                uptime=uptime,
                now_epoch=now,
                clock_ticks=clock_ticks,
            )
        )
        is not None
    ]
    records.sort(key=lambda item: (".exe" not in str(item["command"]).lower(), int(item["pid"])))
    return records


def _control_integer(path: Path, key: str) -> int | None:
    text = _read_tail(path, limit=256 * 1024)
    match = re.search(rf"^\s*(\d+)\s+\[{re.escape(key)}\]", text, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _main_progress(target_dir: Path) -> dict[str, object] | None:
    output, run_boundary_found = _read_from_latest_marker(
        target_dir / "OUTGEN",
        b"Model started on:",
    )
    iterations = re.findall(r"Current great iteration count is\s+(\d+)", output)
    if not iterations:
        iterations = re.findall(r"\(iteration\s+(\d+)\)", output, flags=re.IGNORECASE)
    if not iterations:
        return None
    global_iteration = int(iterations[-1])
    current = len(iterations) if run_boundary_found else global_iteration
    requested = _control_integer(target_dir / "IN_ITS", "NUM_ITS")
    percent = min(100.0, 100.0 * current / requested) if requested and requested > 0 else None
    metrics: list[dict[str, str]] = [
        {
            "label": "Current run iteration" if run_boundary_found else "Current iteration",
            "value": str(current),
        }
    ]
    if run_boundary_found:
        metrics.append({"label": "Global great iteration", "value": str(global_iteration)})
    if requested is not None:
        metrics.append({"label": "Requested iterations", "value": str(requested)})
    luminosities = re.findall(
        r"Luminosity of star .*? is:\s*(\S+)\s+(\S+)", output, flags=re.IGNORECASE
    )
    if luminosities:
        generated = parse_float_token(luminosities[-1][0])
        target = parse_float_token(luminosities[-1][1])
        if generated is not None and target not in {None, 0.0}:
            difference = 100.0 * (generated - target) / abs(target)
            metrics.append({"label": "Luminosity difference", "value": f"{difference:+.4g}%"})
    changes = re.findall(r"Maximm changes .*? is\s+(\S+)", output)
    if changes:
        parsed = parse_float_token(changes[-1])
        if parsed is not None:
            metrics.append({"label": "Latest maximum change", "value": f"{parsed:.6g}"})
    return {
        "label": "CMFGEN iterations",
        "current": current,
        "maximum": requested,
        "percent": round(percent, 1) if percent is not None else None,
        "detail": (
            f"Run iteration {current} of {requested} requested"
            if run_boundary_found and requested is not None
            else f"Run iteration {current}"
            if run_boundary_found
            else f"Iteration {current} of {requested} requested"
            if requested is not None
            else f"Iteration {current}"
        ),
        "estimated": True,
        "metrics": metrics,
    }


def _lte_progress(target_dir: Path) -> dict[str, object] | None:
    output = _read_tail(target_dir / "OUTLTE")
    totals = re.findall(r"Number of frequencies is\s+(\d+)", output)
    counter_text = _read_tail(target_dir / "ML_COUNTER", limit=256 * 1024)
    counters = re.findall(r"\d+", counter_text)
    if not totals or not counters:
        return None
    total = int(totals[-1])
    current = int(counters[-1])
    percent = min(100.0, 100.0 * current / total) if total > 0 else None
    return {
        "label": "LTE frequency integration",
        "current": current,
        "maximum": total,
        "percent": round(percent, 1) if percent is not None else None,
        "detail": f"Frequency {current:,} of {total:,}",
        "estimated": True,
        "metrics": [],
    }


def _hydro_progress(target_dir: Path) -> dict[str, object] | None:
    output = _read_tail(target_dir / "RVSIG_COL_NEW", limit=512 * 1024)
    expected_match = re.search(r"^\s*(\d+)\s*!\s*Number of depth points", output, re.MULTILINE)
    indices = re.findall(r"^\s*\S+\s+\S+\s+\S+\s+\S+\s+(\d+)\s*$", output, re.MULTILINE)
    if expected_match is None or not indices:
        return None
    expected = int(expected_match.group(1))
    current = int(indices[-1])
    percent = min(100.0, 100.0 * current / expected) if expected > 0 else None
    return {
        "label": "Hydro output grid",
        "current": current,
        "maximum": expected,
        "percent": round(percent, 1) if percent is not None else None,
        "detail": f"Depth point {current} of {expected}",
        "estimated": True,
        "metrics": [],
    }


def _cmf_flux_invocation_count(target_dir: Path) -> int | None:
    count = 0
    invocation_pattern = re.compile(
        r"^\s*(?:\$PROG_CMF_OBS|\S*cmf_flux(?:\.exe)?)\s+<\s*\S+",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    for name in ("bat_ins.sh", "batobs.sh"):
        script = _read_tail(target_dir / name, limit=512 * 1024)
        count += len(invocation_pattern.findall(script))
    return count or None


def _flux_progress(target_dir: Path) -> dict[str, object] | None:
    log_path = target_dir / "batobs.log"
    log = _read_tail(log_path, limit=512 * 1024)
    starts = re.findall(
        r"PID of\s+.*?cmf_flux(?:\.exe)?\s+is:\s*\d+",
        log,
        flags=re.IGNORECASE,
    )
    finishes = re.findall(r"Program finished on:", log, flags=re.IGNORECASE)
    if not starts and not finishes:
        return None
    started = len(starts)
    completed = min(len(finishes), started)
    total = _cmf_flux_invocation_count(target_dir)
    running_pass = started if started > completed else None
    if running_pass is not None:
        detail = (
            f"CMF_FLUX pass {running_pass} of {total} running"
            if total is not None
            else f"CMF_FLUX pass {running_pass} running"
        )
    else:
        detail = (
            f"Completed {completed} of {total} CMF_FLUX passes"
            if total is not None
            else f"Completed {completed} CMF_FLUX passes"
        )
    percent = 100.0 * completed / total if total and total > 0 else None
    metrics: list[dict[str, str]] = [
        {
            "label": "Completed passes",
            "value": f"{completed} of {total}" if total is not None else str(completed),
        }
    ]

    output_path = target_dir / "OUT_FLUX"
    control_path = target_dir / "CMF_FLUX_PARAM"
    try:
        output_is_current = output_path.stat().st_mtime >= control_path.stat().st_mtime
    except OSError:
        output_is_current = False
    if output_is_current:
        output = _read_tail(output_path, limit=512 * 1024)
        loops = re.findall(r"LS loop\s*(\d+)\s+is finished", output, flags=re.IGNORECASE)
        if loops:
            metrics.append({"label": "Latest LS loop", "value": loops[-1]})

    control = _read_tail(control_path, limit=256 * 1024)
    turbulence = re.search(r"^\s*(\S+)\s+\[VTURB_FIX\]", control, flags=re.MULTILINE)
    if turbulence:
        metrics.append({"label": "VTURB_FIX", "value": turbulence.group(1)})
    return {
        "label": "CMF_FLUX passes",
        "current": completed,
        "maximum": total,
        "percent": round(percent, 1) if percent is not None else None,
        "detail": detail,
        "estimated": True,
        "metrics": metrics,
    }


def inspect_workflow_runtime(
    target_dir: Path,
    kind: str,
    *,
    proc_root: Path = Path("/proc"),
    now_epoch: float | None = None,
) -> dict[str, object]:
    processes = find_workflow_processes(
        target_dir,
        kind,
        proc_root=proc_root,
        now_epoch=now_epoch,
    )
    main_processes_active = bool(processes)
    flux_processes: list[dict[str, object]] = []
    phase = kind
    progress_target = target_dir
    if kind == "main":
        flux_dir = target_dir / "obs"
        flux_processes = (
            find_workflow_processes(
                flux_dir,
                "flux",
                proc_root=proc_root,
                now_epoch=now_epoch,
            )
            if flux_dir.is_dir()
            else []
        )
        if flux_processes:
            processes.extend(flux_processes)
            processes.sort(key=lambda item: int(item["pid"]))
            phase = "flux"
            progress_target = flux_dir
    progress_reader = {
        "main": _main_progress,
        "flux": _flux_progress,
        "lte": _lte_progress,
        "hydro": _hydro_progress,
    }.get(phase)
    progress = progress_reader(progress_target) if progress_reader is not None else None
    progress_source = {
        "main": target_dir / "OUTGEN",
        "flux": progress_target / "batobs.log",
        "lte": target_dir / "ML_COUNTER",
        "hydro": target_dir / "RVSIG_COL_NEW",
    }.get(phase)
    if processes and progress is not None and progress_source is not None:
        try:
            source_mtime = progress_source.stat().st_mtime
        except OSError:
            source_mtime = 0.0
        earliest_start = min(float(item["start_epoch"]) for item in processes)
        if source_mtime < earliest_start:
            progress = None
    recorded_progress: list[dict[str, object]] = []
    if kind == "main" and not processes:
        main_progress = progress if phase == "main" else _main_progress(target_dir)
        flux_dir = target_dir / "obs"
        flux_progress = _flux_progress(flux_dir) if flux_dir.is_dir() else None
        if main_progress is not None:
            recorded_progress.append(
                {
                    "phase": "main",
                    "phase_label": PROCESS_LABELS["main"],
                    "progress": main_progress,
                }
            )
        if flux_progress is not None:
            recorded_progress.append(
                {
                    "phase": "flux",
                    "phase_label": PROCESS_LABELS["flux"],
                    "progress": flux_progress,
                }
            )
    diagnostics: list[dict[str, object]] = []
    if kind == "main":
        diagnostics = [
            diagnose_main_run(target_dir, active=main_processes_active),
            diagnose_flux_run(target_dir / "obs", active=bool(flux_processes)),
        ]
    return {
        "kind": kind,
        "label": "Main model workflow" if kind == "main" else PROCESS_LABELS.get(kind, kind),
        "phase": phase,
        "phase_label": PROCESS_LABELS.get(phase, phase),
        "active": bool(processes),
        "processes": processes,
        "progress": progress,
        "recorded_progress": recorded_progress,
        "diagnostics": diagnostics,
        "checked_at": datetime.now().astimezone().strftime("%H:%M:%S"),
    }
