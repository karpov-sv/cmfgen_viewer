"""Plan the runner's recoverable model-cleanup stage."""

from __future__ import annotations

from pathlib import Path

from .model_activity import inspect_model_activity
from .model_staging import ModelStagingError, plan_model_cleanup
from .runner_recipe import RunnerError


def _human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def build_cleanup_plan(
    model: Path,
    *,
    selected_names: list[str] | None = None,
) -> dict[str, object]:
    """Return canonical cleanup candidates, optionally narrowed by name."""
    model = model.expanduser().resolve()
    if not model.is_dir():
        raise RunnerError("Not a model workspace")
    try:
        cleanup = plan_model_cleanup(str(model.parent), model_relpath=model.name)
    except ModelStagingError as exc:
        raise RunnerError(str(exc)) from exc

    available = {
        str(item["name"]): item
        for item in cleanup["entries"]
        if isinstance(item, dict)
    }
    errors: list[str] = []
    activity = inspect_model_activity(model)
    if not activity["safe_to_modify"]:
        errors.append(str(activity["reason"] or "Model activity is uncertain."))
    if selected_names:
        names = list(dict.fromkeys(str(name) for name in selected_names))
        missing = [name for name in names if name not in available]
        if missing:
            errors.append(
                "Not a current cleanup candidate: " + ", ".join(missing)
            )
        entries = [available[name] for name in names if name in available]
    else:
        entries = list(cleanup["entries"])
    if not entries:
        errors.append("No model cleanup candidates were found.")

    total_size = sum(int(item["size"]) for item in entries)
    return {
        "schema_version": 1,
        "profile": "ostar-v1",
        "kind": "filesystem",
        "stage": "cleanup",
        "model": str(model),
        "cwd": str(model),
        "entries": entries,
        "activity": activity,
        "selected_names": [str(item["name"]) for item in entries],
        "entry_count": len(entries),
        "total_size": total_size,
        "human_size": _human_size(total_size),
        "timeout": None,
        "passes": [{"id": "cleanup", "overrides": {}}],
        "warnings": [
            "Runner cleanup archives candidates in its run journal; inspect the plan's "
            "top-level file and symlink list before running it."
        ],
        "errors": errors,
        "ready": not errors,
        "scientific_acceptance": "not applicable",
        "launches_legacy_scripts": False,
    }
