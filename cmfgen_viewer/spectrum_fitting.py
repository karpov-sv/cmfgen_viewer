"""Observed-spectrum fitting, residual weighting, and fit diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from .spectrum_constants import (
    FIT_CANCELED_MESSAGE,
    FIT_DIFF_STEPS,
    MAX_SERIES_POINTS,
    PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION,
)
from .spectrum_options import spectrum_fit_bounds
from .spectrum_transforms import (
    _apply_transform_arrays,
    _build_model_series_for_fit,
    _clean_xy_with_band_width,
)

try:
    from scipy.optimize import least_squares
except ModuleNotFoundError:  # pragma: no cover
    least_squares = None

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None


class _FitCanceledError(Exception):
    pass


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
        resolved[name] = (lo, hi)
    return resolved


def _spectrum_sigma_with_fallback(
    observed_y: Any,
    observed_flux_err: Any,
) -> tuple[Any | None, int, int, float | None]:
    """Build spectral fit sigmas, filling sparse gaps from the measured error scale."""
    if np is None or observed_flux_err is None:
        return None, 0, 0, None

    sigma = np.asarray(observed_flux_err, dtype=np.float64).reshape(-1)
    values = np.asarray(observed_y, dtype=np.float64).reshape(-1)
    if sigma.shape != values.shape:
        return None, 0, 0, None

    provided_valid = np.isfinite(sigma) & (sigma > 0.0)
    provided_points = int(np.count_nonzero(provided_valid))
    if provided_points <= 0:
        return None, 0, 0, None

    abs_values = np.abs(values)
    relative_valid = provided_valid & np.isfinite(abs_values) & (abs_values > 0.0)
    fallback_fraction: float | None = None
    if np.any(relative_valid):
        relative_errors = sigma[relative_valid] / abs_values[relative_valid]
        relative_errors = relative_errors[
            np.isfinite(relative_errors) & (relative_errors > 0.0)
        ]
        if relative_errors.size:
            candidate = float(np.median(relative_errors))
            if math.isfinite(candidate) and candidate > 0.0:
                fallback_fraction = candidate

    fallback_absolute = float(np.median(sigma[provided_valid]))
    if not math.isfinite(fallback_absolute) or fallback_absolute <= 0.0:
        return None, 0, 0, None

    if fallback_fraction is not None:
        fallback_sigma = fallback_fraction * abs_values
    else:
        fallback_sigma = np.full(values.shape, fallback_absolute, dtype=np.float64)
    fallback_valid = np.isfinite(fallback_sigma) & (fallback_sigma > 0.0)
    fallback_sigma = np.where(fallback_valid, fallback_sigma, fallback_absolute)
    completed_sigma = np.where(provided_valid, sigma, fallback_sigma)
    return (
        completed_sigma,
        provided_points,
        int(values.size - provided_points),
        fallback_fraction,
    )


def _build_observed_series_for_fit(
    observed: dict[str, object],
    *,
    mode: str,
) -> tuple[tuple[Any, Any, Any | None, Any | None] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = (
        observed.get("band_width") if observation_type == "photometry" else None
    )
    flux_err = observed.get("flux_err")
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
        flux_err if isinstance(flux_err, list) else None,
    )
    if cleaned is None:
        return None, "Observed upload has too few valid points."
    return cleaned, None


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
        sampled[index] = float(np.trapezoid(segment_y, segment_x) / denominator)
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


def _solve_free_normalization(
    model_values: Any,
    observed_values: Any,
    sigma_values: Any | None,
) -> float | None:
    if (
        model_values.size < 1
        or observed_values.size < 1
        or model_values.size != observed_values.size
    ):
        return None

    if sigma_values is not None:
        sigma = np.asarray(sigma_values, dtype=np.float64).reshape(-1)
        if sigma.size != model_values.size:
            return None
        with np.errstate(divide="ignore", invalid="ignore"):
            weights = 1.0 / np.square(sigma)
        valid_weights = np.isfinite(weights) & (weights > 0.0)
        if not np.any(valid_weights):
            return None
        numerator = float(
            np.sum(
                weights[valid_weights]
                * model_values[valid_weights]
                * observed_values[valid_weights]
            )
        )
        denominator = float(
            np.sum(
                weights[valid_weights]
                * model_values[valid_weights]
                * model_values[valid_weights]
            )
        )
        if not math.isfinite(denominator) or denominator <= 0.0:
            return None
        scale_value = numerator / denominator
    else:
        with np.errstate(divide="ignore", invalid="ignore"):
            log_ratio = np.log(observed_values) - np.log(model_values)
        finite = np.isfinite(log_ratio)
        if not np.any(finite):
            return None
        mean_log_ratio = float(np.mean(log_ratio[finite]))
        if not math.isfinite(mean_log_ratio):
            return None
        scale_value = math.exp(mean_log_ratio)

    if not math.isfinite(scale_value) or scale_value <= 0.0:
        return None
    return float(scale_value)


@dataclass
class FitResiduals:
    """Prepared observations and model arrays used by both optimization stages."""

    model_x: Any
    model_y: Any
    observed_x: Any
    observed_y: Any
    observed_band_width: Any
    residual_sigma: Any
    normalized_mode: str
    min_valid_points: int
    use_free_normalization: bool
    obs_scale: float
    norm_weights: Any
    should_cancel: Callable[[], bool] | None = None

    def check_cancel(self) -> None:
        if self.should_cancel and self.should_cancel():
            raise _FitCanceledError(FIT_CANCELED_MESSAGE)

    def __call__(
        self,
        *,
        redshift: float,
        broadening_km_s: float,
        ebv: float,
        distance_kpc: float,
        with_valid_count: bool = False,
        with_normalization: bool = False,
    ) -> Any:
        def package_output(
            residual: Any, valid_count: int, normalization_value: float
        ) -> Any:
            if with_valid_count and with_normalization:
                return residual, valid_count, normalization_value
            if with_valid_count:
                return residual, valid_count
            if with_normalization:
                return residual, normalization_value
            return residual

        self.check_cancel()
        transformed = _apply_transform_arrays(
            self.model_x,
            self.model_y,
            mode=self.normalized_mode,
            redshift=redshift,
            broadening_km_s=broadening_km_s,
            ebv=ebv,
            distance_kpc=distance_kpc,
            normalization=1.0,
        )
        if transformed is None:
            residual = np.full(self.observed_x.shape, 20.0, dtype=np.float64)
            return package_output(residual, 0, 1.0)

        model_transformed_x, model_transformed_y = transformed
        model_on_obs = _sample_model_on_observed_grid(
            model_transformed_x,
            model_transformed_y,
            self.observed_x,
            self.observed_band_width,
        )
        valid = np.isfinite(model_on_obs) & np.isfinite(self.observed_y)
        if self.normalized_mode == "both":
            valid &= (model_on_obs > 0) & (self.observed_y > 0)
        if self.residual_sigma is not None:
            valid &= np.isfinite(self.residual_sigma) & (self.residual_sigma > 0)

        residual = np.full(self.observed_x.shape, 4.0, dtype=np.float64)
        valid_count = int(np.count_nonzero(valid))
        if valid_count < self.min_valid_points:
            return package_output(residual, valid_count, 1.0)

        normalization_value = 1.0
        if self.normalized_mode == "both":
            effective_model = model_on_obs
            if self.use_free_normalization:
                normalization_value = (
                    _solve_free_normalization(
                        model_on_obs[valid],
                        self.observed_y[valid],
                        self.residual_sigma[valid]
                        if self.residual_sigma is not None
                        else None,
                    )
                    or 0.0
                )
                if normalization_value <= 0.0:
                    return package_output(residual, valid_count, 1.0)
                effective_model = model_on_obs * normalization_value
            if self.residual_sigma is not None:
                residual[valid] = (
                    effective_model[valid] - self.observed_y[valid]
                ) / self.residual_sigma[valid]
            else:
                residual[valid] = np.log10(effective_model[valid]) - np.log10(
                    self.observed_y[valid]
                )
        else:
            if self.residual_sigma is not None:
                residual[valid] = (
                    model_on_obs[valid] - self.observed_y[valid]
                ) / self.residual_sigma[valid]
            else:
                residual[valid] = (
                    (model_on_obs[valid] - self.observed_y[valid]) / self.obs_scale
                ) * self.norm_weights[valid]
        residual[~valid] = 2.0
        return package_output(residual, valid_count, normalization_value)


def fit_model_to_observed(
    continuum: dict[str, object],
    final: dict[str, object],
    observed: dict[str, object],
    *,
    mode: str,
    initial_params: dict[str, float] | None = None,
    bounds_override: dict[str, tuple[float, float]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    absolute_scale_mode: str = "distance",
) -> tuple[dict[str, float] | None, dict[str, object] | None, str | None]:
    if np is None or least_squares is None:
        return None, None, "Server-side fitting requires numpy and scipy."

    normalized_mode = "both" if mode == "both" else "normalized"
    use_free_normalization = (
        normalized_mode == "both" and str(absolute_scale_mode).strip().lower() == "free"
    )
    model_series = _build_model_series_for_fit(continuum, final, mode=normalized_mode)
    if model_series is None:
        return None, None, "Model spectrum data could not be prepared for fitting."
    model_x, model_y = model_series

    observed_series, observed_error = _build_observed_series_for_fit(
        observed, mode=normalized_mode
    )
    if observed_error:
        return None, None, observed_error
    if observed_series is None:
        return None, None, "Observed upload could not be prepared for fitting."
    observed_x, observed_y, observed_band_width, observed_flux_err = observed_series
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    is_photometry = observation_type == "photometry"

    if observed_x.size > MAX_SERIES_POINTS:
        sample_idx = np.linspace(0, observed_x.size - 1, MAX_SERIES_POINTS, dtype=int)
        observed_x = observed_x[sample_idx]
        observed_y = observed_y[sample_idx]
        if observed_band_width is not None:
            observed_band_width = observed_band_width[sample_idx]
        if observed_flux_err is not None:
            observed_flux_err = observed_flux_err[sample_idx]

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

    photometry_sigma: Any | None = None
    photometry_sigma_provided_points = 0
    photometry_sigma_fallback_points = 0
    if is_photometry and normalized_mode == "both":
        fallback_sigma = PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION * np.abs(observed_y)
        fallback_valid = np.isfinite(fallback_sigma) & (fallback_sigma > 0.0)
        sigma = np.array(fallback_sigma, copy=True)
        provided_valid = np.zeros(observed_y.shape, dtype=bool)
        if (
            observed_flux_err is not None
            and observed_flux_err.shape == observed_y.shape
        ):
            provided_sigma = np.asarray(observed_flux_err, dtype=np.float64).reshape(-1)
            provided_valid = np.isfinite(provided_sigma) & (provided_sigma > 0.0)
            sigma = np.where(provided_valid, provided_sigma, sigma)

        sigma_valid = np.isfinite(sigma) & (sigma > 0.0)
        if not np.all(sigma_valid):
            if np.any(fallback_valid):
                sigma_floor = float(np.median(fallback_sigma[fallback_valid]))
            else:
                sigma_floor = float(np.finfo(np.float64).tiny)
            if not math.isfinite(sigma_floor) or sigma_floor <= 0.0:
                sigma_floor = float(np.finfo(np.float64).tiny)
            sigma = np.where(sigma_valid, sigma, sigma_floor)

        photometry_sigma = sigma
        photometry_sigma_provided_points = int(np.count_nonzero(provided_valid))
        photometry_sigma_fallback_points = int(
            observed_y.size - photometry_sigma_provided_points
        )

    spectrum_sigma: Any | None = None
    spectrum_sigma_provided_points = 0
    spectrum_sigma_fallback_points = 0
    spectrum_sigma_fallback_fraction: float | None = None
    if not is_photometry:
        (
            spectrum_sigma,
            spectrum_sigma_provided_points,
            spectrum_sigma_fallback_points,
            spectrum_sigma_fallback_fraction,
        ) = _spectrum_sigma_with_fallback(observed_y, observed_flux_err)
    residual_sigma = (
        photometry_sigma if photometry_sigma is not None else spectrum_sigma
    )

    bounds = _resolve_fit_bounds(normalized_mode, bounds_override)
    if use_free_normalization:
        bounds.pop("distance_kpc", None)
    fixed_params = {name: float(lo) for name, (lo, hi) in bounds.items() if lo == hi}
    names = [name for name, (lo, hi) in bounds.items() if lo != hi]
    lower = np.array([bounds[name][0] for name in names], dtype=np.float64)
    upper = np.array([bounds[name][1] for name in names], dtype=np.float64)
    fit_param_count = len(names) + (1 if use_free_normalization else 0)

    initial = dict(initial_params or {})
    default_distance = 1.0
    initial_distance_raw = initial.get("distance_kpc")
    initial_distance_ok = False
    if isinstance(initial_distance_raw, int | float):
        initial_distance_ok = math.isfinite(float(initial_distance_raw))
    if (
        normalized_mode == "both"
        and not use_free_normalization
        and not initial_distance_ok
    ):
        model_on_obs = _sample_model_on_observed_grid(
            model_x, model_y, observed_x, observed_band_width
        )
        valid_scale = (
            np.isfinite(model_on_obs)
            & np.isfinite(observed_y)
            & (model_on_obs > 0)
            & (observed_y > 0)
        )
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
    diff_step = np.array(
        [FIT_DIFF_STEPS.get(name, 1.0) for name in names], dtype=np.float64
    )
    name_to_index = {name: index for index, name in enumerate(names)}

    if is_photometry:
        # Comparing grid candidates on different subsets of sparse photometry
        # biases the ranking toward short spectral segments. A valid
        # photometric SED fit must cover every enabled point.
        min_valid_points = max(fit_param_count + 1, int(observed_x.size))
    else:
        min_valid_points = max(30, int(0.12 * observed_x.size))
    initial_ebv = (
        float(initial.get("ebv", 0.0))
        if isinstance(initial.get("ebv"), int | float)
        else 0.0
    )
    if not math.isfinite(initial_ebv):
        initial_ebv = 0.0
    initial_distance = (
        float(initial.get("distance_kpc", 1.0))
        if isinstance(initial.get("distance_kpc"), int | float)
        else 1.0
    )
    if not math.isfinite(initial_distance) or initial_distance <= 0:
        initial_distance = 1.0

    residual_for_params = FitResiduals(
        model_x=model_x,
        model_y=model_y,
        normalized_mode=normalized_mode,
        observed_x=observed_x,
        observed_y=observed_y,
        observed_band_width=observed_band_width,
        residual_sigma=residual_sigma,
        min_valid_points=min_valid_points,
        use_free_normalization=use_free_normalization,
        obs_scale=obs_scale,
        norm_weights=norm_weights,
        should_cancel=should_cancel,
    )

    def parameter_from_theta(theta: Any, name: str, fallback: float) -> float:
        fixed_value = fixed_params.get(name)
        if fixed_value is not None:
            return fixed_value
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
            x0[redshift_index] = min(
                max(0.0, float(lower[redshift_index])), float(upper[redshift_index])
            )
        if broadening_index is not None:
            x0[broadening_index] = min(
                max(0.0, float(lower[broadening_index])), float(upper[broadening_index])
            )

        stage1_x0: Any | None = None
        stage1_lower: Any | None = None
        stage1_upper: Any | None = None
        stage1_diff_step: Any | None = None

        def stage1_residual(stage_theta: Any) -> Any:
            stage_ebv = (
                float(stage_theta[0])
                if ebv_index is not None
                else parameter_from_theta(stage_theta, "ebv", initial_ebv)
            )
            stage_distance = 1.0 if use_free_normalization else float(stage_theta[1])
            return residual_for_params(
                redshift=0.0,
                broadening_km_s=0.0,
                ebv=stage_ebv,
                distance_kpc=stage_distance,
                with_valid_count=False,
            )

        if ebv_index is not None and use_free_normalization:
            stage1_x0 = np.array([x0[ebv_index]], dtype=np.float64)
            stage1_lower = np.array([lower[ebv_index]], dtype=np.float64)
            stage1_upper = np.array([upper[ebv_index]], dtype=np.float64)
            stage1_diff_step = np.array([diff_step[ebv_index]], dtype=np.float64)
        elif ebv_index is not None and distance_index is not None:
            stage1_x0 = np.array([x0[ebv_index], x0[distance_index]], dtype=np.float64)
            stage1_lower = np.array(
                [lower[ebv_index], lower[distance_index]], dtype=np.float64
            )
            stage1_upper = np.array(
                [upper[ebv_index], upper[distance_index]], dtype=np.float64
            )
            stage1_diff_step = np.array(
                [diff_step[ebv_index], diff_step[distance_index]], dtype=np.float64
            )

        if (
            stage1_x0 is not None
            and stage1_lower is not None
            and stage1_upper is not None
            and stage1_diff_step is not None
        ):
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
                        distance_kpc=1.0
                        if use_free_normalization
                        else float(stage1_result.x[1]),
                        with_valid_count=True,
                    )
                    if stage1_valid_count >= min_valid_points:
                        x0[ebv_index] = float(stage1_result.x[0])
                        if distance_index is not None and not use_free_normalization:
                            x0[distance_index] = float(stage1_result.x[1])
            except _FitCanceledError:
                return None, None, FIT_CANCELED_MESSAGE
            except Exception:
                stage1_result = None

    result: Any | None = None
    if names:
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
    else:
        best = np.array([], dtype=np.float64)
    final_residual, final_valid_count, final_normalization = residual_for_params(
        redshift=parameter_from_theta(best, "redshift", 0.0),
        broadening_km_s=parameter_from_theta(best, "broadening_km_s", 0.0),
        ebv=parameter_from_theta(best, "ebv", initial_ebv),
        distance_kpc=parameter_from_theta(best, "distance_kpc", initial_distance),
        with_valid_count=True,
        with_normalization=True,
    )
    if final_valid_count < min_valid_points:
        if is_photometry and final_valid_count < int(observed_x.size):
            return None, None, "Model does not cover every enabled photometry point."
        return (
            None,
            None,
            "Optimization did not find a usable overlap between model and observed spectra.",
        )

    redshift_value = parameter_from_theta(best, "redshift", 0.0)
    broadening_value = parameter_from_theta(best, "broadening_km_s", 0.0)
    ebv_fallback = (
        float(initial.get("ebv", 0.0))
        if isinstance(initial.get("ebv"), int | float)
        else 0.0
    )
    distance_fallback = (
        float(initial.get("distance_kpc", 1.0))
        if isinstance(initial.get("distance_kpc"), int | float)
        else 1.0
    )
    ebv_value = parameter_from_theta(best, "ebv", ebv_fallback)
    distance_value = (
        1.0
        if use_free_normalization
        else parameter_from_theta(best, "distance_kpc", distance_fallback)
    )
    normalization_value = float(final_normalization) if use_free_normalization else 1.0

    params = {
        "redshift": redshift_value,
        "broadening_km_s": broadening_value,
        "ebv": ebv_value,
        "distance_kpc": distance_value,
        "normalization": normalization_value,
    }
    metrics = {
        "success": bool(result.success) if result is not None else True,
        "message": str(result.message)
        if result is not None
        else "All numerical fit parameters were fixed.",
        "nfev": int(getattr(result, "nfev", 0)) if result is not None else 0,
        "cost": (
            float(getattr(result, "cost", math.nan))
            if result is not None
            else float(0.5 * np.sum(final_residual * final_residual))
        ),
        "rmse": float(np.sqrt(np.mean(final_residual * final_residual))),
        "points": int(final_valid_count),
        "mode": normalized_mode,
    }
    chi2_value = float(np.sum(final_residual * final_residual))
    dof_value = max(1, int(final_valid_count) - int(fit_param_count))
    dof_eff_method = "autocorr_initial_positive_sequence"
    if is_photometry:
        # Photometric points are treated as independent band measurements, so
        # autocorrelation-based DOF shrinkage is too conservative here.
        n_eff_points = float(final_valid_count)
        autocorr_positive_sum = 0.0
        autocorr_lags = 0
        dof_eff_value = dof_value
        dof_eff_method = "nominal_photometry"
    else:
        (
            n_eff_points,
            autocorr_positive_sum,
            autocorr_lags,
        ) = _estimate_effective_sample_size_from_residuals(final_residual)
        n_eff_points = min(float(final_valid_count), max(1.0, float(n_eff_points)))
        dof_eff_value = max(1, int(round(n_eff_points)) - int(fit_param_count))
        dof_eff_value = min(dof_value, dof_eff_value)
    metrics["chi2"] = chi2_value
    metrics["dof"] = dof_value
    metrics["reduced_chi2"] = float(chi2_value / max(1, dof_value))
    metrics["dof_eff"] = int(dof_eff_value)
    metrics["dof_eff_method"] = dof_eff_method
    metrics["n_eff_points"] = float(n_eff_points)
    metrics["autocorr_positive_sum"] = float(autocorr_positive_sum)
    metrics["autocorr_positive_lags"] = int(autocorr_lags)
    metrics["fit_param_count"] = int(fit_param_count)
    metrics["fixed_fit_params"] = dict(fixed_params)
    metrics["absolute_scale_mode"] = (
        "free_normalization" if use_free_normalization else "distance_kpc"
    )
    if photometry_sigma is not None:
        metrics["chi2_weighting"] = "photometry_flux_err_weighted"
        metrics["photometry_error_weighting"] = "flux_err_or_2pct_fallback"
        metrics["photometry_flux_err_fallback_fraction"] = float(
            PHOTOMETRY_FIT_FLUX_ERR_FALLBACK_FRACTION
        )
        metrics["photometry_flux_err_provided_points"] = int(
            photometry_sigma_provided_points
        )
        metrics["photometry_flux_err_fallback_points"] = int(
            photometry_sigma_fallback_points
        )
    elif spectrum_sigma is not None:
        metrics["chi2_weighting"] = "spectrum_flux_err_weighted"
        metrics["flux_error_weighting"] = (
            "flux_err_or_median_relative_fallback"
            if spectrum_sigma_fallback_points > 0
            else "flux_err"
        )
        metrics["spectrum_flux_err_provided_points"] = int(
            spectrum_sigma_provided_points
        )
        metrics["spectrum_flux_err_fallback_points"] = int(
            spectrum_sigma_fallback_points
        )
        if spectrum_sigma_fallback_fraction is not None:
            metrics["spectrum_flux_err_fallback_fraction"] = float(
                spectrum_sigma_fallback_fraction
            )
    elif normalized_mode == "both":
        metrics["chi2_weighting"] = "log_flux_residual_unweighted"
    else:
        metrics["chi2_weighting"] = "normalized_residual_weighted_signal"
    if stage1_result is not None:
        metrics["stage1_success"] = bool(getattr(stage1_result, "success", False))
        metrics["stage1_nfev"] = int(getattr(stage1_result, "nfev", 0))
    return params, metrics, None
