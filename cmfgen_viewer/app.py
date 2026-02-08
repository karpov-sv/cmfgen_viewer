from __future__ import annotations

import secrets
from pathlib import Path

from flask import Flask


def create_app(
    *,
    basepath: str = ".",
    show_all: bool = False,
    secret_key: str | None = None,
) -> Flask:
    """Create Flask app for browsing CMFGEN model outputs."""
    app = Flask(__name__)

    app.config["CMFGEN_VIEWER"] = {
        "basepath": str(Path(basepath).expanduser().resolve()),
        "show_all": bool(show_all),
    }
    app.secret_key = secret_key or secrets.token_hex(24)

    from .views import bp

    app.register_blueprint(bp)
    return app
