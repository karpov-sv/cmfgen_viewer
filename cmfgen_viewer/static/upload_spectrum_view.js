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
  var yAxisName = spectrumMode === "both" ? "Flux" : "Normalized";

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

  function cloneTraceWithArrays(trace) {
    var cloned = Object.assign({}, trace);
    if (trace.line && typeof trace.line === "object") {
      cloned.line = Object.assign({}, trace.line);
    }
    if (trace.meta && typeof trace.meta === "object") {
      cloned.meta = Object.assign({}, trace.meta);
    }
    cloned.x = Array.isArray(trace.x) ? trace.x.slice() : [];
    cloned.y = Array.isArray(trace.y) ? trace.y.slice() : [];
    return cloned;
  }

  function cloneLayoutShape(shape) {
    if (!shape || typeof shape !== "object") {
      return shape;
    }
    var cloned = Object.assign({}, shape);
    if (shape.line && typeof shape.line === "object") {
      cloned.line = Object.assign({}, shape.line);
    }
    return cloned;
  }

  function transformTargetForTrace(trace) {
    if (trace && trace.meta && trace.meta.transform_target === "observed") {
      return "observed";
    }
    return "model";
  }

  var transformTargets = [];
  var baseData = [];
  for (var baseTraceIndex = 0; baseTraceIndex < plotData.length; baseTraceIndex += 1) {
    baseData.push(cloneTraceWithArrays(plotData[baseTraceIndex]));
    transformTargets.push(transformTargetForTrace(plotData[baseTraceIndex]));
  }
  var baseLayoutShapes = Array.isArray(plotLayout.shapes)
    ? plotLayout.shapes.map(cloneLayoutShape)
    : [];
  var gridOverlayIndex = -1;
  var pendingOverlayAction = null;
  var pendingFitRangeAction = null;
  var fitRangeSignature = "";
  var isSyncingVelocity = false;
  var transformFrame = null;

  function formatNumeric(value, decimals) {
    if (!Number.isFinite(value)) {
      return "";
    }
    return Number(value.toFixed(decimals)).toString();
  }

  function normalizeFitRangeValue(value) {
    if (value === null || value === undefined || String(value).trim() === "") {
      return null;
    }
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return null;
    }
    return numeric;
  }

  function fitRangeMarkerSignature(minValue, maxValue) {
    var minText = minValue === null ? "" : formatNumeric(minValue, 6);
    var maxText = maxValue === null ? "" : formatNumeric(maxValue, 6);
    return minText + "|" + maxText;
  }

  function buildFitRangeShapes(minValue, maxValue) {
    var nextShapes = baseLayoutShapes.map(cloneLayoutShape);
    var baseLine = {
      color: "#198754",
      width: 1.2,
      dash: "dot"
    };
    if (minValue !== null) {
      nextShapes.push({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: minValue,
        x1: minValue,
        y0: 0,
        y1: 1,
        line: Object.assign({}, baseLine)
      });
    }
    if (maxValue !== null) {
      nextShapes.push({
        type: "line",
        xref: "x",
        yref: "paper",
        x0: maxValue,
        x1: maxValue,
        y0: 0,
        y1: 1,
        line: Object.assign({}, baseLine)
      });
    }
    return nextShapes;
  }

  function applyFitRangeMarkersNow(minValue, maxValue) {
    if (!target.data || !target.layout) {
      return;
    }
    var normalizedMin = normalizeFitRangeValue(minValue);
    var normalizedMax = normalizeFitRangeValue(maxValue);
    if (normalizedMin !== null && normalizedMax !== null && normalizedMin > normalizedMax) {
      var swap = normalizedMin;
      normalizedMin = normalizedMax;
      normalizedMax = swap;
    }
    var signature = fitRangeMarkerSignature(normalizedMin, normalizedMax);
    if (signature === fitRangeSignature) {
      return;
    }
    fitRangeSignature = signature;
    var nextShapes = buildFitRangeShapes(normalizedMin, normalizedMax);
    plotLayout.shapes = nextShapes.map(cloneLayoutShape);
    Plotly.relayout(target, {
      shapes: nextShapes
    });
  }

  function setFitRangeMarkers(minValue, maxValue) {
    if (!target.data || !target.layout) {
      pendingFitRangeAction = {
        min: minValue,
        max: maxValue
      };
      return;
    }
    applyFitRangeMarkersNow(minValue, maxValue);
  }

  function clearFitRangeMarkers() {
    setFitRangeMarkers(null, null);
  }

  function applyPendingFitRangeAction() {
    if (!pendingFitRangeAction) {
      return;
    }
    var bounds = pendingFitRangeAction;
    pendingFitRangeAction = null;
    setFitRangeMarkers(bounds.min, bounds.max);
  }

  function setTransformHint(message, isError) {
    if (!transformHint) {
      return;
    }
    transformHint.textContent = message;
    transformHint.classList.toggle("text-danger", !!isError);
    transformHint.classList.toggle("text-muted", !isError);
  }

  function formatOverlayRmse(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    return numeric.toExponential(4);
  }

  function buildGridOverlayTrace(overlay, isFinal) {
    if (!overlay || typeof overlay !== "object") {
      return null;
    }
    var xValues = Array.isArray(overlay.x) ? overlay.x.slice() : [];
    var yValues = Array.isArray(overlay.y) ? overlay.y.slice() : [];
    if (xValues.length < 2 || yValues.length < 2 || xValues.length !== yValues.length) {
      return null;
    }

    var modelPath = String(overlay.model_path || overlay.model_name || "");
    var rmseText = formatOverlayRmse(overlay.rmse);
    var label = isFinal ? "Best Fit Model" : "Best-So-Far Model";
    if (modelPath) {
      label += " (" + modelPath + ")";
    }
    if (rmseText) {
      label += " RMSE=" + rmseText;
    }
    var yLabel = yAxisName === "Flux" ? "Flux" : "Normalized";
    var hover = yAxisName === "Flux"
      ? "Wavelength=%{x:.6g} Å<br>Best Model Flux=%{y:.6e}<extra></extra>"
      : "Wavelength=%{x:.6g} Å<br>Best Model Normalized=%{y:.6g}<extra></extra>";

    return {
      type: "scatter",
      mode: "lines",
      name: label,
      x: xValues,
      y: yValues,
      line: {
        color: isFinal ? "#fd7e14" : "#0d6efd",
        width: isFinal ? 1.8 : 1.5,
        dash: isFinal ? "solid" : "dash"
      },
      hovertemplate: hover,
      meta: {
        transform_target: "observed",
        plot_role: "grid_fit_best",
        y_axis_name: yLabel
      }
    };
  }

  function applyGridOverlayTraceNow(overlay, isFinal) {
    if (!target.data) {
      return;
    }
    var trace = buildGridOverlayTrace(overlay, isFinal);
    if (!trace) {
      clearGridOverlayTraceNow();
      return;
    }
    var cloned = cloneTraceWithArrays(trace);
    if (gridOverlayIndex >= 0 && gridOverlayIndex < baseData.length) {
      baseData[gridOverlayIndex] = cloned;
      transformTargets[gridOverlayIndex] = "observed";
      trace = sampling.replaceTrace(gridOverlayIndex, trace);
      Plotly.restyle(target, {
        x: [trace.x],
        y: [trace.y],
        name: [trace.name],
        line: [trace.line],
        hovertemplate: [trace.hovertemplate],
        meta: [trace.meta]
      }, [gridOverlayIndex]).then(function () {
        scheduleTransforms();
      });
      return;
    }
    gridOverlayIndex = baseData.length;
    baseData.push(cloned);
    transformTargets.push("observed");
    trace = sampling.appendTrace(trace);
    Plotly.addTraces(target, [trace]).then(function () {
      scheduleTransforms();
    });
  }

  function clearGridOverlayTraceNow() {
    if (!target.data) {
      return;
    }
    if (gridOverlayIndex < 0 || gridOverlayIndex >= baseData.length) {
      gridOverlayIndex = -1;
      return;
    }
    var deleteIndex = gridOverlayIndex;
    baseData.splice(deleteIndex, 1);
    transformTargets.splice(deleteIndex, 1);
    gridOverlayIndex = -1;
    sampling.removeTrace(deleteIndex);
    Plotly.deleteTraces(target, [deleteIndex]).then(function () {
      scheduleTransforms();
    });
  }

  function setGridOverlayTrace(overlay, isFinal) {
    if (!target.data) {
      pendingOverlayAction = {
        type: "set",
        overlay: overlay,
        isFinal: !!isFinal
      };
      return;
    }
    applyGridOverlayTraceNow(overlay, !!isFinal);
  }

  function clearGridOverlayTrace() {
    if (!target.data) {
      pendingOverlayAction = { type: "clear" };
      return;
    }
    clearGridOverlayTraceNow();
  }

  function applyPendingOverlayAction() {
    if (!pendingOverlayAction) {
      return;
    }
    var action = pendingOverlayAction;
    pendingOverlayAction = null;
    if (action.type === "clear") {
      clearGridOverlayTrace();
      return;
    }
    if (action.type === "set") {
      setGridOverlayTrace(action.overlay, !!action.isFinal);
    }
  }

  window.uploadSpectrumGridOverlay = {
    set: function (overlay, isFinal) {
      setGridOverlayTrace(overlay, !!isFinal);
    },
    clear: function () {
      clearGridOverlayTrace();
    },
    setFitRange: function (minValue, maxValue) {
      setFitRangeMarkers(minValue, maxValue);
    },
    clearFitRange: function () {
      clearFitRangeMarkers();
    }
  };

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
      setTransformHint("Absolute mode applies wavelength shift, reddening, distance scaling, and optional broadening." + broadeningText, false);
    } else {
      setTransformHint("Normalized mode applies wavelength shift and optional broadening." + broadeningText, false);
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
    CmfgenSpectrumControls.bindVerticalResize(target);
    CmfgenSpectralLines.bind(target, { redshiftInput: redshiftInput });
    applyPendingOverlayAction();
    applyPendingFitRangeAction();
  });
})();
