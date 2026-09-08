# Standalone CMFGEN Runner

`cmfgen_run.py` runs a reviewed subset of the ostar workflows directly in Python. It never executes `batch.sh`, `batobs.sh`, sourced setup scripts, or arbitrary shell commands. This is a standalone command, not an in-app execution feature.

## Quick start

Preview the disposable smoke-test model without changing it:

```bash
python3 cmfgen_run.py models/ostar/model_Bstar1060_new --plan \
  --stage init --fresh-start \
  --cmfgen-root /home/karpov/CMFGEN2023/cur_cmf \
  --atomic-root /home/karpov/CMFGEN2023/atomic \
  --threads 1 --timeout 60 --memory-mib 2048
```

Execution is the default: omit `--plan` to run the model with the same options. Planning is always opt-in through `--plan` and never changes the workspace. Main/init runs continue from usable checkpoints by default, following CMFGEN's native behavior. `--fresh-start` explicitly moves existing `POINT1`, `POINT2`, and `SCRTEMP` into that run's `restart-before/` archive before starting from `*_IN`. These checkpoints are retained, not deleted, and are not automatically restored over newly generated restart state. Use a disposable or staged workspace when trying a new configuration.

## Continuation and fresh starts

No `--resume` flag is needed:

```bash
python3 cmfgen_run.py /path/to/model --stage main
```

Preflight reports a `restart` object with the requested policy, detected mode, present files, selected pointer, saved iteration count, and checks. Text progress announces, for example, `Continuation from POINT1 (saved iteration 7, record 2)`. `NUM_ITS`, including `--iterations N`, retains native semantics: iterations to perform in this invocation, not an absolute lifetime iteration target.

The runner checks `POINT1`, falling back to `POINT2` if the first pointer is missing or invalid. A usable pointer and nonempty readable `SCRTEMP` select continuation. No checkpoint files selects a fresh start. An orphan `SCRTEMP` without either pointer also leaves CMFGEN to start fresh, with a warning. Malformed pointers without a usable fallback, missing/empty or obviously truncated scratch data, and unsafe symlinked/hard-linked writable checkpoint files block execution. Repair the checkpoint or use `--fresh-start` to bypass content checks (not filesystem-safety checks).

When `RVTJ` is available for a continuation, preflight also uses its core atmosphere vectors as a checkpoint-health proxy. Its depth count must match `MODEL_SPEC`; radius, velocity, temperature, and electron-density vectors must be complete and finite, with radius, temperature, and electron density positive. A failure blocks continuation as a likely poisoned checkpoint and recommends a known-good checkpoint or `--fresh-start`. Missing `RVTJ` produces a warning rather than rejecting an otherwise usable native checkpoint. Auxiliary radiation fields are deliberately not required because a valid zero-iteration initialization can leave them uncomputed. The checked `RVTJ` is included in the immutable input snapshots.

When a recognizable `MODEL` is available, preflight cross-checks its depth count and ion/full-level/superlevel layout against `MODEL_SPEC`. Missing metadata produces a warning rather than a blanket rejection. `DO_HYDRO` or `REV_RGRID` requires a checkpoint with per-iteration radius/velocity/gradient storage (`WR_RVS=T`). These are conservative consistency checks: `MODEL` is not guaranteed checkpoint provenance, and binary record layout, population values, and complete atomic-data compatibility remain unverified.

Continuation does not require the fresh-start `He2_IN`/`GAMMAS_IN` files and does not recreate `T_IN`. Fresh-start structure/gamma and pending LTE-promotion findings are reported as warnings for continuation: the checkpoint, not a newly prepared input structure, supplies the starting state. If native checkpoint loading falls back to startup, missing fresh-start inputs can still make that native run fail.

Existing checkpoint files are copied in full to `restart-before/` before an automatic-mode run; they remain in place for CMFGEN to update. Preflight checks space for this backup plus the usual 1 GiB working headroom. Explicit `--fresh-start` moves them instead. Snapshots include missing checkpoint paths so newly appeared files invalidate a previously prepared plan. Backups are not automatically rolled back after failure: the new files may contain useful progress, and old versions remain available in the journal.

After execution, `startup_observed` distinguishes native evidence from preflight expectations. A matching first iteration counter confirms continuation; the native fresh-start message identifies startup/fallback. A fallback emits a prominent progress warning and is recorded even if the computation otherwise succeeds. When neither marker is available (notably a zero-iteration continuation), the observed mode is `unconfirmed`, not an invented confirmation. Normal native-output validation still applies.

The installation roots must be supplied by CLI options, environment, or configuration; shell setup is not sourced. Planning checks executable availability, required inputs, dimensions, active-ion atomic dependencies, workspace safety, process activity, and free disk space. An unreviewed script hash or nonliteral command in the atomic-link manifest blocks execution instead of falling back to the shell. Extending support to another script variant requires reviewing and implementing its operations first.

## Configuration defaults

The runner reads `~/.cmfgenrc`, then `.cmfgenrc` in the invoking current directory (not the model directory, unless that is your current directory). Both are optional. Use plain `key = value` entries without a section header:

```ini
cmfgen_root = ~/CMFGEN2023/cur_cmf
atomic_root = ~/CMFGEN2023/atomic
nthreads = 1
```

Settings are merged individually with precedence, highest first:

1. Explicit `--cmfgen-root`, `--atomic-root`, and `--threads` (alias `--nthreads`).
2. Nonempty environment variables `CMFDIST`, `ATOMIC`, and `OMP_NUM_THREADS`, respectively.
3. Current-directory `.cmfgenrc`.
4. Home-directory `~/.cmfgenrc`.
5. One thread by default; there are no built-in installation/data paths.

Config keys are case-insensitive; `CMFDIST` and `ATOMIC` are also accepted as file-key aliases, as is `threads` for `nthreads`. Thread counts must be positive integers. Use `#` comments and quote paths containing spaces. `~` is expanded, and relative paths in a config are relative to that config's directory. Relative CLI/environment paths are relative to the invoking directory. Shell commands, `export` statements, and `$VARIABLE` substitution are not supported. Malformed, unreadable, unknown-key, or duplicate-key config entries are errors; config files are never sourced or executed.

With roots configured, a preview becomes simply:

```bash
python3 cmfgen_run.py models/ostar/model_Bstar1060_new --plan --fresh-start
```

The human-readable plan shows effective settings; `--verbose` also shows their sources. The JSON plan (`--json`) records `configuration_sources` for programmatic inspection. These defaults apply to the standalone runner; the viewer's existing JSON/TOML configuration is unchanged.

## Multi-stage runs

Repeat `--stage` to execute an ordered sequence:

```bash
python3 cmfgen_run.py /path/to/model --plan \
  --stage lte --stage hydro --stage promote --stage init --stage main --stage flux

python3 cmfgen_run.py /path/to/model \
  --stage lte --stage hydro --stage promote --stage init --stage main --stage flux
```

The `--plan` mode fully preflights the first stage and records the remaining order. Later stages are deliberately not accepted in advance: each is rebuilt and preflighted immediately before it runs, after the preceding stage has produced and validated its outputs. A stage starts only when its predecessor returned `succeeded` or, for `init`, `initialized`. Execution failure, invalid output, timeout, cancellation, or a just-in-time preflight error stops the sequence and leaves all remaining stages unstarted. Duplicate stages are rejected; issue a separate runner command when a stage genuinely needs to be repeated.

Executable settings apply to every native stage in the sequence. `--iterations` applies only to its `main` stage. `--fresh-start` applies only to the first `init` or `main` stage, allowing a following `main` stage to continue from a successful initialization. `--cleanup-file` applies to the sequence's `cleanup` stage. A configured `--timeout` is a shared native-execution budget: elapsed execution is deducted before each subsequent native stage, while filesystem-only promotion/cleanup does not consume it. With no `--timeout`, the complete sequence remains unlimited.

## Stages

- `init` (default): temporarily sets `NUM_ITS=0` and runs `cmfgen_dev.exe`. Requires fresh `MODEL` and text `RVTJ`, matching depth count, and complete finite radius, velocity, temperature, and electron-density vectors. Radius, temperature, and electron density must also be positive. Returns **initialized**, not a completed solution. Uncomputed auxiliary diagnostics can be nonfinite; no `MOD_SUM` finalization is required. Initialization alone does not establish scientifically valid spectral-synthesis input.
- `main`: runs `cmfgen_dev.exe` using `IN_ITS`, optionally with a temporary positive `--iterations N` override. Requires fresh `MODEL`, `RVTJ`, and `MOD_SUM`, a native finalization record, valid core vectors, and no nonfinite/overflow tokens in `RVTJ`. It does not automatically launch observer synthesis.
- `lte`: runs `main_lte.exe` in an already prepared `lte/` directory. Checks its own controls and validates the generated Rosseland table's dimensions, complete rows, and finite nonnegative values. It does not prepare, promote, or automatically run hydro.
- `hydro`: runs `wind_hyd.exe` directly in the prepared `lte/` directory after a successful LTE stage. It requires a complete, finite `ROSSELAND_LTE_TAB`, `HYDRO_PARAMS`, and `MODEL_SPEC`; stale Rosseland tables are rejected. The runner selects PGPLOT's `/null` device, exits the diagnostic plot, requests the `MODEL_SPEC` depth count, and accepts the executable's calculated maximum optical depth. When `OLD_MOD=T`, `lte/RVTJ` is also required and selected. Stdout/stderr is captured as both the journal `process.log` and `lte/WIND_HYD`. Success requires a fresh `RVSIG_COL_NEW` with matching depth count, complete ordered rows, and finite physical grid values. The generated structure is not promoted automatically.
- `promote`: performs the same guarded LTE/hydro handoff as the web UI without launching an executable or requiring CMFDIST/ATOMIC. Run `python3 cmfgen_run.py /path/to/model --plan --stage promote` first to review it, then omit `--plan` to execute. It requires fresh LTE and hydro results, extracts the generated radius ratio, synchronizes `lte/VADAT [RMAX]`, copies `ROSSELAND_LTE_TAB`, `RVSIG_COL_NEW`, `RVSIG_COL`, and `VADAT` to the model root, and archives then invalidates incompatible main/restart/radiation state. Promotion checks file integrity and freshness, not scientific suitability; review the reported luminosity and radius ratio before running it. An already-promoted identical result is rejected to protect any newer main solution. Executable resource controls such as `--threads`, `--timeout`, and `--memory-mib` do not apply. Backups remain under `.cmfgen-viewer-backups/lte-hydro/`, and the runner records the handoff under `.cmfgen-runs/`.
- `flux`: runs `cmf_flux.exe` in an already prepared `obs/` directory with `IN_FILE` as stdin. Preflight checks the conventional parent `RVTJ` core vectors and depth count, rejecting NaN temperatures/densities before they can cause misleading native line-profile errors. This is not a complete check of populations or scientific suitability. Recreates the reviewed 15, 10, and 20 km/s passes plus continuum from `CMF_FLUX_PARAM_INIT`. Each pass requires a native completion marker and a fresh, complete, finite spectrum before publishing `obs_fin_15`, `obs_fin_10`, `obs_fin_20`, or `obs_cont`. The frequency heading must provide a point count; the intensity heading may omit it, as in native `OBSFRAME`, but its actual vector length must match exactly. Failure stops subsequent passes. Scientific suitability of the parent model and requested wavelength coverage still require review.
- `cleanup`: performs the viewer's conservative top-level model cleanup without launching an executable or requiring CMFDIST/ATOMIC. Preview with `python3 cmfgen_run.py /path/to/model --plan --stage cleanup`; omit `--plan` to archive every listed candidate, or repeat `--cleanup-file NAME` to select a subset. Candidates are limited to reviewed matrix/scratch/diagnostic names and patterns plus top-level symlinks; subdirectories, checkpoints, main products, and the commented-out `EDDFACTOR*` legacy cleanup commands are excluded. Unlike web cleanup, runner cleanup is recoverable: candidates are atomically moved under the run journal's `removed/` directory. Candidate identity and metadata are rechecked under the shared activity/write guard before anything moves.

Successful execution is distinct from convergence or scientific acceptance. Every report explicitly leaves scientific acceptance unassessed. A zero exit code alone is insufficient: Fortran `STOP` can return zero after an error. Text `RVTJ` is supported; binary variants are not validated by this version.

Observer templates may omit `SOB_EW_LAM_BEG` and `SOB_EW_LAM_END`. The continuum pass overrides these only when present, matching the legacy script's replacement-only edits. Absent bounds retain CMF_FLUX's native defaults (900–50,000 Å in the inspected installation), with Sobolev EW calculations disabled for this pass. Missing required controls and duplicate active controls still fail preflight. Atomic-link extraction ignores unrelated commands in hash-reviewed scripts, including continued `sed` commands; the separate atomic-link manifest still permits only literal link declarations.

## Resources and progress

Defaults are one thread (unless configured above), no execution timeout, and 4096 MiB of per-child virtual address space. `--memory-mib` uses POSIX `RLIMIT_AS`, not an RSS measurement. The runner sets OpenMP/OpenBLAS/MKL thread environment variables, disables core dumps, and raises the child stack limit to its permitted hard limit. Use `--timeout SECONDS` to opt into a time limit for smoke tests or supervised jobs. That timeout is shared across all passes; initial preflight/setup and final archival/validation are outside its budget. Termination can take a few additional seconds.

Each child has an owned process group. Timeout, Ctrl-C, and SIGTERM stop that group; the inherited workspace lock remains held while the native executable is alive. This requires a POSIX environment and usable Linux process visibility. Run on the same host/PID namespace as other model jobs: hidden external jobs cannot be reliably excluded.

Default output is human-readable: a preflight summary, stage updates, and a final result with elapsed time, pass counts, diagnostics, saved spectrum paths, and the run-report location. `[OK]`, `[WARN]`, and `[ERROR]` distinguish success, warnings, and failures. Colors are enabled automatically on terminals; redirected output stays plain. `--color never` disables colors, `--color always` forces them, and automatic mode respects `NO_COLOR` and `TERM=dumb`.

Repeated warnings across passes are grouped. Unavailable inactive-ion links are summarized rather than listed individually. Failed passes show key problems and the last 12 lines of their captured diagnostic tail. `--verbose` shows all reported warnings, captured diagnostic tails, and additional preflight detail; full native logs remain in the journal.

`--progress text` (the default) reports stages and available native iteration/frequency counters on stderr, with repeated unchanged updates throttled. `--progress none` suppresses live updates, not preflight diagnostics or the final summary. Human `plan` output and final run summaries go to stdout; run preflight and live updates normally go to stderr.

JSON output is opt-in for debugging and future workers:

```bash
# Full structured preflight, without launching:
python3 cmfgen_run.py /path/to/model --plan --stage main --json

# One final JSON result on stdout; JSON-lines progress events on stderr:
python3 cmfgen_run.py /path/to/model --stage main --json --progress json
```

The same modes apply to multi-stage runs. The final JSON object contains ordered `stage_results`, `completed_stages`, `remaining_stages`, and `failed_stage` when applicable.

`--json` by itself disables live progress by default. `--progress json` explicitly selects structured stderr events; with human final output, the preflight summary moves to stdout to keep that event stream clean. JSON journals (`plan.json`, `result.json`, and `events.jsonl`) are always retained independently of terminal output options. Exit codes are unchanged.

No `tqdm` dependency is needed, and no percentage is invented when native output lacks a reliable total. The Python event callback remains available for a future UI/progress adapter.

Exit codes: `0` initialized/succeeded, `1` execution or output-validation failure, `2` preflight/argument failure, `124` timeout, `130` cancellation.

## Evidence and recovery

Every executed runner action creates `.cmfgen-runs/<UTC-time>-<id>/` containing:

- `plan.json`, updated `result.json`, and timestamped `events.jsonl`;
- copies of small startup inputs and the previous atomic-link targets in `links-before.json`;
- for executable stages, each pass's stdout/stderr `process.log`, native diagnostics, selected products, and effective overridden control file;
- `before/` copies of selected pre-existing products and moved old logs;
- `restart-before/` full checkpoint copies for automatic-mode runs, or moved checkpoints for explicit `--fresh-start`.

A promotion journal records its plan, events, final result, synchronized `RMAX`, promoted and invalidated filenames, and the path to the separate full recovery backup. A cleanup journal retains every removed file or symlink under `removed/` and reports that recovery path.

A multi-stage invocation adds a parent sequence journal containing the requested order, orchestration events, the initial plan, each just-in-time `stage-NN-NAME-plan.json`, and the aggregate result. Every stage that actually starts also retains its normal detailed child journal; the aggregate `stage_results` link those reports. A stage rejected during just-in-time preflight has no child execution journal because nothing was launched.

Temporary `IN_ITS` or `CMF_FLUX_PARAM` overrides are restored after normal completion, failure, timeout, or handled cancellation, including original timestamps. A main run without overrides does not rewrite `IN_ITS`. SIGKILL, host failure, or disk failure can prevent restoration: consult the archived input/effective-control copies. Named spectra are published with atomic replacement only after validation. Old named spectra are backed up.

Before **every** flux pass, including the first pass of a rerun, the runner moves `EDDFACTOR`, `EDDFACTOR_INFO`, `ES_J_CONV`, `ES_J_CONV_INFO`, `J_COMP`, `MEANOPAC`, and `TRANS_INFO` into that pass's `before/` archive when present. These are grid/profile-dependent observer caches: retaining them in place can cause incompatible-depth failures or reuse radiation data from a different pass. This implements the legacy workflow's cold-cache behavior without deleting evidence. Explicit warm-cache/resume workflows are not supported.

Executable stages retain installed atomic links and other native scratch/diagnostic files; cleanup occurs only through the explicit `cleanup` stage and its reviewed candidate list. Native executables still write directly into the selected workspace. Selected backups are **not** a full directory snapshot or transactional rollback, and the child is **not** sandboxed against arbitrary filesystem writes. Use trusted executables and input workspaces. Unknown symlinks and unsafe known output targets are refused, but these checks are not a general security sandbox.

Inputs and the executable are rechecked under the viewer's shared advisory lock before mutation. Files up to 2 MiB use SHA-256 plus metadata; larger files use metadata only. Atomic data content is not comprehensively hashed or scientifically validated. External scripts do not honor this lock and must not be launched concurrently. Journals are retained for inspection, not cryptographically immutable provenance.

## Disposable Bstar smoke test

The original immediate crash was a depth mismatch: `MODEL_SPEC` requested 11 points while `RVSIG_COL` still contained 115. The test model now uses 11 depth points, 3 core rays, only H/He ions, coarse frequency controls, disabled hydro/clumping/X-rays, and one iteration. `RVSIG_COL` was reduced consistently to 11 points. Original `MODEL_SPEC`, `VADAT`, `IN_ITS`, and `RVSIG_COL` are preserved in `.runner-smoke-original/` inside the model directory.

An important control detail: `ISF` contains important-variable, superlevel, and full-level counts. Setting only the first count to zero does not disable an ion. The unused ion declarations were commented out for this smoke test.

With one thread and a 2 GiB address-space limit, initialization completed in approximately 0.25 seconds. A full iteration finished in approximately 2.2 seconds but produced nonfinite `RVTJ` values and was correctly rejected as `invalid_output`, despite its zero exit code and finalization marker. This configuration exercises fast startup and failure reporting; it is intentionally not physically meaningful or a converged atmosphere.

The observer workflow was subsequently exercised against the real disposable model. A parent atmosphere containing NaN temperatures and electron densities reproduced the reported `INS_LINE` failure. Regenerating finite startup data with `init` removed that crash. The observer template was also coarsened for testing (frequency/profile spacing and spatial interpolation), preserving the original in `.runner-smoke-original/CMF_FLUX_PARAM_INIT`.

All four flux passes then completed and validated in approximately 31.5 seconds total, using one thread, a 60-second shared budget, and a 2 GiB address-space limit. Run `20260907T100701Z-f8af40d8` retains the successful report and individual products. Outputs from this deliberately unconverged initialization are for workflow testing only, not physical interpretation.

The real LTE-to-hydro handoff was subsequently exercised after generating `lte/ROSSELAND_LTE_TAB`. The standalone hydro stage completed in approximately 0.11 seconds and produced a structurally valid 30-point `lte/RVSIG_COL_NEW`, matching the prepared LTE workspace's `MODEL_SPEC`; run `20260907T141011Z-db0d5c4d` retains its generated stdin, captured `WIND_HYD`, and output grid. The native code reported underflow/denormal flags and its outer-opacity extrapolation warning. This verifies runner mechanics only: the deliberately reduced grid and generated structure are not scientifically accepted or automatically promoted.

A subsequent native zero-iteration run (`20260907T102452Z-dd49ff5a`) exercised automatic checkpoint startup in approximately 0.15 seconds, preserved the existing checkpoint bytes, and passed core-output validation. It has no explicit native iteration marker, so its report correctly leaves `startup_observed` unconfirmed. Automated main-stage tests cover incremented iteration evidence and native fresh-start fallback reporting.
