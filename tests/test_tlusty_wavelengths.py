"""Imported SYNSPEC air coordinates must not be converted to air twice."""

import numpy as np
import pytest

from cmfgen_viewer.grid_fitting import _build_tlusty_model_series
from cmfgen_viewer.grid_catalog import _tlusty_row_covers_observed_photometry
from cmfgen_viewer.grid_storage import write_compact_spectrum
from cmfgen_viewer.spectrum_fitting import fit_model_to_observed
from cmfgen_viewer.spectrum_transforms import _apply_transform_arrays
from cmfgen_viewer.wavelengths import air_to_vacuum, vacuum_to_air


@pytest.mark.parametrize("metadata,air", [
    ({"x_axis_kind": "wavelength_input"}, True),  # Legacy TLUSTY cache.
    ({"x_axis_kind": "frequency_hz"}, False),
    ({"x_axis_kind": "wavelength_input", "wavelength_medium": "vacuum"}, False),
    ({"wavelength_medium": "air"}, True),
    ({}, False),  # Other NPZ grids retain their vacuum coordinates.
])
def test_imported_model_axis_and_flux_convention(tmp_path, metadata, air):
    wave = np.linspace(4800, 5000, 5001)
    flux = 2 - np.exp(-((wave - 4861.33) / 1.2)**2)
    path = tmp_path / "spectrum.npz"
    np.savez(path, wavelength_angstrom=wave, flux_lambda_cgs=flux,
             normalized_flux_candidate=flux / 2, **metadata)
    x, y, error = _build_tlusty_model_series(mode="normalized", spectrum_path=path, continuum_path=None)
    assert error is None
    np.testing.assert_allclose(x, air_to_vacuum(wave) if air else wave, atol=1e-10)
    np.testing.assert_array_equal(y, flux / 2)
    vx, vy, error = _build_tlusty_model_series(mode="both", spectrum_path=path, continuum_path=None)
    assert error is None
    # Loading must leave the stored cache unchanged; Air roundtrips preserve F_lambda.
    if air:
        np.testing.assert_allclose(vacuum_to_air(vx), wave, atol=1e-9)
        np.testing.assert_allclose(np.asarray(vy) * vacuum_to_air(vx, flux_jacobian=True), flux)
    else:
        np.testing.assert_array_equal(vy, flux)
    with np.load(path) as saved:
        np.testing.assert_array_equal(saved["wavelength_angstrom"], wave)


@pytest.mark.parametrize("bosz", [False, True])
def test_synspec_air_fit_recovers_velocity_and_aligns_reference(tmp_path, bosz):
    air_wave = np.linspace(4828, 5076, 16001)
    rest = 4921.931
    profile = 1 - .5 * np.exp(-((air_wave - rest) / .6)**2)
    path = tmp_path / ("bosz2024_ap_t10000_r2000_resam.npz" if bosz else "BT18000.vis.7.npz")
    metadata = {} if bosz else {"x_axis_kind": "wavelength_input"}
    np.savez(path, wavelength_angstrom=air_wave, flux_lambda_cgs=profile,
             normalized_flux_candidate=profile, **metadata)
    mx, my, error = _build_tlusty_model_series(mode="normalized", spectrum_path=path, continuum_path=None, as_arrays=True)
    assert error is None
    true_z = -40 / 299792.458
    # Construct the observation from the known physical vacuum rest axis,
    # independently of the importer under test.
    ox, oy = _apply_transform_arrays(air_to_vacuum(air_wave), profile, mode="normalized",
        redshift=true_z, broadening_km_s=20, ebv=0, distance_kpc=1, wavelength_medium="air")
    observed = {"wavelength": ox.tolist(), "flux": oy.tolist(), "wavelength_medium": "air",
                "flux_mode": "normalized"}
    result, _, error = fit_model_to_observed({}, {}, observed, mode="normalized",
        prepared_model=(mx, my),
        bounds_override={"redshift": (-.0003, 0), "broadening_km_s": (20, 20)},
        initial_params={"redshift": -.00012})
    assert error is None
    z = result["redshift"]
    assert z == pytest.approx(true_z, abs=2e-7)
    marker = float(vacuum_to_air(air_to_vacuum(rest) * (1 + z)))
    assert marker == pytest.approx(ox[np.argmin(oy)], abs=.02)


@pytest.mark.parametrize("metadata", [{"x_axis_kind": "wavelength_input"}, {"model_name": "bosz2024_ap_t10000"}])
def test_photometry_coverage_uses_canonical_model_bounds(metadata):
    row = {"wavelength_min_angstrom": 4800., "wavelength_max_angstrom": 5000.,
           **metadata}
    observed = {"observation_type": "photometry", "wavelength_medium": "vacuum",
                "wavelength": [float(air_to_vacuum(4999.5))], "band_width": [0.]}
    assert _tlusty_row_covers_observed_photometry(row, observed)
    assert not _tlusty_row_covers_observed_photometry({**row, "wavelength_medium": "vacuum"}, observed)


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("name,grid,air", [
    ("bosz2024_ap_t10000_r2000_resam", "bosz", True),
    ("bosz2017_legacy", "bosz", False),
    ("lte10000-4.00.PHOENIX-ACES-AGSS-COND-2011", "phoenix", False),
])
def test_existing_cache_release_conventions(tmp_path, compact, name, grid, air):
    wave = np.linspace(4800, 5000, 101)
    flux = np.linspace(1, 2, 101)
    arrays = {"wavelength_angstrom": wave, "flux_lambda_cgs": flux}
    if grid == "bosz":
        arrays.update(continuum_lambda_cgs=flux * 2, normalized_flux_candidate=np.full(101, .5))
    path = tmp_path / (name + ".npz")
    if compact:
        write_compact_spectrum(path, arrays, grid)
    else:
        np.savez(path, **arrays)
    original = path.read_bytes()
    x, y, error = _build_tlusty_model_series(mode="both", spectrum_path=path, continuum_path=None)
    assert error is None
    np.testing.assert_allclose(x, air_to_vacuum(wave) if air else wave)
    np.testing.assert_allclose(y, flux / vacuum_to_air(x, flux_jacobian=True) if air else flux)
    assert path.read_bytes() == original
