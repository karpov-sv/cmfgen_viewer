# Spectral line overlay

Enable **Spectral lines** above a single-model, bulk-model, or uploaded-spectrum
plot to show dotted reference positions. The overlay starts disabled. It is also
available on parsed file plots whose horizontal axis is explicitly Wavelength (Å).
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
