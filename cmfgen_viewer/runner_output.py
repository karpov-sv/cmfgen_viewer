"""Human-facing runner presentation, independent of execution and journals."""

from datetime import datetime
import os

from tqdm import tqdm


LABELS = {
    "succeeded": ("OK", "completed"),
    "tested": ("OK", "startup test passed"),
    "preflight_failed": ("ERROR", "preflight failed"),
    "failed": ("ERROR", "executable failed"),
    "invalid_output": ("ERROR", "output validation failed"),
    "runner_error": ("ERROR", "runner failed"),
    "timeout": ("ERROR", "time limit exceeded"),
    "cancelled": ("WARN", "cancelled"),
}
COLORS = {"OK": "32", "WARN": "33", "ERROR": "31", "RUN": "36", "INFO": "36"}


class TerminalOutput:
    def __init__(self, stream, *, color="auto", verbose=False):
        self.stream = stream
        self.verbose = verbose
        self.color = color == "always" or (
            color == "auto" and getattr(stream, "isatty", lambda: False)()
            and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
        )
        self.progress_bars = {}
        self.disabled_progress_bars = set()

    def line(self, label, message):
        tag = f"[{label}]"
        if self.color:
            tag = f"\033[1;{COLORS.get(label, '36')}m{tag}\033[0m"
        # Native diagnostics and filenames must not inject terminal escapes.
        message = str(message).replace("\033", r"\x1b").replace("\r", r"\r")
        rendered = f"{tag} {message}"
        if self.progress_bars:
            tqdm.write(rendered, file=self.stream)
        else:
            print(rendered, file=self.stream, flush=True)

    def _close_progress(self, stage=None):
        keys = list(self.progress_bars) if stage is None else [stage]
        for key in keys:
            record = self.progress_bars.pop(key, None)
            if record is not None:
                record[1].close()

    def _update_progress_bar(self, item):
        stage = str(item.get("stage", "run"))
        current = item.get("current")
        total = item.get("total")
        if current is None or total is None or stage in self.disabled_progress_bars:
            return False
        try:
            current = max(0, int(current))
            total = int(total)
        except (TypeError, ValueError, OverflowError):
            return False
        if total <= 0:
            return False
        phase = str(item.get("phase", "progress"))
        signature = (phase, total)
        existing = self.progress_bars.get(stage)
        if existing is not None and existing[0] != signature:
            self._close_progress(stage)
            existing = None
        if existing is None:
            units = {
                "iterations": "iteration",
                "frequencies": "frequency",
                "output depth": "point",
                "passes": "pass",
                "stages": "stage",
            }
            remaining = item.get("remaining_seconds")
            bar_options = dict(
                total=total,
                initial=min(current, total),
                desc=f"{stage}: {phase}",
                unit=units.get(phase, "step"),
                file=self.stream,
                disable=None,
                dynamic_ncols=True,
                leave=False,
            )
            if remaining is not None:
                bar_options["postfix"] = f"{remaining:g}s remaining"
            bar = tqdm(**bar_options)
            if bar.disable:
                bar.close()
                self.disabled_progress_bars.add(stage)
                return False
            self.progress_bars[stage] = (signature, bar)
        else:
            bar = existing[1]
            remaining = item.get("remaining_seconds")
            if remaining is not None:
                bar.set_postfix_str(f"{remaining:g}s remaining", refresh=False)
            bounded = min(current, total)
            if bounded >= bar.n:
                difference = bounded - bar.n
                if difference:
                    bar.update(difference)
                else:
                    bar.refresh()
            else:
                bar.n = bounded
                bar.refresh()
        return True

    def details(self, label, messages, *, limit=6):
        messages = list(dict.fromkeys(str(message) for message in messages))
        visible = messages if self.verbose else messages[:limit]
        for message in visible:
            self.line(label, message)
        if len(visible) < len(messages):
            self.line(label, f"{len(messages)-len(visible)} more; use --verbose or inspect the saved report.")

    def warnings(self, messages):
        skipped = [m for m in messages if m.startswith("Skipping unavailable inactive-ion link:")]
        other = [m for m in messages if m not in skipped]
        if skipped and not self.verbose:
            other.append(f"{len(skipped)} unavailable inactive-ion atomic links skipped (details with --verbose).")
        elif skipped:
            other.extend(skipped)
        self.details("WARN", other)

    def status(self, report):
        self.line("INFO", f"CMFGEN model — {report['model']}")
        self.line("INFO", "Read-only status; select --stage main to run or --stage test for a zero-iteration startup check")
        for label, key in (("VADAT", "parameters"), ("MODEL_SPEC", "dimensions")):
            values = report[key]
            self.line("INFO", f"{label}: " + (", ".join(f"{name}={value}" for name, value in values.items()) or "unavailable"))
        state = report["state"]
        self.line("INFO", "Run evidence: " + (", ".join(state["evidence_files"]) if state["evidence_files"] else "runner journal" if state["has_run"] else "none recorded"))
        self.line("INFO", f"Model activity: {state['activity']['state']}")
        if state["activity"].get("reason"):
            self.line("INFO", state["activity"]["reason"])
        self.line("INFO", f"Saved checkpoint iterations: {state['saved_iterations'] if state['saved_iterations'] is not None else 'unavailable'}")
        self.line("INFO", f"Latest logged iteration: {state['last_logged_iteration'] if state['last_logged_iteration'] is not None else 'unavailable'}")
        self.line("INFO", f"Configured iterations for next main run: {state['configured_iterations'] if state['configured_iterations'] is not None else 'unavailable'}")
        self.line("INFO", f"Checkpoint: {state['restart']['message']}")
        latest = state.get("latest_run")
        if latest:
            label, message = LABELS.get(latest["status"], ("INFO", latest["status"]))
            if latest["status"] == "running" and state["activity"]["state"] != "active":
                message = "unfinished report; current execution unconfirmed"
            self.line(label, f"Latest recorded runner run: {latest['stage']} — {message}")
            self.line("INFO", f"Run report: {latest['journal']}/result.json")
        main_result = state["main_result"]
        self.line("INFO", f"Main solution: {main_result['status_label']} — {main_result['summary']}")
        if self.verbose:
            for detail in main_result.get("details", []):
                self.line("INFO", detail["message"])
        self.warnings(report.get("warnings", []))
        self.line("INFO", "Main-stage preflight:")
        preflight = report["preflight"]
        if preflight.get("executable"):
            self.plan(preflight)
        else:
            self.details("ERROR", preflight.get("errors", []))
            self.line("ERROR", "Preflight failed — nothing launched")

    def plan(self, plan):
        if plan.get("kind") == "sequence":
            self.line("INFO", f"CMFGEN multi-stage run — {plan['model']}")
            self.line("INFO", "Sequence: " + " → ".join(plan["stages"]))
            self.warnings(plan.get("warnings", []))
            self.line("INFO", f"Initial stage preflight ({plan['stages'][0]}):")
            self.plan(plan["initial_plan"])
            self.line(
                "OK" if plan["ready"] else "ERROR",
                "Sequence may start; later stages remain guarded by just-in-time preflight"
                if plan["ready"]
                else "Sequence cannot start — nothing launched",
            )
            return
        if plan["stage"] == "cleanup":
            self.line("INFO", f"CMFGEN model cleanup — {plan['model']}")
            entries = list(plan.get("entries", []))
            symlink_count = sum(entry.get("kind") == "Symlink" for entry in entries)
            file_count = len(entries) - symlink_count
            self.line(
                "INFO",
                f"{plan['entry_count']} candidate(s), {plan['human_size']}; "
                f"{file_count} file(s), {symlink_count} symlink(s); "
                "entries will be archived in the run journal",
            )
            display_entries = sorted(
                entries,
                key=lambda entry: (entry.get("kind") == "Symlink", str(entry.get("name", "")).lower()),
            )
            if not self.verbose:
                display_entries = display_entries[:24]
            for entry in display_entries:
                target = f" → {entry['target']}" if entry.get("target") else ""
                self.line("INFO", f"{entry['name']} ({entry['reason']}){target}")
            if len(display_entries) < len(entries):
                self.line(
                    "INFO",
                    f"{len(entries) - len(display_entries)} more candidate(s); "
                    "use --verbose or --json for the complete list.",
                )
            self.warnings(plan.get("warnings", []))
            self.details("ERROR", plan.get("errors", []))
            self.line(
                "OK" if plan["ready"] else "ERROR",
                "Cleanup preflight passed"
                if plan["ready"]
                else "Cleanup preflight failed — nothing changed",
            )
            return
        if plan["stage"] == "promote":
            self.line("INFO", f"CMFGEN LTE/hydro promotion — {plan['model']}")
            self.line("INFO", "Filesystem handoff only; no native executable will be launched")
            if plan.get("synchronized_rmax") is not None:
                self.line("INFO", f"VADAT RMAX will be synchronized to {plan['synchronized_rmax']:.12g}")
            if plan.get("invalidates"):
                self.line(
                    "INFO",
                    "Will archive and invalidate previous main state: "
                    + ", ".join(plan["invalidates"]),
                )
            self.warnings(plan.get("warnings", []))
            self.details("ERROR", plan.get("errors", []))
            self.line("OK" if plan["ready"] else "ERROR", "Promotion preflight passed" if plan["ready"] else "Promotion preflight failed — nothing changed")
            return
        self.line("INFO", f"CMFGEN {plan['stage']} — {plan['model']}")
        timeout = plan.get("timeout")
        time_limit = f"{timeout:g}s budget" if timeout is not None else "no time limit"
        threads = plan.get("threads")
        thread_count = f"{threads} thread(s)" if threads is not None else "inherited thread settings"
        memory_mib = plan.get("memory_mib")
        memory_limit = f"{memory_mib} MiB address-space limit" if memory_mib is not None else "no runner memory limit (host limits inherited)"
        core_dumps = "core dumps disabled" if plan.get("no_core_dumps") else "core-dump policy inherited"
        self.line("INFO", f"{thread_count} | {time_limit} | {memory_limit} | {core_dumps}")
        self.line("INFO", f"Executable: {plan['executable']}")
        if plan.get("restart"):
            self.line("INFO", plan["restart"]["message"])
        passes = plan.get("passes", [])
        if passes:
            self.line("INFO", "Passes: " + " → ".join(step["id"] for step in passes))
        self.warnings(plan.get("warnings", []))
        self.details("ERROR", plan.get("errors", []))
        if self.verbose:
            self.line("INFO", f"Working directory: {plan['cwd']}")
            self.line("INFO", f"{len(plan.get('links', []))} atomic links; {len(plan.get('inputs', []))} input snapshots")
            for name, source in plan.get("configuration_sources", {}).items():
                self.line("INFO", f"{name} supplied by {source}")
            for step in passes:
                if step.get("overrides"):
                    self.line("INFO", f"{step['id']} overrides: " + ", ".join(f"{k}={v}" for k, v in step["overrides"].items()))
        self.line("OK" if plan["ready"] else "ERROR", "Preflight passed" if plan["ready"] else "Preflight failed — nothing launched")

    def event(self, item):
        kind = item["event"]
        stage = item.get("stage", "")
        if kind == "run_finished":
            self._close_progress(stage or None)
            return
        if kind == "sequence_finished":
            self._close_progress("sequence")
            return
        if kind == "sequence_started":
            self.line("RUN", "multi-stage sequence: starting")
        elif kind == "sequence_stage_preflight":
            self.line(
                "RUN",
                f"stage {item['index']}/{item['total']} {stage}: preflight",
            )
        elif kind == "sequence_stage_ready":
            self.line("OK", f"{stage}: preflight passed")
        elif kind == "sequence_stage_completed":
            self.line("OK", f"{stage}: accepted; advancing to the next stage")
        elif kind == "sequence_stage_blocked":
            self.line(
                "ERROR",
                f"{stage}: sequence stopped ({item['status']}); later stages will not run",
            )
            self.details("ERROR", item.get("problems", []))
        elif kind == "startup":
            return  # Already shown by the preflight summary.
        if kind == "startup_fallback":
            self.line("WARN", item["message"])
        elif kind == "stage_started":
            self.line("RUN", f"{stage}: starting")
        elif kind == "stage_finished":
            self._close_progress(stage)
            label, message = LABELS.get(item["status"], ("INFO", item["status"]))
            if stage in {"promote", "cleanup"} and item["status"] == "failed":
                message = "filesystem operation failed"
            self.line(label, f"{stage}: {message}")
        elif kind == "progress":
            if not self._update_progress_bar(item):
                self._close_progress(str(item.get("stage", "run")))
        # The final summary replaces the raw run_finished event.

    def result(self, result, *, preflight_warnings=()):
        if result.get("stage") == "sequence":
            self._sequence_result(result)
            return
        status = result["status"]
        label, message = LABELS.get(status, ("ERROR", status))
        if result.get("stage") in {"promote", "cleanup"} and status == "failed":
            message = "filesystem operation failed"
        passes = result.get("passes", [])
        native_warnings = {}
        for step in passes:
            for warning in step.get("diagnostic_warnings", []):
                native_warnings.setdefault(warning, []).append(step["id"])
        ordered = sorted(native_warnings, key=lambda warning: not any(
            word in warning.lower() for word in ("fell back", "possible error", "converg", "nonfinite", "nan")
        ))
        warnings = [f"{', '.join(dict.fromkeys(native_warnings[w]))}: {w}" for w in ordered]
        warnings.extend(preflight_warnings)
        warnings = list(dict.fromkeys(warnings))
        if warnings and status in {"succeeded", "tested"}:
            label = "WARN"
            message += " with warnings"
        duration = ""
        try:
            elapsed = (datetime.fromisoformat(result["finished_at"]) - datetime.fromisoformat(result["started_at"])).total_seconds()
            duration = f" in {elapsed:.2f}s"
        except (KeyError, ValueError, TypeError):
            pass
        self.line(label, f"{result.get('stage', 'Run')}: {message}{duration}")
        if passes:
            successful = sum(step["status"] == "succeeded" for step in passes)
            total = result.get("planned_passes", len(passes))
            self.line("INFO", f"{successful}/{total} passes completed successfully; {len(passes)} attempted")
        if status == "succeeded" and result.get("promotion"):
            promotion = result["promotion"]
            self.line("OK", f"Promoted LTE/hydro results with RMAX={promotion['synchronized_rmax']:.12g}")
            self.line("INFO", f"Backup: {promotion['backup_path']}")
            invalidated = promotion.get("invalidated_files", [])
            if invalidated:
                self.line("INFO", "Invalidated previous main state: " + ", ".join(invalidated))
        if result.get("cleanup"):
            cleanup = result["cleanup"]
            self.line(
                "OK" if status == "succeeded" else "WARN",
                f"Archived {cleanup['removed_count']} cleanup candidate(s)",
            )
            self.line("INFO", f"Recovery archive: {cleanup['archive_path']}")
        if result.get("error"):
            self.line("ERROR", result["error"])
        self.details("ERROR", result.get("restore_errors", []))
        for step in passes:
            if step.get("returncode") not in {None, 0}:
                self.line("ERROR", f"{step['id']}: exit status {step['returncode']}")
            self.details("ERROR", [f"{step['id']}: {problem}" for problem in step.get("problems", [])])
            if step.get("output"):
                self.line("OK", f"Saved spectrum: {step['output']}")
            if step["status"] != "succeeded" and step.get("log"):
                self.line("INFO", f"{step['id']} log: {step['log']}")
            if step.get("diagnostic_tail") and (self.verbose or step["status"] != "succeeded"):
                lines = step["diagnostic_tail"].strip().splitlines()
                selected = lines if self.verbose else lines[-12:]
                if selected:
                    self.line("INFO", f"{step['id']} native diagnostics" + (":" if self.verbose else " (last 12 lines; more in saved report):"))
                    for line in selected:
                        print("    " + line.replace("\033", r"\x1b").replace("\r", r"\r"), file=self.stream)
        self.warnings(warnings)
        if status in {"succeeded", "tested"}:
            if result.get("stage") in {"promote", "cleanup"}:
                self.line("INFO", "Filesystem checks passed; scientific acceptance is not applicable.")
            else:
                self.line("INFO", "Execution checks passed; scientific convergence/acceptance is not assessed.")
        if result.get("startup_observed", {}).get("mode") == "unconfirmed":
            self.line("INFO", "Startup mode has no explicit native confirmation; see the saved report.")
        if result.get("journal"):
            self.line("INFO", f"Run report: {result['journal']}/result.json")

    def _sequence_result(self, result):
        status = result["status"]
        label, message = LABELS.get(status, ("ERROR", status))
        stages = result.get("stages", [])
        completed = result.get("completed_stages", [])
        duration = ""
        try:
            elapsed = (
                datetime.fromisoformat(result["finished_at"])
                - datetime.fromisoformat(result["started_at"])
            ).total_seconds()
            duration = f" in {elapsed:.2f}s"
        except (KeyError, ValueError, TypeError):
            pass
        self.line(label, f"Multi-stage run: {message}{duration}")
        self.line(
            "INFO",
            f"{len(completed)}/{len(stages)} stages completed successfully: "
            + (", ".join(completed) if completed else "none"),
        )
        for stage_result in result.get("stage_results", []):
            if stage_result["status"] == "preflight_failed":
                self.line("ERROR", f"{stage_result['stage']}: preflight failed")
                self.details("ERROR", stage_result.get("problems", []))
                self.warnings(stage_result.get("preflight_warnings", []))
            else:
                self.result(
                    stage_result,
                    preflight_warnings=stage_result.get("preflight_warnings", []),
                )
                if not stage_result.get("passes"):
                    self.details("ERROR", stage_result.get("problems", []))
        remaining = result.get("remaining_stages", [])
        if remaining:
            self.line("WARN", "Not run: " + ", ".join(remaining))
        if result.get("error"):
            self.line("ERROR", result["error"])
        scientific = result.get("scientific_acceptance", "not assessed")
        self.line(
            "INFO",
            "Stage execution and validation succeeded only where reported; "
            + (
                "scientific acceptance is not applicable."
                if scientific == "not applicable"
                else "scientific convergence/acceptance is not assessed."
            ),
        )
        if result.get("journal"):
            self.line("INFO", f"Sequence report: {result['journal']}/result.json")
