"""Read correlated native crash evidence; never infer a cause from SIGILL alone."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
import sys


def macos_crash_evidence(pid: int, executable: str, *, report_dir: Path | None = None, since: float = 0) -> str:
    if report_dir is None and sys.platform != "darwin":
        return ""
    root = report_dir or Path.home() / "Library/Logs/DiagnosticReports"
    name = Path(executable).name
    try:
        reports = sorted(root.glob(f"{name}-*.ips"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        for path in reports:
            if path.stat().st_size > 4 * 1024 * 1024 or path.stat().st_mtime < since:
                continue
            try:
                text = path.read_text()
                report = json.loads(text.split("\n", 1)[1])
            except (OSError, ValueError, IndexError):
                continue
            if not isinstance(report, dict):
                continue
            if report.get("pid") != pid or report.get("procName") != name:
                continue
            frames = [frame.get("symbol", "") for thread in report.get("threads", [])
                      if thread.get("triggered") for frame in thread.get("frames", [])]
            return "\n".join(f"Native crash frame: {symbol}" for symbol in frames if symbol)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return ""


def runner_crash_sources(model: Path, outgen_mtime: float) -> dict[str, str]:
    """Read latest failed main journal only while its log is current for OUTGEN."""
    sources = {}
    try:
        runs = sorted((model / ".cmfgen-runs").iterdir(), reverse=True)[:20]
        for run in runs:
            if run.is_symlink():
                continue
            result_path = run / "result.json"
            if not result_path.is_file() or result_path.stat().st_size > 2 * 1024 * 1024:
                continue
            result = json.loads(result_path.read_text())
            if not isinstance(result, dict):
                continue
            if result.get("stage") not in {"main", "test"}:
                continue
            for step in result.get("passes", []):
                if step.get("id") not in {"main", "test"}:
                    continue
                if step.get("returncode", 0) is None or step.get("returncode", 0) >= 0:
                    continue
                log = run / step["id"] / "process.log"
                if log.stat().st_mtime < outgen_mtime:
                    continue
                with log.open("rb") as handle:
                    handle.seek(max(0, log.stat().st_size - 64 * 1024))
                    sources["process.log"] = handle.read().decode(errors="replace")
                plan = json.loads((run / "plan.json").read_text())
                frames = macos_crash_evidence(step["pid"], plan.get("executable", ""), since=datetime.fromisoformat(result["started_at"]).timestamp())
                if frames:
                    sources["process.log"] += "\n" + frames
                return sources
            # A newer main invocation supersedes older crash journals.
            return sources
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return sources
