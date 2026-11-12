(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof bootstrap === "undefined" || !bootstrap.Popover) return;
    var active = null;
    document.querySelectorAll("[data-help-popover]").forEach(function (button) {
      var popover = new bootstrap.Popover(button, {
        trigger: "click", container: "body", placement: "auto", html: button.dataset.helpHtml === "true",
        customClass: "spectrum-help-popover"
      });
      button.addEventListener("show.bs.popover", function () {
        if (active && active.button !== button) active.popover.hide();
        active = { button: button, popover: popover };
        button.setAttribute("aria-expanded", "true");
      });
      button.addEventListener("hidden.bs.popover", function () {
        button.setAttribute("aria-expanded", "false");
        if (active && active.button === button) active = null;
      });
    });
    document.addEventListener("click", function (event) {
      if (!active || active.button.contains(event.target)) return;
      var panel = document.getElementById(active.button.getAttribute("aria-describedby"));
      if (!panel || !panel.contains(event.target)) active.popover.hide();
    });
    document.addEventListener("keydown", function (event) {
      if (active && event.key === "Escape") active.popover.hide();
    });
  });
})();
