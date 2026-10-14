"""Structured editing of selected values in CMFGEN control files."""

from __future__ import annotations

import math
import re

from .control_files import control_occurrences as _keyword_occurrences
from .model_editor import (
    ConcurrentModelEditError,
    ModelEditorError,
    list_model_parameter_files,
    load_model_parameter_file,
    review_model_parameter_edit,
    save_model_parameter_edit,
)
from .parsers.common import parse_float_token

QUICK_PARAMETER_FILES = ("VADAT", "IN_ITS")

QUICK_PARAMETER_DEFINITIONS: dict[str, dict[str, dict[str, str]]] = {
    "VADAT": {
        "LSTAR": {
            "label": "Luminosity",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "L☉",
        },
        "RSTAR": {
            "label": "Stellar radius control",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "",
        },
        "MDOT": {
            "label": "Mass-loss rate",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "M☉ / yr",
        },
        "VINF": {
            "label": "Terminal velocity",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "km/s",
        },
        "BETA": {
            "label": "Velocity-law exponent",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "",
        },
        "MASS": {
            "label": "Stellar mass",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "M☉",
        },
        "LOGG": {
            "label": "Surface gravity",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "log g",
            "notice": "Changing LOGG requires regenerating the LTE/hydro structure; this edit alone is not sufficient.",
        },
        "DO_CL": {
            "label": "Enable clumping",
            "group": "Clumping",
            "kind": "boolean",
            "unit": "",
        },
        "CL_LAW": {
            "label": "Clumping law",
            "group": "Clumping",
            "kind": "token",
            "unit": "",
        },
    },
    "IN_ITS": {
        "NUM_ITS": {
            "label": "Number of iterations",
            "group": "Iteration controls",
            "kind": "integer",
            "unit": "",
        },
        "DO_LAM_IT": {
            "label": "Lambda iterations",
            "group": "Iteration controls",
            "kind": "boolean",
            "unit": "",
        },
        "DO_LAM_AUTO": {
            "label": "Automatic lambda iterations",
            "group": "Iteration controls",
            "kind": "boolean",
            "unit": "",
        },
        "DO_T_AUTO": {
            "label": "Automatic temperature iterations",
            "group": "Iteration controls",
            "kind": "boolean",
            "unit": "",
        },
        "DO_GT_AUTO": {
            "label": "Automatic grey-temperature iterations",
            "group": "Iteration controls",
            "kind": "boolean",
            "unit": "",
        },
    },
}

QUICK_PARAMETER_GROUP_ORDER = (
    "Stellar and wind",
    "Clumping",
    "Composition",
    "Additional abundances",
    "Iteration controls",
)

COMMON_ABUNDANCE_LABELS = {
    "HYD/X": "Hydrogen abundance",
    "HE/X": "Helium abundance",
    "CARB/X": "Carbon abundance",
    "NIT/X": "Nitrogen abundance",
    "OXY/X": "Oxygen abundance",
    "IRON/X": "Iron abundance",
}

CLUMPING_PARAMETER_RE = re.compile(r"^CL_PAR_(\d+)$")
INTEGER_TOKEN_RE = re.compile(r"^[+-]?\d+$")
QUICK_TOKEN_RE = re.compile(r"^[A-Za-z0-9_./,+=-]+$")


def _clumping_parameter_number(key: str) -> int:
    match = CLUMPING_PARAMETER_RE.match(key)
    return int(match.group(1)) if match else 0


def _quick_parameter_definitions(
    file_relpath: str,
    occurrences: dict[str, list[dict[str, object]]],
) -> list[tuple[str, dict[str, str]]]:
    definitions = list(QUICK_PARAMETER_DEFINITIONS.get(file_relpath, {}).items())
    if file_relpath != "VADAT":
        return definitions

    clumping_keys = sorted(
        (key for key in occurrences if CLUMPING_PARAMETER_RE.match(key)),
        key=_clumping_parameter_number,
    )
    definitions.extend(
        (
            key,
            {
                "label": f"Clumping parameter {_clumping_parameter_number(key)}",
                "group": "Clumping",
                "kind": "float",
                "unit": "",
            },
        )
        for key in clumping_keys
    )

    abundance_keys = [key for key in occurrences if key.endswith("/X")]
    common_keys = [key for key in COMMON_ABUNDANCE_LABELS if key in abundance_keys]
    additional_keys = sorted(key for key in abundance_keys if key not in COMMON_ABUNDANCE_LABELS)
    definitions.extend(
        (
            key,
            {
                "label": COMMON_ABUNDANCE_LABELS[key],
                "group": "Composition",
                "kind": "float",
                "unit": "",
            },
        )
        for key in common_keys
    )
    definitions.extend(
        (
            key,
            {
                "label": f"{key.removesuffix('/X')} abundance",
                "group": "Additional abundances",
                "kind": "float",
                "unit": "",
            },
        )
        for key in additional_keys
    )
    return definitions


def _validate_quick_parameter_value(field: dict[str, object], raw_value: object) -> str:
    value = str(raw_value).strip()
    key = str(field["key"])
    if not value:
        raise ModelEditorError(f"[{key}] requires a value.")
    if any(character in value for character in "\r\n[]!"):
        raise ModelEditorError(f"[{key}] must contain only a control value, not syntax or comments.")
    if len(value) > 256:
        raise ModelEditorError(f"[{key}] is too long for the quick editor.")

    kind = str(field["kind"])
    if kind == "boolean":
        normalized = value.upper()
        if normalized not in {"T", "F"}:
            raise ModelEditorError(f"[{key}] must be T or F.")
        return normalized
    if kind == "integer":
        if INTEGER_TOKEN_RE.fullmatch(value) is None or int(value) < 0:
            raise ModelEditorError(f"[{key}] must be a non-negative integer.")
        return value
    if kind == "float":
        parsed = parse_float_token(value)
        if parsed is None or not math.isfinite(parsed):
            raise ModelEditorError(f"[{key}] must be a finite number.")
        return value
    if kind == "token":
        if len(value) > 64 or QUICK_TOKEN_RE.fullmatch(value) is None:
            raise ModelEditorError(f"[{key}] must be a single control token.")
        return value
    raise ModelEditorError(f"[{key}] has an unsupported quick-editor field type.")


def _luminosity_scaling_state(contents: str) -> dict[str, object]:
    occurrences = _keyword_occurrences(contents)
    baseline: dict[str, float] = {}
    for key in ("LSTAR", "RSTAR", "MASS", "TEFF", "LOGG"):
        matches = occurrences.get(key, [])
        value = parse_float_token(str(matches[0]["value"])) if len(matches) == 1 else None
        if value is None or not math.isfinite(value) or (key != "LOGG" and value <= 0):
            return {
                "available": False,
                "reason": f"Requires one finite {'positive ' if key != 'LOGG' else ''}[{key}] value.",
            }
        baseline[key] = value
    # Use the LTE/hydro reference radius, not the core-radius control RSTAR.
    log_reference_cm = (
        math.log10(6.9599) + 0.5 * math.log10(baseline["LSTAR"])
        + 2 * (math.log10(0.5770) - math.log10(baseline["TEFF"])) + 10
    )
    implied_logg = (math.log10(6.67430e-8) + math.log10(1.98847e33)
                    + math.log10(baseline["MASS"]) - 2 * log_reference_cm)
    warnings = []
    if abs(implied_logg - baseline["LOGG"]) > 0.05:
        warnings.append(
            f"Existing MASS implies log g = {implied_logg:.3f} at the reference radius derived "
            f"from LSTAR and TEFF, compared with LOGG = {baseline['LOGG']:.3f}. "
            "Scaling preserves this discrepancy; review it before running LTE/hydro."
        )
    return {"available": True, "baseline": baseline, "warnings": warnings}


def _quick_card_from_record(record: dict[str, object]) -> dict[str, object]:
    file_relpath = str(record["file_relpath"])
    occurrences = _keyword_occurrences(str(record["contents"]))
    fields: list[dict[str, object]] = []
    issues: list[str] = []
    for key, definition in _quick_parameter_definitions(file_relpath, occurrences):
        matches = occurrences.get(key, [])
        if not matches:
            continue
        if len(matches) != 1:
            issues.append(f"[{key}] occurs more than once and is available only in the text editor.")
            continue
        occurrence = matches[0]
        safe_key = re.sub(r"[^A-Za-z0-9_-]+", "-", key).strip("-").lower()
        field = {
            **definition,
            **occurrence,
            "key": key,
            "field_name": f"quick_value:{key}",
            "input_id": f"quick-{file_relpath.lower().replace('/', '-')}-{safe_key}",
        }
        try:
            _validate_quick_parameter_value(field, occurrence["value"])
        except ModelEditorError:
            issues.append(f"[{key}] has an unsupported value and is available only in the text editor.")
            continue
        fields.append(field)

    scaling = _luminosity_scaling_state(str(record["contents"])) if file_relpath == "VADAT" else None
    editable_keys = {field["key"] for field in fields}
    if scaling and scaling["available"] and not {"LSTAR", "RSTAR", "MASS", "LOGG"}.issubset(editable_keys):
        scaling = {"available": False, "reason": "Requires editable LSTAR, RSTAR, MASS, and LOGG controls."}

    groups: list[dict[str, object]] = []
    for group_name in QUICK_PARAMETER_GROUP_ORDER:
        group_fields = [field for field in fields if field["group"] == group_name]
        if group_fields:
            groups.append(
                {
                    "name": group_name,
                    "fields": group_fields,
                    "collapsed": group_name == "Additional abundances",
                }
            )
    return {
        "file_relpath": file_relpath,
        "label": "Model setup" if file_relpath == "VADAT" else "Run controls",
        "description": (
            "Frequently changed stellar, wind, clumping, and composition controls."
            if file_relpath == "VADAT"
            else "Iteration count and automatic iteration switches."
        ),
        "keep_temperature_logg": False,
        "luminosity_scaling": scaling,
        "digest": str(record["digest"]),
        "fields": fields,
        "groups": groups,
        "issues": issues,
    }


def load_quick_model_parameter_cards(
    basepath: str,
    *,
    model_relpath: str,
) -> list[dict[str, object]]:
    listing = list_model_parameter_files(basepath, model_relpath=model_relpath)
    files_by_path = {str(item["file_relpath"]): item for item in listing["files"]}
    cards: list[dict[str, object]] = []
    for file_relpath in QUICK_PARAMETER_FILES:
        file_info = files_by_path[file_relpath]
        if not bool(file_info["editable"]):
            continue
        record = load_model_parameter_file(
            basepath,
            model_relpath=model_relpath,
            file_relpath=file_relpath,
        )
        cards.append(_quick_card_from_record(record))
    return cards


def _prepare_quick_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    values: dict[str, object],
    keep_temperature_logg: bool = False,
) -> tuple[dict[str, object], str]:
    if file_relpath not in QUICK_PARAMETER_FILES:
        raise ModelEditorError("This control file is not available in the quick editor.")
    record = load_model_parameter_file(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
    )
    if not expected_digest or str(record["digest"]) != str(expected_digest):
        raise ConcurrentModelEditError(
            "This file changed after the quick editor loaded it. Reload before reviewing or saving."
        )
    card = _quick_card_from_record(record)
    fields = list(card["fields"])
    expected_keys = {str(field["key"]) for field in fields}
    if set(values) != expected_keys:
        raise ModelEditorError("The submitted quick-parameter set does not match the current file.")

    if keep_temperature_logg:
        scaling = card["luminosity_scaling"]
        if not scaling or not scaling["available"]:
            reason = str(scaling["reason"]) if scaling else "This option requires VADAT."
            raise ModelEditorError("Cannot keep temperature and log g fixed. " + reason)
        baseline = scaling["baseline"]
        fields_by_key = {str(field["key"]): field for field in fields}
        luminosity = parse_float_token(_validate_quick_parameter_value(fields_by_key["LSTAR"], values["LSTAR"]))
        if luminosity <= 0:
            raise ModelEditorError("[LSTAR] must be positive when keeping temperature and log g fixed.")
        logg = parse_float_token(_validate_quick_parameter_value(fields_by_key["LOGG"], values["LOGG"]))
        if logg != baseline["LOGG"]:
            raise ModelEditorError("[LOGG] must remain unchanged when keeping temperature and log g fixed.")
        factor = luminosity / baseline["LSTAR"]
        radius = baseline["RSTAR"] * math.sqrt(factor)
        mass = baseline["MASS"] * factor
        if not all(math.isfinite(value) and value > 0 for value in (factor, radius, mass)):
            raise ModelEditorError("Luminosity scaling must yield a finite positive radius and mass.")
        values = {**values, "LOGG": fields_by_key["LOGG"]["value"]}
        # Retain the original notation for a no-op luminosity change.
        if luminosity == baseline["LSTAR"]:
            values.update({key: fields_by_key[key]["value"] for key in ("RSTAR", "MASS")})
        else:
            values.update(RSTAR=f"{radius:.12g}", MASS=f"{mass:.12g}")
        card["keep_temperature_logg"] = True

    lines = str(record["contents"]).splitlines(keepends=True)
    for field in fields:
        key = str(field["key"])
        value = _validate_quick_parameter_value(field, values[key])
        line_index = int(field["line_index"])
        value_start = int(field["value_start"])
        value_end = int(field["value_end"])
        line = lines[line_index]
        lines[line_index] = f"{line[:value_start]}{value}{line[value_end:]}"
        field["value"] = value
    return card, "".join(lines)


def review_quick_model_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    values: dict[str, object],
    keep_temperature_logg: bool = False,
) -> dict[str, object]:
    card, contents = _prepare_quick_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        values=values,
        keep_temperature_logg=keep_temperature_logg,
    )
    review = review_model_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        contents=contents,
    )
    if keep_temperature_logg:
        review["warnings"] = [*review["warnings"], *card["luminosity_scaling"]["warnings"]]
    return {
        **review,
        "card": card,
        "values": {field["key"]: field["value"] for field in card["fields"]},
        "keep_temperature_logg": keep_temperature_logg,
    }


def save_quick_model_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    reviewed_digest: str,
    values: dict[str, object],
    keep_temperature_logg: bool = False,
) -> dict[str, object]:
    review = review_quick_model_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        values=values,
        keep_temperature_logg=keep_temperature_logg,
    )
    if reviewed_digest != str(review["proposed_digest"]):
        raise ModelEditorError(
            "The quick-parameter values changed after review. Preview them again before saving."
        )
    return save_model_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        contents=str(review["contents"]),
    )
