"""Shared model navigation context for folder, file, and workflow pages."""

from pathlib import Path

from .browser import is_model_directory, resolve_path
from .model_staging import is_sn_model_directory
from .spectrum_io import discover_final_spectrum_files


MODEL_PAGES = {
    "viewer.view", "viewer.spectrum", "viewer.model_parameters",
    "viewer.model_lte_hydro", "viewer.model_main_computation",
    "viewer.model_workflow_plan", "viewer.model_create_from_solution",
    "viewer.model_rename", "viewer.model_cleanup",
}


def model_navigation_context(config, endpoint, view_args):
    if endpoint not in MODEL_PAGES:
        return None
    requested = view_args.get("source_path", view_args.get("path", ""))
    base = Path(str(config.get("basepath", "."))).resolve()
    try:
        target = resolve_path(str(base), requested)
    except (FileNotFoundError, NotADirectoryError):
        return None
    candidate = target if target.is_dir() else target.parent
    model = None
    # Prefer the outer model over its LTE workspace, which can have its own
    # MODEL_SPEC/VADAT. Navigation always returns to the same parent model.
    while candidate.is_relative_to(base):
        if is_model_directory(candidate):
            model = candidate
        if candidate == base:
            break
        candidate = candidate.parent
    if model is None:
        return None
    active = {
        "viewer.spectrum": "spectrum", "viewer.model_parameters": "parameters",
        "viewer.model_lte_hydro": "lte", "viewer.model_main_computation": "main",
        "viewer.model_create_from_solution": "create", "viewer.model_rename": "rename",
        "viewer.model_cleanup": "cleanup",
    }.get(endpoint, "")
    if endpoint == "viewer.view" and target == model:
        active = "folder"
    elif endpoint == "viewer.model_workflow_plan":
        active = "lte" if view_args.get("scope") == "lte-hydro" else "main"
    return {
        "path": model.relative_to(base).as_posix(),
        "read_write": bool(config.get("read_write_enabled", False)),
        "supports_staging": not is_sn_model_directory(model),
        "has_spectrum": discover_final_spectrum_files(model) is not None,
        "active": active,
    }
