"""Plan the guarded LTE/hydro-to-main filesystem handoff."""

from __future__ import annotations

from pathlib import Path

from .model_workflow import (
    HYDRO_OUTPUT,
    LTE_OUTPUT,
    MAIN_STATE_FILES,
    ModelWorkflowError,
    _rvsig_generated_values,
    inspect_lte_hydro_workflow,
)
from .runner_recipe import RunnerError, snapshot


def build_promotion_plan(model: Path) -> dict[str, object]:
    """Build a read-only promotion plan; execution rechecks all web guards."""
    model = model.expanduser().resolve()
    if not model.is_dir():
        raise RunnerError("Not a model workspace")
    try:
        state = inspect_lte_hydro_workflow(
            str(model.parent),
            model_relpath=model.name,
        )
    except ModelWorkflowError as exc:
        raise RunnerError(str(exc)) from exc

    lte_dir = model / "lte"
    generated, _metadata = _rvsig_generated_values(lte_dir / HYDRO_OUTPUT)
    generated_rmax = generated.get("radius_ratio")
    errors: list[str] = []
    if state["promoted"]:
        errors.append(
            "LTE/hydro results already match the promoted model inputs; no promotion is needed."
        )
    elif not state["promotion_ready"]:
        activity = state.get("activity", {})
        if isinstance(activity, dict) and not activity.get("safe_to_modify", False):
            errors.append(str(activity.get("reason") or "Model activity is uncertain."))
        else:
            errors.append(
                "Fresh lte/ROSSELAND_LTE_TAB and lte/RVSIG_COL_NEW outputs "
                "are required before promotion."
            )
    if generated_rmax is None or generated_rmax <= 0:
        errors.append(
            "lte/RVSIG_COL_NEW does not report a valid inner-to-outer radius ratio."
        )

    source_names = ("VADAT", LTE_OUTPUT, HYDRO_OUTPUT)
    destination_names = (LTE_OUTPUT, HYDRO_OUTPUT, "RVSIG_COL", "VADAT")
    target_names = tuple(dict.fromkeys((*destination_names, *MAIN_STATE_FILES)))
    for name in target_names:
        path = model / name
        if path.is_symlink():
            errors.append(f"Refusing to modify symlinked model target: {name}")
        elif path.exists() and not path.is_file():
            errors.append(f"Refusing to modify non-regular model target: {name}")

    state_paths = [model / name for name in MAIN_STATE_FILES]
    input_paths = [lte_dir / name for name in source_names]
    input_paths.extend(model / name for name in destination_names)
    input_paths.extend(state_paths)
    input_paths = list(dict.fromkeys(input_paths))
    inputs = [snapshot(path) for path in input_paths]
    existing_state = [path.name for path in state_paths if path.is_file()]
    return {
        "schema_version": 1,
        "profile": "ostar-v1",
        "kind": "filesystem",
        "stage": "promote",
        "model": str(model),
        "cwd": str(model),
        "inputs": inputs,
        "sources": [f"lte/{name}" for name in source_names],
        "destinations": list(destination_names),
        "invalidates": existing_state,
        "synchronized_rmax": generated_rmax,
        "timeout": None,
        "passes": [{"id": "promote", "overrides": {}}],
        "warnings": [
            "Promotion accepts file integrity and freshness only; review the generated "
            "luminosity and radius ratio before running it."
        ],
        "errors": list(dict.fromkeys(errors)),
        "ready": not errors,
        "scientific_acceptance": "not assessed",
        "launches_legacy_scripts": False,
    }
