"""Window plot clipping and native sample preservation."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_diagnostic_window_plots():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for diagnostic plot checks")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("diagnostic_plots.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
