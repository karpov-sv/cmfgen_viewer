"""Shared blueprint, constants, and request/URL helpers for viewer routes."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import math
from pathlib import Path
import re
from threading import Lock
from urllib.parse import urlencode

from flask import Blueprint, current_app, redirect, url_for

from .browser import is_model_context_path, resolve_path
from .final_spectrum import (
    LIGHT_SPEED_KM_PER_S,
    discover_final_spectrum_files,
    spectrum_fit_bounds,
)
from .parsers.common import format_number, parse_float_token
from .observed_spectrum import (
    is_valid_upload_token,
)

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    np = None  # type: ignore[assignment]

bp = Blueprint("viewer", __name__)
HR_AUX_DIR = Path(__file__).resolve().parent.parent / "data"
MAMAJEK_TABLE_PATH = HR_AUX_DIR / "EEM_dwarf_UBVIJHK_colors_Teff.txt"
QUICK_LINK_FILES = (
    "VADAT",
    "MODEL_SPEC",
    "IN_ITS",
    "MOD_SUM",
    "RVTJ",
    "OBSFLUX",
    "MEANOPAC",
    "HYDRO",
    "GAMMAS",
    "OUTGEN",
    "WARNINGS",
    "CORRECTION_SUM",
    "GAMFLUX",
    "GAMFLUX_NEW",
    "GAMRAY_E_DEP",
    "GAMRAY_E_DEP_MOD",
    "ENERGY_COMP",
    "SPECIES_MASSES",
    "GENCOOL",
)
QUICK_LINK_GLOBS = (
    "obs_fin*",
    "obs_cont*",
    "obs/obs_fin*",
    "obs/obs_cont*",
    "obs/hydro_fin*",
    "obs/hydro_cont*",
    "obs/meanopac_fin*",
    "obs/ewdata_fin*",
    "obs/full_timing*",
    "obs/cont_timing*",
)

SUMMARY_COLUMNS = [
    "MODEL",
    "LSTAR",
    "MDOT",
    "T_*",
    "RSTAR",
    "RMAX",
    "T_2/3",
    "R_2/3",
    "Eta",
    "f",
    "f_beg",
    "TAU",
    "Vinf",
    "Beta",
    "HYD/X",
    "NIT/X",
    "IRON/X",
    "logg",
    "OXY/X",
    "CAR/X",
    "Last updated",
]
SUMMARY_COLUMN_INDEX = {name: index for index, name in enumerate(SUMMARY_COLUMNS)}

SPECTRUM_TRANSFORM_DEFAULTS = {
    "redshift": 0.0,
    "broadening_km_s": 0.0,
    "ebv": 0.0,
    "distance_kpc": 1.0,
    "normalization": 1.0,
}

GRID_SEARCH_JOB_TTL_SECONDS = 6 * 60 * 60
GRID_SEARCH_MAX_JOBS = 32
GRID_SEARCH_TOP_RESULTS = 12
GRID_SEARCH_JOBS: dict[str, dict[str, object]] = {}
GRID_SEARCH_JOBS_LOCK = Lock()
GRID_FIT_SOURCE_CMFGEN = "cmfgen"
GRID_FIT_SOURCE_TLUSTY = "tlusty"
GRID_FIT_SOURCE_VALUES = {GRID_FIT_SOURCE_CMFGEN, GRID_FIT_SOURCE_TLUSTY}
TLUSTY_DEFAULT_ROOT = (Path(__file__).resolve().parent.parent / "data" / "tlusly").resolve()
TLUSTY_FIT_MAX_MODEL_POINTS = 20000
DEFAULT_SPECTRUM_LAMBDA_MAX_ANGSTROM = 250000.0
TLUSTY_CONFIDENCE_PARAM_SPECS = (
    {"key": "teff_k", "label": "Teff", "unit": "K", "integer": True},
    {"key": "log_g", "label": "log g", "unit": "", "integer": False},
    {"key": "z_over_zsun", "label": "Z/Zsun", "unit": "", "integer": False},
    {"key": "vturb_km_s", "label": "vturb", "unit": "km/s", "integer": True},
)
TLUSTY_CHI2_CONFIDENCE_LEVELS = (
    {"label": "68%", "delta_chi2": 1.0},
    {"label": "90%", "delta_chi2": 2.705543454095404},
    {"label": "95%", "delta_chi2": 3.841458820694124},
)
TLUSTY_CONFIDENCE_PHOTOMETRY_STRICT_REDUCED_CHI2_MAX = 2.0
TLUSTY_OSTAR_METALLICITY_MAP = {
    "C": 2.0,
    "G": 1.0,
    "L": 0.5,
    "S": 0.2,
    "T": 0.1,
    "V": 0.03,
    "W": 0.01,
    "X": 0.003,
    "Y": 0.001,
    "Z": 0.0001,
}
TLUSTY_BSTAR_METALLICITY_MAP = {
    "BC": 2.0,
    "BG": 1.0,
    "BL": 0.5,
    "BS": 0.2,
    "BT": 0.1,
    "BZ": 0.0,
}
TLUSTY_MODEL_NAME_RE = re.compile(
    r"^(?P<code>[A-Za-z]+)"
    r"(?P<teff>\d{4,5})"
    r"g(?P<logg>\d{3})"
    r"(?:v(?P<vturb>\d+))?"
    r"(?P<tag>[A-Za-z0-9_]*)$"
)
TLUSTY_MODEL_SUFFIXES = (
    ".flux",
    ".cont",
    ".continuum",
    ".hhe",
    ".uv",
    ".uvb",
    ".uvby",
    ".opt",
    ".optical",
    ".vis",
    ".spec",
    ".sp",
)


@lru_cache(maxsize=1)
def _load_mamajek_hr_overlay() -> dict[str, object] | None:
    """
    Load Mamajek dwarf sequence points as Teff-L pairs for HR overlay plotting.

    Source file is kept verbatim under data/ and parsed here on demand.
    """
    if not MAMAJEK_TABLE_PATH.is_file():
        return None

    try:
        lines = MAMAJEK_TABLE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    header_index: int | None = None
    teff_index: int | None = None
    logl_index: int | None = None
    version = ""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# Version"):
            version = stripped.replace("#", "", 1).strip()
        if not stripped.startswith("#SpT"):
            continue
        columns = stripped.lstrip("#").split()
        try:
            teff_index = columns.index("Teff")
            logl_index = columns.index("logL")
        except ValueError:
            continue
        header_index = idx
        break

    if header_index is None or teff_index is None or logl_index is None:
        return None

    points: list[dict[str, object]] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#SpT"):
            break
        if stripped.startswith("#"):
            continue

        parts = stripped.split()
        if len(parts) <= max(teff_index, logl_index):
            continue

        teff_value = parse_float_token(parts[teff_index])
        logl_value = parse_float_token(parts[logl_index])
        if teff_value is None or logl_value is None:
            continue

        teff = float(teff_value)
        log_l = float(logl_value)
        if not math.isfinite(teff) or not math.isfinite(log_l) or teff <= 0:
            continue

        luminosity = 10.0 ** log_l
        if not math.isfinite(luminosity) or luminosity <= 0:
            continue

        points.append(
            {
                "spt": parts[0],
                "teff": teff,
                "log_l": log_l,
                "luminosity": luminosity,
            }
        )

    if len(points) < 2:
        return None

    return {
        "name": "Mamajek Dwarf Sequence",
        "source": "https://www.pas.rochester.edu/~emamajek/EEM_dwarf_UBVIJHK_colors_Teff.txt",
        "version": version,
        "file": str(MAMAJEK_TABLE_PATH.name),
        "points": points,
    }


def _viewer_config() -> dict[str, object]:
    return dict(current_app.config.get("CMFGEN_VIEWER", {}))


def _spectrum_lambda_bounds(config: dict[str, object]) -> tuple[float, float]:
    default_min = 800.0
    default_max = DEFAULT_SPECTRUM_LAMBDA_MAX_ANGSTROM
    try:
        lambda_min = float(config.get("lambda_min_angstrom", default_min))
    except (TypeError, ValueError):
        lambda_min = default_min
    try:
        lambda_max = float(config.get("lambda_max_angstrom", default_max))
    except (TypeError, ValueError):
        lambda_max = default_max

    if not math.isfinite(lambda_min) or lambda_min <= 0:
        lambda_min = default_min
    if not math.isfinite(lambda_max) or lambda_max <= 0:
        lambda_max = default_max
    if lambda_min > lambda_max:
        lambda_min, lambda_max = lambda_max, lambda_min
    return lambda_min, lambda_max


def _upload_root(config: dict[str, object]) -> Path:
    root = str(config.get("upload_root", "/tmp/cmfgen_viewer_uploads"))
    return Path(root).expanduser().resolve()


def _normalize_spectrum_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "both").strip().lower()
    if mode not in {"both", "normalized"}:
        return "both"
    return mode


def _normalize_grid_fit_source(raw_source: object) -> str:
    source = str(raw_source or GRID_FIT_SOURCE_CMFGEN).strip().lower()
    if source not in GRID_FIT_SOURCE_VALUES:
        return GRID_FIT_SOURCE_CMFGEN
    return source


def _grid_fit_source_label(source: str) -> str:
    normalized = _normalize_grid_fit_source(source)
    if normalized == GRID_FIT_SOURCE_TLUSTY:
        return "TLUSTY Grid"
    return "Cached CMFGEN Models"


def _tlusty_root(config: dict[str, object]) -> Path:
    raw = str(config.get("tlusty_root", str(TLUSTY_DEFAULT_ROOT)))
    return Path(raw).expanduser().resolve()


def _collect_obs_tokens(raw_values: list[str]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw).split(","):
            token = part.strip()
            if not token or not is_valid_upload_token(token) or token in seen:
                continue
            tokens.append(token)
            seen.add(token)
    return tokens


def _collect_rel_paths(raw_values: list[str]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        rel = str(raw).strip().strip("/")
        if not rel or rel in seen:
            continue
        paths.append(rel)
        seen.add(rel)
    return paths


def _parse_summary_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        numeric = float(value)
        return numeric if numeric == numeric else None

    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("D", "E").replace("d", "e")
    parsed = parse_float_token(normalized)
    if parsed is not None:
        numeric = float(parsed)
        return numeric if numeric == numeric else None

    match = re.match(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))([+-]\d+)$", normalized)
    if not match:
        return None
    try:
        numeric = float(f"{match.group(1)}E{match.group(2)}")
    except ValueError:
        return None
    return numeric if numeric == numeric else None


def _format_summary_value(value: object, *, default: str = "") -> str:
    if value in (None, ""):
        return default
    numeric = _parse_summary_float(value)
    if numeric is not None:
        return format_number(numeric)
    text = str(value).strip()
    return text if text else default


def _format_summary_timestamp(timestamp: float | None) -> str:
    if timestamp is None or not math.isfinite(timestamp):
        return ""
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _build_summary_row(model: dict[str, object], *, mod_sum_mtime: float | None = None) -> list[str]:
    params = model.get("params")
    vadat = model.get("vadat")
    if not isinstance(params, dict):
        params = {}
    if not isinstance(vadat, dict):
        vadat = {}

    cl_p_1 = params.get("CL_P_1")
    if cl_p_1 in (None, ""):
        cl_p_1 = "-"

    return [
        _format_summary_value(model.get("name")),
        _format_summary_value(vadat.get("LSTAR")),
        _format_summary_value(vadat.get("MDOT")),
        _format_summary_value(params.get("T*(K)")),
        _format_summary_value(vadat.get("RSTAR")),
        _format_summary_value(vadat.get("RMAX")),
        _format_summary_value(params.get("Teff(K)")),
        _format_summary_value(params.get("R_/Rsun")),
        _format_summary_value(params.get("Eta")),
        _format_summary_value(cl_p_1, default="-"),
        _format_summary_value(params.get("CL_P_2")),
        _format_summary_value(params.get("Tau")),
        _format_summary_value(params.get("Vinf1")),
        _format_summary_value(params.get("Beta1")),
        _format_summary_value(vadat.get("HYD/X")),
        _format_summary_value(vadat.get("NIT/X")),
        _format_summary_value(vadat.get("IRON/X")),
        _format_summary_value(params.get("Log_g")),
        _format_summary_value(vadat.get("OXY/X")),
        _format_summary_value(vadat.get("CARB/X")),
        _format_summary_timestamp(mod_sum_mtime),
    ]


def _normalize_transform_params(params: dict[str, object] | None = None) -> dict[str, float]:
    redshift = SPECTRUM_TRANSFORM_DEFAULTS["redshift"]
    broadening = SPECTRUM_TRANSFORM_DEFAULTS["broadening_km_s"]
    ebv = SPECTRUM_TRANSFORM_DEFAULTS["ebv"]
    distance = SPECTRUM_TRANSFORM_DEFAULTS["distance_kpc"]
    normalization = SPECTRUM_TRANSFORM_DEFAULTS["normalization"]
    values = params or {}

    redshift_raw = _parse_summary_float(values.get("redshift"))
    if redshift_raw is None:
        redshift_raw = _parse_summary_float(values.get("z"))
    if redshift_raw is not None and math.isfinite(redshift_raw):
        redshift = max(redshift_raw, -0.999999)

    broadening_raw = _parse_summary_float(values.get("broadening_km_s"))
    if broadening_raw is None:
        broadening_raw = _parse_summary_float(values.get("broadening"))
    if broadening_raw is None:
        broadening_raw = _parse_summary_float(values.get("sigma"))
    if broadening_raw is not None and math.isfinite(broadening_raw):
        broadening = max(0.0, broadening_raw)

    ebv_raw = _parse_summary_float(values.get("ebv"))
    if ebv_raw is not None and math.isfinite(ebv_raw):
        ebv = ebv_raw

    distance_raw = _parse_summary_float(values.get("distance_kpc"))
    if distance_raw is None:
        distance_raw = _parse_summary_float(values.get("distance"))
    if distance_raw is not None and math.isfinite(distance_raw) and distance_raw > 0:
        distance = distance_raw

    normalization_raw = _parse_summary_float(values.get("normalization"))
    if normalization_raw is not None and math.isfinite(normalization_raw) and normalization_raw > 0:
        normalization = normalization_raw

    return {
        "redshift": redshift,
        "velocity_km_s": redshift * LIGHT_SPEED_KM_PER_S,
        "broadening_km_s": broadening,
        "ebv": ebv,
        "distance_kpc": distance,
        "normalization": normalization,
    }


def _normalize_fit_bounds(
    params: dict[str, object] | None = None,
    *,
    mode: str,
    fit_source: object | None = None,
) -> dict[str, tuple[float, float]]:
    defaults = spectrum_fit_bounds(mode)
    if mode == "both" and _normalize_grid_fit_source(fit_source) == GRID_FIT_SOURCE_TLUSTY:
        defaults.pop("distance_kpc", None)
    values = params or {}
    normalized: dict[str, tuple[float, float]] = {}
    for name, (default_min, default_max) in defaults.items():
        min_raw = _parse_summary_float(values.get(f"fit_{name}_min"))
        max_raw = _parse_summary_float(values.get(f"fit_{name}_max"))

        min_value = float(min_raw) if min_raw is not None and math.isfinite(min_raw) else float(default_min)
        max_value = float(max_raw) if max_raw is not None and math.isfinite(max_raw) else float(default_max)
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        if name == "broadening_km_s":
            min_value = max(0.0, min_value)
            max_value = max(min_value + 1e-9, max_value)
        elif name == "distance_kpc":
            min_value = max(1e-6, min_value)
            max_value = max(min_value + 1e-9, max_value)
        elif abs(max_value - min_value) < 1e-12:
            min_value = float(default_min)
            max_value = float(default_max)

        normalized[name] = (min_value, max_value)
    return normalized


def _normalize_fit_wavelength_range(
    params: dict[str, object] | None = None,
    *,
    configured_min: float,
    configured_max: float,
) -> tuple[tuple[float, float] | None, str | None]:
    values = params or {}
    min_text = str(values.get("fit_lambda_min", "")).strip()
    max_text = str(values.get("fit_lambda_max", "")).strip()

    min_value: float | None = None
    max_value: float | None = None

    if min_text:
        min_raw = _parse_summary_float(min_text)
        if min_raw is None or not math.isfinite(min_raw) or min_raw <= 0:
            return None, "Fit wavelength minimum must be a positive number."
        min_value = float(min_raw)

    if max_text:
        max_raw = _parse_summary_float(max_text)
        if max_raw is None or not math.isfinite(max_raw) or max_raw <= 0:
            return None, "Fit wavelength maximum must be a positive number."
        max_value = float(max_raw)

    if min_value is None and max_value is None:
        return None, None

    try:
        window_min = float(configured_min)
        window_max = float(configured_max)
    except (TypeError, ValueError):
        return None, "Configured wavelength window is invalid."
    if not math.isfinite(window_min) or not math.isfinite(window_max):
        return None, "Configured wavelength window is invalid."
    if window_min > window_max:
        window_min, window_max = window_max, window_min

    effective_min = min_value if min_value is not None else window_min
    effective_max = max_value if max_value is not None else window_max
    if effective_min > effective_max:
        effective_min, effective_max = effective_max, effective_min

    effective_min = max(window_min, effective_min)
    effective_max = min(window_max, effective_max)
    if effective_min >= effective_max:
        return (
            None,
            "Fit wavelength range does not overlap the configured window "
            f"{format_number(window_min)} .. {format_number(window_max)} Å.",
        )
    return (effective_min, effective_max), None


def _format_query_float(value: float, *, digits: int = 12) -> str:
    if not math.isfinite(value):
        return "0"
    return f"{value:.{digits}g}"


def _append_transform_query(query: list[tuple[str, str]], transform_params: dict[str, object] | None) -> None:
    if transform_params is None:
        return
    params = _normalize_transform_params(transform_params)
    default = _normalize_transform_params()
    if (
        abs(params["redshift"] - default["redshift"]) < 1e-18
        and abs(params["broadening_km_s"] - default["broadening_km_s"]) < 1e-18
        and abs(params["ebv"] - default["ebv"]) < 1e-18
        and abs(params["distance_kpc"] - default["distance_kpc"]) < 1e-18
    ):
        return
    query.append(("redshift", _format_query_float(params["redshift"])))
    query.append(("broadening_km_s", _format_query_float(params["broadening_km_s"])))
    query.append(("ebv", _format_query_float(params["ebv"])))
    query.append(("distance_kpc", _format_query_float(params["distance_kpc"])))


def _spectrum_url(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
    transform_params: dict[str, object] | None = None,
    fit_notice: str = "",
    fit_wavelength_inputs: dict[str, str] | None = None,
) -> str:
    base = url_for("viewer.spectrum", path=model_root)
    query: list[tuple[str, str]] = [("fin", fin), ("mode", _normalize_spectrum_mode(mode))]
    for token in obs_tokens or []:
        if is_valid_upload_token(token):
            query.append(("obs", token))
    _append_transform_query(query, transform_params)
    if isinstance(fit_wavelength_inputs, dict):
        fit_min = str(fit_wavelength_inputs.get("min", "")).strip()
        fit_max = str(fit_wavelength_inputs.get("max", "")).strip()
        if fit_min:
            query.append(("fit_lambda_min", fit_min))
        if fit_max:
            query.append(("fit_lambda_max", fit_max))
    if upload_error:
        query.append(("upload_error", upload_error))
    if fit_notice:
        query.append(("fit_notice", fit_notice))
    encoded = urlencode(query, doseq=True)
    return f"{base}?{encoded}" if encoded else base


def _spectrum_redirect(
    model_root: str,
    *,
    fin: str,
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
    transform_params: dict[str, object] | None = None,
    fit_notice: str = "",
    fit_wavelength_inputs: dict[str, str] | None = None,
):
    return redirect(
        _spectrum_url(
            model_root,
            fin=fin,
            mode=mode,
            obs_tokens=obs_tokens or [],
            upload_error=upload_error,
            transform_params=transform_params,
            fit_notice=fit_notice,
            fit_wavelength_inputs=fit_wavelength_inputs,
        )
    )


def _bulk_spectra_url(
    path: str,
    *,
    selected_models: list[str],
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
) -> str:
    base = url_for("viewer.bulk_spectra", path=path)
    query: list[tuple[str, str]] = [("mode", _normalize_spectrum_mode(mode))]
    for rel in selected_models:
        query.append(("selected_models", rel))
    for token in obs_tokens or []:
        if is_valid_upload_token(token):
            query.append(("obs", token))
    if upload_error:
        query.append(("upload_error", upload_error))
    encoded = urlencode(query, doseq=True)
    return f"{base}?{encoded}" if encoded else base


def _bulk_spectra_redirect(
    path: str,
    *,
    selected_models: list[str],
    mode: str,
    obs_tokens: list[str] | None = None,
    upload_error: str = "",
):
    return redirect(
        _bulk_spectra_url(
            path,
            selected_models=selected_models,
            mode=mode,
            obs_tokens=obs_tokens or [],
            upload_error=upload_error,
        )
    )


def _resolve_selected_model_dirs(
    basepath: str,
    directory: Path,
    selected_paths: list[str],
) -> tuple[list[tuple[str, Path]], list[list[str]]]:
    valid: list[tuple[str, Path]] = []
    skipped: list[list[str]] = []
    for rel in selected_paths:
        try:
            target = resolve_path(basepath, rel)
        except FileNotFoundError:
            skipped.append([rel, "Not found"])
            continue
        if not target.is_dir():
            skipped.append([rel, "Not a directory"])
            continue
        try:
            target.relative_to(directory)
        except ValueError:
            skipped.append([rel, "Outside current folder"])
            continue
        valid.append((rel, target))
    return valid, skipped


def _join_relpath(parent: str, child: str) -> str:
    if not parent:
        return child
    return f"{parent.rstrip('/')}/{child}"


def _collect_quick_links(basepath: str, directory_relpath: str) -> list[dict[str, str]]:
    try:
        directory = resolve_path(basepath, directory_relpath)
    except (FileNotFoundError, NotADirectoryError):
        return []
    if not directory.is_dir():
        return []

    links: list[dict[str, str]] = []
    seen_paths: set[str] = set()

    def add_link(path_obj: Path, *, label: str | None = None) -> None:
        rel = _join_relpath(directory_relpath, path_obj.relative_to(directory).as_posix())
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        links.append(
            {
                "name": label or path_obj.name,
                "path": rel,
            }
        )

    for name in QUICK_LINK_FILES:
        candidate = directory / name
        if candidate.is_file():
            add_link(candidate, label=name)

    for pattern in QUICK_LINK_GLOBS:
        for candidate in sorted(directory.glob(pattern), key=lambda p: p.name.lower()):
            if candidate.is_file():
                add_link(candidate)
    return links


def _model_root_relpath(relpath: str, basepath: str | None = None) -> str | None:
    parts = [part for part in Path(relpath).parts if part not in ("", ".")]
    for index, part in enumerate(parts):
        lowered = part.lower()
        if lowered.startswith("model") and lowered != "models":
            return "/".join(parts[: index + 1])
        if basepath is not None:
            candidate_relpath = "/".join(parts[: index + 1])
            try:
                candidate = resolve_path(basepath, candidate_relpath)
            except (FileNotFoundError, NotADirectoryError):
                continue
            if candidate.is_dir() and is_model_context_path(str(candidate)):
                return candidate_relpath
    return None


def _spectrum_link_context(basepath: str, relpath: str) -> dict[str, object] | None:
    model_root = _model_root_relpath(relpath, basepath)
    if not model_root:
        return None
    try:
        model_dir = resolve_path(basepath, model_root)
    except (FileNotFoundError, NotADirectoryError):
        return None
    files = discover_final_spectrum_files(model_dir)
    if files is None:
        return None
    return {
        "model_path": model_root,
        "fin_count": len(files["fin_files"]),
    }
