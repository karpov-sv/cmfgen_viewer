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
from .model_initialization import lte_initialization_controls
from .solver_notices import solver_settings_notices

QUICK_PARAMETER_FILES = ("VADAT", "IN_ITS", "ADJUST_CORRECTIONS")

QUICK_PARAMETER_DEFINITIONS: dict[str, dict[str, dict[str, object]]] = {
    "VADAT": {
        "LSTAR": {
            "label": "Luminosity",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "L☉",
        },
        "TEFF": {
            "label": "Effective temperature",
            "group": "Stellar and wind",
            "kind": "float",
            "unit": "10⁴ K",
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
        "EPS_TERM": {
            "label": "Convergence tolerance",
            "group": "Convergence and solver controls",
            "kind": "float",
            "unit": "%",
            "notice": "Positive solver correction tolerance: 0.02 means 0.02%, not 2%. "
                      "Smaller values require tighter convergence. Used by native CMFGEN and "
                      "the automatic runner; this is not a spectrum or physical-accuracy target.",
        },
        "MAX_LIN": {
            "label": "Population correction limit",
            "group": "Convergence and solver controls",
            "kind": "float",
            "unit": "factor",
            "notice": "Must exceed 1. Limits full-iteration population updates according to "
                      "the scaling method; 2 permits changes by a factor of up to 2. "
                      "Smaller limits can reduce overshoot.",
        },
        "MAX_DT": {
            "label": "Temperature correction limit",
            "group": "Convergence and solver controls",
            "kind": "float",
            "unit": "fraction",
            "optional": True,
            "placeholder": "Native default: 0.2 (20%)",
            "notice": "Enter a fraction greater than 0 and at most 0.2: 0.05 means 5%. "
                      "Leave unset to retain the native 20% default. SCALE_OPT=NONE uses "
                      "a fixed 20% temperature limit instead.",
        },
        "COMP_BA": {
            "label": "Compute Jacobian",
            "group": "Advanced solver controls",
            "kind": "boolean",
            "unit": "",
            "notice": "Enable matrix computation. COMP_BA=T with N_FIX_BA=0 rebuilds the Jacobian "
                      "on every full iteration. Automatic verification also sets FIX_BA=0.",
        },
        "N_FIX_BA": {
            "label": "Jacobian reuse iterations",
            "group": "Advanced solver controls",
            "kind": "integer",
            "unit": "iterations",
            "notice": "Number of iterations to hold the Jacobian fixed. Zero disables this "
                      "reuse interval; COMP_BA and FIX_BA also control matrix computation.",
        },
        "FIX_BA": {
            "label": "Jacobian freeze threshold",
            "group": "Advanced solver controls",
            "kind": "float",
            "unit": "%",
            "notice": "Threshold for extending Jacobian reuse near convergence. Zero disables "
                      "threshold-based freezing while permitting periodic reuse with N_FIX_BA>0. "
                      "With COMP_BA=T, this threshold alone does not enable reuse when N_FIX_BA=0.",
        },
        "SCALE_OPT": {
            "label": "Correction scaling method",
            "group": "Advanced solver controls",
            "kind": "token",
            "unit": "",
            "choices": [("MAJOR", "Major species"), ("LOCAL", "Per depth"),
                        ("GLOBAL", "All depths together"), ("NONE", "Individual limits")],
            "notice": "Controls how correction limits scale updates. NONE still limits "
                      "individual updates; its temperature limit is fixed at 20%.",
        },
        "MAX_LAM": {
            "label": "Lambda population correction limit",
            "group": "Advanced solver controls",
            "kind": "float",
            "unit": "factor",
            "notice": "Must exceed 1. Population correction limit for Lambda iterations, "
                      "separate from MAX_LIN for full iterations.",
        },
        "FIX_T": {
            "label": "Fixed temperature",
            "group": "Advanced solver controls",
            "kind": "boolean", "unit": "",
            "notice": "Keep temperature fixed unless native automatic temperature release is enabled. "
                      "Full convergence verification requires variable temperature.",
        },
        "DO_NG": {
            "label": "Ng acceleration",
            "group": "Advanced solver controls",
            "kind": "boolean", "unit": "",
            "notice": "Enable native Ng acceleration, subject to its scheduling and validity checks. "
                      "Disabling it can be intentional during unstable recovery.",
        },
        "DC_METH": {
            "label": "Initial population method",
            "group": "Initialization",
            "kind": "token",
            "unit": "",
            "notice": "Fresh initialization only. Leave unset to preserve the native default "
                      "(ED with LIN_INT=F, R with LIN_INT=T). POP requires the patched CMFGEN "
                      "with LIN_INT=T and POP_SCALE=T; selecting POP enables both in this form. "
                      "Review these changes before saving. LTE is a fallback, not a convergence guarantee.",
            "choices": [
                ("ED", "Electron density"), ("R", "Radius"),
                ("TR", "Temperature / radius"), ("RTX", "Excitation temperature / radius"),
                ("SPH_TAU", "Spherical optical depth"), ("RNS", "Unscaled radius"),
                ("LTE", "LTE initial populations"),
                ("POP", "Population fractions / radius"),
            ],
        },
        "T_EXC": {
            "label": "Minimum initial excitation temperature",
            "group": "Initialization",
            "kind": "float",
            "unit": "10⁴ K",
            "notice": "Used with DC_METH=LTE; 1.0 corresponds to 10,000 K.",
        },
        "LIN_INT": {
            "label": "Interpolate saved model onto the grid",
            "group": "Initialization",
            "kind": "boolean",
            "unit": "",
            "optional": True,
            "notice": "Selects grid interpolation for fresh initialization. POP requires T; "
                      "LTE requires F. Selecting POP enables this switch in the form.",
        },
        "POP_SCALE": {
            "label": "Scale initial populations",
            "group": "Initialization",
            "kind": "boolean",
            "unit": "",
            "optional": True,
            "notice": "Normalize initial populations to the target model. POP requires T. "
                      "Selecting POP enables this switch in the form.",
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
    "ADJUST_CORRECTIONS": {
        "RELAX": {
            "label": "Correction relaxation", "group": "Correction relaxation",
            "kind": "float", "unit": "factor",
            "notice": "Scales corrections within this file's depth range. Values below 1 damp "
                      "updates and may still be needed to prevent oscillations. Review the depth "
                      "range in the text editor and test changes on a copy.",
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
            "notice": "Allow native handoff from requested Lambda iterations to full iterations "
                      "when its switching criteria are met. F retains manual control of this handoff.",
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
    "Correction relaxation",
    "Stellar and wind",
    "Clumping",
    "Composition",
    "Additional abundances",
    "Initialization",
    "Convergence and solver controls",
    "Advanced solver controls",
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
) -> list[tuple[str, dict[str, object]]]:
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
    if not value and field.get("missing") and field.get("optional"):
        return ""
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
        if key in {"T_EXC", "EPS_TERM", "TEFF"} and parsed <= 0:
            raise ModelEditorError(f"[{key}] must be positive")
        if key == 'RELAX' and parsed <= 0:
            raise ModelEditorError('[RELAX] must be positive.')
        if key in {"MAX_LIN", "MAX_LAM"} and parsed <= 1:
            raise ModelEditorError(f"[{key}] must exceed 1.")
        if key == "MAX_DT" and not 0 < parsed <= 0.2:
            raise ModelEditorError("[MAX_dT] must be greater than 0 and at most 0.2 (20%).")
        if key == "FIX_BA" and parsed < 0:
            raise ModelEditorError("[FIX_BA] must be non-negative.")
        return value
    if kind == "token":
        if len(value) > 64 or QUICK_TOKEN_RE.fullmatch(value) is None:
            raise ModelEditorError(f"[{key}] must be a single control token.")
        if field.get("choices"):
            if value.upper() not in {choice[0] for choice in field["choices"]}:
                raise ModelEditorError(f"Unsupported [{key}] selection")
            return value.upper()
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


def ba_reuse_disabled(contents: str) -> bool:
    """Recognize explicit controls that rebuild BA on every full iteration."""
    rows = _keyword_occurrences(contents)
    if any(len(rows.get(key, [])) != 1 for key in ('COMP_BA', 'N_FIX_BA')):
        return False
    if rows['COMP_BA'][0]['value'].upper() != 'T':
        return False
    try:
        return parse_float_token(rows['N_FIX_BA'][0]['value']) == 0
    except (ValueError, TypeError):
        return False


def _quick_card_from_record(record: dict[str, object]) -> dict[str, object]:
    file_relpath = str(record["file_relpath"])
    occurrences = _keyword_occurrences(str(record["contents"]))
    fresh_ba = file_relpath == 'VADAT' and ba_reuse_disabled(str(record['contents']))
    notices = solver_settings_notices(str(record['contents']), file_relpath)
    fields: list[dict[str, object]] = []
    issues: list[str] = []
    for key, definition in _quick_parameter_definitions(file_relpath, occurrences):
        matches = occurrences.get(key, [])
        optional = key in {"DC_METH", "T_EXC"} or definition.get("optional", False)
        if not matches and not optional:
            continue
        if len(matches) > 1:
            issues.append(f"[{key}] occurs more than once and is available only in the text editor.")
            continue
        occurrence = matches[0] if matches else {"value": "", "comment": "Leave unset unless needed", "line_index": -1, "value_start": 0, "value_end": 0}
        safe_key = re.sub(r"[^A-Za-z0-9_-]+", "-", key).strip("-").lower()
        field = {
            **definition,
            **occurrence,
            "key": key,
            "missing": not matches,
            "optional": optional and not matches,
            "field_name": f"quick_value:{key}",
            "input_id": f"quick-{file_relpath.lower().replace('/', '-')}-{safe_key}",
            "ba_reuse_disabled": fresh_ba and key in {'N_FIX_BA', 'FIX_BA'},
            "solver_notice": next((n for n in notices if n['key'] == key), None),
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
                    "collapsed": group_name in {"Additional abundances", "Initialization",
                                                "Advanced solver controls"},
                    "open": group_name == 'Advanced solver controls' and (fresh_ba or any(
                        f['solver_notice'] and f['solver_notice']['active'] for f in group_fields)),
                }
            )
    return {
        "file_relpath": file_relpath,
        "label": ("Model setup" if file_relpath == "VADAT" else
                  "Correction relaxation" if file_relpath == 'ADJUST_CORRECTIONS' else "Run controls"),
        "description": (
            "Stellar, wind, clumping, composition, initialization, and solver controls."
            if file_relpath == "VADAT"
            else "Scoped correction damping; depth limits and other controls are preserved."
            if file_relpath == 'ADJUST_CORRECTIONS' else "Iteration count and automatic iteration switches."
        ),
        "keep_temperature_logg": False,
        "keep_luminosity_logg": False,
        "luminosity_scaling": scaling,
        "digest": str(record["digest"]),
        "fields": fields,
        "groups": groups,
        "issues": issues,
        "ba_reuse_disabled": fresh_ba,
        "solver_notices": notices,
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
    keep_luminosity_logg: bool = False,
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
    values = dict(values)
    for field in fields:
        if field.get("missing"):
            values.setdefault(str(field["key"]), "")
    if set(values) != expected_keys:
        raise ModelEditorError("The submitted quick-parameter set does not match the current file.")

    if keep_temperature_logg and keep_luminosity_logg:
        raise ModelEditorError("Choose only one stellar scaling constraint.")
    if keep_temperature_logg or keep_luminosity_logg:
        scaling = card["luminosity_scaling"]
        if not scaling or not scaling["available"]:
            reason = str(scaling["reason"]) if scaling else "This option requires VADAT."
            raise ModelEditorError("Cannot apply stellar scaling. " + reason)
        baseline = scaling["baseline"]
        fields_by_key = {str(field["key"]): field for field in fields}
        fixed = "TEFF" if keep_temperature_logg else "LSTAR"
        driver = "LSTAR" if keep_temperature_logg else "TEFF"
        for key in (fixed, "LOGG"):
            value = parse_float_token(_validate_quick_parameter_value(fields_by_key[key], values[key]))
            if value != baseline[key]:
                raise ModelEditorError(f"[{key}] must remain unchanged with the selected scaling constraint.")
            values[key] = fields_by_key[key]["value"]
        target = parse_float_token(_validate_quick_parameter_value(fields_by_key[driver], values[driver]))
        if target <= 0:
            raise ModelEditorError(f"[{driver}] must be positive for stellar scaling.")
        try:
            factor = target / baseline[driver] if keep_temperature_logg else (baseline[driver] / target)**4
            radius = baseline["RSTAR"] * math.sqrt(factor)
            mass = baseline["MASS"] * factor
        except (OverflowError, ZeroDivisionError):
            raise ModelEditorError("Stellar scaling must yield a finite positive radius and mass.") from None
        if not all(math.isfinite(value) and value > 0 for value in (factor, radius, mass)):
            raise ModelEditorError("Stellar scaling must yield a finite positive radius and mass.")
        if target == baseline[driver]:
            values.update({key: fields_by_key[key]["value"] for key in ("RSTAR", "MASS")})
        else:
            values.update(RSTAR=f"{radius:.12g}", MASS=f"{mass:.12g}")
        card["keep_temperature_logg"] = keep_temperature_logg
        card["keep_luminosity_logg"] = keep_luminosity_logg

    lines = str(record["contents"]).splitlines(keepends=True)
    for field in fields:
        key = str(field["key"])
        value = _validate_quick_parameter_value(field, values[key])
        if field.get("missing"):
            field["value"] = value
            if value:
                if lines and not lines[-1].endswith("\n"):
                    lines[-1] += "\n"
                lines.append(f"{value:<13} [{key}]\n")
            continue
        line_index = int(field["line_index"])
        value_start = int(field["value_start"])
        value_end = int(field["value_end"])
        line = lines[line_index]
        lines[line_index] = f"{line[:value_start]}{value}{line[value_end:]}"
        field["value"] = value
    contents = "".join(lines)
    if file_relpath == "VADAT":
        original = _keyword_occurrences(str(record["contents"]))
        updated = _keyword_occurrences(contents)
        method = updated.get("DC_METH", [])
        changed = any([r["value"] for r in original.get(key, [])] != [r["value"] for r in updated.get(key, [])]
                      for key in ("DC_METH", "T_EXC", "LIN_INT", "POP_SCALE"))
        if len(method) == 1 and method[0]["value"].upper() == "POP":
            for key in ("LIN_INT", "POP_SCALE"):
                rows = updated.get(key, [])
                if len(rows) != 1 or rows[0]["value"].upper() != "T":
                    raise ModelEditorError(
                        f"[DC_METH]=POP requires [{key}]=T. "
                        "Enable both switches in Initialization before reviewing or saving.")
        if changed and len(method) == 1 and method[0]["value"].upper() == "LTE":
            rows = updated.get("T_EXC", [])
            if len(rows) != 1:
                raise ModelEditorError("Specify [T_EXC] for LTE initialization; 1.0 means 10,000 K for initial estimates.")
            try:
                lte_initialization_controls(contents, parse_float_token(rows[0]["value"]))
            except (ValueError, TypeError) as exc:
                raise ModelEditorError(str(exc)) from exc
    return card, contents


def review_quick_model_parameter_edit(
    basepath: str,
    *,
    model_relpath: str,
    file_relpath: str,
    expected_digest: str,
    values: dict[str, object],
    keep_temperature_logg: bool = False,
    keep_luminosity_logg: bool = False,
) -> dict[str, object]:
    card, contents = _prepare_quick_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        values=values,
        keep_temperature_logg=keep_temperature_logg,
        keep_luminosity_logg=keep_luminosity_logg,
    )
    review = review_model_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        contents=contents,
    )
    if keep_temperature_logg or keep_luminosity_logg:
        review["warnings"] = [*review["warnings"], *card["luminosity_scaling"]["warnings"]]
    return {
        **review,
        "card": card,
        "values": {field["key"]: field["value"] for field in card["fields"]},
        "keep_temperature_logg": keep_temperature_logg,
        "keep_luminosity_logg": keep_luminosity_logg,
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
    keep_luminosity_logg: bool = False,
) -> dict[str, object]:
    review = review_quick_model_parameter_edit(
        basepath,
        model_relpath=model_relpath,
        file_relpath=file_relpath,
        expected_digest=expected_digest,
        values=values,
        keep_temperature_logg=keep_temperature_logg,
        keep_luminosity_logg=keep_luminosity_logg,
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
