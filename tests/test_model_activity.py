from pathlib import Path
import subprocess
import sys

import pytest

from cmfgen_viewer import model_activity as activity


def _proc(tmp_path, model, *, name="main_lte.exe", state="S"):
    proc = tmp_path / "proc"
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "stat").write_text("available")
    entry = proc / "123"
    entry.mkdir()
    (entry / "cmdline").write_bytes(f"/exe/{name}\0".encode())
    (entry / "comm").write_text(name)
    (entry / "stat").write_text("123 (test) " + " ".join([state] + ["0"] * 18 + ["100"]))
    (entry / "cwd").symlink_to(model, target_is_directory=True)
    return proc


def test_activity_covers_child_workspaces_and_ignores_exited_processes(tmp_path):
    model = tmp_path / "model"
    (model / "lte").mkdir(parents=True)
    (model / "VADAT").touch()
    (model / "MODEL_SPEC").touch()
    proc = _proc(tmp_path, model / "lte")
    state = activity.inspect_model_activity(model, proc_root=proc)
    assert state["state"] == "active"
    assert state["processes"][0]["start_ticks"] == "100"
    assert activity.model_workspace_root(model / "lte") == model
    (proc / "123" / "stat").write_text("123 (test) Z")
    assert activity.inspect_model_activity(model, proc_root=proc)["state"] == "idle"


def test_unavailable_visibility_fails_closed(tmp_path):
    assert not activity.inspect_model_activity(tmp_path, proc_root=tmp_path / "missing")["safe_to_modify"]


@pytest.mark.parametrize("name,within", [("unrelated.exe", True), ("cmfgen_dev.exe", False)])
def test_unrelated_process_is_not_active(tmp_path, name, within):
    model = tmp_path / "model"
    model.mkdir()
    proc = _proc(tmp_path, model if within else tmp_path, name=name)
    assert activity.inspect_model_activity(model, proc_root=proc)["state"] == "idle"


def test_unreadable_matching_process_is_unknown(tmp_path, monkeypatch):
    proc = _proc(tmp_path, tmp_path)
    monkeypatch.setattr(activity.os, "readlink", lambda _: (_ for _ in ()).throw(PermissionError()))
    assert activity.inspect_model_activity(tmp_path, proc_root=proc)["state"] == "unknown"


def test_guard_rechecks_after_lock_and_retains_inode(tmp_path, monkeypatch):
    states = iter([{"safe_to_modify": True}, {"safe_to_modify": False, "reason": "became active"}])
    monkeypatch.setattr(activity, "inspect_model_activity", lambda _: next(states))
    with pytest.raises(ValueError, match="became active"):
        with activity.model_mutation_guard(tmp_path):
            pytest.fail("Must not enter mutation")
    lock = tmp_path / activity.LOCK_NAME
    inode = lock.stat().st_ino
    monkeypatch.setattr(activity, "inspect_model_activity", lambda _: {"safe_to_modify": True})
    with activity.model_mutation_guard(tmp_path):
        assert lock.stat().st_ino == inode
    assert lock.exists()


def test_guard_refuses_symlink_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "inspect_model_activity", lambda _: {"safe_to_modify": True})
    target = tmp_path / "keep"
    target.write_text("unchanged")
    (tmp_path / activity.LOCK_NAME).symlink_to(target)
    with pytest.raises(ValueError, match="safely lock"):
        with activity.model_mutation_guard(tmp_path):
            pytest.fail("Must not follow symlink")
    assert target.read_text() == "unchanged"


def test_lock_excludes_other_processes_and_child_workspaces(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "inspect_model_activity", lambda _: {"safe_to_modify": True})
    (tmp_path / "VADAT").touch()
    (tmp_path / "MODEL_SPEC").touch()
    (tmp_path / "lte").mkdir()
    script = "import fcntl,sys; f=open(sys.argv[1], 'a'); fcntl.flock(f, fcntl.LOCK_EX); print('ready', flush=True); sys.stdin.read()"
    process = subprocess.Popen([sys.executable, "-c", script, str(tmp_path / activity.LOCK_NAME)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(ValueError, match="Another viewer process"):
            with activity.model_mutation_guard(tmp_path / "lte"):
                pytest.fail("Must not enter another writer's workspace")
    finally:
        process.communicate(timeout=5)
    with activity.model_mutation_guard(tmp_path / "lte"):
        pass
