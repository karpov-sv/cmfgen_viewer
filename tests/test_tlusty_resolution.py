import gzip
import io
import json
import tarfile

import numpy as np
import pytest
from scipy.integrate import trapezoid

from cmfgen_viewer import grid_fitting
from cmfgen_viewer.grid_catalog import _discover_tlusty_grid_models
from scripts import download_tlusty_spectra as converter
from scripts.compact_tlusty_spectra import compact_spectrum


def test_resolution_preserves_line_area_and_adds_expected_gaussian_width():
    wave = np.linspace(4980, 5020, 100001)
    intrinsic_sigma = 0.04
    absorption = 0.5 * np.exp(-0.5 * ((wave - 5000) / intrinsic_sigma)**2)
    parsed = {"arrays": {"wavelength_angstrom": wave, "flux_lambda_cgs": 1 - absorption,
                         "continuum_lambda_cgs": np.ones_like(wave),
                         "normalized_flux_candidate": 1 - absorption}}
    result = converter._reduce_resolution(parsed, resolving_power=10000, samples_per_resolution=3)
    arrays = result["arrays"]
    new_wave = arrays["wavelength_angstrom"]
    new_absorption = 1 - arrays["flux_lambda_cgs"]
    area = trapezoid(new_absorption, new_wave)
    assert area == pytest.approx(trapezoid(absorption, wave), rel=0.001)
    center = trapezoid(new_absorption * new_wave, new_wave) / area
    variance = trapezoid(new_absorption * (new_wave - center)**2, new_wave) / area
    expected_sigma = np.sqrt(intrinsic_sigma**2 + (5000 / 10000 / np.sqrt(8 * np.log(2)))**2)
    assert center == pytest.approx(5000, abs=0.001)
    assert np.sqrt(variance) == pytest.approx(expected_sigma, rel=0.001)
    np.testing.assert_allclose(arrays["continuum_lambda_cgs"], 1, atol=1e-14)
    np.testing.assert_array_equal(arrays["normalized_flux_candidate"], arrays["flux_lambda_cgs"])
    assert new_wave[0] == wave[0] and new_wave[-1] == wave[-1]
    assert np.max(np.diff(np.log(new_wave))) <= (1 / 30000) * (1 + 1e-8)


def make_archive(root):
    raw = root / "raw" / "ostar"
    raw.mkdir(parents=True)
    path = raw / "Guvspec.tar"
    wave = np.linspace(1400, 1600, 4001)
    flux = 2 - np.exp(-0.5 * ((wave - 1500) / 0.1)**2)
    payloads = {}
    for suffix, values in ((".uv.7", flux), (".uv.17", np.full_like(wave, 2)), (".flux", flux)):
        name = "G35000g400v10" + suffix + ".gz"
        payloads[name] = "\n".join(f"{x:.17g} {y:.17g}" for x, y in zip(wave, values)).encode()
    with tarfile.open(path, "w") as archive:
        for name, payload in payloads.items():
            compressed = gzip.compress(payload)
            info = tarfile.TarInfo(name)
            info.size = len(compressed)
            archive.addfile(info, io.BytesIO(compressed))
    return path, payloads


def extract(root, archive, resolving_power=None, samples=3):
    return converter._extract_archive(
        archive, grid="ostar", archive_url=archive.as_uri(), archive_products=["uv"],
        output_dir=root, force_process=False, dry_run=False,
        resolving_power=resolving_power, samples_per_resolution=samples,
    )


def test_resolution_changes_rebuild_from_raw_and_leave_sed_and_continuum_untouched(tmp_path):
    archive, payloads = make_archive(tmp_path)
    _, native_rows = extract(tmp_path, archive)
    native = {r["model_name"]: (tmp_path / r["spectrum_relpath"]).read_bytes() for r in native_rows}
    stats, rows = extract(tmp_path, archive, resolving_power=1000)
    assert stats.spectra_saved == 1
    detailed = next(r for r in rows if r["model_name"].endswith(".7"))
    path = tmp_path / detailed["spectrum_relpath"]
    assert detailed["resolving_power"] == 1000
    assert detailed["points"] < 4001
    assert converter._existing_npz_spectrum_metadata(path)["resolving_power"] == 1000
    for row in rows:
        if not row["model_name"].endswith(".7"):
            assert (tmp_path / row["spectrum_relpath"]).read_bytes() == native[row["model_name"]]
            assert row["resolving_power"] is None
    assert extract(tmp_path, archive, resolving_power=1000)[0].spectra_saved == 0
    assert extract(tmp_path, archive, resolving_power=1000, samples=4)[0].spectra_saved == 1
    extract(tmp_path, archive, resolving_power=2000)
    original = converter._parse_spectrum_payload(payloads["G35000g400v10.uv.7.gz"], product_tags=["uv"])
    expected = converter._reduce_resolution(original, resolving_power=2000, samples_per_resolution=3)
    with np.load(path) as actual:
        np.testing.assert_array_equal(actual["flux_lambda_cgs"], expected["arrays"]["flux_lambda_cgs"])
    assert extract(tmp_path, archive)[0].spectra_saved == 1
    with np.load(path) as restored:
        np.testing.assert_array_equal(restored["flux_lambda_cgs"], original["arrays"]["flux_lambda_cgs"])
        assert "resolving_power" not in restored


def test_adding_sed_binning_reuses_matching_detailed_spectra(tmp_path):
    archive, _ = make_archive(tmp_path)
    _, rows = extract(tmp_path, archive, resolving_power=1000)
    retained = {r["spectrum_relpath"]: (tmp_path / r["spectrum_relpath"]).read_bytes()
                for r in rows if not r["model_name"].endswith(".flux")}
    stats, rows = converter._extract_archive(
        archive, grid="ostar", archive_url=archive.as_uri(), archive_products=["uv"],
        output_dir=tmp_path, force_process=False, dry_run=False,
        resolving_power=1000, sed_binning_power=3000,
    )
    assert stats.spectra_saved == 1
    for path, previous in retained.items():
        assert (tmp_path / path).read_bytes() == previous
    sed = next(r for r in rows if r["model_name"].endswith(".flux"))
    assert sed["sed_rebin_applied"]


def test_local_conversion_indexes_resolution_and_compactor_preserves_it(tmp_path, monkeypatch):
    make_archive(tmp_path)
    def no_network(*args, **kwargs):
        raise AssertionError("Local conversion attempted network discovery")
    monkeypatch.setattr(converter, "_discover_archive_urls", no_network)
    assert converter.main(["--local-only", "--grid", "ostar", "--output-dir", str(tmp_path),
                           "--resolving-power", "1000"]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    row = next(r for r in manifest["models"] if r["resolving_power"])
    assert manifest["conversion"]["detailed_resolving_power"] == 1000
    compact_spectrum(tmp_path, row)
    with np.load(tmp_path / row["spectrum_relpath"]) as arrays:
        assert float(arrays["resolving_power"]) == 1000
        assert float(arrays["samples_per_resolution"]) == 3
    for mode in ("both", "normalized"):
        candidates, error = _discover_tlusty_grid_models({"tlusty_root": str(tmp_path)}, mode=mode, model_name_pattern="*.uv.*")
        assert error is None
        assert len(candidates) == 1
        assert candidates[0]["grid_metadata"]["resolving_power"] == 1000
        candidate = candidates[0]
        x, y, error = grid_fitting._build_tlusty_model_series(
            mode=mode, spectrum_path=tmp_path / candidate["spectrum_relpath"],
            continuum_path=tmp_path / candidate["continuum_relpath"] if candidate["continuum_relpath"] else None,
        )
        assert error is None
        with np.load(tmp_path / candidate["spectrum_relpath"]) as stored:
            expected = stored["flux_lambda_cgs"] / (2 if mode == "normalized" else 1)
            np.testing.assert_array_equal(y, expected)


@pytest.mark.parametrize("resolution, expected_limit", [(50000, 0), (None, 20000)])
def test_fitting_preserves_resolution_controlled_cache_sampling(monkeypatch, resolution, expected_limit):
    def check_reader(**kwargs):
        assert kwargs["max_points"] == expected_limit
        raise RuntimeError("sampling checked")
    monkeypatch.setattr(grid_fitting, "_build_tlusty_model_series", check_reader)
    candidate = dict(model_name="test", model_path="tlusty/test", spectrum_path_str="unused.npz",
                     grid_metadata={"resolving_power": resolution})
    with pytest.raises(RuntimeError, match="sampling checked"):
        grid_fitting._fit_single_tlusty_candidate(candidate=candidate, observed={}, mode="both", fit_bounds={})


@pytest.mark.parametrize("arguments", [
    ["--resolving-power", "0"], ["--resolving-power", "nan"], ["--resolving-power", "inf"],
    ["--samples-per-resolution", "1"], ["--samples-per-resolution", "nan"],
    ["--local-only", "--force-download"],
])
def test_invalid_conversion_options(arguments):
    with pytest.raises(SystemExit):
        converter.parse_args(arguments)


def test_failed_spectrum_write_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "spectrum.npz"
    path.write_bytes(b"previous spectrum")
    def fail_write(*args, **kwargs):
        raise OSError("disk write failed")
    monkeypatch.setattr(converter.np, "savez_compressed", fail_write)
    with pytest.raises(OSError, match="disk write failed"):
        converter._write_spectrum(path, {})
    assert path.read_bytes() == b"previous spectrum"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_archive_conversion_preserves_previous_indexes(tmp_path, monkeypatch):
    make_archive(tmp_path)
    (tmp_path / "models.csv").write_text("previous csv")
    (tmp_path / "manifest.json").write_text("previous manifest")
    def fail_conversion(*args, **kwargs):
        raise ValueError("invalid spectrum")
    monkeypatch.setattr(converter, "_extract_archive", fail_conversion)
    assert converter.main(["--local-only", "--grid", "ostar", "--output-dir", str(tmp_path)]) == 2
    assert (tmp_path / "models.csv").read_text() == "previous csv"
    assert (tmp_path / "manifest.json").read_text() == "previous manifest"
