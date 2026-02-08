# CMFGEN Viewer

Simple Flask-based browser for CMFGEN model output directories.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python viewer.py --dir /path/to/cmfgen/run --port 5567
```

Then open `http://127.0.0.1:5567`.

## What Exists Now

- Flask app scaffold with runnable entry point: `viewer.py`
- Secure file browsing rooted at `--dir`:
  - `/view/` directory listing
  - `/view/<path>` file metadata + preview
  - `/raw/<path>` inline file serving
  - `/download/<path>` attachment download
- CMFGEN-oriented file role tagging:
  - `core_viewer` (e.g. `RVTJ`, `OBSFLUX`, `MOD_SUM`)
  - `optional_diagnostic` (e.g. `POP*`, `*OUT`, rates)
  - `restart_internal` (e.g. `SCRTEMP`, `POINT1/2`, `*_INFO`)
- Initial structured parsers + preview panels for:
  - `RVTJ` (core radial vectors and profile plots)
  - `OBSFLUX` (spectrum/luminosity vectors and diagnostic scalars)
  - `MOD_SUM` (dimensions, key scalars, tau rows, abundance table)
- Raw text preview supports syntax highlighting for common formats (for example shell scripts, Python, JSON, YAML, Markdown)

## Notes

The browsing UI and route layout are adapted from `../stdview` patterns
(breadcrumb navigation and split list/detail templates), simplified for
CMFGEN text-first workflows.
