from __future__ import annotations

import math

from cmfgen_viewer import final_spectrum as fs


def _build_model_vectors(size: int = 80) -> tuple[list[float], list[float], list[float]]:
    wavelength = [1000.0 + (1000.0 * idx / (size - 1)) for idx in range(size)]
    continuum = [1.0 + 0.0002 * idx for idx in range(size)]
    final = [continuum[idx] * (1.0 + 0.05 * math.sin(idx / 8.0)) for idx in range(size)]
    return wavelength, continuum, final


def _build_absolute_photometry_case(size: int = 8) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    wavelength = [4200.0 + (4200.0 * idx / max(1, size - 1)) for idx in range(size)]
    continuum_jy = [1.0] * size
    final_jy = [1.0 + 0.04 * math.sin(idx / 2.0) for idx in range(size)]
    observed_flux = [
        final_jy[idx] * fs.JY_TO_FLAMBDA_ANGSTROM_FACTOR / (wavelength[idx] * wavelength[idx])
        for idx in range(size)
    ]
    band_width = [120.0] * size
    continuum = {"wavelength": wavelength, "flux": continuum_jy}
    final = {"wavelength": wavelength, "flux": final_jy}
    observed = {
        "wavelength": wavelength,
        "flux": observed_flux,
        "band_width": band_width,
        "flux_mode": "absolute",
        "observation_type": "photometry",
    }
    return continuum, final, observed


def test_fit_model_to_observed_rejects_flux_mode_mismatch() -> None:
    wavelength, continuum_flux, final_flux = _build_model_vectors()
    continuum = {"wavelength": wavelength, "flux": continuum_flux}
    final = {"wavelength": wavelength, "flux": final_flux}
    observed = {
        "wavelength": wavelength,
        "flux": [final_flux[idx] / continuum_flux[idx] for idx in range(len(wavelength))],
        "flux_mode": "normalized",
        "observation_type": "spectrum",
    }

    params, metrics, error = fs.fit_model_to_observed(
        continuum,
        final,
        observed,
        mode="both",
    )
    assert params is None
    assert metrics is None
    assert error == "Observed upload is not absolute-flux data."


def test_fit_model_to_observed_can_be_canceled() -> None:
    wavelength, continuum_flux, final_flux = _build_model_vectors()
    continuum = {"wavelength": wavelength, "flux": continuum_flux}
    final = {"wavelength": wavelength, "flux": final_flux}
    observed = {
        "wavelength": wavelength,
        "flux": [final_flux[idx] / continuum_flux[idx] for idx in range(len(wavelength))],
        "flux_mode": "normalized",
        "observation_type": "spectrum",
    }

    params, metrics, error = fs.fit_model_to_observed(
        continuum,
        final,
        observed,
        mode="normalized",
        should_cancel=lambda: True,
    )
    assert params is None
    assert metrics is None
    assert error == fs.FIT_CANCELED_MESSAGE


def test_fit_model_to_observed_succeeds_for_simple_normalized_case() -> None:
    wavelength, continuum_flux, final_flux = _build_model_vectors()
    continuum = {"wavelength": wavelength, "flux": continuum_flux}
    final = {"wavelength": wavelength, "flux": final_flux}
    observed = {
        "wavelength": wavelength,
        "flux": [final_flux[idx] / continuum_flux[idx] for idx in range(len(wavelength))],
        "flux_mode": "normalized",
        "observation_type": "spectrum",
    }

    params, metrics, error = fs.fit_model_to_observed(
        continuum,
        final,
        observed,
        mode="normalized",
    )
    assert error is None
    assert isinstance(params, dict)
    assert isinstance(metrics, dict)
    assert metrics["points"] >= 30
    assert "redshift" in params
    assert "broadening_km_s" in params


def test_overlay_and_uploaded_plot_photometry_paths() -> None:
    observed = {
        "name": "obs",
        "observation_type": "photometry",
        "wavelength": [5000.0, 6000.0],
        "flux": [1.0, 2.0],
        "band_width": [100.0, 120.0],
        "flux_err": [0.1, 0.0],
        "point_comment": ["a", ""],
        "flux_mode": "absolute",
    }

    trace, error = fs.build_observed_overlay_trace(observed, mode="both")
    assert error is None
    assert isinstance(trace, dict)
    assert "error_x" in trace
    assert "error_y" in trace

    trace_bad_mode, bad_mode_error = fs.build_observed_overlay_trace(observed, mode="normalized")
    assert trace_bad_mode is None
    assert bad_mode_error is not None

    plot_data, warning = fs.build_uploaded_spectrum_plot(observed)
    assert warning is None
    assert isinstance(plot_data, dict)
    assert len(plot_data["data"]) == 1


def test_fit_model_to_observed_photometry_uses_flux_err_fallback() -> None:
    continuum, final, observed = _build_absolute_photometry_case(size=8)
    observed["flux_err"] = [None] * len(observed["wavelength"])

    params, metrics, error = fs.fit_model_to_observed(
        continuum,
        final,
        observed,
        mode="both",
    )
    assert error is None
    assert isinstance(params, dict)
    assert isinstance(metrics, dict)
    assert metrics.get("photometry_error_weighting") == "flux_err_or_2pct_fallback"
    assert metrics.get("photometry_flux_err_provided_points") == 0
    assert metrics.get("photometry_flux_err_fallback_points") == metrics.get("points")


def test_fit_model_to_observed_photometry_chi2_respects_flux_err_weights() -> None:
    continuum, final, observed_base = _build_absolute_photometry_case(size=9)
    observed_flux = [float(value) for value in observed_base["flux"]]
    pivot = len(observed_flux) // 2
    observed_flux[pivot] *= 1.12

    observed_with_fallback = dict(observed_base)
    observed_with_fallback["flux"] = observed_flux
    observed_with_fallback["flux_err"] = [None] * len(observed_flux)

    observed_with_tight_err = dict(observed_base)
    observed_with_tight_err["flux"] = observed_flux
    observed_with_tight_err["flux_err"] = [0.001 * abs(value) for value in observed_flux]

    params_fallback, metrics_fallback, error_fallback = fs.fit_model_to_observed(
        continuum,
        final,
        observed_with_fallback,
        mode="both",
    )
    params_tight, metrics_tight, error_tight = fs.fit_model_to_observed(
        continuum,
        final,
        observed_with_tight_err,
        mode="both",
    )

    assert error_fallback is None
    assert error_tight is None
    assert isinstance(params_fallback, dict)
    assert isinstance(params_tight, dict)
    assert isinstance(metrics_fallback, dict)
    assert isinstance(metrics_tight, dict)

    chi2_fallback = float(metrics_fallback["chi2"])
    chi2_tight = float(metrics_tight["chi2"])
    assert chi2_tight > chi2_fallback * 10.0
    assert metrics_tight.get("photometry_flux_err_provided_points") == metrics_tight.get("points")


def test_fit_model_to_observed_can_profile_free_absolute_normalization() -> None:
    continuum, final, observed = _build_absolute_photometry_case(size=9)
    observed["flux"] = [0.2 * float(value) for value in observed["flux"]]

    params, metrics, error = fs.fit_model_to_observed(
        continuum,
        final,
        observed,
        mode="both",
        absolute_scale_mode="free",
    )

    assert error is None
    assert isinstance(params, dict)
    assert isinstance(metrics, dict)
    assert params["distance_kpc"] == 1.0
    assert abs(float(params["normalization"]) - 0.2) < 5e-3
    assert metrics.get("absolute_scale_mode") == "free_normalization"
    assert metrics.get("fit_param_count") == 4
