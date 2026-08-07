"""State inspection for externally executed main CMFGEN model runs."""

from __future__ import annotations

from pathlib import Path
import shlex

from .browser import is_model_directory, resolve_path
from .model_editor import model_inputs_modified_since_solution


class ModelRunWorkflowError(ValueError):
    """Raised when a main-model workflow target is invalid."""


MAIN_REQUIRED_FILES = ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS")
MAIN_RESULT_FILES = ("MOD_SUM", "OUTGEN", "batch.log", "MODEL", "RVTJ")


def _available_file(path: Path) -> bool:
    return path.is_file()


def _resolve_model(basepath: str, model_relpath: str) -> tuple[str, Path]:
    text = str(model_relpath).strip()
    rel = Path(text)
    if not text or text in {".", "/"} or rel.is_absolute() or ".." in rel.parts:
        raise ModelRunWorkflowError("Model path must remain under the configured root.")
    normalized = Path(*(part for part in rel.parts if part not in {"", "."})).as_posix()
    try:
        model_dir = resolve_path(basepath, normalized)
    except FileNotFoundError as exc:
        raise ModelRunWorkflowError("Model directory was not found.") from exc
    if not is_model_directory(model_dir):
        raise ModelRunWorkflowError("Path is not a recognized CMFGEN model directory.")
    return normalized, model_dir


def _file_record(path: Path) -> dict[str, object]:
    exists = _available_file(path)
    modified_ns = 0
    size = 0
    if exists:
        try:
            info = path.stat()
            modified_ns = info.st_mtime_ns
            size = info.st_size
        except OSError:
            exists = False
    return {
        "name": path.name,
        "path": str(path),
        "exists": exists,
        "modified_ns": modified_ns,
        "size": size,
    }


def inspect_main_model_workflow(basepath: str, *, model_relpath: str) -> dict[str, object]:
    normalized, model_dir = _resolve_model(basepath, model_relpath)
    prerequisites = [_file_record(model_dir / name) for name in MAIN_REQUIRED_FILES]
    gamma_candidates = (model_dir / "GAMMAS_IN", model_dir / "GAMMAS")
    gamma_ready = any(_available_file(path) for path in gamma_candidates)
    prerequisites.append(
        {
            "name": "GAMMAS_IN or GAMMAS",
            "path": " / ".join(str(path) for path in gamma_candidates),
            "exists": gamma_ready,
            "modified_ns": max(
                (path.stat().st_mtime_ns for path in gamma_candidates if _available_file(path)),
                default=0,
            ),
            "size": 0,
        }
    )
    lte_handoff_required = (model_dir / "lte").is_dir()
    if lte_handoff_required:
        prerequisites.extend(
            _file_record(model_dir / name) for name in ("RVSIG_COL", "ROSSELAND_LTE_TAB")
        )
    missing = [str(item["name"]) for item in prerequisites if not item["exists"]]
    ready = not missing

    dependency_paths = [model_dir / name for name in MAIN_REQUIRED_FILES]
    dependency_paths.extend(path for path in gamma_candidates if _available_file(path))
    try:
        dependency_paths.extend(
            path
            for path in model_dir.iterdir()
            if path.name.endswith("_IN") and _available_file(path)
        )
    except OSError:
        pass
    dependency_paths.extend(
        path
        for path in (model_dir / "RVSIG_COL", model_dir / "ROSSELAND_LTE_TAB")
        if _available_file(path)
    )
    try:
        dependency_mtime = max(
            (path.stat().st_mtime_ns for path in dependency_paths if _available_file(path)),
            default=0,
        )
    except OSError:
        dependency_mtime = 0

    results = [_file_record(model_dir / name) for name in MAIN_RESULT_FILES]
    result_by_name = {str(item["name"]): item for item in results}
    mod_sum = result_by_name["MOD_SUM"]
    marker_stale = model_inputs_modified_since_solution(model_dir)
    mod_sum_fresh = bool(
        ready
        and mod_sum["exists"]
        and int(mod_sum["modified_ns"]) >= dependency_mtime
        and not marker_stale
    )
    if not mod_sum["exists"]:
        result_status = "missing"
    elif mod_sum_fresh:
        result_status = "current"
    else:
        result_status = "stale"
    return {
        "model_relpath": normalized,
        "model_path": str(model_dir),
        "prerequisites": prerequisites,
        "missing": missing,
        "ready": ready,
        "command": f"cd {shlex.quote(str(model_dir))} && ./batch.sh",
        "results": results,
        "mod_sum_fresh": mod_sum_fresh,
        "result_status": result_status,
        "marker_stale": marker_stale,
        "lte_handoff_required": lte_handoff_required,
    }
