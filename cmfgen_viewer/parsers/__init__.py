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
    parse_hydro_params,
    parse_j_comp,
    parse_lte_diagnostic_est,
    parse_ml_counter,
    parse_meanopac,
    parse_obs_freq,
    parse_obsframe,
    parse_outlte,
    parse_out_flux,
    parse_out_params,
    parse_pop_family,
    parse_rate_file,
    parse_rosseland_lte_tab,
    parse_rvsig_col,
    parse_sob_force_mult,
    parse_time_pointer,
    parse_trans_info,
)
from .correction_sum import parse_correction_sum
from .mod_sum import parse_mod_sum
from .obsflux import parse_obsflux
from .rvtj import parse_rvtj
from .direct_access import parse_direct_access_file, parse_direct_info
from .extended_text import (
    parse_cmf_spectrum,
    parse_auto_check,
    parse_ewdata,
    parse_gencool,
    parse_keyword_control,
    parse_named_log,
    parse_named_numeric,
    parse_prrr,
    parse_species_masses,
    parse_steq_vals,
    parse_two_phot_sum,
    parse_vector_diagnostic,
)

PARSERS = {
    "RVTJ": parse_rvtj,
    "OBSFLUX": parse_obsflux,
    "MOD_SUM": parse_mod_sum,
    "CORRECTION_SUM": parse_correction_sum,
    "MEANOPAC": parse_meanopac,
    "HYDRO": parse_hydro,
    "HYDRO_PARAMS": parse_hydro_params,
    "RVSIG_COL": parse_rvsig_col,
    "OBSFRAME": parse_obsframe,
    "OUTLTE": parse_outlte,
    "OUT_FLUX": parse_out_flux,
    "GAMMAS": parse_gammas,
    "GAMMAS_IN": parse_gammas,
    "J_COMP": parse_j_comp,
    "NETRATE": parse_rate_file,
    "TOTRATE": parse_rate_file,
    "EWDATA": parse_ewdata,
    "LINEHEAT": parse_rate_file,
    "TRANS_INFO": parse_trans_info,
    "SOB_FORCE_MULT": parse_sob_force_mult,
    "GAMFLUX": parse_gamflux,
    "GAMRAY_ENERGY_DEP": parse_gamray_energy_dep,
    "OUT_PARAMS": parse_out_params,
    "CFDAT_OUT": parse_cfdat_out,
    "CONT_FREQ": parse_cont_freq,
    "OBS_FREQ": parse_obs_freq,
    "ROSSELAND_LTE_TAB": parse_rosseland_lte_tab,
    "DIAGNOSTIC_EST_1": parse_lte_diagnostic_est,
    "DIAGNOSTIC_EST_2": parse_lte_diagnostic_est,
    "ML_COUNTER": parse_ml_counter,
    "MODELS_FN_TIME": parse_time_pointer,
    "TIME_PNT1": parse_time_pointer,
    "TIME_PNT2": parse_time_pointer,
    "GAMRAY_PARAMS": parse_keyword_control,
    "SPECIES_MASSES": parse_species_masses,
    "GENCOOL": parse_gencool,
    "TWO_PHOT_SUM": parse_two_phot_sum,
    "ADIABAT_CHK": parse_named_numeric,
    "AUTO_CHK_C2": parse_auto_check,
    "ENERGY_COMP": parse_named_numeric,
    "NON_THERM_ION_SUM": parse_named_numeric,
    "NEW_SN_R_GRID": parse_named_numeric,
    "OLD_SN_R_GRID": parse_named_numeric,
    "NORM_FACTORS": parse_named_numeric,
    "ADJUST_CORRECTIONS": parse_named_numeric,
    "LCH2": parse_named_numeric,
    "RELCH": parse_named_numeric,
    "RELCH2": parse_named_numeric,
    "CHECK_DECAYS": parse_named_numeric,
    "CHECK_DECAYS_ENERGY_COMPARE": parse_named_numeric,
    "CHECK_EDEP": parse_named_numeric,
    "RAY_CHECK_FOR_GRAYS": parse_named_numeric,
    "GREY_SCL_FACOUT": parse_named_numeric,
    "NEG_OPAC": parse_named_numeric,
    "NEW_CALC_GRID": parse_named_numeric,
    "NON_THERM_COOL": parse_named_numeric,
    "CORRECTION_LINK": parse_named_log,
    "COLLISION_SUMMARY": parse_named_log,
    "HYDRO_ITERATION_INFO": parse_named_log,
    "HYDRO_OLD_MODEL": parse_named_log,
    "MOM_J_ERRORS": parse_named_log,
    "OUTGEN": parse_named_log,
    "TIMING": parse_named_log,
    "WARNINGS": parse_named_log,
    "SN_DATA_INPUT_CHK": parse_named_log,
    "SN_GREY_CHK": parse_named_log,
    "CHG_EXCH_CHK": parse_named_log,
    "CHG_EXCH_RD_CHK": parse_named_log,
    "DDT_WORK_CHK": parse_named_log,
    "MU_VALUE_CHK": parse_named_log,
    "STEQ_VALS": parse_steq_vals,
    "GAMMA_MODEL": parse_keyword_control,
    "WIND_HYD": parse_named_log,
    "JEW": parse_named_log,
    "KEVIN_TESTING": parse_named_log,
    "NON_THERM_SPEC_INFO": parse_named_log,
    "NUM_DECAYS_INFO": parse_vector_diagnostic,
    "NRAY_INFO": parse_named_numeric,
}
POP_FAMILY_RE = re.compile(r"^POP[A-Z0-9_]+$")
DEPARTURE_OUT_RE = re.compile(r"^[A-Z0-9]+OUT$")
OBS_ALIAS_RE = re.compile(r"^OBS_(?:FIN|CONT)(?:[._].*)?$")
RVSIG_ALIAS_RE = re.compile(r"^RVSIG_COL(?:_.+)?$")
HYDRO_ALIAS_RE = re.compile(r"^HYDRO_(?:FIN|CONT)(?:[._].*)?$")
MEANOPAC_ALIAS_RE = re.compile(r"^MEANOPAC(?:_FIN)?(?:[._].*)?$")
EWDATA_ALIAS_RE = re.compile(r"^EWDATA(?:_FIN|_XTGRID)(?:[._].*)?$")
GAMFLUX_ALIAS_RE = re.compile(r"^GAMFLUX_NEW(?:[._].*)?$")
GAMRAY_ALIAS_RE = re.compile(r"^GAMRAY_E_DEP(?:_MOD)?$")
TIMING_ALIAS_RE = re.compile(r"^(?:FULL|CONT)_TIMING(?:[._].*)?$")
CORRECTIONS_ALIAS_RE = re.compile(r"^CORRECTIONS\.\d+$")
PRRR_RE = re.compile(r"^[A-Z0-9]+PRRR$")
AUTO_CHECK_RE = re.compile(r"^AUTO_CHK_[A-Z0-9]+$")
CMF_SPECTRUM_RE = re.compile(r"^.+\.(?:C?UV|C?VIS|C?IR)$")
GAMMA_VERBOSE_RE = re.compile(r"^(?:ETA_ISO_\d+|ETA_MUAVG_\d+_\d+|GAMMA_J_\d+_\d+)\.DAT$")
DIRECT_ACCESS_RE = re.compile(
    r"^(?:EDDFACTOR|FLUX_FILE|CMF_FORCE_DATA|ETA_DATA|CHI_DATA|RAY_DATA|"
    r"SOB_FORCE_DATA|IP_DATA(?:_NEW)?|RTAU_DATA|ZTAU_DATA|DFR_DATA|"
    r"JH_AT_(?:CURRENT|OLD)_TIME|CUR_MODEL_DATA|OLD_MODEL_DATA|ES_J_CONV)$"
)
VECTOR_DIAGNOSTIC_NAMES = {"SN_HYDRO_FOR_NEXT_MODEL"}
GAMMA_VERBOSE_NAMES = {
    "DIAGN_EDEP",
    "E_SCAT_ARRAY",
    "ELECTRON_DENSITY.DAT",
    "GAM_MU_GRID",
    "GAMMA_NU_GRID.DAT",
    "GAMMA_RAY_LINES",
    "GAMMA_RAY_LINE_INFO",
    "GAMMA_RAY_LOCAL_EMISSION.DAT",
    "GAMMA_RAY_LUM.DAT",
    "GAMMA_RAY_LUM_J.DAT",
    "NU_END.DAT",
    "PHOTONS.DAT",
    "RAY1_INTENSITY.DAT",
    "SCATTERING_DIFF.DAT",
    "TAU_GAM_XRAY.DAT",
    "TAU_RAY.DAT",
    "VELOCITY_STEP.DAT",
}

MAX_PARSE_FILE_BYTES = 256 * 1024 * 1024


def _resolve_parser(path: Path):
    if path.suffix.lower() == ".sve" or path.name.endswith("~"):
        return None
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

    if any(RVSIG_ALIAS_RE.match(candidate) for candidate in names):
        return parse_rvsig_col
    if any(HYDRO_ALIAS_RE.match(candidate) for candidate in names):
        return parse_hydro
    if any(MEANOPAC_ALIAS_RE.match(candidate) for candidate in names):
        return parse_meanopac
    if any(EWDATA_ALIAS_RE.match(candidate) for candidate in names):
        return parse_ewdata
    if any(GAMFLUX_ALIAS_RE.match(candidate) for candidate in names):
        return parse_gamflux
    if any(GAMRAY_ALIAS_RE.match(candidate) for candidate in names):
        return parse_gamray_energy_dep
    if any(TIMING_ALIAS_RE.match(candidate) for candidate in names):
        return parse_named_log
    if any(CORRECTIONS_ALIAS_RE.match(candidate) for candidate in names):
        return parse_correction_sum
    if any(PRRR_RE.match(candidate) for candidate in names):
        return parse_prrr
    if any(AUTO_CHECK_RE.match(candidate) for candidate in names):
        return parse_auto_check
    if any(candidate in {"CMF.SED", "SP.DAT", "SPC.DAT"} or CMF_SPECTRUM_RE.match(candidate) for candidate in names):
        return parse_cmf_spectrum
    if any(GAMMA_VERBOSE_RE.match(candidate) or candidate in GAMMA_VERBOSE_NAMES for candidate in names):
        return parse_named_numeric
    if any(candidate in VECTOR_DIAGNOSTIC_NAMES for candidate in names):
        return parse_vector_diagnostic
    if DIRECT_ACCESS_RE.match(name):
        return parse_direct_access_file
    if name.endswith("_INFO") and DIRECT_ACCESS_RE.match(name[:-5]):
        return parse_direct_info

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
