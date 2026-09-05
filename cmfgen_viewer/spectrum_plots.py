"""Plotly presentation and tabular exports for spectra."""

from __future__ import annotations

import math
import re

from .model_metadata import _as_text
from .parsers.common import downsample_xy, format_number
from .spectrum_constants import (
    MAX_SERIES_POINTS,
    OBSERVED_ERROR_BAR_CAP_WIDTH,
    OBSERVED_ERROR_BAR_COLOR,
    OBSERVED_ERROR_BAR_THICKNESS,
)
from .spectrum_transforms import (
    _build_model_series_for_fit,
    _interp_linear,
    _jy_to_cgs_per_angstrom,
)


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
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
        "hovermode": "closest",
    }


def _plot_config() -> dict[str, object]:
    return {
        "responsive": True,
        "displaylogo": False,
        "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    }


def _downsample_spectrum_with_flux_err(
    wavelength: list[float],
    flux: list[float],
    flux_err: object,
    *,
    max_points: int,
) -> tuple[list[float], list[float], list[float | None] | None]:
    """Downsample spectral values and their uncertainties at identical indices."""
    size = min(len(wavelength), len(flux))
    if size <= 0:
        return [], [], None

    errors = flux_err if isinstance(flux_err, list) and len(flux_err) >= size else None
    if size <= max_points:
        indices = list(range(size))
    else:
        step = size / max_points
        indices = [
            min(size - 1, int(round(index * step))) for index in range(max_points)
        ]
        indices[-1] = size - 1

    sampled_x = [wavelength[index] for index in indices]
    sampled_y = [flux[index] for index in indices]
    if errors is None:
        return sampled_x, sampled_y, None

    sampled_errors: list[float | None] = []
    for index in indices:
        value = errors[index]
        if (
            isinstance(value, int | float)
            and math.isfinite(float(value))
            and float(value) > 0.0
        ):
            sampled_errors.append(float(value))
        else:
            sampled_errors.append(None)
    return sampled_x, sampled_y, sampled_errors


def build_observed_overlay_trace(
    observed: dict[str, object], *, mode: str
) -> tuple[dict[str, object] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = (
        observed.get("band_width") if observation_type == "photometry" else None
    )
    flux_err = observed.get("flux_err")
    point_comment = (
        observed.get("point_comment") if observation_type == "photometry" else None
    )
    flux_mode = str(observed.get("flux_mode", "")).strip().lower()
    if not isinstance(wavelength, list) or not isinstance(flux, list):
        return (
            None,
            "Uploaded spectrum could not be plotted: missing wavelength/flux vectors.",
        )

    if mode == "normalized" and flux_mode != "normalized":
        return (
            None,
            "Uploaded spectrum is absolute-flux data; it is shown only in Spectrum + Continuum mode.",
        )
    if mode == "both" and flux_mode != "absolute":
        return (
            None,
            "Uploaded spectrum is continuum-normalized; it is shown only in Normalized mode.",
        )

    if observation_type == "photometry":
        points: list[tuple[float, float, float, float | None, str]] = []
        for index, (wave_raw, flux_raw) in enumerate(zip(wavelength, flux)):
            if not isinstance(wave_raw, int | float) or not isinstance(
                flux_raw, int | float
            ):
                continue
            wave_value = float(wave_raw)
            flux_value = float(flux_raw)
            if (
                not math.isfinite(wave_value)
                or not math.isfinite(flux_value)
                or wave_value <= 0.0
            ):
                continue
            width_value = 0.0
            if isinstance(band_width, list) and index < len(band_width):
                width_raw = band_width[index]
                if isinstance(width_raw, int | float) and math.isfinite(
                    float(width_raw)
                ):
                    width_value = max(0.0, float(width_raw))
            err_value: float | None = None
            if isinstance(flux_err, list) and index < len(flux_err):
                err_raw = flux_err[index]
                if (
                    isinstance(err_raw, int | float)
                    and math.isfinite(float(err_raw))
                    and float(err_raw) >= 0.0
                ):
                    err_value = float(err_raw)
            comment_value = ""
            if isinstance(point_comment, list) and index < len(point_comment):
                comment_value = str(point_comment[index] or "").strip()
            points.append(
                (wave_value, flux_value, width_value, err_value, comment_value)
            )
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
                "color": OBSERVED_ERROR_BAR_COLOR,
                "thickness": OBSERVED_ERROR_BAR_THICKNESS,
                "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
            }
        if any(isinstance(value, float) and value > 0.0 for value in errors):
            trace["error_y"] = {
                "type": "data",
                "array": [
                    value if isinstance(value, float) and value > 0.0 else 0.0
                    for value in errors
                ],
                "visible": True,
                "color": OBSERVED_ERROR_BAR_COLOR,
                "thickness": OBSERVED_ERROR_BAR_THICKNESS,
                "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
            }
        return trace, None

    x, y, errors = _downsample_spectrum_with_flux_err(
        wavelength,
        flux,
        flux_err,
        max_points=MAX_SERIES_POINTS,
    )
    if len(x) < 2:
        return None, "Uploaded spectrum has too few valid points for plotting."

    label = str(observed.get("name", "uploaded-spectrum"))
    if mode == "normalized":
        hover = "Wavelength=%{x:.6g} Å<br>Observed=%{y:.6g}<extra></extra>"
        y_axis_name = "Normalized"
    else:
        hover = "Wavelength=%{x:.6g} Å<br>Observed Flux=%{y:.6e}<extra></extra>"
        y_axis_name = "Flux"

    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": f"Observed ({label})",
        "x": x,
        "y": y,
        "line": {"color": "#212529", "width": 1.2, "dash": "solid"},
        "hovertemplate": hover,
        "meta": {"transform_target": "observed", "y_axis_name": y_axis_name},
    }
    if errors is not None and any(
        isinstance(value, float) and value > 0.0 for value in errors
    ):
        trace["error_y"] = {
            "type": "data",
            "array": [
                value if isinstance(value, float) and value > 0.0 else 0.0
                for value in errors
            ],
            "visible": True,
            "color": OBSERVED_ERROR_BAR_COLOR,
            "thickness": OBSERVED_ERROR_BAR_THICKNESS,
            "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
        }
    return trace, None


def build_uploaded_spectrum_plot(
    observed: dict[str, object],
) -> tuple[dict[str, object] | None, str | None]:
    wavelength = observed.get("wavelength")
    flux = observed.get("flux")
    observation_type = str(observed.get("observation_type", "")).strip().lower()
    band_width = (
        observed.get("band_width") if observation_type == "photometry" else None
    )
    flux_err = observed.get("flux_err")
    point_comment = (
        observed.get("point_comment") if observation_type == "photometry" else None
    )
    flux_mode = str(observed.get("flux_mode", "")).strip().lower()
    if not isinstance(wavelength, list) or not isinstance(flux, list):
        return (
            None,
            "Uploaded spectrum could not be plotted: missing wavelength/flux vectors.",
        )

    if flux_mode not in {"absolute", "normalized"}:
        flux_mode = "absolute"

    if observation_type == "photometry":
        points: list[tuple[float, float, float, float | None, str]] = []
        for index, (wave_raw, flux_raw) in enumerate(zip(wavelength, flux)):
            if not isinstance(wave_raw, int | float) or not isinstance(
                flux_raw, int | float
            ):
                continue
            wave_value = float(wave_raw)
            flux_value = float(flux_raw)
            if (
                not math.isfinite(wave_value)
                or not math.isfinite(flux_value)
                or wave_value <= 0.0
            ):
                continue
            width_value = 0.0
            if isinstance(band_width, list) and index < len(band_width):
                width_raw = band_width[index]
                if isinstance(width_raw, int | float) and math.isfinite(
                    float(width_raw)
                ):
                    width_value = max(0.0, float(width_raw))
            err_value: float | None = None
            if isinstance(flux_err, list) and index < len(flux_err):
                err_raw = flux_err[index]
                if (
                    isinstance(err_raw, int | float)
                    and math.isfinite(float(err_raw))
                    and float(err_raw) >= 0.0
                ):
                    err_value = float(err_raw)
            comment_value = ""
            if isinstance(point_comment, list) and index < len(point_comment):
                comment_value = str(point_comment[index] or "").strip()
            points.append(
                (wave_value, flux_value, width_value, err_value, comment_value)
            )
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
            warning = (
                "Photometric upload includes non-positive values; using linear y-axis."
            )

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
            "meta": {
                "transform_target": "model",
                "plot_role": "final",
                "y_axis_name": "Flux",
            },
        }
        if any(value > 0.0 for value in widths):
            trace["error_x"] = {
                "type": "data",
                "array": [0.5 * value for value in widths],
                "visible": True,
                "color": OBSERVED_ERROR_BAR_COLOR,
                "thickness": OBSERVED_ERROR_BAR_THICKNESS,
                "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
            }
        if any(isinstance(value, float) and value > 0.0 for value in errors):
            trace["error_y"] = {
                "type": "data",
                "array": [
                    value if isinstance(value, float) and value > 0.0 else 0.0
                    for value in errors
                ],
                "visible": True,
                "color": OBSERVED_ERROR_BAR_COLOR,
                "thickness": OBSERVED_ERROR_BAR_THICKNESS,
                "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
            }
        return (
            {
                "data": [trace],
                "layout": _plot_layout(
                    y_label="Flux (uploaded units)", y_scale=y_scale
                ),
                "config": _plot_config(),
                "default_x_scale": "log",
                "default_y_scale": y_scale,
            },
            warning,
        )

    x, y, errors = _downsample_spectrum_with_flux_err(
        wavelength,
        flux,
        flux_err,
        max_points=MAX_SERIES_POINTS,
    )
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
        prefer_log_y = all(
            isinstance(value, int | float)
            and math.isfinite(float(value))
            and float(value) > 0
            for value in y
        )

    y_scale = "log" if prefer_log_y else "linear"
    warning = None
    if flux_mode == "absolute" and not prefer_log_y:
        warning = (
            "Absolute-flux upload includes non-positive values; using linear y-axis."
        )

    label = str(observed.get("name", "uploaded-spectrum"))
    trace = {
        "type": "scatter",
        "mode": "lines",
        "name": f"Uploaded ({label})",
        "x": x,
        "y": y,
        "line": {"color": "#212529", "width": 1.2},
        "hovertemplate": hover,
        "meta": {
            "transform_target": "model",
            "plot_role": "final",
            "y_axis_name": y_axis_name,
        },
    }
    if errors is not None and any(
        isinstance(value, float) and value > 0.0 for value in errors
    ):
        trace["error_y"] = {
            "type": "data",
            "array": [
                value if isinstance(value, float) and value > 0.0 else 0.0
                for value in errors
            ],
            "visible": True,
            "color": OBSERVED_ERROR_BAR_COLOR,
            "thickness": OBSERVED_ERROR_BAR_THICKNESS,
            "width": OBSERVED_ERROR_BAR_CAP_WIDTH,
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


def build_both_plot(
    continuum: dict[str, object], final: dict[str, object]
) -> dict[str, object] | None:
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
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    cont_x_cgs, cont_y_cgs = _jy_to_cgs_per_angstrom(cont_x, cont_y)
    fin_x_cgs, fin_y_cgs = _jy_to_cgs_per_angstrom(fin_x, fin_y)
    if len(cont_x_cgs) < 2 or len(fin_x_cgs) < 2:
        return None

    cont_x_ds, cont_y_ds = downsample_xy(
        cont_x_cgs, cont_y_cgs, max_points=MAX_SERIES_POINTS
    )
    fin_x_ds, fin_y_ds = downsample_xy(
        fin_x_cgs, fin_y_cgs, max_points=MAX_SERIES_POINTS
    )
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
                "meta": {
                    "transform_target": "model",
                    "plot_role": "final",
                    "y_axis_name": "Flux",
                },
            },
            {
                "type": "scatter",
                "mode": "lines",
                "name": "Continuum (obs_cont)",
                "x": cont_x_ds,
                "y": cont_y_ds,
                "line": {"color": "#d62728", "width": 1.3},
                "hovertemplate": "Wavelength=%{x:.6g} Å<br>Flux=%{y:.6e} erg s^-1 cm^-2 Å^-1<extra></extra>",
                "meta": {
                    "transform_target": "model",
                    "plot_role": "continuum",
                    "y_axis_name": "Flux",
                },
            },
        ],
        "layout": _plot_layout(y_label="Flux (erg s^-1 cm^-2 Å^-1)", y_scale="log"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "log",
    }


def build_normalized_plot(
    continuum: dict[str, object], final: dict[str, object]
) -> dict[str, object] | None:
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
    if len(cont_x) < 2 or len(fin_x) < 2:
        return None

    ratio_x: list[float] = []
    ratio_y: list[float] = []
    for wavelength, flux in zip(fin_x, fin_y):
        interp = _interp_linear(cont_x, cont_y, wavelength)
        if (
            interp is None
            or interp == 0
            or not math.isfinite(interp)
            or not math.isfinite(flux)
        ):
            continue
        value = flux / interp
        if not math.isfinite(value):
            continue
        ratio_x.append(wavelength)
        ratio_y.append(value)

    ratio_x_ds, ratio_y_ds = downsample_xy(
        ratio_x, ratio_y, max_points=MAX_SERIES_POINTS
    )
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
                "meta": {
                    "transform_target": "model",
                    "plot_role": "final",
                    "y_axis_name": "Normalized",
                },
            }
        ],
        "layout": _plot_layout(y_label="Normalized flux", y_scale="linear"),
        "config": _plot_config(),
        "default_x_scale": "log",
        "default_y_scale": "linear",
    }


def spectrum_data_rows(
    continuum: dict[str, object], final: dict[str, object]
) -> list[list[str]]:
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
        rows.append(
            [
                "Wavelength window (Å)",
                f"{format_number(lambda_min)} .. {format_number(lambda_max)}",
            ]
        )
    final_skipped = final.get("skipped_points")
    cont_skipped = continuum.get("skipped_points")
    if isinstance(final_skipped, int) and final_skipped > 0:
        rows.append(["Final skipped points", str(final_skipped)])
    if isinstance(cont_skipped, int) and cont_skipped > 0:
        rows.append(["Continuum skipped points", str(cont_skipped)])
    final_range_skipped = final.get("range_skipped_points")
    cont_range_skipped = continuum.get("range_skipped_points")
    if isinstance(final_range_skipped, int) and final_range_skipped > 0:
        rows.append(
            ["Final points skipped by wavelength window", str(final_range_skipped)]
        )
    if isinstance(cont_range_skipped, int) and cont_range_skipped > 0:
        rows.append(
            ["Continuum points skipped by wavelength window", str(cont_range_skipped)]
        )
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
