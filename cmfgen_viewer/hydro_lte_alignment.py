"""Align hydro composition with the fresh opacity table produced by LTE."""
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import shutil
import stat

from .control_files import control_occurrences
from .model_editor import _atomic_replace, mark_model_inputs_modified
from .parsers.common import parse_float_token
from .runner_validation import validate_rosseland_table


def preview_lte_hydro_alignment(model: Path) -> dict:
    workspace = model / "lte"
    preview = {"ready": False, "changed": False, "issues": [], "current": None, "proposed": None}
    try:
        sources = [workspace / name for name in ("ROSSELAND_LTE_TAB", "HYDRO_PARAMS")]
        dependencies = [workspace / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh")
                        if (workspace / name).exists()]
        for path in sources + dependencies:
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ValueError(f"LTE alignment requires a regular unlinked file: {path.name}")
        payloads = {path: path.read_bytes() for path in sources + dependencies}
        table, target = sources
        target_text = payloads[target].decode("utf-8")
        old_mode = control_occurrences(target_text).get("OLD_MOD", [])
        if len(old_mode) == 1 and old_mode[0]["value"].upper() == "T":
            preview.update(ready=True, uses_rvtj=True)
            return preview
        validate_rosseland_table(table)
        if dependencies and table.stat().st_mtime_ns < max(path.stat().st_mtime_ns for path in dependencies):
            raise ValueError("ROSSELAND_LTE_TAB is stale; rerun LTE before aligning MU_ATOM.")
        matches = re.findall(r"^[ \t]*![ \t]*Mean atomic weight \(atoms/ions only\)[ \t]*([^\n]*)$",
                             payloads[table].decode("utf-8"), re.M | re.I)
        value = parse_float_token(matches[0]) if len(matches) == 1 else None
        if value is None or not math.isfinite(value) or value <= 0:
            raise ValueError("ROSSELAND_LTE_TAB requires one finite positive mean atomic weight header.")
        from .lte_hydro_diagnostics import inspect_lte_diagnostics
        if inspect_lte_diagnostics(workspace).get("fatal"):
            raise ValueError("LTE has fatal diagnostics; rerun LTE before aligning MU_ATOM.")
        rows = control_occurrences(target_text).get("MU_ATOM", [])
        if len(rows) > 1:
            raise ValueError("HYDRO_PARAMS has duplicate MU_ATOM controls; correct them before alignment.")
        current = parse_float_token(rows[0]["value"]) if rows else None
        if current is not None and (not math.isfinite(current) or current <= 0):
            current = None
        records = {str(path): hashlib.sha256(payload).hexdigest() for path, payload in payloads.items()}
        if any(path.read_bytes() != payload for path, payload in payloads.items()):
            raise ValueError("LTE alignment inputs changed during inspection; rebuild the preview.")
        digest = hashlib.sha256(repr(sorted(records.items())).encode()).hexdigest()
        preview.update(ready=True, current=current, proposed=value,
                       changed=current is None or not math.isclose(current, value, rel_tol=1e-9, abs_tol=0),
                       digest=digest, file_digests=records)
    except (OSError, ValueError, UnicodeError) as exc:
        preview["issues"] = [str(exc)]
    return preview


def apply_lte_hydro_alignment(model: Path, expected_digest: str) -> dict:
    """Apply under the caller's model mutation guard; leave a recovery checkpoint."""
    from .model_workflow import _updated_control_contents

    preview = preview_lte_hydro_alignment(model)
    if not preview["ready"]:
        raise ValueError(" ".join(preview["issues"]))
    if not expected_digest or preview["digest"] != expected_digest:
        raise ValueError("LTE inputs or HYDRO_PARAMS changed since alignment preview; rebuild the plan.")
    if not preview["changed"]:
        return {"changed": False, "value": preview["proposed"]}
    target = model / "lte/HYDRO_PARAMS"
    updated = _updated_control_contents(target.read_text(), "HYDRO_PARAMS",
        {"MU_ATOM": f"{preview['proposed']:.12g}"},
        definitions_by_file={"HYDRO_PARAMS": ({"key": "MU_ATOM", "comment": "From ROSSELAND_LTE_TAB"},)},
        marker_label="LTE composition alignment")
    for name, digest in preview["file_digests"].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
            raise ValueError("LTE alignment source changed while saving; rebuild the plan.")
    backup = model / ".cmfgen-viewer-backups/lte-composition" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, backup / target.name)
    _atomic_replace(target, updated.encode(), mode=stat.S_IMODE(target.stat().st_mode))
    relative = backup.relative_to(model).as_posix()
    mark_model_inputs_modified(model, file_relpath="lte/HYDRO_PARAMS", backup_relpath=relative)
    return {"changed": True, "value": preview["proposed"], "backup_relpath": relative}
