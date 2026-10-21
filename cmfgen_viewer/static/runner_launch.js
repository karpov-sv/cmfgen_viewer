(() => {
  "use strict";
  const automatic = document.getElementById("run-automatic");
  if (!automatic) return;
  const stages = document.getElementById("run-stages");
  const custom = document.getElementById("custom-stages");
  const limits = document.getElementById("run-auto-limits");
  const iterations = document.getElementById("run-iterations");
  const update = () => {
    const selection = (custom.value.trim() || stages.value).split(",").map(stage => stage.trim()).join(",");
    automatic.disabled = !["main", "main,flux"].includes(selection);
    if (automatic.disabled) automatic.checked = false;
    limits.hidden = !automatic.checked;
    limits.querySelectorAll("input").forEach(input => { input.disabled = !automatic.checked; });
    iterations.min = automatic.checked ? "2" : "1";
    document.querySelector('label[for="run-iterations"]').textContent = automatic.checked ? "Iterations per batch" : "Main iterations";
    iterations.placeholder = automatic.checked ? "5 per batch" : "Use IN_ITS";
  };
  automatic.addEventListener("change", update);
  stages.addEventListener("change", update);
  custom.addEventListener("input", update);
  update();
})();
