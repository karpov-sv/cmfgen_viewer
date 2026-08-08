# LTE / Hydro Workflow

The viewer supports preparation and state tracking for the LTE/hydro sequence used when changing parameters such as `LOGG`. It deliberately does **not** start, stop, or supervise CMFGEN programs. Run every displayed command in a terminal you control; the open workflow page polls read-only run status every five seconds.

Open a concrete, non-SN model and choose **LTE / Hydro** under **Model actions**. Read-write mode must have been enabled at startup.

## 1. Prepare the workspace

Preparation requires these regular files in the model root:

- `VADAT`
- `MODEL_SPEC`
- `clean.sh`

It also requires `GRID_PARAMS`, `ltebat.sh`, and `HYDRO_PARAMS` under the configured model base's `examples/` directory. `GRID_PARAMS` and `ltebat.sh` may be stored in `examples/lte2/`, matching the supplied example layout.

The action creates `lte/` and copies only the required inputs. If the source model has `RVSIG_COL`, it is preserved as `RVSIG_COL_OLD`; models without that optional old structure can still proceed because the hydro stage will generate a new one. An existing incomplete `lte/` path is never merged or overwritten; repair or remove it manually.

## 2. Run LTE externally

Use the inline quick editors to fill or update `TEFF`, `LOGG`, and `CHK_NG` in `lte/VADAT`, and `ND`, `NC`, and `NP` in `lte/MODEL_SPEC`. `CHK_NG` defaults to `F`, matching the supplied example models. Missing controls are appended without rewriting the surrounding file, while existing controls are updated in place; each save creates the usual recoverable editor checkpoint. The grid editor requires `NP = ND + NC`.

Full-text editor links remain available for `VADAT`, `MODEL_SPEC`, and `GRID_PARAMS`. The run command remains guarded until all six required control keys exist. The page then shows an absolute command of this form:

```bash
cd /absolute/path/to/model/lte && ./ltebat.sh
```

The next stage remains blocked until `lte/ROSSELAND_LTE_TAB` exists and is at least as new as its relevant LTE inputs. Editing an input after a run marks the output stale.

The LTE run panel recognizes `main_lte`/`ltebat` processes only when their `/proc` working directory exactly matches the model's `lte/` directory. It displays PID, state, elapsed and accumulated CPU time, average CPU use, memory, and thread count. The latest integer in `ML_COUNTER` is compared with the `Number of frequencies` reported by `OUTLTE` to give an estimated frequency-integration percentage. The counter may be written in batches, so it need not change on every poll.

## 3. Run hydro externally

Review `lte/HYDRO_PARAMS`, including `LOGG`, `TEFF`, luminosity, and related model values. The displayed command uses the conventional `cmfdist` environment variable:

```bash
cd /absolute/path/to/model/lte && $cmfdist/exe/wind_hyd.exe
```

The supplied free-form instructions give the interactive answers `/null`, `e`, `70`, followed by Enter (or the required maximum optical depth). These values are shown as instructions rather than piped automatically so they can be adjusted for the model.

The hydro panel similarly identifies `wind_hyd` by process name and exact `lte/` working directory and reports its runtime statistics. Hydro does not expose a comparably reliable inner-loop counter. If `RVSIG_COL_NEW` is visible while it is being written, the last output-grid index is compared with its declared depth-point count; otherwise the monitor shows the process without inventing a percentage.

For both stages, process presence is authoritative. Output files can survive a completed or failed calculation, so with no matching process any parsed value is labeled **Last recorded progress**. Progress from an older run is hidden when its file predates a newly detected process. Process monitoring is Linux-specific and degrades to file status when `/proc` is unavailable.

Inspect `RVSIG_COL_NEW`. If its luminosity does not match the intended value, update `REF_R` in `HYDRO_PARAMS` and rerun. Once the luminosity is correct, place the reported inner-to-outer radius ratio in `VADAT` as `RMAX`.

The result-review panel links directly to `RVSIG_COL_NEW`, `ROSSELAND_LTE_TAB`, `HYDRO_PARAMS`, and `VADAT`. Inline quick controls update `HYDRO_PARAMS [REF_R]` and `VADAT [RMAX]` with recoverable checkpoints. Changing `REF_R` correctly marks the hydro output stale until `wind_hyd` is rerun; changing the post-hydro `RMAX` alone does not invalidate the LTE/hydro outputs.

When `RVSIG_COL_NEW` is available, its labeled header is summarized directly on the page. Generated luminosity, radius ratio, effective temperature, surface gravity, reference radius, mass, and mass-loss rate are compared with the corresponding `HYDRO_PARAMS` or `VADAT` values. Percentage or absolute differences are highlighted, while core radius, mean atomic mass, Eddington parameter, atom density, and depth-point count are shown as additional diagnostics when present.

## 4. Promote reviewed results

Promotion is enabled only when both `ROSSELAND_LTE_TAB` and `RVSIG_COL_NEW` are fresh. It copies:

| LTE workspace source | Model-root destination |
| --- | --- |
| `ROSSELAND_LTE_TAB` | `ROSSELAND_LTE_TAB` |
| `RVSIG_COL_NEW` | `RVSIG_COL_NEW` and `RVSIG_COL` |
| `VADAT` | `VADAT` |

Existing destination files are saved under `.cmfgen-viewer-backups/lte-hydro/<timestamp>/` first. Promotion also marks the solution stale and removes its cached summary, so a pre-promotion `MOD_SUM` is not treated as current.

## 5. Run the main model externally

The final LTE/hydro card is only a handoff guard. Once `batch.sh`, `VADAT`, `RVSIG_COL`, and `ROSSELAND_LTE_TAB` are available in the model root, it links to the separate **Main Model Computation** workflow. That workflow owns the main-run command, prerequisites, and result freshness checks.
