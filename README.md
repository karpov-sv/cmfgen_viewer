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
- Structured parsing for many CMFGEN/CMF_FLUX text outputs (not only core files).
- Role tagging for CMFGEN and CMF_FLUX related files using known filenames/patterns.
- Single-model and bulk model spectrum visualization workflows.
- Global observed-spectrum upload/overlay workflow for model comparison.
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

### Example with spectral range filtering

```bash
python viewer.py --dir /path/to/cmfgen/run --lambda-min 1200 --lambda-max 9000
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

- Secure rooted browsing (`/view/`, `/raw/`, `/download/`) with resolved-path checks against traversal.
- File table UX with sortable columns, folders-first ordering, symlink hide/show toggle in model context, quick links, and multi-model selection checkboxes.
- Bulk operations on selected model folders:
  - `Summarize`: table output similar to legacy `list_models.py`.
  - `Plot Spectra`: combined interactive plot using first available `obs_fin*` plus `obs/obs_cont`.
- Role classification for CMFGEN/CMF_FLUX files, including input/output/restart/diagnostic categories.
- Raw preview and parsed preview modes:
  - syntax highlighting via Pygments,
  - CMFGEN input lexer with aligned `value [KEY] !comment` style formatting,
  - plain-text fallback for unknown files.
- Parsed-view coverage includes core and diagnostic families such as:
  - `RVTJ`, `OBSFLUX`, `MOD_SUM`, `MEANOPAC`, `RVSIG_COL*`, `GAMMAS*`, `OBSFRAME`, `HYDRO`, `HYDRO_PARAMS`,
  - `OUTLTE`, `OUT_FLUX`, `OUT_PARAMS`, `TRANS_INFO`, `ML_COUNTER`, `DIAGNOSTIC_EST_*`, `TIME_PNT*`,
  - `POP*`, `*OUT` departure files, `NETRATE`/`TOTRATE`/`EWDATA`/`LINEHEAT`, `J_COMP`, `SOB_FORCE_MULT`, `GAMFLUX`, `GAMRAY_ENERGY_DEP`, `CFDAT_OUT`, `CONT_FREQ`, `OBS_FREQ`.
- Final spectrum tools:
  - single-model `/spectrum/<path>` and bulk-spectrum `/bulk/spectra/<path>` views,
  - Plotly interactivity with log/linear toggles, redshift/velocity, distance scaling, reddening `E(B-V)`, and resizable plot container,
  - observed overlay support with flux-mode compatibility checks,
  - bulk visibility toggles for final vs continuum traces (without removing traces).
- Global uploads workflow:
  - upload management page (`/uploads/`),
  - quasi-persistent tokenized uploads under upload root,
  - FITS parsing for common 1D/2D and table-based formats.
- Configurable wavelength window for all displayed spectra:
  - `--lambda-min` / `--lambda-max` bounds applied to both model spectra and uploaded overlays.
- Documentation section with top-nav dropdown populated from `doc/*.md`, rendered as markdown with code highlighting.

### Not yet implemented

- Automated test suite.
- Some CMFGEN output formats still rely on generic/plain text preview instead of dedicated parsers.
- Generic direct-access/binary readers using `_INFO` sidecars.
- Cross-file consistency checks and preflight validation workflows.
- Automatic model fitting/scoring against uploaded observed spectra.

## Repository Layout

- `viewer.py`: executable entry point.
- `cmfgen_viewer/`:
  - `app.py`, `cli.py`, `views.py`: app factory, CLI, routing and UI orchestration.
  - `browser.py`: directory/file metadata and role classification.
  - `final_spectrum.py`: CMFGEN final-spectrum parsing, conversion, and plot assembly helpers.
  - `observed_spectrum.py`: uploaded observed-spectrum parsing and upload-manifest lifecycle.
  - `syntax.py`: syntax highlighting and CMFGEN input lexer.
  - `parsers/`: parsed-view implementations for core and diagnostic file families.
  - `templates/`, `static/`: Jinja templates, client-side JS, and CSS.
- `doc/`: markdown docs surfaced in the Documentation menu.
- `CMFGEN_*_investigation_*.txt`: source investigation logs.

## Notes

- The UI is optimized for local analysis workflows and iterative parser development.
- Large-file parsing is guarded (`MAX_PARSE_FILE_BYTES`) to avoid heavy accidental loads.
- Documentation pages are generated from repository markdown; update files in `doc/` to extend in-app docs.
