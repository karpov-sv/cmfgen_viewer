(() => {
  "use strict";

  const monitors = Array.from(document.querySelectorAll("[data-model-runtime-url]"));
  if (!monitors.length) {
    return;
  }

  const append = (parent, tag, className, text) => {
    const element = document.createElement(tag);
    if (className) {
      element.className = className;
    }
    if (text !== undefined) {
      element.textContent = text;
    }
    parent.appendChild(element);
    return element;
  };

  const renderProcesses = (container, processes, available) => {
    container.replaceChildren();
    if (!processes.length) {
      append(container, "p", "small text-muted mb-2", available
        ? "No matching external process detected."
        : "Live process detection is unavailable on this system. Recorded file progress remains available.");
      return;
    }

    const responsive = append(container, "div", "table-responsive mb-2");
    const table = append(responsive, "table", "table table-sm align-middle mb-0");
    const head = append(table, "thead");
    const headRow = append(head, "tr");
    ["Process", "OS state", "Elapsed", "CPU", "Memory"].forEach((label) => {
      const heading = append(headRow, "th", "", label);
      if (label === "OS state") heading.title = "OS scheduling snapshot; sleeping does not by itself mean the calculation is paused.";
    });
    const body = append(table, "tbody");
    processes.forEach((process) => {
      const row = append(body, "tr");
      const processCell = append(row, "td");
      append(processCell, "code", "", process.name);
      append(processCell, "span", "small text-muted ms-1", `PID ${process.pid}`);
      append(row, "td", "", process.state);
      append(row, "td", "", process.elapsed);
      const cpu = append(row, "td", "", process.cpu_time);
      append(cpu, "span", "small text-muted ms-1", `(${process.cpu_percent}% avg)`);
      const memory = append(row, "td", "", process.rss);
      append(memory, "span", "small text-muted ms-1", `(${process.threads} threads)`);
    });
  };

  const renderProgressBlock = (container, progress, heading, activeBar) => {
    const summary = append(container, "div", "d-flex flex-wrap justify-content-between gap-2 mb-1");
    const detail = append(summary, "span");
    append(detail, "strong", "", `${heading} `);
    detail.append(document.createTextNode(progress.detail));
    if (progress.percent !== null && progress.percent !== undefined) {
      append(summary, "span", "", `${progress.percent}%`);
      const bar = append(container, "div", "progress mb-2");
      bar.setAttribute("role", "progressbar");
      bar.setAttribute("aria-label", progress.label);
      bar.setAttribute("aria-valuenow", progress.percent);
      bar.setAttribute("aria-valuemin", "0");
      bar.setAttribute("aria-valuemax", "100");
      const fill = append(bar, "div", `progress-bar${activeBar ? "" : " bg-secondary"}`);
      fill.style.width = `${Math.max(0, Math.min(100, progress.percent))}%`;
    }
    if (progress.metrics && progress.metrics.length) {
      const metrics = append(container, "div", "d-flex flex-wrap gap-3 small");
      progress.metrics.forEach((metric) => {
        const item = append(metrics, "span");
        append(item, "span", "text-muted", `${metric.label}: `);
        append(item, "code", "", metric.value);
      });
    }
  };

  const renderProgress = (container, runtime) => {
    container.replaceChildren();
    if (!runtime.active && runtime.recorded_progress && runtime.recorded_progress.length) {
      runtime.recorded_progress.forEach((record, index) => {
        const block = append(container, "div", index ? "border-top pt-2 mt-2" : "");
        renderProgressBlock(block, record.progress, `Last recorded ${record.phase_label} progress:`, false);
      });
      return;
    }
    if (runtime.progress) {
      const heading = runtime.active ? "Estimated progress:"
        : runtime.kind === "lte" ? "Last logged LTE frequency counter:" : "Last recorded progress:";
      renderProgressBlock(container, runtime.progress, heading, runtime.active);
    } else if (runtime.active) {
      append(container, "p", "small text-muted mb-0", "The process is running, but no progress marker from this run is available yet.");
    }
  };

  const diagnosticBadgeClass = (status) => ({
    running: "text-bg-primary",
    succeeded: "text-bg-success",
    failed: "text-bg-danger",
    incomplete: "text-bg-warning",
    unknown: "text-bg-secondary",
  }[status] || "text-bg-secondary");

  const diagnosticHref = (monitor, relativePath) => {
    const base = monitor.dataset.runtimeViewPrefix.replace(/\/$/, "");
    const suffix = relativePath.split("/").map(encodeURIComponent).join("/");
    return `${base}/${suffix}`;
  };

  const renderDiagnostics = (monitor, container, diagnostics) => {
    container.replaceChildren();
    if (!diagnostics.length) {
      return;
    }
    const section = append(container, "div", "border-top pt-2 mt-2");
    append(section, "strong", "small", "Latest run diagnostics");
    diagnostics.forEach((diagnostic) => {
      const row = append(section, "div", "d-flex flex-wrap align-items-start gap-2 mt-2");
      append(
        row,
        "span",
        `badge ${diagnosticBadgeClass(diagnostic.status)}`,
        `${diagnostic.phase_label} · ${diagnostic.status_label}`,
      );
      const body = append(row, "div", "small flex-grow-1");
      append(body, "div", "", diagnostic.summary);
      (diagnostic.findings || []).forEach((finding) => {
        const alert = append(body, "div", `alert ${finding.severity === "error" ? "alert-danger" : "alert-warning"} py-2 mt-2 mb-2`);
        append(alert, "strong", "", finding.title);
        append(alert, "p", "mt-1 mb-2", finding.message);
        append(alert, "div", "small", `Native evidence (${finding.path}):`);
        append(alert, "pre", "small text-wrap mb-2", finding.evidence);
        append(alert, "strong", "", "Suggested next steps");
        const suggestions = append(alert, "ul", "mb-2 ps-3");
        (finding.suggestions || []).forEach((suggestion) => append(suggestions, "li", "", suggestion));
        const links = append(alert, "div", "d-flex flex-wrap gap-2");
        (finding.links || []).forEach((path) => {
          const link = append(links, "a", "", `Open ${path}`);
          link.href = diagnosticHref(monitor, path);
        });
        append(alert, "p", "small text-muted mt-2 mb-0", "Settings shown are from current inputs and may differ from the failed invocation. Suggestions require model review.");
      });
      if (diagnostic.details && diagnostic.details.length) {
        const list = append(body, "ul", "mb-0 ps-3");
        diagnostic.details.forEach((detail) => {
          const item = append(
            list,
            "li",
            detail.level === "danger" ? "text-danger" : "text-warning-emphasis",
            `${detail.message} `,
          );
          if (detail.path && detail.available) {
            const link = append(item, "a");
            link.href = diagnosticHref(monitor, detail.path);
            link.append(document.createTextNode("Open "));
            append(link, "code", "", detail.path);
            if (detail.line) {
              link.append(document.createTextNode(`, line ${detail.line}`));
            }
          } else if (detail.path) {
            append(item, "code", "", detail.path);
          }
        });
      }
    });
  };

  let reloadTimer = null;
  let refreshNotice = null;

  const formFields = Array.from(document.querySelectorAll(
    '.workflow-page form input:not([type="hidden"]):not([type="submit"]), .workflow-page form select, .workflow-page form textarea',
  ));
  const fieldValue = field => field.type === "checkbox" || field.type === "radio"
    ? field.checked : field.tagName === "SELECT"
      ? JSON.stringify(Array.from(field.options).map(option => option.selected)) : field.value;
  const initialValues = new Map(formFields.map(field => [field, fieldValue(field)]));
  const hasUnsavedChanges = () => formFields.some(field => fieldValue(field) !== initialValues.get(field));

  // Navigate with GET even if this page was rendered after a failed form POST.
  const reloadPage = () => window.location.replace(window.location.href);

  const refreshResults = (monitor) => {
    if (reloadTimer !== null || refreshNotice) return;
    // Coalesce simultaneous LTE/hydro updates and allow final outputs to settle.
    reloadTimer = window.setTimeout(() => {
      reloadTimer = null;
      if (!hasUnsavedChanges()) {
        reloadPage();
        return;
      }
      refreshNotice = append(monitor, "div", "small border-top pt-2 mt-2");
      append(refreshNotice, "span", "me-2", "Run stopped. This page has unsaved changes.");
      const button = append(refreshNotice, "button", "btn btn-sm btn-outline-primary", "Refresh results");
      button.type = "button";
      button.addEventListener("click", reloadPage);
    }, 1000);
  };

  const render = (monitor, runtime) => {
    if (monitor.dataset.runtimeCompact === "true") {
      monitor.classList.toggle("runtime-idle", !runtime.active && runtime.monitoring_available === true);
    }
    const badge = monitor.querySelector("[data-runtime-state]");
    badge.className = `badge ${runtime.active ? "bg-success" : "bg-secondary"}`;
    badge.textContent = runtime.active ? `Running now · ${runtime.phase_label}`
      : runtime.monitoring_available ? "Not running" : "Monitoring unavailable";
    monitor.querySelector("[data-runtime-checked]").textContent = `Checked ${runtime.checked_at}`;
    renderProcesses(monitor.querySelector("[data-runtime-processes]"), runtime.processes || [], runtime.monitoring_available);
    document.querySelectorAll("[data-workflow-runtime-summary]").forEach(element => {
      if (element.dataset.workflowRuntimeSummary !== monitor.dataset.runtimeKey) return;
      // Output freshness comes from the workflow checks. Runtime updates only
      // report activity; the completion refresh reruns those checks.
      const outputReady = element.dataset.workflowOutputReady === "true";
      element.textContent = !runtime.active && outputReady
        ? `Output ready · ${runtime.monitoring_available ? "not running" : "monitoring unavailable"}`
        : badge.textContent;
      element.className = !runtime.active && outputReady && runtime.monitoring_available
        ? "badge bg-success" : badge.className;
    });
    const stage = monitor.closest("details.workflow-stage");
    if (stage && runtime.active && monitor.dataset.runtimeActive !== "true") stage.open = true;
    const runStopped = monitor.dataset.runtimeActive === "true" &&
      !runtime.active && runtime.monitoring_available === true;
    // A denied read is not evidence of completion; keep the last known activity.
    if (runtime.active || runtime.monitoring_available === true) {
      monitor.dataset.runtimeActive = String(runtime.active);
    }
    if (runStopped) refreshResults(monitor);
    const stageBadge = stage?.querySelector(":scope > summary .badge");
    if (stageBadge) {
      if (!stageBadge.dataset.idleLabel) {
        stageBadge.dataset.idleLabel = stageBadge.textContent.trim() === "Running"
          ? "Run stopped · refresh checks" : stageBadge.textContent.trim();
        stageBadge.dataset.idleClass = stageBadge.textContent.trim() === "Running"
          ? "badge bg-secondary" : stageBadge.className;
      }
      stageBadge.textContent = runtime.active ? "Running" : stageBadge.dataset.idleLabel;
      stageBadge.className = runtime.active ? "badge bg-success" : stageBadge.dataset.idleClass;
    }
    document.querySelectorAll("[data-workflow-diagnostic-summary]").forEach(element => {
      if (element.dataset.workflowDiagnosticSummary !== monitor.dataset.runtimeKey) return;
      const diagnostic = (runtime.diagnostics || []).find(item => item.phase_label === element.dataset.phase);
      if (!diagnostic) return;
      element.textContent = diagnostic.status_label;
      element.className = `badge ${diagnosticBadgeClass(diagnostic.status)}`;
    });
    renderProgress(monitor.querySelector("[data-runtime-progress]"), runtime);
    renderDiagnostics(
      monitor,
      monitor.querySelector("[data-runtime-diagnostics]"),
      runtime.diagnostics || [],
    );
    const diagnosisKey = (runtime.diagnostics || []).map(item => item.status).join(":");
    if (monitor.dataset.diagnosisKey && monitor.dataset.diagnosisKey !== diagnosisKey &&
        (runtime.diagnostics || []).some(item => item.status === "failed")) {
      const stage = monitor.closest("details.workflow-stage");
      if (stage) stage.open = true;
    }
    monitor.dataset.diagnosisKey = diagnosisKey;
  };

  let streamConnected = false;
  let pollTimer = null;

  const refresh = async (monitor) => {
    try {
      const response = await fetch(monitor.dataset.modelRuntimeUrl, {
        cache: "no-store",
        headers: {Accept: "application/json"},
      });
      if (!response.ok) {
        throw new Error(`Runtime status request failed: ${response.status}`);
      }
      const runtime = await response.json();
      if (!streamConnected) render(monitor, runtime);
    } catch (_error) {
      if (!streamConnected) {
        const checked = monitor.querySelector("[data-runtime-checked]");
        checked.textContent = "Live update unavailable";
      }
    }
  };

  const refreshAll = () => {
    if (!document.hidden && !streamConnected) {
      monitors.forEach(refresh);
    }
  };

  const stopPolling = () => {
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = null;
  };
  const startPolling = () => {
    if (document.hidden || streamConnected || pollTimer !== null) return;
    refreshAll();
    pollTimer = window.setInterval(refreshAll, 5000);
  };

  if (window.CmfgenLiveUpdates) {
    monitors.forEach(monitor => {
      const key = monitor.dataset.runtimeKey;
      window.CmfgenLiveUpdates.subscribe("runtime:" + key, runtime => render(monitor, runtime));
      window.CmfgenLiveUpdates.subscribe("runtime-error:" + key, () => {
        monitor.querySelector("[data-runtime-checked]").textContent = "Live update unavailable";
      });
    });
    window.CmfgenLiveUpdates.subscribe("connection", connected => {
      streamConnected = connected;
      if (connected) stopPolling();
      else startPolling();
    });
  } else {
    startPolling();
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopPolling();
    else startPolling();
  });
})();
