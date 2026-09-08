# Workflow Safety and Dry-Run Plans

The viewer supports stage-specific preflight and read-only workflow plans. It does **not** launch, stop, supervise, or automatically advance calculations. Execution remains external to the app, using existing terminal commands or the separate [standalone Python runner](cmfgen-standalone-runner.md).

## Active-run guards

Control edits (including quick editors), model cloning, moving, cleanup, LTE preparation, and output promotion refuse to proceed when a recognized CMFGEN, CMF_FLUX, LTE, hydro, or batch process is visible in the model tree. Unknown process visibility also blocks mutation. Fresh output timestamps no longer permit LTE/hydro handoffs while a stage is active.

Viewer writers share an advisory lock, `.cmfgen-viewer-write.lock`, across the model and its `lte/` and `obs/` workspaces. The lock is acquired without waiting, and process activity is checked again after acquisition. The file remains after use; its presence alone does not mean a calculation or write is active. Do not delete it while a viewer writer might hold it. Symlinked or hard-linked lock files are refused.

This is cooperative protection, not a process supervisor. External scripts do not honor the viewer lock and can start after an activity check. Detection relies on recognizable command names and Linux `/proc` visibility; jobs hidden by another host or PID namespace cannot be reliably excluded. Do not mutate a shared model from multiple hosts or launch an external calculation concurrently with viewer edits. Non-POSIX locking or unavailable process visibility causes writes to fail closed.

## Stage preflight

Main, LTE, hydro, and observer-spectrum stages check their own required nonempty inputs, workspace permissions, free disk space, and configured executable. Script entry points must be executable; direct shebang interpreters are checked too. LTE validates unique controls, finite `TEFF`/`LOGG`, positive `TEFF`, boolean `CHK_NG`, and integer dimensions with `NP = ND + NC`.

Literal sourced scripts and atomic-link declarations are inspected without executing any shell. Resolved missing core hydrogen/helium targets are errors; other missing ion links are warnings because not every declared ion is necessarily enabled. Dynamic targets, shell-selected interpreters, and absent environment configuration remain explicit warnings, not verified dependencies. This does not validate the scientific consistency of the full atomic dataset or every population/restart file. Flux checks conventional parent `MODEL` and `RVTJ` products, but scientific acceptance of that solution remains a manual prerequisite.

For more useful checks, supply the roots used by your external shell:

```bash
python viewer.py --dir /path/to/models --read-write \
  --cmfgen-root /path/to/cur_cmf --atomic-root /path/to/atomic
```

The JSON/TOML configuration keys and command-line options are `cmfgen_root` / `--cmfgen-root` and `atomic_root` / `--atomic-root`. When these are omitted, viewer startup uses the same fallback chain as the standalone runner: nonempty `CMFDIST`, `ATOMIC`, and `OMP_NUM_THREADS` environment variables, then `.cmfgenrc` in the startup working directory, then `~/.cmfgenrc`. The System page shows each effective value and its source. Viewer CLI/JSON/TOML settings have highest priority. These settings are **only checked**, not injected into terminal commands. Sourced shell setup may override them: ensure they match the installation and atomic tree actually used by the scripts. A configured missing/non-executable program blocks readiness; an unconfigured installation produces an explicit warning with configuration guidance.

Less than 100 MiB free is a blocker; less than 1 GiB is a warning. These are basic safeguards, not estimates of CMFGEN scratch requirements. Completed LTE/hydro outputs can still be reviewed and promoted if an executable has since become unavailable; rerunning that stage remains blocked.

## Previewing a workflow

In read-write mode, open **Main model computation** or **LTE / Hydro** under **Model actions**, then follow the new preview button. The main screen also offers a spectra-only preview. Viewing a plan never creates a workspace, writes a lock file, sources a script, or starts a calculation.

Plans are available as HTML and JSON:

```text
/model-actions/plan/main/<model-relative-path>
/model-actions/plan/lte-hydro/<model-relative-path>
/model-actions/plan/flux/<model-relative-path>
```

Add `?format=json` for schema version 1. These are GET-only endpoints gated by read-write mode; responses are not cached.

Each external stage describes dependencies, working directory, input/output conventions, command, checked environment, preflight issues, resource observations, and completion/acceptance checks. LTE/hydro plans also describe preparation copies/checkpoints and the manually approved promotion with backups. The hydro prompt suggestions derive the depth count from the actual LTE `MODEL_SPEC`; they are not automated stdin.

Literal commands from inspected scripts and local sourced includes are shown for review, including control edits, output moves, and cleanup. They are **not executable plan actions**: control flow, substitutions, glob expansion, arbitrary helper calls, and aliases are not interpreted. Inspection is bounded to 16 included scripts of at most 2 MiB each. A recognized direct `batobs.sh` call in `batch.sh` adds a dependent flux stage marked as already invoked by main, not a second launch command. Custom invocation patterns may require manual interpretation.

“No known blocker” means only that the current checks passed. A plan is not complete shell translation, immutable provenance, or scientific acceptance. Small input files have SHA-256 snapshots; larger inputs have metadata only. Existing timestamp-based freshness remains in use. Legacy scripts can still overwrite logs, delete scratch products, and continue after a failed subprocess; the preview does not change these behaviors.

Refresh after external work: preflight and plans are snapshots. Existing live runtime polling does not automatically rebuild the plan. Every guarded mutation rechecks activity and lock availability on the server.

## Python runner boundary

`workflow_plan.py` defines stage contracts independently of Flask routes; `workflow_preflight.py` supplies read-only checks; `model_activity.py` owns cooperative mutation guards. The separate `runner_recipe.py` and `runner.py` implement explicit, reviewed ostar operations, bounded child execution, validation, and per-pass journals. The runner does not execute the viewer's opaque workflow plans. See [Standalone CMFGEN Runner](cmfgen-standalone-runner.md) for its supported subset and limitations. No plan-execution endpoint exists yet.
