# Bstar3512 startup luminosity failure (28 October 2026)

Two distinct model directories were inspected: `models/tests/model_Bstar3512`
(the imported fresh-start model) and `models/test/model_Bstar3512` (the copy
with the manually completed guard-disabled iteration). Neither was modified
by this investigation.

## Runner bookkeeping failure

The imported model's `T_IN` link pointed to a foreign-machine `/i/POEMS/...`
path. The reviewed runner recipe replaced it with the local `He2_IN`. The
source contents were unchanged, but automatic mode compared the repaired link
against its pre-run missing-file snapshot and incorrectly reported an external
edit. This secondary error obscured the native luminosity safeguard failure.

Commit `3116487` adopts tracked links immediately after reviewed runner setup,
before executing solver code or caller callbacks. Source contents remain
protected. Later removal or retargeting is rejected even when another target
contains identical bytes. Tests cover absent, broken, and stale links, real
source edits, link removal, and identical-content retargeting.

## Native failure and the guard-disabled experiment

| State | Evidence |
| --- | --- |
| Fresh POP startup, guarded | Stops in radiation iteration 1, before SOLVEBA. Normalized luminosity minimum 0.44761 at depth 68, Rosseland depth 1.455; inner Rosseland depth 97.51. |
| One fresh iteration with `STOP_IF_MW=F` | Native run `20261028T162324Z-b683fb5f` completes and exports a checkpoint at iteration 1. Largest raw population increase 1.47e11%; largest decrease 6.94e4%; reported major-species scale 0.027383. Completion does not establish a stable atmosphere. |
| Guard restored for continuation | Native run `20261028T170404Z-9cd232b6` stops during radiation iteration 2 before its population solve. Normalized luminosity minimum 0.28115 at depth 72, Rosseland depth 4.16; maximum 1.1366; inner Rosseland depth 103.1. Automatic mode restores the accepted iteration-1 checkpoint. |

The deficit worsened after the first population solve and shifted deeper.
This is not evidence that one unguarded startup step cured the problem. The
Rosseland depth is adequate, so the guard is not reporting a shallow inner
boundary. A native exit code of zero does not establish success: Fortran STOP
can terminate the luminosity check with that code.

## Why existing automatic remedies decline

`DO_HYDRO=T`, but `HYDRO_DEFAULTS/N_ITS=0`: no hydrostatic revisions are actually
scheduled. The hydro-bootstrap policy requires a reviewed continuation and a
revision explicitly scheduled at the stopped iteration; those prerequisites
are absent in the fresh run, and the schedule is still absent after iteration 1.
The ray-refinement policy is restricted to demonstrated negative-luminosity
transport collapse on a fixed structure. This positive luminosity deficit is
outside that evidence, and `DO_HYDRO=T` also excludes that policy.

## Initialization evidence

The source input radius is `405.8490343`, matching Bstar3511
(nominal `TEFF=1.25`). The input is not byte-identical to its current `He2OUT`,
so an exact export iteration has not been established.
The new target specifies `TEFF=1.38`, `RSTAR=332.986303347`, with the same
`LSTAR=84000`. These are model input parameters, not independently measured
photospheric temperatures. The new `RVSIG_COL` also records the radius change.

The active startup controls are `LIN_INT=T`, `POP_SCALE=T`, `DC_METH=POP`.
`SET_NEW_MODEL_ESTIMATES` interpolates source temperature and population fractions
in this branch. Its initial grey-temperature loop explicitly requires
`.NOT. GRID`. Consequently `IT_ON_T=T` is ineffective here; toggling it alone
would not test the thermal initialization. The POP reader's conservation checks
do not imply radiative equilibrium on a changed target structure.

An isolated zero-iteration POP test reproduced startup successfully. Its
exported temperature at depth 68 is 11289 K and at depth 72 is 14225 K. After
the manually completed iteration 1, the corresponding temperatures are 12307 K
and 15770 K, but the luminosity deficit is worse. This implicates the coupled
thermal/population/structure startup rather than proving temperature alone is
the cause. No general safeguard-bypass remedy is established by these data.

## Bounded diagnostic runs

Temporary copies are under `/private/tmp/bstar3512-startup-7pjr3m8p`, with no
binary continuation copied in. The installed patched executable was used with
two threads and a 240-second timeout per zero-iteration test:

- `pop`: original controls, `STOP_IF_MW=T`; startup test passed.
- `lte-grey`: `LIN_INT=F`, `DC_METH=LTE`, `T_EXC=1.38`, retaining `IT_ON_T=T` and
  `STOP_IF_MW=T`; startup test passed in about 225 seconds. This exercises the
  initial grey-temperature loop instead of copying the source thermal structure
  directly. Temperature at depth 68 is 15104 K and at depth 72 is 18494 K;
  innermost temperature is 40863 K, against 37679 K in the POP initialization.
- `lte-tau` (directory label only): `LIN_INT=F`, `DC_METH=LTE`, `T_EXC=1.38`,
  `IT_ON_T=F`; startup test passed. The native default `T_ON_R=T` remained
  active, so this did not select spherical-optical-depth interpolation. Its
  temperatures match the POP seed, confirming that selecting LTE alone does
  not refine the copied thermal profile.

These are initialization diagnostics, not convergence or luminosity-guard
verification runs. A subsequent real radiation iteration with the guard enabled
is necessary to assess any alternative startup.


## Prepared next radiation test

`models/test/model_Bstar3512_lte_grey_test` contains a copy of the successful
LTE/grey initialized state. `T_IN` points to that copy's own `He2_IN`,
`NUM_ITS=1`, and `STOP_IF_MW=T`. The binary checkpoint passes the existing
restart checks; native counter 1 represents initialization, with no radiation
iteration yet. It has not been substituted into either original model.

Run ordinary **main**, one additional iteration, automatic mode **off**, fresh
start **off**, with the usual thread pool. This continues the initialized
checkpoint and avoids repeating grey initialization. No guarded radiation
iteration of this alternative has been run in this investigation. Both
population initialization and temperature refinement change in this test;
success would not isolate temperature as the sole cause.

## First guarded LTE/grey radiation test: failed

The user ran `models/test/model_Bstar3512_lte_grey_test` for one main iteration.
Native run `20261028T191035Z-97092c65` stopped in radiation iteration 2, before
the population solve. The runner correctly reports `invalid_output` despite
native return code 0. `POINT1` still selects initialized counter 1; this attempt
did not produce a new solved checkpoint.

The normalized luminosity spans **-3.558 to 1224.8**. Its minimum is at depth 71
(Rosseland depth 2.727), and its outer maximum is at depth 1. From Rosseland
depth 0.5 inward, the range is -3.558 to 13.333. The inner Rosseland depth is
93.91. Logged emergent luminosity is 1.0276e8 Lsun against 84000 Lsun requested.
The initial grey-temperature adjustment therefore did not solve the problem.

The fresh J_COMP has an approximately 200% moment/ray discrepancy in the UV
at 0.12489 microns, versus 5.53% maximum in the optical band. These are
outer-boundary J comparisons, not direct emergent-flux errors. Negative
luminosity together with the coarse `VFRAC_FG=20000` now resembles the previously
demonstrated ray-transport collapse, unlike the earlier positive-only deficit.
This is a hypothesis to test, not proof of the same cause.

The next controlled experiment should keep this initialized checkpoint and
`STOP_IF_MW=T`, refine only the formal-ray spacing to `VFRAC_FG=0.1` (leaving
`VFRAC_MOM=20000`), rebuild BA, and retire the incompatible BA/EDDFACTOR caches.
For an explicitly fixed-structure trial, set `DO_HYDRO=F`; the existing
`HYDRO_DEFAULTS/N_ITS=0` already schedules no hydro revisions. Do not perform
another LTE reseeding or bypass the guard. This experiment has not been
prepared or launched in this check.

## Refined formal-ray test: completed, safeguard still fails

With user authorization, `models/test/model_Bstar3512_refined_ray_test` was
created from the exact LTE/grey initialized checkpoint, excluding BA and radiation
caches. It retained `STOP_IF_MW=T` and `VFRAC_MOM=20000`, changed
`VFRAC_FG=0.1`, requested fresh BA (`COMP_BA=T`, `N_FIX_BA=0`, `FIX_BA=0`), and
set `DO_HYDRO=F` for an explicitly fixed structure. Native run
`20261028T194111Z-c4adef30` used 10 threads and completed its radiation sweep in
about 27 minutes, stopping before the population solve.

| Measurement | Coarse formal rays | Refined formal rays |
| --- | ---: | ---: |
| Minimum normalized luminosity | -3.558 | -3.5602 |
| Maximum normalized luminosity | 1224.8 | 1231.2 |
| Depth of minimum | 71 | 71 |
| Largest UV outer J(mom)/J(ray) discrepancy | 199.99% | 199.99% |
| Largest optical discrepancy | 5.53% | 3.69% |

Individual UV features change, but the integrated failure is essentially
unchanged. Negative luminosity alone is therefore insufficient to identify the
previously demonstrated coarse-ray remedy as a cure for this LTE seed. No
population solve or new checkpoint was accepted in this experiment.

A bounded zero-iteration comparison with `T_EXC=1.0` also completed in a temporary
copy. `T_EXC` is an excitation floor, not the target effective temperature.
The resulting grey startup has temperatures of 16387 K and 19347 K at depths
68 and 72. No radiation test of this lower-floor seed has yet been performed.

## Scheduled hydro experiment

The next controlled experiment uses the original, manually completed POP
checkpoint at iteration 1, not an LTE seed. The copy is
`models/test/model_Bstar3512_hydro_test`. It schedules one hydro revision with
`N_ITS=1`, `STRT_ITS=2`, `ITS_DONE=0`, retains `DO_HYDRO=T`, and uses fresh BA.
The existing one-iteration `hydro_recovery_probe` temporarily sets
`STOP_IF_MW=F`; restoration is owned by the runner. A two-iteration follow-up
with the guard restored is required before treating the recovery as verified.
A full baseline of coupled controls/checkpoint/output files is retained in the
copy's `INVESTIGATION` directory and restored if the sequence fails.

This tests a structural correction that could not occur when `N_ITS=0`.
It does not assume that merely bypassing the guard repairs energy balance.
Both original model folders remain untouched.

## Scheduled hydro result: safeguard recovery verified, convergence not reached

The bridge (`20261028T201031Z-1e1850e2`) completed radiation/population iteration
2 and one hydro revision, saving counter 3. It changed RSTAR to 318.74691455,
updated RVSIG_COL, consumed the one scheduled revision (`N_ITS=0`, `ITS_DONE=1`),
and restored `STOP_IF_MW=T`.

The guarded follow-up (`20261028T204020Z-4925b083`) completed iterations 4 and 5
with the guard enabled. Final normalized luminosity is **0.7726–1.2116** and
inner Rosseland depth is **74.34**. This verifies recovery past the fatal
luminosity safeguard, not radiative equilibrium or convergence. Nonfatal
25% luminosity warnings and hydrostatic-balance residuals remain.

The population problem remains substantial: iteration 4 is a full,
variable-temperature step with maximum raw increase 3.98e19%; iteration 5 is
fixed-T Lambda with maximum raw increase 2.35e21%. Both used fresh BA. The
selected iteration-5 checkpoint is finite and positive, with relative charge
error 9.46e-14, but that alone does not establish population convergence.

A read-only audit of earlier records in SCRTEMP finds maximum element-sum
changes of about 2.96e-6 from counter 3 to 5 and up to 0.001249 from counter
4 to 5. These comparisons fail the strict 1e-6 conservation tolerance used by
the existing population-bootstrap validator. The largest counter-4-to-5 change
is for MODEL species index 22 at depth 56. This does not establish permanent manganese loss: the counter-3-to-5 offset
is nearly common to all elements, and the larger counter-4-to-5 change can
include restoration of normalization. These cross-step comparisons are not a
substitute for a controlled, fixed-structure bootstrap conservation audit.


## Bounded population recovery trial

After checking the completed hydro result, a separate copy at
`models/test/model_Bstar3512_population_test` was initialized from counter 5.
It explicitly sets `DO_HYDRO=F` after the scheduled hydro revision is exhausted,
retains `STOP_IF_MW=T`, and invokes the existing population-recovery probe:
three fixed-T Lambda steps with `MAX_LAM=1e12`, followed by two full,
variable-temperature fresh-BA steps. The original temporary-control lifecycle
restores ordinary controls on every exit. Existing validators require declining
uncapped corrections, positivity, charge/element conservation, fixed T during
Lambda, and two actual full steps afterward. Failure restores this trial's
counter-5 baseline; the hydro experiment itself is not modified.


## Auto-mode handoff

The extra manual population trial was stopped at the user's request because
that recovery is already implemented in automatic mode. Its separate copy was
restored to counter 5. It did not establish a new verified population state,
and no automatic job was launched; the user will run the auto-mode test.

The workflow now implements `startup_hydro` for the demonstrated missing-startup
revision case, including an audited POP seed when fresh startup has no binary
checkpoint. It also recognizes an explicitly exhausted hydro schedule as fixed
for existing population/ray remedies. The actual hydro-recovered counter-5
state is eligible for the existing three-Lambda/two-full population bootstrap.
Full model convergence is outside this investigation's objective.

## First complete automatic test and deferred population verification

Automatic run `20261029T002100Z-auto-96e10e5d` successfully selected and verified
`startup_hydro`, including fresh POP seeding and guarded hydro follow-up. It
then selected the existing population bootstrap. Its three Lambda steps reduced
maximum raw increases from 2.41e17% to 1.29e11%, passing element conservation
(maximum relative change 7.79e-12) and charge conservation (1.44e-15).

The next batch had a full variable-T solve at iteration 9 and native fixed-T
Lambda fallback at iteration 10. Both native steps succeeded. The old fixed
verification validator rejected the mode mismatch and rolled the population
procedure back to counter 5, retaining the successful hydro recovery.

Population full-step verification now defers, rather than fails, after such
physically audited native fallback. The same step repeats within shared budgets
until two consecutive full variable-T fresh-BA steps are observed. Physical
comparisons stay anchored to the first verification baseline, and the whole
procedure remains provisional until then. Budget exhaustion, interruption, or
physical failure still rolls back. Independent convergence acceptance is unchanged.
No real model run was launched while implementing this verification fix.
