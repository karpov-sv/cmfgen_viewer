import hashlib
import json
import resource
from pathlib import Path
import sys

import pytest

from cmfgen_viewer import runner, runner_recipe
from cmfgen_viewer.runner import run_plan, _progress, _validate
from cmfgen_viewer.runner_recipe import RunnerError, build_run_plan, override_controls, snapshot


RVTJ_CORE = "ND: 2\nRadius\n2 1\nVelocity\n20 10\nTemperature\n1 2\nElectron density\n1e10 2e10\n"

SUCCESS = """
from pathlib import Path
p=Path('.')
(p/'MOD_SUM').write_text('Model Finalized on: today\\n')
(p/'RVTJ').write_text('ND: 2\\nRadius\\n2 1\\nVelocity\\n20 10\\nTemperature\\n1 2\\nElectron density\\n1e10 2e10\\n')
(p/'MODEL').write_text('new model')
(p/'OUTGEN').write_text('computation done')
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.mkdir()
    files = {"batch.sh": "#!/bin/sh\n# reviewed fake entry point, never executed\n",
             "batch_ins.sh": "ln -sf $ATOMIC/test.dat HYD_L_DATA\n",
             "VADAT": "1 [RSTAR]\n", "MODEL_SPEC": "2 [ND]\n1 [NC]\n3 [NP]\n",
             "IN_ITS": "2 [NUM_ITS]\n", "GAMMAS_IN": "gamma", "He2_IN": "helium"}
    for name, text in files.items():
        (model / name).write_text(text)
    (model / "batch.sh").chmod(0o755)
    monkeypatch.setitem(runner_recipe.REVIEWED_SCRIPTS, "batch.sh", {hashlib.sha256(files["batch.sh"].encode()).hexdigest()})
    (tmp_path / "atomic").mkdir()
    (tmp_path / "atomic/test.dat").write_text("data")
    (tmp_path / "cmf/exe").mkdir(parents=True)
    def make_plan(code=SUCCESS, **options):
        stage = options.pop("stage", "init")
        exe = tmp_path / "cmf/exe" / runner_recipe.PROGRAMS[stage]
        exe.write_text(f"#!{sys.executable}\n" + code)
        exe.chmod(0o755)
        return build_run_plan(model, stage=stage, cmfgen_root=tmp_path / "cmf", atomic_root=tmp_path / "atomic", **options)
    return model, make_plan


def test_success_restores_controls_and_archives_old_logs(workspace):
    model, make_plan = workspace
    (model / "OUTGEN").write_text("old failure")
    plan = make_plan()
    assert plan["ready"], plan["errors"]
    assert plan["timeout"] is None
    assert plan["memory_mib"] is None
    assert plan["threads"] is None
    assert plan["no_core_dumps"] is False
    assert not (model / ".cmfgen-runs").exists()
    events = []
    original_mtime = (model / "IN_ITS").stat().st_mtime_ns
    result = run_plan(plan, events.append)
    assert result["status"] == "initialized", result
    assert (model / "IN_ITS").read_text() == "2 [NUM_ITS]\n"
    assert (model / "IN_ITS").stat().st_mtime_ns == original_mtime
    archive = Path(result["journal"])
    assert (archive / "init/IN_ITS").read_text() == "0 [NUM_ITS]\n"
    assert (archive / "init/before/OUTGEN").read_text() == "old failure"
    assert json.loads((archive / "result.json").read_text())["status"] == "initialized"
    assert events[-1]["event"] == "run_finished"
    assert result["scientific_acceptance"] == "not assessed"


@pytest.mark.parametrize("code,expected", [("raise SystemExit(7)", "failed"), ("print('fatal; Fortran STOP with zero exit')", "invalid_output")])
def test_failed_and_zero_exit_runs_are_not_success(workspace, code, expected):
    model, make_plan = workspace
    (model / "MOD_SUM").write_text("Model Finalized on: OLD\n")
    (model / "RVTJ").write_bytes(b"old"*100)
    (model / "MODEL").write_text("old")
    result = run_plan(make_plan(code))
    assert result["status"] == expected
    assert result["passes"][0]["problems"]
    assert (model / "IN_ITS").read_text() == "2 [NUM_ITS]\n"


def test_timeout_is_bounded_and_restores_controls(workspace):
    model, make_plan = workspace
    result = run_plan(make_plan("import time; time.sleep(20)", timeout=0.3))
    assert result["status"] == "timeout"
    assert result["passes"][0]["returncode"] < 0
    assert (model / "IN_ITS").read_text() == "2 [NUM_ITS]\n"


def test_main_progress_reports_current_run_count_and_requested_total(tmp_path):
    (tmp_path / "IN_ITS").write_text("3 [NUM_ITS]\n")
    (tmp_path / "OUTGEN").write_text(
        "Current great iteration count is 18\n"
        "Current great iteration count is 19\n"
    )

    assert _progress("main", tmp_path) == {
        "phase": "iterations",
        "current": 2,
        "total": 3,
    }


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_positive_and_finite_when_provided(workspace, timeout):
    _model, make_plan = workspace
    with pytest.raises(RunnerError, match="--timeout must be a positive finite"):
        make_plan(timeout=timeout)


def test_cancellation_is_recorded(workspace):
    model, make_plan = workspace
    def cancel(item):
        if item["event"] == "progress":
            raise KeyboardInterrupt()
    result = run_plan(make_plan("import time; time.sleep(20)"), cancel)
    assert result["status"] == "cancelled"
    assert result["passes"][0]["status"] == "cancelled"


def test_changed_inputs_fail_before_mutation(workspace):
    model, make_plan = workspace
    plan = make_plan()
    (model / "VADAT").write_text("2 [RSTAR]\n")
    with pytest.raises(RunnerError, match="changed since preflight"):
        run_plan(plan)
    assert not (model / ".cmfgen-runs").exists()


def test_unreviewed_scripts_and_arbitrary_manifest_commands_are_blocked(workspace):
    model, make_plan = workspace
    (model / "batch_ins.sh").write_text("touch NEVER_RUN\n")
    plan = make_plan()
    assert not plan["ready"]
    assert any("Unsupported command" in error for error in plan["errors"])
    assert not (model / "NEVER_RUN").exists()
    (model / "batch.sh").write_text("malicious shell content")
    assert any("Unreviewed" in error for error in make_plan()["errors"])


def test_unsafe_outputs_do_not_overwrite_symlink_target(workspace, tmp_path):
    model, make_plan = workspace
    external = tmp_path / "keep"
    external.write_text("untouched")
    (model / "OUTGEN").symlink_to(external)
    plan = make_plan()
    assert not plan["ready"]
    with pytest.raises(RunnerError):
        run_plan(plan)
    assert external.read_text() == "untouched"


def test_resource_limit_is_applied_in_child(workspace):
    _, make_plan = workspace
    code = """
import os
import resource
assert resource.getrlimit(resource.RLIMIT_AS) == (256*1024**2, 256*1024**2)
assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    assert os.environ[name] == '2'
""" + SUCCESS
    assert run_plan(make_plan(code, memory_mib=256, threads=2, no_core_dumps=True))["status"] == "initialized"


def test_default_children_preserve_inherited_limits_and_thread_settings(workspace, monkeypatch):
    _, make_plan = workspace
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "3")
    monkeypatch.setenv("MKL_NUM_THREADS", "5")
    limits = {}
    for name, requested in (("RLIMIT_AS", 512*1024**2), ("RLIMIT_CORE", 128*1024**2)):
        _, hard = resource.getrlimit(getattr(resource, name))
        limits[name] = (requested if hard == resource.RLIM_INFINITY else min(requested, hard), hard)
    # Set inherited limits in an intermediate process, without altering pytest's limits.
    bootstrap = "import os, resource, sys\n"
    for name, limit in limits.items():
        bootstrap += f"resource.setrlimit(resource.{name}, {limit!r})\n"
    bootstrap += "os.execv(sys.argv[1], sys.argv[1:])\n"
    original_popen = runner.subprocess.Popen

    def launch(command, **kwargs):
        return original_popen([sys.executable, "-c", bootstrap, *command], **kwargs)

    monkeypatch.setattr(runner.subprocess, "Popen", launch)
    code = "import os, resource\n"
    for name, limit in limits.items():
        code += f"assert resource.getrlimit(resource.{name}) == {limit!r}\n"
    code += """
assert 'OMP_NUM_THREADS' not in os.environ
assert os.environ['OPENBLAS_NUM_THREADS'] == '3'
assert os.environ['MKL_NUM_THREADS'] == '5'
soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
assert soft == hard
""" + SUCCESS
    result = run_plan(make_plan(code))
    assert result["status"] == "initialized", result


def test_override_is_lossless_and_requires_unique_keys():
    assert override_controls("  20 [NUM_ITS] ! keep\n", {"NUM_ITS": "1"}) == "  1 [NUM_ITS] ! keep\n"
    with pytest.raises(RunnerError):
        override_controls("1 [A]\n2 [A]\n", {"A": "3"})


@pytest.mark.parametrize("count", [" (2)", ""])
def test_flux_validation_requires_complete_finite_vectors(tmp_path, count):
    (tmp_path / "OUT_FLUX").write_text("CMF_FLUX has finished")
    output = tmp_path / "OBSFRAME"
    output.write_text(f"Continuum Frequencies (2)\n1 2\nObserved intensity (Janskys){count}\n3 4\n")
    assert not _validate("flux", tmp_path, {})
    for values in ("3 nan", "3", "3 4 5", "3 ********"):
        output.write_text(f"Continuum Frequencies (2)\n1 2\nObserved intensity (Janskys){count}\n{values}\n")
        assert _validate("flux", tmp_path, {})


def test_lock_remains_held_in_executable(workspace):
    _, make_plan = workspace
    code = """
import fcntl
f=open('.cmfgen-viewer-write.lock','r')
try:
    fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:
    pass
else:
    raise RuntimeError('runner lost its lease')
""" + SUCCESS
    assert run_plan(make_plan(code))["status"] == "initialized"


def test_fresh_start_archives_checkpoint_instead_of_deleting(workspace):
    model, make_plan = workspace
    (model / "POINT1").write_text("old restart")
    assert not make_plan()["ready"]
    result = run_plan(make_plan(fresh_start=True))
    assert result["status"] == "initialized"
    assert (Path(result["journal"]) / "restart-before/POINT1").read_text() == "old restart"


def test_main_continues_by_default_and_backs_up_checkpoint(workspace):
    model, make_plan = workspace
    (model / "POINT1").write_text("28-Feb-2004 !Format date\n1 7 1 -1000 F\n")
    original = b"checkpoint" * 500
    (model / "SCRTEMP").write_bytes(original)
    (model / "RVTJ").write_text(RVTJ_CORE)
    (model / "GAMMAS_IN").unlink()
    (model / "He2_IN").unlink()
    code = SUCCESS + """
assert (p/'SCRTEMP').read_bytes() == b'checkpoint'*500
(p/'SCRTEMP').write_bytes(b'updated checkpoint')
(p/'OUTGEN').write_text('Current great iteration count is 8')
"""
    plan = make_plan(code, stage="main")
    assert plan["ready"], plan["errors"]
    assert plan["restart"]["mode"] == "continuation"
    assert plan["restart"]["health"]["status"] == "passed"
    assert any(item["path"] == str(model / "RVTJ") for item in plan["inputs"])
    assert plan["restart"]["pointer"]["iterations"] == 7
    assert not any(link["name"] == "T_IN" for link in plan["links"])
    events = []
    result = run_plan(plan, events.append)
    assert result["status"] == "succeeded", result
    assert result["startup_observed"]["mode"] == "continuation"
    assert events[0]["event"] == "startup"
    assert "Continuation" in events[0]["message"]
    assert (model / "SCRTEMP").read_bytes() == b"updated checkpoint"
    assert (Path(result["journal"]) / "restart-before/SCRTEMP").read_bytes() == original


def test_main_rejects_poisoned_checkpoint_before_launch(workspace):
    model, make_plan = workspace
    (model / "POINT1").write_text("28-Feb-2004 !Format date\n1 7 1 -1000 F\n")
    (model / "SCRTEMP").write_bytes(b"checkpoint" * 500)
    (model / "RVTJ").write_text(RVTJ_CORE.replace("Temperature\n1 2", "Temperature\nNaN NaN"))

    plan = make_plan(stage="main")
    assert not plan["ready"]
    assert plan["restart"]["health"]["status"] == "failed"
    assert any("Checkpoint health check failed" in error for error in plan["errors"])
    with pytest.raises(RunnerError, match="Checkpoint health check failed"):
        run_plan(plan)
    assert not (model / ".cmfgen-runs").exists()

    fresh = make_plan(stage="main", fresh_start=True)
    assert fresh["ready"], fresh["errors"]


def test_native_fresh_fallback_is_reported(workspace):
    model, make_plan = workspace
    (model / "POINT1").write_text("1 7 1 -1000\n")
    (model / "SCRTEMP").write_bytes(b"checkpoint"*500)
    events = []
    result = run_plan(make_plan(SUCCESS + "\n(p/'OUTGEN').write_text('Starting a new model.')", stage="main"), events.append)
    assert result["status"] == "succeeded"
    assert result["restart"]["mode"] == "continuation"
    assert result["startup_observed"]["mode"] == "fresh"
    assert any(item["event"] == "startup_fallback" for item in events)
    assert any("fell back" in warning for warning in result["passes"][0]["diagnostic_warnings"])


@pytest.mark.parametrize("name", ["POINT1", "POINT2", "SCRTEMP"])
def test_new_checkpoint_invalidates_fresh_plan(workspace, name):
    model, make_plan = workspace
    plan = make_plan()
    (model / name).write_text("appeared after preflight")
    with pytest.raises(RunnerError, match="Input changed since preflight"):
        run_plan(plan)
    assert not (model / ".cmfgen-runs").exists()


def test_ion_presence_uses_superlevels_not_important_variables(workspace):
    model, make_plan = workspace
    with (model / "MODEL_SPEC").open("a") as handle:
        handle.write("0,2,3 [OVIII_ISF]\n")
    (model / "batch_ins.sh").write_text("ln -sf $ATOMIC/missing OVIII_F_TO_S\n")
    plan = make_plan()
    assert not plan["ready"]
    assert any("OVIII_F_TO_S" in error for error in plan["errors"])


def test_finalized_main_with_nan_is_rejected(workspace):
    model, make_plan = workspace
    plan = make_plan(SUCCESS.replace("Electron density\\n1e10 2e10", "Electron density\\nnan 2e10"))
    plan["stage"] = "main"
    plan["passes"] = [{"id": "main", "overrides": {}}]
    result = run_plan(plan)
    assert result["status"] == "invalid_output"
    assert any("RVTJ" in message for message in result["passes"][0]["problems"])


def test_unchanged_rvtj_is_not_parsed_as_a_new_output(workspace):
    model, _make_plan = workspace
    (model / "MOD_SUM").write_text("Model Finalized on: old\n")
    (model / "RVTJ").write_text("ND: 11\ninvalid old state\n")
    (model / "MODEL").write_text("old model\n")
    before = {name: snapshot(model / name) for name in ("MOD_SUM", "RVTJ", "MODEL")}

    problems = _validate("main", model, before)

    assert "Missing, empty, or unchanged output: RVTJ" in problems
    assert not any(problem.startswith("Invalid RVTJ:") for problem in problems)


def test_main_without_override_does_not_rewrite_control(workspace):
    model, make_plan = workspace
    plan = make_plan()
    plan["stage"] = "main"
    plan["passes"] = [{"id": "main", "overrides": {}}]
    before = (model / "IN_ITS").stat()
    assert run_plan(plan)["status"] == "succeeded"
    after = (model / "IN_ITS").stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_ctime_ns) == (before.st_ino, before.st_mtime_ns, before.st_ctime_ns)


def test_lte_validation_requires_complete_table(tmp_path):
    output = tmp_path / "ROSSELAND_LTE_TAB"
    header = "1 !Number of temperatures\n2 !Number of densities\n"
    row = "1 2 3 4 5 6 7 8\n"
    output.write_text(header + row*2)
    assert not _validate("lte", tmp_path, {})
    output.write_text(header + row)
    assert _validate("lte", tmp_path, {})


def test_lte_executes_in_its_workspace_and_checks_its_controls(workspace, monkeypatch):
    model, make_plan = workspace
    make_plan()
    lte = model / "lte"
    lte.mkdir()
    script = "# reviewed LTE fixture\n"
    (lte / "ltebat.sh").write_text(script)
    monkeypatch.setitem(runner_recipe.REVIEWED_SCRIPTS, "lte/ltebat.sh", {hashlib.sha256(script.encode()).hexdigest()})
    (lte / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n3 [NP]\n")
    (lte / "VADAT").write_text("4 [TEFF]\n3 [LOGG]\nF [CHK_NG]\n")
    (lte / "GRID_PARAMS").write_text("fixture grid")
    exe = model.parent / "cmf/exe/main_lte.exe"
    exe.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nassert Path.cwd().name == 'lte'\nPath('ROSSELAND_LTE_TAB').write_text('1 !Number of temperatures\\n1 !Number of densities\\n1 2 3 4 5 6 7 8\\n')\n")
    exe.chmod(0o755)
    options = dict(stage="lte", cmfgen_root=model.parent / "cmf", atomic_root=model.parent / "atomic")
    plan = build_run_plan(model, **options)
    assert plan["ready"], plan["errors"]
    assert run_plan(plan)["status"] == "succeeded"
    assert not (lte / "IN_ITS").exists()
    (lte / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n4 [NP]\n")
    assert not build_run_plan(model, **options)["ready"]


def test_hydro_runs_after_lte_with_generated_noninteractive_input(workspace):
    model, make_plan = workspace
    lte = model / "lte"
    lte.mkdir()
    (lte / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n3 [NP]\n")
    (lte / "HYDRO_PARAMS").write_text("F [OLD_MOD]\n")
    (lte / "ROSSELAND_LTE_TAB").write_text(
        "1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n"
    )
    (lte / "inherited_atomic").symlink_to(model.parent / "atomic/test.dat")
    code = """
from pathlib import Path
import sys
assert sys.stdin.read().splitlines() == ['/null', 'e', '2', '']
Path('RVSIG_COL_NEW').write_text('''2 !Number of depth points
2.0 20.0 -0.5 0.1 1
1.0 10.0 0.5 100.0 2
''')
print('hydro completed')
"""
    plan = make_plan(code, stage="hydro")
    assert plan["ready"], plan["errors"]
    assert plan["passes"][0]["stdin"]["output_depth_points"] == 2
    assert not plan["links"]
    assert "inherited_atomic" in plan["permitted_links"]
    result = run_plan(plan)
    assert result["status"] == "succeeded", result
    assert (lte / "WIND_HYD").read_text().strip() == "hydro completed"
    archive = Path(result["journal"]) / "hydro"
    assert (archive / "stdin.txt").read_text() == "/null\ne\n2\n\n"
    assert (archive / "RVSIG_COL_NEW").is_file()
    assert (archive / "WIND_HYD").is_file()


def test_hydro_rejects_missing_or_invalid_lte_handoff(workspace):
    model, make_plan = workspace
    lte = model / "lte"
    lte.mkdir()
    (lte / "MODEL_SPEC").write_text("2 [ND]\n")
    (lte / "HYDRO_PARAMS").write_text("F [OLD_MOD]\n")
    missing = make_plan(stage="hydro")
    assert not missing["ready"]
    assert any("ROSSELAND_LTE_TAB" in error for error in missing["errors"])

    (lte / "ROSSELAND_LTE_TAB").write_text("invalid\n")
    invalid = make_plan(stage="hydro")
    assert not invalid["ready"]
    assert any("Invalid hydro input ROSSELAND_LTE_TAB" in error for error in invalid["errors"])


def test_hydro_old_model_requires_and_selects_lte_rvtj(workspace):
    model, make_plan = workspace
    lte = model / "lte"
    lte.mkdir()
    (lte / "MODEL_SPEC").write_text("2 [ND]\n")
    (lte / "HYDRO_PARAMS").write_text("T [OLD_MOD]\n")
    (lte / "ROSSELAND_LTE_TAB").write_text(
        "1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n"
    )
    missing = make_plan(stage="hydro")
    assert not missing["ready"]
    assert any("RVTJ" in error for error in missing["errors"])

    (lte / "RVTJ").write_text(RVTJ_CORE)
    plan = make_plan(stage="hydro")
    assert plan["ready"], plan["errors"]
    assert plan["passes"][0]["stdin"]["structure_file"] == "RVTJ"
    assert plan["passes"][0]["stdin"]["text"].startswith("RVTJ\n/null\ne\n")


def test_hydro_rejects_unrelated_or_output_symlinks(workspace, tmp_path):
    model, make_plan = workspace
    lte = model / "lte"
    lte.mkdir()
    (lte / "MODEL_SPEC").write_text("2 [ND]\n")
    (lte / "HYDRO_PARAMS").write_text("F [OLD_MOD]\n")
    (lte / "ROSSELAND_LTE_TAB").write_text(
        "1 !Number of temperatures\n1 !Number of densities\n1 2 3 4 5 6 7 8\n"
    )
    external = tmp_path / "external"
    external.write_text("keep")
    (lte / "unexpected").symlink_to(external)
    plan = make_plan(stage="hydro")
    assert not plan["ready"]
    assert any("unexpected" in error for error in plan["errors"])

    (lte / "unexpected").unlink()
    (lte / "RVSIG_COL_NEW").symlink_to(external)
    output_plan = make_plan(stage="hydro")
    assert not output_plan["ready"]
    assert any("RVSIG_COL_NEW" in error for error in output_plan["errors"])


@pytest.mark.parametrize("fail_first", [False, True])
@pytest.mark.parametrize("ew_controls", ["present", "absent", "duplicate", "missing_required"])
def test_flux_passes_and_fail_fast(workspace, monkeypatch, fail_first, ew_controls):
    model, make_plan = workspace
    make_plan()
    obs = model / "obs"
    obs.mkdir()
    template = "".join(f"1 [{key}]\n" for key in ("VTURB_FIX", "VTURB_MIN", "VTURB_MAX", "NUM_ES", "DO_SOB_LINES", "GLOBAL_LINE", "SOB_EW_LAM_BEG", "SOB_EW_LAM_END"))
    if ew_controls == "absent":
        template = template.replace("1 [SOB_EW_LAM_BEG]\n", "").replace("1 [SOB_EW_LAM_END]\n", "")
    elif ew_controls == "duplicate":
        template += "2 [SOB_EW_LAM_BEG]\n"
    elif ew_controls == "missing_required":
        template = template.replace("1 [DO_SOB_LINES]\n", "")
    (obs / "CMF_FLUX_PARAM_INIT").write_text(template)
    for name in ("EDDFACTOR", "EDDFACTOR_INFO", "ES_J_CONV", "ES_J_CONV_INFO"):
        (obs / name).write_text("incompatible old cache")
    (obs / "IN_FILE").write_text("../RVTJ [RVTJ]\n1 [MASS]\nF [ONLY_OBS_LINES]\n")
    for name in ("batobs.sh", "bat_ins.sh"):
        text = "# reviewed test script\n"
        if name == "batobs.sh":
            text += 'ln -sf $atomic/test.dat OBS_ATOMIC\nsed -e "s/old/new/" \\\n    -e "s/other/value/" TEMPLATE > OUTPUT\n'
        (obs / name).write_text(text)
        monkeypatch.setitem(runner_recipe.REVIEWED_SCRIPTS, "obs/"+name, {hashlib.sha256(text.encode()).hexdigest()})
    (model / "RVTJ").write_text(RVTJ_CORE)
    (model / "MODEL").write_text("input")
    exe = model.parent / "cmf/exe/cmf_flux.exe"
    code = "raise SystemExit(9)" if fail_first else """
from pathlib import Path
for name in ('EDDFACTOR', 'EDDFACTOR_INFO', 'ES_J_CONV', 'ES_J_CONV_INFO'):
    assert not Path(name).exists(), 'stale cache was reused'
    Path(name).write_text('current pass cache')
Path('OUT_FLUX').write_text('CMF_FLUX has finished')
Path('OBSFRAME').write_text('Continuum Frequencies (2)\\n1 2\\nObserved intensity (Janskys)\\n3 4\\n')
"""
    exe.write_text(f"#!{sys.executable}\n" + code)
    exe.chmod(0o755)
    plan = build_run_plan(model, stage="flux", cmfgen_root=model.parent / "cmf", atomic_root=model.parent / "atomic")
    if ew_controls in {"duplicate", "missing_required"}:
        assert not plan["ready"]
        key = "SOB_EW_LAM_BEG" if ew_controls == "duplicate" else "DO_SOB_LINES"
        assert any(f"Expected exactly one [{key}]" in error for error in plan["errors"])
        return
    assert plan["ready"], plan["errors"]
    assert any(link["name"] == "OBS_ATOMIC" for link in plan["links"])
    assert ("SOB_EW_LAM_BEG" in plan["passes"][-1]["overrides"]) == (ew_controls == "present")
    if ew_controls == "absent":
        assert any("Optional [SOB_EW_LAM_BEG] absent" in warning for warning in plan["warnings"])
    events = []
    result = run_plan(plan, events.append)
    assert result["status"] == ("failed" if fail_first else "succeeded"), result
    assert len(result["passes"]) == (1 if fail_first else 4)
    assert result["planned_passes"] == 4
    flux_progress = [
        item
        for item in events
        if item["event"] == "progress"
        and item["stage"] == "flux"
        and item["phase"] == "passes"
    ]
    assert flux_progress[0]["current"] == 0
    assert flux_progress[-1]["current"] == (0 if fail_first else 4)
    assert all(item["total"] == 4 for item in flux_progress)
    assert not (obs / "CMF_FLUX_PARAM").exists()
    assert (obs / "obs_cont").exists() != fail_first
    assert (Path(result["journal"]) / "flux-15/before/EDDFACTOR_INFO").read_text() == "incompatible old cache"
    if not fail_first:
        assert result["passes"][-1]["output"] == str(obs / "obs_cont")
        assert (Path(result["journal"]) / "flux-10/before/EDDFACTOR_INFO").read_text() == "current pass cache"
        effective = (Path(result["journal"]) / "continuum/CMF_FLUX_PARAM").read_text()
        assert ("[SOB_EW_LAM_BEG]" in effective) == (ew_controls == "present")
    # Numeric failure of the parent model is a preflight error, not a native
    # line-profile crash after startup. The archive must not grow.
    for heading, values in (("Temperature", "NaN NaN"), ("Electron density", "0 0")):
        text = RVTJ_CORE
        original = "1 2" if heading == "Temperature" else "1e10 2e10"
        (model / "RVTJ").write_text(text.replace(heading + "\n" + original, heading + "\n" + values))
        bad_plan = build_run_plan(model, stage="flux", cmfgen_root=model.parent / "cmf", atomic_root=model.parent / "atomic")
        assert not bad_plan["ready"]
        assert any("Invalid flux input RVTJ" in error and heading in error for error in bad_plan["errors"])
        before = sorted((model / ".cmfgen-runs").iterdir())
        with pytest.raises(RunnerError, match="Invalid flux input RVTJ"):
            run_plan(bad_plan)
        assert sorted((model / ".cmfgen-runs").iterdir()) == before


def test_link_manifest_still_rejects_nonlink_continuations(workspace):
    model, make_plan = workspace
    (model / "batch_ins.sh").write_text('sed -e "s/old/new/" \\\n    INPUT > NEVER_RUN\n')
    plan = make_plan()
    assert not plan["ready"]
    assert any("Cannot parse" in error or "Unsupported command" in error for error in plan["errors"])
    assert not (model / "NEVER_RUN").exists()
