"""Numerical equivalence and regression checks for optimized fitting paths."""

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter1d

from cmfgen_viewer import spectrum_transforms as transforms
from cmfgen_viewer.spectrum_fitting import fit_model_to_observed, _sample_model_on_observed_grid


@pytest.mark.parametrize("sigma", [0.4, 16, 17, 100, 267])
@pytest.mark.parametrize("signed", [False, True])
def test_fft_matches_direct_kernel_and_nearest_edges(sigma, signed):
    flux = np.random.default_rng(19).uniform(0.1, 2, 5000)
    flux[:10], flux[-10:] = 10, 0.001
    if signed:
        flux -= 1
    expected = gaussian_filter1d(flux, sigma, mode="nearest", truncate=4)
    actual = transforms._smooth_gaussian(flux, sigma)
    np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=2e-14)


@pytest.mark.parametrize("uniform", [False, True])
@pytest.mark.parametrize("mode", ["both", "normalized"])
def test_prepared_transform_matches_public_transform(uniform, mode):
    wave = np.geomspace(900, 25000, 30000) if uniform else np.linspace(900, 25000, 30000)
    flux = (5000 / wave) ** 3 * (1 + 0.2 * np.sin(wave / 13))
    prepared = transforms.PreparedSpectrumTransform(wave, flux, mode)
    for sigma, ebv, shift in [(0, 0, 0), (100, 0.2, -0.01), (800, 1.5, 0.02)]:
        args = dict(redshift=shift, broadening_km_s=sigma, ebv=ebv, distance_kpc=2, normalization=3)
        expected = transforms._apply_transform_arrays(wave, flux, mode=mode, **args)
        actual = prepared(**args)
        np.testing.assert_array_equal(actual[0], expected[0])
        np.testing.assert_allclose(actual[1], expected[1], rtol=2e-10, atol=1e-14)


def test_reddening_basis_cache_is_bounded_and_reused(monkeypatch):
    wave = np.geomspace(3000, 25000, 10000)
    original = transforms._reddening_exponent
    calls = []

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(transforms, "_reddening_exponent", tracked)
    prepared = transforms.PreparedSpectrumTransform(wave, np.ones_like(wave), "both")
    for ebv in (0, 0.1, 0.2, 1):
        prepared(redshift=0, broadening_km_s=0, ebv=ebv, distance_kpc=1)
    assert len(calls) == 1
    for z in np.linspace(0.001, 0.01, 8):
        prepared(redshift=z, broadening_km_s=0, ebv=0.1, distance_kpc=1)
    assert len(prepared.shift_cache) == 4


@pytest.mark.parametrize("mode", ["both", "normalized"])
@pytest.mark.parametrize("shift", [-0.02, 0, 0.02])
def test_sparse_unbroadened_sampling_preserves_interpolation_and_coverage(mode, shift):
    wave = np.geomspace(3000, 25000, 212027)
    flux = (5000 / wave) ** 3 * (1 + 0.4 * np.sin(wave / 3))
    observed = np.concatenate(([2800], np.linspace(3360, 10200, 343), [25000, 27000]))
    prepared = transforms.PreparedSpectrumTransform(wave, flux, mode)
    args = dict(redshift=shift, ebv=1.5, distance_kpc=2, normalization=1.3)
    full = transforms._apply_transform_arrays(wave, flux, mode=mode, broadening_km_s=0, **args)
    expected = np.interp(observed, *full, left=np.nan, right=np.nan)
    actual = prepared.sample_unbroadened(observed, **args)
    np.testing.assert_allclose(actual, expected, rtol=1e-13, atol=0, equal_nan=True)
    assert prepared.is_unbroadened(0)
    assert prepared.is_unbroadened(0.1)
    assert not prepared.is_unbroadened(20)
    assert not prepared.is_unbroadened(-1)


@pytest.mark.parametrize("photometry", [False, True])
@pytest.mark.parametrize("shift", [-0.02, 0, 0.02])
def test_cropping_preserves_observations_at_extreme_bounds(photometry, shift):
    wave = np.geomspace(3000, 25000, 60000)
    flux = (5000 / wave) ** 3 * (1 + 0.4 * np.sin(wave / 3))
    observed = np.linspace(3360, 10200, 343)
    widths = np.linspace(100, 500, 343) if photometry else None
    bounds = {"redshift": (-0.02, 0.02), "broadening_km_s": (0, 800)}
    x, y = transforms._crop_model_for_fit(wave, flux, observed, widths, bounds)
    assert len(x) < 0.65 * len(wave)
    assert np.all(np.isin(x, wave))  # No new samples or downsampling.
    args = dict(redshift=shift, broadening_km_s=800, ebv=0.3, distance_kpc=1)
    full = transforms.PreparedSpectrumTransform(wave, flux, "both")(**args)
    cropped = transforms.PreparedSpectrumTransform(x, y, "both")(**args)
    expected = _sample_model_on_observed_grid(*full, observed, widths)
    actual = _sample_model_on_observed_grid(*cropped, observed, widths)
    np.testing.assert_allclose(actual, expected, rtol=2e-11, atol=1e-14)


def test_crop_keeps_nonuniform_grids_and_true_model_edges():
    wave = np.linspace(4000, 6000, 1000)
    flux = np.ones_like(wave)
    x, y = transforms._crop_model_for_fit(wave, flux, np.array([4500, 5000]), None, {})
    assert x is wave and y is flux
    wave = np.geomspace(4000, 6000, 1000)
    x, _ = transforms._crop_model_for_fit(wave, flux, np.array([3000, 7000]), None, {})
    np.testing.assert_array_equal(x, wave)


@pytest.mark.parametrize("sigma", [0, 200])
def test_absolute_broadening_can_leave_zero_initial_guess(sigma):
    wave = np.geomspace(4000, 6000, 30000)
    flux = 1e6 * (1 - 0.6 * np.exp(-0.5 * ((wave - 5000) / 1.5) ** 2))
    transformed = transforms._apply_transform_arrays(
        wave, flux, mode="both", redshift=0, broadening_km_s=sigma, ebv=0, distance_kpc=1,
    )
    observed_x = np.linspace(4800, 5200, 401)
    observed = {"wavelength": observed_x.tolist(),
                "flux": (np.interp(observed_x, *transformed) * 2e-20).tolist(), "flux_mode": "absolute"}
    params, metrics, error = fit_model_to_observed(
        {}, {}, observed, mode="both", prepared_model=(wave, flux), absolute_scale_mode="free",
        initial_params={"broadening_km_s": 0},
        bounds_override={"redshift": (0, 0), "ebv": (0, 0), "broadening_km_s": (0, 800)},
    )
    assert error is None
    assert params["normalization"] == pytest.approx(2e-20, rel=1e-5, abs=0)
    assert params["broadening_km_s"] == pytest.approx(sigma, rel=0.01, abs=1)
    assert metrics["points"] == len(observed_x)


@pytest.mark.parametrize("sigma", [0, 800])
def test_optimized_absolute_fit_recovers_reddening_and_normalization(sigma):
    wave = np.geomspace(3000, 25000, 60000)
    flux = 1e6 * (5000 / wave) ** 3 * (1 + 0.2 * np.sin(wave / 13))
    full = transforms._apply_transform_arrays(
        wave, flux, mode="both", redshift=0.01, broadening_km_s=sigma, ebv=0.2, distance_kpc=1,
    )
    observed_x = np.linspace(3400, 10000, 343)
    observed = {"wavelength": observed_x.tolist(), "flux_mode": "absolute",
                "flux": (np.interp(observed_x, *full) * 2e-20).tolist()}
    params, _, error = fit_model_to_observed(
        {}, {}, observed, mode="both", prepared_model=(wave, flux), absolute_scale_mode="free",
        bounds_override={"redshift": (0.01, 0.01), "ebv": (0, 3), "broadening_km_s": (sigma, sigma)},
    )
    assert error is None
    assert params["ebv"] == pytest.approx(0.2, abs=1e-6)
    assert params["normalization"] == pytest.approx(2e-20, rel=1e-6, abs=0)
