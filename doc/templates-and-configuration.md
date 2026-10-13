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
```

Keys are case-insensitive. `CMFDIST`, `ATOMIC`, and `threads` are also accepted configuration keys. Use `#` comments and quote paths containing spaces. `~` expands; relative configuration paths are resolved from the configuration file's directory. CLI/environment paths are relative to the startup directory. Configuration files are parsed, never sourced: shell commands, `export`, and `$VARIABLE` substitution are unsupported. Invalid or duplicate settings produce an error.

Viewer settings support preflight checks and configure UI-launched runner jobs. They are not injected into commands you run separately in a terminal. Make sure your shell setup points to the same installation and atomic tree. The runner uses its resolved settings directly when launching native executables.

## Activity and write protection

Edits, model copying/moving, cleanup, LTE preparation, and promotion require an idle model with available process visibility. Recognized CMFGEN, CMF_FLUX, LTE, hydro, and batch processes in the model tree block writes; unknown visibility also blocks them. Detection uses `psutil` on Linux and macOS.

Viewer and runner writers share the advisory `.cmfgen-viewer-write.lock` across the model and its workspaces. The file remains after use; its presence alone does not indicate a running calculation. Do not remove it while a writer may hold it. External scripts do not honor this lock, and jobs on another host or hidden in another process namespace cannot be reliably detected. Run calculations and workspace edits separately on the same host.

## Workflow previews

Use **Preview workflow**, **Preview main workflow**, or **Preview spectra only** on the corresponding workflow page. Previews are read-only: they do not prepare a workspace or start a calculation. They show stage dependencies, commands, inputs/outputs, selected templates, executable checks, and completion criteria. Errors block readiness; warnings identify checks that remain incomplete or need review.

Preflight checks required files, dimensions and controls, workspace permissions, configured executables, and available disk space. Less than 100 MiB free blocks readiness; less than 1 GiB produces a warning. These thresholds do not estimate a model's full scratch requirements. Literal atomic links and script includes can be checked, but shell substitutions and dynamic setup cannot be fully verified without execution. Missing core hydrogen/helium targets are errors; other missing ion targets are warnings.

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

The standalone runner recognizes the packaged LTE recipe and launches the
native executable directly; it does not execute the shell script. Parent model
scripts and atomic-link manifests still have to pass its existing recipe review.
The packaged cleanup script retains main products and checkpoints; the runner's
`cleanup` stage also retains a recovery archive and is preferable for that use.
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

Only the LTE set and cleanup script are bundled initially. Model-specific atomic
link scripts, iteration settings, wavelength coverage, and observer support files
come from the source model or reviewed local templates. `obs/` is reserved
for adding reviewed packaged observer defaults later.

The historical preparation notes, shell recipe, and sample VADAT are retained in
`doc/workflow-reference/` as reference material; they are not template inputs.
