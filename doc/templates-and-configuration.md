# Templates and configuration

## Installation and configuration

Supply the CMFGEN installation and atomic-data roots when starting the viewer:

```bash
python viewer.py --dir /path/to/models --read-write \
  --cmfgen-root /path/to/cur_cmf --atomic-root /path/to/atomic
```

The same root options are available to `cmfgen_run.py`. The viewer's JSON/TOML configuration uses `cmfgen_root`, `atomic_root`, and `template_root`. The **System** page shows effective installation settings and their sources.

Installation and thread defaults are resolved individually, highest priority first:

1. Explicit command-line options (and viewer JSON/TOML settings).
2. Nonempty `CMFDIST`, `ATOMIC`, and `OMP_NUM_THREADS` environment variables.
3. `.cmfgenrc` in the startup working directory.
4. `~/.cmfgenrc`.
5. Inherited native thread settings; there are no built-in installation paths.

A `.cmfgenrc` uses plain entries without a section header:

```ini
cmfgen_root = ~/CMFGEN2023/cur_cmf
atomic_root = ~/CMFGEN2023/atomic
# Optional positive thread count:
nthreads = 1
# Optional viewer defaults:
read_write = true
# Opt in to full-size recovery files (default: false):
keep_large_files = false
dir = ~/models
lambda_min = 800
lambda_max = 250000
host = 127.0.0.1
port = 5567
all = false
fit_pool_size = 0
# upload_dir = ~/cmfgen-uploads
# template_root = ~/cmfgen-templates
# debug = false
```

Keys are case-insensitive, and hyphens and underscores are interchangeable (`lambda-min` and `lambda_min`). `CMFDIST`, `ATOMIC`, and `threads` are also accepted configuration keys. Use `#` comments and quote paths containing spaces. `~` expands; relative configuration paths are resolved from the configuration file's directory. CLI/environment paths are relative to the startup directory. Configuration files are parsed, never sourced: shell commands, `export`, and `$VARIABLE` substitution are unsupported. Invalid or duplicate settings produce an error.

Viewer options follow **CLI flags > viewer JSON/TOML configuration > startup-directory `.cmfgenrc` > `~/.cmfgenrc` > built-in defaults**. The supported viewer settings are:

| Settings | Meaning |
| --- | --- |
| `dir` / `basepath` | Model tree to browse |
| `host`, `port` | Viewer bind address and port |
| `lambda_min`, `lambda_max` | Positive wavelength limits in Å, with minimum below maximum |
| `read_write` | Allow model-directory modifications; defaults to `false` |
| `keep_large_files` | Keep recovery artifacts above 2 MiB and full diagnostic logs; defaults to `false` |
| `all` / `show_all` | Show hidden files and directories |
| `upload_dir` / `upload_root` | Persistent upload storage |
| `fit_pool_size` | Grid-fitting worker limit; `0` selects automatically |
| `template_root` | Explicit workflow template directory |
| `debug` | Flask debug mode |
| `secret` | Flask session signing key |
| `auth_user`, `auth_password`, `auth_realm` | HTTP Basic Auth credentials and realm |

Boolean values `true`/`false`, `yes`/`no`, `on`/`off`, and `1`/`0` are accepted case-insensitively. `--read-only` and `--read-write` override configured access defaults. Viewer options apply at viewer startup; the standalone runner accepts them in the shared file and uses its own installation/thread settings when executing stages. Installation roots and threads keep the environment-variable precedence described above. The **System** page shows effective access and its source.


Viewer settings support preflight checks and configure UI-launched runner jobs. They are not injected into commands you run separately in a terminal. Make sure your shell setup points to the same installation and atomic tree. The runner uses its resolved settings directly when launching native executables.

Workflow-created model/workspace directories, checkpoints, run journals, logs, and copied or published products are readable by all users: directories normally use `0755`, regular files `0644`, and executable files `0755`. Existing write permissions are retained. Native runner children use umask `022`; the viewer does not change its process-wide umask. Symbolic-link targets are left untouched.

## Activity and write protection

Edits, model copying/moving, cleanup, LTE preparation, and promotion require an idle model with available process visibility. Recognized CMFGEN, CMF_FLUX, LTE, hydro, and batch processes in the model tree block writes; unknown visibility also blocks them. Detection uses `psutil` on Linux and macOS.

Viewer and runner writers share the advisory `.cmfgen-viewer-write.lock` across the model and its workspaces. The file remains after use; its presence alone does not indicate a running calculation. Do not remove it while a writer may hold it. External scripts do not honor this lock, and jobs on another host or hidden in another process namespace cannot be reliably detected. Run calculations and workspace edits separately on the same host.

## Workflow previews

Use **Preview workflow**, **Preview main workflow**, or **Preview spectra only** on the corresponding workflow page. Previews are read-only: they do not prepare a workspace or start a calculation. They show stage dependencies, commands, inputs/outputs, selected templates, executable checks, and completion criteria. Errors block readiness; warnings identify checks that remain incomplete or need review.

Preflight checks required files, dimensions and controls, workspace permissions, configured executables, and available disk space. Less than 100 MiB free blocks readiness; less than 1 GiB produces a warning. These thresholds do not estimate a model's full scratch requirements. The runner reads atomic declarations as data and never executes shell launchers. Missing shell scripts, interpreter permissions, and sourced setup paths are advisory terminal-only diagnostics and do not block native readiness. Missing core hydrogen/helium targets are errors; other missing ion targets are warnings.

Previews are also available as JSON by adding `?format=json` to the plan URL. In read-write mode, the routes are:

```text
/model-actions/plan/lte-hydro/<model-relative-path>
/model-actions/plan/main/<model-relative-path>
/model-actions/plan/flux/<model-relative-path>
```

Plans are snapshots; refresh them after changing inputs or running a calculation. Workflow result pages refresh automatically when a monitored run stops, unless unsaved edits defer the reload. Passing preflight or completing a process does not establish scientific acceptance.

## Template layout

The viewer and standalone runner share one resolver for reusable setup files.
Template collections mirror a model folder directly:

```text
templates/
  clean.sh
  batch.sh                   # optional local model-copy setup
  IN_ITS                     # optional local model-copy controls
  lte/
    GRID_PARAMS
    HYDRO_PARAMS
    ltebat.sh
  obs/
    batobs.sh                # optional local observer setup
    CMF_FLUX_PARAM_INIT
    IN_FILE
```

Use `--template-root /path/to/templates` with either `viewer.py` or
`cmfgen_run.py`. The viewer's JSON/TOML config also accepts `template_root`.
The path names the collection root, not its `lte/` or `obs/` subdirectory.

## Resolution

Each setup file is selected independently, in this order:

1. The relevant path in the source model.
2. The explicit template root, when configured.
3. `templates/` in the model directory and its ancestors, nearest first.
4. `cmfgen_viewer/data/templates/` shipped with the Python package.

For example, `lte/GRID_PARAMS` in an explicit collection can override the
packaged grid while the packaged HYDRO_PARAMS supplies the missing hydro file.
There is no lookup through the previous `examples/` or `lte2/` layouts.
Preparation pages and CLI plans show the selected path and origin for each file.
Runner plans recheck both selection and contents under the model write guard;
changed sources require rebuilding the plan.

## Packaged defaults

The initial bundled set contains `clean.sh` and these LTE files:

- `lte/GRID_PARAMS`: the supplied 25-temperature, 37-density grid.
- `lte/HYDRO_PARAMS`: the supplied ostar hydro starting controls.
- `lte/ltebat.sh`: a reviewed portable shell recipe requiring `CMFDIST`
  and `ATOMIC`, assigning links through the parent model's `batch.sh ass`, then
  running `main_lte.exe` into `ltebat.log`.

The standalone runner launches the native executable directly; it does not
require the LTE or parent shell launchers. Its atomic declarations are validated
as data independently of shell setup.
The packaged cleanup script retains main products and checkpoints; the runner's
`cleanup` stage also retains a recovery archive under the selected size policy and is preferable for that use.
No script is executed during preparation or model copying.

These are starting controls, not a universal physical model. LTE preparation
initializes the supported HYDRO_PARAMS controls from VADAT. Review the grid,
composition-related defaults, and the connection-radius estimate before running.
Existing workspaces and local template files are never rewritten by preparation.

## Model copying and observer setup

Copying a solution continues to obtain VADAT, MODEL_SPEC, GAMMAS, and solution
outputs from the source model. Templates cannot replace those physical inputs.
Missing reusable root scripts and controls can be supplied by the resolver;
missing observer setup files use `obs/`. Observer MODEL_SPEC, when present,
is copied only from the source model. Copy plans show each external template's
origin and retain its permissions. A new copy does not contain an LTE workspace:
prepare it explicitly after configuring the copied model.

The LTE set, cleanup script, and ostar atomic link defaults are bundled.
Iteration settings, wavelength coverage, and observer control files
come from the source model or local templates. `obs/` is reserved
for adding reviewed packaged observer defaults later.

The historical preparation notes, shell recipe, and sample VADAT are retained in
`doc/workflow-reference/` as reference material; they are not template inputs.

## Native atomic link declarations

`atomic_links.json` is a data-only map with `base`, `ions`, and `obs` groups.
Each group maps a destination filename to a path relative to the configured
atomic-data root. An explicit model or template manifest replaces shell-derived
atomic setup; omitted groups are empty. For example:

```json
{"base": {"HYD_L_DATA": "HYD/I/5dec96/hyd_l_data.dat"}, "ions": {}, "obs": {}}
```

This abbreviated example is not a complete production atomic dataset. Use the
packaged manifest as a starting point, then retain the declarations required by
your model and chosen atomic-data versions. Without an explicit manifest, the
runner reads literal atomic links from existing `batch.sh`, `batch_ins.sh`, and
(for spectra) `obs/batobs.sh`. Missing or unusable declarations fall back to the
corresponding packaged ostar group. Other shell text is never executed or used
to select executable paths, environment, or thread counts.

Manifest sources are included in plan snapshots and rechecked before launch.
Targets must stay within the configured atomic root; missing required atomic
data, duplicate destinations, and unsafe workspace links remain blockers.
Changing terminal launcher files alone does not invalidate LTE output freshness.

## Command-line model maintenance

`cmfgen_model.py` exposes the same model-maintenance operations as the UI without starting a web server. It does not require `cmfgen_root` or `atomic_root`. An explicit mutating subcommand authorizes writes; the viewer's `read_write` setting does not enable or disable this standalone tool. Model activity checks and cooperative write locks still apply. `show` and `get` are read-only. Mutating subcommands support `--plan` for read-only inspection; every subcommand supports `--json` for machine-readable reports.

```bash
python3 cmfgen_model.py show /path/to/model
python3 cmfgen_model.py show /path/to/model --file IN_ITS --json
luminosity=$(python3 cmfgen_model.py get /path/to/model LSTAR)
python3 cmfgen_model.py get /path/to/model NUM_ITS --file IN_ITS
python3 cmfgen_model.py copy /path/to/model /path/to/new_model --plan
python3 cmfgen_model.py cleanup /path/to/model --plan
python3 cmfgen_model.py cleanup /path/to/model --lte --plan
python3 cmfgen_model.py cleanup /path/to/model --full --plan
python3 cmfgen_model.py set /path/to/model LSTAR=4e5 --keep-teff-logg --plan
python3 cmfgen_model.py set /path/to/model MDOT=2e-6 VINF=1800 --plan
python3 cmfgen_model.py set /path/to/model --file IN_ITS NUM_ITS=10
```

Omit `--plan` to apply a planned operation. Plans describe the current files; each executing invocation validates its own inputs again. Exit status is `0` for success, a ready plan, or an unchanged operation; `2` for invalid inputs or blocked preflight; `1` for execution failure; and `130` for interruption. Operational errors are reported as JSON when `--json` is selected; argument syntax errors use argparse's normal error output.

**Copy** creates a new directory with `*OUT` copied to `*_IN`, `GAMMAS` copied to `GAMMAS_IN`, and the UI's selected controls and observer setup. Original files are preserved. Binary restart files, old calculated products, archives, and the LTE workspace are omitted. The destination parent must already exist, and the destination cannot already exist or lie inside the source model. `--template-root` overrides the shared `.cmfgenrc` template setting. Templates are resolved through the same source/model-tree/package search as the UI. No shell script is run.

**Cleanup** uses the runner's conservative top-level candidate policy by default, retaining its normal run journal. Repeat `--file NAME` to select specific main-folder candidates. Top-level atomic links are cleanup candidates, but their targets are left untouched. `--lte` instead applies the LTE-workspace policy, preserving regular controls, population inputs, handoff products, and retained diagnostics, with recovery files under `.cmfgen-viewer-backups/lte-cleanup/`. LTE cleanup also removes all top-level symbolic links, including broken links and directory links, without following their targets; ordinary cleanup archives the links themselves. `--full` applies the same link-removal rule in the main, LTE, and observer workspaces. `--file` and `--lte` cannot be combined. An empty valid selection is an unchanged operation. Both modes use `.cmfgenrc` `keep_large_files`, defaulting to compact storage; explicit `--keep-large-files` or `--no-keep-large-files` overrides it. Ordinary cleanup cleans working files, not old recovery archives; use **History** for selective archive housekeeping or `--full` as described below.

`cleanup MODEL --full` performs permanent cleanup across the main folder, `lte/`, and `obs/`, using each workspace's existing temporary-file policy. It additionally removes `.cmfgen-runs/` and `.cmfgen-viewer-backups/` in those workspaces, including editor checkpoints, and deletes this model's detached runner job records. Shared `.cmfgen-runner-jobs/` stores are discovered at the model and its ancestors; only records whose request identifies this model or its LTE/observer workspace are eligible. Other models' records are preserved, and records with unreadable ownership metadata are left in place with a warning. Active or uncertain matching jobs block full cleanup.

**Cleanup Model** in the UI provides the same **Full cleanup** checkbox. Changing it refreshes the preview without deleting anything. Full mode removes the entire listed set after confirmation; an expired preview, changed target inventory, or different model invalidates the reviewed action. Ordinary UI cleanup retains per-file selection.

Full cleanup creates no replacement archive or run journal, regardless of the `keep_large_files` default. Its plan lists all temporary-file, archive, and job-record targets and their sizes before execution. It cannot be combined with `--lte`, `--file`, or explicit recovery-retention flags. Use `--full --plan` first, then omit `--plan` to permanently delete those targets. Current input controls, scientific products and live continuation checkpoints are retained according to the usual cleanup policy, as are the stale-solution marker and cooperative lock files. Symbolic-link targets are never traversed. Execution requires an idle model, revalidates the target inventory under the model write guard, and reports any partial deletion failures. No automatic rollback is available after a full cleanup.

**Get** reads one explicit control, for example `get MODEL LSTAR` or `get MODEL NUM_ITS --file IN_ITS`. Keys are case-insensitive. It accepts any uniquely present control in the selected file, including controls not exposed for quick editing, such as `TEFF`. Successful plain output is exactly the value followed by a newline: no label, unit, warning, or status line. The original notation is preserved (`1.0D5`, `F`, or comma-separated values); implicit native defaults are not evaluated. Missing, empty, or repeated controls return exit status `2`, with a diagnostic on stderr and empty stdout, so shell substitution cannot mistake an error message for a value. `--json` instead returns the normal structured value/error report on stdout. Reading requires no idle-model check and creates no checkpoints.

**Set** accepts one or more `KEY=VALUE` assignments in a single quick-editable file: `VADAT` by default, or `--file IN_ITS`. Use **show** to discover available keys. Values use the same validation, comment/newline preservation, concurrency checks, and checkpoint creation as the UI. Unsupported or duplicate keys are rejected. Ordinary numeric and Fortran `D` notation are accepted where supported by the control. The plan shows a unified diff; execution saves the same reviewed contents and reports its backup path. A no-op creates no backup.

`--keep-teff-logg` requires an explicit positive `LSTAR` assignment in `VADAT`. For luminosity ratio `f = L_new / L_old`, it scales `RSTAR` by `sqrt(f)` and `MASS` by `f`, leaving `TEFF` and `LOGG` unchanged, exactly as the UI does. Luminosity is in solar units. Do not combine this mode with explicit `RSTAR`, `MASS`, or `LOGG` assignments. Existing mass/gravity inconsistencies are preserved and reported by the shared scaling checks.

Parameter editing marks the solution stale as appropriate. It does not regenerate the LTE/hydro structure, change existing population estimates or restart checkpoints, launch a calculation, or guarantee scientific suitability. Choose the subsequent preparation/fresh-start/continuation workflow explicitly, just as after editing in the UI.
