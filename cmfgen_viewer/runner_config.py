"""Shared viewer and runner defaults; rc files are data, never shell scripts."""

import os
from pathlib import Path
import shlex

from .config_options import CONFIG_KEY_ALIASES, normalize_config_value
from .runner_recipe import RunnerError


KEYS = {
    "cmfgen_root": "cmfgen_root", "cmfdist": "cmfgen_root",
    "atomic_root": "atomic_root", "atomic": "atomic_root",
    "nthreads": "threads", "threads": "threads",
    **CONFIG_KEY_ALIASES,
}
ENVIRONMENT = {
    "cmfgen_root": "CMFDIST", "atomic_root": "ATOMIC", "threads": "OMP_NUM_THREADS",
}
LEGACY_ENVIRONMENT = {"cmfgen_root": "cmfdist", "atomic_root": "atomic"}


def _read_rc(path):
    values = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        name = KEYS.get(key.strip().lower().replace("-", "_"))
        location = f"{path}:{number}"
        if not separator or name is None:
            raise RunnerError(f"{location}: expected a supported viewer/runner setting in key = value form")
        if name in values:
            raise RunnerError(f"{location}: duplicate setting {name}")
        try:
            words = shlex.split(raw, comments=True)
        except ValueError as exc:
            raise RunnerError(f"{location}: invalid quoted value: {exc}") from exc
        if len(words) != 1 or not words[0].strip():
            raise RunnerError(f"{location}: expected one nonempty value (quote paths containing spaces)")
        value = words[0]
        if name in {"cmfgen_root", "atomic_root", "basepath", "upload_root", "template_root"}:
            value = Path(value).expanduser()
            if not value.is_absolute():
                value = path.parent / value
        elif name != "threads":
            try:
                value = normalize_config_value(name, value)
            except ValueError as exc:
                raise RunnerError(f"{location}: {exc}") from exc
        values[name] = value
    return values


def _rc_defaults():
    values, sources = {}, {}
    paths = dict.fromkeys((Path.home() / ".cmfgenrc", Path.cwd() / ".cmfgenrc"))
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        for name, value in _read_rc(path).items():
            values[name] = value
            sources[name] = str(path)
    return values, sources


def resolve_viewer_defaults():
    """Load viewer rc defaults; roots and threads retain runner/environment precedence."""
    values, sources = _rc_defaults()
    viewer_keys = set(CONFIG_KEY_ALIASES.values()) - {"cmfgen_root", "atomic_root"}
    return ({key: value for key, value in values.items() if key in viewer_keys},
            {key: source for key, source in sources.items() if key in viewer_keys})


def resolve_runner_config(
    *, cmfgen_root=None, atomic_root=None, threads=None, require_roots=True
):
    """Merge CLI > environment > cwd rc > home rc > built-in defaults.

    Relative rc paths are relative to their config's directory. Environment
    and CLI paths are relative to the invoking working directory.
    """
    values = {"threads": None}
    sources = {"threads": "default"}
    rc_values, rc_sources = _rc_defaults()
    for name in ("cmfgen_root", "atomic_root", "threads"):
        if name in rc_values:
            values[name] = rc_values[name]
            sources[name] = rc_sources[name]
    for environment in (LEGACY_ENVIRONMENT, ENVIRONMENT):
        for name, variable in environment.items():
            value = os.environ.get(variable)
            if value is not None and value.strip():
                values[name] = value
                sources[name] = f"env:{variable}"
    for name, value in {"cmfgen_root": cmfgen_root, "atomic_root": atomic_root, "threads": threads}.items():
        if value is not None:
            values[name] = value
            sources[name] = "cli"
    for name in ("cmfgen_root", "atomic_root"):
        if name not in values:
            if not require_roots:
                continue
            option = "--" + name.replace("_", "-")
            raise RunnerError(f"Missing {name}: supply {option}, {ENVIRONMENT[name]}, or {name} in ~/.cmfgenrc or ./.cmfgenrc")
        values[name] = Path(values[name]).expanduser().resolve()
    if values["threads"] is None:
        return values, sources
    try:
        values["threads"] = int(values["threads"])
        if values["threads"] < 1:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise RunnerError(f"nthreads must be a positive integer (source: {sources['threads']})") from exc
    return values, sources
