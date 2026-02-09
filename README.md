# CMFGEN Viewer

Flask-based, text-first viewer for CMFGEN and CMF_FLUX run directories.

## Aim

This project provides a practical local web UI for inspecting CMFGEN model folders without manual `grep`/editor hopping. The focus is fast triage of run outputs and key control files:

- browse files safely inside a selected root directory,
- identify files by CMFGEN role (input/control/output/restart/etc.),
- preview raw text and parsed summaries for important formats,
- document CMFGEN/CMF_FLUX file-I/O knowledge in-app for quick reference.

## Scope

### In scope

- Local single-user viewer (Flask app), launched against an existing run directory.
- Structured parsing for high-value text outputs (`RVTJ`, `OBSFLUX`, `MOD_SUM`).
- Role tagging for CMFGEN and CMF_FLUX related files using known filenames/patterns.
- Documentation browser backed by markdown files in `doc/`.

### Out of scope (current)

- Running CMFGEN/CMF_FLUX jobs.
- Editing/writing model files from the UI.
- Full binary/direct-access file decoding for all `_INFO`/direct-access artifacts.
- Auth/multi-user deployment hardening.

## Installation

### Prerequisites

- Python 3.10+ recommended
- `pip`

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Viewer

### Basic run

```bash
python viewer.py --dir /path/to/cmfgen/run --port 5567
```

Open `http://127.0.0.1:5567`.

### Alternative entry point

```bash
python -m cmfgen_viewer --dir /path/to/cmfgen/run
```

### Useful flags

- `--host 0.0.0.0` bind on all interfaces.
- `--all` show hidden files/directories.
- `--lambda-min 800` minimum wavelength (Angstroms) used for spectrum parsing/display.
- `--lambda-max 20000` maximum wavelength (Angstroms) used for spectrum parsing/display.
- `--debug` enable Flask debug and auto-reload.
- `--secret <value>` set a fixed Flask secret key.

## Current Implementation Status

### Implemented

- Secure rooted browsing:
  - `/view/` and `/view/<path>`
  - `/raw/<path>` and `/download/<path>`
  - path traversal blocked by resolved-path checks
- File table UX:
  - sortable columns, folders listed first
  - symlink hide/show toggle in model directories
  - quick links under breadcrumb for key files (`VADAT`, `MODEL_SPEC`, `IN_ITS`, `MOD_SUM`, `RVTJ`, `OBSFLUX`, etc.)
- Role classification:
  - roles for core/optional/restart/input categories
  - filename and pattern-based mapping (`POP*`, `*OUT`, `*_F_OSCDAT`, `PHOT*_A`, `DIE*`, etc.)
  - extended CMF_FLUX-related file coverage
- File preview:
  - raw text syntax highlighting (Pygments)
  - CMFGEN control-file lexer with aligned `value [KEY] !comment` columns
  - unknown formats default to plain text fallback (no aggressive lexer guessing)
  - parsed/raw mode toggle (parsed view shown by default when available)
- Parsed views:
  - `RVTJ`: radial vectors, validation warnings, profile plots
  - `OBSFLUX`: wavelength-space spectrum (Å), diagnostics, interactive plots
  - `MOD_SUM`: metadata, dimensions, key scalars, abundance/tau tables
  - Plotly interactions: zoom/pan/hover/export, linear/log axis toggles
- Documentation section:
  - top-nav dropdown populated from `doc/*.md`
  - markdown rendering with syntax-highlighted code blocks
  - pages currently included:
    - CMFGEN input files
    - CMFGEN output files
    - CMFGEN CMF_FLUX files

### Not yet implemented

- Automated test suite.
- Parsers for many additional text outputs (`NETRATE`, `TOTRATE`, `HYDRO`, etc.).
- Generic direct-access/binary readers using `_INFO` sidecars.
- Cross-file consistency checks and preflight validation workflows.

## Repository Layout

- `viewer.py`: executable entry point.
- `cmfgen_viewer/`:
  - `app.py`, `cli.py`, `views.py`: app factory, CLI, routes.
  - `browser.py`: directory/file metadata, role classification.
  - `syntax.py`: syntax highlighting + CMFGEN input lexer.
  - `parsers/`: parsed-view implementations (`rvtj.py`, `obsflux.py`, `mod_sum.py`).
  - `templates/`, `static/`: Jinja templates, JS, CSS.
- `doc/`: markdown docs surfaced in the Documentation menu.
- `CMFGEN_*_investigation_*.txt`: source investigation logs.

## Notes

- The UI is optimized for local analysis workflows and iterative parser development.
- Large-file parsing is guarded (`MAX_PARSE_FILE_BYTES`) to avoid heavy accidental loads.
- Documentation pages are generated from repository markdown; update files in `doc/` to extend in-app docs.
