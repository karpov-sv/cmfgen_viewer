from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def pending_notices():
    """Read action notices without consuming the next HTML page's flashes."""
    def read(client):
        with client.session_transaction() as session:
            return "\n".join(str(message) for _, message in session.get("_flashes", []))
    return read
