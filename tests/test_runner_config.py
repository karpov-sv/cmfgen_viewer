import json
from pathlib import Path

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner_config import resolve_runner_config
from cmfgen_viewer.runner_recipe import RunnerError


@pytest.fixture
def config_dirs(tmp_path, monkeypatch):
    user_dir = tmp_path / "user"
    work_dir = tmp_path / "work"
    user_dir.mkdir()
    work_dir.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_dir))
    monkeypatch.chdir(work_dir)
    for name in ("CMFDIST", "ATOMIC", "OMP_NUM_THREADS", "cmfdist", "atomic"):
        monkeypatch.delenv(name, raising=False)
    return user_dir, work_dir


def test_defaults_and_missing_roots(config_dirs):
    _, work_dir = config_dirs
    with pytest.raises(RunnerError, match="Missing cmfgen_root"):
        resolve_runner_config()
    with pytest.raises(RunnerError, match="Missing atomic_root"):
        resolve_runner_config(cmfgen_root=Path("cmf"))
    values, sources = resolve_runner_config(cmfgen_root=Path("cmf"), atomic_root=Path("atomic"))
    assert values == {"cmfgen_root": work_dir / "cmf", "atomic_root": work_dir / "atomic", "threads": None}
    assert sources == {"cmfgen_root": "cli", "atomic_root": "cli", "threads": "default"}
    assert not (work_dir / ".cmfgenrc").exists()


def test_optional_root_resolution_keeps_available_defaults(config_dirs):
    _, work_dir = config_dirs
    (work_dir / ".cmfgenrc").write_text("nthreads = 3\n")
    values, sources = resolve_runner_config(require_roots=False)
    assert values == {"threads": 3}
    assert sources == {"threads": str(work_dir / ".cmfgenrc")}


def test_home_and_cwd_merge_per_key(config_dirs):
    user_dir, work_dir = config_dirs
    (user_dir / ".cmfgenrc").write_text('CMFDIST = "cmf distribution" # comment\nATOMIC = atomic\nnthreads = 2\n')
    (work_dir / ".cmfgenrc").write_text("# local override\nNTHREADS = 3\n")
    values, sources = resolve_runner_config()
    assert values == {"cmfgen_root": user_dir / "cmf distribution", "atomic_root": user_dir / "atomic", "threads": 3}
    assert sources["cmfgen_root"] == str(user_dir / ".cmfgenrc")
    assert sources["threads"] == str(work_dir / ".cmfgenrc")


def test_environment_then_cli_override(config_dirs, monkeypatch):
    _, work_dir = config_dirs
    (work_dir / ".cmfgenrc").write_text("cmfgen_root = config-cmf\natomic_root = config-atomic\nthreads = 2\n")
    monkeypatch.setenv("CMFDIST", "env-cmf")
    monkeypatch.setenv("ATOMIC", "env-atomic")
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    values, sources = resolve_runner_config()
    assert values == {"cmfgen_root": work_dir / "env-cmf", "atomic_root": work_dir / "env-atomic", "threads": 4}
    assert all(source.startswith("env:") for source in sources.values())
    values, sources = resolve_runner_config(cmfgen_root=Path("cli-cmf"), atomic_root=Path("cli-atomic"), threads=1)
    assert values == {"cmfgen_root": work_dir / "cli-cmf", "atomic_root": work_dir / "cli-atomic", "threads": 1}
    assert set(sources.values()) == {"cli"}


def test_empty_environment_ignored_and_tilde_expanded(config_dirs, monkeypatch):
    user_dir, _ = config_dirs
    (user_dir / ".cmfgenrc").write_text("cmfgen_root = ~/cmf\natomic_root = ~/atomic\nnthreads = 2\n")
    for variable in ("CMFDIST", "ATOMIC", "OMP_NUM_THREADS"):
        monkeypatch.setenv(variable, "  ")
    values, _ = resolve_runner_config()
    assert values["cmfgen_root"] == Path("~/cmf").expanduser()
    assert values["atomic_root"] == Path("~/atomic").expanduser()
    assert values["threads"] == 2


@pytest.mark.parametrize("text", [
    "nthread = 2", "nthreads 2", "nthreads =", 'atomic = "unterminated',
    "nthreads = 2\nthreads = 3", "cmfdist = two unquoted words", "atomic = ''",
    "export ATOMIC=/tmp/atomic", "cmfdist = $(touch NEVER_RUN)",
])
def test_malformed_config_is_reported_without_execution(config_dirs, text):
    _, work_dir = config_dirs
    (work_dir / ".cmfgenrc").write_text(text)
    with pytest.raises(RunnerError, match=r"\.cmfgenrc:\d+:"):
        resolve_runner_config(cmfgen_root=Path("cmf"), atomic_root=Path("atomic"))
    assert not (work_dir / "NEVER_RUN").exists()


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "true", "2,4"])
@pytest.mark.parametrize("source", ["config", "env"])
def test_invalid_thread_counts(config_dirs, monkeypatch, value, source):
    _, work_dir = config_dirs
    if source == "config":
        (work_dir / ".cmfgenrc").write_text(f"nthreads = {value}\n")
    else:
        monkeypatch.setenv("OMP_NUM_THREADS", value)
    with pytest.raises(RunnerError, match="positive integer"):
        resolve_runner_config(cmfgen_root=Path("cmf"), atomic_root=Path("atomic"))
    # A higher-priority valid value supersedes an invalid lower-priority value.
    assert resolve_runner_config(cmfgen_root=Path("cmf"), atomic_root=Path("atomic"), threads=1)[0]["threads"] == 1


@pytest.mark.parametrize("planning", [True, False])
def test_cli_resolves_defaults_and_records_sources(config_dirs, monkeypatch, capsys, planning):
    _, work_dir = config_dirs
    (work_dir / ".cmfgenrc").write_text("cmfdist = cmf\natomic = atomic\nnthreads = 2\n")
    plans = []
    def build(model, **options):
        assert model == Path("model")
        assert options["cmfgen_root"] == work_dir / "cmf"
        assert options["atomic_root"] == work_dir / "atomic"
        assert options["threads"] == 3
        plan = {"ready": True, "threads": options["threads"]}
        plans.append(plan)
        return plan
    monkeypatch.setattr(runner, "build_run_plan", build)
    monkeypatch.setattr(runner, "run_plan", lambda plan, emit: {"status": "tested", "plan": plan})
    args = ["model", "--stage", "test", "--nthreads", "3", "--json"] + (["--plan"] if planning else [])
    assert runner.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["ready"] if planning else output["status"] == "tested"
    assert plans[0]["configuration_sources"]["threads"] == "cli"
    assert plans[0]["configuration_sources"]["cmfgen_root"] == str(work_dir / ".cmfgenrc")


def test_cli_missing_roots_reports_json_before_execution(config_dirs, monkeypatch, capsys):
    monkeypatch.setattr(runner, "build_run_plan", lambda *args, **kwargs: pytest.fail("must not plan with missing roots"))
    assert runner.main(["model", "--stage", "test", "--json"]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "preflight_failed"
    assert "CMFDIST" in output["error"]


@pytest.mark.parametrize("kind", ["directory", "invalid_utf8", "dangling_link"])
def test_cli_unreadable_config_reports_json(config_dirs, capsys, kind):
    _, work_dir = config_dirs
    path = work_dir / ".cmfgenrc"
    if kind == "directory":
        path.mkdir()
    elif kind == "invalid_utf8":
        path.write_bytes(b"\xff")
    else:
        path.symlink_to(work_dir / "missing")
    assert runner.main(["model", "--stage", "test", "--plan", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "preflight_failed"
