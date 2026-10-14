"""Option names and typed values shared by viewer configuration formats."""

from __future__ import annotations

import math

CONFIG_KEY_ALIASES: dict[str, str] = {
    "dir": "basepath",
    "basepath": "basepath",
    "port": "port",
    "host": "host",
    "all": "show_all",
    "show_all": "show_all",
    "lambda_min": "lambda_min",
    "lambda_max": "lambda_max",
    "fit_pool_size": "fit_pool_size",
    "read_write": "read_write",
    "keep_large_files": "keep_large_files",
    "read_write_enabled": "read_write",
    "upload_dir": "upload_root",
    "upload_root": "upload_root",
    "debug": "debug",
    "secret": "secret",
    "auth_user": "auth_user",
    "auth_password": "auth_password",
    "auth_realm": "auth_realm",
    "template_root": "template_root",
    "cmfgen_root": "cmfgen_root",
    "atomic_root": "atomic_root",
}


def _parse_bool_config_value(name: str, value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Config option '{name}' must be a boolean value.")


def _parse_int_config_value(name: str, value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Config option '{name}' must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer():
            return int(value)
        raise ValueError(f"Config option '{name}' must be an integer.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"Config option '{name}' must be an integer.")
        try:
            return int(text, 10)
        except ValueError as exc:
            raise ValueError(f"Config option '{name}' must be an integer.") from exc
    raise ValueError(f"Config option '{name}' must be an integer.")


def _parse_float_config_value(name: str, value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Config option '{name}' must be a number.")
    if isinstance(value, int | float):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
        raise ValueError(f"Config option '{name}' must be a finite number.")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"Config option '{name}' must be a number.")
        try:
            numeric = float(text)
        except ValueError as exc:
            raise ValueError(f"Config option '{name}' must be a number.") from exc
        if math.isfinite(numeric):
            return numeric
        raise ValueError(f"Config option '{name}' must be a finite number.")
    raise ValueError(f"Config option '{name}' must be a number.")


def normalize_config_value(name: str, value: object) -> object:
    if name in {"show_all", "debug", "read_write", "keep_large_files"}:
        return _parse_bool_config_value(name, value)
    if name in {"port", "fit_pool_size"}:
        return _parse_int_config_value(name, value)
    if name in {"lambda_min", "lambda_max"}:
        return _parse_float_config_value(name, value)
    if name in {"secret", "auth_user", "auth_password"}:
        return None if value is None else str(value)
    return str(value)
