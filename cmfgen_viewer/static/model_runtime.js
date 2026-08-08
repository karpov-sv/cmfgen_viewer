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

  const renderProcesses = (container, processes) => {
    container.replaceChildren();
    if (!processes.length) {
      append(container, "p", "small text-muted mb-2", "No matching external process detected.");
      return;
    }

    const responsive = append(container, "div", "table-responsive mb-2");
    const table = append(responsive, "table", "table table-sm align-middle mb-0");
    const head = append(table, "thead");
    const headRow = append(head, "tr");
    ["Process", "State", "Elapsed", "CPU", "Memory"].forEach((label) => append(headRow, "th", "", label));
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
      renderProgressBlock(container, runtime.progress, "Estimated progress:", runtime.active);
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

  const render = (monitor, runtime) => {
    const badge = monitor.querySelector("[data-runtime-state]");
    badge.className = `badge ${runtime.active ? "bg-success" : "bg-secondary"}`;
    badge.textContent = runtime.active ? `Running now · ${runtime.phase_label}` : "Not running";
    monitor.querySelector("[data-runtime-checked]").textContent = `Checked ${runtime.checked_at}`;
    renderProcesses(monitor.querySelector("[data-runtime-processes]"), runtime.processes || []);
    renderProgress(monitor.querySelector("[data-runtime-progress]"), runtime);
    renderDiagnostics(
      monitor,
      monitor.querySelector("[data-runtime-diagnostics]"),
      runtime.diagnostics || [],
    );
  };

  const refresh = async (monitor) => {
    try {
      const response = await fetch(monitor.dataset.modelRuntimeUrl, {
        cache: "no-store",
        headers: {Accept: "application/json"},
      });
      if (!response.ok) {
        throw new Error(`Runtime status request failed: ${response.status}`);
      }
      render(monitor, await response.json());
    } catch (_error) {
      const checked = monitor.querySelector("[data-runtime-checked]");
      checked.textContent = "Live update unavailable";
    }
  };

  const refreshAll = () => {
    if (!document.hidden) {
      monitors.forEach(refresh);
    }
  };

  window.setTimeout(refreshAll, 1000);
  window.setInterval(refreshAll, 5000);
  document.addEventListener("visibilitychange", refreshAll);
})();
