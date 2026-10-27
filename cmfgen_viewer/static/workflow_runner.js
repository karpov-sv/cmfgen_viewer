(() => {
  "use strict";
  const panels = Array.from(document.querySelectorAll("[data-workflow-runner]"));
  if (!panels.length) return;
  const states = panels.map(panel => ({panel, job: null, busy: false}));
  let timer, refreshing = false;
  const query = (state, name) => state.panel.querySelector(`[data-inline-${name}]`);
  const error = (state, message = "") => {
    const target = query(state, "error");
    target.textContent = message;
    target.classList.toggle("d-none", !message);
  };
  const json = async (url, init = {}) => {
    const response = await fetch(url, {cache: "no-store", ...init});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || "The runner is unavailable. Try again after the viewer reconnects.");
    return data;
  };
  const updateButtons = () => {
    const active = states.some(state => state.job?.active || state.busy);
    states.forEach(state => {
      state.panel.querySelectorAll("[data-inline-run]").forEach(button => {
        button.disabled = state.busy || active;
      });
    });
  };
  const render = (state, job) => {
    const finished = state.job?.active && !job.active;
    state.job = job;
    if (query(state, "job")) {
      query(state, "job").classList.remove("d-none");
      const badge = query(state, "state");
      badge.className = `badge ${job.status_class}`;
      badge.textContent = job.status_label;
      query(state, "stage").textContent = job.active ? (job.stage_label || job.sequence_label) : job.sequence_label;
      const elapsed = Math.max(0, Math.floor((Date.now() / 1000) - job.created_epoch));
      query(state, "elapsed").textContent = job.active ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s elapsed` : job.created_label;
      const progress = query(state, "progress");
      if (progress) progress.textContent = job.active ? job.progress_label : "Run finished. Review the workflow results and run details.";
    }
    query(state, "details").href = `/runner-jobs/${job.job_id}`;
    const output = query(state, "output");
    if (output) {
      output.href = `/runner-jobs/${job.job_id}/log?native=1`;
      output.classList.toggle("d-none", !job.native_log);
    }
    const stop = query(state, "stop");
    stop.classList.toggle("d-none", !job.active);
    stop.disabled = !job.can_cancel || state.busy;
    const finish = query(state, "finish");
    if (finish) {
      finish.classList.toggle("d-none", !job.active || (!job.can_stop_after_iteration && !job.stop_after_iteration_pending));
      finish.disabled = !job.can_stop_after_iteration || state.busy;
      finish.textContent = job.stop_after_iteration_pending ? "Finishing iteration…" : "Stop after this iteration";
    }
    if (job.active) {
      state.panel.closest("details.workflow-stage").open = true;
    }
    updateButtons();
    if (finished) {
      document.dispatchEvent(new CustomEvent("cmfgen:runner-finished", {
        detail: {stage: state.panel.dataset.stage}
      }));
    }
  };
  const refresh = async () => {
    clearTimeout(timer);
    if (document.hidden || refreshing) return;
    refreshing = true;
    try {
      const active = states.filter(state => state.job?.active);
      const ids = [...new Set(active.map(state => state.job.job_id))];
      for (const id of ids) {
        const job = await json(`/runner-jobs/${id}?format=json`);
        active.filter(state => state.job.job_id === id).forEach(state => render(state, job));
      }
    } catch (_error) { /* Keep the job visible and reconnect after viewer restart. */ }
    finally {
      refreshing = false;
      if (states.some(state => state.job?.active)) timer = setTimeout(refresh, 5000);
    }
  };
  states.forEach(state => {
    const automatic = query(state, "automatic");
    if (automatic) automatic.addEventListener("change", () => {
      const iterations = state.panel.querySelector('[name="iterations"]');
      iterations.min = automatic.checked ? "2" : "1";
      state.panel.querySelector(`label[for="${iterations.id}"]`).textContent = automatic.checked ? "Iterations per batch" : "Additional iterations";
      iterations.placeholder = automatic.checked ? "5 per batch" : "Use IN_ITS";
    });
    state.panel.addEventListener("submit", async event => {
      const form = event.target;
      if (!form.matches("[data-inline-start]")) return;
      event.preventDefault();
      if (states.some(item => item.busy || item.job?.active)) return;
      const values = new FormData(form);
      const submitter = event.submitter;
      if (submitter?.dataset.inlineSequence) {
        values.set("stage_sequence", submitter.dataset.inlineSequence);
      }
      if (submitter?.dataset.inlineToken) values.set("start_token", submitter.dataset.inlineToken);
      const automaticControl = query(state, "automatic");
      const automatic = automaticControl?.checked === true;
      if (automatic) {
        values.set("automatic", "1");
        values.set("start_token", submitter?.dataset.inlineAutoToken || automaticControl.dataset.startToken);
      }
      else values.delete("automatic");
      const baseLabel = submitter?.dataset.inlineLabel || state.panel.dataset.label;
      const label = automatic ? `${baseLabel} (automatic main)` : baseLabel;
      const iterations = values.get("iterations");
      const threads = values.get("threads");
      const settings = [
        state.panel.dataset.stage === "main" ? (automatic ? `Iterations per batch: ${iterations || "5"}` : `Additional iterations: ${iterations || "IN_ITS"}`) : "",
        automatic ? "Automatic limits: 100 attempts / 500 total iterations. Eligible solver adjustments and recovery enabled; independent verification required. Selected spectra run only after verified convergence." : "",
        `Threads: ${threads || "configured default"}`,
      ].filter(Boolean).join("\n");
      if (!window.confirm(`Start ${label} for ${state.panel.dataset.model}?\n\n${settings}\n\nThe run will continue if you close the page or restart the viewer.`)) return;
      state.busy = true;
      error(state);
      updateButtons();
      try {
        const data = await json(state.panel.dataset.runnerUrl, {method: "POST", body: values});
        state.job = {job_id: data.job_id, active: true};
        render(state, await json(data.status_url));
      } catch (failure) { error(state, failure.message); }
      finally { state.busy = false; updateButtons(); if (state.job?.active) refresh(); }
    });
    query(state, "finish")?.addEventListener("click", async () => {
      state.busy = true;
      query(state, "finish").disabled = true;
      error(state);
      updateButtons();
      try {
        const job = await json(`/runner-jobs/${state.job.job_id}?format=json`);
        await json(`/runner-jobs/${job.job_id}/stop-after-iteration?format=json`, {
          method: "POST", body: new URLSearchParams({cancel_token: job.cancel_token})
        });
        render(state, await json(`/runner-jobs/${job.job_id}?format=json`));
      } catch (failure) { error(state, failure.message); }
      finally { state.busy = false; updateButtons(); refresh(); }
    });
    query(state, "stop").addEventListener("click", async () => {
      state.busy = true;
      query(state, "stop").disabled = true;
      error(state);
      updateButtons();
      try {
        const job = await json(`/runner-jobs/${state.job.job_id}?format=json`);
        await json(`/runner-jobs/${job.job_id}/cancel?format=json`, {
          method: "POST", body: new URLSearchParams({cancel_token: job.cancel_token})
        });
        refresh();
      } catch (failure) { error(state, failure.message); }
      finally { state.busy = false; query(state, "stop").disabled = !state.job.can_cancel; updateButtons(); }
    });
  });
  document.addEventListener("visibilitychange", refresh);
  // One history request restores all cards, with polling only while a job is active.
  json(panels[0].dataset.runnerUrl).then(async ({jobs}) => {
    for (const state of states) {
      // A slow history response may describe the job before an inline launch.
      // Keep the new owner and its completion polling instead of restoring stale history.
      if (state.job || state.busy) continue;
      const job = jobs.find(job => job.stages.includes(state.panel.dataset.stage));
      if (job) render(state, job);
    }
    // An active job from a different workflow also reserves this model.
    const other = jobs.find(job => job.active && !states.some(state => state.job?.job_id === job.job_id));
    if (other && !states.some(state => state.busy || state.job?.active)) render(states[0], other);
    refresh();
  }).catch(failure => states.forEach(state => error(state, failure.message)));
})();
