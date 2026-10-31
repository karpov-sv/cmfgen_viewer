# Audit of related CMFGEN moment and variation paths

24 October 2026. Audited the patched source snapshot after commit
`4d85f58`, following the [inserted-grid repair](cmfgen-inserted-moment-grid.md).
The findings below describe that audited source snapshot. Their subsequent
repairs and validation are recorded in [related moment repairs](cmfgen-related-moment-repairs.md);
this historical report is not the current installation inventory.

## Findings and priority

| Priority | Path | Finding | Evidence |
|---|---|---|---|
| 1 | Ordinary nonrelativistic variation, without inserted moments | The alternate outer boundary and zero-flux stabilization derivatives still differ from the forward equations. The `LOGMON` optical-depth derivative retains its boundary/limiter approximation. | Reproduced with finite differences against the installed native archive. These were deliberately left unchanged in fix 19 to preserve the no-insertion path. |
| 2 | Relativistic moment solver and variation | `MOM_JREL_V9` can insert points and populate shared angular arrays on that grid; `VAR_JREL_V5` still receives model radii and ND. | Confirmed producer/consumer grid mismatch in the active source path; no full relativistic atmosphere run performed. |
| 2 | `CONT_VEL` with `ACCURATE` (`INC_GRID=T`) | A second internal refinement can occur inside `MOM_J_CMF_V11`, beyond the existing extended grid. `VAR_MOM_JEXT_CMF_V3` receives only that earlier extended grid and reads the angular-array prefix. | Confirmed active caller/callee mismatch. The new `DO_VAR_CONT` dispatcher is confined to `.NOT.ACCURATE`. |
| 2 | Relativistic angular-factor interpolation | Stored/requested grid sizes and midpoint initialization are not handled consistently. | Three direct native bounds failures and one signaling-NaN trap. Some cases are masked by current production callers; see below. |
| 3 | Original `UP_TX_TVX` / `UP_TX_TVX_V2` | First-frequency OpenMP private history storage is read without initialization. | Confirmed undefined read by source inspection; no production nondeterminism quantified. The new rectangular updater already initializes its private copy. |
| Investigate | Time-dependent/homologous `MOM_J_DDT_V6` / `VAR_MOM_J_DDT_V6` | Forward transport can use an internally refined grid while variation reconstructs a coarse-grid operator. | Candidate consistency problem; requires native finite differences. It does **not** use the same shared-angular-array prefix mechanism. |

## 1. Unrefined boundary and optical-depth derivatives

The installed regression fixture was linked directly to `libsubs.a`, using
`VFRAC_MOM=20000`, seven model depths, coherent scattering, `G_ONLY`, frozen
formal-ray factors, peaked positive profiles and three frequencies. Central
finite differences used a fractional step of `2^-14`. The zero-flux case uses
`IB_STAB_FACTOR=100`, as prescribed by the fixture; this is not a claim about
the default setting. Current opacity,
emissivity and prior-frequency opacity responses were sampled at all depths.

| Case | Maximum derivative-column relative error |
|---|---:|
| Point-source inner boundary, default outer boundary, `ZERO` | 3.99e-6 |
| Point-source inner boundary, alternate outer boundary, `ZERO` | 1.30 — contaminated by active negative-J fallback; excluded as a Jacobian measurement |
| Zero-flux inner boundary, default outer boundary, `ZERO` | 0.0530 |
| Diffusion inner boundary, default outer boundary, `ZERO` | 1.58e-06 |
| Diffusion inner boundary, default outer boundary, `LOGMON` | 0.463 |

The normalization is the maximum absolute column difference divided by the
larger maximum absolute value of the numerical and analytic columns. Except for the alternate-boundary case, these
numbers measure an approximate-Jacobian discrepancy in synthetic cases; they
are **not** percentages of error in a stellar atmosphere or its emergent flux.

**25 October correction:** the alternate-boundary profile activates native
`ABS(J)/10` repair of a negative solution. Its 1.30 result cannot isolate the
boundary Jacobian and is not evidence for differentiating that clipping. The
boundary source defects were independently confirmed and repaired using opaque,
positive, unclipped cases. No derivative through active clipping is claimed.

Source locations in the installed checkout:

- `subs/edd_j_var_v6.f:185–229`: old alternate-boundary derivative, including
  half-spacing instead of the forward quarter-spacing, the HBC sign, and the
  second-column update using the first-column value.
- `subs/up_tx_tvx_v2.f:133`: the `G_ONLY` recurrence does not select the
  alternate outer-boundary equation.
- `plane/var_mom_j_cmf_v12.f:266` and `subs/edd_j_var_v6.f:231`: the forward
  zero-flux stabilizer is absent from the old opacity derivative.
- `subs/nordtau.f:224` and `subs/nordtau.f:362`: derivative construction and
  the explicitly documented boundary-slope approximation. The limited-slope
  derivative also needs comparison with the actual forward limiter.

The separate refined entries contain the tested corrections. A follow-up should
validate and extend those corrections to the ordinary path, retaining its
forward transport. The unrefined `LOGMON` case affects a commonly used transport method. This
synthetic error measurement does not establish the error on a particular
atmosphere or contradict an independently observed convergence trend.

## 2. Relativistic grid handoff

`new_main/mod_subs/comp_j_blank.f:701` calls `MOM_JREL_V9`.
`plane/mom_jrel_v9.f:368–375` computes an expanded ND, and line 518 calls
`GET_MOMS_REL` with the expanded radii. The routine later samples radiation back
at the model locations but leaves the shared factors on the expanded grid.

`new_main/mod_subs/do_var_cont.f:349` calls `VAR_JREL_V5` with the original
`R` and `ND`. That routine imports `MOD_RAY_MOM_STORE` and uses its factors with
those original radii. The producer/consumer dimensions therefore have the same
incompatibility as the repaired nonrelativistic path.

The forward source already prints a warning that inserting points can affect
convergence. That warning is not a repair. A complete remedy needs a relativistic
fine-grid response and frequency history; copying the nonrelativistic formulas
or merely remapping the angular factors would be insufficient.

## 3. The extended-grid path has two refinement layers

`comp_j_blank.f:372` supplies `REXT/NDEXT` to `MOM_J_CMF_V11`. The latter can add
its own velocity-spacing points. `do_var_cont.f:627` subsequently calls
`VAR_MOM_JEXT_CMF_V3` with `REXT/NDEXT`, not the final moment grid. That variation
routine reads shared `K_ON_J` and `NMID_*` arrays directly.

The existing rectangular dimensions `(NDEXT, ND_model)` address the first,
explicitly extended grid; they do not account for the additional internal moment
grid. Its `FIX_dCHI` reduction likewise maps only the first extension.

Additional source findings in this branch:

- `var_mom_jext_cmf_v3.f:251` builds `WPREV` using current
  `NMID_ON_HMID`, whereas the corresponding forward history requires the
  previous-frequency factor. This matters for `G_ONLY` or mixed G components.
- Its interface supplies `DIF` and `IC`, but lacks the modern inner-boundary
  method, stabilization and outer-boundary selection used by the forward
  solver. Some nondefault combinations therefore cannot have matching equations.
- `NV=200` is an explicit limit with a guard, not an unchecked buffer overflow.

This needs an independently tested composition of both interpolation maps and
fine-grid history, rather than routing the existing extended arrays through the
new single-extension call unchanged.

## 4. Direct `GET_MOMS_REL` failures

The actual routine was compiled with `-O0 -g -fcheck=all -finit-real=snan` and
floating-point traps. Prescribed finite positive ray moments were supplied.

| Input | Observed failure |
|---|---|
| 13 stored ray points, 7 requested points, nodal H/N | `TMP_VEC(1:13)` exceeds its allocated upper bound 8, line 70. |
| Request grows from 7 to 13 points in a second direct call | `RMID(8)` exceeds its allocated upper bound 7, line 59. |
| 7 stored points, 13 requested points, midpoint H/N | `GRSQ(ND)` uses index 13 for a 7-element stored-grid array, line 118. |
| 7 stored/requested points, midpoint H/N | Local `RSQ_HNU_MID` is read before assignment, line 120; the signaling-NaN test traps there. |

There is a corresponding uninitialized N-moment read at line 124. Those local
moments are only calculated later in the midpoint branch.

Reachability matters: the current `CMF_FORMAL_REL_V5` producer sets
`HN_DEF_ON_NODES=.TRUE.` at line 679, so it masks the midpoint defects in its
normal configuration. `USE_FRM_REL` can select a different formal solver. A
helper request-size change is also distinct from normal model execution:
`ALLOC_MOD_JREL_V9` explicitly refuses changed allocation size before the
forward solver proceeds. A native check confirmed that refusal; it is not a
silent allocator overflow. The direct-call tests establish helper defects, not
that every ordinary relativistic run encounters them.

## 5. Frequency-history initialization

Both `subs/up_tx_tvx.f` and the original entry in `subs/up_tx_tvx_v2.f` initialize
`OLD_TX` before an OpenMP loop declaring it `PRIVATE`. That initialization does
not initialize the per-thread copies. With `INIT=T`, the loop skips copying
previous TX into those copies, but its epsilon branch later reads them.
Multiplication by a nominally zero previous-frequency coefficient does not make
an undefined read valid or guarantee protection from NaNs.

`VAR_JREL_V5` and `PP_VAR_MOM_CMF_V1` call the original updater; ordinary
`VAR_MOM_J_CMF_V12` calls V2. The new `UP_TX_TVX_GRID_V1` already initializes
its private buffer inside the loop. The older helpers need the same limited
repair and threaded initialization tests. This audit has not demonstrated a
production crash attributable to this read.

## Other branches and next steps

`MOM_J_DDT_V6` interpolates supplied F onto an internal refined grid, while
`VAR_MOM_J_DDT_V6` takes an explicit F array and rebuilds its operator at the
caller ND. This deserves time-dependent finite-difference tests, but should not
be reported as the identical shared-array indexing bug. Similarly, the
plane-parallel routines take explicit angular factors and do not have this
hidden moment-grid prefix handoff; they do share the old updater above.

Recommended order: validate the ordinary optical-depth/boundary derivatives and
private-history initialization first, then repair and test the relativistic
helper and grid handoff, followed by the two-level extended-grid path. Test DDT
with its own temporal and boundary terms rather than extrapolating formulas.

Assess reachability from the selected transport family, sampling and boundary
controls. For example, `INC_GRID=F`, `VFRAC_MOM=20000`, a diffusion inner boundary
and ordinary `METHOD=LOGMON` do not exercise relativistic or alternate-boundary
paths. An audit finding on an unused path alone does not warrant model changes.

## Reproduce

```sh
python doc/developer/cmfgen-review-tests/check_related_moment_paths.py --cmfgen-root /path/to/cur_cmf
```

The driver reports observations, not success of a source repair. It builds only
in a temporary directory and requires NumPy, the installed moment-grid repair,
and compiler-compatible native modules/libraries. It emits source hashes, build
commands, bounds/trap logs and finite-difference results. Historical artifact
locations are retained in the [patch manifest](patches/cmfgen-current.json).
