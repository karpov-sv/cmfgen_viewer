# Bstar3513 nonpositive source-opacity floor (30 October 2026)

The task is to remove the specific startup failure and hand progress back to
existing automatic remedies, without attempting full convergence. Original model:
`models/tests/model_Bstar3513`. Isolated reproduction/recovery copy:
`models/test/model_Bstar3513_opacity_test`.

## Failure and cause

The imported Linux run `20261030T133652Z-6df748b4` records NaN luminosity in
iteration 1 and a subsequent SCRTEMP record with all 200,970 populations
nonfinite. That record is not a usable restart.

Local macOS runs `20261030T145319Z-5de31463` and
`20261030T152101Z-2feff558` trap in the same `log()` call inside
`FG_J_CMF_V13`. Crash reports, executable disassembly, and symbol addresses
identify the `LOG_CHI_EXT=LOG(CHI_EXT)` loop. The last printed frequency precedes
the offending frequency; it is not the actual crash frequency.

The main caller already attempts to limit negative opacity. However, the
`NEG_OPAC_OPT=SRCE_CHK` branch selects

```fortran
CHI(I)=0.1_LDP*ETA(I)*CHI_NOSCAT(I)/ETA_CONT(I)
```

When absorption `CHI_NOSCAT` is negative, positive emissivities do not make this
a positive floor. The source branch bypasses the following scattering-floor
`ELSE IF`. Original-grid negative opacity then reaches logarithmic interpolation;
refining the formal-ray grid cannot repair the invalid logarithm at that node.

## Real reproduction with the new native guard

Native run `20261030T162613Z-3e9b69e1` in the isolated copy used five threads
and a one-iteration request. It stopped after 2,159.6 seconds, before transfer
could use the nonpositive floor and before a population solve/checkpoint write.

| Measurement | Value |
| --- | ---: |
| Iteration / original model depth | 1 / 75 |
| Frequency, 10^15 Hz | 0.39986577825814823 |
| Selected SRCE_CHK floor | -0.049671642925760338 |
| Continuum opacity | -0.059655662538557863 |
| Absorption opacity, CHI_NOSCAT | -0.49657636028801083 |
| Emissivity | 0.0031517238076133867 |
| Continuum emissivity | 0.0031508350536278732 |
| Electron scattering, CHI_SCAT | 0.43692069774945297 |
| Existing ESEC_CHK floor, 0.1*CHI_SCAT | +0.043692069774945297 |

The negative floor matches the value inferred from the latest macOS crash
registers. The guard replaces the opaque crash/NaN propagation with a precise
nonzero stop; it does not change valid opacities or disable floating-point traps.
The first diagnostic process had imported the runner before the new parser was
written. Its immutable native logs were reanalyzed by the current parser for
remedy selection; the original result journal was not edited.

## Automatic rule and bounded test

`source_opacity` requires the native marker plus complete finite measurements,
negative absorption, and a representable positive scattering floor. Other
nonfinite/checkpoint errors take precedence. A generic crash cannot trigger it.
The rule selects native `ESEC_CHK`, sets fresh BA controls, and retires BA and
Eddington caches. It never reseeds populations, changes structure, or disables
the luminosity safeguard. One application per automatic invocation is allowed.
The usual numerical/fresh-Jacobian acceptance remains required.

The production policy and action functions selected/applied the remedy to the
real failed run's evidence, recorded in the isolated copy's
`.opacity-recovery-trial/diagnosis.json` and action directory. The subsequent
ordinary automatic controller starts at `20261030T170342Z-auto-d22fc59b`, using
two-iteration batches, five threads, a 20-iteration/eight-attempt ceiling, and an
early-stop callback at the first validated batch or existing-remedy handoff.
This intentionally avoids trying to converge the atmosphere. The first failure
was not injected into the auto controller: it is the separate real diagnostic
run. Child-process regressions independently cover failure-to-remedy execution
through the complete automatic controller.

The ESEC-only radiation sweep passed the exact failing frequency with positive,
finite stored mean intensities at all 90 depths (EDDFACTOR record 74684, minimum
7.822080349879742e-15 and maximum 0.05087718991794897). The sweep then failed the
luminosity safeguard: normalized luminosity spans -204.39 (depth 75) to 188.11
(depth 65), with outer value 144.21. There was no population solve or accepted
checkpoint. Startup hydro correctly declined this nonpositive profile. ESEC_CHK
therefore removes the logarithm failure but alone does not establish a usable
initialization.

A second isolated copy, `models/test/model_Bstar3513_lte_seed_test`, was initialized
with LTE populations, `T_EXC=1`, `LIN_INT=F`, and `IT_ON_T=F`; no grey-temperature
iteration was done. Zero-iteration native test `20261030T172738Z-a86837f2` passed.
Ordinary interpolation/POP controls were restored before continuation. Native
POP zero-test `20261030T173335Z-881a0763` in the inactive first copy establishes a
comparison baseline: geometry and all temperatures are **identical**, element
sums differ by at most 4.66e-15, and the LTE seed's charge error is 1.11e-15.
This experiment changes the initial populations while preserving the temperature
and structure, unlike the earlier LTE/grey test on Bstar3512.

Guarded continuation `20261030T172858Z-auto-3b085895` still failed before a
population solve: normalized luminosity ranged from -0.0063071 to 510.5.
The existing formal-ray remedy (`VFRAC_FG=0.1`, moment grid unchanged), tested as
`20261030T175516Z-auto-5975fc8f`, likewise failed (-0.045474 to 512.73).
Neither experiment justified accepting a checkpoint or bypassing the guard.

### Matching LTE/hydro temperatures

The model already contains `lte/FIN_CAL_GRID` with temperatures 1.3862–4.7928
(in 10^4 K), compared with the inherited profile's 1.0267–3.9049. Its paired
`lte/RVSIG_COL_NEW` is byte-identical to the promoted root hydro grid. All 90
radii and velocities, target TEFF/LOGG/LSTAR/MDOT and abundances agree. The
LTE output header also reports the correct luminosity (84000), mass and radius;
stale LSTAR/MASS entries in HYDRO_PARAMS are not consumed by wind_hyd.

A separate copy `models/test/model_Bstar3513_lte_structure_test` used native
`LTE_EST=T, LIN_INT=F, DC_METH=LTE, IT_ON_T=F` for a zero-iteration initialization
(`20261030T182320Z-468523b1`). All ordinary controls were restored afterward.
Initial charge error was 9.99e-16. Guarded two-iteration continuation
`20261030T182404Z-auto-e73e73ae` completed both solves. Its first radiation sweep
passed the factor-of-two safeguard: at Rosseland depth ≥1 the normalized
luminosity was 0.93154–1.2392, and at depth ≥10 it was 0.93154–1.1655.

**This trial checkpoint was not promoted.** Binary-record audits against its
own initial checkpoint show element loss after ordinary capped population
updates: maximum relative element drift was 0.001052 after the first full solve
and 0.766981 after the following Lambda step. The latter's charge error was
0.000309569, above the existing 1e-6 recovery limit. Positive populations and a
successful native exit alone do not establish a conservative bootstrap.

The production zero-initialization API independently reproduced the exact
reviewed LTE/hydro temperatures in `20261030T183538Z-bd681184`, in
`model_Bstar3513_opacity_test`. It restored VADAT and removed its temporary root
FIN_CAL_GRID, retained the consumed source/provenance in the journal, and passed
the unchanged strict charge check. This healthy checkpoint 1 is retained
separately from the unsuccessful ordinary-update trial.

The existing three-step fixed-T Lambda population bootstrap (`MAX_LAM=1e12`,
fresh BA, no Ng), run from that healthy checkpoint as
`20261030T190400Z-c64dd492`, **passed its unchanged strict validator**. Raw maximum
corrections fell from 1.01e26% through 1.88e14% to 1030%. Temperature and geometry
were unchanged; final maximum relative element drift was 4.66294e-15 and charge
error was 1.55431e-15. Intermediate records were explicitly provisional: after
step 1 element drift was 0.0777039 and charge error 1.45725e-5; after step 2 these
were 4.22506e-5 and 1.82034e-8. The third solve filled the remaining capped tiny
populations and restored the conservation equations.

The new `opacity_lte_seed` recipe therefore retains the zero seed, three Lambda
steps and full-step verification as one provisional procedure. A stop, budget
limit, or failed conservation/full-step check rolls back the whole recipe. The
native three-step trial's conserved checkpoint 4 is also independently retained
in `.healthy-bootstrap/` before testing ordinary continuation. Two normal
iterations `20261030T191831Z-44353fbc` then **completed successfully**. Iteration 5
was a full variable-temperature fresh-BA solve (raw maximum increase 4.04e6%);
iteration 6 used the ordinary native Lambda/grey fallback (maximum increase
3580%). The final checkpoint conserves elements to 3.55271e-15 relative to the
bootstrap and charge to 1.11022e-15. Relative to the original LTE seed, maximum
element drift is 4.21885e-15. Both radiation sweeps retained STOP_IF_MW.

The existing full-step validator correctly returns `VerificationPending`:
only one of these two solves was full/free-temperature. An uninterrupted
`opacity_lte_seed` recipe would continue its existing repeatable full-check
phase within the shared budgets. This is **not** numerical convergence or proof
of a steady convergence trend; corrections and luminosity errors remain large.
It establishes that the opacity/initialization failure is overcome without
publishing the earlier abundance-drifting trial, and ordinary automatic remedies
can handle the subsequent progress.

## Handoff to the actual model

The original 54 reviewed inputs (52 excluding VADAT/IN_ITS) still matched their
initial snapshots. Checkpoint 6, its matched native outputs and the persistent
`NEG_OPAC_OPT=ESEC_CHK, COMP_BA=T, N_FIX_BA=0, FIX_BA=0.0` controls were transferred
to `models/tests/model_Bstar3513`. Initial population inputs, structure, atomic
links and original IN_ITS were retained. Obsolete per-depth BC/DS matrix scratch
and ASCII BA diagnostics were retired; these reconstructible caches were not
copied from the trial. All replaced files and original reviewed inputs were
backed up first in:

`models/tests/model_Bstar3513/.cmfgen-recovery/bstar3513-bootstrap-handoff-20261030T231624Z/`

`handoff.json` records file hashes, source runs, conservation checks and retired
cache metadata; `next-auto-check.json` records the post-transfer check. Automatic
preflight passes in continuation mode with checkpoint 6 and an authenticated
repaired executable. The existing registry selects `continue`; no further
native run was started in the main folder. Resume without a fresh start:

```bash
python cmfgen_run.py models/tests/model_Bstar3513 --stage main --auto --iterations 5
```

The investigation stops at this handoff rather than attempting convergence.

## Installation and validation

The installed local source guard is in `~/CMFGEN2023/cur_cmf/new_main/cmfgen_sub.f`.
Rollback backup:
`~/CMFGEN2023/cur_cmf/.cmfgen-backups/20261030T170255Z-source-opacity-guard/`.
The atmosphere executable SHA-256 is
`2b2c7a19e6c30e2146b9134203a0bafb85a22110a973b48f1eb23e9c9e852de9`.
All scientific source hashes match the updated consolidated patch manifest.
Executables were atomically relinked and the authenticated build record updated.
Local compiler/linker settings were retained.

The consolidated patch applied and reversed against release 18jun25, with all
47 before/after file hashes checked. The incremental source-opacity guard patch
is also supplied for installations already carrying fixes 1–31.

The regression driver `cmfgen-review-tests/check_source_opacity_guard.py`
extracts the actual limiter block. Seven cases pass at both O0 and O2 with
invalid/zero/overflow traps: invalid negative/zero source floors stop; the native
ESEC floor is positive; ordinary source limiting and unchanged positive opacity
retain their original behavior; limiter/derivative-control flags remain correct.
Runner regressions cover diagnosis, malformed/stale evidence, unrelated or mixed
crashes, one-time selection, cache requests, continuation preservation, advisory
integration, and independent convergence verification.


## LTE-start variant Bstar3513.2 (31 October 2026)

The copied variation `models/tests/model_Bstar3513.2` has a promoted, matching
LTE/hydro grid, explicit `DC_METH=LTE, LIN_INT=F, T_EXC=1`, and `IT_ON_T=T`.
It does not select `LTE_EST=T`. Its latest native run
`20261030T232831Z-93cba59c` (journals retain the original pre-copy folder name)
confirms LTE initialization and charge consistency, performs grey-temperature
refinement and stops at the first radiation sweep before any population solve.
The exit code is zero, but normalized luminosity spans -5.0188 to 512.21 with
inner Rosseland depth 102.6. Automatic run
`20261030T232827Z-auto-962fe8af` correctly rejects the failed output, then finds
no eligible remedy because the thermal-seed rule previously required POP.

Rebuilding LTE/hydro alone does not select its temperatures for main. The native
initialization reads the inherited `T_IN` profile unless the FIN_CAL_GRID branch
is enabled. The log shows initial core temperature 3.9048744, followed by grey
refinement corrections as large as 76.5%. The model's matching FIN_CAL_GRID spans
1.3862–4.7928. The existing guarded thermal-seed recipe is now extended to an
explicit LTE start, requiring both native LTE/charge markers, complete fresh
negative luminosity evidence and validated local LTE/hydro provenance. It
refuses a continuation or a start already using that profile without grey
refinement. Initialization controls are restored, and the same strict
Lambda/bootstrap/full-verification and rollback procedure follows.

A read-only replay of the actual archived failure selects `opacity_lte_seed`
version 2. All archived input bytes still match the copied model, and OBSFLUX /
MEANOPAC timestamps lie within the native attempt. The replay record is
`models/test/model_Bstar3513_2_lte_seed_test/.archived-failure-diagnosis.json`;
it is diagnostic analysis, not a newly executed automatic run.

Native zero-iteration test `20261031T001821Z-2bdda039` ran in the isolated
input-only copy `models/test/model_Bstar3513_2_lte_seed_test`. It selected the
reviewed LTE/hydro temperatures with no grey iteration and passed the strict
charge check (9.99201e-16). Its complete SCRTEMP is **byte-for-byte identical**
to the initial LTE/hydro checkpoint used in the successful previous bootstrap
and two-solve continuation experiment above. Geometry, temperature and element
densities match exactly. The runner restores original LTE controls and removes
the temporary FIN_CAL_GRID. No radiation iterations were repeated for this
validation, and the original variation was not modified.

The copied variation currently has an absolute T_IN link into the former model
folder. The Python runner rebuilds its reviewed links before starting; the
isolated native test confirms T_IN resolves to its own He2_IN. No manual link
repair or permanent initialization-control change is needed to retry with the
updated automatic runner:

```bash
python cmfgen_run.py models/tests/model_Bstar3513.2 --stage main --auto --iterations 5
```

The retry will first encounter the same guard, then select the new eligible
thermal recovery. Source-floor repair remains a separate rule and changes
NEG_OPAC_OPT only from its own typed native evidence. The LTE thermal remedy
does not disable STOP_IF_MW or declare convergence.
