"""Exercise completion races and the shared workflow refresh guard in JavaScript."""
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


@pytest.mark.parametrize("script", ["model_runtime.cjs", "workflow_runner.cjs"])
def test_workflow_completion(script):
    result = subprocess.run([NODE, str(Path(__file__).with_name(script))],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
