"""Declarative contracts and side-effect-free previews of external workflows.

These plans describe the current workflow; they are not executable jobs. Legacy
shell actions remain explicitly opaque instead of being translated or sourced.
"""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
import shlex

from .browser import is_model_directory, resolve_path
from .control_files import control_occurrences
from .workflow_preflight import STAGE_INPUTS, inspect_stage_preflight


@dataclass(frozen=True)
class StageContract:
    id: str
    workspace: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    validation: tuple[str, ...]
    approval_required: bool = False


CONTRACTS = {
    "main": StageContract("main", ".", STAGE_INPUTS["main"] + ("GAMMAS_IN or GAMMAS", "*_IN"),
                          ("MOD_SUM", "RVTJ", "MODEL", "*OUT", "GAMMAS", "OUTGEN", "batch.log"),
                          ("No active process", "No fatal diagnostics", "Current MOD_SUM finalization marker and RVTJ",
                           "Scientific convergence review remains separate")),
    "lte": StageContract("lte", "lte", STAGE_INPUTS["lte"] + ("../batch.sh", "parent atomic-link includes"),
                         ("ROSSELAND_LTE_TAB", "OUTLTE", "ltebat.log"),
                         ("No active LTE process", "Fresh Rosseland output", "No current fatal LTE diagnostics")),
    "hydro": StageContract("hydro", "lte", STAGE_INPUTS["hydro"], ("RVSIG_COL_NEW", "WIND_HYD"),
                           ("No active hydro process", "Fresh structure output", "Review luminosity, depth count, and radius ratio"), True),
    "flux": StageContract("flux", "obs", STAGE_INPUTS["flux"] + ("../POP*",),
                          ("OBSFRAME → script-selected spectra", "OUT_FLUX", "batobs.log"),
                          ("No active CMF_FLUX process", "No fatal diagnostics", "All planned passes and current spectra present")),
}


def external_stage_command(model_dir: Path, stage: str) -> str:
    contract = CONTRACTS[stage]
    cwd = model_dir if contract.workspace == "." else model_dir / contract.workspace
    if stage == "hydro":
        command = 'set -o pipefail && "$cmfdist/exe/wind_hyd.exe" 2>&1 | tee WIND_HYD'
    else:
        command = {"main": "./batch.sh", "lte": "./ltebat.sh", "flux": "./batobs.sh"}[stage]
    return f"cd {shlex.quote(str(cwd))} && {command}"


def _input_record(path: Path) -> dict:
    record = {"path": str(path), "exists": path.is_file(), "symlink": path.is_symlink()}
    try:
        info = path.stat()
        record.update(size=info.st_size, modified_ns=info.st_mtime_ns)
        if path.is_file() and info.st_size <= 2 * 1024 * 1024:
            record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            record["sha256"] = None
    except OSError:
        record["exists"] = False
    return record


def build_workflow_plan(basepath: str, *, model_relpath: str, scope: str, config: dict | None = None) -> dict:
    if scope not in {"main", "lte-hydro", "flux"}:
        raise ValueError("Unknown workflow plan scope")
    relative = Path(model_relpath)
    if relative.is_absolute() or ".." in relative.parts or model_relpath in {"", ".", "/"}:
        raise ValueError("A model under the configured root is required")
    try:
        model_dir = resolve_path(basepath, model_relpath)
    except FileNotFoundError as exc:
        raise ValueError("Model directory was not found") from exc
    if not is_model_directory(model_dir):
        raise ValueError("Not a recognized model directory")
    steps = []
    if scope == "lte-hydro":
        from .model_workflow import inspect_lte_hydro_workflow
        state = inspect_lte_hydro_workflow(basepath, model_relpath=model_relpath, config=config)
        steps.append({"id": "prepare", "kind": "filesystem", "depends_on": [],
                      "ready": state["prepare_allowed"] or state["prepared"], "approval_required": False,
                      "note": state["prepare_reason"],
                      "changes": [{"action": "create_workspace", "destination": "lte/", "policy": "never merge or overwrite"},
                                  {"action": "copy", "sources": ["VADAT", "MODEL_SPEC", "clean.sh"], "destination": "lte/"},
                                  {"action": "copy_templates", "sources": state["template_files"], "destination": "lte/"},
                                  {"action": "checkpoint_if_present", "source": "RVSIG_COL", "destination": "RVSIG_COL_OLD", "policy": "preserve an existing checkpoint"}],
                      "command": None, "issues": []})
        stages = ["lte", "hydro"]
    elif scope == "main":
        from .model_run_workflow import inspect_main_model_workflow
        state = inspect_main_model_workflow(basepath, model_relpath=model_relpath, config=config)
        stages = ["main"]
        try:
            if re.search(r"^\s*(?:tcsh\s+)?\./batobs\.sh\b", (model_dir / "batch.sh").read_text(), re.M):
                stages.append("flux")
        except (OSError, UnicodeError):
            pass
    else:
        state = {}
        stages = ["flux"]
    for stage in stages:
        contract = CONTRACTS[stage]
        preflight = inspect_stage_preflight(model_dir, stage, config=config)
        cwd = Path(preflight["cwd"])
        prior = steps[-1]["id"] if steps else None
        inputs = [_input_record(cwd / name) for name in STAGE_INPUTS[stage]]
        # Include local control fragments and actual restart inputs, not only
        # entry-point scripts. Atomic tables remain dependency checks, not bulk
        # content hashing of the installation.
        snapshot_paths = {item["path"] for item in inputs}
        extra_paths = [Path(source["path"]) for source in preflight["script_dependencies"]["sources"]
                       if source["path"] and Path(source["path"]).resolve().is_relative_to(model_dir)]
        if stage == "main":
            extra_paths.extend(model_dir.glob("*_IN"))
            extra_paths.extend(model_dir / name for name in ("GAMMAS_IN", "GAMMAS", "RVSIG_COL", "ROSSELAND_LTE_TAB")
                               if (model_dir / name).is_file())
        for path in sorted(set(extra_paths)):
            if str(path) not in snapshot_paths:
                inputs.append(_input_record(path))
                snapshot_paths.add(str(path))
        changes = [{"action": "run_external_program" if stage == "hydro" else "run_legacy_script",
                    "outputs": list(contract.outputs), "retention": "legacy script policy; may overwrite logs and remove scratch files"}]
        links = preflight["script_dependencies"]["links"]
        changes.extend({"action": "symlink", **link} for link in links)
        issues = list(preflight["issues"])
        if stage == "main":
            issues = state["preflight"]["issues"]
        step = {**asdict(contract), "kind": "external", "cwd": str(cwd),
                "depends_on": [prior] if prior else [], "command": external_stage_command(model_dir, stage),
                "executable": preflight["executable"], "environment": preflight["environment"],
                "ready": not any(i["severity"] == "error" for i in issues), "issues": issues,
                "verification_complete": False,
                "input_snapshot": inputs, "changes": changes,
                "script_dependencies": preflight["script_dependencies"],
                "opaque_shell_effects": stage != "hydro",
                "resources": {"free_bytes": preflight["free_bytes"], "threads": "legacy script/environment; not overridden"}}
        if stage == "flux" and scope == "main":
            step["invoked_by"] = "main"
            step["command"] = None
            step["note"] = "Included by batch.sh; do not launch again. Legacy scripts may continue after main failure."
        if stage == "main":
            step["ready"] = bool(state["ready"])
            step["missing_prerequisites"] = state["missing"]
        if stage == "hydro":
            try:
                controls = control_occurrences((cwd / "MODEL_SPEC").read_text())
                depth = int(controls["ND"][0]["value"])
            except (OSError, ValueError, KeyError, IndexError):
                depth = None
            step["stdin"] = {"mode": "interactive", "suggested_answers": ["/null", "e", depth, "default or reviewed maximum optical depth"],
                             "note": "Suggestions only, not a prompt automation protocol. Confirm against this executable and model."}
        if scope == "lte-hydro":
            step["ready"] = bool(state[f"{stage}_ready"])
        steps.append(step)
    if scope == "lte-hydro":
        steps.append({"id": "review-promote", "kind": "filesystem", "depends_on": ["hydro"],
                      "ready": state["promotion_ready"], "approval_required": True,
                      "validation": ["No active process in the model tree", "Fresh LTE/hydro outputs, no fatal diagnostics", "User reviewed luminosity and generated radius ratio"],
                      "changes": [{"action": "backup_then_atomic_copy", "source": f"lte/{source}", "destination": target}
                                  for source, target in (("ROSSELAND_LTE_TAB", "ROSSELAND_LTE_TAB"),
                                                         ("RVSIG_COL_NEW", "RVSIG_COL_NEW"), ("RVSIG_COL_NEW", "RVSIG_COL"), ("VADAT", "VADAT"))]
                                 + [{"action": "mark_solution_stale_and_invalidate_summary"}], "command": None, "issues": []})
    return {"schema_version": 1, "scope": scope, "model_path": str(model_dir),
            "model_relpath": model_relpath, "execution_available": False, "steps": steps,
            "limitations": ["Read-only preview: no programs, shell scripts, or filesystem actions are executed.",
                            "Literal shell links and script text are inspected, not a complete shell interpreter. Custom/dynamic effects require manual review; readiness means no known blocker, not full verification.",
                            "Legacy commands retain their existing failure and cleanup behavior; this preview does not make them fail-safe.",
                            "Input hashes cover files up to 2 MiB; larger products have metadata only. This is not an immutable run record."]}
