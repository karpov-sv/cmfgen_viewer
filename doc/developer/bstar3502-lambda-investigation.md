# Bstar3502 lambda-iteration investigation — 2026-10-21

## Installation and workflow follow-up — 2026-10-24

The validated line/BA, LTE startup, grey-intensity and Ng guard repairs are now
applied to the installed source; atmosphere and spectrum executables have been
rebuilt. The main model remains unchanged. Statements below about untouched
installed source describe the earlier isolated investigation. Use
[the consolidated source record](cmfgen-source-fixes.md) and
`patches/cmfgen-current.{patch,json}` for the current installation status.
The auto registry now covers refined formal rays, superlevel T coupling,
physically checked fixed-T Lambda bootstrap, explicit post-save large-change
safeguard recovery and first-Ng batch cadence. Experimental transport recorders,
alternative Q integration and unvalidated moment-grid changes were not installed.

## Investigation scope — 2026-10-24

**The original-instability investigation can conclude without fully converging
this model.** Matched source/input tests identify actual defects and the
superlevel-temperature coupling remedy; the repaired branch now progresses
steadily, including a fresh-process restart. Physical checks continue to pass.
There is no observed recurrence of the original transport collapse or outer
thermal cycle in this recovery branch. Formal convergence and an independent
final saved-state radiation probe were additional conservative targets, not
necessary evidence for this causal conclusion.

At accepted101, the all-variable maximum is .2530594% and11818 variables exceed
.02%; both decrease steadily. The native outer luminosity remains about .455%
above its target. This stable offset remains an accuracy observation, not an
identified cause of the original instability. No exact radiative-transfer or
formal-convergence certificate is claimed. The separately reproduced Ng guard
safety issue remains documented and experimental; its actual93-event effect
is small and does not explain the original failure.

No further native jobs are planned solely to reach EPS. The already-running
bounded ten-step continuation may finish under its original six-hour guard;
its existing wrappers retain actual success/failure and physical diagnostics.
Installed source/executables and the actual main model remain unchanged; the
successful recovery described here belongs to the isolated diagnostic branch.

## Current assessment — 2026-10-24 13:09 UTC

**Not converged. Full101 is healthy;102 is running.** The isolated ten-step
`original97-sl-temperature-fresh-full10` retains unchanged physics/EPS and
LAST_NG94 (native90491, runner93470, monitor80734, radiation observer23204).
All four completed full/variable-T/fresh-BA steps98–101 pass their gates.
Full101 took2600.23s (~43.3min), longer than99/100 (~27.5min). The ten-step
budget and21600s guard remain unchanged; actual time margin needs continued
monitoring. Main model and installed source/executables remain untouched.

Full101 raw maximum .2530594%, T .000378099%, Ne .000114923%, zero>1%,10%
or100%,11818>.02%, no negative targets. All saved variables equal unlimited
Newton targets bitwise, original geometry unchanged, charge/abundance≤2.22e-15.
Among populations initially≥.01Ne, maximum .00640835%, none>.02%;≥1e-6Ne
maximum .0272958%, only one>.02%. The strict all-variable gate still fails,
so further healthy continuation and final verification remain necessary.

| Full solve | Raw all-variable max (%) | Raw T max (%) | >100% | >10% | >.02% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 82 | 1012.68 | 0.843411 | 4 | 11776 | 154358 |
| 83 | 290.42 | 0.25875 | 22 | 6671 | 147333 |
| 84 | 33.4069 | 0.0424533 | 0 | 1180 | 135346 |
| 85 | 24.4894 | 0.0244157 | 0 | 255 | 127423 |
| 86 | 18.3491 | 0.0187151 | 0 | 97 | 120957 |
| 87 | 13.9427 | 0.0191284 | 0 | 45 | 116159 |
| 88 | 10.7981 | 0.0194566 | 0 | 10 | 110643 |
| 89 | 8.45843 | 0.0185486 | 0 | 0 | 106178 |
| 90 | 6.69985 | 0.0170245 | 0 | 0 | 100251 |
| 91 | 5.35031 | 0.0152755 | 0 | 0 | 95389 |
| 92 | 4.30159 | 0.0135598 | 0 | 0 | 91795 |
| 93 (pre-Ng) | 3.47748 | 0.0119032 | 0 | 0 | 89899 |
| 95 (post-Ng) | 2.56308 | 0.0101243 | 0 | 0 | 91395 |
| 96 (post-Ng) | 0.78029 | 0.00141444 | 0 | 0 | 66159 |
| 97 (post-Ng) | 0.54263 | 0.00078236 | 0 | 0 | 55362 |
| 98 (fresh process) | 0.446366 | 0.000659108 | 0 | 0 | 43266 |
| 99 | 0.369636 | 0.000534004 | 0 | 0 | 30176 |
| 100 | 0.306091 | 0.000446964 | 0 | 0 | 20702 |
| 101 | 0.253059 | 0.000378099 | 0 | 0 | 11818 |

These are exact full raw-vector counts, including arbitrarily small populations,
Ne and T. They are distinct from the native scheduling MAXCH, which can exclude
a small number of largest changes:100 native MAXCH is.28723054%. The current
trajectory and CSVs are retained as `root-cause-v1/figures/bstar3502-sl-temperature-recovery.{png,svg,csv}`. The depth88 snapshot also
shows that the residual is not exclusively tiny populations: HeI ground-state
correction1.6729% atdepth30 starts from .01617Ne.

### Established findings and effective adjustments

- Matched original-checkpoint tests prove Lambda/weak-line and distinct-
  superlevel strong-line cancellations in the actual model's Jacobian. Separate
  physical shared-superlevel tests identify an original aliased-pointer defect
  and a regression in the first experimental guarded repair for the native
  default separate-pointer layout. The final kernel covers both layouts and
  passes8250 physical comparisons. The shared correction alone did not remove
  the model's outer T cycle. Exact mid-2023 source retains the original defects,
  not our intermediate-candidate regression; rollback alone does not remove the
  reproduced original cancellations.
- Refined ray sampling `VFRAC_FG=.1` removes the reproduced FeII-excitation
  transport collapse on the original90-point moment grid. Keep `VFRAC_MOM=20000`: a
  separately reproduced angular-prefix mapping defect affects inserted moment
  grids. Additional Rmax tuning has not been required in this recovery branch.
- `INCL_dSLdT=T` cures the persistent outer temperature cycle in the matched
  repaired-runtime comparison. Enabled full80/82 T maxima4.61514%→.843411%,
  versus default-F7.53602%→8.08718%; continued full91 reaches .01527551%.
  `MAX_LIN=10`, native `MAX_dT=.2`, and `EPS_TERM=.02%` remain unchanged.
  The earlier fixed-T Lambda bootstrap used `MAX_LAM=1e12` to fill genuine tiny
  seeds without population-floor mass loss.
- Independent BA-restart tests identify flag ordering, failure-state mutation,
  truncated-cache acceptance and initial-read bypass defects. The isolated
  runtime includes those repairs; controlled full verification always computes
  BA fresh. The source history and native fixtures are detailed in the
  [focused source report](cmfgen-line-jacobian-cancellation.md).

### Current Ng and radiation checks

Native Ng performed after93 and published94, matching the predicted initial
cadence. Repeated normal five-solve process restarts can postpone the first Ng
indefinitely because of its four-step delay and final-step suppression; this
run used eight contiguous physical iterations. The read-only observer has now
completed a replay on actual93/92/91/90 inputs, proving exact agreement with
published94. The checkpoint-only94 has no radiation/Newton sweep; the next
normal solve is95 on input94, now completed. The94 missing-sweep journal has an
explicit Ng-only explanation and is not a lost spectrum or model failure.

A separate V4 Ng temperature-index guard defect has been natively reproduced,
with25 corrected full-wrapper cases plus25 original controls. On the actual
93 histories, the corrected guard still accepts Ng but skips depths85/89/90.
The largest difference from the actual unpatched Ng is only .008174% in any
population and .047K in T; all changes there are below the .02% component
threshold, and the dominant bulk update is identical. Thus the guard defect
does not explain the large remaining corrections in this event. The experimental
guard patch remains unapplied to the running runtime and installed source.
The earlier offline89-history proposal would have been cancelled, but that
was never a scheduled or forced model event.

Every selected physical input-radiation sweep83–93 and95–100 has a read-consistent capture covering
all152174 native frequencies; later cumulative-ray streams have explicit epoch
proofs. The100 sweep belongs to99, not saved100. Its outer formal/moment
absolute-flux mismatch is 0.220559%, maximum 0.651013% across five sampled depths.
Native outer luminosity200908.957Lsun differs from target200000.046Lsun by .45446%.
These are transport consistency observations, not independent exact-RT or
convergence certificates. The initial missing80 capture was recovered by a
separate replay only after predefined equivalence bounds passed; the original
missing capture was never relabelled or fabricated.

### Remaining work and authoritative local state

The ten-step unchanged-physics continuation has now started from accepted97.
Full98–100 have passed; assess101 onward and actual runtime margin without
changing the convergence threshold.
Completion still requires all raw variables below .02%,
physical state checks, multiple full variable-T/fresh-BA steps, a fresh-process
full verification, and a separate no-update radiation probe of the final saved
state. The final probe runtime and strict provenance verifier are prepared but
no final probe has run. Native success or temperature-only convergence is
insufficient. The active ten-step case must not be promoted or cloned for another run.

`root-cause-v1/AUTONOMOUS_STATUS.json`, the active case's `live-monitor.json`,
`checkpoint-audits.json`, `batch-radiation-observer.json` and
`first-ng-observer.json` retain the current identities and observations. The
older `sl-temperature-replay-and-continuation.json` documents the completed
82→88 controller and is not the active run journal. Installed source/executables
and the actual `models/test/model_Bstar3502` remain unchanged; the actual main
folder is still the earlier diagnostic state and must not be described as this
recovery branch. All experiments are in ignored local diagnostics.

The chronology below preserves earlier hypotheses and instructions. Use this
assessment and the latest dated entries for current state.

### Supporting findings and earlier controlled branches

Initial tiny-population lambda cycling was followed by controlled full-BA/LTE
initialization tests. Experimental fixes for the LTE temperature floor and
self-consistent electron density repair identifiable initialization defects,
but do not by themselves remove the later instability. Smaller Newton steps
delay the collapse rather than establish convergence. Restoring old temperature
alone does not prevent it. Stale BA headers and radiation caches were removed
consistently in the controlled tests.

The subsequent radiation failure is reproduced by changing **only Fe II
within-ion excitation proportions** on physical baseline4, conserving its ion
total and retaining baseline4 temperature and other ions. The sharp persistent
radiation-field difference develops near1630–1633A; no negative line/total
opacity, negative emissivity, or clipping is recorded in1625–1640A. This rules
out those local mechanisms within this window, not throughout the spectrum.

| Controlled input | Minimum normalized luminosity | Native luminosity safeguard |
| --- | ---: | --- |
| Physical baseline4 | 0.83207 | Pass |
| Physical smaller-step5 | -1.4242 | Fail |
| Fe II excitation-only update | -1.3327 | Fail |
| SL36-only update on baseline4 | 0.82551 | Pass |
| Failed Fe II update with SL36 restored | 0.83267 | Pass |
| Same failed Fe II input, G_ONLY | -310.42 | Fail |
| Same failed Fe II input, MIXED | -215.05 | Fail |
| Same failed Fe II input, log-radius Q | -1.2422 | Fail |
| Same failed Fe II input, radial VFRAC_MOM=.1 | -1.3371 | Fail |
| Same failed Fe II input, uniform3 moment grid | -0.77985 | Fail |
| Same failed Fe II input, uniform9 moment grid | 0.14076 | Pass; 25% advisories |
| Same failed Fe II input, projected moment .1 | -0.44062 | Pass; 25% advisories |
| Projected moment .1 + ray .1 | 0.97725 | Pass; no luminosity advisories |
| Original moment grid + ray .1 only | 0.97455 | Pass; no luminosity advisories |

The table lists the minimum over **all depths**. The native factor-two stop
checks only ROSS_PHOT_DPTH_INDX..ND; a global minimum below0.5 outside that
region does not contradict a safeguard pass. Uniform9 is a fixed-input
transport diagnostic with unchanged populations, not a Newton/convergence result.

Both SL36 tests proportionally rescale the other Fe II levels to conserve the
ion total; maximum compensation is about0.0132%. These are not literally
single-variable changes. Together they support an interaction involving SL36
and other Fe II changes. They do not prove which transition or numerical
mechanism causes the collapse. A safeguard pass is not convergence: outer
luminosity remains~17times stellar luminosity, and the rescue's next raw Newton
correction reaches1.615e18% with poor outer-matrix conditioning.

The original physical4->5 update also has a separate damping bottleneck.
Its largest raw request is OVI at population/Ne~3.46e-27; the local MAJOR scale
is instead set by MgIV at population/Ne~1.42e-10, barely above the native1e-10
cutoff. Its requested increase~95705times sets scale1.04488e-5 atdepth18.
Exact reconstruction matches every saved applied population update. Internal
lambda cycling is controlled by LAM_VAL, independently of DO_LAM_AUTO; the
latter is not a global disable switch. Multi-iteration recovery must verify
actual full/T-varying steps, not rely solely on the input checkbox/flag.

A further native Lambda test identifies a separate abundance-loss mechanism.
At MAX_LAM=1e4, independent per-variable clipping loses5.75% of the Fe total
while the common unconstrained update conserves it. LAM_SCALE_OPT=NONE does
not change the result; LIMIT is not responsible here. Full-precision replay
from the recorded native DIAG solution reproduces the actual MAX_LAM=1e12
update bitwise and accounts for the complete old-cap Fe deficit. With the
larger cap, maximum Fe abundance mismatch is6.42e-10 and charge mismatch
1.85e-8. All active elements match their VADAT target to4.29e-5 or better.
This is an isolated, tested bootstrap control, not a universal recommendation
to raise every model's change limits.

The actual resulting physical7 separately passes all152174frequency transport:
minimum normalizedL .98056, maximum5.0526, no native luminosity advisories or
Eddington caps. Outer luminosity decreases3.4169e6->1.0096e6Lsun. Full-spectrum
formal rays also decrease3.1966e6->.9755e6Lsun, so the remaining excess is present
in both methods and is not solely the former moment/ray collapse. UV C IV and
Si IV regions dominate the earlier excess. The input6 full-spectrum moment/ray
absolute flux mismatch is7.24% at the outer boundary, improving to4.14% for
new7; this is distinct from the narrow1625..1640A comparison. The further
native Lambda7->8 passes with charge/abundance errors~1e-15. Full variable-T
Newton8->9 completes with T changing at all90 depths; charge/abundance checks
pass and actual9 independently passes the native radiation guard. Its remaining
window discrepancy is14.96%. A completed same-state FG.05 comparison changes
integrated flux by at most6.01e-6 relative and the window discrepancy only to
14.85%; further ray refinement is not an established cure for that difference.
This fresh-LTE branch is distinct from the exact original68 comparison below.

**Matched original68 source test (11:12UTC): the cancellation defect is now
attributed to the actual checkpoint.** The original/patched runs have identical
prepared SCRTEMP and controls, with input radiation differing by only1.26e-11
peak-normalized. The anomalous N V coefficient scale falls from~1e90 to~1e11;
all17 positive excited-state N V diagonals and all31 negative unlimited
population targets disappear. The correctly exposed tiny-seed request initially
exceeds the unchanged MAX_CHNG=1e100 guard. Native status remains invalid_output;
its explicitly provisional, capped saved state was independently checked before
an isolated continuation. That next iteration completes normally at70 with the
guard unchanged. No population floor or convergence tolerance was changed.

A native batch from70 used the same line fix plus the independently tested
BA-header/EOF correction. The latter prevents cache reuse from silently changing
temperature mode. It completed native71..77; full76 changed all90 temperatures
with four outer depths reaching the20% cap, then77 was internally Lambda again.
A documented live NUM_ITS10→7 edit bounded this test. Its aggregate runner_error
is retained because restoration detected that external control edit; the native
pass itself succeeded. Subsequent matched fresh-process full75→76 runs completed
normally and attributed the strong-line defect to outerOVSL26, while showing
essentially unchanged bulk thermal response. The latest bootstrap/current full
continuation above use both repaired line branches. Actual full-T convergence
and fresh verification remain required.

The actual `models/test/model_Bstar3502` remains at diagnostic6 from the passing
SL36-only experiment. This is a diagnostic branch, not recovered physical5;
its previous next-run note describes the already completed test. Autonomous
work now uses isolated copies in
`models/test/.model_Bstar3502-diagnostics/root-cause-v1/`, preserving the actual
model and original physical checkpoints.

The original failed-input window shows a **transfer inconsistency** despite
accurate linear solves: peak momentJ/formal-rayJ21.93; integrated node24 window
luminosity-5980Lsun versus formal+2075Lsun. G_ONLY and MIXED worsen both the
window and full-spectrum failure. Log-radius Q integration improves analytic
limits but is insufficient here. Radial-velocity-only insertion to228points
also fails. These alternatives have been tested rather than assumed remedies.

**Ray refinement alone is now the simplest demonstrated transport remedy.**
On the exact failed Fe II hybrid checkpoint, changing only VFRAC_FG20000->0.1
with the original90point moment grid changes global minimum normalizedL from
-1.3327 to+.97455, removes all negative luminosities and native luminosity
warnings. In1625..1640A the final moment/ray intensity ratio lies between.95693
and1.03906 (largest symmetric difference4.40%), and node24 integrated flux is
+1144.17 versus formal+1141.12Lsun. This uses existing scientific solver code;
new moment-grid or quadrature source changes are not needed for that result.

Moment refinement alone improved the discrepancy but did not make both methods
agree. Uniform3/9 peak ratios14.60/6.30; projected moment refinement alone10.03.
Combining projected moment refinement with ray .1 gives ratio.96299..1.02327
and window flux agreement~.085%, but the ray-only control demonstrates that
this experimental moment criterion is unnecessary for basic transport recovery
here. Original VFRAC_MOM remains20000, so the separate derivative-grid bug is
avoided by the simple ray-only setting. Original physical5 transport passes
(min normalizedL .97424), as does a full variable-temperature Newton5->6 step.
The actual newly saved6 independently passes transport (min .97917), with no
factor-two/25% luminosity warnings or Eddington iteration caps. This establishes
a physical continuation rather than only a hybrid-input rescue; it does not
establish convergence. A native Lambda bootstrap from physical6 is the next
controlled test of the remaining tiny-ion damping bottleneck.

Recorded-coefficient frequency replay reproduces the native trajectory to
~3e-13. Resetting only its incoming1625A state to formal-ray J/H removes the
large excess through the window with frozen coefficients. Separate source/
history substitutions also reverse the wrong window flux sign. These narrow
the mechanism to accumulated transport-history error; they do not validate
resetting native history as a fix. Baseline4 already has substantial earlier
moment/ray disagreement despite passing its luminosity safeguard.

Fixed-input probes now use an isolated transport-only source path: complete
ordinary DTDR computation retained, derivative updates disabled afterward,
stop before BA reload/Newton. Against the ordinary reference, all152174 recorded
frequency/depth fields agree to1.26e-11 per-field peak-relative error; window
coefficients/radiation1.54e-11 and integrated luminosity1.18e-13 relative.
Initial byte-identity gate was too strict for the measured rounding differences;
full numerical validation is retained. Original inputs/checkpoints remain exact.
The corrected diagnostic exit order is after radiation and native checks and
before unused BA reload; no preceding executable radiation statements changed.

A **separate derivative-grid mismatch** is proven when internal moment points
are inserted: VAR_MOM_J_CMF_V12 indexes expanded angular factors against original
model radii. This does not affect the no-insertion reference or transport-only
probes, but must be addressed before using finer-grid Newton updates. Do not
promote diagnostic checkpoints into the actual model. Installed CMFGEN and main
model remain unchanged. The latest chronological entries below record exact
runtimes, validations, incomplete tests and superseded schedules.

## Initial read-only inspection — 2026-10-21

Read-only inspection after cancellation of automatic continuation. No native
calculation was launched and no model controls or checkpoints were changed.

## Cancellation and retained evidence

Automatic journal: `20261021T124735Z-auto-a42c004e`.
Attempt 1 encountered the explicit EDDFACTOR read error; the registered cache
remedy restored the baseline and retired the incompatible cache. Attempt 2
completed iterations 64–68. Attempt 3 was cancelled; the controller reports
“Native attempt interrupted; stable restart restored.” Both pointer files,
SCRTEMP and VADAT match the retained recovery snapshot byte for byte.
The active pointer is iteration/record 68. IN_ITS is restored to its original
30 iterations, with DO_LAM_IT=T and DO_LAM_AUTO=T.

All five completed steps were temperature-fixed lambda iterations and explicitly
computed BA. Their native maximum correction percentages were:

| Iteration | Maximum correction (%) |
| --- | ---: |
| 64 | 3.57958e32 |
| 65 | 1.45076e31 |
| 66 | 1.40397e55 |
| 67 | 8.54922e27 |
| 68 | 3.45129e31 |

## Binary checkpoint inspection

Decoded the native direct-access layout using the installed source definitions
in `subs/scr_read_v2.f` and `unix/dir_acc_pars_gen.f`: REAL(8), 16376-byte
records, 2047 numbers per record, NT=2233, ND=90, 99 population records per
saved step, with the saved R/V/Sigma record enabled. Population data for pointer
record i begins at byte `((i-1)*100+3)*16376`; the last population record has
padding and was read only up to NT*ND values. Temperature and Ne give sensible
cross-checks on this interpretation.

Every value in the six saved vectors 63–68 is finite and positive. Outermost
T is exactly unchanged at 1669.865818628042 K. Outer Ne stays near 6380.27.
For the population variable at equation 590 (identified in CORRECTION_LINK as
N V superlevel 31, using the model's equation numbering):

| Checkpoint | Depth-1 population variable |
| --- | ---: |
| 63 | 2.40256e-65 |
| 64 | 2.40256e-61 |
| 65 | 2.40256e-64 |
| 66 | 2.40256e-60 |
| 67 | 2.40256e-56 |
| 68 | 2.40256e-59 |

The repeated factors 1e4 and 1e-3 support a limited population cycle rather
than a simple monotone approach. MAX_LAM=1e4 permits very large upward
updates; the lambda LIMIT handling clips large reductions to 0.999. A finite,
positive checkpoint does not establish physically correct populations.
The precise rate-equation cause of the cycle remains unproven.

`new_main/subs/solveba_v13.f` selects the diagonal solve in lambda mode via
`mod_subs/solve_for_pops.f`. Thus “BA matrix computed” does not imply a fully
coupled variable-temperature step. The latter source also forces lambda
iterations for MAXCH>1e5. Existing auto LTE/POP policies only handle diagnosed
pre-iteration startup failures. The fixed-temperature policy stops after three
successful batches with no full steps; it does not repair this cycle.

## Proposed isolated tests (not run or prepared)

Preserve checkpoint68 and use separate disposable workspaces with the same
executable, atomic data, grid, abundances, X-rays and thread count. Ordinary
bounded runs are preferable for diagnosis so automatic remedies do not confound
comparisons. Exclude incompatible BA/radiation caches consistently.

1. **Lambda update-limit comparison:** one continuation step from68 with only
   MAX_LAM reduced from1e4 to10. Compare against retained native step69 if it
   completed before cancellation, otherwise a one-step unchanged control.
   Record raw requests, actual population ratios, ion totals and Ne. This tests
   the role of the aggressive update cap, not final convergence. Smaller applied
   changes alone do not demonstrate improvement.
2. **One full linearization probe:** another copy of checkpoint68, DO_LAM_IT=F,
   DO_LAM_AUTO=F, fresh BA and one requested step. Confirm the log actually
   reports a full variable-temperature step. Compare raw corrections and ion
   totals to the lambda case. Huge corrections can force lambda mode again on
   subsequent steps; this is a one-step diagnostic, not a validated remedy.
3. **Initialization comparison:** fresh default initialization versus explicit
   LTE initialization at identical physical controls, first zero iterations to
   compare initial populations/charge, then two bounded iterations if both
   initial states are healthy. LIN_INT=F is retained; explicit LTE can use the
   existing runner option and default T_EXC=1 (10000 K). Compare N V/O IV/O V/
   Fe V outer populations and whether the cycle appears immediately. The LTE
   path is a hypothesis, not an established solution. POP is not selected:
   this model currently uses LIN_INT=F and compatible population interpolation
   sources would need separate validation.

Validate a successful intervention over further full variable-temperature steps
before defining a bounded automatic rule and independent verification. Do not
suppress trace ions, disable X-rays, change the outer grid or reseed a live
continuation as an untested automatic remedy.

## MAX_LAM=10 one-step result

Journal `20261021T132244Z-71c56dc5` succeeded. Native startup confirms
continuation at69 from saved68. One lambda step computed BA, held T fixed,
and wrote checkpoint69. MAX_LAM was10, with the other physical/solver controls
retained; NUM_ITS was1. No further calculation or model preparation was done
while inspecting this result.

The raw maximum correction remains8.18850e31% (N V SL10, equation569,
depth1), compared with3.45129e31% on the preceding step68. The maximum raw
reduction is103.35% for Fe V SL88 at depth2; the saved state stays positive
because update limiting is applied. This requested reduction alone must not
be interpreted as an actual negative population.

Correction counts above100% /10% /1% change from47 /121 /254 at68 to
43 /102 /235 at69. This small decrease does not establish recovery.
Decoded checkpoint69 is finite and positive throughout. Applied population
ratios relative to68 range from0.1 to10, confirming the smaller cap acts.
At depth1 equation590 changes from2.40256e-59 to2.40256e-60. Temperature is
byte-numerically unchanged (maximum relative change0); maximum absolute
relative Ne change is0.00054391%. Outermost T remains1669.865818628042 K.

Conclusion: the cap limits applied excursions but the raw rate-equation
problem and lambda trap persist. One step cannot determine long-term damping
behavior. The next discriminating test is a single full variable-temperature
linearization from the *same backed-up checkpoint68*, restoring original
MAX_LAM=1e4 and disabling explicit/automatic lambda requests for that probe,
with fresh BA. Confirm the native mode in the log; do not infer it from BA
computation alone. Keep69 as a separate result, not the baseline for this
comparison. Native large-correction logic can re-enable lambda on later steps.

## Full-linearization probe from68

Journal `20261021T134441Z-c8189057` succeeded (native return code0), continuing
at69 from the unchanged backed-up68 population block. Unlike the lambda
comparison, the log confirms “Beginning TRI solution in CMF_BLKBAND”, no lambda
marker and no all-depth temperature-fixed marker; BA was computed. Thus the
intended coupled, variable-temperature diagnostic actually ran.

Raw maximum increase is1.34461e28% (N V SL14 at depth1), but raw maximum
reduction is2.0805e30% (N V SL26 at depth1). The native reported maximum is
1.34461e28%; it must not obscure the still larger requested reduction.
Counts above100% /10% /1% are9910 /48829 /113434, compared with47 /121 /254
at68 and43 /102 /235 for the MAX_LAM=10 lambda comparison from the same68.
The full step therefore exposes large requests throughout the model; it has
not solved the problem merely by escaping explicit lambda mode.

Binary69 is finite and positive; population update ratios remain in[0.1,10].
Outermost T hits the default20% decrease cap, from1669.865818628042 to
1335.892654902434 K. Maximum absolute relative Ne change is2.47355% at28.
The major-species minimum scale is0.12033. These limiting operations preserve
numerical positivity but do not establish approach to a physical solution.
Luminosity discrepancy printed during the radiation evaluation is-0.25124%;
that evaluation precedes the applied population/T update and is identical for
both tests from68, so it is not evidence that the updated atmospheres agree.

Assessment: neither reducing the lambda update cap for one step nor taking one
full coupled step removes the raw outer-ion pathology. A single full step
cannot establish long-term behavior, especially after a long frozen-T history.
Do not continue an unattended sequence from this69 as a demonstrated remedy.
Next priority is the fresh-initialization comparison already proposed: compare
initial states (zero iterations), then a short bounded LTE-initialized run if
healthy, while preserving68 as the common reference. Current active files
are the full-step69 result; no subsequent model edits or runs were performed
while recording this assessment.

## Default fresh initialization: zero iterations

Test journal `20261021T144722Z-ec4baa12` reports tested, native return code0,
confirmed fresh startup, no diagnosed fatal error, and NUM_ITS=0. The native
process log has no great-iteration counters. POINT1/2 contain record1 and
counter1; this is the initialization write convention, not a completed
radiation/linearization iteration.

The log confirms the default ED departure-coefficient initialization via
REGRID_LOG_DC_V1, followed by the grey initialization loop. Decoded initial
SCRTEMP (90x2233) is entirely finite and positive; minimum population variable
is2.24832e-90. Outermost T=1736.539910331477 K and Ne=6812.912716498464.
Depth1 population variables associated with N V include equation569=1.32809e-76,
573=1.65632e-78,585=9.84745e-68,590=8.04460e-61,593=2.54045e-71 and
598=1.80807e-68. Thus extremely small high-ion population variables are already
present before any full iteration; they are not solely generated by the long
lambda history. Whether their subsequent huge corrections originate in poor
initialization or in the rate solution remains unresolved.

The process also reports IEEE underflow, without a failed exit or nonfinite
saved values. The small grey-loop temperature corrections near0.195% are
initialization diagnostics, not full NLTE convergence. Old CORRECTION_SUM/LINK
cannot assess this zero-iteration state. Next comparison: independently fresh
zero-iteration LTE initialization at identical grid/physical controls, preserving
this default initial checkpoint first. No further controls were changed or
calculations launched during this inspection.

## LTE zero-iteration initialization crashes in the grey solve

Test journal `20261021T145233Z-cccd9693`: fresh startup confirmed, native
return code-4 (SIGILL), no fresh RVTJ and no POINT1/POINT2/SCRTEMP written.
DC_METH=LTE, T_EXC=1, LIN_INT=F, POP_SCALE=T and IT_ON_T=T were installed as
prepared. The default initial checkpoint remains backed up separately.

The macOS crash report
`~/Library/Logs/DiagnosticReports/cmfgen_dev.exe-2026-10-21-165307.ips`
symbolicates the main-thread stack as `pow -> comp_grey_v4_+2556 ->
set_new_model_estimates_+9052 -> cmfgen_sub_`. Thus this is a failure during
LTE startup's grey-temperature calculation, not a full NLTE iteration or
atomic-link opening failure. Source `new_main/mod_subs/comp_grey_v4.f:277`
computes `TGREY=(PI/5.67e-5*RJ)**0.25*1e-4` without validating RJ first.
An invalid/nonfinite argument (particularly negative grey J) is a plausible
cause, but RJ was not captured at the failure and the exact value/depth must
be established by an instrumented or debug reproduction. SIGILL alone is
not proof of a CPU-incompatible executable: the same executable completed the
preceding tests, and the system crash stack locates this specific math path.

IT_ON_T controls the initial grey-refinement loop in SET_NEW_MODEL_ESTIMATES;
setting it F bypasses that loop without disabling temperature variation in
subsequent full iterations. Next diagnostic: paired fresh zero-iteration
ED and LTE initializations with IT_ON_T=F, to compare population seeds without
the grey solve confounding the comparison. A direct investigation should
also capture RJ/ROSSMEAN and the selected grey branch before the power call;
invalid output should result in a clear diagnostic rather than clipping an
unphysical J to make the calculation continue. No source patch, new run,
or model control change was made while inspecting this crash. The active
model remains set to LTE initialization and has no usable binary checkpoint.

## LTE initialization with IT_ON_T=F succeeds, but Ne needs investigation

Test journal `20261021T145644Z-da21b6e3` is tested, return code0, confirmed
fresh startup, no solver-iteration counters. Pointer record1/counter1 is the
initialization write. Disabling grey refinement avoids the prior crash.
The decoded initial population vector is finite and positive, minimum1.03247e-65.
Outermost T is1736.539910331477 K (same as ED+grey initial state), but Ne is
1.8582635946521058e-8 versus6812.912716498464 in ED+grey. The T profiles differ
by up to0.316615%; these are not yet the fully controlled pair because the
ED case still had IT_ON_T=T.

Depth1 N V equation569 changes from1.32809e-76 in ED+grey to7.72512e-26
in LTE without grey; equation590 changes from8.04460e-61 to4.22924e-28.
Larger seeds alone do not prove a better initial atmosphere, particularly
with the large Ne difference. No radiation iteration or correction measurement
has tested the LTE seed.

Source inspection identifies an additional concern in `new_main/subs/det_lte_ed.f`:
TEMP=T followed by `IF(T(I)<TMIN) TEMP(I)=T(I)` does not apply TMIN at all.
By contrast, SET_DC_LTE_V2 explicitly uses a TMIN-derived excitation scale
when constructing departure coefficients. Thus T_EXC=1 does not impose a
10000K floor in the DET_LTE_ED Saha calculation in this source. This could
explain the nearly neutral outer electron-density seed and deserves a
charge-consistency check and source-level validation before treating LTE
startup as a remedy. The mathematical cause of the grey crash remains
unconfirmed. No installed source or executable was modified.

Next: preserve this LTE initial checkpoint and prepare the matched ED
zero-iteration case with IT_ON_T=F; then examine population/charge consistency
before launching more full iterations. Active model remains the LTE zero-step
result and no new model preparation or native run was done during inspection.

## Matched ED initialization with IT_ON_T=F

Test journal `20261021T145915Z-95f30eae` reports tested, return code0,
confirmed fresh startup and zero great-iteration counters. The log selects
REGRID_LOG_DC_V1 option ED. The initial vector is finite and positive,
minimum population2.55334e-90. Pointer1/counter1 is again the initialization
write, not a completed solver iteration.

The no-grey ED and LTE temperature profiles are exactly equal in the decoded
binary checkpoints, including outer T=1736.539910331477 K. At that identical
T, ED outer Ne=6383.708287920128 while LTE outer Ne=1.8582635946521058e-8,
a ratio3.43531e11. N V equation569 at depth1 is1.51268e-76 in ED versus
7.72512e-26 in LTE; equation590 is9.16272e-61 versus4.22924e-28. This
controlled comparison establishes that the seed differences originate in the
initialization methods rather than grey-temperature adjustments. Neither
zero-step test establishes that its seed will converge.

Default ED with/without grey differs in T by at most0.316615%, and outer Ne
by roughly6.7%; that is much smaller than the ED/LTE initialization difference.
The remaining priority is to examine LTE charge consistency and the ignored
TMIN in DET_LTE_ED before promoting this LTE seed to an automatic remedy or
starting a long run. Active model remains the ED no-grey initial checkpoint;
no model controls or native calculations were changed during this assessment.

## Charge audit and prepared POP comparison

Before preparing the next run, constructed ionic charges from MODEL's N_S,
Z, equation-start and species columns. Explicit superlevels carry Z-1;
the terminal continuum variable following each element carries the final Z.
This maps all2231 population slots exactly, leaving only Ne and T unassigned.
Summing charge times population in the decoded zero-step states gives:

- ED no-grey: stored outer Ne6383.7083, charge sum6812.9127 (6.723% mismatch).
- LTE no-grey: stored outer Ne1.85826e-8, charge sum6815.1303 (ratio3.66747e11).
  Worst charge/stored-Ne discrepancy is at depth2, ratio about3.77174e11.

The LTE zero-step seed is therefore charge-inconsistent despite being finite
and positive. Do not start a full iteration sequence from it as a demonstrated
remedy. This audit is independent of the possible ignored-TMIN defect; a
complete source fix needs to establish the whole LTE conversion lifecycle.

Preserved ED no-grey initial state under
`.model_Bstar3502-history/ed-no-grey-initialization-zero-iterations`, including
verified hashes. Prepared active model for fresh zero-iteration POP comparison:
DC_METH=POP, LIN_INT=T, POP_SCALE=T and IT_ON_T=F. Source-grid/full-level
checks pass for all43 input atoms on90 depths, and compiled POP support is
confirmed. Native validation of stage contiguity, atomic mapping, occupation
convergence and conservation remains required. Physical controls and source
input files are retained; the initialization method/interpolation switch are
explicit experimental changes. Active checkpoint files are retired; ordinary
TEST stage now initializes afresh. No native calculation was launched.

## POP zero-iteration initialization passes charge conservation

Test journal `20261021T150310Z-f13d23e8` reports tested, return code0,
confirmed fresh startup, no great-iteration counters. OUTGEN contains the
exact native marker “POP: interpolated source superlevel fractions; Ne set
from charge conservation”. It selected direct interpolation/GRID startup,
so this is a different initialization path, not merely an ED seed with Ne
replaced. Native compatibility and occupation reconstruction completed.

Decoded record1 is finite and positive throughout; minimum population6.78443e-119.
Outermost T=1736.539910331477 K, Ne=6382.494826594852, and charge sum from
the saved populations=6382.494826594854. Maximum relative charge mismatch over
all90 depths is1.22125e-15. This resolves the initialization charge inconsistency
seen in ED (up to6.723%) and especially LTE (up to3.77174e11 relative mismatch).

Outer N V seeds are even smaller than ED: equation569=1.76620e-107,
573=4.51528e-110,585=4.31663e-100,590=2.64929e-93,593=7.08991e-104,
598=4.11600e-101. Charge consistency does not imply that the raw trace-ion
relative corrections will be modest or that the model will converge. The
source input population fractions themselves can contain extreme trace-ion
seeds. No rate-equation correction or full NLTE step has yet tested POP here.

Recommended next diagnostic: back up this initial checkpoint and perform
one ordinary full variable-temperature continuation step with fresh BA,
lambda requests disabled, retaining the same physical model and grid. Compare
raw requests, actual population/Ne/T changes and charge conservation after
the step; do not interpret a small applied change as convergence. The active
model remains the zero-step POP state. No further edits/runs were performed
while inspecting this result.

## First full continuation step from the POP initial state

Journal `20261021T150517Z-aa23fcf4` succeeded, return code0, confirmed binary
continuation at2. The saved POP initial block is unchanged. Native log confirms
fresh BA and “Beginning TRI solution in CMF_BLKBAND”, with no lambda or
all-depth fixed-T marker. Checkpoint2 is finite and positive throughout.

Raw maximum increase3.14900e72% (O V SL9, equation805, depth2); raw maximum
reduction8.8980e75% (terminal O VI population, equation829, depth1). Outer N V
also remains among the extreme requests. Counts above100% /10% /1% are
23141 /70635 /151168. Native reported maximum3.149e72% again does not include
the still larger raw requested reduction. Minimum major-species scale6.6013e-4.
Applied population ratios are bounded in[0.1,10]. Outermost T hits the20%
increase cap,1736.53991 ->2083.84789 K. Maximum relative Ne change2.42040%
at depth28; depth1 Ne6382.49483 ->6390.41089. Ionic-charge sum at depth1 is
6390.40942; maximum relative charge mismatch across the grid4.86999e-6.
Thus near-neutrality survives the full step, but raw rate-equation requests
remain pathological. Correct initialization charge alone is insufficient.

Radiation evaluation reports luminosity+1.51308% relative to target and a
last-frequency outer-boundary J(mom)/J(ray) warning exceeding1000%. These
radiation diagnostics precede the applied update; neither is a measure of
convergence of the resulting checkpoint2. The boundary discrepancy deserves
separate investigation and does not yet establish the cause of the population
cycle.

Assessment: POP provides a well-defined charge-conserving reconstruction but
is not a demonstrated convergence remedy for this source atmosphere. The
seed contains extremely tiny high-ion populations and the first full solve
requests enormous sign-inconsistent relative corrections. More automatic
batches are not justified as a validated solution. Next investigation should
examine absolute high-ion populations, rate residuals and matrix conditioning,
and separately inspect frequency-resolved outer-boundary transfer. Any further
trial should retain this result and use a common saved initial checkpoint;
no additional model preparation or native execution was performed here.

## Follow-up: absolute corrections, conservation rows and radiation bands

Read-only analysis of the saved POP full-step solution. Streamed only the
STEQ_VALS suffix after byte128425560, the exact pre-run file size retained in
the POP-initialization backup manifest. The suffix contains exactly one
complete STEQ_ARRAY and STEQ SOLUTION ARRAY, each90x2233. Equation labels and
element totals are derived from MODEL. Binary pre-step populations match the
saved initial checkpoint, so absolute requested delta is `-solution*population`.
Printed solution precision limits the accuracy of these derived deltas.
Analysis script and parsed arrays are under `/private/tmp/bstar3502-analysis/`.
No native solver execution, model mutation, source patch or executable rebuild
was performed.

### The largest percentage is largely a denominator/precision problem

At depth1 terminal O VI (equation829) starts at9.48829e-87. Its raw requested
fractional reduction8.898e73 corresponds to an absolute delta-8.44268e-13,
only1.51767e-12 of the local oxygen abundance0.556293. O V SL9 at depth2
starts at4.50262e-97; its3.149e70 fractional increase is an absolute delta
1.41787e-26, or2.40982e-26 of local oxygen. These examples do not represent
macroscopic density explosions.

The mapped RHS of the terminal O VI equation is-1.1102e-16, around roundoff
scale. `cmfgen.f` assigns each element's number-conservation equation to its
terminal-ion slot; GENERATE_FULL_MATRIX_V3 replaces that row accordingly and
scales matrix columns by population to solve fractional corrections. Thus an
almost-empty terminal ion shares a system with an abundance-conservation row
whose residual cannot resolve populations near1e-87 in ordinary double precision.
This supports cancellation/conditioning as a contributor to the enormous
signed trace corrections; the exact contribution is not proven without the
outer-depth matrix blocks or a higher-precision/reformulated solve. Available
BA_ASCI dumps cover depths5,41,90, not the offending1–2. Existing DGEEQU row/
column equilibration is already used before LU; simple additional diagonal
scaling cannot be assumed to fix it. Do not claim a measured condition number
from these data.

584 population variables have raw fractional corrections above1e10 (>1e12%).
Their largest initial population fraction of the element is1.5825e-16.
However not all requested absolute changes in this group are negligible:
N IV ground at depth1 has initial fraction3.97645e-22 but a requested decrease
of0.250087 of all local nitrogen. Therefore indiscriminately ignoring every
tiny variable or capping the reported metric would conceal real trouble.

### There is also a substantial physical/linearization adjustment

Among10367 population variables holding at least1e-4 of their element,
194 still request changes above100%. At depth2, terminal Ne IV requests
+95.07 times all local neon and Ne III ground requests-90.04 times that total;
terminal Mg IV requests+70.19 times all local magnesium. These signed
redistributions preserve element totals approximately but are not viable
unlimited population updates. At depth28, the He I/He II redistribution is
about30.47% of total helium. The raw temperature requests at outer depths1–2
are+22582% and+30297%, although the applied temperature is capped at+20%.
Consequently this state is far from an acceptable linearization basin even
when extreme trace-ion ratios are discounted.

### The boundary warning is frequency-dependent

J_COMP has152174 finite rows and no negative outer moment/ray intensities.
Its %Diff uses a symmetric normalization, unlike the source's ratio-based
last-frequency warning. Extremes from the saved radiation evaluation:

| Band | Largest absolute symmetric discrepancy | Wavelength | J(moment)/J(ray) at that point |
| --- | ---: | ---: | ---: |
| All / extreme UV |199.52%|0.0405166 microns|0.0012055|
| UV 0.09–0.3 microns |64.41%|0.123894 microns|0.51283|
| Optical 0.3–1 microns |1.61%|0.389267 microns|1.01620|
| IR 1–1000 microns |169.67%|78.9086 microns|12.1860|

At the last frequency (85.6802 microns), the ratio is about11.765 and the
symmetric difference168.67%. This explains how the source can warn about a
>1000% disagreement while the table remains below200%. It is a local boundary
transfer disagreement, not a >1000% emergent-flux error. Its causal effect on
the trace-ion equations is not established; the extreme-UV discrepancy warrants
separate radiation/rate checks rather than assuming an IR-only problem.

### Next discriminating test

The least-confounded next native comparison is one full fresh-BA step from
the saved **ED no-grey initial checkpoint**, with the same lambda-off and
variable-temperature controls used for POP. ED and POP initial temperature
profiles are identical, whereas checkpoint68 came after a long lambda history
and had a different thermal state. This separates source-population
reconstruction effects from the previous iteration history. Inspect raw
absolute and element-normalized deltas, charge, and thermal requests, not just
MAXCH. Do not run more automatic batches as a demonstrated cure.

A diagnostic source build should additionally capture matrix/RHS/populations
at1–2, distinguish conservation rows from rate residuals, estimate scaled
linear-system conditioning/backward error, and record grey RJ before taking
its fourth root. The LTE ignored-TMIN and post-conversion charge mismatch
need separate regression cases. No new remedy is validated by these findings.

## Matched full step from the ED initial state

Journal `20261021T163200Z-c54ff9f2` succeeded, return code0, confirmed
continuation at2. Full TRI solve with fresh BA and variable T; the backed-up
ED initial population block is unchanged. Executable size and nanosecond
mtime/ctime match the POP comparison's recorded executable snapshot. VADAT
and IN_ITS had been verified byte-identical to that POP probe before launch.

Raw maximum increase7.29055e50% (N V SL6 at depth2), reduction1.9152e58%
(N V SL16 at depth2). Counts above100% /10% /1% are149474 /157159 /165105,
compared with23141 /70635 /151168 in the POP full step. The smaller extreme
percentage therefore does not indicate a healthier overall correction field.
Minimum major-species scale is1.1442e-21 versus6.6013e-4 with POP: much of
the ED outer update is effectively frozen by a pathological shared scale.

Checkpoint2 is finite and positive, minimum population1.44214e-89. Outermost
T changes from1736.539910331477 to1736.539910231996 K (effectively unchanged),
while the largest T change is+2.96196% at depth68. Largest Ne change+0.725694%
is also at68. Outer stored Ne6383.70828793384 versus charge sum6812.91299199178:
maximum relative mismatch6.72343855%, so the seed's charge inconsistency is
not materially corrected by this limited step. POP retained neutrality to
about4.87e-6 after its full step.

The radiation evaluation before updating populations reports luminosity
319845.265 versus target200000.046, a+59.9226% discrepancy; the matched POP
seed produced+1.51308%. There are also poor inner-flux accuracy and photospheric
hydrostatic residual warnings. These belong to the radiation evaluation of
the starting state, not proof of the resulting checkpoint's quality.

Conclusion: returning to ordinary ED reconstruction does not improve the
problem. POP provides the more consistent seed (charge and initial radiation
balance), but is still not a validated convergence solution. The effectively
unchanged ED outer temperature is caused by overwhelming update limiting,
not convergence. The next priority is source-level outer matrix/RHS/backward-error
diagnostics and the separately established LTE/grey-initialization issues,
rather than another unchanged batch. Current active checkpoint2 is the ED
full-step result, with the POP full-step result retained separately. No further
model/source edits or native calculations were made during this assessment.

## Prepared outer-matrix diagnostic repeat from the POP seed

Saved matrix outputs cannot establish the conditioning of the failing outer
rows: GENERATE_FULL_MATRIX_V3 only dumps depths5,41,90. Its native column
scaling and the block solver's DGEEQU equilibration are already active.
To distinguish amplification of rounding-scale conservation residuals from
an inaccurate solve, built a separate instrumented executable under
`models/test/.model_Bstar3502-diagnostics/outer-matrix-v1/exe/cmfgen_dev.exe`.
Installed sources, archives, executable, and global CMFGEN configuration were
not modified. The local src/ directory contains the two instrumented routines,
diagnostic helpers and reproducible build script. build-manifest.json records
original source/archive/object hashes, build commands and diagnostic binary hash.

Instrumentation is opt-in via OUTER_MATRIX_DIAGNOSTICS in the run directory:

- Stream binary matrices at depths1–2, all available lower/diagonal/upper
  bands, after population column scaling and equation replacement, before
  block elimination/equilibration. Includes full-precision RHS and column
  populations with dimensions and depth/band metadata.
- Record reciprocal1-norm condition estimates using DGECON on the equilibrated
  Schur LU factors at depths1–2. These are local block estimates, not a global
  condition estimate or guaranteed forward-error bound.
- Save the full-precision raw solution after back substitution, before update
  limiting, to compute componentwise backward errors against the captured rows.
- No changes to the physical equations, update controls or solve arithmetic;
  the diagnostic calls add observations. Output about200MB plus1.6MB solution.

Compilation and synthetic checks passed: binary matrix/solution round trips,
known diagonal reciprocal condition0.5 with info0, unchanged diagnostic matrix
input, and an829-variable three-depth coupled system analyzed with backward
error<1e-14. No atmosphere/radiation iteration was launched by the agent.
The analyze_outer.py helper reads the binary outputs and produces JSON for
local original-row backward errors and selected problematic equations.

Preserved current ED full-step2 under
`.model_Bstar3502-history/ed-full-step-result-checkpoint-2`, including hashes.
Restored verified POP initial checkpoint1, the more consistent baseline for
this numerical diagnostic; VADAT and IN_ITS exactly match the prior POP probe.
Fresh BA, variable T, lambda requests disabled, one iteration. Matrix/radiation
caches retired. Preflight with the isolated diagnostic root passes.
NEXT_DIAGNOSTIC_RUN.md in the active model contains the exact command:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/outer-matrix-v1
```

Automatic and fresh-start modes must remain off. Expected next native iteration2.
Ordinary launch without this cmfgen-root override selects the installed
executable and will not produce the new diagnostic files. Global settings
are intentionally left alone. No scientific convergence remedy is being
claimed or tested by this observational executable.

## Outer-matrix diagnostic run: severe ill-conditioning confirmed

Diagnostic journal `20261021T171656Z-c8964245` succeeded, return code0,
continuing at2 from the unchanged POP initial block. The planned isolated
instrumented executable was used. All five outer matrix blocks, full-precision
solution and condition log are present. Captured depth1 column populations
match the binary pre-step POP vector exactly. Copies and SHA256 hashes are
retained under `.model_Bstar3502-diagnostics/outer-matrix-v1/results/20261021T171656Z-c8964245/`.

Native DGECON estimates after DGEEQU scaling and Schur-block LU (info0):

| Depth | Equilibrated matrix1-norm | Reciprocal condition estimate |
| --- | ---: | ---: |
| 1 |568.3979754|1.16668e-65|
| 2 |620.6821723|1.67324e-55|

Independent NumPy reconstruction of depth1's row/column equilibration gives
the identical1-norm568.3979754 and condition1=6.21865e64, consistent in order
with the native estimate. This is far beyond double precision's ability to
guarantee accurate corrections. A zero LU info code does not establish an
accurate solution to such a system. These are local blocks; no global condition
number has been computed.

Using original captured bands/RHS and the full-precision native solution,
componentwise local backward errors reach0.99999970 at depth1 and0.99999945
at depth2. Some individual trace rows are accurate while others fail badly;
this is not a uniformly inaccurate relative metric. For charge conservation,
backward errors are3.84687e-5 and0.00331446; residuals are-9.89703 and
-2090.26148 in the unnormalized equations. Temperature-row errors are0.000834575
and0.00101125. Thus the problem extends beyond giant relative corrections
of negligible trace populations. JSON contains selected rows, denominators,
RHS and signed residuals. These are checks of the linear solve, not measures
of nonlinear convergence or final physical quality.

As an offline diagnostic, divided out the original population column scaling
and re-equilibrated the absolute-population Jacobian. Depth1 condition1 improves
to7.32518e40, still catastrophically large. Merely changing variable normalization
cannot be claimed as a sufficient fix. This was a saved-matrix calculation;
no source/solver remedy was installed or run.

The diagnostic repeat remains finite and positive but differs substantially
from the earlier nominally identical POP step: outer T decreases20% to
1389.231928 K rather than increasing20%. Ne becomes6374.602928. Raw maximum
increase2.81037e75%, reduction3.60e66%; major-species minimum scale1.2175e-4.
Instrumentation/recompilation/execution-order perturbations need not preserve
answers for a numerically sensitive system; no unique cause of this repeat
variation is asserted. Both runs use the verified identical initial population
block and the same physical controls, and neither yields a reliable correction.

Assessment: there is now direct evidence of a badly conditioned, inadequately
satisfied outer linear system. Further native iteration, cache changes or
more damping alone are not an established resolution. Next source investigation
should target stable conservation/ionization equation assembly and nearly
absent ion stages, then compare an improved formulation against these saved
blocks and physically significant populations. A precision increase of only
ordinary extended/quad precision cannot by itself guarantee resolving condition
numbers around1e65. Do not silently floor trace populations or ignore their
metrics as a convergence remedy. No model/source changes or new native runs
were made during this inspection.

## Further offline isolation and experimental LTE startup correction

### Conditioning is not only a trace-ion conservation issue

On the saved depth1 block, converting to absolute-population variables gives
scaled condition1=7.32518e40. Exactly eliminating each number-conservation
row using the largest-population variable as dependent only reduces this to
2.66965e40. Simulating native FIX_IMP trace-ion row replacements still gives
2.18141e40. These are local algebra experiments, not altered atmosphere solves.

The absolute-population block has about140 singular values below1e-12 of
the largest at double resolution. The least determined numerical modes involve
C IV and Fe V excited levels. Their isolated ion blocks have condition estimates
about2.15e27 and5.27e38, despite holding about4.18% of carbon and13.60% of iron.
For example, a Fe V low-level row contains a derivative with respect to Fe V
SL131 around1.75e41 while its own diagonal is about0.00273. SL131's initial
population is only5.54e-74. These are nearly absent levels inside an abundant
ion, so freezing only whole trace stages cannot address them.

Freezing individual low-population levels while retaining exact elemental
conservation reduces conditioning, but not to acceptable values at defensible
cutoffs: population-fraction thresholds1e-30 and1e-15 give about1.46e20 and
1.19e17. A threshold1e-8 would freeze2011 variables and still gives3.53e11.
This is not a supported physical remedy. Detailed bound-free/radiative derivative
assembly needs further attribution; a direct excited-target term contains
REV_HNST*WSE*JREC/DI(target), so nearly absent target levels are a plausible
amplifier. That mechanism has not yet been proven to be the source of each
large captured coefficient.

### Two LTE initialization defects have a tested local correction

Used disposable zero-iteration model copies and isolated executables only.
The installed CMFGEN tree and actual model were never modified.

1. DET_LTE_ED initializes TEMP=T and then assigns T again when T<TMIN. It
   therefore ignores the requested floor. Correcting this assignment to TMIN
   alone changes outer stored Ne from1.85826e-8 to6300.2701, but leaves
   maximum reconstructed charge mismatch5.6188% (outer charge sum6306.5486).
2. RECONSTRUCT_DC_ESTIMATES iterates charged-ion density for occupation
   probabilities while keeping ED fixed. LTE departure-coefficient conversion
   and normalization can therefore invalidate the Saha ED estimate. Added an
   LTE-only bounded fixed-point loop: retain original log coefficients and
   continuum seeds, reconstruct at current ED, compute the charge sum, and
   geometrically damp ED toward that sum. Stop at relative1e-10 or fail after
   100 passes. Include the new control_variable_mod dependency in Makefile.

The combined correction converges in30 outer passes with a last reconstruction
residual7.6095e-11. The saved state uses ED equal to the charge sum: outer
Ne6306.544035611174 and maximum relative mismatch1.55431e-15. Every saved
population is finite and positive, with physical T retained (outer1736.54 K).
Problematic excited-level seeds are much less extreme: C IV SL32=6.62e-21,
Fe V SL131=3.39e-20, and N V SL19=4.53e-30. Compared with POP, the count of
outer population variables below1e-30 falls from311 to12; none are below1e-60.
This is a starting estimate, not proof of correct NLTE populations.

An additional isolated zero-iteration test with IT_ON_T=T completes all five
grey-refinement passes, avoiding the prior crash. Maximum grey-loop T updates
are initially1.73%, ending near0.237%; saved temperature differs by up to1.4104%
from no-grey. The final state remains finite and positive, with maximum charge
mismatch3.54e-7. A diagnostic guard rejects nonfinite/nonpositive grey J before
its fourth root; it was never triggered in this corrected test. The run took
under its180-second bound; no full solver iteration was performed.

Regression tests on ED and POP initializations using the same temporary
executable produce bit-for-bit identical200970-value vectors to their respective
saved baselines. These demonstrate the new LTE branch does not disturb these
two demonstrated initialization paths; broad model coverage is not established.

Candidate runtime, compiler sources, zero-step workspaces, reports and hashes
are preserved under `.model_Bstar3502-diagnostics/lte-startup-v1/`. The no-grey
experimental seed is in model/, the grey-enabled result in grey-model/.
Experimental patches exported for source review:

- `doc/developer/patches/bstar3502-lte-startup-experimental.patch`: floor,
  charge-consistent LTE reconstruction, and build dependency.
- `doc/developer/patches/bstar3502-grey-intensity-guard-experimental.patch`:
  separate diagnostic grey-J guard.

Neither patch has been applied to the installed source or registered as an
automatic remedy. Existing recovery requires both startup and full-continuation
validation; zero-step success alone does not satisfy that requirement.
The next useful native test is one full fresh-BA step from the new charge-
consistent LTE no-grey seed, with the same physical controls and lambda-off
recipe used for ED/POP, ideally retaining the outer matrix diagnostics. This
can establish whether a less pathological seed improves the actual rate
Jacobian. The actual model remains the previous POP diagnostic checkpoint2;
no new actual-model preparation was performed in this investigation turn.

### Prepared: one full step from corrected LTE initialization

On user request, the active `models/test/model_Bstar3502` now holds the
charge-consistent LTE no-grey initialization from
`.model_Bstar3502-diagnostics/lte-startup-v1/model/`. POINT1/POINT2/SCRTEMP
hashes match that tested seed; restart record/counter1 is initialization,
and the next full iteration is2. The previous instrumented POP checkpoint2,
its outputs and matrix records are preserved with SHA256 manifest under
`.model_Bstar3502-history/pop-outer-diagnostic-result-checkpoint-2/`.
BA and radiation caches were retired there; prior diagnostic records were
archived and removed from the active directory to avoid mixed results.

Built `.model_Bstar3502-diagnostics/lte-outer-matrix-v1/exe/cmfgen_dev.exe`
by linking the previously tested experimental LTE/grey-guard objects together
with the outer-matrix instrumentation and installed main objects/archives.
Build manifest records the link command and input/output hashes. Installed
source, executable and global configuration were not changed. The candidate
LTE seed is already initialized, so this test requires continuation, not a
fresh-start request. VADAT and IN_ITS are byte-identical to the previous POP
full-step recipe: fresh BA, variable temperature, lambda requests disabled,
one iteration. Physical inputs and regular *_IN files match the seed inputs.

Runner preflight reports ready, continuation, initial checkpoint1, and the
explicit combined executable. No full iteration was run during preparation.
Command from the repository root, using the usual Python environment:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic mode OFF and fresh start OFF. Native matrix output adds about200MB.
The active NEXT_DIAGNOSTIC_RUN.md repeats the instructions; runtime
prepared-run-plan.json preserves the reviewed preflight. This experiment
must establish whether the corrected LTE seed improves the full NLTE solve;
its zero-step charge consistency alone does not establish convergence.

### Corrected LTE full-step result: 20261021T181703Z-acb91ea9

The requested one-step continuation completed normally (native return0,
validated success), with native first iteration2 and final checkpoint2. The
combined isolated executable was used. All200970 saved values are finite and
positive. Maximum relative saved charge mismatch is8.02016e-7; at depth1 it
is3.44546e-10. This validates the first full continuation after the candidate
LTE startup, but not convergence or a broadly applicable automatic remedy.

Measured improvement over the instrumented POP test:

| Quantity | POP step | Corrected LTE step |
| --- | --- | --- |
| Equilibrated Schur rcond, depth1 | 1.17e-65 | 5.94087e-20 |
| Equilibrated Schur rcond, depth2 | 1.67e-55 | 1.59912e-19 |
| Max componentwise backward error, depth1 rows | 0.999999696 | 1.44786e-9 |
| Max componentwise backward error, depth2 rows | 0.999999453 | 2.14077e-9 |
| Variables exceeding100% | 23917 | 52339 |
| Variables exceeding10% | 70705 | 152186 |

Outer Ne-equation backward errors are1.01e-12/3.18e-12; T-equation errors
2.69e-15/3.67e-15. The same full-precision original-row residual analyzer
was used. The blocks remain ill-conditioned; these local residuals are not
forward-error estimates or evidence about unrecorded interior rows. The
corrected initialization has nevertheless removed the demonstrated gross
outer linear residual failure in this first step.

Maximum raw increase is6.35529e19% at depth19, equation829 (O VI, the terminal
continuum after explicit O V). The raw seed1.52631e-21 would increase by
0.000970014 cm^-3, only6.21852e-7 of the local oxygen density1559.878 cm^-3.
The saved change is bounded to a factor10, ending1.52631e-20. Thus this largest
percentage alone does not imply a large absolute oxygen change. Maximum raw
decrease is1.76e6%; the first-step residual distribution remains substantial.
Saved population ratios range0.1–10. The minimum major-species scale is
2.3998e-5, so some physically important steps are still heavily damped.

Outer T changes1736.53991 ->1736.91556 K (+0.021632%), whereas its raw request
is+125.541%. Depths33/34 reach the+20% temperature limit. The outer radiative
luminosity evaluated from the starting LTE state is3.38567e6 Lsun versus
2.00000046e5 at the inner boundary (ratio16.9283). This is substantially worse
than the POP starting radiation agreement (ratio1.01513). OUTGEN/OBSFLUX of
this single iteration evaluate radiation before the saved Newton update;
they do not establish the updated checkpoint's flux agreement. Photospheric
hydrostatic RMS error is about10.1%, maximum23%; outer J(mom)/J(ray warning
persists. LTE is a numerically better seed, not yet a physically consistent
NLTE solution.

Copied/hash-verified matrix records, condition log, pointer and correction
outputs, OUTGEN, full residual analysis and assessment to
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261021T181703Z-acb91ea9/`.
No active model inputs or restart state were changed during assessment.
Suggested next experiment: another single full continuation step from this
checkpoint with the same isolated executable and unchanged controls, auto OFF,
fresh start OFF. This will measure whether nonlinear residuals and luminosity
agreement improve after updating populations, before committing to a long run.

### Second corrected-LTE continuation: 20261021T220043Z-647dc2f2

Native return0; runner success; first native iteration3, final pointer3.
Elapsed about25 minutes. The record2/3 population vectors were read directly
from the current SCRTEMP so comparison uses the actual immediately preceding
checkpoint. All200970 saved values remain finite and positive; maximum relative
charge mismatch2.80479e-6 (outer1.65322e-9).

| Quantity | Iteration2 | Iteration3 |
| --- | --- | --- |
| Variables above100% correction | 52339 | 40480 |
| Variables above10% correction | 152186 | 144089 |
| Variables above1% correction | 166634 | 158112 |
| Maximum raw increase, percent | 6.35529e19 | 6.08247e18 |
| Maximum raw decrease, percent | 1.76e6 | 6.69e7 |
| Minimum major-species scale | 2.3998e-5 | 4.4082e-5 |
| Outer/inner luminosity ratio | 16.9283 | 17.1805 |
| Schur rcond depth1 | 5.94087e-20 | 3.02864e-15 |
| Schur rcond depth2 | 1.59912e-19 | 4.14223e-15 |
| Max componentwise backward error depth1 | 1.44786e-9 | 1.56780e-10 |
| Max componentwise backward error depth2 | 2.14077e-9 | 1.24639e-11 |

Largest raw increase remains terminal O VI at depth19: population1.52631e-20,
raw requested increase0.000928373 cm^-3. The tenfold reduction in the percentage
is largely explained by the tenfold growth of its tiny starting population;
the absolute requested increment declined only about4.3%. The reduction in
maximum percentage is therefore not by itself strong convergence evidence.
Radiative luminosity agreement did not improve. Outer J(mom)/J(ray warning
increased from >20% to >50%. Photospheric hydrostatic RMS11.2%, maximum39.2%.

Important qualification: iteration3 held T fixed at all90 depths. Native
OUTGEN explicitly says so, raw full-precision solution has T=0, and the saved
T vector is bitwise unchanged (outer1736.91556 K). VADAT, including the archived
run inputs, still has FIX_T=F and FIX_T_AUTO=F; IN_ITS lambda controls are F.
Consequently the better matrix conditioning is partly for a different system
with temperature frozen, and cannot be attributed entirely to seed evolution.

Source inspection identified an independent BAMATPNT field-order defect:

- `new_main/subs/store_ba_data_v3.f`, INIT_BA_DATA_PNT_V3 writes successful,
  then FIXED_T, then COMPUTE_BA.
- `new_main/subs/read_ba_data_v3.f` reads successful, then COMPUTE_BA_RD,
  then FIXED_T. The two flags are swapped.
- `new_main/cmfgen_sub.f` startup passes CHK=.FALSE. to READ_BA_DATA_V3,
  so even a fresh-BA request attempts this initial cache read and can import
  the third flag as FIXED_T. COMPUTE_BA is subsequently set from input but
  FIXED_T is not restored there. Thus a saved COMPUTE_BA=T can freeze T
  despite FIX_T=F. Both cached flags in the current pointer are T; the initial
  tested LTE step had both caches removed and did vary T.

Next useful controlled experiment: preserve checkpoint3, retire BAMAT and
BAMATPNT before another single continuation using the same isolated executable,
then verify nonzero T corrections. Do not repeat the same command with the
current BA cache and assume temperature is variable. Fixing the reader order
and testing both mixed flag cases is a separate source change; no source or
active model input/cache/restart was modified during this assessment.

Matrix output and hashes, OUTGEN, corrections and full analysis are saved at
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261021T220043Z-647dc2f2/`.
The condition log contains both iterations; its final two rows belong to3.

### Prepared checkpoint3 continuation without cached BA flags

On user request, preserved checkpoint3, controls, input estimates and diagnostic
outputs with SHA256 verification in
`.model_Bstar3502-history/lte-fixed-temperature-result-checkpoint-3/`.
BAMAT was already absent; moved BAMATPNT to that backup's retired/ directory.
This distinction strengthens the diagnosis: OUTGEN records a successful
BAMATPNT header read followed by failure opening BAMAT, so the swapped flag
can leak into FIXED_T even when no matrix is available for reuse. Removing
the pointer prevents that startup read entirely. No source fix was installed.

POINT1/POINT2/SCRTEMP and VADAT/IN_ITS are hash-verified unchanged. Radiation
caches retained. Moved prior full-precision matrix files and condition log
into the checkpoint backup, keeping the diagnostic marker enabled. Runner
preflight is ready for continuation from3, expected next full iteration4,
using the unchanged isolated lte-outer-matrix-v1 executable. No native model
iteration was run during preparation. Command from repository root:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF, fresh start OFF. Verify variable-T behavior from the native
solution after this run. NEXT_DIAGNOSTIC_RUN.md contains these instructions;
the backup includes the reviewed next-test-plan.json.

### Attempt4 stopped before solving: 20261021T223055Z-a0e9cb0a

The attempt is NOT a completed iteration. Native Fortran STOP returned0,
but the runner correctly classified invalid_output with inner_flux_accuracy,
unchanged MOD_SUM and RVTJ. Native first counter4 was observed; POINT1 remains3.
SHA256 verification against the prepared checkpoint3 backup confirms POINT1,
POINT2 and SCRTEMP are all unchanged. CORRECTION_SUM is also unchanged and
belongs to iteration3; no OUTER_MATRIX binary or condition log was produced.
Therefore there is no new linear solve, no updated T, and no new correction
counts to compare. Removing the BA pointer did not itself change populations.

The stop is in cmfgen_sub.f's normalized luminosity guard, before
SOLVE_FOR_POPS. The test rejects normalized luminosities outside0.5–2 from
ROSS_PHOT_DPTH_INDX through ND when STOP_IF_MW is true (default). Thus the
attempt did not reach the point where variable-T behavior could be verified.

OBSFLUX normalized luminosity profile changed from min0.76156 (depth36) in
iteration3's radiation evaluation to min-1.3267 (depth25) in this attempt.
It is now negative over depths10–65; total radiative luminosity is also
negative in this range, so this is not merely the mechanical correction.
Outer radiative luminosity is3.87920199e6 Lsun versus2.00000046e5 at the inner
boundary (ratio19.3960). The corresponding normalized corrected check at
the outer point is19.413. Photospheric hydrostatic RMS error65.3%, max191%.
These radiation and force diagnostics evaluate checkpoint3, whereas the
previous successful attempt evaluated checkpoint2 before writing3.
Consequently the prior correction-count improvement did not guarantee an
improved radiation/thermal state after the saved population update.

Copied/hash-verified OUTGEN, OBSFLUX, WARNINGS, controls and pointer records,
plus assessment.json to
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261021T223055Z-a0e9cb0a/`.
No active inputs, caches or checkpoint data were changed during assessment.
Do not repeatedly rerun this setup or disable STOP_IF_MW as a convergence fix.
A useful next controlled diagnostic is reevaluating the same checkpoint3 with
radiation caches retired as well as BA absent, to distinguish radiation-cache
history from a bad saved population/T state before choosing a thermal reset
or a more strongly damped restart from an earlier checkpoint. This cause is
not yet established; this assessment did not perform another native run.

### Prepared: radiation-cache rebuild at checkpoint3

On user request, backed up failed attempt4's diagnostics, controls and current
checkpoint to `.model_Bstar3502-history/lte-inner-flux-stop-checkpoint-3/`, with
SHA256 manifest. Moved EDDFACTOR and EDDFACTOR_INFO to its retired/ directory.
BAMAT, BAMATPNT, ES_J_CONV, ES_J_CONV_INFO and OLD_J_FILE were already absent.
POINT1/POINT2/SCRTEMP remain hash-identical to checkpoint3 and its prior backup;
VADAT/IN_ITS are unchanged. STOP_IF_MW remains enabled. The isolated executable
matches its build-manifest hash. Outer diagnostic marker remains enabled and
no previous matrix records/condition log are present in the active directory.

Runner preflight is ready for continuation from3, expected iteration4. Run:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF, fresh start OFF. This tests whether rebuilding radiation
factors changes the flux failure at the same saved population/T state; it is
not an established convergence remedy. No native iteration was run during
preparation. Active NEXT_DIAGNOSTIC_RUN.md records the instructions, and the
backup contains the reviewed next-test-plan.json.

### Radiation-cache rebuild result: 20261021T230101Z-0aee2c28

The controlled radiation rebuild reproduces the same pre-solve failure.
Runner status invalid_output, native return0; native counter4 observed, but
POINT1 stays3. POINT1/POINT2/SCRTEMP hashes match both the immediately preceding
failed-attempt backup and the original checkpoint3 backup. Correction output
is unchanged and no outer matrix diagnostic output was produced. The model
did not perform a new Newton step and variable-T behavior remains untested.

Freshly rebuilt EDDFACTOR gives outer/inner radiative luminosities
3.87921166e6/2.00000046e5, compared with3.87920199e6/2.00000046e5 with retained
radiation history: relative outer difference about2.49e-6. Normalized check
again reaches-1.3267 at depth25, is negative at depths10–65, and has outer
value19.413. Maximum absolute difference between the two printed normalized
profiles is1e-4. The same inner-flux safeguard fires before SOLVE_FOR_POPS.
Hydrostatic RMS/max errors remain65.3%/191%. This strongly excludes the
retained radiation caches as the explanation for this particular failure;
it does not prove which population/thermal or transfer issue causes it.

Recorded failed-attempt diagnostics and hashes plus assessment.json in
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261021T230101Z-0aee2c28/`.
No active inputs, caches or restart data were changed during assessment.

Recommended next experiment: return to checkpoint2 (before the unintended
fixed-temperature population update that produced3), retire both BA and
radiation caches, and repeat one full iteration3 with variable temperature.
The radiation evaluation of checkpoint2 passed the inner safeguard during
the prior iteration3, although its outer luminosity was already excessive.
This tests the role of the unintended fixed-T step without bypassing the
safeguard. It is a diagnostic branch, not a demonstrated remedy; its inputs
have not yet been prepared. Repeating checkpoint3 unchanged is uninformative.

### Prepared: replay iteration3 from checkpoint2 with variable temperature

On user request, preserved checkpoint3, the failed rebuilt-radiation attempt,
controls and diagnostics under
`.model_Bstar3502-history/lte-rebuilt-radiation-stop-before-replay-step-3/`,
with SHA256 manifest and reviewed next-test-plan.json. Restored POINT1/POINT2
from the saved successful iteration2 result (hash-checked against its manifest).
SCRTEMP remains unchanged: its record2 still contains the desired checkpoint,
all200970 entries are finite/positive, and both outer-depth population vectors
are bit-for-bit identical to the archived matrix inputs for the prior
iteration3. Direct-access restart therefore selects the intended saved2,
while later record3 remains available in the backup before being overwritten.

Retired regenerated EDDFACTOR and EDDFACTOR_INFO; BAMAT/BAMATPNT and other
radiation caches were already absent. VADAT/IN_ITS remain hash-identical.
FIX_T=F, FIX_T_AUTO=F, fresh BA, lambda requests disabled. STOP_IF_MW remains
enabled. The isolated executable is unchanged and matches its build hash.
No previous outer matrix binary/condition records are present; marker enabled.
Existing RVTJ/MOD_SUM/correction/radiation outputs remain historical until
regenerated; restart selection uses pointers and SCRTEMP, not those outputs.

Preflight ready: continuation record2/counter2, expected next iteration3.
No native iteration was run during preparation. From the repository root:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF, fresh start OFF. Active NEXT_DIAGNOSTIC_RUN.md contains the
instructions. Afterward verify native variable-temperature behavior and
compare this branch against the prior fixed-T iteration3.

### Variable-temperature iteration3 replay: 20261021T233910Z-ee8b1d45

Replay from checkpoint2 succeeded (native return0, runner succeeded), observed
first native counter3 and final pointer3. All200970 stored variables are finite
and positive; maximum relative charge mismatch2.73931e-6 (outer1.63276e-9).
This time T changed at all90 depths, confirming the cache-retirement workaround
allowed the intended variable-temperature step. Outer T1736.91556 ->1740.64806 K
(+0.214893%); depths29–31 hit+20%, with substantial updates nearby.

| Quantity | Iteration2 | Fixed-T iteration3 | Variable-T replay3 |
| --- | --- | --- | --- |
| Corrections above100% | 52339 | 40480 | 42786 |
| Corrections above10% | 152186 | 144089 | 148123 |
| Corrections above1% | 166634 | 158112 | 162631 |
| Raw maximum increase (%) | 6.35529e19 | 6.08247e18 | 6.45368e18 |
| Raw maximum decrease (%) | 1.76e6 | 6.69e7 | 1.37e7 |
| Minimum major-species scale | 2.3998e-5 | 4.4082e-5 | 4.4032e-5 |

The largest raw increase is still terminal O VI at depth19; requested absolute
increase0.000985032 cm^-3, comparable to iteration2's0.000970014. Most of the
percentage reduction again reflects growth of a tiny seed. The new step is
not converged and some major-variable updates remain heavily damped.

Outer Schur rcond is5.14786e-19/1.39280e-18 at depths1/2; maximum original-row
componentwise backward errors2.28237e-10/2.29925e-10. Temperature-equation errors
2.61e-16/2.49e-15; raw outer T request+143.95%, subsequently damped. These local
measurements establish good measured residuals despite ill-conditioning, not
global forward accuracy or thermal convergence.

The radiation diagnostics evaluate the shared INPUT checkpoint2: outer/inner
luminosity3.43610331e6/2.00000046e5, virtually identical to the prior iteration3
from that same input. Hydrostatic RMS/max11.2%/39.2%, >50% outer J warning.
They cannot assess the newly saved variable-T checkpoint3. A next radiation
evaluation is necessary to test whether allowing T avoids the prior branch's
negative inner flux. Do not interpret this successful solve as demonstrating
that the next iteration's luminosity safeguard will pass.

Archived/hash-verified matrix data, conditions, OUTGEN, pointers and corrections,
analysis.json and assessment.json in
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261021T233910Z-ee8b1d45/`.
Active checkpoint and controls were not modified during assessment. BAMATPNT
has been regenerated with both flags T; the swapped-reader source bug remains
unfixed in the isolated executable. Before another variable-T continuation,
retire the BA pointer again. Recommended next diagnostic: one continuation
from the NEW checkpoint3, fresh BA/radiation caches, auto OFF/fresh start OFF,
then evaluate whether radiation/thermal agreement improves. Preparation not
yet performed; repeating the command without cache retirement is unsuitable.

### Prepared: continuation4 from the variable-temperature checkpoint3

On user request, preserved the successful variable-T replay checkpoint3 and
its diagnostics in `.model_Bstar3502-history/lte-variable-temperature-result-checkpoint-3/`,
with verified SHA256 manifest. Retired BAMATPNT, EDDFACTOR and EDDFACTOR_INFO
into its retired/ directory; other BA/electron-scattering/old-J caches were
already absent. Archived prior outer matrices and condition log, leaving the
marker enabled. Installed and isolated executables remain unchanged.

POINT1/POINT2 match the saved successful replay result and remain at3;
SCRTEMP and VADAT/IN_ITS are hash-verified unchanged through preparation.
This continues the NEW variable-temperature branch, not the earlier fixed-T
checkpoint3. STOP_IF_MW remains enabled. Preflight ready for continuation3,
expected next iteration4. No native iteration run during preparation.

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF, fresh start OFF. The next radiation evaluation will determine
whether the new checkpoint avoids the earlier branch's luminosity failure.
NEXT_DIAGNOSTIC_RUN.md contains instructions; reviewed next-test-plan.json is
in the backup directory.

### Variable-T branch continuation4 failed: 20261022T002603Z-0bb7d46b

The attempt stopped at the same inner luminosity safeguard before the Newton
solve. Native return0, runner invalid_output; counter4 observed, pointer stays3.
Hashes of POINT1/POINT2/SCRTEMP match the variable-temperature checkpoint3
backup. CORRECTION_SUM unchanged; no new outer matrix diagnostics. Thus no
new corrections were computed, and all active correction displays still
refer to the successful replay3.

The normalized luminosity minimum is-1.3732 at depth25 (fixed-T branch was
-1.3267), negative at depths10–65; outer corrected ratio19.517. Outer/inner
radiative luminosities3.89998173e6/2.00000046e5, ratio19.4999. Hydrostatic
RMS/max70.6%/198%, versus65.3%/191% on the failed fixed-T branch. This is not
an improvement despite the successful variable-T linear solve. The inputs
had both BA and radiation caches retired, so the cached flag defect and
radiation cache history do not explain this repeated failure. They remain
real independent concerns, but removing them is insufficient for convergence.

The prior iteration3 radiation evaluation describes checkpoint2: normalized
minimum0.76157, no negative values; hence the saved update2->3 deteriorates
the radiation state in both branches. Good outer linear residuals, finite
positive populations, and near charge conservation are insufficient to
ensure a good nonlinear atmosphere update.

Copied/hash-verified diagnostics, controls and pointer records plus assessment
into `.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T002603Z-0bb7d46b/`.
No active inputs, caches or restart were changed during this assessment.

Recommended next controlled branch: restore checkpoint2 and reduce update
limits, e.g. MAX_LIN=2 instead of10 and MAX_dT=0.05 instead of the default0.2,
retaining MAJOR scaling, variable temperature, fresh BA/radiation caches and
the safeguard. One solver step followed by a radiation evaluation tests whether
the aggressive nonlinear update is the problem. These are experimental
limits, not an established remedy; preparation and execution are not yet done.
If reducing limits still produces bad radiation, inspect the nonlinear
residuals/derivatives in the failing interior region rather than assuming
that the outer linear solve or tiny O VI percentage explains the failure.

### Prepared: smaller nonlinear update from checkpoint2

On user request, preserved the variable-T checkpoint3 and failed continuation4
in `.model_Bstar3502-history/lte-variableT-flux-stop-before-smaller-step/` with
verified hashes and reviewed next-test-plan.json. Restored the saved iteration2
POINT1/POINT2; SCRTEMP unchanged and record2 retained. Its outer-depth1/2
population vectors exactly match the archived inputs to the original iteration3;
all checkpoint2 variables are finite and positive.

VADAT diff contains only MAX_LIN10->2 and explicit MAX_dT=0.05 (default0.2).
MAJOR scaling and variable T remain enabled; IN_ITS unchanged, one iteration,
lambda requests disabled. These limits permit factor0.5–2 population changes
and at most5% T corrections. Marked VADAT inputs modified with the backup.
Retired EDDFACTOR and EDDFACTOR_INFO; BA and other radiation caches already
absent. No prior matrix records/condition log present; diagnostic marker enabled.
Installed source and isolated executable remain unchanged and executable hash
matches its manifest. STOP_IF_MW remains enabled.

Preflight ready, continuation2 -> expected iteration3. No native iteration run
during preparation. Command from repository root, automatic OFF/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md records this branch. The experiment tests smaller updates;
next-step radiation evaluation will still be needed to assess the saved state's
luminosity behavior. Old summary/correction outputs are historical until replaced.

### Smaller-step iteration3 result: 20261022T011328Z-ad2416d9

The MAX_LIN=2 / MAX_dT=0.05 replay from checkpoint2 succeeded (native return0,
runner succeeded, first native3, final pointer3). All200970 stored values are
finite and positive. Maximum relative charge mismatch8.02499e-7, outer
4.87682e-10. T varied at all90 depths. Actual population ratios are exactly
bounded0.5–2; maximum T update5%, reached at depths31/32. Outer temperature
1736.91556 ->1737.33028 K (+0.023877%). Thus both requested limits are active.

Unscaled diagnostics are effectively unchanged from the larger replay because
the input checkpoint2 and rate solve are the same: above100%42785 (previous
42786), above10%148123, above1%162631. Largest raw increase6.45368e18% at
terminal O VI depth19, raw absolute increment0.000985032 cm^-3. CORRECTION_SUM
is generated before damping, so its unchanged counts do not mean MAX_LIN was
ignored or that the applied step was unchanged. Minimum major-species scale
4.8924e-6 versus4.4032e-5 in the larger replay.

Local original-row maximum componentwise backward errors at depths1/2 are
2.71905e-10 /4.47314e-11. Schur rcond5.14786e-19/1.39281e-18. Linear residual
quality remains good in the recorded outer rows, with the same limitations
on forward accuracy and interior behavior described above.

Radiation diagnostics again evaluate INPUT checkpoint2, and are identical
to the larger replay's printed output: outer luminosity3.43610331e6 Lsun vs
inner2.00000046e5, hydrostatic RMS/max11.2%/39.2%, >50% outer J warning. They
do not yet test the NEW smaller-step checkpoint3. A subsequent radiation
calculation must establish whether this branch avoids negative inner flux.

Copied/hash-verified matrices, conditions, OUTGEN, corrections and pointers,
plus analysis.json and assessment.json, to
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T011328Z-ad2416d9/`.
No active inputs/caches/restart changed during assessment. Recommend one more
continuation from this smaller-step checkpoint3 with the reduced limits
retained, BA pointer and radiation caches retired, auto/fresh start OFF.
This is a controlled evaluation of the damped state, not yet a proven fix.
Preparation has not been performed; the regenerated BA pointer must be retired
before running again to avoid the known cached temperature-flag defect.

### Prepared: continuation4 from smaller-step checkpoint3

On user request, backed up the smaller-step checkpoint3, controls and outputs
with SHA256 verification under
`.model_Bstar3502-history/lte-smaller-step-result-checkpoint-3/`.
Retired BAMATPNT, EDDFACTOR and EDDFACTOR_INFO into retired/; other BA and
radiation caches already absent. Previous outer matrices and condition log
archived; diagnostic marker remains enabled. Hashes verify checkpoint and
VADAT/IN_ITS unchanged. Explicitly verified MAX_LIN=2 and MAX_dT=0.05 remain
active. Variable T, fresh BA, lambda requests disabled, STOP_IF_MW enabled.
Isolated executable hash matches its build manifest; no installed changes.

Preflight ready: continuation from3, expected next iteration4. No native run
performed during preparation. From repository root:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF/fresh start OFF. This radiation evaluation tests the new damped
checkpoint3 against the prior branches' inner-flux failure. Instructions in
NEXT_DIAGNOSTIC_RUN.md; reviewed next-test-plan.json saved with the backup.

### Smaller-step continuation4 succeeds: 20261022T014119Z-337134e8

Native return0, runner succeeded, observed first iteration4 and final pointer4.
Unlike both larger-step branches, the smaller-step checkpoint3 passes the
inner luminosity safeguard. Normalized luminosity minimum improves0.76157
at checkpoint2 evaluation to0.79584 at checkpoint3 evaluation (both depth36),
with no negative values. Larger-step checkpoint3 evaluations gave negative
values down to-1.3267 (fixed T) or-1.3732 (variable T). This supports smaller
nonlinear updates as a useful remedy for the demonstrated immediate failure,
although it does not establish eventual convergence.

| Quantity | Smaller iteration3 | Smaller iteration4 |
| --- | --- | --- |
| Corrections above100% | 42785 | 39613 |
| Corrections above10% | 148123 | 145138 |
| Corrections above1% | 162631 | 162388 |
| Maximum raw increase (%) | 6.45368e18 | 3.22723e18 |
| Maximum raw decrease (%) | 1.37e7 | 2.56e7 |
| Minimum major-species scale | 4.8924e-6 | 6.8421e-6 |

Saved values all finite/positive; max relative charge mismatch1.08730e-6.
Population ratios0.5–2, T changed at all90 depths, max5% (8 depths hit limit).
Outer T1737.33028 ->1738.17891 K (+0.0488468%). The largest percentage still
belongs to terminal O VI depth19; its seed doubled and raw absolute increment
is essentially unchanged (0.000985151 vs0.000985032 cm^-3). The halving of that
percentage is therefore not evidence of comparable residual reduction.

Outer local backward errors remain small3.35988e-11/2.37779e-10; Schur rcond
9.74312e-19/2.63720e-18. Outer/inner radiative luminosity3.44289892e6/2.00000046e5
(ratio17.2145), so outer radiation equilibrium remains poor, slightly worse
than the prior evaluation. Hydrostatic RMS/max11.8%/41.3%, >50% outer J warning
persists. The new checkpoint4 radiation is not evaluated until the next pass.

Archived/hash-verified matrix outputs, conditions, corrections, OUTGEN and
pointers, analysis.json and assessment.json at
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T014119Z-337134e8/`.
No active checkpoint, controls or caches modified during assessment. Recommend
another single continuation from4 retaining MAX_LIN=2/MAX_dT=0.05 and retiring
BA/radiation caches beforehand. Preserve the safeguard and diagnostic controls;
a long unattended continuation is not justified by two successful damped steps.
Preparation not yet performed; regenerated BAMATPNT still needs retirement.

### Prepared: smaller-step continuation5

On user request, preserved checkpoint4, controls and diagnostics with verified
SHA256 manifest under `.model_Bstar3502-history/lte-smaller-step-result-checkpoint-4/`.
Retired BAMATPNT, EDDFACTOR and EDDFACTOR_INFO, with all other BA/radiation
caches already absent. Archived previous outer matrix records/condition log;
diagnostic marker remains enabled. Checkpoint and VADAT/IN_ITS hashes unchanged.
Verified MAX_LIN=2/MAX_dT=0.05 retained; isolated executable matches build hash.
Variable T, fresh BA, lambda requests disabled, STOP_IF_MW remains enabled.
Preflight ready for continuation from4, expected next iteration5. No native
iteration run during preparation. From repository root, auto/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Active NEXT_DIAGNOSTIC_RUN.md records the instructions. Backup includes the
reviewed next-test-plan.json. This evaluates the newly saved smaller-step4
radiation state and, if it passes the safeguard, computes the next update.

### Smaller-step iteration5: 20261022T091600Z-5a216fb6

Native return0, runner succeeded, first iteration5 and final pointer5.
The radiation evaluation of smaller-step checkpoint4 passes the inner safeguard;
normalized luminosity minimum improves0.79584->0.83207 (depth37), no negative
values. This follows0.76157 at input checkpoint2 and gives a consistent short
trend toward better inner luminosity agreement. Outer corrected normalized
ratio nevertheless grows17.229->17.258; outer/inner raw radiative luminosity
3.44852872e6/2.00000046e5 (ratio17.2426) remains severely out of equilibrium.

| Quantity | Iteration4 | Iteration5 |
| --- | --- | --- |
| Corrections above100% | 39613 | 36254 |
| Corrections above10% | 145138 | 140885 |
| Corrections above1% | 162388 | 161541 |
| Maximum raw increase (%) | 3.22723e18 | 1.61558e18 |
| Maximum raw decrease (%) | 2.56e7 | 5.88e7 |
| Minimum major-species scale | 6.8421e-6 | 1.0449e-5 |

Saved values all finite/positive; max relative charge mismatch1.08746e-6,
outer1.38099e-9. Population ratios remain0.5–2. T varied at all90 depths,
max5%, six depths reach limit. Outer T1738.17891->1740.05668 K (+0.10803%).
Outer measured backward errors2.69663e-13/3.43879e-11; Schur reciprocal
condition1.87072e-18/5.04977e-18. The good local linear residuals persist.

Largest percentage still terminal O VI at depth19: initial6.10524e-20,
raw absolute increment0.000986351 cm^-3, almost unchanged from0.000985151.
Its percentage halving mostly tracks doubling the tiny starting population,
not halving the absolute nonlinear correction. Major corrections and damping
remain large. Hydrostatic RMS/max13.8%/38.1%; RMS worsens slightly.

Native outer J(mom)/J(ray) warning rises to >1000%. All152174 parsed J_COMP
rows have positive outer J. The maximum printed/symmetric difference is about
200% (bounded symmetric normalization): at frequency2.129153e15 Hz one row
has Jmom7.027e-14 versus Jray8.2398e-9. This is an intensity disagreement,
not a >1000% emergent-flux error or a negative-J failure. The significant
outer transfer mismatch and luminosity excess remain unresolved.

Archived/hash-verified matrices, conditions, corrections, OUTGEN and pointers,
plus analysis.json/assessment.json in
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T091600Z-5a216fb6/`.
No active inputs/restart/cache changed during assessment. Another controlled
single continuation with the same smaller limits and BA/radiation retirement
is reasonable to measure whether inner improvement continues; outer agreement
must also be monitored. Do not call this converged or release the limits yet.
Preparation not performed; regenerated BAMATPNT must be retired before running.

### Prepared: smaller-step continuation6

On user request, preserved checkpoint5, controls and diagnostic outputs under
`.model_Bstar3502-history/lte-smaller-step-result-checkpoint-5/` with verified
SHA256 manifest. Retired BAMATPNT, EDDFACTOR and EDDFACTOR_INFO; other BA and
radiation caches already absent. Archived previous outer matrix records and
condition log; diagnostic marker remains enabled. Checkpoint and VADAT/IN_ITS
hashes unchanged. Verified MAX_LIN=2/MAX_dT=0.05 retained, and isolated executable
matches build hash. Variable T, fresh BA, lambda requests disabled and
STOP_IF_MW enabled. Preflight ready: continuation5 -> expected iteration6.
No native iteration run during preparation. From repository root:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

Automatic OFF/fresh start OFF. NEXT_DIAGNOSTIC_RUN.md records instructions;
backup includes reviewed next-test-plan.json. This evaluates the saved
checkpoint5 radiation state and computes the next update if the safeguard passes.

### Smaller-step continuation6 fails: 20261022T095011Z-47700866

Native returns0 via STOP; runner correctly reports invalid_output. Native
counter6 observed but final pointer remains5. POINT1/POINT2/SCRTEMP hashes
match the checkpoint5 preparation backup, CORRECTION_SUM unchanged and no
outer matrix outputs. There is no completed iteration6 or new correction set.

The radiation evaluation of checkpoint5 fails the same inner luminosity
safeguard. Normalized luminosity minimum-1.4242 at depth24, negative57 depths,
outer corrected ratio19.669. The preceding checkpoint4 evaluation passed
(min0.83207 at depth37, no negatives). Outer/inner radiative luminosity
3.93038605e6/2.00000046e5 (ratio19.6519). Hydrostatic RMS/max71.0%/200%.
The reduced MAX_LIN=2/MAX_dT=0.05 limits delayed the negative-flux failure
but have not established sustained convergence. Cached BA flags, radiation
history, or freezing T are insufficient explanations: caches were retired
and checkpoint5 came from a verified variable-T, bounded population update.

Direct saved-vector comparison4->5 shows changes to appreciably populated
ions, not just the tiny O VI level dominating the percentage metric. At
depth25 T10969.04->11506.17 K; Fe III fraction0.41695->0.30395 and Fe IV
0.58290->0.69582; O II0.58418->0.51262, O III0.41581->0.48737. At depth37
T12089.52->12512.46 K; Al III0.62344->0.49629, C III0.84198->0.90536,
N III0.15846->0.22025. These co-occurring changes identify the interior
update to inspect; they do not establish which ion, rate or derivative
caused the flux failure. Do not infer causation from fraction changes alone.

Archived diagnostics, controls/pointers with verified hashes and assessment
at `.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T095011Z-47700866/`.
No active controls/restart/caches changed during assessment. Repeating
checkpoint5 unchanged or simply assuming additional bounded iterations will
converge is not justified. Next investigation should isolate the checkpoint4
->5 interior population/T update and its radiation/energy-balance effects,
especially depths24–37. Further reducing limits could postpone the symptom
again and is not a demonstrated fix; keep STOP_IF_MW enabled while diagnosing.

### Prepared: temperature-isolation test of failed checkpoint5

On user request for the next diagnostic run, preserved complete original
checkpoint5, controls and failed-attempt outputs with verified SHA256 hashes
in `.model_Bstar3502-history/lte-smaller-step-flux-stop-before-temperature-isolation/`.
Prepared a diagnostic hybrid: retain checkpoint5 populations and Ne, replace
only its90 temperature values with checkpoint4 T. Reference record4 was
bitwise verified against the saved smaller-step checkpoint4 backup. Verified
all modified record5 values finite/positive, all populations/Ne bitwise
unchanged, T exactly equal to reference4, and EVERY byte outside the90 float64
T locations unchanged. Manifest records offsets, original/prepared SCRTEMP
hashes and verification. Pointers still select record/counter5.

This tests the contribution of the last T update while holding saved
populations/Ne fixed. It is an experimental starting state, not an accepted
physical solution. Fresh radiation evaluation either reproduces the failure,
implicating the population update or other effects beyond T alone, or improves
it, indicating T sensitivity at these populations. Neither outcome alone
identifies a faulty rate/derivative. If the guard passes, the ordinary main
stage also performs one new Newton step; its radiation output precedes that
update and must be used for the controlled comparison.

Retired EDDFACTOR/EDDFACTOR_INFO; other radiation/BA caches already absent.
Controls unchanged: MAX_LIN=2, MAX_dT=0.05, variable T, lambda requests off,
fresh BA and STOP_IF_MW enabled. Marker enabled, no old matrix/condition files.
Executable unchanged/hash-verified. Marked SCRTEMP modified with backup link.
Preflight ready for continuation5, expected attempted iteration6. No native
run performed during preparation. From repository root, auto/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md explains the hybrid and output interpretation; reviewed
next-test-plan.json stored with the backup. Old RVTJ/MOD_SUM/correction outputs
remain historical until regenerated; the actual restart uses SCRTEMP record5.

### Temperature-isolation result: 20261022T102318Z-3394bb2e

The hybrid (checkpoint5 populations/Ne with checkpoint4 T) reproduces the
inner-flux failure before solving. Native return0 via STOP; runner invalid_output,
unchanged MOD_SUM/RVTJ, pointer stays5, no new matrix diagnostics/corrections.
SCRTEMP hash exactly matches the prepared hybrid hash in the preparation
manifest. POINT1/POINT2 match the preserved originals. Thus the diagnostic
checkpoint has not been advanced or changed by this attempt.

| Quantity | Original checkpoint5 T5 | Same populations/Ne with T4 |
| --- | --- | --- |
| Minimum normalized luminosity, depth24 | -1.4242 | -1.4212 |
| Minimum radiative luminosity, Lsun | -284920 | -284320 |
| Outer radiative luminosity, Lsun | 3930386.05 | 3929743.88 |
| Photospheric hydrostatic RMS, percent | 71.0 | 70.2 |

Maximum absolute difference of printed normalized profiles is0.00301.
Raw Luminosity and Total Radiative Luminosity are identical at the failing
depth; this is not a mechanical-luminosity bookkeeping correction. Restoring
the entire previous T profile barely changes the failed radiation evaluation.
This strongly shifts the investigation to the population update4->5 (or the
transfer/opacity response to it), rather than the last T increment alone.
It does not establish which species or derivative is responsible, or exclude
longer-term thermal effects and interactions.

Copied/hash-verified failed outputs, pointers/controls and assessment.json into
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T102318Z-3394bb2e/`.
No active state/controls/caches modified during assessment. Active checkpoint
is STILL THE DIAGNOSTIC HYBRID, not the original5; original5 remains preserved
in `.model_Bstar3502-history/lte-smaller-step-flux-stop-before-temperature-isolation/`.
Do not treat the hybrid as a converged state or blindly continue it.

Recommended next diagnostic: isolate groups of population changes4->5 while
holding T4 and maintaining charge/element consistency, starting with a broad
iron-group-versus-other-species split if source/opacity diagnostics do not
identify a more direct target. This would localize the nonlinear transfer
failure without attributing causation to the largest raw O VI percentage.
The next diagnostic has not been prepared and no further native run performed.

### Prepared: iron-group population isolation

On user request, backed up the failed temperature-isolation hybrid and outputs
under `.model_Bstar3502-history/lte-temperature-isolation-result-before-iron-group-test/`
with verified SHA256 manifest. Original unmodified checkpoint5 still preserved
at `.model_Bstar3502-history/lte-smaller-step-flux-stop-before-temperature-isolation/`.

Constructed diagnostic record5 from checkpoint4 baseline/T, replacing only the
populations of present iron-group elements Cr, Mn, Fe, Ni (Z24,25,26,28;
979 variables) with original checkpoint5 values. All explicit ion stages and
terminal continua included. Normalized each selected element to its baseline4
total density; maximum relative renormalization1.50113e-5 (Fe). Ne recomputed
from the full ionic charge sum; max relative change from checkpoint4 Ne is
4.86989e-6. Other populations and T exactly bitwise baseline4, all values finite
and positive. Maximum element abundance error1.44329e-15. Confirmed grid and
velocity vectors identical between4 and5. Verified file bytes outside the
record5 population-vector slots unchanged. Pointers remain5. Manifest records
the experiment and prepared SCRTEMP hash; marked modified with backup link.

This tests whether the iron-group update alone, at T4 and otherwise baseline4,
is sufficient to reproduce the negative radiation profile. A failure implicates
this group or its transfer coupling without identifying the responsible rate;
a pass does not exclude interactions or another group's update. If the
safeguard passes, the one-step main command also computes a Newton update;
OBSFLUX evaluates the input hybrid and is the controlled diagnostic observable.

Retired EDDFACTOR/EDDFACTOR_INFO; other BA/radiation caches absent. Controls
unchanged: MAX_LIN2/MAX_dT0.05, variable T, lambda requests off, safeguard on.
No old matrix records/conditions, marker enabled. Executable hash unchanged.
Preflight ready for continuation5, expected attempted6. No native run during
preparation. Command from repository root, automatic OFF/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md documents the hybrid/interpretation; reviewed plan saved
with the backup. Existing summary/correction outputs remain historical until
regenerated. The active hybrid is not an accepted physical solution.

### Iron-group isolation reproduces failure: 20261022T111148Z-f61f46a4

The diagnostic hybrid containing checkpoint4 T/populations except updated
Cr/Mn/Fe/Ni reproduces the inner luminosity failure before the Newton solve.
Native return0 via STOP, runner invalid_output; pointer remains5, no new
matrix diagnostics/corrections. SCRTEMP hash equals the prepared hybrid hash,
so the hybrid has not advanced. Original physical checkpoint5 remains backed up.

| Input-state radiation evaluation | Min normalized luminosity |
| --- | --- |
| Checkpoint4 baseline | +0.83207 |
| All checkpoint5 populations at T4 | -1.4212 |
| Only Cr/Mn/Fe/Ni updated, otherwise baseline4/T4 | -1.4005 |

The iron-group hybrid has negative normalized luminosity at57 depths, as did
the all-updated-population/T4 hybrid. Minimum radiative luminosity-280160 Lsun
vs-284320 for all-updated-population/T4; outer radiative luminosity3.91790655e6
vs3.92974388e6 Lsun. The failure persists with other element populations and T
held at baseline4 and only a small charge-consistent Ne adjustment.
Therefore the combined iron-group population update is sufficient to reproduce
the dominant negative-radiation symptom in this controlled construction.
This does not identify an individual element/rate or prove atomic data faulty;
the transfer coupling and the nonlinear step remain candidate mechanisms.

Copied/hash-verified failed outputs, controls/pointers and assessment.json into
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T111148Z-f61f46a4/`.
No active controls, caches or checkpoint changes during assessment. The active
model remains the iron-group diagnostic hybrid, not the original physical5.

Recommended next split: Fe alone updated from5 on baseline4/T4, abundance
normalized and Ne charge-consistent. Fe is a sensible first split because of
its abundance/line contribution and demonstrated large ion redistribution;
causation is not established until this test. If Fe alone does not reproduce
the failure, test Cr/Mn/Ni together and consider interactions. Next experiment
not yet prepared; do not continue the current hybrid as a convergence run.

### Follow-up investigation and prepared Fe-only isolation

Compared original checkpoint4->5 Fe fractions at fixed reference4 depths.
At depth24 Fe III0.44731->0.37334 and Fe IV0.55240->0.62615; at depth25
Fe III0.41695->0.30395 and Fe IV0.58290->0.69582. At depth37 Fe III0.90805
->0.86884 and Fe IV0.09182->0.13109. These are populated stages, distinct
from the tiny O VI variable setting the maximum percentage. Saved the direct
comparison as results/20261022T111148Z-f61f46a4/Fe-population-comparison.json.
These changes motivate a Fe split but do not establish causation.

Source review: existing NEG_OPAC_OPT=SRCE_CHK can raise CHI to a source-function
related bound when CHI<CHI_CONT and CHI<0.1*ETA*CHI_NOSCAT/ETA_CONT, in addition
to a scattering-opacity floor; ESEC_CHK applies only the latter floor.
cmfgen_sub.f explicitly describes these as alternative treatments of negative
line opacity. No evidence from the current output establishes whether/where
this branch triggered; avoid diagnosing it as the cause without instrumentation.
No source or opacity control changed. Hold it fixed for Fe-only isolation.

On user request, preserved current iron-group hybrid and failed outputs with
SHA256 verification in
`.model_Bstar3502-history/lte-iron-group-result-before-Fe-only-test/`.
Prepared diagnostic record5 from baseline checkpoint4/T4, replacing ONLY Fe
(Z26,419 population variables) with original physical checkpoint5 Fe values,
normalized to baseline4 element density. Includes Fe II–V and terminal
continuum. Ne recomputed from full charge sum. Non-Fe populations and T exactly
bitwise baseline4. All values finite/positive; max abundance error1.44329e-15;
max Ne change relative baseline4 is4.72873e-6. Verified changes restricted to
record5 vector bytes; pointers/grid/controls unchanged. Prepared hash recorded
in manifest, marked SCRTEMP modified with backup. Original physical5 remains
in the earlier pre-temperature-isolation backup.

Retired EDDFACTOR/EDDFACTOR_INFO; BA/other radiation caches absent. Reduced
limits retained, variable T, lambda requests off, STOP_IF_MW enabled. Executable
unchanged/hash-verified; diagnostic marker enabled, no stale matrix records.
Preflight ready, continuation5 -> attempted iteration6. No native run during
this investigation/preparation. From repository root, auto/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md records the Fe-only construction and interpretation;
reviewed next-test-plan.json with backup. If safeguard passes, main also takes
one Newton step; input-state OBSFLUX is the observable for the controlled test.
If it fails, Fe update is sufficient under these conditions, but the responsible
rate/opacity/transfer mechanism will still require investigation. Active model
is a diagnostic hybrid, not an accepted converged checkpoint.

### Fe-only update reproduces failure: 20261022T114954Z-47edc0d1

Fe-only diagnostic hybrid fails the same inner luminosity safeguard before
solving. Native return0 via STOP, runner invalid_output; pointer remains5,
no new correction/matrix outputs. SCRTEMP hash matches the prepared Fe-only
hash, so no model update occurred. Active state is still the Fe-only hybrid.

| Input-state radiation evaluation at T4 | Minimum normalized luminosity |
| --- | --- |
| Baseline checkpoint4 | +0.83207 |
| All checkpoint5 populations | -1.4212 |
| Cr/Mn/Fe/Ni populations updated | -1.4005 |
| Fe alone updated | -1.3874 |

Fe-only min radiative luminosity-277530 Lsun (56 negative normalized-depth
values), vs-280160 for all iron-group updates. Outer radiative luminosity
3.91395667e6 Lsun vs3.91790655e6 for iron group. Hydrostatic RMS/max69.1%/192%.
Other populations and temperature were held at baseline4 and Ne adjusted only
for charge consistency. Thus Fe population changes alone are sufficient to
reproduce most of the observed negative-radiation symptom under these controls.
This localizes the trigger but is not proof that Fe atomic data or a specific
rate is faulty; inconsistent nonlinear updates, excitation/ionization balance,
and opacity/transfer treatment remain possible mechanisms.

Archived/hash-verified failed outputs and assessment in
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T114954Z-47edc0d1/`.
No active checkpoint/controls/cache changed during assessment. Original physical
checkpoint5 remains in the pre-temperature-isolation backup.

Next useful split: distinguish changing Fe ion totals (ionization fractions)
from changing level fractions within each ion. First test checkpoint5 within-ion
Fe level proportions rescaled to checkpoint4 ion totals, including the terminal
continuum consistently, on baseline4/T4. If that reproduces failure, excitation
redistribution is sufficient. A complementary test keeps baseline4 within-ion
proportions and applies checkpoint5 ion totals. Preserve charge/abundance and
fresh-cache controls. These tests are proposed only; next run not prepared.

### Fe excitation/ionization split and prepared within-ion test

Direct decomposition of physical update4->5 saved at
results/20261022T114954Z-47edc0d1/Fe-ionization-excitation-comparison.json.
At depth25 Fe III density ratio5/4 is0.728980 (about27.1% decrease), and
Fe IV1.193716 (19.4% increase). Within-ion total-variation distances of normalized
superlevel populations are0.0117684 for Fe III and0.00908718 for Fe IV. Fe III
SL1 fraction0.733038->0.723314, SL3 0.100161->0.107250. Thus the density and
internal distribution both changed; the smaller within-ion mass movement can
still materially change individual line opacity and cannot be dismissed.

On user request, preserved Fe-only hybrid/result with verified hashes under
`.model_Bstar3502-history/lte-Fe-only-result-before-excitation-test/`.
Prepared excitation-only diagnostic record5 from checkpoint4 baseline/T:
for each explicit Fe ion (II,III,IV,V), take original checkpoint5 superlevel
proportions and rescale to that ion's checkpoint4 total population. Terminal
Fe continuum kept bitwise checkpoint4. All other element populations/T bitwise
checkpoint4. Ne recomputed from full charge sum, differing from baseline4 by
at most1.08730e-6 (baseline's small saved charge residual). Every value finite
and positive, each Fe ion total preserved within2.23e-15 relative and each
element total within2e-15.418 explicit Fe population slots replaced; file
changes restricted to record5 vector bytes. Grid/pointers/controls unchanged.
Manifest records construction/hash and verification; marked SCRTEMP modified.

This tests whether within-ion excitation redistribution alone reproduces the
failure at baseline ionization, temperature and other populations. If it passes,
the complementary ion-total-only test remains necessary; a pass does not prove
the excitation update is harmless in the changed-ionization state. If it fails,
the next split should isolate Fe ion stages and trace opacity/transfer response.
In both outcomes, avoid attributing a bad rate without further source evidence.

Retired radiation caches; BA/other caches absent. Reduced update limits retained,
variable T, lambda requests off, STOP_IF_MW enabled, same hash-verified isolated
executable. Marker enabled, no stale matrix records. Preflight ready for
continuation5 -> attempted6. No native iteration run during this investigation.
From repository root, automatic OFF and fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

If the safeguard passes, main also computes one Newton step; the input-state
radiation output is the controlled observable. NEXT_DIAGNOSTIC_RUN.md explains
this, and backup contains reviewed next-test-plan.json. Active model is the
excitation-only diagnostic hybrid; original physical5 remains preserved in
the pre-temperature-isolation backup. Historical summary/corrections stay old
until regenerated.

### Fe excitation-only failure: 20261022T124002Z-d85eda8e

The within-ion Fe update at fixed checkpoint4 ion totals reproduces the
inner-flux failure before solving. Native return0 via STOP, runner invalid_output;
pointer remains5, no new correction/matrix outputs. SCRTEMP hash equals the
prepared excitation-only hybrid hash, confirming no update occurred.

| Input at T4 | Minimum normalized luminosity |
| --- | --- |
| Baseline checkpoint4 | +0.83207 |
| Entire Fe population update | -1.3874 |
| Only Fe within-ion level proportions updated | -1.3304 |

Excitation-only min radiative luminosity-266130 Lsun, vs-277530 for full Fe;
56 normalized-depth values negative in both tests. Outer radiative luminosity
3.89636011e6 Lsun; photospheric hydrostatic RMS/max71.2%/200%.
Every Fe ion total and terminal continuum were held at baseline4 to near
machine precision, other elements/T bitwise baseline4. Therefore changing
within-ion Fe excitation proportions is sufficient to reproduce the dominant
symptom in this controlled state; a change in Fe ionization totals is not
required. This does not identify an atomic-data defect or prove a particular
population inversion or negative-opacity limiter was involved.

Copied/hash-verified diagnostics, controls/pointers and assessment.json into
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T124002Z-d85eda8e/`.
No active controls, checkpoint or caches modified during assessment. Active
model remains the excitation-only diagnostic hybrid; original physical5 and
all previous controls remain backed up.

Next diagnostic: restrict the within-ion redistribution to a single Fe ion,
starting with Fe III (baseline4 ion total, checkpoint5 within-ion proportions),
other Fe ions and all other populations/T at baseline4, charge-consistent Ne.
Then split Fe IV/remaining ions if needed. A complementary ion-total-only test
could quantify another contribution but is not needed to establish that
within-ion redistribution already suffices. Next run not prepared.

### Fe III mapping and prepared single-ion excitation test

Mapped all81 Fe III superlevels to the linked FeIII_F_TO_S data and ranked
normalized within-ion changes. At depth25 the largest fraction movement is
SL1 (lowest constituent3d6_5De[4], ground term),0.733038->0.723314. SL3
(lowest3d6_3He[6],20051.36 cm^-1) grows0.100161->0.107250 (+7.08% relative),
and SL8 (lowest3d6_3De[2],30715.98 cm^-1) grows0.0125830->0.0138023 (+9.69%).
These identify appreciably populated low/metastable terms for later opacity
analysis, but do not prove they cause the failure; high excited levels or
other ions may still dominate particular transitions. Saved full depth24/25/37
ranking to results/20261022T124002Z-d85eda8e/FeIII-level-redistribution.json.

On user request, preserved the all-Fe excitation-only hybrid and failed outputs
with verified hashes in
`.model_Bstar3502-history/lte-Fe-excitation-result-before-FeIII-test/`.
Prepared record5 as baseline checkpoint4 with ONLY81 Fe III superlevel ratios
from original checkpoint5, rescaled to checkpoint4 Fe III total. Every other
population including other Fe ions/terminal continuum and T bitwise baseline4.
Ne recomputed from charge sum (max relative adjustment from baseline4
1.08730e-6). All entries finite/positive; Fe III total preserved to2.23e-15,
element totals to1.78e-15. Verified file modifications restricted to record5
vector slots; grid/pointers/controls unchanged. Manifest records prepared hash
and construction, marked SCRTEMP modified with backup link.

Retired EDDFACTOR/EDDFACTOR_INFO, other BA/radiation caches already absent.
MAX_LIN2/MAX_dT0.05 retained, variable T, lambda requests off, safeguard on.
Same hash-verified isolated executable, marker enabled, no old matrix output.
Preflight ready for continuation5, attempted6. No native iteration run during
investigation/preparation. Run from repository root, auto/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

A pre-solve failure localizes sufficient excitation changes to Fe III in this
controlled state. A pass requires testing remaining Fe ions/interactions;
it does not prove Fe III irrelevant. If main passes the safeguard it also
computes a Newton step; input-state OBSFLUX remains the controlled observable.
Instructions in NEXT_DIAGNOSTIC_RUN.md; reviewed next-test-plan.json with backup.
The active model is a diagnostic hybrid, not a converged solution.

### Fe III-only excitation test PASSES: 20261022T132748Z-486983ed

Native return0 and runner succeeded. The input Fe III-only diagnostic hybrid
passes the inner luminosity check: minimum normalized luminosity0.83235 at
depth37, no negative values. This is almost unchanged from baseline checkpoint4
(min0.83207), unlike all-Fe excitation-only(min-1.3304). Outer radiative
luminosity3.44852761e6 Lsun, also nearly baseline4's3.44852872e6. Thus Fe III
excitation redistribution alone does not reproduce the failure in this
controlled baseline; it does not exclude Fe III interactions in another state.

After that input-state radiation evaluation the native program did take one
Newton step, writing diagnostic checkpoint6. Saved values finite/positive,
max relative charge mismatch5.25223e-7, population ratios0.5–2, all90 T updated
with max5%. This is a diagnostic branch from the hybrid, NOT proof that the
original physical smaller-step branch recovered or reached iteration6. Do
not interpret its native counter as a successful continuation of original5.
The radiation output precedes that new update, as required for the test.

Saved matrix data, conditions, corrections, OUTGEN, OBSFLUX, pointer records,
analysis.json and contextualized assessment.json with hashes under
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T132748Z-486983ed/`.
No active inputs/checkpoint/caches modified during assessment. Active record6
is the result of the FeIII-only diagnostic branch; original physical5 and
all preceding diagnostic inputs remain preserved.

Next useful test: Fe IV-only within-ion proportions from original5 rescaled
to baseline4 Fe IV total, with all other ions/populations/T at baseline4,
charge-consistent Ne and fresh caches. Fe III alone does not account for the
all-Fe excitation failure; remaining candidates include Fe IV, II, V, or
interactions. Do not attribute it solely to Fe IV until tested. Next diagnostic
not yet prepared; do not blindly continue the generated diagnostic record6.

### Fe IV level mapping and prepared single-ion test

Mapped Fe IV superlevels through FeIV_F_TO_S. At depth25, normalized SL2
(lowest constituent3d5_4Ge[11/2]) decreases0.193687->0.185228, SL1
(3d5_6Se[5/2]) increases0.602430->0.607350 and SL6 (3d5_4Fe[9/2]) increases
0.0434443->0.0463243. Total-variation distance0.00908718. Saved depth24/25/37
ranking to results/20261022T132748Z-486983ed/FeIV-level-redistribution.json.
This identifies terms to inspect if Fe IV alone reproduces the failure;
no opacity/rate mechanism established yet.

On user request, preserved successful Fe III diagnostic checkpoint6, controls,
outputs and full-precision matrix records with verified hashes in
`.model_Bstar3502-history/lte-FeIII-result-checkpoint-6-before-FeIV-test/`.
Constructed new diagnostic record5 from baseline checkpoint4/T4, changing ONLY
110 Fe IV level proportions to original checkpoint5 proportions, rescaled to
checkpoint4 Fe IV total. Every other ion/population and T bitwise baseline4.
Ne charge-consistent, max adjustment from baseline4 1.08730e-6. All values
finite/positive; Fe IV total error1.34e-15, element abundance error1.78e-15.
SCRTEMP changes restricted to record5 vector slots; earlier/later records
preserved. Restored saved physical5 pointers (hash-checked) for controlled
iteration6 evaluation; the prior diagnostic6 remains in the backup.

Retired BAMATPNT/EDDFACTOR/EDDFACTOR_INFO, other caches absent. Archived previous
matrix records/condition log, marker enabled. MAX_LIN2/MAX_dT0.05 and all
physical/solver controls unchanged; variable T, lambda requests off, safeguard
on. Same hash-verified executable. Preflight ready for continuation5 -> attempted6.
No native run during this investigation/preparation. From repository root,
automatic OFF/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md describes the Fe IV hybrid and input-state OBSFLUX
interpretation; backup has reviewed next-test-plan.json. If safeguard passes,
main also takes a Newton step. A fail localizes sufficient excitation changes
to Fe IV under this baseline; a pass leaves Fe II/V or interactions to test.
Active state is a diagnostic hybrid and summaries remain historical until
regenerated. Installed source/executable/global config unchanged.

### Fe IV-only excitation test PASSES: 20261022T140551Z-507e180a

Native return0, runner succeeded. The input Fe IV-only excitation hybrid
passes the inner safeguard: normalized minimum0.83242 at depth37, no negatives,
almost identical to baseline4 min0.83207 and Fe III-only min0.83235. Outer
radiative luminosity3.44846491e6 Lsun, also close to baseline4. Therefore
Fe IV excitation redistribution alone does not reproduce the failure under
these baseline conditions. Both major Fe ions tested individually pass;
remaining candidates include Fe II, Fe V, or interactions across stages.
Neither single-ion pass proves its irrelevance to a combined changed state.

The solver then wrote diagnostic checkpoint6: all values finite/positive,
max relative charge mismatch5.25283e-7; population ratios0.5–2 and maxT5%.
This is the result of the Fe IV diagnostic branch, not a recovered physical
continuation from original smaller-step5. Its input radiation is the controlled
observable; newly written6 radiation has not yet been evaluated.

Archived/hash-verified matrix data, condition log, corrections, OUTGEN, OBSFLUX,
pointers, analysis.json and contextualized assessment.json under
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T140551Z-507e180a/`.
No active checkpoint/controls/cache modified during assessment. Active6 belongs
to this diagnostic branch; original physical5 and all prior hybrids preserved.

Next useful test: Fe V-only within-ion excitation proportions from original5,
rescaled to baseline4 Fe V total, all other populations/T baseline4 and Ne
charge-consistent. Fe V previously featured extreme excited-level seeds in
the matrix investigation, making this a reasonable next split, without claiming
it is responsible. If Fe V passes, test Fe II and combined-stage interactions.
Preparation not yet performed; do not blindly continue diagnostic6.

### Fe V level comparison and prepared single-ion test

Mapped139 Fe V superlevels with FeV_F_TO_S. At depth25, within-ion total
variation4->5 is0.0127766: SL1 (lowest3d4_5De[0]) fraction0.898289->0.885515,
SL3(3d4_3He[4])0.0425247->0.0476992, SL2(3d4_3P2e[0])0.0308254->0.0344017,
SL4(3d4_3Ge[3])0.0175863->0.0200084. Saved depth1/24/25/37 ranking at
results/20261022T140551Z-507e180a/FeV-level-redistribution.json. Neither these
fraction changes nor the earlier tiny Fe V seeds establish causation; the
single-ion radiation test is needed.

On user request, preserved successful Fe IV diagnostic checkpoint6 and outputs,
including matrix records and conditions, with verified hashes under
`.model_Bstar3502-history/lte-FeIV-result-checkpoint-6-before-FeV-test/`.
Prepared record5 on checkpoint4 baseline/T, changing ONLY139 Fe V level ratios
to original5 proportions, rescaled to checkpoint4 Fe V total. Other populations,
including other Fe ions/terminal continuum, and T bitwise baseline4. Charge-
consistent Ne differs from baseline4 at most1.08730e-6. All entries finite and
positive; Fe V total error1.56e-15, element abundance error1.78e-15. File changes
restricted to record5 vector; restored saved5 pointers, earlier/later records
retained and original source5 preserved. Manifest records the construction and
prepared hash; marked SCRTEMP modified with backup link.

Retired BAMATPNT/EDDFACTOR/EDDFACTOR_INFO; other caches absent. Archived prior
matrix/condition records, marker enabled. Controls unchanged: MAX_LIN2,
MAX_dT0.05, variable T, fresh BA, lambda requests off, safeguard on. Same
hash-verified executable. Preflight ready for continuation5 -> attempted6.
No native run during this investigation/preparation. From repository root,
automatic OFF/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md documents this input hybrid and interpretation; reviewed
plan saved with the backup. If safeguard passes, main also takes a Newton step;
its input-state radiation is the controlled observable. If Fe V passes, Fe II
and inter-ion interactions remain to test. Active state remains diagnostic,
not an accepted physical/converged continuation.

### Fe V-only excitation test PASSES: 20261022T151159Z-5fd41dd3

Native return0, runner succeeded, input hybrid passes the inner safeguard.
Minimum normalized luminosity0.83207 at depth37, no negatives, effectively
identical to baseline4. Outer radiative luminosity3.44852869e6 Lsun vs
baseline4 3.44852872e6. Thus Fe V within-ion redistribution alone has negligible
effect on this input-state radiation profile at baseline ion totals/T.

Single-ion results: Fe III min0.83235, Fe IV0.83242, Fe V0.83207, all pass;
all-Fe excitation-only min-1.3304 fails. Fe II is the remaining untested
individual stage; coupled effects also remain possible. Do not conclude Fe II
is responsible solely by eliminating these individual tests.

The run subsequently computed a Newton step and wrote diagnostic record6.
All saved values finite/positive, max relative charge mismatch5.25213e-7,
population ratios0.5–2 and maxT5%. This remains the Fe V diagnostic branch,
not recovery of original physical5. New record6 radiation untested.

Archived matrices, condition log, corrections, OUTGEN, OBSFLUX and pointers,
analysis.json and contextualized assessment.json with hashes under
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T151159Z-5fd41dd3/`.
No active checkpoint/controls/cache modified during assessment. Next useful
diagnostic: Fe II-only within-ion proportions from original5, rescaled to
baseline4 Fe II total, all other populations/T baseline4, charge-consistent
Ne and fresh caches. If it passes too, test coupled stages or audit hybrid
construction/transfer response; no single-ion culprit would be established.
Next run not prepared. Active6 belongs to this diagnostic branch.

### Fe II level comparison and prepared final single-ion split

Mapped88 Fe II superlevels through Fe2_F_TO_S. At depth25 the normalized
within-ion total variation4->5 is0.00403904: SL1 (lowest3d6(5D)4s_a6De[9/2])
fraction0.413707->0.411498; SL2 (3d7_a4Fe[9/2])0.292729->0.291052; SL8
(3d6(3P2)4s_b4Pe[5/2])0.0406032->0.0414163; SL11
(3d6(3G)4s_a4Ge[11/2])0.0145566->0.0152864. Saved depth1/24/25/37 ranking in
results/20261022T151159Z-5fd41dd3/FeII-level-redistribution.json. Small total
fraction motion does not guarantee small opacity changes in individual lines;
this comparison does not establish a population inversion or causal rate.

On user request, preserved successful Fe V diagnostic6 and its outputs with
verified hashes under
`.model_Bstar3502-history/lte-FeV-result-checkpoint-6-before-FeII-test/`.
Prepared record5 from checkpoint4 baseline/T, changing only88 Fe II level
proportions to original5 ratios, rescaled to baseline4 Fe II total. Other
populations including other Fe ions/terminal continuum and T bitwise baseline4.
Ne charge-consistent (max relative adjustment1.08730e-6). All values finite and
positive; Fe II total error1.89e-15, element abundance error2.23e-16. File
changes restricted to record5 vector, restored saved5 pointers; grid/controls
unchanged. Manifest records prepared hash/construction; marked modified with
backup link. Original physical5 and earlier diagnostic6 branches preserved.

Retired BAMATPNT/EDDFACTOR/EDDFACTOR_INFO; other caches absent. Archived previous
matrix records/condition log; marker enabled. MAX_LIN2/MAX_dT0.05, variable T,
lambda off and safeguard on retained. Executable unchanged/hash verified.
Preflight ready for continuation5 -> attempted6. No native run during this
investigation/preparation. From repository root, automatic/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

NEXT_DIAGNOSTIC_RUN.md explains the test and interpretation, reviewed plan
saved with backup. Input-state OBSFLUX is the observable; main also performs
a Newton step if the safeguard passes. If Fe II alone passes, all explicit
single-stage excitation tests pass, requiring combined-stage tests or audit
of the construction/native transfer rather than declaring one stage guilty.
Active model is diagnostic, not a recovered physical continuation.

### Fe II-only excitation FAILS: 20261022T164434Z-20d3a35c

Native return0 via STOP, runner invalid_output at the same inner luminosity
safeguard before solving. Pointer remains5, no new corrections/matrix output;
SCRTEMP hash matches the prepared Fe II hybrid, so the test state is unchanged.

| Excitation update alone on baseline4/T4 | Minimum normalized luminosity |
| --- | --- |
| No changes (baseline4) | +0.83207 |
| Fe III | +0.83235 |
| Fe IV | +0.83242 |
| Fe V | +0.83207 |
| Fe II | -1.3327 |
| All Fe explicit ions | -1.3304 |

Fe II alone produces56 negative normalized-depth values and minimum radiative
luminosity-266600 Lsun; all-Fe excitation test was-266130. Outer radiative
luminosity3.89691956e6 Lsun versus all-Fe excitation3.89636011e6. Thus within-ion
Fe II redistribution alone reproduces essentially the all-Fe excitation
failure with Fe II ion total, other populations and T held at baseline4.
Fe III/IV/V are not required for this sufficient trigger. The same Ne charge
adjustment protocol was used for the passing individual-ion tests.

At depth25 baseline Fe II represents only6.0144e-6 of Fe, and its normalized
level total variation is0.00403904. The disproportionately large radiation
response motivates inspecting specific Fe II transitions, inversion/opacity
thresholds and the transfer/negative-opacity treatment. It does not prove a
rate or atomic dataset is faulty, nor establish that a small trace-ion
population can be discarded safely.

Archived/hash-verified failed diagnostics, controls/pointers and assessment
under `.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T164434Z-20d3a35c/`.
No active checkpoint/controls/cache modified during assessment. Active model
remains the Fe II-only diagnostic hybrid; original physical5 and all prior
successful diagnostics preserved. Next investigation should localize Fe II
level/transition changes and inspect how their opacity enters transfer,
including the existing SRCE_CHK limiter. Avoid further indiscriminate damping
or a combined-stage hypothesis now that a single stage is sufficient. Next
run not yet prepared; this result localizes a trigger, not a convergence fix.

### Opacity-treatment review and prepared ESEC_CHK comparison

Reviewed the native negative-line-opacity block in cmfgen_sub.f around2220.
SRCE_CHK, currently selected by the failed model, has two tests: when CHI is
below continuum and below0.1*ETA*CHI_NOSCAT/ETA_CONT it replaces CHI with that
source-function-derived bound; otherwise it applies a0.1*CHI_SCAT floor.
ESEC_CHK only applies the scattering floor. Both mark NEG_OPACITY and set
NEG_OPAC_FAC=0 when triggered. The code comments describe SRCE_CHK as added
for far-IR transition problems and ESEC_CHK as the older alternative. This is
source evidence for different prescriptions, not evidence that either branch
triggered at the Fe II frequencies responsible for the observed negative flux.
Current archived outputs do not provide depth/frequency-resolved CHI/ETA/limiter
flags, so identifying a specific culprit transition is not yet justified.

Rather than assuming a particular level is guilty, prepared a controlled
single-option comparison on user request. Preserved failed Fe II-only state,
SRCE_CHK controls and diagnostics with verified hashes under
`.model_Bstar3502-history/lte-FeII-excitation-result-before-ESEC-test/`.
POINT1/POINT2/SCRTEMP remain BYTEWISE identical to the failed Fe II hybrid.
VADAT diff is exactly NEG_OPAC_OPT SRCE_CHK->ESEC_CHK; IN_ITS unchanged.
No source/executable changes. Retired EDDFACTOR/EDDFACTOR_INFO; other BA and
radiation caches absent. STOP_IF_MW remains enabled; MAX_LIN2/MAX_dT0.05,
variable T and lambda requests off retained. Marker enabled, no old matrices.

Preflight ready for continuation5 -> attempted6. No native run during this
investigation/preparation. From repository root, automatic/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/lte-outer-matrix-v1
```

A pass would implicate sensitivity to the clipping prescription and motivate
instrumenting CHI/ETA/NEG_OPAC flags for physical verification; it would not
prove ESEC_CHK is a general convergence fix. A fail means this single option
is insufficient and Fe II level/transition isolation is still needed. If guard
passes, main also computes one Newton step; compare input-state OBSFLUX for
this diagnostic. NEXT_DIAGNOSTIC_RUN.md records interpretation, reviewed plan
and manifest saved with backup. Active model remains a diagnostic hybrid with
ESEC_CHK, not a converged physical model.

### ESEC_CHK comparison does NOT help: 20261022T171838Z-4f0fb818

Native MODEL confirms NEG_OPAC_OPT=ESEC_CHK was read. Nevertheless the input
Fe II-only hybrid produces the same inner-flux safeguard STOP, native return0,
runner invalid_output. Pointer remains5; prepared hybrid SCRTEMP hash unchanged,
no new matrix/correction outputs. The printed Luminosity, Total Radiative
Luminosity and Normalized luminosity check vectors are exactly equal to the
SRCE_CHK comparison (max absolute printed difference0). Both have normalized
minimum-1.3327, min radiative luminosity-266600 Lsun and56 negative normalized
values. Outer luminosity unchanged at printed3.89691956e6 Lsun.

This rules out changing SRCE_CHK to ESEC_CHK as a remedy for this diagnostic
failure. It does not prove no opacity floor triggered: the two prescriptions
share the scattering floor, may act identically here, or differ below print
precision. There is no evidence yet to attribute the failure to the additional
SRCE_CHK source-function threshold. Do not carry ESEC_CHK forward as a fix.

Archived/hash-verified failed diagnostics, controls/pointers and assessment at
`.model_Bstar3502-diagnostics/lte-outer-matrix-v1/results/20261022T171838Z-4f0fb818/`.
No active checkpoint/controls/caches changed during assessment. Active state
is the unchanged Fe II-only hybrid with ESEC_CHK; original SRCE_CHK controls
and hybrid backed up before this experiment.

Next investigation should return to Fe II level/transition localization and
native frequency/depth-resolved opacity/emissivity/flux diagnostics. Another
single uninstrumented retry with either opacity prescription adds little.
If preparing another level split, restore SRCE_CHK to keep the main control
baseline. No further run prepared in this assessment.

### Prepared: isolated frequency/depth transfer instrumentation

Further uninstrumented opacity-option retries are not informative after the
printed-identical SRCE_CHK/ESEC_CHK profiles. On user request, built a separate
observational runtime `.model_Bstar3502-diagnostics/fe-transfer-v1/`. It relinks
the previous LTE/outer-diagnostic objects with a copied cmfgen_sub.f and a new
fe_transfer_diagnostics module; installed source/executable/global config are
unchanged. Original main source, instrumented source, minimal main-diagnostics.patch,
helper/test sources, commands and input/output SHA256 hashes are preserved there.

Main additions are a module import and four calls: capture opacity/emissivity
before clipping, capture opacity/flag after clipping, record after native SOB
flux evaluation, and finalize after frequency integration before the luminosity
safeguard. No native equation, clipping input or integration statement modified.
The helper's arrays are private saved copies; all physics arguments intent(in).
It activates only when FE_TRANSFER_DIAGNOSTICS marker exists.

Outputs at selected depths1/24/25/37/ND:

- FE_TRANSFER_FREQUENCIES.bin: native stream magicFEFLX001; int32 nselected5,
  nfields12, ND90, then5 int32 selected depths (40-byte header). Each frequency
  record500bytes: int32 ML, real64 frequency and FQW, then12x5 real64 Fortran
  array. For each depth fields: dL[Lsun], SOB, CHI_before_clip, CHI_after_clip,
  ETA_before_clip, CHI_cont, ETA_cont, CHI_scat, RJ, R, T[1e4K], clipped[0/1].
  About76MB for152174 frequencies. Values refer to the native blanketing loop;
  integration is of per-frequency contributions, not a changed observed spectrum.
- FE_TRANSFER_SUMMARY.txt: compares sum of captured dL to native RLUMST BEFORE
  the safeguard and records20 most-negative contributions per selected depth,
  with active resonance-zone candidate names (4096char limit, explicit truncation
  marker). Names identify candidates, not which line caused a contribution.

Compiled successfully against current native modules. Standalone synthetic
25-frequency tests verify binary headers/records, signed contributions, pre/post
clip values/flag, correct top20 retention, exact agreement with synthetic native
luminosity sums, and no outputs with marker absent. These tests do not prove the
native instrumented model reproduces prior radiation output; recompiling main
can alter floating-point behavior, so compare that on the next user run. No
native iteration was run during preparation.

Preserved failed ESEC controls/checkpoint/outputs with verified hashes in
`.model_Bstar3502-history/lte-FeII-ESEC-result-before-transfer-diagnostics/`.
Prepared the SAME Fe II excitation-only hybrid: POINT1/POINT2/SCRTEMP bytewise
unchanged. Restored NEG_OPAC_OPT=SRCE_CHK to original baseline; no other control
change. Retired EDDFACTOR/EDDFACTOR_INFO; BA/other radiation caches absent.
Enabled new marker, retained outer marker, no old matrices present. MAX_LIN2/
MAX_dT0.05, variable T, lambda off and STOP_IF_MW enabled retained.

Preflight ready using the NEW explicit runtime, continuation5 -> attempted6:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/fe-transfer-v1
```

Automatic OFF/fresh start OFF. Another pre-solve luminosity STOP is expected;
it should still produce the intended diagnostic files before stopping. If it
passes, main also computes a Newton step, and input-state radiation remains
the comparison. NEXT_DIAGNOSTIC_RUN.md explains outputs and reviewed plan is
saved with backup. Active state remains the Fe II diagnostic hybrid, not a
recovered physical continuation. The records should now allow ranking actual
negative interior frequency contributions, testing raw opacity/limiter behavior,
and identifying transitions for a targeted follow-up instead of further blind
level splits.

### Instrumented transfer result: 20261022T181445Z-73cc5620

The expected pre-solve inner luminosity STOP occurred (native return0, runner
invalid_output); pointer stays5 and SCRTEMP hash equals the prepared Fe II-only
hybrid hash. No new Newton corrections. Instrumented printed normalized
luminosity profile is EXACTLY the archived uninstrumented SRCE_CHK profile,
minimum-1.3327. This real-model comparison supports observational equivalence
for this radiation diagnostic despite recompiling the main routine.

Recorder produced152174 frequency records (76MB) and summary. Its serial sum
of per-frequency contributions agrees EXACTLY with native pre-guard RLUMST
at all5 depths1/24/25/37/90 (difference0). Thus the recorded negative interior
luminosity accounts for the actual native integration, rather than a summary
parser or mechanical-energy bookkeeping artifact.

At depth24, positive contributions sum+35233.42 Lsun, negative-301821.12,
net-266587.70.103791 frequency points have inward/negative flux. The negative
contributions are broadband, not a single isolated line:

| Wavelength range, Angstrom | Negative contributions, Lsun |
| --- | --- |
| below912 | -1035 |
| 912–1200 | -466 |
| 1200–1500 | -2762 |
| 1500–2000 | -103943 |
| 2000–3000 | -75439 |
| 3000–10000 | -62098 |
| above10000 | -56078 |

The most negative single contribution at depth24 is near1407.625 Angstrom
(ML44508),-121.09 Lsun. There CHI=1.36912e-6 before AND after clipping,
ETA8.16999e-13, scattering/total opacity0.98575, RJ2.87142e-4. Many active
resonance-zone transitions overlap; names are candidates, not attribution.
The broad-band integrated deficit cannot be explained solely by this largest
single sample or its frequency neighborhood.

No clipping flags at sampled depths1/24/25/90 at ANY frequency. At depth37
one frequency clipped. At depths24/25, all negative-contribution samples
have positive raw total opacity, positive emissivity and positive RJ. This
rules out local negative total opacity or local limiter activation at those
sampled failing depths as a direct explanation, but does NOT exclude opacity
behavior/clipping at unsampled depths, individual negative line opacities under
positive continuum, or upstream frequency coupling. The prior SRCE/ESEC
comparison also showed no radiation difference. Do not label clipping the cause.

Additional flux-to-J check found a few moment-ratio anomalies if SOB/R^2 and
RJ are interpreted at common depth/frame:69 negative rows with abs(H)/J>1.01
at24,42 at25,2 at37. Their signed luminosity sums are only-124.76,-55.90,
-1.91e-6 Lsun, respectively, far below the301821 Lsun negative total at24.
These may warrant transfer/interpolation review but cannot by themselves account
for the broad deficit. Saved details in moment-consistency-check.json; avoid
interpreting this as a demonstrated causal numerical bug.

Archived/hash-verified binary/summary, OUTGEN, OBSFLUX, controls and pointers,
analysis.json and moment check at
`.model_Bstar3502-diagnostics/fe-transfer-v1/results/20261022T181445Z-73cc5620/`.
Reproducible run analyzer saved at runtime/analyze_failed_transfer_run.py.
A temporary analysis-script namespace collision initially targeted the historical
attempt4 artifact directory; corrected the analyzer to use a local vector reader,
archived here, and restored that historical directory from its preserved original
model backup (old assessment retained). No active scientific model data was
modified by this artifact correction or by assessment.

Next necessary comparison: instrumented baseline checkpoint4 radiation with
otherwise matching controls/caches and charge-consistent Ne. A good-state
frequency/depth reference will allow subtracting failed-minus-baseline spectra,
locating where flux/J/opacity first diverge and whether Fe II line emission
or transfer coupling seeds the broadband change. Current records alone localize
where negative flux emerges but do not uniquely identify the responsible
transition or a remedy. Next run not prepared; active state remains the failed
Fe II-only hybrid at5 with original SRCE_CHK and diagnostics enabled.

### Prepared: instrumented baseline4 for differential transfer analysis

On user request, preserved failed Fe II instrumented hybrid, controls, frequency
records/summary and other outputs with verified hashes under
`.model_Bstar3502-history/lte-FeII-transfer-result-before-baseline-test/`.
Prepared checkpoint4 populations/T as a controlled baseline in diagnostic
record5, retaining pointers/counter5 to match the failed experiment's native
iteration conditions. This is a diagnostic reference, not a new physical
checkpoint5. All population slots and T are bitwise baseline4; Ne recomputed
from the ionic charge sum agrees with failed Fe II input Ne to4.44e-16
relative. Thus Fe II within-ion proportions are the material population
change between these two tests. Grid/controls/executable unchanged. All
values finite/positive; verified file modifications restricted to record5
vector slots. Manifest records construction and prepared hash; marked modified
with backup link. Original physical5 and all diagnostic branches preserved.

Retired EDDFACTOR/EDDFACTOR_INFO; other BA/radiation caches already absent.
Archived previous transfer binary/summary and cleared old matrix records;
both markers remain enabled. SRCE_CHK, MAX_LIN2/MAX_dT0.05, variable T,
lambda requests off and STOP_IF_MW retained. Executable hash matches build.
Preflight ready for continuation5 -> attempted6. No native run during preparation.
From repository root, automatic/fresh start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/fe-transfer-v1
```

Expected good baseline should pass inner safeguard; main will then also compute
one Newton step. Use input-state FE_TRANSFER records/OBSFLUX as reference,
not the subsequently saved state. Confirm sum check and frequency grids before
subtracting recorded spectra; if grids differ, integrate bins consistently
rather than subtracting weighted samples at unmatched frequencies. Compare
failed-minus-baseline flux, J, emissivity and opacity to locate the initial
spectral/transfer divergence; broad integrated inward flux alone does not
identify a particular Fe II transition. NEXT_DIAGNOSTIC_RUN.md documents the
run and reviewed next-test-plan.json is in the backup. Old model summaries
remain historical until regenerated.

### Instrumented baseline succeeds and localizes differential divergence

Run20261022T222200Z-4f24e04f: native return0, runner succeeded. Input baseline
radiation minimum normalized luminosity0.83207, no negatives, matching archived
checkpoint4. Serial captured dL sums exactly equal native RLUMST at all5 sampled
depths. After radiation, main wrote diagnostic6; its stored values finite and
positive. This remains a controlled baseline branch, not recovery of original5.

Baseline and failed Fe II runs have EXACTLY identical152174-point frequency
arrays and quadrature weights; direct per-frequency comparison is valid.
At depth24, baseline+166885.40 Lsun vs failed-266587.70, difference-433473.10.
Failed-minus-baseline band-integrated changes in Lsun:

| Wavelength range A | Difference |
| --- | --- |
| below912 | -0.00047 |
| 912–1200 | +75.44 |
| 1200–1500 | -4.85 |
| 1500–2000 | -91539.50 |
| 2000–3000 | -119787.44 |
| 3000–10000 | -157845.87 |
| above10000 | -64370.88 |

The largest negative per-frequency flux seen in the failed run near1408A was
not the largest failed-minus-baseline effect: both states share much of that
local structure. The large persistent differential deficit develops around
1630–1632A and propagates across longer wavelengths (native loop runs decreasing
frequency). Smaller J differences occur earlier (first >10% criterion near927A),
so do not call1632A the first possible seed or infer causation just from this
threshold. Recorded cumulative failed-minus-good difference crosses-1/-10Lsun
at1631.738A, -100 at1631.929A, -1000 at1633.840A, -10000 at1656.054A.

At1632.789A, depth24 contribution+3.54803 ->-44.62242 Lsun, J1.00241e-5
->1.37128e-4 (13.68x), while local raw opacity changes by only-5.38e-6
relative and local emissivity by-1.31e-6; clipping flag0 in both. At1656.054A,
J rises about6.26x with local chi/eta relative changes only-3.35e-9/-1.29e-9.
This shows that the large response is in the coupled radiation field rather
than a comparably large LOCAL opacity/emissivity jump at the sampled depth.
It does not rule out changes at other depths or upstream frequencies, or prove
a numerical solver defect. Full-depth transfer coefficients around the onset
are the next useful observable.

Matched atomic Fe II transitions near1625–1635A (modeled full indices<=827)
to superlevel assignments. Candidate strong lines include1629.159A f0.0345
(full3->139, SL1->36, 3d5(6S)4s_4p(3P)y6Po[5/2] upper),1631.129A f0.0184
(full3->138, same upper superlevel36), and1633.909A f0.021 (full8->159,
SL2->35). These are candidates in the onset window, not identified causes;
other overlapping species/lines and velocity-shifted resonance zones matter.
A targeted follow-up should record full-depth coefficients and individual
Fe II line contributions in this window before accepting a particular
superlevel or source-rate diagnosis.

Archived baseline transfer binary/summary, OUTGEN, OBSFLUX, controls, pointers,
corrections and outer matrix data with verified hashes at
`.model_Bstar3502-diagnostics/fe-transfer-v1/results/20261022T222200Z-4f24e04f/`.
Differential analysis saved in transfer-comparison.json, divergence-onset.json,
FeII-near-onset-candidates.json; reproducible comparison script at runtime/
compare_baseline_transfer.py. No active inputs/checkpoint/caches modified during
assessment. Active6 is the baseline diagnostic branch; prior failed Fe II state
and physical checkpoints remain preserved. No further run prepared here.

### Prepared: full-depth/individual Fe II coefficients around1630A onset

On user request, extended observational recorder in a new isolated runtime
`.model_Bstar3502-diagnostics/fe-transfer-v2/`. Prior v1 outputs showed a large
radiation response around1630–1632A despite only ppm-level LOCAL changes at
sampled depths, so further blind damping/level splits are less informative
than full-depth line/transfer data. This does not yet prove a transfer bug:
unsampled-depth or upstream-frequency changes remain possible.

V2 preserves the five-depth/all-frequency recorder and adds:

- FE_TRANSFER_WINDOW.bin,1625–1640A inclusive, all90 depths. Header magic
  FEWIN001 +int32 ND,nfields12 (16bytes); records8660bytes: int32ML,
  real64frequency/FQW, then12x90 real64 Fortran array, same fields/order as v1.
  Pre-clip fields captured before limiter; post-clip opacity/flag afterward;
  SOB/J recorded after native flux calculation.
- FEII_LINE_WINDOW.bin, same window, active Fe2 resonance-zone lines only.
  Header FELIN001 +int32 ND90,nfields5,name_length50 (20bytes). Each record
  3698bytes: four int32 ML,slot,SIM_NL,SIM_NUP; four real64 current frequency,
  rest frequency,oscillator strength,EinsteinA;50-byte name;5x90 real64 array
  of CHIL_MAT,ETAL_MAT,LINE_PROF_SIM,CHIL*profile,ETAL*profile. Indices are
  native SIM_NL/NUP values, not automatically assumed full-atom indices.
  Coefficients captured before clipping; names may truncate at native50chars.
  Individual local contributions are not themselves attribution of total J/H.

Copied main routine gains one extra observational call after pre-clip capture;
module has private saved copies and intent(in) arguments. No physics statements,
controls or installed source/executable/global config changed. Build manifest,
original/instrumented main, patch and helper/test sources preserved. Compiled
successfully against native modules and prior isolated LTE/outer objects.
Standalone tests verify all-depth roundtrips, window inclusion/exclusion,
active FeII filtering (other ions/inactive lines excluded), signed raw/profile
products, indices/metadata and exact summed luminosity; disabled-marker test
produces no files. No native model run during preparation. Real-model comparison
against failed v1 remains required to verify observational equivalence.

Preserved successful instrumented baseline diagnostic6 and outputs (including
frequency records/matrices) with verified hashes at
`.model_Bstar3502-history/lte-instrumented-baseline-result-before-full-depth-window/`.
Restored EXACT failed Fe II-only SCRTEMP/POINT1/POINT2 from the verified backup
before the baseline experiment; hashes identical. Pointers select5. Controls
unchanged SRCE_CHK, MAX_LIN2/MAX_dT0.05, variable T, lambda off, safeguard on.
Retired BAMATPNT/EDDFACTOR/EDDFACTOR_INFO; other caches absent. Both markers
retained, previous diagnostic files archived. Preflight ready for attempted6:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/fe-transfer-v2
```

From repository root, automatic OFF/fresh start OFF. Another pre-solve STOP is
expected; intended diagnostic streams should be finalized before the safeguard.
If it passes, main also takes a Newton step. NEXT_DIAGNOSTIC_RUN.md documents
outputs and reviewed plan is saved with backup. Active state is again failed
Fe II-only diagnostic5, not the subsequently generated baseline6.

### Full-depth Fe II window result: 20261022T225936Z-affbf828

Expected inner-flux safeguard STOP before solve, native return0, runner
invalid_output; pointer5 and prepared failed-hybrid hash unchanged. V2
reproduces v1 per-frequency dL to max absolute7.56e-10 Lsun, with exact serial
capture/native luminosity sum checks at all5 broad-record depths. The expanded
recorder therefore retains the demonstrated failure accurately.

Window contains164 frequencies across1625–1640A and1003 active Fe II line
records,82 distinct native(lower,upper,rest_frequency) combinations. Across
ALL90 depths in this window: no nonpositive total raw opacity, no negative
emissivity, no clipping flags, and no negative raw or profile-weighted individual
Fe II line opacity/emissivity. Thus a local maser/negative-opacity clip in this
recorded window is unsupported; behavior outside the window remains untested.

Full-depth data reveals strong Fe II line contributions at depths not covered
by v1. Ground-superlevel1 ->superlevel36 transitions (native equations1646/1681)
dominate several line cores at deeper layers:

-1636.331A rest (recorded1636.316A), y6Po[3/2] upper to a6De[3/2] lower:
  individual line99.0% of local total raw opacity at depth62 and99.93% of
  local total emissivity at depth48.
-1639.401A rest (recorded1639.382A), same upper to a6De[1/2] lower:
 98.5% opacity at62 and99.96% emissivity at48.
-Total Fe II local opacity/emissivity fractions reach99.27%/99.97% in the window.

These percentages are local at selected line cores/depths, not fractions of
bolometric luminosity or proof those frequencies seed the first divergence.
The same upper superlevel36 includes the previously identified1629.159 and
1631.129A transitions near the onset. This makes SL36 a grounded candidate
for a controlled population test, while overlaps and transfer coupling remain.

Compared original normalized Fe II update4->5: SL36 fraction at depth48 grows
0.000278273->0.000408205; at55 0.000169959->0.000274858; at62 0.000135706
->0.000226090. The SL36/SL1 population ratio rises by factors1.5468,1.7496,
1.7903 respectively. At24/25 it changes only1.00774/1.02630. This explains
why ppm-scale changes in local total coefficients at24 do not constrain the
much larger deeper source-population changes. It suggests a plausible deeper
line-source/transport contribution but does not yet establish a faulty rate,
solver bug, or unique causation. Baseline full-depth coefficients were not
recorded by v1, so direct all-depth coefficient subtraction is not available.

Archived/hash-verified all4 transfer streams/summary plus native outputs,
controls/pointers and window-analysis.json under
`.model_Bstar3502-diagnostics/fe-transfer-v2/results/20261022T225936Z-affbf828/`.
FeII-SL36-population-comparison.json records depth-dependent ratios. Analyzer
saved at runtime/analyze_window.py. No active state/controls/caches changed.

Recommended next controlled test: change only SL36 population on baseline4
using the normalized Fe II target5 SL36 value, preserve total Fe II by scaling
all other Fe II levels proportionally, keep other ions/elements/T baseline4,
recompute Ne charge-consistently. Scaling the complement is a required,
explicit conservation adjustment; record its size. A failure shows this
upper-level update plus that small conservation compensation is sufficient;
a pass requires a rescue/ratio test or additional level combinations. Retain
v2 diagnostics and safeguards. Next run not yet prepared; active model remains
the unchanged failed Fe II-only input at5.

### Prepared: SL36-only sufficiency test with quantified compensation

On user request, preserved failed Fe II window input, all transfer streams,
controls and outputs with verified hashes under
`.model_Bstar3502-history/lte-FeII-window-result-before-SL36-test/`.
Prepared baseline4 population/T state in diagnostic record5, changing Fe II
SL36 (native equation1681) to EXACTLY its failed Fe II excitation-only value.
The other87 Fe II levels retain baseline4 relative proportions and are scaled
per depth by (FeII_total - target36)/(FeII_total - baseline36), preserving
the ion total. Max complement rescaling is0.000131664 relative (0.0131664%)
at depth52. This is a small but explicit conservation compensation, not a
literally single-variable test. All other ions/populations and T bitwise
baseline4. Ne recomputed from charge sum. Fe II ion total preserved within
1.78e-15 relative, element totals within computed floating-point precision;
all entries finite and positive. Target matches failed-state36 exactly.
Verified file changes restricted to record5 vector; pointers/grid/controls
unchanged. Manifest records construction, prepared hash and compensation.
Marked SCRTEMP modified with backup link. Original physical5 remains preserved.

This tests sufficiency of SL36 change plus that small compensation on baseline4.
A fail would provide a narrow controlled trigger; a pass would leave other
Fe II levels or combinations, and would not exonerate SL36 interactions. All
Fe II levels should not be reset indiscriminately as a claimed remedy yet.

Retired EDDFACTOR/EDDFACTOR_INFO, BA/other radiation caches absent. Archived
previous transfer/matrix output, markers enabled. Same hash-verified v2 runtime,
SRCE_CHK, MAX_LIN2/MAX_dT0.05, variable T, lambda off, safeguard on. Preflight
ready for continuation5 -> attempted6, explicit one-iteration plan. No native
model run during investigation/preparation. From repository root, auto/fresh
start OFF:

```sh
python cmfgen_run.py models/test/model_Bstar3502 --stage main --iterations 1 \
  --cmfgen-root models/test/.model_Bstar3502-diagnostics/fe-transfer-v2
```

Input-state radiation and v2 window records are the controlled observables;
if safeguard passes, main ALSO takes a Newton step. NEXT_DIAGNOSTIC_RUN.md
records construction, compensation and interpretation; reviewed plan in backup.
Existing model summaries/corrections remain historical until regenerated.

### SL36-only sufficiency test PASSES: 20261022T233359Z-cedb7fba

Native return0, runner succeeded. Input SL36-only hybrid passes the inner
luminosity safeguard: minimum normalized luminosity0.82551, no negatives,
versus baseline4 0.83207 and full Fe II excitation update-1.3327. At depth24
radiative luminosity165570.25 Lsun vs baseline166885.40 and failed-266587.70.
Outer luminosity3.45040949e6 Lsun vs baseline3.44852872e6. Thus the SL36
change plus the documented0.0132%-maximum conservation compensation produces
a modest radiation change but does not reproduce the catastrophic deficit.
The earlier deep line dominance is not sufficient causal evidence. This pass
does not exclude interactions involving SL36 and other Fe II levels.

All recorded window coefficients/emissivities remain nonnegative, no clipping.
As main passed the safeguard, it ALSO computed a Newton step, writing diagnostic6;
all stored values finite and positive. The controlled observation is radiation
of the input SL36 hybrid, not radiation of the newly saved6. The active result
belongs to this diagnostic branch, not recovery of physical smaller-step5.
Whole-SCRTEMP differs from prepared input because6 was written, as expected;
window-analysis.json records this context rather than treating it as failed
checkpoint integrity.

Archived/hash-verified4 transfer outputs, OUTGEN, OBSFLUX, controls/pointers and
window-analysis.json at
`.model_Bstar3502-diagnostics/fe-transfer-v2/results/20261022T233359Z-cedb7fba/`.
No active inputs/restart/caches modified during assessment. Prior failed Fe II
state and physical baseline remain preserved.

Next useful complementary diagnostic: start from the failed all-level Fe II
excitation hybrid, reset ONLY SL36 to baseline4, and proportionally rescale
other Fe II levels to preserve total Fe II. Other ions/T remain baseline4,
Ne charge-consistent. A remaining failure demonstrates SL36 population change
is not necessary for the trigger; a pass indicates dependence on SL36 combined
with other changes. Record the small conservation compensation explicitly.
This is preferable to declaring SL36 innocent from a sufficiency test alone.
Next run not prepared during this assessment.


### Autonomous follow-up in isolated copies (2026-10-23, running)

User authorized running models directly as needed for full investigation.
Actual model remains unchanged at diagnostic6 from the SL36-only test. Started
complementary SL36 rescue in `.model_Bstar3502-diagnostics/root-cause-v1/rescue-SL36`,
journal `20261023T000918Z-a3158816`, with v2 observational runtime, one iteration,
normal configured full threads. Exact failed Fe II excitation-only input5 is
copied from the preserved backup, SL36 restored to baseline4, remaining Fe II
levels scaled proportionally to conserve the Fe II total, Ne recomputed from
charge sum. Maximum complementary rescaling0.00013168114 (0.0131681%). Prepared
SCRTEMP SHA256 `8b99e8d020af18c74df2ac5260666c1f5a06274e7ec3463202a375ecb4f3c15e`.
A pass/fail interpretation must wait for completion; frequency recording still
in progress when these notes were written. This does not replace physical5.

Further source review found a useful numerical discriminator, not a proven bug:
`plane/mom_j_cmf_v11.f` solves a frequency-coupled tridiagonal system; N_ON_J
introduces signed EPS terms, while G_ONLY uses bounded N/H closure. Negative
raw mean intensities are replaced by abs(value)/10 before computing flux and
saving the frequency history. Existing successful diagnostic runs also contain
many such replacements in MOM_J_ERRORS, so their mere presence is not causal
evidence. `subs/thomas.f` cautions against transfer optical-depth steps below
approximately1e-5; actual problematic matrices need assessment before claiming
this is relevant. Outer Newton matrix accuracy does not test this transfer solve.

Built isolated `moment-window-v1` runtime: all prior v2 diagnostics plus copied
MOM_J_CMF_V11 with observational calls. Records pre-THOMAS matrix/RHS (before
its destructive factorization), raw solution, post-repair J, pre-limited H,
independent formal-ray J/H and previous-frequency terms in1625–1640A. Captures
every Eddington-factor subiteration. All scientific arrays are intent(in) to
private recording storage; installed source/libraries/executable unchanged.
Applicable to this test's matching original/moment/ray90-point grids. Stream
MOMENT_WINDOW.bin header magic MOMWIN01, int32 ND,NFIELD=16; records int32
sequence, real64 frequency,dlnnu, six-character N_TYPE, then NDx16 real64 in
Fortran order. Fields: R, lower, diagonal, upper, RHS, raw r2J, repaired r2J,
pre-limited r2H(mid), formal-ray J(node), raw formal HSTORE (nodal for INT/INS;
last H90 not saved), EPS, HU, HL, HS,
previous r2J, previous r2H. Last midpoint and unused boundary entries zero.
No frequency quadrature in this stream; join frequency to v2 transfer records.

Synthetic validation passed: disabled marker creates no output, outside-window
calls omitted, raw tridiagonal coefficients retained despite THOMAS mutation,
solution unchanged within1e-14, raw/repaired J and ray/moment fields round-trip.
Commands, source/executable hashes, instrumentation.patch, and validation JSON
saved alongside runtime. Builder/test scripts copied to root-cause-v1.

Prepared two additional isolated one-iteration comparisons with identical exact
failed Fe II input5, both using moment-window-v1: `failed-FeII-moment-observation`
(N_ON_J, observational numerical baseline) and `failed-FeII-G_ONLY` (only N_TYPE
changed to G_ONLY). Input hashes, controls and ready plans saved in each folder;
BA/radiation caches absent. Serial queue waits for rescue result before launching
these, with bounded three-hour wait and two-hour timeout per run. No concurrent
full-thread model jobs intended. Queue script/session91608; live rescue session92570.
These tests are pending and do not establish a remedy or convergence. Scripts
and experiment manifests preserved; normal main model remains untouched.


Offline comparison of the failed Fe II all-level window versus the passing
SL36-only window finds several other line changes: maximum change in a single
line's emissivity / total passing emissivity is0.473 (SL5->46 atdepth59),0.455
(SL15->60 atdepth59),0.390 (SL3->41 atdepth62). SL2->35 transitions contribute
up to0.317 in this metric. These ratios rank differences, not causal importance.
At1630.021A, maximum failed/passing J ratio71.87 occurs atdepth1 while depth24
ratio is only1.0024; by1632.789A depth24 ratio6.17 and per-frequency luminosity
is-44.62Lsun vs+2.98Lsun. This strengthens the need to observe the transfer
solution throughout depth and its frequency history rather than selecting a
line from its largest local coefficient. JSON and reproducible comparison
script saved in root-cause-v1. This comparison is between two hybrids, not a
baseline-vs-physical5 attribution.

Prepared `bstar3502-analyze-moment-window.py` to check row-scaled residuals of
raw and repaired solutions, independent dense solves/condition estimates for
extreme records, signed intensity, ray/moment discrepancies and off-diagonal
signs. Validated against synthetic tridiagonal fixture: backward error5.55e-17,
independent dense solution matches native exactly. This is analysis tooling;
no actual failed-state moment-window output is available yet. Source review
also confirms FG_OPT=INT/INS selects the formal INTEGRAL branch, so the
negative-AV repair in the DIFFERENCE branch is not applicable here. MOM_J's
negative-XM repair remains applicable; do not conflate the two paths.


Live SL36-rescue observation (partial, not final safeguard result): at 49518 recorded frequencies, wavelength 1849.5609865261554A, integrated depth24 luminosity so far 10559.739858775683Lsun versus -52699.92697525717Lsun in failed FeII input over exactly the same frequency grid/weights. This avoids the previously observed sharp collapse so far. Combined with the SL36-only sufficiency pass, this provisionally points to an interaction with other FeII changes rather than SL36 alone. Full frequency completion is required before reporting rescue as a safeguard pass. partial-observation.json records exact extent and timestamp.


### Complementary SL36 rescue PASSES: 20261023T000918Z-a3158816

Native returned0 and runner succeeded after26m29s. Full152174-frequency transfer
completed; minimum normalized luminosity0.83267, zero negative depths, maximum
17.259 (outer atmosphere remains far from radiative equilibrium). Depth24
luminosity167000.7759Lsun, outer3448845.7742Lsun, inner200000.0460Lsun. Serial
record sums exactly match native values at all five captured depths. The
1625–1640A window has164 frequency/1003 line records, no negative raw total
opacity/emissivity, no negative individual FeII opacity/emissivity, no clipping.

Reconstructed prepared input record5 from preserved failed FeII input plus
baseline4 SL36/complement compensation/charge sum and verified bitwise exact
against retained record5. Native wrote6; all entries finite and positive,
charge residual max5.25e-7 relative after this Newton step. Input T_IN resolves
to unchanged original He2_IN, hash identical in main/backup/isolated copy.
MODEL difference is only native start timestamp. Completed outputs and restart
hashes saved in completed-output-manifest.json; analysis.json and reproducible
analyzer saved. Actual main model untouched at prior SL36-only diagnostic6.

This is conditional rescue evidence: SL36-only failed-state value plus small
conservation compensation on baseline4 does not trigger the collapse; restoring
SL36 baseline4 in the all-level failed FeII hybrid plus the corresponding
compensation prevents it. Thus the controlled observations point to an
interaction with other FeII changes, not SL36 alone. These experiments preserve
total FeII by changing the complement, so do not overstate literal single-variable
necessity/sufficiency. They do not yet establish a transfer bug or physical remedy.

The resulting Newton step is poor: maximum raw correction1.615e18%, minimum
major-species scaling1.0449e-5. Outer matrix reciprocal condition estimates
1.87e-18/5.05e-18, column-equilibration scale ratios1.60e-7/1.51e-7 (not residual errors). This hybrid
must not be treated as a converged or useful physical continuation simply because
it passed radiation validation. Outer normalized luminosity~17 also remains.
The goal remains incomplete pending actual mechanism and validated remedy.

The serial queue started `failed-FeII-moment-observation` at00:35:55UTC,
one iteration using exact failed FeII input and observational moment-window-v1.
G_ONLY comparison remains queued behind it. No overlapping native jobs intended.
Raw moment recording precedes the optional very-large-negative THOMAS fallback;
analyzer flags raw values at/below-1e20 so a fallback cannot be confused with
simple post-solve sign repair. Negative synthetic fixture additionally verifies
signed raw solution, small original residual5.55e-17 and large post-repair
residual0.846; independent dense solve matches the signed native solution.


Prepared bounded conditional follow-up `root-cause-v1/physical5-G_ONLY` from
verified physical smaller-step5 backup (not a hybrid). SCRTEMP is an exact copy
of that failed physical checkpoint; no population/temperature/Ne changes.
Only numerical control changed is N_TYPE=N_ON_J -> G_ONLY. MAX_LIN2,
MAX_dT0.05, variable T, fresh BA and radiation caches, safeguards retained.
Uses the same observational moment-window-v1 executable. Plan ready, hashes
and experiment manifest preserved. Separate watcher/session82318 waits for
the queued hybrid G_ONLY result and runs this one iteration ONLY if runner
status is succeeded. Otherwise writes conditional-skip.json without running.
Three-hour bounded wait, two-hour native timeout. Main model unchanged. This
extends validation to actual physical5 if the hybrid comparison is promising;
preparation is not evidence that G_ONLY helps. Script archived in root-cause-v1.


Outer-solution residual audit for the completed SL36 rescue: native full-precision
original block rows and full solution give componentwise backward errors
1.6546e-13 atdepth1 and4.3942e-11 atdepth2. Existing validated analyze_outer.py
used; outer-residual-analysis.json retained/hash-recorded. Corrected an earlier
label in the rescue entry: the fifth CONDITION column is the DGEEQU column
scaling ratio, NOT a backward error. Source declares columns as depth, norm1,
rcond1, rowc, colc, amax, info. Updated analysis.json/analyzer with explicit
column names and independently calculated residuals. Poor reciprocal condition
estimates remain real, but huge raw corrections do not establish inaccurate
linear algebra here. These local residuals do not bound global forward error.


### Failed-input moment-window evidence (native full run still active)

The observational N_ON_J build reaches/passes1625–1640A.659 moment subiterations
at164 frequencies,3–5 per frequency. All signed raw intensities positive; no
-1e20 fallback, no sign repair in this window. Maximum original-system
componentwise backward error2.3933e-16. Independent dense solves of the five
largest ray/moment discrepancies agree with native within5.45e-14 relative
infinity norm. Those matrices have raw2-norm condition~2.93–3.15e8 and
row-scaled condition~1.30–1.39e5. Thus numerical inaccuracy of THOMAS does not
explain this observed window anomaly. Sign replacement elsewhere in frequency
history has not been excluded, but is not the direct window mechanism.

Moment/ray inconsistency is substantial despite stable subiteration results.
Worst final subiteration at1635.369776A, depth41: momentJ3.5894124e-4 vs
formalJ1.6364419e-5 (21.93425times). MidpointH -2.2352059e-4 from moment
(pre-limiter) vs+9.0620527e-6 from formal rays. These are same-grid physicalH;
moment's stored r2H was divided by midpoint r2 for this comparison. Three
subiterations at that frequency progress in maxJ/rayJ ratio20.956->21.932->21.934;
this is not the20-iteration cap. Source stops on Eddington-factor agreement,
which does not guarantee ray/moment intensity agreement.

Every recorded N_ON_J matrix has some positive interior off-diagonal entries
and some negative RHS entries, though all diagonals and solutions positive.
At worst record458, positive lower off-diagonal terms correspond to cells3–12
where -EPS>HL (max1.65748); maxpositiveEPS/HU0.19007. These facts alone do not
prove the cause; compare G_ONLY and, if needed, spatial discretization/BC.

Superseded unaligned H analysis (see location correction below): the original
formal-ray estimate was+1886.8034Lsun, raw moment integrated luminosity-5982.5993Lsun. Boundary/node
H and native post-limiter/interpolated flux are different observables; recorded
native node24 window luminosity is saved in moment-window-summary.json.
This opposite flux sign on the identical input warrants transfer-discretization
investigation before blaming the population linear solver. Optical depths are
small in outer cells and formal rays there are outward while momentH is inward.
At worst frequency depth24 scattering fraction0.9311, depth41 fraction0.1453.
No scientific controls changed during this observation.

moment-analysis.json, moment-window-summary.json, ray-moment-window-comparison.json
and full streams retained in failed-FeII-moment-observation. Full native run,
G_ONLY contrast and conditional physical5 test remain pending. Source also
provides MIXED closure (N/H where reasonable, N/J near Hzero), and OBC_TYPE with
BC_PAR1 frequency switch; neither is a validated remedy or executed test yet.
MOM's VFRAC grid insertion uses radial deltaV, so constant-velocity outer
geometric terms are not necessarily refined by tightening that option alone.


### Instrumented failure reproduced; G_ONLY started01:02:36UTC

Full152174-frequency observational N_ON_J run ends invalid_output after native
poor-flux STOP (native0), minnormalizedL-1.3327 with56 negative depths. SCRTEMP
SHA256 exactly unchanged from prepared input5. IntegratedL atdepth24-266587.7002,
outer3896919.5577, inner200000.0460. Maxabsolute per-frequency dL difference
from v2 failing reference9.7006e-10Lsun. Thus added matrix recording preserves
the failure to floating-point precision. completed-analysis.json and hashed
output manifest saved with full MOM_J_ERRORS, streams and matrix analysis.

Serial queue started exact same failed FeII input with only N_TYPE=G_ONLY at
01:02:36UTC. Physical5-G_ONLY watcher remains conditional on its success.

### Analytic geometry tests and experimental Q integration (not a model remedy yet)

To separate geometry/closure effects from atomic populations, built standalone
MOM_J_CMF_V11 fixture with the actual90 baseline radii, constant radial velocity
255km/s, sigma=-1, tiny scattering optical depth (innerCHI1e-12), analytical
J=K=H=N=amplitude/r2, dlnnu6e-5 and amplitudes1,10,.1,1,.01. Closure moments
supplied analytically, no atomic solve. This is NOT a model replay. Both existing
PNT_SRCE and stabilized prescribed-J boundary tested. The transparent PNT_SRCE
fixture is badly conditioned under N_ON_J and is not representative of this
stellar model's optically thick diffusion inner boundary. It remains unstable
in a separate exact-Q=1 control and MUST NOT be cited as proof of this model's
cause. G_ONLY and MIXED preserve spectral amplitude far better in that fixture.

A clean directly testable issue is geometric Q quadrature. Existing QFROMF
integrates(3F-1)/(rF) over r then subtracts2ln(r/rND). For constantF=1, exactQ=1,
but maxrelative error on this grid is0.006566916. ConstantF=1/3 is exact by
construction in old formula. Equivalent log-radius formulation is
ln Q = integral[(F-1)/F dlnr], from innermost radius to requested radius.
This avoids cancellation of separately approximated geometric terms and is
exact for constantF on any grid. Experimental copied QFROMF changes only the
integration variable/integrand and removes the final2log term.

Direct analytic checks on actual90 radii:

| Profile | Original max relative Q error | Log-radius max relative Q error |
| --- | ---: | ---: |
| F=1, Q=1 | 0.006566916 | 0 |
| F=1/3, Q=(rND/r)^2 | 8.88e-16 | 2.78e-15 |
| F=1/2, Q=rND/r | 0.003288866 | 8.88e-16 |
| F=1/(3-0.4z), z=ln(r/rND) | 0.001125657 | 1.11e-15 |

Last profile has exact lnQ=-2z+0.2z^2. All computedQ finite positive. In the
stabilized prescribed-J free-stream fixture, original N_ON_J J errors grow up
to~4.82% across changing amplitudes; exact-Q/log-radius variant reduces these
to<=3.68e-8. G_ONLY/MIXED also improve their baseline geometric error from~0.66%
to~6.34e-10. Small flux clipping and boundary-conditioning effects persist;
these tests do not establish an astrophysical remedy. The existing routine is
used by moment and variation solvers, so the new executable overrides QFROMF
consistently, while the formal integral-ray branch does not call it.

Isolated runtime `moment-logq-v1` links all other moment-window-v1 objects
unchanged, hashes/build commands/analytic driver/results preserved. Patch for
review at `doc/developer/patches/bstar3502-qfromf-log-radius-experimental.patch`.
Installed source/libraries/executable untouched. Full-model evidence still
required: prepared `root-cause-v1/failed-FeII-logQ`, exact failed FeII input5,
original N_ON_J controls, only alternative Q quadrature plus same observations.
Watcher/session85111 waits until physical5-G_ONLY is completed or conditionally
skipped, then runs one full iteration (four-hour bounded wait, two-hour native
timeout). This keeps native jobs serial. Reproducible scripts archived in
root-cause-v1. A passing analytic limit alone is not sufficient to adopt it.


### Huge corrections and MAJOR damping traced on physical4->5

Reconstructed FIDDLE_POP_CORRECTIONS_V2 directly from full-precision saved
solution, old populations and native controls, without changing any input.
For the SL36 rescue5->6, predicted updates match ALL saved new populations
bitwise (maxrelative difference0). Minimum scale1.0448820354e-5 is set atdepth18
by equation925, terminal after MgIII, i.e.MgIV: inputpopulation0.001510549,
population/Ne1.4185593e-10, rawfractional request-95704.5835 (negative means
increase). Native MAJOR includes every non-T variable with population>1e-10Ne,
so this trace ion qualifies and scales all corrections at that depth. It grows
by exactly factor2 with MAX_LIN2. Other worst scales are set by this same MgIV
variable atdepths11–17, NeIV at19–20, FeVI at8–10, andOV at5–6.

Largest raw increase is equation829, OVI (terminal after OV), atdepth19:
inputpopulation6.10524e-20, population/Ne3.45526e-27, requestedfractional
increase1.6150984e16 (displayed1.615e18%). It is excluded from MAJOR's common
scale and individually capped. Largest raw decrease MnII SL36 atdepth12 has
population/Ne~1.995e-25 and is also individually capped. Thus a maximum raw
percentage alone greatly exaggerates the material population change, while
other still-trace ions just above the MAJOR cutoff genuinely throttle progress.

Repeated the same audit READ-ONLY on preserved original physical smaller-step
4->5 (not a hybrid). Predicted updates again match every saved output population
bitwise. Minimum scale1.0448766724e-5, same MgIV equation925/depth18, rawrequest
-95705.0747 andpopulation/Ne1.4185582e-10. Largest OVI rawrequest1.6155810e16,
same negligible input; recorded physical result confirms this is not created by
the SL36 diagnostic. JSON at root-cause-v1/physical4-to5-major-scaling-analysis.json;
rescue-specific JSON stays with that run; configurable analyzer archived. No
archived backup file was edited. This diagnoses damping, not a validated new
cutoff/relaxation remedy. Radiation changes may change these requests.

Source audit confirms DO_LAM_AUTO controls starting non-lambda steps when an
explicit lambda start has converged, not the internal cycling in
SOLVE_FOR_POPS. With RD_LAMBDA false and MAXCH>=LAM_VAL, a full step schedules
a fixed-T lambda step; a huge MAXCH>1e5 keeps lambda active. Setting both
DO_LAM_IT and DO_LAM_AUTO false does not disable that cycle. Current LAM_VAL800
can therefore select lambda because of the negligible OVI request. A bounded
full-step recovery trial can suppress that internal switch with LAM_VAL1e100, matching the existing MAX_CHNG failure limit.
This suppresses cycling for practical requests below that limit. This has NOT been applied
to prepared one-iteration comparisons, where it has no next-iteration effect.
Verify multi-step behavior before recommending it. Existing auto policy _fixed
only reports/stops missing full steps; it does not implement this remedy.


### G_ONLY window is worse; physical follow-up cancelled before launch

With unchanged exact failed FeII input and default QFROMF, G_ONLY records852
subiterations across164 window frequencies (histogram3:6,4:29,5:71,6:43,7:15).
All raw intensities positive, maxbackward error2.7087e-16; no opposite-signed
off-diagonal entries or negative RHS entries. Independent dense solutions
match within4.15e-14, scaled matrix conditions~2577 for extreme records.
Nevertheless final1635.369776A moment/rayJ ratio189.1009 atdepth42, versus
N_ON_J21.93425 atdepth41. Early-subiteration peak199.3223 is not the final value.
Integrated window native node24 L=-592050.2948, rawmoment midpoint24=-592338.8062,
formalray unaligned estimate=+78062.4093 (superseded below). Thus simply replacing N_ON_J by G_ONLY does
not repair the measured transfer inconsistency. Global OUTGEN additionally
reports failed Eddington-factor convergence at some shorter wavelengths near
844A; window iterations themselves are below the cap. Full-spectrum native
guard/result remains pending. No positivity/small-residual argument overrides
these actual ray/moment discrepancies.

Stopped only waiting wrapper PIDs24906 and30618 after verifying their exact
commands, not the live native G_ONLY process or parent serial queue. Wrote
physical5-G_ONLY/conditional-skip.json with measured reason. Prepared physical
input remains unrun and unchanged. Old source scripts preserved as historical;
new active watcher/session48346 waits directly for G_ONLY native result and then
runs failed-FeII-logQ. This avoids unsupported physical G_ONLY follow-up and
keeps native jobs serial. Model controls/SCRTEMP in logQ test are bitwise
identical to failed FeII reference; only executable's Q quadrature differs.
Prepared physical5-logQ/session89752 from original physical5, identical original
controls and populations; it runs one iteration only if hybrid logQ succeeds,
otherwise records skip. Bounded waits/timeouts retained, main model untouched.

General reusable ray/moment window analyzer archived; new analysis-v2.json
files keep native nodal, raw pre-limiter midpoint and formal midpoint quantities
explicit. Existing N_ON_J completed hashed artifacts remain preserved.

Extended Q analytic tests to two smooth nonlinear profiles, to avoid relying
solely on profiles polynomial in logR. Let z=ln(r/rND). ProfileF=1-(2/3)e^-2z
has exact Q=1/sqrt(3F); original maxrelative error0.005219884, log-radius
0.0002874311. ProfileF=1/(1+2e^-z) has Q=exp[2(e^-z-1)]; original0.003780155,
log-radius2.2802264e-5. Both remain positive. Thus improvement extends beyond
constant/log-linear profiles, though general quadrature is not exact. Updated
analytic-validation.json/build manifest/driver retained. Git inspection of
b5f07ccc930a4096eaae482184d4a7b8bac8da87 confirms the same original r-based
Q integration formula existed in mid-2023 (D0 constants instead of LDP). This
specific geometric quadrature behavior is not introduced by recent source fixes.


### G_ONLY full-spectrum failure; logQ comparison started01:30:34UTC

Runner invalid_output after native poor-flux guard, normalizedLminimum-310.42,
maximum354.36,74 negative depths. All152174 frequencies completed. Depth24
luminosity-62021764.3731Lsun, outer70811657.1570, inner200000.0460.126 global
Eddington-factor convergence warnings. Entire SCRTEMP hash exactly unchanged
from prepared input5, so no new Newton checkpoint. Completed analysis and
hash-verified output manifest saved in failed-FeII-G_ONLY. Native0 again does
not indicate success. Skipped physical G_ONLY test remains unrun.

Watcher48346 started failed-FeII-logQ at01:30:34UTC, same failed input5 and
original N_ON_J controls, experimental Q quadrature only. Physical5-logQ watcher
89752 waits for that result; no other native job intended. Main model/source
installation remain untouched. Full goal still incomplete: no validated model
remedy or convergence claim from analytic limits alone.


### Correction: formal H storage is nodal under INT/INS

Rechecking FG_J_CMF_V13 source confirms DEFINE_AT_MID_POINTS is a false
parameter. Its INTEGRAL branch sets HN_DEF_ON_NODES=true and stores HNU_STORE
at the radial nodes. Earlier H comparison interpreted the raw field as midpoint
values. That was incorrect; J storage is nodal in both routines and was compared
correctly. Raw momentH is r2H at midpoints as previously described. No native
run/input/scientific quantity changed; this corrects derived analysis only.

New analysis-tools/project_ray_nodes uses the installed MON_INTERP with precisely
the GET_MOMS_NON_REL projection: interpolate H/J and r2J separately to Rmid,
then multiply. The raw recorder saved Hnode1..89 but omitted Hnode90, so use
only midpoints1..87 whose local cubic stencils are fully recorded; do not invent
inner-boundary H. Synthetic constant r2J and signed-linear H/J cases validate
projection to<1e-14. Native source and local-stencil bounds checked explicitly.

Corrected complete-window comparisons:

| Case | Native node24 L | Formal node24 L | Raw moment midpoint24 L | Projected formal midpoint24 L |
| --- | ---: | ---: | ---: | ---: |
| N_ON_J | -5979.8347 | +2074.6158 | -5982.5993 | +2073.1168 |
| G_ONLY | -592050.2948 | +85832.7407 | -592338.8062 | +85772.8306 |

UnitsLsun, integrated1625–1640A, final subiteration per frequency. Opposite signs
and strong discrepancy survive correct alignment. Final nodal J ratios21.93425
and189.10091, all matrix/residual/condition metrics, bolometric luminosity and
checkpoint results unaffected. Earlier formal-midpoint flux figures1886.8 and
78062.4 and unprojected H differences are superseded, not comparable midpoint
measurements. Retain old derived files/hashes as historical evidence, with
analysis-location-correction.json pointing to new ray-moment-window-analysis-v3.json.
Updated completed manifests add native-projected arrays and corrected analyses.
Runtime raw-ray-H-location.json documents original binary schema interpretation;
compiled source/executable left frozen. Analyzer now omits the unaligned H
comparison fields and directs flux work to v3. Reusable recorder should add
location flag/full H90 if extended beyond this fixed-INT setup.


### 2026-10-23: logQ rejected as sufficient remedy; MIXED comparison launched

The isolated logQ run20261023T013034Z-89cfa93b completed all152174 frequencies
and failed the native luminosity safeguard (runner invalid_output). Minimum
normalized luminosity-1.2422, maximum19.397,56negative depths; depth24 bolometric
luminosity-248483.1271Lsun, outer3876150.9710, inner200000.0460. Entire SCRTEMP
hash still matches the prepared exact failed FeII input. No Newton update was
accepted. Physical5-logQ watcher correctly skipped rather than propagating an
unvalidated candidate into the physical branch.

All659 window moment systems remain positive with backward errors<=2.209e-16.
At1635.369776A final moment/rayJ ratio21.66839 atdepth41 (original21.93425).
Correctly aligned window flux comparison: native node24-5934.7490Lsun versus
formal node24+2069.0526; rawmoment midpoint24-5937.7077 versus projected formal
midpoint24+2067.5337. This is a modest numerical change, not resolution of the
sign/transfer inconsistency. Analytic Q accuracy alone does not justify a model
remedy. Saved completed-analysis.json and hashed completed-output-manifest.json
in failed-FeII-logQ, plus moment-analysis and v3 projected-ray comparison.

Verified no native CMFGEN process remained before launching the next comparison.
At03:24:57UTC started failed-FeII-MIXED using original moment-window-v1 executable
and original Q integration; only VADAT N_TYPE changes from N_ON_J to MIXED.
SCRTEMP is byte-identical to failed-FeII-moment-observation and the saved failed
FeII history. One iteration, timeout7200, default full configured thread pool;
fresh radiation/BA caches. Actual model and installed source remain untouched.
Script bstar3502-run-mixed-comparison.py and reviewed plan/manifests archived
under root-cause-v1. Exec session26401; full result pending. MIXED uses N/H
where the native ratio is0.05..1.1, otherwise N/J; this distinguishes a locally
selected closure from both globally fixed choices. Current no-insertion moment
grid avoids the native MIXED-with-extra-points limitation. A pass, if any, will
still require testing original physical5 and subsequent full updates.


### 2026-10-23: MIXED full failure; moment-resolution comparison

MIXED completed all152174 frequencies and failed the guard: min normalized
luminosity-215.05, max249.11,73negative depths,178 Eddington-factor convergence
cap warnings. Depth24 bolometric L=-42952050.4194Lsun, outer49778737.3257,
inner200000.0460. Checkpoint hash unchanged. Window846subiterations,164
frequencies; worst final moment/rayJ ratio184.38269 at1635.369776A,
depth42. Window node24 native-444255.6627 versus formal+64704.9741Lsun;
aligned midpoint values-444419.9365 versus+64660.1209. Thus both G_ONLY and
MIXED worsen the original N_ON_J failure. Completed analysis/manifests retained.

Built isolated observational moment-window-v2 (no Q/scientific change). V1's
recorder assumed NDmoment=ND_STORE and would read beyond the ray array after
moment insertion; do not use it on unequal grids. New recorder writes separate
complete formal-ray R,J,H,K,N with nodal-location flag, including innermost H,
and36fields of original matrix/solution/coefficients on the moment grid. Formal
J uses native r2J interpolation when grids differ. Native MON_INTERP projector
now handles every midpoint on the expanded grid using complete original ray H.
Bounds-checked recorder tested on equal90/90 and unequal178/90 synthetic grids:
all returned J/H vectors bitwise identical to original uninstrumented routine
both disabled and enabled. Projection constant-r2J,H/J=1 fixture error2.22e-16.
Independent interior matrix/RHS reconstruction from recorded coefficients
matches fixture within2.16e-16. Source, schema, commands, hashes and validation
outputs saved in moment-window-v2; reproducible scripts archived root-cause-v1.

At03:49:49UTC started failed-FeII-momrefine01 after MIXED completion, original
failed FeII checkpoint, VADAT identical except VFRAC_MOM20000->0.1. N_ON_J,
Q quadrature, ray settings and all physical inputs unchanged; fresh caches,
one iteration, full configured threads. Expected moment depth count228 using
previously measured minimum Doppler width17.537km/s; actual header will decide.
Native comparison result pending. Session10618. Main model untouched.

### Separate source issue: derivative angular factors after moment insertion

Source call chain COMP_J_BLANK -> MOM_J_CMF_V11 -> GET_MOMS_NON_REL populates
shared K_ON_J/NMID_* arrays on the expanded moment grid. CMFGEN_SUB then calls
DO_VAR_CONT with original ND/R. VAR_MOM_J_CMF_V12 directly reads the firstND
entries of these expanded arrays, including previous factors; no remapping or
refresh is present between calls. Thus the vectors are indexed against the
wrong radii after insertion. Default20000/no-insertion comparisons are not
affected by this issue.

A standalone reproduction uses original uninstrumented MOM source, actual90
model radii, synthetic V(r) and f(r)=.34+.6log(r/rND)/log(r1/rND), VFRAC_MOM=.1.
Expanded grid178, original90. Prefix90 of shared f differs from the required
original-node f by up to0.47823846. Positive synthetic angular factors and
all five frequencies reproduce the mismatch. This is evidence for the grid
mapping defect, not a physical model test. Saved driver, output, analysis.json
in moment-window-v2/angular-grid-audit. Source inputs and test are archived.

The running refinement is still a valid fixed-input radiation comparison:
variation calculations do not write shared angular factors or update the
populations during the frequency sweep. Any final Newton update, if the guard
passes, must not be treated as a validated remedy until angular-grid derivative
handling is addressed and checked. Even mapped coarse-grid derivatives remain
an approximation to a refined transfer solve; assess with finite differences.
Do not silently promote a safeguard pass or one correction to convergence.


### 2026-10-23 04:15UTC: refined-grid window and frequency-history localization

VFRAC_MOM=.1 actually produces228moment points while ray grid stays90. All660
recorded window systems are finite with positive rawJ, no fallback, backward
error<=2.325e-16. Independent dense solves agree within3.53e-14 relative;
row-scaled condition~1.85e5 at worst record. Final peakJratio23.10236 at
1635.369776A, radius673.4345 (originaldepth41, refinedindex179). Native node24
windowL=-6421.9319Lsun versus formal+2135.7347; raw moment midpoint24-6425.3200
versus projected formal+2134.1340. Thus simply tightening radial-velocity
insertion did not repair the measured transfer discrepancy. Full guard pending.

New recorded coefficients independently reconstruct every interior A/B/C/RHS
to4.19e-16 relative (RHS normalized by sum of terms), and rawH to9.25e-17.
For each frequency except the first in the window, replace only the previous
frequency momentJ/H in the RHS with recorded formal-rayJ/projectedH. Angular
factors/current matrix and true source remain fixed. At worst record this
reduces maxJratio23.10236->1.05966 (minimumratio.90056); substitution residual
for formalJ reduces.17244->.004895. No negative counterfactualJ. This is a
one-frequency counterfactual, not a new self-consistent native solution.

Important qualification: formal rays used previous-subiteration momentJ for
coherent-scattering illumination, whereas the moment matrix treats scattering
implicitly. Therefore remaining residual must not all be attributed to spatial
error. Adding a separate frozen-scattering-source estimate gives Jratio range
.99664..1.07742 at the worst record. It uses previous-subiteration fine-gridJ;
source illumination is exact at original nodes, but ray/moment interpolations
differ between inserted nodes, so this is not an exact ray-equation replay.
Largest residual remains near radius692.335 (originaldepth28), which already
has velocity-inserted neighbors. Earlier provisional wording that all remaining
error was in intervals without inserted points was too strong. Uniform spatial
refinement remains a controlled test, not a demonstrated fix.

For exactly the same163frequencies (first window frequency excluded): rawnative
midpoint24 L=-6414.5430, projectedformal+2129.9153, formal-history counterfactual
+1966.8854, and history+frozen-scattering estimate+2130.5438Lsun. This checks the
flux sign as well as J. Counterfactual H limiter is not applied in these
one-frequency flux calculations; this is explicit in saved metadata.

A separate frequency-window replay holds final native angular factors and true
emissivity fixed, propagates J/H frequency by frequency, and reproduces native
repair/limiting rules. Starting from native first-window state reproduces all
subsequent savedJ within3.16e-13 relative infinity norm; L24 matches within
7.1e-9Lsun. Native path has17H-limit events and no negativeJ repairs. Resetting
only the initial window state to the recorded formal J/H instead leaves
positive integratedL24=+1122.9599Lsun over the remaining163frequencies, no H
limits or negativeJ, and maxJratio never exceeds1.00499. MinimumJratio can be
.42563 because the recorded formal fields were illuminated by the old larger
moment source; this is not an independently recomputed ray solution. The
original native peak23.1 therefore depends strongly on the radiation history
entering1625A; the window alone does not regenerate it from that formal seed
with frozen coefficients. This narrows the mechanism but does not prove the
earlier origin or validate resetting native radiation memory as a remedy.
Saved history-coupling-analysis.json, depth/source estimates, and
frequency-window-replay.json with reproducible scripts under root-cause-v1.

Cancelled only waiting boundary-test wrapper70032 before native launch; saved
conditional-skip reason in failed-FeII-boundary2. Prioritized uniform spatial
comparison instead of treating boundary changes as the next established fix.
Built moment-uniform3-v1, original scientific MOM routine with only IT1=max(IT1,2)
in both grid-size/build loops (minimum three subintervals everywhere), original
Q and all other scientific operations unchanged. Recorder is validated v2.
Fixture produces268points, preserves every original node exactly and every
original midpoint within2.03e-16 relative. All recorded fields finite. Source,
patch, executable hash, build commands and fixture outputs preserved.

Prepared failed-FeII-uniform3 with exact original VADAT and SCRTEMP; conditional
wrapper/session11663 starts one iteration only after current refinement returns
invalid_output with inner_flux_accuracy. Other outcomes skip for review.
Derivative angular-grid mismatch remains: this is a radiation comparison only;
do not promote its Newton checkpoint into the actual model. Actual model and
installed source remain unchanged.


### 2026-10-23 04:20UTC: velocity-refinement full failure; uniform test underway

failed-FeII-momrefine01 completed all152174frequencies, invalid_output at native
flux guard. Min normalizedL-1.3371, max18.679,57negative depths, zero Eddington
iteration-cap warnings. Depth24 L=-267449.9246Lsun, outer3732616.1349,
inner200000.0460. SCRTEMP hash exactly unchanged. Completed analysis and hashed
manifest retained. This rejects VFRAC_MOM=.1 alone as the remedy.

Conditional uniform3 run started04:16:14UTC after this result. NativePID74104,
wrapper72317/session11663. Source change only minimum two inserted moment points
per original interval; original N_ON_J/Q/VADAT/populations retained. Expected268
moment versus90ray points. Full result pending; main model untouched.

Boundary-only J_COMP comparison uses matching152174frequency grids and actual
Fortran exponent parsing. Both baseline4 and failed FeII input already have
outerJmom/Jray~36.2755 near800A and~4.8near1625A; their pre-window numerical
inconsistency is largely common. At1630.021A baseline ratio.0159 versusfailed
4.0627; at1635.370A baseline1.0182 versusfailed4.7641; at1800.036A baseline.9918
versusfailed3.1098. Thus the branch difference becomes persistent in this window,
while a substantial shared transfer inconsistency exists earlier. A per-bin
signal screen (>0.01Lsun absolute native outerdL) finds ratios>10 alreadynear
493A in both inputs; this is not a convergence threshold or a full-depth onset
measurement. Saved pre-window-jcomp-history-analysis.json and script. Passing
the luminosity safeguard at baseline4 is not evidence of globally accurate
radiation transfer (its outerbolometricL was already~17Lstar).

A possible future grid criterion, not implemented: include projected/geometric
velocity variation as well as radial deltaV. FG source GAM uses V/R*(1+sigma*mu2),
so constant radial velocity still has geometric advection. On this actual grid
max radialdeltaV19.4362km/s versus max Vavg*abs(deltaLogR)62.0698km/s. Taking
max of these increments at VFRAC_MOM=.1 and Doppler17.537 gives594points versus
228for radialdeltaV alone. This is a proposal only, not a validated source fix;
see projected-velocity-grid-proposal.json. Uniform3 tests spatial resolution
without assuming that proposed criterion is the final remedy.


### 2026-10-23 04:35UTC: validated faster fixed-input radiation diagnostic

The initial uniform3 full-BA run was unexpectedly slow in X-rays. Read-only
one-second sample at04:24:20UTC showed time dominated by BA_UPDATE_V7 and OpenMP
synchronization, not MOM/FG transport; memory footprint10.8GB. No MOM_J_ERRORS
or Eddington-cap warnings at that point. Interrupted only nativePID74104 at
04:27UTC, preserving9432partial frequencies and unchanged SCRTEMP. This was
an intentional incomplete experiment, not a native luminosity-guard result.
Saved performance-sample.txt and interruption-analysis.json.

Added opt-in isolated TRANSPORT_ONLY_DIAGNOSTICS to copied CMFGEN_SUB in
transport-only-v1: preserve the complete ordinary DTDR calculation, then set
COMPUTE_BA/WRBAMAT false; stop before SOLVE_FOR_POPS even if luminosity check
passes. No input/model/installed source change. This avoids known derivative
mapping problem and unnecessary BA work for fixed-population radiation tests.
It is not a new production iteration mode. Native FLUX_CAL_ONLY was deliberately
not substituted, because it changes DTDR treatment. Normal runner may report
invalid_output when no Newton checkpoint is produced; assess completed radiation
and native safeguard separately, never call that convergence.

Ran failed-FeII-reference-transport with exact ordinary failed input/control
checkpoint and original90point moment grid. Full152174frequencies and659window
subiterations completed~5m15 (versus~26m ordinary full BA). Original reference
versus diagnostic: frequency grid/weights bitwise identical; SCRTEMP unchanged;
FEII_LINE_WINDOW and printed J_COMP byte-identical. Other radiation/coefficient
arrays differ at floating-point level (DTDR.10584259500956791 versus original
.10584259500956794). Initial strict byte-identity gate correctly stopped its
wrapper before launching a candidate. Do not describe all arrays as bitwise equal.

Then quantified full numerical equivalence before proceeding: max per-field
peak-normalized error1.2582e-11 across all recorded frequency/depth/opacity/
radiation fields, window coefficients/radiation1.5431e-11, integrated five-depth
luminosity relative difference1.1724e-13; largest absolute integrated difference
3.68e-8Lsun. Gate requires<1e-9 for each of these plus identical frequencies and
checkpoint. All checks passed. Original failed luminosity/transfer behavior
reproduced. Saved numerical-reference-equivalence.json with complete metrics,
strict-byte report retained separately. This is measured floating-point
validation of a diagnostic, not relaxation of physical convergence criteria.

At04:35:20UTC started failed-FeII-uniform3-transport using same validated
CMFGEN_SUB and uniform3 MOM routine (expected268points). Exact original
VADAT/SCRTEMP retained; native original Q and N_ON_J; no BA or Newton after
normal DTDR. Session9096; full result pending. Prior strict wrapper59838
terminated at its byte-identity assertion as intended; it did not launch a
second native job. Main model and installed source remain unchanged.


### 2026-10-23 04:46UTC: uniform refinement sequence and targeted grid candidate

Uniform3 transport completed all152174frequencies, still native guard failure:
min normalizedL-.77985, max17.839,53negative depths, no Eddington caps,
checkpoint unchanged. Depth24 L=-155927.5730, outer3564736.2607, inner200000.0460.
Window621systems, worst finalJratio14.6011; native node24L=-3026.3525 versus
formal+1674.4207Lsun. The residual/linear-system checks remain at rounding error.
Thus refinement improves the discrepancy on exact fixed input but is not yet
sufficient. Source-grid derivative issue cannot explain this diagnostic: no
variation equations run after unchanged DTDR, no population solver is called.

At04:41:40UTC started failed-FeII-uniform9-transport using802moment points
(minimum8inserted points per original interval) and same validated diagnostic
backend. Original Q/VADAT/pops/physical grid retained. Fixture preserves original
nodes exactly, original midpoints within4.36e-16, all recorded fields finite.
Window577systems complete: peakJratio6.30170 at1635.369776A, native node24L
-429.8064 versus formal+1335.7795Lsun; midpoint-430.0827 versus+1335.1761.
Full luminosity guard pending. No convergence claim from this partial result.

The velocity-only .1 test left all660window systems with opposite-signed
interior off-diagonals, just like659/659 original systems. Uniform3 reduces this
to24/621. At the peakJ discrepancy, -EPS/HL falls1.6575->.61485, but the maximum
across finer-frequency steps is still6.1518 (original16.5765). This is consistent
with a frequency/space resolution interaction; G_ONLY's earlier failure proves
that a sign property by itself is not a remedy. Evaluate actual radiation.

Prepared a targeted experimental candidate transport-only-projected-grid-v1,
not yet launched: replace radialdeltaV in both moment-grid loops by
max(radialdeltaV,max(abs(Vi),abs(Vi+1))*abs(log(Ri/Ri+1))). Keep the original
VFRAC_MOM*minVDop threshold and even-point insertion preserving midpoints.
This uses a conservative endpoint speed instead of the earlier average-speed
proposal. Motivation is source GAM=V/R*(1+sigma*mu2), which includes geometric
Doppler terms even for constant radialV. Fixture constantV255km/s gives764
moment points atVFRAC_MOM=.1, compared with90under the old rule; all original
nodes exact, midpoints preserved, all recorded fields finite. This validates
construction only, not a physical remedy. Actual model grid size will be read
from native output. Installed source remains unchanged; source/patch/commands/
hashes and fixture saved in isolated runtime. Reproducible generic
root-cause-v1/run_transport_probe.py preserves independent input checkpoints,
records native guard versus intentional no-Newton stop separately, and supports
controlled fixed-input resolution or boundary comparisons.


### 2026-10-23 04:50UTC: uniform9 passes major check; diagnostic exit corrected

Uniform9 completed all152174frequencies, global normalizedL min.14076,
max16.769, zero negative depths, no Eddington-cap warnings. Depth24L=28402.3556,
outer3350811.8598, inner200000.0460. Checkpoint unchanged. Importantly OUTGEN
contains **only25% advisories**, no factor-two warning. The native major check
is photosphere-to-inner-boundary, not all depths. The initial generic summary
incorrectly conflated every 'poor flux accuracy' substring with fatal failure;
transport-summary.json now corrects that classification and preserves the reason.

The diagnostic then hit a missing-BA reload before its intentional no-Newton
stop. That error is a harness artifact: full radiation and native quality checks
were already recorded, and no checkpoint changed. Built transport-only-v2 and
linked uniform9/projected variants: move the existing opt-in STOP block ahead
of unused READ_BA_DATA_V3. Static source-prefix equality confirms no executable
change before complete radiation and final energy-equation output. Old binaries/
logs/manifests remain immutable. New no-Newton flag and 25%-versus-factor-two
classification are explicit; a diagnostic runner invalid_output is not itself
a physical convergence judgment.

At04:50:12UTC started failed-FeII-projected01-transport using targeted projected
velocity criterion withVFRAC_MOM=.1, exact failed hybrid checkpoint and original
Q/N_ON_J/other controls. Validated transport backend and corrected exit; no BA
or Newton. Session62509. Full result pending; main model/source untouched.


### 2026-10-23 05:15UTC: ray-only control isolates a simple existing remedy

Projected moment.1 + ray.1 completed all152174frequencies, clean diagnostic stop,
no factor-two or25% luminosity warnings, no Eddington caps. Global minimum
normalizedL.97725, maximum15.808, no negative depths. Depth24L210970.4208,
outer3158807.5234, inner200000.0460. Window560systems: maximum finalJratio1.02327,
minimum.96299; largest symmetric difference3.7703%. Native node24windowL1142.0971
versus formal1141.1270; rawmidpoint1141.7475 versus projectedformal1140.7926.
Maximum-ratio labels in earlier analyses described overprediction only; added
independent two-sided-window-agreement.json to include underprediction too.
No earlier raw/max-ratio measurements changed. Do not claim a2.3% two-sided
bound: the measured full range in this window is approximately-3.7%..+2.3%.

Then ran failed-FeII-ray01-transport, original90point MOM/scientific source,
only VFRAC_FG20000->.1. Full result clean: min normalizedL.97455,max17.109,
zero negative depths, no factor-two/25% luminosity warnings or Eddington caps,
checkpoint unchanged. Depth24L205122.3719, outer3418933.7120, inner200000.0460.
Window559systems: maxJratio1.03906,min.95693, max symmetric difference4.4016%;
node24nativewindowL1144.1745 versus formal1141.1230; midpoint1143.8611 versus
formal1140.7904. Both intensities and signed flux now agree closely using
existing source and original model populations/temperature. Thus source
quadrature/closure/moment-grid changes are unnecessary to remove this
reproduced hybrid transport failure. This finding does not replace the separate
initialization fixes or prove that all raw population corrections are settled.

Started physical5-ray01-transport at05:13:30UTC from exact original physical
checkpoint5 (all species and its ownT/Ne, not the hybrid). Only VFRAC_FG=.1;
original Q/N_ON_J/VFRAC_MOM and physical parameters retained. Session79255.
Prepared physical5-ray01-full/session12002 with ordinary full-BA observational
runtime, one full iteration, fresh caches, same physical input and ray setting.
It launches only if the physical transport probe completes intentionally with
unchanged checkpoint, no factor-two warning, min normalizedL>=.5 and max window
symmetric J difference<10%. Otherwise it records a skip for review. Main model
SCRTEMP/T_IN hashes captured for an independent unchanged-main check. No main
or installed-source changes made.

Historical git check atb5f07ccc930a4096eaae482184d4a7b8bac8da87 confirms radial-only
moment insertion and direct shared-angular-factor reads by VAR_MOM_J_CMF_V12
were already present in mid2023. This is provenance, not evidence that the
historical model suffered the same failure. Current successful ray-only setting
does not insert moment points and therefore does not exercise that derivative
mapping defect.


### 2026-10-23 05:47UTC: native BA cache regression and isolated patch

Real STORE_BA_DATA_V3 -> READ_BA_DATA_V3 binary round trips reproduce the flag
swap: two of four stored FIXED_T/COMPUTE_BA combinations return the wrong T mode.
Missing binary data or mismatched dimensions also mutate the caller's FIXED_T
before reporting failure. An additional regression shows that truncating only
the final BA_T_EHB record is incorrectly accepted: READ uses IOSTAT/ERR without
an END handler, and EOF on the last record can fall through as success.
These are actual native reader/writer tests with small matrices, not inferred
from condition columns or mocked Python file readers.

Isolated proposed fix reads header flags in the writer's order into local
FIXED_T_RD; commits FIXED_T only after all matrices read successfully; gives
each READ an explicit EOF failure path. CMFGEN_SUB passes COMPUTE_BARDIN via
CHK for the initial read, honoring an explicit fresh-matrix request rather
than always probing a stale cache. This initial read is outside iteration
label20000, so the change does not override within-run BA reuse decisions.
The reader's existing COMPUTE_BA bypass is validated separately. Installed
source/executables remain untouched.

All patched native cases pass: four flag combinations and exact matrix values,
missing binary/dimension failure without mode mutation, truncated final record
rejection without mode mutation, and fresh-compute bypass without reading or
altering cached matrices. Original flags fail2/4 and accept the truncated final
record. Bounds checking enabled. Native source/commands/hashes/outputs retained
in ba-restart-flags-v1/validation.json. Public standalone regression also passes
against the isolated proposed reader and caller source; git apply --check passes
against the installed source tree.

Reviewable artifacts:

- [Experimental BA restart patch](patches/bstar3502-ba-restart-flags-experimental.patch).
- [Native BA regression](cmfgen-review-tests/check_ba_restart_flags.py).

Run the regression after applying/compiling source changes with
`python doc/developer/cmfgen-review-tests/check_ba_restart_flags.py --cmfgen-root ~/CMFGEN2023/cur_cmf`.
For isolated review copies, pass `--reader-source` and `--caller-source`; neither
option edits the installed tree. The physical ray-only trial is independent
of this patch because its BA/radiation caches were retired before launch.

The first full physical step continues with original scientific source and
VFRAC_FG=.1, native fresh BA and variable T. Its window matches the validated
physical transport probe (peakJratio1.0391134, native node24windowL1181.8981
versus formal1178.6916Lsun). Pre-window full/probe field differences are~5.2e-14
per-field peak-normalized. No source/cache-mode change has been introduced
mid-run. A follow-up watcher analyzes raw/applied corrections, charge/element
conservation and original outer block residuals, then probes the actual new
checkpoint before any further continuation is accepted. Session97225; main
model remains unchanged. This is still an investigation, not convergence.


### 2026-10-23 06:00UTC: genuine physical continuation and new-state verification

`physical5-ray01-full` completed successfully: native continuation5->6, full BA,
variable temperature, original moment grid/source and only VFRAC_FG=.1 changed
from the failing physical5 controls. Input5 preserved bitwise. All new
populations/T/Ne finite and positive; geometry unchanged. T changes at all90
depths (largest applied5%, outer1740.057->1743.184K). Maximum charge mismatch
1.0878e-6; maximum element-total relative change .001116 (~.1116%) from damping
and clipping, so exact elemental conservation is not claimed. Population
factors span .5..2, consistent with MAX_LIN=2.

The full step's radiation is for input5: minimum normalizedL .97424, no
negative depths or luminosity warnings. It matches the fast physical5 probe
to3.266e-12 per-field peak-normalized; depth24 integrated L differs1.25e-9Lsun.
A separate `physical6-ray01-transport` evaluates the actual new6 with fresh
caches: all152174frequencies complete, minimum normalizedL .97917, no negative
depths, no factor-two/25% luminosity warnings or Eddington caps. Depth24 L is
207652.6471Lsun versus stellar200000.046. Window native/formal node24 L is
1085.4382/1082.6014Lsun. These independent checks avoid interpreting input
radiation as a validation of output populations.

The raw corrections remain large: OVI terminal continuum at depth19 requests
8.1749e17%, with input population/Ne6.91e-27. Its seed merely doubles. The
local MAJOR scale is set instead by MgIV, population/Ne1.6245e-10, just above
the hardcoded1e-10 cutoff: requested fractional increase54485 gives minimum
scale1.8354e-5. Prediction reproduces every applied pop/T/Ne value exactly.
Do not attribute the lower raw OVI maximum solely to transport improvement;
doubling an extremely small seed also reduces its fractional correction.
Outer Schur rcond is3.95e-18/1.05e-17, but original block componentwise backward
errors are9.44e-13/6.42e-13. Condition column5 is column scaling, not residual.

Started `physical6-ray01-lambda` at06:00:17UTC, one normal native Lambda step
from actual6 in an isolated copy. Only temporary IN_ITS DO_LAM_IT= T differs
from that checkpoint's controls. Existing MAX_LAM=1e4, default LAM_SCALE_OPT=
LIMIT, MAJOR scaling, ray .1, full threads and fresh caches retained. Native
SOLVE_FOR_POPS itself schedules Lambda after MAXCH>LAM_VAL, so this tests its
intended bootstrap rather than artificial population edits. Temperature should
remain fixed during this step; verify actual output, charge/element drift and
radiation separately before accepting further continuation. Main model and
installed source/executables remain untouched.


### 2026-10-23 06:08UTC: Lambda bootstrap advances seeds but fails abundance gate

`physical6-ray01-lambda` succeeds natively6->7. T remains bitwise unchanged;
all populations finite positive, geometry unchanged. Factors1e-4..1e4. OVI
seed atdepth19 grows from1.3821e-26 to1.3798e-22 relativeNe; MgIV from3.2490e-10
to3.2437e-6. Raw >100% correction count16991 (previous full43268); largest raw
request2.8322e17%. This is useful seed progress, not convergence.

However Fe total changes by5.7528%, exceeding the predeclared1% saved-state
gate. Ne changes up to2.0644%; charge mismatch1.0785e-5, and N/O/Mg totals
also drift .26/.68/.29%. Follow-up watcher correctly stops before launching
new7 transport or further continuation. This branch is held, not promoted.
Native continuation directly reads POPS/SUP_TO_FULL; POP_SCALE applies to
new-model estimates and does not repair saved abundances at a normal restart.

Default LAM_SCALE_OPT=LIMIT in SOLVEBA_V13 replaces raw fractional decreases
above1.1 with.999 *before* MAJOR scaling, potentially breaking the solved
element/charge constraint. MAJOR also clips individual corrections. Thus
positivity and low charge error alone are insufficient to certify the update.
Started `physical6-ray01-lambda-no-limit` at06:08:02UTC, identical physical6,
ray.1, Lambda flag and MAX_LAM=1e4, changing only LAM_SCALE_OPT=NONE relative
to the held trial. Native MAJOR positivity/change limits remain active. This
comparison will establish whether the pre-scaling LIMIT operation causes
the excessive Fe drift; no change to installed source or main model.


### 2026-10-23 06:14UTC: LIMIT hypothesis rejected; test finite-population clipping

The native no-LIMIT comparison completes with essentially identical state:
Fe drift5.7528039459%, charge mismatch1.07845e-5, same .39711 minimum MAJOR
scale and1e-4..1e4 applied factor range. Removing LAM_SCALE_OPT=LIMIT does
**not** remedy the abundance deficit. This rejects the preceding tentative
LIMIT attribution for this model; it is not a confirmed source bug. Both
branches fail the same predeclared gate and neither is continued or promoted.

Independent abundance-target analysis uses exact negative mass fractions in
VADAT, MODEL atomic masses and saved element numbers relative H. Physical6
Fe mismatch is8.01e-5; default Lambda7 has a5.7547% Fe deficit (depth14).
Thus the Lambda deficit is not merely correction toward an already mismatched
input abundance. Script and per-model abundance-target-analysis.json retained.

Next controlled question: common MAJOR scaling ignores populations below
1e-10Ne, but individual factor1e4 caps still apply to them. A balanced transfer
from a populated ion into a tiny seed can therefore lose abundance when the
necessary increase is clipped separately. Prepare MAX_LAM=1e12 (finite
positive lower factor~1e-12), keeping default LIMIT and all other controls,
to test this mechanism. No hand-edited populations, abundance renormalization
or installed source changes. A new observational runtime also records raw
DIAG corrections and full-spectrum formal-ray R/J/H at five native depths;
this checks the still-large outer luminosity beyond the repaired UV window.


### 2026-10-23 09:36UTC: verified larger-cap bootstrap and actual new7 radiation

physical6-ray01-lambda-cap12 succeeded6->7. Raw DIAG recording and native
MAJOR replay reproduce every saved pop/T/Ne value exactly (max relative
prediction error0). No raw decrease exceeds1.1, confirming that LIMIT was
inactive. T and geometry unchanged, all variables positive/finite. OVI seed
atdepth19 grows1e12fold to1.3764e-14Ne; MgIV grows25180fold to8.1472e-6Ne.
Charge mismatch1.85395e-8; exact VADAT mass-fraction target comparison gives
max mismatch4.28555e-5 (O), Fe6.42272e-10. The~.388% change from the preceding
state is predominantly correction of its existing abundance errors, not a
new comparable error. Absolute targets must be checked alongside step changes.

Offline replay of the same solved native matrix gives:

| MAX_LAM | Minimum common scale | Maximum Fe target mismatch |
| ---: | ---: | ---: |
| 1e4 | .39711348 | .05754738 |
| 1e6 | .99954253 | .00512407 |
| 1e8 | .99954352 | 6.42e-10 |
| 1e10 | .99954353 | 6.42e-10 |
| 1e12 | .99954353 | 6.42e-10 |

At the1e4 peak(depth14), the common update before individual clips matches
the Fe target to6.66e-16. Increase clipping alone removes .05754737695 of
the target Fe total; decrease clipping contributes only8.05e-13. Thus the
abundance-loss mechanism is directly accounted for, not inferred from a
smaller convergence metric. Replaying1e4 against the independently executed
earlier1e4 step has maximum per-variable relative difference7.87e-4 in
sensitive populations; it is not a bitwise rerun. The actual1e12 prediction
is bitwise, and the Fe aggregate deficit agrees with the earlier run.

New observational moment-window-v3 retains scientific MOM/ray operations;
adds five-depth nodal formal R/J/H across allfrequencies and a raw correction
dump on the fresh DIAG branch. Native90point fixture output is bitwise
identical with recorder enabled/disabled. Transport-only-v3 retains the
validated no-Newton stop. Sources/build commands/hashes/fixture outputs saved.

For physical6, all152174frequency ray coverage is exact: native/formal outer
L3.4169078e6/3.1966109e6Lsun; absolute spectral flux mismatch7.2365%. Native
CIV1535..1565A contributes1.7574e6Lsun and SiIV1380..1415A .91956e6Lsun,
with no negative total opacity or clipping at the five sampled nodes in those
bands. These sampled counts do not rule out negative opacity at other depths
or individual lines. Formal rays also show the excess; no claim of complete
radiative equilibrium is made from the now-passing native safeguard.

physical7-ray01-lambda-cap12-transport completed with checkpoint unchanged,
min normalizedL .98056/max5.0526, no luminosity advisories/Eddington caps.
Native/formal outer L1.0096356e6/.9755032e6Lsun; absolute spectral flux mismatch
4.1379%. Narrow-window max symmetric J discrepancy8.9917%, still below the
predeclared10% gate. Both broad and narrow agreement are reported separately.
Thus the actual updated populations improve the previously excessive emergent
UV emission substantially, while outer luminosity is still far from equilibrium.

At09:36:07UTC started one additional native Lambda step in
physical7-ray01-lambda-cap12, source actual7, same refined rays, MAX_LAM1e12
and default LIMIT. Exactly one iteration/full threads/fresh caches. The main
model and installed source/executables remain unchanged. If saved-state and
abundance checks pass, next test is normal full temperature-varying continuation
from actual8; no additional Lambda-only result will be called convergence.


### 2026-10-23 09:43UTC: second bootstrap closes abundance constraints; full test live

physical7-ray01-lambda-cap12 completed7->8. T and geometry unchanged; all
variables finite positive. Maximum charge mismatch1.3323e-15; maximum
specified-abundance mismatch2.1094e-15. OVI atdepth19 now4.9296e-11Ne,
growth3586.54, while MgIV is8.3792e-6Ne (growth1.0285). Ne changes at most
.6974%. Largest applied population growth4.9875e6, below the tested1e12 cap.
Raw >100% count21310 and >10%107781 still show that this is not convergence.

Queued full test preparation initially failed on copying the already-archived
generic wrapper onto itself, before native execution. Corrected the archive
guard, independently checked absence of OUTGEN/result and unchanged prepared
checkpoint/VADAT/IN_ITS hashes, and launched the retained reviewed plan.
This is a wrapper bookkeeping correction, not another scientific intervention.

physical8-ray01-full-cap12 started09:42:52UTC, native PID48849 (confirmed live
09:43UTC), genuine continuation at iteration9. IN_ITS DO_LAM_IT=F, fresh BA,
variable T requested. Original90point moment grid, FG.1, MAX_LIN2/MAX_dT.05,
tested MAX_LAM1e12/default LIMIT retained. Exactly one iteration/full pool.
Current helper/output analyzer and raw/full-ray diagnostics are archived.

Watcher /private/tmp/bstar3502-follow-full8-probe9.py (PID48551) launches
physical9-ray01-post-full-transport only if actual saved output9 passes
finite-positive, geometry, charge, specified-abundance and nonzero-T-change
checks. The probe uses fresh caches and normal iteration flag, records all
frequencies and leaves the checkpoint unchanged. Native guard remains enabled.

Main SCRTEMP/T_IN-target hashes rechecked unchanged. No model promotion,
installed source change, commit, or claim of convergence. Current process,
case/control and next-check handoff is in ignored root-cause-v1/
AUTONOMOUS_STATUS.json. Compileall passes with its bytecode cache redirected
inside /private/tmp (default macOS cache location is outside writable roots).


### 2026-10-23 09:55UTC: historical provenance and direct original-checkpoint comparison

Read-only git inspection of exact historical commit
b5f07ccc930a4096eaae482184d4a7b8bac8da87 confirms:
the BA writer stores FIXED_T then COMPUTE_BA, while its reader consumes
COMPUTE_BA_RD then FIXED_T; DET_LTE_ED has the ignored-floor assignment;
MAJOR uses the same pop>1e-10Ne eligibility and individual increase/decrease
clipping. Reader flag lines appear in the2016 git snapshot. These mechanisms
are not introduced by a recent OS/compiler change. This source provenance
does not prove the original model's machine exercised a failing cache path.
The current init_population_estimates.f90 reconstruction module is a local
untracked source addition, absent in mid2023; the current LTE charge-loop
regression must not be attributed wholesale to that historical module.
Exact excerpts saved in historical-mechanism-provenance.json.

Important scope check: the stable physical5..8 recovery is the corrected
LTE-initialized branch. It does not yet prove that original physical68 can be
rescued without reinitialization. Prepared original68-recovery-baseline from
the exact before-max-lam-10-checkpoint-68 history. SCRTEMP hash/pointer68
unchanged; all physical parameters and original MAX_LIN10/default MAX_dT
retained. Only tested VFRAC_FG20000->.1 and MAX_LAM1e4->1e12 changed in this
isolated baseline. Native atomic links are the same valid current links used
for the other tests; no copied populations were regenerated.

Original68 abundances already match exact VADAT targets to1.9984e-15.
Native preflight passes with no errors (requires process visibility). Queued
original68-ray01-lambda-cap12 as a single native step, to run only after
current full8/actual9 checks terminate and a process-list check establishes
no concurrent CMFGEN executable. This comparison is necessary before claiming
the bootstrap generalizes directly to the old continuation. It is not a
second simultaneous model job.

Generated reproducible scientific figures/data with gnuplot, inspected PNG
visually and corrected legends so they do not hide the Fe deficit or C IV
peak. Figure shows Fe target error for input6, rejected default-cap7 and
accepted larger-cap7, alongside before/after C IV outer spectral luminosity.
No smoothing or arbitrary spectrum rescaling: native frequency weights are
converted to wavelength density and normalized by fixed Lstar200000.046Lsun.

[Bootstrap diagnostic figure (SVG)](../../models/test/.model_Bstar3502-diagnostics/root-cause-v1/figures/bstar3502-bootstrap-diagnostics.svg)
and [PNG](../../models/test/.model_Bstar3502-diagnostics/root-cause-v1/figures/bstar3502-bootstrap-diagnostics.png).
CSV, plotting script and provenance README are in the same figures directory.
This figure illustrates a tested intervention, not final convergence.


### 2026-10-23 10:00UTC: later-population accuracy check needs finer-ray comparison

Full8 native spectrum has passed2846A, so its1625..1640A recorder is complete
and no longer being written (single requested iteration). On actual input8,
the two-sided window comparison gives ratio .89220..1.07246 and maximum
symmetric J discrepancy11.39399%, exceeding the earlier10% provisional target.
This is not a recurrence of the factor20 collapsed transfer solution, but it
prevents certifying FG.1 as sufficiently resolved over the whole trajectory.
The ongoing full step is exploratory; its final native/state checks are still
pending and no main-model promotion is allowed from this partial observation.

CIV1535..1565A outer native luminosity in completed input8 spectrum is
19798.718Lsun, down from1.7574e6 for input6. SiIV1380..1415A is283094.635Lsun,
also reduced, but still excessive. These are completed spectral bands, not
a statement about total luminosity before remaining frequencies finish.

Queued physical9-ray005-post-full-transport after the already queued original68
native comparison. It will use the same validated actual9 populations/T/Ne
as physical9-ray01-post-full-transport, change only VFRAC_FG .1->.05, retain
normal iteration mode and fresh caches, and intentionally perform no Newton
update. Checkpoint invariance and full-frequency/narrow-window agreement
will be assessed. It runs only if actual9 passes saved-state validation and
a process-list check confirms no concurrent native CMFGEN. This is a numerical
resolution comparison, not another physical parameter adjustment.


### 2026-10-23 10:29UTC: full8->9 and actual9 probe pass; original68 test live

physical8-ray01-full-cap12 succeeds with actual9 saved, all populations/T/Ne
finite positive, geometry unchanged and T changed at all90depths (max5%).
Maximum charge mismatch2.76177e-11; specified abundance mismatch2.17911e-7.
Minimum MAJOR scale .045654 versus1.8354e-5 before bootstrap. Outer Schur
rcond1.0094e-16/1.3881e-16, original-block backward errors5.16e-14/3.51e-14.
These matrix measures describe the outer blocks only, not all90depths.

Raw maxima remain large: increase2.39917e11% is NV SL31 atdepth55, input
population/Ne7.0642e-79; strongest decrease9.2714e9% is NV SL26 atdepth56,
population/Ne2.2797e-79. Largest requested absolute changes are therefore
utterly different from those percentages. Native strict convergence remains
unmet; >100% count25398 and >10%125055 also show bulk variables still need
work. Do not declare convergence by discarding the N V percentages.

Input8 radiation min normalizedL .98113/max2.8817; native/formal outer
L575839.56/563506.47Lsun, absolute spectral flux mismatch3.03%. The separate
physical9-ray01-post-full-transport then completes all152174frequencies with
checkpoint unchanged, no native luminosity advisories or Eddington caps,
min .98385/max2.7460. Native/formal outer L548718.21/537111.33Lsun, absolute
spectral mismatch2.9378%; depth24 L208649.18/209869.97Lsun. Actual9 C IV band
L18419.19 and Si IV265657.93Lsun. These are positive progress but the wind
still has excess luminosity and no final equilibrium is established.

Actual9 narrow-window maximum symmetric discrepancy14.9614%, above the
earlier10% provisional target. The queued same-checkpoint FG.05 comparison
remains required; a native safeguard pass does not certify this accuracy.

The original68 comparison starts sequentially after the actual9 probe,
using exact archived physical68, no LTE reseeding, and only ray/cap controls
changed. Native PID58565 confirmed live; case original68-ray01-lambda-cap12.
Its runtime trace-depth-v1 adds observations only: N V equations560..601 plus
Ne/T rows across every depth/band, and Schur condition estimates at every
depth for future TRI runs. Original scientific equations/operations retained.
Binary row/value/order and disabled-recorder tests pass at2233x90 dimensions;
its original68 preflight passes. This addresses the new deep N V requests
without relying only on outer-depth matrix diagnostics. No installed changes.

An offline formulation diagnostic on existing Lambda7->8 outer blocks compares
Ne-variable increments, fixed-Ne increments and direct fixed-Ne steady-state
populations. Fixed-Ne increments remove the two negative unlimited tiny
requests at those depths, but the direct-population formulation still has
2/4 negative tiny populations and componentwise residual1 in weak rows.
It is not a verified solver remedy and has not been installed or used to
update any checkpoint. It is retained only for discriminating causes on the
forthcoming original68 matrices; no convergence tolerance or population floor
was changed. Earlier evidence of poor conditioning cannot be dismissed merely
by changing variable normalization or holding trace stages fixed.

Main SCRTEMP/T_IN hashes rechecked unchanged. Next native job remains the
conditional same-state9 finer-ray probe, after original68 native completion.


### 2026-10-23 10:36UTC: full-step damping driver and scratch retirement

Exact raw-solution replay of full8->9 again matches every saved variable
(max relative prediction error0). Its minimum MAJOR scale .0456544 is set
by FeIII SL1 atdepth1: input3.9381e-5cm^-3 =6.1856e-9Ne and requested
fractional increase21.9037. Similar FeIII ground-state requests set the next
outer-depth scales. The largest N V percentage is not the damping driver.

This is a material improvement from the prior MgIV-controlled~1e-5 scale,
but diagnostic MAX_LIN2 still only doubles a small FeIII seed while damping
the common update. The former small-step controls delayed the underresolved
transport collapse rather than solved it. After the original68 comparison
and FG.05 accuracy result, consider a single full step restoring the original
MAX_LIN10/default MAX_dT.2 if appropriate, then independently verify its saved
radiation state. No such next full run has been prepared or launched: choose
the branch and controls from the pending evidence, not a blind iteration queue.

Retired only BCSCRATCH0001..0090 generated factorization files from completed
isolated physical5-ray01-full and physical8-ray01-full-cap12. Each run already
has complete science/state analysis and a successful native result. Idle-model
mutation guards were held; strict filenames/regular files only. Freed
14,373,417,600bytes (~13.39GiB), returning disk free space to43GiB. Checkpoints,
all captured original matrix blocks/raw solution, spectra, logs and analyses
are retained; SCRTEMP/POINT1/POINT2/raw-solution hashes verified unchanged.
Per-case cache-retirement journals list exact files/sizes and retained hashes.
These are rebuildable LU scratch, not model backups or scientific evidence.


### 2026-10-23 11:00UTC: original68 and cancellation-free Lambda Jacobian candidate

The original68 ray/cap comparison completed natively at69. All saved values
finite positive, unchanged T/geometry; charge mismatch1.33e-15, specified
abundance mismatch2.89e-15. Ne changes at most .006568%. Raw maximum increase
remains5.7566e27% (NV SL10, original input4.35e-120Ne), >100% count47 and
>10%137. Increased cap advances positive seeds by1e12, but NV SL31 and other
variables still receive negative unlimited targets and are reduced by LIMIT.
Thus the fresh-LTE recovery does not yet prove direct original recovery.

All-depth captured original NV rows have max componentwise backward error
1.7152e-15; Ne5.4681e-13; T0. This rules out an inadequately satisfied captured
Lambda system as the primary explanation here; it does not prove forward
accuracy or correct derivative assembly. Dividing the population column scale
out of NV SL22 diagonal gives log10 magnitude89.97344 atdepth1; depth2 diagonal
is positive with log10 magnitude62.66858. Most deeper NV diagonal magnitudes
are ordinary~1e11. These are derivatives, not automatically physical single
transition rates; the exceptional signs/magnitudes require assembly attribution.

Offline holding Ne fixed leaves the same12/5 negative unlimited NV populations
atdepths1/2. The direct absolute-population steady-state experiment is worse,
with96/44 negative variables and weak-row backward error~1. It is rejected
as a remedy for this checkpoint; no native FIX_NE run or edited populations
were used. A normalization/trace suppression shortcut is not established.

Located a specific cancellation in UPDATE_BA_FOR_LINE's Lambda/weak-line
explicit upper-population derivative. CMFGEN_SUB accumulates, at fixed
per-line opacity/emissivity,
ZNET = sum(w*(1-J*chiL/etaL)), JBAR=sum(w*J), QW=sum(w).
Therefore ZNET + JBAR*chiL/etaL = QW exactly. The old derivative explicitly
adds those large opposite quantities; when upper populations vanish it loses
the finite spontaneous term and can produce enormous positive or negative
diagonals. The same file already uses direct QW/JBAR expressions for heating.

Isolated candidate replaces only
(ZNET_SIM+VC+STIM_FAC*VB) with (LINE_QW_SUM+STIM_FAC*VB).
No rate/RHS, population, elemental abundance, opacity, radiation, grid,
damping or convergence definition is changed. Exact integrated profile
normalization is retained, including incomplete profiles. Installed source
and executable remain untouched. Historical b5f07ccc confirms the same old
expression; rollback would not remove it.

Actual native UPDATE_BA_FOR_LINE fixture (only TUNE profiling stubbed), five
upper populations1e-4..1e-128 plus inverted-opacity case, two depths, profile
weight sum.91: original upper derivative error reaches1.5022e98 relative;
candidate matches all10 cases. Public independent oracle uses350-digit
central differences of the original source-function net-rate expression,
rather than comparing two copies of the candidate formula. Lower derivatives
and source-column number conservation pass. Initial fixture development caught
and corrected an argument-count/formatting issue before any model launch;
explicit native interface now checks the fixture call.

Artifacts:
- [Experimental cancellation-free patch](patches/bstar3502-stable-lambda-line-experimental.patch).
- [Standalone native regression](cmfgen-review-tests/check_lambda_line_jacobian.py).
- [Fixture](cmfgen-review-tests/fixtures/lambda_line_jacobian.f90).

Default test on installed unpatched source correctly fails; pass --source
pointing at the candidate to test it. Native reports retained under ignored
root-cause-v1/lambda-line-public-{original,patched}-report.json. git apply
--check passes against the current installed source without modifying it.

Candidate runtime lambda-line-stable-v1 retains trace-depth-v1 observations
and links only the changed UPDATE_BA_FOR_LINE object before libsubs. Queued
one paired original68-ray01-lambda-stable-line step after the running actual9
FG.05 probe. Same exact physical68 input, FG.1/MAX_LAM1e12 and all other
controls as the completed unpatched comparison. The next required evidence
is unchanged input radiation/RHS, removal of suspect NV diagonal terms, and
actual saved-state/raw-correction behaviour. Whole-model validation is pending.


### 2026-10-23 11:40UTC: actual original68 source attribution and bounded continuation

Paired source test `original68-ray01-lambda-stable-line` versus
`original68-ray01-lambda-cap12` retains exact prepared checkpoint hash
`d23e05cee08f318244ecac749a46f0bda05c6c5841a7f9020bcc4f75448bd038`, VADAT,
IN_ITS, FG.1 and MAX_LAM1e12. Only the upper line derivative expression changes.
Frequency weights are identical; maximum radiation difference1.2584e-11 relative
to each field's peak, integrated luminosity differences <=5.85e-9Lsun. Captured
N V rows still satisfy the solved equations to~2e-15 componentwise backward
error. The old matrix was accurately solved but incorrectly assembled.

The maximum N V unscaled coefficient log10 falls89.9734->11.3556. SL22 outer
diagonals become negative at both first depths, log10 magnitude9.0083 instead
of -1e89.97/+1e62.67. Positive excited N V diagonals17->0; all unlimited negative
population targets31->0 (including17 N V). This isolates an actual model defect,
not merely a synthetic fixture failure. Same expression exists in mid2023.

The corrected raw request initially grows to8.0698e109% because O V SL26 starts
at1.114e-134Ne and its genuine target is~9e-27Ne. The native MAX_CHNG1e100 guard
stops this first run after writing a capped checkpoint69. This run is retained
as `invalid_output`, explicitly not relabelled successful. Independent validation
of that provisional state finds finite positive populations, unchanged T/geometry,
charge error1.33e-15, abundance error1.22e-14. No main-model promotion occurred.

Continuation `original69-stable-line-continuation` from that explicitly checked
state completes normally at70, with MAX_CHNG1e100 unchanged. Largest raw increase
falls to8.0762e97%, the expected twelve orders as the cap raises tiny seeds.
Charge error9.99e-16, abundance error1.21e-14. All90 temperatures remain fixed.
This is bootstrap progress, not convergence.

New combined isolated runtime `lambda-line-ba-stable-v1` links the same corrected
line derivative plus the previously proven READ_BA_DATA_V3 header-order, failed-read
transactionality and final-record EOF fixes, and forwards the initial fresh-BA
request through CMFGEN_SUB. Native BA regression passes all flag round trips,
missing/mismatched/truncated cache cases and fresh-cache bypass. Installed source
and executable are untouched. Build commands/hashes and regression JSON retained.

Bounded batch `original70-stable-line-normal-batch10` launched11:33UTC, up to10
native iterations and five-hour timeout, full configured thread pool. Original
MAX_LIN10/default MAX_dT.2, EPS_TERM.02%, MAX_CHNG1e100, N_FIX_BA2, COMP_BA=T,
FIX_BA10 and automatic Lambda/T flags retained; only the tested FG.1/MAX_LAM1e12
bootstrap controls differ from original model inputs. Native mode switches are
left to CMFGEN. A callback independently checks each published checkpoint for
positive finite populations, unchanged geometry, charge and elemental abundance
errors <1%, stopping this isolated job if a bad state is confirmed. Closed
observational matrix dumps are archived per checkpoint to prevent stale files
across native Lambda/TRI switches. Scientific inputs/caches are not moved.

First published checkpoint71 passes, charge1.44e-15, abundance2.44e-15, T unchanged.
The callback's initial `native_solver_record` metadata can point at the next
in-progress OUTGEN header; this field must be reconciled by global iteration at
batch end. Independent binary temperature checks and conservation are unaffected.
Do not interpret an unfinished header's default false flags as a full-T solve.
Actual completed solver records and final fresh convergence evidence remain pending.

Separate same-state actual9 FG.1->.05 transport comparison is complete: largest
integrated-flux change6.012e-6 relative, spectral absolute L1 change <=9.50e-5,
window maximum symmetric J discrepancy14.9614->14.8538%. Thus halving ray spacing
does not explain or cure that remaining local difference. Two spacings do not
establish an asymptotic accuracy bound; this fresh-LTE branch is not the primary
original68 source-repair branch.


Matched actual68 diagonal-versus-depth figure is retained under ignored diagnostics
as `root-cause-v1/figures/bstar3502-line-cancellation.{svg,png}`, with CSV, generator
and gnuplot source. It compares the same N V SL22 population-unscaled coefficient
at all90 depths, not a different physical model or altered convergence threshold.
Native regression repeated with an explicit caller interface: corrected source
passes10/10; original fails with maximum relative upper-derivative error1.5022e98.
Reports `lambda-line-interface-{original,patched}-report.json` retain the exact
source and updated fixture hashes. Combined BA regression report archived too.

Read-only `bstar3502-analyze-native-batch.py` independently reconciles audit rows
with the completed OUTGEN global iteration and emits JSON/CSV. At71 it confirms
Lambda=true, fixed-T=true, fresh BA=true, raw maximum8.07776e85%, zero negative
unlimited targets. An unfinished next header is explicitly excluded. This corrects
the observational metadata association without touching native model files.


At11:43UTC checkpoint72 completes in Lambda/fixed-T mode with fresh BA. Maximum
raw request8.07791e73%, maximum requested decrease3.47%, zero negative unlimited
targets. Independent saved-state charge1.33e-15 and abundance2.89e-15 pass; T
unchanged. The batch is still active at73. Historical blame of the mid2023 source
attributes the current expression to b661735f (2012-01-10), but its parent already
contains ZNET+VC with a differently factored stimulated term. The cancellation
predates that refactoring; this is not evidence that the 2012 commit introduced it.


### 2026-10-23 11:50UTC: third normal bootstrap checkpoint and verification tooling

Checkpoint73 completes normally inside the ongoing native batch. Exact captured
matrix input populations are bitwise equal to published checkpoint72. Raw request
8.077742e61%, maximum requested decrease2.86%, zero negative unlimited targets.
Independent saved-state charge9.99e-16, abundance2.22e-15, all finite positive,
unchanged geometry and all90 temperatures. Three consecutive normal steps now
advance the corrected tiny seeds by the expected per-step cap; no full-T or
convergence claim is made. Native job74132 is continuing at74.

Prepared reusable ignored diagnostic runner `bstar3502-run-native-batch.py` accepts
--source, --case, --iterations (1..20), optional --fresh-ba. It refuses existing
case paths, requires a natively successful source and independently validated
binary state, retains all source controls unless fresh verification is selected,
and uses the same combined isolated runtime and per-checkpoint gates. Fresh BA
sets N_FIX_BA0/FIX_BA0/COMP_BA=T and requests DO_LAM_IT=F; convergence EPS and
population floors remain unchanged. It has passed CLI/import/compile checks;
no additional model job has been launched with it. Choose the next run only
from the completed current batch evidence.

Batch analysis now checks every raw-solution dump against the exact2233x90
captured matrix input and prior published state, and explicitly maps successful
Ng counter increments. Missing raw dumps remain explicit. This improves evidence
provenance without changing native physics or the active run. The line source
repair covers Lambda/all weak lines; full strong-line linearization remains
unchanged and must be evaluated by the forthcoming full-T solves.


### 2026-10-23 12:00UTC: native automatic mode release differs from raw maximum

Checkpoint74: rawmax8.07756e49%, >100%14, >10%15, >1%79; decrease2.42%,
charge1.22e-15, abundance2.55e-15, no negative unlimited targets, unchanged T.
Checkpoint75: rawmax8.07739e37%, >100%6, >10%6, >1%63; decrease2.09%,
charge9.99e-16, abundance2.11e-15, no negative unlimited targets, unchanged T.
All saved states positive; geometry unchanged. At75 native outer luminosity
199486.742 vs200000.046Lsun, deficit0.25665%. This original-model branch stays
close to specified luminosity, unlike the earlier fresh-LTE recovery branch.

Native75 nevertheless returns MAXCH=1.7703829649%, not the actual8e37% maximum.
Source SOLVEBA_V13 (NV=10, DO_LEVEL_CHK) substitutes the tenth-largest increase
and transformed tenth-largest decrease when those are below10%. The comment
dates this behaviour to2010. With only6 large requests left this condition
activates, so native DO_LAM_AUTO sets DO_LAM_IT=F. Iteration76 is the pending
full-solve test. This is unchanged native policy, not a tolerance relaxation
introduced by this investigation. Do not interpret its switching measure as
all-variable convergence; our independent checks retain raw extrema/counts.

Closed raw dumps are now independently counted at100%,10%,1%,.1%,.01%,.001%,
.0001%; at74 they exactly match CORRECTION_SUM. Counts >100% at71..75:
63,47,28,14,6. Counts >1%:353,150,104,79,63. This is broader improvement than
merely capping the largest percentage. Still~76946 variables exceed.01% at75;
strict .02% convergence remains unproved.

A separate two-panel CSV/SVG/PNG trajectory is retained in the active case's
figures directory. It explicitly separates the actual raw maximum from the
native trimmed switching measure and displays correction counts on a linear
axis (including zero). Generator `bstar3502-plot-native-batch.py` is retained
at root-cause-v1. Visual inspection confirms labels/legends and the discrepancy
at75. Short review note `doc/developer/cmfgen-line-jacobian-cancellation.md`
contains the reproducible source defect and matched proof separately from this
long chronology; whole-model convergence is explicitly still pending.

Next action: observe76 full mode, fresh/reused BA and actual binary temperature
change, matrices and state gates. If the6 remaining tiny seeds are slowed by
MAX_LIN10 after early native mode release, evaluate an explicit further Lambda
bootstrap with DO_LAM_AUTO=F before returning to full mode. This is a conditional
next decision, not a launched job or reason to change native convergence logic.


At12:04:59UTC, native76 is confirmed live (PID74132) and the iteration budget
is reduced using CMFGEN's documented live IN_ITS edit support: NUM_ITS10->7.
The five Lambda iterations are complete; two full solves will be retained before
choosing a further seed bootstrap. This avoids committing to five costly full
solves while four trace seeds still require~25/22/16/10 orders of growth at the
input to76. Source reads the edited limit after76, sets the remaining count to1,
and writes a normal final-output iteration next (subject to native Ng/cycling).
Native76 cannot be labelled successful until it actually completes.

Only the iteration budget changes. Exact pre/post contents and hashes, reason,
and UTC timestamp are in `live-iteration-budget-adjustment.json`. The original
prepared experiment/plan is preserved; case name remains batch10. The wrapper's
initial assess requested10 can produce quality wording for the original budget;
reassess final quality with effective7 if necessary. New batch-analysis JSON
records both planned and effective budgets rather than hiding the live edit.

All six >100% requests at75 are N V/O V trace levels atdepths1/2. The four
largest input fractions/Ne are1.1e-62,6.6e-60,1.3e-52,4.3e-48; their unlimited
targets/Ne are9.0e-27,1.7e-27,3.2e-26,2.3e-27. Detailed retained raw labels and
values are in `matrix-snapshots/record-075/largest-raw-targets.json`. No population
is edited to those targets; they remain observations of the native correction.


### 2026-10-23 12:24UTC: full strong-line defect reproduced in a native kernel limit

While unchanged native76 computes, a new fixed-J test calls the actual line
routine in Lambda, weak/full and strong/full modes. The existing Lambda/weak
repair passes; unchanged strong branch upper-derivative relative error reaches
2.334e98. Thus the analogous source-function cancellation also exists in full
strong-line assembly; its contribution on this active physical checkpoint is
not yet attributed. Do not describe the active runtime as containing the fix.

Private `line-strong-stable-candidate.f` excludes only explicit emissivity
normalization derivatives from accumulated dZ and cancels them analytically
with ZNET in final population/thermal assembly. Opacity and full dJ responses
remain. Native ZNET_VAR_LIM bypass is preserved; shared lower/upper superlevel
slots retain their old path. Initial distinct-level candidate exposed the need
for this shared-slot guard during review; it was added before any model launch.

Expanded public native fixture spans4depths/3bands, prescribed nonzero local
and neighboring-depth radiation responses, Ne coupling and optional temperature
ratios. 350-digit differences of the original physical source-function net rate
and eta*ZNET heating verify2,750 entries; largest rate/heat error1.11e-15.
Skipped full linearization250entries and strong shared-superlevel1,000entries
remain bitwise identical to installed-original control. All source column
particle-number balances exact. Original max rate/heat errors2.33e98/2.83e98.

New reviewable artifacts: check_line_jacobian_branches.py, two native fixtures,
and bstar3502-stable-strong-line-experimental.patch. The additional patch checks
cleanly against installed source read-only; all changes remain isolated or
untracked review artifacts. Public reports/commands/hashes archived under
line-branches-public-{original,candidate}-report.json. Two continuum routines
and profiling are explicitly stubbed in this line-only fixture; this is not a
transport/convergence test. Focused source review note documents scope/commands.

Native76 observational radiation records151960/152174 at12:23:54UTC, POINT75
unchanged. Same native PID74132 remains the only model job. Need actual full
checkpoint/matrix evidence before choosing a matched strong-line comparison.


### 2026-10-23 14:42UTC: batch complete; first full step remains problematic

Batch ended12:31:59UTC. Native pass succeeded with return0 and normal final
outputs. Aggregate result remains runner_error because the planned live NUM_ITS
edit10->7 conflicts with the runner's restoration of its temporary override:
`IN_ITS: [NUM_ITS] changed during execution; preserving external edit`.
This was our documented budget change, not a native failure or failed scientific
state gate. Do not rewrite either native or aggregate status. No final native
convergence evidence was emitted because the wrapper correctly withheld success.

Independent checkpoint76: full/nonLambda, freshBA, Tchangedall90/max20%; geometry
unchanged, positive populations, charge1.1358e-11, abundance4.0249e-8. However raw
maximum3.02018e22%, >100%8251, >10%47043;5,140 unlimited targets negative, largest
negative fraction6.82358e-4Ne. Applied damping protects the saved populations.
This is not a healthy near-converged full update. Captured N V SL22 outer
diagonals now ordinary log10~9.0083, all90 depths have zero positive excited
N V diagonals. The original Lambda N V anomaly is removed, but that does not
explain or cure the full-step problem by itself.

Native77 automatically returns to Lambda (not a second full solve), freshBA,
Tfixed; grey solution is reported but saved binary temperature unchanged from76.
Charge/abundance~1e-15, allfinitepositive. Raw maximum9.6973e24%, >100%17553,
>10%31783. No negative unlimited targets in that Lambda solve. Neither76 nor77
is promoted to the main model. The initial expectation of two full steps was
superseded by the actual native internal mode cycle.

Built isolated full-line-ba-stable-v1: exact combined Lambda/weak+BA runtime,
only UPDATE_BA_FOR_LINE object replaced with the publicly tested guarded
strong-line candidate. Build commands/source/executable hashes retained. No
installed source/executable changes. Public extended regression passes on exact
candidate source and fails on installed original; read-only patch check passes.

Prepared original75-paired-full-baseline by selecting exact earlier record75
from completed batch, before full76/77. Entire checkpoint copied bitwise; only
POINT1/POINT2 select75. Geometry/positive/charge/abundance independent gatepasses.
Original VADAT hashd11a4551... matches prepared batch control exactly; full mode,
NUM_ITS1 requested. Source metadata preserves nativepasssuccess and aggregate
control-conflict distinction. This is a diagnostic input baseline, not a new
successful run or main-model promotion.

Queued sequential one-step full pair: original75-full-fresh-control using
lambda-line-ba-stable-v1, then original75-full-fresh-strong-stable using
full-line-ba-stable-v1. Both clone identical baseline and recompute all radiation
and BA; same original physics/controls, only line-Jacobian source differs.
Fresh control is necessary: in-process batch76 inherited previous radiation and
two-photon cache state, so it is not a strictly source-only comparison against
a fresh-process candidate. Nativecontrol started14:41:12UTC; controller17525,
native17528, execsession81741. Secondleg requires firstnativeSUCC and accepted
state/postchecks. Allscript/source/nativeinputs retained; full pool sequential,
OPENBLASthreads1. Need compare exact inputs/radiation/RHS before interpreting
matrix/temperature differences. No other model jobs launched or queued.


At14:46UTC retired only90 rebuildable BCSCRATCH factorization files from the
completed mixed batch:7,186,708,800bytes. Acquired its idle model mutationguard
with existing diagnostic psutil dependencies; first attempts lacking that path
failed closed before any mutation. Current control run is in another case.
All checkpoint/rawsolution hashes, including archived full76 rawsolution,
verified unchanged. Every captured matrix/radiation/log/analysis retained;
per-case retirement journal lists exact files. Disk headroom19->26GiB.

Link provenance strengthened before interpreting the pair: relinked original
combined-control command with current object/library dependencies. A preliminary
different output basename changes Mach-O UUID/ad-hoc signature (all10 mapped
code/data sections and addresses identical). Repeating with the original
cmfgen_dev.exe basename in a separate folder reproduces the control binary
byte-for-byte, SHA256256d8a3f50c9f2e074e5427c5e22ff39c18bfa9f54d68894a8a364ebd4687a1e.
Thus no background library rebuild confounds the candidate link. Exact commands,
section hashes, both comparisons retained in paired-control-relink-proof.json.
No installed executable or running control executable was overwritten.


### 2026-10-23 14:55UTC: full-step localization and residual evidence

Refined binary/raw temperature analysis of completed batch75->76: raw maxT34.88%,
applied20% cap reached only atouterdepths1..4 (input1669.9,1776.5,2211.9,3962.2K).
Depth5 changes14.8%, depth6 +7.47%. Arounddepths48..50 T~9800K cools5.3..5.4%.
Of90depths,32 change>1%,9>5%,5>10%. All90 change by some nonzero amount, but
not all reachthecap. This is a bounded nonlinear Newton response; one such step
and negative unlimited trace targets do not alone prove a growing instability.
`full76-temperature-profile-analysis.json` retains all90 depths and raw/applied
T/Ne changes. Saved positive/conservation gates still pass, strict convergence
remains unproved.

Captured original full rows at76 satisfy all neighboring-block equations:
max componentwise backwarderror N V1.3620e-14, Ne3.9991e-14, T4.2312e-15.
Largest unscaled N V coefficient log10 11.35555 (ordinary scale, no original
1e90 anomaly). This argues against an inaccurate linear solve in the captured
rows; does not prove forward accuracy or correct Jacobian/physical equilibrium.
The extended trace helper accepts --matrix-dir and a narrowly explicit
--allow-control-restore-conflict only with the exact documented NUM_ITS conflict,
nativepasssuccess/return0 and budget journal. Aggregate status remains visible;
no fake successful result file was created. Residual JSON is in record-076.

Prepared read-only matched-pair analyzer bstar3502-compare-full75-pair.py:
requires bothnativeSUCC andacceptedstate; exact initial SCRTEMP/VADAT/IN_ITS
hashes, sharedsource, identicalfrequencyweights andcapturedinputpopulations.
It reports perfield peak-normalizedradiation andluminosity differences, all
captured N V/Ne/T RHS differences andmatrix changes, then rawnegativecounts,
allvariablethresholdcounts andactualTupdates. It is compiled but not yet run;
bothmodelresultsare required. Radiation/RHS equivalence must be assessed before
attributing matrix/population changes to source repair.

Freshcontrol remainslive, POINT75. Frequencyprogress16244 at14:51 to21484
at14:54 proves continuedwork. Cold formalray/EDD recomputation is slower than
the inprocess batch76; native is bounded7200sec. Controller17525/session81741
will launchcandidate only aftercontrol completes with acceptedstate andchecks.
Do notduplicate/restartmerelybecauseitsoutputpauseislong. Diskheadroom26GiB
following the documented completed-batch LU scratch retirement.


### 2026-10-23 15:05UTC: optional line-heating paths checked while pair runs

Extended standalone reproducer adds --variant cooling and --variant mixed-new-line.
Cooling scales low-density heat by2 and resets scaling above densitylimit;
mixed method sets INDX_BA_METH3 on4depths (old at1/2, new at3/4). Eachcandidate
variant passes2,750 finite-difference rate/heat entries with <=1.11e-15 error,
250skipped and1,000strong-shared entries bitwise original. For mixednewdepths,
continuumBA_UPDATE is deliberately stubbed, so independent heat oracle checks
only directline heat there; fullSEradiationresponses remain nonzero/tested.
This doesnot certify the complete continuum/transfer heating solver.

Re-ran default variant after optional oracle support: candidatepasses and
installedoriginalfails2.33e98/2.83e98 asbefore. Reports archived as
line-branches-public-{baseline-v2,cooling,mixed,original-v2}-report.json.
The running matchedmodel executable/source/control files remain unchanged.
Control has26462->27772->32226->34584 frequencies completed over observation
interval, POINT75, nativeprocess17528stillactive. No candidate modelresult yet;
controller will launch it sequentially only after required controlchecks.


### 2026-10-23 16:10UTC: fresh control complete, candidate active, evidence preserved

Fresh control original75-full-fresh-control finishes normally at15:49:43UTC,
all one-step postanalyses/state gateaccepted. Charge1.1358e-11, abundance4.02485e-8,
Tchangedall90 with20%caponlyouter4, counts>100%8251/>10%47043. Rawmax3.0201789e22%.
Native luminosity199482.727Lsun vsinprocessbatch76 199482.711, relative8e-8 of
stellarL. These closely reproduce the earlier full behaviour with fresh radiation;
this doesnot certify every spectral/RHS component as identical. Strong candidate
startssequentially15:49:48UTC, native33778/wrapper33770/controller17525. Main unchanged.

Fulloutermatrix diagonal scan of control (excitedrows only, excludesground/
conservation/Ne/T): no positiveexcited diagonals atdepth1/2. Largestpopulation-
unscaleddiagonal atdepth1 is O V SL26 eq822, log10magnitude18.66386, input1.114e-50Ne;
otherlargest~1e11. Atdepth2 maxlog10 10.919. These are coupledJacobcoefficients,
not automaticallyindividualatomicrates. This identifies a specific coefficient
to compare with the candidate; attribution still requiresmatched source result.

Read-only postprocessing watcher (session35014) waits forbothnativeSUCC and
acceptedstategates, thenruns bstar3502-compare-full75-pair.py. It starts no models,
neverrelabelsresults, andjournals failures forinspection instead ofrestarting.
Controller session81741 remainsresponsible onlyfor the twoauthorizednativelegs.

Updated scientific figures showactualraw vsnative switchingmeasure andactualT
profile/change vsdepth. full76-temperature.{svg,png} plusCSV/generator retained
in completedbatch figures. Upper logarithmicT ticks werecleaned aftervisualQA;
plots nowmake the fourcoldoutercappeddepths and~5%coolingnear48..50 explicit.

Storage headroom was7.7GiB aftercontrol completed. RetiredonlycontrolBCCLU
7,186,708,800bytes andDSCRATCHback-substitutionfactors fromfourcompletedcases:
physical5-ray01-full, physical8-ray01-full-cap12, mixedbatch70 andfreshcontrol75,
each89files/3,550,238,480bytes. Source CMF_BLKBAND_V3 explicitlystores alpha[k]
=C_k^-1D_k inthese D files forbacksubstitution; they arerebuildable, notcheckpoints.
Everycase wasidle underguard, nativepasscompleted, physicalanalysisretained;
checkpoint/POINT/rawsolutionhashes verifiedunchanged. Per-caseretirementjournals
list exactfiles. No activecandidate cache was touched.

Preserved bothidlefullBAMATcaches losslessly (original8,350,538,888byteseach).
Control gzip archive5,403,909,027bytes, batch zstd archive5,219,038,519bytes.
Eachentiredecompressedstream SHA256 andbytecount matchedbeforeoriginalcache
removal; checkpoint/rawsnapshot hashes unchanged. Slowgzip maintenance completed
control, thenwasstopped onbatchpartial668,171,295bytes with originalbatchcache
stillintact. OnlythemaintenancePythonprocess35053 wasterminated; modelunaffected.
Theincompletegzwasdiscarded underidlelock andbatcharchivedvia zstd -1 --long=27 -T1.
Allarchive/attemptjournals andscripts retained. Fullscientificevidence remains;
BAMAT canberestored exactly ifneeded, futureexperiments compute freshBA.
Diskfree now27GiB; monitorwhilecandidateallocates its~19GiB peakworkspace.


### 2026-10-23 16:24UTC: comparison widened to the O V anomaly

Expanded matched-pair analyzer now includes all2,233rows in the five valid
full outer blocks (depth1/2, validbands), inaddition to268selected N V/Ne/T
traceblocks acrossall90depths. It reports full RHS/matrix differences and
all-excited-row diagonal changes, explicitly retaining the preidentified
O V SL26 eq822 at bothouterdepths. Thus actual strong-line attribution will
not rely onlyon N V rows, where the earlierLambda fix already removed anomalies.

A real-control selfcomparison verifies everycaptured inputpopulation equals
checkpoint75 exactly, allheaders/frequencyweights align, andallradiation,
RHS andmatrix differences arezero. It covers268trace and5fullouterblocks.
Report matched-full75-comparison-parser-selfcheck.json explicitly labels this
as a parser/provenance check, not proof of the candidate's benefit. Candidate
native stillactive; watcherwillinvokeupdated analyzer onlyafterbothaccepted.

The completed coldcontrol raw summary independently confirms5,140negative
unlimited targets, maxnegative6.82385e-4Ne andrawmax3.0201789e22%; rawTmax34.883728%.
These agree closely with the earlier inprocess fullstep, strengthening the
baseline before changing the strong-line assembly. No source benefit is yetclaimed.


### 2026-10-23 18:02UTC: strong-line attribution complete; fixed-T recovery resumed

Matched candidate completes normally16:44:09UTC; allstate/one-step postchecks
accepted. Whole pair comparison completes16:44:35UTC. ExactpreparedSCRTEMP/
VADAT/IN_ITS hashes andcaptured inputpops match, frequencyweights identical.
Full inputradiation peak-normalized difference1.22816e-11; integratedLsun
changes<=9.41e-9. Outer O V SL26 RHS changes2.15e-15relative. Itsunscaled
Jacobian diagonal log10magnitude18.66386->10.690786, withdepth2unchanged10.690784.
This attributes the secondcancellation defect to anactual full modelsolve,
beyond the earlier Lambda/weak N V proof. It isnot evidence of fullconvergence.

Fulltemperature rawmax34.883728->34.883697%, appliedmax20% atfourcoldouterdepths;
negative unlimitedpopulationtargets5,140unchanged. Charge1.13578e-11 andabundance
4.02485e-8 pass; allpopulationspositive, geometryunchanged. Rawmaximumgrows
3.02018e22->1.01020e26% because the fixedO V derivative requests a physical
increaseof anextremelysmallseed; normalfullMAX_LIN10 bounds theappliedgrowth.
The repairedcoefficient doesnot remove thebulk nonlinear thermal response.
No populationfloor, convergence threshold orphysical modelparameterwas changed.

A priorattempt toretirecompletedcandidatefactors wasnotexecuted becauseautomatic
approvalreview hit itsusagelimit. Afteruserresumedgoal, read-onlyprocesschecks
confirmedbothpairedjobsended; reviewserviceworkedagain. RetiredcandidateBC/D
rebuildablefactors underidlelocks, retainedcheckpoint/rawhashes unchanged.
CandidatefullBAMAT isbeingarchivedlosslessly withzstd andfullSHA256roundtrip;
newLambda runis in adifferentcopy. Noapprovalbypass orinstalled/main edits.

Launched original76-guarded-line-lambda-bootstrap3 at17:58:39UTC fromaccepted
correctedfull76, runtimefull-line-ba-stable-v1, up to3nativeiterations, five-hour
bound/fullinheritedOpenMPpool. ExplicitDO_LAM_IT=T, DO_LAM_AUTO=F avoids the
native10th-largest/MAXCH early-releasebehaviour. Otherphysical/numericalcontrols,
includingEPS_TERM.02%, MAX_LAM1e12 andoriginalMAX_LIN10/defaultMAX_dT.2 remain.
Independentcheckpointcallback additionallyrequiresexactlyunchangedtemperature,
alongwithfinitepositivepops, unchangedgeometry, charge/elementerrors<1%.
Wrapper62339/native62347, session5164. Noothermodeljoborfullfollowupisqueued.

Next: inspectfixed-T seedrecovery andactualrawcorrections afterthisboundedbatch,
thenchoosefreshfullcontinuation/verification fromevidence. Neither removalof
thecorrectcoefficientanomalies norlargepercentageclippingalone certifiesconvergence.


### 2026-10-23 18:19 UTC — first guarded-line bootstrap checkpoint

Explicit fixed-temperature Lambda 76→77 passed the independent positive,
geometry, charge (1.11e-15) and abundance (2.00e-15) gates. All90 temperatures
remain bitwise unchanged. The closed matrix snapshot matches the previous
published state at every depth. O V SL26 at depth1 requests1.079e-26 of input
Ne from1.113e-49 and is saved at1.113e-37, the unchanged MAX_LAM1e12 cap.
N V SL22 similarly advances12orders. This bridges actual seed deficits rather
than imposing populations or floors. Zero unlimited population targets are
negative. Of31780 population corrections >10%, only4 have input population
>=1e-6 Ne andnone >=.01 Ne. These descriptive counts do not exclude any
variable from the strict convergence criterion. Native78 radiation is running;
three bootstrap steps are still the bounded budget. Main model and installed
CMFGEN remain unchanged. Tail analyzer and JSON retained under root-cause-v1.


### 2026-10-23 18:27 UTC — guarded bootstrap complete; fresh full continuation

`original76-guarded-line-lambda-bootstrap3` finished natively with status
`succeeded`, all three independent saved-state gates accepted. Records77/78/79
have actual raw maxima9.697e24%,9.710e12%,32.281%; >100% counts17552,3,0;
>10% counts31780,1347,363. Every population remains positive; geometry and all90
temperatures are bitwise unchanged. Charge<=1.56e-15, abundance<=2.67e-15.
No unlimited population target is negative at any of the three solves.
Native MAXCH79=47.669% differs from captured actual rawmaximum32.281%; neither
is replaced by the other. The documented convergence criterion is unchanged.
The two extreme outer OV/NV seeds reached their computed targets at78.
`bootstrap-tail-analysis.json` retains largest requests/input/target/saved
populations and confirms every captured matrix input matches prior checkpoint.
The rendered/visually checked `figures/bstar3502-guarded-bootstrap.{svg,png}`
plots raw maxima and both counts, with sourceCSV/generator retained.

Started `original79-guarded-line-fresh-full3` at18:27:21UTC, wrapper68875,
native68876, session23580, using isolated `full-line-ba-stable-v1`.
Three full/T-variable iterations requested, explicit DO_LAM_ITF/DO_LAM_AUTOF;
N_FIX_BA0,FIX_BA0,COMP_BAT ensure freshBA each step and avoid largeBAMATcache.
OriginalMAXLIN10/MAXdT.2/EPS.02 and otherphysicalcontrols retained.
Previouswrapper/native confirmedidle beforelaunch; actualdisk19GiBfree.
Independent checkpoint audits and rawmatrix snapshots remain enabled.
Mainmodel and installedsource/executable unchanged. This is a bounded test
of remaining nonlinear temperature/population relaxation, not convergence.


### 2026-10-23 18:37 UTC — historical native line reproducer/backport

Exact UPDATE_BA_FOR_LINE from b5f07ccc930a4096eaae482184d4a7b8bac8da87
reproduces the same cancellation numerically in the nativefixtures: Lambda
maximumerror1.50223e98, expandedrate2.33418e98/heat2.83209e98.
Historicalsource is unchangedbytes from Git; compiled againstcurrentmodule
types/libs for isolatedfixture, notoriginal2023fullruntime/OS reconstruction.
Lambdaone-expression substitution passes10/10cases. Isolatedbackport of both
line repairs (REAL*8/D0 retained) passesall2750oracleentries ineach default,
cooling andmixed-new-linevariant, maxerror1.11e-15; skipped250/sharedstrong1000
remainbitwisebaseline. HistoricalinstalledlinefilehashmatchesGitobject, and
read-onlygitapplycheck passes fornewpublic combinedmid2023experimentalpatch.
Noinstalledsource ormainmodel edited. This establishes numericalbugpresence
inJune2023routine, notthat originalmodelrunencounteredthesametinyseeds.
Artifacts in historical2023-line-audit; focusedreview documents commands/scope.

A separate staticpaths audit confirms GLOBAL_LINEBLANK bypasses legacy
SUB_CMF_LINE/SUB_SOB_LINE_V3, which retain similar untestedexpressions.
Currentexperimentalfixes coverUPDATE_BA_FOR_LINE only; do notclaimallline
options repaired. Sourcehashes/physicalnewlinereferences retained.
The alreadyrunning full80..82 test is unchanged.


### 2026-10-23 19:11 UTC — shared-level physical oracle and completed full80

The earlier guarded strong candidate's compatibility fixture covered only
LOW_POINTER=UP_POINTER. A new independent physical heating oracle varies the
upper full-level ratio while both full levels depend on one superlevel. The
original aliased-pointer source loses the upper opacity response; full heating
population derivative can be about2x its correct value. Lambda/weak heat passes.
NEW_VST_METH defaultsT, using separate pointers for the same population. In that
layout the original fixed-ratio population heating derivative passes (~5.25e-16),
but the experimental guard removed upper emissivity response while retaining
ZNET final assembly, introducing a ~100% relative population-heating error.
This is a coverage gap/regression in the experimental candidate, not an
installed-source change. Shared temperature-ratio stress tests also expose
original cancellation (relativeheaterror3.847e98); physical trigger notproved.

New candidate combines both opacity responses for aliased pointers and defers
emissivity consistently for all shared population/temperature cases. The public
check_line_jacobian_branches.py --shared-check physical now runs2750distinct
plus2750shared and2750separate-pointer physical oracles: all8250pass. Shared
heaterrors<=9.49e-16; scaledinternalSEresidual<=5.90e-17. Both250entry skipped
shared approximations remainbitwiseoriginal. All3000distinct native outputrows
arebitwisepriorguardedkernel. Legacycompatibilitydifference is recordedexplicitly,
notacceptedwithoutthe strongerphysicalchecks. No fullmodel attribution yet.

Isolated full-line-shared-ba-stable-v1 is built. Its base same-basename relink
is byteidenticalto currentlyrunningfull-line-ba-stable-v1, verifyingunchanged
linkdependencies; onlyUPDATEobjectchanges. Threecurrentpatches apply inisolated
copy to exactnative-testedcandidatebytes. Publicmid2023combinedlinepatch now
includesall3repairs and passes8250physicalchecks/read-onlygitapplycheck.
Prior2repairhistoricalsource/reports retainedunchanged.

Currentcontrol firstfull79→80 completed andpassedpositive/geometry/charge
(1.11e-15)/abundance(5.88e-14) checks. All90T changed, maximumraw/applied
7.5360%, nocap. Previousfull75→76 rawT34.8837%/applied20%; this is trajectory
progress on differentinputs, not a source-only comparison. Raw80max19618.5297%
(HeII SL2 depth28 input7.44e-21Ne,target1.47e-18Ne); >100262, >1024861,
negativeunlimitedtargets64 (previousfull5140). NativeMAXCH1e7is its sentinel
for a proposeddecrease>100%, notthecapturedrawmaximum. Native81nowrunning.

Firstfull80input79radiation snapshotcapturedread-consistently at19:02:08UTC
beforeoverwrite. Full152174frequenciesmatchformalraynodes: nativeouterL
200016.946,target200000.046; outerabsoluteformal/momentfluxmismatch.21753%.
Lastfrequency85.6802micron has outerJratio1.26416, but binL1.125e-4Lsun
(fraction5.63e-10) andabsopacityJexposureproxyfraction3.36e-15. Whole>=10micron
band11.419Lsun. Proxy isnotnetheatingcertification andformalraysarenotexacttruth.
No boundary-grid change justifiedbylastfrequencywarningalone atthisstage.

New selectedfirstfull-step comparator is self-checked on actual80: all273blocks
(268trace+5fullouter),268thermalrows, exactinput79populationcolumns, identical
self-radiation/RHS/matrices. This is parservalidation, notsharedfixattribution.
The nextmatchedsource test muststartfromexactsame79and firstnonfinalfullmode
(prefer same3budget), aftercurrentnativeexit and diskchecks. No nextmodelqueued.


### 2026-10-23 19:24 UTC — temperature trajectory plot and model-like cooling controls

Created/visuallychecked figures/bstar3502-full-temperature-recovery.svg/png
from actual binary full76/full80 states/rawsolutions. T76 isbitwiseinput79
after77..79fixedT steps. Leftpanelzoomsouter12depths; rightshowsall90rawT
requests and76appliedpointswhere damping occurs. Fourouterdepthsreach20%
Tcap; additionaldampingat28,48,49,50 isshownwithoutcallingittemperaturecap.
Full80T isuncapped. Differentinputs/priorguardedkernel: trajectoryevidence,
not a matchedsourcecomparison orconvergenceproof. CSV/generator retained.

ActualVADAT SCL_LNT/SCL_LN_FAC.5 gives shared-SL DeltaE0, causingnative
resettounity(ABS(0-1)>.5), sothisflagdoesnotsuppresssharedheatbug.
Newpublic --cooling-reset fixture checksbothpointerlayouts: all2750physical
entriesperlayoutpassandall3000nativeoutputrowsperlayout arebitwisebaseline.
Source-default NEW_LINE_BAF/INCL_dSLdTF areconsistentwithabsentVADAToverrides;
ratio-temperaturestresscasesarebroaderthanthiscurrentmode. No activeinput
orinstalledsourceedited. Native82ongoing; cleanuphelperpreparedbutnotrun,
requiringcompletednativeSUCC+analysis+idlemodelguard beforeBC/Dcacheunlink.


### 2026-10-23 19:47 UTC — controlcomplete82; matchedsharedrepaircandidate launched

Control original79-guarded-line-fresh-full3 finished nativelysucceeded at~19:42UTC,
allthreeindependentcheckpointgatespass. Actualmodes full80/Lambda81/full82,
allfreshBA. Full82rawmax1012.812%, >1007, >1011871, nonegativeunlimitedtargets.
All90Tchanged, raw/appliedmax8.08718% atouterdepth1, noclip; charge1.78e-15,
abundance2.89e-15, geometryunchanged/positive. Temperaturehasreverseddirection:
outerT2003.84(input79)->1878.20(full80)->2030.09(full82)K; depth3
2654.25->2454.23->2633.46K. Populationtailmuchhealthier buttemperatureisnotyet
settling. NativeconvergenceevidencecandidateFalse retained.

Confirmedwrapper68875/native68876gone. Underidlemodelguard, deletedonly179
rebuildableBC/Dfactorfiles(10,736,947,280bytes); checkpoint/pointer/allrawsolution
hashesunchanged. Journalcompleted-batch-factor-cache-retirement.jsoncomplete;
all273firstfullmatrixblocks, allradiation, inputs, logs, checkpointsretained.
Disk6.9->17GiBfree. NoBAMATgenerated withfreshBAcontrols.

Started original79-shared-line-fresh-full3 at19:44:26UTC, wrapper88117/native88118,
session11341, runtimefull-line-shared-ba-stable-v1. Exactsamepreparedsource79,
SCRTEMP/VADAT/INITS hashes, sourcepointer, requested3/freshBA/mode allmatchcontrol
(matched-shared79-input-verification.json). Onlyindependentlynative-testedUPDATE
objectchanges, basedonbyteidenticalcontrolrelinkproof. Noactualmainorinstalled
sourceedit. Native80isfirstexpectedsolve; resultpending.
Read-consistentcandidatefirst-radiationcapture started19:45UTC/session49485,
processidentityandcwd/exevalidated. Genericselectedfull-stepcomparatorreadyand
selfchecked; use archivedcontrol80rad/matrices andcandidate80oncepublished.
Do notclaimwholemodelsharedrepairattributionbeforethismatchedcomparison.


### 2026-10-23 20:51 UTC — matched shared repair firstfull result; nextthermalJacobian test

Candidate firstfull80completed/published20:11UTC, allindependentgatespass.
ExactpreparedS79/controlhashes/capturedinputpopulationcolumns; all152174
frequencyweightsmatch, peakinputradiationdiff1.098e-11, Ldiff<=6.64e-9Lsun.
Compared273matrixblocks/268thermalrows. Actualsharedrepairchangesdeepthermal
coefficients(maxrowL1relative4.34e-6 atdepth79; outer1..5<=2.34e-12), but
rawTmax7.53601724488->7.53601724435% andmaxsavedTdiff5.40e-5K.
Raw>100262andnegativeunlimited64unchanged. Largeststrongthermalcolumnchanges
includeAlIII SL22(eq985) andMgII SL22(eq894), assembledcoefficients notatomicrates.
Maxsavedpopulationrelativechange2.623e-6; absΔP/Ne<=7.075e-11; forP>=.01Ne
relative<=6.947e-9. Thisisactualkernel/modelvalidationwithoutmateriallychanging
firstouterthermalstep; fullcandidate3stillrunning, do notassertfinalconvergence.
Reports matched-shared79-firstfull-comparison.json/summary andpopulation-difference.

Nextcontrolledhypothesis: INCL_dSLdT currentlyabsent/defaultF zeroswithin-SL
ratioTderivatives inSET_LINE_OPAC. EnablingT addsphysicalJacTcouplings in
DO_VAR_CONT andUPDATE_BA_FOR_LINE whileleavinginputpopulations/rates/radiation
unchangedatthefirststate. Preparedbstar3502-run-sl-temperature-batch.py uses
original79andfullyrepairedsharedruntime, exactsame3budget/INITS/caps/EPS,
pinsentirepre-changeVADATtoall3kernelreferenceandappendsINCL_dSLdTTonly.
Archivesbefore/afterandcontrolled-change.json. RequiresreferencejobSUCCand
positivecompletedanalysisbeforecasecreation; no suchtriallaunched yet.
Comparator --allow-sl-temperature-change verifiesexactbefore/afterbytehashes,
oneappendedkey/sameruntime; strictsourcecomparisonrecheckedidenticalv1/v2.
No benefitclaimbeforeactualmodeltest. NativekernelTderivativesalreadycovered
byphysicaloracles, butnotfulltransportJacobianfinite-differencecertification.

At20:49oneCMFGENnative88118,10threads,RSS8.31GiB,32GiBphysicalRAM,8.47GiB
available,5.40GiBswap; disk5.4GiBfree. Native82advancing, saved81, noresult.
No othernativejob, threadlimit, activemodelchange ornewtestlaunch.


### 2026-10-23 23:20 UTC — superlevel temperature coupling improves full-step settling

The shared-kernel baseline finished all three native steps successfully, with
all independent state gates accepted. Full82 temperature maximum remains
8.08718%; the shared repair alone does not resolve the outer thermal cycle.

The controlled INCL_dSLdT=T case `original79-shared-line-sl-temperature-full3`
then succeeded at 22:35:32 UTC (full80 / Lambda81 / full82), from exact original79.
Prepared checkpoint, runtime, IN_ITS and three-step budget match the F baseline;
archived before/after VADAT bytes prove a single appended INCL_dSLdT tag.
Full raw/applied Tmax decreases 4.6151404% -> 0.8434111%, instead of baseline
7.5360172% -> 8.0871755%. No T clipping, all90 depths updated on both full steps.
Outer five final temperatures: 1949.2587, 2118.6817, 2553.1069, 4725.3265,
8291.7546 K. All states positive, original geometry exact, charge/abundance
errors around 1e-15 (largest abundance error at80 is5.88e-14).
Full82 raw max1012.6829%, >100=4, >10=11776, no negative unlimited targets.
Promising thermal settling, but not a convergence candidate.

The original T-enabled first80 radiation capture is missing because the turn
was interrupted before observer attachment. Its matrix snapshots and checkpoint
are intact; final root radiation belongs to input81 and cannot substitute for79.
Single-step replay `original79-sl-temperature-first80-replay` launched23:11:38UTC,
wrapper34372/native34394, session24584. Same source79/runtime/VADAT/IN_ITS, but
one-step final solve versus original first nonfinal step of three. Its helper
captures all radiation internally after successful native exit and checks the
radiation's temperature epoch against input79. A separate verifier pins matrix,
RHS, raw-vector and saved-state precision gates before examining replay results.
Only if these pass may the recovered spectrum represent the original first step;
no original capture will be fabricated. The comparator has an explicit validated
replay report option; strict default equal-budget behavior remains intact.
Physical continuation must start from original successful T-enabled82, not replay80.

At local midnight the old /private/tmp Python dependency tree lost Python source
files, leaving namespace imports without real psutil APIs. Initial factor-cache
retirement failed inside model_mutation_guard before mutation. Switched to the
existing /Users/karpov/miniforge3/envs/cmfgen/bin/python environment (real psutil,
NumPy, Astropy, runner imports); no guard bypass or native/input/thread change.
The completed T-enabled case's179 rebuildable BC/D factors were then retired
successfully under the idle guard; journal records10,736,947,280bytes and unchanged
checkpoint/raw hashes. Disk54GiBfree23:17UTC; active replay caches untouched.
Main model and installed source/executables remain unchanged.


### 2026-10-23 23:23 UTC — temperature-column localization and sequential controller

Compared the original F/T full80 matrix snapshots directly, independently of
any replay data. All273 captured blocks have identical input79 population columns.
Largest non-temperature-column difference is1.902e-12 peak-relative; largest
non-T part of a thermal-row difference is1.652e-12 relative to that row L1 norm.
RHS differs at most1.038e-8 peak-relative. Temperature coefficients change
substantially: local outer-depth1 thermal T coefficient +1.994e-7 -> -7.788e-5,
depth3 +2.447e-7 -> -6.740e-5. These are assembled scaled Jacobian coefficients,
not atomic rates. This localizes the intended coupling change to the T columns;
it is not an independent full-transport finite-difference certification.
Evidence: sl-temperature-original80-column-analysis.json, with reproducible helper.

Generated and visually checked figures/bstar3502-superlevel-temperature-option
SVG/PNG/CSV and gnuplot scripts from original actual full80/full82 solutions.
Panel1 compares matched input79; panel2 compares each branch's evolved input81,
explicitly labelled trajectory evidence. Neither plot depends on missing radiation.
Tail audit shows the four >100% full82 requests are extremely small HeII/OIII
populations;20 populations >=1e-6Ne still exceed10%, six >=.01Ne exceed10%.
No tail exclusion or relaxed convergence gate has been applied.

Started sequential controller36688/session95728. It waits for existing replay
wrapper34372 to exit, requires successful native/postanalysis, runs strict replay
precision verifier, then the explicitly permitted replay spectral comparison.
Only after success does it launch one bounded6-step freshBA continuation from
original accepted T-enabled82 (case original82-sl-temperature-fresh-full6), with
same repaired executable/physical controls/INCL_dSLdT. It attaches first83 radiation
observer immediately after identifying the native PID and stops on any failed
precondition; no concurrent native runs or automatic model promotion. Journal:
sl-temperature-replay-and-continuation.json. Full82 uses native grey solution
alongside variable-T full solve in both original branches; retained in native
records, not mislabeled as a fixed-T step. Goal active; main/installed untouched.


### 2026-10-23 23:26 UTC — option provenance

Read-only Git history shows INCLUDE_dSLdT was introduced by490e8b92db846e95565dfb140ebe8cc58bf0a88d on2010-01-13. The original-model
mid2023 commit b5f07ccc930a4096eaae482184d4a7b8bac8da87 has the same explicit
false default and opt-in tag. This is an existing Jacobian option, not a new
post2023 feature. No commit rationale proving universal safety/convergence has
been found; the present model's controlled test and further continuation remain
the basis for any recommendation. Exact historical excerpt retained in
sl-temperature-option-history.json. Original first80 source/input comparisons
remain independent of the running replay spectrum.


### 2026-10-23 23:38 UTC — prepare independent final-output transport observer

Built isolated full-line-shared-transport-v1 from the exact currently tested
full-line-shared-ba-stable-v1 objects/libraries. A control relink first reproduces
that executable byte-for-byte. Only CMFGEN_SUB gains the previously tested opt-in
TRANSPORT_ONLY_DIAGNOSTICS branch: preserve normal DTDR, disable unused BA
variation work, then STOP before Newton/checkpoint update. Line/BA repairs,
radiation objects and all link dependencies remain the same. Candidate executable
SHA25605617d777ecf43b9f5ec073ba0b6a8d2039d1caf031d5d8644e8474a255d8421.
Build manifest, source diff and reproducible builder retained; no native probe
started or queued while replay/controller jobs are active.

Initial control relink correctly failed because gfortran embedded the different
build cwd as a Mach-O RPATH. Retained that failed proof in the .rejected-cwd
runtime directory, then rebuilt from original repository cwd; control hash exact.
No candidate from the rejected build was compiled/run. This was a build-provenance
issue, not a scientific model failure or active runtime edit.

Existing run_transport_probe.py now uses its actual Python interpreter for
analysis subprocesses, supports --require-accepted-native-source, and runs the
all-frequency formal-ray comparison when requested. The optional source gate
requires genuine native success and independent positivity/geometry/charge/
abundance acceptance before copying a final-state probe. Final acceptance must
still prove unchanged checkpoint/pointers and exact source temperature epoch in
complete radiation output; intentional no-update probe runner status is retained,
not relabeled as native success or model convergence. Probe is for after the
physical recovery meets correction criteria. Observational batch summaries also
now report temperature/Ne raw maxima and counts at the actual .02% threshold;
no solver convergence tolerance or model controls changed.


### 2026-10-23 23:46 UTC — live replay prefix agrees with matched input radiation

Replay34394 remains live, with native10threads and controller36688 waiting.
Compared only the first20000 completed FE frequency records, far behind the
current append position, against the full archived Fbaseline input79 spectrum.
Candidate prefix was read twice identically; control full-file SHA matches its
read-consistent capture journal. All frequency IDs, frequencies and weights
match exactly; all selected-depth T fields at every prefix frequency equal
source79 temperatures bitwise. All60 radiation/opacity/emissivity/geometry/T
fields agree at max5.644e-15 peak-relative. Report records prefix SHA and explicit
partial scope: sl-temperature-replay-partial-radiation-check.json. No complete
spectrum, full replay equivalence or convergence claim. Keep waiting for genuine
native exit; no restart or parallelmodel launched.


### 2026-10-24 00:23 UTC — replay verified; physical continuation82→88 launched

The one-step replay succeeded natively, saved80 passed independent physical
gates (charge1.22e-15, abundance5.91e-14, originalgeometry, positive/all90Tchanged).
All predefined replay equivalence limits passed versus original T-enabled80:
273blocks, RHSpeak1.156e-8, matrixpeak5.153e-12, full raw-vector scaled difference
1.555e-10, savedpopulationrelative5.185e-10, absΔP/Ne4.239e-14, savedTmaxΔ
1.613e-8K. The replay is final1 and includes native grey diagnostic; original80
was nonfinalfirstof3. Actual measured equivalence handles this explicit mode/
budget difference. Full replay rawmax19618.3589789465%, original19618.3589789483%;
>100262/>1024715, negativeunlimited64. Not convergence; no missingcapture fabricated.

Then compared Fbaseline first80 to the verified T replay at sameinput79:
all152174 frequencies/weights and all273 captured populationcolumns exact;
allfields peakradiationdifference1.177e-11, luminositydifference<=4.69e-9Lsun,
RHSpeakdifference2.194e-8. RawTmax7.53601724435% ->4.61514040731% with only
INCL_dSLdT changed within the fully repaired runtime. This completes the missing
whole-spectrum attribution check. Reports sl-temperature-replay-equivalence.json,
matched-sl-temperature79-firstfull-comparison.json and
matched-sl-temperature79-firstfull-summary.json.

Controller36688/session95728 launched original82-sl-temperature-fresh-full6 at
00:21:52UTC, wrapper52192/native52200, observer52201. Exact copied source82
SCRTEMPsha d10b5f2777586bb71ce811589ec0d5398e0256552ff7daf67fc9d0e4465e81cc;
VADAT ac296... unchanged T-enabled. Six bounded freshBA iterations, originalcaps/
EPS/geometry, no LTE reseed or floor. Source is original healthy T-enabled82,
not replay80. Capture journal waitingforfirst83, attached atnativeage1second.
Oldreplay34394/wrapper34372 gone; onlynew52200native. No checkpoint yet.
Mainmodel/installedsource untouched. Future final-output puretransport probe is
built but notrun. Goal active, proper convergence still unproved.


### 2026-10-24 00:26 UTC — continuation live, completed replay factors retired

Verified native52200/controller36688/observer52201 live; currentgreatiteration83,
13100/152174 frequencyrecords,10native threads. Actualmain SCRTEMP and T_INtarget
SHA values remain the original handoff hashes. The continuation is a genuine
restart from82; no state from replay80 is promoted.

After replay native success, independent gates and completed spectral/matrix
comparison, retired only its179 explicitly whitelisted BC/D factor-cache files
under that replay's idle model_mutation_guard. Journal complete with
10,736,947,280bytes; all protected checkpoint/pointer/raw-vector hashes unchanged.
All original assembled matrices, radiation snapshots, controls, logs and state
records retained. The active continuation has its own fresh factors and was
untouched. Free disk52.3GiB. No further test or final-output probe queued beyond
the current bounded6 native iterations. Inspect each completed state/rawsolution
before choosing next physical action; model convergence remains unproven.


### 2026-10-24 00:49–01:02 UTC — first full continuation83 settles further

First83 full/freshBA step accepted. All90 captured input population columns
match exact source82 (separate observational reconciled snapshot, aggregate
native status retained as running). Raw/appliedTmax0.258750448% atdepth3;
rawNe max0.386210842%. Outer3T2553.1069->2546.5008K, outer1T1949.2587->1945.0027K.
Every saved population/Ne/T equals old*(1-raw) bit-for-bit: no limiting/damping
on this step. All targetspositive; originalgeometry exact; charge1.443e-15,
abundance1.998e-15. Evidence in `continuation-observations/through083/`:
`reconciled-batch-analysis.json` and `full-step-target-analysis.json`.
Analyzer now accepts --output-dir
for observational snapshots separate from the active native batch's final report;
default existing behavior retained, native driver unaffected.

Rawmax290.419869%, >10022, >106671, >.02147333. The22 >100 are OIII2/NiIV20;
all input fractions<=3.9306e-21Ne. Largest NiIV SL14 depth28 input2.8836e-22Ne
->target/saved1.1258e-21Ne. No negative targets; no trace variables excluded.
For inputpop>=1e-6Ne only4still exceed10% (previous82:20), >=.01Ne only2 (was6).
Pop corrections remain too large for convergence despite thermal improvement.

First83 input82 radiation was captured read-consistently before overwrite.
All7 SHA hashes verified, every recorded selected-depth T field at all152174
frequencies matches source82 bitwise. All frequencies matched formal-ray samples;
outer nativeL200361.849 vs formal200084.192Lsun, absolute outerflux mismatch.22058%.
Deepest selected mismatch.38324%, maximum across5depths.65175%; no missingflux.
This is formal/moment consistency, not an exact solution or output83 radiation.

Generated/visually checked figures/bstar3502-sl-temperature-recovery.svg/png,
source CSVs, gnuplot scripts and reproducible plot helper. ActualfullTmax:
4.61514->.843411->.258750%; defaultFbranch7.53602->8.08718% shown separately.
Lambda81 omitted from T graph, retained in all-variable counts; log10(1+count)
keeps exactzero counts without a fakefloor. All90matrixinputcolumns revalidated
for each plotted solve. Later points are trajectories, not matched-input source
comparisons. Native84 currently running; no additional test or finalprobe started.


### 2026-10-24 01:14–01:24 UTC — full84 improves further; progressive sweep capture

Full/freshBA84 accepted with originalgeometry and all90 Tupdated. Charge1.110e-15,
abundance2.220e-15; no negative unlimited targets. All saved populations/Ne/T
again equal old*(1-raw) bit-for-bit, so no limiting. RawTmax0.0424533038% atdepth4
(previous.258750%), Ne max.120092145%, all-variable max33.4069068% (was290.420%).
No variables exceed100%;1180exceed10%. Exact full threshold table in observational snapshot:
continuation-observations/through084/reconciled-batch-analysis.json; >1=44672,
>.1=99075, >.02=135346, >.01=149704. Model still not converged.
Largest request SkIII SL10 depth37 input5.644e-14Ne->target/saved7.529e-14Ne.
All >10% populations initially below1e-6Ne;36 initially>=1e-12Ne. OutermostT
1945.0027->1944.7226K (-.0143976%), depth3 2546.5008->2546.1086K (-.0154013%).
Full-step-target-analysis.json retains the precise profile and unlimited checks.
Updated/re-rendered trajectory CSV/SVG/PNG through84; zero>100count shown exactly
using log10(1+count), all tracevariables stillincluded. Full90inputcolumns matched
previouspublished83 in separate reconciled analysis; aggregate status remainsrunning.

Extended the read-only generic observer with --solve-record, retaining first-step
default. Selected capture requires the accepted previousinput checkpoint and
bitwise matching selected-depth T across all152174 FErecords, plus existing
before/afterstat/fullSHA checks. Parent63906/session67571 captures84..88 sequentially;
84 completed01:13:51UTC, worker63912 nowwaiting85. No native inputs/runs altered.
Newcomplete84spectrum is input83, not output84. Ray stream appends across solves:
verified exact archived83prefix269517records and new84tail234570records, cumulative
504087. Every FEfrequency occurs in new84tail; cumulative last-per-frequency
samples equal newtail last samples bitwise. ray-epoch-verification.json proves
current-epoch comparison. All-frequency outerabsolute flux mismatch.22174%, max
selecteddepth.65317%, no missingflux. Formalrays remain consistency data, not an
exact solution. Physical iteration85 running on same native52200,10threads;
controller36688/session95728. Newfinalprobe is built but notstarted.


### 2026-10-24 02:06 UTC — full85 and Ng scheduling audit

Full85 accepted, freshBA/variableT, no negative targets; charge1.554e-15,
abundance2.331e-15, originalgeometry. Raw/appliedTmax.024415678% atdepth33,
Ne max.099137161% atsamepoint (Tbefore9884.66K). Outer3T2546.1086->2545.4875K
(-.0243924%); outer1T1944.7226->1944.2940K (-.0220414%). All saved populations,
Ne andT equal unlimitedtarget bitwise. Rawallmax24.489413% atSkIII SL37depth38;
zero>100%,255>10%,34211>1%,91306>.1%,127423>.02%. None above1e-6Ne exceed10%,
but44 exceed1% and311 exceed.02%: no claim that only negligible variables remain.
Largest request input1.7046e-17Ne->target/saved2.1220e-17Ne. Native latest spectral
change3.61% (was10.7%). Model not converged, aggregate native stillrunning86.
Closed evidence continuation-observations/through085; trajectory plotupdated.

Capture85 completed01:39:01UTC, FEsource84Tepochallfreqverified. Dedicated
bstar3502-verify-ray-epoch.py checks same-native-process journals/dataSHA,
immutable previousprefix and complete newtail coverage:504087old+233645new
=737732rays; all152174FEfreqcurrent, cumulative-last==tail-last bitwise. Pass.
Formal/moment outerabsolute flux mismatch.22150%, maxselecteddepth.65257%,
no missingflux; this remains consistency-only. Subsequent86observer waiting.

Ng read-only audit finds originalDO_NGT,BEG_NG10%,IBEG25,BW10,ITS/NG20,CHK_NGF.
MAXCH85=24.4894 isnotyeteligible; POINT1LAST_NG=-1000 confirmsnone. Current
SOLVE_FOR_POPS source schedules firstNg4solves ahead, skipsLST_ITERATION; main
resetsNEXT_NG2000eachprocess. Thus normal5solve continuation blocks repeatedly
placefirstNgonlaststep and canstarveit indefinitely. This is source-derived
cadence evidence, not a nativeNgacceptance experiment or originalcatastrophic
instabilitycause. Exact excerpts/hashes in ng-scheduling-source-audit.json.
Current controlled6testunchanged; anypost-testhealthycontinuationbelowtrigger
shouldleave>5contiguoussolves and retainphysical/freshfullverification. No
parameterchange ornewNativejob made forthisfinding.


### 2026-10-24 02:13 UTC — full86 temperature passes its threshold, model still unconverged

Full/freshBA86 accepted, all90Tchanged, originalgeometry; charge1.110e-15,
abundance2.442e-15. Every saved population/Ne/T matches unlimitedtarget bitwise.
No negative targets. RawTmax.018715108% atdepth34, Ne max.069105562% atsamepoint.
All outerfive Trequests between-.00344% and-.00723%, wellbelowformer8% cycle.
Rawallmax18.349053%, zero>100%,97>10%,25722>1%,84960>.1%,120957>.02%.
All97>10inputfractions below1e-12Ne; forinput>=1e-6Ne,17 exceed1%,277 exceed.02%.
Largest SkIII SL37 depth38 input2.1216e-17Ne ->target/saved2.5108e-17Ne.
Native spectralchange1.54% (previous3.61%). Temperature criterion alone doesnot
establish convergence; populations/Ne and freshfinalchecks remain outstanding.
Closed evidence continuation-observations/through086 and updatedtrajectoryplot.

Capture86 complete02:05:17UTC; FE Tepochsource85verified. Rayepoch helper proves
737732oldprefix+233702new=971434cumulative, all152174FEfreqcurrent. Formal/moment
outerabsolute flux mismatch.22131%, maxselecteddepth.65224%, no missingflux.
No stale-ray epoch mixing. Selected87 observer waiting; same native52200/controller
36688 and no parameterchange/newNativejob. Ng stillnoteligible atMAXCH18.349>10.
Source-derived five-step cadence caveat retained forpost-testcontinuationbudget.


## 2026-10-24 06:31 UTC — terminal88 reviewed; eight-step continuation

The completed six-step batch is native `succeeded` and all83–88 state gates
pass. Every solve used variable T and freshly computed BA; the last step's
grey diagnostic is recorded separately. Final88 has raw all-variable maximum
10.7981287%, T maximum .01945662%, Ne maximum .04392998%, no negative
unlimited targets, zero variables >100%, ten >10%, and110643 >.02%.
The ten largest-relative population changes are all below1e-12 of input Ne;
they remain counted in the strict convergence requirement.

All selected input-radiation sweeps83–88 were captured read-consistently. The
final88 appended-ray epoch proof covers all152174 native frequencies, with
no missing contribution. Its formal/moment absolute-flux mismatch is .221114%
at the outer point and at most .651867% across the five sampled depths.
Native outer luminosity is200615.436Lsun against target200000.046Lsun. These
are transport consistency observations, not a convergence certificate or a
claim that the final saved88 populations have already been independently
probed. The captured88 sweep used input87, as its epoch checks explicitly prove.

The next isolated case `original88-sl-temperature-fresh-full8` starts from
accepted88, retains `INCL_dSLdT=T`, all three line-Jacobian repairs, fresh BA,
original90-point moment grid, refined ray grid and EPS=.02%. Eight contiguous
physical steps allow the existing native Ng schedule to reach an interior
step if its MAXCH<10% condition is met. No forced Ng or relaxed physical gate
was introduced. Native PID34863 uses ten threads; session10383 owns the runner,
and read-only radiation observer session31591 follows actual solve counters.
No second model job is allowed concurrently. Main model and installed sources
remain unchanged.

Terminal87/88 were additionally checked against their exact full raw Newton
targets: all saved populations, Ne and T match `old*(1-raw)` bit-for-bit,
completing that proof for all six83–88 steps. Thus the observed improvement
was not produced by clipping or damping the saved update. The report is
`original82-sl-temperature-fresh-full6/full-unlimited-target-verification.json`.
All90 temperatures are below .02% in both87 and88; nine Ne corrections still
exceed .02%, and the all-population gate remains unsatisfied.

### Residual depth and population scales at88

A new exact correction-versus-depth figure and CSV,
`figures/bstar3502-corrections-by-depth88.{png,svg,csv}`, separates T/Ne
from population corrections and explicitly labels population-scale selections.
Although the ten >10% variables are tiny, the remaining error is not exclusively
a tiny-population tail. Among populations initially≥1e-6Ne,262 still exceed
.02%,93 exceed.1%, and ten exceed1%. The largest is HeI ground state atdepth30:
1.672913% correction from an input population .0161708Ne. The same maximum
survives a stricter≥.01Ne selection, which still has32 populations above.02%.
Thus there is a resolved, physically significant ionization adjustment remaining
in the intermediate layers; relaxing the gate for tiny populations would not
establish convergence. `population-scale-corrections88.json` retains exact
counts and input normalization. These scale selections describe the state and
do not change the strict all-variable convergence requirement.


## 2026-10-24 — separate Ng temperature-sign guard defect reproduced

While the accepted88 continuation remains unchanged and running, a native
arithmetic fixture reproduces a separate defect in `do_ng_accel_band_v4.f`.
The outer routine appends R, V and Sigma+1 to the physical population vector
and passes `NT_MOD=NT+3` as the inner routine's NT. Its advertised temperature
sign check still uses `NEWPOP(NT,L)` and `RDPOPS(NT,L,...)`; this selects
Sigma+1 rather than physical T. Constant geometry makes its difference zero
and bypasses the intended sign rejection. This is independent of `CHK_NG`,
whose optional outer validity check is disabled in this model.

The actual unmodified numerical routines, linked to native NGACCEL, receive
the same positive P/T history at four depths. Current T=1, previous=.98,
older=.97/.965 produces extrapolated T=.96, opposite to the latest increase.
With only physical variables the routine rejects all four proposals. With
the actual three constant geometry components appended, it incorrectly
accepts all four and returns .96. No checkpoint I/O or model job is involved.
`ng-temperature-guard-audit/report.json` retains source hashes, compiler
commands and native output. Exact mid-2023 Git source has the same dimension
and guard-index expressions (`historical-source-comparison.json`); only the
current-source arithmetic reproducer has been executed so far.

This does not establish that an eventual Bstar3502 Ng proposal has wrong-sign
T, or explain the already observed pre-Ng failures. The running model and
installed source remain unchanged. Its actual first Ng, if performed, must
be assessed explicitly for temperature direction and physical state. An
isolated correction can pass the physical temperature index separately; it
must preserve existing correct-sign and fixed-temperature behavior.

The isolated explicit-T-index correction now passes full-wrapper validation,
not just an extracted inner-kernel check. The actual full V4 caller and
fitting functions were compiled with a deterministic scratch-reader stub:
25 corrected cases reject wrong-sign warming/cooling and preserve correct-sign
warming/cooling and fixed T, across five band widths, all geometry bitwise
unchanged. Candidate bounds checks and floating-point traps pass. Another25
full-wrapper controls reproduce the unpatched error. Public reusable test
`cmfgen-review-tests/check_ng_temperature_guard.py` has separately passed in
both original-defect and corrected modes. The experimental patch is
`patches/bstar3502-ng-temperature-guard-experimental.patch`; it passes read-only
application checks and does not change the Ng fitting mathematics or legacy
V1 ABI. No installed source or running model change was made.


## 2026-10-24 06:56 UTC — first restarted full89 accepted

Fresh-process/full/fresh-BA89 passes the physical gates, with no limiting:
every saved population, Ne and T equals its unlimited Newton target bitwise.
Largest raw correction8.458432%, T .01854863%, Ne .03652598%; zero variables
>10% or100%,106178 >.02%, no negative unlimited targets. Geometry is identical,
charge error9.99e-16 and abundance error2.00e-15. The native scheduling MAXCH
is7.8636678%, distinct from the strict full raw maximum8.458432%; both are
below10%. Source therefore predicts an initial Ng opportunity at93 if later
steps remain eligible and its other guards pass. Actual Ng has not yet occurred.

The complete89 input-radiation capture belongs to saved88 (all152174 selected
T epochs verified), with all frequency contributions represented. Outer
formal/moment absolute-flux mismatch is .220390%, maximum .651009% across
the five sampled depths. Native outer L is200640.328Lsun against target
200000.046Lsun. The source state is still not converged; this is a complete
fresh-process radiation consistency observation, not final-state certification.
The same native process is now solving90; no second model job was started.


## 2026-10-24 07:07 UTC — offline Ng replay on actual closed histories

The Ng guard concern also occurs on copied model histories, not only the
synthetic reproducer. An offline invocation of the actual original V4 Ng
arithmetic on closed accepted89/88/87/86 states would accept a proposal with
T opposite to its latest step atdepths41–50. Maximum T change .2199065%,
maximum population change77.5716%; all returned values remain positive,
geometry stays bitwise fixed and charge/abundance error is~1.42e-13. The
corrected T-index guard would cancel that proposal because more than three
depths fail its intended sign condition.

This was not a scheduled or forced model Ng, and none of these returned
populations was written to any checkpoint or used to continue the model.
It does not prove the original proposal would harm convergence: extrapolation
may legitimately reverse an individual component. It establishes that the
index mismatch can alter the intended safeguard on actual stored histories.
The scheduled first opportunity remains93 and uses different input histories.
The read-only observer in session38256 waits for an explicit actual native Ng
plus an accepted extra checkpoint, then independently replays those actual
inputs and compares with the published Ng state. Native model34863 continues
unchanged at90; observer or arithmetic outcomes never restart or modify it.
Evidence: `hypothetical-ng-arithmetic89/report.json`.


## 2026-10-24 07:22 UTC — full90 accepted, spectrum preserved

The same fresh-process continuation completes its second full/fresh-BA step90:
raw maximum6.6998493%, T .01702454%, Ne .03081627%, zero>10% or100%,
100251>.02%, no negative unlimited targets. All saved variables equal their
full unlimited Newton targets bit-for-bit. Geometry is unchanged, charge
error9.99e-16 and abundance error2.22e-15. Native scheduling MAXCH6.2288953%
remains below10%; first Ng opportunity remains93 if the conditions persist.
Native latest spectrum-change diagnostic is .393%. No actual Ng has occurred.

The read-consistent90 spectrum belongs to input89, and the appended-ray
epoch proof covers all152174 native frequencies with zero missing contribution.
Formal/moment absolute-flux mismatch is .2209995% at the outer point, maximum
.6516569% across five sampled depths. Outer native L is200661.687Lsun against
target200000.046Lsun. These remain consistency measurements, not exact RT
certification or a claim that saved90 is converged. Trajectory plots and CSVs
now include90. The unchanged native34863 is running91.

For eventual final saved-state verification, the no-update probe helper now
pins SCRTEMP and both POINT-file hashes in its preparation metadata. A separate
post-run verifier checks their preservation, exact T/R epochs across all
152174 frequencies, the explicit pre-Newton stop marker, no completed Newton
record, complete formal-ray coverage and executable build hash. This verifier
is prepared, not yet executed on a final probe; all-variable convergence and
fresh full verification must be established before that final probe is run.


## 2026-10-24 07:48 UTC — full91 accepted

Third resumed full/variable-T/fresh-BA solve91 completes normally. Raw
all-variable maximum5.3503095%, T .01527551%, Ne .02628444%; zero corrections
>10% or100%,95389>.02%, no negative unlimited targets. Every saved population,
Ne and T again equals the unlimited Newton target bitwise. Geometry remains
identical; charge mismatch1.33e-15, abundance mismatch2.44e-15. Native scheduling
MAXCH4.9774932% is distinct from the full raw maximum and remains below10%.
Its latest spectrum-change diagnostic is .245%. No actual Ng has occurred;
Native34863 is running92 and the first scheduled opportunity remains93 if
conditions persist. The aggregate eight-step run is still active and cannot
be promoted or treated as a completed source.

All152174 selected temperature epochs in the91 capture match input90. The
appended formal-ray stream has232351 new samples covering all152174 native
frequencies, with prefix SHA and last-sample epoch proof passing. Native outer
L is200680.326Lsun against target200000.046Lsun. All-variable convergence,
fresh final verification and an independent final saved-state probe remain
unproven; the continued decline in corrections alone does not establish them.


## 2026-10-24 08:15 UTC — full92 accepted;93 starts

Fourth resumed full/variable-T/fresh-BA solve92 passes: raw all-variable
maximum4.3015860%, T .01355981%, Ne .02262565%, no corrections>10% or100%,
91795>.02%, no negative unlimited targets. Every saved variable equals its
unlimited Newton target bitwise. Charge mismatch1.11e-15, abundance2.44e-15;
geometry unchanged. Native scheduling MAXCH4.0046572% remains below10%.
Latest native spectrum change .201%; outer L200696.877Lsun against target
200000.046Lsun. The unchanged native34863 now solves93, the first predicted
Ng opportunity, not yet an actual Ng event. The first-Ng observer remains
waiting for explicit success and accepted publication before replay.

The92 capture belongs to input91. The cumulative ray-prefix SHA matches91,
and232186 newly appended samples cover all152174 native frequencies with
no missing contribution. Actual final convergence, fresh verification and
final saved-state probe remain unproven.


## 2026-10-24 08:42 UTC — first actual Ng93→94 verified

Full93 raw maximum3.4774754%, T .01190325%, Ne .01958271%, zero>10% or100%,
89899>.02%, no negative targets. Stored93 matches its unlimited Newton target
bitwise and passes positivity/geometry/conservation (≤2.23e-15). Native Ng then
publishes94. The actual full V4 arithmetic, replayed independently on the four
closed93/92/91/90 states, reproduces every94 population/Ne/T and geometry bitwise
(max relative difference0). Post-Ng94 remains positive, original geometry
unchanged, charge1.39e-13 and abundance2.54e-13. POINT1 LAST_NG is94.

Applied Ng maxima are population22.5478% and T .0868822%, distinct from the
pre-Ng raw Newton residual. The largest population change is tiny SkIII SL37
atdepth39; among populations initially≥1e-6Ne, the largest is a5.10250% decrease
in HeI ground state atdepth31, initially .0196029Ne. These are applied
extrapolation changes, not evidence that94 is converged. Subsequent full95,
currently running in the same unchanged process, will measure that residual.

The corrected safety guard still accepts this actual Ng, but retains pre-Ng
values at depths85/89/90. Its maximum population difference there is .008174%,
T difference≤.047K, Ne difference≤.000038%; these are all below .02%. It leaves
the dominant Ng update and87 other depths bitwise identical. This proves the
guard can affect this actual event, but its measured effect does not explain
the large residual or justify attributing the earlier instability to it. No
guard patch or candidate populations were installed/promoted into the run.

The93 radiation capture belongs to92; prefix SHA and231962 new ray samples
prove complete current-epoch coverage of all152174 frequencies. Native94 is
Ng-only, without a radiation or Newton solve. Its observer journal's
`missed_selected_sweep_requires_inspection` is explained in
`input-record093-solve094/ng-only-record-explanation.json` and is expected.
Plots now place93 raw corrections at93 and mark Ng-only94 separately; no
fictitious94 residual/count point is drawn. CSVs separate pre-Ng linear saved
T from post-Ng saved T. `ng93-reconciliation.json` retains the exact state,
matrix, arithmetic and guard comparisons. Convergence remains unproven.


## 2026-10-24 09:08 UTC — first full post-Ng95 healthy

Full/variable-T/fresh-BA95 passes all gates: raw maximum2.5630761%, T .01012434%,
Ne .00182803%, zero>10% or100%,91395>.02%, no negative unlimited targets.
Every saved variable equals its unlimited Newton target bitwise. Charge
mismatch1.22e-15, abundance2.66e-15, original geometry unchanged. Native MAXCH
2.4724101% and latest spectrum change1.34% are retained separately; the finite
post-Ng population redistribution changes the spectrum without a transport
collapse. Native outer L200896.856Lsun, target200000.046Lsun.

Compared with pre-Ng full93, Ne correction drops .0195827%→.0018280%; for
populations initially≥.01Ne, maximum .747519%→.122433% (both HeI ground state).
For≥1e-6Ne, maximum .747519%→.269825% (now NIII ground state). All >1%
population corrections are now below1e-12Ne, and their count drops10639→2647.
The strict >.02% count nevertheless rises89899→91395, and the≥1e-12Ne >.02%
count rises6190→8591. Smaller populations are still readjusting; there is no
monotonic all-metric convergence claim. The before/after observations are not
a controlled no-Ng counterfactual. Exact scale-conditioned data are in
`post-Ng-first-full95-comparison.json`; no selected group changes the strict gate.

The complete95 spectrum belongs to Ng94. Its ray-prefix SHA matches93
(skipping Ng-only94), with237556 new samples covering all152174 native
frequencies and no missing contribution. Outer formal/moment absolute-flux
mismatch .223790%, maximum .654248% across five sampled depths. The plot now
includes Ne as a separate full-step curve and marks Ng94 without inventing a
Newton residual there. Native34863 is running96;97 remains in the same planned
batch. Further settling, fresh final verification and final saved-state
transport probe are still required.


## 2026-10-24 09:35 UTC — second full post-Ng96 settles

Full/variable-T/fresh-BA96 passes: raw maximum .7802896%, T .00141444%,
Ne .00101719%, no variables>1%,10% or100%,66159>.02%, no negative targets.
Every saved population/Ne/T equals its unlimited Newton update bitwise.
Charge1.11e-15, abundance2.33e-15, geometry identical. Native MAXCH .74842145%
and spectrum change .0712% are separate observations. Native outer L200904.148
against target200000.046Lsun. Among populations initially≥.01Ne, maximum
.0245385%, only two>.02%; among≥1e-6Ne, maximum .152229%,99>.02%. Unlike the
first post-Ng step, the full threshold count now declines91395→66159.

The96 capture belongs to95; its225704 appended ray samples cover all152174
frequencies with prefix SHA/current-epoch checks passed. The same native34863
is running final planned97. This case must finish, its wrapper exit and terminal
raw/physical/native results be reviewed before cloning or retirement of its
rebuildable factors. If healthy but still above EPS, the prospective next case
`original97-sl-temperature-fresh-full10` would retain all physics, fresh BA,
EPS and LAST_NG. It is not created or running. Ten steps fit the five-hour
helper limit at the observed~26min/step and retain enough future cadence to
reach the next Ng at114 in a later block if needed.


## 2026-10-24 09:50 UTC — slower last-step observed-flux path

Final97 is live and advancing, but its frequency sweep is slower. Read-only
source inspection identifies the enabled additional `CMF_FORM_SOL_V2` observed-
flux calculation in `COMP_J_BLANK`: LST_ITERATION, full (not Lambda), native
MAXCH<100%, non-SN; the regular-grid branch also requires ND<200. This is not
a new1% population-precision switch. Continuing starts initialize MAXCH=0,
which also enables this extra work in single-final-step replays.

The earlier one-final-step80 replay already passed predefined full primary
radiation/RHS/raw-vector/saved-state equivalence bounds against nonfinal80;
no new claim of whole-model operator equivalence is inferred from static
inspection alone. Source excerpts and hashes are retained in
`last-step-formal-flux-source-audit.json`. The current97 data remain pending.

The isolated batch helper now accepts an optional bounded `--timeout` value;
its default18000s and the active eight-step job's existing five-hour plan are
unchanged. The prospective ten-step continuation, if terminal97 is healthy
and not converged, will use21600s (six hours) to allow the additional final
observed-flux work. This changes only a wall-time guard, with all physical
controls/EPS unchanged. No next model has been prepared or run.

Timing qualification: the completed six-step case's TIMING assigns97.75s to
CMF_FORM_SOL, with final step1696.91s versus preceding1579.12s. Thus that
enabled extra observed-flux path accounts for some overhead but does not by
itself explain the full slowdown of current97. Its actual cost attribution
is not established from static source inspection. Current97 continues to
advance; the prospective six-hour guard allows scheduling margin without
changing physical precision or model controls.


## 2026-10-24 10:39 UTC — terminal97 verified; ten-step continuation launched

The eight-step batch ends native `succeeded`, wrapper exit0, all eight completed
full/variable-T/fresh-BA solves and all published physical audits accepted.
Terminal97 raw maximum .5426303%, T .00078236%, Ne .00038314%, zero>1%,10%
or100%,55362>.02%, no negative targets, unlimited saved update bitwise.
Charge1.33e-15, abundance2.00e-15, original geometry. Native MAXCH .51720597%;
ordinary convergence evidence correctly says candidate=False, fresh_verified=False.
All≥.01Ne populations are below .02% (maximum .0188310%);≥1e-6Ne maximum
.0550700%,61>.02%. Exact grouping is in `terminal97-population-scale.json`;
all variables remain in the strict gate.

The97 radiation capture belongs to96, with226375 new appended ray samples
covering all152174 frequencies and passing prefix SHA/current-epoch checks.
Outer absolute-flux mismatch .220573%, maximum .651030% at sampled depths;
outer native L200906.253Lsun against target200000.046Lsun. Final97 elapsed
3592.79s versus96 1617.06s. CMF_FORM_SOL accounts for197.72s and new
PRRRCOOL89.84s; broad BA/transfer counters also rise. Inclusive timing counters
do not establish an exclusive cause for the slowdown. The actual raw/physical
results are healthy. `terminal97-native-timing-comparison.json` preserves data.

After the wrapper exited and a global native-process scan confirmed idle,
179 rebuildable BC/D scratch factors were removed under the model guard,
freeing10736947280bytes with protected checkpoint/raw hashes unchanged. No
scientific snapshots, spectra, checkpoints, inputs or user backups were removed.
The next case `original97-sl-temperature-fresh-full10` then started10:37:26UTC,
native90491, runner session93470, read-only monitor80734 and radiation observer
23204. It clones exact accepted97, retains unchanged VADAT/runtime/EPS and
LAST_NG94, and computes fresh BA. Ten physical steps have a21600s guard;
no new numerical remedy or physical tuning is introduced. The next Ng at114
lies beyond this nominal97→107 block if no other native adjustment occurs.

Main model SCRTEMP/T_IN hashes were rechecked unchanged. Installed source
and executables remain untouched. No final fresh convergence verification or
final saved-state probe has yet run; the new98 checkpoint is still pending.


## 2026-10-24 10:51 UTC — short resource sample during fresh98

Native90491 has ten threads, normal nice0, about271% CPU over a two-second
sample,9.55GiB resident on32GiB RAM, with10.72GiB available; system CPU57.9%,
swap used5.33GiB. The short sample neither proves active memory pressure nor
identifies the slowdown's exclusive cause. It is retained in the active case
`resource-sample-start98.json`. Normal nonfinal98 is also progressing more
slowly than the earlier block, so final-only formal output cannot be the sole
explanation. Completed first98 and warm99 timings will inform the time guard.
No active iteration budget or numerical control has been changed.

Read-only inspection also confirms CMFGEN supports live NUM_ITS edits, but
the runner deliberately treats an un-restored change to its temporary
override as a control-restoration conflict (an earlier diagnostic case retains
such a runner_error). A live budget edit must therefore not be made casually
or relabelled as native success. Current10 iterations and21600s guard remain
unchanged while actual step timings are collected.


## 2026-10-24 11:21 UTC — fresh-process98 accepted

Full/fresh-BA98 passes independent input/state checks. Raw maximum .4463662%,
T .00065911%, Ne .00029543%, zero>1%,10% or100%,43266>.02%, no negative targets.
All archived input columns match copied97, and every saved variable equals its
unlimited Newton target bitwise. Geometry unchanged, charge1.55e-15, abundance
2.11e-15. The executable SHA was rechecked6e21ede3…, matching the tested
isolated runtime. The first new process has not reintroduced the instability.

The≥.01Ne population maximum .0130823% is below EPS for every such variable;
≥1e-6Ne maximum .0414550%,22>.02%;≥1e-12Ne maximum .229808%,1465>.02%.
Scale grouping does not exclude any variable from the strict gate. Native
MAXCH .42233029% is kept distinct. First-step GIT2569.43s, CPU8516.76s, average
fG calls1.77062; a warm99 measurement is still needed for the batch forecast.
Current10 and21600s remain unchanged, and Native90491 is running99.

The complete98 capture belongs to copied97, all152174 selected T epochs
verified under the new native process identity, with complete formal-ray
frequency coverage. This first-sweep stream is new, not a continuation of the
old process's97 rays. The final saved98 has not yet had an independent no-update
probe. Further settling and final fresh verification remain required.


## 2026-10-24 11:48 UTC — warm99 accepted; time margin supports original budget

Full/variable-T/fresh-BA99 passes: raw maximum .3696363%, T .00053400%,
Ne .00021626%, no variables>1%,10% or100%,30176>.02%, no negative targets.
Unlimited Newton target equals saved99 bitwise; geometry original, charge
1.22e-15 and abundance2.33e-15. Populations initially≥.01Ne maximum .0105758%,
none>.02%;≥1e-6Ne maximum .0353343%, four>.02%;≥1e-12Ne maximum .1922984%,
761>.02%. All variables remain in the strict gate. Native MAXCH .34795720%;
latest spectrum change .0231%, outer L200908.192Lsun against200000.046Lsun.

Warm99 GIT1651.00s (~27.5min), CPU6551.38s, versus first98 2569.43s. This
supports keeping the planned ten physical iterations and21600s guard: seven
similar warm steps plus a~60min final step project~4.2hours more, within the
remaining guard with~36min margin. This is a forecast, not a guarantee; actual
progress remains monitored. No live budget or numerical input edit was made.
The same native90491 is running100.

The99 capture belongs to98; its224633 newly appended ray samples cover all
152174 frequencies with prefix SHA and selected-T epoch checks passed.
`first-and-warm-step-timing.json` retains the timing measurement.


## 2026-10-24 12:16 UTC — full100 accepted

Raw maximum .3060905%, T .00044696%, Ne .00015546%; zero>1%,10% or100%,
20702>.02%, no negative targets. Full/variable-T/fresh-BA, unlimited saved
update bitwise, original geometry, charge1.00e-15 and abundance2.89e-15.
Populations initially≥.01Ne maximum .00832570%, none>.02%;≥1e-6Ne maximum
.0309836%, only one>.02%;≥1e-12Ne maximum .1591525%,434>.02%. All variables
remain in the strict gate. Native MAXCH .28723054%, spectrum change .0182%.
Warm step1667.46s supports keeping10 and21600s unchanged. Native90491 runs101.

The100 capture belongs to99,224650 new ray samples cover all152174 frequencies,
with prefix SHA/current-T-epoch proof passing. It is not an independent probe
of saved100. Final convergence and fresh final verification remain unproven.


## 2026-10-24 13:09 UTC — full101 accepted

Raw maximum .2530594%, T .000378099%, Ne .000114923%; zero>1%,10% or100%,
11818>.02%, no negative unlimited targets. Full/variable-T/fresh-BA, saved
update equals unlimited Newton target bitwise, original geometry, charge1.55e-15
and abundance2.22e-15. Input populations≥.01Ne maximum .00640835%, none>.02%;
≥1e-6Ne maximum .0272958%, one>.02%. Every variable remains in the strict gate.
Step GIT2600.23s (~43.3min) is longer than99/100; no live budget/input edit.
Native90491 runs102. Remaining six planned solves need continued time monitoring.

The101 capture belongs to100. All152174 frequencies have new current-epoch
formal samples (224659 newly appended records), with exact prior-prefix SHA,
selected-input-T and same-process provenance checks passed. This is not a
no-update radiation verification of saved101. Final convergence remains unproven.
