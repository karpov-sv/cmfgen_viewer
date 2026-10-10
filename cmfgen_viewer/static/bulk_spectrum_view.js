(function () {
  "use strict";
  var pageConfig = JSON.parse(document.currentScript.previousElementSibling.textContent);
  var target = document.getElementById(pageConfig.plot_id);
  if (!target || !window.Plotly) {
    if (target) {
      target.innerHTML = '<p class="text-muted small mb-0">Plotly failed to load.</p>';
    }
    return;
  }

  var plotData = pageConfig.plot_data_data;
  var spectrumMode = pageConfig.mode;

  var finalToggle = document.getElementById(pageConfig.final_toggle_id);
  var continuumToggle = document.getElementById(pageConfig.continuum_toggle_id);

  var transformTargets = [];
  var baseData = plotData.map(function (trace) {
    var cloned = Object.assign({}, trace);
    cloned.x = Array.isArray(trace.x) ? trace.x.slice() : [];
    cloned.y = Array.isArray(trace.y) ? trace.y.slice() : [];
    var targetKind = "model";
    if (trace.meta && trace.meta.transform_target === "observed") {
      targetKind = "observed";
    }
    transformTargets.push(targetKind);
    return cloned;
  });
  var showFinal = true;
  var showContinuum = true;

  function syncVisibilityButtons() {
    if (finalToggle) {
      finalToggle.textContent = showFinal ? "Final: On" : "Final: Off";
      finalToggle.classList.toggle("btn-primary", showFinal);
      finalToggle.classList.toggle("btn-outline-secondary", !showFinal);
    }
    if (continuumToggle) {
      continuumToggle.textContent = showContinuum ? "Continuum: On" : "Continuum: Off";
      continuumToggle.classList.toggle("btn-primary", showContinuum);
      continuumToggle.classList.toggle("btn-outline-secondary", !showContinuum);
    }
  }

  function applyBulkVisibilityToggles() {
    if (spectrumMode !== "both") {
      return;
    }
    var visibleValues = baseData.map(function (trace) {
      var role = trace.meta && trace.meta.plot_role ? String(trace.meta.plot_role) : "";
      if (role === "final") {
        return showFinal ? true : "legendonly";
      }
      if (role === "continuum") {
        return showContinuum ? true : "legendonly";
      }
      return true;
    });
    Plotly.restyle(target, { visible: visibleValues });
    syncVisibilityButtons();
  }

  var viewer = CmfgenSpectrumViewer.create(pageConfig, {
    baseData: baseData,
    transformTargets: transformTargets,
    shouldBroaden: function (index, trace) { return spectrumMode !== "both" || trace.meta?.plot_role === "final"; }
  });
  viewer.ready.then(function () {
    if (finalToggle) {
      finalToggle.addEventListener("click", function () {
        showFinal = !showFinal;
        applyBulkVisibilityToggles();
      });
    }
    if (continuumToggle) {
      continuumToggle.addEventListener("click", function () {
        showContinuum = !showContinuum;
        applyBulkVisibilityToggles();
      });
    }
    syncVisibilityButtons();
    applyBulkVisibilityToggles();
  });
})();
