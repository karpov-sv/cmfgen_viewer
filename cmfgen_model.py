#!/usr/bin/env python3
"""Standalone CMFGEN model maintenance; no web server is started."""
from cmfgen_viewer.model_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
