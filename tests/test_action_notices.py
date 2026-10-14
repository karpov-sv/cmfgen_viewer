"""Action feedback is session-local, escaped, and consumed only by HTML pages."""

from urllib.parse import parse_qs, urlsplit

from flask import get_flashed_messages, redirect

from cmfgen_viewer.app import create_app
from cmfgen_viewer.view_common import _notification_url, _spectrum_redirect


def test_upload_error_shown_once_and_status_polling_does_not_consume_it(tmp_path):
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"), secret_key="test")
    client = app.test_client()
    response = client.post("/uploads/upload")
    assert response.headers["Location"] == "/uploads/"
    assert client.get("/tasks/status").status_code == 200
    assert b"No file selected for upload." not in app.test_client().get("/uploads/").data
    page = client.get(response.headers["Location"])
    assert b"No file selected for upload." in page.data
    assert b"alert-danger" in page.data
    assert b"No file selected for upload." not in client.get(response.headers["Location"]).data


def test_notices_preserve_anchor_escape_text_and_ignore_query_messages(tmp_path):
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"), secret_key="test")

    @app.post("/test-notice")
    def notice():
        return redirect(_notification_url("viewer.uploads", message="<script>example</script>",
                                         warning="Review inputs.", _anchor="uploads"))

    client = app.test_client()
    response = client.post("/test-notice")
    assert response.headers["Location"] == "/uploads/#uploads"
    page = client.get(response.headers["Location"])
    assert b"&lt;script&gt;example&lt;/script&gt;" in page.data
    assert b"<script>example</script>" not in page.data
    assert b"Review inputs." in page.data
    assert b"alert-warning" in page.data
    assert b"Review inputs." not in client.get("/uploads/").data
    assert b"query-notice" not in client.get("/uploads/?message=query-notice&error=query-notice").data


def test_spectrum_redirect_preserves_view_settings_without_message_parameters(tmp_path):
    app = create_app(basepath=str(tmp_path), secret_key="test")
    with app.test_request_context("/"):
        response = _spectrum_redirect("model_a", fin="obs_fin", mode="both", obs_tokens=["Token_0001"],
                                      transform_params={"redshift": 0.1},
                                      fit_wavelength_inputs={"min": "1200", "max": "5000"},
                                      upload_error="Review upload.", fit_notice="Fit completed.")
        query = parse_qs(urlsplit(response.headers["Location"]).query)
        assert query["fin"] == ["obs_fin"]
        assert query["obs"] == ["Token_0001"]
        assert query["redshift"] == ["0.1"]
        assert query["fit_lambda_min"] == ["1200"]
        assert "upload_error" not in query and "fit_notice" not in query
        assert get_flashed_messages(with_categories=True) == [("danger", "Review upload."), ("success", "Fit completed.")]
