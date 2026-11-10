import gzip
import io
import json
import tarfile

import numpy as np
import pytest

from cmfgen_viewer import grid_fitting
from cmfgen_viewer.grid_catalog import _discover_tlusty_grid_models
from scripts import download_tlusty_spectra as converter
from scripts.compact_tlusty_spectra import compact_spectrum
from scripts.investigate_tlusty_sed_rebinning import conservative_bins, ranking_diagnostics


@pytest.mark.parametrize("slope", [0, 1])
def test_conservative_bins_preserve_native_linear_flux_and_full_coverage(slope):
    x = np.geomspace(50, 3e6, 10001)
    y = 2 + slope * x
    wave, flux, mass = conservative_bins(x, y, 300)
    assert wave[0] == x[0] and wave[-1] == x[-1]
    assert np.all(np.diff(wave) > 0)
    assert np.all(np.isfinite(flux))
    assert mass.sum() == pytest.approx(np.trapezoid(y, x), rel=1e-14)


def test_rebinning_preserves_narrow_line_area_between_output_centers():
    x = np.linspace(4000, 6000, 100001)
    y = 1 + 8 * np.exp(-0.5 * ((x - 4803) / .4)**2)
    _, _, mass = conservative_bins(x, y, 300)
    assert mass.sum() == pytest.approx(np.trapezoid(y, x), rel=1e-14)


def test_local_integrals_preserve_faint_infrared_tail():
    x = np.geomspace(50, 3e6, 200001)
    y = (x / 5000)**-4
    wave, flux, _ = conservative_bins(x, y, 1000)
    # A global cumulative integral loses tiny IR-bin areas to subtraction.
    # Local summation should agree with the analytic power-law integral.
    count = len(wave) - 2
    edges = np.geomspace(x[0], x[-1], count + 1)
    analytic_tail_mean = 5000**4 / 3 * (edges[-2]**-3 - edges[-1]**-3) / (edges[-1] - edges[-2])
    assert flux[-2] == pytest.approx(analytic_tail_mean, rel=1e-7)


def test_ranking_check_accounts_for_free_normalization():
    records = [dict(broadband_flux=[1., 2., 3.], methods={"scaled": dict(broadband_flux=[2., 4., 6.])}),
               dict(broadband_flux=[3., 2., 1.], methods={"scaled": dict(broadband_flux=[9., 6., 3.])})]
    results = ranking_diagnostics(records, ["scaled"])["methods"]["scaled"]
    assert results["noiseless"]["changed_best_model"] == 0
    assert results["one_percent_noise"]["changed_best_model"] == 0


@pytest.fixture
def sed_archive(tmp_path):
    raw = tmp_path / "raw" / "bstar"
    raw.mkdir(parents=True)
    archive = raw / "BGflux_v2.tar"
    with tarfile.open(archive, "w") as handle:
        for teff, count in ((25000, 40001), (30000, 201)):
            wave = np.geomspace(80, 3e6, count)
            flux = (wave / 5000)**-3
            flux *= 1 - .8 * np.exp(-.5 * ((wave - 1500) / 1)**2)
            frequency = converter.LIGHT_SPEED_ANGSTROM_PER_SECOND / wave
            hnu = flux * wave**2 / converter.LIGHT_SPEED_ANGSTROM_PER_SECOND
            payload = "\n".join(f"{x:.17g} {y:.17g}" for x, y in zip(frequency, hnu)).encode()
            data = gzip.compress(payload)
            member = tarfile.TarInfo(f"BG{teff}g400v2.flux.gz")
            member.size = len(data)
            handle.addfile(member, io.BytesIO(data))
    return archive


def extract_seds(tmp_path, archive, power=None):
    return converter._extract_archive(
        archive, grid="bstar", archive_url=archive.as_uri(), archive_products=["flux"],
        output_dir=tmp_path, force_process=False, dry_run=False, sed_binning_power=power,
    )


def test_sed_settings_rebuild_from_raw_reuse_sparse_models_and_restore_native(tmp_path, sed_archive):
    original_archive = sed_archive.read_bytes()
    _, native_rows = extract_seds(tmp_path, sed_archive)
    native = {}
    for row in native_rows:
        with np.load(tmp_path / row["spectrum_relpath"]) as source:
            native[row["model_name"]] = {key: source[key] for key in source.files}
    stats, rows = extract_seds(tmp_path, sed_archive, 3000)
    assert stats.spectra_saved == 2
    dense = next(r for r in rows if "25000" in r["model_name"])
    sparse = next(r for r in rows if "30000" in r["model_name"])
    assert 20000 < dense["points"] < 40001
    assert dense["sed_rebin_applied"]
    assert not sparse["sed_rebin_applied"] and sparse["points"] == 201
    for row in rows:
        assert row["sed_binning_power"] == 3000
        assert row["sed_binning_method"] == converter.SED_BINNING_METHOD
        cached = converter._existing_npz_spectrum_metadata(tmp_path / row["spectrum_relpath"])
        assert cached["sed_binning_power"] == 3000
        assert cached["sed_rebin_applied"] == row["sed_rebin_applied"]
    with np.load(tmp_path / sparse["spectrum_relpath"]) as source:
        np.testing.assert_array_equal(source["flux_lambda_cgs"], native[sparse["model_name"]]["flux_lambda_cgs"])
    assert extract_seds(tmp_path, sed_archive, 3000)[0].spectra_saved == 0
    # Higher binning power must reconstruct from raw, not from the coarser cache.
    _, rebuilt = extract_seds(tmp_path, sed_archive, 4000)
    dense = next(r for r in rebuilt if "25000" in r["model_name"])
    assert not dense["sed_rebin_applied"]  # Native sampling is already sparser.
    with np.load(tmp_path / dense["spectrum_relpath"]) as source:
        np.testing.assert_array_equal(source["flux_lambda_cgs"], native[dense["model_name"]]["flux_lambda_cgs"])
    assert extract_seds(tmp_path, sed_archive, 1000)[0].spectra_saved == 2
    assert extract_seds(tmp_path, sed_archive)[0].spectra_saved == 2
    for row in native_rows:
        with np.load(tmp_path / row["spectrum_relpath"]) as source:
            assert "sed_binning_power" not in source
            np.testing.assert_array_equal(source["flux_lambda_cgs"], native[row["model_name"]]["flux_lambda_cgs"])
    assert sed_archive.read_bytes() == original_archive


def test_cli_sed_metadata_discovery_and_compaction(tmp_path, sed_archive):
    assert converter.main(["--local-only", "--grid", "bstar", "--output-dir", str(tmp_path),
                           "--resolving-power", "50000", "--sed-binning-power", "3000"]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["conversion"]["sed_binning_power"] == 3000
    row = next(r for r in manifest["models"] if r["sed_rebin_applied"])
    path = tmp_path / row["spectrum_relpath"]
    # Exercise compaction of a binned file that also contains a redundant array.
    with np.load(path) as source:
        arrays = {key: source[key] for key in source.files}
    arrays["y_col_1"] = arrays["flux_lambda_cgs"]
    np.savez_compressed(path, **arrays)
    compact_spectrum(tmp_path, row)
    with np.load(path) as source:
        assert float(source["sed_binning_power"]) == 3000
        assert str(source["sed_binning_method"]) == converter.SED_BINNING_METHOD
        assert bool(source["sed_rebin_applied"])
        assert "y_col_1" not in source
    config = {"tlusty_root": str(tmp_path)}
    photometry = dict(observation_type="photometry", wavelength=[5000., 15000.], band_width=[1000., 2000.])
    candidates, error = _discover_tlusty_grid_models(config, mode="both", model_name_pattern="*25000*", observed=photometry)
    assert error is None and len(candidates) == 1
    assert candidates[0]["grid_metadata"]["sed_binning_power"] == 3000
    assert candidates[0]["grid_metadata"]["sed_rebin_applied"]
    for observed in (None, {"observation_type": "spectrum"}):
        candidates, _ = _discover_tlusty_grid_models(config, mode="both", model_name_pattern="*25000*", observed=observed)
        assert not candidates
    # Sparse native SEDs remain available for ordinary spectral fitting.
    candidates, error = _discover_tlusty_grid_models(config, mode="both", model_name_pattern="*30000*", observed={"observation_type": "spectrum"})
    assert error is None and len(candidates) == 1


@pytest.mark.parametrize("photometry, binning, expected_points", [(True, None, 30001), (False, None, 20000), (True, 3000, 30001)])
def test_photometric_fitter_receives_all_native_or_binned_samples(tmp_path, monkeypatch, photometry, binning, expected_points):
    path = tmp_path / "spectrum.npz"
    np.savez_compressed(path, wavelength_angstrom=np.geomspace(100, 3e6, 30001), flux_lambda_cgs=np.ones(30001))
    candidate = dict(model_name="test", model_path="tlusty/test", spectrum_path_str=str(path),
                     grid_metadata={"sed_binning_power": binning})
    def check_fit(*args, **kwargs):
        assert len(kwargs["prepared_model"][0]) == expected_points
        raise RuntimeError("photometry sampling checked")
    monkeypatch.setattr(grid_fitting, "fit_model_to_observed", check_fit)
    with pytest.raises(RuntimeError, match="photometry sampling checked"):
        grid_fitting._fit_single_tlusty_candidate(candidate=candidate, observed={"observation_type": "photometry" if photometry else "spectrum"}, mode="both", fit_bounds={})


@pytest.mark.parametrize("power", ["0", "-1", "nan", "inf"])
def test_invalid_sed_binning_option(power):
    with pytest.raises(SystemExit):
        converter.parse_args(["--sed-binning-power", power])
