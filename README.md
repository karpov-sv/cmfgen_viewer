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
- Global observed-spectrum upload/overlay workflow, including async model-grid fitting against uploaded spectra.
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

### Example with config file

```bash
python viewer.py --config viewer.toml
```

`viewer.toml` (equivalent to CLI options):

```toml
[cmfgen_viewer]
dir = "/path/to/cmfgen/run"
port = 5567
host = "127.0.0.1"
all = false
lambda_min = 800
lambda_max = 20000
fit_pool_size = 0
debug = false
# Optional:
# secret = "fixed-secret"
# auth_user = "viewer"
# auth_password = "change-me"
# auth_realm = "CMFGEN Viewer"
```

### Useful flags

- `--config <path>` load defaults from a JSON/TOML config file (`[cmfgen_viewer]` section is supported for TOML).
- `--host 0.0.0.0` bind on all interfaces.
- `--all` show hidden files/directories.
- `--lambda-min 800` minimum wavelength (Angstroms) used for spectrum parsing/display.
- `--lambda-max 20000` maximum wavelength (Angstroms) used for spectrum parsing/display.
- `--fit-pool-size 0` max worker processes for upload grid fitting (`0` = auto/CPU count).
- `--auth-user <name>` enable HTTP Basic Auth (must be paired with `--auth-password`).
- `--auth-password <value>` HTTP Basic Auth password (must be paired with `--auth-user`).
- `--auth-realm <label>` auth prompt realm text (default: `CMFGEN Viewer`).
- `--debug` enable Flask debug and auto-reload.
- `--secret <value>` set a fixed Flask secret key.

## TLUSTY Grid Workflow

### 1. Download and preprocess TLUSTY spectra

Use the helper script to download OSTAR2002/BSTAR2006 archives and build reusable `.npz` spectra plus a CSV index:

```bash
python scripts/download_tlusty_spectra.py
```

Useful options:

- `--grid ostar --grid bstar` select one or both TLUSTY grids.
- `--product flux --product uv --product optical --product continuum` limit archive classes (default already includes all four).
- `--archive-pattern "<glob>"` limit archive names using shell-style patterns.
- `--crawl-depth <n>` set HTML link crawl depth (default: `2`).
- `--force-download` and `--force-process` refresh cached archives / processed `.npz` outputs.

By default, output is written under `data/tlusly/`:

- `data/tlusly/models.csv`: model index used by viewer-side TLUSTY discovery.
- `data/tlusly/manifest.json`: run metadata and archive-level processing summary.
- `data/tlusly/spectra/.../*.npz`: processed spectrum arrays used during fitting/overlay.

### 2. Run TLUSTY grid fitting in the upload viewer

After uploading an observed spectrum (`/uploads/view/<token>`):

- choose `TLUSTY grid` as the fit source and start the grid search;
- optionally restrict candidates with `model_name_pattern` (shell-style `fnmatch` rules);
- use the same fit controls as CMFGEN fitting: parameter bounds, optional wavelength fit range, progress polling, and `Stop Search`;
- see real-time best-so-far updates and overplot of the best current/final TLUSTY model.

Flux handling:

- absolute observed spectra are fitted against TLUSTY UV/optical absolute flux spectra;
- normalized observed spectra are fitted against TLUSTY spectra normalized by matched continuum counterparts.

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
  - `RVTJ`, `OBSFLUX`, `MOD_SUM`, `CORRECTION_SUM`, `MEANOPAC`, `RVSIG_COL*`, `GAMMAS*`, `OBSFRAME`, `HYDRO`, `HYDRO_PARAMS`,
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
  - upload detail page (`/uploads/view/<token>`) with file/format summary, parsed point counts, skipped-point diagnostics, and configured wavelength window display,
  - interactive uploaded-spectrum viewer with redshift/velocity sync, broadening, reddening, distance scaling, axis controls, and a resizable plot area,
  - FITS parsing for common 1D/2D and table-based formats,
  - normalized-spectrum safety filter: uploaded points with negative flux are treated as invalid.
- Upload model-grid fitting:
  - async server-side fit job API (`/uploads/fit-grid/...`) with progress polling and result payloads,
  - model discovery is DB-backed only via `model_summary_cache.sqlite` (no direct filesystem crawl during fit),
  - optional `model_name_pattern` filtering (shell-style pattern matching via `fnmatch.fnmatch`),
  - live indication of currently matched model count while editing the pattern,
  - configurable fit bounds (`z`, `sigma`, and in absolute mode also `E(B-V)` and distance),
  - optional fit wavelength limits (`fit_lambda_min`/`fit_lambda_max`), plus a `Use Plot Range` shortcut,
  - fit range visualization on the upload plot via vertical marker lines when range limits are set,
  - live "current best candidate" updates while the search runs,
  - best-so-far and final best-fit model overplot on the uploaded spectrum (final spectrum only, clipped to observed wavelength coverage),
  - active-search resume on page reload for the same upload token,
  - user-triggered cancellation (`Stop Search`) with immediate pool termination in parallel mode,
  - result reporting includes both redshift and corresponding velocity (`v = z * c`).
- Parallel upload grid fitting:
  - optional multiprocessing worker pool controlled by `--fit-pool-size` (`0` means auto),
  - sequential fallback remains available when resolved worker count is 1.
- Configurable wavelength window for all displayed spectra:
  - `--lambda-min` / `--lambda-max` bounds applied to both model spectra and uploaded overlays.
- Documentation section with top-nav dropdown populated from `doc/*.md`, rendered as markdown with code highlighting.

### Not yet implemented

- Automated test suite.
- Some CMFGEN output formats still rely on generic/plain text preview instead of dedicated parsers.
- Generic direct-access/binary readers using `_INFO` sidecars.
- Cross-file consistency checks and preflight validation workflows.
- Persisting grid-fit jobs/results across Flask process restarts.
- TLUSTY absolute-flux calibration follow-up: validate whether scaling should use model-specific stellar radius rather than the current fixed 1 `R_sun` reference.

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
- Upload grid fitting requires a populated summary cache database (`model_summary_cache.sqlite`), typically produced by the `Summarize` workflow.
- Optional app-wide HTTP Basic Auth can be enabled from CLI using `--auth-user` and `--auth-password`.
