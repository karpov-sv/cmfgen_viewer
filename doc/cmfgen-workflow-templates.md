# Workflow templates

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
