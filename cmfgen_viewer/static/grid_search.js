(function () {
  "use strict";
  var pageConfig = JSON.parse(document.currentScript.previousElementSibling.textContent);
  var form = document.getElementById("grid-fit-form");
  if (!form || !window.fetch || !window.FormData) {
    return;
  }

  var statusUrlTemplate = pageConfig.statusUrlTemplate;
  var cancelUrlTemplate = pageConfig.cancelUrlTemplate;
  var overlayUrlTemplate = pageConfig.overlayUrlTemplate;
  var feedback = document.getElementById("grid-fit-feedback");
  var progressWrap = document.getElementById("grid-fit-progress-wrap");
  var progressBar = document.getElementById("grid-fit-progress-bar");
  var progressText = document.getElementById("grid-fit-progress-text");
  var bestWrap = document.getElementById("grid-fit-best-wrap");
  var bestBody = document.getElementById("grid-fit-best-body");
  var resultWrap = document.getElementById("grid-fit-result");
  var resultBody = document.getElementById("grid-fit-result-body");
  var submitButtons = Array.prototype.slice.call(form.querySelectorAll("button[type='submit'][data-fit-source]"));
  var activeSubmitButton = null;
  var cancelButton = document.getElementById("grid-fit-cancel");
  var patternInput = document.getElementById("grid-model-pattern");
  var patternMatch = document.getElementById("grid-pattern-match");
  var fitSourceInput = document.getElementById("grid-fit-source");
  var distanceFields = document.getElementById("grid-fit-distance-fields");
  var tlustyScaleNote = document.getElementById("grid-fit-tlusty-scale-note");
  var lambdaMinInput = document.getElementById("grid-fit-lambda-min");
  var lambdaMaxInput = document.getElementById("grid-fit-lambda-max");
  var usePlotRangeButton = document.getElementById("grid-fit-use-plot-range");
  var uploadPlot = document.getElementById("upload-spectrum-plot");
  var matchCountUrl = pageConfig.matchCountUrl;
  var initialActiveJob = pageConfig.active_grid_job;
  var spectrumMode = pageConfig.mode;
  var matchCountTimer = null;
  var activeJobId = "";
  var cancelInFlight = false;
  var overlaySignature = "";
  var overlayRequestId = 0;
  var LIGHT_SPEED_KM_PER_S = 299792.458;

  function asFiniteNumber(value, fallback) {
    var numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function formatRmse(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    return numeric.toExponential(4);
  }

  function formatParam(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    return Number(numeric.toFixed(6)).toString();
  }

  function formatNormalization(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "";
    }
    if (numeric >= 1e4 || numeric < 1e-3) {
      return numeric.toExponential(4);
    }
    return Number(numeric.toFixed(6)).toString();
  }

  function formatVelocityFromRedshift(redshiftValue) {
    var redshift = Number(redshiftValue);
    if (!Number.isFinite(redshift)) {
      return "";
    }
    var velocity = redshift * LIGHT_SPEED_KM_PER_S;
    if (!Number.isFinite(velocity)) {
      return "";
    }
    return Number(velocity.toFixed(6)).toString();
  }

  function fitSourceFromModel(model) {
    var source = String(model && model.fit_source || "").trim().toLowerCase();
    return source === "tlusty" ? "tlusty" : "cmfgen";
  }

  function updateFitSourceUi(source) {
    var normalized = source === "tlusty" ? "tlusty" : "cmfgen";
    var hideDistance = spectrumMode === "both" && normalized === "tlusty";
    if (distanceFields) {
      distanceFields.classList.toggle("d-none", hideDistance);
    }
    if (tlustyScaleNote) {
      tlustyScaleNote.classList.toggle("d-none", !hideDistance);
    }
  }

  function extractTlustyParams(model) {
    if (!model || typeof model !== "object") {
      return null;
    }
    var params = model.tlusty_params;
    if (!params || typeof params !== "object") {
      return null;
    }
    return params;
  }

  function formatTlustyParam(model, key) {
    var params = extractTlustyParams(model);
    if (!params) {
      return "";
    }
    return formatParam(params[key]);
  }

  function addTlustySummaryLines(container, model) {
    if (!container || fitSourceFromModel(model) !== "tlusty") {
      return;
    }
    var teff = formatTlustyParam(model, "teff_k");
    var logg = formatTlustyParam(model, "log_g");
    var metallicity = formatTlustyParam(model, "z_over_zsun");
    var vturb = formatTlustyParam(model, "vturb_km_s");
    if (teff) {
      addSummaryLine(container, "Teff (K)", teff);
    }
    if (logg) {
      addSummaryLine(container, "log g", logg);
    }
    if (metallicity) {
      addSummaryLine(container, "Z/Zsun", metallicity);
    }
    if (vturb) {
      addSummaryLine(container, "vturb (km/s)", vturb);
    }
  }

  function extractCmfgenParams(model) {
    if (!model || typeof model !== "object") {
      return null;
    }
    var params = model.cmfgen_params;
    if (!params || typeof params !== "object") {
      return null;
    }
    return params;
  }

  function formatCmfgenParam(model, key) {
    var params = extractCmfgenParams(model);
    if (!params) {
      return "";
    }
    return formatParam(params[key]);
  }

  function addCmfgenSummaryLines(container, model) {
    if (!container || fitSourceFromModel(model) !== "cmfgen") {
      return;
    }
    var teff = formatCmfgenParam(model, "teff_k");
    var logg = formatCmfgenParam(model, "log_g");
    var luminosity = formatCmfgenParam(model, "luminosity");
    if (teff) {
      addSummaryLine(container, "Teff (K)", teff);
    }
    if (logg) {
      addSummaryLine(container, "log g", logg);
    }
    if (luminosity) {
      addSummaryLine(container, "Luminosity", luminosity);
    }
  }

  function addAbsoluteScaleSummaryLines(container, model, params) {
    if (!container || spectrumMode !== "both") {
      return;
    }
    var ebvText = formatParam(params && params.ebv);
    if (ebvText) {
      addSummaryLine(container, "E(B-V)", ebvText);
    }
    if (fitSourceFromModel(model) === "tlusty") {
      var normalizationText = formatNormalization(params && params.normalization);
      if (normalizationText) {
        addSummaryLine(container, "normalization", normalizationText);
      }
      return;
    }
    var distanceText = formatParam(params && params.distance_kpc);
    if (distanceText) {
      addSummaryLine(container, "distance (kpc)", distanceText);
    }
  }

  function addFitWeightingSummaryLines(container, model) {
    if (!container || !model || typeof model !== "object") {
      return;
    }
    var weighting = String(model.chi2_weighting || "").trim();
    if (weighting) {
      addSummaryLine(container, "Fit weighting", weighting);
    }
    if (weighting !== "spectrum_flux_err_weighted") {
      return;
    }
    var provided = Number(model.spectrum_flux_err_provided_points);
    var fallback = Number(model.spectrum_flux_err_fallback_points);
    if (Number.isFinite(provided)) {
      addSummaryLine(container, "Spectrum error points", String(Math.round(provided)));
    }
    if (Number.isFinite(fallback) && fallback > 0) {
      addSummaryLine(container, "Spectrum error fallbacks", String(Math.round(fallback)));
    }
  }

  function formatConfidenceValue(value, isInteger) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    if (isInteger) {
      return String(Math.round(numeric));
    }
    return Number(numeric.toFixed(6)).toString();
  }

  function formatConfidenceInterval(param, levelLabel) {
    if (!param || typeof param !== "object") {
      return "";
    }
    var intervals = param.intervals && typeof param.intervals === "object"
      ? param.intervals
      : null;
    if (!intervals) {
      return "";
    }
    var interval = intervals[levelLabel];
    if (!interval || typeof interval !== "object") {
      return "";
    }
    var isInteger = !!param.is_integer;
    var minText = formatConfidenceValue(interval.min_value, isInteger);
    var maxText = formatConfidenceValue(interval.max_value, isInteger);
    if (!minText || !maxText) {
      return "";
    }
    var text = minText === maxText ? minText : (minText + " .. " + maxText);
    var unit = String(param.unit || "").trim();
    if (unit) {
      text += " " + unit;
    }
    return text;
  }

  function renderTlustyConfidenceSummary(container, result, best) {
    if (!container || fitSourceFromModel(best) !== "tlusty") {
      return;
    }
    var confidence = result && result.tlusty_confidence && typeof result.tlusty_confidence === "object"
      ? result.tlusty_confidence
      : null;
    if (!confidence) {
      return;
    }
    var parameters = confidence.parameters && typeof confidence.parameters === "object"
      ? confidence.parameters
      : null;
    if (!parameters) {
      return;
    }

    var title = document.createElement("div");
    title.className = "small text-muted mb-1 mt-2";
    var confidenceMethod = String(confidence.method || "").trim();
    if (confidenceMethod === "profile_delta_chi2_known_variance") {
      title.textContent = "Profile delta-chi2 confidence intervals (known photometric errors)";
    } else if (confidenceMethod === "profile_delta_chi2_profile_jitter") {
      title.textContent = "Profile delta-chi2 confidence intervals (profiled jitter scale)";
    } else {
      title.textContent = "Profile delta-chi2 confidence intervals (unknown variance)";
    }
    container.appendChild(title);

    var chi2Info = confidence.chi2 && typeof confidence.chi2 === "object"
      ? confidence.chi2
      : null;
    if (chi2Info) {
      var bestChi2 = formatParam(chi2Info.best_chi2);
      var bestDof = formatConfidenceValue(chi2Info.best_dof, true);
      var bestDofEff = formatConfidenceValue(chi2Info.best_dof_eff, true);
      var bestDofEffMethod = String(chi2Info.best_dof_eff_method || "").trim();
      var reducedChi2Eff = formatParam(chi2Info.reduced_chi2_eff);
      var chi2Weighting = String(chi2Info.chi2_weighting || "").trim();
      var photometryErrorWeighting = String(chi2Info.photometry_error_weighting || "").trim();
      var sigma2Hat = formatParam(chi2Info.sigma2_hat);
      var sigma2HatNominal = formatParam(chi2Info.sigma2_hat_nominal);
      if (bestChi2) {
        addSummaryLine(container, "Best RSS", bestChi2);
      }
      if (bestDof) {
        addSummaryLine(container, "DOF (nominal)", bestDof);
      }
      if (bestDofEff) {
        addSummaryLine(container, "DOF (effective)", bestDofEff);
      }
      if (bestDofEffMethod) {
        addSummaryLine(container, "DOF (effective method)", bestDofEffMethod);
      }
      if (reducedChi2Eff) {
        addSummaryLine(container, "Reduced chi2 (effective)", reducedChi2Eff);
      }
      if (chi2Weighting) {
        addSummaryLine(container, "Chi2 weighting", chi2Weighting);
      }
      if (photometryErrorWeighting) {
        addSummaryLine(container, "Photometry error model", photometryErrorWeighting);
      }
      if (sigma2Hat) {
        addSummaryLine(container, "sigma^2_hat (RSS/dof_eff)", sigma2Hat);
      }
      if (sigma2HatNominal) {
        addSummaryLine(container, "sigma^2_hat_nominal (RSS/dof)", sigma2HatNominal);
      }
    }

    var keys = ["teff_k", "log_g", "z_over_zsun", "vturb_km_s"];
    var labels = {
      teff_k: "Teff",
      log_g: "log g",
      z_over_zsun: "Z/Zsun",
      vturb_km_s: "vturb",
    };
    var levelOrder = ["68%", "90%", "95%"];
    for (var i = 0; i < keys.length; i += 1) {
      var key = keys[i];
      var param = parameters[key];
      if (!param || typeof param !== "object") {
        continue;
      }
      for (var j = 0; j < levelOrder.length; j += 1) {
        var levelLabel = levelOrder[j];
        var rangeText = formatConfidenceInterval(param, levelLabel);
        if (!rangeText) {
          continue;
        }
        addSummaryLine(container, levelLabel + " " + (labels[key] || key) + " CI", rangeText);
      }
    }
  }

  function getSelectedFitSource() {
    if (!fitSourceInput) {
      return "cmfgen";
    }
    var source = String(fitSourceInput.value || "").trim().toLowerCase();
    if (source !== "tlusty") {
      source = "cmfgen";
    }
    return source;
  }

  function getFitSourceLabel(source) {
    return source === "tlusty" ? "TLUSTY grid" : "CMFGEN grid";
  }

  function setSelectedFitSource(source) {
    var normalized = String(source || "").trim().toLowerCase();
    if (normalized !== "tlusty") {
      normalized = "cmfgen";
    }
    if (fitSourceInput) {
      fitSourceInput.value = normalized;
    }
    for (var i = 0; i < submitButtons.length; i += 1) {
      var button = submitButtons[i];
      var buttonSource = String(button.getAttribute("data-fit-source") || "").trim().toLowerCase();
      button.classList.toggle("active", buttonSource === normalized);
    }
    updateFitSourceUi(normalized);
  }

  function setSubmitButtonsDisabled(disabled) {
    for (var i = 0; i < submitButtons.length; i += 1) {
      submitButtons[i].disabled = !!disabled;
    }
  }

  function overlayController() {
    var controller = window.uploadSpectrumGridOverlay;
    if (!controller || typeof controller !== "object") {
      return null;
    }
    return controller;
  }

  function clearOverlayTrace() {
    overlaySignature = "";
    overlayRequestId += 1;
    var controller = overlayController();
    if (controller && typeof controller.clear === "function") {
      controller.clear();
    }
  }

  function modelSignature(model) {
    if (!model || typeof model !== "object") {
      return "";
    }
    var fitParams = model.fit_params && typeof model.fit_params === "object"
      ? model.fit_params
      : {};
    return JSON.stringify({
      model_path: String(model.model_path || model.model_name || ""),
      fin: String(model.fin || ""),
      redshift: asFiniteNumber(fitParams.redshift, 0),
      broadening_km_s: asFiniteNumber(fitParams.broadening_km_s, 0),
      ebv: asFiniteNumber(fitParams.ebv, 0),
      distance_kpc: asFiniteNumber(fitParams.distance_kpc, 1),
      normalization: asFiniteNumber(fitParams.normalization, 1)
    });
  }

  function fetchOverlayTrace(jobId, which, signature, isFinal) {
    if (!jobId || !signature) {
      return;
    }
    overlayRequestId += 1;
    var requestId = overlayRequestId;
    var overlayUrl = overlayUrlTemplate.replace("__JOB_ID__", encodeURIComponent(jobId)) + "?which=" + encodeURIComponent(which);
    fetch(overlayUrl, {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    })
      .then(parseJsonResponse)
      .then(function (result) {
        if (requestId !== overlayRequestId) {
          return;
        }
        if (!result.payload || typeof result.payload !== "object") {
          return;
        }
        if (!result.ok || result.payload.ok === false) {
          return;
        }
        if (signature !== overlaySignature) {
          return;
        }
        var trace = result.payload.trace;
        var controller = overlayController();
        if (!controller || typeof controller.set !== "function") {
          return;
        }
        controller.set(trace, !!isFinal);
      })
      .catch(function () {
      });
  }

  function ensureOverlayForModel(jobId, model, which, isFinal) {
    var signature = modelSignature(model);
    if (!signature) {
      clearOverlayTrace();
      return;
    }
    if (!isFinal && signature === overlaySignature) {
      return;
    }
    overlaySignature = signature;
    fetchOverlayTrace(jobId, which, signature, !!isFinal);
  }

  function setFeedback(message, isError) {
    if (!feedback) {
      return;
    }
    if (!message) {
      feedback.textContent = "";
      feedback.classList.add("d-none");
      feedback.classList.remove("alert-danger");
      feedback.classList.remove("alert-info");
      return;
    }
    feedback.textContent = message;
    feedback.classList.remove("d-none");
    feedback.classList.remove("alert-danger");
    feedback.classList.remove("alert-info");
    feedback.classList.add(isError ? "alert-danger" : "alert-info");
  }

  function formatRangeValue(value) {
    var numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "";
    }
    return Number(numeric.toFixed(6)).toString();
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

  function syncFitRangeMarkers() {
    var controller = overlayController();
    if (!controller || typeof controller.setFitRange !== "function") {
      return;
    }
    var minValue = parseFitRangeInputValue(lambdaMinInput);
    var maxValue = parseFitRangeInputValue(lambdaMaxInput);
    controller.setFitRange(minValue, maxValue);
  }

  function readCurrentPlotXRange() {
    if (!uploadPlot || !uploadPlot._fullLayout || !uploadPlot._fullLayout.xaxis) {
      return null;
    }
    var xaxis = uploadPlot._fullLayout.xaxis;
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

  function applyPlotRangeToFitInputs() {
    if (!lambdaMinInput || !lambdaMaxInput) {
      return;
    }
    var range = readCurrentPlotXRange();
    if (!range) {
      setFeedback("Could not read the current plot range. Zoom or pan the spectrum plot first.", true);
      return;
    }
    var minText = formatRangeValue(range[0]);
    var maxText = formatRangeValue(range[1]);
    lambdaMinInput.value = minText;
    lambdaMaxInput.value = maxText;
    syncFitRangeMarkers();
    setFeedback("Fit wavelength range set from plot view: " + minText + " .. " + maxText + " Å.", false);
  }

  function setProgress(percentage, text, isRunning, stateClass) {
    if (!progressWrap || !progressBar || !progressText) {
      return;
    }
    var bounded = Math.max(0, Math.min(100, asFiniteNumber(percentage, 0)));
    var state = String(stateClass || "").toLowerCase();
    progressWrap.classList.remove("d-none");
    progressBar.style.width = bounded.toFixed(1) + "%";
    progressBar.textContent = Math.round(bounded) + "%";
    progressBar.classList.toggle("progress-bar-animated", !!isRunning);
    progressBar.classList.toggle("bg-success", !isRunning && state === "success");
    progressBar.classList.toggle("bg-danger", !isRunning && state === "danger");
    progressText.textContent = text || "";
  }

  function setCancelControl(isRunning, isCancelRequested) {
    if (!cancelButton) {
      return;
    }
    if (!isRunning) {
      cancelButton.classList.add("d-none");
      cancelButton.disabled = false;
      cancelButton.textContent = "Stop Search";
      return;
    }
    cancelButton.classList.remove("d-none");
    if (isCancelRequested || cancelInFlight) {
      cancelButton.disabled = true;
      cancelButton.textContent = "Stopping...";
      return;
    }
    cancelButton.disabled = false;
    cancelButton.textContent = "Stop Search";
  }

  function resetResult() {
    if (resultWrap) {
      resultWrap.classList.add("d-none");
    }
    if (resultBody) {
      resultBody.innerHTML = "";
    }
  }

  function codeElement(text) {
    var code = document.createElement("code");
    code.textContent = text;
    return code;
  }

  function addSummaryLine(container, label, value) {
    var row = document.createElement("div");
    row.className = "mb-1";
    row.appendChild(codeElement(label));
    row.appendChild(document.createTextNode(": "));
    row.appendChild(codeElement(value));
    container.appendChild(row);
  }

  function resetBestSoFar() {
    if (bestWrap) {
      bestWrap.classList.add("d-none");
    }
    if (bestBody) {
      bestBody.innerHTML = "";
    }
  }

  function renderBestSoFar(best) {
    if (!bestWrap || !bestBody) {
      return;
    }
    if (!best || typeof best !== "object") {
      resetBestSoFar();
      return;
    }

    bestBody.innerHTML = "";
    bestWrap.classList.remove("d-none");
    addSummaryLine(bestBody, "Model", String(best.model_path || best.model_name || ""));
    addSummaryLine(bestBody, "RMSE", formatRmse(best.rmse));
    addSummaryLine(bestBody, "Fit points", String(best.points || ""));
    addFitWeightingSummaryLines(bestBody, best);
    addTlustySummaryLines(bestBody, best);
    addCmfgenSummaryLines(bestBody, best);

    var params = best.fit_params && typeof best.fit_params === "object" ? best.fit_params : {};
    addSummaryLine(bestBody, "z", formatParam(params.redshift));
    addSummaryLine(bestBody, "v(z) (km/s)", formatVelocityFromRedshift(params.redshift));
    addSummaryLine(bestBody, "sigma (km/s)", formatParam(params.broadening_km_s));
    addAbsoluteScaleSummaryLines(bestBody, best, params);

    var linksRow = document.createElement("div");
    linksRow.className = "d-flex flex-wrap gap-2 mt-2";
    if (best.spectrum_url) {
      var spectrumLink = document.createElement("a");
      spectrumLink.className = "btn btn-sm btn-outline-success";
      spectrumLink.href = String(best.spectrum_url);
      spectrumLink.textContent = "Preview Best-So-Far Spectrum";
      linksRow.appendChild(spectrumLink);
    }
    if (best.browse_url) {
      var browseLink = document.createElement("a");
      browseLink.className = "btn btn-sm btn-outline-secondary";
      browseLink.href = String(best.browse_url);
      browseLink.textContent = "Open Model Folder";
      linksRow.appendChild(browseLink);
    }
    if (linksRow.children.length) {
      bestBody.appendChild(linksRow);
    }
  }

  function renderResult(result) {
    if (!resultWrap || !resultBody) {
      return;
    }
    resultBody.innerHTML = "";
    resultWrap.classList.remove("d-none");

    var elapsed = asFiniteNumber(result && result.elapsed_seconds, 0);
    addSummaryLine(resultBody, "Elapsed (s)", elapsed.toFixed(2));

    var best = result && typeof result.best_model === "object" ? result.best_model : null;
    if (!best) {
      var empty = document.createElement("div");
      empty.className = "text-muted";
      empty.textContent = "No model produced a valid fit result with the current settings.";
      resultBody.appendChild(empty);
      return;
    }

    addSummaryLine(resultBody, "Best model", String(best.model_path || best.model_name || ""));
    addSummaryLine(resultBody, "Best RMSE", formatRmse(best.rmse));
    addSummaryLine(resultBody, "Fit points", String(best.points || ""));
    addFitWeightingSummaryLines(resultBody, best);
    addTlustySummaryLines(resultBody, best);
    addCmfgenSummaryLines(resultBody, best);

    var params = best.fit_params && typeof best.fit_params === "object" ? best.fit_params : {};
    addSummaryLine(resultBody, "z", formatParam(params.redshift));
    addSummaryLine(resultBody, "v(z) (km/s)", formatVelocityFromRedshift(params.redshift));
    addSummaryLine(resultBody, "sigma (km/s)", formatParam(params.broadening_km_s));
    addAbsoluteScaleSummaryLines(resultBody, best, params);
    renderTlustyConfidenceSummary(resultBody, result, best);

    var linksRow = document.createElement("div");
    linksRow.className = "d-flex flex-wrap gap-2 mb-2";
    if (best.spectrum_url) {
      var spectrumLink = document.createElement("a");
      spectrumLink.className = "btn btn-sm btn-outline-success";
      spectrumLink.href = String(best.spectrum_url);
      spectrumLink.textContent = "Open Best Model Spectrum";
      linksRow.appendChild(spectrumLink);
    }
    if (best.browse_url) {
      var browseLink = document.createElement("a");
      browseLink.className = "btn btn-sm btn-outline-secondary";
      browseLink.href = String(best.browse_url);
      browseLink.textContent = "Open Model Folder";
      linksRow.appendChild(browseLink);
    }
    if (linksRow.children.length) {
      resultBody.appendChild(linksRow);
    }

    var topModels = Array.isArray(result.top_models) ? result.top_models : [];
    if (!topModels.length) {
      return;
    }

    var title = document.createElement("div");
    title.className = "small text-muted mb-1";
    title.textContent = "Top candidate models by RMSE";
    resultBody.appendChild(title);

    var tableWrap = document.createElement("div");
    tableWrap.className = "table-responsive";
    var table = document.createElement("table");
    table.className = "table table-sm table-striped mb-0";
    var thead = document.createElement("thead");
    var includeTlustyColumns = fitSourceFromModel(best) === "tlusty";
    var includeCmfgenColumns = fitSourceFromModel(best) === "cmfgen";
    if (includeTlustyColumns) {
      thead.innerHTML = "<tr><th>Model</th><th>RMSE</th><th>Points</th><th>Spectrum</th><th>Teff (K)</th><th>log g</th><th>Z/Zsun</th><th>vturb (km/s)</th></tr>";
    } else if (includeCmfgenColumns) {
      thead.innerHTML = "<tr><th>Model</th><th>RMSE</th><th>Points</th><th>Spectrum</th><th>Teff (K)</th><th>log g</th><th>Luminosity</th></tr>";
    } else {
      thead.innerHTML = "<tr><th>Model</th><th>RMSE</th><th>Points</th><th>Spectrum</th></tr>";
    }
    table.appendChild(thead);

    var tbody = document.createElement("tbody");
    for (var i = 0; i < topModels.length; i += 1) {
      var item = topModels[i] || {};
      var tr = document.createElement("tr");

      var tdModel = document.createElement("td");
      tdModel.appendChild(codeElement(String(item.model_path || item.model_name || "")));
      tr.appendChild(tdModel);

      var tdRmse = document.createElement("td");
      tdRmse.appendChild(codeElement(formatRmse(item.rmse)));
      tr.appendChild(tdRmse);

      var tdPoints = document.createElement("td");
      tdPoints.appendChild(codeElement(String(item.points || "")));
      tr.appendChild(tdPoints);

      var tdFin = document.createElement("td");
      tdFin.appendChild(codeElement(String(item.fin || "")));
      tr.appendChild(tdFin);

      if (includeTlustyColumns) {
        var tdTeff = document.createElement("td");
        tdTeff.appendChild(codeElement(formatTlustyParam(item, "teff_k")));
        tr.appendChild(tdTeff);

        var tdLogg = document.createElement("td");
        tdLogg.appendChild(codeElement(formatTlustyParam(item, "log_g")));
        tr.appendChild(tdLogg);

        var tdZ = document.createElement("td");
        tdZ.appendChild(codeElement(formatTlustyParam(item, "z_over_zsun")));
        tr.appendChild(tdZ);

        var tdVturb = document.createElement("td");
        tdVturb.appendChild(codeElement(formatTlustyParam(item, "vturb_km_s")));
        tr.appendChild(tdVturb);
      } else if (includeCmfgenColumns) {
        var tdTeffCmfgen = document.createElement("td");
        tdTeffCmfgen.appendChild(codeElement(formatCmfgenParam(item, "teff_k")));
        tr.appendChild(tdTeffCmfgen);

        var tdLoggCmfgen = document.createElement("td");
        tdLoggCmfgen.appendChild(codeElement(formatCmfgenParam(item, "log_g")));
        tr.appendChild(tdLoggCmfgen);

        var tdLuminosity = document.createElement("td");
        tdLuminosity.appendChild(codeElement(formatCmfgenParam(item, "luminosity")));
        tr.appendChild(tdLuminosity);
      }

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    tableWrap.appendChild(table);
    resultBody.appendChild(tableWrap);
  }

  function parseJsonResponse(response) {
    return response.text().then(function (rawText) {
      var payload = null;
      if (rawText) {
        try {
          payload = JSON.parse(rawText);
        } catch (_error) {
          payload = null;
        }
      }
      return {
        ok: response.ok,
        payload: payload
      };
    });
  }

  function setPatternMatch(message, isError) {
    if (!patternMatch) {
      return;
    }
    patternMatch.textContent = message;
    patternMatch.classList.toggle("text-danger", !!isError);
    patternMatch.classList.toggle("text-muted", !isError);
  }

  function fetchPatternMatchCount() {
    if (!patternInput) {
      return;
    }
    var patternValue = String(patternInput.value || "").trim();
    var fitSource = getSelectedFitSource();
    var query = new URLSearchParams(new FormData(form));
    query.set("model_name_pattern", patternValue);
    query.set("fit_source", fitSource);
    query.set("mode", spectrumMode);
    query.delete("async");
    var url = matchCountUrl + "?" + query.toString();
    fetch(url, {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    })
      .then(parseJsonResponse)
      .then(function (result) {
        if (!result.payload || typeof result.payload !== "object") {
          throw new Error("Could not determine pattern matches.");
        }
        if (!result.ok || result.payload.ok === false) {
          throw new Error(String(result.payload.error || "Could not determine pattern matches."));
        }
        var count = asFiniteNumber(result.payload.total_models, 0);
        var scope = String(result.payload.fit_source_label || getFitSourceLabel(fitSource));
        setPatternMatch("Matching " + scope + ": " + String(count), false);
      })
      .catch(function (error) {
        setPatternMatch(error && error.message ? error.message : "Could not determine pattern matches.", true);
      });
  }

  function schedulePatternMatchCount() {
    if (matchCountTimer !== null) {
      window.clearTimeout(matchCountTimer);
    }
    matchCountTimer = window.setTimeout(function () {
      matchCountTimer = null;
      fetchPatternMatchCount();
    }, 220);
  }

  function requestCancelActiveJob() {
    if (!activeJobId || cancelInFlight) {
      return;
    }
    cancelInFlight = true;
    setCancelControl(true, true);
    var cancelUrl = cancelUrlTemplate.replace("__JOB_ID__", encodeURIComponent(activeJobId));
    fetch(cancelUrl, {
      method: "POST",
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    })
      .then(parseJsonResponse)
      .then(function (result) {
        if (!result.payload || typeof result.payload !== "object") {
          throw new Error("Could not request cancellation.");
        }
        if (!result.ok || result.payload.ok === false) {
          throw new Error(String(result.payload.error || "Could not request cancellation."));
        }
        setFeedback("Stopping grid fit...", false);
      })
      .catch(function (error) {
        cancelInFlight = false;
        setCancelControl(true, false);
        setFeedback(error && error.message ? error.message : "Could not request cancellation.", true);
      });
  }

  function pollJob(jobId) {
    activeJobId = jobId;
    var statusUrl = statusUrlTemplate.replace("__JOB_ID__", encodeURIComponent(jobId));
    fetch(statusUrl, {
      method: "GET",
      headers: {
        "Accept": "application/json"
      }
    })
      .then(parseJsonResponse)
      .then(function (result) {
        if (!result.payload || typeof result.payload !== "object") {
          throw new Error("Grid fit failed: invalid server response.");
        }
        var payload = result.payload;
        if (!result.ok || payload.ok === false) {
          throw new Error(String(payload.error || "Grid fit failed."));
        }

        var processed = asFiniteNumber(payload.processed, 0);
        var total = asFiniteNumber(payload.total, 0);
        var successful = asFiniteNumber(payload.successful, 0);
        var failed = asFiniteNumber(payload.failed, 0);
        var status = String(payload.status || "");
        var fitSource = String(payload.fit_source || "").trim().toLowerCase();
        if (fitSource !== "tlusty") {
          fitSource = "cmfgen";
        }
        var fitSourceLabel = String(payload.fit_source_label || getFitSourceLabel(fitSource));
        setSelectedFitSource(fitSource);
        var percentage = asFiniteNumber(payload.progress_percent, total > 0 ? (100 * processed / total) : 0);
        var cancelRequested = !!payload.cancel_requested;
        var current = String(payload.current_model || "");
        var bestSoFar = payload.best_so_far && typeof payload.best_so_far === "object"
          ? payload.best_so_far
          : null;
        var progressLine = fitSourceLabel + ": processed " + processed + "/" + total + " models; valid fits: " + successful + "; failed/skipped: " + failed + ".";
        if (current) {
          progressLine += " Current: " + current;
        }
        setProgress(
          percentage,
          progressLine,
          status === "running",
          status === "running"
            ? ""
            : (status === "canceled" || status === "failed" ? "danger" : "success")
        );

        if (status === "running") {
          setSubmitButtonsDisabled(true);
          renderBestSoFar(bestSoFar);
          if (bestSoFar) {
            ensureOverlayForModel(jobId, bestSoFar, "best_so_far", false);
          } else {
            clearOverlayTrace();
          }
          setCancelControl(true, cancelRequested);
          window.setTimeout(function () {
            pollJob(jobId);
          }, 900);
          return;
        }

        activeJobId = "";
        window.dispatchEvent(new Event("cmfgen:background-tasks-changed"));
        cancelInFlight = false;
        resetBestSoFar();
        setCancelControl(false, false);
        setSubmitButtonsDisabled(false);

        if (status === "failed") {
          throw new Error(String(payload.error || "Grid fit failed."));
        }

        var completedResult = payload.result && typeof payload.result === "object" ? payload.result : {};
        renderResult(completedResult);
        var completedBest = completedResult.best_model && typeof completedResult.best_model === "object"
          ? completedResult.best_model
          : null;
        if (completedBest) {
          ensureOverlayForModel(jobId, completedBest, "final", status === "completed");
        } else {
          clearOverlayTrace();
        }
        if (status === "canceled") {
          var canceledBest = completedResult.best_model && typeof completedResult.best_model === "object"
            ? completedResult.best_model
            : null;
          if (canceledBest && canceledBest.model_path) {
            var canceledParams = canceledBest.fit_params && typeof canceledBest.fit_params === "object"
              ? canceledBest.fit_params
              : {};
            var canceledZ = formatParam(canceledParams.redshift);
            var canceledV = formatVelocityFromRedshift(canceledParams.redshift);
            var canceledFitText = "";
            if (canceledZ || canceledV) {
              canceledFitText = " z=" + (canceledZ || "?");
              if (canceledV) {
                canceledFitText += ", v=" + canceledV + " km/s";
              }
            }
            setFeedback(
              fitSourceLabel + " fit canceled. Best-so-far model: " + String(canceledBest.model_path) + " (RMSE=" + formatRmse(canceledBest.rmse) + ")." + canceledFitText,
              false
            );
          } else {
            setFeedback(String(payload.message || (fitSourceLabel + " fit canceled.")), false);
          }
        } else {
          var best = completedResult.best_model && typeof completedResult.best_model === "object"
            ? completedResult.best_model
            : null;
          if (best && best.model_path) {
            var bestParams = best.fit_params && typeof best.fit_params === "object"
              ? best.fit_params
              : {};
            var bestZ = formatParam(bestParams.redshift);
            var bestV = formatVelocityFromRedshift(bestParams.redshift);
            var bestFitText = "";
            if (bestZ || bestV) {
              bestFitText = " z=" + (bestZ || "?");
              if (bestV) {
                bestFitText += ", v=" + bestV + " km/s";
              }
            }
            setFeedback(
              fitSourceLabel + " fit completed. Best model: " + String(best.model_path) + " (RMSE=" + formatRmse(best.rmse) + ")." + bestFitText,
              false
            );
          } else {
            setFeedback(fitSourceLabel + " fit completed. No valid fit was found.", false);
          }
        }
      })
      .catch(function (error) {
        activeJobId = "";
        cancelInFlight = false;
        setCancelControl(false, false);
        setSubmitButtonsDisabled(false);
        clearOverlayTrace();
        setProgress(0, "", false, "danger");
        setFeedback(error && error.message ? error.message : "Grid fit failed.", true);
      });
  }

  form.addEventListener("submit", function (event) {
    if (!window.fetch || !window.FormData) {
      return;
    }
    event.preventDefault();
    var submitter = event.submitter || activeSubmitButton;
    if (submitter && submitter.getAttribute) {
      setSelectedFitSource(submitter.getAttribute("data-fit-source"));
    }
    var selectedFitSource = getSelectedFitSource();
    var fitSourceLabel = getFitSourceLabel(selectedFitSource);
    resetResult();
    resetBestSoFar();
    clearOverlayTrace();
    setFeedback("", false);
    setProgress(0, "Starting " + fitSourceLabel + " fit...", true, "");
    activeJobId = "";
    cancelInFlight = false;
    setCancelControl(false, false);
    setSubmitButtonsDisabled(true);

    var formData = new FormData(form);
    formData.set("async", "1");
    formData.set("fit_source", selectedFitSource);

    fetch(form.action, {
      method: "POST",
      body: formData,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    })
      .then(parseJsonResponse)
      .then(function (result) {
        if (!result.payload || typeof result.payload !== "object") {
          throw new Error("Grid fit failed: invalid server response.");
        }
        if (!result.ok || result.payload.ok === false) {
          throw new Error(String(result.payload.error || "Grid fit failed."));
        }
        var jobId = String(result.payload.job_id || "");
        if (!jobId) {
          throw new Error("Grid fit failed: missing job id.");
        }
        window.dispatchEvent(new Event("cmfgen:background-tasks-changed"));
        var sourceLabel = String(result.payload.fit_source_label || fitSourceLabel);
        if (result.payload.existing_job) {
          setFeedback("A " + sourceLabel + " fit is already running for this upload. Re-attaching to active search.", false);
        } else {
          setFeedback(sourceLabel + " fit started across " + String(result.payload.total_models || 0) + " candidates.", false);
        }
        setCancelControl(true, false);
        pollJob(jobId);
      })
      .catch(function (error) {
        activeJobId = "";
        cancelInFlight = false;
        setCancelControl(false, false);
        setSubmitButtonsDisabled(false);
        resetBestSoFar();
        clearOverlayTrace();
        setProgress(0, "", false, "danger");
        setFeedback(error && error.message ? error.message : "Grid fit failed.", true);
      });
  });

  for (var submitIndex = 0; submitIndex < submitButtons.length; submitIndex += 1) {
    (function (button) {
      button.addEventListener("click", function () {
        activeSubmitButton = button;
        setSelectedFitSource(button.getAttribute("data-fit-source"));
        schedulePatternMatchCount();
      });
    })(submitButtons[submitIndex]);
  }
  setSelectedFitSource(getSelectedFitSource());

  if (patternInput) {
    patternInput.addEventListener("input", schedulePatternMatchCount);
    patternInput.addEventListener("change", schedulePatternMatchCount);
  }
  if (lambdaMinInput) {
    lambdaMinInput.addEventListener("input", syncFitRangeMarkers);
    lambdaMinInput.addEventListener("change", syncFitRangeMarkers);
  }
  if (lambdaMaxInput) {
    lambdaMaxInput.addEventListener("input", syncFitRangeMarkers);
    lambdaMaxInput.addEventListener("change", syncFitRangeMarkers);
  }
  var fitControlInputs = Array.prototype.slice.call(form.querySelectorAll(".grid-fit-range-input"));
  for (var fitControlIndex = 0; fitControlIndex < fitControlInputs.length; fitControlIndex += 1) {
    fitControlInputs[fitControlIndex].addEventListener("change", schedulePatternMatchCount);
  }
  if (usePlotRangeButton) {
    usePlotRangeButton.addEventListener("click", applyPlotRangeToFitInputs);
    if (!uploadPlot) {
      usePlotRangeButton.disabled = true;
      usePlotRangeButton.title = "Spectrum plot is not available.";
    }
  }
  if (cancelButton) {
    cancelButton.addEventListener("click", requestCancelActiveJob);
  }
  setCancelControl(false, false);
  fetchPatternMatchCount();
  syncFitRangeMarkers();

  if (initialActiveJob && typeof initialActiveJob === "object") {
    var initialJobId = String(initialActiveJob.job_id || "");
    if (initialJobId) {
      var initialSource = String(initialActiveJob.fit_source || "").trim().toLowerCase();
      if (initialSource !== "tlusty") {
        initialSource = "cmfgen";
      }
      var initialSourceLabel = String(initialActiveJob.fit_source_label || getFitSourceLabel(initialSource));
      setSelectedFitSource(initialSource);
      var initialProcessed = asFiniteNumber(initialActiveJob.processed, 0);
      var initialTotal = asFiniteNumber(initialActiveJob.total, 0);
      var initialSuccessful = asFiniteNumber(initialActiveJob.successful, 0);
      var initialFailed = asFiniteNumber(initialActiveJob.failed, 0);
      var initialProgress = asFiniteNumber(initialActiveJob.progress_percent, initialTotal > 0 ? (100 * initialProcessed / initialTotal) : 0);
      var initialCurrent = String(initialActiveJob.current_model || "");
      var initialBestSoFar = initialActiveJob.best_so_far && typeof initialActiveJob.best_so_far === "object"
        ? initialActiveJob.best_so_far
        : null;
      var initialCancelRequested = !!initialActiveJob.cancel_requested;
      var initialText = "Processed " + initialProcessed + "/" + initialTotal + " models; valid fits: " + initialSuccessful + "; failed/skipped: " + initialFailed + ".";
      if (initialCurrent) {
        initialText += " Current: " + initialCurrent;
      }
      if (initialCancelRequested) {
        setFeedback("An active " + initialSourceLabel + " fit is stopping; waiting for cancellation to finalize.", false);
      } else {
        setFeedback("Resuming active " + initialSourceLabel + " fit for this upload.", false);
      }
      setProgress(initialProgress, initialText, true, "");
      renderBestSoFar(initialBestSoFar);
      setSubmitButtonsDisabled(true);
      if (initialBestSoFar) {
        ensureOverlayForModel(initialJobId, initialBestSoFar, "best_so_far", false);
      } else {
        clearOverlayTrace();
      }
      setCancelControl(true, initialCancelRequested);
      pollJob(initialJobId);
    }
  }
})();
