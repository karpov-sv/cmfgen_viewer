"""Domain-aware summaries for externally run LTE and wind_hyd calculations."""

from __future__ import annotations

from pathlib import Path
import re

from .parsers.common import format_number, parse_float_token


MAX_HEAD_BYTES = 2 * 1024 * 1024
MAX_TAIL_BYTES = 4 * 1024 * 1024
FATAL_RE = re.compile(
    r"Fortran runtime error|error termination|segmentation fault|SIGSEGV|"
    r"backtrace for this error|\bERROR STOP\b|floating invalid operation",
    re.IGNORECASE,
)
NUMBER_RE = r"([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+\-]?\d+)?)"


def _read_limited(path: Path, limit: int = MAX_TAIL_BYTES) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            if size > limit:
                stream.seek(size - limit)
                stream.readline()
            payload = stream.read(limit)
    except OSError:
        return ""
    return payload.decode("utf-8", errors="replace")


def _read_head_tail(path: Path) -> tuple[str, bool]:
    try:
        size = path.stat().st_size
        with path.open("rb") as stream:
            if size <= MAX_HEAD_BYTES + MAX_TAIL_BYTES:
                return stream.read().decode("utf-8", errors="replace"), False
            head = stream.read(MAX_HEAD_BYTES)
            stream.seek(size - MAX_TAIL_BYTES)
            stream.readline()
            tail = stream.read(MAX_TAIL_BYTES)
    except OSError:
        return "", False
    return (head + b"\n\n[... retained tail ...]\n\n" + tail).decode(
        "utf-8", errors="replace"
    ), True


def _last_float(text: str, pattern: str) -> float | None:
    matches = re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    if not matches:
        return None
    token = matches[-1]
    if isinstance(token, tuple):
        token = token[-1]
    return parse_float_token(str(token))


def _last_integer(path: Path) -> int | None:
    values = re.findall(r"\d+", _read_limited(path, 256 * 1024))
    return int(values[-1]) if values else None


def _file_is_current(path: Path, dependencies: tuple[Path, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        newest_dependency = max(
            (dependency.stat().st_mtime_ns for dependency in dependencies if dependency.is_file()),
            default=0,
        )
        return path.stat().st_mtime_ns >= newest_dependency
    except OSError:
        return False


def _timing(lte_dir: Path) -> dict[str, str] | None:
    matches = re.findall(
        rf"^\s*GIT\s+{NUMBER_RE}\s+{NUMBER_RE}\s*$",
        _read_limited(lte_dir / "TIMING", 512 * 1024),
        flags=re.MULTILINE,
    )
    if not matches:
        return None
    elapsed = parse_float_token(matches[-1][0])
    cpu = parse_float_token(matches[-1][1])
    if elapsed is None or cpu is None:
        return None
    return {"elapsed": format_number(elapsed), "cpu": format_number(cpu)}


def _log_marker_value(text: str, marker: str) -> str | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() != marker.lower():
            continue
        for candidate in lines[index + 1 : index + 4]:
            if candidate.strip():
                return candidate.strip()
    return None


def _diagnostic(
    label: str,
    detail: str,
    *,
    path: str,
    level: str = "warning",
) -> dict[str, str]:
    return {"label": label, "detail": detail, "path": path, "level": level}


def inspect_lte_diagnostics(lte_dir: Path, *, active: bool = False) -> dict[str, object]:
    """Summarize OUTLTE and the small files that establish its run state."""
    outlte = lte_dir / "OUTLTE"
    run_log_path = lte_dir / "ltebat.log"
    available = outlte.is_file() or run_log_path.is_file()
    if not available:
        return {"available": False, "cards": [], "diagnostics": [], "links": []}

    text, truncated = _read_head_tail(outlte)
    run_log = _read_limited(run_log_path, 512 * 1024)
    totals = re.findall(r"Number of frequencies is:?\s+(\d+)", text, flags=re.IGNORECASE)
    total = int(totals[-1]) if totals else None
    current = _last_integer(lte_dir / "ML_COUNTER")
    if current is None:
        ml_values = re.findall(r"^\s*ML\s*=\s*(\d+)", text, flags=re.MULTILINE)
        current = int(ml_values[-1]) if ml_values else None
    percent = (
        min(100.0, 100.0 * current / total)
        if current is not None and total is not None and total > 0
        else None
    )

    dependencies = tuple(
        lte_dir / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh")
    )
    log_current = _file_is_current(outlte, dependencies)
    result_path = lte_dir / "ROSSELAND_LTE_TAB"
    result_exists = result_path.is_file()
    result_current = _file_is_current(result_path, dependencies)
    fatal_lines = [line.strip() for line in text.splitlines() if FATAL_RE.search(line)]
    started = _log_marker_value(run_log, "Program started on:")
    finished = _log_marker_value(run_log, "Program finished on:")

    fatal = bool(fatal_lines and log_current)
    if fatal:
        status = "failed"
        status_label = "Fatal runtime diagnostic detected"
    elif active:
        status = "running"
        status_label = "LTE calculation is running"
    elif result_current:
        status = "ready"
        status_label = "Current Rosseland result is available"
    elif result_exists:
        status = "stale"
        status_label = "Rosseland result predates an LTE input"
    elif text or run_log:
        status = "incomplete"
        status_label = "No current Rosseland result is available"
    else:
        status = "not_started"
        status_label = "No LTE run output is available"

    cards: list[dict[str, str]] = [
        {"label": "LTE run state", "value": status_label, "detail": "ROSSELAND_LTE_TAB is the authoritative result."}
    ]
    if total is not None:
        progress_value = f"{current:,} / {total:,}" if current is not None else f"— / {total:,}"
        progress_detail = (
            f"{percent:.1f}% by the latest recorded ML counter."
            if percent is not None
            else "No ML progress counter was recorded."
        )
        cards.append(
            {"label": "Frequency integration", "value": progress_value, "detail": progress_detail}
        )
    delta_ed = _last_float(text, rf"DELTA_ED\s*=\s*{NUMBER_RE}")
    delta_t = _last_float(text, rf"DELTA_T\s*=\s*{NUMBER_RE}")
    if delta_ed is not None or delta_t is not None:
        values = []
        if delta_ed is not None:
            values.append(f"ED {format_number(delta_ed)}")
        if delta_t is not None:
            values.append(f"T {format_number(delta_t)}")
        cards.append(
            {
                "label": "LTE initialization corrections",
                "value": " / ".join(values),
                "detail": "Reported DELTA_ED and DELTA_T values; no universal acceptance threshold is applied.",
            }
        )
    if started or finished:
        cards.append(
            {
                "label": "Batch markers",
                "value": "Finished" if finished else "Started only",
                "detail": " · ".join(
                    item for item in (f"Started {started}" if started else "", f"Finished {finished}" if finished else "") if item
                ),
            }
        )
    timing = _timing(lte_dir)
    if timing is not None:
        cards.append(
            {
                "label": "Recorded LTE timing",
                "value": f"{timing['elapsed']} s elapsed",
                "detail": f"{timing['cpu']} s accumulated CPU time.",
            }
        )

    diagnostics: list[dict[str, str]] = []
    if fatal_lines:
        unique = list(dict.fromkeys(fatal_lines))
        diagnostics.append(
            _diagnostic(
                "Fatal runtime output",
                "; ".join(unique[:4]),
                path="OUTLTE",
                level="danger",
            )
        )
    key_errors = len(re.findall(r"Error in GET_KEY_STRING", text, flags=re.IGNORECASE))
    if key_errors:
        diagnostics.append(
            _diagnostic(
                "Control-key lookup notices",
                f"OUTLTE contains {key_errors} GET_KEY_STRING error notice(s); inspect their surrounding text.",
                path="OUTLTE",
            )
        )
    oscillator = len(re.findall(r"bad oscillator strengths|Warning/error reading in Level Names", text, flags=re.IGNORECASE))
    if oscillator:
        diagnostics.append(
            _diagnostic(
                "Atomic-data notices",
                f"OUTLTE contains {oscillator} oscillator-strength or level-name notice(s).",
                path="OUTLTE",
            )
        )
    grid_warnings = len(re.findall(r"Warning from (?:INS_LINE|SET_FREQUENCY_GRID)", text, flags=re.IGNORECASE))
    if grid_warnings:
        diagnostics.append(
            _diagnostic(
                "Frequency-grid notices",
                f"OUTLTE contains {grid_warnings} line-insertion or frequency-grid warning(s).",
                path="OUTLTE",
                level="info",
            )
        )
    two_phot = len(re.findall(r"Warning in SET_TWO_PHOT", text, flags=re.IGNORECASE))
    if two_phot:
        diagnostics.append(
            _diagnostic(
                "Two-photon adjustments",
                f"LTE setup adjusted {two_phot} full n=2 two-photon transition(s).",
                path="OUTLTE",
                level="info",
            )
        )
    float_notice = re.search(r"floating-point exceptions[^\n]*", run_log, flags=re.IGNORECASE)
    if float_notice:
        diagnostics.append(
            _diagnostic(
                "Floating-point flags",
                float_notice.group(0).strip(),
                path="ltebat.log",
                level="info",
            )
        )
    if not active and not result_exists and (current is not None or text):
        diagnostics.append(
            _diagnostic(
                "Incomplete LTE result",
                "Run output exists but ROSSELAND_LTE_TAB is absent.",
                path="OUTLTE",
            )
        )

    return {
        "available": True,
        "status": status,
        "status_label": status_label,
        "cards": cards,
        "diagnostics": diagnostics,
        "frequency_current": current,
        "frequency_total": total,
        "frequency_percent": round(percent, 1) if percent is not None else None,
        "delta_ed": delta_ed,
        "delta_t": delta_t,
        "started_at": started,
        "finished_at": finished,
        "result_exists": result_exists,
        "result_current": result_current,
        "log_current": log_current,
        "fatal": fatal,
        "source_truncated": truncated,
        "links": [
            name
            for name in ("OUTLTE", "ML_COUNTER", "ltebat.log", "ROSSELAND_LTE_TAB", "TIMING")
            if (lte_dir / name).is_file()
        ],
    }


def inspect_wind_hyd_diagnostics(lte_dir: Path, *, active: bool = False) -> dict[str, object]:
    """Summarize captured wind_hyd stdout and its generated structure."""
    log_path = lte_dir / "WIND_HYD"
    output_path = lte_dir / "RVSIG_COL_NEW"
    if not log_path.is_file():
        return {
            "available": False,
            "cards": [],
            "diagnostics": [],
            "links": ["RVSIG_COL_NEW"] if output_path.is_file() else [],
            "message": "No captured WIND_HYD log is available; older runs may predate output capture.",
        }
    text, truncated = _read_head_tail(log_path)
    fatal_lines = [line.strip() for line in text.splitlines() if FATAL_RE.search(line)]
    dependencies = (lte_dir / "ROSSELAND_LTE_TAB", lte_dir / "HYDRO_PARAMS")
    log_current = _file_is_current(log_path, dependencies)
    output_current = _file_is_current(output_path, dependencies)
    fatal = bool(fatal_lines and log_current)
    if fatal:
        status = "failed"
        status_label = "Fatal runtime diagnostic detected"
    elif active:
        status = "running"
        status_label = "wind_hyd is running"
    elif output_current:
        status = "ready"
        status_label = "Current hydro structure is available"
    elif output_path.is_file():
        status = "stale"
        status_label = "Hydro structure predates an input"
    else:
        status = "incomplete"
        status_label = "No current hydro structure is available"

    scalar_patterns = (
        ("Transition radius", rf"Transition radius is\s*{NUMBER_RE}", ""),
        ("Transition velocity", rf"Transition velocity is\s*{NUMBER_RE}", "km/s"),
        ("Old reference radius", rf"Old reference radius is\s*{NUMBER_RE}", "10¹⁰ cm"),
        ("Desired reference radius", rf"Desired reference radius is\s*{NUMBER_RE}", "10¹⁰ cm"),
        ("Effective temperature", rf"New effective temperature is:?\s*{NUMBER_RE}", "10⁴ K"),
        ("Eddington parameter", rf"Eddington parameter is:?\s*{NUMBER_RE}", ""),
        ("Stellar mass", rf"Mass of star is:?\s*{NUMBER_RE}", "M☉"),
    )
    values: dict[str, float] = {}
    units: dict[str, str] = {}
    for label, pattern, unit in scalar_patterns:
        value = _last_float(text, pattern)
        if value is not None:
            values[label] = value
            units[label] = unit

    cards: list[dict[str, str]] = [
        {
            "label": "Hydro run state",
            "value": status_label,
            "detail": "RVSIG_COL_NEW is the authoritative generated structure.",
        }
    ]
    old_radius = values.get("Old reference radius")
    desired_radius = values.get("Desired reference radius")
    if old_radius is not None and desired_radius not in {None, 0.0}:
        difference = 100.0 * (old_radius - desired_radius) / abs(desired_radius)
        cards.append(
            {
                "label": "Final reference-radius difference",
                "value": f"{difference:+.4g}%",
                "detail": f"Generated {format_number(old_radius)}; desired {format_number(desired_radius)} (10¹⁰ cm).",
            }
        )
    if "Transition radius" in values or "Transition velocity" in values:
        parts = []
        if "Transition radius" in values:
            parts.append(f"R {format_number(values['Transition radius'])}")
        if "Transition velocity" in values:
            parts.append(f"V {format_number(values['Transition velocity'])} km/s")
        cards.append(
            {
                "label": "Wind transition",
                "value": " / ".join(parts),
                "detail": "Latest transition quantities reported by wind_hyd.",
            }
        )

    diagnostics: list[dict[str, str]] = []
    if fatal_lines:
        diagnostics.append(
            _diagnostic(
                "Fatal runtime output",
                "; ".join(list(dict.fromkeys(fatal_lines))[:4]),
                path="WIND_HYD",
                level="danger",
            )
        )
    warning_lines = [
        line.strip()
        for line in text.splitlines()
        if re.search(r"\bwarning\b", line, flags=re.IGNORECASE)
    ]
    if warning_lines:
        diagnostics.append(
            _diagnostic(
                "Hydro warnings",
                f"Captured {len(warning_lines)} warning line(s); first: {warning_lines[0]}",
                path="WIND_HYD",
            )
        )
    if not active and not output_path.is_file():
        diagnostics.append(
            _diagnostic(
                "Incomplete hydro result",
                "Captured output exists but RVSIG_COL_NEW is absent.",
                path="WIND_HYD",
            )
        )

    return {
        "available": True,
        "status": status,
        "status_label": status_label,
        "cards": cards,
        "diagnostics": diagnostics,
        "scalars": [
            {"label": label, "value": format_number(value), "unit": units[label]}
            for label, value in values.items()
        ],
        "result_exists": output_path.is_file(),
        "result_current": output_current,
        "log_current": log_current,
        "fatal": fatal,
        "source_truncated": truncated,
        "links": [name for name in ("WIND_HYD", "RVSIG_COL_NEW") if (lte_dir / name).is_file()],
        "message": "",
    }
