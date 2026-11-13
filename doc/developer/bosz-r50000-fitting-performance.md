# BOSZ R=50000 optical fitting performance

Investigation on 2026-11-13 using the local upload
`HD36030_220217_total_cont.fts` and the **Optical wind + photosphere** preset.
The uploaded file was read without modification. No imported grid was changed.

## Reproduction

- Upload: 131,849 normalized samples, air wavelengths 3963.88–8746.71 Å.
- Preset: default source redshift zero and ±3000 km/s half-width, giving five
  windows after merging overlapping He I 4471 and He II 4542 intervals.
- Selected observed samples: 17,179; the existing optimizer limit selects 5,000.
- Fit bounds: redshift −0.02 to +0.02, additional Gaussian σ 0–800 km/s.
- Models: ATLAS9, log g=4, solar metallicity, alpha/carbon enhancement zero,
  microturbulence 2 km/s, temperatures 7500, 10000 and 16000 K.

These settings reconstruct the preset defaults; they do not recover any edited
browser-local window settings or a previous in-memory fit job.

## Cause

Every BOSZ spectrum has 750,000 samples from 500 Å to 32 μm. Published wavelength
rounding and conversion from air to vacuum make the axis nonuniform in log λ.
The existing fit crop only handles uniform logarithmic axes: changing a
nonuniform axis's endpoints or length would change the temporary convolution
lattice and the resulting predictions.

Consequently, optical residual evaluations repeatedly broadened and interpolated
all 750,000 model samples. A profile of the 10000 K candidate took 2.35 seconds;
2.14 seconds were inside the fitting function, predominantly transformations.
Loading and preparing the model accounted for approximately 0.20 seconds.

## Change and comparison

Normalized point-spectrum fitting now limits native output to the span required
by the selected observations and redshift bounds. Its temporary broadening grid
is a slice of the **original** logarithmic lattice, retaining its spacing and
phase, with enough surrounding samples for the full four-sigma kernel at the
maximum allowed width. It preserves the original interpolation mappings, native
output samples, and true model-edge extension. The zero-width shortcut remains.
Absolute flux and photometry keep their existing transformation paths.

Serial candidate timings, comparing the previous full-vector transform with
the limited transform in the same process:

| Teff | Previous | Limited | Speedup |
|---|---:|---:|---:|
| 7500 K | 6.070 s | 0.448 s | 13.5× |
| 10000 K | 2.299 s | 0.294 s | 7.8× |
| 16000 K | 2.707 s | 0.314 s | 8.6× |

All three optimized fits agreed with their reference RMSE within 4×10⁻¹³ in
absolute terms. The largest broadening difference was below 5×10⁻⁹ km/s and
the largest redshift difference below 3×10⁻¹³. These are candidate benchmarks,
not a timing of a complete 6,628-model parallel search. Reading/decompressing
each model still contributes to the full-grid runtime.

Regression checks compare limited and full transforms in air and vacuum,
at both redshift bounds, from zero to maximum broadening, and across true model
edges and missing coverage.
