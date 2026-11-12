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
    nv: { label: "N V 1239/1243", medium: "vacuum", waves: [1238.821, 1242.804] },
    siiv: { label: "Si IV 1394/1403", medium: "vacuum", waves: [1393.7546, 1402.7697] },
    civ: { label: "C IV 1548/1551", medium: "vacuum", waves: [1548.204, 1550.781] },
    pv: { label: "P V 1118/1128", medium: "vacuum", waves: [1117.977, 1128.008] }
  };
  var presets = [
    { id: "optical-wind", label: "Optical wind: Hα + He II 4686", features: ["halpha", "he4686"] },
    { id: "optical-combined", label: "Optical wind + photosphere", features: ["halpha", "he4686", "hbeta", "hgamma", "he4471", "he4542"] },
    { id: "uv-wind", label: "UV wind: N V + Si IV + C IV", features: ["nv", "siiv", "civ"] },
    { id: "fuv-wind", label: "Far-UV wind: P V", features: ["pv"] }
  ];

  function plan(id, context) {
    var preset = presets.find(function (row) { return row.id === id; });
    if (!preset) throw new Error("Choose a diagnostic preset.");
    var width = Number(context.halfWidth), z = Number(context.redshift);
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
    return { rows: rows, windows: windows };
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
    select.disabled = false;
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
        button.disabled = !selection.windows.length;
      } catch (error) { preview.textContent = error.message; button.disabled = true; }
    }
    [select, width, redshift, velocity, options.rangeMin, options.rangeMax].forEach(function (input) {
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
