"""Conservative diagnostics for externally run CMFGEN programs.

These checks deliberately recognize only strong failure signatures.  CMFGEN
outputs contain many scientifically useful warnings whose text includes words
such as ``error``; treating those as process failures would make the result
status unusably noisy.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from .model_editor import model_inputs_modified_since_solution


STATUS_LABELS = {
    "running": "Running",
    "succeeded": "Succeeded",
    "failed": "Failed",
    "incomplete": "Incomplete",
    "unknown": "Unknown",
}

_FATAL_PATTERNS = (
    re.compile(r"Fortran runtime error:", re.IGNORECASE),
    re.compile(r"Error termination\.?", re.IGNORECASE),
    re.compile(r"Program received signal\s+SIG[A-Z0-9]+", re.IGNORECASE),
    re.compile(r"\bsegmentation fault\b", re.IGNORECASE),
    re.compile(r"\bbus error\b", re.IGNORECASE),
    re.compile(r"\bfloating point exception(?:\s|\(|$)", re.IGNORECASE),
    re.compile(r"\bcore dumped\b", re.IGNORECASE),
    re.compile(r"\babort trap\b", re.IGNORECASE),
    re.compile(r"\bfatal(?: runtime)? error\b", re.IGNORECASE),
)
_SHELL_DATE_FORMATS = (
    "%a %b %d %I:%M:%S %p %Y",
    "%a %b %d %H:%M:%S %Y",
)
_FLUX_INVOCATION_PATTERN = re.compile(
    r"^\s*(?:\$PROG_CMF_OBS|\S*cmf_flux(?:\.exe)?)\s+<\s*\S+",
    flags=re.IGNORECASE | re.MULTILINE,
)
_OBSFRAME_MOVE_PATTERN = re.compile(
    r"^\s*mv(?:\s+-\S+)*\s+OBSFRAME\s+([^\s#;&]+)",
    flags=re.IGNORECASE | re.MULTILINE,
)


def _read_text(path: Path, *, limit: int = 4 * 1024 * 1024) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            truncated = size > limit
            if truncated:
                handle.seek(size - limit)
                handle.readline()
            payload = handle.read(limit)
    except OSError:
        return ""
    text = payload.decode("utf-8", errors="replace")
    return text if not truncated else f"[earlier log omitted]\n{text}"


def _read_head(path: Path, *, limit: int = 256 * 1024) -> str:
    try:
        with path.open("rb") as handle:
            payload = handle.read(limit)
    except OSError:
        return ""
    return payload.decode("utf-8", errors="replace")


def _record(
    phase: str,
    status: str,
    summary: str,
    details: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "phase": phase,
        "phase_label": "CMFGEN" if phase == "main" else "CMF_FLUX",
        "status": status,
        "status_label": STATUS_LABELS[status],
        "summary": summary,
        "details": details or [],
    }


def _detail(
    message: str,
    *,
    path: str,
    level: str = "warning",
    line: int | None = None,
    available: bool = True,
) -> dict[str, object]:
    return {
        "level": level,
        "message": message,
        "path": path,
        "line": line,
        "available": available,
    }


def _fatal_details(
    text: str,
    *,
    path: str,
    pass_starts: list[int] | None = None,
) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    offset = 0
    for line_number, raw_line in enumerate(text.splitlines(keepends=True), start=1):
        line = raw_line.strip()
        if line and any(pattern.search(line) for pattern in _FATAL_PATTERNS):
            prefix = ""
            if pass_starts:
                pass_number = sum(start <= offset for start in pass_starts)
                if pass_number:
                    prefix = f"CMF_FLUX pass {pass_number}: "
            details.append(
                _detail(
                    f"{prefix}{line}",
                    path=path,
                    level="danger",
                    line=line_number,
                )
            )
            if len(details) == 3:
                break
        offset += len(raw_line)
    return details


def _latest_shell_date(text: str, marker: str) -> float | None:
    matches = re.findall(rf"^\s*{re.escape(marker)}\s*(.+?)\s*$", text, re.MULTILINE)
    if not matches:
        return None
    date_text = matches[-1].strip()
    parts = date_text.split()
    # The output of `date` normally includes a timezone abbreviation before
    # the year. Python's strptime does not portably recognize CEST and similar
    # local abbreviations, so parse it in the viewer's local timezone.
    if len(parts) >= 7 and parts[-2].upper() not in {"AM", "PM"}:
        date_text = " ".join(parts[:-2] + parts[-1:])
    for date_format in _SHELL_DATE_FORMATS:
        try:
            return datetime.strptime(date_text, date_format).astimezone().timestamp()
        except ValueError:
            continue
    return None


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _latest_mtime(paths: list[Path]) -> float | None:
    times = [value for path in paths if (value := _mtime(path)) is not None]
    return max(times) if times else None


def _is_fresh(path: Path, anchor: float | None) -> bool:
    modified = _mtime(path)
    if modified is None:
        return False
    # Shell timestamps have one-second precision, while output replacement and
    # logging can straddle that boundary by a fraction of a second.
    return anchor is None or modified + 2.0 >= anchor


def _main_input_anchor(model_dir: Path) -> float | None:
    inputs = [model_dir / name for name in ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS")]
    gamma_in = model_dir / "GAMMAS_IN"
    inputs.append(gamma_in if gamma_in.is_file() else model_dir / "GAMMAS")
    inputs.extend(model_dir / name for name in ("RVSIG_COL", "ROSSELAND_LTE_TAB"))
    try:
        inputs.extend(
            path for path in model_dir.iterdir() if path.is_file() and path.name.endswith("_IN")
        )
    except OSError:
        pass
    return _latest_mtime(inputs)


def diagnose_main_run(model_dir: Path, *, active: bool = False) -> dict[str, object]:
    """Classify the latest CMFGEN result without mistaking warnings for failures."""
    log_path = model_dir / "batch.log"
    log = _read_text(log_path)
    fatal = _fatal_details(log, path="batch.log")
    if fatal:
        return _record(
            "main",
            "failed",
            "The current batch log contains a fatal runtime signature.",
            fatal,
        )
    if active:
        return _record("main", "running", "A CMFGEN process is currently active.")

    mod_sum = model_dir / "MOD_SUM"
    rvtj = model_dir / "RVTJ"
    outgen = model_dir / "OUTGEN"
    if not log and not any(path.is_file() for path in (mod_sum, rvtj, outgen)):
        return _record("main", "unknown", "No CMFGEN run result has been recorded yet.")

    anchors = [value for value in (_main_input_anchor(model_dir), _latest_shell_date(log, "Model started at:")) if value is not None]
    anchor = max(anchors) if anchors else None
    details: list[dict[str, object]] = []
    for path in (mod_sum, rvtj):
        if not path.is_file():
            details.append(
                _detail(
                    f"Required result {path.name} is missing.",
                    path=path.name,
                    available=False,
                )
            )
        elif not _is_fresh(path, anchor):
            details.append(
                _detail(
                    f"{path.name} predates the latest run or a current input.",
                    path=path.name,
                )
            )
    if model_inputs_modified_since_solution(model_dir):
        details.append(
            _detail(
                "A model input was modified after the recorded solution.",
                path=".cmfgen-viewer-input-modified.json",
            )
        )
    mod_sum_text = _read_head(mod_sum)
    if mod_sum.is_file() and not re.search(r"^Model Finalized on:", mod_sum_text, re.MULTILINE):
        details.append(
            _detail("MOD_SUM has no model-finalization marker.", path="MOD_SUM")
        )
    if details:
        return _record(
            "main",
            "incomplete",
            "The latest CMFGEN run has no complete, current solution result.",
            details,
        )
    return _record(
        "main",
        "succeeded",
        "The latest CMFGEN run produced current MOD_SUM and RVTJ results.",
    )


def _flux_scripts(obs_dir: Path) -> list[tuple[str, str]]:
    return [
        (name, _read_text(obs_dir / name, limit=512 * 1024))
        for name in ("bat_ins.sh", "batobs.sh")
    ]


def _expected_flux_outputs(scripts: list[tuple[str, str]]) -> list[str]:
    outputs: list[str] = []
    for _name, script in scripts:
        for match in _OBSFRAME_MOVE_PATTERN.finditer(script):
            token = match.group(1).strip("'\"")
            relative = Path(token)
            if token and not relative.is_absolute() and ".." not in relative.parts and "$" not in token:
                normalized = relative.as_posix()
                if normalized not in outputs:
                    outputs.append(normalized)
    return outputs


def _expected_flux_passes(scripts: list[tuple[str, str]]) -> int | None:
    count = sum(len(_FLUX_INVOCATION_PATTERN.findall(script)) for _name, script in scripts)
    return count or None


def _flux_input_anchor(obs_dir: Path, log: str) -> float | None:
    paths = [
        obs_dir / name
        for name in ("batobs.sh", "bat_ins.sh", "CMF_FLUX_PARAM_INIT", "IN_FILE", "RVTJ", "MODEL")
    ]
    paths.extend(obs_dir.parent / name for name in ("RVTJ", "MODEL", "MOD_SUM"))
    values = [value for value in (_latest_mtime(paths), _latest_shell_date(log, "Program started at:")) if value is not None]
    return max(values) if values else None


def diagnose_flux_run(obs_dir: Path, *, active: bool = False) -> dict[str, object]:
    """Classify the latest CMF_FLUX batch and validate its moved spectra."""
    log_path = obs_dir / "batobs.log"
    log = _read_text(log_path)
    pass_starts = [
        match.start()
        for match in re.finditer(
            r"PID of\s+.*?cmf_flux(?:\.exe)?\s+is:\s*\d+",
            log,
            flags=re.IGNORECASE,
        )
    ]
    fatal = _fatal_details(log, path="batobs.log", pass_starts=pass_starts)
    if fatal:
        return _record(
            "flux",
            "failed",
            "The current CMF_FLUX log contains a fatal runtime signature.",
            fatal,
        )
    if active:
        return _record("flux", "running", "A CMF_FLUX process is currently active.")
    if not log:
        return _record("flux", "unknown", "No CMF_FLUX run log has been recorded yet.")

    scripts = _flux_scripts(obs_dir)
    expected_passes = _expected_flux_passes(scripts)
    completed = min(
        len(pass_starts),
        len(re.findall(r"Program finished on:", log, flags=re.IGNORECASE)),
    )
    details: list[dict[str, object]] = []
    if expected_passes is None:
        details.append(
            _detail(
                "The expected CMF_FLUX pass count could not be derived from batobs.sh and bat_ins.sh.",
                path="batobs.sh",
                available=(obs_dir / "batobs.sh").is_file(),
            )
        )
    elif completed < expected_passes:
        details.append(
            _detail(
                f"Only {completed} of {expected_passes} expected CMF_FLUX passes have completion markers.",
                path="batobs.log",
            )
        )

    anchor = _flux_input_anchor(obs_dir, log)
    expected_outputs = _expected_flux_outputs(scripts)
    if not expected_outputs:
        details.append(
            _detail(
                "Expected spectrum outputs could not be derived from OBSFRAME moves in the run scripts.",
                path="batobs.sh",
                available=(obs_dir / "batobs.sh").is_file(),
            )
        )
    for relative_name in expected_outputs:
        output = obs_dir.joinpath(*Path(relative_name).parts)
        if not output.is_file():
            details.append(
                _detail(
                    f"Expected spectrum {relative_name} is missing.",
                    path=relative_name,
                    available=False,
                )
            )
        elif not _is_fresh(output, anchor):
            details.append(
                _detail(
                    f"Expected spectrum {relative_name} predates this run or a current input.",
                    path=relative_name,
                )
            )

    out_flux = obs_dir / "OUT_FLUX"
    out_flux_text = _read_text(out_flux, limit=512 * 1024)
    if not out_flux.is_file():
        details.append(
            _detail("OUT_FLUX is missing.", path="OUT_FLUX", available=False)
        )
    elif not _is_fresh(out_flux, anchor):
        details.append(
            _detail("OUT_FLUX predates this run or a current input.", path="OUT_FLUX")
        )
    elif not re.search(r"CMF_FLUX has finished", out_flux_text, flags=re.IGNORECASE):
        details.append(
            _detail("OUT_FLUX has no successful completion marker.", path="OUT_FLUX")
        )

    if details:
        return _record(
            "flux",
            "incomplete",
            "The latest CMF_FLUX run did not produce every expected current result.",
            details,
        )
    return _record(
        "flux",
        "succeeded",
        f"All {completed} CMF_FLUX passes and their spectrum outputs completed successfully.",
    )
