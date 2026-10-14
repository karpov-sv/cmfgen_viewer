"""Explicit, journaled LTE workspace preparation using the viewer's implementation."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .workflow_permissions import mkdir_readable, open_readable
from .model_workflow import (
    ModelWorkflowError,
    _hydro_alignment_from_records,
    inspect_lte_hydro_workflow,
    prepare_lte_hydro_workspace,
)
from .runner_recipe import RunnerError


def build_preparation_plan(model: Path, *, template_root: Path | None = None) -> dict:
    model = model.expanduser().resolve()
    if not model.is_dir():
        raise RunnerError("Not a model workspace")
    template_root = template_root.expanduser().resolve() if template_root is not None else None
    try:
        state = inspect_lte_hydro_workflow(
            str(model.parent), model_relpath=model.name, template_root=str(template_root) if template_root is not None else None,
        )
    except ModelWorkflowError as exc:
        raise RunnerError(str(exc)) from exc
    errors = [] if state["prepare_allowed"] else [state["prepare_reason"]]
    if (model / ".cmfgen-runs").is_symlink():
        errors.append("Refusing symlinked run archive")
    sources = [model / name for name in ("VADAT", "MODEL_SPEC", "RVSIG_COL", "RVSIG_COL_OLD")]
    copies = [{"source": str(model / name), "destination": str(model / "lte" / name)}
              for name in ("VADAT", "MODEL_SPEC")]
    for item in state["template_files"]:
        if item["exists"]:
            source = Path(item["path"])
            sources.append(source)
            copies.append({"source": str(source), "destination": str(model / "lte" / item["name"]), "origin": item["origin"]})
    digests = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
               for path in sources}
    warnings = ["Review CON_R before running hydro; preparation preserves the template CON_R / REF_R ratio."]
    alignment = None
    hydro_source = next((Path(item["source"]) for item in copies
                         if Path(item["destination"]).name == "HYDRO_PARAMS"), None)
    if hydro_source is not None and (model / "VADAT").is_file():
        try:
            records = {}
            for name, path in (("VADAT", model / "VADAT"), ("HYDRO_PARAMS", hydro_source)):
                records[name] = {"contents": path.read_text(encoding="utf-8"), "digest": digests[str(path)]}
            alignment = _hydro_alignment_from_records(records)
            if not alignment["ready"]:
                warnings.append("HYDRO_PARAMS will retain template values: " + "; ".join(alignment["issues"]))
        except UnicodeError:
            warnings.append("HYDRO_PARAMS will retain template values: inputs are not UTF-8 text.")
    return {
        "schema_version": 1, "profile": "ostar-v1", "kind": "filesystem",
        "stage": "prepare-lte", "model": str(model), "cwd": str(model),
        "template_root": str(template_root) if template_root is not None else None, "copies": copies, "expected_digests": digests,
        "hydro_alignment": alignment,
        "backs_up_rvsig": (model / "RVSIG_COL").is_file() and not (model / "RVSIG_COL_OLD").exists(),
        "activity": state["activity"], "timeout": None,
        "passes": [{"id": "prepare-lte", "overrides": {}}],
        "warnings": warnings, "errors": errors, "ready": not errors,
        "scientific_acceptance": "not applicable", "launches_legacy_scripts": False,
    }


def run_preparation_plan(plan: dict, emit=None) -> dict:
    # Import only at execution time to avoid a circular runner dependency.
    from .runner import _json

    if not plan["ready"]:
        raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
    model = Path(plan["model"])
    root = model / ".cmfgen-runs"
    if root.is_symlink():
        raise RunnerError("Refusing symlinked run archive")
    mkdir_readable(root, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    journal = root / run_id
    mkdir_readable(journal)
    _json(journal / "plan.json", plan)
    record = {"id": "prepare-lte", "status": "running", "problems": []}
    result = {
        "run_id": run_id, "stage": "prepare-lte", "status": "running",
        "journal": str(journal), "passes": [record], "planned_passes": 1,
        "scientific_acceptance": "not applicable",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    def event(kind, **values):
        item = {"event": kind, "run_id": run_id, "time": datetime.now(timezone.utc).isoformat(), **values}
        with open_readable(journal / "events.jsonl", "a") as handle:
            handle.write(json.dumps(item) + "\n")
        if emit:
            emit(item)

    _json(journal / "result.json", result)
    event("stage_started", stage="prepare-lte")
    try:
        prepared = prepare_lte_hydro_workspace(
            str(model.parent), model_relpath=model.name,
            template_root=plan["template_root"], expected_digests=plan["expected_digests"],
        )
        result["preparation"] = {
            "workspace": str(model / "lte"), "hydro_initialized": prepared["hydro_initialized"],
            "hydro_initialization_issues": prepared["hydro_initialization_issues"],
        }
        record["warnings"] = prepared["hydro_initialization_issues"]
        record["status"] = result["status"] = "succeeded"
    except (ModelWorkflowError, OSError, UnicodeError) as exc:
        record["status"] = result["status"] = "failed"
        record["problems"] = [str(exc)]
    except Exception as exc:  # Preserve evidence of unexpected preparation failures.
        record["status"] = result["status"] = "runner_error"
        record["problems"] = [f"{type(exc).__name__}: {exc}"]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    _json(journal / "result.json", result)
    event("stage_finished", stage="prepare-lte", status=result["status"], problems=record["problems"])
    event("run_finished", stage="prepare-lte", status=result["status"], journal=str(journal))
    return result
