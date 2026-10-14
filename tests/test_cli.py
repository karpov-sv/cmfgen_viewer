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
                    "template_root": "/tmp/templates",
                    "cmfgen_root": "/tmp/cmf",
                    "atomic_root": "/tmp/atomic",
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
    assert defaults["template_root"] == "/tmp/templates"
    assert defaults["cmfgen_root"] == "/tmp/cmf"
    assert defaults["atomic_root"] == "/tmp/atomic"


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
            "--template-root",
            str(tmp_path / "custom-templates"),
            "--cmfgen-root",
            "/tmp/cmf",
            "--atomic-root",
            "/tmp/atomic",
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
    assert create_kwargs["template_root"] == str(tmp_path / "custom-templates")
    assert create_kwargs["cmfgen_root"] == str(Path("/tmp/cmf").resolve())
    assert create_kwargs["atomic_root"] == str(Path("/tmp/atomic").resolve())
    assert create_kwargs["cmfgen_config_sources"]["cmfgen_root"] == "viewer CLI/config"
    assert create_kwargs["cmfgen_config_sources"]["atomic_root"] == "viewer CLI/config"
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


@pytest.mark.parametrize("threads", [None, 3])
def test_main_uses_runner_rc_fallbacks_for_workflow_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, threads: int | None
) -> None:
    captured: dict[str, object] = {}
    user_dir = tmp_path / "home"
    work_dir = tmp_path / "work"
    model_dir = tmp_path / "models"
    user_dir.mkdir()
    work_dir.mkdir()
    model_dir.mkdir()
    (user_dir / ".cmfgenrc").write_text(
        "cmfgen_root = cmf\natomic_root = atomic\n" + (f"nthreads = {threads}\n" if threads is not None else ""),
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_dir))
    monkeypatch.chdir(work_dir)
    for name in ("CMFDIST", "ATOMIC", "OMP_NUM_THREADS"):
        monkeypatch.delenv(name, raising=False)

    class DummyApp:
        def run(self, **kwargs) -> None:
            captured["run"] = kwargs

    def fake_create_app(**kwargs):
        captured["create_app"] = kwargs
        return DummyApp()

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    cli.main(["--dir", str(model_dir)])

    create_kwargs = captured["create_app"]
    assert isinstance(create_kwargs, dict)
    assert create_kwargs["cmfgen_root"] == str(user_dir / "cmf")
    assert create_kwargs["atomic_root"] == str(user_dir / "atomic")
    assert create_kwargs["cmfgen_runner_threads"] == threads
    assert create_kwargs["cmfgen_config_sources"] == {
        "cmfgen_root": str(user_dir / ".cmfgenrc"),
        "atomic_root": str(user_dir / ".cmfgenrc"),
        "threads": str(user_dir / ".cmfgenrc") if threads is not None else "default",
        "read_write": "default",
    }


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


@pytest.mark.parametrize("config_values,flags,expected_access,expected_min", [
    ({}, [], True, 1000),
    ({}, ["--read-only", "--lambda-min", "1500"], False, 1500),
    ({"read_write": False, "lambda_min": 1200}, [], False, 1200),
    ({"read_write": False, "lambda_min": 1200}, ["--read-write", "--lambda-min", "1600"], True, 1600),
])
def test_main_rc_viewer_defaults_with_config_and_cli_precedence(
    tmp_path, monkeypatch, config_values, flags, expected_access, expected_min
):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    models = home / "model tree"
    models.mkdir()
    (home / ".cmfgenrc").write_text('dir = "model tree"\nlambda_min = 900\nread_write = false\n'
                                       'cmfgen_root = rc-cmf\natomic_root = rc-atomic\nnthreads = 2\n')
    (work / ".cmfgenrc").write_text(
        'read_write = true\nlambda-min = 1000\nlambda-max = 20000\nport = 6002\n'
        'host = 127.0.0.2\nall = true\nfit_pool_size = 2\n'
        'upload_dir = uploads\ntemplate_root = templates\ndebug = false\n'
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(work)
    monkeypatch.setenv("CMFDIST", "env-cmf")
    monkeypatch.setenv("ATOMIC", "env-atomic")
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    captured = {}

    class DummyApp:
        def run(self, **kwargs):
            captured["run"] = kwargs

    def create(**kwargs):
        captured.update(kwargs)
        return DummyApp()

    monkeypatch.setattr(cli, "create_app", create)
    arguments = list(flags)
    if config_values:
        config = work / "viewer.json"
        config.write_text(json.dumps(config_values))
        arguments += ["--config", str(config)]
    cli.main(arguments)
    assert captured["cmfgen_root"] == str(work / "env-cmf")
    assert captured["atomic_root"] == str(work / "env-atomic")
    assert captured["cmfgen_runner_threads"] == 3
    assert captured["basepath"] == str(models)
    assert captured["read_write_enabled"] is expected_access
    assert captured["lambda_min_angstrom"] == expected_min
    assert captured["lambda_max_angstrom"] == 20000
    assert captured["show_all"] is True
    assert captured["fit_pool_size_max"] == 2
    assert captured["upload_root"] == str(work / "uploads")
    assert captured["template_root"] == work / "templates"
    assert captured["run"] == {"host": "127.0.0.2", "port": 6002, "debug": False}
    assert captured["cmfgen_config_sources"]["read_write"] == (
        "viewer CLI/config" if config_values or "--read-only" in flags else str(work / ".cmfgenrc")
    )


@pytest.mark.parametrize("text", ["read_write = maybe", "lambda_min = -5", "lambda_max = 500",
                                  "fit_pool_size = -1", "port = 12.5"])
def test_main_rejects_invalid_viewer_rc_before_starting(tmp_path, monkeypatch, text):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cmfgenrc").write_text(text)
    monkeypatch.setattr(cli, "create_app", lambda **kwargs: pytest.fail("must not start with invalid config"))
    with pytest.raises(SystemExit):
        cli.main([])
