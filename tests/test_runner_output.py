import io
import json

import pytest

from cmfgen_viewer import runner, runner_output
from cmfgen_viewer.runner_output import TerminalOutput


@pytest.fixture
def plan():
    return {
        "ready": True, "stage": "main", "model": "/tmp/test-model",
        "cwd": "/tmp/test-model", "executable": "/opt/cmf/exe/cmfgen_dev.exe",
        "threads": 2, "timeout": None, "memory_mib": 2048,
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
    assert "no time limit" in text
    assert "Continuation from POINT1" in text
    assert "[WARN] 20 unavailable inactive-ion" in text
    assert "ion-19" not in text
    assert "\033" not in text
    assert not text.lstrip().startswith("{")


def test_readable_preflight_shows_explicit_timeout(plan):
    plan["timeout"] = 60
    stream = io.StringIO()

    TerminalOutput(stream).plan(plan)

    assert "60s budget" in stream.getvalue()


def test_readable_preflight_shows_inherited_resources(plan):
    plan.update(threads=None, memory_mib=None)
    stream = io.StringIO()
    TerminalOutput(stream).plan(plan)
    text = stream.getvalue()
    assert "inherited thread settings" in text
    assert "no runner memory limit (host limits inherited)" in text
    assert "core-dump policy inherited" in text
    assert "None" not in text


def test_sequence_plan_and_result_are_presented_in_order(plan, result):
    sequence_plan = {
        "kind": "sequence",
        "stage": "sequence",
        "model": "/tmp/test-model",
        "stages": ["init", "main"],
        "initial_plan": plan,
        "warnings": ["Later stages use just-in-time preflight."],
        "ready": True,
    }
    stream = io.StringIO()
    TerminalOutput(stream).plan(sequence_plan)
    text = stream.getvalue()
    assert "Sequence: init → main" in text
    assert "Initial stage preflight (init)" in text
    assert "later stages remain guarded" in text

    first = {**result, "stage": "init", "status": "initialized"}
    first["passes"] = [{**result["passes"][0], "id": "init"}]
    sequence_result = {
        "stage": "sequence",
        "status": "preflight_failed",
        "stages": ["init", "main", "flux"],
        "completed_stages": ["init"],
        "remaining_stages": ["flux"],
        "stage_results": [
            first,
            {
                "stage": "main",
                "status": "preflight_failed",
                "passes": [],
                "problems": ["checkpoint is unhealthy"],
                "preflight_warnings": [],
            },
        ],
        "journal": "/tmp/test-model/.cmfgen-runs/sequence",
    }
    stream = io.StringIO()
    TerminalOutput(stream).result(sequence_result)
    text = stream.getvalue()
    assert "Multi-stage run: preflight failed" in text
    assert "1/3 stages completed successfully: init" in text
    assert "main: preflight failed" in text
    assert "checkpoint is unhealthy" in text
    assert "Not run: flux" in text
    assert "Sequence report:" in text


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


def test_promotion_result_reports_backup_and_invalidated_state(result):
    result["stage"] = "promote"
    result["passes"][0]["id"] = "promote"
    result["promotion"] = {
        "synchronized_rmax": 12.5,
        "backup_path": "/tmp/model/.cmfgen-viewer-backups/lte-hydro/test",
        "invalidated_files": ["POINT1", "RVTJ"],
    }
    stream = io.StringIO()

    TerminalOutput(stream).result(result)

    text = stream.getvalue()
    assert "Promoted LTE/hydro results with RMAX=12.5" in text
    assert "Backup: /tmp/model/.cmfgen-viewer-backups/lte-hydro/test" in text
    assert "Invalidated previous main state: POINT1, RVTJ" in text
    assert "Filesystem checks passed" in text


def test_cleanup_plan_summarizes_long_candidate_lists():
    entries = [
        {
            "name": f"SCRATCH{i:02d}",
            "kind": "File",
            "reason": "Native scratch output",
            "target": "",
        }
        for i in range(30)
    ]
    plan = {
        "ready": True,
        "stage": "cleanup",
        "model": "/tmp/test-model",
        "entry_count": len(entries),
        "human_size": "1.0 MB",
        "entries": entries,
        "warnings": [],
        "errors": [],
    }
    stream = io.StringIO()

    TerminalOutput(stream).plan(plan)

    text = stream.getvalue()
    assert "30 candidate(s), 1.0 MB; 30 file(s), 0 symlink(s)" in text
    assert "SCRATCH23" in text
    assert "SCRATCH24" not in text
    assert "6 more candidate(s); use --verbose or --json" in text


def test_cleanup_result_reports_recovery_archive(result):
    result["stage"] = "cleanup"
    result["passes"][0]["id"] = "cleanup"
    result["cleanup"] = {
        "removed_count": 3,
        "archive_path": "/tmp/test-model/.cmfgen-runs/test/removed",
    }
    stream = io.StringIO()

    TerminalOutput(stream).result(result)

    text = stream.getvalue()
    assert "Archived 3 cleanup candidate(s)" in text
    assert "Recovery archive: /tmp/test-model/.cmfgen-runs/test/removed" in text
    assert "Filesystem checks passed" in text

    result["status"] = "failed"
    result["passes"][0].update(status="failed", problems=["fort.63: permission denied"])
    stream = io.StringIO()
    TerminalOutput(stream).result(result)
    text = stream.getvalue()
    assert "cleanup: filesystem operation failed" in text
    assert "[WARN] Archived 3 cleanup candidate(s)" in text
    assert "Recovery archive: /tmp/test-model/.cmfgen-runs/test/removed" in text


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


def test_known_progress_falls_back_to_text_when_not_interactive():
    stream = io.StringIO()
    output = TerminalOutput(stream)

    output.event(
        {
            "event": "progress",
            "stage": "lte",
            "phase": "frequencies",
            "current": 25,
            "total": 100,
        }
    )

    assert "[RUN] lte: frequencies 25/100" in stream.getvalue()
    assert output.progress_bars == {}


def test_known_progress_uses_tqdm_with_terminal_autodetection(monkeypatch):
    class TTY(io.StringIO):
        def isatty(self):
            return True

    class FakeTqdm:
        instances = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.disable = False
            self.n = kwargs["initial"]
            self.closed = False
            self.postfix = kwargs.get("postfix")
            self.__class__.instances.append(self)

        def update(self, amount):
            self.n += amount

        def set_postfix_str(self, value, refresh=False):
            self.postfix = value

        def refresh(self):
            pass

        def close(self):
            self.closed = True

        @staticmethod
        def write(message, file):
            print(message, file=file)

    monkeypatch.setattr(runner_output, "tqdm", FakeTqdm)
    stream = TTY()
    output = TerminalOutput(stream)
    event = {
        "event": "progress",
        "stage": "main",
        "phase": "iterations",
        "current": 2,
        "total": 5,
        "remaining_seconds": 30,
    }

    output.event(event)
    output.event({**event, "current": 4})

    bar = FakeTqdm.instances[0]
    assert bar.kwargs["disable"] is None
    assert bar.kwargs["desc"] == "main: iterations"
    assert bar.kwargs["unit"] == "iteration"
    assert bar.n == 4
    assert bar.postfix == "30s remaining"
    assert stream.getvalue() == ""

    output.event({"event": "stage_finished", "stage": "main", "status": "succeeded"})
    assert bar.closed is True
    assert output.progress_bars == {}


def setup_cli(monkeypatch, plan, result):
    monkeypatch.setattr(runner, "resolve_runner_config", lambda **kwargs: ({}, {}))
    monkeypatch.setattr(runner, "build_run_plan", lambda *args, **kwargs: plan)
    def run(plan, emit):
        emit({"event": "stage_started", "stage": "main"})
        emit({"event": "stage_finished", "stage": "main", "status": "succeeded"})
        return result
    monkeypatch.setattr(runner, "run_plan", run)


@pytest.mark.parametrize("planning", [True, False])
def test_cli_defaults_to_human_output(monkeypatch, capsys, plan, result, planning):
    setup_cli(monkeypatch, plan, result)
    args = ["/tmp/test-model"] + (["--plan"] if planning else [])
    assert runner.main(args) == 0
    captured = capsys.readouterr()
    assert "[OK]" in captured.out
    assert not captured.out.lstrip().startswith("{")
    assert captured.err == "" if planning else "[RUN]" in captured.err


def test_cli_omitted_action_defaults_to_run(monkeypatch, capsys, plan, result):
    setup_cli(monkeypatch, plan, result)

    assert runner.main(["--stage", "main", "/tmp/test-model"]) == 0

    captured = capsys.readouterr()
    assert "[OK] main: completed" in captured.out
    assert "[RUN] main: starting" in captured.err


def test_cli_resource_limits_are_opt_in(monkeypatch, capsys, plan):
    seen = []
    monkeypatch.setattr(runner, "resolve_runner_config", lambda **kwargs: ({}, {}))

    def build(*args, **kwargs):
        seen.append((kwargs["timeout"], kwargs["memory_mib"], kwargs["no_core_dumps"]))
        return plan

    monkeypatch.setattr(runner, "build_run_plan", build)

    assert runner.main(["/tmp/test-model", "--plan"]) == 0
    assert runner.main(["/tmp/test-model", "--plan", "--timeout", "3600", "--memory-mib", "16384", "--no-core-dumps"]) == 0
    capsys.readouterr()

    assert seen == [(None, None, False), (3600.0, 16384, True)]


def test_cli_repeated_stage_builds_ordered_sequence(monkeypatch, capsys, plan):
    captured_stages = []
    monkeypatch.setattr(
        runner,
        "resolve_runner_config",
        lambda **kwargs: ({}, {"threads": "default"}),
    )

    def build(_model, stages, **_options):
        captured_stages.append(stages)
        return {
            "kind": "sequence",
            "stage": "sequence",
            "model": "/tmp/test-model",
            "stages": stages,
            "initial_plan": plan,
            "warnings": [],
            "errors": [],
            "ready": True,
        }

    monkeypatch.setattr(runner, "build_sequence_plan", build)

    assert runner.main(
        [
            "/tmp/test-model",
            "--plan",
            "--stage",
            "init",
            "--stage",
            "main",
            "--stage",
            "flux",
        ]
    ) == 0

    assert captured_stages == [["init", "main", "flux"]]
    assert "Sequence: init → main → flux" in capsys.readouterr().out


@pytest.mark.parametrize("progress", [None, "json"])
def test_json_mode_has_clean_stdout_and_opt_in_events(monkeypatch, capsys, plan, result, progress):
    setup_cli(monkeypatch, plan, result)
    args = ["/tmp/test-model", "--json"]
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
    assert runner.main(["/tmp/test-model"]) == 2
    captured = capsys.readouterr()
    assert "[ERROR] SCRTEMP is missing" in captured.err
    assert "nothing launched" in captured.err
    assert captured.out == ""


def test_config_error_is_readable_by_default(monkeypatch, capsys):
    def fail(**kwargs):
        raise runner.RunnerError("Missing CMFDIST")
    monkeypatch.setattr(runner, "resolve_runner_config", fail)
    assert runner.main(["/tmp/test-model"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "[ERROR] Preflight failed: Missing CMFDIST" in captured.err


def test_progress_none_preserves_final_summary(monkeypatch, capsys, plan, result):
    setup_cli(monkeypatch, plan, result)
    assert runner.main(["/tmp/test-model", "--progress", "none"]) == 0
    captured = capsys.readouterr()
    assert "[RUN]" not in captured.err
    assert "[OK] main: completed" in captured.out
