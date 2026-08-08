"""Preparation and result handling for externally run LTE/hydro calculations."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import tempfile

from .browser import is_model_directory, resolve_path
from .model_editor import (
    MODEL_EDITOR_BACKUP_DIR,
    ModelEditorError,
    load_model_parameter_file,
    mark_model_inputs_modified,
    save_model_parameter_edit,
)
from .model_staging import MODEL_WRITE_LOCK, is_sn_model_directory
from .model_runtime import inspect_workflow_runtime
from .parsers.common import parse_float_token
from .parsers.extended_text import KEYWORD_ROW_RE


class ModelWorkflowError(ValueError):
    """Raised when an LTE/hydro workflow action is unavailable or unsafe."""


ROOT_REQUIRED_INPUTS = ("VADAT", "MODEL_SPEC", "clean.sh")
ROOT_OPTIONAL_INPUTS = ("RVSIG_COL",)
LTE_INPUTS = ("VADAT", "MODEL_SPEC", "clean.sh", "GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS")
LTE_OUTPUT = "ROSSELAND_LTE_TAB"
HYDRO_OUTPUT = "RVSIG_COL_NEW"
LTE_QUICK_CONTROLS: dict[str, tuple[dict[str, str], ...]] = {
    "VADAT": (
        {
            "key": "TEFF",
            "label": "Effective temperature",
            "kind": "float",
            "comment": "Effective temperature for LTE structure",
        },
        {
            "key": "LOGG",
            "label": "Surface gravity",
            "kind": "float",
            "comment": "Surface gravity for LTE structure",
        },
        {
            "key": "CHK_NG",
            "label": "Check NG corrections",
            "kind": "boolean",
            "default": "F",
            "comment": "Check whether NG acceleration made a reasonable temperature correction",
        },
    ),
    "MODEL_SPEC": (
        {"key": "ND", "label": "Depth points", "kind": "positive_integer", "comment": "Number of depth points"},
        {"key": "NC", "label": "Core rays", "kind": "nonnegative_integer", "comment": "Number of core rays"},
        {
            "key": "NP",
            "label": "Impact parameters",
            "kind": "positive_integer",
            "comment": "Number of impact parameters (ND+NC)",
        },
    ),
}
RESULT_QUICK_CONTROLS: dict[str, tuple[dict[str, str], ...]] = {
    "HYDRO_PARAMS": (
        {
            "key": "REF_R",
            "label": "Reference radius",
            "kind": "float",
            "comment": "Reference radius adjusted to match the intended luminosity",
            "help": "Adjust when the generated luminosity is wrong, then rerun wind_hyd.",
        },
    ),
    "VADAT": (
        {
            "key": "RMAX",
            "label": "Outer radius ratio",
            "kind": "float",
            "comment": "Ratio of inner to outer radius from the hydro result",
            "help": "Use the final radius ratio reported after luminosity is correct.",
        },
    ),
}
RVSIG_SUMMARY_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("teff", "Effective temperature", r"Effective temperature \(10\^4 K\) is:\s*(\S+)", "10⁴ K"),
    ("logg", "Surface gravity", r"Log surface gravity \(cgs\) is:\s*(\S+)", "dex"),
    ("core_radius", "Core radius", r"Core radius \(10\^10 cm\) is:\s*(\S+)", "10¹⁰ cm"),
    ("reference_radius", "Reference radius", r"Reference radius \(10\^10 cm\) is:\s*(\S+)", "10¹⁰ cm"),
    ("luminosity", "Luminosity", r"Luminosity \(Lsun\) is:\s*(\S+)", "L☉"),
    ("mass", "Mass", r"Mass \(Msun\) of star is:\s*(\S+)", "M☉"),
    ("mass_loss", "Mass-loss rate", r"Mass loss rate \(Msun/yr\) is:\s*(\S+)", "M☉/yr"),
    ("mean_atomic_mass", "Mean atomic mass", r"Mean atomic mass \(amu\) is:\s*(\S+)", "amu"),
    ("eddington", "Eddington parameter", r"Eddington parameter is:\s*(\S+)", ""),
    ("atom_density", "Atom density", r"Atom density is:\s*(\S+)", "cm⁻³"),
    ("radius_ratio", "Radius ratio (RMAX)", r"Ratio of inner to outer radius is:\s*(\S+)", ""),
)


def _resolve_model(basepath: str, model_relpath: str) -> tuple[str, Path]:
    text = str(model_relpath).strip()
    rel = Path(text)
    if not text or text in {".", "/"} or rel.is_absolute() or ".." in rel.parts:
        raise ModelWorkflowError("Model path must remain under the configured root.")
    normalized = Path(*(part for part in rel.parts if part not in {"", "."})).as_posix()
    try:
        model_dir = resolve_path(basepath, normalized)
    except FileNotFoundError as exc:
        raise ModelWorkflowError("Model directory was not found.") from exc
    if not is_model_directory(model_dir):
        raise ModelWorkflowError("Path is not a recognized CMFGEN model directory.")
    if is_sn_model_directory(model_dir):
        raise ModelWorkflowError("LTE/hydro preparation is not supported for SN models.")
    return normalized, model_dir


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _file_state(path: Path, *, dependencies: tuple[Path, ...] = ()) -> dict[str, object]:
    exists = _regular_file(path)
    modified_ns = 0
    size = 0
    if exists:
        try:
            info = path.stat()
            modified_ns = info.st_mtime_ns
            size = info.st_size
        except OSError:
            exists = False
    dependency_times: list[int] = []
    for dependency in dependencies:
        if not _regular_file(dependency):
            continue
        try:
            dependency_times.append(dependency.stat().st_mtime_ns)
        except OSError:
            pass
    fresh = bool(exists and (not dependency_times or modified_ns >= max(dependency_times)))
    return {
        "name": path.name,
        "path": str(path),
        "exists": exists,
        "size": size,
        "modified_ns": modified_ns,
        "fresh": fresh,
        "stale": bool(exists and not fresh),
    }


def _template_paths(basepath: str) -> dict[str, Path | None]:
    root = Path(basepath).expanduser().resolve() / "examples"
    result: dict[str, Path | None] = {}
    for name in ("GRID_PARAMS", "ltebat.sh", "HYDRO_PARAMS"):
        candidates = (root / name, root / "lte2" / name)
        result[name] = next((path for path in candidates if _regular_file(path)), None)
    return result


def _same_contents(left: Path, right: Path) -> bool:
    if not _regular_file(left) or not _regular_file(right):
        return False
    try:
        if left.stat().st_size != right.stat().st_size:
            return False
        left_hash = hashlib.sha256(left.read_bytes()).digest()
        return left_hash == hashlib.sha256(right.read_bytes()).digest()
    except OSError:
        return False


def _missing_control_keys(path: Path, keys: tuple[str, ...]) -> list[str]:
    if not _regular_file(path):
        return list(keys)
    try:
        contents = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return list(keys)
    present: set[str] = set()
    for line in contents.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match is not None:
            present.add(match.group(2).upper())
    return [key for key in keys if key.upper() not in present]


def _control_occurrences(contents: str) -> dict[str, list[dict[str, object]]]:
    occurrences: dict[str, list[dict[str, object]]] = {}
    for line_index, line in enumerate(contents.splitlines(keepends=True)):
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match is None:
            continue
        value_raw, key, _comment = match.groups()
        occurrences.setdefault(key.upper(), []).append(
            {
                "line_index": line_index,
                "value_start": match.start(1),
                "value_end": match.end(1),
                "value": value_raw.strip(),
            }
        )
    return occurrences


def _control_numeric_values(path: Path) -> dict[str, float]:
    if not _regular_file(path):
        return {}
    try:
        contents = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    values: dict[str, float] = {}
    for key, matches in _control_occurrences(contents).items():
        if len(matches) != 1:
            continue
        parsed = parse_float_token(str(matches[0]["value"]))
        if parsed is not None and float("-inf") < parsed < float("inf"):
            values[key] = parsed
    return values


def _format_workflow_number(value: float) -> str:
    absolute = abs(value)
    if absolute and (absolute >= 1.0e5 or absolute < 1.0e-3):
        return f"{value:.6e}"
    return f"{value:.7g}"


def _comparison_row(
    *,
    label: str,
    generated: float,
    configured: float | None,
    configured_source: str,
    unit: str,
    difference_kind: str = "percent",
) -> dict[str, object]:
    difference = "—"
    status = ""
    if configured is not None:
        if difference_kind == "absolute":
            delta = generated - configured
            difference = f"{delta:+.5g}"
            status = "success" if abs(delta) <= 1.0e-4 else "warning"
        elif configured != 0:
            percentage = 100.0 * (generated - configured) / abs(configured)
            difference = f"{percentage:+.4g}%"
            absolute_percentage = abs(percentage)
            status = "success" if absolute_percentage <= 0.5 else "warning" if absolute_percentage <= 2 else "danger"
    return {
        "label": label,
        "generated": _format_workflow_number(generated),
        "configured": _format_workflow_number(configured) if configured is not None else "—",
        "configured_source": configured_source,
        "difference": difference,
        "unit": unit,
        "status": status,
    }


def _rvsig_result_summary(lte_dir: Path) -> dict[str, object] | None:
    rvsig = lte_dir / HYDRO_OUTPUT
    if not _regular_file(rvsig):
        return None
    try:
        contents = rvsig.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    generated: dict[str, float] = {}
    metadata: dict[str, tuple[str, str]] = {}
    for key, label, pattern, unit in RVSIG_SUMMARY_PATTERNS:
        match = re.search(pattern, contents, flags=re.IGNORECASE)
        if match is None:
            continue
        parsed = parse_float_token(match.group(1))
        if parsed is None or not (float("-inf") < parsed < float("inf")):
            continue
        generated[key] = parsed
        metadata[key] = (label, unit)
    depth_match = re.search(r"^\s*(\d+)\s*!\s*Number of depth points", contents, flags=re.MULTILINE)
    if depth_match is not None:
        generated["depth_points"] = float(depth_match.group(1))
        metadata["depth_points"] = ("Depth points", "")

    hydro = _control_numeric_values(lte_dir / "HYDRO_PARAMS")
    vadat = _control_numeric_values(lte_dir / "VADAT")
    comparisons: list[dict[str, object]] = []
    comparison_specs = (
        ("luminosity", hydro.get("LSTAR"), "HYDRO_PARAMS [LSTAR]", "percent"),
        ("radius_ratio", vadat.get("RMAX"), "VADAT [RMAX]", "percent"),
        ("teff", hydro.get("TEFF"), "HYDRO_PARAMS [TEFF]", "percent"),
        ("logg", hydro.get("LOG_G"), "HYDRO_PARAMS [LOG_G]", "absolute"),
        ("reference_radius", hydro.get("REF_R"), "HYDRO_PARAMS [REF_R]", "percent"),
        ("mass", hydro.get("MASS"), "HYDRO_PARAMS [MASS]", "percent"),
        ("mass_loss", hydro.get("MDOT"), "HYDRO_PARAMS [MDOT]", "percent"),
    )
    compared_keys: set[str] = set()
    for key, configured, source, difference_kind in comparison_specs:
        if key not in generated:
            continue
        label, unit = metadata[key]
        comparisons.append(
            _comparison_row(
                label=label,
                generated=generated[key],
                configured=configured,
                configured_source=source,
                unit=unit,
                difference_kind=difference_kind,
            )
        )
        compared_keys.add(key)
    diagnostics = [
        {
            "label": metadata[key][0],
            "value": _format_workflow_number(value),
            "unit": metadata[key][1],
        }
        for key, value in generated.items()
        if key not in compared_keys
    ]
    if not comparisons and not diagnostics:
        return None
    return {"comparisons": comparisons, "diagnostics": diagnostics}


def _quick_control_cards(
    basepath: str,
    model_relpath: str,
    *,
    definitions_by_file: dict[str, tuple[dict[str, str], ...]],
    field_prefix: str,
) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for filename, definitions in definitions_by_file.items():
        try:
            record = load_model_parameter_file(
                basepath,
                model_relpath=f"{model_relpath}/lte",
                file_relpath=filename,
            )
        except ModelEditorError:
            continue
        occurrences = _control_occurrences(str(record["contents"]))
        fields: list[dict[str, object]] = []
        issues: list[str] = []
        for definition in definitions:
            key = definition["key"]
            matches = occurrences.get(key, [])
            if len(matches) > 1:
                issues.append(f"[{key}] occurs more than once; resolve it in the text editor.")
            fields.append(
                {
                    **definition,
                    "value": (
                        str(matches[0]["value"])
                        if len(matches) == 1
                        else str(definition.get("default", ""))
                    ),
                    "exists": len(matches) == 1,
                    "field_name": f"{field_prefix}:{key}",
                }
            )
        cards.append(
            {
                "file_relpath": filename,
                "digest": str(record["digest"]),
                "fields": fields,
                "issues": issues,
                "can_save": not issues,
            }
        )
    return cards


def _lte_quick_control_cards(basepath: str, model_relpath: str) -> list[dict[str, object]]:
    return _quick_control_cards(
        basepath,
        model_relpath,
        definitions_by_file=LTE_QUICK_CONTROLS,
        field_prefix="lte_value",
    )


def _result_quick_control_cards(basepath: str, model_relpath: str) -> list[dict[str, object]]:
    return _quick_control_cards(
        basepath,
        model_relpath,
        definitions_by_file=RESULT_QUICK_CONTROLS,
        field_prefix="result_value",
    )


def _validate_quick_values(
    filename: str,
    values: dict[str, object],
    *,
    definitions_by_file: dict[str, tuple[dict[str, str], ...]],
) -> dict[str, str]:
    definitions = definitions_by_file.get(filename)
    if definitions is None:
        raise ModelWorkflowError("Unsupported workflow quick-control file.")
    normalized: dict[str, str] = {}
    for definition in definitions:
        key = definition["key"]
        value = str(values.get(key, "")).strip()
        if not value or any(character in value for character in "\r\n[]!"):
            raise ModelWorkflowError(f"[{key}] requires a single control value.")
        kind = definition["kind"]
        if kind == "float":
            parsed = parse_float_token(value)
            if parsed is None or not (float("-inf") < parsed < float("inf")):
                raise ModelWorkflowError(f"[{key}] must be a finite number.")
        elif kind == "boolean":
            value = value.upper()
            if value not in {"T", "F"}:
                raise ModelWorkflowError(f"[{key}] must be T or F.")
        elif not value.isdigit():
            raise ModelWorkflowError(f"[{key}] must be an integer.")
        elif kind == "positive_integer" and int(value) <= 0:
            raise ModelWorkflowError(f"[{key}] must be greater than zero.")
        normalized[key] = value
    if "ND" in normalized and int(normalized["NP"]) != int(normalized["ND"]) + int(normalized["NC"]):
        raise ModelWorkflowError("[NP] must equal [ND] + [NC].")
    return normalized


def _updated_control_contents(
    contents: str,
    filename: str,
    values: dict[str, str],
    *,
    definitions_by_file: dict[str, tuple[dict[str, str], ...]],
    marker_label: str,
) -> str:
    occurrences = _control_occurrences(contents)
    definitions = definitions_by_file[filename]
    for definition in definitions:
        key = definition["key"]
        if len(occurrences.get(key, [])) > 1:
            raise ModelWorkflowError(f"[{key}] occurs more than once; resolve it in the text editor.")

    lines = contents.splitlines(keepends=True)
    for definition in definitions:
        key = definition["key"]
        matches = occurrences.get(key, [])
        if matches:
            occurrence = matches[0]
            index = int(occurrence["line_index"])
            line = lines[index]
            lines[index] = (
                line[: int(occurrence["value_start"])]
                + values[key]
                + line[int(occurrence["value_end"]):]
            )
    updated = "".join(lines)
    missing = [definition for definition in definitions if not occurrences.get(definition["key"], [])]
    if missing:
        if updated and not updated.endswith(("\n", "\r")):
            updated += "\n"
        if updated and updated.strip():
            updated += f"! Added by CMFGEN Viewer {marker_label}\n"
        for definition in missing:
            key = definition["key"]
            updated += f"{values[key]:<12} [{key}] ! {definition['comment']}\n"
    return updated


def save_lte_quick_controls(
    basepath: str,
    *,
    model_relpath: str,
    filename: str,
    expected_digest: str,
    values: dict[str, object],
) -> dict[str, object]:
    return _save_workflow_quick_controls(
        basepath,
        model_relpath=model_relpath,
        filename=filename,
        expected_digest=expected_digest,
        values=values,
        definitions_by_file=LTE_QUICK_CONTROLS,
        marker_label="LTE quick setup",
    )


def save_result_quick_controls(
    basepath: str,
    *,
    model_relpath: str,
    filename: str,
    expected_digest: str,
    values: dict[str, object],
) -> dict[str, object]:
    return _save_workflow_quick_controls(
        basepath,
        model_relpath=model_relpath,
        filename=filename,
        expected_digest=expected_digest,
        values=values,
        definitions_by_file=RESULT_QUICK_CONTROLS,
        marker_label="LTE/hydro result review",
        preserve_modified_time=str(filename).strip().upper() == "VADAT",
    )


def _save_workflow_quick_controls(
    basepath: str,
    *,
    model_relpath: str,
    filename: str,
    expected_digest: str,
    values: dict[str, object],
    definitions_by_file: dict[str, tuple[dict[str, str], ...]],
    marker_label: str,
    preserve_modified_time: bool = False,
) -> dict[str, object]:
    normalized_filename = str(filename).strip().upper()
    normalized_values = _validate_quick_values(
        normalized_filename,
        values,
        definitions_by_file=definitions_by_file,
    )
    lte_model_relpath = f"{model_relpath.rstrip('/')}/lte"
    try:
        record = load_model_parameter_file(
            basepath,
            model_relpath=lte_model_relpath,
            file_relpath=normalized_filename,
        )
        updated = _updated_control_contents(
            str(record["contents"]),
            normalized_filename,
            normalized_values,
            definitions_by_file=definitions_by_file,
            marker_label=marker_label,
        )
        return save_model_parameter_edit(
            basepath,
            model_relpath=lte_model_relpath,
            file_relpath=normalized_filename,
            expected_digest=expected_digest,
            contents=updated,
            preserve_modified_time=preserve_modified_time,
        )
    except ModelEditorError as exc:
        raise ModelWorkflowError(str(exc)) from exc


def inspect_lte_hydro_workflow(basepath: str, *, model_relpath: str) -> dict[str, object]:
    normalized, model_dir = _resolve_model(basepath, model_relpath)
    lte_dir = model_dir / "lte"
    templates = _template_paths(basepath)
    root_files = [
        {**_file_state(model_dir / name), "required": name in ROOT_REQUIRED_INPUTS}
        for name in (*ROOT_REQUIRED_INPUTS, *ROOT_OPTIONAL_INPUTS)
    ]
    template_files = [
        {
            "name": name,
            "path": str(path) if path is not None else "",
            "exists": path is not None,
        }
        for name, path in templates.items()
    ]
    lte_files = [_file_state(lte_dir / name) for name in LTE_INPUTS]
    lte_exists = lte_dir.exists() or lte_dir.is_symlink()
    prepared = lte_dir.is_dir() and not lte_dir.is_symlink() and all(
        bool(item["exists"]) for item in lte_files
    )
    missing_root = [
        str(item["name"]) for item in root_files if item["required"] and not item["exists"]
    ]
    missing_templates = [str(item["name"]) for item in template_files if not item["exists"]]
    missing_lte = [str(item["name"]) for item in lte_files if not item["exists"]]
    prepare_allowed = not lte_exists and not missing_root and not missing_templates
    if lte_exists and not prepared:
        prepare_reason = "The existing lte path is incomplete; repair or remove it manually before preparing again."
    elif missing_root:
        prepare_reason = f"Missing model input(s): {', '.join(missing_root)}."
    elif missing_templates:
        prepare_reason = f"Missing template(s) under {Path(basepath).resolve() / 'examples'}: {', '.join(missing_templates)}."
    elif prepared:
        prepare_reason = "The LTE workspace is prepared."
    else:
        prepare_reason = ""

    lte_dependencies = tuple(lte_dir / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS", "ltebat.sh"))
    lte_output = _file_state(lte_dir / LTE_OUTPUT, dependencies=lte_dependencies)
    hydro_dependencies = (lte_dir / LTE_OUTPUT, lte_dir / "HYDRO_PARAMS")
    hydro_output = _file_state(lte_dir / HYDRO_OUTPUT, dependencies=hydro_dependencies)
    missing_lte_controls = {
        "VADAT": _missing_control_keys(lte_dir / "VADAT", ("TEFF", "LOGG", "CHK_NG")),
        "MODEL_SPEC": _missing_control_keys(lte_dir / "MODEL_SPEC", ("ND", "NC", "NP")),
    }
    missing_lte_control_keys = [
        f"{filename} [{key}]"
        for filename, keys in missing_lte_controls.items()
        for key in keys
    ]
    lte_ready = bool(prepared and not missing_lte_control_keys)
    hydro_ready = bool(lte_ready and lte_output["fresh"])
    hydro_output_ready = bool(hydro_ready and hydro_output["fresh"])
    promotion_ready = hydro_output_ready
    promoted = bool(
        promotion_ready
        and _same_contents(lte_dir / LTE_OUTPUT, model_dir / LTE_OUTPUT)
        and _same_contents(lte_dir / HYDRO_OUTPUT, model_dir / HYDRO_OUTPUT)
        and _same_contents(lte_dir / HYDRO_OUTPUT, model_dir / "RVSIG_COL")
        and _same_contents(lte_dir / "VADAT", model_dir / "VADAT")
    )
    main_dependencies = tuple(model_dir / name for name in ("VADAT", "RVSIG_COL", LTE_OUTPUT))
    main_ready = all(_regular_file(path) for path in main_dependencies) and _regular_file(
        model_dir / "batch.sh"
    )
    lte_command = f"cd {shlex.quote(str(lte_dir))} && ./ltebat.sh"
    hydro_command = f"cd {shlex.quote(str(lte_dir))} && $cmfdist/exe/wind_hyd.exe"
    return {
        "model_relpath": normalized,
        "model_path": str(model_dir),
        "lte_path": str(lte_dir),
        "template_root": str(Path(basepath).expanduser().resolve() / "examples"),
        "root_files": root_files,
        "template_files": template_files,
        "lte_files": lte_files,
        "missing_lte": missing_lte,
        "missing_lte_control_keys": missing_lte_control_keys,
        "lte_exists": lte_exists,
        "prepared": prepared,
        "prepare_allowed": prepare_allowed,
        "prepare_reason": prepare_reason,
        "rvsig_backup_exists": _regular_file(model_dir / "RVSIG_COL_OLD"),
        "lte_ready": lte_ready,
        "lte_output": lte_output,
        "hydro_ready": hydro_ready,
        "hydro_output": hydro_output,
        "hydro_output_ready": hydro_output_ready,
        "promotion_ready": promotion_ready,
        "promoted": promoted,
        "main_ready": main_ready,
        "commands": {"lte": lte_command, "hydro": hydro_command},
        "hydro_answers": ["/null", "e", "70", "press Enter (or enter the required maximum optical depth)"],
        "lte_quick_control_cards": _lte_quick_control_cards(basepath, normalized) if prepared else [],
        "result_quick_control_cards": (
            _result_quick_control_cards(basepath, normalized) if prepared and hydro_output["exists"] else []
        ),
        "result_summary": _rvsig_result_summary(lte_dir),
        "lte_runtime": inspect_workflow_runtime(lte_dir, "lte"),
        "hydro_runtime": inspect_workflow_runtime(lte_dir, "hydro"),
    }


def _copy_regular(source: Path, destination: Path) -> None:
    if not _regular_file(source):
        raise ModelWorkflowError(f"Required regular file is unavailable: {source}")
    shutil.copy2(source, destination)


def prepare_lte_hydro_workspace(basepath: str, *, model_relpath: str) -> dict[str, object]:
    with MODEL_WRITE_LOCK:
        state = inspect_lte_hydro_workflow(basepath, model_relpath=model_relpath)
        if not state["prepare_allowed"]:
            raise ModelWorkflowError(str(state["prepare_reason"] or "LTE workspace cannot be prepared."))
        model_dir = Path(str(state["model_path"]))
        lte_dir = model_dir / "lte"
        templates = _template_paths(basepath)
        staging = Path(tempfile.mkdtemp(prefix=".cmfgen-lte-", dir=str(model_dir)))
        created_rvsig_backup = False
        try:
            for name in ("VADAT", "MODEL_SPEC", "clean.sh"):
                _copy_regular(model_dir / name, staging / name)
            for name, source in templates.items():
                if source is None:
                    raise ModelWorkflowError(f"Required workflow template is unavailable: {name}")
                _copy_regular(source, staging / name)
            if _regular_file(model_dir / "RVSIG_COL") and not (model_dir / "RVSIG_COL_OLD").exists():
                _copy_regular(model_dir / "RVSIG_COL", model_dir / "RVSIG_COL_OLD")
                created_rvsig_backup = True
            os.replace(staging, lte_dir)
        except (OSError, shutil.Error) as exc:
            if created_rvsig_backup:
                try:
                    (model_dir / "RVSIG_COL_OLD").unlink()
                except OSError:
                    pass
            raise ModelWorkflowError(f"Could not prepare LTE workspace: {exc}") from exc
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    return inspect_lte_hydro_workflow(basepath, model_relpath=model_relpath)


def _atomic_copy(source: Path, destination: Path) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".cmfgen-promote-", dir=str(destination.parent))
        temporary = Path(name)
        with source.open("rb") as source_handle, os.fdopen(descriptor, "wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        source_mode = stat.S_IMODE(source.stat().st_mode)
        temporary.chmod(source_mode)
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def promote_lte_hydro_results(basepath: str, *, model_relpath: str) -> dict[str, object]:
    with MODEL_WRITE_LOCK:
        state = inspect_lte_hydro_workflow(basepath, model_relpath=model_relpath)
        if not state["promotion_ready"]:
            raise ModelWorkflowError(
                "Fresh ROSSELAND_LTE_TAB and RVSIG_COL_NEW outputs are required before promotion."
            )
        model_dir = Path(str(state["model_path"]))
        lte_dir = model_dir / "lte"
        sources = {
            "ROSSELAND_LTE_TAB": lte_dir / "ROSSELAND_LTE_TAB",
            "RVSIG_COL_NEW": lte_dir / "RVSIG_COL_NEW",
            "RVSIG_COL": lte_dir / "RVSIG_COL_NEW",
            "VADAT": lte_dir / "VADAT",
        }
        for name in sources:
            if (model_dir / name).is_symlink():
                raise ModelWorkflowError(f"Refusing to replace symlinked model target: {name}")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup_dir = model_dir / MODEL_EDITOR_BACKUP_DIR / "lte-hydro" / timestamp
        original_names: set[str] = set()
        replaced_names: list[str] = []
        try:
            backup_dir.mkdir(parents=True, exist_ok=False)
            for name in sources:
                target = model_dir / name
                if _regular_file(target):
                    original_names.add(name)
                    shutil.copy2(target, backup_dir / name)
            for name, source in sources.items():
                _atomic_copy(source, model_dir / name)
                replaced_names.append(name)
            backup_relpath = backup_dir.relative_to(model_dir).as_posix()
            mark_model_inputs_modified(
                model_dir,
                file_relpath="LTE/hydro promoted outputs",
                backup_relpath=backup_relpath,
            )
        except (OSError, shutil.Error, ModelEditorError) as exc:
            for name in reversed(replaced_names):
                target = model_dir / name
                try:
                    if name in original_names:
                        _atomic_copy(backup_dir / name, target)
                    else:
                        target.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ModelWorkflowError(f"Could not promote LTE/hydro results: {exc}") from exc
    result = inspect_lte_hydro_workflow(basepath, model_relpath=model_relpath)
    result["backup_relpath"] = backup_relpath
    return result
