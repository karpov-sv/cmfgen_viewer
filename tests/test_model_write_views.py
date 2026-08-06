from __future__ import annotations

from pathlib import Path

from cmfgen_viewer.app import create_app
from cmfgen_viewer.summary_cache import inspect_model_summary_entry, upsert_model_summary


def _make_app(tmp_path: Path, *, read_write: bool):
    app = create_app(basepath=str(tmp_path), secret_key="test-secret", read_write_enabled=read_write)
    app.testing = True
    app.config["CMFGEN_VIEWER"]["summary_cache_db"] = str(tmp_path / "summary.sqlite")
    return app


def _write_solution(source: Path, *, sn: bool = False) -> None:
    source.mkdir(parents=True)
    for name in ("batch.sh", "IN_ITS", "VADAT", "MODEL_SPEC", "GAMMAS", "HeIOUT"):
        (source / name).write_text(f"{name}\n", encoding="utf-8")
    if sn:
        (source / "SN_HYDRO_DATA").write_text("sn\n", encoding="utf-8")


def test_create_from_solution_route_previews_and_creates_model(tmp_path: Path) -> None:
    _write_solution(tmp_path / "grid" / "model_a")
    app = _make_app(tmp_path, read_write=True)
    client = app.test_client()

    source_page = client.get("/view/grid/model_a")
    assert source_page.status_code == 200
    assert b"New Model from Current" in source_page.data
    assert b"Model actions:" in source_page.data
    assert b"Rename / Move Model" in source_page.data
    assert b'/model-actions/create/grid/model_a' in source_page.data
    assert b'/model-actions/rename/grid/model_a' in source_page.data

    preview = client.post(
        "/model-actions/create/grid/model_a",
        data={"action": "preview", "destination_relpath": "grid/model_b"},
    )
    assert preview.status_code == 200
    assert b"Copy Preview" in preview.data
    assert b"GAMMAS_IN" in preview.data
    assert b"HeI_IN" in preview.data

    response = client.post(
        "/model-actions/create/grid/model_a",
        data={"action": "create", "destination_relpath": "grid/model_b"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/view/grid/model_b?created=1"
    assert (tmp_path / "grid" / "model_b" / "MODEL_SPEC").is_file()

    created_page = client.get(response.headers["Location"])
    assert created_page.status_code == 200
    assert b"New model created from the selected solution" in created_page.data


def test_create_from_solution_requires_read_write_mode(tmp_path: Path) -> None:
    _write_solution(tmp_path / "model_a")
    app = _make_app(tmp_path, read_write=False)
    client = app.test_client()

    source_page = client.get("/view/model_a")
    assert source_page.status_code == 200
    assert b"Model-directory read-write mode is disabled" in source_page.data
    assert b'/model-actions/create/model_a' not in source_page.data
    assert b'/model-actions/rename/model_a' not in source_page.data
    assert client.get("/model-actions/create/model_a").status_code == 403
    assert client.get("/model-actions/rename/model_a").status_code == 403
    assert not (tmp_path / "model_a_new").exists()


def test_create_from_solution_disables_and_rejects_sn_models(tmp_path: Path) -> None:
    _write_solution(tmp_path / "SN" / "model_sn", sn=True)
    app = _make_app(tmp_path, read_write=True)
    client = app.test_client()

    source_page = client.get("/view/SN/model_sn")
    assert source_page.status_code == 200
    assert b"Creating new models from SN solutions is not supported yet" in source_page.data
    assert b'/model-actions/create/SN/model_sn' not in source_page.data
    assert b'/model-actions/rename/SN/model_sn' in source_page.data

    create_page = client.get("/model-actions/create/SN/model_sn")
    assert create_page.status_code == 200
    assert b"Creating a model from an SN solution is not supported yet" in create_page.data


def test_created_model_replaces_stale_destination_cache_and_is_cached_after_run(tmp_path: Path) -> None:
    source = tmp_path / "grid" / "model_a"
    _write_solution(source)
    old_destination = tmp_path / "grid" / "model_b"
    old_destination.mkdir()
    (old_destination / "VADAT").write_text("old [LSTAR]\n", encoding="utf-8")
    (old_destination / "MOD_SUM").write_text("old summary\n", encoding="utf-8")

    app = _make_app(tmp_path, read_write=True)
    config = app.config["CMFGEN_VIEWER"]
    db_path = str(config["summary_cache_db"])
    basepath = str(config["basepath"])
    upsert_model_summary(
        db_path,
        basepath=basepath,
        relpath="grid/model_b",
        model_dir=old_destination,
        model_name="old-model-b",
        values=["old-model-b"],
        vadat_mtime=(old_destination / "VADAT").stat().st_mtime,
        mod_sum_mtime=(old_destination / "MOD_SUM").stat().st_mtime,
    )
    (old_destination / "VADAT").unlink()
    (old_destination / "MOD_SUM").unlink()
    old_destination.rmdir()

    client = app.test_client()
    created = client.post(
        "/model-actions/create/grid/model_a",
        data={"action": "create", "destination_relpath": "grid/model_b"},
        follow_redirects=True,
    )
    assert created.status_code == 200
    new_destination = tmp_path / "grid" / "model_b"
    assert not (new_destination / "MOD_SUM").exists()
    assert inspect_model_summary_entry(
        db_path,
        basepath=basepath,
        relpath="grid/model_b",
    )["status"] == "absent"

    (new_destination / "MOD_SUM").write_text("new summary\n", encoding="utf-8")
    visited = client.get("/view/grid/model_b")
    assert visited.status_code == 200
    cached = inspect_model_summary_entry(
        db_path,
        basepath=basepath,
        relpath="grid/model_b",
    )
    assert cached["status"] == "valid"
    assert cached["model_name"] == "model_b"


def test_rename_model_route_moves_cache_entry_and_redirects(tmp_path: Path) -> None:
    source = tmp_path / "grid" / "model_a"
    _write_solution(source)
    (source / "MOD_SUM").write_text("summary\n", encoding="utf-8")
    (tmp_path / "archive").mkdir()
    app = _make_app(tmp_path, read_write=True)
    client = app.test_client()
    config = app.config["CMFGEN_VIEWER"]
    db_path = str(config["summary_cache_db"])
    basepath = str(config["basepath"])

    assert client.get("/view/grid/model_a").status_code == 200
    assert inspect_model_summary_entry(
        db_path, basepath=basepath, relpath="grid/model_a"
    )["status"] == "valid"
    rename_page = client.get("/model-actions/rename/grid/model_a")
    assert rename_page.status_code == 200
    assert b"Rename or Move Model" in rename_page.data
    assert b'value="grid/model_a"' in rename_page.data

    renamed = client.post(
        "/model-actions/rename/grid/model_a",
        data={"destination_relpath": "archive/model_b"},
        follow_redirects=False,
    )
    assert renamed.status_code == 302
    assert renamed.headers["Location"] == "/view/archive/model_b?renamed=1"
    assert not source.exists()
    assert (tmp_path / "archive" / "model_b" / "MODEL_SPEC").is_file()
    assert inspect_model_summary_entry(
        db_path, basepath=basepath, relpath="grid/model_a"
    )["status"] == "absent"
    new_cache = inspect_model_summary_entry(
        db_path, basepath=basepath, relpath="archive/model_b"
    )
    assert new_cache["status"] == "valid"
    assert new_cache["model_name"] == "model_b"

    result_page = client.get(renamed.headers["Location"])
    assert result_page.status_code == 200
    assert b"Model directory renamed or moved successfully" in result_page.data


def test_rename_model_route_rejects_existing_name_without_moving_source(tmp_path: Path) -> None:
    _write_solution(tmp_path / "model_a")
    (tmp_path / "model_b").mkdir()
    app = _make_app(tmp_path, read_write=True)

    response = app.test_client().post(
        "/model-actions/rename/model_a",
        data={"destination_relpath": "model_b"},
    )

    assert response.status_code == 200
    assert b"already exists" in response.data
    assert (tmp_path / "model_a").is_dir()
