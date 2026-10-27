(() => {
  "use strict";

  const payload = document.getElementById("model-convergence-plots");
  const targets = Array.from(document.querySelectorAll("[data-model-convergence-plot]"));
  if (!payload || !targets.length) {
    return;
  }
  if (!window.Plotly) {
    targets.forEach((target) => {
      target.textContent = "Plotly failed to load.";
      target.classList.add("small", "text-muted", "p-3");
    });
    return;
  }

  let plots;
  try {
    plots = JSON.parse(payload.textContent);
  } catch (_error) {
    return;
  }

  const bindVerticalResize = (plotElement) => {
    const container = plotElement.closest(".plotly-resizable");
    if (!container) {
      return;
    }
    if (window.ResizeObserver) {
      let frameId = null;
      const observer = new ResizeObserver(() => {
        if (frameId !== null) {
          window.cancelAnimationFrame(frameId);
        }
        frameId = window.requestAnimationFrame(() => {
          if (plotElement.data) {
            window.Plotly.Plots.resize(plotElement);
          }
        });
      });
      observer.observe(container);
    }

    const handle = container.querySelector(".plot-resize-handle");
    if (!handle) {
      return;
    }
    let drag = null;
    const finish = (event) => {
      if (!drag || event.pointerId !== drag.pointerId) {
        return;
      }
      drag = null;
      document.body.classList.remove("plot-resizing");
    };
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) {
        return;
      }
      event.preventDefault();
      drag = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight: container.getBoundingClientRect().height,
      };
      handle.setPointerCapture?.(event.pointerId);
      document.body.classList.add("plot-resizing");
    });
    handle.addEventListener("pointermove", (event) => {
      if (!drag || event.pointerId !== drag.pointerId) {
        return;
      }
      container.style.height = `${Math.max(320, Math.round(drag.startHeight + event.clientY - drag.startY))}px`;
      if (plotElement.data) {
        window.Plotly.Plots.resize(plotElement);
      }
    });
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  };

  const charts = [];
  targets.forEach((target) => {
    const index = Number.parseInt(target.dataset.modelConvergencePlot, 10);
    const plot = plots[index];
    if (!plot) {
      return;
    }
    const panel = target.closest('[data-convergence-panel]');
    if (panel) panel.hidden = !plot.data.some(trace => trace.x?.length);
    const ready = window.Plotly.newPlot(target, plot.data, plot.layout, plot.config).then(() => {
      bindVerticalResize(target);
    });
    if (plot.history_key) charts.push({target, panel, plot, ready});
  });

  const toggle = document.querySelector('[data-correction-history-toggle]');
  const status = document.querySelector('[data-correction-history-status]');
  if (!toggle || !status || !charts.length) return;
  const preference = 'cmfgen:correction-history:' + toggle.dataset.historyPreference;
  let history = null, pending = null;
  function render() {
    const show = toggle.checked && history;
    charts.forEach(({target, panel, plot}) => {
      const data = JSON.parse(JSON.stringify(plot.data));
      const layout = JSON.parse(JSON.stringify(plot.layout));
      layout.uirevision = show ? 'earlier-runs' : 'current-run';
      const earlier = show ? history[plot.history_key] : [];
      const displayed = [...earlier, ...data];
      if (panel) panel.hidden = !displayed.some(trace => trace.x?.length);
      window.Plotly.react(target, displayed, layout, plot.config);
    });
    status.textContent = show ? (history.run_count ?
      `${history.run_count} earlier runs, ${history.record_count} completed solves. ${history.note}${history.limited ? ' History was truncated to its size limits.' : ''}${history.luminosity_data.length ? '' : ' No earlier luminosity records are available.'}` :
      'No earlier records are available.') : '';
  }
  async function update() {
    try { window.localStorage?.setItem(preference, toggle.checked ? '1' : '0'); } catch (_error) {}
    if (!toggle.checked) { await Promise.all(charts.map(chart => chart.ready)); render(); return; }
    if (!history) {
      status.textContent = 'Loading earlier correction and luminosity history…';
      try {
        pending ||= fetch(toggle.dataset.historyUrl, {cache:'no-store', credentials:'same-origin'})
          .then(response => { if (!response.ok) throw new Error('History unavailable'); return response.json(); });
        history = await pending;
        if (!Array.isArray(history.data) || !Array.isArray(history.luminosity_data)) throw new Error('Invalid history');
      } catch (_error) {
        history = null; pending = null; toggle.checked = false;
        status.textContent = 'Could not load earlier history. Toggle again to retry.';
        return;
      }
    }
    await Promise.all(charts.map(chart => chart.ready));
    render();
  }
  toggle.addEventListener('change', update);
  try { toggle.checked = window.localStorage?.getItem(preference) === '1'; } catch (_error) {}
  if (toggle.checked) update();
})();
