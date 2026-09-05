"""Pure spectrum array preparation, physical transformations, and interpolation."""

from __future__ import annotations

import math
from bisect import bisect_right
from functools import lru_cache
from typing import Any

from .spectrum_constants import JY_TO_FLAMBDA_ANGSTROM_FACTOR, LIGHT_SPEED_KM_PER_S

try:
    from scipy.interpolate import CubicSpline
except ModuleNotFoundError:  # pragma: no cover
    CubicSpline = None

try:
    from scipy.ndimage import gaussian_filter1d
except ModuleNotFoundError:  # pragma: no cover
    gaussian_filter1d = None

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None


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


def _jy_to_cgs_per_angstrom(
    wavelength: list[float], flux_jy: list[float]
) -> tuple[list[float], list[float]]:
    converted_x: list[float] = []
    converted_y: list[float] = []
    for wavelength_angstrom, flux_value_jy in zip(wavelength, flux_jy):
        if (
            wavelength_angstrom <= 0
            or not math.isfinite(wavelength_angstrom)
            or not math.isfinite(flux_value_jy)
        ):
            continue
        flux_cgs = (
            flux_value_jy
            * JY_TO_FLAMBDA_ANGSTROM_FACTOR
            / (wavelength_angstrom * wavelength_angstrom)
        )
        if not math.isfinite(flux_cgs):
            continue
        converted_x.append(wavelength_angstrom)
        converted_y.append(flux_cgs)
    return converted_x, converted_y


def _clean_xy_arrays(
    x_values: list[float], y_values: list[float]
) -> tuple[Any, Any] | None:
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
    flux_err_values: list[float | None] | None = None,
) -> tuple[Any, Any, Any | None, Any | None] | None:
    if np is None:
        return None
    if len(x_values) < 2 or len(y_values) < 2:
        return None

    x = np.asarray(x_values, dtype=np.float64).reshape(-1)
    y = np.asarray(y_values, dtype=np.float64).reshape(-1)
    if x.size != y.size or x.size < 2:
        return None

    width: Any | None = None
    if isinstance(band_width_values, list):
        if len(band_width_values) < 2:
            return None
        width = np.asarray(band_width_values, dtype=np.float64).reshape(-1)
        if x.size != width.size:
            return None

    flux_err: Any | None = None
    if isinstance(flux_err_values, list) and len(flux_err_values) == x.size:
        flux_err = np.full(x.shape, np.nan, dtype=np.float64)
        for index, value in enumerate(flux_err_values):
            if isinstance(value, int | float):
                numeric = float(value)
                if math.isfinite(numeric) and numeric >= 0.0:
                    flux_err[index] = numeric

    mask = np.isfinite(x) & np.isfinite(y) & (x > 0)
    if width is not None:
        mask &= np.isfinite(width) & (width >= 0)
    x = x[mask]
    y = y[mask]
    if width is not None:
        width = width[mask]
    if flux_err is not None:
        flux_err = flux_err[mask]
    if x.size < 2:
        return None

    order = np.argsort(x)
    x = x[order]
    y = y[order]
    if width is not None:
        width = width[order]
    if flux_err is not None:
        flux_err = flux_err[order]

    # Keep only strictly increasing wavelengths to match interpolation assumptions.
    keep = np.ones(x.shape[0], dtype=bool)
    keep[1:] = x[1:] > x[:-1]
    x = x[keep]
    y = y[keep]
    if width is not None:
        width = width[keep]
    if flux_err is not None:
        flux_err = flux_err[keep]
    if x.size < 2:
        return None
    return x, y, width, flux_err


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
    xsplopir = np.array(
        [
            0,
            10000 / 26500,
            10000 / 12200,
            10000 / 6000,
            10000 / 5470,
            10000 / 4670,
            10000 / 4110,
        ]
    )
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
    if (
        not math.isfinite(first)
        or not math.isfinite(last)
        or first <= 0
        or last <= first
    ):
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
    smoothed = gaussian_filter1d(
        sampled, sigma=sigma_pixels, mode="nearest", truncate=4.0
    )
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
    normalization: float = 1.0,
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
        normalization=normalization,
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
    normalization: float = 1.0,
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
    if not math.isfinite(normalization):
        return None

    # Shift rest-frame model wavelengths into the observed frame.  Positive
    # redshift/velocity must move spectral features to longer wavelengths.
    wavelength_scale = 1.0 + redshift
    transformed_x = wavelength * wavelength_scale
    transformed_y = flux.copy()

    if mode == "both":
        transformed_y = transformed_y * normalization
        transformed_y = transformed_y / (distance_kpc * distance_kpc)
        transformed_y = transformed_y * _reddening_scale(transformed_x, ebv)

    if broadening_km_s > 0:
        transformed_y = _gaussian_broaden_by_velocity(
            transformed_x, transformed_y, broadening_km_s
        )

    return transformed_x, transformed_y


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
    if (
        not isinstance(cont_x, list)
        or not isinstance(cont_y, list)
        or not isinstance(fin_x, list)
        or not isinstance(fin_y, list)
    ):
        return None

    cleaned_fin = _clean_xy_arrays(fin_x, fin_y)
    cleaned_cont = _clean_xy_arrays(cont_x, cont_y)
    if cleaned_fin is None or cleaned_cont is None:
        return None
    fin_x_np, fin_y_np = cleaned_fin
    cont_x_np, cont_y_np = cleaned_cont

    if mode == "both":
        converted_x, converted_y = _jy_to_cgs_per_angstrom(
            fin_x_np.tolist(), fin_y_np.tolist()
        )
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
