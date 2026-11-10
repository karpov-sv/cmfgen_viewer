import json

import numpy as np
import pytest

from cmfgen_viewer.grid_storage import (
    PHOENIX_FLUX_FACTOR, atomic_npz, load_spectrum, write_compact_spectrum,
)
from scripts.compact_imported_grids import compact_grid


def bosz_arrays():
    flux = np.array([1., 2., np.nan, 3.])
    continuum = np.array([2., -1., 4., 6.])
    return dict(wavelength_angstrom=np.arange(4000., 4004.), flux_lambda_cgs=flux,
                continuum_lambda_cgs=continuum,
                normalized_flux_candidate=np.array([.5, np.nan, np.nan, .5]),
                raw_flux_lambda_cgs=np.array([1., 2., -.1, 3.]))


def assert_same(actual, expected):
    assert set(actual) == set(expected)
    for key in expected:
        np.testing.assert_array_equal(actual[key], expected[key])


def test_shared_axis_masks_and_legacy_compatibility(tmp_path):
    arrays = bosz_arrays()
    legacy = tmp_path / "legacy.npz"
    np.savez_compressed(legacy, **arrays)
    assert_same(load_spectrum(legacy), arrays)
    for name in ("one", "two"):
        path = tmp_path / f"{name}.npz"
        write_compact_spectrum(path, arrays, "bosz")
        assert_same(load_spectrum(path), arrays)
    assert len(list(tmp_path.glob("_wavelength_*.npz"))) == 1
    one, two = (load_spectrum(tmp_path / f"{name}.npz") for name in ("one", "two"))
    assert one["wavelength_angstrom"] is two["wavelength_angstrom"]
    assert not one["wavelength_angstrom"].flags.writeable


@pytest.mark.parametrize("source_precision", ["f4", "f8"])
def test_phoenix_exact_flux_or_precision_preserving_fallback(tmp_path, source_precision):
    source = np.array([1.23456789123e14, -9.87654321987e12, 2.], dtype=source_precision)
    arrays = dict(wavelength_angstrom=np.array([4000., 5000., 6000.]),
                  flux_lambda_cgs=source.astype(np.float64) * PHOENIX_FLUX_FACTOR)
    path = tmp_path / "phoenix.npz"
    write_compact_spectrum(path, arrays, "phoenix")
    assert_same(load_spectrum(path), arrays)
    with np.load(path) as stored:
        assert ("source_flux" in stored) == (source_precision == "f4")


def test_invalid_normalization_aborts_without_replacing_original(tmp_path):
    arrays = bosz_arrays()
    path = tmp_path / "model.npz"
    np.savez_compressed(path, **arrays)
    original = path.read_bytes()
    arrays["normalized_flux_candidate"][0] = .7
    with pytest.raises(ValueError, match="Lossless verification"):
        write_compact_spectrum(path, arrays, "bosz")
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".model-*"))


def test_shared_axis_corruption_and_unsafe_reference_are_rejected(tmp_path):
    path = tmp_path / "model.npz"
    write_compact_spectrum(path, bosz_arrays(), "bosz")
    axis = next(tmp_path.glob("_wavelength_*.npz"))
    # A cached axis must not hide a replacement with different values.
    atomic_npz(axis, {"wavelength_angstrom": np.arange(5000., 5004.)})
    with pytest.raises(ValueError, match="Invalid shared wavelength"):
        load_spectrum(path)
    with np.load(path) as payload:
        stored = {key: payload[key] for key in payload.files}
    stored["wavelength_key"] = np.array("../outside")
    np.savez_compressed(path, **stored)
    with pytest.raises(ValueError, match="Invalid shared wavelength key"):
        load_spectrum(path)


def test_migration_preserves_metadata_and_can_resume_mixed_grid(tmp_path):
    spectra = tmp_path / "spectra"
    spectra.mkdir()
    arrays = bosz_arrays()
    np.savez_compressed(spectra / "old.npz", **arrays)
    write_compact_spectrum(spectra / "new.npz", arrays, "bosz")
    rows = [dict(grid="bosz", model_name=name, spectrum_relpath=f"spectra/{name}.npz",
                 masked_flux_points=1, masked_normalized_points=2, source_sha256="untouched")
            for name in ("old", "new")]
    manifest = dict(schema_version=1, models=rows, quality_policy="untouched")
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "models.csv").write_bytes(b"metadata must remain identical\n")
    before_csv = (tmp_path / "models.csv").read_bytes()
    for _ in range(2):
        report = compact_grid(tmp_path, workers=2, log=lambda *a, **kw: None)
        assert report["models"] == 2
        result = json.loads((tmp_path / "manifest.json").read_text())
        result.pop("spectrum_storage")
        assert result == manifest
        assert (tmp_path / "models.csv").read_bytes() == before_csv
        for name in ("old", "new"):
            assert_same(load_spectrum(spectra / f"{name}.npz"), arrays)
