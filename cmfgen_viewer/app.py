from __future__ import annotations

import hmac
import secrets
from pathlib import Path
import tempfile

from flask import Flask, Response, request


def create_app(
    *,
    basepath: str = ".",
    show_all: bool = False,
    lambda_min_angstrom: float = 800.0,
    lambda_max_angstrom: float = 250000.0,
    upload_root: str | None = None,
    secret_key: str | None = None,
    fit_pool_size_max: int = 0,
    auth_username: str | None = None,
    auth_password: str | None = None,
    auth_realm: str = "CMFGEN Viewer",
) -> Flask:
    """Create Flask app for browsing CMFGEN model outputs."""
    app = Flask(__name__)
    default_summary_cache_db = (Path(__file__).resolve().parent.parent / "model_summary_cache.sqlite").resolve()
    default_upload_root = (Path(tempfile.gettempdir()) / "cmfgen_viewer_uploads").resolve()
    configured_upload_root = (
        Path(upload_root).expanduser().resolve()
        if isinstance(upload_root, str) and upload_root.strip()
        else default_upload_root
    )
    auth_user = auth_username if isinstance(auth_username, str) else ""
    auth_pass = auth_password if isinstance(auth_password, str) else ""
    auth_enabled = bool(auth_user and auth_pass)
    auth_realm_text = str(auth_realm or "CMFGEN Viewer")

    app.config["CMFGEN_VIEWER"] = {
        "basepath": str(Path(basepath).expanduser().resolve()),
        "show_all": bool(show_all),
        "lambda_min_angstrom": float(lambda_min_angstrom),
        "lambda_max_angstrom": float(lambda_max_angstrom),
        "fit_pool_size_max": max(0, int(fit_pool_size_max)),
        "upload_root": str(configured_upload_root),
        "summary_cache_db": str(default_summary_cache_db),
        "auth_enabled": auth_enabled,
        "auth_realm": auth_realm_text,
    }
    app.secret_key = secret_key or secrets.token_hex(24)

    if auth_enabled:

        def auth_challenge_response() -> Response:
            return Response(
                "Authorization required.\n",
                401,
                {
                    "WWW-Authenticate": f'Basic realm="{auth_realm_text}"',
                    "Cache-Control": "no-store",
                },
            )

        @app.before_request
        def _require_http_basic_auth() -> Response | None:
            auth = request.authorization
            if auth is None or str(auth.type or "").lower() != "basic":
                return auth_challenge_response()

            username = str(auth.username or "")
            password = str(auth.password or "")
            if not hmac.compare_digest(username, auth_user):
                return auth_challenge_response()
            if not hmac.compare_digest(password, auth_pass):
                return auth_challenge_response()
            return None

    from .views import bp

    app.register_blueprint(bp)
    return app
