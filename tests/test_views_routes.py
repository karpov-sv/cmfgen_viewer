from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cmfgen_viewer.app import create_app
from cmfgen_viewer.observed_spectrum import list_upload_manifests, read_upload_manifest
from cmfgen_viewer.vizier_photometry import VizierPhotometryPoint


def _make_app(tmp_path: Path):
    app = create_app(basepath=str(tmp_path), secret_key="test-secret")
    app.testing = True
    config = app.config["CMFGEN_VIEWER"]
    config["upload_root"] = str((tmp_path / "uploads").resolve())
    config["summary_cache_db"] = str((tmp_path / "summary.sqlite").resolve())
    return app


def _write_obs_spectrum(path: Path) -> None:
    path.write_text(
        """Continuum Frequencies (3)
1.0 2.0 3.0
Observed intensity (Janskys)
1.0 2.0 3.0
""",
        encoding="utf-8",
    )


def test_spectrum_routes_accept_marker_detected_model_name(tmp_path: Path) -> None:
    model_dir = tmp_path / "CMF1780221445ICG8C4S3"
    model_dir.mkdir()
    (model_dir / "MODEL_SPEC").write_text("settings", encoding="utf-8")
    (model_dir / "VADAT").write_text("settings", encoding="utf-8")
    obs_dir = model_dir / "obs"
    obs_dir.mkdir()
    _write_obs_spectrum(obs_dir / "obs_cont")
    _write_obs_spectrum(obs_dir / "obs_fin")

    app = _make_app(tmp_path)
    client = app.test_client()
    response = client.get(f"/spectrum/{model_dir.name}")

    assert response.status_code == 200
    assert model_dir.name.encode() in response.data
    for endpoint in ("spectrum-upload", "spectrum-upload/remove", "spectrum-fit"):
        response = client.post(f"/{endpoint}/{model_dir.name}", data={})
        assert response.status_code == 302
        assert f"/spectrum/{model_dir.name}" in response.headers["Location"]


def test_core_routes_index_docs_view_raw_download(tmp_path: Path) -> None:
    model_dir = tmp_path / "model_a"
    model_dir.mkdir()
    (model_dir / "RVTJ").write_text(
        """ND: 2
Radius
1 2
Velocity
10 20
""",
        encoding="utf-8",
    )

    app = _make_app(tmp_path)
    client = app.test_client()

    index_response = client.get("/", follow_redirects=False)
    assert index_response.status_code == 302
    assert "/view/" in index_response.headers["Location"]

    docs_root = client.get("/documentation/", follow_redirects=False)
    assert docs_root.status_code == 302
    assert "/documentation/" in docs_root.headers["Location"]

    docs_missing = client.get("/documentation/not-a-real-doc")
    assert docs_missing.status_code == 404

    list_response = client.get("/view/model_a")
    assert list_response.status_code == 200
    assert b"RVTJ" in list_response.data

    file_response = client.get("/view/model_a/RVTJ")
    assert file_response.status_code == 200
    assert b"RVTJ" in file_response.data

    raw_response = client.get("/raw/model_a/RVTJ")
    assert raw_response.status_code == 200
    assert b"ND: 2" in raw_response.data

    download_response = client.get("/download/model_a/RVTJ")
    assert download_response.status_code == 200
    assert "attachment;" in download_response.headers.get("Content-Disposition", "")

    missing_response = client.get("/view/missing")
    assert missing_response.status_code == 404


def test_upload_routes_end_to_end_for_photometry(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    uploads_response = client.get("/uploads/")
    assert uploads_response.status_code == 200

    no_file = client.post("/uploads/upload", data={}, follow_redirects=False)
    assert no_file.status_code == 302
    assert "No+file+selected+for+upload." in no_file.headers["Location"]

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n6000 100 1.2\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    assert "Uploaded+obs.phot." in upload_response.headers["Location"]

    manifests = list_upload_manifests(upload_root)
    assert len(manifests) == 1
    token = str(manifests[0]["token"])

    view_response = client.get(f"/uploads/view/{token}")
    assert view_response.status_code == 200

    update_response = client.post(
        f"/uploads/update-photometry/{token}",
        data={
            "photometry_table": "5000 100 2.0\n",
            "photometry_name": "updated.phot",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302
    assert f"/uploads/view/{token}" in update_response.headers["Location"]

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert manifest["filename"] == "updated.phot"
    assert "updated_at" in manifest

    delete_response = client.post(f"/uploads/delete/{token}", follow_redirects=False)
    assert delete_response.status_code == 302
    assert not (upload_root / token).exists()


def test_update_photometry_allows_clearing_table(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n6000 100 1.2\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    assert len(manifests) == 1
    token = str(manifests[0]["token"])

    clear_response = client.post(
        f"/uploads/update-photometry/{token}",
        data={
            "photometry_table": "",
            "photometry_name": "cleared.phot",
        },
        follow_redirects=False,
    )
    assert clear_response.status_code == 302
    assert f"/uploads/view/{token}" in clear_response.headers["Location"]

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert manifest["filename"] == "cleared.phot"
    assert int(manifest["points"]) == 0

    stored_path = upload_root / token / str(manifest["stored_name"])
    assert stored_path.read_text(encoding="utf-8") == ""

    view_response = client.get(f"/uploads/view/{token}")
    assert view_response.status_code == 200
    assert b"No photometry points yet" in view_response.data


def test_update_photometry_preserves_vizier_state_in_redirect(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    update_response = client.post(
        f"/uploads/update-photometry/{token}",
        data={
            "photometry_table": "5000 100 2.0\n",
            "photometry_name": "stateful.phot",
            "vizier_center": "11:22:33 +44:55:06",
            "vizier_radius_arcsec": "7.5",
            "vizier_table_ids": "II/122B/merged, J/ApJ/123/456/table1",
            "vizier_catalog": ["gaia_dr3_syntphot", "twomass"],
            "vizier_all_catalogs": "1",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302
    location = update_response.headers["Location"]
    assert "Photometry+data+updated." in location
    query = parse_qs(urlparse(location).query)
    assert query.get("vizier_center") == ["11:22:33 +44:55:06"]
    assert query.get("vizier_radius_arcsec") == ["7.5"]
    assert query.get("vizier_table_ids") == ["II/122B/merged, J/ApJ/123/456/table1"]
    assert query.get("vizier_all_catalogs") == ["1"]
    assert sorted(query.get("vizier_catalog", [])) == ["gaia_dr3_syntphot", "twomass"]


def test_upload_photometry_allows_empty_then_append_from_vizier(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload-photometry",
        data={
            "photometry_name": "empty.phot",
            "photometry_table": "",
        },
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    assert "Uploaded+photometry+empty.phot." in upload_response.headers["Location"]

    manifests = list_upload_manifests(upload_root)
    assert len(manifests) == 1
    token = str(manifests[0]["token"])
    assert int(manifests[0]["points"]) == 0

    view_response = client.get(f"/uploads/view/{token}")
    assert view_response.status_code == 200
    assert b"No photometry points yet" in view_response.data

    def _fake_query(**_kwargs):
        return [
            VizierPhotometryPoint(
                lambda_eff_a=5109.0,
                band_width_a=2157.0,
                flux=8.0e-13,
                flux_err=6.0e-14,
                comment="Gaia DR3 syntphot BP",
            )
        ]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)
    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "empty.phot",
            "photometry_table": "",
            "vizier_center": "120.5 -20.25",
            "vizier_radius_arcsec": "5",
            "vizier_catalog": ["gaia_dr3_syntphot"],
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    assert "Appended+1+VizieR+photometry+point" in append_response.headers["Location"]

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert int(manifest["points"]) == 1
    content = (upload_root / token / str(manifest["stored_name"])).read_text(encoding="utf-8")
    assert "Gaia DR3 syntphot BP" in content


def test_append_vizier_photometry_route_appends_rows(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302

    manifests = list_upload_manifests(upload_root)
    assert len(manifests) == 1
    token = str(manifests[0]["token"])

    captured: dict[str, object] = {}

    def _fake_query(**kwargs):
        captured.update(kwargs)
        return [
            VizierPhotometryPoint(
                lambda_eff_a=4810.0,
                band_width_a=1530.0,
                flux=1.0e-12,
                flux_err=1.0e-13,
                comment="Pan-STARRS g",
            )
        ]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)

    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "updated.phot",
            "photometry_table": "5000 100 1.0\n",
            "vizier_center": "12:00:00 +15:00:00",
            "vizier_radius_arcsec": "5",
            "vizier_table_ids": "II/122B/merged, J/ApJ/123/456/table1",
            "vizier_catalog": ["gaia_dr3_syntphot", "panstarrs_dr1"],
            "vizier_all_catalogs": "1",
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    location = append_response.headers["Location"]
    assert "Appended+1+VizieR+photometry+point" in location
    parsed_query = parse_qs(urlparse(location).query)
    assert parsed_query.get("vizier_center") == ["12:00:00 +15:00:00"]
    assert parsed_query.get("vizier_radius_arcsec") == ["5"]
    assert parsed_query.get("vizier_table_ids") == ["II/122B/merged, J/ApJ/123/456/table1"]
    assert parsed_query.get("vizier_all_catalogs") == ["1"]
    assert sorted(parsed_query.get("vizier_catalog", [])) == ["gaia_dr3_syntphot", "panstarrs_dr1"]

    assert captured["include_all_catalogs"] is True
    assert captured["catalog_keys"] == ["gaia_dr3_syntphot", "panstarrs_dr1"]
    assert captured["source_ids"] == ["II/122B/merged", "J/ApJ/123/456/table1"]
    assert captured["radius_arcsec"] == 5.0

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert manifest["filename"] == "updated.phot"
    assert int(manifest["points"]) == 2

    stored_name = str(manifest["stored_name"])
    stored_path = upload_root / token / stored_name
    content = stored_path.read_text(encoding="utf-8")
    assert "Pan-STARRS g" in content
    assert "5000 100 1.0" in content


def test_append_vizier_photometry_uses_current_textarea_state_even_if_empty(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    def _fake_query(**_kwargs):
        return [
            VizierPhotometryPoint(
                lambda_eff_a=5500.0,
                band_width_a=800.0,
                flux=1.0e-12,
                flux_err=1.0e-13,
                comment="Gaia DR3 syntphot G",
            )
        ]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)

    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "cleared-then-appended.phot",
            "photometry_table": "",
            "vizier_center": "120.5 -20.25",
            "vizier_radius_arcsec": "5",
            "vizier_catalog": ["gaia_dr3_syntphot"],
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    assert "Appended+1+VizieR+photometry+point" in append_response.headers["Location"]

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert int(manifest["points"]) == 1
    stored = (upload_root / token / str(manifest["stored_name"])).read_text(encoding="utf-8")
    assert "5000 100 1.0" not in stored
    assert "Gaia DR3 syntphot G" in stored


def test_append_vizier_photometry_requires_selected_catalog_or_all(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_table": "5000 100 1.0\n",
            "vizier_center": "120.5 -20.25",
            "vizier_radius_arcsec": "5",
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    location = append_response.headers["Location"]
    assert "Select+at+least+one+VizieR+catalog+or+specify+VizieR+table+IDs." in location
    parsed_query = parse_qs(urlparse(location).query)
    assert parsed_query.get("vizier_center") == ["120.5 -20.25"]
    assert parsed_query.get("vizier_radius_arcsec") == ["5"]


def test_append_vizier_photometry_deduplicates_against_disabled_existing_row(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (
                io.BytesIO(
                    b"4810.000 1530.000 1.00000000e-12 1.00000000e-13 1 # Pan-STARRS g\n"
                    b"5500.000 800.000 2.00000000e-12 2.00000000e-13 1 # Keep enabled\n",
                ),
                "obs.phot",
            ),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    def _fake_query(**_kwargs):
        return [
            VizierPhotometryPoint(
                lambda_eff_a=4810.0,
                band_width_a=1530.0,
                flux=1.0e-12,
                flux_err=1.0e-13,
                comment="Pan-STARRS g",
            )
        ]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)

    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "dedup-flag.phot",
            "photometry_table": (
                "4810.000 1530.000 1.00000000e-12 1.00000000e-13 0 # Pan-STARRS g\n"
                "5500.000 800.000 2.00000000e-12 2.00000000e-13 1 # Keep enabled\n"
            ),
            "vizier_center": "120.5 -20.25",
            "vizier_radius_arcsec": "5",
            "vizier_catalog": ["panstarrs_dr1"],
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    location = append_response.headers["Location"]
    assert "Photometry+data+updated.+No+new+rows+appended." in location
    assert "Skipped+1+duplicate+VizieR+row" in location

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert int(manifest["points"]) == 1
    stored = (upload_root / token / str(manifest["stored_name"])).read_text(encoding="utf-8")
    assert " 0 # Pan-STARRS g" in stored
    assert " 1 # Pan-STARRS g" not in stored
    assert "Keep enabled" in stored


def test_append_vizier_photometry_accepts_manual_table_ids_only(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    captured: dict[str, object] = {}

    def _fake_query(**kwargs):
        captured.update(kwargs)
        return [
            VizierPhotometryPoint(
                lambda_eff_a=5500.0,
                band_width_a=800.0,
                flux=1.0e-12,
                flux_err=1.0e-13,
                comment="Custom catalog entry",
            )
        ]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)

    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "manual-id.phot",
            "photometry_table": "5000 100 1.0\n",
            "vizier_center": "120.5 -20.25",
            "vizier_radius_arcsec": "5",
            "vizier_table_ids": "II/122B/merged",
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    assert "Appended+1+VizieR+photometry+point" in append_response.headers["Location"]

    assert captured["catalog_keys"] == []
    assert captured["source_ids"] == ["II/122B/merged"]


def test_append_vizier_photometry_skips_fully_duplicate_rows_textually(tmp_path: Path, monkeypatch) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()
    upload_root = Path(app.config["CMFGEN_VIEWER"]["upload_root"])

    upload_response = client.post(
        "/uploads/upload",
        data={
            "observed_file": (io.BytesIO(b"5000 100 1.0\n"), "obs.phot"),
            "flux_mode": "auto",
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302
    manifests = list_upload_manifests(upload_root)
    token = str(manifests[0]["token"])

    duplicate_point = VizierPhotometryPoint(
        lambda_eff_a=4810.0,
        band_width_a=1530.0,
        flux=1.0e-12,
        flux_err=1.0e-13,
        comment="Pan-STARRS g",
    )

    def _fake_query(**_kwargs):
        return [duplicate_point, duplicate_point]

    monkeypatch.setattr("cmfgen_viewer.upload_views.query_vizier_photometry_points", _fake_query)
    append_response = client.post(
        f"/uploads/append-vizier-photometry/{token}",
        data={
            "photometry_name": "dedup.phot",
            "photometry_table": "5000 100 1.0\n",
            "vizier_center": "12:00:00 +15:00:00",
            "vizier_radius_arcsec": "5",
            "vizier_catalog": ["panstarrs_dr1"],
        },
        follow_redirects=False,
    )
    assert append_response.status_code == 302
    location = append_response.headers["Location"]
    assert "Appended+1+VizieR+photometry+point" in location
    assert "Skipped+1+duplicate+row" in location

    manifest = read_upload_manifest(upload_root, token)
    assert isinstance(manifest, dict)
    assert int(manifest["points"]) == 2
    stored = (upload_root / token / str(manifest["stored_name"])).read_text(encoding="utf-8")
    assert stored.count("Pan-STARRS g") == 1


def test_upload_grid_endpoints_return_not_found_for_missing_jobs_and_tokens(tmp_path: Path) -> None:
    app = _make_app(tmp_path)
    client = app.test_client()

    status_response = client.get("/uploads/fit-grid/status/missing-job")
    assert status_response.status_code == 404
    assert status_response.get_json()["ok"] is False

    overlay_response = client.get("/uploads/fit-grid/overlay/missing-job")
    assert overlay_response.status_code == 404
    assert overlay_response.get_json()["ok"] is False

    cancel_response = client.post("/uploads/fit-grid/cancel/missing-job")
    assert cancel_response.status_code == 404
    assert cancel_response.get_json()["ok"] is False

    match_count_invalid = client.get("/uploads/fit-grid/match-count/bad")
    assert match_count_invalid.status_code == 404

    upload_view_invalid = client.get("/uploads/view/bad")
    assert upload_view_invalid.status_code == 404
