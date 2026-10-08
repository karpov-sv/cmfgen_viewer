"""Pure spectrum array preparation, physical transformations, and interpolation."""

from __future__ import annotations

import math
from collections import OrderedDict
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
    from scipy.signal import fftconvolve
except ModuleNotFoundError:  # pragma: no cover
    gaussian_filter1d = None
    fftconvolve = None

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
    x_values: Any, y_values: Any
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

    if np.any(x[1:] <= x[:-1]):
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


def _reddening_exponent(wavelength_angstrom: Any, *, r_v: float = 3.1) -> Any:
    """Base-10 attenuation exponent per unit E(B-V), independent of E(B-V)."""
    if np is None:
        return None

    wavelength = np.asarray(wavelength_angstrom, dtype=np.float64)
    out = np.zeros_like(wavelength, dtype=np.float64)
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

    out[valid] = -0.4 * curve
    return out


def _attenuation_from_exponent(exponent: Any, ebv: float) -> Any:
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        factor = np.power(10.0, ebv * exponent)
    factor[~np.isfinite(factor)] = 1.0
    factor[factor <= 0] = 1.0
    return factor


def _reddening_scale(wavelength_angstrom: Any, ebv: float, *, r_v: float = 3.1) -> Any:
    if np is None:
        return None
    if not math.isfinite(ebv) or ebv == 0:
        return np.ones_like(wavelength_angstrom, dtype=np.float64)
    return _attenuation_from_exponent(_reddening_exponent(wavelength_angstrom, r_v=r_v), ebv)


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
    smoothed = _smooth_gaussian(sampled, sigma_pixels)
    position = (np.log(wavelength) - log_min) / d_log
    return np.interp(position, np.arange(wavelength.size, dtype=np.float64), smoothed)


def _smooth_gaussian(flux: Any, sigma_pixels: float) -> Any:
    """Same discrete 4-sigma kernel and nearest edges, using FFT for wide kernels."""
    if sigma_pixels <= 16 or fftconvolve is None:
        return gaussian_filter1d(flux, sigma=sigma_pixels, mode="nearest", truncate=4.0)
    radius = int(4.0 * sigma_pixels + 0.5)
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (offsets / sigma_pixels) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(flux, (radius, radius), mode="edge")
    result = fftconvolve(padded, kernel, mode="valid")
    if np.all(flux >= 0):
        # FFT roundoff must not turn a nonnegative spectrum into negative flux.
        np.maximum(result, 0, out=result)
    return result


def _uniform_log_step(wavelength: Any) -> float | None:
    if wavelength.size < 3:
        return None
    log_wave = np.log(wavelength)
    step = float((log_wave[-1] - log_wave[0]) / (wavelength.size - 1))
    if step > 0 and np.allclose(np.diff(log_wave), step, rtol=1e-7, atol=1e-14):
        return step
    return None


class _PreparedLinearInterpolation:
    """Fixed linear interpolation, with np.interp's nearest-edge extension."""

    def __init__(self, source: Any, target: Any):
        self.left = np.clip(np.searchsorted(source, target, side="right") - 1, 0, source.size - 2)
        self.fraction = np.clip(
            (target - source[self.left]) / (source[self.left + 1] - source[self.left]), 0, 1,
        )
        self.edges = np.flatnonzero((target <= source[0]) | (target >= source[-1]))
        self.edge_sources = np.where(target[self.edges] <= source[0], 0, source.size - 1)

    def __call__(self, values: Any) -> Any:
        left_values = values[self.left]
        result = left_values + self.fraction * (values[self.left + 1] - left_values)
        # Avoid cancellation at the endpoints, including tiny nonzero fluxes.
        result[self.edges] = values[self.edge_sources]
        return result


class _PreparedBroadeningGeometry:
    """Reuse the native-size log lattice and both interpolation mappings.

    A redshift scales all wavelengths equally, leaving this geometry unchanged
    apart from roundoff. Extinction is still applied on the native, shifted
    wavelengths before interpolation and the existing Gaussian convolution.
    """

    def __init__(self, wavelength: Any):
        log_min, log_max = math.log(wavelength[0]), math.log(wavelength[-1])
        self.step = (log_max - log_min) / (wavelength.size - 1)
        sample_x = np.exp(np.linspace(log_min, log_max, wavelength.size))
        position = (np.log(wavelength) - log_min) / self.step
        self.to_log = _PreparedLinearInterpolation(wavelength, sample_x)
        self.to_native = _PreparedLinearInterpolation(np.arange(wavelength.size), position)

    def __call__(self, values: Any, sigma_km_s: float, shifted: Any) -> Any:
        # Match the original shifted-axis arithmetic for the discrete kernel's
        # radius/threshold, even exactly at rounding-sensitive boundaries.
        step = (math.log(shifted[-1]) - math.log(shifted[0])) / (shifted.size - 1)
        sigma_pixels = sigma_km_s / LIGHT_SPEED_KM_PER_S / step
        if sigma_pixels < 0.15:
            return values
        sampled = self.to_log(values)
        smoothed = _smooth_gaussian(sampled, sigma_pixels)
        return self.to_native(smoothed)


class PreparedSpectrumTransform:
    """Per-fit, bounded caches; retain transform order and the native model axis."""

    def __init__(self, wavelength: Any, flux: Any, mode: str):
        self.wavelength, self.flux, self.mode = wavelength, flux, mode
        self.log_step = _uniform_log_step(wavelength)
        self.shift_cache = OrderedDict()
        self.broadening_geometry = None

    def is_unbroadened(self, sigma_km_s: float) -> bool:
        if not math.isfinite(sigma_km_s) or sigma_km_s < 0:
            return False
        if gaussian_filter1d is None or sigma_km_s == 0 or self.wavelength.size < 3:
            return True
        step = math.log(self.wavelength[-1] / self.wavelength[0]) / (self.wavelength.size - 1)
        return sigma_km_s / LIGHT_SPEED_KM_PER_S / step < 0.15

    def sample_unbroadened(self, observed_x: Any, *, redshift: float, ebv: float,
                          distance_kpc: float, normalization: float = 1.0) -> Any:
        """Exact point-sampling shortcut; redden the interpolation neighbors only.

        This does not commute reddening and interpolation. Each retained model
        sample is transformed first, just as in the full-vector calculation.
        Not applicable to band-integrated photometry or nonzero smoothing.
        """
        if not math.isfinite(redshift) or redshift <= -1:
            return None
        positions = np.searchsorted(self.wavelength, observed_x / (1 + redshift))
        indices = np.unique(np.clip(np.concatenate((positions - 1, positions, positions + 1)),
                                    0, self.wavelength.size - 1))
        transformed = _apply_transform_arrays(
            self.wavelength[indices], self.flux[indices], mode=self.mode,
            redshift=redshift, broadening_km_s=0, ebv=ebv, distance_kpc=distance_kpc,
            normalization=normalization,
        )
        if transformed is None:
            return None
        return np.interp(observed_x, *transformed, left=np.nan, right=np.nan)

    def __call__(self, *, redshift: float, broadening_km_s: float,
                 ebv: float, distance_kpc: float, normalization: float = 1.0) -> Any:
        if (not all(math.isfinite(v) for v in (redshift, broadening_km_s, ebv, distance_kpc, normalization))
                or redshift <= -1 or broadening_km_s < 0 or distance_kpc <= 0):
            return None
        if redshift not in self.shift_cache:
            shifted = self.wavelength * (1 + redshift)
            self.shift_cache[redshift] = shifted, None
            if len(self.shift_cache) > 4:
                self.shift_cache.popitem(last=False)
        self.shift_cache.move_to_end(redshift)
        shifted, exponent = self.shift_cache[redshift]
        values = self.flux
        if self.mode == "both":
            values = values * (normalization / distance_kpc ** 2)
            if ebv != 0:
                if exponent is None:
                    exponent = _reddening_exponent(shifted)
                    self.shift_cache[redshift] = shifted, exponent
                values = values * _attenuation_from_exponent(exponent, ebv)
        if broadening_km_s > 0:
            if self.log_step is not None and gaussian_filter1d is not None:
                sigma_pixels = broadening_km_s / LIGHT_SPEED_KM_PER_S / self.log_step
                if sigma_pixels >= 0.15:
                    values = _smooth_gaussian(values, sigma_pixels)
            elif gaussian_filter1d is not None and not self.is_unbroadened(broadening_km_s):
                if self.broadening_geometry is None:
                    self.broadening_geometry = _PreparedBroadeningGeometry(self.wavelength)
                values = self.broadening_geometry(values, broadening_km_s, shifted)
            else:
                values = _gaussian_broaden_by_velocity(shifted, values, broadening_km_s)
        return shifted, values


def _crop_model_for_fit(wavelength: Any, flux: Any, observed_x: Any,
                        band_width: Any, bounds: dict) -> tuple[Any, Any]:
    """Crop only uniform log grids: preserve sampling and all convolution support.

    Nonuniform grids retain their full axis because changing their endpoints
    would change the temporary convolution resampling lattice.
    """
    step = _uniform_log_step(wavelength)
    if step is None:
        return wavelength, flux
    zlo, zhi = bounds.get("redshift", (0, 0))
    sigma_max = max(bounds.get("broadening_km_s", (0, 0)))
    # Stage-one absolute fits also evaluate zero redshift.
    zlo, zhi = min(zlo, 0), max(zhi, 0)
    if zlo <= -1 or not np.isfinite([zlo, zhi, sigma_max]).all():
        return wavelength, flux
    half_width = band_width / 2 if band_width is not None else 0
    support = 4 * max(0, sigma_max) / LIGHT_SPEED_KM_PER_S + 3 * step
    if support > 100:
        return wavelength, flux
    lo = float(np.min(observed_x - half_width)) / (1 + zhi) * math.exp(-support)
    hi = float(np.max(observed_x + half_width)) / (1 + zlo) * math.exp(support)
    left = max(0, int(np.searchsorted(wavelength, lo)) - 1)
    right = min(wavelength.size, int(np.searchsorted(wavelength, hi, side="right")) + 1)
    if right - left < 3:
        return wavelength, flux
    return wavelength[left:right], flux[left:right]


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
        not isinstance(fin_x, (list, np.ndarray))
        or not isinstance(fin_y, (list, np.ndarray))
    ):
        return None

    cleaned_fin = _clean_xy_arrays(fin_x, fin_y)
    if cleaned_fin is None:
        return None
    fin_x_np, fin_y_np = cleaned_fin

    if mode == "both":
        converted_y = fin_y_np * JY_TO_FLAMBDA_ANGSTROM_FACTOR / np.square(fin_x_np)
        valid = np.isfinite(converted_y)
        if np.count_nonzero(valid) < 2:
            return None
        return fin_x_np[valid], converted_y[valid]

    if not isinstance(cont_x, (list, np.ndarray)) or not isinstance(cont_y, (list, np.ndarray)):
        return None
    cleaned_cont = _clean_xy_arrays(cont_x, cont_y)
    if cleaned_cont is None:
        return None
    cont_x_np, cont_y_np = cleaned_cont

    cont_interp = np.interp(fin_x_np, cont_x_np, cont_y_np, left=np.nan, right=np.nan)
    valid = np.isfinite(cont_interp) & np.isfinite(fin_y_np) & (cont_interp != 0)
    if not np.any(valid):
        return None
    ratio_x = fin_x_np[valid]
    ratio_y = fin_y_np[valid] / cont_interp[valid]
    cleaned_ratio = _clean_xy_arrays(ratio_x, ratio_y)
    if cleaned_ratio is None:
        return None
    return cleaned_ratio
