"""Regression checks for the shared spectrum UI controller."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_spectrum_controller_preserves_trace_ownership_and_control_behavior():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for spectrum controller checks")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("spectrum_controller.cjs"))],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
