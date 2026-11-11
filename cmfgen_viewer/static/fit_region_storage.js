/* Browser-local drafts, scoped to each upload's fixed wavelength coordinates. */
(function () {
  "use strict";
  function bind(options) {
    if (!options.token || !options.windows || !options.exclusions) return;
    var key = "cmfgen-fit-regions-v1:" + options.token;
    var fields = ["windows", "exclusions"];
    var authoritative = options.authoritative || [];
    var saved;
    try { saved = JSON.parse(window.localStorage.getItem(key)); }
    catch (error) { /* Editing remains available without browser storage. */ }
    if (saved && typeof saved === "object" && !Array.isArray(saved)) {
      fields.forEach(function (name) {
        var input = options[name], value = saved[name];
        if (authoritative.indexOf(name) < 0 && typeof value === "string" &&
            value.length <= input.maxLength) input.value = value;
      });
    }
    function save() {
      var values = { windows: options.windows.value, exclusions: options.exclusions.value };
      try { window.localStorage.setItem(key, JSON.stringify(values)); }
      catch (error) { /* Storage may be blocked or full; keep the form usable. */ }
    }
    fields.forEach(function (name) {
      function changed() {
        save();
        if (options.onChange) options.onChange();
      }
      options[name].addEventListener("input", changed);
      options[name].addEventListener("change", changed);
    });
    // Explicit URL values (including blanks) and restored running-job settings
    // take precedence, and become the draft for the next visit.
    if (authoritative.length) save();
  }
  window.CmfgenFitRegionStorage = { bind: bind };
})();
