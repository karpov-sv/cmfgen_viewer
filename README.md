# CMFGEN Viewer

Flask-based, text-first viewer for CMFGEN and CMF_FLUX run directories, with a
standalone command-line runner for model inspection and execution.

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
- Standalone command-line model status, preflight, and reviewed native execution workflows.
- Documentation browser backed by markdown files in `doc/`.

### Out of scope (current)

- Launching or supervising CMFGEN/CMF_FLUX jobs from the web UI.
- Arbitrary editing of model files beyond the allowlisted control-file editor and controlled model workflows.
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
lambda_max = 250000
fit_pool_size = 0
upload_dir = "/path/to/persistent/spectrum-uploads"
read_write = false
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
- `--lambda-max 250000` maximum wavelength (Angstroms) used for spectrum parsing/display (25 um).
- `--upload-dir <path>` store uploaded-spectrum bundles in a persistent directory instead of the default temporary location.
- `--fit-pool-size 0` max worker processes for upload grid fitting (`0` = auto/CPU count).
- `--read-write` enable operations that modify the configured model directory tree (disabled by default).
- `--read-only` explicitly disable model-directory mutations, overriding a read-write config setting.
- `--auth-user <name>` enable HTTP Basic Auth (must be paired with `--auth-password`).
- `--auth-password <value>` HTTP Basic Auth password (must be paired with `--auth-user`).
- `--auth-realm <label>` auth prompt realm text (default: `CMFGEN Viewer`).
- `--debug` enable Flask debug and auto-reload.
- `--secret <value>` set a fixed Flask secret key.

## Model Grids

The upload viewer fits observed spectra and photometry against CMFGEN models
and imported TLUSTY, BOSZ, or PHOENIX grids, with candidate filtering, progress,
cancellation, and best-fit overlays. See [Model Grids](MODEL_GRIDS.md) for
TLUSTY downloads, local BOSZ/PHOENIX imports, flux conventions, quality checks,
and fitting performance.

## Command-line Runner

`cmfgen_run.py` inspects model state and runs a reviewed subset of the ostar
workflows directly through native CMFGEN/CMF_FLUX executables. It runs
independently of Flask and does not execute the legacy shell scripts.

Configure installation and atomic-data roots in `~/.cmfgenrc` or a `.cmfgenrc`
in the invoking current directory:

```ini
cmfgen_root = ~/CMFGEN2023/cur_cmf
atomic_root = ~/CMFGEN2023/atomic
```

You can also supply `--cmfgen-root` and `--atomic-root`, or set `CMFDIST` and
`ATOMIC` in the environment.

```bash
# Read-only model information, run/checkpoint state, iteration counts, and preflight
python3 cmfgen_run.py /path/to/model

# Preview a main-stage run without changing the model
python3 cmfgen_run.py /path/to/model --stage main --plan

# Run the model using its configured iteration controls
python3 cmfgen_run.py /path/to/model --stage main

# Run a zero-iteration native startup test
python3 cmfgen_run.py /path/to/model --stage test
```

Execution requires an explicit `--stage`. The `test` stage validates startup
and writes atmosphere/checkpoint outputs; it does not create a model directory.
Available stages are `test`, `main`, `lte`, `hydro`, `promote`, `flux`, and
`cleanup`. Repeat `--stage` for an ordered sequence, for example
`--stage test --stage main`.

Main/test runs continue from usable checkpoints automatically. Use
`--fresh-start` to archive them and start from `*_IN`; `--iterations N`
temporarily overrides the main-stage iteration count. Memory, time, and thread
controls are opt-in through `--memory-mib`, `--timeout`, and `--threads` (or
configured thread settings); host limits still apply. Terminal progress bars
appear when an estimate is available. `--json` returns structured status,
plans, or results, and executed actions retain logs under `.cmfgen-runs/`.

See the [standalone runner guide](doc/cmfgen-standalone-runner.md) for stage
requirements, configuration precedence, resource controls, journals, recovery,
and exit codes. Execution checks do not establish scientific convergence.

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
  - toggleable common spectral line markers (hydrogen, helium, metals), optional labels,
    air/vacuum conventions, and positions following model redshift; also available on
    uploaded spectra and parsed wavelength plots ([usage and sources](doc/spectral-line-overlay.md)),
  - quick wavelength zoom presets for each reference line (±150 Å), the optical
    range (3800–7500 Å), and the whole visible spectrum, with vertical scaling
    to the displayed wavelength region,
  - native spectral samples retained in the browser; adaptive overview curves preserve
    peaks/troughs and restore native detail on zoom or pan, with a full-resolution option,
  - physical preview transforms and broadening applied before display reduction,
  - single-model `/spectrum/<path>` and bulk-spectrum `/bulk/spectra/<path>` views,
  - Plotly interactivity with log/linear toggles, redshift/velocity, distance scaling, reddening `E(B-V)`, and resizable plot container,
  - observed overlay support with flux-mode compatibility checks,
  - bulk visibility toggles for final vs continuum traces (without removing traces).
- Global uploads workflow:
  - text/CSV and VOTable files with explicit wavelength, flux, and bandwidth (`bandwidth`, `band_width`, `bandpass_width`, or `filter_width`, optionally suffixed `_A`) columns are automatically imported as absolute-flux photometry; commented text headers and quoted comments are supported,
  - detected photometry is saved as canonical `source.phot` with errors, comments, and enabled flags (default `1`) preserved; the original uploaded file remains in the bundle. VOTable wavelength and bandwidth units are both converted to Å, and declared flux/error units to erg/s/cm²/Å (including Jy). Generic `width` and headerless tables do not trigger automatic photometry detection,
  - upload management page (`/uploads/`),
  - quasi-persistent tokenized uploads under upload root,
  - upload detail page (`/uploads/view/<token>`) with file/format summary, parsed point counts, skipped-point diagnostics, and configured wavelength window display,
  - interactive uploaded-spectrum viewer with redshift/velocity sync, broadening, reddening, distance scaling, axis controls, and a resizable plot area,
  - FITS parsing for common 1D/2D and table-based formats,
  - VOTable, CSV, and plain-text spectrum parsing with named or positional wavelength/flux columns,
  - spectral flux-error bars and per-point uncertainty weighting during single-model and grid fitting,
  - normalized-spectrum safety filter: uploaded points with negative flux are treated as invalid.
- Upload model-grid fitting:
  - async server-side fit job API (`/uploads/fit-grid/...`) with progress polling and result payloads,
  - model discovery is DB-backed only via `model_summary_cache.sqlite` (no direct filesystem crawl during fit),
  - optional `model_name_pattern` filtering (shell-style pattern matching via `fnmatch.fnmatch`),
  - live indication of currently matched model count while editing the pattern,
  - configurable fit bounds (`z`, `sigma`, and in absolute mode also `E(B-V)` plus distance for CMFGEN; equal lower/upper values freeze a parameter and exclude it from the fitted degrees of freedom; TLUSTY absolute fits use free normalization instead of distance),
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
- System and maintenance view:
  - runtime configuration, upload-storage usage, and active background-task counts,
  - explicit model-summary cache checks for missing, stale, or retargeted entries,
  - background refresh/removal actions plus guarded cleanup of current, unavailable, or non-current cache namespaces.
- Read-write model operations:
  - startup-gated model-directory write access (`--read-write`, disabled by default),
  - preview-first creation of a fresh non-SN model from an existing solution using the CMFGEN
    `GAMMAS → GAMMAS_IN` and `*OUT → *_IN` staging conventions,
  - transactional copy into a new destination without merging, overwriting, or carrying restart/diagnostic files;
    cleanup scripts and an allowlisted `obs/` bootstrap are included when available,
  - collision-safe model renaming or moving within the configured root, including cross-filesystem moves,
    with matching summary-cache relocation,
  - previewed, selectively confirmed cleanup of completed-run transient files and top-level symlinks,
    following the active policy in CMFGEN's canonical `com/clean.sh`,
  - lossless editing of allowlisted model control files with diff review, optimistic concurrency checks,
    atomic replacement, checkpoint loading/restoration, recoverable backups, and stale-solution/cache tracking,
  - compact quick editing of commonly changed `VADAT` stellar/wind, clumping, and abundance values plus
    `IN_ITS` iteration controls, while preserving the surrounding control-file text and using the same review path.
  - guarded LTE/hydro workflow preparation: the app creates the input workspace, reports missing or stale
    artifacts, gives copyable terminal commands, and checkpoints/promotes reviewed results, but deliberately
    never starts or supervises CMFGEN processes; read-only monitors match externally launched processes by
    name and working directory and estimate LTE/hydro progress from their output files; domain-aware LTE
    diagnostics combine `OUTLTE`, frequency progress, batch markers, timing, and result freshness, while the
    hydro command preserves interactive output in a parsed `WIND_HYD` log,
  - a separate main-model computation workflow with input guards, the external `batch.sh` command, and
    current/stale `MOD_SUM` result tracking, live CMFGEN and `obs/` CMF_FLUX process statistics, estimated
    `OUTGEN` iteration progress, and CMF_FLUX pass/loop activity; LTE/hydro ends with a guarded handoff to
    this workflow,
  - a latest-run convergence overview built from appended `OUTGEN` iterations, including solver/population,
    luminosity, spectrum-change and timing cards, interactive trends, compact `CORRECTION_SUM` thresholds,
    and grouped scientific warnings without imposing a universal convergence threshold; the same analysis is
    available as the structured parsed view when opening `OUTGEN`,
  - conservative read-only model preflight validation for executable/file usability, required grid and
    iteration controls, selected `RVSIG_COL` dimensions, clumping completeness, CMF_FLUX ranges, and newer
    unpromoted LTE/hydro results; blocking errors and advisory findings link to the relevant editor or file.
- Configurable wavelength window for all displayed spectra:
  - `--lambda-min` / `--lambda-max` bounds applied to both model spectra and uploaded overlays.
- Documentation section with top-nav dropdown populated from `doc/*.md`, rendered as markdown with code highlighting.
- Standalone runner with read-only status by default, explicit execution stages, continuation/fresh-start
  controls, output validation, and recoverable run journals; see [Command-line Runner](#command-line-runner).

### Not yet implemented

- Some CMFGEN output formats still rely on generic/plain text preview instead of dedicated parsers.
- Generic direct-access/binary readers using `_INFO` sidecars.
- Broader scientific cross-file consistency checks beyond the conservative main-workflow preflight.
- Persisting grid-fit jobs/results across Flask process restarts.

## Repository Layout

- `viewer.py`: executable entry point.
- `cmfgen_run.py`: standalone model status, preflight, and execution entry point.
- `MODEL_GRIDS.md`: model-grid preparation, import, conventions, and fitting guide.
- `cmfgen_viewer/`:
  - `app.py`, `cli.py`: app factory and CLI configuration.
  - `runner.py`, `runner_recipe.py`, `runner_status.py`, `runner_output.py`:
    standalone execution, stage recipes, read-only model inspection, and terminal reporting.
  - `views.py`, `view_common.py`: blueprint assembly and shared route helpers.
  - `browser_views.py`, `model_views.py`, `spectrum_views.py`, `upload_views.py`:
    browser, model-summary, spectrum, and upload route groups.
  - `grid_views.py`, `grid_jobs.py`, `grid_fitting.py`, `grid_catalog.py`:
    model-grid APIs, job orchestration, numerical fitting, and grid discovery.
  - `system_views.py`, `cache_jobs.py`, `summary_cache.py`:
    runtime status, explicit cache maintenance jobs, and cached model-summary storage.
  - `model_write_views.py`, `model_staging.py`:
    guarded model-operation routes and non-SN model staging contracts.
  - `model_editor_views.py`, `model_editor.py`, `model_quick_editor.py`:
    allowlisted control-file editing routes, structured quick edits, diff review, backups, and safe persistence.
  - `model_preflight.py`, `model_convergence.py`, `model_run_workflow.py`, `model_runtime.py`:
    pre-run consistency guards, convergence summaries, external-run workflow state, process/progress monitoring,
    and result diagnostics.
  - `browser.py`: directory/file metadata and role classification.
  - `model_metadata.py`, `model_summary.py`: model metadata, named scientific summaries,
    versioned cache payloads, and table presentation. Both model summaries and file previews
    use the structured `MOD_SUM` reader in `parsers/mod_sum.py`.
  - `spectrum_io.py`, `spectrum_transforms.py`, `spectrum_fitting.py`, `spectrum_plots.py`:
    spectrum discovery/parsing, physical transformations, numerical fitting, and Plotly presentation.
    `spectrum_constants.py` and `spectrum_options.py` hold shared units/defaults and option validation;
    `final_spectrum.py` retains compatibility imports for existing callers.
  - `control_files.py`: shared lossless control-row tokenization for editing, metadata, and validation.
  - `upload_service.py`: upload bundle creation with failure rollback and atomic manifest persistence.
  - `job_store.py`: shared thread-safe job lifecycle; each app owns separate grid and cache job stores
    through `app.extensions["cmfgen_jobs"]`. Background workers receive their store explicitly.
  - `live_events.py`, `live_event_views.py`: application-local job notifications and a shared
    server-sent event endpoint for task navigation and model runtime panels.
  - `grid_config.py`, `hr_diagram.py`: grid definitions and reference HR-diagram data without Flask dependencies.
  - `observed_spectrum.py`: uploaded observed-spectrum parsing and upload-manifest lifecycle.
  - `syntax.py`: syntax highlighting and CMFGEN input lexer.
  - `parsers/`: parsed-view implementations for core and diagnostic file families.
  - `templates/`, `static/`: Jinja templates, client-side JS, and CSS.
- `doc/`: markdown docs surfaced in the Documentation menu.
- `CMFGEN_*_investigation_*.txt`: source investigation logs.

## Notes

Task navigation and model runtime panels share one `/tasks/events` connection per visible
page. Each connection starts with current snapshots, including after a reload or reconnect.
Job-store changes push task updates, coalesced to at most once per second. While a runtime
panel is open, the server checks its external processes and output files every five seconds
and pushes changed status, progress, and completion diagnostics. Linux `/proc` remains the
source of process detection, including runs started outside the viewer. Idle task streams
wait for notifications and send only a keepalive every 15 seconds.

Hidden pages close the stream and resynchronize when visible. The existing JSON status
endpoints provide a polling fallback if SSE is unavailable. Individual fit/summary job pages
retain their own job-specific progress polling. No new dependencies are needed. As with the
in-memory job stores, notification delivery assumes a single server process; deploying
multiple worker processes would require a shared job store and notification service.

Spectrum pages share Jinja components for axes, zoom, line settings, transformations,
the plot canvas, and JSON configuration (`templates/_spectrum_*.html`).
`static/spectrum_controls.js` initializes plots and binds axes, sampling, line overlays,
and resizing, including parsed file previews. `static/spectrum_viewer.js` adds shared
transformation validation, redshift/velocity synchronization, reset, and trace updates.
Numerical code lives in `static/spectrum_transforms.js`. The single-model, bulk, and
upload scripts supply trace policies and handle their own fitting, visibility toggles,
and grid-search overlays. Layout and common control behavior should be changed in the
shared components rather than copied into a page adapter.

- The UI is optimized for local analysis workflows and iterative parser development.
- Large-file parsing is guarded (`MAX_PARSE_FILE_BYTES`) to avoid heavy accidental loads.
- Documentation pages are generated from repository markdown; update files in `doc/` to extend in-app docs.
- Upload grid fitting requires a populated summary cache database (`model_summary_cache.sqlite`). Visiting a model folder that contains both `VADAT` and `MOD_SUM` automatically adds it to the cache, or refreshes its entry when either file has changed. The folder-level `Summarize` workflow remains available for adding multiple selected models at once; cache maintenance refreshes stale entries already known to the cache but does not discover new models.
- Folder-level `Summarize` starts a background job and redirects immediately to
  a bookmarkable result page. It shows progress, the current folder, elapsed
  time, updated/reused/skipped/failed counts, and per-folder diagnostics. The
  Background Tasks menu links back to running summaries; the Models page lists
  recent summary jobs, including completed, canceled, and failed attempts. Cancellation finishes
  the current folder; successful summaries remain committed. Retry processes
  only failed and unfinished folders, with a link back to the previous attempt.
  Unchanged valid cache entries are reused unless **Force summary refresh** is
  selected. Bulk jobs reuse one SQLite connection and commit each model rather
  than keeping a long transaction open. A systemic database failure stops the
  job; individual model failures do not abort the remaining selection.
- Bulk summarization and cache maintenance share one atomic job slot, and cache
  deletion is blocked while either runs. Job state/results are process-local,
  retained for up to six hours/16 recent cache jobs, and lost on server restart;
  the summaries already written to SQLite are unaffected. This is intended for
  a single web process, like the existing in-memory grid-job infrastructure.
  Multi-process coordination and restart recovery would require durable job
  bookkeeping and a separate worker. JavaScript polls only progress counters;
  without JavaScript, refresh the result page manually.
- The summary cache stores versioned, named numeric fields, independently of table column order.
  Existing positional summaries are migrated automatically using their historical layout. Migration
  preserves their already-rounded values; refreshing a model summary reads full precision from its source files.
- Optional app-wide HTTP Basic Auth can be enabled from CLI using `--auth-user` and `--auth-password`.
- Uploaded spectra can be removed individually or all at once from the Uploads page. “Delete All” only removes valid viewer-managed bundles and leaves unrelated files in the configured upload directory untouched.
- The upload directory uses the viewer's token/manifest bundle layout; loose spectrum files placed directly in that directory are left untouched and are not automatically imported into the Uploads page.

## Validation

Run the automated test suite and bytecode compilation checks from the repository root:

```bash
python3 -m pytest -q
python3 -m compileall cmfgen_viewer viewer.py
```

When Node.js is available, pytest also compares the shared browser reddening and broadening calculations
against the Python fitting implementation. The optional browser smoke check requires Chromium, Node.js,
and the Python `plotly` package:

```bash
CMFGEN_BROWSER_TESTS=1 python3 -m pytest -q -s tests/test_browser_smoke.py
```

It starts an isolated local server and exercises parsed-file pages, documentation links, all three spectrum
plots, redshift/reset, axes, resizing, and bulk visibility. It serves real Plotly locally and omits external
Bootstrap/Font Awesome assets, so it checks application behavior without depending on CDN access.
