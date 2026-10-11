"""Explain CMFGEN's scientific safeguards, including zero-exit Fortran STOPs.

Recognition requires specific native messages. Recovery suggestions are
review guidance, not automatic changes or a claim of scientific convergence.
"""

from __future__ import annotations

import math
from pathlib import Path
import re

from .control_files import control_occurrences
from .parsers.common import parse_float_token


def latest_main_log(text: str) -> str:
    """Discard older invocations in native or wrapper logs that were appended."""
    starts = list(re.finditer(r"^\s*Model started (?:on|at):", text, re.MULTILINE | re.IGNORECASE))
    return text[starts[-1].start():] if starts else text


def _read(path: Path, limit: int = 256 * 1024) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _inner_optical_depth(model: Path) -> float | None:
    text = _read(model / "MEANOPAC")
    if "Tau(Ross)" not in text:
        return None
    try:
        if (model / "MEANOPAC").stat().st_mtime + 2 < (model / "OUTGEN").stat().st_mtime:
            return None
    except OSError:
        return None
    depth = None
    for line in text.splitlines():
        columns = line.split()
        if len(columns) != 15 or not columns[1].isdigit():
            continue
        value = parse_float_token(columns[2])
        if value is not None and math.isfinite(value) and value >= 0:
            depth = value
    return depth


def analyze_main_diagnostics(
    model: Path,
    sources: dict[str, str],
    *,
    completed: bool = False,
) -> list[dict[str, object]]:
    """Analyze invocation-specific log text shared by runner and web diagnostics.

    A major warning is a failure only when completion is absent and the
    STOP_IF_MW safeguard is enabled (the native default). Disabled or ambiguous
    safeguards and completed runs retain the finding as a warning.
    """
    controls = control_occurrences(_read(model / "VADAT"))
    sources = {name: latest_main_log(text) for name, text in sources.items()}

    def control(key: str, default: str = "unknown") -> str:
        rows = controls.get(key, [])
        return str(rows[0]["value"]).upper() if len(rows) == 1 else "ambiguous" if rows else default

    stop = control("STOP_IF_MW", "T (native default)")
    stops = stop in {"T", "TRUE", ".TRUE.", "T (native default)"}
    it_on_t = control("IT_ON_T")
    findings: list[dict[str, object]] = []
    signatures = (
        ("inner_optical_depth", "Inner boundary optical depth is too small",
         r"This model does not extend sufficiently deeply to guarantee the accuracy of"),
        ("inner_flux_accuracy", "Inner luminosity consistency check failed",
         r"Some normalized luminosities are out by a factor of\s*2"),
        ("inner_flux_accuracy_warning", "Inner luminosity differs by more than 25%",
         r"Some normalized luminosities are out by\s*25\s*%"),
    )
    for code, title, pattern in signatures:
        # Deduplicate messages repeated across OUTGEN and captured process logs.
        match_source = next(((name, text, match) for name, text in sources.items()
                             if (match := re.search(pattern, text, re.IGNORECASE))), None)
        if match_source is None:
            continue
        if code == "inner_flux_accuracy_warning" and any(item["code"] == "inner_flux_accuracy" for item in findings):
            continue
        name, text, match = match_source
        start = text.rfind("\n", 0, match.start()) + 1
        evidence = "\n".join(text[start:].splitlines()[:4]).strip()
        major = code != "inner_flux_accuracy_warning"
        severity = "error" if major and stops and not completed else "warning"
        if code == "inner_optical_depth":
            message = "The structure is too optically thin at its inner boundary for CMFGEN's boundary condition (native check: Rosseland optical depth < 30)."
            tau = _inner_optical_depth(model)
            if tau is not None:
                message += f" MEANOPAC reports an innermost Rosseland optical depth of {tau:.6g}."
            suggestions = [
                "Review LTE/HYDRO_PARAMS against LTE/VADAT, especially TEFF, LOG_G versus LOGG, MDOT, and REF_R. Use the workflow's VADAT alignment preview if they differ.",
                "Generate a structure extending to Rosseland optical depth at least 50, preferably 100; rerun the needed LTE/hydro stages and promote the reviewed results, including RSTAR and RMAX.",
            ]
            links = ("MEANOPAC", "RVSIG_COL", "VADAT", "lte/HYDRO_PARAMS")
        else:
            message = (
                "CMFGEN's luminosity consistency check is outside 0.5–2 times the inner-boundary luminosity in the photosphere/inner region."
                if major else
                "CMFGEN's luminosity consistency check is outside 0.8–1.25 times the inner-boundary luminosity in the photosphere/inner region; this message alone does not stop the run."
            )
            if it_on_t in {"F", "FALSE", ".FALSE."}:
                temperature_advice = "Current VADAT [IT_ON_T]=F disables initial grey-temperature refinement. Consider IT_ON_T=T for a fresh start, then rerun main."
            else:
                temperature_advice = f"Review initial temperature refinement in VADAT [IT_ON_T] (current value: {it_on_t}), GREY_TAU, and the starting T_IN/population estimates. If inputs were corrected after this log, rerun main."
            suggestions = [
                "Inspect OBSFLUX's 'Normalized luminosity check' and the corresponding depth region. This check measures luminosity consistency through the atmosphere.",
                temperature_advice,
                "If the discrepancy persists, review depth/ray resolution in MODEL_SPEC and the boundary/transfer settings. Revisit LTE/hydro only if the structure itself needs changing.",
            ]
            links = ("OBSFLUX", "VADAT", "T_IN", "MODEL_SPEC")
        if major:
            message += f" Current VADAT [STOP_IF_MW]={stop}."
            if severity == "error":
                message += " This safeguard can execute Fortran STOP with exit code 0; that does not indicate a successful model."
            suggestions.append("Review and correct the cause before considering disabling STOP_IF_MW; disabling it does not fix the model.")
        findings.append({
            "code": code, "title": title, "severity": severity, "message": message,
            "path": name, "evidence": evidence, "suggestions": suggestions,
            "links": [path for path in links if (model / path).is_file()],
            "controls": {"STOP_IF_MW": stop, "IT_ON_T": it_on_t},
        })
    return findings
