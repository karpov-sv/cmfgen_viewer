(function () {
  "use strict";

  var job = document.getElementById("cache-maintenance-job");
  if (!job || job.getAttribute("data-status") !== "running" || !window.fetch) {
    return;
  }
  var statusUrl = String(job.getAttribute("data-status-url") || "");
  var returnUrl = String(job.getAttribute("data-return-url") || "");
  var progress = document.getElementById("cache-maintenance-progress");
  var detail = document.getElementById("cache-maintenance-detail");

  function poll() {
    window.fetch(statusUrl, {cache: "no-store", headers: {"Accept": "application/json"}})
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Could not read cache maintenance status.");
        }
        return response.json();
      })
      .then(function (payload) {
        var state = payload && payload.job ? payload.job : null;
        if (!state) {
          throw new Error("Invalid cache maintenance response.");
        }
        var percentage = Math.min(100, Math.max(0, Number(state.progress_percent) || 0));
        if (progress) {
          progress.style.width = percentage.toFixed(1) + "%";
          progress.textContent = Math.round(percentage) + "%";
        }
        if (detail) {
          var line = String(state.phase || "Working") + ": " + String(state.processed || 0) + "/" + String(state.total || 0);
          if (state.current_entry) {
            line += " — " + String(state.current_entry);
          }
          detail.textContent = line;
        }
        if (String(state.status || "") !== "running") {
          window.location.replace(returnUrl);
          return;
        }
        window.setTimeout(poll, 1000);
      })
      .catch(function (error) {
        if (detail) {
          detail.textContent = error && error.message ? error.message : "Could not read cache maintenance status.";
          detail.classList.add("text-danger");
        }
        window.setTimeout(poll, 5000);
      });
  }

  window.setTimeout(poll, 500);
})();
