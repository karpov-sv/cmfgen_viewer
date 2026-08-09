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

  targets.forEach((target) => {
    const index = Number.parseInt(target.dataset.modelConvergencePlot, 10);
    const plot = plots[index];
    if (!plot) {
      return;
    }
    window.Plotly.newPlot(target, plot.data, plot.layout, plot.config).then(() => {
      bindVerticalResize(target);
    });
  });
})();
