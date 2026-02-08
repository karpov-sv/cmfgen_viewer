# Parser Implementation Queue

## Objective
Define a concrete, execution-ready parser roadmap for files that currently do not have structured viewers.

## Baseline (Already Implemented)
- `RVTJ`
- `OBSFLUX`
- `MOD_SUM`

## Ticket Definition of Done
For each ticket below:
- parser integrated in `cmfgen_viewer/parsers/` and registered in `PARSERS`,
- parsed summary table is visible in UI,
- at least one meaningful table/plot is shown when data permits,
- malformed/partial input produces non-fatal parser warnings,
- parser does not regress raw view fallback.

## Phase 1: Highest Priority Text Parsers

### P1-01 `MEANOPAC`
Scope: parse depth-wise opacity/tau diagnostics and core columns.
Acceptance: summary + table + opacity/tau profile plots.

### P1-02 `HYDRO`
Scope: parse momentum/force-balance terms by depth.
Acceptance: summary + term comparison plots + mismatch warnings.

### P1-03 `OBSFRAME`
Scope: parse observer-frame synthetic spectrum output.
Acceptance: wavelength/frequency spectrum plot with axis toggles.

### P1-04 `OUT_FLUX`
Scope: parse run log milestones, warnings, and completion state.
Acceptance: timeline-like summary table + extracted warning list.

### P1-05 `GAMMAS`
Scope: parse mean ionic charge profiles by species.
Acceptance: species-selectable profile plot + species table.

### P1-06 `POP*` Family
Scope: generic parser for species population files.
Acceptance: per-species depth profile plots and key header metadata.

### P1-07 `*OUT` Family
Scope: generic departure-coefficient parser.
Acceptance: parsed physical columns and log/linear coefficient plots.

## Phase 2: Diagnostic and CMF_FLUX Text Parsers

### P2-01 `J_COMP`
Scope: parse boundary J consistency diagnostics.
Acceptance: J(moment) vs J(ray) comparison plots and residual stats.

### P2-02 Rate Files `NETRATE` `TOTRATE` `EWDATA` `LINEHEAT`
Scope: shared rate parser framework for related formats.
Acceptance: consistent table layout + filterable/plot-ready vectors.

### P2-03 `TRANS_INFO` and `SOB_FORCE_MULT`
Scope: parse transfer and Sobolev-force diagnostics.
Acceptance: key scalar extraction + profile/summary plots.

### P2-04 `GAMFLUX` and `GAMRAY_ENERGY_DEP`
Scope: gamma transport outputs (spectrum + deposition profiles).
Acceptance: spectrum/deposition panels with units-aware labels.

### P2-05 CMF_FLUX Support Text Files
Scope: `OUT_PARAMS`, `CFDAT_OUT`, `CONT_FREQ`, `OBS_FREQ`.
Acceptance: parsed diagnostics tables and preview plots where relevant.

## Phase 3: Direct-Access/Binary Parsers

### P3-01 `_INFO` Sidecar Reader Infrastructure
Scope: implement shared direct-access metadata decoding (`RECL`, word-size, endian).
Acceptance: validated loader used by all binary parser tickets.

### P3-02 `ETA_DATA` `CHI_DATA` `RAY_DATA`
Scope: parse primary direct-access transfer fields.
Acceptance: indexed extraction and profile/slice visualization.

### P3-03 `FLUX_FILE` `CMF_FORCE_DATA` `SOB_FORCE_DATA`
Scope: parse direct-access force/flux products.
Acceptance: profile tables + force/flux plots.

### P3-04 `IP_DATA` `RTAU_DATA` `ZTAU_DATA` `dFR_DATA`
Scope: observer-frame auxiliary direct-access outputs.
Acceptance: parsed diagnostic panels linked from `OBSFRAME` context.

### P3-05 Reuse/Continuation Diagnostics
Scope: `JH_AT_CURRENT_TIME`, `EDDFACTOR`, `ES_J_CONV` (with `_INFO`).
Acceptance: read-only diagnostics with graceful fallback when sidecars are missing.

## Recommended Execution Order
1. P1-01
2. P1-02
3. P1-03
4. P1-04
5. P1-05
6. P1-06
7. P1-07
8. P2-01
9. P2-02
10. P2-04
11. P2-03
12. P2-05
13. P3-01
14. P3-02
15. P3-03
16. P3-04
17. P3-05
