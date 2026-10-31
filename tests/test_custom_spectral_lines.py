"""Shared custom-line parsing and overlay behavior."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_custom_line_controls_and_overlay():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for spectral line checks")
    result = subprocess.run([node, str(Path(__file__).with_name("custom_spectral_lines.cjs"))],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
