"""Explicit first-generation ostar recipes; legacy scripts are never executed.

Atomic declarations are read as data; shell launchers are never executed.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import sys

from .model_initialization import lte_initialization_controls
from .control_files import control_occurrences
from .model_activity import inspect_model_activity
from .model_preflight import inspect_model_preflight
from .parsers.common import parse_float_token
from .hydro_lte_alignment import preview_lte_hydro_alignment
from .runner_validation import validate_rosseland_table, validate_rvtj_core
from .runner_restart import RESTART_FILES, inspect_restart
from .model_templates import resolve_model_template


class RunnerError(ValueError):
    pass


PROGRAMS = {"main": "cmfgen_dev.exe", "test": "cmfgen_dev.exe", "lte": "main_lte.exe",
            "hydro": "wind_hyd.exe", "flux": "cmf_flux.exe"}
# Observer passes use different grids/profiles. The legacy script discards
# these scratch caches between passes; retire them, including before
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


def _links(script: Path, atomic: Path) -> list[dict]:
    result = []
    for number, line in enumerate(script.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Read only literal link declarations. All other shell text is ignored,
        # including commands continued across physical lines.
        if line.split(None, 1)[0] != "ln":
            continue
        try:
            words = shlex.split(line, comments=True)
        except ValueError as exc:
            raise RunnerError(f"Cannot parse {script}:{number}") from exc
        if not words or words[0] != "ln":
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


def resolve_atomic_links(model: Path, stage: str, atomic: Path):
    """Read atomic setup data independently of shell entry-point behavior."""
    record = resolve_model_template(model, "atomic_links.json")
    manifest = Path(record["path"])
    groups = [("base", "batch.sh"), ("ions", "batch_ins.sh")]
    if stage == "flux":
        groups.append(("obs", "obs/batobs.sh"))
    explicit = record["origin"] != "packaged templates"
    links, sources, notes = [], [], []
    defaults = None
    for group, filename in groups:
        script = model / filename
        if not explicit and script.is_file():
            try:
                # Inspect atomic declarations only; never require a launcher hash,
                # interpreter, executable bit, sourced environment, or shell command.
                rows = _links(script, atomic)
                links.extend(rows)
                sources.append(script)
                continue
            except (OSError, UnicodeError, RunnerError) as exc:
                notes.append(f"Ignoring unusable atomic declarations in {filename}: {exc}")
        if defaults is None:
            defaults = json.loads(manifest.read_text())
            if not isinstance(defaults, dict) or set(defaults) - {"base", "ions", "obs"}:
                raise RunnerError(f"Invalid atomic link manifest: {manifest}")
        mapping = defaults.get(group, {})
        if not isinstance(mapping, dict):
            raise RunnerError(f"Invalid atomic link group {group}: {manifest}")
        for name, relative in mapping.items():
            unsafe = (not name or Path(name).name != name or name in {".", ".."}
                      or not isinstance(relative, str) or not relative
                      or Path(relative).is_absolute() or ".." in Path(relative).parts)
            if unsafe:
                raise RunnerError(f"Unsafe atomic declaration {name}: {manifest}")
            target = (atomic / relative).resolve()
            if not target.is_relative_to(atomic):
                raise RunnerError(f"Atomic link escapes configured root: {name}")
            links.append({"name": name, "target": str(target), "source": str(manifest)})
        sources.append(manifest)
        notes.append(f"Atomic {group} declarations from {record['origin']}: {manifest}")
    return links, list(dict.fromkeys(sources)), notes


def build_run_plan(model: Path, *, stage: str, cmfgen_root: Path, atomic_root: Path,
                   threads=None, timeout=None, memory_mib=None, iterations=None, fresh_start=False,
                   no_core_dumps=False, lte_initialization=False, t_exc=1.0) -> dict:
    if stage not in PROGRAMS:
        raise RunnerError("Supported stages: test, main, lte, hydro, flux")
    if (threads is not None and threads < 1) or (memory_mib is not None and memory_mib < 128):
        raise RunnerError("Require positive threads and at least 128 MiB memory")
    if memory_mib is not None and sys.platform == "darwin":
        raise RunnerError("--memory-mib is unsupported on macOS: RLIMIT_AS cannot enforce "
                          "the requested address-space cap. Omit --memory-mib to inherit host limits.")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise RunnerError("--timeout must be a positive finite number of seconds")
    if iterations is not None and (iterations < 1 or stage != "main"):
        raise RunnerError("--iterations is a positive main-stage override only")
    if fresh_start and stage not in {"main", "test"}:
        raise RunnerError("--fresh-start applies only to main/test")
    if lte_initialization and stage not in {"main", "test"}:
        raise RunnerError("--lte-initialization applies only to main/test")
    if lte_initialization and (not math.isfinite(t_exc) or t_exc <= 0):
        raise RunnerError("T_EXC must be positive and finite (units of 10^4 K)")
    model, cmfgen_root, atomic_root = (p.expanduser().resolve() for p in (model, cmfgen_root, atomic_root))
    if not model.is_dir() or not (model / "VADAT").is_file() or not (model / "MODEL_SPEC").is_file():
        raise RunnerError("Not a model workspace")
    cwd = model / "lte" if stage in {"lte", "hydro"} else model / "obs" if stage == "flux" else model
    errors, warnings = [], []
    restart = inspect_restart(model, fresh_start=fresh_start) if stage in {"main", "test"} else None
    continuing = restart is not None and restart["mode"] == "continuation"
    initialization = None
    if lte_initialization:
        if continuing:
            errors.append("LTE initialization applies to fresh startup; explicitly select --fresh-start to retire checkpoints")
        try:
            lte_initialization_controls((model / "VADAT").read_text(), t_exc)
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
        vadat = model / "VADAT"
        if vadat.is_symlink() or vadat.stat().st_nlink != 1:
            errors.append("Refusing unsafe writable VADAT for LTE initialization")
        initialization = {"method": "LTE", "t_exc": t_exc, "temporary": True}
        warnings.append("Fresh LTE initial populations: DC_METH=LTE, T_EXC=" + str(t_exc) + " (10^4 K). VADAT will be restored afterward; convergence remains unassessed.")
    if restart:
        errors.extend(restart["errors"])
        warnings.extend(restart["warnings"])
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
        adjustment = model / "ADJUST_CORRECTIONS"
        if adjustment.is_symlink() or (adjustment.exists() and
                (not adjustment.is_file() or adjustment.stat().st_nlink != 1)):
            errors.append("ADJUST_CORRECTIONS must be an unshared regular file")
        for issue in inspect_model_preflight(model)["issues"]:
            if continuing and (issue["file"] == "RVSIG_COL" or issue["code"] in {"missing-gamma-input", "empty-gamma-input", "unpromoted-lte-result"}):
                warnings.append("Fresh-start input check (not used by continuation): " + issue["message"])
                continue
            (errors if issue["severity"] == "error" else warnings).append(issue["message"])
    links, recipe_files = [], []
    if stage != "hydro":
        try:
            links, recipe_files, notes = resolve_atomic_links(model, stage, atomic_root)
            warnings.extend(notes)
        except (OSError, ValueError) as exc:
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
    paths = {cwd / name for name in required} | set(recipe_files)
    if stage in {"main", "test"}:
        paths.add(model / "ADJUST_CORRECTIONS")
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
    lte_alignment = preview_lte_hydro_alignment(model) if stage == "hydro" and not old_model else None
    if lte_alignment:
        if not lte_alignment["ready"]:
            errors.extend(lte_alignment["issues"])
        else:
            paths.update(Path(name) for name in lte_alignment["file_digests"])
            if lte_alignment["changed"]:
                warnings.append(f"Before hydro, align MU_ATOM with LTE: {lte_alignment['current']} -> {lte_alignment['proposed']}")
    return {"lte_composition_alignment": lte_alignment, "schema_version": 1, "profile": "ostar-v1", "stage": stage, "model": str(model), "cwd": str(cwd),
            "executable": str(exe), "executable_snapshot": snapshot(exe), "links": kept, "passes": passes,
            "inputs": [snapshot(path) for path in sorted(paths)], "threads": threads, "timeout": timeout,
            "memory_mib": memory_mib, "no_core_dumps": no_core_dumps, "errors": errors, "warnings": warnings,
            "fresh_start": fresh_start, "initialization": initialization,
            "restart": restart,
            "permitted_links": sorted(permitted_links),
            "cache_files": list(FLUX_CACHE_FILES) if stage == "flux" else [],
            "ready": not errors, "cleanup": "retire flux caches before each pass; retain diagnostics and atomic links; recovery retains fresh inputs, history, and diagnostic excerpts",
            "scientific_acceptance": "not assessed", "launches_legacy_scripts": False}
