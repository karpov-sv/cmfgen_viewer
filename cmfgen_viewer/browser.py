from __future__ import annotations

from datetime import datetime, timezone
import mimetypes
from pathlib import Path
import re

from .parsers import parse_known_file
from .syntax import highlight_text, syntax_css

CORE_FILES = {
    "RVTJ",
    "OBSFLUX",
    "OBSFRAME",
    "MOD_SUM",
    "MEANOPAC",
    "HYDRO",
    "GAMMAS",
}

OPTIONAL_FILES = {
    "NETRATE",
    "TOTRATE",
    "EWDATA",
    "LINEHEAT",
    "J_COMP",
    "NON_THERM_COOL",
    "GAMFLUX",
    "GAMRAY_ENERGY_DEP",
    "WARNINGS",
    "OUTGEN",
    "STEQ_VALS",
    "OUT_FLUX",
    "OUT_PARAMS",
    "CFDAT_OUT",
    "CONT_FREQ",
    "OBS_FREQ",
    "TRANS_INFO",
    "SOB_FORCE_MULT",
    "PLANCK_KAPPA_MEAN",
    "ION_LINE_FORCE_TABLE",
    "ION_FLUX_MEAN_OPAC",
    "PHOTOSPHERIC_RADIUS",
    "MOM_J_ERRORS",
    "FLUX_FILE",
    "CMF_FORCE_DATA",
    "ETA_DATA",
    "CHI_DATA",
    "RAY_DATA",
    "SOB_FORCE_DATA",
    "IP_DATA",
    "RTAU_DATA",
    "ZTAU_DATA",
    "DFR_DATA",
    "IP_FG_DATA",
    "NEG_OPAC",
    "NON_TH_RATES",
    "SN_HYDRO_FOR_NEXT_MODEL",
    "HYDRO_ITERATION_INFO",
    "HYDRO_OLD_MODEL",
    "NEW_CALC_GRID",
    "R_REGRIDDING_LOG",
    "NEW_R_GRID",
    "TIMING",
    "KEVIN_TESTING",
    "OUTLTE",
    "ROSSELAND_LTE_TAB",
    "ML_COUNTER",
    "DIAGNOSTIC_EST_1",
    "DIAGNOSTIC_EST_2",
    "OLD_GRID",
    "CORRECTION_SUM",
    "CORRECTION_LINK",
    "ADIABAT_CHK",
    "COLLISION_SUMMARY",
    "TWO_PHOT_SUM",
    "GENCOOL",
    "NORM_FACTORS",
    "ENERGY_COMP",
    "SPECIES_MASSES",
    "NON_THERM_ION_SUM",
    "GAMMA_MODEL",
    "GAMRAY_E_DEP",
    "GAMRAY_E_DEP_MOD",
    "GAMFLUX_NEW",
    "NEW_SN_R_GRID",
    "OLD_SN_R_GRID",
    "SN_DATA_INPUT_CHK",
    "SN_GREY_CHK",
    "CHG_EXCH_CHK",
    "CHG_EXCH_RD_CHK",
    "DDT_WORK_CHK",
    "MU_VALUE_CHK",
    "CHECK_DECAYS.DAT",
    "CHECK_DECAYS_ENERGY_COMPARE.DAT",
    "CHECK_EDEP.DAT",
    "RAY_CHECK_FOR_GRAYS.DAT",
    "ADJUST_CORRECTIONS",
    "LCH2.DAT",
    "RELCH.DAT",
    "RELCH2.DAT",
}

RESTART_INTERNAL_FILES = {
    "SCRTEMP",
    "POINT1",
    "POINT2",
    "NEW_POINT1",
    "NEW_POINT2",
    "NEW_SCRTEMP",
    "BAMAT",
    "BAMATPNT",
    "CUR_MODEL_DATA",
    "MODEL_SCR",
    "CHEK+CK_ON_BA_UPDATE",
    "IMPURITYJ",
    "EDDFACTOR",
    "EDDFACTOR_STORE",
    "ES_J_CONV",
    "JH_AT_CURRENT_TIME",
    "JEW",
    "MODELS_FN_TIME",
    "TIME_PNT1",
    "TIME_PNT2",
}

INPUT_CONTROL_FILES = {
    "MODEL",
    "MODEL_SPEC",
    "VADAT",
    "IN_ITS",
    "CMF_FLUX_PARAM",
    "FORB_LINE_CONTROL",
    "GAMRAY_PARAMS",
    "GAMMA_MODEL",
}

INPUT_RESTART_FILES = {
    "POINT1",
    "POINT2",
    "SCRTEMP",
    "OLD_J_FILE",
    "JH_AT_OLD_TIME",
    "OLD_MODEL_DATA",
}

INPUT_ATOMIC_CORE_FILES = {
    "HYD_L_DATA",
    "GBF_N_DATA",
    "XRAY_PHOT_FITS",
}

INPUT_ATOMIC_OPTIONAL_FILES = {
    "TWO_PHOT_DATA",
    "CHG_EXCH_DATA",
    "RS_XRAY_FLUXES",
    "FULL_STRK_LIST",
}

INPUT_INIT_MODEL_FILES = {
    "T_IN",
    "GAMMAS_IN",
    "FIN_CAL_GRID",
    "GREY_SCL_FAC_IN",
    "GREY_SCL_FAC",
    "GREY_SCL_FAC_SAVE",
}

INPUT_GRID_PROFILE_FILES = {
    "CFDAT",
    "CFDAT__IN",
    "GRID_PARAMS",
    "PROF_T_ED",
    "REVISED_LAMBDAS",
    "REVISE_P_PARAMS",
}

INPUT_VELOCITY_FILES = {
    "RDINR",
    "RVSIG_COL",
    "DEKOTER",
}

INPUT_SN_NONTHERM_FILES = {
    "SN_HYDRO_DATA",
    "NUC_DECAY_DATA",
    "INPUT_HYDRO.DAT",
    "ARNAUD_ROTHENFLUG.DAT",
    "NT_CROSEC_SCLFAC",
    "NT_ION_CROSEC_SCLFAC",
    "NON_THERM_DEGRADATION_SPEC",
    "INCIDENT_INTENSITY",
}

INPUT_HYDRO_ITERATION_FILES = {
    "HYDRO_DEFAULTS",
    "ADJUST_R_DEFAULTS",
    "IT_SPECIFIER",
    "SOL_ABUNDANCE",
    "HYDRO_PARAMS",
}

ION_OSC_PATTERN = re.compile(r"^[A-Z0-9]+_F_OSCDAT$")
ION_MAP_PATTERN = re.compile(r"^[A-Z0-9]+_F_TO_S$")
# A few archived LTE trees contain names clipped by one character.  They are
# still recognizable members of the same atomic-data families.
ION_OSC_TRUNCATED_PATTERN = re.compile(r"^[A-Z0-9]+_F_OSCDA$")
ION_MAP_TRUNCATED_PATTERN = re.compile(r"^[A-Z0-9]+_F_TO_$")
ION_PHOT_PATTERN = re.compile(r"^PHOT[A-Z0-9]+_[A-Z]+$")
ION_COL_PATTERN = re.compile(r"^[A-Z0-9]+_COL_DATA$")
ION_DIE_PATTERN = re.compile(r"^DIE[A-Z0-9]+$")
ION_AUTO_PATTERN = re.compile(r"^[A-Z0-9]+_AUTO_DATA$")
ION_INIT_PATTERN = re.compile(r"^[A-Z0-9]+_IN$")
ION_PRRR_PATTERN = re.compile(r"^[A-Z0-9]+PRRR$")
AUTO_CHECK_PATTERN = re.compile(r"^AUTO_CHK_[A-Z0-9]+$")
CMF_SPECTRUM_PATTERN = re.compile(r"^.+\.(?:C?UV|C?VIS|C?IR)$")
GAMMA_VERBOSE_PATTERN = re.compile(r"^(?:ETA_ISO_\d+|ETA_MUAVG_\d+_\d+|GAMMA_J_\d+_\d+)\.DAT$")
GAMMA_VERBOSE_FILES = {
    "DIAGN_EDEP",
    "E_SCAT_ARRAY",
    "ELECTRON_DENSITY.DAT",
    "GAM_MU_GRID",
    "GAMMA_NU_GRID.DAT",
    "GAMMA_RAY_LINES",
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
DIRECT_ACCESS_DATA_PATTERN = re.compile(
    r"^(?:EDDFACTOR|FLUX_FILE|CMF_FORCE_DATA|ETA_DATA|CHI_DATA|RAY_DATA|"
    r"SOB_FORCE_DATA|IP_DATA(?:_NEW)?|RTAU_DATA|ZTAU_DATA|DFR_DATA|"
    r"JH_AT_(?:CURRENT|OLD)_TIME|CUR_MODEL_DATA|OLD_MODEL_DATA|ES_J_CONV)$"
)

TEXT_EXTENSIONS = {
    ".txt",
    ".sh",
    ".log",
    ".dat",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".out",
}

MAX_TEXT_PREVIEW_BYTES = 512 * 1024

# MODEL_SPEC identifies the run configuration, while one of these files confirms
# that the directory is a concrete CMFGEN run rather than a generic input folder.
MODEL_PRIMARY_MARKERS = {"MODEL_SPEC"}
MODEL_SECONDARY_MARKERS = {"VADAT", "RVTJ", "MODEL", "IN_ITS"}


def resolve_path(basepath: str, relpath: str = "") -> Path:
    base = Path(basepath).expanduser().resolve()
    rel = Path(relpath)

    # Keep URL-supplied paths lexical and safe:
    # - reject absolute targets
    # - reject any path traversal segments
    # This still allows browsing symlink directories that are listed under base.
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise FileNotFoundError(relpath)

    clean_parts = [part for part in rel.parts if part not in ("", ".")]
    target = base.joinpath(*clean_parts)
    if not target.exists():
        raise FileNotFoundError(relpath)
    return target


def make_breadcrumb(path: str, base_name: str = "ROOT") -> list[dict[str, str | None]]:
    parts = [part for part in Path(path).parts if part not in ("", ".")]
    if not parts:
        return [{"name": base_name, "path": None}]

    breadcrumb: list[dict[str, str | None]] = [{"name": base_name, "path": ""}]
    cursor: list[str] = []
    for part in parts:
        cursor.append(part)
        breadcrumb.append({"name": part, "path": "/".join(cursor)})

    breadcrumb[-1]["path"] = None
    return breadcrumb


def _join_relpath(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent.rstrip('/')}/{child}"


def _is_in_model_dir(relpath: str) -> bool:
    parts = [part.lower() for part in Path(relpath).parts if part not in ("", ".")]
    if len(parts) <= 1:
        return False
    for part in parts[:-1]:
        if part.startswith("model") and part != "models":
            return True
    return False


def is_model_context_path(relpath: str) -> bool:
    """
    Return True when the path is in a concrete model folder.

    Keep supporting the conventional ``model*`` directory names, but also detect
    existing CMFGEN run directories from their characteristic files.  The latter
    supports run IDs such as ``CMF1770005901JULIKAS3`` and their subdirectories.
    """
    parts = [part.lower() for part in Path(relpath).parts if part not in ("", ".")]
    for part in parts:
        if part.startswith("model") and part != "models":
            return True

    path = Path(relpath).expanduser()
    if not path.exists():
        return False
    if path.is_file():
        path = path.parent

    for directory in (path, *path.parents):
        try:
            names = {entry.name.upper() for entry in directory.iterdir()}
        except (OSError, NotADirectoryError):
            continue
        if MODEL_PRIMARY_MARKERS <= names and MODEL_SECONDARY_MARKERS & names:
            return True
    return False


def classify_cmfgen_role(
    filename: str,
    relpath: str = "",
    *,
    model_context: bool = False,
) -> str:
    name = filename.upper()
    stem = Path(filename).stem.upper()
    suffix = Path(filename).suffix.lower()
    names = {name}
    if stem and stem != name:
        names.add(stem)

    if suffix == ".sh" and (model_context or _is_in_model_dir(relpath or filename)):
        return "script"
    if suffix == ".sve" or filename.endswith("~"):
        return "other"

    # Post-processed spectrum suffixes can have a stem such as ``MODEL`` that is
    # also a canonical control filename.  The compound filename is authoritative.
    if name in {"CMF.SED", "SP.DAT", "SPC.DAT"} or CMF_SPECTRUM_PATTERN.match(name):
        return "optional_diagnostic"

    if any(candidate.startswith("CMF_FLUX_PARAM") for candidate in names):
        return "input_control"
    if any(candidate in INPUT_CONTROL_FILES for candidate in names):
        return "input_control"
    if any(candidate in INPUT_RESTART_FILES for candidate in names):
        return "input_restart"
    if any(candidate in INPUT_ATOMIC_CORE_FILES for candidate in names):
        return "input_atomic_core"
    if any(candidate in INPUT_ATOMIC_OPTIONAL_FILES for candidate in names):
        return "input_atomic_optional"
    if any(candidate in INPUT_INIT_MODEL_FILES for candidate in names):
        return "input_init_model"
    if any(candidate in INPUT_GRID_PROFILE_FILES for candidate in names):
        return "input_grid_profile"
    if any(candidate in INPUT_VELOCITY_FILES for candidate in names):
        return "input_velocity"
    if any(candidate.startswith("RVSIG_COL") for candidate in names):
        return "input_velocity"
    if any(candidate in INPUT_SN_NONTHERM_FILES for candidate in names):
        return "input_sn_nonthermal"
    if any(candidate in INPUT_HYDRO_ITERATION_FILES for candidate in names):
        return "input_hydro_iteration"

    if any(candidate in CORE_FILES for candidate in names):
        return "core_viewer"
    if any(candidate in OPTIONAL_FILES for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("OBS_FIN") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("OBS_CONT") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("OBS_CMF") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("HYDRO_FIN") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("MEANOPAC") and candidate != "MEANOPAC" for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("FULL_TIMING") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("CONT_TIMING") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("J_COMP") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("HYDRO_CONT") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("EWDATA_FIN") or candidate.startswith("EWDATA_XTGRID") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("GAMFLUX_NEW") for candidate in names):
        return "optional_diagnostic"
    if any(candidate.startswith("GAMRAY_E_DEP") for candidate in names):
        return "optional_diagnostic"
    if any(re.match(r"^CORRECTIONS\.\d+$", candidate) for candidate in names):
        return "optional_diagnostic"
    if any(ION_PRRR_PATTERN.match(candidate) for candidate in names):
        return "optional_diagnostic"
    if any(AUTO_CHECK_PATTERN.match(candidate) for candidate in names):
        return "optional_diagnostic"
    if any(candidate in GAMMA_VERBOSE_FILES or GAMMA_VERBOSE_PATTERN.match(candidate) for candidate in names):
        return "optional_diagnostic"
    if any(DIRECT_ACCESS_DATA_PATTERN.match(candidate) for candidate in names):
        return "restart_internal"

    if any(ION_OSC_PATTERN.match(candidate) or ION_OSC_TRUNCATED_PATTERN.match(candidate) for candidate in names) or any(ION_MAP_PATTERN.match(candidate) or ION_MAP_TRUNCATED_PATTERN.match(candidate) for candidate in names) or any(ION_PHOT_PATTERN.match(candidate) for candidate in names) or any(ION_COL_PATTERN.match(candidate) for candidate in names):
        return "input_atomic_core"
    if any(ION_DIE_PATTERN.match(candidate) for candidate in names) or any(ION_AUTO_PATTERN.match(candidate) for candidate in names):
        return "input_atomic_optional"
    if any(ION_INIT_PATTERN.match(candidate) and candidate not in {"IN_ITS"} for candidate in names):
        return "input_init_model"

    if any(candidate.startswith("POP") or candidate.endswith("OUT") for candidate in names):
        return "optional_diagnostic"
    if any(candidate in RESTART_INTERNAL_FILES or candidate.endswith("_INFO") for candidate in names):
        return "restart_internal"
    return "other"


def _is_text_like_file(path: Path, mime: str | None, role: str) -> bool:
    if mime and mime.startswith("text/"):
        return True
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    if role in {"core_viewer", "optional_diagnostic"}:
        return True

    try:
        with path.open("rb") as handle:
            chunk = handle.read(4096)
    except OSError:
        return False

    if b"\x00" in chunk:
        return False

    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _classify_kind(path: Path, mime: str | None, role: str) -> str:
    if path.is_dir():
        return "dir"
    if mime and mime.startswith("image/"):
        return "image"
    if _is_text_like_file(path, mime, role):
        return "text"
    return "file"


def _human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            break
        value /= 1024.0
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def list_directory(
    basepath: str,
    relpath: str = "",
    show_all: bool = False,
    show_symlinks: bool = True,
) -> list[dict[str, object]]:
    directory = resolve_path(basepath, relpath)
    if not directory.is_dir():
        raise NotADirectoryError(str(directory))

    entries: list[dict[str, object]] = []
    model_context = is_model_context_path(str(directory))
    for entry in directory.iterdir():
        if entry.name.startswith(".") and not show_all:
            continue

        try:
            is_symlink = entry.is_symlink()
        except OSError:
            continue

        if is_symlink and not show_symlinks:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue

        try:
            stat = entry.stat()
            is_dir = entry.is_dir()
        except OSError:
            continue

        rel = _join_relpath(relpath, entry.name)
        mime = mimetypes.guess_type(entry.name)[0]
        role = classify_cmfgen_role(entry.name, relpath=rel, model_context=model_context)
        kind = _classify_kind(entry, mime, role)
        modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

        entries.append(
            {
                "name": entry.name,
                "path": rel,
                "is_dir": is_dir,
                "is_symlink": is_symlink,
                "kind": kind,
                "mime": mime or "application/octet-stream",
                "cmfgen_role": role,
                "size": stat.st_size,
                "human_size": _human_size(stat.st_size),
                "modified_iso": modified_at.isoformat(),
                "modified_display": modified_at.strftime("%Y-%m-%d %H:%M:%S"),
                "modified_ts": stat.st_mtime,
            }
        )

    entries.sort(key=lambda item: (not bool(item["is_dir"]), str(item["name"]).lower()))
    return entries


def _text_preview(path: Path, max_bytes: int = MAX_TEXT_PREVIEW_BYTES) -> tuple[str, bool]:
    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    truncated = len(payload) > max_bytes
    payload = payload[:max_bytes]
    return payload.decode("utf-8", errors="replace"), truncated


def describe_file(basepath: str, relpath: str) -> dict[str, object]:
    target = resolve_path(basepath, relpath)
    if not target.is_file():
        raise FileNotFoundError(relpath)

    stat = target.stat()
    mime = mimetypes.guess_type(target.name)[0]
    role = classify_cmfgen_role(
        target.name,
        relpath=relpath,
        model_context=is_model_context_path(str(target.parent)),
    )
    kind = _classify_kind(target, mime, role)
    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    context: dict[str, object] = {
        "name": target.name,
        "size": stat.st_size,
        "human_size": _human_size(stat.st_size),
        "modified_iso": modified_at.isoformat(),
        "modified_display": modified_at.strftime("%Y-%m-%d %H:%M:%S"),
        "modified_ts": stat.st_mtime,
        "mime": mime or "application/octet-stream",
        "cmfgen_role": role,
        "kind": kind,
        "mode": "download",
    }

    try:
        parsed = parse_known_file(target)
        if parsed is not None:
            context["parsed"] = parsed
    except Exception as exc:
        context["parse_error"] = str(exc)

    if kind == "text":
        contents, truncated = _text_preview(target)
        context["mode"] = "text"
        context["contents"] = contents
        context["truncated"] = truncated
        highlighted_html, lexer_name = highlight_text(
            contents,
            filename=target.name,
            mime=context["mime"],
            role=role,
        )
        context["highlighted_html"] = highlighted_html
        context["highlight_css"] = syntax_css()
        context["highlight_lexer"] = lexer_name
    elif kind == "image":
        context["mode"] = "image"

    return context
