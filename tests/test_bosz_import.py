import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.import_bosz_spectra import import_grid
from cmfgen_viewer.grid_catalog import _discover_tlusty_grid_models
from cmfgen_viewer.grid_fitting import _build_tlusty_model_series


def source_grid(tmp_path: Path, families=("ap",)) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "bosz2024_wave_r2000.txt").write_text("4000\n5000\n6000\n")
    for family in families:
        path = source / f"bosz2024_{family}_t8000_g+4.0_m-0.50_a+0.00_c+0.00_v2_r2000_resam.txt.gz"
        with gzip.open(path, "wt") as handle:
            handle.write("1 2\n3 4\n5 6\n")
    return source


def test_bosz_preserves_flux_continuum_and_distinct_atmospheres(tmp_path):
    source = source_grid(tmp_path, ("ap", "mp"))
    output = tmp_path / "output"
    assert import_grid(source, output, log=lambda _: None) == 2
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["surface_flux_factor"] == pytest.approx(4 * np.pi)
    assert {r["atmosphere_family"] for r in manifest["models"]} == {"ap", "mp"}
    for row in manifest["models"]:
        assert row["z_over_zsun"] == pytest.approx(10 ** -0.5)
        assert row["resolving_power"] == 2000
        with np.load(output / row["spectrum_relpath"]) as arrays:
            np.testing.assert_array_equal(arrays["flux_lambda_cgs"], [1, 3, 5])
            np.testing.assert_array_equal(arrays["continuum_lambda_cgs"], [2, 4, 6])
            np.testing.assert_allclose(arrays["normalized_flux_candidate"], [0.5, 0.75, 5/6])
        x, y, error = _build_tlusty_model_series(
            mode="normalized", spectrum_path=output / row["spectrum_relpath"], continuum_path=None,
        )
        assert error is None
        assert x == [4000, 5000, 6000]
        np.testing.assert_allclose(y, [0.5, 0.75, 5/6])
    # The CSV and normalized-array conventions are compatible with the current
    # external-grid reader, without changing or merging the TLUSTY catalogue.
    candidates, error = _discover_tlusty_grid_models(
        {"tlusty_root": str(output)}, mode="normalized", model_name_pattern="",
    )
    assert error is None
    assert len(candidates) == 2


def test_bosz_refuses_overwrite(tmp_path):
    source = source_grid(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    sentinel = output / "keep"
    sentinel.write_text("unchanged")
    with pytest.raises(FileExistsError):
        import_grid(source, output)
    assert sentinel.read_text() == "unchanged"


@pytest.mark.parametrize("content", ["4000\n4000\n6000\n", "6000\n5000\n4000\n", "4000\nnan\n6000\n"])
def test_bosz_rejects_invalid_wavelengths(tmp_path, content):
    source = source_grid(tmp_path)
    (source / "bosz2024_wave_r2000.txt").write_text(content)
    with pytest.raises(ValueError, match="Wavelength axis"):
        import_grid(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("content", ["1 2\n", "1 2\nnan 3\n4 5\n"])
def test_bosz_failed_import_leaves_no_partial_grid(tmp_path, content):
    source = source_grid(tmp_path)
    path = next(source.glob("*.gz"))
    with gzip.open(path, "wt") as handle:
        handle.write(content)
    with pytest.raises(ValueError):
        import_grid(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()
    assert not list(tmp_path.glob(".output-import-*"))


def test_bosz_masks_undefined_normalization(tmp_path):
    source = source_grid(tmp_path)
    with gzip.open(next(source.glob("*.gz")), "wt") as handle:
        handle.write("0 0\n3 4\n5 6\n")
    output = tmp_path / "output"
    import_grid(source, output)
    with np.load(next((output / "spectra").glob("*.npz"))) as arrays:
        assert np.isnan(arrays["normalized_flux_candidate"][0])


def test_bosz_preserves_but_masks_negative_source_flux(tmp_path):
    source = source_grid(tmp_path)
    with gzip.open(next(source.glob("*.gz")), "wt") as handle:
        handle.write("1 2\n3 4\n-0.8 0.5\n")
    output = tmp_path / "output"
    import_grid(source, output)
    row = json.loads((output / "manifest.json").read_text())["models"][0]
    assert row["masked_flux_points"] == 1
    assert row["masked_normalized_points"] == 1
    assert row["wavelength_max_angstrom"] == 5000
    with np.load(output / row["spectrum_relpath"]) as arrays:
        assert arrays["raw_flux_lambda_cgs"][-1] == -0.8
        assert np.isnan(arrays["flux_lambda_cgs"][-1])
        assert np.isnan(arrays["normalized_flux_candidate"][-1])


def test_bosz_rejects_duplicate_source_names(tmp_path):
    source = source_grid(tmp_path)
    first = next(source.glob("*.gz"))
    (source / "duplicate").mkdir()
    (source / "duplicate" / first.name).write_bytes(first.read_bytes())
    with pytest.raises(ValueError, match="Duplicate"):
        import_grid(source, tmp_path / "output")
