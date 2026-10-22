import json
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

from cmfgen_viewer.app import create_app
from cmfgen_viewer.model_initialization import lte_initialization_controls
from cmfgen_viewer.model_editor import ModelEditorError
from cmfgen_viewer.model_quick_editor import load_quick_model_parameter_cards, review_quick_model_parameter_edit
from cmfgen_viewer.native_crash import macos_crash_evidence
from cmfgen_viewer.native_diagnostics import analyze_main_diagnostics
from cmfgen_viewer.runner import run_plan
from cmfgen_viewer.runner import build_sequence_plan
from cmfgen_viewer.runner_job_views import parse_options
from cmfgen_viewer.runner_recipe import RunnerError
from test_runner import workspace, SUCCESS


def test_initialization_preserves_comments_and_appends_missing_controls():
    text = "F [LIN_INT] !fresh\nED   [DC_METH] !interpolation\n"
    changed = lte_initialization_controls(text, 0.8)
    assert "LTE   [DC_METH] !interpolation" in changed
    assert "0.8           [T_EXC]" in changed
    assert changed.count("[DC_METH]") == 1
    assert lte_initialization_controls(changed, 0.8) == changed


@pytest.mark.parametrize("text,t_exc", [("ED [DC_METH]\nR [DC_METH]\n", 1),
                                         ("T [LIN_INT]\n", 1), ("T [LTE_EST]\n", 1),
                                         ("", float("nan")), ("", 0)])
def test_unsafe_or_inapplicable_initialization_is_rejected(text, t_exc):
    with pytest.raises(ValueError):
        lte_initialization_controls(text, t_exc)


@pytest.mark.parametrize("ending,expected,timeout", [(SUCCESS, "tested", None),
                                                      ("raise SystemExit(7)", "failed", None),
                                                      ("import time; time.sleep(20)", "timeout", 0.5)])
def test_runner_uses_and_restores_initialization_on_all_exit_paths(workspace, ending, expected, timeout):
    model, make_plan = workspace
    vadat = model / "VADAT"
    original = vadat.read_bytes()
    original_stat = vadat.stat()
    code = "from pathlib import Path\nv=Path('VADAT').read_text()\nassert 'LTE' in v and '[DC_METH]' in v and '[T_EXC]' in v\n" + ending
    plan = make_plan(code, lte_initialization=True, t_exc=0.8, timeout=timeout)
    assert plan["ready"], plan["errors"]
    result = run_plan(plan)
    assert result["status"] == expected, result
    assert vadat.read_bytes() == original
    assert vadat.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert vadat.stat().st_mode == original_stat.st_mode
    effective = Path(result["journal"]) / "effective/VADAT"
    assert "LTE" in effective.read_text()
    assert "0.8" in effective.read_text()
    assert (Path(result["journal"]) / "inputs/VADAT").read_bytes() == original


def test_lte_option_requires_explicit_checkpoint_restart(workspace):
    model, make_plan = workspace
    (model / "POINT1").write_text("28-Feb-2004 !Format date\n2 9 1 -1000 F\nlabels\n")
    (model / "SCRTEMP").write_bytes(b"\0" * 4096)
    (model / "MODEL").write_text("2 !Number of depth points\nSpecies N_F N_S Z\nHI 5 3 1.0 1.0\n\f")
    blocked = make_plan(lte_initialization=True)
    assert not blocked["ready"]
    assert any("explicitly select --fresh-start" in e for e in blocked["errors"])
    assert make_plan(lte_initialization=True, fresh_start=True)["ready"]


def test_sequence_retains_lte_option_for_each_fresh_native_stage(workspace):
    model, make_plan = workspace
    make_plan("from pathlib import Path\nassert '[DC_METH]' in Path('VADAT').read_text()\n" + SUCCESS)
    plan = build_sequence_plan(model, ["test", "main"],
        native_config={"cmfgen_root": model.parent / "cmf", "atomic_root": model.parent / "atomic"},
        configuration_sources={}, timeout=None, iterations=None, fresh_start=False, cleanup_files=None,
        lte_initialization=True, t_exc=0.8)
    assert plan["stage_options"]["lte_initialization"]
    result = run_plan(plan)
    assert result["status"] == "succeeded", result
    assert all(r["initialization"]["t_exc"] == 0.8 for r in result["stage_results"])
    assert "[DC_METH]" not in (model / "VADAT").read_text()


def test_runner_web_option_is_explicit_and_temperature_validated():
    assert not parse_options(MultiDict(), ["main"])["lte_initialization"]
    selected = parse_options(MultiDict({"lte_initialization":"1", "t_exc":"0.8"}), ["main"])
    assert selected["lte_initialization"] and selected["t_exc"] == 0.8
    with pytest.raises(RunnerError):
        parse_options(MultiDict({"lte_initialization":"1", "t_exc":"NaN"}), ["main"])
    with pytest.raises(RunnerError):
        parse_options(MultiDict({"lte_initialization":"1"}), ["flux"])


def test_editor_initialization_fields_preview_and_save_with_backup(workspace):
    model, _ = workspace
    root = str(model.parent)
    app = create_app(basepath=root, read_write_enabled=True, secret_key="test")
    client = app.test_client()
    initial = (model / "VADAT").read_bytes()
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    values = {field["key"]: field["value"] for field in card["fields"]}
    values.update(DC_METH="LTE", T_EXC="0.8")
    data = {"action": "quick_preview", "quick_file_relpath": "VADAT", "expected_digest": card["digest"],
            **{f"quick_value:{key}": value for key, value in values.items()}}
    response = client.post("/model-actions/edit/model", data=data)
    assert response.status_code == 200
    assert b'Quick Change Review' in response.data
    assert (model / "VADAT").read_bytes() == initial
    review = review_quick_model_parameter_edit(root, model_relpath="model", file_relpath="VADAT",
                                              expected_digest=card["digest"], values=values)
    saved = client.post("/model-actions/edit/model", data={**data, "action": "quick_save", "reviewed_digest": review["proposed_digest"]})
    assert saved.status_code == 302
    contents = (model / "VADAT").read_text()
    assert "LTE" in contents and "0.8" in contents
    assert list((model / ".cmfgen-viewer-backups").rglob("VADAT.*.bak"))


def test_missing_initialization_controls_stay_unset_for_normal_edits(workspace):
    model, _ = workspace
    root = str(model.parent)
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    values = {f["key"]: f["value"] for f in card["fields"]}
    assert values["DC_METH"] == values["T_EXC"] == ""
    assert values["LIN_INT"] == values["POP_SCALE"] == ""
    args = dict(model_relpath="model", file_relpath="VADAT", expected_digest=card["digest"], values=values)
    assert not review_quick_model_parameter_edit(root, **args)["changed"]
    values["RSTAR"] = "2"
    review = review_quick_model_parameter_edit(root, **args)
    assert "[DC_METH]" not in review["contents"] and "[T_EXC]" not in review["contents"]
    assert "[LIN_INT]" not in review["contents"] and "[POP_SCALE]" not in review["contents"]
    values["DC_METH"] = "LTE"
    with pytest.raises(ModelEditorError, match="Specify.*T_EXC"):
        review_quick_model_parameter_edit(root, **args)


def test_initialization_selector_is_below_abundances_and_luminosity(workspace):
    model, _ = workspace
    with (model / "VADAT").open("a") as stream:
        stream.write("84000 [LSTAR]\n1 [HYD/X]\n0.1 [HE/X]\n0.001 [TEST/X]\n")
    app = create_app(basepath=str(model.parent), read_write_enabled=True, secret_key="test")
    page = app.test_client().get("/model-actions/edit/model").data.decode()
    assert page.index('id="quick-vadat-lstar"') < page.index("Additional abundances") < page.index("Initialization")
    assert 'name="quick_value:DC_METH"' in page
    assert 'name="quick_value:LIN_INT"' in page
    assert 'name="quick_value:POP_SCALE"' in page
    assert 'Unset (leave unchanged)' in page
    assert 'Native default (leave unset)' in page
    assert 'LTE — LTE initial populations' in page
    assert 'Preview LTE initialization settings' not in page


def test_population_method_is_editable_and_preserved_during_other_edits(workspace):
    model, _ = workspace
    with (model / "VADAT").open("a") as stream:
        stream.write("T [LIN_INT]\nT [POP_SCALE]\nPOP [DC_METH] !population regrid\n")
    root = str(model.parent)
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    field = next(field for field in card["fields"] if field["key"] == "DC_METH")
    assert field["value"] == "POP"
    assert ("POP", "Population fractions / radius") in field["choices"]
    assert not any("[DC_METH]" in issue for issue in card["issues"])
    values = {field["key"]: field["value"] for field in card["fields"]}
    values.update(RSTAR="2", DC_METH="pop")
    review = review_quick_model_parameter_edit(root, model_relpath="model", file_relpath="VADAT",
                                              expected_digest=card["digest"], values=values)
    assert "POP [DC_METH] !population regrid" in review["contents"]
    app = create_app(basepath=root, read_write_enabled=True, secret_key="test")
    page = app.test_client().get("/model-actions/edit/model").data.decode()
    assert 'POP — Population fractions / radius' in page
    assert '[DC_METH] has an unsupported value' not in page
    values["DC_METH"] = "UNKNOWN"
    with pytest.raises(ModelEditorError, match="Unsupported.*DC_METH"):
        review_quick_model_parameter_edit(root, model_relpath="model", file_relpath="VADAT",
                                          expected_digest=card["digest"], values=values)


@pytest.mark.parametrize("controls,key", [
    ("", "LIN_INT"),
    ("F [LIN_INT]\nT [POP_SCALE]\n", "LIN_INT"),
    ("T [LIN_INT]\n", "POP_SCALE"),
    ("T [LIN_INT]\nF [POP_SCALE]\n", "POP_SCALE"),
    ("T [LIN_INT]\nT [LIN_INT]\nT [POP_SCALE]\n", "LIN_INT"),
    ("T [LIN_INT]\nT [POP_SCALE]\nT [POP_SCALE]\n", "POP_SCALE"),
])
def test_pop_selection_requires_explicit_enabled_switches(workspace, controls, key):
    model, _ = workspace
    with (model / "VADAT").open("a") as stream:
        stream.write(controls)
    original = (model / "VADAT").read_bytes()
    root = str(model.parent)
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    values = {field["key"]: field["value"] for field in card["fields"]}
    values["DC_METH"] = "POP"
    with pytest.raises(ModelEditorError, match=rf"POP requires \[{key}\]=T"):
        review_quick_model_parameter_edit(root, model_relpath="model", file_relpath="VADAT",
                                          expected_digest=card["digest"], values=values)
    assert (model / "VADAT").read_bytes() == original


@pytest.mark.parametrize("existing", [False, True])
def test_pop_switches_are_explicitly_reviewed_and_saved(workspace, existing):
    model, _ = workspace
    if existing:
        with (model / "VADAT").open("a") as stream:
            stream.write("F [LIN_INT] ! keep interpolation comment\nF [POP_SCALE] ! keep scaling comment\n")
    original = (model / "VADAT").read_bytes()
    root = str(model.parent)
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    values = {field["key"]: field["value"] for field in card["fields"]}
    values.update(DC_METH="POP", LIN_INT="T", POP_SCALE="T")
    args = dict(model_relpath="model", file_relpath="VADAT", expected_digest=card["digest"], values=values)
    review = review_quick_model_parameter_edit(root, **args)
    assert (model / "VADAT").read_bytes() == original
    assert review["contents"].count("[LIN_INT]") == 1
    assert review["contents"].count("[POP_SCALE]") == 1
    if existing:
        assert "T [LIN_INT] ! keep interpolation comment" in review["contents"]
        assert "T [POP_SCALE] ! keep scaling comment" in review["contents"]
    client = create_app(basepath=root, read_write_enabled=True, secret_key="test").test_client()
    data = {"action": "quick_save", "quick_file_relpath": "VADAT", "expected_digest": card["digest"],
            "reviewed_digest": review["proposed_digest"],
            **{f"quick_value:{key}": value for key, value in values.items()}}
    assert client.post("/model-actions/edit/model", data=data).status_code == 302
    assert (model / "VADAT").read_bytes() == review["contents"].encode()
    assert any(path.read_bytes() == original for path in
               (model / ".cmfgen-viewer-backups").rglob("VADAT.*.bak"))
    # A crafted save must also reject disabling either prerequisite.
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    saved = (model / "VADAT").read_bytes()
    for key in ("LIN_INT", "POP_SCALE"):
        response = client.post("/model-actions/edit/model", data={
            **data, "expected_digest": card["digest"], f"quick_value:{key}": "F"})
        assert response.status_code == 200
        assert f"POP requires [{key}]=T" in response.data.decode()
        assert (model / "VADAT").read_bytes() == saved


def test_lte_rejects_enabling_interpolation_without_changing_method(workspace):
    model, _ = workspace
    with (model / "VADAT").open("a") as stream:
        stream.write("LTE [DC_METH]\n1 [T_EXC]\nF [LIN_INT]\n")
    root = str(model.parent)
    card = load_quick_model_parameter_cards(root, model_relpath="model")[0]
    values = {field["key"]: field["value"] for field in card["fields"]}
    values["LIN_INT"] = "T"
    with pytest.raises(ModelEditorError, match=r"LTE.*\[LIN_INT\]=F"):
        review_quick_model_parameter_edit(root, model_relpath="model", file_relpath="VADAT",
                                          expected_digest=card["digest"], values=values)


def test_population_postmortem_distinguishes_confirmed_and_suspected(tmp_path):
    (tmp_path / "VADAT").write_text("F [LIN_INT]\nT [IT_ON_T]\n")
    startup = "Starting a new model.\nCalling AUTO_ADD_ION\n"
    signal = "Program received signal SIGILL: Illegal instruction.\n"
    confirmed = analyze_main_diagnostics(tmp_path, {"OUTGEN": startup, "process.log": signal + "Native crash frame: scale_pops_\n"})
    assert confirmed[0]["code"] == "initial_population_scaling"
    assert "--lte-initialization --t-exc 1.0" in " ".join(confirmed[0]["suggestions"])
    suspected = analyze_main_diagnostics(tmp_path, {"OUTGEN": startup, "process.log": signal})
    assert suspected[0]["code"] == "suspected_initial_population_failure"
    assert "does not confirm" in suspected[0]["message"]
    assert not analyze_main_diagnostics(tmp_path, {"process.log": signal})
    assert not analyze_main_diagnostics(tmp_path, {"OUTGEN": startup,
        "process.log": "Note: The following floating-point exceptions are signalling: IEEE_UNDERFLOW_FLAG"})
    assert not analyze_main_diagnostics(tmp_path, {"OUTGEN": startup + "Current great iteration count is 1\n", "process.log": signal})
    assert not analyze_main_diagnostics(tmp_path, {"OUTGEN": startup, "process.log": signal}, completed=True)
    guard = analyze_main_diagnostics(tmp_path, {"OUTGEN": "Error in SETPOP_WLD_V2 -- zero RGU"})
    assert guard[0]["severity"] == "error"


def test_macos_report_requires_matching_pid_and_recent_timestamp(tmp_path):
    path = tmp_path / "cmfgen_dev.exe-example.ips"
    path.write_text('{}\n' + json.dumps({"pid": 123, "procName": "cmfgen_dev.exe",
        "threads": [{"triggered": True, "frames": [{"symbol": "scale_pops_"}]}]}))
    assert "scale_pops_" in macos_crash_evidence(123, "/native/cmfgen_dev.exe", report_dir=tmp_path)
    assert not macos_crash_evidence(124, "/native/cmfgen_dev.exe", report_dir=tmp_path)
    assert not macos_crash_evidence(123, "/native/cmfgen_dev.exe", report_dir=tmp_path, since=path.stat().st_mtime + 1)
    (tmp_path / "cmfgen_dev.exe-bad.ips").write_text("invalid")
    assert "scale_pops_" in macos_crash_evidence(123, "/native/cmfgen_dev.exe", report_dir=tmp_path)
