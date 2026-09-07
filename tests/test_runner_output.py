import io
import json

import pytest

from cmfgen_viewer import runner
from cmfgen_viewer.runner_output import TerminalOutput


@pytest.fixture
def plan():
    return {
        "ready": True, "stage": "main", "model": "/tmp/test-model",
        "cwd": "/tmp/test-model", "executable": "/opt/cmf/exe/cmfgen_dev.exe",
        "threads": 2, "timeout": 60, "memory_mib": 2048,
        "restart": {"message": "Continuation from POINT1 (saved iteration 7, record 2)"},
        "passes": [{"id": "main", "overrides": {}}], "warnings": [], "errors": [],
    }


@pytest.fixture
def result():
    return {
        "status": "succeeded", "stage": "main", "journal": "/tmp/test-model/.cmfgen-runs/test",
        "started_at": "2026-09-07T10:00:00+00:00", "finished_at": "2026-09-07T10:00:02+00:00",
        "passes": [{"id": "main", "status": "succeeded", "returncode": 0,
                    "problems": [], "diagnostic_warnings": [], "log": "/tmp/test/process.log"}],
    }


def test_readable_preflight_summary_and_grouped_warnings(plan):
    plan["warnings"] = [f"Skipping unavailable inactive-ion link: ion-{i}" for i in range(20)]
    stream = io.StringIO()
    TerminalOutput(stream).plan(plan)
    text = stream.getvalue()
    assert "[OK] Preflight passed" in text
    assert "2 thread(s)" in text
    assert "Continuation from POINT1" in text
    assert "[WARN] 20 unavailable inactive-ion" in text
    assert "ion-19" not in text
    assert "\033" not in text
    assert not text.lstrip().startswith("{")


def test_success_and_warning_states_are_distinct(result):
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    assert "[OK] main: completed in 2.00s" in stream.getvalue()
    assert "scientific convergence/acceptance is not assessed" in stream.getvalue()
    assert "/result.json" in stream.getvalue()
    stream = io.StringIO()
    result["passes"][0]["diagnostic_warnings"] = ["Possible error converging f"]
    TerminalOutput(stream).result(result)
    assert "[WARN] main: completed with warnings" in stream.getvalue()
    assert "[WARN] main: Possible error converging f" in stream.getvalue()


@pytest.mark.parametrize("status", ["failed", "invalid_output", "runner_error", "timeout", "cancelled"])
def test_failures_show_diagnostics_and_log_location(result, status):
    result["status"] = status
    step = result["passes"][0]
    step.update(status=status, returncode=9, problems=["Missing OBSFRAME"],
                diagnostic_tail="Error in INS_LINE:\nInconsistent line and start line frequencies")
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    text = stream.getvalue()
    assert "[ERROR]" in text
    assert "exit status 9" in text
    assert "Missing OBSFRAME" in text
    assert "Inconsistent line and start line frequencies" in text
    assert step["log"] in text


def test_verbose_shows_all_reported_warnings_and_tail(result):
    result["passes"][0]["diagnostic_warnings"] = [f"Warning {i}" for i in range(12)]
    result["passes"][0]["diagnostic_tail"] = "captured native diagnostic"
    stream = io.StringIO()
    TerminalOutput(stream, verbose=True).result(result)
    assert "Warning 11" in stream.getvalue()
    assert "captured native diagnostic" in stream.getvalue()


def test_identical_warnings_across_passes_are_grouped(result):
    step = result["passes"][0]
    step["diagnostic_warnings"] = ["Warning repeated"]
    result["passes"].append({**step, "id": "second"})
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    assert stream.getvalue().count("Warning repeated") == 1
    assert "main, second: Warning repeated" in stream.getvalue()


def test_color_auto_and_explicit_controls(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    stream = TTY()
    TerminalOutput(stream).line("OK", "ready")
    assert "\033[1;32m" in stream.getvalue()
    monkeypatch.setenv("NO_COLOR", "")
    stream = TTY()
    TerminalOutput(stream).line("OK", "ready")
    assert "\033" not in stream.getvalue()
    stream = io.StringIO()
    TerminalOutput(stream, color="always").line("ERROR", "bad")
    assert "\033[1;31m" in stream.getvalue()
    stream = TTY()
    TerminalOutput(stream, color="never").line("OK", "ready")
    assert "\033" not in stream.getvalue()


def test_progress_is_throttled_without_losing_counter_updates():
    stream = io.StringIO()
    output = TerminalOutput(stream)
    event = {"event": "progress", "stage": "main", "phase": "iteration", "current": 8}
    output.event(event)
    output.event(event)
    output.event({**event, "current": 9})
    assert stream.getvalue().count("iteration 8") == 1
    assert "iteration 9" in stream.getvalue()
    output.event({"event": "startup_fallback", "message": "fell back to fresh startup"})
    assert "[WARN] fell back" in stream.getvalue()


def setup_cli(monkeypatch, plan, result):
    monkeypatch.setattr(runner, "resolve_runner_config", lambda **kwargs: ({}, {}))
    monkeypatch.setattr(runner, "build_run_plan", lambda *args, **kwargs: plan)
    def run(plan, emit):
        emit({"event": "stage_started", "stage": "main"})
        emit({"event": "stage_finished", "stage": "main", "status": "succeeded"})
        return result
    monkeypatch.setattr(runner, "run_plan", run)


@pytest.mark.parametrize("action", ["plan", "run"])
def test_cli_defaults_to_human_output(monkeypatch, capsys, plan, result, action):
    setup_cli(monkeypatch, plan, result)
    assert runner.main([action, "/tmp/test-model"]) == 0
    captured = capsys.readouterr()
    assert "[OK]" in captured.out
    assert not captured.out.lstrip().startswith("{")
    assert "[RUN]" in captured.err if action == "run" else captured.err == ""


@pytest.mark.parametrize("progress", [None, "json"])
def test_json_mode_has_clean_stdout_and_opt_in_events(monkeypatch, capsys, plan, result, progress):
    setup_cli(monkeypatch, plan, result)
    args = ["run", "/tmp/test-model", "--json"]
    if progress:
        args += ["--progress", progress]
    assert runner.main(args) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "succeeded"
    if progress:
        events = [json.loads(line) for line in captured.err.splitlines()]
        assert [item["event"] for item in events] == ["stage_started", "stage_finished"]
    else:
        assert captured.err == ""


def test_preflight_failure_never_runs_and_is_readable(monkeypatch, capsys, plan, result):
    setup_cli(monkeypatch, plan, result)
    plan.update(ready=False, errors=["SCRTEMP is missing"])
    monkeypatch.setattr(runner, "run_plan", lambda *args: pytest.fail("should not run"))
    assert runner.main(["run", "/tmp/test-model"]) == 2
    captured = capsys.readouterr()
    assert "[ERROR] SCRTEMP is missing" in captured.err
    assert "nothing launched" in captured.err
    assert captured.out == ""


def test_config_error_is_readable_by_default(monkeypatch, capsys):
    def fail(**kwargs):
        raise runner.RunnerError("Missing CMFDIST")
    monkeypatch.setattr(runner, "resolve_runner_config", fail)
    assert runner.main(["run", "/tmp/test-model"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR] Preflight failed: Missing CMFDIST" in captured.err


def test_progress_none_preserves_final_summary(monkeypatch, capsys, plan, result):
    setup_cli(monkeypatch, plan, result)
    assert runner.main(["run", "/tmp/test-model", "--progress", "none"]) == 0
    captured = capsys.readouterr()
    assert "[RUN]" not in captured.err
    assert "[OK] main: completed" in captured.out
