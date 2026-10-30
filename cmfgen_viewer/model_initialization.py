"""Explicit, lossless LTE population initialization controls."""
import math

from .control_files import control_occurrences


def lte_initialization_controls(contents: str, t_exc: float = 1.0) -> str:
    if not math.isfinite(t_exc) or t_exc <= 0:
        raise ValueError("T_EXC must be positive and finite (units of 10^4 K)")
    rows = control_occurrences(contents)
    for key in ("DC_METH", "T_EXC", "LIN_INT", "LTE_EST"):
        if len(rows.get(key, [])) > 1:
            raise ValueError(f"Duplicate [{key}]; resolve it before selecting LTE initialization")
    for key in ("LIN_INT", "LTE_EST"):
        if rows.get(key) and rows[key][0]["value"].upper() not in {"F", "FALSE", ".FALSE."}:
            raise ValueError(f"LTE departure-coefficient initialization requires [{key}]=F")
    lines = contents.splitlines(keepends=True)
    for key, value in {"DC_METH": "LTE", "T_EXC": f"{t_exc:.12g}"}.items():
        if rows.get(key):
            row = rows[key][0]
            i = row["line_index"]
            lines[i] = lines[i][:row["value_start"]] + value + lines[i][row["value_end"]:]
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{value:<13} [{key}]\n")
    return "".join(lines)


def opacity_lte_seed_controls(contents: str, t_exc: float = 1.0, *, structure=False) -> dict:
    """A diagnosed fresh POP seed may use LTE on the same temperature grid.

    This is an internal zero-iteration recovery mode, not permission for the
    ordinary LTE flag to override interpolation or to reseed a continuation.
    The caller restores the whole original VADAT using TemporaryControl.
    """
    from .runner_controls import _patch
    rows = control_occurrences(contents)
    for key in ('DC_METH', 'LIN_INT', 'IT_ON_T', 'T_EXC', 'LTE_EST', 'T_ON_R', 'SN_MODEL',
                'REVISE_R_GRID', 'FLUX_CAL_ONLY', 'USE_FIXED_J'):
        if len(rows.get(key, [])) > 1:
            raise ValueError(f'Duplicate [{key}]; opacity seed recovery refused')
    value = lambda key, default='': rows[key][0]['value'].upper().strip('.') if rows.get(key) else default
    if value('DC_METH') != 'POP' or value('LIN_INT') not in {'T', 'TRUE'}:
        raise ValueError('Opacity LTE seed requires an explicit interpolated POP fresh-start model')
    for key in ('SN_MODEL', 'REVISE_R_GRID', 'FLUX_CAL_ONLY', 'USE_FIXED_J'):
        if value(key, 'F') not in {'F', 'FALSE'}:
            raise ValueError(f'Opacity LTE seed is not validated with [{key}] enabled')
    if not structure and value('T_ON_R', 'T') not in {'T', 'TRUE'}:
        raise ValueError('Opacity LTE seed is validated only with the ordinary radius temperature interpolation')
    changes = {'LIN_INT': 'F', 'IT_ON_T': 'F', 'DC_METH': 'LTE', 'T_EXC': f'{t_exc:.12g}'}
    lte_initialization_controls(_patch(contents, {'LIN_INT': 'F', 'IT_ON_T': 'F'}), t_exc)
    if structure:
        changes['LTE_EST'] = 'T'
    return changes
