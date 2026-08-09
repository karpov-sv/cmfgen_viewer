"""Conservative, read-only validation before an external CMFGEN run."""

from __future__ import annotations

import filecmp
import math
import os
from pathlib import Path
import re

from .model_editor import EDITABLE_MODEL_FILES
from .parsers.common import parse_float_token
from .parsers.extended_text import KEYWORD_ROW_RE


SEVERITIES = ("error", "warning", "info")
REQUIRED_FILES = ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS")
BOOLEAN_CONTROLS = {
    "VADAT": ("DO_CL", "DO_HYDRO", "RD_IN_R_GRID", "LIN_INT", "POP_SCALE", "IT_ON_T"),
    "IN_ITS": ("DO_LAM_IT", "DO_LAM_AUTO", "DO_T_AUTO", "DO_GT_AUTO"),
}
POSITIVE_VADAT_CONTROLS = ("RSTAR", "RMAX", "VINF", "LSTAR", "MASS", "TEFF")
SPECTRUM_NUMERIC_CONTROLS = (
    "VTURB_FIX",
    "VTURB_MIN",
    "VTURB_MAX",
    "F_LAM_BEG",
    "F_LAM_END",
)
RVSIG_DEPTH_RE = re.compile(r"^\s*(\d+)\s*(?:!.*Number of depth points)?\s*$", re.IGNORECASE)
INTEGER_RE = re.compile(r"^[+-]?\d+$")


def _issue(
    severity: str,
    code: str,
    message: str,
    *,
    file: str | None = None,
    line: int | None = None,
    available: bool = True,
) -> dict[str, object]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "file": file,
        "line": line,
        "available": available,
        "editable": bool(file and file in EDITABLE_MODEL_FILES and available),
    }


def _read_control(
    model_dir: Path,
    relative_name: str,
    issues: list[dict[str, object]],
) -> tuple[str, dict[str, list[dict[str, object]]]] | None:
    path = model_dir.joinpath(*Path(relative_name).parts)
    if not path.is_file():
        return None
    try:
        if path.stat().st_size == 0:
            issues.append(
                _issue(
                    "error",
                    "empty-file",
                    f"{relative_name} is empty.",
                    file=relative_name,
                )
            )
            return None
        if path.stat().st_size > 2 * 1024 * 1024:
            issues.append(
                _issue(
                    "error",
                    "control-file-too-large",
                    f"{relative_name} is unexpectedly large for a text control file.",
                    file=relative_name,
                )
            )
            return None
        contents = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        issues.append(
            _issue(
                "error",
                "unreadable-file",
                f"{relative_name} could not be read: {exc}.",
                file=relative_name,
            )
        )
        return None
    if "\ufffd" in contents:
        issues.append(
            _issue(
                "warning",
                "invalid-text-bytes",
                f"{relative_name} contains byte sequences that are not valid UTF-8.",
                file=relative_name,
            )
        )
    occurrences: dict[str, list[dict[str, object]]] = {}
    for line_number, line in enumerate(contents.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("!", "#")):
            continue
        match = KEYWORD_ROW_RE.match(line)
        if match is None:
            continue
        value, key, _comment = match.groups()
        occurrences.setdefault(key.upper(), []).append(
            {"value": value.strip(), "line": line_number}
        )
    if not occurrences:
        issues.append(
            _issue(
                "error",
                "no-control-rows",
                f"{relative_name} contains no active value [KEY] control rows.",
                file=relative_name,
            )
        )
        return None
    return contents, occurrences


def _single_control(
    occurrences: dict[str, list[dict[str, object]]],
    key: str,
    *,
    file: str,
    issues: list[dict[str, object]],
    required: bool,
) -> dict[str, object] | None:
    matches = occurrences.get(key, [])
    if not matches:
        if required:
            issues.append(
                _issue(
                    "error",
                    "missing-control",
                    f"{file} is missing required [{key}].",
                    file=file,
                )
            )
        return None
    if len(matches) > 1:
        issues.append(
            _issue(
                "error",
                "duplicate-control",
                f"{file} defines [{key}] {len(matches)} times; the active value is ambiguous.",
                file=file,
                line=int(matches[1]["line"]),
            )
        )
        return None
    return matches[0]


def _integer_control(
    occurrences: dict[str, list[dict[str, object]]],
    key: str,
    *,
    file: str,
    issues: list[dict[str, object]],
    minimum: int,
) -> int | None:
    match = _single_control(occurrences, key, file=file, issues=issues, required=True)
    if match is None:
        return None
    value = str(match["value"])
    if not INTEGER_RE.fullmatch(value):
        issues.append(
            _issue(
                "error",
                "invalid-integer",
                f"{file} [{key}] must be an integer, not {value!r}.",
                file=file,
                line=int(match["line"]),
            )
        )
        return None
    parsed = int(value)
    if parsed < minimum:
        qualifier = "positive" if minimum == 1 else f"at least {minimum}"
        issues.append(
            _issue(
                "error",
                "integer-out-of-range",
                f"{file} [{key}] must be {qualifier}; found {parsed}.",
                file=file,
                line=int(match["line"]),
            )
        )
        return None
    return parsed


def _numeric_control(
    occurrences: dict[str, list[dict[str, object]]],
    key: str,
    *,
    file: str,
    issues: list[dict[str, object]],
    required: bool = False,
    positive: bool = False,
) -> float | None:
    match = _single_control(
        occurrences,
        key,
        file=file,
        issues=issues,
        required=required,
    )
    if match is None:
        return None
    value = str(match["value"])
    parsed = parse_float_token(value)
    if parsed is None or not math.isfinite(parsed):
        issues.append(
            _issue(
                "error",
                "invalid-number",
                f"{file} [{key}] must be a finite number, not {value!r}.",
                file=file,
                line=int(match["line"]),
            )
        )
        return None
    if positive and parsed <= 0:
        issues.append(
            _issue(
                "error",
                "nonpositive-control",
                f"{file} [{key}] must be positive; found {value}.",
                file=file,
                line=int(match["line"]),
            )
        )
        return None
    return parsed


def _validate_booleans(
    occurrences: dict[str, list[dict[str, object]]],
    *,
    file: str,
    issues: list[dict[str, object]],
) -> None:
    for key in BOOLEAN_CONTROLS.get(file, ()):
        match = _single_control(
            occurrences,
            key,
            file=file,
            issues=issues,
            required=False,
        )
        if match is not None and str(match["value"]).upper() not in {"T", "F"}:
            issues.append(
                _issue(
                    "error",
                    "invalid-boolean",
                    f"{file} [{key}] must be T or F, not {match['value']!r}.",
                    file=file,
                    line=int(match["line"]),
                )
            )


def _validate_required_files(model_dir: Path, issues: list[dict[str, object]]) -> None:
    for relative_name in REQUIRED_FILES:
        path = model_dir / relative_name
        if not path.is_file():
            kind = "broken symbolic link" if path.is_symlink() else "missing file"
            issues.append(
                _issue(
                    "error",
                    "missing-file",
                    f"Required {relative_name} is a {kind}.",
                    file=relative_name,
                    available=False,
                )
            )
    batch = model_dir / "batch.sh"
    if batch.is_file():
        try:
            batch_empty = batch.stat().st_size == 0
        except OSError:
            batch_empty = True
        if batch_empty:
            issues.append(
                _issue(
                    "error",
                    "empty-script",
                    "batch.sh is empty or unreadable.",
                    file="batch.sh",
                )
            )
        if not os.access(batch, os.X_OK):
            issues.append(
                _issue(
                    "error",
                    "script-not-executable",
                    "batch.sh is not executable, so the displayed ./batch.sh command cannot run.",
                    file="batch.sh",
                )
            )


def _validate_gamma_input(model_dir: Path, issues: list[dict[str, object]]) -> None:
    gamma = next(
        (model_dir / name for name in ("GAMMAS_IN", "GAMMAS") if (model_dir / name).is_file()),
        None,
    )
    if gamma is None:
        issues.append(
            _issue(
                "error",
                "missing-gamma-input",
                "Neither GAMMAS_IN nor the GAMMAS fallback is available.",
                file="GAMMAS_IN",
                available=False,
            )
        )
        return
    try:
        empty = gamma.stat().st_size == 0
    except OSError:
        empty = True
    if empty:
        issues.append(
            _issue(
                "error",
                "empty-gamma-input",
                f"Selected gamma input {gamma.name} is empty or unreadable.",
                file=gamma.name,
            )
        )


def _validate_rvsig(
    model_dir: Path,
    *,
    nd: int | None,
    required: bool,
    issues: list[dict[str, object]],
) -> None:
    relative_name = "RVSIG_COL"
    path = model_dir / relative_name
    if not required:
        return
    if not path.is_file():
        issues.append(
            _issue(
                "error",
                "missing-structure",
                "The current model setup requires RVSIG_COL, but it is unavailable.",
                file=relative_name,
                available=False,
            )
        )
        return
    declared: int | None = None
    declared_line: int | None = None
    row_indices: list[int] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped or stripped.startswith(("!", "#")):
                    continue
                if declared is None:
                    match = RVSIG_DEPTH_RE.match(line)
                    if match:
                        declared = int(match.group(1))
                        declared_line = line_number
                        continue
                tokens = stripped.split()
                if len(tokens) not in {4, 5} or not INTEGER_RE.fullmatch(tokens[-1]):
                    continue
                if all(parse_float_token(token) is not None for token in tokens[:-1]):
                    row_indices.append(int(tokens[-1]))
    except OSError as exc:
        issues.append(
            _issue(
                "error",
                "unreadable-structure",
                f"RVSIG_COL could not be read: {exc}.",
                file=relative_name,
            )
        )
        return
    if declared is None:
        issues.append(
            _issue(
                "error",
                "missing-depth-count",
                "RVSIG_COL has no declared number of depth points.",
                file=relative_name,
            )
        )
        return
    if declared <= 0:
        issues.append(
            _issue(
                "error",
                "invalid-depth-count",
                f"RVSIG_COL declares a nonpositive depth count ({declared}).",
                file=relative_name,
                line=declared_line,
            )
        )
    if nd is not None and declared != nd:
        issues.append(
            _issue(
                "error",
                "structure-grid-mismatch",
                f"RVSIG_COL declares {declared} depth points, while MODEL_SPEC [ND] is {nd}.",
                file=relative_name,
                line=declared_line,
            )
        )
    if len(row_indices) != declared:
        issues.append(
            _issue(
                "error",
                "structure-row-count",
                f"RVSIG_COL declares {declared} depth points but contains {len(row_indices)} indexed rows.",
                file=relative_name,
                line=declared_line,
            )
        )
    elif row_indices != list(range(1, declared + 1)):
        issues.append(
            _issue(
                "warning",
                "structure-index-sequence",
                "RVSIG_COL row indices are not the expected sequence 1 through ND.",
                file=relative_name,
            )
        )


def _validate_spectrum_controls(
    model_dir: Path,
    issues: list[dict[str, object]],
) -> None:
    relative_name = "obs/CMF_FLUX_PARAM_INIT"
    path = model_dir / "obs" / "CMF_FLUX_PARAM_INIT"
    if not path.is_file():
        batch_path = model_dir / "batch.sh"
        try:
            batch_text = batch_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            batch_text = ""
        if re.search(r"^\s*cd\s+['\"]?obs(?:/|['\"]|\s|$)", batch_text, re.MULTILINE):
            issues.append(
                _issue(
                    "warning",
                    "missing-spectrum-controls",
                    "batch.sh enters obs/, but obs/CMF_FLUX_PARAM_INIT is unavailable.",
                    file=relative_name,
                    available=False,
                )
            )
        return
    parsed = _read_control(model_dir, relative_name, issues)
    if parsed is None:
        return
    _contents, occurrences = parsed
    values = {
        key: _numeric_control(
            occurrences,
            key,
            file=relative_name,
            issues=issues,
        )
        for key in SPECTRUM_NUMERIC_CONTROLS
    }
    for key in ("VTURB_FIX", "VTURB_MIN", "VTURB_MAX", "F_LAM_BEG"):
        value = values[key]
        if value is not None and value < 0:
            issues.append(
                _issue(
                    "error",
                    "negative-spectrum-control",
                    f"CMF_FLUX [{key}] must not be negative; found {value:g}.",
                    file=relative_name,
                )
            )
    if values["F_LAM_END"] is not None and values["F_LAM_END"] <= 0:
        issues.append(
            _issue(
                "error",
                "nonpositive-spectrum-end",
                "CMF_FLUX [F_LAM_END] must be positive.",
                file=relative_name,
            )
        )
    minimum = values["VTURB_MIN"]
    maximum = values["VTURB_MAX"]
    if None not in {minimum, maximum} and minimum > maximum:
        issues.append(
            _issue(
                "error",
                "turbulence-order",
                "CMF_FLUX [VTURB_MIN] must not exceed [VTURB_MAX].",
                file=relative_name,
            )
        )
    wavelength_begin = values["F_LAM_BEG"]
    wavelength_end = values["F_LAM_END"]
    if None not in {wavelength_begin, wavelength_end} and wavelength_begin >= wavelength_end:
        issues.append(
            _issue(
                "error",
                "wavelength-order",
                "CMF_FLUX [F_LAM_BEG] must be smaller than [F_LAM_END].",
                file=relative_name,
            )
        )
    obs_extent = _numeric_control(
        occurrences,
        "OBS_EXT_RAT",
        file=relative_name,
        issues=issues,
    )
    if obs_extent is not None and obs_extent < 1.0:
        issues.append(
            _issue(
                "warning",
                "small-observer-extent",
                f"CMF_FLUX [OBS_EXT_RAT] is {obs_extent:g}; values below 1 may clip the profile.",
                file=relative_name,
            )
        )


def _fresh_result(path: Path, dependencies: tuple[Path, ...]) -> bool:
    if not path.is_file() or not all(item.is_file() for item in dependencies):
        return False
    try:
        result_mtime = path.stat().st_mtime_ns
        input_mtimes = [item.stat().st_mtime_ns for item in dependencies]
    except OSError:
        return False
    return bool(input_mtimes) and result_mtime >= max(input_mtimes)


def _validate_lte_handoff(model_dir: Path, issues: list[dict[str, object]]) -> None:
    lte_dir = model_dir / "lte"
    if not lte_dir.is_dir():
        return
    pairs = (
        (
            lte_dir / "ROSSELAND_LTE_TAB",
            model_dir / "ROSSELAND_LTE_TAB",
            (lte_dir / "VADAT", lte_dir / "MODEL_SPEC", lte_dir / "GRID_PARAMS"),
        ),
        (
            lte_dir / "RVSIG_COL_NEW",
            model_dir / "RVSIG_COL",
            (lte_dir / "ROSSELAND_LTE_TAB", lte_dir / "HYDRO_PARAMS"),
        ),
    )
    for generated, promoted, dependencies in pairs:
        if not _fresh_result(generated, dependencies):
            continue
        try:
            generated_is_newer = (
                not promoted.is_file()
                or generated.stat().st_mtime_ns > promoted.stat().st_mtime_ns
            )
            matches = promoted.is_file() and filecmp.cmp(generated, promoted, shallow=False)
        except OSError:
            generated_is_newer = False
            matches = False
        if generated_is_newer and not matches:
            issues.append(
                _issue(
                    "error",
                    "unpromoted-lte-result",
                    f"Fresh lte/{generated.name} differs from the promoted {promoted.name}; review and promote the LTE/hydro result first.",
                    file=f"lte/{generated.name}",
                )
            )


def inspect_model_preflight(model_dir: Path) -> dict[str, object]:
    """Return reusable preflight issues without changing model files."""
    issues: list[dict[str, object]] = []
    _validate_required_files(model_dir, issues)
    _validate_gamma_input(model_dir, issues)

    controls: dict[str, dict[str, list[dict[str, object]]]] = {}
    for relative_name in ("VADAT", "MODEL_SPEC", "IN_ITS"):
        parsed = _read_control(model_dir, relative_name, issues)
        if parsed is not None:
            _contents, controls[relative_name] = parsed

    model_spec = controls.get("MODEL_SPEC", {})
    if "MODEL_SPEC" in controls:
        nd = _integer_control(
            model_spec,
            "ND",
            file="MODEL_SPEC",
            issues=issues,
            minimum=1,
        )
        nc = _integer_control(
            model_spec,
            "NC",
            file="MODEL_SPEC",
            issues=issues,
            minimum=0,
        )
        np_value = _integer_control(
            model_spec,
            "NP",
            file="MODEL_SPEC",
            issues=issues,
            minimum=1,
        )
    else:
        nd = None
        nc = None
        np_value = None
    if None not in {nd, nc, np_value}:
        minimum_np = int(nd) + int(nc)
        if int(np_value) < minimum_np:
            issues.append(
                _issue(
                    "error",
                    "impact-grid-too-small",
                    f"MODEL_SPEC [NP] is {np_value}, but at least ND + NC = {minimum_np} impact parameters are required.",
                    file="MODEL_SPEC",
                )
            )
        elif int(np_value) > minimum_np:
            issues.append(
                _issue(
                    "info",
                    "additional-impact-rays",
                    f"MODEL_SPEC includes {int(np_value) - minimum_np} additional impact parameter(s) beyond ND + NC.",
                    file="MODEL_SPEC",
                )
            )

    in_its = controls.get("IN_ITS", {})
    if "IN_ITS" in controls:
        _integer_control(
            in_its,
            "NUM_ITS",
            file="IN_ITS",
            issues=issues,
            minimum=1,
        )
        _validate_booleans(in_its, file="IN_ITS", issues=issues)

    vadat = controls.get("VADAT", {})
    if "VADAT" in controls:
        _validate_booleans(vadat, file="VADAT", issues=issues)
        for key in POSITIVE_VADAT_CONTROLS:
            _numeric_control(
                vadat,
                key,
                file="VADAT",
                issues=issues,
                positive=True,
            )
        do_cl_matches = vadat.get("DO_CL", [])
        if len(do_cl_matches) == 1 and str(do_cl_matches[0]["value"]).upper() == "T":
            clumping_count = _integer_control(
                vadat,
                "N_CL_PAR",
                file="VADAT",
                issues=issues,
                minimum=1,
            )
            if clumping_count is not None:
                for index in range(1, clumping_count + 1):
                    _numeric_control(
                        vadat,
                        f"CL_PAR_{index}",
                        file="VADAT",
                        issues=issues,
                        required=True,
                    )
        velocity_option = _single_control(
            vadat,
            "VEL_OPT",
            file="VADAT",
            issues=issues,
            required=False,
        )
        uses_rvsig = bool(
            velocity_option
            and str(velocity_option["value"]).strip().upper().startswith("RVSIG_COL")
        )
    else:
        uses_rvsig = False

    _validate_rvsig(
        model_dir,
        nd=nd,
        required=uses_rvsig or (model_dir / "lte").is_dir(),
        issues=issues,
    )
    _validate_spectrum_controls(model_dir, issues)
    _validate_lte_handoff(model_dir, issues)

    counts = {severity: 0 for severity in SEVERITIES}
    for issue in issues:
        relative_file = issue.get("file")
        if relative_file:
            issue_path = model_dir.joinpath(*Path(str(relative_file)).parts)
            issue["editable"] = bool(
                issue["available"]
                and relative_file in EDITABLE_MODEL_FILES
                and issue_path.is_file()
                and not issue_path.is_symlink()
            )
        counts[str(issue["severity"])] += 1
    return {
        "issues": issues,
        "counts": counts,
        "blocking": counts["error"] > 0,
        "passed": counts["error"] == 0,
    }
