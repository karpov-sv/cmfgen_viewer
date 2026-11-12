# Bstar3514 localized population instability (1 November 2026)

Investigation scope: remove the specific instability and hand back to ordinary
iteration/recovery, without attempting convergence. The original model is
`models/tests/model_Bstar3514`; native experiments use separate copies under
`models/test/`. The initial original checkpoint is record 74, not the incomplete
iteration 75 printed at the end of its imported OUTGEN.

## Baseline

The selected binary checkpoint has positive finite populations, positive T/Ne,
and maximum relative charge error 1.34337e-14. The latest local automatic attempt
was cancelled and restored this state. Imported Linux journals marked running
are historical records, not evidence of a currently executing local process.

Full solves repeatedly predict impossible negative populations near depth 31.
Iteration 71 requests a 3.54e8% decrease and has minimum major-species scale
3.4397e-4; iteration 73 requests a 7.23e7% decrease and scale 1.3935e-3. The
following fixed-T Lambda step still requests a 1346.77% increase. Emergent
luminosity is 98984.9594 versus 84000.0193 Lsun. EPS_TERM remains 0.02 percent.

Printed raw solution arrays identify He I level 5 (1s 2p singlet) at depth 31
as the largest negative target in both full solves. At checkpoint 74:

| Depth | He I ground / Ne | He I singlet 2p / Ne | He II ground / Ne |
| --- | ---: | ---: | ---: |
| 29 | 1.42492e-5 | 7.97172e-12 | 0.0796865 |
| 30 | 2.80254e-5 | 8.47972e-12 | 0.0803588 |
| 31 | 0.0776299 | 4.14547e-15 | 0.00943420 |
| 32 | 9.11773e-5 | 3.83129e-11 | 0.0806813 |
| 33 | 2.77088e-4 | 6.18755e-11 | 0.0805384 |

The single-depth neutral-helium spike grew during iteration; it is not simply
the initial seed. Raw/checkpoint audit records are retained in
`model_Bstar3514_instability_test/original-raw-audit.json` and
`original-helium-history.json`.

Superlevel temperature coupling is already enabled and BA is fresh. Existing
RELAX=0.125 covers depths 26–30. Native `FIDDLE_POP_CORRECTIONS` uses RELAX only
when its internally calculated scale is exactly one; adding depth 31 alone
therefore would not establish effective damping of its strongly scaled steps.

Both transfer sampling controls initially equal 20000. MOM_J_ERRORS records
negative raw moment intensities (r-squared J), which the native forward solver
replaces with abs(value)/10. This motivates a transfer-resolution experiment;
the diagnostic alone does not establish the cause of the helium spike.

## Fixed-temperature Lambda experiment — not promoted

Copy: `models/test/model_Bstar3514_instability_test`.
Native run: `20261101T165128Z-d4cf73bd`.

The existing population recovery primitive requested three fixed-T Lambda
solves with MAX_LAM=1e12, fresh BA, and Ng disabled. Temporary controls were
restored. No input population reseeding, atmosphere-grid change, or guard
bypass was used. The original model had no EDDFACTOR cache to copy.

The first two maximum requests declined from 321.960% to 82.6483%. At iteration
76, the existing native SCL_XLUM logic applied factor 0.1 to both X-ray filling
factors, moving 0.87437042 to 0.08743704. This is a real source transition,
not a fixed-source continuation. It forced an extra native solve: actual
completed records are 75–78, despite the three-solve request. Later maxima
were 3700% and 1.30809e11%, respectively.

The final state conserves element densities relative to checkpoint 74 to
3.33067e-15 and charge to 1.22125e-15, with exact geometry and temperature.
Nevertheless, the original spike persisted after the initial three updates
(He I ground / Ne = 0.0701664 at record 77). This experiment has not passed
the bootstrap improvement gate and is not an accepted remedy. Full evidence
is retained in `probe-result.json`, `probe-check.json`, and the native journal.

## Transfer-resolution experiment

Copy: `models/test/model_Bstar3514_transfer_test`, independently copied from
original checkpoint 74 and original inputs.
Native run: `20261101T170343Z-0c586237`.

The bounded trial requests two ordinary solves, retaining native Lambda and
temperature automation. It changes VFRAC_FG/VFRAC_MOM to 0.1, COMP_F/COMP_BA to
T, N_FIX_BA to zero and FIX_BA to 0.0. The atmosphere's 90 physical depth points,
initial populations, temperatures, abundances and luminosity safeguard remain
those of the original model. Internal transfer insertion is supported by the
installed repaired executable. Original hashes and physical baseline are in
the copy's `baseline.json`; exact trial controls are in `trial-changes.json`.

This expensive comparison was stopped before its first population solve to
concentrate resources on the targeted preconditioner below. It has no accepted
numerical result. A separate ordinary two-solve follow-up of the Lambda/X-ray
branch (`20261101T171249Z-688ec8ab`, first requested iteration 79) is likewise
cancelled before completing its first solve. Both comparison jobs are now
cancelled; neither branch was promoted.

## Conservative one-depth population preconditioning

Copy: `models/test/model_Bstar3514_helium_projection_test`.
The initial checkpoint and inputs again come from original record 74. The
restart guess is adjusted only for helium and Ne at depth 31:

1. Normalize the complete helium population vector at each neighboring depth
   by that neighbor's helium total.
2. Interpolate those positive fractions geometrically in log radius, with
   weight 0.520758393205523 between depths 30 and 32.
3. Renormalize to the original helium total at depth 31. Recompute local Ne
   from all ionic charges, keeping every other population unchanged.

T and the radius/velocity/gradient vectors are exact. Initial maximum relative
element change is 2.22045e-16 and charge error 1.22125e-15. Ne changes from
1.5506917673e10 to 1.6711316200e10 cm^-3, consistently with the revised helium
ionization. The He I ground / Ne ratio becomes 5.18822e-5. No physical parameter
or stopping tolerance is altered. The pointer/counter remains 74: preparing a
restart guess is not a native solved iteration.

`projection.json` retains the before/after values and original hashes. The
implemented generic primitive reproduces the trial's entire SCRTEMP
**byte-for-byte**, independently recorded in
`model_Bstar3514_projection_api_test/equivalence.json`.

### First ordinary native response

Run `20261101T173032Z-9dcaa29b` requests two ordinary solves and completes
75 (full/free-T/fresh BA) and 76 (native fixed-T Lambda). Native controls,
including the X-ray target/source, remain those of the original model.

The raw solutions bind the baseline failure to the outlier ion: **68 excited
He I levels plus Ne** have nonpositive unlimited targets at depth 31 in both
failing full solves 71 and 73. The He I ground-state target remains positive.
Their largest predicted decreases are 3.5357e8% and
7.2311e7%, both at He I level 5. The imported incomplete iteration-75 header
is explicitly excluded from the read-only signature replay; the imported
interrupted batch is not relabelled a successful automatic attempt.

After preconditioning, full solve 75 has **zero** nonpositive He I/Ne targets
at the repaired depth. Maximum He I/Ne decrease is 69.931%; maximum increase
is 71.626% (the singlet 2p level). The ion-fraction spike contrast falls from
790.089 to 0.4655 after the full update and 0.477931 after Lambda 76. Its stage
fraction lies between the neighboring stage fractions.

The global full-step increase is still 5.03859e7%, now associated with Ne III
variable 847 at depth 31. Its starting population is 1.00231e-9 cm^-3, only
5.99779e-20 per electron; its unlimited target is 5.05025e-4 cm^-3. This is a
trace-population filling request. The same full solve has four moderate
nonpositive excited He II targets (maximum decrease 388.33%), which remain
explicitly reported in the remedy check. Major-species scale is 0.1057,
compared with 0.0013935 in original full solve 73. The physical check after
the full step is within the established 1e-6 limits (element error 1.17597e-7,
charge 1.42475e-11).

Lambda 76 completes normally. Relative to original record 74, final element
change is 3.10862e-15 and charge error 1.33227e-15. The normalized luminosity
profile spans 0.99146–1.1792 with inner Rosseland depth 103.0. The largest
Lambda request remains 513932%, so this is far from convergence.

`first-projection-response.json` records a successful physical/local check
with **VerificationPending** because only one full response has completed.
`first-full-trace-audit.json` retains the Ne III input/target audit.

### Independent full-response verification

Run `20261101T181044Z-5ca4aaf9` completed one additional ordinary
full/free-T/fresh-BA solve, iteration 77, from the post-Lambda checkpoint.
There are again zero nonpositive unlimited He I/Ne targets at depth 31;
maximum decrease is 69.156% and increase 41.3%. The four moderate He II
failures seen at 75 are also absent. The local stage contrast is now 0.347156.
Element error is 1.99923e-9, charge error 1.74305e-13, and geometry is unchanged.
The normalized luminosity spans 0.99147–1.1789, with inner Rosseland depth 103.

`verified-projection.json` records the two successful full responses (75 and
77, separated by Lambda 76). This resolves the diagnosed instability, but
global requests still reach 76300% increase and 194% decrease. No further
native iterations were run to pursue convergence.

### Handoff to the original model

The verified record 77 and its matching native outputs/radiation cache were
transferred to `models/tests/model_Bstar3514`. Protected inputs, including
VADAT, IN_ITS, ADJUST_CORRECTIONS, structure and atomic inputs, remain
byte-identical. Replaced original files and retired original matrix caches
are preserved under:

```
.cmfgen-recovery/bstar3514-localized-population-handoff-20261101T184811Z/
```

`handoff.json` contains the file hashes and transfer audit; `evidence/` contains
the native verification and projection reports. `next-auto-check.json`
confirms a healthy continuation at 77 and finite matching radiation cache,
with no native run started. Ordinary automatic continuation can now resume
from this checkpoint without a fresh start. Luminosity remains about 17.8%
above target, so this handoff is explicitly not a convergence certification.

### Implementation and acceptance boundaries

The generic primitive is `population_projection.py`. Following the successful
native verification, `localized_population_projection` is registered as a
one-application automatic policy before population bootstrap. It requires two
fresh, free-temperature full solves in one validated invocation, each predicting
a decrease >=1e6% at the same interior depth with major-species scale <=0.01.
Invocation-scoped complete raw arrays must identify the outlier ion itself as
the offending coordinate, with at least half its levels having nonpositive
unlimited targets in both full solves. A scalar maximum alone is insufficient.

The checkpoint must be positive and charge-conserving on a fixed structure,
with supported repaired ordinary transfer and MAJOR scaling. Explicit fixed
T/Ne/impurity constraints are preserved. Exactly one ion-stage peak may qualify:
fraction >=5%, contrast >=100 over both neighbors, neighboring fractions within
a factor ten, three-depth T range <=25%, and element-density range <=4.

The later [Bstar3518 investigation](bstar3518-instability-investigation.md)
extends the contrast boundary to 50 in policy version 2; the original version-1
boundary above records the Bstar3514 trial. All other recognition and response
guards remain required.

Application recomputes the proposal from checksum-bound native data, writes an
atomic replacement, and preserves every other element/depth and the restart
counter. The controller retains its complete baseline across the provisional
procedure and invalidates radiation/BA caches. Failure, cancellation, stale
input, or insufficient verification budget restores the whole procedure.

Acceptance requires two actual full/free-T/fresh-BA responses, positive
unlimited targets for the diagnosed ion and local Ne, contrast <10, and unchanged
geometry/conserved elements/charge with the established luminosity guards.
Other ions' unlimited targets remain visible. Native Lambda steps may occur
between the full checks, within at most two two-solve verification batches.
Passing this local check does not change EPS_TERM or satisfy global convergence.

The ordinary native grey-output calculation computes TGREY for reporting; its
presence does not replace the full ordinary population/temperature solve.
Accordingly, full/free-T classification follows the ordinary solver markers,
not the presence of the grey-output diagnostic.

The read-only negative-moment diagnostic recognizes complete native compact
rows and their matching iteration/frequency footer. Truncated, stale,
untracked, nonfinite, and inconsistent evidence is rejected. Its depth indices
refer to the internal transfer grid. Regression tests cover the conservative
binary mutation, tiny representable populations, wrong-target near-matches,
complete native subprocess follow-up, read-only ordinary advice, and complete
failure/cancellation/budget rollback.

Validation: 275 affected diagnostic, recovery, policy, runner and UI tests
passed, and the application passed Python compilation checks.
