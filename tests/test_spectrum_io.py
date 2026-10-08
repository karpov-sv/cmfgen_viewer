"""Bulk spectrum loading must retain the legacy format and filtering rules."""

import numpy as np
import pytest

from cmfgen_viewer import spectrum_io, spectrum_transforms


@pytest.mark.parametrize("contents", [
    "Continuum Frequencies (5)\n1D0 .5d0\n0.3-00 0.2, 0.1;\n"
    "Observed intensity (Janskys)\n100 80\n6.0+01 40, 20;\n",
    "Continuum Frequencies (6)\n.2 .5 .5 1 2 0\n"
    "Observed intensity (Janskys)\n8 6 5 3 2 1\n",
    "Continuum Frequencies (7)\n2 1 0.5 0.2 0.1 0.01 0.005\n"
    "Observed intensity (Janskys)\n1 1 3 0.5 2 1 1\n",
    "Continuum Frequencies (2)\n1 0.5\nObserved intensity (Janskys)\n1\n",
    "Continuum Frequencies (4)\n1e999 1 0.5 0.1\n"
    "Observed intensity (Janskys)\n1 1e999 3 1\n",
    "Continuum Frequencies (0)\nObserved intensity (Janskys)\n",
])
@pytest.mark.parametrize("bounds", [(None, None), (3000., 15000.)])
def test_bulk_loader_matches_dependency_free_parser(tmp_path, monkeypatch, contents, bounds):
    path = tmp_path / "obs_fin"
    path.write_text(contents, encoding="utf-8")
    args = (str(path), 0, 0, *bounds)
    optimized = spectrum_io._load_obs_spectrum_cached.__wrapped__(*args)
    arrays = spectrum_io._load_obs_spectrum_cached.__wrapped__(*args, as_arrays=True)
    with monkeypatch.context() as patch:
        patch.setattr(spectrum_io, "np", None)
        legacy = spectrum_io._load_obs_spectrum_cached.__wrapped__(*args)
    assert optimized == legacy
    for key in ("wavelength", "flux"):
        np.testing.assert_array_equal(arrays[key], legacy[key])
        assert not arrays[key].flags.writeable
    assert {key: value for key, value in arrays.items() if key not in ("wavelength", "flux")} == {
        key: value for key, value in legacy.items() if key not in ("wavelength", "flux")
    }


def test_bulk_loader_does_not_accept_partial_numeric_lines(tmp_path):
    path = tmp_path / "obs_fin"
    path.write_text(
        "Continuum Frequencies (3)\n1 .5\n.25 invalid .1\n.05\n"
        "Continuum Frequencies (3)\n.1\n"
        "Observed intensity (Janskys)\n10 8 6\n"
        "Luminosity\n123456\n",
        encoding="utf-8",
    )
    vectors, count = spectrum_io._read_obs_vectors(path)
    np.testing.assert_array_equal(vectors["continuum_frequencies"], [1, .5, .1])
    np.testing.assert_array_equal(vectors["observed_intensity_janskys"], [10, 8, 6])
    assert count == 3


def test_standard_numeric_blocks_do_not_use_per_token_parser(tmp_path, monkeypatch):
    path = tmp_path / "obs_fin"
    path.write_text(
        "Continuum Frequencies (3)\n1D0 .5e0 .1\n"
        "Observed intensity (Janskys)\n100 20 3\n", encoding="utf-8",
    )

    def unexpected(*args):
        raise AssertionError("Standard numeric vectors must use bulk conversion")

    monkeypatch.setattr(spectrum_io, "parse_numeric_tokens", unexpected)
    loaded = spectrum_io.load_obs_spectrum(path, as_arrays=True)
    assert loaded["raw_points"] == 3
    assert isinstance(loaded["flux"], np.ndarray)


def test_array_loader_cache_reuses_data_and_invalidates_changed_file(tmp_path):
    path = tmp_path / "obs_fin"
    contents = "Continuum Frequencies (3)\n1 .5 .1\nObserved intensity (Janskys)\n100 20 3\n"
    path.write_text(contents, encoding="utf-8")
    first = spectrum_io.load_obs_spectrum(path, as_arrays=True)
    assert spectrum_io.load_obs_spectrum(path, as_arrays=True) is first
    with pytest.raises(ValueError):
        first["flux"][0] = 0
    path.write_text(contents.replace("100 20 3", "2000 20 3"), encoding="utf-8")
    changed = spectrum_io.load_obs_spectrum(path, as_arrays=True)
    assert changed["flux"][0] == 2000
    assert changed is not first
    viewer = spectrum_io.load_obs_spectrum(path)
    assert isinstance(viewer["flux"], list)
    np.testing.assert_array_equal(viewer["flux"], changed["flux"])


@pytest.mark.parametrize("mode", ["both", "normalized"])
def test_model_preparation_accepts_loader_arrays_without_changing_values(tmp_path, mode):
    path = tmp_path / "obs_fin"
    path.write_text(
        "Continuum Frequencies (3)\n1 .5 .1\n"
        "Observed intensity (Janskys)\n100 20 3\n", encoding="utf-8",
    )
    arrays = spectrum_io.load_obs_spectrum(path, as_arrays=True)
    lists = spectrum_io.load_obs_spectrum(path)
    actual = spectrum_transforms._build_model_series_for_fit(arrays, arrays, mode=mode)
    expected = spectrum_transforms._build_model_series_for_fit(lists, lists, mode=mode)
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
