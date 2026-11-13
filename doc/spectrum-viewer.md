# Spectrum viewer

The single-model, model-comparison, uploaded-data, and parsed wavelength viewers share zoom, axis, and reference-line controls. Available spectra and overlays depend on the page and files in the model.

## Choose a spectrum and view

On a model's final spectrum page, choose an available `obs_fin` spectrum and a spectrum type. Select the continuum or other available overlays to compare curves on the same axes. Missing products must be generated before they can be displayed.

Use the wavelength and flux scale selectors to switch between linear and logarithmic axes. Logarithmic axes require positive values. Drag to zoom, use **Zoom to** for a preset or reference line, and double-click the plot to reset the view. Use the plot legend to show or hide curves.

## Compare models on the Models page

Use the checkbox beside each model name on **Models** (or a bulk summary page)
to overlay its spectrum in **Compare Model Spectra** above the table. Spectra
load only when selected. The checkbox in the MODEL header selects or deselects
the currently visible rows; **Clear selection** removes all curves, including
models hidden by a scatter-plot filter. Filtering or sorting the table does not
otherwise change the comparison selection.

Use **Filter models** immediately above the list to narrow rows by a name or
relative path. Matching ignores case and accepts partial text; `*` matches any
text and `?` matches one character (for example, `Bstar3*` or `grid/*3100`).
Other punctuation is literal. The count shows how many rows match both this
filter and any scatter-plot selection. **Clear filter** or Escape clears only
the name filter; **Clear Point Filter** clears only the scatter selection.
Hidden checked models remain in the spectrum comparison, and the header
checkbox selects only the visible rows. Copy as Text exports only visible rows.

Choose **Normalized (F/Fc)** for line profiles or **Spectrum + continuum** for
absolute flux at the native 1 kpc reference distance. Each model uses its first
available `obs_fin*` file in the same numeric order as the bulk spectrum viewer,
with its own `obs/obs_cont`. Model colors remain stable while selecting curves;
the continuum uses a dotted line in the same color. Legend labels include the
model path so models with identical folder names remain distinguishable.
Missing or unusable spectra are listed without hiding the other selected models.
Use **Reload spectra** after a calculation produces new output.

The inline comparison shares wavelength zoom, axis scales, spectral line markers,
and adaptive display sampling with the other spectrum viewers. The wavelength
window is retained when adding or removing models; the vertical scale refits to
the selected curves. Use the individual or bulk spectrum page for
transformations and observed-data overlays.

## Upload wavelength convention

Choose **Air wavelengths** (the default) or **Vacuum wavelengths** when uploading
from Uploads, a single-model page, or the bulk-spectrum page. On the upload's own
page, change **Uploaded wavelengths** and press **Save wavelength convention** to
correct the interpretation later. This updates metadata only: the source file,
wavelength values, flux values, uncertainties, and bad pixels are not rewritten.
Uploads made before this property existed default to Air. FITS wavelength-medium
keywords are not used to override the explicit choice. Native vacuum uploads
must be marked Vacuum. VizieR-generated photometry is recorded as Vacuum.

Stop a running grid fit before editing its convention, and rerun completed fits
following a change. Cached parsing immediately uses the updated property; old
job overlays with a different convention are rejected. Photometry edits preserve
the saved convention; VizieR points appended to Air photometry are converted to
that convention before merging. Air/vacuum and the velocity frame are separate properties:
the source velocity must match the upload's existing topocentric, heliocentric,
or barycentric frame; the viewer does not infer a velocity-frame correction.

## Spectrum transformations

The **uploaded spectrum defines the fixed plotted wavelength system**. Enter
**Source redshift z** or **Source velocity (km/s)** relative to that system. The
fields use **v = c z**, the optical velocity convention, rather than the
relativistic Doppler velocity. Positive source velocity shifts the model and
stellar reference markers towards **longer** wavelengths.

| Component | Display and fitting behavior |
| --- | --- |
| Upload, its uncertainties and bad pixels | Native values; never shifted, smoothed or resampled |
| Fitting windows, diagnostics and exclusions | Fixed intervals in the upload's original wavelengths |
| Model spectra | Redshift in vacuum, broaden, convert to the upload's convention, then sample at observed pixels for fitting |
| Stellar line markers and line-zoom centers | Redshift vacuum rest wavelengths, then convert to the upload's convention |
| Telluric guides | Fixed in the upload convention, independent of source redshift |

For an Air upload the model coordinate is
`lambda_air = vacuum_to_air(lambda_model_vacuum * (1 + z))`.
For a Vacuum upload it is `lambda_model_vacuum * (1 + z)`.
An air-rest line-list entry is first converted to vacuum so markers follow the
same order of operations as models. At z = 0, Air uploads still require the
model vacuum-to-air conversion; the conversion must not be absorbed into velocity.

Imported TLUSTY/SYNSPEC wavelength tables use air above 2000 Å by default.
The viewer first converts those native model coordinates to vacuum; TLUSTY
frequency-based SEDs already use vacuum. Existing caches with the importer's
`x_axis_kind` metadata are handled automatically, without rewriting their files.
Explicit `wavelength_medium` metadata takes precedence for all-vacuum SYNSPEC
runs. Treating these optical tables as vacuum would introduce an approximately
80 km/s velocity bias and displace reference markers even when the fit looks good.
The convention follows the [SYNSPEC manual, §5.3.1](https://arxiv.org/pdf/1706.01859#page=20).

BOSZ 2024 also uses air above 2000 Å and is converted to vacuum on loading,
including existing `bosz2024_` caches. BOSZ 2017 and PHOENIX-ACES use vacuum.
See [BOSZ 2024, §3.3](https://arxiv.org/pdf/2407.10872#page=5) and
[PHOENIX-ACES, §2.4](https://arxiv.org/pdf/1303.5632#page=5).

Model broadening uses the native model samples before conversion and before
interpolation onto observed pixels. Models with inadequate native resolution
cannot be sharpened. Both the Python fitting pipeline and browser display use
the same wavelength conversion and transform order. Normalized model flux values
are unchanged by the air/vacuum conversion. Absolute F-lambda model densities
include `d(lambda_vacuum)/d(lambda_air)` so integrated flux is preserved.
Extinction is evaluated on the redshifted vacuum wavelengths.

**Spectrum transformations** affects models only. Uploaded fluxes, bandwidths
and errors remain unchanged even when distance, reddening or broadening is edited.
Grid fits load a native vacuum model overlay and initialize the model controls
with its fitted parameters; subsequent edits transform that model from its native
samples, avoiding double shifting, conversion, or broadening. **Reset
transformations** restores z = 0 and the other preview defaults; it does not
change the upload's wavelength property. Invalid transform values retain the
last valid display. Display adjustments do not modify saved observations or the
native data used by subsequent fits.

Candidate model overlays display only within the uploaded wavelength span
(including band edges for photometry). This limit is applied after transforming
and broadening the native model and is updated when preview parameters change.
It uses the whole upload, independently of narrower diagnostic fitting windows.

**Wavelengths** in Line and display settings is locked to the active upload's
property. Update that property on its upload page to correct it. Multiple observed
overlays on a model page must have the same convention; incompatible overlays are
omitted with a warning. Without an upload, model comparisons and their line
markers default to Air, with Vacuum available through **Wavelengths**.

## Fit diagnostic regions in uploaded spectra

Open **Grid Fit → Fit settings → Diagnostic regions** on an uploaded spectrum.
Leave both fields blank for the existing full-spectrum fit, or enter one interval
per line in **Diagnostic windows**, for example:

```text
He I 4471, 4455, 4485
He II 4542, 4525, 4558
```

These are illustrative bounds; choose widths appropriate to the observed shift,
line broadening, blends, and wavelength coverage. A label is optional:
`4455, 4485` also works. Windows must not overlap or share endpoints. In
**Exclude intervals**, use the same format to remove telluric absorption,
nebular emission, unreliable pixels, or line cores. Exclusions override windows;
with no windows, they remove samples from the full fit range.

Diagnostic windows restrict the actual fit as well as defining the reported
diagnostics. The selected samples are the overall wavelength range intersected
with the union of windows (or the whole range when windows are blank), minus
exclusions. The display checkboxes affect only overlays. Editing either field
requires rerunning the fit to update parameters and scores.

Zoom the plot to a region and click **Add zoom range as window** or
**Exclude zoom range** to append its bounds to the corresponding field. Existing
entries are preserved, and an optional label can be added afterward. Both buttons
use uploaded wavelengths, including when the plot has a logarithmic axis.

Diagnostic windows and exclusions are saved automatically in this browser,
separately for each upload, and restored on your next visit. Manual edits and
zoom-button additions both persist; the **Clear** button beside each zoom action
empties its corresponding field, updates the plot guides, and saves it empty. Explicit
URL values and a restored running fit's regions take precedence over saved
drafts. Browser storage does not change a running fit or its saved results.

The **Zoom to → Diagnostic windows** group follows the windows in the form,
including restored browser drafts and zoom-button additions. Each option uses
the window's exact uploaded-wavelength bounds, independently of source redshift
and the line-jump Width field. Incomplete or invalid rows are omitted while
editing; windows outside the displayed spectra's coverage are disabled.

The main plot's separate **Diagnostic windows** checkbox shows faint amber bands
for the windows currently in the form. They update with edits and restored drafts,
stay fixed as source velocity changes, and are independent of the spectral-line
and telluric toggles. These bands show the complete entered windows; fit-range
limits and exclusions still apply to scoring. Labels appear when there is room.
The display toggle does not enable or disable a window for fitting.

**OB-star diagnostic preset** offers Optical wind (Hα and He II 4686), Optical
wind + photosphere (also Hβ, Hγ, He I 4471 and He II 4542), UV wind (N V,
Si IV and C IV doublets), and Far-UV wind (P V). **Half-width (km/s)** sets the
optical-convention velocity extent on either side of each line or doublet;
Choosing a preset sets an editable suggested half-width: 3000 km/s for wind
sets and 250 km/s for GOSSS classification sets. These are starting profile
windows, not universal boundaries or calibrated EW integration limits. Adjust
for rotation, instrumental resolution, and blending. The preview
shows each interval in uploaded wavelengths, including unavailable and partially
covered intervals. It considers both native upload coverage and the overall fit
range; fully unavailable intervals are skipped without changing that fit range.

The four GOSSS classification presets follow [Sota et al. (2011)](https://arxiv.org/abs/1101.4002)
and [Sota et al. (2014)](https://arxiv.org/html/1312.6222v1):

| Preset | Selected features | Interpretation |
| --- | --- | --- |
| Late-O subtype | He I 4144, He II 4200, He I 4388, He II 4542, Si III 4552 | Peak-strength comparisons 4542/4388, 4200/4144 and 4552/4542; Paper II, Table 3. |
| Late-O luminosity | He I+II 4026, Si IV 4089, He II 4686, He I 4713 | Compare 4686/4713 and 4089/4026 for O9–O9.7; Paper I, Table 6. The 4026 feature is blended. |
| Of / Ofc morphology | N III 4634–4642, C III 4647–4652, He II 4686 | Compare emission/absorption morphology. Overlapping nitrogen/carbon windows are combined as context; they are not separate EW measurements. |
| Vz helium diagnostics | He I 4471, He II 4542, He II 4686 | Paper II uses EW(4686) / max[EW(4471), EW(4542)]. This classification ratio is distinct from source redshift z. |

These presets select fitting regions and show profiles; they do not calculate
line-strength ratios, equivalent widths, or spectral classifications. The preset
help popover describes the selected comparison. The reference-line overlay and
diagnostic plots include the added helium/silicon features and representative
positions for the nitrogen/carbon blends.

Preset controls sit below the window and exclusion fields. Click the circled
**i** beside a field or section label for details about selection, persistence,
coordinate conventions, or model limitations. Popovers also work with keyboard
activation; Escape or clicking outside closes them. Live coverage previews,
fit feedback, and the short selection reminder remain visible.

**Add windows** converts vacuum rest bounds using the current source redshift
from Spectrum transformations, then the upload's Air/Vacuum convention, once.
Inserted bounds remain fixed when transformation controls change. Overlapping
new preset intervals are combined into their union; existing windows are kept
and overlapping additions skipped. Clear existing windows first to replace them.
Exclusions are preserved. Added windows save automatically and update the main
plot bands and Zoom to menu. All bounds remain editable.

These presets identify standard diagnostics, not a mass-loss estimator. Wind
parameter estimates require wind models with suitable parameter coverage, such
as CMFGEN, and must account for ionization and clumping. The current hydrostatic
TLUSTY, BOSZ and PHOENIX grids provide photospheric comparisons. See
[Puls, Vink & Najarro (2008)](https://arxiv.org/abs/0811.0487) for wind diagnostics;
the P V doublet wavelengths follow [Fullerton et al. (2006)](https://discovery.ucl.ac.uk/id/eprint/9920/1/9920.pdf).

**Excluded intervals** shows pale red bands, independently of the amber windows
and blue telluric guides. **Add telluric bands** appends the same approximate
bands used by the telluric overlay, converted to the upload's Air/Vacuum convention
and fixed independently of stellar velocity. Only bands overlapping the native
upload coverage are added, using their full bounds regardless of current zoom.
Existing exclusions are preserved and bands already covered by an exclusion
are skipped. The fields save automatically; edit these broad guide intervals
to match your observations. Adding bands affects the next fit, while merely
turning on the telluric display does not exclude any samples.

All bounds are inclusive, in **observed-frame Å**, using the upload's air/vacuum
convention. Windows stay fixed as the model redshift is optimized. The overall
wavelength range still applies. Numeric fields and their plotted boundary markers
refer directly to the stored upload wavelengths. Changing model velocity,
broadening or wavelength conversion does not change the selected observed pixels.
**Use plot range** copies the displayed limits directly, with no redshift or
medium conversion. This applies to Grid Fit and the single-model fit controls.
At least 30
usable samples in total and two unmasked samples per window are required.
Candidate models must cover every selected sample, ensuring the same comparison
data for each candidate, including full-window fits without named diagnostics.
A shorter model segment cannot silently omit observed edge pixels. The redshift search is intersected with the interval
that gives complete coverage (and can become fixed at an edge). Selection happens before the existing fitting sample
cap. Effective sample-size estimates do not correlate residuals across masked
intervals or separate windows.

The current and final best models show **Diagnostic scores** below the compact
parameter summary. For a top candidate, use its **Diagnostic scores** button to
expand a full-width row below the candidate without changing the main columns.
The diagnostic table shows sample counts, sums of squared residuals, and mean
squared residuals per window. These use the existing fit residual weighting
(uploaded uncertainties when available); they are not independent reduced χ²
measurements. The combined score retains pixel weighting, so larger windows
usually contribute more. Inspect all windows for conflicting diagnostics.
Grid confidence intervals are presented in a parameter table with 68%, 90%, and
95% columns; **Fit statistics** and **Residual weighting** retain the detailed
scoring information in collapsible sections.

The final best-fit result also includes **Diagnostic window plots**: one plot per
window with native uploaded samples, the fitted model, and common plus saved
custom stellar line markers at the fitted redshift. Excluded intervals are shaded;
their data are shown for context but remain excluded from the numeric scores.
Plots use the upload's Air/Vacuum convention and the saved best-fit parameters,
independently of later changes to the main plot's transformation controls. Each
plot supports zooming and image export through its Plotly toolbar.

Diagnostic regions work with spectral uploads in the existing supported grid
modes; they do not apply to photometry. Normalized spectra must already be
continuum-normalized. Local continuum fitting, EW measurements, and EW ratios
are not yet implemented.

## Spectral line overlay

Enable **Spectral lines** above a single-model, bulk-model, or uploaded-spectrum
plot to show dotted reference positions. The overlay starts disabled. It is also
available on parsed file plots whose horizontal axis is explicitly Wavelength (Å)
or Wavelength (Angstrom).
For files containing both wavelength and depth plots, use **Separate** to view the
overlay on the wavelength plot.

The model, bulk, upload, and parsed-file viewers share the same zoom and line
controls. Open **Line and display settings** to choose a line group, wavelength
convention, labels, and sampling detail. Spectrum transformations are in a separate
expandable group on the model, bulk, and upload pages.

Choose **All lines**, **Hydrogen**, **Helium**, **Metals**, or **Custom lines**. Hydrogen includes
Lyman, Balmer, Paschen, and Brackett lines; helium includes common He I and He II
diagnostics; metals include UV blends, Ca II, Na I D, and common nebular lines.
This is a small reference list for visual inspection. Multiplets use representative
positions; entries labeled “blend” mark a combined feature, rather than individual
doublet components. Square brackets denote forbidden transitions.

**Air** is the default wavelength convention for model comparisons and line
lists. With an upload, its saved Air/Vacuum property controls the display; models
and markers are converted to match it. This never converts the uploaded axis.
Values below 2000 Å stay vacuum. Parsed model-file plots without transformation
controls retain native vacuum coordinates and initialize their marker display to
Vacuum, so their file axes and markers agree.

Turn **Labels** off to keep only the dotted lines. Markers are limited to the
visible wavelength range. Closely spaced labels are omitted at wide zoom levels;
zoom in to reveal them, or select a single line family. Hover over a label for its
rest wavelength and convention. The overlay leaves the spectrum data, fit bounds,
and exported tables unchanged.

Use **Zoom to** to jump to a reference line, the **optical range (3800–7500 Å)**,
or the **whole spectrum**. The adjacent **Width (Å)** input sets the total span
around a selected line: the default **300 Å** means **±150 Å**, and **40 Å** means
**±20 Å**. Set it before choosing a line; blank uses 300 Å. It applies to common
and custom lines, on linear and logarithmic axes, without changing the Optical
or Whole spectrum presets. The menu works with
the line overlay on or off. Lines are grouped by family and show their current
redshifted positions using the selected air/vacuum convention. Lines
outside the displayed spectra's wavelength coverage are disabled. The whole
spectrum preset covers the current data of all visible curves, excluding curves
hidden through the legend or bulk visibility controls. Presets also fit the vertical
range to visible flux values in the chosen wavelength window, including error bars
and line segments crossing its edges, with a small margin. They retain the selected
linear/logarithmic scales. Empty windows keep the previous vertical range; log
scales use positive flux values. After a jump,
the menu returns to its prompt so you can select the same destination again.

### Custom spectral lines

Open **Line and display settings** and enter custom rest wavelengths in the
textarea, one per line, followed by an optional label. Wavelengths are in Å;
spaces, commas, or semicolons can separate the wavelength and label:

```text
# Optical diagnostics in air
5006.84 [O III]
6562.80, Hα
6678.15 He I
```

The **Input wavelengths** default is **Air**, as in this example. Choose **Vacuum** for vacuum
values. This specifies the convention of the entered numbers independently of
the **Wavelengths** display selector. Below 2000 Å, values remain in vacuum.
Blank lines and lines beginning with `#` are ignored. Labels are optional and
display as plain text. Invalid rows are listed beneath the field and skipped;
valid rows still appear. Edits apply immediately. Previously saved custom lists
retain their saved input convention; new lists default to Air.

Enable **Spectral lines**, then choose **Custom lines** to show only your lines,
or **All lines** to include the built-in catalog. Custom lines also appear in
the **Zoom to** menu, follow the source redshift, and use the same wavelength
conversion and label-spacing rules. Their labels take priority in crowded views.

The list and its input convention are saved in this browser, when browser
storage is available, and shared across viewers and tabs on the same server
origin. Clear the textarea to remove the list. Custom lines affect reference
markers only; model files, uploaded spectrum values, fitting masks, and exports are unchanged.

### Telluric bands

Enable **Telluric bands** beside **Spectral lines** to shade common atmospheric
absorption regions. The toggle starts off and works independently of the stellar
line overlay. The guides use approximate air intervals in Å:

| Band | Approximate interval |
| --- | --- |
| O₂ γ + O₄ | 6270–6335 |
| O₂ B | 6860–6970 |
| H₂O | 7140–7400 |
| O₂ A | 7580–7710 |
| H₂O | 8080–8255 |
| H₂O | 8910–9940 |
| H₂O | 13450–14500 |
| H₂O | 18000–19400 |

The first six are rounded reference regions informed by
[Buton et al. (2013), Table 1](https://www.aanda.org/articles/aa/pdf/2013/01/aa19834-12.pdf).
The two infrared guides use strongly contaminated regions listed in
[Davies et al. (2023), Table B2](https://academic.oup.com/mnras/article/521/1/289/7069299).
These are broad visual guides, not exact boundaries or a complete telluric atlas.
Absorption depths depend on airmass, water vapour, and observing conditions.

Bands use the upload's Air/Vacuum convention and stay fixed as source redshift
changes. The table lists approximate air-frame intervals; selecting Vacuum
converts the atmospheric guides to vacuum without applying stellar redshift.

The atmospheric catalog assumes **topocentric** uploaded wavelengths. A previously
applied barycentric or heliocentric correction also moves atmospheric features;
that prior correction is not inferred from a FITS header or source velocity.
For such uploads the guides remain approximate until that separate correction
is accounted for. It must not be replaced by the star's redshift.

Only overlapping parts of bands are shaded; labels appear when there is room,
with approximate bounds on hover. Guides do not expand the spectrum's wavelength
coverage, correct absorption, modify exports, or automatically exclude fitting
samples. Use **Exclude intervals** in Grid Fit for any desired masks, accounting
for the uploaded spectrum's actual wavelength frame.

## Spectrum detail

Spectral viewers keep native samples in the browser. **Detail → Adaptive** reduces
only the drawn curve: wide views
retain the first/last points and flux minima/maxima in wavelength bins, so narrow
line cores and emission peaks survive the overview. Bins follow the selected
linear or logarithmic wavelength axis. Zooming or panning redraws from the native
spectrum; windows with at most the display budget (normally 5,000 samples per
curve, rising to 12,000 for wide plots) show every original sample. Gaps and
uncertainties remain aligned with the selected samples. Photometry keeps all bands.

Choose **Full resolution in displayed region** to draw every sample even in a
dense window. The count beside the selector shows displayed points and the total
native points of visible curves. Plotly's additional line simplification is disabled.
**Whole spectrum**, double-click/reset, and line-menu availability use the native
coverage, so zooming does not discard access to other wavelengths. The quick zoom
presets calculate the vertical range from native transformed flux and error bars.

Model redshift, distance, reddening, and velocity broadening operate on the complete
native model arrays before display reduction. Broadening therefore has the surrounding
data it needs even when inspecting a narrow window. Fitted-model overlays also
retain their native samples. Display settings do not change fitting or exports.

Keeping native arrays increases page size and browser memory use, especially in
bulk comparisons. Adaptive mode bounds the drawn curve, but loading and physical
transforms still process the full spectrum; full-resolution views of very dense
regions may take longer to draw. The existing wavelength limits and any source
file's intrinsic resolution still apply.

## Reference data

The compact catalog uses the [SDSS reference line table](https://classic.sdss.org/dr7/algorithms/linestable.php),
with hydrogen and helium additions from the NIST strong-line tables for
[hydrogen](https://physics.nist.gov/PhysRefData/Handbook/Tables/hydrogentable2_a.htm)
and [helium](https://physics.nist.gov/PhysRefData/Handbook/Tables/heliumtable2.htm).
Optical Hβ, Hα, [O III], and [S II] positions follow the
[SDSS common-transition table](https://www.sdss4.org/dr17/spectro/spectro_basics/#Vacuum).
Air/vacuum conversion uses the Ciddor (1996) equation documented on that page.
Air catalog entries are converted to vacuum before the display convention is
applied. Source redshift is applied in vacuum before the displayed medium conversion;
the stored rest catalog is unchanged.
