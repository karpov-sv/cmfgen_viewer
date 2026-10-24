"""Read-only physical-input validation before a CMFGEN run."""

from __future__ import annotations

import filecmp
import math
import os
import re
from pathlib import Path

from .control_files import control_occurrences
from .model_editor import EDITABLE_MODEL_FILES
from .parsers.common import parse_float_token
from .runner_validation import validate_rosseland_table

SEVERITIES = ("error", "warning", "info")
REQUIRED_FILES = ("VADAT", "MODEL_SPEC", "IN_ITS")
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
RVSIG_DEPTH_RE = re.compile(r"^\s*(\d+)\s*(?:!.*\bNumber of depth points\b.*)?\s*$", re.IGNORECASE)
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
    occurrences = control_occurrences(contents)
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
                    "warning",
                    "empty-script",
                    "Terminal launcher batch.sh is empty or unreadable; the native runner does not execute it.",
                    file="batch.sh",
                )
            )
        if not os.access(batch, os.X_OK):
            issues.append(
                _issue(
                    "warning",
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


def _printed_relative_precision(token: str, number: float) -> float:
    """Half the last printed digit, expressed relative to a positive value."""
    text = token.strip().rstrip(',;').upper().replace('D', 'E')
    if 'E' not in text:
        text = re.sub(r'(?<=[0-9.])([+-]\d+)$', r'E\1', text)
    mantissa, _, exponent = text.partition('E')
    decimals = len(mantissa.partition('.')[2])
    try:
        return (0.5 * 10.0 ** (int(exponent or '0') - decimals)) / number
    except (OverflowError, ValueError):
        return math.inf


def _rvsig_gradient_warning(radii, velocities, sigmas, tokens, lines, issues):
    """Advisory screening of well-resolved, locally smooth interior gradients."""
    log_r = [math.log(r) for r in radii]
    log_v = [math.log(v) for v in velocities]
    r_error = [_printed_relative_precision(t[0], r) for t, r in zip(tokens, radii)]
    v_error = [_printed_relative_precision(t[1], v) for t, v in zip(tokens, velocities)]
    suspect = []
    for i in range(1, len(radii) - 1):
        left, right = log_r[i-1] - log_r[i], log_r[i] - log_r[i+1]
        dv_left, dv_right = log_v[i-1] - log_v[i], log_v[i] - log_v[i+1]
        # Require changes well above text-rounding uncertainty on both sides.
        if (left <= 20 * (r_error[i-1] + r_error[i]) or
                right <= 20 * (r_error[i] + r_error[i+1]) or
                abs(dv_left) <= 20 * (v_error[i-1] + v_error[i]) or
                abs(dv_right) <= 20 * (v_error[i] + v_error[i+1])):
            continue
        slope_left, slope_right = dv_left / left, dv_right / right
        if (slope_left * slope_right <= 0 or
                abs(slope_left - slope_right) > 0.5 * max(abs(slope_left), abs(slope_right))):
            continue  # A turning point or steep curvature needs a better-resolved grid.
        estimated = (right * slope_left + left * slope_right) / (left + right)
        reported = sigmas[i] + 1
        if abs(reported - estimated) > max(0.5, 0.5 * max(abs(reported), abs(estimated))):
            suspect.append((i, reported, estimated))
    if suspect:
        i, reported, estimated = suspect[0]
        issues.append(_issue('warning', 'structure-sigma-gradient-mismatch',
            f'Sigma differs substantially from the resolved numerical velocity gradient at '
            f'{len(suspect)} interior depth(s). At depth {i+1}, sigma+1 is {reported:.6g}, '
            f'while dln(V)/dln(R) is approximately {estimated:.6g}. Review the profile or '
            'use Update structure → Recalculate sigma. This is advisory, not a physical-validity test.',
            file='RVSIG_COL', line=lines[i]))


def _validate_rvsig(
    model_dir: Path,
    *,
    nd: int | None,
    rmax: float | None,
    vinf: float | None,
    required: bool,
    issues: list[dict[str, object]],
) -> None:
    relative_name = 'RVSIG_COL'
    path = model_dir / relative_name
    if not required:
        return
    if not path.is_file():
        issues.append(_issue('error', 'missing-structure',
            'The current model setup requires RVSIG_COL, but it is unavailable.',
            file=relative_name, available=False))
        return
    declared = declared_line = None
    indices, radii, velocities, sigmas, tokens, lines = [], [], [], [], [], []
    malformed, nonfinite, invalid_density = [], [], []
    try:
        with path.open('r', encoding='utf-8', errors='replace') as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.split('!', 1)[0].strip()
                if not stripped or stripped.startswith('#'):
                    continue
                if declared is None:
                    match = RVSIG_DEPTH_RE.match(line)
                    if match:
                        declared, declared_line = int(match[1]), line_number
                    continue
                fields = stripped.split()
                # Native reads need three columns; standard exports add an index,
                # optionally preceded by Tau or density/clumping columns.
                indexed = len(fields) in {4, 5, 6} and INTEGER_RE.fullmatch(fields[-1])
                if len(fields) != 3 and not indexed:
                    malformed.append(line_number)
                    continue
                numeric = fields[:-1] if indexed else fields
                values = []
                for token in numeric:
                    value = parse_float_token(token)
                    if value is None and re.fullmatch(r'[+-]?(?:nan|inf(?:inity)?)', token, re.I):
                        value = float(token)
                    values.append(value)
                if any(v is None for v in values):
                    malformed.append(line_number)
                    continue
                if not all(math.isfinite(v) for v in values):
                    nonfinite.append(line_number)
                if len(fields) == 6 and any(v <= 0 for v in values[3:5]):
                    invalid_density.append(line_number)
                indices.append(int(fields[-1]) if indexed else None)
                radii.append(values[0])
                velocities.append(values[1])
                sigmas.append(values[2])
                tokens.append(fields)
                lines.append(line_number)
    except OSError as exc:
        issues.append(_issue('error', 'unreadable-structure',
            f'RVSIG_COL could not be read: {exc}.', file=relative_name))
        return
    if declared is None:
        issues.append(_issue('error', 'missing-depth-count',
            'RVSIG_COL has no declared number of depth points.', file=relative_name))
        return
    if declared <= 0:
        issues.append(_issue('error', 'invalid-depth-count',
            f'RVSIG_COL declares a nonpositive depth count ({declared}).',
            file=relative_name, line=declared_line))
    if nd is not None and declared != nd:
        issues.append(_issue('error', 'structure-grid-mismatch',
            f'RVSIG_COL declares {declared} depth points, while MODEL_SPEC [ND] is {nd}.',
            file=relative_name, line=declared_line))
    if len(radii) != declared:
        issues.append(_issue('error', 'structure-row-count',
            f'RVSIG_COL declares {declared} depth points but contains {len(radii)} parsed rows.',
            file=relative_name, line=declared_line))
    elif any(i is not None for i in indices) and indices != list(range(1, declared+1)):
        issues.append(_issue('warning', 'structure-index-sequence',
            'RVSIG_COL row indices are not the expected sequence 1 through ND.', file=relative_name))
    for affected, code, detail in (
        (malformed, 'structure-invalid-row', 'malformed or nonnumeric data rows'),
        (nonfinite, 'structure-nonfinite-data', 'nonfinite numeric values'),
        (invalid_density, 'structure-invalid-density', 'nonpositive density or clumping values'),
    ):
        if affected:
            issues.append(_issue('error', code,
                f'RVSIG_COL contains {detail} at {len(affected)} row(s); first at line {affected[0]}.',
                file=relative_name, line=affected[0]))
    if not radii or malformed or nonfinite:
        return  # Do not compute ratios/gradients from incomplete or nonfinite vectors.
    positive_r = all(r > 0 for r in radii)
    positive_v = all(v > 0 for v in velocities)
    ordered_r = all(a > b for a, b in zip(radii, radii[1:]))
    for valid, code, detail, affected in (
        (positive_r, 'structure-nonpositive-radius', 'radii must be positive',
         [lines[i] for i, r in enumerate(radii) if r <= 0]),
        (positive_v, 'structure-nonpositive-velocity', 'velocities must be positive',
         [lines[i] for i, v in enumerate(velocities) if v <= 0]),
        (ordered_r, 'structure-radius-order', 'radii must decrease strictly with depth index',
         [lines[i+1] for i, (a, b) in enumerate(zip(radii, radii[1:])) if a <= b]),
    ):
        if not valid:
            issues.append(_issue('error', code, 'RVSIG_COL ' + detail + '.',
                                 file=relative_name, line=affected[0]))
    if positive_r and ordered_r and rmax is not None and len(radii) >= 2:
        generated_rmax = radii[0] / radii[-1]
        tolerance = 0.1 * abs(radii[0] - radii[1]) / radii[-1]
        if not math.isfinite(generated_rmax) or abs(generated_rmax - rmax) > tolerance:
            issues.append(_issue('error', 'structure-radius-ratio-mismatch',
                f'RVSIG_COL has an outer-to-inner radius ratio of {generated_rmax:.10g}, '
                f'while VADAT [RMAX] is {rmax:.10g}.', file=relative_name))
    if positive_v and vinf is not None and vinf > 0.1:
        if abs(velocities[0] - vinf) / velocities[0] > 0.1:
            issues.append(_issue('error', 'structure-terminal-velocity-mismatch',
                f'RVSIG_COL has an outer-grid velocity of {velocities[0]:.10g} km/s, '
                f'while VADAT [VINF] is {vinf:.10g} km/s; CMFGEN allows at most a 10% difference.',
                file=relative_name))
    low_sigma = [i for i, s in enumerate(sigmas) if s < -1]
    if low_sigma:
        issues.append(_issue('warning', 'structure-negative-gradient',
            f'RVSIG_COL has sigma < -1 at {len(low_sigma)} depth(s), implying a negative '
            'radial velocity gradient. Review the intended velocity law; CMFGEN may not handle '
            'nonmonotonic flow.', file=relative_name, line=lines[low_sigma[0]]))
    if positive_v:
        reversals = [i for i, (a, b) in enumerate(zip(velocities, velocities[1:])) if a <= b]
        if reversals:
            issues.append(_issue('warning', 'structure-velocity-order',
                f'RVSIG_COL velocity is not strictly increasing with radius in {len(reversals)} '
                'interval(s). Repeated values can reflect text rounding; review any genuine reversal.',
                file=relative_name, line=lines[reversals[0]]))
    if positive_r and ordered_r and positive_v and len(radii) == declared:
        _rvsig_gradient_warning(radii, velocities, sigmas, tokens, lines, issues)


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


def _validate_hydro_opacity(model_dir: Path, vadat: dict, issues: list[dict[str, object]]) -> None:
    rows = vadat.get("DO_HYDRO", [])
    if len(rows) != 1 or str(rows[0]["value"]).upper() != "T":
        return
    defaults = model_dir / "HYDRO_DEFAULTS"
    try:
        remaining = control_occurrences(defaults.read_text()).get("N_ITS", [])
    except (OSError, UnicodeError):
        remaining = []
    # Native hydro returns before using opacity when all revisions are done.
    if len(remaining) == 1 and str(remaining[0]["value"]) == "0":
        return
    table = model_dir / "ROSSELAND_LTE_TAB"
    if not table.is_file():
        issues.append(_issue(
            "error", "missing-hydro-opacity",
            "VADAT [DO_HYDRO]=T requires ROSSELAND_LTE_TAB in the model root, including for continuation. "
            "Restore a compatible LTE opacity table or generate one with the LTE stage.",
            file=table.name, available=False,
        ))
        return
    try:
        validate_rosseland_table(table)
    except (OSError, ValueError, UnicodeError) as exc:
        issues.append(_issue(
            "error", "invalid-hydro-opacity",
            f"Invalid hydro input ROSSELAND_LTE_TAB: {exc}. "
            "Restore a compatible complete LTE opacity table or regenerate it before running main/test.",
            file=table.name,
        ))


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
    from .structure_update import inspect_structure_update
    structure = inspect_structure_update(model_dir)
    if structure['required']:
        issues.append(_issue('error', 'structure-update-required',
            structure['message'] + ' Use Edit Parameters → Update structure before running.',
            file='RVSIG_COL', available=(model_dir / 'RVSIG_COL').is_file()))
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
    rmax = None
    vinf = None
    if "VADAT" in controls:
        _validate_booleans(vadat, file="VADAT", issues=issues)
        for key in POSITIVE_VADAT_CONTROLS:
            value = _numeric_control(
                vadat,
                key,
                file="VADAT",
                issues=issues,
                positive=True,
            )
            if key == "RMAX":
                rmax = value
            elif key == "VINF":
                vinf = value
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
        rmax=rmax,
        vinf=vinf,
        required=uses_rvsig or (model_dir / "lte").is_dir(),
        issues=issues,
    )
    _validate_hydro_opacity(model_dir, vadat, issues)
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
