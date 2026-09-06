from pathlib import Path
import shlex
from types import SimpleNamespace

import pytest

from cmfgen_viewer.app import create_app
from cmfgen_viewer import workflow_preflight as preflight
from cmfgen_viewer.workflow_plan import build_workflow_plan, external_stage_command


@pytest.fixture
def model(tmp_path, monkeypatch):
    for key in ("cmfdist", "ATOMIC", "atomic"):
        monkeypatch.delenv(key, raising=False)
    root = tmp_path / "model_a"
    (root / "obs").mkdir(parents=True)
    (root / "lte").mkdir()
    files = {"VADAT": "3D0 [TEFF]\n3.5 [LOGG]\nF [CHK_NG]\n1 [RSTAR]\n",
             "MODEL_SPEC": "2 [ND]\n1 [NC]\n3 [NP]\n", "IN_ITS": "10 [NUM_ITS]\n",
             "GAMMAS_IN": "gamma\n", "HI_IN": "population\n", "MODEL": "model\n", "RVTJ": "result\n",
             "batch.sh": "#!/bin/sh\nsource batch_ins.sh\ncd obs\n./batobs.sh\n",
             "batch_ins.sh": "ln -sf $atomic/hyd.dat HYD_L_DATA\n",
             "lte/ltebat.sh": "#!/bin/sh\n../batch.sh ass\n",
             "lte/GRID_PARAMS": "grid\n", "lte/HYDRO_PARAMS": "hydro\n",
             "obs/batobs.sh": "#!/bin/sh\nsource bat_ins.sh\n",
             "obs/bat_ins.sh": "mv -f OBSFRAME obs_fin_15\nrm -f fort.*\n",
             "obs/CMF_FLUX_PARAM_INIT": "F [FLUX_CAL_ONLY]\n", "obs/IN_FILE": "input\n"}
    files.update({"lte/" + name: files[name] for name in ("VADAT", "MODEL_SPEC")})
    for name, text in files.items():
        target = root / name
        target.write_text(text)
        if name.endswith(".sh"):
            target.chmod(0o755)
    return root


def _snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_mode)
            for path in root.rglob("*") if path.is_file()}


def test_plan_html_json_are_read_only_and_never_execute_scripts(model):
    before = _snapshot(model)
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key="test")
    app.testing = True
    with app.test_client() as client:
        for scope in ("main", "lte-hydro", "flux"):
            route = f"/model-actions/plan/{scope}/model_a"
            html = client.get(route)
            assert html.status_code == 200
            assert b"Preview only" in html.data
            response = client.get(route + "?format=json")
            assert response.status_code == 200
            assert response.headers["Cache-Control"] == "no-store"
            plan = response.get_json()
            assert plan["execution_available"] is False
            assert plan["schema_version"] == 1
            assert client.post(route).status_code == 405
    assert _snapshot(model) == before
    assert not (model / ".cmfgen-viewer-write.lock").exists()


def test_main_plan_includes_nested_flux_and_literal_cleanup(model):
    plan = build_workflow_plan(str(model.parent), model_relpath=model.name, scope="main")
    assert [step["id"] for step in plan["steps"]] == ["main", "flux"]
    flux = plan["steps"][1]
    assert flux["invoked_by"] == "main" and flux["command"] is None
    effects = flux["script_dependencies"]["effects"]
    assert any(item["shell_text"] == "mv -f OBSFRAME obs_fin_15" for item in effects)
    assert any(item["shell_text"] == "rm -f fort.*" for item in effects)
    assert flux["opaque_shell_effects"] and not flux["verification_complete"]
    assert plan["steps"][0]["input_snapshot"][0]["sha256"]
    assert {Path(item["path"]).name for item in plan["steps"][0]["input_snapshot"]} >= {"batch_ins.sh", "GAMMAS_IN", "HI_IN"}


def test_lte_hydro_contract_dependencies_and_interactive_depth(model):
    plan = build_workflow_plan(str(model.parent), model_relpath=model.name, scope="lte-hydro")
    assert [step["id"] for step in plan["steps"]] == ["prepare", "lte", "hydro", "review-promote"]
    assert plan["steps"][2]["depends_on"] == ["lte"]
    assert plan["steps"][2]["stdin"]["suggested_answers"][2] == 2
    assert plan["steps"][-1]["approval_required"]
    assert not plan["steps"][-1]["ready"]


def test_plan_routes_validate_scope_path_and_mode(model):
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key="test")
    with app.test_client() as client:
        for path in ("unknown/model_a", "main/missing", "main/../model_a"):
            assert client.get("/model-actions/plan/" + path).status_code == 404
    app = create_app(basepath=str(model.parent), read_write_enabled=False, secret_key="test")
    assert app.test_client().get("/model-actions/plan/main/model_a").status_code == 403


def test_command_quotes_model_paths():
    path = Path("/tmp/model 'with space;$(touch danger)")
    assert shlex.split(external_stage_command(path, "lte"))[1] == str(path / "lte")


def test_preflight_executable_and_atomic_targets(model, tmp_path):
    config = {"cmfgen_root": str(tmp_path / "cmf"), "atomic_root": str(tmp_path / "atomic")}
    result = preflight.inspect_stage_preflight(model, "main", config=config)
    assert {"executable-unavailable", "link-target-not-file"} <= {i["code"] for i in result["issues"]}
    exe = tmp_path / "cmf/exe/cmfgen_dev.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("must never run")
    exe.chmod(0o755)
    (tmp_path / "atomic").mkdir()
    (tmp_path / "atomic/hyd.dat").write_text("data")
    result = preflight.inspect_stage_preflight(model, "main", config=config)
    assert not result["blocking"]
    assert result["executable"] == str(exe)


def test_lte_preflight_checks_controls_script_and_parent(model):
    (model / "lte/ltebat.sh").chmod(0o644)
    (model / "batch.sh").chmod(0o644)
    (model / "lte/VADAT").write_text("-1 [TEFF]\n1e999 [LOGG]\nmaybe [CHK_NG]\n")
    (model / "lte/MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n9 [NP]\n")
    codes = {i["code"] for i in preflight.inspect_stage_preflight(model, "lte")["issues"]}
    assert {"lte-control-value", "lte-grid", "stage-script-not-executable", "parent-link-script"} <= codes


def test_preflight_missing_source_and_interpreter(model):
    (model / "batch.sh").write_text("#!/no/such/interpreter\nsource missing.sh\n")
    codes = {i["code"] for i in preflight.inspect_stage_preflight(model, "main")["issues"]}
    assert {"script-interpreter", "sourced-file-missing"} <= codes


def test_unknown_environment_and_dynamic_shell_are_explicit(model):
    result = preflight.inspect_stage_preflight(model, "main")
    codes = {i["code"] for i in result["issues"]}
    assert {"atomic-root-unresolved", "executable-unresolved", "link-target-unresolved"} <= codes
    script = model / "dynamic.sh"
    script.write_text("source `touch NEVER_RUN`\nln -sf $unknown/data DATA\n")
    deps = preflight.inspect_script_dependencies(script, model, {})
    assert deps["links"][0]["target"] is None
    assert not (model / "NEVER_RUN").exists()


def test_disk_and_activity_preflight(model, monkeypatch):
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    result = preflight.inspect_stage_preflight(model, "main", activity={"safe_to_modify": False, "reason": "active"})
    assert {"disk-space-critical", "model-not-idle"} <= {i["code"] for i in result["issues"]}
