(() => {
  "use strict";
  document.querySelectorAll("[data-copy-command]").forEach(button => {
    button.addEventListener("click", async () => {
      const code = document.getElementById(button.dataset.copyCommand);
      const status = button.closest(".workflow-command").querySelector("[data-copy-status]");
      try {
        await navigator.clipboard.writeText(code.textContent);
        status.textContent = "Command copied.";
      } catch (_error) {
        const selection = window.getSelection();
        const range = document.createRange();
        range.selectNodeContents(code);
        selection.removeAllRanges();
        selection.addRange(range);
        status.textContent = "Select and copy the command.";
      }
    });
  });
  document.querySelectorAll("details.workflow-stage").forEach(section => {
    section.addEventListener("toggle", () => {
      if (!section.open || !window.Plotly) return;
      section.querySelectorAll(".plotly-chart").forEach(plot => {
        if (plot.data) window.Plotly.Plots.resize(plot);
      });
    });
  });
})();
