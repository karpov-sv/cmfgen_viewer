"""Read-only model information and native/runner execution evidence."""

import json
from pathlib import Path
import re

from .control_files import control_occurrences
from .model_activity import inspect_model_activity
from .model_run_diagnostics import diagnose_main_run
from .runner_recipe import RunnerError
from .runner_restart import inspect_restart


def _latest_native_run(model, warnings):
    directory = model / ".cmfgen-runs"
    if not directory.is_dir():
        return None
    reports = []
    for journal in directory.iterdir():
        result_path = journal / "result.json"
        if not journal.is_dir() or not result_path.is_file():
            continue
        try:
            reports.append((result_path.stat().st_mtime_ns, journal))
        except OSError as exc:
            warnings.append(f"Cannot inspect run report {result_path}: {exc}")
    for _, journal in sorted(reports, reverse=True):
        result_path = journal / "result.json"
        try:
            result = json.loads(result_path.read_text())
            if not isinstance(result, dict):
                raise ValueError("expected a JSON object")
            if result.get("stage") not in ("main", "test", "init"):
                continue
            if not isinstance(result.get("status", "unknown"), str) or not isinstance(result.get("passes", []), list):
                raise ValueError("invalid status or pass records")
        except (OSError, UnicodeError, ValueError) as exc:
            warnings.append(f"Cannot read run report {result_path}: {exc}")
            continue
        return {
            "stage": result["stage"],
            "status": result.get("status", "unknown"),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
            "journal": str(journal),
            "executed": any(
                isinstance(step, dict) and (step.get("pid") or "returncode" in step)
                for step in result.get("passes", [])
            ),
        }
    return None


def inspect_model_status(model: Path) -> dict:
    """Inspect existing evidence without launching processes or creating files."""
    model = model.expanduser().resolve()
    if not model.is_dir():
        raise RunnerError("Not a model workspace")
    warnings = []

    def controls(name, keys):
        path = model / name
        try:
            rows = control_occurrences(path.read_text())
        except (OSError, UnicodeError) as exc:
            warnings.append(f"Cannot read {name}: {exc}")
            return {}
        return {key: rows[key][0]["value"] for key in keys if len(rows.get(key, [])) == 1}

    parameters = controls("VADAT", ("TEFF", "LOGG", "RSTAR", "RMAX", "LSTAR", "MDOT", "VINF", "BETA"))
    dimensions = controls("MODEL_SPEC", ("ND", "NC", "NP", "NUM_BNDS", "NCF_MAX"))
    iteration_controls = controls("IN_ITS", ("NUM_ITS",))
    try:
        configured_iterations = int(iteration_controls["NUM_ITS"])
    except (KeyError, ValueError):
        configured_iterations = None
    try:
        restart = inspect_restart(model)
    except (OSError, UnicodeError, ValueError) as exc:
        restart = {"mode": "unknown", "pointer": None, "message": f"Checkpoint inspection unavailable: {exc}"}
    activity = inspect_model_activity(model)
    latest_run = _latest_native_run(model, warnings)
    evidence = [
        name for name in ("OUTGEN", "batch.log", "RVTJ", "MODEL", "MOD_SUM", "POINT1", "POINT2", "SCRTEMP")
        if (model / name).is_file() and (model / name).stat().st_size
    ]
    last_logged_iteration = None
    outgen = model / "OUTGEN"
    if outgen.is_file():
        try:
            with outgen.open(errors="replace") as handle:
                for line in handle:
                    match = re.search(r"Current great iteration count is\s+(\d+)", line)
                    if match:
                        last_logged_iteration = int(match[1])
        except OSError as exc:
            warnings.append(f"Cannot read OUTGEN iteration counters: {exc}")
    pointer = restart.get("pointer")
    return {
        "schema_version": 1,
        "kind": "status",
        "model": str(model),
        "name": model.name,
        "parameters": parameters,
        "dimensions": dimensions,
        "state": {
            "has_run": bool(evidence) or bool(latest_run and latest_run["executed"]),
            "evidence_files": evidence,
            "activity": activity,
            "main_result": diagnose_main_run(model),
            "latest_run": latest_run,
            "restart": restart,
            "saved_iterations": pointer["iterations"] if pointer else None,
            "last_logged_iteration": last_logged_iteration,
            "configured_iterations": configured_iterations,
        },
        "warnings": warnings,
    }
