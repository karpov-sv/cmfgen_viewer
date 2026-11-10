import csv
import json

import numpy as np
import pytest

from cmfgen_viewer.grid_fitting import _build_tlusty_model_series
from scripts.compact_tlusty_spectra import compact_grid, compact_spectrum
from scripts.download_tlusty_spectra import (
    _existing_npz_spectrum_metadata,
    _parse_spectrum_payload,
)


@pytest.mark.parametrize("normalization", ["paired", "embedded", "continuum"])
def test_compaction_preserves_absolute_and_normalized_fitting(tmp_path, normalization):
    wavelength = np.linspace(4000, 6000, 100)
    flux = 2 + np.sin(wavelength / 100)
    arrays = dict(wavelength_angstrom=wavelength, flux_lambda_cgs=flux,
                  y_col_1=flux, hnu_cgs=flux, frequency_hz=3e18 / wavelength)
    continuum = tmp_path / "continuum.npz"
    np.savez_compressed(continuum, wavelength_angstrom=wavelength, flux_lambda_cgs=flux + 1)
    if normalization == "embedded":
        arrays["normalized_flux_candidate"] = flux / (flux + 1)
        arrays["continuum_candidate_col2"] = flux + 1
    elif normalization == "continuum":
        arrays["continuum_lambda_cgs"] = flux.copy()
    path = tmp_path / "spectrum.npz"
    np.savez_compressed(path, **arrays)
    row = dict(spectrum_relpath=path.name, input_columns=2, x_axis_kind="frequency_hz", x_unit_guess="hz")

    def series(mode):
        return _build_tlusty_model_series(mode=mode, spectrum_path=path, continuum_path=continuum)

    before = {mode: series(mode) for mode in ("both", "normalized")}
    old_size, new_size, _ = compact_spectrum(tmp_path, row)
    assert new_size < old_size
    for mode, (x, y, error) in before.items():
        assert error is None
        new_x, new_y, error = series(mode)
        assert error is None
        np.testing.assert_array_equal(x, new_x)
        np.testing.assert_array_equal(y, new_y)
    metadata = _existing_npz_spectrum_metadata(path)
    assert metadata["x_axis_kind"] == "frequency_hz"
    assert metadata["x_unit_guess"] == "hz"
    assert metadata["input_columns"] == 2
    assert compact_spectrum(tmp_path, row)[:2] == (new_size, new_size)


@pytest.mark.parametrize("frequency", [False, True])
def test_converter_omits_unused_arrays_and_preserves_source_metadata(tmp_path, frequency):
    x = np.linspace(1e14, 2e14, 100) if frequency else np.linspace(4000, 6000, 100)
    payload = "\n".join(f"{value:.17g} 2 4" for value in x).encode()
    parsed = _parse_spectrum_payload(payload, product_tags=[])
    arrays = parsed["arrays"]
    assert set(arrays) == {"wavelength_angstrom", "flux_lambda_cgs", "normalized_flux_candidate",
                           "input_columns", "x_axis_kind", "x_unit_guess"}
    np.testing.assert_array_equal(arrays["normalized_flux_candidate"], np.full(100, 0.5))
    path = tmp_path / "spectrum.npz"
    np.savez_compressed(path, **arrays)
    metadata = _existing_npz_spectrum_metadata(path)
    for key in ("input_columns", "x_axis_kind", "x_unit_guess", "points"):
        assert metadata[key] == parsed[key]
    assert _build_tlusty_model_series(mode="normalized", spectrum_path=path, continuum_path=None)[2] is None


def test_compact_grid_updates_both_indexes(tmp_path):
    arrays = dict(wavelength_angstrom=np.arange(10.) + 4000, flux_lambda_cgs=np.ones(10), y_col_1=np.ones(10))
    np.savez_compressed(tmp_path / "test.npz", **arrays)
    row = dict(spectrum_relpath="test.npz", input_columns=2, x_axis_kind="wavelength_input",
               x_unit_guess="angstrom", available_arrays=json.dumps(list(arrays)))
    with (tmp_path / "models.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    (tmp_path / "manifest.json").write_text(json.dumps({"models": [row], "format": {}}))
    compact_grid(tmp_path, workers=1, log=lambda *args, **kwargs: None)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    with (tmp_path / "models.csv").open() as handle:
        row = next(csv.DictReader(handle))
    with np.load(tmp_path / "test.npz") as saved:
        assert json.loads(row["available_arrays"]) == sorted(saved.files)
        assert manifest["models"][0]["available_arrays"] == sorted(saved.files)
