/* Lazy, in-page spectrum comparison for the Models and bulk summary tables. */
(function () {
  "use strict";
  const panel = document.getElementById("model-spectrum-comparison");
  if (!panel) return;
  const target = document.getElementById("model-comparison-plot");
  const canvas = document.getElementById("comparison-canvas");
  const status = document.getElementById("comparison-status");
  const errors = document.getElementById("comparison-errors");
  const mode = document.getElementById("comparison-mode");
  const xScale = document.getElementById(target.id + "-xscale");
  const yScale = document.getElementById(target.id + "-yscale");
  const clear = document.getElementById("comparison-clear");
  const refresh = document.getElementById("comparison-refresh");
  const selectVisible = document.getElementById("comparison-select-visible");
  const table = document.getElementById("summary-table");
  const boxes = Array.from(table.querySelectorAll(".comparison-model"));
  const colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22"];
  const cache = new Map();
  let generation = 0;
  let viewer = null;
  let active = 0;
  const queue = [];

  if (!window.Plotly) {
    status.textContent = "Plotly failed to load. Reload the page to compare spectra.";
    boxes.forEach(box => { box.disabled = true; });
    selectVisible.disabled = true;
    return;
  }

  function pump() {
    while (active < 3 && queue.length) {
      const job = queue.shift();
      active += 1;
      job().finally(() => { active -= 1; pump(); });
    }
  }

  function load(path, spectrumMode) {
    const key = JSON.stringify([path, spectrumMode]);
    if (!cache.has(key)) {
      cache.set(key, new Promise(resolve => {
        queue.push(async () => {
          try {
            const url = new URL(panel.dataset.spectrumUrl, window.location.href);
            url.searchParams.set("model", path);
            url.searchParams.set("mode", spectrumMode);
            const response = await fetch(url, { headers: { Accept: "application/json" } });
            const data = await response.json();
            if (!response.ok || !data.plot) throw new Error(data.error || "Spectrum could not be loaded.");
            resolve(data);
          } catch (error) {
            // Failed loads may be retried after a spectrum finishes computing.
            cache.delete(key);
            resolve({ error: error.message || "Spectrum could not be loaded." });
          }
        });
        pump();
      }));
    }
    return cache.get(key);
  }

  function syncSelectVisible() {
    const visible = boxes.filter(box => !box.closest("tr").hidden);
    const count = visible.filter(box => box.checked).length;
    selectVisible.checked = visible.length > 0 && count === visible.length;
    selectVisible.indeterminate = count > 0 && count < visible.length;
    selectVisible.disabled = !visible.length;
  }

  async function update() {
    const revision = ++generation;
    const selected = boxes.filter(box => box.checked);
    const spectrumMode = mode.value;
    clear.disabled = refresh.disabled = !selected.length;
    syncSelectVisible();
    errors.replaceChildren();
    errors.hidden = true;
    if (!selected.length) {
      status.textContent = "Select models using the checkboxes in the table below.";
      canvas.hidden = true;
      if (viewer) await viewer.ready.then(() => viewer.sampling.setTraces([], target.layout, target._context));
      return;
    }
    status.textContent = "Loading spectra for " + selected.length + " model(s)…";
    const results = await Promise.all(selected.map(box => load(box.value, spectrumMode)));
    if (revision !== generation) return;
    const traces = [];
    let firstPlot = null;
    let plotted = 0;
    results.forEach((result, index) => {
      const box = selected[index];
      const label = box.value || "ROOT";
      if (result.error) {
        const item = document.createElement("li");
        item.textContent = label + ": " + result.error;
        errors.appendChild(item);
        return;
      }
      firstPlot = firstPlot || result.plot;
      plotted += 1;
      result.plot.data.forEach((trace, traceIndex) => {
        const role = trace.meta.plot_role;
        traces.push(Object.assign({}, trace, {
          // Plotly also uses trace IDs in CSS selectors during cleanup.
          uid: "comparison-" + boxes.indexOf(box) + "-" + spectrumMode + "-" + role,
          name: label + (role === "continuum" ? " · continuum" : " · " + result.fin),
          legendgroup: box.value || "ROOT",
          legendgrouptitle: undefined,
          line: Object.assign({}, trace.line, { color: colors[boxes.indexOf(box) % colors.length], dash: traceIndex ? "dot" : "solid" }),
          hovertemplate: trace.hovertemplate.replace("<extra></extra>", "<extra>%{fullData.name}</extra>")
        }));
      });
    });
    errors.hidden = !errors.children.length;
    status.textContent = plotted + " of " + selected.length + " selected models displayed.";
    canvas.hidden = !traces.length;
    if (!traces.length) return;
    const layout = Object.assign({}, firstPlot.layout, {
      uirevision: spectrumMode + ":" + xScale.value + ":" + yScale.value,
      xaxis: Object.assign({}, firstPlot.layout.xaxis, { type: xScale.value }),
      // Keep the wavelength window while fitting the flux range to newly
      // added models, including deeper lines outside the old vertical range.
      yaxis: Object.assign({}, firstPlot.layout.yaxis, {
        type: yScale.value, autorange: true,
        uirevision: JSON.stringify([spectrumMode, yScale.value, selected.map(box => box.value)])
      }),
      legend: Object.assign({}, firstPlot.layout.legend, { groupclick: "toggleitem" })
    });
    if (!viewer) viewer = CmfgenSpectrumControls.createPlot(target, [], layout, firstPlot.config);
    await viewer.ready;
    if (revision !== generation) return;
    await viewer.sampling.setTraces(traces, layout, firstPlot.config);
    await Plotly.Plots.resize(target);
  }

  function requestUpdate() {
    update().catch(error => {
      status.textContent = "Spectrum comparison failed: " + error.message;
    });
  }
  boxes.forEach((box, index) => {
    box.style.accentColor = colors[index % colors.length];
    box.addEventListener("change", requestUpdate);
  });
  selectVisible.addEventListener("change", () => {
    boxes.filter(box => !box.closest("tr").hidden).forEach(box => { box.checked = selectVisible.checked; });
    requestUpdate();
  });
  clear.addEventListener("click", () => {
    boxes.forEach(box => { box.checked = false; });
    requestUpdate();
  });
  refresh.addEventListener("click", () => { cache.clear(); requestUpdate(); });
  mode.addEventListener("change", () => {
    yScale.value = mode.value === "both" ? "log" : "linear";
    requestUpdate();
  });
  xScale.addEventListener("change", requestUpdate);
  yScale.addEventListener("change", requestUpdate);
  // Scatter selection hides rows without replacing them; sorting moves rows.
  new MutationObserver(syncSelectVisible).observe(table.tBodies[0], { subtree: true, attributes: true, attributeFilter: ["hidden"] });
  requestUpdate();
})();
