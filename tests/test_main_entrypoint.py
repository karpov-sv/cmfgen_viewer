from __future__ import annotations

import runpy

from cmfgen_viewer import cli


def test_main_module_invokes_cli_main(monkeypatch) -> None:
    called = {"count": 0}

    def fake_main() -> None:
        called["count"] += 1

    monkeypatch.setattr(cli, "main", fake_main)
    runpy.run_module("cmfgen_viewer.__main__", run_name="__main__")
    assert called["count"] == 1
