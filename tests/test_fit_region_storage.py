"""Browser draft persistence for diagnostic windows and exclusions."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_fit_region_storage():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for browser storage checks")
    result = subprocess.run(
        [node, str(Path(__file__).with_name("fit_region_storage.cjs"))],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
