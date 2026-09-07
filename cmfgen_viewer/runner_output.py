"""Human-facing runner presentation, independent of execution and journals."""

from datetime import datetime
import os
import time


LABELS = {
    "succeeded": ("OK", "completed"),
    "initialized": ("OK", "initialization completed"),
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
        self.last_progress = {}

    def line(self, label, message):
        tag = f"[{label}]"
        if self.color:
            tag = f"\033[1;{COLORS.get(label, '36')}m{tag}\033[0m"
        # Native diagnostics and filenames must not inject terminal escapes.
        message = str(message).replace("\033", r"\x1b").replace("\r", r"\r")
        print(f"{tag} {message}", file=self.stream, flush=True)

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

    def plan(self, plan):
        self.line("INFO", f"CMFGEN {plan['stage']} — {plan['model']}")
        self.line("INFO", f"{plan['threads']} thread(s) | {plan['timeout']:g}s budget | {plan['memory_mib']} MiB address-space limit")
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
        if kind == "startup":
            return  # Already shown by the preflight summary.
        if kind == "startup_fallback":
            self.line("WARN", item["message"])
        elif kind == "stage_started":
            self.line("RUN", f"{stage}: starting")
        elif kind == "stage_finished":
            label, message = LABELS.get(item["status"], ("INFO", item["status"]))
            self.line(label, f"{stage}: {message}")
        elif kind == "progress":
            phase, current, total = item.get("phase", "working"), item.get("current"), item.get("total")
            key = (phase, current, total)
            now = time.monotonic()
            previous = self.last_progress.get(stage)
            if previous and previous[0] == key and now - previous[1] < 10:
                return
            self.last_progress[stage] = (key, now)
            detail = phase
            if current is not None:
                detail += f" {current}"
                if total is not None:
                    detail += f"/{total}"
            if item.get("remaining_seconds") is not None:
                detail += f" ({item['remaining_seconds']:g}s remaining)"
            self.line("RUN", f"{stage}: {detail}")
        # The final summary replaces the raw run_finished event.

    def result(self, result, *, preflight_warnings=()):
        status = result["status"]
        label, message = LABELS.get(status, ("ERROR", status))
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
        if warnings and status in {"succeeded", "initialized"}:
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
        if status in {"succeeded", "initialized"}:
            self.line("INFO", "Execution checks passed; scientific convergence/acceptance is not assessed.")
        if result.get("startup_observed", {}).get("mode") == "unconfirmed":
            self.line("INFO", "Startup mode has no explicit native confirmation; see the saved report.")
        if result.get("journal"):
            self.line("INFO", f"Run report: {result['journal']}/result.json")
