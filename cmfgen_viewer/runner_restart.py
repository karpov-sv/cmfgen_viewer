"""Read-only detection of native CMFGEN checkpoint state.

Pointer semantics follow SCR_READ_V2. Binary population records remain native
CMFGEN's responsibility; MODEL provides a consistency check, not provenance.
"""

import os
import re

from .control_files import control_occurrences
from .runner_validation import validate_rvtj_core


RESTART_FILES = ("POINT1", "POINT2", "SCRTEMP")


def read_pointer(path):
    if path.stat().st_size > 8192:
        raise ValueError("pointer file is unexpectedly large")
    lines = path.read_text().splitlines()
    modern = bool(lines and "!Format date" in lines[0])
    row = lines[1] if modern and len(lines) > 1 else lines[0] if lines else ""
    fields = row.split("!", 1)[0].replace(",", " ").split()
    required = 5 if modern else 4
    if len(fields) < required:
        raise ValueError("incomplete pointer record")
    record, iterations, writes, last_ng = (int(v) for v in fields[:4])
    if record < 1 or iterations < 0 or writes < 0:
        raise ValueError("invalid record or iteration counters")
    logical = fields[4].upper().strip(".") if modern else "F"
    if logical not in {"T", "F", "TRUE", "FALSE"}:
        raise ValueError("invalid WR_RVS logical")
    return {"file": path.name, "record": record, "iterations": iterations,
            "writes": writes, "last_ng": last_ng,
            "writes_rvsig": logical in {"T", "TRUE"},
            "format_date": lines[0].split("!", 1)[0].strip() if modern else None}


def inspect_restart(model, *, fresh_start=False):
    errors, warnings = [], []
    present = [name for name in RESTART_FILES if (model / name).exists() or (model / name).is_symlink()]
    result = {"requested": "fresh" if fresh_start else "auto", "mode": "fresh",
              "present_files": present, "pointer": None, "health": {"status": "not_checked"},
              "errors": errors, "warnings": warnings}
    for name in present:
        path = model / name
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            errors.append(f"Unsafe restart file {name}: require an unshared regular file")
        elif not os.access(path, os.R_OK):
            errors.append(f"Restart file is not readable: {name}")
    if errors or fresh_start or not present:
        result["message"] = "Explicit fresh start: archive checkpoints and use *_IN" if fresh_start else "Fresh start from *_IN"
        return result
    failures = []
    for name in ("POINT1", "POINT2"):
        if name not in present:
            continue
        try:
            result["pointer"] = read_pointer(model / name)
            break
        except (OSError, ValueError, UnicodeError) as exc:
            failures.append(f"{name}: {exc}")
    if result["pointer"] is None:
        if failures:
            errors.append("No usable restart pointer: " + "; ".join(failures) + ". Repair the checkpoint or use --fresh-start.")
            result["mode"] = "invalid"
        else:
            warnings.append("SCRTEMP has no pointer files; CMFGEN will start fresh from *_IN.")
    elif "SCRTEMP" not in present or (model / "SCRTEMP").stat().st_size == 0:
        errors.append("Restart pointer exists but SCRTEMP is missing or empty; repair the checkpoint or use --fresh-start.")
        result["mode"] = "invalid"
    else:
        result["mode"] = "continuation"
        warnings.extend(f"Using POINT2 fallback after {failure}" for failure in failures)
        warnings.append("Continuation checks do not fully validate binary checkpoint layout, population values, or atomic-data compatibility.")
        rvtj = model / "RVTJ"
        if rvtj.is_file():
            try:
                validate_rvtj_core(rvtj, model / "MODEL_SPEC")
            except (OSError, ValueError, UnicodeError) as exc:
                result["health"] = {"status": "failed", "source": "RVTJ", "problem": str(exc)}
                errors.append(
                    f"Checkpoint health check failed: invalid RVTJ core ({exc}). "
                    "The restart may be poisoned; recover a known-good checkpoint or use --fresh-start."
                )
            else:
                result["health"] = {
                    "status": "passed",
                    "source": "RVTJ",
                    "evidence": "finite positive radius, temperature, and electron-density vectors",
                }
        else:
            result["health"] = {"status": "unavailable", "source": "RVTJ"}
            warnings.append("RVTJ is absent; checkpoint numerical health cannot be checked before continuation.")
        spec = control_occurrences((model / "MODEL_SPEC").read_text())
        nd = None
        try:
            nd = int(spec["ND"][0]["value"])
            if (model / "SCRTEMP").stat().st_size < max(1, nd) * 3 * 8:
                errors.append("SCRTEMP is too short even for the radius/velocity/gradient vectors; use a valid checkpoint or --fresh-start.")
        except (KeyError, IndexError, ValueError):
            pass  # General control preflight reports malformed dimensions.
        metadata = model / "MODEL"
        if metadata.is_file():
            with metadata.open(errors="replace") as handle:
                header = handle.read(65536).split("\f", 1)[0]
            old_nd = re.search(r"^\s*(\d+)\s+!Number of depth points", header, re.M)
            if old_nd and nd is not None and int(old_nd[1]) != nd:
                errors.append("Restart MODEL depth count differs from MODEL_SPEC; review checkpoint compatibility or use --fresh-start.")
            old_ions = {m[1].upper(): (int(m[2]), int(m[3])) for m in re.finditer(
                r"^\s*([A-Za-z][A-Za-z0-9]*)\s+(\d+)\s+(\d+)\s+[0-9]+\.[0-9]+", header, re.M)}
            current = {}
            for key, rows in spec.items():
                if key.endswith(("_ISF", "_NSF")):
                    try:
                        numbers = [int(v.strip()) for v in rows[0]["value"].split(",")]
                        ns, nf = numbers[-2:]
                        if ns > 0:
                            current[key[:-4]] = (nf, ns)
                    except ValueError:
                        continue  # General ion preflight reports this.
            if old_ions and current != old_ions:
                errors.append("Restart MODEL ion/level layout differs from MODEL_SPEC; review checkpoint compatibility or use --fresh-start.")
            if not old_nd or not old_ions:
                warnings.append("MODEL does not provide complete recognizable checkpoint dimension/ion metadata.")
        else:
            warnings.append("MODEL is absent; checkpoint dimension/ion compatibility cannot be cross-checked.")
        vadat = control_occurrences((model / "VADAT").read_text())
        if not result["pointer"]["writes_rvsig"] and any(
            vadat.get(key) and vadat[key][0]["value"].upper() == "T" for key in ("DO_HYDRO", "REV_RGRID")
        ):
            errors.append("DO_HYDRO/REV_RGRID requires a checkpoint with WR_RVS=T; use --fresh-start or convert the checkpoint natively.")
    pointer = result["pointer"]
    result["message"] = (f"Continuation from {pointer['file']} (saved iteration {pointer['iterations']}, record {pointer['record']})"
                         if result["mode"] == "continuation" else "Fresh start from *_IN" if result["mode"] == "fresh" else "Invalid restart state")
    return result


def observe_startup(restart, paths):
    """Report native fallback and iteration evidence without inventing certainty."""
    text = ""
    for path in paths:
        if path.is_file():
            with path.open(errors="replace") as handle:
                text += handle.read(256 * 1024) + "\n"
    if "Starting a new model." in text:
        return {"mode": "fresh", "evidence": "native fresh-start message"}
    counters = re.findall(r"Current great iteration count is\s+(\d+)", text)
    pointer = restart.get("pointer")
    if counters and pointer and int(counters[0]) == pointer["iterations"] + 1:
        return {"mode": "continuation", "evidence": "native iteration counter", "first_iteration": int(counters[0])}
    return {"mode": "unconfirmed", "evidence": "no explicit startup evidence in captured log prefix"}
