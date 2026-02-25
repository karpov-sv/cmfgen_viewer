from __future__ import annotations

import base64
from pathlib import Path

from cmfgen_viewer.app import create_app


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def test_create_app_sets_expected_config_values(tmp_path: Path) -> None:
    app = create_app(
        basepath=str(tmp_path),
        show_all=True,
        lambda_min_angstrom=1000.0,
        lambda_max_angstrom=9000.0,
        secret_key="fixed-secret",
        fit_pool_size_max=-4,
    )
    cfg = app.config["CMFGEN_VIEWER"]
    assert cfg["basepath"] == str(tmp_path.resolve())
    assert cfg["show_all"] is True
    assert cfg["lambda_min_angstrom"] == 1000.0
    assert cfg["lambda_max_angstrom"] == 9000.0
    assert cfg["fit_pool_size_max"] == 0
    assert app.secret_key == "fixed-secret"


def test_create_app_without_auth_allows_requests(tmp_path: Path) -> None:
    app = create_app(basepath=str(tmp_path), secret_key="x")
    client = app.test_client()
    response = client.get("/", follow_redirects=False)
    assert response.status_code != 401


def test_create_app_with_auth_challenges_and_accepts_valid_credentials(tmp_path: Path) -> None:
    app = create_app(
        basepath=str(tmp_path),
        secret_key="x",
        auth_username="viewer",
        auth_password="secret",
        auth_realm="CMFGEN Test",
    )
    client = app.test_client()

    no_auth = client.get("/", follow_redirects=False)
    assert no_auth.status_code == 401
    assert no_auth.headers["WWW-Authenticate"] == 'Basic realm="CMFGEN Test"'

    wrong_auth = client.get("/", headers=_basic_auth_header("viewer", "wrong"), follow_redirects=False)
    assert wrong_auth.status_code == 401

    wrong_user = client.get("/", headers=_basic_auth_header("other", "secret"), follow_redirects=False)
    assert wrong_user.status_code == 401

    ok_auth = client.get("/", headers=_basic_auth_header("viewer", "secret"), follow_redirects=False)
    assert ok_auth.status_code != 401
