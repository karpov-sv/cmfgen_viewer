from __future__ import annotations

import csv
from pathlib import Path

from cmfgen_viewer import grid_catalog


def _eight_band_photometry() -> dict[str, object]:
    return {
        "observation_type": "photometry",
        "wavelength": [3531.0, 4772.245, 6125.714, 7479.852, 8652.019, 12500.207, 16300.155, 21900.245],
        "band_width": [353.1, 1530.0, 1440.0, 1230.0, 960.0, 1620.0, 2510.0, 2620.0],
    }


def test_tlusty_photometry_coverage_rejects_optical_only_segment() -> None:
    observed = _eight_band_photometry()
    optical = {
        "wavelength_min_angstrom": 3200.0,
        "wavelength_max_angstrom": 9998.8,
    }
    full_sed = {
        "wavelength_min_angstrom": 54.4,
        "wavelength_max_angstrom": 2_997_924.6,
    }

    assert not grid_catalog._tlusty_row_covers_observed_photometry(
        optical,
        observed,
        redshift_bounds=(-0.02, 0.02),
    )
    assert grid_catalog._tlusty_row_covers_observed_photometry(
        full_sed,
        observed,
        redshift_bounds=(-0.02, 0.02),
    )
    spectral_upload = {**observed, "observation_type": "spectrum"}
    assert grid_catalog._tlusty_row_covers_observed_photometry(
        optical,
        spectral_upload,
        redshift_bounds=(-0.02, 0.02),
    )


def test_tlusty_discovery_excludes_incomplete_photometry_segments(tmp_path: Path) -> None:
    spectra_dir = tmp_path / "spectra"
    spectra_dir.mkdir()
    optical_path = spectra_dir / "BG25000g400v2.vis.7.npz"
    full_sed_path = spectra_dir / "BG25000g400v2.flux.npz"
    optical_path.touch()
    full_sed_path.touch()

    columns = [
        "grid",
        "model_name",
        "spectrum_relpath",
        "wavelength_min_angstrom",
        "wavelength_max_angstrom",
        "member_products",
        "archive_products",
        "available_arrays",
        "points",
    ]
    with (tmp_path / "models.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "grid": "bstar",
                "model_name": "BG25000g400v2.vis.7",
                "spectrum_relpath": str(optical_path.relative_to(tmp_path)),
                "wavelength_min_angstrom": 3200.0,
                "wavelength_max_angstrom": 9998.8,
                "member_products": '["optical"]',
                "archive_products": '["optical"]',
                "available_arrays": '["flux_lambda_cgs"]',
                "points": 100,
            }
        )
        writer.writerow(
            {
                "grid": "bstar",
                "model_name": "BG25000g400v2.flux",
                "spectrum_relpath": str(full_sed_path.relative_to(tmp_path)),
                "wavelength_min_angstrom": 54.4,
                "wavelength_max_angstrom": 2_997_924.6,
                "member_products": '["flux"]',
                "archive_products": '["flux"]',
                "available_arrays": '["flux_lambda_cgs"]',
                "points": 100,
            }
        )

    candidates, error = grid_catalog._discover_tlusty_grid_models(
        {"tlusty_root": str(tmp_path)},
        mode="both",
        model_name_pattern="",
        observed=_eight_band_photometry(),
        fit_bounds={"redshift": (-0.02, 0.02)},
    )

    assert error is None
    assert [candidate["model_name"] for candidate in candidates] == ["BG25000g400v2.flux"]
