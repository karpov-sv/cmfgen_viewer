# LTE / Hydro

Use **Preview workflow** for a read-only stage plan covering preparation through manual promotion. Stage preflight checks native executable configuration, atomic dependencies, controls, workspace resources, and activity. Shell launcher problems are advisory for terminal execution and do not block the native runner. Mutations and handoffs are blocked during visible active calculations or uncertain activity; see [Templates and configuration](/documentation/templates-and-configuration#activity-and-write-protection) for shared settings and write protection.

The viewer supports preparation and state tracking for the LTE/hydro sequence used when changing parameters such as `LOGG`. Use **Run LTE** and **Run hydro** in their stage cards to launch execution without leaving the workflow after a confirmation popup. The server validates current inputs before starting. Plan previews remain available on the full **Model runner** page. Running jobs survive viewer restarts; their cards restore status after reload, show the job status and timestamp with **Run details**, **View output**, and **Stop run** links and controls, and refresh workflow results when execution finishes. Promotion remains a separate action after reviewing hydro results. For custom sequences and resource settings, use **Model runner**; expand **Run in terminal** for terminal commands; the open workflow page receives server-sent status updates. The server checks process and file status every five seconds while subscribed.

Open a concrete, non-SN model and choose **LTE / Hydro** under **Model actions**. Read-write mode must have been enabled at startup.

## 1. Prepare the workspace

Preparation requires these regular files in the model root:

- `VADAT`
- `MODEL_SPEC`

`GRID_PARAMS`, `ltebat.sh`, `HYDRO_PARAMS`, and `clean.sh` use the shared
[workflow template resolver](/documentation/templates-and-configuration). It prefers the source
model, an explicit `--template-root`, model-tree `templates/` directories, then
packaged defaults. Template paths mirror the model layout: `lte/` for LTE
files and `clean.sh` for cleanup. Each selected source is shown on the page.
A model without a local template collection can therefore prepare LTE using the
bundled files. Physical model inputs remain mandatory.

The action creates `lte/` and copies only the required inputs. Before publishing the new workspace, it initializes the copied `HYDRO_PARAMS` from the copied `VADAT`: `LOGG` maps to `LOG_G`, and `TEFF`, `MDOT`, `VINF`, and `BETA` are transferred. `REF_R` is derived from `LSTAR` and `TEFF`; `CON_R` is scaled to preserve the template's `CON_R / REF_R` ratio. Review this connection-radius estimate before running hydro. Template comments and other controls are preserved. Published workspace directories are traversable by all users (`0755` by default); copied controls are readable by all users (`0644` by default), and executable scripts retain execute access (`0755` by default).

Initialization uses the same validation and calculation as **Use VADAT parameters**. Missing, ambiguous, nonfinite, or unsupported inputs leave the entire copied template unchanged and produce a preparation warning with details. An initialization write failure prevents publication of the workspace. No calculation starts, and the source model and shared templates are not rewritten. Later `VADAT` edits can still be reconciled through the alignment preview.

If the source model has `RVSIG_COL`, it is preserved as `RVSIG_COL_OLD`; models without that optional old structure can still proceed because the hydro stage will generate a new one. An existing incomplete `lte/` path is never merged or overwritten; repair or remove it manually.

## 2. Run LTE externally

Use the inline quick editors to fill or update `TEFF`, `LOGG`, and `CHK_NG` in `lte/VADAT`, and `ND`, `NC`, and `NP` in `lte/MODEL_SPEC`. `CHK_NG` defaults to `F`, matching the supplied example models. Missing controls are appended without rewriting the surrounding file, while existing controls are updated in place; each save creates the usual recoverable editor checkpoint. The grid editor requires `NP = ND + NC`.

Full-text editor links remain available for `VADAT`, `MODEL_SPEC`, and `GRID_PARAMS`. The run command remains guarded until all six required control keys exist. The page then shows an absolute command of this form:

```bash
cd /absolute/path/to/model/lte && ./ltebat.sh
```

The next stage remains blocked until `lte/ROSSELAND_LTE_TAB` exists and is at least as new as its relevant LTE inputs. Editing an input after a run marks the output stale.

The LTE run panel recognizes `main_lte`/`ltebat` processes only when their native working directory exactly matches the model's `lte/` directory. It displays PID, state, elapsed and accumulated CPU time, average CPU use, memory, and thread count. The latest integer in `ML_COUNTER` is compared with the `Number of frequencies` reported by `OUTLTE` to give an estimated frequency-integration percentage. The counter may be written in batches, so it need not change on every status update. After a current result becomes available, it is labeled **Last logged frequency counter** rather than a completion percentage; a final counter below 100% does not mean the run is unfinished.

The same panel now gives a retained run summary when the process is absent. It combines bounded head/tail parsing of `OUTLTE` with `ML_COUNTER`, `ltebat.log`, `TIMING`, and the freshness of `ROSSELAND_LTE_TAB`. It reports frequency progress, `DELTA_ED`/`DELTA_T`, batch start/finish markers, accumulated timing, and grouped runtime, atomic-data, frequency-grid, and floating-point diagnostics. Fatal diagnostics in a current `OUTLTE` block the hydro handoff even if an older Rosseland result still exists. Opening `OUTLTE` in **Parsed** mode exposes the same analysis. Large logs are not rejected by the generic parser size limit.

## 3. Run hydro externally

After LTE completes, align `HYDRO_PARAMS [MU_ATOM]` with the mean atomic weight reported in the fresh `ROSSELAND_LTE_TAB` header. Preparation leaves this value awaiting the LTE result. If it differs, the hydro panel shows the current and proposed values and offers **Apply LTE parameters**. Applying saves a recovery checkpoint and makes existing hydro output stale; rerun hydro afterwards. Viewing the page does not change files.

Hydro readiness and promotion require this agreement. Missing, duplicate, nonfinite, or nonpositive LTE metadata, a stale opacity table, or fatal LTE diagnostics blocks alignment. The preview is rechecked under the model write guard when applied. LTE output itself is preserved.

Review `lte/HYDRO_PARAMS`, including `LOG_G`, `TEFF`, and related model values. A red warning highlights disagreement with the intended model in `lte/VADAT`, even when an old template matches the generated hydro output.

Open **Use VADAT parameters — preview changes** to review the proposed values. **Apply VADAT parameters** copies `LOGG` to `LOG_G` and aligns `TEFF`, `MDOT`, `VINF`, and `BETA`. It derives `REF_R` from the intended luminosity and temperature using the same relation as wind_hyd: `REF_R = 6.9599 × sqrt(LSTAR) × (0.5770 / TEFF)²`, with `REF_R` in 10¹⁰ cm and `TEFF` in 10⁴ K. It scales `CON_R` to preserve the existing `CON_R / REF_R` ratio; this is an estimate that you must review for the model.

The action supports the supplied wind mode (`OLD_MOD=F`, `OLD_V=F`, `WIND_PRES=T`). Missing, duplicate, or invalid numeric controls require manual correction first. It checks that neither file changed since the preview, refuses active or uncertain workspaces, and checkpoints `HYDRO_PARAMS` before saving. It leaves VADAT untouched, marks hydro results stale, and starts no calculation. LTE results remain usable. `LSTAR`, `RSTAR`, and `MASS` entries in HYDRO_PARAMS are ignored by wind_hyd: luminosity is derived from temperature and reference radius, and mass from gravity and reference radius.

The displayed command uses the conventional `cmfdist` environment variable:

```bash
cd /absolute/path/to/model/lte && set -o pipefail && $cmfdist/exe/wind_hyd.exe 2>&1 | tee WIND_HYD
```

The supplied free-form instructions give the interactive answers `/null`, `e`, `70`, followed by Enter (or the required maximum optical depth). These values are shown as instructions rather than piped automatically so they can be adjusted for the model. The pipeline leaves stdin attached to the terminal, captures stdout and stderr in `WIND_HYD`, and uses `pipefail` so a failed executable is not hidden by a successful `tee`.

The hydro panel similarly identifies `wind_hyd` by process name and exact `lte/` working directory and reports its runtime statistics. Hydro does not expose a comparably reliable inner-loop counter. If `RVSIG_COL_NEW` is visible while it is being written, the last output-grid index is compared with its declared depth-point count; otherwise the monitor shows the process without inventing a percentage.

For newly captured runs, the panel and parsed `WIND_HYD` view extract fatal runtime messages, warnings, transition radius and velocity, effective temperature, Eddington parameter, stellar mass, and the final generated-versus-desired reference-radius difference. `RVSIG_COL_NEW` remains the authoritative result. Workspaces without `WIND_HYD` can still be reviewed using the generated structure, but captured hydro diagnostics are unavailable.

When a monitored LTE or hydro run stops, the workflow page refreshes automatically to update outputs, diagnostics, and promotion readiness. Unsaved control edits defer the reload and show a **Refresh results** button.

For both stages, process presence is authoritative. Output files can survive a completed or failed calculation, so with no matching process any parsed value is labeled **Last recorded progress**. Progress from an older run is hidden when its file predates a newly detected process. Process monitoring uses `psutil` on Linux and macOS. Missing or denied process visibility is shown as unavailable; it does not establish that the workspace is idle.

Inspect `RVSIG_COL_NEW`. If its luminosity does not match the intended value, update `REF_R` in `HYDRO_PARAMS` and rerun. Once the luminosity is correct, promotion automatically writes the reported inner-to-outer radius ratio to `VADAT` as `RMAX` and its reported core radius as `RSTAR`. This preserves the generated radius scale instead of allowing the main model to rescale the structure to an old radius. Legacy outputs without a labeled core radius retain the existing RSTAR, which needs manual review.

The result-review panel shows the generated quantities and promotion action first. RMAX and core-radius differences are labeled **Will be synchronized during promotion**, rather than parameter-mismatch warnings. Other parameter differences still require review. No manual RMAX edit is needed. The collapsed **Adjust parameters and rerun** section contains the REF_R quick editor and full HYDRO_PARAMS/VADAT editor links. Saving REF_R creates a recoverable checkpoint and makes hydro output stale until wind_hyd is rerun. Full VADAT edits require rerunning LTE and hydro.

Promotion preserves all other root `VADAT` values, comments, and formatting. It also synchronizes the generated radii in `lte/VADAT`. Root-only edits, including initialization controls, are retained. Differences in core physics settings between root and LTE controls are shown for review; promotion does not merge those settings or establish that the structure matches changed physics. Both original VADAT files are backed up. Promotion status compares installed structures and generated radii, allowing the two configuration files to differ intentionally.

Promotion archives and removes old main-run checkpoints and solution products (`POINT1`, `POINT2`, `SCRTEMP`, their `NEW_*` variants, `MODEL`, `RVTJ`, and `MOD_SUM`) together with grid-dependent radiation caches (`EDDFACTOR*`, `ES_J_CONV*`, `J_COMP`, `MEANOPAC`, and `TRANS_INFO`). They describe the previous depth/radius grid and cannot be made compatible by copying the new hydro structure into them. A subsequent fresh main or initialization run regenerates the solution state; all invalidated files remain recoverable in the promotion checkpoint.

When `RVSIG_COL_NEW` is available, its labeled header is summarized directly on the page. Generated luminosity, radius ratio, core radius, effective temperature, surface gravity, mass, and mass-loss rate are compared with the intended `lte/VADAT` values; reference radius is compared with `HYDRO_PARAMS [REF_R]`. Parameter mismatches are highlighted with colored rows and a warning; radius changes are marked for synchronization during promotion. Mean atomic mass, Eddington parameter, atom density, and depth-point count are shown as additional diagnostics when present. Fresh files alone do not establish that the generated structure matches the intended model.

## 4. Promote reviewed results

Promotion is enabled only when both `ROSSELAND_LTE_TAB` and `RVSIG_COL_NEW` are fresh. It copies:

| LTE workspace source | Model-root destination |
| --- | --- |
| `ROSSELAND_LTE_TAB` | `ROSSELAND_LTE_TAB` |
| `RVSIG_COL_NEW` | `RVSIG_COL_NEW` and `RVSIG_COL` |
| Generated `RSTAR` / `RMAX` | Patch these controls in the current root `VADAT` |

Successful promotion also moves known top-level LTE temporary files into the same checkpoint, under `lte/temporary/`. Candidates include regular `*OUT`, `POP*`, numeric `fort.*` files, and the standard matrix, scratch, and intermediate diagnostics targeted by the model cleanup policy. Controls and `*_IN` population inputs, `ROSSELAND_LTE_TAB`, `RVSIG_COL_NEW`, `MODEL`, `RVTJ`, `GAMMAS`, and retained run diagnostics (`OUTLTE`, `WIND_HYD`, `TIMING`, `ML_COUNTER`, `OUT_PARAMS`, and `ltebat.log`) stay in `lte/`. Symbolic links, hard-linked inputs, nested directories, and unrelated files are excluded. If promotion fails, moved temporary files and previous model state are restored.

Expand **LTE temporary files** in the result-review card to see candidates and sizes. **Clean LTE Temporary Files** also works independently of promotion, including for already-promoted models, and archives files under `.cmfgen-viewer-backups/lte-cleanup/<timestamp>/`. Cleanup requires an idle model with available process visibility. It tidies the working directory without reducing total disk usage; remove the recovery archive separately when it is no longer needed. The runner's `promote-hydro` stage performs the same automatic cleanup and records its results.

Existing destination files are saved under `.cmfgen-viewer-backups/lte-hydro/<timestamp>/` first. Promotion also marks the solution stale and removes its cached summary, so a pre-promotion `MOD_SUM` is not treated as current.

## 5. Run the main model externally

The final LTE/hydro card is only a handoff guard. After the current results have been promoted and `batch.sh`, `VADAT`, `RVSIG_COL`, and `ROSSELAND_LTE_TAB` are available in the model root, it links to the separate **Main Model Computation** workflow. That workflow owns the main-run command, prerequisites, and result freshness checks.

The overview identifies the next stage from the current workspace results. Hydro stays collapsed while waiting for usable LTE output; its header still reports parameter mismatches. Validation lists blockers separately from missing atomic/restart link targets and script/environment warnings, with full target paths available on demand. The overview distinguishes available output from idle process status. Until the current results are promoted, the main-computation handoff says **Awaiting promotion** and directs the user back to result review. After promotion, main computation performs its own readiness checks.

The **OS state** column reports the operating system's scheduling snapshot, independently of the workflow's **Running now** status. A live calculation can be reported as sleeping; this alone does not establish that it is paused or stalled. CPU-time changes and file progress provide additional evidence of ongoing work.
