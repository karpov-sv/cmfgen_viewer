from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .app import create_app
from .config_options import (
    CONFIG_KEY_ALIASES,
    _parse_bool_config_value,
    _parse_int_config_value,
    _parse_float_config_value,
    normalize_config_value,
)
from .runner_config import resolve_viewer_defaults, resolve_runner_config
from .runner_recipe import RunnerError

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.11+ provides tomllib
    tomllib = None


def _load_config_defaults(config_path: str) -> dict[str, object]:
    path = Path(config_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"--config must point to an existing file: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read config file '{path}': {exc}") from exc

    suffix = path.suffix.lower()
    parsed: object
    if suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON config '{path}': {exc}") from exc
    elif suffix in {".toml", ".tml"}:
        if tomllib is None:
            raise ValueError("TOML config is not supported on this Python version.")
        try:
            parsed = tomllib.loads(text)
        except Exception as exc:
            raise ValueError(f"Failed to parse TOML config '{path}': {exc}") from exc
    else:
        parse_errors: list[str] = []
        parsed = None
        if tomllib is not None:
            try:
                parsed = tomllib.loads(text)
            except Exception as exc:
                parse_errors.append(f"TOML: {exc}")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"JSON: {exc}")
        if parsed is None:
            joined = "; ".join(parse_errors) if parse_errors else "unsupported format"
            raise ValueError(
                f"Could not parse config '{path}'. Use .json or .toml file extension. Details: {joined}"
            )

    if not isinstance(parsed, dict):
        raise ValueError(f"Config file '{path}' must contain a JSON object or TOML table.")

    section: dict[str, object] = parsed
    for section_name in ("cmfgen_viewer", "viewer"):
        candidate = parsed.get(section_name)
        if isinstance(candidate, dict):
            section = candidate
            break

    defaults: dict[str, object] = {}
    unknown_keys: list[str] = []
    for raw_key, raw_value in section.items():
        normalized_key = str(raw_key).strip().lower().replace("-", "_")
        dest = CONFIG_KEY_ALIASES.get(normalized_key)
        if dest is None:
            unknown_keys.append(str(raw_key))
            continue
        defaults[dest] = raw_value

    if unknown_keys:
        keys = ", ".join(sorted(unknown_keys))
        raise ValueError(f"Unsupported config option(s): {keys}")

    return {key: normalize_config_value(key, value) for key, value in defaults.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CMFGEN model results viewer")
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help="Path to JSON/TOML config file with the same options as CLI flags",
    )
    parser.add_argument(
        "-d",
        "--dir",
        dest="basepath",
        default=".",
        help="Directory to browse (default: current directory)",
    )
    parser.add_argument(
        "-p",
        "--port",
        dest="port",
        type=int,
        default=5567,
        help="Port to bind (default: 5567)",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "-a",
        "--all",
        dest="show_all",
        action="store_true",
        help="Show hidden files and directories",
    )
    parser.add_argument(
        "--lambda-min",
        dest="lambda_min",
        type=float,
        default=800.0,
        help="Minimum wavelength in Angstroms for parsed/displayed spectra (default: 800)",
    )
    parser.add_argument(
        "--lambda-max",
        dest="lambda_max",
        type=float,
        default=250000.0,
        help="Maximum wavelength in Angstroms for parsed/displayed spectra (default: 250000, 25 um)",
    )
    parser.add_argument(
        "--upload-dir",
        dest="upload_root",
        default=None,
        help=(
            "Directory for persistent uploaded-spectrum bundles "
            "(default: system temporary directory/cmfgen_viewer_uploads)"
        ),
    )
    parser.add_argument(
        "--fit-pool-size",
        dest="fit_pool_size",
        type=int,
        default=0,
        help=(
            "Maximum worker processes for upload grid fitting "
            "(0 = auto based on CPU count, default: 0)"
        ),
    )
    access_group = parser.add_mutually_exclusive_group()
    access_group.add_argument(
        "--read-write",
        dest="read_write",
        action="store_true",
        help="Allow operations that modify model directories (default: viewer config, .cmfgenrc read_write, or disabled)",
    )
    access_group.add_argument(
        "--read-only",
        dest="read_write",
        action="store_false",
        help="Disable operations that modify model directories (the default; overrides config)",
    )
    parser.set_defaults(read_write=False)
    parser.add_argument("--keep-large-files", action=argparse.BooleanOptionalAction, default=False, help="Keep full-size recovery artifacts and logs for UI-launched workflows (default: false)")
    parser.add_argument("--template-root", default=None, help="Workflow template root containing lte/ and obs/ (default: model-tree templates, then packaged defaults)")
    parser.add_argument(
        "--cmfgen-root",
        default=None,
        help="CMFGEN installation root for workflow preflight (default: CMFDIST or .cmfgenrc)",
    )
    parser.add_argument(
        "--atomic-root",
        default=None,
        help="Atomic-data root for workflow preflight (default: ATOMIC or .cmfgenrc)",
    )
    parser.add_argument(
        "--auth-user",
        dest="auth_user",
        default=None,
        help="Enable HTTP Basic Auth with this username (requires --auth-password)",
    )
    parser.add_argument(
        "--auth-password",
        dest="auth_password",
        default=None,
        help="HTTP Basic Auth password (requires --auth-user)",
    )
    parser.add_argument(
        "--auth-realm",
        dest="auth_realm",
        default="CMFGEN Viewer",
        help="HTTP Basic Auth realm label (default: CMFGEN Viewer)",
    )
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable Flask debug mode",
    )
    parser.add_argument(
        "-s",
        "--secret",
        dest="secret",
        default=None,
        help="Flask secret key; random key is generated by default",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--config", dest="config_path", default=None)
    pre_access = pre_parser.add_mutually_exclusive_group()
    pre_access.add_argument("--read-write", dest="read_write", action="store_true")
    pre_access.add_argument("--read-only", dest="read_write", action="store_false")
    pre_parser.set_defaults(read_write=None)
    pre_args, _unknown_args = pre_parser.parse_known_args(argv)

    config_defaults: dict[str, object] = {}
    config_error = ""
    if pre_args.config_path:
        try:
            config_defaults = _load_config_defaults(str(pre_args.config_path))
        except ValueError as exc:
            config_error = str(exc)

    parser = build_parser()
    if config_error:
        parser.error(config_error)
    try:
        rc_defaults, rc_sources = resolve_viewer_defaults()
    except (RunnerError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    parser.set_defaults(**rc_defaults)
    if config_defaults:
        parser.set_defaults(**config_defaults)
    args = parser.parse_args(argv)

    basepath = Path(args.basepath).expanduser().resolve()
    if not basepath.exists() or not basepath.is_dir():
        parser.error(f"--dir must point to an existing directory: {basepath}")
    if not math.isfinite(args.lambda_min) or not math.isfinite(args.lambda_max):
        parser.error("--lambda-min and --lambda-max must be finite numbers.")
    if args.lambda_min <= 0 or args.lambda_max <= 0:
        parser.error("--lambda-min and --lambda-max must be positive.")
    if args.lambda_min >= args.lambda_max:
        parser.error("--lambda-min must be smaller than --lambda-max.")
    if args.fit_pool_size < 0:
        parser.error("--fit-pool-size must be zero or a positive integer.")

    upload_root: Path | None = None
    if args.upload_root is not None:
        upload_root_text = str(args.upload_root).strip()
        if not upload_root_text:
            parser.error("--upload-dir must not be empty.")
        upload_root = Path(upload_root_text).expanduser().resolve()
        if upload_root.exists() and not upload_root.is_dir():
            parser.error(f"--upload-dir must point to a directory or a path that can be created: {upload_root}")

    auth_user_provided = args.auth_user is not None
    auth_password_provided = args.auth_password is not None
    if auth_user_provided != auth_password_provided:
        parser.error("--auth-user and --auth-password must be provided together.")

    auth_user: str | None = None
    auth_password: str | None = None
    if auth_user_provided and auth_password_provided:
        auth_user = str(args.auth_user).strip()
        auth_password = str(args.auth_password)
        if not auth_user:
            parser.error("--auth-user must not be empty.")
        if not auth_password:
            parser.error("--auth-password must not be empty.")

    try:
        cmfgen_settings, cmfgen_sources = resolve_runner_config(
            cmfgen_root=args.cmfgen_root,
            atomic_root=args.atomic_root,
            require_roots=False,
        )
    except RunnerError as exc:
        parser.error(str(exc))
    cmfgen_sources = {
        key: "viewer CLI/config" if source == "cli" else source
        for key, source in cmfgen_sources.items()
    }

    cmfgen_sources["read_write"] = (
        "viewer CLI/config" if pre_args.read_write is not None or "read_write" in config_defaults
        else rc_sources.get("read_write", "default")
    )

    app = create_app(
        basepath=str(basepath),
        show_all=args.show_all,
        lambda_min_angstrom=args.lambda_min,
        lambda_max_angstrom=args.lambda_max,
        upload_root=str(upload_root) if upload_root is not None else None,
        fit_pool_size_max=args.fit_pool_size,
        read_write_enabled=args.read_write,
        keep_large_files=args.keep_large_files,
        secret_key=args.secret,
        auth_username=auth_user,
        auth_password=auth_password,
        auth_realm=str(args.auth_realm or "CMFGEN Viewer"),
        template_root=args.template_root,
        cmfgen_root=str(cmfgen_settings["cmfgen_root"])
        if "cmfgen_root" in cmfgen_settings
        else None,
        atomic_root=str(cmfgen_settings["atomic_root"])
        if "atomic_root" in cmfgen_settings
        else None,
        cmfgen_runner_threads=cmfgen_settings["threads"],
        cmfgen_config_sources=cmfgen_sources,
    )
    app.run(host=args.host, port=args.port, debug=args.debug)
