(() => {
  "use strict";
  const panel = document.getElementById("runner-job");
  if (!panel || panel.dataset.active !== "true") return;
  let timer;
  let busy = false;
  const refresh = async () => {
    window.clearTimeout(timer);
    if (document.hidden || busy) return;
    busy = true;
    try {
      const response = await fetch(panel.dataset.statusUrl, {cache: "no-store"});
      if (!response.ok) throw Error("Job unavailable");
      const job = await response.json();
      if (!job.active) { window.location.reload(); return; }
      const cancelToken = document.querySelector('input[name="cancel_token"]');
      if (cancelToken) cancelToken.value = job.cancel_token;
      const stopButton = document.querySelector("[data-runner-stop]");
      if (stopButton) stopButton.disabled = !job.can_cancel;
      const nativeOutput = panel.querySelector("[data-runner-native-output]");
      if (nativeOutput) nativeOutput.classList.toggle("d-none", !job.native_log);
      const autoNote = panel.querySelector("[data-runner-auto-note]");
      if (autoNote) autoNote.textContent = job.auto_action ? `Latest automatic action: ${job.auto_action}` : (job.auto_reason || "Eligible recovery and independent verification are enabled.");
      const badge = panel.querySelector("[data-runner-state]");
      badge.textContent = job.status_label;
      badge.className = `badge ${job.status_class}`;
      panel.querySelector("[data-runner-stage]").textContent = job.stage_label || "";
      panel.querySelector("[data-runner-progress]").textContent = job.progress_label;
    } catch (_error) { /* Reconnect after the viewer restarts. */ }
    finally { busy = false; }
    timer = window.setTimeout(refresh, 5000);
  };
  document.addEventListener("visibilitychange", refresh);
  refresh();
})();
