# Bstar3518 coupled convergence acceleration — 14 November 2026

Continued investigation after committing the computational reuse remedy as
`3c102dc`. The original production copy remains at checkpoint 310, unchanged.
The aim here is fewer ordinary solves for a given reduction of the thermal error.

Result: the coupled extrapolation passes six ordinary full solves and an
independent saved-state radiation audit. At saved 316, absolute RE residual is
17.61% below saved 310 and maximum normalized luminosity deviation is 16.63%
lower. This is actual state acceleration, separate from the earlier BA-reuse
timing improvement. Automatic selection is implemented under `global_ng`
version 3, with the existing acceptance, rollback, receipt and cooldown guards.

## Candidate

The previous four-state global geometric fit improves radiation balance but
its first native response has a 27.9% population correction, chiefly OSIX at
depth 55, outside the dominant deep thermal residual. That exceeds the existing
2.30% transient guard. The fitted coefficients are large and cancel strongly;
an extrapolation along the latest observed coupled step avoids that curvature fit.

For every population and temperature coordinate, construct

`log(seed) = log(state310) + 64 * (log(state310) - log(state309))`.

Renormalize each element to its original total and recompute Ne from charge.
All populations participate, including tiny trace ions; none is floored or
excluded. Geometry, native counters, control inputs and stopping tolerances
remain unchanged. Four saved states still verify the common physical regime.
The reusable constructor backs off the common integer factor from 64 by powers
of two if ratios leave 0.1–10 or T changes exceed 0.25%. This case retains factor
64, coordinate ratios 0.476750–1.054382, and maximum T change 0.214415%.
Element-density and charge errors are 2.66e-15 and zero. A read-only replay of
the reusable implementation matches the laboratory seed byte-for-byte, while
the existing four-state proposal remains exactly unchanged.

## Native screen and verification protocol

The isolated branch is `models/test/model_Bstar3518_secant64_310`. A native
fresh-radiation calculation with zero population solves preserves the seeded
checkpoint exactly and all 56 protected input hashes. It measures:

| Saved-state radiation diagnostic | Original 310 | Coupled proposal | Reduction |
| --- | ---: | ---: | ---: |
| Absolute RE residual (Lsun) | 3455.3383 | 2991.6877 | 13.42% |
| Maximum normalized luminosity deviation | 4.21% | 3.57% | 15.20% |
| Inner Rosseland depth | 95.94 | 96.05 | — |

This is a proposed restart state, with no convergence or native iteration credit.
It remains provisional until ordinary solves demonstrate a retained gain.
The selected branch requests three pairs of full/free-T/fresh-BA solves with
native Ng and automatic Lambda/T switching temporarily disabled. Each pair
uses the existing global trial validator: maximum uncapped correction at most
2.30%, physical conservation and luminosity guards, exactly consecutive native
counters, and no source/grid/hydro transitions. Final acceptance also requires
settled corrections below the starting 1.15%, nonworsening significant counts,
and at least 10% reduction in both absolute RE residual and profile deviation.
An independent zero-solve saved-endpoint audit follows a successful trial.

The full response test started at 17:45 UTC. During verification, no automatic
policy selected the new constructor. Evidence, reproducible scripts, proposal arrays, native
plans and per-pair results are in `output/bstar3518-acceleration/`.

The first full response completes at saved 311 with native metric 1.134314%
and maximum raw decrease 2.02% (depth 55). This passes the unchanged 2.30%
transient limit; the earlier four-state proposal produced 27.9% there. It is
an interim response, not acceptance of the coupled proposal.

The first pair passes all interim guards at saved 312. Uncapped maxima settle
from 2.02% to 1.15%; the last ordinary forward calculation has absolute RE
residual 2,886.7352 Lsun and profile deviation 3.56%. Element-density and charge
errors are 3.33e-15 and 1.22e-15. This forward residual precedes the final update.
The saved 312 endpoint is copied with authenticated restart hashes for a later
independent radiation audit and comparison against ordinary saved 312.
Four further full solves remain required before acceptance.

The third full solve settles further to raw maximum 1.14% and native metric
1.011877%, both below the original corresponding values. The six-solve trial
and independent saved-state audits are still in progress.

The second pair also passes its interim checks at saved 314. Raw maxima are
1.14% and 1.07%; native metrics are 1.011877% and 0.961633%. Counts above 1%
fall to 2 and above 0.1% to 33,069. The last forward residual is 2,869.8913 Lsun,
profile deviation 3.54%, with element-density/charge errors 3.11e-15/9.99e-16.
Only the final pair and independent endpoint audits remain.

All six full solves finish at saved 316 and the unchanged global validator
accepts the trial. The last pair's raw maxima are 1.12% and 1.03%, below the
starting 1.15% and settling within the pair; native metrics are 0.983243% and
0.931779%. Counts above 1% fall from 15 to 1, and above 0.1% from 38,346 to
32,822. The final pre-update forward residual is 2,854.5233 Lsun and profile
deviation 3.52%, with element-density/charge errors 2.66e-15/8.88e-16.
No native correction, count, conservation or thermal acceptance threshold was
relaxed.

## Independent saved-state confirmation

The native radiation-only audit at saved 316 counts zero population solves.
The complete SCRTEMP and pointer hashes, decoded physical state, and all 56
protected inputs remain unchanged. It measures absolute RE residual
**2,846.8564 Lsun**, normalized luminosity 1.0–1.0351, and inner Rosseland depth
96.06. Compared with saved 310, the residual fraction remaining is 0.8239009
and the profile-deviation fraction remaining is 0.8337292. Element densities
and charge agree within 2.66e-15 and 8.88e-16, with identical geometry.

| Fresh saved-state audit | Full solves after 310 | Absolute RE (Lsun) | Profile deviation |
| --- | ---: | ---: | ---: |
| Original 310 | 0 | 3455.3383 | 4.21% |
| Ordinary control 312 | 2 | 3437.7765 | 4.19% |
| Coupled extrapolation 312 | 2 | 2877.5806 | 3.55% |
| Coupled extrapolation 316 | 6 | 2846.8564 | 3.51% |

The native correction sequence is 2.02%, 1.15%, 1.14%, 1.07%, 1.12%, 1.03%.
The last pair settles below the starting 1.15%; the intermediate small rebound
is retained in the record. The independent preserved-312 audit also passes,
with unchanged complete restart and protected-input hashes. After the same
two full solves, the accelerated branch has **16.30% less remaining absolute
RE residual** and **15.27% less profile deviation** than ordinary continuation.
Relative to original 310, two ordinary solves remove 0.51% of the absolute
residual, whereas the conserved extrapolation plus two solves removes 16.72%.
This is a bounded state advance, not a universal steady-rate multiplier.

## Automatic remedy

`global_ng` version 3 selects the coupled secant constructor for normalized
profile errors from 2% to below 5%. At 5% and above, the validated four-state
global fit remains unchanged. The new branch still needs the same six observed
healthy ordinary solves, a persistent surface-flux error at least 2%, fixed
structure and supported solver settings, and a severely limited rejected
native affine proposal. It retains the existing six full follow-up solves,
transient bound, final significant-count and 10% dual-thermal-merit checks,
rollback, eight-ordinary-solve cooldown, three-application budget and resumable
provisional trial protocol. Both variants share checkpoint attempt receipts;
switching variants cannot retry an identical restored checkpoint.

A read-only replay of the actual copied 304/310 evidence through the complete
policy chooser selects `global_ng`, coupled secant kind, factor 64 at 310.
This establishes numerical eligibility; automatic startup still requires
authenticated accepted history or fresh ordinary observations. It does not
bypass the stale historical receipt in this copied mid-run model.

The original selected checkpoint remains 310, with SCRTEMP SHA-256
`4771e123398b11584568f997fbb463ae473a76c00befa7cc0a9e907735016480`.
All original proposal-input hashes and 56 protected inputs remain unchanged.
The reusable constructor exactly replays the tested seed, and the old
four-state proposal at 310 remains identical. No experiment checkpoint is
promoted, no installed native solver is modified, and no convergence credit
is assigned to the extrapolation. Independent final convergence verification
remains required. The native Jacobian's ordinary slow-mode rate is not repaired;
the remedy bypasses part of that mode with a guarded coupled state advance.

## Validation

220 focused tests pass across global reconstruction, automatic selection and
acceptance, bounded fallback, accepted history, rollback and trial resumption.
New coverage includes coupled-secant conservation/tiny populations/common
backoff, exact publication and staging faults, malformed/tampered descriptors,
shared receipts across variants, the 2%/5% selection boundaries, and interrupted
success/rejection without reapplying the seed. Compilation and `git diff --check`
pass. The native six-solve validator and both independent saved-state audits
pass. Only code and documentation are promoted; the original model is untouched.
