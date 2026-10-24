# Bstar3100 startup failure investigation — 24 October 2026

## Finding

The 24 October fresh startup reused a nonfinite `EDDFACTOR` cache from an
earlier failed run. `VADAT` has `COMP_F=F`. The native cache reader accepts the
file's completion marker, reads NaN mean intensities, and incorporates them
into the scattering emissivity. The outer-boundary extrapolation subsequently
traps an invalid floating-point operation. The macOS signal is `SIGILL`.

The immediate cause is confirmed by inspection of the retained binary cache,
a native cache-opening test, and an instrumented isolated startup. It is not
necessary to infer a processor-instruction incompatibility from the signal.

## Failed invocation and retained evidence

Paths below are relative to `models/test/model_Bstar3100/`:

- Automatic invocation: `.cmfgen-runs/20261024T144922Z-auto-71886488/`.
- Native child: `.cmfgen-runs/20261024T144936Z-3c204fcb/`.
- Earlier failed continuation: `.cmfgen-runs/20261023T143520Z-08dbc9ad/`.

The latest native child ran from 14:49:36 to 15:00:28 UTC on 24 October,
PID 61110, and returned `-4`. It entered iteration 1 but completed no iteration.
The automatic runner's five charged iterations are an allowance charge, not
five completed iterations. Root `RVTJ` and `MOD_SUM` are older outputs.

The matching macOS report is
`~/Library/Logs/DiagnosticReports/cmfgen_dev.exe-2026-10-24-170029.ips`.
Its executable UUID matches the installed atmosphere executable:
`2c026b70-46de-36af-b932-21b2af613a76`. Its faulting frame is
`fg_j_cmf_v13_ + 30264`. Disassembly identifies the floating-point comparison
with 3.5 following the emissivity slope calculation in
`plane/fg_j_cmf_v13.f:1059–1060`:

```fortran
ALPHA=LOG(ETA(IDMAX)/ETA(IDMIN))/LOG(R(IDMIN)/R(IDMAX))
IF(ALPHA .LT. 3.5_LDP)ALPHA=3.5_LDP
```

The build enables `-ffpe-trap=invalid`. Symbolication identifies where the
nonfinite value is detected; the cache investigation identifies its origin.

## Cache contents and propagation

`EDDFACTOR_INFO` describes 90 depths, 728-byte direct-access records,
8-byte reals and little-endian data. The retained cache has:

| Property | Value |
|---|---|
| File size | 110,792,864 bytes |
| SHA-256 | `453d869d304d491559a61e011c704e74742ee7daeb03d6168b8824af1bbbeade` |
| Modification time | 23 October 2026, 17:15:09 local time |
| Completion marker, record 5 | `1.0` |
| First radiation record | 15 |
| First frequency | `1000.0` in units of 10^15 Hz |
| Frequency records | 152,174 |
| Records with all 90 intensities NaN | 152,174 |
| Total NaN intensity values | 13,695,660 |
| Finite frequency tags | 152,174 |

This is numerical contamination of the radiation vectors, with readable
metadata and frequency tags. The native frequency-match check therefore passes.

The earlier continuation's `OUTGEN` already reports `DTDR=NaN` at iteration
119, NaN luminosities at iterations 119 and 120, and NaN opacities. It later
terminates with a separate formatting error in `wr_x_info.f`. The cache
timestamp and nonfinite contents are consistent with that failed calculation.
This investigation does not establish what first made that earlier
continuation nonfinite.

The current source path is:

1. `new_main/subs/open_rw_eddfactor.f:80–97` checks that the cache opens and
   has a nonzero completion marker. It does not check the radiation vectors
   for finite values. The native opening test leaves `COMPUTE_EDDFAC=F` for
   this cache and reads 90 nonfinite intensities from record 15.
2. `new_main/mod_subs/comp_j_blank.f:578–585` reads the cached `RJ` and checks
   its frequency tag. The tag is valid.
3. With coherent electron scattering, line 608 forms
   `TA = ETA_CLUMP + CHI_SCAT_CLUMP * RJ` and passes `TA` as the formal
   solver's emissivity. NaN `RJ` makes `TA` NaN.
4. `FG_J_CMF_V13` uses that emissivity in its logarithmic extrapolation.
   The comparison with 3.5 encounters NaN and traps.

The native fresh-start path initializes populations from `*_IN` and resets
`ITS_DONE`; it does not override the request to reuse `EDDFACTOR`.
The viewer fresh-start path in `cmfgen_viewer/runner.py` retires population
checkpoint files but does not retire the atmosphere radiation cache.

## Isolated reproduction

Diagnostic sources, executables, copied inputs, logs and cache scan results
are retained locally in `/private/tmp/bstar3100-investigation/`.
The installed CMFGEN sources/executable and original model were not modified.

The instrumented executable links the installed objects and libraries with a
diagnostic copy of `FG_J_CMF_V13`. Before the logarithmic extrapolation it
records the input emissivity, opacity, electron scattering, radius, underlying
thermal emissivity and `RJ`, and deliberately stops if emissivity is invalid.

`poisoned-cache-fast/` uses the failed native child's saved inputs and a copy
of the retained `EDDFACTOR` and its metadata. `NUM_ITS=1` bounds the run and
`IT_ON_T=F` skips the expensive initial temperature iteration. These changes
make this a targeted cache-path reproduction rather than an exact repetition
of the entire failed startup.

It reaches the same native state marker `T 15 F`, then the first formal-solver
call at frequency 1000, with `IDMIN=1`, `IDMAX=8` and 24 added outer points.
All 90 total-emissivity entries and all 90 cached `RJ` entries are NaN.
The thermal emissivity is finite at `1e-280`; opacity and radius are finite.
At depth 1, scattering opacity is `5.952604740743877e-11` and radius is
`4.821545682222801e4`. The instrument deliberately exits with `STOP 86`
before executing the invalid logarithmic calculation.

This directly establishes the cached-radiation origin of the invalid
emissivity. The earlier hypothesis of a zero/underflowed emissivity ratio is
not the trigger demonstrated for this run.

The paired `recomputed-cache-fast/` control uses the same saved startup inputs,
`NUM_ITS=1` and `IT_ON_T=F`, but has `COMP_F=T` and no copied radiation cache.
It reaches `T 15 T`, completes four formal-solver calls, and deliberately stops
at entry to the fifth (`STOP 87`). All 90 emissivities and all 90 `RJ` values
are finite at each of those five entries. The sampled frequencies are 1000
and 999.3328718096037. The first call's minimum emissivity is `1e-280`; after
the scattering iterations it remains finite and positive. Thus the control
passes the point where cache reuse fails, including its repeated scattering
solves. This is a bounded startup check, not a completed model iteration.

## Separate controller reporting problem

The automatic result reports
`Structure controls changed without completed native hydro evidence`.
The only observed `HYDRO_DEFAULTS` change is `ITS_DONE: 2 -> 0`, explicitly
announced by native fresh initialization in `OUTGEN`. There is no completed
hydro revision. `auto_hydro.native_updates` rejects this fresh-start reset
and masks the more useful native failure in the top-level reason.

This reporting problem is separate from the NaN radiation cache.

## Recommended corrections and limits

- Preserve the contaminated cache as evidence, then regenerate the atmosphere
  radiation field with `COMP_F=T`. Review other retained restart caches before
  reuse; `BAMAT` and `BAMATPNT` also predate the fresh invocation, although this
  investigation does not establish their numerical contents as the crash cause.
- Have preflight identify nonfinite radiation caches when a run requests their
  reuse. Fresh population initialization should retire incompatible radiation
  caches or explicitly arrange recomputation.
- Reject nonfinite cached radiation values in native readers with a useful
  filename, record/frequency and depth diagnostic. A downstream formal-solver
  guard can provide additional context. Replacing NaNs with an emissivity floor
  would conceal the invalid radiation state.
- Recognize the narrowly verified native `ITS_DONE` reset during fresh startup
  so that the automatic runner preserves the native failure as its primary
  explanation.

Cache regeneration addresses the demonstrated startup failure mechanism.
It does not establish subsequent model convergence or explain the original
nonfinite state in the older continuation. No production fix, original-model
edit, full convergence run or commit was performed during this investigation.

## Generic automatic remedy

The viewer now implements a preparation policy for this failure class, described
in [automatic convergence policies](automatic-convergence-policies.md#nonfinite-radiation-cache-preparation).
It detects nonfinite records in recognized caches requested for reuse, preserves
the evidence and enables radiation recomputation before launching native code.
It also handles the verified fresh-start counter reset. These are viewer changes;
the installed CMFGEN source and this original model remain untouched.

Validation: 222 automatic-recovery tests passed, followed by the final expanded
33-test radiation-cache module. All three documentation tests, compile checks,
and listing/parser-page/documentation smoke checks passed. The original cache
was assessed read-only by the new policy and its recorded SHA-256 matched.
