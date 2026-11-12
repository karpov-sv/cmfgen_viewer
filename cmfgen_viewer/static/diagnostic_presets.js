/* Editable OB-star starting intervals, inserted once in uploaded coordinates. */
(function () {
  "use strict";
  var c = 299792.458;
  // Representative rest wavelengths. Optical entries follow the reference-line
  // catalogue; UV doublets are vacuum. See doc/spectrum-viewer.md for sources.
  var features = {
    halpha: { label: "Hα", medium: "vacuum", waves: [6564.614] },
    he4686: { label: "He II 4686", medium: "air", waves: [4685.7044] },
    hbeta: { label: "Hβ", medium: "vacuum", waves: [4862.683] },
    hgamma: { label: "Hγ", medium: "vacuum", waves: [4341.68] },
    he4471: { label: "He I 4471", medium: "air", waves: [4471.479] },
    he4542: { label: "He II 4542", medium: "air", waves: [4541.59] },
    he4388: { label: "He I 4388", medium: "air", waves: [4387.929] },
    he4200: { label: "He II 4200", medium: "air", waves: [4199.83] },
    he4144: { label: "He I 4144", medium: "air", waves: [4143.76] },
    si4552: { label: "Si III 4552", medium: "air", waves: [4552.62] },
    he4713: { label: "He I 4713", medium: "air", waves: [4713.146] },
    si4089: { label: "Si IV 4089", medium: "air", waves: [4088.86] },
    he4026: { label: "He I+II 4026", medium: "air", waves: [4026.191] },
    niii: { label: "N III 4634–4642", medium: "air", waves: [4634.14, 4640.64, 4641.85] },
    ciii: { label: "C III 4647–4652", medium: "air", waves: [4647.42, 4650.25, 4651.47] },
    nv: { label: "N V 1239/1243", medium: "vacuum", waves: [1238.821, 1242.804] },
    siiv: { label: "Si IV 1394/1403", medium: "vacuum", waves: [1393.7546, 1402.7697] },
    civ: { label: "C IV 1548/1551", medium: "vacuum", waves: [1548.204, 1550.781] },
    pv: { label: "P V 1118/1128", medium: "vacuum", waves: [1117.977, 1128.008] }
  };
  var presets = [
    { id: "optical-wind", label: "Optical wind: Hα + He II 4686", features: ["halpha", "he4686"] },
    { id: "optical-combined", label: "Optical wind + photosphere", features: ["halpha", "he4686", "hbeta", "hgamma", "he4471", "he4542"] },
    { id: "uv-wind", label: "UV wind: N V + Si IV + C IV", features: ["nv", "siiv", "civ"] },
    { id: "fuv-wind", label: "Far-UV wind: P V", features: ["pv"] },
    { id: "gosss-late-o", label: "GOSSS: late-O subtype", halfWidth: 250,
      description: "Late-O subtype comparisons: He II 4542 / He I 4388, He II 4200 / He I 4144, and Si III 4552 / He II 4542 (peak line strengths).",
      features: ["he4542", "he4388", "he4200", "he4144", "si4552"] },
    { id: "gosss-luminosity", label: "GOSSS: late-O luminosity", halfWidth: 250,
      description: "O9–O9.7 luminosity comparisons: He II 4686 / He I 4713 and Si IV 4089 / He I 4026. The 4026 feature is a He I+II blend.",
      features: ["he4686", "he4713", "si4089", "he4026"] },
    { id: "gosss-of-ofc", label: "GOSSS: Of / Ofc morphology", halfWidth: 250,
      description: "Compare N III 4634–4642, C III 4647–4652, and He II 4686 emission/absorption morphology. Overlapping nitrogen/carbon intervals form one context window, not separate EW measurements.",
      features: ["niii", "ciii", "he4686"] },
    { id: "gosss-vz", label: "GOSSS: Vz helium diagnostics", halfWidth: 250,
      description: "Vz uses EW(He II 4686) / max[EW(He I 4471), EW(He II 4542)]. These windows select profiles; the ratio and spectral class are not calculated. This Vz ratio is distinct from source redshift z.",
      features: ["he4471", "he4542", "he4686"] }
  ];

  function plan(id, context) {
    var preset = presets.find(function (row) { return row.id === id; });
    if (!preset) throw new Error("Choose a diagnostic preset.");
    var defaultWidth = preset.halfWidth || 3000;
    var width = context.halfWidth == null ? defaultWidth : Number(context.halfWidth), z = Number(context.redshift);
    if (!Number.isFinite(width) || width <= 0 || width >= c) throw new Error("Enter a velocity half-width greater than 0 and less than 299792.458 km/s.");
    if (!Number.isFinite(z) || z <= -1) throw new Error("Enter a valid source redshift greater than −1 in Spectrum transformations.");
    if (context.medium !== "air" && context.medium !== "vacuum") throw new Error("Unknown upload wavelength convention.");
    var coverage = context.coverage, range = context.fitRange || [0, Infinity];
    if (!coverage || !Number.isFinite(coverage[0]) || !Number.isFinite(coverage[1]) || coverage[0] >= coverage[1]) {
      throw new Error("Wait for the uploaded spectrum to load.");
    }
    if (Number.isNaN(range[0]) || Number.isNaN(range[1]) || range[0] < 0 || range[1] <= range[0]) {
      throw new Error("Enter a valid overall fit range, or leave its bounds blank.");
    }
    var api = window.CmfgenSpectralLines;
    var rows = preset.features.map(function (key) {
      var feature = features[key];
      var vacuum = feature.waves.map(function (wave) { return feature.medium === "air" ? api.airToVacuum(wave) : wave; });
      var lower = Math.min.apply(null, vacuum) * (1 - width / c) * (1 + z);
      var upper = Math.max.apply(null, vacuum) * (1 + width / c) * (1 + z);
      if (context.medium === "air") { lower = api.vacuumToAir(lower); upper = api.vacuumToAir(upper); }
      lower = Number(lower.toFixed(6)); upper = Number(upper.toFixed(6));
      if (!(lower > 0 && upper > lower)) throw new Error("The chosen redshift or width produces invalid wavelength bounds.");
      var status = "available";
      if (upper < coverage[0] || lower > coverage[1]) status = "outside upload";
      else if (upper < range[0] || lower > range[1]) status = "outside fit range";
      else if (Math.min(upper, coverage[1], range[1]) <= Math.max(lower, coverage[0], range[0])) status = "outside fit range";
      else if (lower < Math.max(coverage[0], range[0]) || upper > Math.min(coverage[1], range[1])) status = "partially covered";
      return { label: feature.label, min: lower, max: upper, status: status };
    });
    // Broad neighboring features can overlap. Their union is one fit window,
    // preserving the selected samples and satisfying the backend overlap rule.
    var windows = [];
    rows.filter(function (row) { return row.status === "available" || row.status === "partially covered"; })
      .sort(function (a, b) { return a.min - b.min; }).forEach(function (row) {
        var previous = windows[windows.length - 1];
        if (previous && row.min <= previous.max) {
          previous.max = Math.max(previous.max, row.max);
          previous.label += " + " + row.label;
        } else windows.push({ label: row.label, min: row.min, max: row.max });
      });
    return { rows: rows, windows: windows, halfWidth: width,
      description: preset.description || "Wind-profile comparison windows; quantitative wind estimates require a suitable wind-model grid." };
  }

  function append(text, selection) {
    var existing = [];
    String(text || "").split(/\r?\n/).forEach(function (line, index) {
      if (!line.trim()) return;
      var fields = line.split(",").map(function (field) { return field.trim(); });
      var lower = Number(fields[fields.length - 2]), upper = Number(fields[fields.length - 1]);
      if ((fields.length !== 2 && fields.length !== 3) || !fields[fields.length - 2] || !fields[fields.length - 1] ||
          !Number.isFinite(lower) || !Number.isFinite(upper) || lower <= 0 || lower >= upper ||
          (fields.length === 3 && (!fields[0] || fields[0].length > 80))) {
        throw new Error("Fix diagnostic window line " + (index + 1) + " before adding a preset.");
      }
      if (existing.some(function (row) { return lower <= row.max && upper >= row.min; })) {
        throw new Error("Existing diagnostic windows overlap; adjust them before adding a preset.");
      }
      existing.push({ min: lower, max: upper });
    });
    var added = [], skipped = [];
    selection.windows.forEach(function (row) {
      if (existing.some(function (other) { return other.min <= row.max && other.max >= row.min; })) {
        skipped.push(row.label + " (already covered or overlaps an existing window)");
      } else { added.push(row); existing.push(row); }
    });
    var original = String(text || "");
    var next = added.length ? original.trimEnd() + (original.trim() ? "\n" : "") + added.map(function (row) {
      return row.label + ", " + row.min + ", " + row.max;
    }).join("\n") : original;
    if (existing.length > 64 || next.length > 16000) throw new Error("Not enough room: use at most 64 windows and 16000 characters.");
    return { text: next, added: added.length, skipped: skipped };
  }

  function bind(options) {
    var select = document.getElementById("grid-fit-preset"), width = document.getElementById("grid-fit-preset-width");
    var button = document.getElementById("grid-fit-add-preset"), preview = document.getElementById("grid-fit-preset-preview");
    if (!select || !width || !button || !preview || !options.windows || !options.plot) return;
    select.textContent = "";
    presets.forEach(function (preset) {
      var option = document.createElement("option"); option.value = preset.id; option.textContent = preset.label; select.appendChild(option);
    });
    select.value = presets[0].id;
    width.value = String(presets[0].halfWidth || 3000);
    select.disabled = false;
    var helpButton = document.getElementById("grid-fit-preset-help-button");
    var helpDescription = document.getElementById("grid-fit-preset-help");
    var helpBase = helpButton ? helpButton.getAttribute("data-bs-content") : "";
    var redshift = document.getElementById(options.plot.id + "-redshift");
    var velocity = document.getElementById(options.plot.id + "-velocity");
    function context() {
      var sources = options.plot.__spectrumSampling ? options.plot.__spectrumSampling.getSources() : [];
      var observed = sources.filter(function (trace) { return trace.meta && trace.meta.transform_target === "observed"; });
      var lower = Infinity, upper = -Infinity;
      observed.forEach(function (trace) { trace.x.forEach(function (x) {
        if (Number.isFinite(x) && x > 0) { lower = Math.min(lower, x); upper = Math.max(upper, x); }
      }); });
      function bound(input, fallback) {
        if (input && input.checkValidity && !input.checkValidity()) return NaN;
        return input && input.value.trim() ? Number(input.value) : fallback;
      }
      return { halfWidth: width.value.trim() ? Number(width.value) : NaN,
        redshift: bound(redshift, 0), medium: observed.length ? observed[0].meta.wavelength_medium || "air" : "air",
        coverage: [lower, upper], fitRange: [bound(options.rangeMin, 0), bound(options.rangeMax, Infinity)] };
    }
    var attached = false;
    function refresh() {
      if (!attached && typeof options.plot.on === "function") { options.plot.on("plotly_afterplot", refresh); attached = true; }
      try {
        var ctx = context(), selection = plan(select.value, ctx);
        var text = "At source z=" + ctx.redshift + ", " + ctx.medium + " wavelengths: " + selection.rows.map(function (row) {
          return row.label + ": " + row.min.toFixed(2) + "–" + row.max.toFixed(2) + " Å (" + row.status + ")";
        }).join("; ");
        if (preview.textContent !== text) preview.textContent = text;
        select.title = selection.description;
        if (helpButton) {
          var helpText = helpBase + " " + selection.description;
          helpButton.setAttribute("data-bs-content", helpText);
          if (helpDescription && helpDescription.textContent !== helpText) helpDescription.textContent = helpText;
        }
        button.disabled = !selection.windows.length;
      } catch (error) { preview.textContent = error.message; button.disabled = true; }
    }
    select.addEventListener("change", function () {
      var preset = presets.find(function (row) { return row.id === select.value; });
      if (preset) width.value = String(preset.halfWidth || 3000);
      refresh();
    });
    [width, redshift, velocity, options.rangeMin, options.rangeMax].forEach(function (input) {
      if (input) { input.addEventListener("input", refresh); input.addEventListener("change", refresh); }
    });
    button.addEventListener("click", function () {
      try {
        var selection = plan(select.value, context()), result = append(options.windows.value, selection);
        if (result.added) {
          options.windows.value = result.text;
          options.windows.dispatchEvent(new Event("input", { bubbles: true }));
          options.windows.dispatchEvent(new Event("change", { bubbles: true }));
        }
        var unavailable = selection.rows.filter(function (row) { return row.status.indexOf("outside") === 0; })
          .map(function (row) { return row.label + " (" + row.status + ")"; });
        var skipped = unavailable.concat(result.skipped);
        options.feedback("Added " + result.added + " diagnostic window(s). Overlapping preset intervals are combined; existing windows and exclusions are kept." +
          (skipped.length ? " Skipped: " + skipped.join("; ") + "." : ""), false);
      } catch (error) { options.feedback(error.message, true); }
    });
    refresh();
    window.requestAnimationFrame(refresh);
  }
  window.CmfgenDiagnosticPresets = { plan: plan, append: append, bind: bind };
})();
