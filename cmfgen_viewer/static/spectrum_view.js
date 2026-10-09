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
  var transformSyncForms = document.querySelectorAll("form.spectrum-transform-sync");
  var fitForm = document.getElementById("spectrum-fit-form");
  var fitFeedback = document.getElementById("fit-feedback");
  var fitLambdaMinInput = document.getElementById("fit-lambda-min");
  var fitLambdaMaxInput = document.getElementById("fit-lambda-max");
  var fitUsePlotRangeButton = document.getElementById("fit-use-plot-range");

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

  var transformTargets = [];
  var broadeningTargets = [];
  var seenModelTraces = 0;
  var baseLayoutShapes = Array.isArray(plotLayout.shapes)
    ? plotLayout.shapes.map(cloneLayoutShape)
    : [];
  var fitRangeSignature = "";
  var baseData = plotData.map(function (trace) {
    var cloned = Object.assign({}, trace);
    cloned.x = Array.isArray(trace.x) ? trace.x.slice() : [];
    cloned.y = Array.isArray(trace.y) ? trace.y.slice() : [];
    var targetKind = "model";
    if (trace.meta && trace.meta.transform_target === "observed") {
      targetKind = "observed";
    }
    transformTargets.push(targetKind);
    var broadenThisTrace = false;
    if (targetKind === "model") {
      if (spectrumMode === "both") {
        var role = trace.meta && trace.meta.plot_role ? String(trace.meta.plot_role).toLowerCase() : "";
        if (role) {
          broadenThisTrace = role === "final";
        } else {
          var name = trace.name ? String(trace.name).toLowerCase() : "";
          if (name.indexOf("continuum") !== -1) {
            broadenThisTrace = false;
          } else if (name.indexOf("final") !== -1) {
            broadenThisTrace = true;
          } else {
            broadenThisTrace = seenModelTraces === 0;
          }
        }
        seenModelTraces += 1;
      } else {
        broadenThisTrace = true;
      }
    }
    broadeningTargets.push(broadenThisTrace);
    return cloned;
  });
  var isSyncingVelocity = false;
  var transformFrame = null;

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

  function syncTransformHiddenFields() {
    var redshiftValue = redshiftInput ? redshiftInput.value : "";
    var broadeningValue = broadeningInput ? broadeningInput.value : "";
    var ebvValue = ebvInput ? ebvInput.value : "";
    var distanceValue = distanceInput ? distanceInput.value : "";

    document.querySelectorAll(".transform-redshift-field").forEach(function (field) {
      field.value = redshiftValue;
    });
    document.querySelectorAll(".transform-broadening-field").forEach(function (field) {
      field.value = broadeningValue;
    });
    document.querySelectorAll(".transform-ebv-field").forEach(function (field) {
      field.value = ebvValue;
    });
    document.querySelectorAll(".transform-distance-field").forEach(function (field) {
      field.value = distanceValue;
    });
    if (fitLambdaMinInput) {
      document.querySelectorAll(".fit-lambda-min-field").forEach(function (field) {
        field.value = fitLambdaMinInput.value;
      });
    }
    if (fitLambdaMaxInput) {
      document.querySelectorAll(".fit-lambda-max-field").forEach(function (field) {
        field.value = fitLambdaMaxInput.value;
      });
    }
  }

  function setFitFeedback(message, isError) {
    if (!fitFeedback) {
      return;
    }
    if (!message) {
      fitFeedback.textContent = "";
      fitFeedback.classList.add("d-none");
      fitFeedback.classList.remove("alert-info");
      fitFeedback.classList.remove("alert-danger");
      return;
    }
    fitFeedback.textContent = message;
    fitFeedback.classList.remove("d-none");
    fitFeedback.classList.remove("alert-info");
    fitFeedback.classList.remove("alert-danger");
    fitFeedback.classList.add(isError ? "alert-danger" : "alert-info");
  }

  function formatRangeValue(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    return Number(numeric.toFixed(6)).toString();
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

  function parseFitRangeInputValue(input) {
    if (!input) {
      return null;
    }
    var text = String(input.value || "").trim();
    if (!text) {
      return null;
    }
    var numeric = Number(text);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return null;
    }
    return numeric;
  }

  function fitRangeMarkerSignature(minValue, maxValue) {
    var minText = minValue === null ? "" : formatRangeValue(minValue);
    var maxText = maxValue === null ? "" : formatRangeValue(maxValue);
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

  function readCurrentPlotXRange() {
    if (!target || !target._fullLayout || !target._fullLayout.xaxis) {
      return null;
    }
    var xaxis = target._fullLayout.xaxis;
    var range = xaxis.range;
    if (!Array.isArray(range) || range.length < 2) {
      return null;
    }
    var first = Number(range[0]);
    var second = Number(range[1]);
    if (!Number.isFinite(first) || !Number.isFinite(second)) {
      return null;
    }
    var axisType = String(xaxis.type || "").toLowerCase();
    if (axisType === "log") {
      first = Math.pow(10, first);
      second = Math.pow(10, second);
    }
    if (!Number.isFinite(first) || !Number.isFinite(second)) {
      return null;
    }
    var lower = Math.min(first, second);
    var upper = Math.max(first, second);
    if (lower <= 0 || upper <= lower) {
      return null;
    }
    return [lower, upper];
  }

  function applyFitRangeMarkers(minValue, maxValue) {
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

  function syncFitRangeMarkers() {
    if (!fitLambdaMinInput || !fitLambdaMaxInput) {
      return;
    }
    var minValue = parseFitRangeInputValue(fitLambdaMinInput);
    var maxValue = parseFitRangeInputValue(fitLambdaMaxInput);
    applyFitRangeMarkers(minValue, maxValue);
  }

  function applyPlotRangeToFitInputs() {
    if (!fitLambdaMinInput || !fitLambdaMaxInput) {
      return;
    }
    var range = readCurrentPlotXRange();
    if (!range) {
      setFitFeedback("Could not read the current plot range. Zoom or pan the spectrum plot first.", true);
      return;
    }
    var minText = formatRangeValue(range[0]);
    var maxText = formatRangeValue(range[1]);
    fitLambdaMinInput.value = minText;
    fitLambdaMaxInput.value = maxText;
    syncFitRangeMarkers();
    setFitFeedback("Fit wavelength range set from plot view: " + minText + " .. " + maxText + " Å.", false);
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

      var shouldBroaden = broadeningTargets[traceIndex];
      var transformed = CmfgenSpectrumTransforms.transformSeries(sourceX, sourceY, {
        mode: spectrumMode, redshift: redshift, distance_kpc: distanceKpc,
        ebv: ebv, broadening_km_s: shouldBroaden ? sigmaVelocity : 0
      });
      transformedX.push(transformed[0]);
      transformedY.push(transformed[1]);
    }

    Plotly.restyle(target, {
      x: transformedX,
      y: transformedY
    });
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

  Plotly.newPlot(target, plotData, plotLayout, plotConfig).then(function () {
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
    if (fitLambdaMinInput) {
      fitLambdaMinInput.addEventListener("input", syncFitRangeMarkers);
      fitLambdaMinInput.addEventListener("change", syncFitRangeMarkers);
    }
    if (fitLambdaMaxInput) {
      fitLambdaMaxInput.addEventListener("input", syncFitRangeMarkers);
      fitLambdaMaxInput.addEventListener("change", syncFitRangeMarkers);
    }
    if (fitUsePlotRangeButton) {
      fitUsePlotRangeButton.addEventListener("click", applyPlotRangeToFitInputs);
      if (!fitLambdaMinInput || !fitLambdaMaxInput) {
        fitUsePlotRangeButton.disabled = true;
        fitUsePlotRangeButton.title = "Fit wavelength controls are not available.";
      }
    }
    updateVelocityFromRedshift();
    if (transformSyncForms) {
      transformSyncForms.forEach(function (formElement) {
        formElement.addEventListener("submit", syncTransformHiddenFields);
      });
    }
    if (fitForm) {
      fitForm.addEventListener("submit", function (event) {
        if (!window.fetch || !window.FormData) {
          return;
        }
        event.preventDefault();
        syncTransformHiddenFields();

        var submitButton = fitForm.querySelector("button[type='submit']");
        if (submitButton) {
          submitButton.disabled = true;
        }
        setFitFeedback("Running fit...", false);

        var formData = new FormData(fitForm);
        formData.set("async", "1");

        fetch(fitForm.action, {
          method: "POST",
          body: formData,
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json"
          }
        })
          .then(function (response) {
            return response.text().then(function (rawText) {
              var payload = null;
              if (rawText) {
                try {
                  payload = JSON.parse(rawText);
                } catch (error) {
                  payload = null;
                }
              }
              return {
                ok: response.ok,
                payload: payload
              };
            });
          })
          .then(function (result) {
            if (!result.payload || typeof result.payload !== "object") {
              throw new Error("Fit failed: invalid server response.");
            }
            if (!result.ok || result.payload.ok === false) {
              throw new Error(String(result.payload.error || "Fit failed."));
            }

            var fitted = result.payload.transform_params || {};
            var redshiftValue = Number(fitted.redshift);
            var broadeningValue = Number(fitted.broadening_km_s);
            var ebvValue = Number(fitted.ebv);
            var distanceValue = Number(fitted.distance_kpc);
            if (redshiftInput && Number.isFinite(redshiftValue)) {
              redshiftInput.value = formatNumeric(redshiftValue, 10);
            }
            if (broadeningInput && Number.isFinite(broadeningValue) && broadeningValue >= 0) {
              broadeningInput.value = formatNumeric(broadeningValue, 6);
            }
            if (ebvInput && Number.isFinite(ebvValue)) {
              ebvInput.value = formatNumeric(ebvValue, 6);
            }
            if (distanceInput && Number.isFinite(distanceValue) && distanceValue > 0) {
              distanceInput.value = formatNumeric(distanceValue, 6);
            }

            updateVelocityFromRedshift();
            syncTransformHiddenFields();
            scheduleTransforms();
            setFitFeedback(String(result.payload.fit_notice || "Fit completed."), false);
          })
          .catch(function (error) {
            setFitFeedback(error && error.message ? error.message : "Fit failed.", true);
          })
          .finally(function () {
            if (submitButton) {
              submitButton.disabled = false;
            }
          });
      });
    }
    applyAxisScale();
    scheduleTransforms();
    syncTransformHiddenFields();
    CmfgenSpectrumControls.bindVerticalResize(target);
    CmfgenSpectralLines.bind(target, { redshiftInput: redshiftInput });
    syncFitRangeMarkers();
  });
})();
