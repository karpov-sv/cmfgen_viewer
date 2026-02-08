from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from .diagnostic_text import (
    parse_cfdat_out,
    parse_cont_freq,
    parse_departure_out_family,
    parse_gamflux,
    parse_gammas,
    parse_gamray_energy_dep,
    parse_hydro,
    parse_j_comp,
    parse_meanopac,
    parse_obs_freq,
    parse_obsframe,
    parse_out_flux,
    parse_out_params,
    parse_pop_family,
    parse_rate_file,
    parse_sob_force_mult,
    parse_trans_info,
)
from .mod_sum import parse_mod_sum
from .obsflux import parse_obsflux
from .rvtj import parse_rvtj

PARSERS = {
    "RVTJ": parse_rvtj,
    "OBSFLUX": parse_obsflux,
    "MOD_SUM": parse_mod_sum,
    "MEANOPAC": parse_meanopac,
    "HYDRO": parse_hydro,
    "OBSFRAME": parse_obsframe,
    "OUT_FLUX": parse_out_flux,
    "GAMMAS": parse_gammas,
    "GAMMAS_IN": parse_gammas,
    "J_COMP": parse_j_comp,
    "NETRATE": parse_rate_file,
    "TOTRATE": parse_rate_file,
    "EWDATA": parse_rate_file,
    "LINEHEAT": parse_rate_file,
    "TRANS_INFO": parse_trans_info,
    "SOB_FORCE_MULT": parse_sob_force_mult,
    "GAMFLUX": parse_gamflux,
    "GAMRAY_ENERGY_DEP": parse_gamray_energy_dep,
    "OUT_PARAMS": parse_out_params,
    "CFDAT_OUT": parse_cfdat_out,
    "CONT_FREQ": parse_cont_freq,
    "OBS_FREQ": parse_obs_freq,
}
POP_FAMILY_RE = re.compile(r"^POP[A-Z0-9_]+$")
DEPARTURE_OUT_RE = re.compile(r"^[A-Z0-9]+OUT$")
OBS_ALIAS_RE = re.compile(r"^OBS_(?:FIN|CONT)(?:[._].*)?$")

MAX_PARSE_FILE_BYTES = 256 * 1024 * 1024


def _resolve_parser(path: Path):
    name = path.name.upper()
    stem = path.stem.upper()
    names = (name, stem) if stem != name else (name,)

    for candidate in names:
        parser = PARSERS.get(candidate)
        if parser is not None:
            return parser

    if any(OBS_ALIAS_RE.match(candidate) for candidate in names):
        # `obs_fin*` / `obs_cont*` are post-processed OBSFLUX/OBSFRAME aliases.
        # Their content follows the OBSFLUX vector-block structure.
        return parse_obsflux

    if any(POP_FAMILY_RE.match(candidate) for candidate in names):
        return parse_pop_family
    if any(DEPARTURE_OUT_RE.match(candidate) for candidate in names):
        return parse_departure_out_family
    return None


@lru_cache(maxsize=64)
def _parse_cached(path_str: str, mtime_ns: int, size: int) -> dict[str, object] | None:
    path = Path(path_str)
    parser = _resolve_parser(path)
    if parser is None:
        return None
    if size > MAX_PARSE_FILE_BYTES:
        return {
            "parser": path.name.upper(),
            "title": f"{path.name} parsed view",
            "summary_table": {
                "title": "Parser",
                "columns": ["Field", "Value"],
                "rows": [["status", "skipped"], ["reason", f"file is larger than {MAX_PARSE_FILE_BYTES} bytes"]],
            },
            "tables": [],
            "plots": [],
            "warnings": [],
        }
    return parser(path)


def parse_known_file(path: Path) -> dict[str, object] | None:
    stat = path.stat()
    return _parse_cached(str(path), stat.st_mtime_ns, stat.st_size)
