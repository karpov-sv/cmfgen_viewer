"""Accuracy checks against native integration, including line-rich spectra."""

import numpy as np
import pytest

from cmfgen_viewer.photometry_sampling import PreparedPhotometrySampler
from cmfgen_viewer import grid_fitting, spectrum_fitting
from cmfgen_viewer.spectrum_fitting import _sample_model_on_observed_grid
from cmfgen_viewer.spectrum_transforms import PreparedSpectrumTransform
from cmfgen_viewer import spectrum_transforms


@pytest.mark.parametrize("redshift", [-0.02, 0.0, 0.02])
@pytest.mark.parametrize("ebv", [0.0, 0.17, 1.37, 3.0])
def test_compact_bands_preserve_native_flux_with_lines_and_extinction(redshift, ebv):
    x = np.geomspace(900, 260000, 60000)
    y = (x / 5000) ** -2
    # Narrow features must contribute their area even when between coarse nodes.
    y *= 1 + 8 * np.exp(-0.5 * ((x - 4803) / 0.8) ** 2)
    y *= 1 - 0.8 * np.exp(-0.5 * ((x - 6469) / 2) ** 2)
    centers = np.array([1500, 4800, 6500, 12500, 115000, 220000, 6000])
    widths = np.array([300, 1200, 1300, 3000, 55000, 41000, 0])
    transform = PreparedSpectrumTransform(x, y, "both")
    sampler = PreparedPhotometrySampler(x, y, centers, widths)

    actual = sampler.sample(transform, redshift=redshift, ebv=ebv, distance_kpc=2)
    transformed = transform(redshift=redshift, broadening_km_s=0, ebv=ebv, distance_kpc=2)
    expected = _sample_model_on_observed_grid(*transformed, centers, widths)

    np.testing.assert_allclose(actual, expected, rtol=1.1e-4, atol=0)
    if redshift == 0 and ebv == 0:
        np.testing.assert_allclose(actual, expected, rtol=1e-13)
        assert sampler.cache[redshift][0].size < 3000


def test_signed_flux_uses_native_weights_and_missing_band_returns_nan():
    x = np.linspace(1000, 10000, 10000)
    y = np.sin(x / 20)
    centers = np.array([5000, 20000])
    widths = np.array([1000, 100])
    transform = PreparedSpectrumTransform(x, y, "both")
    sampler = PreparedPhotometrySampler(x, y, centers, widths)

    actual = sampler.sample(transform, redshift=0, ebv=1.3, distance_kpc=1)
    expected = _sample_model_on_observed_grid(
        *transform(redshift=0, broadening_km_s=0, ebv=1.3, distance_kpc=1), centers, widths,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, equal_nan=True)


def test_sampler_preserves_partial_band_edge_interpolation_and_cache_bound():
    x = np.array([1000., 2000., 4000.])
    y = np.array([1., 8., 2.])
    centers = np.array([1000., 4000.])
    widths = np.array([1000., 1000.])
    sampler = PreparedPhotometrySampler(x, y, centers, widths)
    transform = PreparedSpectrumTransform(x, y, "both")
    for redshift in np.linspace(-0.02, 0.02, 8):
        actual = sampler.sample(transform, redshift=redshift, ebv=2.1, distance_kpc=1)
        expected = _sample_model_on_observed_grid(
            *transform(redshift=redshift, broadening_km_s=0, ebv=2.1, distance_kpc=1), centers, widths,
        )
        np.testing.assert_allclose(actual, expected, rtol=1e-13)
    assert len(sampler.cache) == 4


@pytest.mark.parametrize("redshift,ebv,distance", [(-1, 0, 1), (0, np.nan, 1), (0, 0, 0)])
def test_sampler_rejects_invalid_transform_parameters(redshift, ebv, distance):
    x = np.array([1000., 2000., 4000.])
    y = np.ones_like(x)
    sampler = PreparedPhotometrySampler(x, y, np.array([2000.]), np.array([100.]))
    transform = PreparedSpectrumTransform(x, y, "both")
    assert sampler.sample(transform, redshift=redshift, ebv=ebv, distance_kpc=distance) is None


def test_absolute_model_preparation_needs_no_continuum_and_preserves_conversion():
    x = [6000., 4000., -1., 5000., np.nan, 4000.]
    y = [1., 3., 1., 2., 1., 99.]
    clean_x, clean_y = spectrum_transforms._clean_xy_arrays(x, y)
    expected = spectrum_transforms._jy_to_cgs_per_angstrom(clean_x.tolist(), clean_y.tolist())
    actual = spectrum_transforms._build_model_series_for_fit(
        {}, {"wavelength": x, "flux": y}, mode="both",
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_allclose(actual[1], expected[1], rtol=1e-15)
    assert spectrum_transforms._build_model_series_for_fit(
        {}, {"wavelength": x, "flux": y}, mode="normalized",
    ) is None


def test_compact_bands_respect_custom_extinction_bounds():
    x = np.geomspace(1000, 10000, 20000)
    y = (x / 5000) ** -3
    centers = np.array([1600., 3200., 7000.])
    widths = centers * 0.2
    transform = PreparedSpectrumTransform(x, y, "both")
    sampler = PreparedPhotometrySampler(x, y, centers, widths, ebv_bounds=(-2, 8))
    for ebv in (-2, 5.3, 8):
        actual = sampler.sample(transform, redshift=0, ebv=ebv, distance_kpc=1)
        expected = _sample_model_on_observed_grid(
            *transform(redshift=0, broadening_km_s=0, ebv=ebv, distance_kpc=1), centers, widths,
        )
        np.testing.assert_allclose(actual, expected, rtol=1.1e-4, atol=0)


def test_photometry_fit_recovers_extinction_distance_and_reports_native_score(monkeypatch):
    x = np.geomspace(3000, 250000, 60000)
    y = 1e-10 * (x / 5000) ** -2 * (1 + 0.2 * np.sin(x / 13))
    centers = np.geomspace(4000, 220000, 16)
    widths = centers * 0.2
    transform = PreparedSpectrumTransform(x, y, "both")
    obs_flux = _sample_model_on_observed_grid(
        *transform(redshift=0, broadening_km_s=0, ebv=1.2, distance_kpc=2), centers, widths,
    )
    sigma = obs_flux * 0.02
    observed = {
        "wavelength": centers.tolist(), "flux": obs_flux.tolist(),
        "band_width": widths.tolist(), "flux_err": sigma.tolist(),
        "observation_type": "photometry", "flux_mode": "absolute",
    }
    calls = []
    original = spectrum_fitting.least_squares

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(spectrum_fitting, "least_squares", tracked)
    params, metrics, error = spectrum_fitting.fit_model_to_observed(
        {}, {}, observed, mode="both", prepared_model=(x, y),
        bounds_override={"redshift": (0, 0), "broadening_km_s": (0, 0)},
    )
    assert error is None
    assert params["ebv"] == pytest.approx(1.2, abs=1e-4)
    assert params["distance_kpc"] == pytest.approx(2, rel=1e-4)
    assert len(calls) == 1  # No redundant extinction/distance pre-fit.
    assert "stage1_nfev" not in metrics
    native = _sample_model_on_observed_grid(
        *transform(redshift=params["redshift"], broadening_km_s=params["broadening_km_s"],
                   ebv=params["ebv"], distance_kpc=params["distance_kpc"]), centers, widths,
    )
    residual = (native - obs_flux) / sigma
    assert metrics["rmse"] == pytest.approx(np.sqrt(np.mean(residual ** 2)), rel=1e-9, abs=1e-11)
    assert metrics["chi2"] == pytest.approx(np.sum(residual ** 2), rel=1e-9, abs=1e-11)


def test_broadened_residuals_use_native_spectrum(monkeypatch):
    x = np.geomspace(3000, 10000, 10000)
    y = 1 + 10 * np.exp(-0.5 * ((x - 5000) / 2) ** 2)
    centers = np.array([4500., 5000., 6500.])
    widths = np.array([100., 100., 100.])
    transform = PreparedSpectrumTransform(x, y, "both")
    expected = _sample_model_on_observed_grid(
        *transform(redshift=0.01, broadening_km_s=400, ebv=0.5, distance_kpc=2), centers, widths,
    )
    residuals = spectrum_fitting.FitResiduals(
        model_x=x, model_y=y, observed_x=centers, observed_y=expected,
        observed_band_width=widths, residual_sigma=np.ones(3), normalized_mode="both",
        min_valid_points=3, use_free_normalization=False, obs_scale=1, norm_weights=np.ones(3),
    )

    def unexpected(*args, **kwargs):
        raise AssertionError("Broadened spectra must not use compact unbroadened quadrature")

    monkeypatch.setattr(residuals.photometry_sampler, "sample", unexpected)
    actual = residuals(redshift=0.01, broadening_km_s=400, ebv=0.5, distance_kpc=2)
    np.testing.assert_allclose(actual, 0, atol=1e-14)


@pytest.mark.parametrize("mode,expected_loads", [("both", ["final"]), ("normalized", ["continuum", "final"])])
def test_cmfgen_grid_loads_continuum_only_for_normalized_fits(monkeypatch, tmp_path, mode, expected_loads):
    monkeypatch.setattr(grid_fitting, "discover_final_spectrum_files", lambda path: {
        "obs_cont": tmp_path / "continuum", "fin_files": [tmp_path / "final"],
    })
    loaded = []

    def load(path, **kwargs):
        assert kwargs["as_arrays"] is True
        loaded.append(path.name)
        return {"wavelength": [1000, 2000], "flux": [1, 2]}

    monkeypatch.setattr(grid_fitting, "load_obs_spectrum", load)
    monkeypatch.setattr(grid_fitting, "fit_model_to_observed", lambda *args, **kwargs: (
        {"redshift": 0, "broadening_km_s": 0, "ebv": 0, "distance_kpc": 1},
        {"rmse": 0, "points": 2}, None,
    ))
    grid_fitting._fit_single_cmfgen_candidate(
        candidate={"model_name": "test", "model_relpath": "test", "model_path_str": str(tmp_path)},
        observed={}, mode=mode, fit_bounds={}, lambda_min=800, lambda_max=250000,
    )
    assert loaded == expected_loads
