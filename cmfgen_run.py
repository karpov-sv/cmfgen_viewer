#!/usr/bin/env python3
"""Standalone CMFGEN runner; no web server is started."""
from cmfgen_viewer.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
