(() => {
  "use strict";
  document.querySelectorAll("[data-copy-path]").forEach(button => {
    const status = button.closest("nav").querySelector("[data-path-copy-status]");
    let resetTimer;
    button.addEventListener("click", async () => {
      window.clearTimeout(resetTimer);
      status.replaceChildren();
      status.classList.remove("text-success");
      const path = button.dataset.copyPath;
      let copied = false;
      try {
        await navigator.clipboard.writeText(path);
        copied = true;
      } catch (_error) {
        // Support HTTP hosts and browsers without Clipboard API access.
        const field = document.createElement("input");
        field.value = path;
        field.readOnly = true;
        field.setAttribute("aria-label", `Full ${button.dataset.copyPathKind} path`);
        field.className = "form-control form-control-sm font-monospace";
        status.append(field);
        field.select();
        try { copied = document.execCommand("copy"); } catch (_copyError) { /* Keep manual copy available. */ }
        if (!copied) {
          status.prepend("Copy the selected path: ");
          return;
        }
        button.focus();
      }
      status.textContent = "Copied";
      status.classList.add("text-success");
      resetTimer = window.setTimeout(() => {
        status.textContent = "";
        status.classList.remove("text-success");
      }, 2000);
    });
  });
})();
