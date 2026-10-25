# Actual Bstar3010 negative-J derivative reproducer

One native coefficient record from checkpoint86's first radiation sweep, at
frequency5.940069672129668 ×10^15Hz. All125 depths, native angular factors,
previous-frequency J/H, opacity/emissivity, and the unfactored transport matrix
are retained. The main model was unchanged. The instrumented probe stopped
before any population update.

`replay_current_eta.f90` links the actual CMFGEN variation kernel and THOMAS
solver. It holds angular factors, current opacity/scattering and frequency
history fixed, changes current emissivity through its exact native RHS term,
and evaluates the forward `abs(J)/10` replacement. This is the relevant partial
of the frozen-angular-factor Newton operator, not a derivative of a new ray
calculation. The native analytic derivative is computed independently by
`VAR_MOM_J_CMF_V12`. Only the profiling hook TUNE is stubbed.

On the recorded negative depth33 field, finite differences give -2.98070679
versus native +29.80706790, consistently across relative perturbations
1e-2,1e-3,1e-4,1e-5. At positive depth35 the local finite difference and analytic
derivative agree. Other rows of that control column can still encounter
negative-J repairs; the entire column is not claimed correct.

To reproduce against the compatible local source build, compile in this folder
(or a scratch copy), then run the retained record1 at source depths33 and35:

```sh
gfortran -fopenmp -O -ffree-line-length-none \
  -I/home/karpov/CMFGEN2023/cur_cmf.25/mod replay_current_eta.f90 \
  -L/home/karpov/CMFGEN2023/cur_cmf.25/lib -lsubs -lmod -llapack -lblas \
  -o /tmp/bstar3010-replay-eta
/tmp/bstar3010-replay-eta 1 33
/tmp/bstar3010-replay-eta 1 35
```

The retained logs used original stream record130; the extracted file contains
only that record, now numbered1. Provenance and the binary schema are in
`manifest.json`. Populations, stellar parameters, atomic rates and installed
code were not changed to construct this counterexample.

A second independent counterexample, with all J positive but active H caps, is
retained in [h-clamp](h-clamp/README.md). It also documents a diagnostic chain-rule
correction that recovers the current-emissivity partial for both cases. This is
not a complete solver patch.
