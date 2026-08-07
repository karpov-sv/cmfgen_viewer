"""Lossless, allowlisted editing of CMFGEN model control files."""

from __future__ import annotations

from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from .browser import is_model_directory, resolve_path
from .model_staging import MODEL_WRITE_LOCK
from .parsers.extended_text import KEYWORD_ROW_RE


MODEL_PARAMETER_MAX_BYTES = 512 * 1024
MODEL_INPUT_MODIFIED_MARKER = ".cmfgen-viewer-input-modified.json"
MODEL_EDITOR_BACKUP_DIR = ".cmfgen-viewer-backups"

EDITABLE_MODEL_FILES: dict[str, dict[str, object]] = {
    "VADAT": {
        "label": "VADAT",
        "group": "Core controls",
        "description": "Main physics, structure, abundance, and run controls.",
        "required": True,
        "affects_solution": True,
    },
    "MODEL_SPEC": {
        "label": "MODEL_SPEC",
        "group": "Core controls",
        "description": "Grid dimensions, limits, and included ion stages.",
        "required": True,
        "affects_solution": True,
    },
    "IN_ITS": {
        "label": "IN_ITS",
        "group": "Core controls",
        "description": "Iteration counts and automatic iteration controls.",
        "required": True,
        "affects_solution": True,
    },
    "HYDRO_DEFAULTS": {
        "label": "HYDRO_DEFAULTS",
        "group": "Optional controls",
        "description": "Hydrostatic iteration defaults and counters.",
        "required": False,
        "affects_solution": True,
    },
    "ADJUST_R_DEFAULTS": {
        "label": "ADJUST_R_DEFAULTS",
        "group": "Optional controls",
        "description": "Radius-grid adjustment controls.",
        "required": False,
        "affects_solution": True,
    },
    "IT_SPECIFIER": {
        "label": "IT_SPECIFIER",
        "group": "Optional controls",
        "description": "Per-iteration override controls.",
        "required": False,
        "affects_solution": True,
    },
    "GAMRAY_PARAMS": {
        "label": "GAMRAY_PARAMS",
        "group": "Optional controls",
        "description": "Gamma-ray transport controls.",
        "required": False,
        "affects_solution": True,
    },
    "CMF_FLUX_PARAM": {
        "label": "CMF_FLUX_PARAM",
        "group": "Spectrum controls",
        "description": "Top-level CMF_FLUX controls when kept beside the model.",
        "required": False,
        "affects_solution": False,
    },
    "obs/CMF_FLUX_PARAM": {
        "label": "obs/CMF_FLUX_PARAM",
        "group": "Spectrum controls",
        "description": "CMF_FLUX spectrum and line-profile controls.",
        "required": False,
        "affects_solution": False,
    },
}


class ModelEditorError(ValueError):
    """Raised when an editor request is unsafe, stale, or invalid."""


class ConcurrentModelEditError(ModelEditorError):
    """Raised when the file changed after the editor loaded it."""


def _normalize_model_relpath(raw_path: str) -> str:
    text = str(raw_path).strip()
    relpath = Path(text)
    if not text or text in {".", "/"}:
        raise ModelEditorError("Model path is required.")
    if relpath.is_absolute() or any(part == ".." for part in relpath.parts):
        raise ModelEditorError("Model path must remain under the configured root.")
    parts = [part for part in relpath.parts if part not in {"", "."}]
    if not parts:
        raise ModelEditorError("Model path is required.")
    return Path(*parts).as_posix()


def _resolve_model(basepath: str, model_relpath: str) -> tuple[str, Path]:
    normalized = _normalize_model_relpath(model_relpath)
    try:
        model_dir = resolve_path(basepath, normalized)
    except FileNotFoundError as exc:
        raise ModelEditorError("Model directory was not found.") from exc
    if not is_model_directory(model_dir):
        raise ModelEditorError("Path is not a recognized CMFGEN model directory.")
    return normalized, model_dir


def _file_policy(file_relpath: str) -> tuple[str, dict[str, object]]:
    raw_path = str(file_relpath).strip()
    relative = Path(raw_path)
    if not raw_path or relative.is_absolute() or any(part == ".." for part in relative.parts):
        raise ModelEditorError("Editable file path is invalid.")
    normalized = Path(*(part for part in relative.parts if part not in {"", "."})).as_posix()
    policy = EDITABLE_MODEL_FILES.get(normalized)
    if policy is None:
        raise ModelEditorError("This file is not in the editable model-control allowlist.")
    return normalized, policy


def _resolve_editable_file(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
) -> tuple[str, Path, str, Path, dict[str, object]]:
    normalized_model, model_dir = _resolve_model(basepath, model_relpath)
    normalized_file, policy = _file_policy(file_relpath)
    target = model_dir.joinpath(*Path(normalized_file).parts)
    if not target.exists():
        raise ModelEditorError(f"Editable control file '{normalized_file}' was not found.")
    if target.is_symlink() or not target.is_file():
        raise ModelEditorError("Only regular, non-symlinked control files may be edited.")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise ModelEditorError(f"Could not inspect control file: {exc}") from exc
    if size > MODEL_PARAMETER_MAX_BYTES:
        raise ModelEditorError(
            f"Control file is larger than the {MODEL_PARAMETER_MAX_BYTES // 1024} KB editor limit."
        )
    return normalized_model, model_dir, normalized_file, target, policy


def _decode_text(payload: bytes) -> str:
    if b"\x00" in payload:
        raise ModelEditorError("Binary files cannot be edited here.")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ModelEditorError("Control file is not valid UTF-8 text.") from exc


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _newline_style(payload: bytes) -> str:
    if b"\r\n" in payload:
        return "crlf"
    if b"\r" in payload:
        return "cr"
    return "lf"


def _encode_submitted_text(contents: str, *, newline_style: str) -> bytes:
    normalized = str(contents).replace("\r\n", "\n").replace("\r", "\n")
    if newline_style == "crlf":
        normalized = normalized.replace("\n", "\r\n")
    elif newline_style == "cr":
        normalized = normalized.replace("\n", "\r")
    payload = normalized.encode("utf-8")
    if len(payload) > MODEL_PARAMETER_MAX_BYTES:
        raise ModelEditorError(
            f"Edited content is larger than the {MODEL_PARAMETER_MAX_BYTES // 1024} KB editor limit."
        )
    if b"\x00" in payload:
        raise ModelEditorError("Edited content contains a NUL byte.")
    return payload


def control_file_warnings(contents: str) -> list[str]:
    warnings: list[str] = []
    keys: dict[str, list[int]] = {}
    malformed: list[int] = []
    for line_number, line in enumerate(contents.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match is None:
            malformed.append(line_number)
            continue
        key = match.group(2)
        keys.setdefault(key, []).append(line_number)

    if malformed:
        shown = ", ".join(map(str, malformed[:12]))
        suffix = "…" if len(malformed) > 12 else ""
        warnings.append(f"Unrecognized non-comment control lines: {shown}{suffix}.")
    duplicates = [(key, lines) for key, lines in keys.items() if len(lines) > 1]
    if duplicates:
        shown = ", ".join(f"{key} ({'/'.join(map(str, lines))})" for key, lines in duplicates[:8])
        suffix = "…" if len(duplicates) > 8 else ""
        warnings.append(f"Duplicate control keys: {shown}{suffix}.")
    if not keys and contents.strip():
        warnings.append("No bracketed CMFGEN control keys were recognized.")
    return warnings


def _file_record(
    *,
    model_relpath: str,
    model_dir: Path,
    file_relpath: str,
    target: Path,
    policy: dict[str, object],
    payload: bytes,
) -> dict[str, object]:
    stat_result = target.stat()
    contents = _decode_text(payload)
    return {
        **policy,
        "model_relpath": model_relpath,
        "model_path": str(model_dir),
        "file_relpath": file_relpath,
        "path": str(target),
        "contents": contents,
        "digest": _digest(payload),
        "newline_style": _newline_style(payload),
        "size": len(payload),
        "modified_ns": stat_result.st_mtime_ns,
        "warnings": control_file_warnings(contents),
    }


def list_model_parameter_files(basepath: str, *, model_relpath: str) -> dict[str, object]:
    normalized_model, model_dir = _resolve_model(basepath, model_relpath)
    files: list[dict[str, object]] = []
    for file_relpath, policy in EDITABLE_MODEL_FILES.items():
        target = model_dir.joinpath(*Path(file_relpath).parts)
        exists = target.exists() or target.is_symlink()
        is_symlink = target.is_symlink()
        editable = exists and target.is_file() and not is_symlink
        size = 0
        if editable:
            try:
                size = int(target.stat().st_size)
            except OSError:
                editable = False
            if size > MODEL_PARAMETER_MAX_BYTES:
                editable = False
        files.append(
            {
                **policy,
                "file_relpath": file_relpath,
                "path": str(target),
                "exists": exists,
                "is_symlink": is_symlink,
                "editable": editable,
                "size": size,
            }
        )
    return {
        "model_relpath": normalized_model,
        "model_path": str(model_dir),
        "files": files,
        "editable_count": sum(1 for item in files if item["editable"]),
    }


def load_model_parameter_file(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
) -> dict[str, object]:
    normalized_model, model_dir, normalized_file, target, policy = _resolve_editable_file(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
    )
    try:
        payload = target.read_bytes()
    except OSError as exc:
        raise ModelEditorError(f"Could not read control file: {exc}") from exc
    return _file_record(
        model_relpath=normalized_model,
        model_dir=model_dir,
        file_relpath=normalized_file,
        target=target,
        policy=policy,
        payload=payload,
    )


def list_model_parameter_checkpoints(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
) -> list[dict[str, object]]:
    _, model_dir, normalized_file, target, _ = _resolve_editable_file(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
    )
    relative_file = Path(normalized_file)
    backup_dir = model_dir / MODEL_EDITOR_BACKUP_DIR / relative_file.parent
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        return []

    checkpoints: list[dict[str, object]] = []
    prefix = f"{target.name}."
    try:
        candidates = list(backup_dir.iterdir())
    except OSError as exc:
        raise ModelEditorError(f"Could not list editor checkpoints: {exc}") from exc
    for candidate in candidates:
        if not candidate.name.startswith(prefix) or not candidate.name.endswith(".bak"):
            continue
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            stat_result = candidate.stat()
        except OSError:
            continue
        if stat_result.st_size > MODEL_PARAMETER_MAX_BYTES:
            continue
        modified = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
        checkpoints.append(
            {
                "name": candidate.name,
                "backup_relpath": candidate.relative_to(model_dir).as_posix(),
                "size": int(stat_result.st_size),
                "modified_ns": stat_result.st_mtime_ns,
                "modified_display": modified.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }
        )
    checkpoints.sort(key=lambda item: int(item["modified_ns"]), reverse=True)
    return checkpoints


def load_model_parameter_checkpoint(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    checkpoint_name: str,
) -> dict[str, object]:
    name = str(checkpoint_name).strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ModelEditorError("Checkpoint selection is invalid.")
    checkpoints = list_model_parameter_checkpoints(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
    )
    checkpoint = next((item for item in checkpoints if item["name"] == name), None)
    if checkpoint is None:
        raise ModelEditorError("Checkpoint was not found for this control file.")
    _, model_dir = _resolve_model(basepath, model_relpath)
    checkpoint_path = model_dir.joinpath(*Path(str(checkpoint["backup_relpath"])).parts)
    if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
        raise ModelEditorError("Checkpoint is no longer a regular file.")
    try:
        payload = checkpoint_path.read_bytes()
    except OSError as exc:
        raise ModelEditorError(f"Could not read editor checkpoint: {exc}") from exc
    contents = _decode_text(payload)
    return {
        **checkpoint,
        "contents": contents,
        "digest": _digest(payload),
        "warnings": control_file_warnings(contents),
    }


def _verified_edit_payload(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    contents: str,
) -> tuple[dict[str, object], bytes]:
    record = load_model_parameter_file(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
    )
    if not expected_digest or str(record["digest"]) != str(expected_digest):
        raise ConcurrentModelEditError(
            "This file changed after the editor loaded it. Reload before reviewing or saving your changes."
        )
    proposed = _encode_submitted_text(contents, newline_style=str(record["newline_style"]))
    return record, proposed


def review_model_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    contents: str,
) -> dict[str, object]:
    record, proposed = _verified_edit_payload(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        contents=contents,
    )
    current_text = str(record["contents"])
    proposed_text = _decode_text(proposed)
    diff_lines: list[dict[str, str]] = []
    for line in difflib.unified_diff(
        current_text.splitlines(),
        proposed_text.splitlines(),
        fromfile=f"{record['file_relpath']} (current)",
        tofile=f"{record['file_relpath']} (proposed)",
        lineterm="",
    ):
        kind = "context"
        if line.startswith("+++") or line.startswith("---"):
            kind = "header"
        elif line.startswith("@@"):
            kind = "range"
        elif line.startswith("+"):
            kind = "added"
        elif line.startswith("-"):
            kind = "removed"
        diff_lines.append({"text": line, "kind": kind})
    return {
        "file": record,
        "contents": proposed_text,
        "proposed_digest": _digest(proposed),
        "changed": _digest(proposed) != str(record["digest"]),
        "diff_lines": diff_lines,
        "warnings": control_file_warnings(proposed_text),
    }


def _write_backup(model_dir: Path, file_relpath: str, payload: bytes, digest: str) -> str:
    source_relpath = Path(file_relpath)
    backup_dir = model_dir / MODEL_EDITOR_BACKUP_DIR / source_relpath.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_name = f"{source_relpath.name}.{timestamp}.{digest[:12]}.bak"
    backup_path = backup_dir / backup_name
    try:
        with backup_path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ModelEditorError(f"Could not create editor backup: {exc}") from exc
    return backup_path.relative_to(model_dir).as_posix()


def _atomic_replace(target: Path, payload: bytes, *, mode: int) -> None:
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".cmfgen-edit-", dir=str(target.parent))
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, target)
        temporary_path = None
    except OSError as exc:
        raise ModelEditorError(f"Could not save control file: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _write_modified_marker(model_dir: Path, *, file_relpath: str, backup_relpath: str) -> str:
    marker = model_dir / MODEL_INPUT_MODIFIED_MARKER
    payload = json.dumps(
        {
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "file": file_relpath,
            "backup": backup_relpath,
        },
        sort_keys=True,
    ).encode("utf-8")
    _atomic_replace(marker, payload, mode=0o600)
    return marker.name


def save_model_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    contents: str,
) -> dict[str, object]:
    with MODEL_WRITE_LOCK:
        record, proposed = _verified_edit_payload(
            basepath,
            model_relpath=model_relpath,
            file_relpath=file_relpath,
            expected_digest=expected_digest,
            contents=contents,
        )
        target = Path(str(record["path"]))
        current = target.read_bytes()
        if _digest(current) != str(expected_digest):
            raise ConcurrentModelEditError(
                "This file changed while it was being saved. Reload before trying again."
            )
        if proposed == current:
            raise ModelEditorError("No changes were made.")
        try:
            mode = stat.S_IMODE(target.stat().st_mode)
        except OSError as exc:
            raise ModelEditorError(f"Could not inspect control-file permissions: {exc}") from exc
        backup_relpath = _write_backup(
            Path(str(record["model_path"])),
            str(record["file_relpath"]),
            current,
            str(record["digest"]),
        )
        _atomic_replace(target, proposed, mode=mode)
        marker = ""
        marker_error = ""
        if bool(record.get("affects_solution", False)):
            try:
                marker = _write_modified_marker(
                    Path(str(record["model_path"])),
                    file_relpath=str(record["file_relpath"]),
                    backup_relpath=backup_relpath,
                )
            except ModelEditorError as exc:
                marker_error = str(exc)
    return {
        **record,
        "new_digest": _digest(proposed),
        "backup_relpath": backup_relpath,
        "modified_marker": marker,
        "marker_error": marker_error,
    }


def model_inputs_modified_since_solution(model_dir: Path) -> bool:
    marker = model_dir / MODEL_INPUT_MODIFIED_MARKER
    if not marker.is_file():
        return False
    mod_sum = model_dir / "MOD_SUM"
    if not mod_sum.is_file():
        return True
    try:
        return marker.stat().st_mtime_ns > mod_sum.stat().st_mtime_ns
    except OSError:
        return True


def find_editable_model_file(basepath: str, file_relpath: str) -> dict[str, str] | None:
    parts = [part for part in Path(file_relpath).parts if part not in {"", "."}]
    for index in range(len(parts) - 1, 0, -1):
        model_relpath = Path(*parts[:index]).as_posix()
        try:
            model_dir = resolve_path(basepath, model_relpath)
        except FileNotFoundError:
            continue
        if not is_model_directory(model_dir):
            continue
        relative_file = Path(*parts[index:]).as_posix()
        if relative_file not in EDITABLE_MODEL_FILES:
            return None
        target = model_dir.joinpath(*Path(relative_file).parts)
        if target.is_file() and not target.is_symlink():
            return {"model_relpath": model_relpath, "file_relpath": relative_file}
        return None
    return None
