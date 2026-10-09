from __future__ import annotations

import time
from pathlib import Path

import pytest

from cmfgen_viewer import observed_spectrum as obs


@pytest.mark.parametrize("header", ["wavelength bandwidth flux flux_error comment", "# wavelength bandwidth flux flux_error comment", "! wavelength bandwidth flux flux_error comment"])
def test_named_sed_text_is_photometry_including_commented_headers(tmp_path, header):
    path = tmp_path / "sed.txt"
    path.write_text(
        header + '\n5000 100 1.2e-12 nan "Survey, B # band"\n6000 200 2.3e-12 4e-14 "Survey V"\n',
        encoding="utf-8",
    )
    parsed = obs.parse_uploaded_spectrum(path, flux_mode="normalized")
    assert parsed["observation_type"] == "photometry"
    assert parsed["flux_mode"] == "absolute"
    assert parsed["flux"] == [1.2e-12, 2.3e-12]
    assert parsed["band_width"] == [100, 200]
    assert parsed["flux_err"] == [0, 4e-14]
    assert parsed["point_comment"] == ["Survey, B # band", "Survey V"]


def test_named_sed_csv_maps_reordered_columns_and_preserves_disabled_rows(tmp_path):
    path = tmp_path / "sed.csv"
    path.write_text(
        'comment,flux,enabled,band_width_A,wavelength_A,flux_error\n'
        '"B, survey",1.2e-12,true,100,5000,4e-14\n'
        '"V band",2.3e-12,false,200,6000,nan\n', encoding="utf-8",
    )
    canonical = obs.uploaded_photometry_table(path)
    assert "6000 200 2.3e-12 0 0 # V band" in canonical
    parsed = obs.parse_uploaded_spectrum(path)
    assert parsed["wavelength"] == [5000]
    assert parsed["band_width"] == [100]
    assert parsed["point_comment"] == ["B, survey"]
    assert parsed["disabled_points"] == 1


@pytest.mark.parametrize("width_name", ["bandwidth", "band_width", "bandpass_width_A", "filter_width"])
def test_bandwidth_aliases_trigger_photometry(tmp_path, width_name):
    path = tmp_path / "sed.csv"
    path.write_text(f"wavelength,{width_name},flux\n5000,0,1.2e-12\n", encoding="utf-8")
    assert obs.parse_uploaded_spectrum(path)["band_width"] == [0]


@pytest.mark.parametrize("content", [
    "wavelength flux width\n5000 1 100\n6000 2 200\n",
    "wavelength flux bandwidth_error\n5000 1 100\n6000 2 200\n",
    "5000 100 1.2e-12\n6000 200 2.3e-12\n",
])
def test_ambiguous_width_or_headerless_tables_remain_spectra(tmp_path, content):
    path = tmp_path / "spectrum.txt"
    path.write_text(content, encoding="utf-8")
    assert obs.uploaded_photometry_table(path) is None
    assert obs.parse_uploaded_spectrum(path)["observation_type"] == "spectrum"


@pytest.mark.parametrize("row,match", [
    ("5000 -100 1.2e-12 1", "Invalid photometry row"),
    ("5000 nan 1.2e-12 1", "Invalid photometry row"),
    ("5000 100 1.2e-12 maybe", "enabled flag"),
    ("5000 100", "fewer columns"),
])
def test_invalid_named_photometry_is_not_silently_parsed_as_spectrum(tmp_path, row, match):
    path = tmp_path / "sed.txt"
    path.write_text("wavelength bandwidth flux enabled\n" + row + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        obs.parse_uploaded_spectrum(path)


def test_named_votable_photometry_converts_wave_width_flux_and_errors(tmp_path):
    table_module = pytest.importorskip("astropy.table")
    units = pytest.importorskip("astropy.units")
    table = table_module.Table({
        "wavelength": [500, 600] * units.nm,
        "bandwidth": [0.01, 0.02] * units.um,
        "flux": [1, 2] * units.Jy,
        "flux_error": [0.1, 0.2] * units.Jy,
        "comment": ["Survey B", "Survey V"],
    })
    path = tmp_path / "sed.vot"
    table.write(path, format="votable")
    parsed = obs.parse_uploaded_spectrum(path)
    assert parsed["observation_type"] == "photometry"
    assert parsed["wavelength"] == pytest.approx([5000, 6000])
    assert parsed["band_width"] == pytest.approx([100, 200])
    expected = table["flux"].quantity.to_value(
        "erg / (s cm2 Angstrom)", equivalencies=units.spectral_density(table["wavelength"].quantity)
    )
    assert parsed["flux"] == pytest.approx(expected)
    assert parsed["flux_err"] == pytest.approx(expected * 0.1)
    assert parsed["point_comment"] == ["Survey B", "Survey V"]


def test_named_votable_photometry_preserves_masked_error_and_enabled(tmp_path):
    table_module = pytest.importorskip("astropy.table")
    table = table_module.Table({
        "wavelength": [5000, 6000], "bandwidth": [100, 200], "flux": [1e-12, 2e-12],
        "enabled": [True, False],
    })
    table["flux_error"] = table_module.MaskedColumn([9e-14, 2e-14], mask=[True, False], unit="erg / (s cm2 Angstrom)")
    path = tmp_path / "sed.vot"
    table.write(path, format="votable")
    parsed = obs.parse_uploaded_spectrum(path)
    assert parsed["flux_err"] == [0]
    assert parsed["disabled_points"] == 1


def test_named_votable_photometry_rejects_invalid_bandwidth_units(tmp_path):
    table_module = pytest.importorskip("astropy.table")
    table = table_module.Table({"wavelength": [5000], "bandwidth": [100], "flux": [1e-12]})
    table["bandwidth"].unit = "s"
    path = tmp_path / "sed.vot"
    table.write(path, format="votable")
    with pytest.raises(ValueError, match="Cannot convert photometry width unit"):
        obs.parse_uploaded_spectrum(path)


@pytest.mark.parametrize("missing", ["wavelength", "bandwidth", "flux"])
def test_named_votable_photometry_rejects_masked_required_values(tmp_path, missing):
    table_module = pytest.importorskip("astropy.table")
    table = table_module.Table({"wavelength": [5000], "bandwidth": [100], "flux": [1e-12]})
    table[missing] = table_module.MaskedColumn(table[missing], mask=[True])
    path = tmp_path / "sed.vot"
    table.write(path, format="votable")
    with pytest.raises(ValueError, match="Invalid photometry row"):
        obs.parse_uploaded_spectrum(path)


def test_named_csv_photometry_missing_error_is_zero(tmp_path):
    path = tmp_path / "sed.csv"
    path.write_text("wavelength,bandwidth,flux,flux_error\n5000,100,1e-12,\n", encoding="utf-8")
    assert obs.parse_uploaded_spectrum(path)["flux_err"] == [0]


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


def test_normalize_photometry_table_emits_complete_canonical_schema() -> None:
    normalized = obs.normalize_photometry_table(
        "5000 100 1.2e-12\n6000 200 2.3e-12 4e-14 0 # red\n"
    )

    assert normalized.startswith(obs.CANONICAL_PHOTOMETRY_HEADER + "\n")
    assert "5000 100 1.2e-12 0 1" in normalized
    assert "6000 200 2.3e-12 4e-14 0 # red" in normalized


def test_manifest_photometry_type_parses_legacy_txt_schema(tmp_path: Path) -> None:
    path = tmp_path / "source.txt"
    path.write_text(
        '# wavelength flux flux_error comment\n5000 1.2e-12 4e-14 "legacy B"\n',
        encoding="utf-8",
    )

    parsed = obs.parse_uploaded_spectrum(
        path,
        flux_mode="absolute",
        observation_type="photometry",
    )

    assert parsed["observation_type"] == "photometry"
    assert parsed["wavelength"] == [5000.0]
    assert parsed["band_width"] == [0.0]
    assert parsed["flux"] == [1.2e-12]
    assert parsed["flux_err"] == [4e-14]
    assert parsed["point_comment"] == ["legacy B"]


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
