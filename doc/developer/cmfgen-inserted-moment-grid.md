# Inserted moment grids: transport and Jacobian repair

The repair is installed in `~/CMFGEN2023/cur_cmf/` and included in
[cmfgen-current.patch](patches/cmfgen-current.patch). It corrects the
nonrelativistic spherical continuum-velocity path when `MOM_J_CMF_V11` inserts
points between the model depths. Models without inserted moment points retain
the previous numerical path. This is fix 19 in the
[consolidated source record](cmfgen-source-fixes.md).

## Cause

The forward moment solver evaluates its angular factors on an internal grid
with more points than the atmosphere. `GET_MOMS_NON_REL` leaves those factors
in shared arrays. Previously, `DO_VAR_CONT` called `VAR_MOM_J_CMF_V12` with the
original atmosphere radii and depth count, so the latter read the *prefix* of
the refined arrays as if it belonged to the atmosphere. The radii did not
match. The same indexing defect was found in the mid-2023 source.

On the original Bstar3502 geometry, a 90-point atmosphere produced 178 moment
points. Reading the first 90 angular factors gave a maximum K/J mismatch of
about 0.478. Disabling insertion with `VFRAC_MOM=20000` avoided this error.

Simply recomputing the factors on the atmosphere grid is insufficient: the
resulting coarse-grid variation is still not the derivative of the refined
forward solve. An isolated candidate using that approach failed finite
differences and was excluded from the installed patch.

## Implemented repair

The refined path now retains response rows on the **moment grid** and parameter
columns on the **atmosphere grid**. It differentiates the same log-radius,
log-value monotonic interpolation used by the forward solver, solves the
variation equations on the refined grid, and samples the resulting J and H
responses at the original model locations. The frequency history stays on the
refined grid until it has been propagated; projecting history too early would
lose responses at inserted points.

The production wrapper applies its existing continuum-frequency scaling,
clumping, overlapping-line transformations and superlevel temperature terms to
these rectangular arrays. Reusing a line-variable slot clears its refined
history as well as its model-grid storage. Coherent electron scattering gets
its own interpolation response: interpolating electron-scattering opacity and
then multiplying by fine-grid J cannot generally be replaced by multiplying a
model-grid emissivity derivative by model-grid J.

Finite-difference tests also exposed derivative inconsistencies that must be
corrected for the refined path to represent the forward equations:

- The optical-depth derivative now follows the actual limited slopes and
  quadrature, including their endpoint dependencies.
- The alternate outer boundary uses the forward equation's quarter-spacing
  coefficient, correct HBC sign, independent first/second opacity columns,
  and separate current/previous-frequency epsilon factors.
- The outer-boundary frequency recurrence is used even for `G_ONLY`, and for
  diffusion temperature/gradient responses.
- The zero-flux inner-boundary derivative includes its stabilization term.

These derivative corrections use separate refined-grid entries; the original
no-insertion entries are unchanged. Angular-factor interpolation work storage
also accommodates a stored ray grid larger than the requested grid, including
midpoint endpoint padding. Variation work arrays resize when refinement changes
between independently initialized sweeps. Makefile dependencies ensure the
persistent response module exists before its callers are compiled.

## Validation

The native driver compiles the actual transport, variation, interpolation,
quadrature and linear-algebra code. Only the profiling hook is stubbed.
A second fixture compiles the actual `DO_VAR_CONT` prefix through its final
projection; the later atomic-rate assembly is explicitly excluded. The complete
production routine and its line-slot caller are also compiled, and all three
installed executables were rebuilt and relinked against the final archives.

| Check | Bounds-checked O0, 1 thread | Bounds-checked O2, 5 threads |
|---|---:|---:|
| Forward-transport comparisons against the previous source | 64 bit-for-bit matches | 64 bit-for-bit matches |
| No-insertion radiation, Jacobian and diffusion-vector comparisons | 64 bit-for-bit matches | 64 bit-for-bit matches |
| Maximum relative J/H disagreement between forward and variation solves | 5.25e-14 | 3.81e-14 |
| Maximum finite-difference column error, refined kernel | 6.64e-6 | 1.50e-5 |
| Maximum finite-difference column error, production wrapper | 1.62e-7 | 1.62e-7 |

The error is the maximum absolute difference within a derivative column divided
by the larger maximum absolute value of the numerical and analytic columns.
The acceptance threshold is 3e-5. Each configuration makes 607 kernel and 680
wrapper native invocations, plus the baseline comparisons.

A separate regression linked directly against the installed `libsubs.a` also
passed (543 native invocations; maximum column error 7.96e-6). The recovery and
documentation test suites passed all 21 tests. Installed source, executable and
patch hashes were checked again before committing the repair.

Coverage includes `G_ONLY` and `N_ON_J`, nodal and midpoint stored rays, both
outer-boundary types, point-source/zero-flux/diffusion/Schuster inner boundaries,
coherent and noncoherent scattering, peaked profiles that exercise interpolation
limiters, all six optical-depth methods (`ZERO`, `LOGMON`, `LINMON`, `LINEAR`,
`LOGLIN`, `LOGLOG`), current opacity/emissivity/scattering columns, previous-frequency
history, and diffusion boundary derivatives. Tests include 31- and 259-point
moment grids, same-frequency radiation subiterations, changed refinement between
initialized sweeps, line-slot reuse, nonuniform clumping, line-level responses,
and superlevel temperature responses.

These are derivatives with **frozen formal-ray angular factors**, as required by
this approximate Newton operator. They do not assert differentiation through the
formal-ray iteration or active radiation clipping, validate `N_TYPE=MIXED`, or
establish a new full-atmosphere convergence result. The already unsupported
mixed-coherency variation (`MIX_COH` with noncoherent scattering) is explicitly
refused on the refined path rather than silently using an inconsistent source.
The experimental log-radius `QFROMF` integration remains excluded.

Reproduce on an installed, built checkout:

```sh
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py
python doc/developer/cmfgen-review-tests/check_moment_grid_jacobian.py --optimization O2 --threads 5
```

NumPy and a compatible Fortran compiler, installed modules and libraries are
required. `--source-root` accepts an isolated edited source tree;
`--baseline-root` additionally enables the bit-for-bit comparisons. Every run
uses its own build directory and writes a JSON report and build commands.

Local evidence and rollback products are in
`models/test/.model_Bstar3502-diagnostics/moment-grid-fix-v1/`:
`validation-workflow/report.json`, `validation-o2-five/report.json`,
`installation.json`, and `installed-before/`. The consolidated patch was applied
in a fresh directory outside the viewer Git worktree and all 35 resulting source
files matched the installed checkout byte for byte.

## Workflow behavior

The authenticated build capability is `moment-grid-jacobian-v1`. Automatic
formal-ray refinement can now preserve an already inserted moment grid when the
executable hash and this capability match its build record. Unpatched or
unidentified executables remain declined for that case. Recovery still requires
its existing luminosity, structure and continuation checks and never changes
`VFRAC_MOM` itself.

The main `model_Bstar3502` checkpoint, controls and `VFRAC_MOM=20000` are unchanged.
There is no reason to refine a steadily converging model solely because the
option is repaired. If a scientific comparison is wanted, use an independent
copy, change only `VFRAC_MOM`, recompute BA and radiation caches, and compare
physical diagnostics as well as correction sizes.

The subsequent [related-path audit](cmfgen-related-moment-paths-audit.md) identified
counterparts in ordinary boundary derivatives, relativistic, time-dependent,
and separately extended transport. The [25 October follow-up](cmfgen-related-moment-repairs.md)
repairs those paths and supersedes fix 19's preservation of the old unrefined
Jacobian. Nonrelativistic forward transport remains unchanged; the newer build
capability is `moment-grid-family-v1`.
