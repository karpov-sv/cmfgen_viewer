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
  var plotLayout = pageConfig.plot_data_layout;
  var plotConfig = pageConfig.plot_data_config;
  var spectrumMode = pageConfig.mode;

  var LIGHT_SPEED_KM_PER_S = 299792.458;

  var xScale = document.getElementById(pageConfig.x_scale_id);
  var yScale = document.getElementById(pageConfig.y_scale_id);
  var redshiftInput = document.getElementById(pageConfig.redshift_id);
  var velocityInput = document.getElementById(pageConfig.velocity_id);
  var broadeningInput = document.getElementById(pageConfig.broadening_id);
  var ebvInput = document.getElementById(pageConfig.ebv_id);
  var distanceInput = document.getElementById(pageConfig.distance_id);
  var resetTransform = document.getElementById(pageConfig.reset_transform_id);
  var transformHint = document.getElementById(pageConfig.transform_hint_id);
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
  var isSyncingVelocity = false;
  var transformFrame = null;
  var showFinal = true;
  var showContinuum = true;

  function formatNumeric(value, decimals) {
    if (!Number.isFinite(value)) {
      return "";
    }
    return Number(value.toFixed(decimals)).toString();
  }

  function setTransformHint(message, isError) {
    if (!transformHint) {
      return;
    }
    transformHint.textContent = message;
    transformHint.classList.toggle("text-danger", !!isError);
    transformHint.classList.toggle("text-muted", !isError);
  }

  function updateVelocityFromRedshift() {
    if (!redshiftInput || !velocityInput) {
      return;
    }
    var redshift = Number(redshiftInput.value);
    if (!Number.isFinite(redshift)) {
      return;
    }
    isSyncingVelocity = true;
    velocityInput.value = formatNumeric(redshift * LIGHT_SPEED_KM_PER_S, 6);
    isSyncingVelocity = false;
  }

  function updateRedshiftFromVelocity() {
    if (!redshiftInput || !velocityInput) {
      return;
    }
    var velocity = Number(velocityInput.value);
    if (!Number.isFinite(velocity)) {
      return;
    }
    isSyncingVelocity = true;
    redshiftInput.value = formatNumeric(velocity / LIGHT_SPEED_KM_PER_S, 10);
    isSyncingVelocity = false;
  }

  function applyAxisScale() {
    CmfgenSpectrumControls.setAxisScale(target, xScale.value, yScale.value);
  }

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

  function applyPhysicalTransforms() {
    var redshift = redshiftInput ? Number(redshiftInput.value) : 0;
    if (!Number.isFinite(redshift)) {
      redshift = 0;
    }
    if ((1 + redshift) <= 0) {
      setTransformHint("Redshift must be greater than -1.", true);
      return;
    }

    var distanceKpc = distanceInput ? Number(distanceInput.value) : 1;
    if (!Number.isFinite(distanceKpc) || distanceKpc <= 0) {
      setTransformHint("Distance must be a positive number in kpc.", true);
      return;
    }

    var ebv = ebvInput ? Number(ebvInput.value) : 0;
    if (!Number.isFinite(ebv)) {
      setTransformHint("E(B-V) must be a valid number.", true);
      return;
    }

    var sigmaVelocity = broadeningInput ? Number(broadeningInput.value) : 0;
    if (!Number.isFinite(sigmaVelocity) || sigmaVelocity < 0) {
      setTransformHint("Velocity dispersion must be zero or positive (km/s).", true);
      return;
    }

    var broadeningText = sigmaVelocity > 0
      ? " Gaussian line broadening uses sigma_v=" + formatNumeric(sigmaVelocity, 4) + " km/s."
      : " Gaussian line broadening is disabled.";
    if (spectrumMode === "both") {
      setTransformHint("Flux is shown in erg s^-1 cm^-2 Å^-1, distance-scaled as 1/d^2 (1 kpc reference), and reddened with Fitzpatrick (1999) using E(B-V)." + broadeningText, false);
    } else {
      setTransformHint("Normalized mode applies wavelength shift only; distance and reddening cancel in F/Fc." + broadeningText, false);
    }

    var transformedX = [];
    var transformedY = [];

    for (var traceIndex = 0; traceIndex < baseData.length; traceIndex += 1) {
      var sourceX = baseData[traceIndex].x;
      var sourceY = baseData[traceIndex].y;
      if (transformTargets[traceIndex] !== "model") {
        transformedX.push(sourceX.slice());
        transformedY.push(sourceY.slice());
        continue;
      }

      var shouldBroaden = spectrumMode !== "both" || baseData[traceIndex].meta?.plot_role === "final";
      var transformed = CmfgenSpectrumTransforms.transformSeries(sourceX, sourceY, {
        mode: spectrumMode, redshift: redshift, distance_kpc: distanceKpc,
        ebv: ebv, broadening_km_s: shouldBroaden ? sigmaVelocity : 0
      });
      transformedX.push(transformed[0]);
      transformedY.push(transformed[1]);
    }

    sampling.setSeries(transformedX, transformedY);
  }

  function scheduleTransforms() {
    if (transformFrame !== null) {
      window.cancelAnimationFrame(transformFrame);
    }
    transformFrame = window.requestAnimationFrame(function () {
      transformFrame = null;
      applyPhysicalTransforms();
    });
  }

  var sampling = CmfgenSpectrumSampling.create(target, plotData, plotLayout);
  Plotly.newPlot(target, sampling.initialData, plotLayout, plotConfig).then(function () {
    sampling.bind();
    xScale.addEventListener("change", applyAxisScale);
    yScale.addEventListener("change", applyAxisScale);
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
    if (redshiftInput) {
      redshiftInput.addEventListener("input", function () {
        if (!isSyncingVelocity) {
          updateVelocityFromRedshift();
        }
        scheduleTransforms();
      });
    }
    if (velocityInput) {
      velocityInput.addEventListener("input", function () {
        if (!isSyncingVelocity) {
          updateRedshiftFromVelocity();
        }
        scheduleTransforms();
      });
    }
    if (distanceInput) {
      distanceInput.addEventListener("input", scheduleTransforms);
    }
    if (ebvInput) {
      ebvInput.addEventListener("input", scheduleTransforms);
    }
    if (broadeningInput) {
      broadeningInput.addEventListener("input", scheduleTransforms);
    }
    if (resetTransform) {
      resetTransform.addEventListener("click", function () {
        if (redshiftInput) {
          redshiftInput.value = "0";
        }
        if (velocityInput) {
          velocityInput.value = "0";
        }
        if (broadeningInput) {
          broadeningInput.value = "0";
        }
        if (distanceInput) {
          distanceInput.value = "1";
        }
        if (ebvInput) {
          ebvInput.value = "0";
        }
        scheduleTransforms();
      });
    }
    updateVelocityFromRedshift();
    applyAxisScale();
    scheduleTransforms();
    syncVisibilityButtons();
    applyBulkVisibilityToggles();
    CmfgenSpectrumControls.bindVerticalResize(target);
    CmfgenSpectralLines.bind(target, { redshiftInput: redshiftInput });
  });
})();
