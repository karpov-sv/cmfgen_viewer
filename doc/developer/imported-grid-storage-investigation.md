# BOSZ and PHOENIX storage and conversion investigation

Date: 2026-11-10. Code baseline: `3313d6d`.

The lossless storage changes identified below are now implemented in both
importers and the shared reader, and applied to the installed BOSZ and PHOENIX
caches. Wavelength samples, coverage, numerical fitting values, and quality
metadata are preserved. Raw downloads are unchanged. Machine-readable original
measurements and migration results are in
[the audit JSON](data/imported-grid-storage-audit.json).

The investigation measurements below describe the original caches; the
implementation and final sizes are recorded in the migration section.

## Current local products

| Property | BOSZ | PHOENIX |
|---|---:|---:|
| Cached spectra | 6,628 | 7,559 |
| Fit-eligible spectra | 6,628, with sample masks | 7,553; six excluded for negative flux |
| Instrumental resolving power | 2,000 | 10,000 |
| Samples per spectrum | 30,000 | 212,027 |
| Approximate wavelength coverage | 500–319,931 Angstrom | 3,000–25,000 Angstrom |
| Samples per nominal instrumental FWHM | 2.32 | 10.00 |
| Converted NPZ storage | 3.099 GiB | 19.103 GiB |
| Original spectra/archives | 0.995 GiB | 4.832 GiB |

BOSZ contains `ap`, `mp`, and `ms` atmosphere families, all at microturbulence
2 km/s in this local selection. Its temperatures span 2,800–16,000 K. PHOENIX
spans 2,300–12,000 K and its microturbulence is a derived model property.

The current BOSZ `--resolution` flag selects downloaded products rather than
resampling them. The [publisher's BOSZ description](https://archive.stsci.edu/hlsp/bosz)
provides pre-broadened products and a shared wavelength file per resolution.
The PHOENIX product convention is enforced by the local importer; its FITS
natural-log step is 1e-5 and all cached wavelength axes match.

Neither imported grid has the TLUSTY-specific 20,000-point fitting cap. The
shared fitter already requests all their stored samples.

CMFGEN follows a different path: candidates come from the model-summary cache,
and fitting reads a selected final spectrum and, when needed, its continuum
directly from each model directory. The NPZ layout savings below therefore
apply to BOSZ and PHOENIX. Similar CMFGEN preprocessing would be a separate
derived cache, preserving the original model outputs.

## Lossless storage opportunities

The inventory sums compressed ZIP member sizes without decoding every array:

| Stored array | BOSZ | PHOENIX |
|---|---:|---:|
| Repeated wavelength | 0.8455 GiB | 8.7744 GiB |
| F-lambda flux | 0.5758 GiB | 10.3272 GiB |
| Continuum | 0.5441 GiB | — |
| Precomputed normalized flux | 1.1264 GiB | — |
| Original negative-flux backup | 0.0036 GiB | — |

ZIP/container overhead accounts for the small difference from total NPZ sizes.
Every file in each grid has the same wavelength ZIP CRC and uncompressed size.
SHA-256 checks of actual wavelength arrays from seven evenly spaced models per
grid also match. A production migration should validate shared axes fully,
rather than relying on CRCs as an integrity guarantee.

### BOSZ: shared wavelengths and derived normalization

Store the common wavelength axis once. Store flux and continuum per model, and
construct normalized flux on demand using the importer's existing rule:

```python
normalized = np.full(flux.shape, np.nan)
np.divide(flux, continuum, out=normalized,
          where=(continuum > 0) & (flux >= 0))
```

This reconstruction was checked against **all 6,628 cached normalized arrays**:
zero mismatches, including all 120 masked/NaN normalized samples. No cached
continuum samples were nonpositive, but the existing mask rule should still be
preserved for future imports.

The 46 models containing `raw_flux_lambda_cgs` must keep those original negative
values and their quality/mask metadata. Removing the normalized array alone
without changing the loader's mask handling would be insufficient.

Estimated storage after these changes: **about 1.13 GiB**, down **63.6%**, without
changing resolution or coverage. Absolute fits can avoid constructing normalized
flux entirely; normalized fits perform a cheap vector division instead of reading
the large precomputed ratio arrays.

### PHOENIX: shared wavelengths and source-flux encoding

Sharing the wavelength array alone reduces approximately **19.10 to 10.33 GiB**.

There is a second lossless opportunity. Sampled original FITS files use BITPIX=-32.
The importer currently promotes source flux to float64 and multiplies it by
`FLUX_FACTOR = 1e-8 / (4*pi)`, producing less-compressible float64 arrays.
Instead, a cache can retain the source float32 values and the exact float64
scale, applying the existing conversion on load.

For **every one of the 7,559 cached flux vectors**, the following reconstructed
the current numerical values exactly:

```python
source_flux = (cached_flux / FLUX_FACTOR).astype(np.float32)
restored_flux = source_flux.astype(np.float64) * FLUX_FACTOR
assert np.array_equal(restored_flux, cached_flux)
```

Three original FITS spectra, spanning the catalogue, were also read and checked
against their cached scaled fluxes. This is source-value preservation, not an
arbitrary downcast of the already converted flux. The scale should be stored
explicitly as float64, and conversion should occur in float64 on loading.

Re-encoding all flux vectors in memory at the importer's existing compression
level 1 measured **4.797 GiB**, including per-model scale/reference overhead.
Adding one shared wavelength file gives **about 4.80 GiB total**, down **74.9%**
from the current cache. All source samples and fitting values are retained.
Vacuum wavelength metadata, inferred-unit flags, interpolation flags, and the
exclusion of the six negative-flux models must remain unchanged.

Both changes require compatible loader/importer support and an explicit cache
migration; deleting arrays from existing NPZs would break the current reader.
Legacy self-contained files should remain readable.

## Resolution, sampling, and optional photometry caches

The BOSZ spectra are already at R=2,000 with only about 2.32 samples per
instrumental FWHM. There is little sampling redundancy to remove while keeping
line profiles. A target of R=50,000 cannot recover information absent from this
product. Lower-resolution publisher products are an alternative when genuinely
coarser data are wanted.

PHOENIX is oversampled by a factor of ten. Resampling at three or five samples
per native R=10,000 FWHM gives about 63,609 or 106,014 points, respectively.
That could reduce storage further, but it is not lossless for the viewer's
linear-interpolation spectral fitting.

A 32-model PHOENIX probe compared such resampled curves against native samples
in 100-Angstrom windows centered at 4,861, 5,000, 6,563, and 7,600 Angstrom.
Errors were normalized to each window's median native flux:

| Sampling | 95th-percentile absolute pixel deviation | Maximum deviation |
|---|---:|---:|
| Three samples/FWHM | 0.99% of window median flux | 26.1% |
| Five samples/FWHM | 0.31% of window median flux | 9.76% |

Large extremes are model/window dependent; these are not claims about the
relative error at every pixel or the error in fitted parameters. They show why
sampling reduction should be an optional, separately validated spectral product.
Broadband errors for these two samplings were much smaller, below 0.003% in the
tested passbands.

The TLUSTY conservative bin integrator was also tried on separate broadband-only
prototypes. The test used 31 valid BOSZ models (one of 32 selected models had
masked data and was skipped) and 32 valid PHOENIX models. It included z=-0.02,
0, +0.02 and E(B-V)=0, 1, 3. Only rectangular bands fully covered under all
three shifts were tested: 18 broad bands for BOSZ and 12 for PHOENIX.

| Grid | Binning power lambda/bin-width | Output points | Largest tested broadband error |
|---|---:|---:|---:|
| BOSZ | 1,000 | 6,464 | 0.542% |
| BOSZ | 3,000 | 19,386 | 0.098% |
| PHOENIX | 1,000 | 2,123 | 0.650% |
| PHOENIX | 3,000 | 6,363 | 0.172% |

The largest deviations involved cool stars, UV/U bands, and high extinction.
These preliminary results do not establish the TLUSTY study's error tolerance
for these different atmosphere grids. True throughput curves, narrow bands,
masked intervals, and full fit-parameter behavior need separate validation.
PHOENIX also lacks UV and mid-IR coverage; rebinning cannot add those wavelengths.

Optional coarse photometry products could be useful, but should retain native
spectral products for line fitting. Quality exclusions must follow the original
models, even when averaging would hide negative samples.

If further Gaussian degradation is added, the existing instrumental width must
be accounted for. For Gaussian kernels and R_target < R_native:

```text
1 / R_kernel**2 = 1 / R_target**2 - 1 / R_native**2
```

TLUSTY's detailed-spectrum helper adds a full instrumental kernel to native
stellar profiles. Applying it unchanged to an already broadened BOSZ/PHOENIX
product would broaden more than the stated target.

## Conversion parallelism

Both importers already default to four threads. BOSZ uses NumPy text loading;
PHOENIX reads binary FITS. They do not have TLUSTY's Python token/regex parser
bottleneck.

Conversion-kernel benchmarks on 64 real models per grid used the current read
and NPZ compression routines, writing only temporary outputs:

| Grid | Serial | Four threads | Four processes |
|---|---:|---:|---:|
| BOSZ | 3.282 s | 1.582 s | 1.112 s |
| PHOENIX | 5.651 s | 1.541 s | 1.744 s |

These are single local trials, including process startup but excluding whole-
archive checksums and final catalogue publication. The production PHOENIX
importer assigns entire archives to threads; the kernel benchmark used individual
model tasks, so it is not an end-to-end import timing.

BOSZ might gain a further approximately 1.4x over its existing threaded path by
using processes. PHOENIX's existing threads were faster than processes in this
test. Removing redundant compression and I/O is the more compelling first
improvement for both grids.

## Implementation and possible follow-ups

1. Implemented backward-compatible shared wavelength storage for both importers/readers.
2. Implemented BOSZ normalization on load with the existing masks.
3. Implemented PHOENIX source flux storage plus an explicit scale, reconstructing
   the current float64 flux on load. Exact reconstruction is checked per file;
   inputs that cannot use float32 losslessly retain scaled float64 storage.
4. Consider optional, separately labelled photometry caches and PHOENIX sampling
   settings after validation against actual observations.
5. Consider an optional BOSZ process pool; keep PHOENIX's working threaded path
   unless an end-to-end benchmark indicates otherwise.

The existing staging-directory publication, checksums, masks, and eligibility
policies should be preserved. The strongest supported result is substantial
lossless storage reduction before making any scientific-resolution tradeoff.


## Completed cache migration

The installed caches and both converters now use `shared-wavelength-v1`.
The reader remains compatible with legacy standalone files and mixed caches.
The conversion uses fast DEFLATE level 1; BOSZ's final size is slightly above
its earlier estimate, which counted the original higher-compression members.

| Cache | Before (GiB) | After (GiB) | Reduction |
|---|---:|---:|---:|
| BOSZ, 6,628 models | 3.099 | 1.163 | 62.5% |
| PHOENIX, 7,559 models | 19.103 | 4.801 | 74.9% |
| Combined | 22.202 | 5.965 | 73.1% |

Each spectrum was reconstructed and compared against every original logical
array before atomic replacement, including NaNs and BOSZ raw negative flux.
Wavelength sharing compares complete axes and verifies their content hashes.
Per-model manifest metadata and the original CSV bytes were preserved.
Migration took about 48 seconds for BOSZ and 134 seconds for PHOENIX with four
threads; this includes validation and is not a full raw-source import benchmark.

The reusable migration command is documented in
[Model Grids](../../MODEL_GRIDS.md#lossless-bosz-and-phoenix-storage).
Existing viewer processes need a restart to load the new reader. Source
archives, TLUSTY caches, physical resolution, and wavelength coverage were
left unchanged. No optional lossy sampling reduction was introduced.


A full post-migration reread confirmed all 6,628 BOSZ models remain available
in both modes, with 120 masked flux/normalized samples and 46 raw negative-flux
records. PHOENIX retains 7,553 fit-eligible models, six excluded models with
144 negative samples, and 51 interpolated models. Every model's point count
and quality fields agree with its unchanged index. Original CSV SHA-256 values
and structured manifest metadata were verified unchanged for both grids.

Validation: 87 grid/storage/fitting tests and 31 listing/parser/documentation
tests passed, followed by a 38-test grid/storage rerun after avoiding redundant
BOSZ decompression. Compilation and whitespace checks also passed.
