/* Common reference lines, in Angstroms. See doc/spectral-line-overlay.md for
 * sources and conventions. Multiplets use representative positions. */
(function () {
  "use strict";
  var markerName = "cmfgen-spectral-line";
  var colors = { hydrogen: "#a34747", helium: "#7054a2", metals: "#537787" };

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
  // SDSS supplies optical metal lines and representative UV blend positions.
  var catalog = [
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
    ["He I", "helium", 4387.929, "air"],
    ["He I", "helium", 4471.479, "air"],
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

  function bind(target, options) {
    var show = document.getElementById(target.id + "-lines-show");
    if (!show || target.__spectralLinesBound) return;
    target.__spectralLinesBound = true;
    options = options || {};
    var group = document.getElementById(target.id + "-lines-group");
    var medium = document.getElementById(target.id + "-lines-medium");
    var labels = document.getElementById(target.id + "-lines-labels");
    var zoom = document.getElementById(target.id + "-lines-zoom");
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

    function currentRedshift() {
      return options.redshiftInput ? Number(options.redshiftInput.value) : 0;
    }

    function updateZoomOptions(redshift) {
      var range = spectrumCoverage();
      zoom.querySelector('[value="full"]').disabled = !range;
      zoomOptions.forEach(function (option, index) {
        var line = catalog[index];
        var center = line[medium.value] * (1 + redshift);
        var text = line.label + " · " + center.toFixed(1) + " Å";
        if (option.textContent !== text) option.textContent = text;
        option.disabled = !range || !Number.isFinite(center) || center < range[0] || center > range[1];
      });
    }

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
      } else if (selection.indexOf("line-") === 0) {
        var line = catalog[Number(selection.slice(5))];
        var redshift = currentRedshift();
        if (!line || !Number.isFinite(redshift) || redshift <= -1) return;
        var center = line[medium.value] * (1 + redshift);
        zoomToRange([Math.max(center - 150, 1), center + 150]);
      }
    });

    function refresh() {
      frame = null;
      if (!target.layout || !target._fullLayout) return;
      var shapes = target.layout.shapes || [];
      var annotations = target.layout.annotations || [];
      var nextShapes = shapes.filter(function (item) { return item.name !== markerName; });
      var nextAnnotations = annotations.filter(function (item) { return item.name !== markerName; });
      var axis = target._fullLayout.xaxis;
      var redshift = currentRedshift();
      updateZoomOptions(redshift);
      // Invalid transform inputs leave both the spectrum and its markers at
      // their last valid positions, rather than drawing at invalid wavelengths.
      if (show.checked && (!Number.isFinite(redshift) || redshift <= -1)) return;
      if (show.checked && axis && Array.isArray(axis.range)) {
        var low = Math.min(axis.range[0], axis.range[1]);
        var high = Math.max(axis.range[0], axis.range[1]);
        var candidates = [];
        catalog.forEach(function (line) {
          if (group.value !== "all" && group.value !== line.group) return;
          var rest = line[medium.value];
          var wavelength = rest * (1 + redshift);
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
        // Keep every marker. Give hydrogen labels priority in crowded views,
        // so a nearby metal or helium feature cannot obscure Hα or Hβ.
        var priority = { hydrogen: 0, helium: 1, metals: 2 };
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
            text: line.label, textangle: -90, showarrow: false,
            xanchor: "center", yanchor: "top", font: { size: 10, color: colors[line.group] },
            bgcolor: "rgba(255,255,255,0.75)", borderpad: 1,
            hovertext: line.label + "<br>Rest: " + candidate.rest.toFixed(2) + " Å (" +
              (medium.value === "air" && line.vacuum >= 2000 ? "air" : "vacuum") +
              ")<br>Shifted: " + candidate.wavelength.toFixed(2) + " Å"
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
    // afterplot covers zoom, scale, resize, fit bounds, and transformed/model
    // traces; no extra traces are added to legends or fitting/export data.
    target.on("plotly_afterplot", schedule);
    schedule();
  }

  window.CmfgenSpectralLines = { bind: bind };
})();
