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

- absolute observed spectra are fitted against TLUSTY UV/optical/SED spectra with a free multiplicative normalization (distance is ignored);
- absolute photometry requires every enabled band to be covered, preventing partial UV/optical segments from competing with full-range TLUSTY SEDs;
- normalized observed spectra are fitted against TLUSTY spectra normalized by matched continuum counterparts.

## Local BOSZ Import

Convert a downloaded BOSZ 2024 resampled subset into the same CSV/NPZ storage
format, without downloading or resampling anything:

```bash
python3 scripts/import_bosz_spectra.py ~/tmp/grids/bosz
```

The source must contain `bosz2024_wave_r2000.txt` and matching
`bosz2024_*_r2000_resam.txt.gz` files (subdirectories are supported). Use
`--resolution N` for another downloaded resolution and `--output-dir PATH`
to change the default `data/bosz/` destination.
Conversion uses four workers by default (`--workers N` to change this).

The importer writes `models.csv`, `manifest.json`, and one compressed NPZ per
model. It preserves both the flux and continuum columns, adds their ratio for
normalized fitting, and retains the published wavelength samples. Flux and
continuum remain Eddington H-lambda in erg/s/cm²/Å, matching the TLUSTY storage
convention; multiply by 4π when a physical surface flux is required.
Atmosphere family (`ap`, `mp`, `ms`), metallicity, alpha/carbon abundance,
microturbulence, and the existing instrumental resolving power are recorded
in the catalogue. Full model names distinguish overlapping atmosphere families.
Source checksums are retained, but filenames alone do not identify whether a
download contains the publisher's corrected revision.

An R=2000 import remains an R=2000 product, even though its sampling is finer
than one resolution element. It is not a replacement for detailed TLUSTY line
spectra. The imported catalogue remains separate from TLUSTY.

In the upload viewer, click **Find Best BOSZ Model** to search the imported grid.
Normalized spectra use the stored flux/continuum ratio; absolute spectra and
photometry use a free normalization per model, with no distance parameter.
Photometry candidates must cover every enabled band. Model-name patterns can
select a subset, for example `*_ap_*` for ATLAS9 or `*_t8000_*` for 8000 K.
The fit uses all native BOSZ samples. Its Gaussian broadening parameter is
**additional** broadening, not the total instrumental width: an R=2000 input
grid cannot fit narrower instrumental profiles by sharpening itself.
Progress, cancellation, best-fit overlays, and parameter confidence summaries
work as for the other grids. Results retain the atmosphere family and native
resolving power. The default catalogue is `data/bosz/`; an application embedding
the viewer can override `app.config["CMFGEN_VIEWER"]["bosz_root"]`.

Existing output directories are never overwritten. The importer publishes the
new directory only after all files validate and convert successfully; failed
imports clean up their temporary output. Original downloads are never changed.
Generated data are gitignored.
Negative source fluxes are masked with NaN in fitting arrays, with their
original values retained in `raw_flux_lambda_cgs`. Non-positive continua are
excluded from normalization. Per-model mask counts are recorded, and catalogue
wavelength coverage excludes unusable edge samples. Non-finite source values
or malformed arrays stop the import rather than silently dropping a model.

## Local PHOENIX R10000 Import

```bash
python3 scripts/import_phoenix_spectra.py ~/tmp/grids/R10000FITS
```

Reads local `PHOENIX-ACES-AGSS-COND-2011_R10000FITS_Z*.zip` archives without
extracting or modifying them. Output is `data/phoenix/` by default; use
`--output-dir PATH` or `--workers N` (default four) as needed. Existing output
is never overwritten; publication is atomic, with failed staging data removed.
Generated CSV, manifest, and NPZ data are gitignored.

The installed subset has 7,559 spectra: Teff 2300–12000 K, log g 0–6,
[M/H] −4 to +1, and [alpha/M] = 0 (not every parameter combination exists).
Each spectrum retains all 212,027 samples, spanning approximately 3000–25000 Å.
The logarithmic sampling is ten points per resolution element, **not R=100000**:
the actual product is broadened to R=10000, about 30 km/s FWHM.

This product needs explicit convention handling, following
[Husser et al. (2013)](https://arxiv.org/abs/1303.5632):

- Wavelengths are `exp(CRVAL1 + (pixel - CRPIX1)*CDELT1)` in Å, using
  one-based pixels and CRPIX1 = 1 when absent. The published **vacuum** convention
  overrides these archives' misleading `AWAV-LOG` header; no air-to-vacuum shift
  is applied. The source header and override are recorded in provenance.
- Surface F-lambda per cm is multiplied by `1e-8 / (4*pi)` to store Eddington
  H-lambda per Å, matching the existing TLUSTY/BOSZ convention.
- The 51 `INTERPOL` spectra remain available and are labelled in fit results.
  Missing BUNIT on these files uses the published product convention and is
  flagged. Fractional microturbulence is retained as a **derived property**,
  not treated as an independent fit axis or rounded to integer km/s.
- Six spectra contain 144 negative samples in interior wavelength intervals.
  Their data are retained unchanged apart from unit conversion, but those six
  whole models are excluded from fitting; corrupt intervals are not bridged.
  This leaves **7,553 eligible fitting models**. Source/member SHA-256 checksums
  and per-model quality flags are recorded in `manifest.json` and `models.csv`.

Use **Find Best PHOENIX Model** on an absolute-flux spectrum or photometry upload.
There are no supplied continua, so normalized-spectrum fitting is disabled in
the UI and rejected by the server. Absolute fits solve a free normalization;
distance is not fitted. Photometry requires every enabled band to be covered,
including any allowed redshift range (optical and JHKs can fit, UV/WISE cannot).
The Gaussian broadening parameter adds to native broadening; use observed
spectra at comparable or lower resolution and on a compatible vacuum axis.
Progress, cancellation, confidence summaries, and best-fit overlays use the
shared grid workflow. Model-name patterns such as `lte06000*` restrict searches.
Full-grid fits use more CPU and storage than BOSZ; the installed NPZ grid is
about 20.5 GB. Embedders can override
`app.config["CMFGEN_VIEWER"]["phoenix_root"]`.

### Fitting performance

NPZ grid fits keep NumPy arrays in their existing F-lambda/normalized convention,
without converting through Jy or Python lists. Uniform logarithmic grids are
cropped to the enabled observations with margins for the full redshift bounds,
Gaussian kernel, and photometric band edges. Native sampling is retained;
nonuniform grids keep their original convolution lattice.

CMFGEN spectra use validated bulk numeric parsing, with the legacy parser as a
fallback for missing-E Fortran exponents and punctuation. Grid fits request
read-only NumPy arrays directly; viewer callers continue to receive lists.
Nonuniform-grid broadening prepares its native-size logarithmic lattice and
interpolation mappings once per fit and reuses them across redshift, extinction,
distance, and width trials. The native axis, transform order, discrete Gaussian
kernel, and edge extension are retained. All caches remain memory-only.

Fits cache reddening-law values by redshift. Unbroadened point-spectrum trials
transform only the model samples needed for interpolation (reddening still
precedes interpolation); photometry continues to integrate full bands. Wide
Gaussian kernels use FFT convolution with the same discrete four-sigma kernel
and nearest-edge extension as the direct implementation. Small kernels use
direct convolution. These optimizations do not modify imported spectra or
introduce additional downsampling for spectral fits; the legacy TLUSTY point
cap is unchanged.

Unbroadened absolute photometry fits prepare compact band quadrature, preserving
native line fluxes and interpolated band edges. Logarithmic grouping starts at
approximately R=300 and refines until a conservative extinction-averaging bound
limits relative band-flux error to 0.01% over the fitted E(B-V) range. Signed
fluxes or bands that cannot meet the bound retain native quadrature. Redshift
and broadening remain available; trials with nonzero smoothing use native
spectra. Band integration uses sorted slices rather than scanning the whole
spectrum per band. Final scores and the zero-broadening comparison use native
integration. Absolute CMFGEN grid fits skip loading the unused continuum
and convert Jy to F-lambda directly in NumPy. Fixing redshift and broadening
to zero also avoids repeating the same extinction/distance optimization stage.

The default free-broadening seed starts above the no-smoothing threshold, uses a 1% relative
finite-difference step, and explicitly checks the zero-width boundary. Unlike
the former zero seed, this lets absolute fits explore nonzero widths. Results
and iteration counts can therefore change; not every free-parameter fit gets
the same speedup. A narrow model-name pattern remains useful for exploratory
searches before evaluating thousands of atmospheres.

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

### Not yet implemented

- Some CMFGEN output formats still rely on generic/plain text preview instead of dedicated parsers.
- Generic direct-access/binary readers using `_INFO` sidecars.
- Broader scientific cross-file consistency checks beyond the conservative main-workflow preflight.
- Persisting grid-fit jobs/results across Flask process restarts.

## Repository Layout

- `viewer.py`: executable entry point.
- `cmfgen_viewer/`:
  - `app.py`, `cli.py`: app factory and CLI configuration.
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
  - `grid_config.py`, `hr_diagram.py`: grid definitions and reference HR-diagram data without Flask dependencies.
  - `observed_spectrum.py`: uploaded observed-spectrum parsing and upload-manifest lifecycle.
  - `syntax.py`: syntax highlighting and CMFGEN input lexer.
  - `parsers/`: parsed-view implementations for core and diagnostic file families.
  - `templates/`, `static/`: Jinja templates, client-side JS, and CSS.
- `doc/`: markdown docs surfaced in the Documentation menu.
- `CMFGEN_*_investigation_*.txt`: source investigation logs.

## Notes

Spectrum pages pass configuration through JSON to static JavaScript. Shared numerical code lives in
`static/spectrum_transforms.js`, plot controls in `static/spectrum_controls.js`, and page-specific
behavior in the single-model, bulk, upload, photometry-editor, and grid-search scripts.

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
