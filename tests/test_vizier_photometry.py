from __future__ import annotations

import math
from pathlib import Path

from astropy.table import Table

from cmfgen_viewer import vizier_photometry as vp


def test_normalize_center_query_supports_decimal_and_sexagesimal() -> None:
    decimal = vp.normalize_center_query("120.5 -20.25")
    dec_ra, dec_dec = [float(value) for value in decimal.split()]
    assert math.isclose(dec_ra, 120.5, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(dec_dec, -20.25, rel_tol=0.0, abs_tol=1e-9)

    sexagesimal = vp.normalize_center_query("12:00:00 +30:00:00")
    sex_ra, sex_dec = [float(value) for value in sexagesimal.split()]
    assert math.isclose(sex_ra, 180.0, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(sex_dec, 30.0, rel_tol=0.0, abs_tol=1e-6)


def test_build_vizier_query_params_source_selection() -> None:
    selected = [vp.CATALOG_OPTIONS_BY_KEY["panstarrs_dr1"].source_id]
    restricted = vp._build_vizier_query_params(
        center_query="120.0 30.0",
        radius_arcsec=5.0,
        source_ids=selected,
        include_all_catalogs=False,
        max_rows=100,
    )
    assert restricted["-source"] == selected[0]

    all_catalogs = vp._build_vizier_query_params(
        center_query="120.0 30.0",
        radius_arcsec=5.0,
        source_ids=selected,
        include_all_catalogs=True,
        max_rows=100,
    )
    assert "-source" not in all_catalogs


def test_extract_points_from_sed_table_converts_flux_and_builds_comments() -> None:
    table = Table(
        {
            "sed_freq": [623000.0, 89279.0],
            "sed_flux": [1.0, 0.5],
            "sed_eflux": [0.1, 0.05],
            "sed_filter": ["PS1 g", "2MASS Ks"],
            "sed_source": ["II/349/ps1", "II/246/out"],
        }
    )
    points = vp._extract_points_from_sed_table(table)
    assert len(points) == 2

    first = points[0]
    assert first.lambda_eff_a > 4000.0
    assert first.band_width_a > 0.0
    assert first.flux > 0.0
    assert first.flux_err is not None and first.flux_err > 0.0
    assert first.comment.startswith("II/349/ps1 ")
    assert "Pan-STARRS" in first.comment

    expected_lambda = vp.LIGHT_SPEED_ANGSTROM_PER_S / (623000.0 * 1e9)
    expected_flux = 1.0 * vp.JY_TO_FLAMBDA_ANGSTROM_FACTOR / (expected_lambda * expected_lambda)
    assert math.isclose(first.lambda_eff_a, expected_lambda, rel_tol=0.0, abs_tol=1e-6)
    assert math.isclose(first.flux, expected_flux, rel_tol=1e-12, abs_tol=0.0)


def test_format_photometry_table_rows_includes_comments() -> None:
    rows = vp.format_photometry_table_rows(
        [
            vp.VizierPhotometryPoint(
                lambda_eff_a=5500.0,
                band_width_a=800.0,
                flux=1.2e-12,
                flux_err=1.0e-13,
                comment="Gaia DR3 syntphot G",
            )
        ]
    )
    assert "5500.000" in rows
    assert "Gaia DR3 syntphot G" in rows
    assert "# " in rows


def test_format_photometry_table_rows_emits_flux_err_column_when_missing() -> None:
    rows = vp.format_photometry_table_rows(
        [
            vp.VizierPhotometryPoint(
                lambda_eff_a=4810.0,
                band_width_a=1530.0,
                flux=1.0e-12,
                flux_err=None,
                comment="Pan-STARRS g",
            )
        ]
    )
    assert "0.00000000e+00 1" in rows


def test_persist_vizier_raw_payload_writes_latest_and_timestamped_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(vp, "VIZIER_DEBUG_DIR", tmp_path)
    payload = b"<VOTABLE>example</VOTABLE>"
    url = "https://vizier.cds.unistra.fr/viz-bin/sed?-c=PY+Gem"

    vp._persist_vizier_raw_payload(query_url=url, payload=payload)

    latest_payload = tmp_path / "latest.votable"
    latest_url = tmp_path / "latest.url.txt"
    assert latest_payload.is_file()
    assert latest_payload.read_bytes() == payload
    assert latest_url.is_file()
    assert latest_url.read_text(encoding="utf-8").strip() == url

    dumped_payloads = [path for path in tmp_path.iterdir() if path.name.startswith("vizier_sed_") and path.suffix == ".votable"]
    dumped_urls = [path for path in tmp_path.iterdir() if path.name.startswith("vizier_sed_") and path.suffix == ".txt"]
    assert dumped_payloads
    assert dumped_urls
