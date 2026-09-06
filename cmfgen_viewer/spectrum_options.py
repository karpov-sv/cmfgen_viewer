"""Spectrum options definitions independent of Flask."""

from __future__ import annotations

import math

from .grid_config import NPZ_GRID_FIT_SOURCES, _normalize_grid_fit_source
from .model_summary import _parse_summary_float
from .parsers.common import format_number
from .spectrum_constants import (
    ABSOLUTE_FIT_BOUNDS,
    DEFAULT_SPECTRUM_LAMBDA_MAX_ANGSTROM,
    LIGHT_SPEED_KM_PER_S,
    NORMALIZED_FIT_BOUNDS,
    SPECTRUM_TRANSFORM_DEFAULTS,
)


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


def _normalize_spectrum_mode(raw_mode: str | None) -> str:
    mode = (raw_mode or "both").strip().lower()
    if mode not in {"both", "normalized"}:
        return "both"
    return mode


def _normalize_transform_params(
    params: dict[str, object] | None = None,
) -> dict[str, float]:
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
    if (
        normalization_raw is not None
        and math.isfinite(normalization_raw)
        and normalization_raw > 0
    ):
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
    if (
        mode == "both"
        and _normalize_grid_fit_source(fit_source) in NPZ_GRID_FIT_SOURCES
    ):
        defaults.pop("distance_kpc", None)
    values = params or {}
    normalized: dict[str, tuple[float, float]] = {}
    for name, (default_min, default_max) in defaults.items():
        min_raw = _parse_summary_float(values.get(f"fit_{name}_min"))
        max_raw = _parse_summary_float(values.get(f"fit_{name}_max"))

        min_value = (
            float(min_raw)
            if min_raw is not None and math.isfinite(min_raw)
            else float(default_min)
        )
        max_value = (
            float(max_raw)
            if max_raw is not None and math.isfinite(max_raw)
            else float(default_max)
        )
        if min_value > max_value:
            min_value, max_value = max_value, min_value

        if name == "broadening_km_s":
            min_value = max(0.0, min_value)
            max_value = max(0.0, max_value)
        elif name == "distance_kpc":
            min_value = max(1e-6, min_value)
            max_value = max(1e-6, max_value)

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


def spectrum_fit_bounds(mode: str) -> dict[str, tuple[float, float]]:
    if mode == "both":
        return dict(ABSOLUTE_FIT_BOUNDS)
    return dict(NORMALIZED_FIT_BOUNDS)
