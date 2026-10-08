/* Poll counts only. The stable GET page retains partial and final results. */
(function () {
  "use strict";
  var panel = document.getElementById("summary-job");
  if (!panel || panel.dataset.status !== "running") { return; }
  var connection = document.getElementById("summary-job-connection");
  function text(id, value) { document.getElementById(id).textContent = value; }
  function poll() {
    var controller = window.AbortController ? new window.AbortController() : null;
    var timeout = controller ? window.setTimeout(function () { controller.abort(); }, 10000) : null;
    var options = {cache: "no-store", headers: {"Accept": "application/json"}};
    if (controller) { options.signal = controller.signal; }
    window.fetch(panel.dataset.statusUrl, options)
      .then(function (response) {
        if (response.status === 404) {
          var missing = new Error("Job progress is unavailable; the job may have expired or the server restarted. Saved summaries remain on the Models page.");
          missing.terminal = true;
          throw missing;
        }
        if (!response.ok) { throw new Error("Progress temporarily unavailable. Retrying; do not resubmit the selection."); }
        return response.json();
      })
      .then(function (payload) {
        var job = payload.job;
        if (!payload.ok || !job) { throw new Error("Invalid progress response. Retrying."); }
        if (job.status !== "running") { window.location.reload(); return; }
        connection.classList.add("d-none");
        text("summary-job-status", job.status_label);
        text("summary-job-counts", job.processed + "/" + job.total + " folders; updated: " + job.updated +
             ", reused: " + job.reused + ", skipped: " + job.skipped_count + ", failed: " + job.failed_count + ".");
        text("summary-job-current", job.phase + (job.current_entry ? ": " + job.current_entry : ""));
        text("summary-job-elapsed", "Elapsed: " + Math.round(job.elapsed_seconds) + " seconds.");
        var progress = document.getElementById("summary-job-progress");
        progress.style.width = job.progress_percent + "%";
        progress.parentElement.setAttribute("aria-valuenow", String(Math.round(job.progress_percent)));
        document.getElementById("summary-job-cancel").disabled = Boolean(job.cancel_requested);
        window.setTimeout(poll, 1500);
      })
      .catch(function (error) {
        connection.textContent = error.terminal ? error.message :
          "Progress temporarily unavailable. Retrying; the job may still be running. Do not resubmit the selection.";
        connection.classList.remove("d-none");
        if (error.terminal) {
          text("summary-job-status", "Unavailable");
          document.getElementById("summary-job-cancel").disabled = true;
        } else { window.setTimeout(poll, 5000); }
      })
      .finally(function () {
        if (timeout !== null) { window.clearTimeout(timeout); }
      });
  }
  poll();
})();
