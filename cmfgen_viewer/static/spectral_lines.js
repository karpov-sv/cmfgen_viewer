/* Common reference lines, in Angstroms. See doc/spectrum-viewer.md for
 * sources and conventions. Multiplets use representative positions. */
(function () {
  "use strict";
  var markerName = "cmfgen-spectral-line";
  var telluricName = "cmfgen-telluric-band";
  var diagnosticName = "cmfgen-diagnostic-window";
  var exclusionName = "cmfgen-excluded-interval";
  var colors = { hydrogen: "#a34747", helium: "#7054a2", metals: "#537787", custom: "#b06a18" };
  var customStorageKey = "cmfgen-custom-spectral-lines-v1";

  function escapePlotText(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function parseCustomLines(text, medium) {
    medium = medium === "vacuum" ? "vacuum" : "air";
    var lines = [];
    var invalidRows = [];
    String(text).split(/\r?\n/).forEach(function (row, index) {
      row = row.trim();
      if (!row || row[0] === "#") return;
      var match = row.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][+-]?\d+)?)(?:[\s,;]+(.*))?$/);
      var wavelength = match ? Number(match[1].replace(/[dD]/, "e")) : NaN;
      var vacuum = medium === "air" ? airToVacuum(wavelength) : wavelength;
      var air = vacuumToAir(vacuum);
      if (!Number.isFinite(wavelength) || wavelength <= 0 || !Number.isFinite(vacuum) ||
          vacuum <= 0 || !Number.isFinite(air) || air <= 0) {
        invalidRows.push(index + 1);
        return;
      }
      lines.push({ label: match[2] && match[2].trim() || wavelength + " Å", group: "custom", vacuum: vacuum, air: air });
    });
    return { lines: lines, invalidRows: invalidRows };
  }

  // Ciddor (1996), as used by SDSS DR9+. Never extrapolate into the vacuum UV.
  function vacuumToAir(wavelength) {
    if (wavelength < 2000) return wavelength;
    var s2 = Math.pow(10000 / wavelength, 2);
    return wavelength / (1 + 0.05792105 / (238.0185 - s2) + 0.00167917 / (57.362 - s2));
  }

  function airToVacuum(wavelength) {
    var vacuum = wavelength;
    for (var i = 0; i < 4; i += 1) vacuum *= wavelength / vacuumToAir(vacuum);
    return vacuum;
  }

  // [label, group, rest wavelength, native medium]. NIST supplies H/He;
  // SDSS supplies nebular/UV positions; GOSSS adds optical classification
  // features. Multiplet markers use representative positions, not every component.
  var commonCatalog = [
    ["Lyγ", "hydrogen", 972.5367, "vacuum"],
    ["Lyβ", "hydrogen", 1025.7222, "vacuum"],
    ["Lyα", "hydrogen", 1215.6682, "vacuum"],
    ["H8", "hydrogen", 3889.049, "air"],
    ["Hε", "hydrogen", 3970.072, "air"],
    ["Hδ", "hydrogen", 4102.89, "vacuum"],
    ["Hγ", "hydrogen", 4341.68, "vacuum"],
    ["Hβ", "hydrogen", 4862.683, "vacuum"],
    ["Hα", "hydrogen", 6564.614, "vacuum"],
    ["Paδ", "hydrogen", 10049.4, "air"],
    ["Paγ", "hydrogen", 10938.1, "air"],
    ["Paβ", "hydrogen", 12818.07, "air"],
    ["Paα", "hydrogen", 18751.01, "air"],
    ["Brγ", "hydrogen", 21655.3, "air"],
    ["Brα", "hydrogen", 40511.6, "air"],
    ["He II", "helium", 1640.4, "vacuum"],
    ["He I", "helium", 3888.6489, "air"],
    ["He I", "helium", 4026.191, "air"],
    ["He I", "helium", 4143.76, "air"],
    ["He II", "helium", 4199.83, "air"],
    ["He I", "helium", 4387.929, "air"],
    ["He I", "helium", 4471.479, "air"],
    ["He II", "helium", 4541.59, "air"],
    ["He II", "helium", 4685.7044, "air"],
    ["He I", "helium", 4713.146, "air"],
    ["He I", "helium", 4921.931, "air"],
    ["He I", "helium", 5015.678, "air"],
    ["He II", "helium", 5411.52, "air"],
    ["He I", "helium", 5875.6148, "air"],
    ["He II", "helium", 6560.10, "air"],
    ["He I", "helium", 6678.1517, "air"],
    ["He I", "helium", 7065.1771, "air"],
    ["He I", "helium", 10830.3398, "air"],
    ["He I", "helium", 20581.287, "air"],
    ["O VI blend", "metals", 1033.82, "vacuum"],
    ["N V blend", "metals", 1240.81, "vacuum"],
    ["Si IV blend", "metals", 1397.61, "vacuum"],
    ["C IV blend", "metals", 1549.48, "vacuum"],
    ["C III] blend", "metals", 1908.734, "vacuum"],
    ["Mg II blend", "metals", 2799.117, "vacuum"],
    ["[O II]", "metals", 3727.092, "vacuum"],
    ["[O II]", "metals", 3729.875, "vacuum"],
    ["Ca II K", "metals", 3934.777, "vacuum"],
    ["Ca II H", "metals", 3969.588, "vacuum"],
    ["Si IV", "metals", 4088.86, "air"],
    ["Si III", "metals", 4552.62, "air"],
    ["N III 4634–4642", "metals", 4640.64, "air"],
    ["C III 4647–4652", "metals", 4650.25, "air"],
    ["[O III]", "metals", 4364.436, "vacuum"],
    ["[O III]", "metals", 4960.295, "vacuum"],
    ["[O III]", "metals", 5008.239, "vacuum"],
    ["Na I D blend", "metals", 5895.6, "vacuum"],
    ["[O I]", "metals", 6302.046, "vacuum"],
    ["[N II]", "metals", 6549.86, "vacuum"],
    ["[N II]", "metals", 6585.27, "vacuum"],
    ["[S II]", "metals", 6718.29, "vacuum"],
    ["[S II]", "metals", 6732.68, "vacuum"],
    ["Ca II", "metals", 8500.36, "vacuum"],
    ["Ca II", "metals", 8544.44, "vacuum"],
    ["Ca II", "metals", 8664.52, "vacuum"]
  ].map(function (line) {
    var vacuum = line[3] === "air" ? airToVacuum(line[2]) : line[2];
    return { label: line[0], group: line[1], vacuum: vacuum, air: vacuumToAir(vacuum) };
  }).sort(function (a, b) { return a.vacuum - b.vacuum; });

  // Approximate air intervals, rounded outwards from Buton et al. (2013),
  // Table 1, with the strong NIR H2O regions from Davies et al. (2023),
  // Table B2. These are band guides, not a transmission model or line atlas.
  var telluricBands = [
    ["O₂ γ + O₄", 6270, 6335],
    ["O₂ B", 6860, 6970],
    ["H₂O", 7140, 7400],
    ["O₂ A", 7580, 7710],
    ["H₂O", 8080, 8255],
    ["H₂O", 8910, 9940],
    ["H₂O", 13450, 14500],
    ["H₂O", 18000, 19400]
  ];

  function parseRegionIntervals(text) {
    var rows = [];
    String(text || "").split(/\r?\n/).forEach(function (row) {
      var fields = row.split(",").map(function (field) { return field.trim(); });
      if (fields.length !== 2 && fields.length !== 3) return;
      if (!fields[fields.length - 2] || !fields[fields.length - 1]) return;
      var lower = Number(fields[fields.length - 2]), upper = Number(fields[fields.length - 1]);
      var label = fields.length === 3 ? fields[0] : "";
      if (!Number.isFinite(lower) || !Number.isFinite(upper) || lower <= 0 || lower >= upper ||
          (fields.length === 3 && (!label || label.length > 80)) || rows.length >= 64) return;
      rows.push({ label: label, min: lower, max: upper });
    });
    return rows;
  }

  function telluricIntervals(medium) {
    return telluricBands.map(function (band) {
      return { label: "Telluric " + band[0], min: medium === "vacuum" ? airToVacuum(band[1]) : band[1],
        max: medium === "vacuum" ? airToVacuum(band[2]) : band[2] };
    });
  }

  function appendTelluricExclusions(text, medium, coverage) {
    var existing = parseRegionIntervals(text);
    var bands = telluricIntervals(medium).filter(function (row) {
      return row.max >= coverage[0] && row.min <= coverage[1];
    });
    var additions = bands.filter(function (row) {
      return !existing.some(function (other) { return other.min <= row.min + 1e-9 && other.max >= row.max - 1e-9; });
    });
    if (!additions.length) return { text: String(text || ""), added: 0, matching: bands.length };
    var original = String(text || "").trimEnd();
    var lines = original.split(/\r?\n/).filter(function (row) { return row.trim(); }).length;
    var next = original + (original && additions.length ? "\n" : "") + additions.map(function (row) {
      return row.label + ", " + row.min + ", " + row.max;
    }).join("\n");
    if (lines + additions.length > 64 || next.length > 16000) {
      throw new Error("Not enough room for telluric bands: use at most 64 intervals and 16000 characters.");
    }
    return { text: next, added: additions.length, matching: bands.length };
  }

  function bind(target) {
    var show = document.getElementById(target.id + "-lines-show");
    if (!show || target.__spectralLinesBound) return;
    target.__spectralLinesBound = true;
    var telluricShow = document.getElementById(target.id + "-telluric-show");
    var diagnosticShow = document.getElementById(target.id + "-diagnostic-show");
    var exclusionShow = document.getElementById(target.id + "-exclusions-show");
    var group = document.getElementById(target.id + "-lines-group");
    var medium = document.getElementById(target.id + "-lines-medium");
    var labels = document.getElementById(target.id + "-lines-labels");
    var zoom = document.getElementById(target.id + "-lines-zoom");
    var zoomWidth = document.getElementById(target.id + "-lines-zoom-width");
    var customInput = document.getElementById(target.id + "-lines-custom");
    var customClear = document.getElementById(target.id + "-lines-custom-clear");
    var customMedium = document.getElementById(target.id + "-lines-custom-medium");
    var customStatus = document.getElementById(target.id + "-lines-custom-status");
    var catalog = commonCatalog.slice();
    var customOptgroup = null;
    var diagnosticOptgroup = null;
    var diagnosticWindows = [];
    var diagnosticText = null;
    var exclusionIntervals = [];
    var exclusionText = null;
    var zoomOptions = [];
    var coverageSnapshot = [];
    var coverage = null;
    var frame = null;

    function spectrumCoverage() {
      var data = target.__spectrumSampling ? target.__spectrumSampling.getSources() : target.data || [];
      if (coverageSnapshot.length === data.length && data.every(function (trace, index) {
        return coverageSnapshot[index].x === trace.x && coverageSnapshot[index].visible === trace.visible;
      })) return coverage;
      coverageSnapshot = data.map(function (trace) { return { x: trace.x, visible: trace.visible }; });
      var low = Infinity;
      var high = -Infinity;
      data.forEach(function (trace) {
        if (trace.visible === false || trace.visible === "legendonly" || !trace.x) return;
        for (var i = 0; i < trace.x.length; i += 1) {
          var wavelength = Number(trace.x[i]);
          if (!Number.isFinite(wavelength) || wavelength <= 0) continue;
          low = Math.min(low, wavelength);
          high = Math.max(high, wavelength);
        }
      });
      coverage = high > low ? [low, high] : null;
      return coverage;
    }

    function linePosition(line) {
      var vacuum = line.vacuum * (1 + (target.__spectrumDisplayRedshift || 0));
      return medium.value === "air" ? vacuumToAir(vacuum) : vacuum;
    }

    function updateZoomOptions() {
      var range = spectrumCoverage();
      zoom.querySelector('[value="full"]').disabled = !range;
      zoomOptions.forEach(function (option, index) {
        var line = catalog[index];
        var center = linePosition(line);
        var text = line.label + " · " + center.toFixed(1) + " Å";
        if (option.textContent !== text) option.textContent = text;
        option.disabled = !range || !Number.isFinite(center) || center < range[0] || center > range[1];
      });
      if (diagnosticOptgroup) {
        diagnosticWindows.forEach(function (row, index) {
          diagnosticOptgroup.children[index].disabled = !range || row.max < range[0] || row.min > range[1];
        });
      }
    }

    function updateDiagnosticWindows(text) {
      text = String(text || "");
      if (text === diagnosticText) return;
      diagnosticText = text;
      if (diagnosticOptgroup) diagnosticOptgroup.remove();
      diagnosticOptgroup = null;
      diagnosticWindows = parseRegionIntervals(text);
      if (diagnosticWindows.length) {
        diagnosticOptgroup = document.createElement("optgroup");
        diagnosticOptgroup.label = "Diagnostic windows";
        diagnosticWindows.forEach(function (row, index) {
          var option = document.createElement("option");
          option.value = "diagnostic-" + index;
          option.textContent = (row.label ? row.label + " · " : "") + row.min + "–" + row.max + " Å";
          diagnosticOptgroup.appendChild(option);
        });
        zoom.appendChild(diagnosticOptgroup);
      }
      if (diagnosticShow) diagnosticShow.disabled = !diagnosticWindows.length;
      schedule();
    }

    function updateExclusions(text) {
      text = String(text || "");
      if (text === exclusionText) return;
      exclusionText = text;
      exclusionIntervals = parseRegionIntervals(text);
      if (exclusionShow) exclusionShow.disabled = !exclusionIntervals.length;
      schedule();
    }

    window.addEventListener("cmfgen:diagnostic-windows-changed", function (event) {
      if (event.detail && event.detail.plotId === target.id) {
        updateDiagnosticWindows(event.detail.text);
        if (event.detail.exclusions !== undefined) updateExclusions(event.detail.exclusions);
      }
    });
    var diagnosticInput = target.id === "upload-spectrum-plot" && document.getElementById("grid-fit-windows");
    if (diagnosticInput) updateDiagnosticWindows(diagnosticInput.value);
    var exclusionInput = target.id === "upload-spectrum-plot" && document.getElementById("grid-fit-exclusions");
    if (exclusionInput) updateExclusions(exclusionInput.value);

    function fluxRangeInWindow(range) {
      var xIsLog = target._fullLayout.xaxis.type === "log";
      var yAxis = target._fullLayout.yaxis;
      var yIsLog = yAxis.type === "log";
      var low = Infinity;
      var high = -Infinity;

      function axisFlux(value) {
        if (value === null || value === undefined || value === "") return NaN;
        value = Number(value);
        if (!Number.isFinite(value) || (yIsLog && value <= 0)) return NaN;
        return yIsLog ? Math.log10(value) : value;
      }

      function include(value) {
        if (!Number.isFinite(value)) return;
        low = Math.min(low, value);
        high = Math.max(high, value);
      }

      (target.__spectrumSampling ? target.__spectrumSampling.getSources() : target.data || []).forEach(function (trace) {
        if (trace.visible === false || trace.visible === "legendonly" ||
            (trace.yaxis && trace.yaxis !== "y") || !trace.x || !trace.y) return;
        var drawLines = String(trace.mode || "lines").indexOf("lines") !== -1;
        var errors = trace.error_y;
        var previous = null;
        for (var i = 0; i < Math.min(trace.x.length, trace.y.length); i += 1) {
          var x = trace.x[i] == null ? NaN : Number(trace.x[i]);
          var y = axisFlux(trace.y[i]);
          if (!Number.isFinite(x) || !Number.isFinite(y) || (xIsLog && x <= 0)) {
            if (!trace.connectgaps) previous = null;
            continue;
          }
          if (x >= range[0] && x <= range[1]) {
            include(y);
            if (errors && errors.visible !== false && (!errors.type || errors.type === "data")) {
              var plus = Number(errors.array && errors.array[i]);
              var minus = errors.symmetric === false
                ? Number(errors.arrayminus && errors.arrayminus[i]) : plus;
              if (Number.isFinite(plus) && plus >= 0) include(axisFlux(Number(trace.y[i]) + plus));
              if (Number.isFinite(minus) && minus >= 0) include(axisFlux(Number(trace.y[i]) - minus));
            }
          }
          // A sparse line can cross the window even when neither endpoint is
          // inside it. Interpolate in plot coordinates, including log axes.
          if (drawLines && previous && previous.x !== x) {
            range.forEach(function (edge) {
              if (edge <= Math.min(previous.x, x) || edge >= Math.max(previous.x, x)) return;
              var first = xIsLog ? Math.log10(previous.x) : previous.x;
              var last = xIsLog ? Math.log10(x) : x;
              var position = xIsLog ? Math.log10(edge) : edge;
              include(previous.y + (y - previous.y) * (position - first) / (last - first));
            });
          }
          previous = { x: x, y: y };
        }
      });
      if (!Number.isFinite(low) || !Number.isFinite(high)) return null;
      var padding = high > low ? (high - low) * 0.05 : yIsLog ? 0.05 : (Math.abs(low) || 1) * 0.05;
      var result = [low - padding, high + padding];
      return yAxis.range && yAxis.range[0] > yAxis.range[1] ? result.reverse() : result;
    }

    function zoomToRange(range) {
      var axis = target._fullLayout.xaxis;
      var update = {
        "xaxis.autorange": false,
        "xaxis.range": axis.type === "log" ? range.map(Math.log10) : range
      };
      var fluxRange = fluxRangeInWindow(range);
      if (fluxRange) {
        update["yaxis.autorange"] = false;
        update["yaxis.range"] = fluxRange;
      }
      return Plotly.relayout(target, update);
    }

    ["hydrogen", "helium", "metals"].forEach(function (family) {
      var optgroup = document.createElement("optgroup");
      optgroup.label = family.charAt(0).toUpperCase() + family.slice(1);
      catalog.forEach(function (line, index) {
        if (line.group !== family) return;
        var option = document.createElement("option");
        option.value = "line-" + index;
        zoomOptions[index] = option;
        optgroup.appendChild(option);
      });
      zoom.appendChild(optgroup);
    });

    function updateCustomLines() {
      if (!customInput || !customMedium) return;
      var parsed = parseCustomLines(customInput.value, customMedium.value);
      catalog = commonCatalog.concat(parsed.lines);
      zoomOptions.length = commonCatalog.length;
      if (customOptgroup) customOptgroup.remove();
      customOptgroup = null;
      if (parsed.lines.length) {
        customOptgroup = document.createElement("optgroup");
        customOptgroup.label = "Custom lines";
        parsed.lines.forEach(function (line, index) {
          var option = document.createElement("option");
          var catalogIndex = commonCatalog.length + index;
          option.value = "line-" + catalogIndex;
          zoomOptions[catalogIndex] = option;
          customOptgroup.appendChild(option);
        });
        zoom.appendChild(customOptgroup);
      }
      customInput.setAttribute("aria-invalid", String(parsed.invalidRows.length > 0));
      if (customStatus) {
        customStatus.textContent = parsed.lines.length + " custom line(s)." + (parsed.invalidRows.length
          ? " Ignored invalid rows: " + parsed.invalidRows.join(", ") + ". Enter a positive wavelength in Å, then an optional label." : "");
        customStatus.classList.toggle("text-danger", parsed.invalidRows.length > 0);
        customStatus.classList.toggle("text-muted", parsed.invalidRows.length === 0);
      }
      schedule();
    }

    function useCustomSettings(settings) {
      if (!customInput || !customMedium) return;
      customInput.value = settings && typeof settings.text === "string" ? settings.text : "";
      customMedium.value = settings && settings.medium === "vacuum" ? "vacuum" : "air";
      updateCustomLines();
    }

    if (customInput && customMedium) {
      customInput.disabled = customMedium.disabled = false;
      try { useCustomSettings(JSON.parse(window.localStorage.getItem(customStorageKey))); }
      catch (error) { updateCustomLines(); } // Storage may be unavailable; editing still works.
      function customChanged() {
        updateCustomLines();
        var settings = { text: customInput.value, medium: customMedium.value };
        try { window.localStorage.setItem(customStorageKey, JSON.stringify(settings)); }
        catch (error) { /* Keep the current plot usable without storage access. */ }
        window.dispatchEvent(new CustomEvent("cmfgen-custom-lines-changed", { detail: settings }));
      }
      if (customClear) {
        customClear.disabled = false;
        customClear.addEventListener("click", function () {
          customInput.value = "";
          customChanged();
        });
      }
      customInput.addEventListener("input", customChanged);
      customMedium.addEventListener("change", customChanged);
      // Keep multiple wavelength plots on one page, and other viewer tabs, in sync.
      window.addEventListener("cmfgen-custom-lines-changed", function (event) {
        if (customInput.value !== event.detail.text || customMedium.value !== event.detail.medium) useCustomSettings(event.detail);
      });
      window.addEventListener("storage", function (event) {
        if (event.key !== customStorageKey && event.key !== null) return;
        try { useCustomSettings(JSON.parse(window.localStorage.getItem(customStorageKey))); }
        catch (error) { /* Ignore unavailable or malformed browser storage. */ }
      });
    }
    zoom.addEventListener("change", function () {
      var selection = zoom.value;
      // This is a jump menu: returning to the prompt lets the same preset be
      // selected again after panning, changing scale, or changing redshift.
      zoom.value = "";
      if (selection === "full") {
        var range = spectrumCoverage();
        if (range) zoomToRange(range);
      } else if (selection === "optical") {
        zoomToRange([3800, 7500]);
      } else if (selection.indexOf("diagnostic-") === 0) {
        var diagnostic = diagnosticWindows[Number(selection.slice(11))];
        if (diagnostic) zoomToRange([diagnostic.min, diagnostic.max]);
      } else if (selection.indexOf("line-") === 0) {
        var line = catalog[Number(selection.slice(5))];
        if (!line) return;
        var center = linePosition(line);
        var width = zoomWidth && zoomWidth.value.trim() ? Number(zoomWidth.value) : 300;
        if (!Number.isFinite(width) || width <= 0 || (zoomWidth && zoomWidth.checkValidity && !zoomWidth.checkValidity())) {
          if (zoomWidth && zoomWidth.reportValidity) zoomWidth.reportValidity();
          return;
        }
        zoomToRange([Math.max(center - width / 2, 1), center + width / 2]);
      }
    });

    function refresh() {
      frame = null;
      if (!target.layout || !target._fullLayout) return;
      var shapes = target.layout.shapes || [];
      var annotations = target.layout.annotations || [];
      var ownedNames = [markerName, telluricName, diagnosticName, exclusionName];
      var nextShapes = shapes.filter(function (item) { return ownedNames.indexOf(item.name) < 0; });
      var nextAnnotations = annotations.filter(function (item) { return ownedNames.indexOf(item.name) < 0; });
      var axis = target._fullLayout.xaxis;
      updateZoomOptions();
      if (show.checked && axis && Array.isArray(axis.range)) {
        var low = Math.min(axis.range[0], axis.range[1]);
        var high = Math.max(axis.range[0], axis.range[1]);
        var candidates = [];
        catalog.forEach(function (line) {
          if (group.value !== "all" && group.value !== line.group) return;
          var rest = line[medium.value];
          var wavelength = linePosition(line);
          var axisPosition = axis.type === "log" ? Math.log10(wavelength) : wavelength;
          if (axisPosition < low || axisPosition > high) return;
          nextShapes.push({
            name: markerName, type: "line", xref: "x", yref: "paper",
            x0: wavelength, x1: wavelength, y0: 0, y1: 1,
            layer: "below", line: { color: colors[line.group], width: 1, dash: "dot" }
          });
          var pixel = (axisPosition - low) / (high - low) * axis._length;
          candidates.push({ line: line, rest: rest, wavelength: wavelength, x: axisPosition, pixel: pixel });
        });
        // Keep every marker. Prefer user labels, then hydrogen, in crowded views.
        var priority = { custom: -1, hydrogen: 0, helium: 1, metals: 2 };
        var occupied = [];
        candidates.sort(function (a, b) { return priority[a.line.group] - priority[b.line.group]; });
        candidates.forEach(function (candidate) {
          var line = candidate.line;
          var pixel = candidate.pixel;
          if (!labels.checked || pixel < 10 || pixel > axis._length - 10 ||
              occupied.some(function (other) { return Math.abs(pixel - other) < 20; })) return;
          occupied.push(pixel);
          nextAnnotations.push({
            name: markerName, xref: "x", yref: "paper", x: candidate.x, y: 0.98,
            text: escapePlotText(line.label), textangle: -90, showarrow: false,
            xanchor: "center", yanchor: "top", font: { size: 10, color: colors[line.group] },
            bgcolor: "rgba(255,255,255,0.75)", borderpad: 1,
            hovertext: escapePlotText(line.label) + "<br>Rest: " + candidate.rest.toFixed(2) + " Å (" +
              (medium.value === "air" && line.vacuum >= 2000 ? "air" : "vacuum") + ")<br>Displayed: " + candidate.wavelength.toFixed(2) + " Å"
          });
        });
      }
      function addRegionBands(rows, name, fill, color, prefix, labelY) {
        if (!axis || !Array.isArray(axis.range)) return;
        var diagnosticCoverage = spectrumCoverage();
        var diagnosticLow = Math.min(axis.range[0], axis.range[1]);
        var diagnosticHigh = Math.max(axis.range[0], axis.range[1]);
        var visibleDiagnosticLow = axis.type === "log" ? Math.pow(10, diagnosticLow) : diagnosticLow;
        var visibleDiagnosticHigh = axis.type === "log" ? Math.pow(10, diagnosticHigh) : diagnosticHigh;
        var lastDiagnosticLabel = -Infinity;
        rows.forEach(function (row) {
          var left = Math.max(row.min, visibleDiagnosticLow, diagnosticCoverage ? diagnosticCoverage[0] : Infinity);
          var right = Math.min(row.max, visibleDiagnosticHigh, diagnosticCoverage ? diagnosticCoverage[1] : -Infinity);
          if (right <= left) return;
          nextShapes.push({
            name: name, type: "rect", xref: "x", yref: "paper",
            x0: left, x1: right, y0: 0, y1: 1, layer: "below",
            fillcolor: fill, line: { width: 0 }
          });
          var first = axis.type === "log" ? Math.log10(left) : left;
          var last = axis.type === "log" ? Math.log10(right) : right;
          var center = (first + last) / 2;
          var pixel = (center - diagnosticLow) / (diagnosticHigh - diagnosticLow) * axis._length;
          if ((last - first) / (diagnosticHigh - diagnosticLow) * axis._length < 65 ||
              Math.abs(pixel - lastDiagnosticLabel) < 80) return;
          lastDiagnosticLabel = pixel;
          var label = row.label || row.min + "–" + row.max + " Å";
          nextAnnotations.push({
            name: name, xref: "x", yref: "paper", x: center, y: labelY,
            text: escapePlotText(label), showarrow: false, xanchor: "center", yanchor: "bottom",
            font: { size: 10, color: color }, bgcolor: "rgba(255,255,255,0.7)",
            hovertext: prefix + ": " + escapePlotText(label) + "<br>" + row.min + "–" + row.max +
              " Å (upload frame). Display toggles do not change fit selection."
          });
        });
      }
      if (diagnosticShow && diagnosticShow.checked) {
        addRegionBands(diagnosticWindows, diagnosticName, "rgba(190, 139, 45, 0.065)", "#98732a", "Diagnostic window", 0.10);
      }
      if (exclusionShow && exclusionShow.checked) {
        addRegionBands(exclusionIntervals, exclusionName, "rgba(185, 65, 75, 0.10)", "#a2414a", "Excluded interval", 0.18);
      }
      if (telluricShow && telluricShow.checked && axis && Array.isArray(axis.range)) {
        var coverage = spectrumCoverage();
        var axisLow = Math.min(axis.range[0], axis.range[1]);
        var axisHigh = Math.max(axis.range[0], axis.range[1]);
        var visibleLow = axis.type === "log" ? Math.pow(10, axisLow) : axisLow;
        var visibleHigh = axis.type === "log" ? Math.pow(10, axisHigh) : axisHigh;
        var lastLabelPixel = -Infinity;
        telluricIntervals(medium.value).forEach(function (band) {
          var start = band.min;
          var end = band.max;
          // Keep guides inside both the viewport and the actual data coverage;
          // an atmospheric band must never extend the spectrum's autorange.
          var left = Math.max(start, visibleLow, coverage ? coverage[0] : Infinity);
          var right = Math.min(end, visibleHigh, coverage ? coverage[1] : -Infinity);
          if (right <= left) return;
          nextShapes.push({
            name: telluricName, type: "rect", xref: "x", yref: "paper",
            x0: left, x1: right, y0: 0, y1: 1, layer: "below",
            fillcolor: "rgba(47, 113, 130, 0.14)", line: { width: 0 }
          });
          var first = axis.type === "log" ? Math.log10(left) : left;
          var last = axis.type === "log" ? Math.log10(right) : right;
          var center = (first + last) / 2;
          var pixel = (center - axisLow) / (axisHigh - axisLow) * axis._length;
          if ((last - first) / (axisHigh - axisLow) * axis._length < 35 || pixel - lastLabelPixel < 55) return;
          lastLabelPixel = pixel;
          nextAnnotations.push({
            name: telluricName, xref: "x", yref: "paper", x: center, y: 0.02,
            text: band.label.slice(9), showarrow: false, xanchor: "center", yanchor: "bottom",
            font: { size: 10, color: "#246478" }, bgcolor: "rgba(255,255,255,0.8)",
            hovertext: band.label + "<br>Approx. " + start.toFixed(0) + "–" + end.toFixed(0) +
              " Å (" + medium.value + ", upload frame)<br>Atmospheric guides do not follow stellar redshift. Strength varies with observing conditions."
          });
        });
      }
      // Preserve fit bounds and other annotations. The equality check also
      // stops our own relayout from starting an afterplot/relayout loop.
      if (JSON.stringify(shapes) !== JSON.stringify(nextShapes) ||
          JSON.stringify(annotations) !== JSON.stringify(nextAnnotations)) {
        Plotly.relayout(target, { shapes: nextShapes, annotations: nextAnnotations });
      }
    }

    function schedule() {
      if (frame === null) frame = window.requestAnimationFrame(refresh);
    }

    show.addEventListener("change", function () {
      group.disabled = labels.disabled = !show.checked;
      schedule();
    });
    [group, medium, labels].forEach(function (input) { input.addEventListener("change", schedule); });
    if (telluricShow) telluricShow.addEventListener("change", schedule);
    if (diagnosticShow) diagnosticShow.addEventListener("change", schedule);
    if (exclusionShow) exclusionShow.addEventListener("change", schedule);
    // afterplot covers zoom, scale, resize, fit bounds, and transformed/model
    // traces; no extra traces are added to legends or fitting/export data.
    target.on("plotly_afterplot", schedule);
    schedule();
  }

  function referenceLines(medium, redshift) {
    var lines = commonCatalog.slice();
    try {
      var settings = JSON.parse(window.localStorage.getItem(customStorageKey));
      if (settings && settings.text) lines = lines.concat(parseCustomLines(settings.text, settings.medium).lines);
    } catch (error) { /* Common lines remain available without browser storage. */ }
    return lines.map(function (line) {
      var wave = line.vacuum * (1 + redshift);
      return { label: line.label, wavelength: medium === "air" ? vacuumToAir(wave) : wave,
        color: colors[line.group] };
    });
  }

  window.CmfgenSpectralLines = { bind: bind, parseCustomLines: parseCustomLines, referenceLines: referenceLines,
    telluricIntervals: telluricIntervals, appendTelluricExclusions: appendTelluricExclusions,
    vacuumToAir: vacuumToAir, airToVacuum: airToVacuum };
})();
