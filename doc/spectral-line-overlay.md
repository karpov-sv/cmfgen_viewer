# Spectral line overlay

Enable **Spectral lines** above a single-model, bulk-model, or uploaded-spectrum
plot to show dotted reference positions. The overlay starts disabled. It is also
available on parsed file plots whose horizontal axis is explicitly Wavelength (Å)
or Wavelength (Angstrom).
For files containing both wavelength and depth plots, use **Separate** to view the
overlay on the wavelength plot.

Choose **All common lines**, **Hydrogen**, **Helium**, or **Metals**. Hydrogen includes
Lyman, Balmer, Paschen, and Brackett lines; helium includes common He I and He II
diagnostics; metals include UV blends, Ca II, Na I D, and common nebular lines.
This is a small reference list for visual inspection. Multiplets use representative
positions; entries labeled “blend” mark a combined feature, rather than individual
doublet components. Square brackets denote forbidden transitions.

**Vacuum** is the default wavelength convention. Select **Air** for spectra on an
air wavelength scale. This changes only the markers; it does not convert the
spectrum's wavelength axis. Reference wavelengths below 2000 Å remain in vacuum.
On model and upload viewers, marker positions use the current model redshift:
λ = λ_rest × (1 + z). On parsed file plots they stay at rest wavelengths.

Turn **Labels** off to keep only the dotted lines. Markers are limited to the
visible wavelength range. Closely spaced labels are omitted at wide zoom levels;
zoom in to reveal them, or select a single line family. Hover over a label for its
rest and shifted wavelengths. The overlay leaves the spectrum data, fit bounds,
and exported tables unchanged.

Use **Zoom to** to jump to a reference line with a window of **±150 Å**, the
**optical range (3800–7500 Å)**, or the **whole spectrum**. The menu works with
the line overlay on or off. Lines are grouped by family and show their current
positions using the selected air/vacuum convention and model redshift. Lines
outside the displayed spectra's wavelength coverage are disabled. The whole
spectrum preset covers the current data of all visible curves, excluding curves
hidden through the legend or bulk visibility controls. Presets also fit the vertical
range to visible flux values in the chosen wavelength window, including error bars
and line segments crossing its edges, with a small margin. They retain the selected
linear/logarithmic scales. Empty windows keep the previous vertical range; log
scales use positive flux values. After a jump,
the menu returns to its prompt so you can select the same destination again.

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

Redshift, distance, reddening, and velocity broadening operate on the complete
native arrays before display reduction. Broadening therefore has the surrounding
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
Air catalog entries are converted to vacuum before the display convention and
redshift are applied.
