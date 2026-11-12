/* Shared plot and transformation controller. Page adapters own fitting and overlays. */
(function () {
  "use strict";
  function create(pageConfig, options) {
    var target = document.getElementById(pageConfig.plot_id);
    var mediumInput = document.getElementById(pageConfig.plot_id + "-lines-medium");
    var observed = options.baseData.find(function (trace, i) { return options.transformTargets[i] === "observed"; });
    if (mediumInput && observed) {
      mediumInput.value = observed.meta && observed.meta.wavelength_medium || "air";
      mediumInput.disabled = true;
      mediumInput.title = "Fixed by the upload's wavelength property. Edit it on the upload page; the observed samples stay unchanged.";
    }
    pageConfig.plot_data_layout.xaxis = Object.assign({}, pageConfig.plot_data_layout.xaxis,
      { title: { text: observed ? "Uploaded wavelength (Å, " + (observed.meta && observed.meta.wavelength_medium || "air") + ")" : "Wavelength (Å)" } });
    var plot = CmfgenSpectrumControls.createPlot(target, pageConfig.plot_data_data,
      pageConfig.plot_data_layout, pageConfig.plot_data_config, {
        xScale: document.getElementById(pageConfig.x_scale_id),
        yScale: document.getElementById(pageConfig.y_scale_id)
      });
    var sampling = plot.sampling;
    var baseData = options.baseData;
    var transformTargets = options.transformTargets;
    var spectrumMode = pageConfig.mode;
    var LIGHT_SPEED_KM_PER_S = 299792.458;
    var redshiftInput = document.getElementById(pageConfig.redshift_id);
    var velocityInput = document.getElementById(pageConfig.velocity_id);
    var broadeningInput = document.getElementById(pageConfig.broadening_id);
    var ebvInput = document.getElementById(pageConfig.ebv_id);
    var distanceInput = document.getElementById(pageConfig.distance_id);
    var resetTransform = document.getElementById(pageConfig.reset_transform_id);
    var transformHint = document.getElementById(pageConfig.transform_hint_id);
    var transformSettings = document.getElementById(pageConfig.plot_id + "-transforms");
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
      transformHint.hidden = !isError;
      if (!isError) {
        var helpButton = document.getElementById(pageConfig.transform_hint_id + "-help-button");
        var helpDescription = document.getElementById(pageConfig.transform_hint_id + "-help");
        if (helpButton) {
          var helpHtml = message.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/vacuum rest × \(1 \+ source z\)|F\/Fc|sigma_v=[\d.]+ km\/s/g, "<code>$&</code>");
          helpButton.setAttribute("data-bs-content", helpHtml);
        }
        if (helpDescription) helpDescription.textContent = message;
      }
      transformHint.classList.toggle("text-danger", !!isError);
      transformHint.classList.toggle("text-muted", !isError);
      if (isError && transformSettings) {
        transformSettings.open = true;
      }
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

    function applyPhysicalTransforms() {
      var redshift = redshiftInput ? Number(redshiftInput.value) : 0;
      if (!Number.isFinite(redshift) || (1 + redshift) <= 0) {
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
      var medium = mediumInput ? mediumInput.value : "air";
      var frameText = "Uploaded samples and fit intervals stay fixed. Model and stellar-marker wavelengths use vacuum rest × (1 + source z), then convert to " + medium + ". Telluric bands stay in the upload frame. ";
      if (spectrumMode === "both") {
        setTransformHint(frameText + "Distance, reddening and broadening apply to models only; uploaded flux and uncertainties are unchanged." + broadeningText, false);
      } else {
        setTransformHint(frameText + "Distance and reddening cancel in F/Fc; broadening applies to models only." + broadeningText, false);
      }

      var transformedX = [];
      var transformedY = [];

      for (var traceIndex = 0; traceIndex < baseData.length; traceIndex += 1) {
        var sourceX = baseData[traceIndex].x;
        var sourceY = baseData[traceIndex].y;
        var kind = transformTargets[traceIndex];
        var shouldBroaden = options.shouldBroaden(traceIndex, baseData[traceIndex]);
        var adjustFlux = kind === "model";
        var transformed = adjustFlux ? CmfgenSpectrumTransforms.transformSeries(sourceX, sourceY, {
          mode: spectrumMode, redshift: redshift, wavelength_medium: medium,
          normalization: baseData[traceIndex].meta && baseData[traceIndex].meta.fit_normalization || 1,
          distance_kpc: distanceKpc, ebv: ebv, broadening_km_s: shouldBroaden ? sigmaVelocity : 0
        }) : [sourceX, sourceY];
        transformedX.push(transformed[0].slice());
        transformedY.push(transformed[1].slice());
      }

      target.__spectrumDisplayRedshift = redshift;
      target.__spectrumWavelengthMedium = medium;
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

    var ready = plot.ready.then(function () {
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
      if (mediumInput) mediumInput.addEventListener("change", scheduleTransforms);
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
      scheduleTransforms();
    });
    return {
      sampling: sampling,
      ready: ready,
      scheduleTransforms: scheduleTransforms,
      updateVelocityFromRedshift: updateVelocityFromRedshift
    };
  }
  window.CmfgenSpectrumViewer = { create: create };
})();
