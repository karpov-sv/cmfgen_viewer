"""Standalone execution, per-pass evidence, and conservative validation."""

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from .model_activity import model_mutation_guard
from .parsers.common import parse_float_token
from .runner_config import resolve_runner_config
from .runner_cleanup import build_cleanup_plan
from .runner_promotion import build_promotion_plan
from .runner_recipe import RunnerError, build_run_plan, override_controls, snapshot
from .runner_validation import validate_rosseland_table, validate_rvsig_structure, validate_rvtj_core
from .runner_restart import RESTART_FILES, observe_startup
from .runner_output import TerminalOutput


NATIVE_STAGES = {"init", "main", "lte", "hydro", "flux"}
FILESYSTEM_STAGES = {"promote", "cleanup"}
STAGE_CHOICES = ("init", "main", "lte", "hydro", "promote", "flux", "cleanup")


def _stage_succeeded(stage: str, status: str) -> bool:
    return status == "succeeded" or (stage == "init" and status == "initialized")


def _json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix=".report-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _tail(path, limit=1024*1024):
    if not path.is_file():
        return ""
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - limit))
        return handle.read(limit).decode(errors="replace")


def _write_control(path, contents, mode=0o644):
    descriptor, temporary = tempfile.mkstemp(prefix=".runner-control-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _publish(source, destination):
    descriptor, temporary = tempfile.mkstemp(prefix=".runner-product-", dir=destination.parent)
    os.close(descriptor)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _stop(process):
    # Only the process group created by this runner is signalled.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=3)
    # The leader can exit before descendants. Never leave its process group
    # running after cancellation/timeout.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _validate(stage, cwd, before):
    required = {"main": ("MOD_SUM", "RVTJ", "MODEL"), "init": ("RVTJ", "MODEL"),
                "lte": ("ROSSELAND_LTE_TAB",), "hydro": ("RVSIG_COL_NEW",),
                "flux": ("OBSFRAME",)}[stage]
    problems = []
    fresh_outputs = {}
    for name in required:
        current = snapshot(cwd / name)
        fresh_outputs[name] = bool(
            current["exists"] and current.get("size") and current != before.get(name)
        )
        if not fresh_outputs[name]:
            problems.append(f"Missing, empty, or unchanged output: {name}")
    if stage in {"main", "init"}:
        if (
            stage == "main"
            and fresh_outputs["MOD_SUM"]
            and "Model Finalized on:" not in _tail(cwd / "MOD_SUM")
        ):
            problems.append("Missing CMFGEN finalization record")
        if fresh_outputs["RVTJ"]:
            try:
                validate_rvtj_core(cwd / "RVTJ", cwd / "MODEL_SPEC", finite_all=stage == "main")
                # NUM_ITS=0 does not compute opacity/radiation diagnostics or write
                # MOD_SUM. Its acceptance covers only initialized core vectors.
            except (OSError, ValueError, UnicodeError) as exc:
                problems.append(f"Invalid RVTJ: {exc}")
    elif stage == "flux":
        if "CMF_FLUX has finished" not in _tail(cwd / "OUT_FLUX"):
            problems.append("Missing native CMF_FLUX completion marker")
        if fresh_outputs["OBSFRAME"]:
            try:
                text = (cwd / "OBSFRAME").read_text()
                arrays = []
                for heading in ("Continuum Frequencies", "Observed intensity (Janskys)"):
                    matches = list(re.finditer(r"^[ \t]*" + re.escape(heading) + r"[ \t]*(?:\([ \t]*(\d+)[ \t]*\))?[ \t]*\n", text, re.I | re.M))
                    if len(matches) != 1:
                        raise ValueError(f"Missing or duplicate {heading} vector")
                    match = matches[0]
                    if not arrays and match[1] is None:
                        raise ValueError("Missing continuum frequency count")
                    expected_count = int(match[1]) if match[1] is not None else len(arrays[0])
                    numbers = []
                    for token in text[match.end():].split():
                        number = parse_float_token(token)
                        if number is None:
                            break
                        numbers.append(number)
                    if len(numbers) != expected_count or len(numbers) < 2 or not all(math.isfinite(x) for x in numbers):
                        raise ValueError(f"Truncated/nonfinite {heading} vector")
                    arrays.append(numbers)
                if len(arrays[0]) != len(arrays[1]) or any(x <= 0 for x in arrays[0]):
                    raise ValueError("Invalid spectrum dimensions/frequencies")
            except Exception as exc:
                problems.append(f"Spectrum could not be parsed: {exc}")
    elif stage == "lte":
        if fresh_outputs["ROSSELAND_LTE_TAB"]:
            try:
                validate_rosseland_table(cwd / "ROSSELAND_LTE_TAB")
            except (OSError, ValueError, UnicodeError) as exc:
                problems.append(f"Invalid Rosseland table: {exc}")
    else:
        if fresh_outputs["RVSIG_COL_NEW"]:
            try:
                validate_rvsig_structure(cwd / "RVSIG_COL_NEW", cwd / "MODEL_SPEC")
            except (OSError, ValueError, UnicodeError) as exc:
                problems.append(f"Invalid hydro structure: {exc}")
    return problems


def _progress(stage, cwd):
    filename = "OUTGEN" if stage in {"main", "init"} else "OUTLTE" if stage == "lte" else "WIND_HYD" if stage == "hydro" else "OUT_FLUX"
    text = _tail(cwd / filename, 128*1024)
    if stage == "lte":
        total = re.findall(r"Number of frequencies is\s+(\d+)", text)
        counter = re.findall(r"\d+", _tail(cwd / "ML_COUNTER", 2048))
        if total and counter:
            return {"phase": "frequencies", "current": int(counter[-1]), "total": int(total[-1])}
    elif stage == "main":
        counters = re.findall(r"Current great iteration count is\s+(\d+)", text)
        if counters:
            return {"phase": "iteration", "current": int(counters[-1])}
    elif stage == "hydro":
        text = _tail(cwd / "RVSIG_COL_NEW", 512*1024)
        expected = re.search(r"^\s*(\d+)\s*!\s*Number of depth points", text, re.M | re.I)
        indices = re.findall(r"^\s*\S+\s+\S+\s+\S+\s+\S+\s+(\d+)\s*$", text, re.M)
        if expected and indices:
            return {"phase": "output depth", "current": int(indices[-1]), "total": int(expected[1])}
    elif stage == "flux":
        counters = re.findall(r"LS loop\s*(\d+)\s+is finished", text)
        if counters:
            return {"phase": "LS loop", "current": int(counters[-1])}
    return {"phase": "initialization" if stage == "init" else "working"}


def _build_requested_stage_plan(
    model: Path,
    stage: str,
    *,
    native_config: dict[str, object],
    configuration_sources: dict[str, str],
    timeout: float | None,
    memory_mib: int,
    iterations: int | None,
    fresh_start: bool,
    cleanup_files: list[str] | None,
) -> dict[str, object]:
    """Build one stage, applying sequence-wide options only where relevant."""
    if stage == "promote":
        plan = build_promotion_plan(model)
        sources: dict[str, str] = {}
    elif stage == "cleanup":
        plan = build_cleanup_plan(model, selected_names=cleanup_files)
        sources = {}
    else:
        plan = build_run_plan(
            model,
            stage=stage,
            **native_config,
            timeout=timeout,
            memory_mib=memory_mib,
            iterations=iterations if stage == "main" else None,
            fresh_start=fresh_start if stage in {"main", "init"} else False,
        )
        sources = configuration_sources
    plan["configuration_sources"] = sources
    return plan


def build_sequence_plan(
    model: Path,
    stages: list[str],
    *,
    native_config: dict[str, object],
    configuration_sources: dict[str, str],
    timeout: float | None,
    memory_mib: int,
    iterations: int | None,
    fresh_start: bool,
    cleanup_files: list[str] | None,
) -> dict[str, object]:
    """Build the initial preflight and a serializable just-in-time stage recipe."""
    if len(stages) < 2:
        raise RunnerError("A multi-stage plan requires at least two stages")
    if len(set(stages)) != len(stages):
        raise RunnerError("A multi-stage run cannot contain duplicate stages")
    fresh_start_stage = (
        next((stage for stage in stages if stage in {"init", "main"}), None)
        if fresh_start
        else None
    )
    initial = _build_requested_stage_plan(
        model,
        stages[0],
        native_config=native_config,
        configuration_sources=configuration_sources,
        timeout=timeout,
        memory_mib=memory_mib,
        iterations=iterations,
        fresh_start=stages[0] == fresh_start_stage,
        cleanup_files=cleanup_files,
    )
    model_path = Path(str(initial["model"]))
    serialized_config = {
        key: str(value) if isinstance(value, Path) else value
        for key, value in native_config.items()
    }
    return {
        "schema_version": 1,
        "profile": "ostar-v1",
        "kind": "sequence",
        "stage": "sequence",
        "model": str(model_path),
        "cwd": str(model_path),
        "stages": stages,
        "initial_plan": initial,
        "stage_options": {
            "native_config": serialized_config,
            "timeout": timeout,
            "memory_mib": memory_mib,
            "iterations": iterations,
            "fresh_start": fresh_start,
            "fresh_start_stage": fresh_start_stage,
            "cleanup_files": cleanup_files,
        },
        "configuration_sources": configuration_sources,
        "warnings": [
            "Only the first stage is preflighted now; every later stage is "
            "preflighted immediately before execution against outputs from preceding stages."
        ],
        "errors": list(initial.get("errors", [])),
        "ready": bool(initial.get("ready")),
        "scientific_acceptance": (
            "not applicable"
            if all(stage in FILESYSTEM_STAGES for stage in stages)
            else "not assessed"
        ),
        "launches_legacy_scripts": False,
    }


def _sequence_stage_plan(
    sequence: dict[str, object],
    stage: str,
    *,
    timeout: float | None,
) -> dict[str, object]:
    options = sequence["stage_options"]
    native_config = dict(options["native_config"])
    for key in ("cmfgen_root", "atomic_root"):
        if key in native_config:
            native_config[key] = Path(str(native_config[key]))
    return _build_requested_stage_plan(
        Path(str(sequence["model"])),
        stage,
        native_config=native_config,
        configuration_sources=dict(sequence.get("configuration_sources", {})),
        timeout=timeout,
        memory_mib=int(options["memory_mib"]),
        iterations=options.get("iterations"),
        fresh_start=stage == options.get("fresh_start_stage"),
        cleanup_files=options.get("cleanup_files"),
    )


def run_plan(plan: dict, emit=None) -> dict:
    if plan.get("kind") == "sequence":
        return _run_sequence_plan(plan, emit)
    if plan["stage"] == "cleanup":
        return _run_cleanup_plan(plan, emit)
    if plan["stage"] == "promote":
        return _run_promotion_plan(plan, emit)
    if not plan["ready"]:
        raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
    model, cwd = Path(plan["model"]), Path(plan["cwd"])
    stage = plan["stage"]
    with model_mutation_guard(model, RunnerError) as lock_fd:
        for old in [*plan["inputs"], plan["executable_snapshot"]]:
            if snapshot(Path(old["path"])) != old:
                raise RunnerError(f"Input changed since preflight: {old['path']}")
        for path in cwd.iterdir():
            if path.is_symlink() and path.name not in plan["permitted_links"]:
                raise RunnerError(f"Unclassified symlink in execution workspace: {path}")
        root = model / ".cmfgen-runs"
        if root.is_symlink():
            raise RunnerError("Refusing symlinked run archive")
        root.mkdir(exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        journal = root / run_id
        journal.mkdir()
        _json(journal / "plan.json", plan)
        result = {"run_id": run_id, "stage": stage, "status": "running", "journal": str(journal),
                  "passes": [], "planned_passes": len(plan["passes"]),
                  "scientific_acceptance": "not assessed", "started_at": datetime.now(timezone.utc).isoformat()}
        if plan.get("restart"):
            result["restart"] = plan["restart"]

        def event(kind, **values):
            item = {"event": kind, "run_id": run_id, "time": datetime.now(timezone.utc).isoformat(), **values}
            with (journal / "events.jsonl").open("a") as handle:
                handle.write(json.dumps(item) + "\n")
            if emit:
                emit(item)

        _json(journal / "result.json", result)
        controls = {}
        process = None
        try:
            if plan.get("restart"):
                event("startup", **plan["restart"])
            # Preserve all small startup controls/restart files used by the run.
            inputs_dir = journal / "inputs"
            inputs_dir.mkdir()
            for record in plan["inputs"]:
                path = Path(record["path"])
                if record.get("sha256") and path.is_relative_to(model):
                    target = inputs_dir / path.relative_to(model)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
            if stage in {"main", "init"} and plan.get("restart", {}).get("present_files"):
                restart_backup = journal / "restart-before"
                restart_backup.mkdir()
                for name in RESTART_FILES:
                    path = model / name
                    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
                        raise RunnerError(f"Refusing unsafe restart file: {path}")
                    if path.is_file():
                        if plan.get("fresh_start"):
                            path.rename(restart_backup / name)
                        else:
                            shutil.copy2(path, restart_backup / name)
            control_name = "CMF_FLUX_PARAM" if stage == "flux" else "IN_ITS"
            if stage == "flux" or any(step["overrides"] for step in plan["passes"]):
                path = cwd / control_name
                if path.is_symlink():
                    raise RunnerError(f"Refusing symlinked control: {path}")
                controls[path] = (path.read_bytes(), path.stat().st_mode, path.stat().st_atime_ns, path.stat().st_mtime_ns) if path.exists() else None
            _json(journal / "links-before.json", {link["name"]: os.readlink(cwd / link["name"]) if (cwd / link["name"]).is_symlink() else None for link in plan["links"]})
            for link in plan["links"]:
                destination = cwd / link["name"]
                if destination.exists() and not destination.is_symlink():
                    raise RunnerError(f"Refusing non-symlink link destination: {destination}")
                if destination.is_symlink():
                    if os.readlink(destination) == link["target"]:
                        continue
                    destination.unlink()
                destination.symlink_to(link["target"])
            env = os.environ.copy()
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
                env[key] = str(plan["threads"])
            timeout = plan.get("timeout")
            deadline = time.monotonic() + timeout if timeout is not None else None
            for step in plan["passes"]:
                pass_dir = journal / step["id"]
                pass_dir.mkdir()
                previous = pass_dir / "before"
                previous.mkdir()
                logs = (("OUTGEN", "WARNINGS") if stage in {"main", "init"} else
                        ("OUTLTE", "ML_COUNTER") if stage == "lte" else
                        ("WIND_HYD",) if stage == "hydro" else ("OUT_FLUX",))
                products = (("MOD_SUM", "RVTJ", "MODEL") if stage in {"main", "init"} else
                            ("ROSSELAND_LTE_TAB",) if stage == "lte" else
                            ("RVSIG_COL_NEW",) if stage == "hydro" else ("OBSFRAME",))
                retired = (*logs, *plan.get("cache_files", []))
                native_names = tuple(dict.fromkeys((*retired, *products, "TIMING", "OUT_PARAMS")))
                for name in native_names:
                    path = cwd / name
                    if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
                        raise RunnerError(f"Refusing unsafe output target: {path}")
                    if path.is_file():
                        if name in retired:
                            path.rename(previous / name)
                        else:
                            shutil.copy2(path, previous / name)
                before = {name: snapshot(cwd / name) for name in products}
                if step["overrides"] or stage == "flux":
                    original = (cwd / "CMF_FLUX_PARAM_INIT").read_text() if stage == "flux" else controls[cwd / "IN_ITS"][0].decode()
                    rendered = override_controls(original, step["overrides"])
                    original_control = controls[cwd / control_name]
                    _write_control(cwd / control_name, rendered.encode(), original_control[1] if original_control else 0o644)
                    (pass_dir / control_name).write_text(rendered)
                record = {"id": step["id"], "status": "running", "log": str(pass_dir / "process.log")}
                result["passes"].append(record)
                _json(journal / "result.json", result)
                event("stage_started", stage=step["id"])
                if deadline is not None and time.monotonic() >= deadline:
                    record["status"] = result["status"] = "timeout"
                    record["problems"] = ["Execution budget exhausted before launch"]
                    event("stage_finished", stage=step["id"], status="timeout", problems=record["problems"])
                    break
                if stage == "flux":
                    input_handle = (cwd / "IN_FILE").open("rb")
                elif stage == "hydro":
                    input_path = pass_dir / "stdin.txt"
                    input_path.write_text(step["stdin"]["text"])
                    input_handle = input_path.open("rb")
                else:
                    input_handle = subprocess.DEVNULL
                try:
                    with (pass_dir / "process.log").open("wb") as output:
                        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("runner_child.py")), plan["executable"], str(plan["memory_mib"])],
                                                   cwd=cwd, env=env, stdin=input_handle, stdout=output, stderr=subprocess.STDOUT,
                                                   start_new_session=True, pass_fds=(lock_fd,))
                        record["pid"] = process.pid
                        _json(journal / "result.json", result)
                        last_report = 0
                        while process.poll() is None:
                            now = time.monotonic()
                            if deadline is not None and now >= deadline:
                                _stop(process)
                                record["status"] = "timeout"
                                break
                            if now - last_report >= 2:
                                progress = _progress(stage, cwd)
                                if deadline is not None:
                                    progress["remaining_seconds"] = round(deadline - now, 1)
                                event("progress", stage=step["id"], **progress)
                                last_report = now
                            time.sleep(0.1)
                        record["returncode"] = process.wait()
                finally:
                    if input_handle != subprocess.DEVNULL:
                        input_handle.close()
                if stage == "hydro":
                    _publish(pass_dir / "process.log", cwd / "WIND_HYD")
                problems = _validate(stage, cwd, before)
                diagnostic = "\n".join(_tail(cwd / name, 64*1024) for name in logs) + "\n" + _tail(pass_dir / "process.log", 64*1024)
                startup_warnings = []
                if plan.get("restart"):
                    record["startup_observed"] = observe_startup(plan["restart"], (cwd / "OUTGEN", pass_dir / "process.log"))
                    result["startup_observed"] = record["startup_observed"]
                    if plan["restart"]["mode"] == "continuation" and record["startup_observed"]["mode"] == "fresh":
                        startup_warnings.append("Expected continuation, but CMFGEN fell back to a fresh *_IN start; inspect native checkpoint diagnostics.")
                        event("startup_fallback", message=startup_warnings[-1], mode="fresh")
                    record["restart_after"] = [snapshot(model / name) for name in RESTART_FILES]
                # Error messages about absent restart pointers/EDDFACTOR can be
                # recoverable. Preserve them as evidence, not blanket failures.
                fatal = [line.strip() for line in diagnostic.splitlines() if re.search(r"Fortran runtime error|SIGSEGV|SIGABRT|segmentation fault|unable to allocate|Error in RD_RV_FILE|different number of depth|differnet number of depth", line, re.I)]
                problems.extend(fatal[-8:])
                if problems:
                    native_errors = [line.strip() for line in diagnostic.splitlines()
                                     if re.search(r"^\s*(?:Error (?:in |with )|Incompatible |Inconsistent |Unable to locate|Routine can't|MIN_FREQ =)", line)]
                    problems.extend(native_errors[-8:])
                if record["status"] != "timeout":
                    record["status"] = "failed" if record["returncode"] != 0 else "invalid_output" if problems else "succeeded"
                record["problems"] = problems
                record["diagnostic_warnings"] = startup_warnings + list(dict.fromkeys(line.strip() for line in diagnostic.splitlines() if re.search(r"warning|floating-point exceptions|possible error", line, re.I)))[-20:]
                record["diagnostic_tail"] = diagnostic[-8000:]
                for name in native_names:
                    path = cwd / name
                    if path.is_file() and not path.is_symlink():
                        shutil.copy2(path, pass_dir / name)
                event("stage_finished", stage=step["id"], status=record["status"], returncode=record["returncode"], problems=problems)
                if record["status"] != "succeeded":
                    result["status"] = record["status"]
                    break
                if stage == "flux":
                    destination = cwd / step["output"]
                    if destination.is_symlink():
                        raise RunnerError(f"Refusing symlinked spectrum target: {destination}")
                    if destination.exists():
                        shutil.copy2(destination, previous / destination.name)
                    _publish(cwd / "OBSFRAME", destination)
                    record["output"] = str(destination)
            else:
                result["status"] = "initialized" if stage == "init" else "succeeded"
        except KeyboardInterrupt:
            result["status"] = "cancelled"
        except Exception as exc:
            result["status"] = "runner_error"
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if process is not None and process.poll() is None:
                _stop(process)
            for path, original in controls.items():
                try:
                    if path.is_symlink():
                        raise RunnerError(f"Control became a symlink during execution: {path}")
                    if original is None:
                        path.unlink(missing_ok=True)
                    else:
                        _write_control(path, original[0], original[1])
                        os.utime(path, ns=(original[2], original[3]))
                except (OSError, RunnerError) as exc:
                    result["status"] = "runner_error"
                    result.setdefault("restore_errors", []).append(str(exc))
            for record in result["passes"]:
                if record["status"] == "running":
                    record["status"] = result["status"]
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            _json(journal / "result.json", result)
            event("run_finished", status=result["status"], journal=str(journal))
        return result


def _run_promotion_plan(plan: dict, emit=None) -> dict:
    """Run the existing guarded web promotion with runner-style evidence."""
    if not plan["ready"]:
        raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
    model = Path(plan["model"])
    for old in plan["inputs"]:
        if snapshot(Path(old["path"])) != old:
            raise RunnerError(f"Input changed since preflight: {old['path']}")
    root = model / ".cmfgen-runs"
    if root.is_symlink():
        raise RunnerError("Refusing symlinked run archive")
    root.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    journal = root / run_id
    journal.mkdir()
    _json(journal / "plan.json", plan)
    started_at = datetime.now(timezone.utc).isoformat()
    record = {"id": "promote", "status": "running", "problems": []}
    result = {
        "run_id": run_id,
        "stage": "promote",
        "status": "running",
        "journal": str(journal),
        "passes": [record],
        "planned_passes": 1,
        "scientific_acceptance": plan.get("scientific_acceptance", "not assessed"),
        "started_at": started_at,
    }

    def event(kind, **values):
        item = {
            "event": kind,
            "run_id": run_id,
            "time": datetime.now(timezone.utc).isoformat(),
            **values,
        }
        with (journal / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(item) + "\n")
        if emit:
            emit(item)

    _json(journal / "result.json", result)
    event("stage_started", stage="promote")
    try:
        from .model_workflow import ModelWorkflowError, promote_lte_hydro_results

        promotion = promote_lte_hydro_results(
            str(model.parent),
            model_relpath=model.name,
        )
        result["promotion"] = {
            "backup_relpath": promotion["backup_relpath"],
            "backup_path": str(model / promotion["backup_relpath"]),
            "invalidated_files": promotion["invalidated_files"],
            "synchronized_rmax": promotion["synchronized_rmax"],
            "promoted_files": ["ROSSELAND_LTE_TAB", "RVSIG_COL_NEW", "RVSIG_COL", "VADAT"],
        }
        record["status"] = result["status"] = "succeeded"
    except (ModelWorkflowError, OSError, UnicodeError) as exc:
        record["status"] = result["status"] = "failed"
        record["problems"] = [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive journal preservation
        record["status"] = result["status"] = "runner_error"
        record["problems"] = [f"{type(exc).__name__}: {exc}"]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    _json(journal / "result.json", result)
    event(
        "stage_finished",
        stage="promote",
        status=record["status"],
        problems=record["problems"],
    )
    event("run_finished", status=result["status"], journal=str(journal))
    return result


def _run_cleanup_plan(plan: dict, emit=None) -> dict:
    """Archive canonical cleanup candidates through the shared model guard."""
    if not plan["ready"]:
        raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
    model = Path(plan["model"])
    root = model / ".cmfgen-runs"
    if root.is_symlink():
        raise RunnerError("Refusing symlinked run archive")
    root.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    journal = root / run_id
    journal.mkdir()
    archive = journal / "removed"
    archive.mkdir()
    _json(journal / "plan.json", plan)
    record = {"id": "cleanup", "status": "running", "problems": []}
    result = {
        "run_id": run_id,
        "stage": "cleanup",
        "status": "running",
        "journal": str(journal),
        "passes": [record],
        "planned_passes": 1,
        "scientific_acceptance": "not applicable",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    def event(kind, **values):
        item = {
            "event": kind,
            "run_id": run_id,
            "time": datetime.now(timezone.utc).isoformat(),
            **values,
        }
        with (journal / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(item) + "\n")
        if emit:
            emit(item)

    _json(journal / "result.json", result)
    event("stage_started", stage="cleanup")
    try:
        from .model_staging import ModelStagingError, cleanup_model_directory

        cleanup = cleanup_model_directory(
            str(model.parent),
            model_relpath=model.name,
            selected_names=plan["selected_names"],
            expected_entries=plan["entries"],
            archive_dir=archive,
        )
        failures = [
            f"{item['name']}: {item['error']}"
            for item in cleanup["failures"]
        ]
        failures.extend(f"Candidate was no longer available: {name}" for name in cleanup["skipped"])
        result["cleanup"] = {
            "archive_path": str(archive),
            "removed_files": [str(item["name"]) for item in cleanup["removed"]],
            "removed_count": cleanup["removed_count"],
            "removed_bytes": sum(int(item["size"]) for item in cleanup["removed"]),
            "skipped": cleanup["skipped"],
            "failures": cleanup["failures"],
        }
        record["problems"] = failures
        record["status"] = result["status"] = "failed" if failures else "succeeded"
    except (ModelStagingError, OSError, UnicodeError) as exc:
        record["status"] = result["status"] = "failed"
        record["problems"] = [str(exc)]
    except Exception as exc:  # pragma: no cover - defensive journal preservation
        record["status"] = result["status"] = "runner_error"
        record["problems"] = [f"{type(exc).__name__}: {exc}"]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    _json(journal / "result.json", result)
    event(
        "stage_finished",
        stage="cleanup",
        status=record["status"],
        problems=record["problems"],
    )
    event("run_finished", status=result["status"], journal=str(journal))
    return result


def _run_sequence_plan(plan: dict, emit=None) -> dict:
    """Run stages in order, rebuilding each preflight after its predecessor."""
    if not plan["ready"]:
        raise RunnerError("Preflight failed: " + "; ".join(plan["errors"]))
    model = Path(plan["model"])
    root = model / ".cmfgen-runs"
    if root.is_symlink():
        raise RunnerError("Refusing symlinked run archive")
    root.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    journal = root / run_id
    journal.mkdir()
    _json(journal / "plan.json", plan)
    stages = list(plan["stages"])
    result = {
        "run_id": run_id,
        "stage": "sequence",
        "stages": stages,
        "status": "running",
        "journal": str(journal),
        "stage_results": [],
        "completed_stages": [],
        "planned_stages": len(stages),
        "scientific_acceptance": plan.get("scientific_acceptance", "not assessed"),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    def event(kind, **values):
        item = {
            "event": kind,
            "run_id": run_id,
            "time": datetime.now(timezone.utc).isoformat(),
            **values,
        }
        with (journal / "events.jsonl").open("a") as handle:
            handle.write(json.dumps(item) + "\n")
        if emit:
            emit(item)

    _json(journal / "result.json", result)
    configured_timeout = plan["stage_options"].get("timeout")
    remaining_timeout = float(configured_timeout) if configured_timeout is not None else None
    try:
        event("sequence_started", stages=stages)
        for index, stage in enumerate(stages, 1):
            event(
                "sequence_stage_preflight",
                stage=stage,
                index=index,
                total=len(stages),
            )
            if stage in NATIVE_STAGES and remaining_timeout is not None and remaining_timeout <= 0:
                stage_result = {
                    "stage": stage,
                    "status": "timeout",
                    "passes": [],
                    "problems": ["Multi-stage execution budget exhausted before preflight"],
                    "preflight_warnings": [],
                }
                result["stage_results"].append(stage_result)
                result["status"] = "timeout"
                result["failed_stage"] = stage
                _json(journal / "result.json", result)
                event(
                    "sequence_stage_blocked",
                    stage=stage,
                    index=index,
                    total=len(stages),
                    status="timeout",
                    problems=stage_result["problems"],
                )
                break
            try:
                stage_plan = _sequence_stage_plan(
                    plan,
                    stage,
                    timeout=remaining_timeout if stage in NATIVE_STAGES else None,
                )
            except (RunnerError, OSError, UnicodeError) as exc:
                stage_result = {
                    "stage": stage,
                    "status": "preflight_failed",
                    "passes": [],
                    "problems": [str(exc)],
                    "preflight_warnings": [],
                }
                result["stage_results"].append(stage_result)
                result["status"] = "preflight_failed"
                result["failed_stage"] = stage
                _json(journal / "result.json", result)
                event(
                    "sequence_stage_blocked",
                    stage=stage,
                    index=index,
                    total=len(stages),
                    status="preflight_failed",
                    problems=stage_result["problems"],
                )
                break
            _json(journal / f"stage-{index:02d}-{stage}-plan.json", stage_plan)
            if not stage_plan["ready"]:
                stage_result = {
                    "stage": stage,
                    "status": "preflight_failed",
                    "passes": [],
                    "problems": list(stage_plan["errors"]),
                    "preflight_warnings": list(stage_plan.get("warnings", [])),
                }
                result["stage_results"].append(stage_result)
                result["status"] = "preflight_failed"
                result["failed_stage"] = stage
                _json(journal / "result.json", result)
                event(
                    "sequence_stage_blocked",
                    stage=stage,
                    index=index,
                    total=len(stages),
                    status="preflight_failed",
                    problems=stage_result["problems"],
                )
                break
            event(
                "sequence_stage_ready",
                stage=stage,
                index=index,
                total=len(stages),
            )
            result["current_stage"] = stage
            _json(journal / "result.json", result)
            execution_started = time.monotonic()
            stage_result = run_plan(stage_plan, emit)
            if stage in NATIVE_STAGES and remaining_timeout is not None:
                remaining_timeout = max(
                    0.0,
                    remaining_timeout - (time.monotonic() - execution_started),
                )
            stage_result["preflight_warnings"] = list(stage_plan.get("warnings", []))
            result["stage_results"].append(stage_result)
            result.pop("current_stage", None)
            if not _stage_succeeded(stage, stage_result["status"]):
                result["status"] = stage_result["status"]
                result["failed_stage"] = stage
                _json(journal / "result.json", result)
                event(
                    "sequence_stage_blocked",
                    stage=stage,
                    index=index,
                    total=len(stages),
                    status=stage_result["status"],
                    problems=[
                        problem
                        for item in stage_result.get("passes", [])
                        for problem in item.get("problems", [])
                    ],
                )
                break
            result["completed_stages"].append(stage)
            _json(journal / "result.json", result)
            event(
                "sequence_stage_completed",
                stage=stage,
                index=index,
                total=len(stages),
                status=stage_result["status"],
                journal=stage_result.get("journal"),
            )
        else:
            result["status"] = "succeeded"
    except KeyboardInterrupt:
        result["status"] = "cancelled"
        if len(result["completed_stages"]) < len(stages):
            result["failed_stage"] = stages[len(result["completed_stages"])]
    except Exception as exc:  # pragma: no cover - defensive journal preservation
        result["status"] = "runner_error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        if len(result["completed_stages"]) < len(stages):
            result["failed_stage"] = stages[len(result["completed_stages"])]
    result.pop("current_stage", None)
    result["remaining_stages"] = stages[len(result["stage_results"]):]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    _json(journal / "result.json", result)
    event(
        "sequence_finished",
        status=result["status"],
        completed_stages=result["completed_stages"],
        remaining_stages=result["remaining_stages"],
        journal=str(journal),
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "CMFGEN runner (default action: run; reviewed ostar recipes; "
            "no Flask or shell execution)"
        ),
    )
    parser.add_argument("model", type=Path)
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Perform read-only preflight without executing (default: execute)",
    )
    parser.add_argument(
        "--stage",
        choices=STAGE_CHOICES,
        action="append",
        help="Stage to run; repeat for an ordered multi-stage run (default: init)",
    )
    parser.add_argument("--cmfgen-root", type=Path, help="Installation root (default: CMFDIST or .cmfgenrc)")
    parser.add_argument("--atomic-root", type=Path, help="Atomic data root (default: ATOMIC or .cmfgenrc)")
    parser.add_argument("--threads", "--nthreads", type=int, help="Thread count (default: OMP_NUM_THREADS, .cmfgenrc nthreads, or 1)")
    parser.add_argument(
        "--timeout",
        type=float,
        help="Shared execution time limit in seconds (default: no timeout)",
    )
    parser.add_argument(
        "--memory-mib",
        type=int,
        help="Per-child virtual-memory limit in MiB (default: 4096)",
    )
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--fresh-start", action="store_true", help="Archive POINT1/POINT2/SCRTEMP and force *_IN startup (default: continue when checkpoints are usable)")
    parser.add_argument(
        "--cleanup-file",
        action="append",
        help="Restrict cleanup to this current candidate (repeatable; default: all)",
    )
    parser.add_argument("--json", action="store_true", help="Emit the full JSON plan/result on stdout (default: readable terminal summary)")
    parser.add_argument("--verbose", action="store_true", help="Show all reported warnings and captured diagnostic tails")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="Status-label colors (default: auto; respects NO_COLOR)")
    parser.add_argument("--progress", choices=("text", "json", "none"), help="Live stderr output (default: text, or none with --json)")
    args = parser.parse_args(argv)
    stages = args.stage or ["init"]
    progress = args.progress or ("none" if args.json else "text")
    terminal = TerminalOutput(sys.stdout, color=args.color, verbose=args.verbose)
    live = TerminalOutput(sys.stderr, color=args.color, verbose=args.verbose)
    def emit(item):
        if progress == "json":
            print(json.dumps(item), file=sys.stderr, flush=True)
        elif progress == "text":
            live.event(item)
    old_handler = signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        if len(set(stages)) != len(stages):
            raise RunnerError("A multi-stage run cannot contain duplicate stages")
        native_stages = [stage for stage in stages if stage in NATIVE_STAGES]
        if not native_stages:
            inapplicable = [
                option
                for option, supplied in (
                    ("--cmfgen-root", args.cmfgen_root is not None),
                    ("--atomic-root", args.atomic_root is not None),
                    ("--threads", args.threads is not None),
                    ("--timeout", args.timeout is not None),
                    ("--memory-mib", args.memory_mib is not None),
                    ("--iterations", args.iterations is not None),
                    ("--fresh-start", args.fresh_start),
                )
                if supplied
            ]
            if inapplicable:
                stage_label = (
                    "promotion"
                    if stages == ["promote"]
                    else "cleanup"
                    if stages == ["cleanup"]
                    else "filesystem stages"
                )
                raise RunnerError(
                    f"{', '.join(inapplicable)} do not apply to {stage_label}"
                )
            config: dict[str, object] = {}
            sources = {}
        else:
            config, sources = resolve_runner_config(cmfgen_root=args.cmfgen_root, atomic_root=args.atomic_root, threads=args.threads)
        if native_stages and args.timeout is not None and (
            not math.isfinite(args.timeout) or args.timeout <= 0
        ):
            raise RunnerError("--timeout must be a positive finite number of seconds")
        if native_stages and args.memory_mib is not None and args.memory_mib < 128:
            raise RunnerError("Require at least 128 MiB memory")
        if args.iterations is not None and args.iterations < 1:
            raise RunnerError("--iterations is a positive main-stage override only")
        if args.iterations is not None and "main" not in stages:
            raise RunnerError("--iterations is a positive main-stage override only")
        if args.fresh_start and not any(stage in {"init", "main"} for stage in stages):
            raise RunnerError("--fresh-start applies only to main/init")
        if args.cleanup_file and "cleanup" not in stages:
            raise RunnerError("--cleanup-file applies only to the cleanup stage")
        memory_mib = args.memory_mib if args.memory_mib is not None else 4096
        if len(stages) == 1:
            plan = _build_requested_stage_plan(
                args.model,
                stages[0],
                native_config=config,
                configuration_sources=sources,
                timeout=args.timeout,
                memory_mib=memory_mib,
                iterations=args.iterations,
                fresh_start=args.fresh_start,
                cleanup_files=args.cleanup_file,
            )
        else:
            plan = build_sequence_plan(
                args.model,
                stages,
                native_config=config,
                configuration_sources=sources,
                timeout=args.timeout,
                memory_mib=memory_mib,
                iterations=args.iterations,
                fresh_start=args.fresh_start,
                cleanup_files=args.cleanup_file,
            )
        if args.plan:
            if args.json:
                print(json.dumps(plan, indent=2))
            else:
                terminal.plan(plan)
            return 0 if plan["ready"] else 2
        if not args.json:
            (terminal if progress == "json" else live).plan(plan)
            if not plan["ready"]:
                return 2
        result = run_plan(plan, emit)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            terminal.result(result, preflight_warnings=plan.get("warnings", []))
        return 0 if result["status"] in {"initialized", "succeeded"} else 2 if result["status"] == "preflight_failed" else 124 if result["status"] == "timeout" else 130 if result["status"] == "cancelled" else 1
    except (RunnerError, OSError, UnicodeError) as exc:
        if args.json:
            print(json.dumps({"status": "preflight_failed", "error": str(exc)}))
        else:
            live.line("ERROR", f"Preflight failed: {exc}")
        return 2
    finally:
        signal.signal(signal.SIGTERM, old_handler)


if __name__ == "__main__":
    sys.exit(main())
