import os

import pytest

from cmfgen_viewer.runner_restart import inspect_restart, read_pointer


RVTJ_CORE = "ND: 2\nRadius\n2 1\nVelocity\n20 10\nTemperature\n1 2\nElectron density\n1e10 2e10\n"


@pytest.fixture
def checkpoint(tmp_path):
    (tmp_path / "MODEL_SPEC").write_text("2 [ND]\n1 [NC]\n3 [NP]\n3,3,5 [HI_ISF]\n")
    (tmp_path / "VADAT").write_text("F [DO_HYDRO]\n")
    (tmp_path / "POINT1").write_text("28-Feb-2004 !Format date\n2 9 1 -1000 F\nlabels\n")
    (tmp_path / "SCRTEMP").write_bytes(b"\0"*4096)
    (tmp_path / "MODEL").write_text("2 !Number of depth points\nSpecies N_F N_S Z\nHI 5 3 1.0 1.0\n\f")
    return tmp_path


def test_checkpoint_detected_with_selected_iteration(checkpoint):
    result = inspect_restart(checkpoint)
    assert result["mode"] == "continuation"
    assert result["pointer"]["record"] == 2
    assert result["pointer"]["iterations"] == 9
    assert not result["errors"]
    assert result["health"]["status"] == "unavailable"
    assert any("health cannot be checked" in warning for warning in result["warnings"])


def test_finite_rvtj_core_passes_checkpoint_health_check(checkpoint):
    (checkpoint / "RVTJ").write_text(RVTJ_CORE)
    result = inspect_restart(checkpoint)
    assert result["mode"] == "continuation"
    assert result["health"]["status"] == "passed"
    assert not result["errors"]


@pytest.mark.parametrize(
    ("heading", "old", "bad", "reason"),
    [
        ("Temperature", "1 2", "NaN NaN", "Temperature"),
        ("Electron density", "1e10 2e10", "0 0", "Electron density"),
    ],
)
def test_poisoned_rvtj_blocks_continuation_but_not_fresh_start(checkpoint, heading, old, bad, reason):
    (checkpoint / "RVTJ").write_text(RVTJ_CORE.replace(heading + "\n" + old, heading + "\n" + bad))
    result = inspect_restart(checkpoint)
    assert result["mode"] == "continuation"
    assert result["health"]["status"] == "failed"
    assert any("Checkpoint health check failed" in error and reason in error for error in result["errors"])

    fresh = inspect_restart(checkpoint, fresh_start=True)
    assert fresh["mode"] == "fresh"
    assert fresh["health"]["status"] == "not_checked"
    assert not fresh["errors"]


@pytest.mark.parametrize("contents", [
    "2 9 1 -1000\n",
    "28-Feb-2004 !Format date\n2,9,1,-1000,.FALSE.\n",
    "28-Feb-2004 !Format date\n2 9 1 -1000 F\n",
])
def test_supported_pointer_formats(checkpoint, contents):
    (checkpoint / "POINT1").write_text(contents)
    pointer = read_pointer(checkpoint / "POINT1")
    assert pointer["iterations"] == 9
    assert pointer["writes_rvsig"] is False


@pytest.mark.parametrize("primary", [None, "", "corrupt", "0 0 0 -1000"])
def test_backup_pointer_fallback(checkpoint, primary):
    if primary is None:
        (checkpoint / "POINT1").unlink()
    else:
        (checkpoint / "POINT1").write_text(primary)
    (checkpoint / "POINT2").write_text("1 8 1 -1000\n")
    result = inspect_restart(checkpoint)
    assert result["mode"] == "continuation"
    assert result["pointer"]["file"] == "POINT2"
    assert not result["errors"]


@pytest.mark.parametrize("damage", ["missing_scratch", "empty_scratch", "short_scratch", "bad_pointer", "changed_depth", "changed_ions", "hydro_format"])
def test_invalid_checkpoint_blocked_but_fresh_start_allowed(checkpoint, damage):
    if damage == "missing_scratch":
        (checkpoint / "SCRTEMP").unlink()
    elif damage == "empty_scratch":
        (checkpoint / "SCRTEMP").write_bytes(b"")
    elif damage == "short_scratch":
        (checkpoint / "SCRTEMP").write_bytes(b"abc")
    elif damage == "bad_pointer":
        (checkpoint / "POINT1").write_text("broken")
    elif damage == "changed_depth":
        (checkpoint / "MODEL_SPEC").write_text("3 [ND]\n3,3,5 [HI_ISF]\n")
    elif damage == "changed_ions":
        (checkpoint / "MODEL_SPEC").write_text("2 [ND]\n2,2,5 [HI_ISF]\n")
    else:
        (checkpoint / "VADAT").write_text("T [DO_HYDRO]\n")
    assert inspect_restart(checkpoint)["errors"]
    fresh = inspect_restart(checkpoint, fresh_start=True)
    assert fresh["mode"] == "fresh"
    assert not fresh["errors"]


def test_orphan_scratch_uses_native_fresh_start(checkpoint):
    (checkpoint / "POINT1").unlink()
    result = inspect_restart(checkpoint)
    assert result["mode"] == "fresh"
    assert not result["errors"]
    assert any("no pointer" in warning for warning in result["warnings"])


@pytest.mark.parametrize("link_type", ["symlink", "hardlink"])
def test_unsafe_writable_checkpoints_rejected_even_for_fresh(checkpoint, link_type):
    path = checkpoint / "POINT1"
    path.rename(checkpoint / "original-pointer")
    if link_type == "symlink":
        path.symlink_to(checkpoint / "original-pointer")
    else:
        os.link(checkpoint / "original-pointer", path)
    assert inspect_restart(checkpoint)["errors"]
    assert inspect_restart(checkpoint, fresh_start=True)["errors"]


def test_missing_metadata_is_warning_not_blanket_restart_rejection(checkpoint):
    (checkpoint / "MODEL").unlink()
    result = inspect_restart(checkpoint)
    assert result["mode"] == "continuation"
    assert not result["errors"]
    assert any("cannot be cross-checked" in warning for warning in result["warnings"])
