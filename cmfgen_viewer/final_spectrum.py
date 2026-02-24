from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import math
from pathlib import Path
import re
from typing import Any, Callable

from .parsers.common import downsample_xy, format_number, parse_float_token, parse_numeric_tokens

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    np = None  # type: ignore[assignment]

try:
    from scipy.interpolate import CubicSpline
    from scipy.ndimage import gaussian_filter1d
    from scipy.optimize import least_squares
except ModuleNotFoundError:  # pragma: no cover - optional dependency for fitting
    CubicSpline = None  # type: ignore[assignment]
    gaussian_filter1d = None  # type: ignore[assignment]
    least_squares = None  # type: ignore[assignment]

VADAT_ENTRY_RE = re.compile(r"^\s*(\S+)\s+\[(\S*)\]")
COUNT_RE = re.compile(r"\((\s*\d+)\)")

# OBSFLUX/OBS_CONT frequencies are in units of 10^15 Hz.
LIGHT_SPEED_ANGSTROM_PER_10P15_HZ = 2997.92458
LIGHT_SPEED_CM_PER_S = 2.99792458e10
ANGSTROM_PER_CM = 1e8
JANSKY_TO_CGS_HZ = 1e-23
JY_TO_FLAMBDA_ANGSTROM_FACTOR = JANSKY_TO_CGS_HZ * LIGHT_SPEED_CM_PER_S * ANGSTROM_PER_CM
LIGHT_SPEED_KM_PER_S = 299792.458

MAX_MODEL_TIME_LINES = 4
MAX_SPECIES_ROWS = 12
MAX_SERIES_POINTS = 5000
PHOTOMETRY_ERROR_BAR_COLOR = "rgba(33, 37, 41, 0.45)"
PHOTOMETRY_ERROR_BAR_THICKNESS = 1.2
PHOTOMETRY_ERROR_BAR_CAP_WIDTH = 0

ABSOLUTE_FIT_BOUNDS = {
    "redshift": (-0.02, 0.02),
    "broadening_km_s": (0.0, 800.0),
    "ebv": (0.0, 3.0),
    "distance_kpc": (0.05, 50.0),
}
NORMALIZED_FIT_BOUNDS = {
    "redshift": (-0.02, 0.02),
    "broadening_km_s": (0.0, 800.0),
}

FIT_CANCELED_MESSAGE = "Fit canceled."


class _FitCanceledError(Exception):
    pass


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

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.lstrip().startswith("!"):
                continue
            match = VADAT_ENTRY_RE.match(line)
            if not match:
                continue
            values[match.group(2)] = match.group(1)
    return values


def _parse_mod_sum(path: Path, do_cl_flag: str = "F") -> dict[str, object]:
    model: dict[str, object] = {"params": {}, "ions": [], "species": {}, "time": "", "maxcorr": ""}
    if not path.is_file():
        return model

    params = model["params"]
    ions = model["ions"]
    species = model["species"]
    if not isinstance(params, dict) or not isinstance(ions, list) or not isinstance(species, dict):
        return model

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    state = 0
    just_skipped = False
    do_cl = str(do_cl_flag).upper()
    for line in lines:
        tokens = line.split()
        if not tokens:
            if not just_skipped:
                state += 1
            just_skipped = True
            continue
        just_skipped = False

        if state == 1:
            model["time"] = f"{model.get('time', '')}{line}"
            continue

        if state == 2:
            for token in tokens:
                if "[" not in token or not token.endswith("]"):
                    continue
                left, right = token.split("[", 1)
                value = right[:-1]
                try:
                    model[left] = int(value)
                except ValueError:
                    continue
            continue

        if state == 3:
            for token in tokens:
                if "[" not in token:
                    continue
                ions.append(token.split("[", 1)[0])
            continue

        if state in (4, 5):
            normalized_line = line.replace("R ", "R_").replace("Log g", "Log_g")
            for token in normalized_line.split():
                if "=" not in token:
                    continue
                key, raw = token.split("=", 1)
                params[key] = _parse_float_legacy(raw)
            continue

        if state == 7:
            if tokens[0] == "SPECIES" or len(tokens) < 5:
                continue
            species[tokens[0]] = {
                "rel_frac": _parse_float_legacy(tokens[1]),
                "mass_frac": _parse_float_legacy(tokens[2]),
                "z_z_sun": _parse_float_legacy(tokens[3]),
                "z_sun": _parse_float_legacy(tokens[4]),
            }
            continue

        if state == 8 and do_cl == "T":
            for token in tokens:
                if "=" not in token:
                    continue
                key, raw = token.split("=", 1)
                params[key] = _parse_float_legacy(raw)
            continue

        if state == 9 or (state == 8 and do_cl != "T"):
            if ":" in line:
                model["maxcorr"] = _parse_float_legacy(line.split(":", 1)[1])

    return model


@lru_cache(maxsize=64)
def _read_model_cached(path_str: str, vadat_mtime: int, vadat_size: int, mod_sum_mtime: int, mod_sum_size: int) -> dict[str, object]:
    del vadat_mtime, vadat_size, mod_sum_mtime, mod_sum_size
    model_dir = Path(path_str)
    model: dict[str, object] = {"params": {}, "ions": [], "species": {}, "vadat": {}}
    model["path"] = str(model_dir)
    model["name"] = model_dir.name
    vadat = _parse_vadat(model_dir / "VADAT")
    model["vadat"] = vadat

    mod_sum = _parse_mod_sum(model_dir / "MOD_SUM", do_cl_flag=str(vadat.get("DO_CL", "F")))
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
    time_lines = [line.strip() for line in time_raw.splitlines() if line.strip()][:MAX_MODEL_TIME_LINES]
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
    parameter_rows = [(label, _as_text(value)) for label, value in key_param_rows if value not in (None, "")]

    composition_rows: list[tuple[str, str]] = []
    hyd = species.get("HYD")
    if isinstance(hyd, dict) and "mass_frac" in hyd:
        composition_rows.append(("Hydrogen mass fraction", _as_text(hyd.get("mass_frac", ""))))
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
        {"title": "Species Table", "rows": species_rows, "columns": ["Species", "Rel. # Fraction", "Mass Fraction"]},
    ]


def discover_final_spectrum_files(model_dir: Path) -> dict[str, object] | None:
    obs_dir = model_dir / "obs"
    if not obs_dir.is_dir():
        return None
    obs_cont = obs_dir / "obs_cont"
    if not obs_cont.is_file():
        return None
    fin_files = [path for path in obs_dir.glob("obs_fin*") if path.is_file()]

    def sort_key(item: Path) -> tuple[int, int, str]:
        match = re.match(r"^obs_fin[_-]?(\d+)", item.name, re.IGNORECASE)
        if match:
            return (0, int(match.group(1)), item.name.lower())
        return (1, 0, item.name.lower())

    fin_files.sort(key=sort_key)
    if not fin_files:
        return None
    return {
        "obs_dir": obs_dir,
        "obs_cont": obs_cont,
        "fin_files": fin_files,
    }


def _series_heading(line: str) -> tuple[str | None, int | None]:
    text = " ".join(line.strip().split())
    if text.startswith("Continuum Frequencies"):
        match = COUNT_RE.search(text)
        return "continuum_frequencies", int(match.group(1)) if match else None
    if text.startswith("Observed intensity (Janskys)"):
        return "observed_intensity_janskys", None
    return None, None


def _trim_short_wavelength_floor(wavelengths: list[float], flux: list[float]) -> tuple[list[float], list[float], int]:
    if len(wavelengths) < 3 or len(flux) < 3 or len(wavelengths) != len(flux):
        return wavelengths, flux, 0

    # Match the OBSFLUX view trimming rule: treat the intensity at the
    # longest wavelength as the run-specific floor and trim only the leading
    # short-wavelength segment that stays at or below that floor.
    longest_wavelength_floor = flux[-1]
    if not math.isfinite(longest_wavelength_floor):
        return wavelengths, flux, 0

    first_keep_index = 0
    max_trim = len(flux) - 2
    while first_keep_index < max_trim and flux[first_keep_index] <= longest_wavelength_floor:
        first_keep_index += 1

    if first_keep_index <= 0:
        return wavelengths, flux, 0
    return wavelengths[first_keep_index:], flux[first_keep_index:], first_keep_index


def _normalize_wavelength_bounds(
    lambda_min: float | None,
    lambda_max: float | None,
) -> tuple[float | None, float | None]:
    min_value = float(lambda_min) if isinstance(lambda_min, int | float) else None
    max_value = float(lambda_max) if isinstance(lambda_max, int | float) else None
    if min_value is not None and (not math.isfinite(min_value) or min_value <= 0):
        min_value = None
    if max_value is not None and (not math.isfinite(max_value) or max_value <= 0):
        max_value = None
    if min_value is not None and max_value is not None and min_value > max_value:
        min_value, max_value = max_value, min_value
    return min_value, max_value


@lru_cache(maxsize=16)
def _load_obs_spectrum_cached(
    path_str: str,
    mtime_ns: int,
    size: int,
    lambda_min: float | None,
    lambda_max: float | None,
) -> dict[str, object]:
    del mtime_ns, size
    path = Path(path_str)
    vectors: dict[str, list[float]] = {
        "continuum_frequencies": [],
        "observed_intensity_janskys": [],
    }
    expected_count: int | None = None
    active_key: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue

            heading_key, count = _series_heading(stripped)
            if heading_key:
                active_key = heading_key
                if heading_key == "continuum_frequencies" and count is not None:
                    expected_count = count
                continue

            values = parse_numeric_tokens(stripped)
            if active_key and values:
                vectors[active_key].extend(values)
                continue
            active_key = None

    freq = vectors["continuum_frequencies"]
    intensity = vectors["observed_intensity_janskys"]
    size = min(len(freq), len(intensity))
    wavelengths: list[float] = []
    flux: list[float] = []
    skipped = 0
    for frequency, value in zip(freq[:size], intensity[:size]):
        if frequency <= 0 or not math.isfinite(frequency) or not math.isfinite(value):
            skipped += 1
            continue
        wavelengths.append(LIGHT_SPEED_ANGSTROM_PER_10P15_HZ / frequency)
        flux.append(value)

    if len(wavelengths) >= 2 and wavelengths[0] > wavelengths[-1]:
        paired = sorted(zip(wavelengths, flux), key=lambda item: item[0])
        wavelengths = [item[0] for item in paired]
        flux = [item[1] for item in paired]

    range_skipped = 0
    if lambda_min is not None or lambda_max is not None:
        filtered_wavelengths: list[float] = []
        filtered_flux: list[float] = []
        for wavelength, intensity in zip(wavelengths, flux):
            if lambda_min is not None and wavelength < lambda_min:
                continue
            if lambda_max is not None and wavelength > lambda_max:
                continue
            filtered_wavelengths.append(wavelength)
            filtered_flux.append(intensity)
        range_skipped = len(wavelengths) - len(filtered_wavelengths)
        wavelengths = filtered_wavelengths
        flux = filtered_flux

    wavelengths, flux, trimmed_points = _trim_short_wavelength_floor(wavelengths, flux)

    return {
        "name": path.name,
        "wavelength": wavelengths,
        "flux": flux,
        "lambda_min": lambda_min,
        "lambda_max": lambda_max,
        "expected_count": expected_count,
        "raw_points": size,
        "skipped_points": skipped,
        "range_skipped_points": range_skipped,
        "trimmed_points": trimmed_points,
    }


def load_obs_spectrum(
    path: Path,
    *,
    lambda_min: float | None = None,
    lambda_max: float | None = None,
) -> dict[str, object]:
    bound_min, bound_max = _normalize_wavelength_bounds(lambda_min, lambda_max)
    mtime_ns, size = _safe_stat(path)
    return _load_obs_spectrum_cached(str(path.resolve()), mtime_ns, size, bound_min, bound_max)


def _interp_linear(x_src: list[float], y_src: list[float], x: float) -> float | None:
    if len(x_src) < 2:
        return None
    if x < x_src[0] or x > x_src[-1]:
        return None

    right = bisect_right(x_src, x)
    if right <= 0:
        return None
    if right >= len(x_src):
        return y_src[-1]

    left = right - 1
    x0 = x_src[left]
    x1 = x_src[right]
    y0 = y_src[left]
    y1 = y_src[right]
    if x1 == x0:
        return y0
    weight = (x - x0) / (x1 - x0)
    return y0 + (y1 - y0) * weight


def _plot_layout(*, y_label: str, y_scale: str) -> dict[str, object]:
    return {
        "template": "plotly_white",
        "margin": {"l": 62, "r": 24, "t": 14, "b": 52},
        "height": 420,
        "xaxis": {
            "title": {"text": "Wavelength (Å)"},
            "showgrid": True,
            "zeroline": False,
            "type": "log",
        },
        "yaxis": {
            "title": {"text": y_label},
            "showgrid": True,
            "zeroline": False,
            "type": y_scale,
            "exponentformat": "e",
            "showexponent": "all",
            "minexponent": 0,
        },
        "showlegend": True,
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        "hovermode": "closest",
    }


def _plot_config() -> dict[str, object]:
    return {
        "responsive": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }


def _jy_to_cgs_per_angstrom(wavelength: list[float], flux_jy: list[float]) -> tuple[list[float], list[float]]:
    converted_x: list[float] = []
    converted_y: list[float] = []
    for wavelength_angstrom, flux_value_jy in zip(wavelength, flux_jy):
        if wavelength_angstrom <= 0 or not math.isfinite(wavelength_angstrom) or not math.isfinite(flux_value_jy):
            continue
        flux_cgs = flux_value_jy * JY_TO_FLAMBDA_ANGSTROM_FACTOR / (wavelength_angstrom * wavelength_angstrom)
        if not math.isfinite(flux_cgs):
            continue
        converted_x.append(wavelength_angstrom)
        converted_y.append(flux_cgs)
    return converted_x, converted_y


def spectrum_fit_bounds(mode: str) -> dict[str, tuple[float, float]]:
    if mode == "both":
        return dict(ABSOLUTE_FIT_BOUNDS)
    return dict(NORMALIZED_FIT_BOUNDS)


def _resolve_fit_bounds(
    mode: str,
    bounds_override: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    bounds = spectrum_fit_bounds(mode)
    if not bounds_override:
        return bounds

    resolved = dict(bounds)
    for name, value in bounds_override.items():
        if name not in resolved:
            continue
        if not isinstance(value, tuple) or len(value) != 2:
            continue
        lo_raw, hi_raw = value
        if not isinstance(lo_raw, int | float) or not isinstance(hi_raw, int | float):
            continue
        lo = float(lo_raw)
        hi = float(hi_raw)
        if not math.isfinite(lo) or not math.isfinite(hi):
            continue
        if lo > hi:
            lo, hi = hi, lo
        if abs(hi - lo) < 1e-12:
            continue
        resolved[name] = (lo, hi)
    return resolved


def _clean_xy_arrays(x_values: list[float], y_values: list[float]) -> tuple[Any, Any] | None:
    if np is None:
        return None
    if len(x_values) < 2 or len(y_values) < 2:
        return None

    x = np.asarray(x_values, dtype=np.float64).reshape(-1)
    y = np.asarray(y_values, dtype=np.float64).reshape(-1)
    if x.size != y.size or x.size < 2:
        return None

    mask = np.isfinite(x) & np.isfinite(y) & (x > 0)
    x = x[mask]
    y = y[mask]
    if x.size < 2:
        return None

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    # np.interp requires monotonic increasing x; collapse duplicate wavelengths.
    keep = np.ones(x.shape[0], dtype=bool)
    keep[1:] = x[1:] > x[:-1]
    x = x[keep]
    y = y[keep]
    if x.size < 2:
        return None
    return x, y


def _clean_xy_with_band_width(
    x_values: list[float],
    y_values: list[float],
    band_width_values: list[float] | None,
) -> tuple[Any, Any, Any | None] | None:
    if np is None:
        return None
    if not isinstance(band_width_values, list):
        cleaned = _clean_xy_arrays(x_values, y_values)
        if cleaned is None:
            return None
        x, y = cleaned
        return x, y, None
    if len(x_values) < 2 or len(y_values) < 2 or len(band_width_values) < 2:
        return None

    x = np.asarray(x_values, dtype=np.float64).reshape(-1)
    y = np.asarray(y_values, dtype=np.float64).reshape(-1)
    width = np.asarray(band_width_values, dtype=np.float64).reshape(-1)
    if x.size != y.size or x.size != width.size or x.size < 2:
        return None

    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(width) & (x > 0) & (width >= 0)
    x = x[mask]
    y = y[mask]
    width = width[mask]
    if x.size < 2:
        return None

    order = np.argsort(x)
    x = x[order]
    y = y[order]
    width = width[order]

    # Keep only strictly increasing wavelengths to match interpolation assumptions.
    keep = np.ones(x.shape[0], dtype=bool)
    keep[1:] = x[1:] > x[:-1]
    x = x[keep]
    y = y[keep]
    width = width[keep]
    if x.size < 2:
        return None
    return x, y, width


def _build_model_series_for_fit(
    continuum: dict[str, object],
    final: dict[str, object],
    *,
    mode: str,
) -> tuple[Any, Any] | None:
    if np is None:
        return None

    cont_x = continuum.get("wavelength")
    cont_y = continuum.get("flux")
    fin_x = final.get("wavelength")
    fin_y = final.get("flux")
    if not isinstance(cont_x, list) or not isinstance(cont_y, list) or not isinstance(fin_x, list) or not isinstance(fin_y, list):
        return None

    cleaned_fin = _clean_xy_arrays(fin_x, fin_y)
    cleaned_cont = _clean_xy_arrays(cont_x, cont_y)
    if cleaned_fin is None or cleaned_cont is None:
        return None
    fin_x_np, fin_y_np = cleaned_fin
    cont_x_np, cont_y_np = cleaned_cont

    if mode == "both":
        converted_x, converted_y = _jy_to_cgs_per_angstrom(fin_x_np.tolist(), fin_y_np.tolist())
        return _clean_xy_arrays(converted_x, converted_y)

    cont_interp = np.interp(fin_x_np, cont_x_np, cont_y_np, left=np.nan, right=np.nan)
    valid = np.isfinite(cont_interp) & np.isfinite(fin_y_np) & (cont_interp != 0)
    if not np.any(valid):
        return None
    ratio_x = fin_x_np[valid]
    ratio_y = fin_y_np[valid] / cont_interp[valid]
    cleaned_ratio = _clean_xy_arrays(ratio_x.tolist(), ratio_y.tolist())
    if cleaned_ratio is None:
        return None
    return cleaned_ratio


def _build_observed_series_for_fit(
    observed: dict[str, object],
    *,
    mode: str,
) -> tuple[tuple[Any, Any, Any | None] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = observed.get("band_width") if observation_type == "photometry" else None
    flux_mode = str(observed.get("flux_mode", "")).strip().lower()
    if not isinstance(wavelength, list) or not isinstance(flux, list):
        return None, "Observed upload is missing wavelength/flux vectors."

    if mode == "both" and flux_mode != "absolute":
        return None, "Observed upload is not absolute-flux data."
    if mode == "normalized" and flux_mode != "normalized":
        return None, "Observed upload is not continuum-normalized data."

    cleaned = _clean_xy_with_band_width(
        wavelength,
        flux,
        band_width if isinstance(band_width, list) else None,
    )
    if cleaned is None:
        return None, "Observed upload has too few valid points."
    return cleaned, None


@lru_cache(maxsize=4)
def _fm_curve_spline(r_v: float) -> Any | None:
    if np is None or CubicSpline is None:
        return None

    xspluv = np.array([10000 / 2700, 10000 / 2600], dtype=np.float64)
    x0 = 4.596
    gamma = 0.99
    c4 = 0.41
    c3 = 3.23
    c2 = -0.824 + 4.717 / r_v
    c1 = 2.030 - 3.007 * c2

    def uv_curve(x: Any) -> Any:
        xx = x * x
        drude_den = (xx - x0 * x0) * (xx - x0 * x0) + (x * gamma) * (x * gamma)
        y = c1 + c2 * x + c3 * xx / drude_den
        delta = np.maximum(0.0, x - 5.9)
        y += c4 * (0.5392 * delta * delta + 0.05644 * delta * delta * delta)
        return y + r_v

    yspluv = uv_curve(xspluv)
    xsplopir = np.array([0, 10000 / 26500, 10000 / 12200, 10000 / 6000, 10000 / 5470, 10000 / 4670, 10000 / 4110])
    ysplir = np.array([0, 0.26469, 0.82925], dtype=np.float64) * (r_v / 3.1)
    ysplop = np.array(
        [
            np.polyval([2.13572e-4, 1.00270, -4.22809e-1], r_v),
            np.polyval([-7.35778e-5, 1.00216, -5.13540e-2], r_v),
            np.polyval([-3.32598e-5, 1.00184, 7.00127e-1], r_v),
            np.polyval([-4.45636e-5, 7.97809e-4, -5.46959e-3, 1.01707, 1.19456], r_v),
        ],
        dtype=np.float64,
    )
    xs_spline = np.concatenate([xsplopir, xspluv])
    ys_spline = np.concatenate([ysplir, ysplop, yspluv])
    return CubicSpline(xs_spline, ys_spline, bc_type="natural")


def _reddening_scale(wavelength_angstrom: Any, ebv: float, *, r_v: float = 3.1) -> Any:
    if np is None:
        return None
    if not math.isfinite(ebv) or ebv == 0:
        return np.ones_like(wavelength_angstrom, dtype=np.float64)

    wavelength = np.asarray(wavelength_angstrom, dtype=np.float64)
    out = np.ones_like(wavelength, dtype=np.float64)
    valid = np.isfinite(wavelength) & (wavelength > 0)
    if not np.any(valid):
        return out

    x = 10000.0 / wavelength[valid]
    xcutuv = 10000 / 2700
    x0 = 4.596
    gamma = 0.99
    c4 = 0.41
    c3 = 3.23
    c2 = -0.824 + 4.717 / r_v
    c1 = 2.030 - 3.007 * c2

    xx = x * x
    drude_den = (xx - x0 * x0) * (xx - x0 * x0) + (x * gamma) * (x * gamma)
    uv = c1 + c2 * x + c3 * xx / drude_den
    delta = np.maximum(0.0, x - 5.9)
    uv += c4 * (0.5392 * delta * delta + 0.05644 * delta * delta * delta)
    uv += r_v

    curve = np.empty_like(x)
    uv_mask = x >= xcutuv
    if np.any(uv_mask):
        curve[uv_mask] = uv[uv_mask]

    if np.any(~uv_mask):
        spline = _fm_curve_spline(r_v)
        if spline is None:
            curve[~uv_mask] = uv[~uv_mask]
        else:
            curve[~uv_mask] = spline(x[~uv_mask])

    factor = np.power(10.0, -0.4 * ebv * curve)
    factor[~np.isfinite(factor)] = 1.0
    factor[factor <= 0] = 1.0
    out[valid] = factor
    return out


def _gaussian_broaden_ascending(wavelength: Any, flux: Any, sigma_km_s: float) -> Any:
    if np is None:
        return flux
    if gaussian_filter1d is None or sigma_km_s <= 0:
        return flux.copy()
    if wavelength.size < 3 or flux.size != wavelength.size:
        return flux.copy()

    first = float(wavelength[0])
    last = float(wavelength[-1])
    if not math.isfinite(first) or not math.isfinite(last) or first <= 0 or last <= first:
        return flux.copy()

    log_min = math.log(first)
    log_max = math.log(last)
    d_log = (log_max - log_min) / float(wavelength.size - 1)
    if not math.isfinite(d_log) or d_log <= 0:
        return flux.copy()

    sigma_log = sigma_km_s / LIGHT_SPEED_KM_PER_S
    sigma_pixels = sigma_log / d_log
    if not math.isfinite(sigma_pixels) or sigma_pixels < 0.15:
        return flux.copy()

    log_grid = np.linspace(log_min, log_max, wavelength.size, dtype=np.float64)
    sample_x = np.exp(log_grid)
    sampled = np.interp(sample_x, wavelength, flux)
    smoothed = gaussian_filter1d(sampled, sigma=sigma_pixels, mode="nearest", truncate=4.0)
    position = (np.log(wavelength) - log_min) / d_log
    return np.interp(position, np.arange(wavelength.size, dtype=np.float64), smoothed)


def _gaussian_broaden_by_velocity(wavelength: Any, flux: Any, sigma_km_s: float) -> Any:
    if np is None:
        return flux
    if sigma_km_s <= 0 or wavelength.size < 3:
        return flux.copy()
    if wavelength[0] <= wavelength[-1]:
        return _gaussian_broaden_ascending(wavelength, flux, sigma_km_s)
    return _gaussian_broaden_ascending(wavelength[::-1], flux[::-1], sigma_km_s)[::-1]


def apply_spectrum_transform(
    wavelength: list[float],
    flux: list[float],
    *,
    mode: str,
    redshift: float,
    broadening_km_s: float,
    ebv: float,
    distance_kpc: float,
) -> tuple[list[float], list[float]] | None:
    """
    Mirror browser-side transforms used in the final-spectrum view:
    redshift -> distance/reddening (absolute mode only) -> Gaussian broadening.
    """
    cleaned = _clean_xy_arrays(wavelength, flux)
    if cleaned is None:
        return None
    x, y = cleaned
    transformed = _apply_transform_arrays(
        x,
        y,
        mode=mode,
        redshift=redshift,
        broadening_km_s=broadening_km_s,
        ebv=ebv,
        distance_kpc=distance_kpc,
    )
    if transformed is None:
        return None
    transformed_x, transformed_y = transformed
    return transformed_x.tolist(), transformed_y.tolist()


def _apply_transform_arrays(
    wavelength: Any,
    flux: Any,
    *,
    mode: str,
    redshift: float,
    broadening_km_s: float,
    ebv: float,
    distance_kpc: float,
) -> tuple[Any, Any] | None:
    if np is None:
        return None
    if not math.isfinite(redshift) or (1.0 + redshift) <= 0:
        return None
    if not math.isfinite(broadening_km_s) or broadening_km_s < 0:
        return None
    if not math.isfinite(ebv):
        return None
    if not math.isfinite(distance_kpc) or distance_kpc <= 0:
        return None

    wavelength_scale = 1.0 / (1.0 + redshift)
    transformed_x = wavelength * wavelength_scale
    transformed_y = flux.copy()

    if mode == "both":
        transformed_y = transformed_y / (distance_kpc * distance_kpc)
        transformed_y = transformed_y * _reddening_scale(transformed_x, ebv)

    if broadening_km_s > 0:
        transformed_y = _gaussian_broaden_by_velocity(transformed_x, transformed_y, broadening_km_s)

    return transformed_x, transformed_y


def _sample_model_on_observed_grid(
    model_x: Any,
    model_y: Any,
    observed_x: Any,
    band_width: Any | None = None,
) -> Any:
    if np is None:
        return None

    sampled = np.interp(observed_x, model_x, model_y, left=np.nan, right=np.nan)
    if band_width is None:
        return sampled

    width = np.asarray(band_width, dtype=np.float64).reshape(-1)
    if width.size != sampled.size:
        return sampled
    if model_x.size < 2:
        return sampled

    x_min = float(model_x[0])
    x_max = float(model_x[-1])
    for index, width_value in enumerate(width):
        if not math.isfinite(float(width_value)) or float(width_value) <= 0.0:
            continue
        center = float(observed_x[index])
        half_width = 0.5 * float(width_value)
        lo = max(x_min, center - half_width)
        hi = min(x_max, center + half_width)
        if hi <= lo:
            continue

        segment_mask = (model_x > lo) & (model_x < hi)
        segment_x = model_x[segment_mask]
        segment_y = model_y[segment_mask]
        segment_x = np.concatenate(([lo], segment_x, [hi]))
        segment_y = np.concatenate(
            (
                [float(np.interp(lo, model_x, model_y))],
                segment_y,
                [float(np.interp(hi, model_x, model_y))],
            )
        )
        if segment_x.size < 2:
            continue
        denominator = hi - lo
        if denominator <= 0.0:
            continue
        sampled[index] = float(np.trapz(segment_y, segment_x) / denominator)
    return sampled


def _estimate_effective_sample_size_from_residuals(
    residual: Any,
    *,
    max_lag: int = 200,
) -> tuple[float, float, int]:
    if np is None:
        return 1.0, 0.0, 0
    values = np.asarray(residual, dtype=np.float64).reshape(-1)
    if values.size < 4:
        size = float(max(1, int(values.size)))
        return size, 0.0, 0

    finite = np.isfinite(values)
    values = values[finite]
    n = int(values.size)
    if n < 4:
        return float(max(1, n)), 0.0, 0

    centered = values - float(np.mean(values))
    variance_scale = float(np.dot(centered, centered))
    if not math.isfinite(variance_scale) or variance_scale <= 0.0:
        return float(n), 0.0, 0

    lag_cap = min(int(max_lag), n // 4)
    if lag_cap < 1:
        return float(n), 0.0, 0

    rho_sum = 0.0
    used_lags = 0
    for lag in range(1, lag_cap + 1):
        numerator = float(np.dot(centered[:-lag], centered[lag:]))
        rho = numerator / variance_scale
        if not math.isfinite(rho):
            break
        rho = max(-1.0, min(1.0, rho))
        if rho <= 0.0:
            break
        rho_sum += rho
        used_lags = lag

    inflation = 1.0 + (2.0 * rho_sum)
    if not math.isfinite(inflation) or inflation <= 0.0:
        return float(n), rho_sum, used_lags
    n_eff = float(n) / inflation
    if not math.isfinite(n_eff):
        return float(n), rho_sum, used_lags
    n_eff = min(float(n), max(1.0, n_eff))
    return n_eff, rho_sum, used_lags


def fit_model_to_observed(
    continuum: dict[str, object],
    final: dict[str, object],
    observed: dict[str, object],
    *,
    mode: str,
    initial_params: dict[str, float] | None = None,
    bounds_override: dict[str, tuple[float, float]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, float] | None, dict[str, object] | None, str | None]:
    if np is None or least_squares is None:
        return None, None, "Server-side fitting requires numpy and scipy."

    normalized_mode = "both" if mode == "both" else "normalized"
    model_series = _build_model_series_for_fit(continuum, final, mode=normalized_mode)
    if model_series is None:
        return None, None, "Model spectrum data could not be prepared for fitting."
    model_x, model_y = model_series

    observed_series, observed_error = _build_observed_series_for_fit(observed, mode=normalized_mode)
    if observed_error:
        return None, None, observed_error
    if observed_series is None:
        return None, None, "Observed upload could not be prepared for fitting."
    observed_x, observed_y, observed_band_width = observed_series
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    is_photometry = observation_type == "photometry"

    if observed_x.size > MAX_SERIES_POINTS:
        sample_idx = np.linspace(0, observed_x.size - 1, MAX_SERIES_POINTS, dtype=int)
        observed_x = observed_x[sample_idx]
        observed_y = observed_y[sample_idx]
        if observed_band_width is not None:
            observed_band_width = observed_band_width[sample_idx]

    obs_scale = 1.0
    norm_weights = np.ones_like(observed_y, dtype=np.float64)
    if normalized_mode != "both":
        finite_obs = observed_y[np.isfinite(observed_y)]
        if finite_obs.size:
            scale_candidate = float(np.median(np.abs(finite_obs)))
            if math.isfinite(scale_candidate) and scale_candidate > 0:
                obs_scale = scale_candidate
            continuum_level = float(np.median(finite_obs))
            signal = np.abs(observed_y - continuum_level)
            signal_finite = signal[np.isfinite(signal)]
            if signal_finite.size:
                signal_scale = float(np.percentile(signal_finite, 90))
                if math.isfinite(signal_scale) and signal_scale > 0:
                    norm_weights = 1.0 + 4.0 * np.clip(signal / signal_scale, 0.0, 1.0)

    bounds = _resolve_fit_bounds(normalized_mode, bounds_override)
    names = list(bounds.keys())
    lower = np.array([bounds[name][0] for name in names], dtype=np.float64)
    upper = np.array([bounds[name][1] for name in names], dtype=np.float64)

    initial = dict(initial_params or {})
    default_distance = 1.0
    initial_distance_raw = initial.get("distance_kpc")
    initial_distance_ok = False
    if isinstance(initial_distance_raw, int | float):
        initial_distance_ok = math.isfinite(float(initial_distance_raw))
    if normalized_mode == "both" and not initial_distance_ok:
        model_on_obs = _sample_model_on_observed_grid(model_x, model_y, observed_x, observed_band_width)
        valid_scale = np.isfinite(model_on_obs) & np.isfinite(observed_y) & (model_on_obs > 0) & (observed_y > 0)
        min_scale_points = 4 if is_photometry else 20
        if np.count_nonzero(valid_scale) >= min_scale_points:
            ratio = np.median(model_on_obs[valid_scale] / observed_y[valid_scale])
            if math.isfinite(float(ratio)) and ratio > 0:
                default_distance = math.sqrt(float(ratio))

    x0_values: list[float] = []
    for index, name in enumerate(names):
        default = 0.0
        if name == "distance_kpc":
            default = default_distance
        raw = initial.get(name, default)
        value = float(raw) if isinstance(raw, int | float) else default
        if not math.isfinite(value):
            value = default
        value = min(max(value, float(lower[index])), float(upper[index]))
        if normalized_mode != "both" and name == "redshift" and abs(value) < 1e-10:
            value = min(max(5e-4, float(lower[index])), float(upper[index]))
        elif normalized_mode != "both" and name == "broadening_km_s" and value < 1e-9:
            value = min(max(20.0, float(lower[index])), float(upper[index]))
        elif name == "ebv" and normalized_mode == "both" and value < 1e-9:
            value = min(max(0.05, float(lower[index])), float(upper[index]))
        x0_values.append(value)
    x0 = np.array(x0_values, dtype=np.float64)
    diff_step = np.array([1e-4, 1.0, 0.01, 0.05], dtype=np.float64) if normalized_mode == "both" else np.array([1e-4, 1.0], dtype=np.float64)
    name_to_index = {name: index for index, name in enumerate(names)}

    if is_photometry:
        min_valid_points = max(len(names) + 1, int(math.ceil(0.6 * observed_x.size)))
    else:
        min_valid_points = max(30, int(0.12 * observed_x.size))
    initial_ebv = float(initial.get("ebv", 0.0)) if isinstance(initial.get("ebv"), int | float) else 0.0
    if not math.isfinite(initial_ebv):
        initial_ebv = 0.0
    initial_distance = (
        float(initial.get("distance_kpc", 1.0))
        if isinstance(initial.get("distance_kpc"), int | float)
        else 1.0
    )
    if not math.isfinite(initial_distance) or initial_distance <= 0:
        initial_distance = 1.0

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise _FitCanceledError(FIT_CANCELED_MESSAGE)

    def residual_for_params(
        *,
        redshift: float,
        broadening_km_s: float,
        ebv: float,
        distance_kpc: float,
        with_valid_count: bool = False,
    ) -> Any:
        check_cancel()
        transformed = _apply_transform_arrays(
            model_x,
            model_y,
            mode=normalized_mode,
            redshift=redshift,
            broadening_km_s=broadening_km_s,
            ebv=ebv,
            distance_kpc=distance_kpc,
        )
        if transformed is None:
            residual = np.full(observed_x.shape, 20.0, dtype=np.float64)
            return (residual, 0) if with_valid_count else residual

        model_transformed_x, model_transformed_y = transformed
        model_on_obs = _sample_model_on_observed_grid(
            model_transformed_x,
            model_transformed_y,
            observed_x,
            observed_band_width,
        )
        valid = np.isfinite(model_on_obs) & np.isfinite(observed_y)
        if normalized_mode == "both":
            valid &= (model_on_obs > 0) & (observed_y > 0)

        residual = np.full(observed_x.shape, 4.0, dtype=np.float64)
        valid_count = int(np.count_nonzero(valid))
        if valid_count < min_valid_points:
            return (residual, valid_count) if with_valid_count else residual

        if normalized_mode == "both":
            residual[valid] = np.log10(model_on_obs[valid]) - np.log10(observed_y[valid])
        else:
            residual[valid] = ((model_on_obs[valid] - observed_y[valid]) / obs_scale) * norm_weights[valid]
        residual[~valid] = 2.0
        return (residual, valid_count) if with_valid_count else residual

    def parameter_from_theta(theta: Any, name: str, fallback: float) -> float:
        idx = name_to_index.get(name)
        if idx is None or idx >= len(theta):
            return fallback
        value = float(theta[idx])
        if not math.isfinite(value):
            return fallback
        return value

    def residual_vector(theta: Any, *, with_valid_count: bool = False) -> Any:
        return residual_for_params(
            redshift=parameter_from_theta(theta, "redshift", 0.0),
            broadening_km_s=parameter_from_theta(theta, "broadening_km_s", 0.0),
            ebv=parameter_from_theta(theta, "ebv", initial_ebv),
            distance_kpc=parameter_from_theta(theta, "distance_kpc", initial_distance),
            with_valid_count=with_valid_count,
        )

    stage1_result: Any | None = None
    if normalized_mode == "both":
        redshift_index = name_to_index.get("redshift")
        broadening_index = name_to_index.get("broadening_km_s")
        ebv_index = name_to_index.get("ebv")
        distance_index = name_to_index.get("distance_kpc")

        if redshift_index is not None:
            x0[redshift_index] = min(max(0.0, float(lower[redshift_index])), float(upper[redshift_index]))
        if broadening_index is not None:
            x0[broadening_index] = min(max(0.0, float(lower[broadening_index])), float(upper[broadening_index]))

        if ebv_index is not None and distance_index is not None:
            stage1_x0 = np.array([x0[ebv_index], x0[distance_index]], dtype=np.float64)
            stage1_lower = np.array([lower[ebv_index], lower[distance_index]], dtype=np.float64)
            stage1_upper = np.array([upper[ebv_index], upper[distance_index]], dtype=np.float64)
            stage1_diff_step = np.array([diff_step[ebv_index], diff_step[distance_index]], dtype=np.float64)

            def stage1_residual(stage_theta: Any) -> Any:
                return residual_for_params(
                    redshift=0.0,
                    broadening_km_s=0.0,
                    ebv=float(stage_theta[0]),
                    distance_kpc=float(stage_theta[1]),
                    with_valid_count=False,
                )

            try:
                stage1_result = least_squares(
                    stage1_residual,
                    stage1_x0,
                    bounds=(stage1_lower, stage1_upper),
                    method="trf",
                    loss="soft_l1",
                    f_scale=0.35,
                    diff_step=stage1_diff_step,
                    max_nfev=80,
                )
                if np.all(np.isfinite(stage1_result.x)):
                    _, stage1_valid_count = residual_for_params(
                        redshift=0.0,
                        broadening_km_s=0.0,
                        ebv=float(stage1_result.x[0]),
                        distance_kpc=float(stage1_result.x[1]),
                        with_valid_count=True,
                    )
                    if stage1_valid_count >= min_valid_points:
                        x0[ebv_index] = float(stage1_result.x[0])
                        x0[distance_index] = float(stage1_result.x[1])
            except _FitCanceledError:
                return None, None, FIT_CANCELED_MESSAGE
            except Exception:
                stage1_result = None

    try:
        result = least_squares(
            residual_vector,
            x0,
            bounds=(lower, upper),
            method="trf",
            loss="soft_l1",
            f_scale=0.35 if normalized_mode == "both" else 1.0,
            diff_step=diff_step,
            max_nfev=120,
        )
    except _FitCanceledError:
        return None, None, FIT_CANCELED_MESSAGE
    except Exception as exc:
        return None, None, f"Optimization failed: {exc}"

    if not np.all(np.isfinite(result.x)):
        return None, None, "Optimization returned non-finite parameters."

    best = result.x
    final_residual, final_valid_count = residual_vector(best, with_valid_count=True)
    if final_valid_count < min_valid_points:
        return None, None, "Optimization did not find a usable overlap between model and observed spectra."

    redshift_value = float(best[0])
    broadening_value = float(best[1])
    ebv_value = float(best[2]) if normalized_mode == "both" else float(initial.get("ebv", 0.0))
    distance_value = float(best[3]) if normalized_mode == "both" else float(initial.get("distance_kpc", 1.0))

    params = {
        "redshift": redshift_value,
        "broadening_km_s": broadening_value,
        "ebv": ebv_value,
        "distance_kpc": distance_value,
    }
    metrics = {
        "success": bool(result.success),
        "message": str(result.message),
        "nfev": int(getattr(result, "nfev", 0)),
        "cost": float(getattr(result, "cost", math.nan)),
        "rmse": float(np.sqrt(np.mean(final_residual * final_residual))),
        "points": int(final_valid_count),
        "mode": normalized_mode,
    }
    chi2_value = float(np.sum(final_residual * final_residual))
    fit_param_count = len(names)
    dof_value = max(1, int(final_valid_count) - int(fit_param_count))
    n_eff_points, autocorr_positive_sum, autocorr_lags = _estimate_effective_sample_size_from_residuals(final_residual)
    n_eff_points = min(float(final_valid_count), max(1.0, float(n_eff_points)))
    dof_eff_value = max(1, int(round(n_eff_points)) - int(fit_param_count))
    dof_eff_value = min(dof_value, dof_eff_value)
    metrics["chi2"] = chi2_value
    metrics["dof"] = dof_value
    metrics["reduced_chi2"] = float(chi2_value / max(1, dof_value))
    metrics["dof_eff"] = int(dof_eff_value)
    metrics["n_eff_points"] = float(n_eff_points)
    metrics["autocorr_positive_sum"] = float(autocorr_positive_sum)
    metrics["autocorr_positive_lags"] = int(autocorr_lags)
    metrics["fit_param_count"] = int(fit_param_count)
    if stage1_result is not None:
        metrics["stage1_success"] = bool(getattr(stage1_result, "success", False))
        metrics["stage1_nfev"] = int(getattr(stage1_result, "nfev", 0))
    return params, metrics, None


def build_observed_overlay_trace(observed: dict[str, object], *, mode: str) -> tuple[dict[str, object] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = observed.get("band_width") if observation_type == "photometry" else None
    flux_err = observed.get("flux_err") if observation_type == "photometry" else None
    point_comment = observed.get("point_comment") if observation_type == "photometry" else None
    flux_mode = str(observed.get("flux_mode", "")).strip().lower()
    if not isinstance(wavelength, list) or not isinstance(flux, list):
        return None, "Uploaded spectrum could not be plotted: missing wavelength/flux vectors."

    if mode == "normalized" and flux_mode != "normalized":
        return None, "Uploaded spectrum is absolute-flux data; it is shown only in Spectrum + Continuum mode."
    if mode == "both" and flux_mode != "absolute":
        return None, "Uploaded spectrum is continuum-normalized; it is shown only in Normalized mode."

    if observation_type == "photometry":
        points: list[tuple[float, float, float, float | None, str]] = []
        for index, (wave_raw, flux_raw) in enumerate(zip(wavelength, flux)):
            if not isinstance(wave_raw, int | float) or not isinstance(flux_raw, int | float):
                continue
            wave_value = float(wave_raw)
            flux_value = float(flux_raw)
            if not math.isfinite(wave_value) or not math.isfinite(flux_value) or wave_value <= 0.0:
                continue
            width_value = 0.0
            if isinstance(band_width, list) and index < len(band_width):
                width_raw = band_width[index]
                if isinstance(width_raw, int | float) and math.isfinite(float(width_raw)):
                    width_value = max(0.0, float(width_raw))
            err_value: float | None = None
            if isinstance(flux_err, list) and index < len(flux_err):
                err_raw = flux_err[index]
                if isinstance(err_raw, int | float) and math.isfinite(float(err_raw)) and float(err_raw) >= 0.0:
                    err_value = float(err_raw)
            comment_value = ""
            if isinstance(point_comment, list) and index < len(point_comment):
                comment_value = str(point_comment[index] or "").strip()
            points.append((wave_value, flux_value, width_value, err_value, comment_value))
        points.sort(key=lambda item: item[0])
        if not points:
            return None, "Uploaded photometry has too few valid points for plotting."

        x = [item[0] for item in points]
        y = [item[1] for item in points]
        widths = [item[2] for item in points]
        errors = [item[3] for item in points]
        comments = [item[4] for item in points]
        hover_details: list[str] = []
        for err_value, comment_value in zip(errors, comments):
            detail = ""
            if isinstance(err_value, float):
                detail += f"<br>Flux Err={err_value:.6e}"
            if comment_value:
                detail += "<br>Comment: " + comment_value
            hover_details.append(detail)
        label = str(observed.get("name", "uploaded-photometry"))
        trace: dict[str, object] = {
            "type": "scatter",
            "mode": "markers",
            "name": f"Observed ({label})",
            "x": x,
            "y": y,
            "customdata": widths,
            "text": hover_details,
            "marker": {"color": "#212529", "size": 8, "symbol": "circle-open"},
            "hovertemplate": (
                "Wavelength=%{x:.6g} Å<br>Observed Flux=%{y:.6e}<br>Band Width=%{customdata:.6g} Å%{text}<extra></extra>"
            ),
            "meta": {"transform_target": "observed", "y_axis_name": "Flux"},
        }
        if any(value > 0.0 for value in widths):
            trace["error_x"] = {
                "type": "data",
                "array": [0.5 * value for value in widths],
                "visible": True,
                "color": PHOTOMETRY_ERROR_BAR_COLOR,
                "thickness": PHOTOMETRY_ERROR_BAR_THICKNESS,
                "width": PHOTOMETRY_ERROR_BAR_CAP_WIDTH,
            }
        if any(isinstance(value, float) and value > 0.0 for value in errors):
            trace["error_y"] = {
                "type": "data",
                "array": [value if isinstance(value, float) and value > 0.0 else 0.0 for value in errors],
                "visible": True,
                "color": PHOTOMETRY_ERROR_BAR_COLOR,
                "thickness": PHOTOMETRY_ERROR_BAR_THICKNESS,
                "width": PHOTOMETRY_ERROR_BAR_CAP_WIDTH,
            }
        return trace, None

    x, y = downsample_xy(wavelength, flux, max_points=MAX_SERIES_POINTS)
    if len(x) < 2:
        return None, "Uploaded spectrum has too few valid points for plotting."

    label = str(observed.get("name", "uploaded-spectrum"))
    if mode == "normalized":
        hover = "Wavelength=%{x:.6g} Å<br>Observed=%{y:.6g}<extra></extra>"
        y_axis_name = "Normalized"
    else:
        hover = "Wavelength=%{x:.6g} Å<br>Observed Flux=%{y:.6e}<extra></extra>"
        y_axis_name = "Flux"

    return (
        {
            "type": "scatter",
            "mode": "lines",
            "name": f"Observed ({label})",
            "x": x,
            "y": y,
            "line": {"color": "#212529", "width": 1.2, "dash": "solid"},
            "hovertemplate": hover,
            "meta": {"transform_target": "observed", "y_axis_name": y_axis_name},
        },
        None,
    )


def build_uploaded_spectrum_plot(observed: dict[str, object]) -> tuple[dict[str, object] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = observed.get("band_width") if observation_type == "photometry" else None
    flux_err = observed.get("flux_err") if observation_type == "photometry" else None
    point_comment = observed.get("point_comment") if observation_type == "photometry" else None
    flux_mode = str(observed.get("flux_mode", "")).strip().lower()
    if not isinstance(wavelength, list) or not isinstance(flux, list):
        return None, "Uploaded spectrum could not be plotted: missing wavelength/flux vectors."

    if flux_mode not in {"absolute", "normalized"}:
        flux_mode = "absolute"

    if observation_type == "photometry":
        points: list[tuple[float, float, float, float | None, str]] = []
        for index, (wave_raw, flux_raw) in enumerate(zip(wavelength, flux)):
            if not isinstance(wave_raw, int | float) or not isinstance(flux_raw, int | float):
                continue
            wave_value = float(wave_raw)
            flux_value = float(flux_raw)
            if not math.isfinite(wave_value) or not math.isfinite(flux_value) or wave_value <= 0.0:
                continue
            width_value = 0.0
            if isinstance(band_width, list) and index < len(band_width):
                width_raw = band_width[index]
                if isinstance(width_raw, int | float) and math.isfinite(float(width_raw)):
                    width_value = max(0.0, float(width_raw))
            err_value: float | None = None
            if isinstance(flux_err, list) and index < len(flux_err):
                err_raw = flux_err[index]
                if isinstance(err_raw, int | float) and math.isfinite(float(err_raw)) and float(err_raw) >= 0.0:
                    err_value = float(err_raw)
            comment_value = ""
            if isinstance(point_comment, list) and index < len(point_comment):
                comment_value = str(point_comment[index] or "").strip()
            points.append((wave_value, flux_value, width_value, err_value, comment_value))
        points.sort(key=lambda item: item[0])
        if not points:
            return None, "Uploaded photometry has too few valid points for plotting."

        x = [item[0] for item in points]
        y = [item[1] for item in points]
        widths = [item[2] for item in points]
        errors = [item[3] for item in points]
        comments = [item[4] for item in points]
        hover_details: list[str] = []
        for err_value, comment_value in zip(errors, comments):
            detail = ""
            if isinstance(err_value, float):
                detail += f"<br>Flux Err={err_value:.6e}"
            if comment_value:
                detail += "<br>Comment: " + comment_value
            hover_details.append(detail)
        prefer_log_y = all(value > 0.0 and math.isfinite(value) for value in y)
        y_scale = "log" if prefer_log_y else "linear"
        warning = None
        if not prefer_log_y:
            warning = "Photometric upload includes non-positive values; using linear y-axis."

        label = str(observed.get("name", "uploaded-photometry"))
        trace: dict[str, object] = {
            "type": "scatter",
            "mode": "markers",
            "name": f"Uploaded ({label})",
            "x": x,
            "y": y,
            "customdata": widths,
            "text": hover_details,
            "marker": {"color": "#212529", "size": 8, "symbol": "circle-open"},
            "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6e}<br>Band Width=%{customdata:.6g} Å%{text}<extra></extra>",
            "meta": {"transform_target": "model", "plot_role": "final", "y_axis_name": "Flux"},
        }
        if any(value > 0.0 for value in widths):
            trace["error_x"] = {
                "type": "data",
                "array": [0.5 * value for value in widths],
                "visible": True,
                "color": PHOTOMETRY_ERROR_BAR_COLOR,
                "thickness": PHOTOMETRY_ERROR_BAR_THICKNESS,
                "width": PHOTOMETRY_ERROR_BAR_CAP_WIDTH,
            }
        if any(isinstance(value, float) and value > 0.0 for value in errors):
            trace["error_y"] = {
                "type": "data",
                "array": [value if isinstance(value, float) and value > 0.0 else 0.0 for value in errors],
                "visible": True,
                "color": PHOTOMETRY_ERROR_BAR_COLOR,
                "thickness": PHOTOMETRY_ERROR_BAR_THICKNESS,
                "width": PHOTOMETRY_ERROR_BAR_CAP_WIDTH,
            }
        return (
            {
                "data": [trace],
                "layout": _plot_layout(y_label="Flux (uploaded units)", y_scale=y_scale),
                "config": _plot_config(),
                "default_x_scale": "log",
                "default_y_scale": y_scale,
            },
            warning,
        )

    x, y = downsample_xy(wavelength, flux, max_points=MAX_SERIES_POINTS)
    if len(x) < 2:
        return None, "Uploaded spectrum has too few valid points for plotting."

    prefer_log_y = False
    y_label = "Normalized flux"
    hover = "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6g}<extra></extra>"
    y_axis_name = "Normalized"
    if flux_mode == "absolute":
        y_label = "Flux (uploaded units)"
        hover = "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6e}<extra></extra>"
        y_axis_name = "Flux"
        prefer_log_y = all(isinstance(value, int | float) and math.isfinite(float(value)) and float(value) > 0 for value in y)

    y_scale = "log" if prefer_log_y else "linear"
    warning = None
    if flux_mode == "absolute" and not prefer_log_y:
        warning = "Absolute-flux upload includes non-positive values; using linear y-axis."

    label = str(observed.get("name", "uploaded-spectrum"))
    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": f"Uploaded ({label})",
        "x": x,
        "y": y,
        "line": {"color": "#212529", "width": 1.2},
        "hovertemplate": hover,
        "meta": {"transform_target": "model", "plot_role": "final", "y_axis_name": y_axis_name},
    }
    return (
        {
            "data": [trace],
            "layout": _plot_layout(y_label=y_label, y_scale=y_scale),
            "config": _plot_config(),
            "default_x_scale": "log",
            "default_y_scale": y_scale,
        },
        warning,
    )


def build_final_model_series(
    continuum: dict[str, object],
    final: dict[str, object],
    *,
    mode: str,
    max_points: int = MAX_SERIES_POINTS,
) -> tuple[list[float], list[float]] | None:
    """
    Build the model's final-spectrum-only series in the requested plotting mode.

    - `both`: absolute final flux converted to CGS per Angstrom.
    - `normalized`: final/continuum ratio.
    """
    normalized_mode = "both" if mode == "both" else "normalized"
    prepared = _build_model_series_for_fit(continuum, final, mode=normalized_mode)
    if prepared is None:
        return None

    model_x, model_y = prepared
    x_values = model_x.tolist()
    y_values = model_y.tolist()
    if len(x_values) < 2 or len(y_values) < 2:
        return None

    x_ds, y_ds = downsample_xy(x_values, y_values, max_points=max_points)
    if len(x_ds) < 2 or len(y_ds) < 2:
        return None
    return x_ds, y_ds


def build_both_plot(continuum: dict[str, object], final: dict[str, object]) -> dict[str, object] | None:
    cont_x = continuum.get("wavelength")
    cont_y = continuum.get("flux")
    fin_x = final.get("wavelength")
    fin_y = final.get("flux")
    if not isinstance(cont_x, list) or not isinstance(cont_y, list) or not isinstance(fin_x, list) or not isinstance(fin_y, list):
        return None
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    cont_x_cgs, cont_y_cgs = _jy_to_cgs_per_angstrom(cont_x, cont_y)
    fin_x_cgs, fin_y_cgs = _jy_to_cgs_per_angstrom(fin_x, fin_y)
    if len(cont_x_cgs) < 2 or len(fin_x_cgs) < 2:
        return None

    cont_x_ds, cont_y_ds = downsample_xy(cont_x_cgs, cont_y_cgs, max_points=MAX_SERIES_POINTS)
    fin_x_ds, fin_y_ds = downsample_xy(fin_x_cgs, fin_y_cgs, max_points=MAX_SERIES_POINTS)
    if len(cont_x_ds) < 2 or len(fin_x_ds) < 2:
        return None

    return {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"Final ({final.get('name', 'obs_fin')})",
                "x": fin_x_ds,
                "y": fin_y_ds,
                "line": {"color": "#1f77b4", "width": 1.6},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6e} erg s^-1 cm^-2 Å^-1<extra></extra>",
                "meta": {"transform_target": "model", "plot_role": "final", "y_axis_name": "Flux"},
            },
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Continuum (obs_cont)",
                "x": cont_x_ds,
                "y": cont_y_ds,
                "line": {"color": "#d62728", "width": 1.3},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6e} erg s^-1 cm^-2 Å^-1<extra></extra>",
                "meta": {"transform_target": "model", "plot_role": "continuum", "y_axis_name": "Flux"},
            },
        ],
        "layout": _plot_layout(y_label="Flux (erg s^-1 cm^-2 Å^-1)", y_scale="log"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "log",
    }


def build_normalized_plot(continuum: dict[str, object], final: dict[str, object]) -> dict[str, object] | None:
    cont_x = continuum.get("wavelength")
    cont_y = continuum.get("flux")
    fin_x = final.get("wavelength")
    fin_y = final.get("flux")
    if not isinstance(cont_x, list) or not isinstance(cont_y, list) or not isinstance(fin_x, list) or not isinstance(fin_y, list):
        return None
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    ratio_x: list[float] = []
    ratio_y: list[float] = []
    for wavelength, flux in zip(fin_x, fin_y):
        interp = _interp_linear(cont_x, cont_y, wavelength)
        if interp is None or interp == 0 or not math.isfinite(interp) or not math.isfinite(flux):
            continue
        value = flux / interp
        if not math.isfinite(value):
            continue
        ratio_x.append(wavelength)
        ratio_y.append(value)

    ratio_x_ds, ratio_y_ds = downsample_xy(ratio_x, ratio_y, max_points=MAX_SERIES_POINTS)
    if len(ratio_x_ds) < 2:
        return None

    return {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "name": f"{final.get('name', 'obs_fin')} / obs_cont",
                "x": ratio_x_ds,
                "y": ratio_y_ds,
                "line": {"color": "#198754", "width": 1.5},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Normalized=%{y:.6g}<extra></extra>",
                "meta": {"transform_target": "model", "plot_role": "final", "y_axis_name": "Normalized"},
            }
        ],
        "layout": _plot_layout(y_label="Normalized flux", y_scale="linear"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "linear",
    }


def spectrum_data_rows(continuum: dict[str, object], final: dict[str, object]) -> list[list[str]]:
    rows = [
        ["Selected final spectrum", _as_text(final.get("name", ""))],
        ["Final points", _as_text(len(final.get("wavelength", [])))],
        ["Continuum points", _as_text(len(continuum.get("wavelength", [])))],
        ["Absolute flux units", "erg s^-1 cm^-2 Å^-1"],
        ["Reference distance", "1 kpc"],
    ]
    lambda_min = final.get("lambda_min")
    lambda_max = final.get("lambda_max")
    if isinstance(lambda_min, int | float) and isinstance(lambda_max, int | float):
        rows.append(["Wavelength window (Å)", f"{format_number(lambda_min)} .. {format_number(lambda_max)}"])
    final_skipped = final.get("skipped_points")
    cont_skipped = continuum.get("skipped_points")
    if isinstance(final_skipped, int) and final_skipped > 0:
        rows.append(["Final skipped points", str(final_skipped)])
    if isinstance(cont_skipped, int) and cont_skipped > 0:
        rows.append(["Continuum skipped points", str(cont_skipped)])
    final_range_skipped = final.get("range_skipped_points")
    cont_range_skipped = continuum.get("range_skipped_points")
    if isinstance(final_range_skipped, int) and final_range_skipped > 0:
        rows.append(["Final points skipped by wavelength window", str(final_range_skipped)])
    if isinstance(cont_range_skipped, int) and cont_range_skipped > 0:
        rows.append(["Continuum points skipped by wavelength window", str(cont_range_skipped)])
    final_trimmed = final.get("trimmed_points")
    cont_trimmed = continuum.get("trimmed_points")
    if isinstance(final_trimmed, int) and final_trimmed > 0:
        rows.append(["Final trimmed short-wavelength points", str(final_trimmed)])
    if isinstance(cont_trimmed, int) and cont_trimmed > 0:
        rows.append(["Continuum trimmed short-wavelength points", str(cont_trimmed)])
    return rows


def fin_file_label(filename: str) -> str:
    match = re.match(r"^obs_fin[_-]?(.+)$", filename, re.IGNORECASE)
    if not match:
        return filename
    suffix = match.group(1).strip("_-")
    if not suffix:
        return filename
    if suffix.isdigit():
        return f"{filename} (vturb={suffix})"
    return filename
