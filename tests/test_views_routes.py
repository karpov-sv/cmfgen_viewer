from __future__ import annotations

import io
from pathlib import Path

from cmfgen_viewer.app import create_app
from cmfgen_viewer.observed_spectrum import list_upload_manifests, read_upload_manifest


def _make_app(tmp_path: Path):
    app = create_app(basepath=str(tmp_path), secret_key="test-secret")
    app.testing = True
    config = app.config["CMFGEN_VIEWER"]
    config["upload_root"] = str((tmp_path / "uploads").resolve())
    config["summary_cache_db"] = str((tmp_path / "summary.sqlite").resolve())
    return app


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
