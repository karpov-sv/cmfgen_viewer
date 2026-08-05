"""Numerical fitting and spectrum preparation for model-grid candidates."""

from __future__ import annotations

import math
import os
from pathlib import Path

from .final_spectrum import (
    FIT_CANCELED_MESSAGE,
    JY_TO_FLAMBDA_ANGSTROM_FACTOR,
    discover_final_spectrum_files,
    fit_model_to_observed,
    load_obs_spectrum,
)
from .grid_catalog import _cmfgen_fit_params_payload, _tlusty_fit_params_payload
from .parsers.common import downsample_xy
from .view_common import (
    GRID_FIT_SOURCE_CMFGEN,
    GRID_FIT_SOURCE_TLUSTY,
    SPECTRUM_TRANSFORM_DEFAULTS,
    TLUSTY_FIT_MAX_MODEL_POINTS,
    _normalize_grid_fit_source,
)

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - runtime dependency
    np = None  # type: ignore[assignment]

def _fit_bounds_payload(bounds: dict[str, tuple[float, float]]) -> dict[str, list[float]]:
    return {
        name: [float(min_value), float(max_value)]
        for name, (min_value, max_value) in bounds.items()
    }


def _fit_wavelength_range_payload(bounds: tuple[float, float] | None) -> dict[str, float]:
    if bounds is None:
        return {}
    return {"min": float(bounds[0]), "max": float(bounds[1])}


def _fit_wavelength_range_from_payload(payload: object) -> tuple[float, float] | None:
    if not isinstance(payload, dict):
        return None
    min_raw = payload.get("min")
    max_raw = payload.get("max")
    if not isinstance(min_raw, int | float) or not isinstance(max_raw, int | float):
        return None
    min_value = float(min_raw)
    max_value = float(max_raw)
    if not math.isfinite(min_value) or not math.isfinite(max_value):
        return None
    if min_value > max_value:
        min_value, max_value = max_value, min_value
    if min_value <= 0 or min_value >= max_value:
        return None
    return min_value, max_value


def _resolve_grid_fit_pool_size(max_pool_size: int, total_models: int) -> int:
    if total_models <= 1:
        return 1
    resolved = int(max_pool_size) if isinstance(max_pool_size, int | float) else 0
    if resolved <= 0:
        cpu_count = os.cpu_count()
        resolved = cpu_count if isinstance(cpu_count, int) and cpu_count > 0 else 1
    resolved = max(1, resolved)
    return min(int(total_models), resolved)


def _fit_single_cmfgen_candidate(
    *,
    candidate: dict[str, object],
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
    should_cancel: object | None = None,
) -> dict[str, object]:
    model_name = str(candidate.get("model_name", "")).strip()
    model_relpath = str(candidate.get("model_relpath", candidate.get("model_path", ""))).strip().strip("/")
    model_path_str = str(candidate.get("model_path_str", "")).strip()
    if not model_name or not model_relpath or not model_path_str:
        return {"status": "failed"}

    model_dir = Path(model_path_str)
    spectrum_files = discover_final_spectrum_files(model_dir)
    if spectrum_files is None:
        return {"status": "failed"}

    fin_files = spectrum_files.get("fin_files")
    if not isinstance(fin_files, list) or not fin_files:
        return {"status": "failed"}
    selected_fin = fin_files[0]
    if not isinstance(selected_fin, Path):
        return {"status": "failed"}

    try:
        continuum = load_obs_spectrum(
            Path(spectrum_files["obs_cont"]),
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
        final = load_obs_spectrum(
            selected_fin,
            lambda_min=lambda_min,
            lambda_max=lambda_max,
        )
    except Exception:
        return {"status": "failed"}

    best_params, metrics, fit_error = fit_model_to_observed(
        continuum,
        final,
        observed,
        mode=mode,
        initial_params=SPECTRUM_TRANSFORM_DEFAULTS,
        bounds_override=fit_bounds,
        should_cancel=should_cancel,
    )
    if fit_error == FIT_CANCELED_MESSAGE:
        return {"status": "canceled"}
    if fit_error or best_params is None or not isinstance(metrics, dict):
        return {"status": "failed"}

    rmse_raw = metrics.get("rmse")
    if not isinstance(rmse_raw, int | float) or not math.isfinite(float(rmse_raw)):
        return {"status": "failed"}

    points_raw = metrics.get("points", 0)
    points = int(points_raw) if isinstance(points_raw, int | float) else 0
    chi2_raw = metrics.get("chi2")
    chi2_value = float(chi2_raw) if isinstance(chi2_raw, int | float) and math.isfinite(float(chi2_raw)) else None
    dof_raw = metrics.get("dof")
    dof_value = int(dof_raw) if isinstance(dof_raw, int | float) and int(dof_raw) > 0 else None
    dof_eff_raw = metrics.get("dof_eff")
    dof_eff_value = int(dof_eff_raw) if isinstance(dof_eff_raw, int | float) and int(dof_eff_raw) > 0 else None
    dof_eff_method_raw = metrics.get("dof_eff_method")
    dof_eff_method = str(dof_eff_method_raw).strip() if isinstance(dof_eff_method_raw, str) else ""
    chi2_weighting_raw = metrics.get("chi2_weighting")
    chi2_weighting = str(chi2_weighting_raw).strip() if isinstance(chi2_weighting_raw, str) else ""
    photometry_error_weighting_raw = metrics.get("photometry_error_weighting")
    photometry_error_weighting = (
        str(photometry_error_weighting_raw).strip()
        if isinstance(photometry_error_weighting_raw, str)
        else ""
    )
    photometry_flux_err_provided_raw = metrics.get("photometry_flux_err_provided_points")
    photometry_flux_err_provided = (
        int(photometry_flux_err_provided_raw)
        if isinstance(photometry_flux_err_provided_raw, int | float) and int(photometry_flux_err_provided_raw) >= 0
        else None
    )
    photometry_flux_err_fallback_raw = metrics.get("photometry_flux_err_fallback_points")
    photometry_flux_err_fallback = (
        int(photometry_flux_err_fallback_raw)
        if isinstance(photometry_flux_err_fallback_raw, int | float) and int(photometry_flux_err_fallback_raw) >= 0
        else None
    )
    cmfgen_params_raw = candidate.get("cmfgen_params")
    if isinstance(cmfgen_params_raw, dict):
        cmfgen_params = _cmfgen_fit_params_payload(cmfgen_params_raw)
    else:
        cmfgen_params = _cmfgen_fit_params_payload(candidate)
    return {
        "status": "success",
        "item": {
            "fit_source": GRID_FIT_SOURCE_CMFGEN,
            "model_name": model_name,
            "model_path": model_relpath,
            "fin": selected_fin.name,
            "rmse": float(rmse_raw),
            "points": points,
            "chi2": chi2_value,
            "dof": dof_value,
            "dof_eff": dof_eff_value,
            "dof_eff_method": dof_eff_method,
            "chi2_weighting": chi2_weighting,
            "photometry_error_weighting": photometry_error_weighting,
            "photometry_flux_err_provided_points": photometry_flux_err_provided,
            "photometry_flux_err_fallback_points": photometry_flux_err_fallback,
            "cmfgen_params": cmfgen_params,
            "fit_params": {
                "redshift": float(best_params.get("redshift", 0.0)),
                "broadening_km_s": float(best_params.get("broadening_km_s", 0.0)),
                "ebv": float(best_params.get("ebv", 0.0)),
                "distance_kpc": float(best_params.get("distance_kpc", 1.0)),
            },
        },
    }


_GRID_FIT_WORKER_CONTEXT: dict[str, object] = {}


def _load_tlusty_npz_arrays(npz_path: Path) -> dict[str, object] | None:
    if np is None:
        return None
    if not npz_path.is_file():
        return None
    try:
        with np.load(npz_path, allow_pickle=False) as payload:
            arrays: dict[str, object] = {}
            for key in payload.files:
                arrays[key] = np.asarray(payload[key], dtype=np.float64).reshape(-1)
            return arrays
    except Exception:
        return None


def _tlusty_pick_flux_array(arrays: dict[str, object]) -> object | None:
    preferred = ["flux_lambda_cgs", "hnu_cgs", "y_col_1"]
    for name in preferred:
        value = arrays.get(name)
        if value is not None:
            return value
    return None


def _build_tlusty_model_series(
    *,
    mode: str,
    spectrum_path: Path,
    continuum_path: Path | None,
    max_points: int = 0,
) -> tuple[list[float] | None, list[float] | None, str | None]:
    if np is None:
        return None, None, "numpy is required for TLUSTY fitting."

    spectrum_arrays = _load_tlusty_npz_arrays(spectrum_path)
    if not isinstance(spectrum_arrays, dict):
        return None, None, f"TLUSTY spectrum file is not available: {spectrum_path.name}"

    wavelength_raw = spectrum_arrays.get("wavelength_angstrom")
    flux_raw = _tlusty_pick_flux_array(spectrum_arrays)
    if wavelength_raw is None or flux_raw is None:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' is missing required arrays."

    wavelength = np.asarray(wavelength_raw, dtype=np.float64).reshape(-1)
    flux = np.asarray(flux_raw, dtype=np.float64).reshape(-1)
    if wavelength.size != flux.size or wavelength.size < 2:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' has incompatible wavelength/flux arrays."

    y_values: object
    if mode == "both":
        y_values = flux
    else:
        normalized_candidate = spectrum_arrays.get("normalized_flux_candidate")
        if normalized_candidate is not None:
            y_values = np.asarray(normalized_candidate, dtype=np.float64).reshape(-1)
            if y_values.size != wavelength.size:
                normalized_candidate = None
        if normalized_candidate is None:
            continuum = spectrum_arrays.get("continuum_lambda_cgs")
            if continuum is not None:
                continuum_arr = np.asarray(continuum, dtype=np.float64).reshape(-1)
                if continuum_arr.size != wavelength.size:
                    continuum_arr = np.array([], dtype=np.float64)
            else:
                continuum_arr = np.array([], dtype=np.float64)

            if continuum_arr.size != wavelength.size and continuum_path is not None:
                continuum_arrays = _load_tlusty_npz_arrays(continuum_path)
                if not isinstance(continuum_arrays, dict):
                    return None, None, f"TLUSTY continuum file is not available: {continuum_path.name}"
                continuum_wavelength_raw = continuum_arrays.get("wavelength_angstrom")
                continuum_flux_raw = continuum_arrays.get("continuum_lambda_cgs")
                if continuum_flux_raw is None:
                    continuum_flux_raw = _tlusty_pick_flux_array(continuum_arrays)
                if continuum_wavelength_raw is None or continuum_flux_raw is None:
                    return None, None, f"TLUSTY continuum file '{continuum_path.name}' is missing required arrays."

                continuum_wavelength = np.asarray(continuum_wavelength_raw, dtype=np.float64).reshape(-1)
                continuum_flux = np.asarray(continuum_flux_raw, dtype=np.float64).reshape(-1)
                if continuum_wavelength.size != continuum_flux.size or continuum_wavelength.size < 2:
                    return None, None, f"TLUSTY continuum file '{continuum_path.name}' has incompatible arrays."

                cont_valid = np.isfinite(continuum_wavelength) & np.isfinite(continuum_flux) & (continuum_wavelength > 0)
                continuum_wavelength = continuum_wavelength[cont_valid]
                continuum_flux = continuum_flux[cont_valid]
                if continuum_wavelength.size < 2:
                    return None, None, f"TLUSTY continuum file '{continuum_path.name}' has too few valid points."

                order = np.argsort(continuum_wavelength)
                continuum_wavelength = continuum_wavelength[order]
                continuum_flux = continuum_flux[order]
                unique = np.concatenate(([True], np.diff(continuum_wavelength) > 0.0))
                continuum_wavelength = continuum_wavelength[unique]
                continuum_flux = continuum_flux[unique]
                if continuum_wavelength.size < 2:
                    return None, None, f"TLUSTY continuum file '{continuum_path.name}' has duplicate wavelength points only."
                continuum_arr = np.interp(wavelength, continuum_wavelength, continuum_flux, left=np.nan, right=np.nan)

            if continuum_arr.size != wavelength.size:
                return None, None, "Could not derive continuum for normalized TLUSTY fitting."

            with np.errstate(divide="ignore", invalid="ignore"):
                y_values = flux / continuum_arr

    y_array = np.asarray(y_values, dtype=np.float64).reshape(-1)
    if y_array.size != wavelength.size:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' has inconsistent vectors."

    valid = np.isfinite(wavelength) & np.isfinite(y_array) & (wavelength > 0)
    wavelength = wavelength[valid]
    y_array = y_array[valid]
    if wavelength.size < 2:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' has too few valid points."

    order = np.argsort(wavelength)
    wavelength = wavelength[order]
    y_array = y_array[order]
    unique = np.concatenate(([True], np.diff(wavelength) > 0.0))
    wavelength = wavelength[unique]
    y_array = y_array[unique]
    if wavelength.size < 2:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' has duplicate wavelengths only."

    x_values = wavelength.tolist()
    y_values_out = y_array.tolist()
    if max_points > 0 and len(x_values) > max_points:
        x_values, y_values_out = downsample_xy(x_values, y_values_out, max_points=max_points)
    if len(x_values) < 2:
        return None, None, f"TLUSTY spectrum file '{spectrum_path.name}' has too few usable points."
    return x_values, y_values_out, None


def _fit_single_tlusty_candidate(
    *,
    candidate: dict[str, object],
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    should_cancel: object | None = None,
) -> dict[str, object]:
    model_name = str(candidate.get("model_name", "")).strip()
    model_path = str(candidate.get("model_path", "")).strip()
    spectrum_relpath = str(candidate.get("spectrum_relpath", "")).strip()
    spectrum_path_str = str(candidate.get("spectrum_path_str", "")).strip()
    continuum_relpath = str(candidate.get("continuum_relpath", "")).strip()
    continuum_path_str = str(candidate.get("continuum_path_str", "")).strip()
    fin_label = str(candidate.get("spectrum_label", "spectrum")).strip() or "spectrum"
    if not model_name or not model_path or not spectrum_path_str:
        return {"status": "failed"}

    spectrum_path = Path(spectrum_path_str)
    continuum_path = Path(continuum_path_str) if continuum_path_str else None
    model_x, model_y, build_error = _build_tlusty_model_series(
        mode=mode,
        spectrum_path=spectrum_path,
        continuum_path=continuum_path,
        max_points=TLUSTY_FIT_MAX_MODEL_POINTS,
    )
    if build_error or not isinstance(model_x, list) or not isinstance(model_y, list):
        return {"status": "failed"}

    tlusty_params_raw = candidate.get("tlusty_params")
    if isinstance(tlusty_params_raw, dict):
        tlusty_params = _tlusty_fit_params_payload(tlusty_params_raw)
    else:
        tlusty_params = _tlusty_fit_params_payload(candidate)

    if mode == "both":
        jy_flux: list[float] = []
        wavelength_out: list[float] = []
        for wavelength, flux in zip(model_x, model_y):
            if not isinstance(wavelength, int | float) or not isinstance(flux, int | float):
                continue
            wave = float(wavelength)
            value = float(flux)
            if not math.isfinite(wave) or not math.isfinite(value) or wave <= 0:
                continue
            jy = value * wave * wave / JY_TO_FLAMBDA_ANGSTROM_FACTOR
            if not math.isfinite(jy):
                continue
            wavelength_out.append(wave)
            jy_flux.append(jy)
        if len(wavelength_out) < 2 or len(jy_flux) < 2:
            return {"status": "failed"}
        continuum = {"wavelength": wavelength_out, "flux": jy_flux}
        final = {"wavelength": wavelength_out, "flux": jy_flux}
    else:
        continuum = {"wavelength": model_x, "flux": [1.0] * len(model_x)}
        final = {"wavelength": model_x, "flux": model_y}

    best_params, metrics, fit_error = fit_model_to_observed(
        continuum,
        final,
        observed,
        mode=mode,
        initial_params=SPECTRUM_TRANSFORM_DEFAULTS,
        bounds_override=fit_bounds,
        should_cancel=should_cancel,
        absolute_scale_mode="free",
    )
    if fit_error == FIT_CANCELED_MESSAGE:
        return {"status": "canceled"}
    if fit_error or best_params is None or not isinstance(metrics, dict):
        return {"status": "failed"}

    rmse_raw = metrics.get("rmse")
    if not isinstance(rmse_raw, int | float) or not math.isfinite(float(rmse_raw)):
        return {"status": "failed"}
    points_raw = metrics.get("points", 0)
    points = int(points_raw) if isinstance(points_raw, int | float) else 0
    chi2_raw = metrics.get("chi2")
    chi2_value = float(chi2_raw) if isinstance(chi2_raw, int | float) and math.isfinite(float(chi2_raw)) else None
    dof_raw = metrics.get("dof")
    dof_value = int(dof_raw) if isinstance(dof_raw, int | float) and int(dof_raw) > 0 else None
    dof_eff_raw = metrics.get("dof_eff")
    dof_eff_value = int(dof_eff_raw) if isinstance(dof_eff_raw, int | float) and int(dof_eff_raw) > 0 else None
    dof_eff_method_raw = metrics.get("dof_eff_method")
    dof_eff_method = str(dof_eff_method_raw).strip() if isinstance(dof_eff_method_raw, str) else ""
    chi2_weighting_raw = metrics.get("chi2_weighting")
    chi2_weighting = str(chi2_weighting_raw).strip() if isinstance(chi2_weighting_raw, str) else ""
    photometry_error_weighting_raw = metrics.get("photometry_error_weighting")
    photometry_error_weighting = (
        str(photometry_error_weighting_raw).strip()
        if isinstance(photometry_error_weighting_raw, str)
        else ""
    )
    photometry_flux_err_provided_raw = metrics.get("photometry_flux_err_provided_points")
    photometry_flux_err_provided = (
        int(photometry_flux_err_provided_raw)
        if isinstance(photometry_flux_err_provided_raw, int | float) and int(photometry_flux_err_provided_raw) >= 0
        else None
    )
    photometry_flux_err_fallback_raw = metrics.get("photometry_flux_err_fallback_points")
    photometry_flux_err_fallback = (
        int(photometry_flux_err_fallback_raw)
        if isinstance(photometry_flux_err_fallback_raw, int | float) and int(photometry_flux_err_fallback_raw) >= 0
        else None
    )

    return {
        "status": "success",
        "item": {
            "fit_source": GRID_FIT_SOURCE_TLUSTY,
            "model_name": model_name,
            "model_path": model_path,
            "fin": fin_label,
            "rmse": float(rmse_raw),
            "points": points,
            "chi2": chi2_value,
            "dof": dof_value,
            "dof_eff": dof_eff_value,
            "dof_eff_method": dof_eff_method,
            "chi2_weighting": chi2_weighting,
            "photometry_error_weighting": photometry_error_weighting,
            "photometry_flux_err_provided_points": photometry_flux_err_provided,
            "photometry_flux_err_fallback_points": photometry_flux_err_fallback,
            "fit_params": {
                "redshift": float(best_params.get("redshift", 0.0)),
                "broadening_km_s": float(best_params.get("broadening_km_s", 0.0)),
                "ebv": float(best_params.get("ebv", 0.0)),
                "distance_kpc": 1.0,
                "normalization": float(best_params.get("normalization", 1.0)),
            },
            "tlusty_spectrum_relpath": spectrum_relpath,
            "tlusty_continuum_relpath": continuum_relpath,
            "tlusty_grid": str(candidate.get("grid", "")),
            "tlusty_params": tlusty_params,
        },
    }


def _fit_single_grid_candidate(
    *,
    fit_source: str,
    candidate: dict[str, object],
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
    should_cancel: object | None = None,
) -> dict[str, object]:
    if _normalize_grid_fit_source(fit_source) == GRID_FIT_SOURCE_TLUSTY:
        return _fit_single_tlusty_candidate(
            candidate=candidate,
            observed=observed,
            mode=mode,
            fit_bounds=fit_bounds,
            should_cancel=should_cancel,
        )
    return _fit_single_cmfgen_candidate(
        candidate=candidate,
        observed=observed,
        mode=mode,
        fit_bounds=fit_bounds,
        lambda_min=lambda_min,
        lambda_max=lambda_max,
        should_cancel=should_cancel,
    )


def _grid_fit_worker_init(
    observed: dict[str, object],
    mode: str,
    fit_bounds: dict[str, tuple[float, float]],
    lambda_min: float,
    lambda_max: float,
    fit_source: str,
) -> None:
    global _GRID_FIT_WORKER_CONTEXT
    _GRID_FIT_WORKER_CONTEXT = {
        "observed": observed,
        "mode": mode,
        "fit_bounds": fit_bounds,
        "lambda_min": float(lambda_min),
        "lambda_max": float(lambda_max),
        "fit_source": _normalize_grid_fit_source(fit_source),
    }


def _grid_fit_worker_task(model_candidate: dict[str, object]) -> dict[str, object]:
    observed = _GRID_FIT_WORKER_CONTEXT.get("observed")
    mode = _GRID_FIT_WORKER_CONTEXT.get("mode")
    fit_bounds = _GRID_FIT_WORKER_CONTEXT.get("fit_bounds")
    lambda_min = _GRID_FIT_WORKER_CONTEXT.get("lambda_min")
    lambda_max = _GRID_FIT_WORKER_CONTEXT.get("lambda_max")
    fit_source = _GRID_FIT_WORKER_CONTEXT.get("fit_source")
    if not isinstance(observed, dict):
        return {"status": "failed"}
    if not isinstance(mode, str):
        return {"status": "failed"}
    if not isinstance(fit_bounds, dict):
        return {"status": "failed"}
    if not isinstance(lambda_min, int | float) or not isinstance(lambda_max, int | float):
        return {"status": "failed"}
    if not isinstance(model_candidate, dict):
        return {"status": "failed"}
    if not isinstance(fit_source, str):
        return {"status": "failed"}
    return _fit_single_grid_candidate(
        fit_source=fit_source,
        candidate=model_candidate,
        observed=observed,
        mode=mode,
        fit_bounds=fit_bounds,
        lambda_min=float(lambda_min),
        lambda_max=float(lambda_max),
        should_cancel=None,
    )


