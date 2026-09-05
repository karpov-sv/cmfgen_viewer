"""Model control/output metadata and summary presentation."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .control_files import tokenize_control
from .parsers.common import format_number, parse_float_token
from .parsers.mod_sum import read_mod_sum
from .spectrum_constants import MAX_MODEL_TIME_LINES, MAX_SPECIES_ROWS

VADAT_ENTRY_RE = re.compile(r"^\s*(\S+)\s+\[(\S*)\]")


def _safe_stat(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _parse_float_legacy(value: str):
    stripped = value.strip().replace("D", "E").replace("d", "e")
    parsed = parse_float_token(stripped)
    if parsed is not None:
        return parsed

    match = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$", stripped)
    if match:
        try:
            return float(f"{match.group(1)}E{match.group(2)}")
        except ValueError:
            return stripped
    return stripped


def _as_text(value: object) -> str:
    if isinstance(value, float | int):
        return format_number(value)
    return str(value)


def _parse_vadat(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for row in tokenize_control(path.read_text(encoding="utf-8", errors="replace")):
        values[row.key] = row.value
    return values


def _parse_mod_sum(path: Path, do_cl_flag: str = "F") -> dict[str, object]:
    if not path.is_file():
        return {"params": {}, "ions": [], "species": {}, "time": "", "maxcorr": ""}
    data = read_mod_sum(path)
    params = dict(data.parameters)
    if str(do_cl_flag).upper() != "T":
        params = {
            key: value for key, value in params.items() if not key.startswith("CL_P_")
        }
    return {
        "params": params,
        "ions": data.ions,
        "species": data.species,
        "time": "".join(data.time_lines),
        "maxcorr": data.max_correction_pct
        if data.max_correction_pct is not None
        else "",
        **data.dimensions,
    }


@lru_cache(maxsize=64)
def _read_model_cached(
    path_str: str,
    vadat_mtime: int,
    vadat_size: int,
    mod_sum_mtime: int,
    mod_sum_size: int,
) -> dict[str, object]:
    del vadat_mtime, vadat_size, mod_sum_mtime, mod_sum_size
    model_dir = Path(path_str)
    model: dict[str, object] = {"params": {}, "ions": [], "species": {}, "vadat": {}}
    model["path"] = str(model_dir)
    model["name"] = model_dir.name
    vadat = _parse_vadat(model_dir / "VADAT")
    model["vadat"] = vadat

    mod_sum = _parse_mod_sum(
        model_dir / "MOD_SUM", do_cl_flag=str(vadat.get("DO_CL", "F"))
    )
    if isinstance(mod_sum.get("params"), dict):
        model["params"] = mod_sum["params"]
    if isinstance(mod_sum.get("ions"), list):
        model["ions"] = mod_sum["ions"]
    if isinstance(mod_sum.get("species"), dict):
        model["species"] = mod_sum["species"]
    if "time" in mod_sum:
        model["time"] = mod_sum["time"]
    if "maxcorr" in mod_sum:
        model["maxcorr"] = mod_sum["maxcorr"]
    for key, value in mod_sum.items():
        if key in {"params", "ions", "species", "time", "maxcorr", "vadat"}:
            continue
        model[key] = value
    return model


def read_model(model_dir: Path) -> dict[str, object]:
    vadat = model_dir / "VADAT"
    mod_sum = model_dir / "MOD_SUM"
    vadat_mtime, vadat_size = _safe_stat(vadat) if vadat.is_file() else (0, 0)
    mod_sum_mtime, mod_sum_size = _safe_stat(mod_sum) if mod_sum.is_file() else (0, 0)
    return _read_model_cached(
        str(model_dir.resolve()),
        vadat_mtime,
        vadat_size,
        mod_sum_mtime,
        mod_sum_size,
    )


def build_model_summary_sections(model: dict[str, object]) -> list[dict[str, object]]:
    params = model.get("params")
    vadat = model.get("vadat")
    species = model.get("species")
    if not isinstance(params, dict):
        params = {}
    if not isinstance(vadat, dict):
        vadat = {}
    if not isinstance(species, dict):
        species = {}

    time_raw = str(model.get("time", "")).strip()
    time_lines = [line.strip() for line in time_raw.splitlines() if line.strip()][
        :MAX_MODEL_TIME_LINES
    ]
    time_text = " | ".join(time_lines)

    metadata_rows = [
        ("Model name", _as_text(model.get("name", ""))),
        ("Model path", _as_text(model.get("path", ""))),
        ("Run time block", time_text),
    ]
    metadata_rows = [(label, value) for label, value in metadata_rows if value]

    key_param_rows = [
        ("Luminosity (L*)", params.get("L*")),
        ("Mass-loss rate (Mdot)", params.get("Mdot")),
        ("T* temperature (K)", params.get("T*(K)")),
        ("Effective temperature (K)", params.get("Teff(K)")),
        ("Log g", params.get("Log_g")),
        ("Vinf1", params.get("Vinf1")),
        ("Velocity law", vadat.get("VEL_LAW")),
        ("CL_PAR_1", vadat.get("CL_PAR_1")),
        ("CL_PAR_2", vadat.get("CL_PAR_2")),
    ]
    parameter_rows = [
        (label, _as_text(value))
        for label, value in key_param_rows
        if value not in (None, "")
    ]

    composition_rows: list[tuple[str, str]] = []
    hyd = species.get("HYD")
    if isinstance(hyd, dict) and "mass_frac" in hyd:
        composition_rows.append(
            ("Hydrogen mass fraction", _as_text(hyd.get("mass_frac", "")))
        )
    for key, label in [
        ("HYD", "Hydrogen number fraction"),
        ("CARB", "Carbon number fraction"),
        ("NIT", "Nitrogen number fraction"),
        ("OXY", "Oxygen number fraction"),
        ("IRON", "Iron number fraction"),
    ]:
        data = species.get(key)
        if not isinstance(data, dict):
            continue
        rel = data.get("rel_frac")
        if rel in (None, ""):
            continue
        composition_rows.append((label, _as_text(rel)))

    species_rows: list[list[str]] = []
    for name in sorted(species.keys()):
        data = species[name]
        if not isinstance(data, dict):
            continue
        rel = _as_text(data.get("rel_frac", ""))
        mass = _as_text(data.get("mass_frac", ""))
        if not rel and not mass:
            continue
        species_rows.append([str(name), rel, mass])
    species_rows = species_rows[:MAX_SPECIES_ROWS]

    dimensions_rows = []
    for key in ("ND", "NC", "NP", "NCF"):
        value = model.get(key)
        if value in (None, ""):
            continue
        dimensions_rows.append((key, _as_text(value)))

    return [
        {"title": "Metadata", "rows": metadata_rows},
        {"title": "Key Parameters", "rows": parameter_rows},
        {"title": "Composition Highlights", "rows": composition_rows},
        {"title": "Dimensions", "rows": dimensions_rows},
        {
            "title": "Species Table",
            "rows": species_rows,
            "columns": ["Species", "Rel. # Fraction", "Mass Fraction"],
        },
    ]
