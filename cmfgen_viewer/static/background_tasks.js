(function () {
  "use strict";

  var nav = document.getElementById("background-task-nav");
  var count = document.getElementById("background-task-count");
  var list = document.getElementById("background-task-list");
  var live = document.getElementById("background-task-live");
  if (!nav || !count || !list || !window.fetch) {
    return;
  }

  var statusUrl = String(nav.getAttribute("data-status-url") || "");
  if (!statusUrl) {
    return;
  }

  var pollTimer = null;
  var requestInFlight = false;

  function asFiniteNumber(value, fallback) {
    var numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  }

  function clearList() {
    while (list.firstChild) {
      list.removeChild(list.firstChild);
    }
  }

  function appendText(parent, className, value) {
    var element = document.createElement("div");
    element.className = className;
    element.textContent = String(value || "");
    parent.appendChild(element);
    return element;
  }

  function buildTaskLink(task) {
    var link = document.createElement("a");
    link.className = "dropdown-item background-task-item rounded px-2 py-2";
    link.href = String(task.href || "#");

    var heading = document.createElement("div");
    heading.className = "d-flex align-items-start justify-content-between gap-3";
    appendText(heading, "fw-semibold text-wrap", task.title || "Background task");
    appendText(heading, "small text-muted flex-shrink-0", task.status_label || "Running");
    link.appendChild(heading);

    appendText(link, "small text-muted background-task-target", task.target || "");

    var percentage = Math.min(100, Math.max(0, asFiniteNumber(task.progress_percent, 0)));
    var progress = document.createElement("div");
    progress.className = "progress background-task-progress my-2";
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-valuemin", "0");
    progress.setAttribute("aria-valuemax", "100");
    progress.setAttribute("aria-valuenow", String(Math.round(percentage)));
    var progressBar = document.createElement("div");
    progressBar.className = "progress-bar progress-bar-striped progress-bar-animated";
    progressBar.style.width = percentage.toFixed(1) + "%";
    progress.appendChild(progressBar);
    link.appendChild(progress);

    appendText(link, "small", task.progress_label || "Working...");
    if (task.current_model) {
      appendText(link, "small text-muted background-task-current", "Current: " + task.current_model);
    }
    appendText(link, "small text-primary mt-1", task.return_label || "Return to task");
    return link;
  }

  function render(payload) {
    var tasks = payload && Array.isArray(payload.tasks) ? payload.tasks : [];
    clearList();
    if (!tasks.length) {
      nav.classList.add("d-none");
      count.textContent = "0";
      if (live) {
        live.textContent = "No background tasks running.";
      }
      return 0;
    }

    for (var index = 0; index < tasks.length; index += 1) {
      list.appendChild(buildTaskLink(tasks[index]));
    }
    count.textContent = String(tasks.length);
    nav.classList.remove("d-none");
    nav.title = tasks.length === 1 ? "1 background task running" : tasks.length + " background tasks running";
    if (live) {
      live.textContent = nav.title;
    }
    return tasks.length;
  }

  function schedulePoll(delay) {
    if (pollTimer !== null) {
      window.clearTimeout(pollTimer);
    }
    pollTimer = window.setTimeout(refresh, delay);
  }

  function refresh() {
    if (requestInFlight) {
      return;
    }
    requestInFlight = true;
    window.fetch(statusUrl, {
      method: "GET",
      cache: "no-store",
      headers: {"Accept": "application/json"}
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Could not load background task status.");
        }
        return response.json();
      })
      .then(function (payload) {
        var runningCount = render(payload);
        schedulePoll(runningCount > 0 ? 1500 : 5000);
      })
      .catch(function () {
        schedulePoll(10000);
      })
      .finally(function () {
        requestInFlight = false;
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) {
      refresh();
    }
  });
  window.addEventListener("cmfgen:background-tasks-changed", refresh);
  refresh();
})();
