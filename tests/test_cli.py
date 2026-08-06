from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmfgen_viewer import cli


def test_parse_bool_config_value_accepts_supported_inputs() -> None:
    assert cli._parse_bool_config_value("flag", True) is True
    assert cli._parse_bool_config_value("flag", 1) is True
    assert cli._parse_bool_config_value("flag", "off") is False
    with pytest.raises(ValueError):
        cli._parse_bool_config_value("flag", "maybe")


def test_parse_int_config_value_accepts_int_like_values() -> None:
    assert cli._parse_int_config_value("port", 5567) == 5567
    assert cli._parse_int_config_value("port", 5567.0) == 5567
    assert cli._parse_int_config_value("port", "8080") == 8080
    with pytest.raises(ValueError):
        cli._parse_int_config_value("port", True)
    with pytest.raises(ValueError):
        cli._parse_int_config_value("port", "12.5")


def test_parse_float_config_value_accepts_numeric_values() -> None:
    assert cli._parse_float_config_value("x", 1.5) == 1.5
    assert cli._parse_float_config_value("x", "2.5") == 2.5
    with pytest.raises(ValueError):
        cli._parse_float_config_value("x", "nan")
    with pytest.raises(ValueError):
        cli._parse_float_config_value("x", False)


def test_load_config_defaults_from_json(tmp_path: Path) -> None:
    config_path = tmp_path / "viewer.json"
    config_path.write_text(
        json.dumps(
            {
                "cmfgen_viewer": {
                    "dir": "/tmp/models",
                    "port": "6000",
                    "all": "true",
                    "lambda_min": "900.0",
                    "lambda_max": 20000,
                    "fit_pool_size": "2",
                    "read_write": "true",
                    "upload_dir": "/tmp/spectrum-uploads",
                    "auth_user": "u",
                    "auth_password": "p",
                    "auth_realm": "Realm",
                }
            }
        ),
        encoding="utf-8",
    )
    defaults = cli._load_config_defaults(str(config_path))
    assert defaults["basepath"] == "/tmp/models"
    assert defaults["port"] == 6000
    assert defaults["show_all"] is True
    assert defaults["lambda_min"] == 900.0
    assert defaults["lambda_max"] == 20000.0
    assert defaults["fit_pool_size"] == 2
    assert defaults["read_write"] is True
    assert defaults["upload_root"] == "/tmp/spectrum-uploads"
    assert defaults["auth_user"] == "u"
    assert defaults["auth_password"] == "p"
    assert defaults["auth_realm"] == "Realm"


def test_load_config_defaults_from_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "viewer.toml"
    config_path.write_text(
        """
[cmfgen_viewer]
dir = "/tmp/models"
port = 6001
all = false
lambda_min = 1000.0
lambda_max = 21000.0
fit_pool_size = 4
read_write_enabled = false
upload_root = "/tmp/toml-spectrum-uploads"
debug = true
""".strip(),
        encoding="utf-8",
    )
    defaults = cli._load_config_defaults(str(config_path))
    assert defaults["basepath"] == "/tmp/models"
    assert defaults["port"] == 6001
    assert defaults["show_all"] is False
    assert defaults["lambda_min"] == 1000.0
    assert defaults["lambda_max"] == 21000.0
    assert defaults["fit_pool_size"] == 4
    assert defaults["read_write"] is False
    assert defaults["upload_root"] == "/tmp/toml-spectrum-uploads"
    assert defaults["debug"] is True


def test_load_config_defaults_rejects_unknown_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(json.dumps({"cmfgen_viewer": {"unsupported": 1}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported config option"):
        cli._load_config_defaults(str(config_path))


def test_read_only_flag_can_override_read_write_config_default() -> None:
    parser = cli.build_parser()
    parser.set_defaults(read_write=True)

    assert parser.parse_args([]).read_write is True
    assert parser.parse_args(["--read-only"]).read_write is False
    assert parser.parse_args(["--read-write"]).read_write is True


def test_main_invokes_create_app_and_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    upload_root = tmp_path / "persistent-uploads"

    class DummyApp:
        def run(self, *, host: str, port: int, debug: bool) -> None:
            captured["run"] = {"host": host, "port": port, "debug": debug}

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return DummyApp()

    monkeypatch.setattr(cli, "create_app", fake_create_app)

    cli.main(
        [
            "--dir",
            str(tmp_path),
            "--port",
            "7777",
            "--host",
            "0.0.0.0",
            "--lambda-min",
            "1000",
            "--lambda-max",
            "9000",
            "--fit-pool-size",
            "2",
            "--read-write",
            "--upload-dir",
            str(upload_root),
            "--secret",
            "fixed",
            "--auth-user",
            "viewer",
            "--auth-password",
            "secret",
            "--auth-realm",
            "Realm",
            "--debug",
        ]
    )

    create_kwargs = captured["create_app"]
    assert isinstance(create_kwargs, dict)
    assert create_kwargs["basepath"] == str(tmp_path.resolve())
    assert create_kwargs["lambda_min_angstrom"] == 1000.0
    assert create_kwargs["lambda_max_angstrom"] == 9000.0
    assert create_kwargs["fit_pool_size_max"] == 2
    assert create_kwargs["read_write_enabled"] is True
    assert create_kwargs["upload_root"] == str(upload_root.resolve())
    assert create_kwargs["auth_username"] == "viewer"
    assert create_kwargs["auth_password"] == "secret"
    assert create_kwargs["auth_realm"] == "Realm"
    assert captured["run"] == {"host": "0.0.0.0", "port": 7777, "debug": True}


def test_main_rejects_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--dir", str(tmp_path / "missing")])

    with pytest.raises(SystemExit):
        cli.main(["--dir", str(tmp_path), "--lambda-min", "10", "--lambda-max", "5"])

    with pytest.raises(SystemExit):
        cli.main(["--dir", str(tmp_path), "--auth-user", "viewer"])

    upload_file = tmp_path / "not-a-directory"
    upload_file.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["--dir", str(tmp_path), "--upload-dir", str(upload_file)])
