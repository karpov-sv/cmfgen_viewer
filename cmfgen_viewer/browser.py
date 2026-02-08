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
}

RESTART_INTERNAL_FILES = {
    "SCRTEMP",
    "POINT1",
    "POINT2",
    "BAMAT",
    "BAMATPNT",
    "EDDFACTOR",
    "ES_J_CONV",
    "JH_AT_CURRENT_TIME",
    "JEW",
}

INPUT_CONTROL_FILES = {
    "MODEL",
    "MODEL_SPEC",
    "VADAT",
    "IN_ITS",
    "CMF_FLUX_PARAM",
    "FORB_LINE_CONTROL",
}

INPUT_RESTART_FILES = {
    "POINT1",
    "POINT2",
    "SCRTEMP",
    "OLD_J_FILE",
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
}

INPUT_GRID_PROFILE_FILES = {
    "CFDAT",
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
}

ION_OSC_PATTERN = re.compile(r"^[A-Z0-9]+_F_OSCDAT$")
ION_MAP_PATTERN = re.compile(r"^[A-Z0-9]+_F_TO_S$")
ION_PHOT_PATTERN = re.compile(r"^PHOT[A-Z0-9]+_[A-Z]+$")
ION_COL_PATTERN = re.compile(r"^[A-Z0-9]+_COL_DATA$")
ION_DIE_PATTERN = re.compile(r"^DIE[A-Z0-9]+$")
ION_AUTO_PATTERN = re.compile(r"^[A-Z0-9]+_AUTO_DATA$")
ION_INIT_PATTERN = re.compile(r"^[A-Z0-9]+_IN$")

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


def resolve_path(basepath: str, relpath: str = "") -> Path:
    base = Path(basepath).expanduser().resolve()
    target = (base / relpath).resolve()

    try:
        target.relative_to(base)
    except ValueError as exc:
        raise FileNotFoundError(relpath) from exc

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
    Return True when current directory path looks like a concrete model folder
    (e.g. .../model_Bstar1026[/...]), not a generic collection folder like "models".
    """
    parts = [part.lower() for part in Path(relpath).parts if part not in ("", ".")]
    for part in parts:
        if part.startswith("model") and part != "models":
            return True
    return False


def classify_cmfgen_role(filename: str, relpath: str = "") -> str:
    name = filename.upper()
    suffix = Path(filename).suffix.lower()

    if suffix == ".sh" and _is_in_model_dir(relpath or filename):
        return "script"

    if name in INPUT_CONTROL_FILES:
        return "input_control"
    if name in INPUT_RESTART_FILES:
        return "input_restart"
    if name in INPUT_ATOMIC_CORE_FILES:
        return "input_atomic_core"
    if name in INPUT_ATOMIC_OPTIONAL_FILES:
        return "input_atomic_optional"
    if name in INPUT_INIT_MODEL_FILES:
        return "input_init_model"
    if name in INPUT_GRID_PROFILE_FILES:
        return "input_grid_profile"
    if name in INPUT_VELOCITY_FILES:
        return "input_velocity"
    if name in INPUT_SN_NONTHERM_FILES:
        return "input_sn_nonthermal"
    if name in INPUT_HYDRO_ITERATION_FILES:
        return "input_hydro_iteration"

    if name in CORE_FILES:
        return "core_viewer"
    if name in OPTIONAL_FILES:
        return "optional_diagnostic"

    if ION_OSC_PATTERN.match(name) or ION_MAP_PATTERN.match(name) or ION_PHOT_PATTERN.match(name) or ION_COL_PATTERN.match(name):
        return "input_atomic_core"
    if ION_DIE_PATTERN.match(name) or ION_AUTO_PATTERN.match(name):
        return "input_atomic_optional"
    if ION_INIT_PATTERN.match(name) and name not in {"IN_ITS"}:
        return "input_init_model"

    if name.startswith("POP") or name.endswith("OUT"):
        return "optional_diagnostic"
    if name in RESTART_INTERNAL_FILES or name.endswith("_INFO"):
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
        role = classify_cmfgen_role(entry.name, relpath=rel)
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
    role = classify_cmfgen_role(target.name, relpath=relpath)
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
        try:
            parsed = parse_known_file(target)
            if parsed is not None:
                context["parsed"] = parsed
        except Exception as exc:
            context["parse_error"] = str(exc)
    elif kind == "image":
        context["mode"] = "image"

    return context
