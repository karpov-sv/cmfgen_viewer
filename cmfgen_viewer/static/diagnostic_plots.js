/* Diagnostic plots are snapshots of the fitted model, independent of display controls. */
(function () {
  "use strict";

  function escapeText(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function clipSeries(source, lower, upper, neighbors) {
    var x = source.x || [], y = source.y || [];
    // Wavelength arrays are sorted. Keep neighboring model samples so the
    // interpolated profile reaches both window edges without extrapolation.
    function bound(value, right) {
      var lo = 0, hi = x.length;
      while (lo < hi) {
        var mid = (lo + hi) >>> 1;
        if (x[mid] < value || (right && x[mid] === value)) lo = mid + 1;
        else hi = mid;
      }
      return lo;
    }
    var first = Math.max(0, bound(lower, false) - (neighbors ? 1 : 0));
    var last = Math.min(x.length, bound(upper, true) + (neighbors ? 1 : 0));
    return { x: x.slice(first, last), y: y.slice(first, last) };
  }

  function windowPlot(score, observed, model, medium, exclusions, lines, mode) {
    var lower = Number(score.min), upper = Number(score.max);
    var traces = observed.map(function (source) {
      var series = clipSeries(source, lower, upper, false);
      return { x: series.x, y: series.y, type: "scatter", mode: "lines",
        name: "Observed", line: { color: "#245b85", width: 1.2 },
        hovertemplate: "%{x:.3f} Å<br>%{y:.5g}<extra>Observed</extra>" };
    });
    var profile = clipSeries(model, lower, upper, true);
    traces.push({ x: profile.x, y: profile.y, type: "scatter", mode: "lines", name: "Fitted model",
      line: { color: "#c23e38", width: 1.8 },
      hovertemplate: "%{x:.3f} Å<br>%{y:.5g}<extra>Fitted model</extra>" });
    var shapes = [], annotations = [];
    (exclusions || []).forEach(function (interval) {
      var left = Math.max(lower, Number(interval.min)), right = Math.min(upper, Number(interval.max));
      if (left > right) return;
      shapes.push({ type: "rect", xref: "x", yref: "paper", x0: left, x1: right, y0: 0, y1: 1,
        fillcolor: "rgba(108,117,125,0.18)", line: { width: 0 }, layer: "below" });
    });
    (lines || []).filter(function (line) {
      return line.wavelength >= lower && line.wavelength <= upper;
    }).forEach(function (line, index) {
      shapes.push({ type: "line", xref: "x", yref: "paper", x0: line.wavelength, x1: line.wavelength,
        y0: 0, y1: 1, line: { color: line.color, width: 1, dash: "dot" }, layer: "below" });
      annotations.push({ xref: "x", yref: "paper", x: line.wavelength, y: index % 2 ? 1.05 : 1.14,
        text: escapeText(line.label), showarrow: false, font: { size: 10, color: line.color },
        hovertext: escapeText(line.label) + " · " + line.wavelength.toFixed(3) + " Å" });
    });
    // Limit the vertical range to samples inside the window; the neighboring
    // model points exist only for interpolation at the horizontal bounds.
    var ymin = Infinity, ymax = -Infinity;
    traces.forEach(function (trace) {
      trace.x.forEach(function (x, i) {
        var y = trace.y[i];
        if (x >= lower && x <= upper && Number.isFinite(y)) { ymin = Math.min(ymin, y); ymax = Math.max(ymax, y); }
      });
    });
    var padding = Math.max((ymax - ymin) * 0.08, Math.abs(ymax) * 0.01, 1e-30);
    var yaxis = { title: { text: mode === "both" ? "Flux" : "Normalized flux" }, automargin: true };
    if (Number.isFinite(ymin) && Number.isFinite(ymax)) yaxis.range = [ymin - padding, ymax + padding];
    return { data: traces, layout: { height: 300, margin: { l: 58, r: 12, t: 42, b: 65 },
      xaxis: { title: { text: "Uploaded wavelength (Å, " + medium + ")" }, range: [lower, upper],
        exponentformat: "none", automargin: true }, yaxis: yaxis,
      shapes: shapes, annotations: annotations, hovermode: "closest",
      legend: { orientation: "h", x: 0, y: -0.3 }, font: { size: 11 } } };
  }

  function mount(container, best, options) {
    var scores = best.window_scores || [];
    if (!scores.length) return;
    var section = document.createElement("details");
    section.className = "grid-fit-result-details diagnostic-window-section";
    section.open = true;
    var summary = document.createElement("summary");
    summary.textContent = "Diagnostic window plots";
    section.appendChild(summary);
    var help = document.createElement("p");
    help.className = "small text-muted mt-1 mb-2";
    help.textContent = "Saved best-fit parameters; native observed samples and fitted model. Dotted markers show common and saved custom stellar lines at the fitted redshift. Shaded intervals are excluded from scoring; their data remain visible. Main-plot controls do not alter these snapshots.";
    section.appendChild(help);
    var status = document.createElement("p");
    status.className = "small text-muted";
    status.textContent = "Loading fitted model…";
    section.appendChild(status);
    var grid = document.createElement("div");
    grid.className = "diagnostic-window-grid";
    section.appendChild(grid);
    container.appendChild(section);
    fetch(options.url, { headers: { Accept: "application/json" } }).then(function (response) {
      return response.json().then(function (payload) {
        if (!response.ok || !payload.ok || !payload.trace) throw new Error(payload.error || "Fitted model unavailable.");
        return payload.trace;
      });
    }).then(function (model) {
      if (!section.isConnected) return;
      var sources = options.plot.__spectrumSampling.getSources().filter(function (trace) {
        return trace.meta && trace.meta.transform_target === "observed";
      });
      if (!sources.length) throw new Error("Observed samples unavailable.");
      var medium = sources[0].meta.wavelength_medium || "air";
      var lines = window.CmfgenSpectralLines.referenceLines(medium, Number(best.fit_params.redshift) || 0);
      var plots = scores.map(function (score) {
        var card = document.createElement("section");
        card.className = "diagnostic-window-card";
        var heading = document.createElement("h5");
        heading.className = "h6 mb-0";
        heading.textContent = score.label + " · " + score.min + "–" + score.max + " Å";
        card.appendChild(heading);
        var plot = document.createElement("div");
        plot.className = "diagnostic-window-plot";
        card.appendChild(plot);
        grid.appendChild(card);
        return { plot: plot, score: score };
      });
      section.addEventListener("toggle", function () {
        if (section.open) grid.querySelectorAll(".diagnostic-window-plot").forEach(function (plot) { Plotly.Plots.resize(plot); });
      });
      // Build every card before Plotly measures widths in the responsive grid.
      return Promise.all(plots.map(function (entry) {
        var spec = windowPlot(entry.score, sources, model, medium,
          best.fit_regions && best.fit_regions.exclusions, lines, options.mode);
        return Plotly.newPlot(entry.plot, spec.data, spec.layout, { responsive: true, displaylogo: false,
          modeBarButtonsToRemove: ["select2d", "lasso2d"] });
      })).then(function () { status.remove(); });
    }).catch(function (error) {
      if (!section.isConnected) return;
      status.textContent = "Could not load diagnostic plots: " + error.message;
      status.classList.add("text-danger");
    });
  }

  function purge(container) {
    container.querySelectorAll(".diagnostic-window-plot").forEach(function (plot) { Plotly.purge(plot); });
  }

  window.CmfgenDiagnosticPlots = { mount: mount, purge: purge, windowPlot: windowPlot };
})();
