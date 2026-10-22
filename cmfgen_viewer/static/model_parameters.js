(function () {
  "use strict";
  document.querySelectorAll("[data-quick-parameter-form]").forEach(function (form) {
    const field = (key) => form.elements.namedItem("quick_value:" + key);
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
    if (!checkbox || checkbox.disabled) return;
    const luminosity = field("LSTAR");
    const radius = field("RSTAR");
    const mass = field("MASS");
    const gravity = field("LOGG");
    if (!luminosity || !radius || !mass || !gravity) return;
    const baselineLuminosity = Number(checkbox.dataset.baselineLuminosity);
    const baselineRadius = Number(checkbox.dataset.baselineRadius);
    const baselineMass = Number(checkbox.dataset.baselineMass);
    let manualValues = null;
    function updateDerivedValues() {
      if (!checkbox.checked) return;
      const value = Number(luminosity.value.trim().replace(/[dD]/g, "e"));
      const factor = value / baselineLuminosity;
      const newRadius = baselineRadius * Math.sqrt(factor);
      const newMass = baselineMass * factor;
      const valid = Number.isFinite(factor) && factor > 0 &&
        Number.isFinite(newRadius) && newRadius > 0 && Number.isFinite(newMass) && newMass > 0;
      luminosity.setCustomValidity(valid ? "" : "Enter a luminosity that gives a finite positive radius and mass.");
      if (valid) {
        radius.value = Number(newRadius.toPrecision(12)).toString();
        mass.value = Number(newMass.toPrecision(12)).toString();
      }
    }
    function toggleScaling() {
      if (checkbox.checked) {
        manualValues = [radius.value, mass.value, gravity.value];
        gravity.value = checkbox.dataset.baselineLogg;
      } else {
        if (manualValues) [radius.value, mass.value, gravity.value] = manualValues;
        luminosity.setCustomValidity("");
      }
      [radius, mass, gravity].forEach((input) => { input.readOnly = checkbox.checked; });
      updateDerivedValues();
    }
    checkbox.addEventListener("change", toggleScaling);
    luminosity.addEventListener("input", updateDerivedValues);
    toggleScaling();
  });
})();
