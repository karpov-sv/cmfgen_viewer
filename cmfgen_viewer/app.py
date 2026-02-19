from __future__ import annotations

import secrets
from pathlib import Path
import tempfile

from flask import Flask


def create_app(
    *,
    basepath: str = ".",
    show_all: bool = False,
    lambda_min_angstrom: float = 800.0,
    lambda_max_angstrom: float = 20000.0,
    secret_key: str | None = None,
    fit_pool_size_max: int = 0,
) -> Flask:
    """Create Flask app for browsing CMFGEN model outputs."""
    app = Flask(__name__)
    default_summary_cache_db = (Path(__file__).resolve().parent.parent / "model_summary_cache.sqlite").resolve()

    app.config["CMFGEN_VIEWER"] = {
        "basepath": str(Path(basepath).expanduser().resolve()),
        "show_all": bool(show_all),
        "lambda_min_angstrom": float(lambda_min_angstrom),
        "lambda_max_angstrom": float(lambda_max_angstrom),
        "fit_pool_size_max": max(0, int(fit_pool_size_max)),
        "upload_root": str((Path(tempfile.gettempdir()) / "cmfgen_viewer_uploads").resolve()),
        "summary_cache_db": str(default_summary_cache_db),
    }
    app.secret_key = secret_key or secrets.token_hex(24)

    from .views import bp

    app.register_blueprint(bp)
    return app
