"""Create a fresh non-SN CMFGEN model from an existing model solution."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import tempfile
from threading import Lock

from .browser import is_model_directory, resolve_path


MODEL_CREATE_REQUIRED_FILES = ("batch.sh", "IN_ITS", "VADAT", "MODEL_SPEC", "GAMMAS")
MODEL_CREATE_OPTIONAL_FILES = (
    "batch_ins.sh",
    "RVSIG_COL",
    "HYDRO_DEFAULTS",
    "ROSSELAND_LTE_TAB",
    "RDINR",
    "ADJUST_R_DEFAULTS",
    "IT_SPECIFIER",
    "arnaud_rothenflug.dat",
)
MODEL_CREATE_SN_MARKERS = {
    "SN_HYDRO_DATA",
    "SN_HYDRO_FOR_NEXT_MODEL",
    "JH_AT_CURRENT_TIME",
    "JH_AT_OLD_TIME",
    "CUR_MODEL_DATA",
    "OLD_MODEL_DATA",
    "NUC_DECAY_DATA",
}
MODEL_CREATE_LOCK = Lock()


class ModelStagingError(ValueError):
    """Raised when a model cannot be staged safely or completely."""


def _human_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def is_sn_model_directory(model_dir: Path) -> bool:
    try:
        names = {entry.name.upper() for entry in model_dir.iterdir()}
    except OSError:
        return False
    return bool(names & MODEL_CREATE_SN_MARKERS)


def _normalize_relpath(raw_path: str, *, label: str) -> str:
    text = str(raw_path).strip()
    rel = Path(text)
    if not text or text in {".", "/"}:
        raise ModelStagingError(f"{label} is required.")
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise ModelStagingError(f"{label} must be a relative path without '..' components.")
    parts = [part for part in rel.parts if part not in {"", "."}]
    if not parts:
        raise ModelStagingError(f"{label} is required.")
    return Path(*parts).as_posix()


def _model_source(basepath: str, source_relpath: str) -> tuple[str, Path]:
    normalized = _normalize_relpath(source_relpath, label="Source model path")
    try:
        source = resolve_path(basepath, normalized)
    except FileNotFoundError as exc:
        raise ModelStagingError("Source model directory was not found.") from exc
    if not is_model_directory(source):
        raise ModelStagingError("Source path is not a recognized CMFGEN model directory.")
    if is_sn_model_directory(source):
        raise ModelStagingError("Creating a model from an SN solution is not supported yet.")
    return normalized, source


def _model_destination(
    basepath: str,
    *,
    source_relpath: str,
    destination_relpath: str,
) -> tuple[str, Path]:
    normalized = _normalize_relpath(destination_relpath, label="Destination model path")
    source_parts = Path(source_relpath).parts
    destination_parts = Path(normalized).parts
    if destination_parts == source_parts:
        raise ModelStagingError("Destination must differ from the source model.")
    if destination_parts[: len(source_parts)] == source_parts:
        raise ModelStagingError("Destination cannot be inside the source model directory.")

    destination = Path(basepath).expanduser().resolve().joinpath(*destination_parts)
    if destination.exists() or destination.is_symlink():
        raise ModelStagingError("Destination already exists; existing directories are never merged or overwritten.")
    if not destination.parent.is_dir():
        raise ModelStagingError("Destination parent directory does not exist.")
    return normalized, destination


def _copy_entry(source: Path, *, destination_name: str, category: str) -> dict[str, object]:
    try:
        file_stat = source.stat()
    except OSError as exc:
        raise ModelStagingError(f"Could not inspect required source file '{source.name}': {exc}") from exc
    if not source.is_file():
        raise ModelStagingError(f"Source entry '{source.name}' is not a regular file.")
    return {
        "source_name": source.name,
        "destination_name": destination_name,
        "category": category,
        "size": int(file_stat.st_size),
        "human_size": _human_size(int(file_stat.st_size)),
        "renamed": source.name != destination_name,
    }


def plan_model_from_solution(
    basepath: str,
    *,
    source_relpath: str,
    destination_relpath: str,
) -> dict[str, object]:
    source_relpath, source = _model_source(basepath, source_relpath)
    destination_relpath, destination = _model_destination(
        basepath,
        source_relpath=source_relpath,
        destination_relpath=destination_relpath,
    )

    entries: list[dict[str, object]] = []
    missing_required: list[str] = []
    destination_names: set[str] = set()

    for name in MODEL_CREATE_REQUIRED_FILES:
        source_file = source / name
        if not source_file.is_file():
            missing_required.append(name)
            continue
        destination_name = "GAMMAS_IN" if name == "GAMMAS" else name
        entry = _copy_entry(source_file, destination_name=destination_name, category="Required")
        entries.append(entry)
        destination_names.add(destination_name)

    try:
        output_files = sorted(
            (entry for entry in source.iterdir() if entry.name.endswith("OUT") and entry.is_file()),
            key=lambda entry: entry.name.lower(),
        )
    except OSError as exc:
        raise ModelStagingError(f"Could not list source model files: {exc}") from exc
    if not output_files:
        missing_required.append("*OUT")
    for source_file in output_files:
        destination_name = f"{source_file.name[:-3]}_IN"
        if destination_name in destination_names:
            raise ModelStagingError(f"Multiple source files would create '{destination_name}'.")
        entries.append(
            _copy_entry(source_file, destination_name=destination_name, category="Solution output → input")
        )
        destination_names.add(destination_name)

    for name in MODEL_CREATE_OPTIONAL_FILES:
        source_file = source / name
        if not source_file.is_file():
            continue
        if name in destination_names:
            raise ModelStagingError(f"Multiple source files would create '{name}'.")
        entries.append(_copy_entry(source_file, destination_name=name, category="Optional support"))
        destination_names.add(name)

    category_order = {"Required": 0, "Solution output → input": 1, "Optional support": 2}
    entries.sort(
        key=lambda item: (
            category_order.get(str(item["category"]), 99),
            str(item["destination_name"]).lower(),
        )
    )
    total_size = sum(int(item["size"]) for item in entries)
    return {
        "source_relpath": source_relpath,
        "source_path": str(source),
        "destination_relpath": destination_relpath,
        "destination_path": str(destination),
        "resolved_destination_path": str(destination.resolve()),
        "entries": entries,
        "entry_count": len(entries),
        "total_size": total_size,
        "human_size": _human_size(total_size),
        "missing_required": missing_required,
        "ready": not missing_required,
    }


def create_model_from_solution(
    basepath: str,
    *,
    source_relpath: str,
    destination_relpath: str,
) -> dict[str, object]:
    with MODEL_CREATE_LOCK:
        plan = plan_model_from_solution(
            basepath,
            source_relpath=source_relpath,
            destination_relpath=destination_relpath,
        )
        missing = plan.get("missing_required")
        if isinstance(missing, list) and missing:
            raise ModelStagingError(f"Source model is missing required files: {', '.join(map(str, missing))}.")

        source = Path(str(plan["source_path"]))
        destination = Path(str(plan["destination_path"]))
        staging_path: Path | None = None
        try:
            staging_path = Path(tempfile.mkdtemp(prefix=".cmfgen-create-", dir=str(destination.parent)))
            staging_path.chmod(stat.S_IMODE(source.stat().st_mode))
            entries = plan.get("entries")
            if not isinstance(entries, list):
                raise ModelStagingError("Model copy plan is invalid.")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ModelStagingError("Model copy plan contains an invalid entry.")
                source_file = source / str(entry["source_name"])
                destination_file = staging_path / str(entry["destination_name"])
                shutil.copy2(source_file, destination_file, follow_symlinks=True)

            if destination.exists() or destination.is_symlink():
                raise ModelStagingError(
                    "Destination appeared while the model was being copied; nothing was overwritten."
                )
            os.rename(staging_path, destination)
            staging_path = None
        except ModelStagingError:
            raise
        except OSError as exc:
            raise ModelStagingError(f"Could not create model: {exc}") from exc
        finally:
            if staging_path is not None and staging_path.exists():
                shutil.rmtree(staging_path)
        return plan
