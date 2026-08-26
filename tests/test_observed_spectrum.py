from __future__ import annotations

import time
from pathlib import Path

import pytest

from cmfgen_viewer import observed_spectrum as obs


def test_upload_token_generation_and_validation() -> None:
    token = obs.generate_upload_token()
    assert obs.is_valid_upload_token(token)
    assert not obs.is_valid_upload_token("bad token with spaces")


def test_manifest_write_read_list_and_remove(tmp_path: Path) -> None:
    token = "Token_1234"
    payload = {"stored_name": "spec.phot", "created_at": time.time()}
    obs.write_upload_manifest(tmp_path, token, payload)
    (tmp_path / token / "spec.phot").write_text("5000 100 1\n", encoding="utf-8")

    loaded = obs.read_upload_manifest(tmp_path, token)
    assert isinstance(loaded, dict)
    assert loaded["stored_name"] == "spec.phot"

    listed = obs.list_upload_manifests(tmp_path)
    assert len(listed) == 1
    assert listed[0]["token"] == token
    assert listed[0]["exists"] is True

    obs.remove_upload_bundle(tmp_path, token)
    assert not (tmp_path / token).exists()


def test_cleanup_upload_root_removes_expired_entries(tmp_path: Path) -> None:
    old_token = "OldToken1"
    new_token = "NewToken1"
    obs.write_upload_manifest(tmp_path, old_token, {"created_at": time.time() - 1000})
    obs.write_upload_manifest(tmp_path, new_token, {"created_at": time.time()})
    obs.cleanup_upload_root(tmp_path, ttl_seconds=60)
    assert not (tmp_path / old_token).exists()
    assert (tmp_path / new_token).exists()


def test_remove_all_upload_bundles_preserves_unmanaged_entries(tmp_path: Path) -> None:
    for token in ("Token_1001", "Token_1002"):
        obs.write_upload_manifest(tmp_path, token, {"stored_name": "source.phot", "created_at": time.time()})
        (tmp_path / token / "source.phot").write_text("5000 100 1\n", encoding="utf-8")

    unmanaged_dir = tmp_path / "Unmanaged_1"
    unmanaged_dir.mkdir()
    (unmanaged_dir / "spectrum.fits").write_text("keep", encoding="utf-8")
    unrelated_file = tmp_path / "notes.txt"
    unrelated_file.write_text("keep", encoding="utf-8")

    removed, failed = obs.remove_all_upload_bundles(tmp_path)

    assert (removed, failed) == (2, 0)
    assert unmanaged_dir.is_dir()
    assert unrelated_file.is_file()


def test_parse_uploaded_spectrum_photometry_mode_and_filters(tmp_path: Path) -> None:
    path = tmp_path / "upload.phot"
    path.write_text(
        """5000 100 1.0 0.1 true # blue
6000 100 1.2 0.2 false
bad line
7000 100 1.4
""",
        encoding="utf-8",
    )
    parsed = obs.parse_uploaded_spectrum(
        path,
        flux_mode="normalized",
        lambda_min=5500,
        lambda_max=7500,
    )

    assert parsed["observation_type"] == "photometry"
    assert parsed["flux_mode"] == "absolute"
    assert parsed["wavelength"] == [7000.0]
    assert parsed["flux"] == [1.4]
    assert parsed["range_skipped_points"] == 1
    assert any("Skipped 1 invalid photometry row(s)" in w for w in parsed["warnings"])
    assert any("Skipped 1 disabled photometry row(s)." in w for w in parsed["warnings"])
    assert any("treated as absolute-flux data" in w for w in parsed["warnings"])


def test_parse_uploaded_photometry_token4_boolean_not_misread_as_flux_err(tmp_path: Path) -> None:
    path = tmp_path / "upload.phot"
    path.write_text(
        "5000 100 1.0 1 # bool-enabled without explicit error\n",
        encoding="utf-8",
    )
    parsed = obs.parse_uploaded_spectrum(path, flux_mode="absolute")
    assert parsed["observation_type"] == "photometry"
    assert parsed["wavelength"] == [5000.0]
    assert parsed["flux"] == [1.0]
    assert parsed["flux_err"] == [None]


def test_parse_uploaded_spectrum_rejects_unsupported_suffix(tmp_path: Path) -> None:
    path = tmp_path / "upload.abc"
    path.write_text("text", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported uploaded spectrum format"):
        obs.parse_uploaded_spectrum(path)


def test_parse_uploaded_spectrum_csv_named_columns_and_filters(tmp_path: Path) -> None:
    path = tmp_path / "upload.csv"
    path.write_text(
        "wavelength,flux,flux_error\n"
        "7000,1.2e-11,1.2e-13\n"
        "bad,9.9e-12,1.1e-13\n"
        "6000,1.1e-11,1.1e-13\n"
        "5000,1.0e-11,1.0e-13\n",
        encoding="utf-8",
    )

    parsed = obs.parse_uploaded_spectrum(path, flux_mode="absolute", lambda_min=4500, lambda_max=6500)

    assert parsed["format"] == "csv-table"
    assert parsed["wavelength"] == [5000.0, 6000.0]
    assert parsed["flux"] == [1.0e-11, 1.1e-11]
    assert parsed["flux_err"] == [1.0e-13, 1.1e-13]
    assert parsed["raw_points"] == 4
    assert parsed["skipped_points"] == 1
    assert parsed["range_skipped_points"] == 1
    assert any("line(s): 3" in warning for warning in parsed["warnings"])


def test_parse_uploaded_spectrum_text_positional_columns(tmp_path: Path) -> None:
    path = tmp_path / "upload.txt"
    path.write_text(
        "# wavelength flux uncertainty\n"
        "6000 1.10D+00 0.03\n"
        "5000 0.95 0.02 # inline comment\n",
        encoding="utf-8",
    )

    parsed = obs.parse_uploaded_spectrum(path, flux_mode="normalized")

    assert parsed["format"] == "text-table"
    assert parsed["wavelength"] == [5000.0, 6000.0]
    assert parsed["flux"] == [0.95, 1.1]
    assert parsed["flux_err"] == [0.02, 0.03]
    assert parsed["flux_mode"] == "normalized"


def test_parse_uploaded_spectrum_votable_named_columns_and_units(tmp_path: Path) -> None:
    table_module = pytest.importorskip("astropy.table")
    units = pytest.importorskip("astropy.units")
    path = tmp_path / "upload.vot"
    table = table_module.Table()
    table["wavelength"] = [500.0, 600.0] * units.nm
    table["flux"] = [1.0e-11, 1.2e-11]
    table["flux_error"] = [1.0e-13, 1.2e-13]
    table.write(path, format="votable")

    parsed = obs.parse_uploaded_spectrum(path, flux_mode="absolute")

    assert parsed["format"] == "votable"
    assert parsed["wavelength"] == pytest.approx([5000.0, 6000.0])
    assert parsed["flux"] == pytest.approx([1.0e-11, 1.2e-11])
    assert parsed["flux_err"] == pytest.approx([1.0e-13, 1.2e-13])


def test_extract_2d_fits_rows_uses_long_dimension_as_samples() -> None:
    np = pytest.importorskip("numpy")
    data = np.asarray(
        [
            [4000.0, 5000.0, 6000.0, 7000.0],
            [0.8, 1.0, 1.2, 1.1],
        ]
    )

    wavelength, flux, format_name, warnings = obs._extract_wave_flux_from_fits_data(data, {})

    assert wavelength.tolist() == [4000.0, 5000.0, 6000.0, 7000.0]
    assert flux.tolist() == [0.8, 1.0, 1.2, 1.1]
    assert format_name == "fits-2d-rows"
    assert warnings == ["Using first two rows of 2D FITS data as wavelength and flux."]


def test_extract_2d_fits_columns_uses_long_dimension_as_samples() -> None:
    np = pytest.importorskip("numpy")
    data = np.asarray(
        [
            [4000.0, 0.8],
            [5000.0, 1.0],
            [6000.0, 1.2],
            [7000.0, 1.1],
        ]
    )

    wavelength, flux, format_name, warnings = obs._extract_wave_flux_from_fits_data(data, {})

    assert wavelength.tolist() == [4000.0, 5000.0, 6000.0, 7000.0]
    assert flux.tolist() == [0.8, 1.0, 1.2, 1.1]
    assert format_name == "fits-2d-columns"
    assert warnings == ["Using first two columns of 2D FITS data as wavelength and flux."]


def test_private_helpers_for_enabled_token_bounds_and_flux_mode() -> None:
    assert obs._parse_enabled_token("true") is True
    assert obs._parse_enabled_token("off") is False
    assert obs._parse_enabled_token("x") is None

    assert obs._normalize_wavelength_bounds(7000.0, 5000.0) == (5000.0, 7000.0)
    assert obs._normalize_wavelength_bounds(-1.0, 5000.0) == (None, 5000.0)

    normalized_like = [1.0 + ((idx % 5) - 2) * 0.01 for idx in range(40)]
    assert obs._detect_flux_mode(normalized_like) == "normalized"
    assert obs._detect_flux_mode([1, 2, 3]) == "absolute"
