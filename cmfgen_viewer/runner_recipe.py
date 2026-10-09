"""Explicit first-generation ostar recipes; legacy scripts are never executed.

Only reviewed shell entry points are recognized. Atomic include files may vary,
but must consist solely of literal atomic link declarations.
"""

import hashlib
import math
import os
from pathlib import Path
import shlex
import shutil

from .control_files import control_occurrences
from .model_activity import inspect_model_activity
from .model_preflight import inspect_model_preflight
from .parsers.common import parse_float_token
from .runner_validation import validate_rosseland_table, validate_rvtj_core
from .runner_restart import RESTART_FILES, inspect_restart


class RunnerError(ValueError):
    pass


REVIEWED_SCRIPTS = {
    "batch.sh": {"df872ab82a353d16e8a42489b6ad8b0eb0ad3ea2c4a78e911bb4f7fbb77e3585",
                 "28c5fa0de471edbaaae5ab61527bd74193f40e7e124c56203d403131e338f5d9"},
    "obs/batobs.sh": {"82ba5a0d6000438e3a9d2574237a71bd5c79f0eab01735c7de9bb87c0acc55de"},
    "obs/bat_ins.sh": {"95c167e47d7e3419b045832f0743237e4aae8bdf8121f3bfefc4dfa60fafb40f"},
    "lte/ltebat.sh": {"0591cd72fd414cc1835547e20c283f07287c41ed7a75bdef9e545cd63a4c9fad"},
}
PROGRAMS = {"main": "cmfgen_dev.exe", "test": "cmfgen_dev.exe", "lte": "main_lte.exe",
            "hydro": "wind_hyd.exe", "flux": "cmf_flux.exe"}
# Observer passes use different grids/profiles. The legacy script discards
# these scratch caches between passes; archive them instead, including before
# the first pass so reruns cannot consume caches from an earlier invocation.
FLUX_CACHE_FILES = ("EDDFACTOR", "EDDFACTOR_INFO", "ES_J_CONV", "ES_J_CONV_INFO",
                    "J_COMP", "MEANOPAC", "TRANS_INFO")


def snapshot(path: Path) -> dict:
    result = {"path": str(path), "exists": path.is_file()}
    if result["exists"]:
        info = path.stat()
        result.update(size=info.st_size, mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)
        result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() if info.st_size <= 2 * 1024**2 else None
    return result


def override_controls(text: str, values: dict) -> str:
    rows = control_occurrences(text)
    lines = text.splitlines(keepends=True)
    for key, value in values.items():
        if len(rows.get(key, [])) != 1:
            raise RunnerError(f"Expected exactly one [{key}] for control override")
        row = rows[key][0]
        index = row["line_index"]
        lines[index] = lines[index][:row["value_start"]] + str(value) + lines[index][row["value_end"]:]
    return "".join(lines)


def _links(script: Path, atomic: Path, *, links_only=False) -> list[dict]:
    result = []
    for number, line in enumerate(script.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Entry points are hash-reviewed elsewhere, not parsed as arbitrary
        # shell programs here. Non-link commands can span physical lines
        # (notably sed edits); shlex on their first line rejects the trailing
        # backslash. Only tokenize literal ln statements in reviewed scripts.
        # The separate links-only manifest remains strict about every command.
        if not links_only and line.split(None, 1)[0] != "ln":
            continue
        try:
            words = shlex.split(line, comments=True)
        except ValueError as exc:
            raise RunnerError(f"Cannot parse {script}:{number}") from exc
        if not words or words[0] != "ln":
            if links_only:
                raise RunnerError(f"Unsupported command in atomic manifest {script}:{number}")
            continue
        if len(words) != 4 or words[1] != "-sf":
            raise RunnerError(f"Unsupported link declaration {script}:{number}")
        target, name = words[2:]
        if target == "He2_IN" and name == "T_IN":
            continue  # Restart link is main-only, not part of atomic setup.
        prefix = next((p for p in ("$ATOMIC/", "$atomic/") if target.startswith(p)), None)
        if not prefix or Path(name).name != name or name in {".", ".."}:
            raise RunnerError(f"Nonliteral atomic link {script}:{number}")
        relative = target[len(prefix):]
        if any(c in relative for c in "$`*?;|&<>") or ".." in Path(relative).parts:
            raise RunnerError(f"Unsafe atomic path {script}:{number}")
        resolved = (atomic / relative).resolve()
        if not resolved.is_relative_to(atomic):
            raise RunnerError(f"Atomic link escapes configured root: {target}")
        result.append({"name": name, "target": str(resolved), "source": str(script), "line": number})
    return result


def build_run_plan(model: Path, *, stage: str, cmfgen_root: Path, atomic_root: Path,
                   threads=None, timeout=None, memory_mib=None, iterations=None, fresh_start=False,
                   no_core_dumps=False) -> dict:
    if stage not in PROGRAMS:
        raise RunnerError("Supported stages: test, main, lte, hydro, flux")
    if (threads is not None and threads < 1) or (memory_mib is not None and memory_mib < 128):
        raise RunnerError("Require positive threads and at least 128 MiB memory")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise RunnerError("--timeout must be a positive finite number of seconds")
    if iterations is not None and (iterations < 1 or stage != "main"):
        raise RunnerError("--iterations is a positive main-stage override only")
    if fresh_start and stage not in {"main", "test"}:
        raise RunnerError("--fresh-start applies only to main/test")
    model, cmfgen_root, atomic_root = (p.expanduser().resolve() for p in (model, cmfgen_root, atomic_root))
    if not model.is_dir() or not (model / "VADAT").is_file() or not (model / "MODEL_SPEC").is_file():
        raise RunnerError("Not a model workspace")
    cwd = model / "lte" if stage in {"lte", "hydro"} else model / "obs" if stage == "flux" else model
    errors, warnings = [], []
    restart = inspect_restart(model, fresh_start=fresh_start) if stage in {"main", "test"} else None
    continuing = restart is not None and restart["mode"] == "continuation"
    if restart:
        errors.extend(restart["errors"])
        warnings.extend(restart["warnings"])
        backup_bytes = sum((model / name).stat().st_size for name in restart["present_files"] if (model / name).is_file())
        if not fresh_start and shutil.disk_usage(model).free < backup_bytes + 1024**3:
            errors.append("Insufficient free space for checkpoint backup plus 1 GiB working headroom")
    activity = inspect_model_activity(model)
    if not activity["safe_to_modify"]:
        errors.append(activity["reason"])
    exe = cmfgen_root / "exe" / PROGRAMS[stage]
    if not exe.is_file() or not os.access(exe, os.X_OK):
        errors.append(f"Executable is missing or non-executable: {exe}")
    if not cwd.is_dir() or not os.access(cwd, os.W_OK | os.X_OK):
        errors.append(f"Workspace is not writable: {cwd}")
    if shutil.disk_usage(model).free < 1024**3:
        errors.append("Runner requires at least 1 GiB free; actual scratch requirements may be larger")
    scripts = [] if stage == "hydro" else ["batch.sh"] + (
        ["obs/batobs.sh", "obs/bat_ins.sh"] if stage == "flux" else ["lte/ltebat.sh"] if stage == "lte" else []
    )
    for name in scripts:
        path = model / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() not in REVIEWED_SCRIPTS[name]:
            errors.append(f"Unreviewed script recipe: {name}; no automatic shell fallback")
    hydro_controls = control_occurrences((cwd / "HYDRO_PARAMS").read_text()) if stage == "hydro" and (cwd / "HYDRO_PARAMS").is_file() else {}
    old_model = False
    if stage == "hydro":
        rows = hydro_controls.get("OLD_MOD", [])
        if len(rows) != 1 or rows[0]["value"].upper() not in {"T", "F"}:
            errors.append("Hydro requires exactly one boolean [OLD_MOD] in HYDRO_PARAMS")
        else:
            old_model = rows[0]["value"].upper() == "T"
    required = (["VADAT", "MODEL_SPEC", "IN_ITS"] + ([] if continuing else ["GAMMAS_IN", "He2_IN"])) if stage in {"main", "test"} else (
        ["VADAT", "MODEL_SPEC", "GRID_PARAMS"] if stage == "lte" else
        ["HYDRO_PARAMS", "ROSSELAND_LTE_TAB", "MODEL_SPEC"] + (["RVTJ"] if old_model else []) if stage == "hydro" else
        ["CMF_FLUX_PARAM_INIT", "IN_FILE", "../RVTJ", "../MODEL", "../MODEL_SPEC"])
    for name in required:
        path = cwd / name
        if not path.is_file() or not path.stat().st_size:
            errors.append(f"Required nonempty input missing: {path}")
    if stage == "flux" and (model / "RVTJ").is_file():
        try:
            validate_rvtj_core(model / "RVTJ", model / "MODEL_SPEC")
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"Invalid flux input RVTJ: {exc}. Regenerate a finite atmosphere before spectral synthesis.")
    if stage in {"main", "test"}:
        for issue in inspect_model_preflight(model)["issues"]:
            if issue["code"] == "script-not-executable":
                continue  # The runner reads scripts as recipes, never runs them.
            if continuing and (issue["file"] == "RVSIG_COL" or issue["code"] in {"missing-gamma-input", "empty-gamma-input", "unpromoted-lte-result"}):
                warnings.append("Fresh-start input check (not used by continuation): " + issue["message"])
                continue
            (errors if issue["severity"] == "error" else warnings).append(issue["message"])
    links = []
    if stage != "hydro" and not any("Unreviewed" in error for error in errors):
        try:
            links = _links(model / "batch.sh", atomic_root) + _links(model / "batch_ins.sh", atomic_root, links_only=True)
            if stage == "flux":
                links += _links(model / "obs/batobs.sh", atomic_root)
        except (OSError, RunnerError) as exc:
            errors.append(str(exc))
    spec_path = cwd / "MODEL_SPEC" if stage == "lte" else model / "MODEL_SPEC"
    controls = control_occurrences(spec_path.read_text()) if spec_path.is_file() else {}
    if stage == "lte":
        try:
            nd, nc, np_ = (int(controls[key][0]["value"]) for key in ("ND", "NC", "NP"))
            if nd < 1 or nc < 0 or np_ != nd+nc or any(len(controls[k]) != 1 for k in ("ND", "NC", "NP")):
                raise ValueError()
        except (KeyError, IndexError, ValueError):
            errors.append("LTE requires unique integer ND/NC/NP with ND > 0 and NP = ND + NC")
        values = control_occurrences((cwd / "VADAT").read_text()) if (cwd / "VADAT").is_file() else {}
        for key in ("TEFF", "LOGG", "CHK_NG"):
            rows = values.get(key, [])
            valid = len(rows) == 1
            if valid and key == "CHK_NG":
                valid = rows[0]["value"].upper() in {"T", "F"}
            elif valid:
                number = parse_float_token(rows[0]["value"])
                valid = number is not None and math.isfinite(number) and (key != "TEFF" or number > 0)
            if not valid:
                errors.append(f"Missing, duplicate, or invalid LTE [{key}]")
    elif stage == "hydro":
        try:
            nd_rows = controls["ND"]
            hydro_nd = int(nd_rows[0]["value"])
            if len(nd_rows) != 1 or hydro_nd < 1:
                raise ValueError()
        except (KeyError, IndexError, ValueError):
            hydro_nd = None
            errors.append("Hydro requires exactly one positive integer [ND] in lte/MODEL_SPEC")
        table = cwd / "ROSSELAND_LTE_TAB"
        if table.is_file():
            try:
                validate_rosseland_table(table)
            except (OSError, ValueError, UnicodeError) as exc:
                errors.append(f"Invalid hydro input ROSSELAND_LTE_TAB: {exc}. Rerun the LTE stage.")
            dependencies = [cwd / name for name in ("VADAT", "MODEL_SPEC", "GRID_PARAMS") if (cwd / name).is_file()]
            if dependencies and table.stat().st_mtime_ns < max(path.stat().st_mtime_ns for path in dependencies):
                errors.append("ROSSELAND_LTE_TAB predates an LTE input; rerun the LTE stage before hydro.")
    active = set()
    for key, rows in controls.items():
        if not key.endswith(("_ISF", "_NSF")):
            continue
        try:
            values = [int(value.strip()) for value in rows[0]["value"].split(",")]
            expected = 3 if key.endswith("_ISF") else 2
            if len(rows) != 1 or len(values) != expected or min(values) < 0:
                raise ValueError()
            # ISF = important variables, superlevels, full levels. NV=0 does
            # NOT disable an ion: NS controls whether it is present.
            ns = values[1] if expected == 3 else values[0]
            if ns > 0:
                active.add(key[:-4].upper())
        except ValueError:
            errors.append(f"Invalid or duplicate ion dimensions [{key}]")
    kept, seen = [], set()
    for link in links:
        if link["name"] in seen:
            errors.append(f"Duplicate atomic destination: {link['name']}")
        seen.add(link["name"])
        target = Path(link["target"])
        if not target.is_file() or not os.access(target, os.R_OK):
            ion = link["name"].split("_", 1)[0].upper()
            if link["name"].endswith("_F_TO_S") and ion not in active:
                warnings.append(f"Skipping unavailable inactive-ion link: {link['name']}")
                continue
            errors.append(f"Atomic target is not a readable file: {link['name']} -> {target}")
        destination = cwd / link["name"]
        if destination.exists() and not destination.is_symlink():
            errors.append(f"Refusing to replace non-symlink atomic destination: {destination}")
        kept.append(link)
    if stage in {"main", "test"} and not continuing:
        kept.append({"name": "T_IN", "target": str(model / "He2_IN"), "source": "recipe"})
    permitted_links = seen | {"T_IN"} | {Path(name).name for name in required}
    if stage == "hydro" and cwd.is_dir():
        # The preceding LTE stage leaves its atomic links in this shared
        # workspace. wind_hyd does not use them, but they are known read-only
        # residue when they still resolve inside the configured atomic root.
        for path in cwd.iterdir():
            if not path.is_symlink() or path.name in {"WIND_HYD", "RVSIG_COL_NEW"}:
                continue
            try:
                target = path.resolve(strict=True)
                inherited = target.is_file() and target.is_relative_to(atomic_root)
            except OSError:
                inherited = False
            if inherited:
                permitted_links.add(path.name)
    if cwd.is_dir():
        for path in cwd.iterdir():
            if path.is_symlink() and path.name not in permitted_links:
                errors.append(f"Unclassified symlink in execution workspace: {path}; inspect before running")
    passes = []
    if stage == "flux":
        for velocity in (15, 10, 20):
            passes.append({"id": f"flux-{velocity}", "overrides": {"VTURB_FIX": f"{velocity}.0D0", "VTURB_MIN": f"{velocity}.0D0", "VTURB_MAX": "250.0D0"}, "output": f"obs_fin_{velocity}"})
        continuum = {"NUM_ES": "1", "DO_SOB_LINES": "F", "GLOBAL_LINE": "SOB"}
        template_path = cwd / "CMF_FLUX_PARAM_INIT"
        template_controls = control_occurrences(template_path.read_text()) if template_path.is_file() else {}
        # The reviewed sed recipe only replaces existing rows. These EW
        # bounds are optional in rd_cmf_flux_controls.f (with these defaults),
        # and this pass disables Sobolev EWs. Do not require or insert them
        # in older templates. Present duplicates still fail override checks.
        for key, value in (("SOB_EW_LAM_BEG", "900.0D0"), ("SOB_EW_LAM_END", "5.0E+04")):
            if key in template_controls:
                continuum[key] = value
            else:
                warnings.append(f"Optional [{key}] absent; leaving native default (continuum disables Sobolev EWs)")
        passes.append({"id": "continuum", "overrides": continuum, "output": "obs_cont"})
    elif stage == "hydro":
        prefix = "RVTJ\n" if old_model else ""
        stdin = prefix + "/null\ne\n" + (f"{hydro_nd}\n" if hydro_nd is not None else "\n") + "\n"
        passes = [{"id": "hydro", "overrides": {}, "stdin": {
            "mode": "generated", "plot_device": "/null", "plot_command": "e",
            "structure_file": "RVTJ" if old_model else None,
            "output_depth_points": hydro_nd, "maximum_optical_depth": "native default", "text": stdin,
        }}]
    else:
        passes = [{"id": stage, "overrides": {"NUM_ITS": "0" if stage == "test" else str(iterations)} if stage == "test" or iterations is not None else {}}]
    for step in passes:
        filename = "CMF_FLUX_PARAM_INIT" if stage == "flux" else "IN_ITS"
        if step["overrides"] and (cwd / filename).is_file():
            try:
                override_controls((cwd / filename).read_text(), step["overrides"])
            except RunnerError as exc:
                errors.append(str(exc))
    for filename in ("IN_ITS", "CMF_FLUX_PARAM"):
        path = cwd / filename
        if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
            errors.append(f"Refusing symlinked writable control: {cwd / filename}")
    paths = {cwd / name for name in required} | {model / name for name in scripts}
    if stage != "hydro":
        paths.add(model / "batch_ins.sh")
    paths.update(cwd.glob("*_IN"))
    if stage in {"main", "test"}:
        # Snapshot absent files too: a newly appeared checkpoint changes the
        # startup mode and must invalidate a previously prepared plan.
        paths.update(model / name for name in RESTART_FILES)
        if continuing:
            paths.add(model / "MODEL")
            if (model / "RVTJ").is_file():
                # RVTJ is the numerical-health proxy used during restart
                # preflight, so execution must see the same file we checked.
                paths.add(model / "RVTJ")
    paths.update(path for path in (model / "RVSIG_COL", model / "HYDRO_DEFAULTS", model / "RDINR") if path.is_file())
    if stage == "flux":
        paths.update(model.glob("POP*"))
        paths.update(cwd / name for name in FLUX_CACHE_FILES if (cwd / name).exists())
    return {"schema_version": 1, "profile": "ostar-v1", "stage": stage, "model": str(model), "cwd": str(cwd),
            "executable": str(exe), "executable_snapshot": snapshot(exe), "links": kept, "passes": passes,
            "inputs": [snapshot(path) for path in sorted(paths)], "threads": threads, "timeout": timeout,
            "memory_mib": memory_mib, "no_core_dumps": no_core_dumps, "errors": errors, "warnings": warnings,
            "fresh_start": fresh_start,
            "restart": restart,
            "permitted_links": sorted(permitted_links),
            "cache_files": list(FLUX_CACHE_FILES) if stage == "flux" else [],
            "ready": not errors, "cleanup": "no deletion; archive flux caches before each pass; retain diagnostics and atomic links",
            "scientific_acceptance": "not assessed", "launches_legacy_scripts": False}
