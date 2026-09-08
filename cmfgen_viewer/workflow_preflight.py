"""Stage-specific, read-only checks for externally executed workflows.

Only literal shell link/source declarations are inspected. Never source a
script or evaluate shell expressions to discover configuration.
"""

import math
import os
from pathlib import Path
import re
import shlex
import shutil

from .control_files import control_occurrences
from .model_activity import inspect_model_activity
from .parsers.common import parse_float_token

STAGE_INPUTS = {
    "main": ("batch.sh", "VADAT", "MODEL_SPEC", "IN_ITS"),
    "lte": ("ltebat.sh", "VADAT", "MODEL_SPEC", "GRID_PARAMS"),
    "hydro": ("HYDRO_PARAMS", "ROSSELAND_LTE_TAB"),
    "flux": ("batobs.sh", "CMF_FLUX_PARAM_INIT", "IN_FILE", "../MODEL", "../RVTJ"),
}
STAGE_PROGRAMS = {"main": "cmfgen_dev.exe", "lte": "main_lte.exe", "hydro": "wind_hyd.exe", "flux": "cmf_flux.exe"}
REQUIRED_ATOMIC_LINKS = {"HYD_L_DATA", "GBF_N_DATA", "HI_F_OSCDAT", "He2_F_OSCDAT"}


def workflow_environment(config: dict | None = None) -> dict:
    config = config or {}
    return {
        "cmfdist": str(
            config.get("cmfgen_root")
            or os.environ.get("CMFDIST")
            or os.environ.get("cmfdist", "")
        ),
        "ATOMIC": str(
            config.get("atomic_root")
            or os.environ.get("ATOMIC")
            or os.environ.get("atomic", "")
        ),
    }


def _literal_path(text: str, cwd: Path, environment: dict, script: Path) -> Path | None:
    values = {**environment, "atomic": environment.get("ATOMIC", ""), "local_path:h": str(script.parent)}
    unresolved = []

    def replace(match):
        key = match.group(1) or match.group(2)
        value = values.get(key)
        if not value:
            unresolved.append(key)
        return value or match.group(0)

    expanded = re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_]\w*)", replace, text)
    if unresolved or any(char in expanded for char in "`$*?[];|<>\n"):
        return None
    expanded = os.path.expanduser(expanded)
    if expanded.startswith("~"):
        return None
    path = Path(expanded)
    return path if path.is_absolute() else cwd / path


def inspect_script_dependencies(script: Path, cwd: Path, environment: dict) -> dict:
    """Inspect literal links and sourced files, with a bounded include traversal."""
    links, sources, warnings, effects, visited = [], [], [], [], set()

    def visit(path):
        resolved = path.resolve()
        if resolved in visited:
            return
        if len(visited) >= 16:
            warnings.append("Script include limit reached; remaining effects require manual review.")
            return
        visited.add(resolved)
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                warnings.append(f"Script is too large to inspect: {path}")
                return
            contents = path.read_text(errors="replace")
        except OSError:
            return
        for number, line in enumerate(contents.splitlines(), 1):
            # Preserve commands for review, not execution. In particular, do not
            # resolve rm globs or pretend to evaluate sed/loops/conditionals.
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                effects.append({"source": str(path), "line": number, "shell_text": line,
                                "interpretation": "literal script text; control flow is not evaluated"})
            try:
                words = shlex.split(line, comments=True)
            except ValueError:
                continue
            if not words:
                continue
            if words[0] == "source" and len(words) == 2:
                target = _literal_path(words[1], cwd, environment, path)
                if "${local_path:h}" in words[1]:
                    warnings.append(f"{path}:{number}: assuming local_path points to this script for include discovery; its shell assignment is not evaluated.")
                sources.append({"source": str(path), "line": number, "expression": words[1],
                                "path": str(target) if target else None,
                                "exists": target.is_file() if target else None})
                # Only model-local includes are recursively inspected. Environment
                # setup scripts may have conditional assignments; never interpret them.
                if target and target.resolve().is_relative_to(cwd.parent.resolve()) and target.is_file():
                    visit(target)
            elif (words[0] == "ln" and len(words) >= 4
                  and all(flag in {"-s", "-f", "-sf", "-fs", "--"} for flag in words[1:-2])
                  and any("s" in flag for flag in words[1:-2])):
                target = _literal_path(words[-2], cwd, environment, path)
                destination = _literal_path(words[-1], cwd, environment, path)
                links.append({"source": str(path), "line": number, "target_expression": words[-2],
                              "destination_expression": words[-1], "target": str(target) if target else None,
                              "destination": str(destination) if destination else None,
                              "target_is_file": target.is_file() if target else None})
    visit(script)
    return {"links": links, "sources": sources, "warnings": warnings, "effects": effects,
            "coverage": "Literal link/source declarations only; arbitrary shell side effects are not inferred."}


def inspect_stage_preflight(model_dir: Path, stage: str, *, config: dict | None = None,
                            activity: dict | None = None) -> dict:
    if stage not in STAGE_INPUTS:
        raise ValueError("Unknown workflow stage")
    model_dir = model_dir.resolve()
    cwd = model_dir / ("obs" if stage == "flux" else "lte") if stage != "main" else model_dir
    environment = workflow_environment(config)
    issues = []

    def issue(level, code, message, file=None):
        issues.append({"severity": level, "code": code, "message": message, "file": file,
                       "available": bool(file and (model_dir / file).is_file()), "editable": False, "line": None})

    activity = activity if activity is not None else inspect_model_activity(model_dir)
    if not activity["safe_to_modify"]:
        issue("error", "model-not-idle", activity["reason"])
    for name in STAGE_INPUTS[stage]:
        path = cwd / name
        try:
            readable = path.is_file() and path.stat().st_size > 0 and os.access(path, os.R_OK)
        except OSError:
            readable = False
        if not readable:
            issue("error", "stage-input", f"{stage}: required input is missing, empty, or unreadable: {path}", str(path.relative_to(model_dir)))
        elif name.endswith(".sh") and not os.access(path, os.X_OK):
            issue("error", "stage-script-not-executable", f"{path} is not executable.", str(path.relative_to(model_dir)))
        elif name.endswith(".sh"):
            try:
                with path.open() as handle:
                    first_line = handle.readline(4096).strip()
                interpreter = shlex.split(first_line[2:]) if first_line.startswith("#!") else []
                if interpreter and (not Path(interpreter[0]).is_file() or not os.access(interpreter[0], os.X_OK)):
                    issue("error", "script-interpreter", f"Script interpreter is unavailable: {interpreter[0]}")
                elif not interpreter or Path(interpreter[0]).name == "env":
                    issue("warning", "script-interpreter-unresolved", f"Interpreter selection needs external-shell review: {path}")
            except (OSError, UnicodeError, ValueError):
                issue("error", "script-unreadable", f"Cannot read script header: {path}")
    if not cwd.is_dir() or not os.access(cwd, os.W_OK | os.X_OK):
        issue("error", "workspace-not-writable", f"Stage workspace is not writable/searchable: {cwd}")
    free = None
    if cwd.is_dir():
        try:
            free = shutil.disk_usage(cwd).free
        except OSError:
            issue("warning", "disk-space-unknown", "Could not inspect free space in the stage filesystem.")
    if free is not None:
        if free < 100 * 1024 * 1024:
            issue("error", "disk-space-critical", "Less than 100 MiB free in the stage filesystem.")
        elif free < 1024 ** 3:
            issue("warning", "disk-space-low", "Less than 1 GiB free; model-specific scratch requirements may be much larger.")

    executable = None
    if environment["cmfdist"]:
        executable = Path(environment["cmfdist"]).expanduser().resolve() / "exe" / STAGE_PROGRAMS[stage]
        if not executable.is_file() or not os.access(executable, os.X_OK):
            issue("error", "executable-unavailable", f"Configured executable is unavailable or non-executable: {executable}")
    else:
        issue(
            "warning",
            "executable-unresolved",
            "CMFDIST is not configured. Use --cmfgen-root, the CMFDIST "
            "environment variable, or cmfgen_root in .cmfgenrc. Executable "
            "resolution in the external shell is unverified.",
        )
    if not environment["ATOMIC"] and stage != "hydro":
        issue(
            "warning",
            "atomic-root-unresolved",
            "Atomic-data root is not configured. Use --atomic-root, the ATOMIC "
            "environment variable, or atomic_root in .cmfgenrc; shell-resolved "
            "data targets cannot be verified.",
        )

    script = cwd / ("ltebat.sh" if stage == "lte" else "batobs.sh" if stage == "flux" else "batch.sh")
    dependencies = inspect_script_dependencies(script, cwd, environment) if stage != "hydro" else {"links": [], "sources": [], "warnings": [], "effects": []}
    if stage in {"lte", "flux"}:
        try:
            text = script.read_text(errors="replace")
        except OSError:
            text = ""
        if "../batch.sh" in text:
            parent_script = model_dir / "batch.sh"
            if not parent_script.is_file() or not os.access(parent_script, os.X_OK):
                issue("error", "parent-link-script", "This stage calls ../batch.sh for atomic links, but that script is unavailable or non-executable.", "batch.sh")
            parent = inspect_script_dependencies(parent_script, cwd, environment)
            for key in ("links", "sources", "warnings", "effects"):
                dependencies[key].extend(parent[key])
    for source in dependencies["sources"]:
        if source["exists"] is False:
            issue("error", "sourced-file-missing", f"Required sourced script is missing: {source['path']}")
        elif source["exists"] is None:
            issue("warning", "sourced-file-unresolved", f"Cannot resolve sourced script statically: {source['expression']}")
    bad_links = [link for link in dependencies["links"] if link["target_is_file"] is False]
    for link in bad_links:
        name = Path(link["destination_expression"]).name
        level = "error" if name in REQUIRED_ATOMIC_LINKS else "warning"
        issue(level, "link-target-not-file", f"Link {name} targets a missing file or a directory: {link['target']}. Check whether this ion is enabled.")
    if any(link["target"] is None for link in dependencies["links"]):
        issue("warning", "link-target-unresolved", "Some atomic/restart link targets depend on unresolved shell expressions; review the script dependencies.")
    if stage == "lte":
        for filename, keys in {"VADAT": ("TEFF", "LOGG", "CHK_NG"), "MODEL_SPEC": ("ND", "NC", "NP")}.items():
            try:
                controls = control_occurrences((cwd / filename).read_text())
            except (OSError, UnicodeError):
                continue
            for key in keys:
                if len(controls.get(key, [])) != 1:
                    issue("error", "lte-control", f"lte/{filename} must contain exactly one [{key}].", f"lte/{filename}")
            if filename == "VADAT":
                for key in ("TEFF", "LOGG"):
                    value = parse_float_token(controls[key][0]["value"]) if controls.get(key) else None
                    if value is None or not math.isfinite(value) or (key == "TEFF" and value <= 0):
                        issue("error", "lte-control-value", f"LTE [{key}] must be finite" + (" and positive." if key == "TEFF" else "."), "lte/VADAT")
                if controls.get("CHK_NG") and controls["CHK_NG"][0]["value"].strip().upper() not in {"T", "F"}:
                    issue("error", "lte-control-value", "LTE [CHK_NG] must be T or F.", "lte/VADAT")
            if filename == "MODEL_SPEC":
                try:
                    nd, nc, np_ = (int(controls[key][0]["value"]) for key in keys)
                    valid = nd > 0 and nc >= 0 and np_ == nd + nc
                except (ValueError, KeyError, IndexError):
                    valid = False
                if not valid:
                    issue("error", "lte-grid", "LTE requires positive ND, nonnegative NC, and NP = ND + NC.", "lte/MODEL_SPEC")
    for warning in dependencies["warnings"]:
        issue("warning", "script-review", warning)
    counts = {level: sum(i["severity"] == level for i in issues) for level in ("error", "warning", "info")}
    return {"stage": stage, "cwd": str(cwd), "issues": issues, "counts": counts,
            "blocking": counts["error"] > 0, "activity": activity,
            "environment": environment, "executable": str(executable) if executable else None,
            "free_bytes": free, "script_dependencies": dependencies}
