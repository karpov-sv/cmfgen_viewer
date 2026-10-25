# Actual positive-J / capped-H counterexample

This is original recorder record126, now retained as record1. At frequency
5.9407647040489984 ×10^15 Hz all125 raw J values are positive. Five midpoint
fluxes are capped by the native default `CHK_H=MAX_VAL` (no override in VADAT).

The native current-emissivity derivative of J agrees with finite differences.
The corresponding derivative of r²H at midpoint33 does not:

| Derivative w.r.t. ETA(33) | Native variation | Forward finite difference |
| --- | ---: | ---: |
| J(33) | +25.3324874652 | +25.3324874652 |
| r²H(33) | -5,814,002.2543 | +12,514,581.0355 |

Relative perturbations1e-2,1e-3,1e-4,1e-5 reproduce the disagreement. The
reconstructed capped H values agree with native stored history; reconstruction
across95 frequency transitions in the parent observer agrees to1.4e-13 relative
on interior midpoints. This is an active forward branch, not an assumed cap.

`replay_current_h.f90` extends the parent native replay with the same native H
expression and cap. Compile against the compatible source tree and run here:

```sh
gfortran -fopenmp -O -ffree-line-length-none \
  -I/home/karpov/CMFGEN2023/cur_cmf.25/mod replay_current_h.f90 \
  -L/home/karpov/CMFGEN2023/cur_cmf.25/lib -lsubs -lmod -llapack -lblas \
  -o /tmp/bstar3010-replay-h
/tmp/bstar3010-replay-h 1 33
```

`replay_chain_rule.f90` additionally applies the analytic chain rule to the
native current-ETA derivative: multiply negative-J rows by-0.1 before computing
H variations, then differentiate the signed0.99999 × maximum(r²J) branch where
H is capped. Compile it with the same flags and run record1/depth33.
`chain-rule-replay.log` retains the result. The corrected whole-column J/H
responses agree with independent RHS/THOMAS finite differences at the1e-11 and
3e-9 levels for perturbation1e-2. Smaller perturbations encounter more subtractive
cancellation. A matching negative-J chain-rule log is in the parent directory.

This diagnostic correction covers the current-emissivity partial only. It is
**not** a complete replacement variation kernel: opacity derivatives, earlier
frequency histories, diffusion derivatives, refined-grid composition and other
transport families require consistent treatment and separate tests. Installed
CMFGEN sources and executable were not patched during this investigation.
