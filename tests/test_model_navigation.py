from pathlib import Path

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_navigation import model_navigation_context


def make_model(path: Path):
    path.mkdir(parents=True)
    (path / "MODEL_SPEC").write_text("model\n")
    (path / "VADAT").write_text("1 [TEFF]\n")


@pytest.mark.parametrize("endpoint, section", [
    ("viewer.view", ""),
    ("viewer.model_parameters", "parameters"),
    ("viewer.model_lte_hydro", "lte"),
    ("viewer.model_main_computation", "main"),
    ("viewer.model_create_from_solution", "create"),
    ("viewer.model_rename", "rename"),
    ("viewer.model_cleanup", "cleanup"),
])
def test_workspace_navigation_returns_to_parent_model(tmp_path, endpoint, section):
    make_model(tmp_path / "grid" / "star")
    make_model(tmp_path / "grid" / "star" / "lte")
    nav = model_navigation_context(
        {"basepath": str(tmp_path), "read_write_enabled": True},
        endpoint, {"source_path": "grid/star/lte"},
    )
    assert nav["path"] == "grid/star"
    assert nav["active"] == section


def test_navigation_respects_scope_and_capabilities(tmp_path):
    make_model(tmp_path / "star")
    (tmp_path / "star" / "SN_HYDRO_DATA").write_text("sn\n")
    config = {"basepath": str(tmp_path), "read_write_enabled": False}
    nav = model_navigation_context(config, "viewer.model_workflow_plan", {
        "source_path": "star", "scope": "lte-hydro",
    })
    assert nav["active"] == "lte"
    assert not nav["read_write"]
    assert not nav["supports_staging"]
    assert not nav["has_spectrum"]
    assert model_navigation_context(config, "viewer.models", {}) is None
    assert model_navigation_context(config, "viewer.view", {"path": ""}) is None
    assert model_navigation_context(config, "viewer.view", {"path": "../star"}) is None


def test_folder_and_file_share_one_toolbar(tmp_path):
    make_model(tmp_path / "star")
    app = create_app(basepath=str(tmp_path), upload_root=str(tmp_path / "uploads"))
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "summary.sqlite")
    client = app.test_client()
    for path in ("star", "star/VADAT"):
        response = client.get(f"/view/{path}")
        assert response.status_code == 200
        html = response.data.decode()
        assert html.count('aria-label="Model workflow"') == 1
        assert 'href="/view/star"' in html
        assert 'disabled title="Model-directory read-write mode is disabled."' in html
    assert b'aria-label="Model workflow"' not in client.get("/view/").data
