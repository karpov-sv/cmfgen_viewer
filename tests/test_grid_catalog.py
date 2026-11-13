from __future__ import annotations

import csv
import json
from pathlib import Path

from cmfgen_viewer import grid_catalog


def _write_imported_index(root, rows):
    root.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with (root / "models.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, list) else value
                             for key, value in row.items()})


def test_grid_inventory_uses_fit_rules_and_updates_when_files_appear(tmp_path):
    config = {f"{source}_root": str(tmp_path / source) for source in ("tlusty", "bosz", "phoenix")}
    for source in ("bosz", "phoenix"):
        root = Path(config[f"{source}_root"])
        (root / "spectra").mkdir(parents=True)
        rows = []
        for name in ("good", "excluded", "missing"):
            row = dict(grid=source, model_name=name, spectrum_relpath=f"spectra/{name}.npz",
                       available_arrays=["wavelength_angstrom", "flux_lambda_cgs"],
                       fit_eligible="false" if name == "excluded" else "true",
                       negative_flux_points=1 if name == "excluded" else 0,
                       resolving_power=2000 if source == "bosz" else 10000,
                       wavelength_min_angstrom=3000, wavelength_max_angstrom=25000)
            if source == "bosz":
                row["available_arrays"].append("continuum_lambda_cgs")
            rows.append(row)
            if name != "missing":
                # Inventory must inspect indices/file presence, never decompress spectra.
                (root / row["spectrum_relpath"]).touch()
        _write_imported_index(root, rows)
    inventory = {item["source"]: item for item in grid_catalog._imported_grid_inventory(config)}
    assert inventory["tlusty"]["status"] == "Not installed"
    assert inventory["bosz"]["indexed_spectra"] == 3
    assert inventory["bosz"]["absolute_candidates"] == 1
    assert inventory["bosz"]["normalized_candidates"] == 1
    assert inventory["bosz"]["coverage"] == "3,000–25,000"
    assert inventory["bosz"]["resolution"] == "R=2000"
    assert inventory["phoenix"]["absolute_candidates"] == 1
    assert inventory["phoenix"]["normalized_candidates"] is None
    assert inventory["phoenix"]["status"] == "Available"
    (tmp_path / "bosz" / "spectra" / "missing.npz").touch()
    updated = {item["source"]: item for item in grid_catalog._imported_grid_inventory(config)}
    assert updated["bosz"]["absolute_candidates"] == 2
    assert updated["bosz"]["normalized_candidates"] == 2


def test_grid_inventory_reports_missing_empty_and_unreadable_indices(tmp_path):
    config = {f"{source}_root": str(tmp_path / source) for source in ("tlusty", "bosz", "phoenix")}
    (tmp_path / "tlusty").mkdir()
    (tmp_path / "bosz").mkdir()
    (tmp_path / "bosz" / "models.csv").write_text("grid,model_name,spectrum_relpath\n")
    _write_imported_index(tmp_path / "phoenix", [dict(grid="phoenix", model_name="x" * 200000,
                                                   spectrum_relpath="spectra/invalid.npz")])
    inventory = {item["source"]: item for item in grid_catalog._imported_grid_inventory(config)}
    assert inventory["tlusty"]["status"] == "Index missing"
    assert inventory["bosz"]["status"] == "No fitting candidates"
    assert inventory["phoenix"]["status"] == "Index unreadable"
    assert inventory["phoenix"]["detail"]


def test_tlusty_resolution_note_distinguishes_sed_binning_from_broadening(tmp_path):
    _write_imported_index(tmp_path, [
        dict(grid="bstar", model_name="detailed", spectrum_relpath="detailed.npz",
             resolving_power=50000),
        dict(grid="ostar", model_name="sed", spectrum_relpath="sed.npz", sed_binning_power=3000),
        dict(grid="ostar", model_name="native", spectrum_relpath="native.npz"),
    ])
    note = grid_catalog._imported_grid_resolution_note({"tlusty_root": str(tmp_path)}, "tlusty")
    assert "R=50000" in note["label"]
    assert "other spectra not recorded" in note["label"]
    assert "SED binning λ/Δλ=3000" in note["label"]
    assert "about 6 km/s FWHM" in note["tooltip"]
    assert "not Gaussian broadening" in note["tooltip"]
    assert "R = 3000" not in note["tooltip"]


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
    inventory = grid_catalog._imported_grid_inventory({
        "tlusty_root": str(tmp_path), "bosz_root": str(tmp_path / "absent-bosz"),
        "phoenix_root": str(tmp_path / "absent-phoenix"),
    })
    assert inventory[0]["indexed_spectra"] == 2
    # Inventory counts are independent of this particular observation's bands.
    assert inventory[0]["absolute_candidates"] == 2
    assert inventory[0]["normalized_candidates"] == 0
    assert inventory[0]["status"] == "Available"
