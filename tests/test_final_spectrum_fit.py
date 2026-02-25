from __future__ import annotations

import math

from cmfgen_viewer import final_spectrum as fs


def _build_model_vectors(size: int = 80) -> tuple[list[float], list[float], list[float]]:
    wavelength = [1000.0 + (1000.0 * idx / (size - 1)) for idx in range(size)]
    continuum = [1.0 + 0.0002 * idx for idx in range(size)]
    final = [continuum[idx] * (1.0 + 0.05 * math.sin(idx / 8.0)) for idx in range(size)]
    return wavelength, continuum, final


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
