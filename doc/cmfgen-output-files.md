# CMFGEN Output Files

Top-Level Execution Context
---------------------------
1) `CMFGEN` main opens global logs:
   - `OUTGEN` (`new_main/cmfgen.f:101`) append mode
   - `WARNINGS` (`new_main/cmfgen.f:108`)
2) `CMFGEN_SUB` drives iteration, physics, and most output files.
3) Final-iteration block in `cmfgen_sub` emits compact/final science outputs (`MOD_SUM`, `RVTJ`, species files, DC files, `GAMMAS`, etc.).

File Types Used by CMFGEN
-------------------------
1) ASCII text files (human-readable)
- Examples: `RVTJ`, `OBSFLUX`, `MOD_SUM`, `MEANOPAC`, `HYDRO`, `POP*`, `*OUT`, `GAMMAS`, `NETRATE`...

2) Direct-access unformatted binary files (+ metadata sidecar)
- Examples: `EDDFACTOR`, `ES_J_CONV`, `JH_AT_CURRENT_TIME`.
- Companion sidecars: `<name>_INFO` written by `WRITE_DIRECT_INFO_V3` (`subs/write_direct_info_v3.f`).
- `_INFO` is required to reopen record length/word-size/endian safely across systems.

3) Sequential unformatted binary files
- Examples: `BAMAT`, `CUR_MODEL_DATA`.

4) Scratch/restart binary + pointer text files
- Examples: `SCRTEMP` + `POINT1` + `POINT2`.


Core Final Products (viewer-first priority)
===============================================

RVTJ
- File: `RVTJ`
- Writer: `new_main/cmfgen_sub.f:4312`
- Format: ASCII
- Condition: final iteration (`LST_ITERATION` block)
- Contains:
  - global header/date/program date
  - dimensions ND/NC/NP/NCF
  - core scalar params (Mdot, L, abundance, naming convention)
  - vectors: Radius, Velocity, Sigma, ED, T, TGREY, radioactive heating
  - mean opacities: Rosseland/Flux/Planck/Absorption means
  - integrated moments: J/H/K
  - densities: atom/ion/mass/clumping
  - selected species/ion population blocks (e.g., H, He, HeI, HeII data)
- Existing readers:
  - `tools/rd_rvtj_v4.f` (`RD_RVTJ_PARAMS_V4`, `RD_RVTJ_VEC_V4`)
  - `tools/rd_sing_vec_rvtj.f`
- Viewer relevance: highest. This is the main radial-structure payload.

OBSFLUX
- File: `OBSFLUX`
- Writers: `new_main/cmfgen_sub.f:3027` (initial), `new_main/cmfgen_sub.f:3715` (append)
- Format: ASCII vector blocks (via `WRITV` / `WRITV_V2`)
- Contains:
  - continuum frequency grid
  - observed intensity (Janskys)
  - luminosity vectors and appended diagnostics (line emission, dielectronic terms, mechanical luminosity, radioactive/shock depositions, normalized luminosity checks)
- Viewer relevance: highest for spectral/sed view.

MOD_SUM
- File: `MOD_SUM`
- Writer: `new_main/cmfgen_sub.f:4091`
- Format: ASCII summary
- Contains:
  - start/finalization timestamps
  - model dimensions and counts
  - atomic model summary by species/ion
  - stellar/wind parameters (L, Mdot, R*, Teff diagnostics at tau points)
  - velocity law parameters
  - abundance summary (including solar-reference comparison helpers)
  - clumping summary and max correction on final iteration
- Viewer relevance: high for model-overview panel and metadata cards.

MEANOPAC
- File: `MEANOPAC`
- Writer: `new_main/cmfgen_sub.f:3081`
- Format: ASCII table
- Contains depth-wise opacity/tau diagnostics (Rosseland, flux, e-scattering means, ratios, kappa, velocity).
- Viewer relevance: medium-high for diagnostic plots.

HYDRO
- File: `HYDRO`
- Opened in `subs/hydro_terms_v5.f:118`; called from `new_main/cmfgen_sub.f:3168`
- Format: ASCII table
- Contains momentum equation term balance / force diagnostics.
- Viewer relevance: medium-high for hydro-consistency diagnostics.


Species/Ion Population Outputs (final iteration)
===================================================

POP files
- Pattern: `POP<species>` (e.g., `POPCARB`, `POPNIT`, etc.)
- Writer loop: `new_main/cmfgen_sub.f:4449`
- Format: ASCII
- Contains:
  - format date, completion date, ND, abundance
  - species total population vector
  - ion-specific blocks emitted through `RITE_ASC`
- Viewer relevance: high for composition/population depth plots.

Departure coefficient files
- Pattern: `<ION_ID>OUT` (e.g., `CIVOUT`, etc.)
- Writer call site: `new_main/cmfgen_sub.f:4485`
- Writer implementation: `subs/writedc_v3.f`
- Format: ASCII
- Details:
  - opened with `STATUS='REPLACE'` (`subs/writedc_v3.f:58`)
  - can output DC or LOG(DC) depending on numeric range
  - includes R, ion density proxy, ED, T, velocity, clumping, depth index
- Viewer relevance: high for NLTE departure visualizations.

Mean ionic charge file
- File: `GAMMAS`
- Writer: `new_main/cmfgen_sub.f:4496` via `RITE_GAM_HEAD` + `RITE_GAM_V2`
- Implementation: `subs/rite_gam_v2.f`
- Format: ASCII
- Contains ED/R/T headers and species-wise mean charge profiles.
- Viewer relevance: medium-high.


Rates/Line Diagnostics (conditional)
=======================================

Written when `WRITE_RATES=.TRUE.`
- Files opened at `new_main/cmfgen_sub.f:1303-1306`:
  - `NETRATE`
  - `TOTRATE`
  - `EWDATA`
  - `LINEHEAT`
- Format: ASCII
- Condition: final-iteration output stage with rates enabled.
- Viewer relevance: medium-high for advanced diagnostics.

Negative opacity diagnostic fallback
- File: `NEG_OPAC`
- Open at `new_main/cmfgen_sub.f:1308` when not writing full rates
- Format: ASCII diagnostic
- Viewer relevance: diagnostic/debug only.

Boundary J consistency diagnostic
- File: `J_COMP`
- Writers in both branches: `new_main/mod_subs/comp_j_blank.f:445` and `:869`
- Format: ASCII
- Contains frequency-wise comparison of J(moment) vs J(ray) at boundaries.
- Viewer relevance: medium (numerical quality diagnostics).

Iteration equation tracing
- File: `STEQ_VALS`
- Opened append at `new_main/cmfgen_sub.f:528`, reused throughout iterations.
- Format: ASCII iterative logs/arrays.
- Viewer relevance: low-medium unless building convergence-debug tooling.

Solver correction depth summary
- File: `CORRECTION_SUM`
- Writer family: `solveba_v*.f` (e.g., `solveba_v13.f`).
- Format: ASCII table with depth index and counts above multiple correction thresholds (e.g., `100.0%`, `10.0%`, ..., `0.0001%`).
- Typical header includes `NT=<value>` and a `Depth` table heading.
- Viewer relevance: medium-high for convergence-quality diagnostics by depth.


Restart/State/Continuation Files (not viewer-first)
=======================================================

SCRTEMP + POINT pointers
- Files:
  - `SCRTEMP` (unformatted direct-access state)
  - `POINT1`, `POINT2` (ASCII pointer files)
- Read/write implementation: `subs/scr_read_v2.f`
  - reads: `POINT1` / `POINT2` at lines ~87/106
  - opens `SCRTEMP` direct at ~136 and ~347
  - writes pointer files at ~449 and ~460
- Called by `CMFGEN_SUB` via `SCR_READ_V2` / `SCR_RITE_V2` (e.g., `new_main/cmfgen_sub.f:912`, `1175`, `4033`, `4656`).
- Purpose: restart and iteration history, not primary science display.

BA matrix cache
- Files:
  - `BAMAT` (sequential unformatted)
  - `BAMATPNT` (ASCII pointer/metadata; created as `DESC//'PNT'`)
- Writer: `new_main/subs/store_ba_data_v3.f`
- Calls from `cmfgen_sub`:
  - read: `new_main/cmfgen_sub.f:1204`, `3912`
  - write: `new_main/cmfgen_sub.f:2943`, `3624`
  - pointer init: `new_main/cmfgen_sub.f:4062`
- Purpose: avoid recomputing BA matrix near convergence.

Radiation field direct-access files
- `EDDFACTOR`
  - managed by `new_main/subs/open_rw_eddfactor.f`
  - called from `cmfgen_sub` at `1331` and `4665`
  - format: direct-access unformatted + `EDDFACTOR_INFO`
- `ES_J_CONV`
  - written by `subs/comp_j_conv_v2.f` (same direct format logic as EDDFACTOR)
  - calls from `cmfgen_sub` at `1990`, `3880`, `4081`
  - sidecar: `ES_J_CONV_INFO`
- `JEW`
  - direct-access unformatted equivalent-width auxiliary J field (`cmfgen_sub.f:1360`, `1370`)
- Purpose: continuation/transfer internals.

Other internal diagnostics seen in code path
- `CHEK+CK_ON_BA_UPDATE` (`new_main/cmfgen_sub.f:1312`)
- `IMPURITYJ` (`new_main/cmfgen_sub.f:1317`)
- These are specialized and not generally viewer targets.


SN / Time-Dependent Outputs
==============================

SN hydro handoff model
- File: `SN_HYDRO_FOR_NEXT_MODEL`
- Call: `new_main/cmfgen_sub.f:4442`
- Writer: `new_main/subs/out_sn_pops_v3.f`
- Format: ASCII structured vectors
- Contains R/V/sigma/T/density/atom/electron/clumping/opacity and species/isotope mass fractions.
- Viewer relevance: high for SN sequence workflows.

Sequential binary model handoff
- File: `CUR_MODEL_DATA`
- Call: `new_main/cmfgen_sub.f:4509` (also `4628` in time-sequence path)
- Writer: `new_main/subs/write_seq_time_file_v1.f:21`
- Format: sequential unformatted binary
- Contains ND, species metadata, and full arrays for continuation.
- Viewer relevance: medium (requires custom parser).

J/H field storage at current time
- File: `JH_AT_CURRENT_TIME`
- Writer: `plane/out_jh.f:60`
- Sidecar: `JH_AT_CURRENT_TIME_INFO` (via `WRITE_DIRECT_INFO_V3`)
- Triggered via `OUT_JH` calls in `new_main/mod_subs/comp_j_blank.f` (e.g., around `:751` when `LST_ITERATION .AND. WRITE_JH`).
- Format: direct-access unformatted records of J/H vs frequency and depth.
- Viewer relevance: high for detailed radiation field browser.


Gamma-Transport Outputs
==========================

Main gamma spectrum output
- File: `GAMFLUX`
- Writer: `new_main/gam_transport/gamray_sub_v3.f90:445`
- Format: ASCII (frequency + observed intensity similar style to OBSFLUX)
- Viewer relevance: high when gamma transport is enabled.

Gamma energy deposition profile
- File: `GAMRAY_ENERGY_DEP`
- Writer: `new_main/gam_transport/gamma_energy_dep_v7.f90:114`
- Format: ASCII
- Contains ND, SN age, and depth table with radius/velocity/energy deposition/local emission/decay kinetic energy.
- Used by reader path in `new_main/subs/get_non_loc_gamma_energy_v2.f`.
- Viewer relevance: high for SN/gamma diagnostics.

Verbose gamma diagnostics (when `VERBOSE_GAMMA`)
- Written under `./data/`, examples:
  - `gamma_nu_grid.dat`
  - `scattering_diff.dat`
  - `velocity_step.dat`
  - `gamma_ray_local_emission.dat`
  - `electron_density.dat`
  - `nu_end.dat`
  - `TAU_gam_xray.dat`
  - plus others from helper routines
- Code: `new_main/gam_transport/gamray_sub_v3.f90`.
- Note: code checks that `data/` directory exists when verbose gamma is active.

Additional gamma diagnostic artifact
- File: `kevin_testing`
- Opened in `new_main/gam_transport/gamray_sub_v3.f90:128`.
- Looks like developer/diagnostic logging; treat as non-contract output.


Hydro/Regridding Option-Specific Outputs
===========================================

Hydro iteration files (`DO_HYDRO` workflows)
- Source: `new_main/subs/do_cmf_hydro_v2.f`
- Files:
  - `HYDRO_ITERATION_INFO`
  - `GREY_SCL_FAC_IN`
  - `HYDRO_OLD_MODEL`
  - `NEW_CALC_GRID`
  - `RVSIG_COL`
  - archived `RVSIG_COL_IT_<iter>`
  - `FIN_CAL_GRID`
- Viewer relevance: medium (workflow/provenance diagnostics).

Radius-grid revision logs
- File: `R_REGRIDDING_LOG`
- Writers:
  - `new_main/subs/do_tau_regrid.f:75`
  - `new_main/subs/do_vel_regrid.f:133`
- Additional file in velocity regrid path: `NEW_R_GRID` (`do_vel_regrid.f:356`).

Grey scaling output (final iteration diagnostic)
- File: `GREY_SCL_FACOUT`
- Writer location: `new_main/cmfgen_sub.f:3145`
- Contains log(tau), T/Tgrey profile when grey solve succeeded.


Control Flags That Change Output Set
=======================================
Key toggles from `new_main/mod_subs/rd_control_variables.f`:
- `WRITE_RATES` (default false): controls `NETRATE`, `TOTRATE`, `EWDATA`, `LINEHEAT`.
- `WRITE_JH` (default false; set true by default for SN models): controls `JH_AT_CURRENT_TIME` writes.
- `VERBOSE_OUTPUT` (default false): enables extra diagnostic output paths.
- `DO_HYDRO`: enables hydro update outputs.
- `REV_RGRID` / `REVISE_R_GRID`: enables automatic regrid outputs/logs.
- `TRT_NON_TE` / `TREAT_NON_THERMAL_ELECTRONS`: enables non-thermal outputs.
- SN model modes (`VELTYPE 10/11` logic) enable SN/time-sequence-specific products.

Also note: `UPDATE_KEYWORD` is used in several places to modify control files (`VADAT`, `IN_ITS`, etc.) during automation. These are not science products but may change future output behavior.


Non-Thermal Outputs
======================

Non-thermal cooling summary
- File: `NON_THERM_COOL`
- Writer: `new_main/cmfgen_sub.f:4425`
- Condition: `TREAT_NON_THERMAL_ELECTRONS`
- Format: ASCII by ion, excitation/ionization cooling terms.

Non-thermal rates
- File: `NON_TH_RATES`
- Writer: `new_main/subs/non_therm/write_non_therm_v1.f90:60`
- Condition: `TREAT_NON_THERMAL_ELECTRONS` and `WRITE_RATES`
- Format: ASCII


Additional Always/Run-Level Files
====================================
- `OUTGEN` main run log (`new_main/cmfgen.f:101`)
- `WARNINGS` warning log (`new_main/cmfgen.f:108`)
- `MODEL` descriptor/config/atomic summary file (`new_main/cmfgen_sub.f:803`), with appended `MODEL_SCR` content.
- `STEQ_VALS` iterative SE/R.E. tracking (`new_main/cmfgen_sub.f:528`).

These are useful provenance sources but lower priority for first viewer visuals.


Viewer-Oriented Priority Recommendation
==========================================
Phase 1 (minimum useful viewer)
1) Parse `RVTJ` for radial structure and moments.
2) Parse `OBSFLUX` for SED/spectrum and luminosity vectors.
3) Parse `MOD_SUM` for metadata cards / run summary.

Phase 2 (composition + NLTE)
1) Parse `POP*` files.
2) Parse `*OUT` departure coefficient files.
3) Parse `GAMMAS`.

Phase 3 (advanced diagnostics)
1) `MEANOPAC`, `HYDRO`, `J_COMP`, `NETRATE/TOTRATE/EWDATA/LINEHEAT`, `CORRECTION_SUM`.
2) SN/gamma set: `SN_HYDRO_FOR_NEXT_MODEL`, `GAMFLUX`, `GAMRAY_ENERGY_DEP`.
3) Optionally add binary readers for `JH_AT_CURRENT_TIME`, `EDDFACTOR`, `ES_J_CONV` (use `_INFO` sidecars).


Existing Parser/Reader Code to Reuse
=======================================
- RVTJ:
  - `tools/rd_rvtj_v4.f`
  - `tools/rd_sing_vec_rvtj.f`
- MODEL:
  - `obs/rd_model_file.f`
- Direct-access metadata:
  - `subs/write_direct_info_v3.f` (`READ_DIRECT_INFO_V3` / `WRITE_DIRECT_INFO_V3`)
- Gamma deposition reader path:
  - `new_main/subs/get_non_loc_gamma_energy_v2.f`


Caveats and Risk Notes
=========================
1) This map is static; actual file set is option-dependent.
2) Some files are overwritten each run (`STATUS='UNKNOWN'`/`REPLACE` behavior).
3) Direct-access binaries are not portable without matching `_INFO` metadata.
4) Gamma transport includes developer/verbose diagnostic files (`./data/*`, `kevin_testing`) that may not be stable APIs.
5) Restart/internal artifacts (`SCRTEMP`, `BAMAT`, `EDDFACTOR`, etc.) are critical for continuation but not ideal first targets for a lightweight viewer.


Quick Reference: Output File Names Collected
================================================
Always/typical:
- OUTGEN, WARNINGS, MODEL, STEQ_VALS, OBSFLUX, MEANOPAC, HYDRO, MOD_SUM, RVTJ, GAMMAS

Final/species:
- POP<species>, <ION_ID>OUT, NON_THERM_COOL

Rates/diagnostics:
- NETRATE, TOTRATE, EWDATA, LINEHEAT, NEG_OPAC, J_COMP, CORRECTION_SUM, GREY_SCL_FACOUT

Restart/internal:
- SCRTEMP, POINT1, POINT2, BAMAT, BAMATPNT, EDDFACTOR, EDDFACTOR_INFO,
  ES_J_CONV, ES_J_CONV_INFO, JEW, IMPURITYJ, CHEK+CK_ON_BA_UPDATE

SN/time-dependent:
- SN_HYDRO_FOR_NEXT_MODEL, CUR_MODEL_DATA, JH_AT_CURRENT_TIME, JH_AT_CURRENT_TIME_INFO

Gamma:
- GAMFLUX, GAMRAY_ENERGY_DEP, kevin_testing, and optional verbose `./data/*` diagnostics

Hydro/regrid options:
- HYDRO_ITERATION_INFO, GREY_SCL_FAC_IN, HYDRO_OLD_MODEL, NEW_CALC_GRID,
  RVSIG_COL, RVSIG_COL_IT_<iter>, FIN_CAL_GRID, R_REGRIDDING_LOG, NEW_R_GRID


Post-Processed Observer Aliases (`cmf_flux` workflows)
======================================================
`obs_fin` and `obs_cont` are convention-driven aliases, not native writer names in the main `cmfgen` path.

Code-trace summary:
- `cmf_flux` writes `OBSFRAME` (`obs/cmf_flux_sub_v5.f:2120-2128`).
- Legacy batch flow renames `obsframe.dat` -> `obs_fin.dat`, then on a second run renames `obsframe.dat` -> `obs_cont.dat` (`opac/batobs.com:10,25`).
- The generated script path also emits `mv -f OBSFRAME obs_fin...` (`misc/create_batobs_ins.f:216`).
- Plot tools consume these names directly (`spec_plt/plt_spec.f:1123,1191`; `spec_plt/plt_many_sn_spec.f:97-99`).

Viewer implication:
- Treat `obs_fin`/`obs_cont` as aliases of `OBSFRAME` produced by specific workflows, not guaranteed standalone outputs of every run.
- Discovery logic should include `OBSFRAME`, `obs_fin*`, and `obs_cont*`.


Other Script-Created Alias Files
================================
Beyond `obs_fin`/`obs_cont`, helper scripts create staging aliases that are easy to misinterpret as native outputs.

Additional `cmf_flux` post-processing aliases (`create_batobs_ins`):
- `OBSFLUX` -> `obs_cmf*`
- `HYDRO` -> `hydro_fin*`
- `MEANOPAC` -> `meanopac*`
- `TIMING` -> `full_timing*`
- `J_COMP` -> `J_COMP*`
- `CMF_FLUX_PARAM` -> `CMF_FLUX_PARAM*`
- Optional archival aliases: `EDDFACTOR` -> `EDDFACTOR_STORE`, `EDDFACTOR_INFO` -> `EDDFACTOR_STORE_INFO`
References: `misc/create_batobs_ins.f:216-223`, `misc/create_batobs_ins.f:235-236`.

Model-startup staging aliases (`cpmod`/`drad_cpmod`/`sn_update`):
- `GAMMAS` -> `GAMMAS_IN`
- `JH_AT_CURRENT_TIME` -> `JH_AT_OLD_TIME`
- `JH_AT_CURRENT_TIME_INFO` -> `JH_AT_OLD_TIME_INFO`
- `SN_HYDRO_FOR_NEXT_MODEL` -> `SN_HYDRO_DATA`
- `CUR_MODEL_DATA` -> `OLD_MODEL_DATA`
- `GREY_SCL_FAC_IN` -> `GREY_SCL_FAC_SAVE` when copying into same directory

Generic family renames:
- Any `*OUT` files -> `*_IN` via `out2in`.
- Restart pointer promotions:
  - `NEW_POINT1` -> `POINT1`
  - `NEW_POINT2` -> `POINT2`
  - `NEW_SCRTEMP` -> `SCRTEMP`

Viewer implication:
- Distinguish native writer names from script aliases.
- Treat alias names as equivalent identities during directory scans.
