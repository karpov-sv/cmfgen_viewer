(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof bootstrap === "undefined" || !bootstrap.Tooltip) return;
    document.querySelectorAll("[data-parameter-help]").forEach(function (button) {
      const tooltip = new bootstrap.Tooltip(button, {trigger: "hover focus", container: "body"});
      button.addEventListener("keydown", function (event) {
        if (event.key === "Escape") tooltip.hide();
      });
    });
  });
  document.querySelectorAll("[data-structure-form]").forEach(function (form) {
    const operation = form.elements.namedItem("operation");
    if (!operation) return;
    function updateOperation() {
      form.querySelectorAll("[data-structure-for]").forEach(function (panel) {
        const visible = panel.dataset.structureFor.split(" ").includes(operation.value);
        panel.hidden = !visible;
        panel.querySelectorAll("input, select, textarea").forEach(function (control) {
          control.disabled = !visible;
        });
      });
    }
    operation.addEventListener("change", updateOperation);
    updateOperation();
  });
  document.querySelectorAll("[data-quick-parameter-form]").forEach(function (form) {
    const field = (key) => form.elements.namedItem("quick_value:" + key);
    const solverNotices = form.querySelector("[data-solver-notices]");
    if (solverNotices && solverNotices.querySelectorAll) {
      solverNotices.querySelectorAll("[data-solver-notice]").forEach(function (notice) {
        const conditions = JSON.parse(notice.dataset.solverRule);
        function updateNotice() {
          const active = conditions.every(function (condition) {
            const control = field(condition.key);
            if (!control || !control.value.trim()) return false;
            const value = control.value.trim().toUpperCase();
            if (condition.op === "eq") return value === condition.value;
            const number = Number(value.replace(/D/g, "e"));
            if (!Number.isFinite(number)) return false;
            if (condition.op === "gt") return number > condition.value;
            return condition.op === "lt" && number < condition.value;
          });
          notice.hidden = !active;
          const control = field(notice.dataset.solverKey);
          if (control) control.classList.toggle("border-" + notice.dataset.solverTone, active);
          form.querySelectorAll("[data-solver-badge]").forEach(function (badge) {
            if (badge.dataset.solverBadge === notice.dataset.solverNotice) badge.hidden = !active;
          });
        }
        conditions.forEach(function (condition) {
          const control = field(condition.key);
          if (!control) return;
          control.addEventListener("input", updateNotice);
          control.addEventListener("change", updateNotice);
        });
        updateNotice();
      });
    }
    const computeBA = field("COMP_BA"), reuseBA = field("N_FIX_BA");
    const baNotice = form.querySelector("[data-ba-reuse-notice]");
    if (computeBA && reuseBA && baNotice) {
      function updateBAReuse() {
        const value = reuseBA.value.trim();
        const disabled = computeBA.value.trim().toUpperCase() === "T" && value !== "" &&
          Number(value.replace(/[dD]/g, "e")) === 0;
        baNotice.hidden = !disabled;
        ["N_FIX_BA", "FIX_BA"].forEach(function (key) {
          const control = field(key);
          if (control) control.classList.toggle("border-warning", disabled);
        });
        form.querySelectorAll("[data-ba-reuse-badge]").forEach(function (badge) {badge.hidden = !disabled;});
      }
      [computeBA, reuseBA].forEach(function (control) {
        control.addEventListener("input", updateBAReuse);
        control.addEventListener("change", updateBAReuse);
      });
      updateBAReuse();
    }
    const method = field("DC_METH");
    if (method) {
      method.addEventListener("change", function () {
        if (method.value.toUpperCase() !== "POP") return;
        ["LIN_INT", "POP_SCALE"].forEach(function (key) {
          const control = field(key);
          if (control) control.value = "T";
        });
      });
    }
    const checkbox = form.querySelector("[data-luminosity-scaling]");
    const temperatureCheckbox = form.querySelector("[data-temperature-scaling]");
    if (!checkbox || checkbox.disabled || !temperatureCheckbox) return;
    const controls = Object.fromEntries(["LSTAR", "TEFF", "RSTAR", "MASS", "LOGG"].map(key => [key, field(key)]));
    if (Object.values(controls).some(input => !input)) return;
    const baseline = {
      LSTAR: Number(checkbox.dataset.baselineLuminosity),
      TEFF: Number(checkbox.dataset.baselineTemperature),
      RSTAR: Number(checkbox.dataset.baselineRadius),
      MASS: Number(checkbox.dataset.baselineMass),
      LOGG: Number(checkbox.dataset.baselineLogg)
    };
    let manualValues = null;
    function updateDerivedValues() {
      if (!checkbox.checked && !temperatureCheckbox.checked) return;
      const driver = checkbox.checked ? "LSTAR" : "TEFF";
      if (manualValues) manualValues[driver] = controls[driver].value;
      const value = Number(controls[driver].value.trim().replace(/[dD]/g, "e"));
      const factor = checkbox.checked ? value / baseline.LSTAR : Math.pow(baseline.TEFF / value, 4);
      const radius = baseline.RSTAR * Math.sqrt(factor);
      const mass = baseline.MASS * factor;
      const valid = value > 0 && Number.isFinite(value) && Number.isFinite(factor) && factor > 0 &&
        Number.isFinite(radius) && radius > 0 && Number.isFinite(mass) && mass > 0;
      controls[driver].setCustomValidity(valid ? "" : "Enter a value that gives a finite positive radius and mass.");
      if (valid) {
        controls.RSTAR.value = Number(radius.toPrecision(12)).toString();
        controls.MASS.value = Number(mass.toPrecision(12)).toString();
      }
    }
    function toggleScaling(changed) {
      if (changed && changed.checked) {
        if (!manualValues) manualValues = Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, input.value]));
        (changed === checkbox ? temperatureCheckbox : checkbox).checked = false;
      }
      const active = checkbox.checked || temperatureCheckbox.checked;
      if (active && !manualValues) manualValues = Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, input.value]));
      Object.values(controls).forEach(input => { input.readOnly = false; input.setCustomValidity(""); });
      if (active) {
        const fixed = checkbox.checked ? "TEFF" : "LSTAR";
        const driver = checkbox.checked ? "LSTAR" : "TEFF";
        controls[driver].value = manualValues[driver];
        controls[fixed].value = baseline[fixed];
        controls.LOGG.value = baseline.LOGG;
        [fixed, "LOGG", "RSTAR", "MASS"].forEach(key => { controls[key].readOnly = true; });
      } else if (manualValues) {
        Object.entries(manualValues).forEach(([key, value]) => { controls[key].value = value; });
        manualValues = null;
      }
      updateDerivedValues();
    }
    checkbox.addEventListener("change", () => toggleScaling(checkbox));
    temperatureCheckbox.addEventListener("change", () => toggleScaling(temperatureCheckbox));
    [controls.LSTAR, controls.TEFF].forEach(input => input.addEventListener("input", updateDerivedValues));
    toggleScaling();
  });
})();
