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
