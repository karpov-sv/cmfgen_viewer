/* Keep native spectra outside Plotly; reduce only the current display window. */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CmfgenSpectrumSampling = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  function finite(value) {
    return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));
  }

  function sampleTrace(trace, range, logarithmic, budget, native) {
    var size = Math.min((trace.x || []).length, (trace.y || []).length);
    var result = Object.assign({}, trace);
    result.line = Object.assign({}, trace.line, { simplify: false });
    // Photometry retains every band and its uncertainty, including bands that
    // overlap the window even if their central wavelength is outside it.
    if (String(trace.mode || "lines").indexOf("lines") === -1) return result;
    var first = size;
    var last = -1;
    var low = range ? Math.min(range[0], range[1]) : -Infinity;
    var high = range ? Math.max(range[0], range[1]) : Infinity;
    var previous = null;
    for (var i = 0; i < size; i += 1) {
      var x = Number(trace.x[i]);
      if (!finite(trace.x[i]) || (logarithmic && x <= 0)) continue;
      if (x >= low && x <= high) {
        first = Math.min(first, i);
        last = i;
      }
      // Include endpoints of crossing segments, also for sparse spectra with
      // no samples inside the window. Original order and gaps are preserved.
      if (previous !== null && Math.min(x, previous.x) <= high && Math.max(x, previous.x) >= low) {
        first = Math.min(first, previous.index);
        last = Math.max(last, i);
      }
      previous = { x: x, index: i };
    }
    if (last < 0) { first = 0; last = -1; }
    else {
      first = Math.max(0, first - 1);
      last = Math.min(size - 1, last + 1);
    }
    var indices = [];
    if (native || last - first + 1 <= budget) {
      for (i = first; i <= last; i += 1) indices.push(i);
    } else {
      // Four representatives per wavelength bin: first, minimum, maximum,
      // last. Unlike uniform index decimation this retains narrow line cores.
      var coordinate = function (value) { return logarithmic ? Math.log10(value) : value; };
      var start = Infinity;
      var end = -Infinity;
      for (i = first; i <= last; i += 1) {
        if (!finite(trace.x[i]) || (logarithmic && Number(trace.x[i]) <= 0)) continue;
        var position = coordinate(Number(trace.x[i]));
        start = Math.min(start, position);
        end = Math.max(end, position);
      }
      var errors = trace.error_y;
      var hasErrors = errors && errors.visible !== false && (!errors.type || errors.type === "data") && Array.isArray(errors.array);
      function envelope(index, upper) {
        var array = !upper && errors.symmetric === false ? errors.arrayminus : errors.array;
        var error = array && finite(array[index]) ? Math.max(0, Number(array[index])) : 0;
        return Number(trace.y[index]) + (upper ? error : -error);
      }
      var bins = Math.max(1, Math.floor(budget / (hasErrors ? 6 : 4)));
      var buckets = new Map();
      var keep = new Set([first, last]);
      for (i = first; i <= last; i += 1) {
        if (!finite(trace.x[i]) || !finite(trace.y[i]) || (logarithmic && Number(trace.x[i]) <= 0)) {
          // Keep break points and both sides so reduction cannot bridge gaps.
          keep.add(i);
          if (i > first) keep.add(i - 1);
          if (i < last) keep.add(i + 1);
          continue;
        }
        var bin = end > start ? Math.min(bins - 1, Math.floor((coordinate(Number(trace.x[i])) - start) / (end - start) * bins)) : 0;
        var bucket = buckets.get(bin);
        if (!bucket) buckets.set(bin, { first: i, last: i, min: i, max: i, lower: i, upper: i });
        else {
          bucket.last = i;
          if (Number(trace.y[i]) < Number(trace.y[bucket.min])) bucket.min = i;
          if (Number(trace.y[i]) > Number(trace.y[bucket.max])) bucket.max = i;
          if (hasErrors && envelope(i, false) < envelope(bucket.lower, false)) bucket.lower = i;
          if (hasErrors && envelope(i, true) > envelope(bucket.upper, true)) bucket.upper = i;
        }
      }
      buckets.forEach(function (bucket) {
        [bucket.first, bucket.min, bucket.max, bucket.last].forEach(function (index) { keep.add(index); });
        if (hasErrors) { keep.add(bucket.lower); keep.add(bucket.upper); }
      });
      indices = Array.from(keep).sort(function (a, b) { return a - b; });
    }
    function select(values) { return indices.map(function (index) { return values[index]; }); }
    ["x", "y", "text", "hovertext", "customdata", "ids"].forEach(function (key) {
      if (Array.isArray(trace[key]) && trace[key].length >= size) result[key] = select(trace[key]);
    });
    ["error_x", "error_y"].forEach(function (key) {
      if (!trace[key]) return;
      result[key] = Object.assign({}, trace[key]);
      ["array", "arrayminus"].forEach(function (field) {
        if (Array.isArray(trace[key][field])) result[key][field] = select(trace[key][field]);
      });
    });
    return result;
  }

  function create(target, traces, layout) {
    var sources = traces.map(function (trace) { return Object.assign({}, trace); });
    var frame = null;
    var resetting = false;
    var renderPromise = Promise.resolve();
    var native = false;
    var selector;
    var status;
    var initialAxis = (layout || {}).xaxis || {};

    function displayed(trace, initial) {
      var axis = initial ? initialAxis : (target._fullLayout || {}).xaxis || initialAxis;
      var autorange = initial ? axis.autorange !== false && !axis.range
        : axis.autorange === undefined ? (target.layout.xaxis || {}).autorange !== false : axis.autorange !== false;
      var range = !autorange && axis.range ? axis.range.slice() : null;
      if (range && axis.type === "log") range = range.map(function (value) { return Math.pow(10, value); });
      var budget = Math.max(5000, Math.min(12000, Math.ceil((axis._length || 1000) * 4)));
      return sampleTrace(trace, range, axis.type === "log", budget, native);
    }

    function report(data) {
      if (!status) return;
      var shown = 0;
      var total = 0;
      data.forEach(function (trace, index) {
        if (trace.visible === false || trace.visible === "legendonly") return;
        shown += (trace.x || []).length;
        total += (sources[index].x || []).length;
      });
      status.textContent = shown.toLocaleString() + " displayed / " + total.toLocaleString() + " native samples";
    }

    function getSources() {
      return sources.map(function (trace, index) {
        return Object.assign({}, trace, { visible: target.data && target.data[index] ? target.data[index].visible : trace.visible });
      });
    }

    function renderNow() {
      if (!target.data) return;
      var data = getSources().map(function (trace) { return displayed(trace, false); });
      var update = { x: [], y: [], "line.simplify": false };
      data.forEach(function (trace) { update.x.push(trace.x); update.y.push(trace.y); });
      ["text", "hovertext", "customdata", "ids"].forEach(function (key) {
        var values = data.map(function (trace) { return trace[key]; });
        if (values.some(function (value) { return Array.isArray(value); })) update[key] = values.map(function (value) { return value === undefined ? null : value; });
      });
      ["error_x", "error_y"].forEach(function (key) {
        if (data.some(function (trace, index) { return trace[key] || target.data[index][key]; })) {
          update[key] = data.map(function (trace) { return trace[key] || null; });
        }
      });
      report(data);
      return Plotly.restyle(target, update);
    }

    function render() {
      // Zooms, transformations and reset may overlap while Plotly is drawing.
      // Serialize redraws and always read the latest native sources/range.
      renderPromise = renderPromise.then(renderNow);
      return renderPromise;
    }

    function schedule() {
      if (frame === null) frame = window.requestAnimationFrame(function () { frame = null; render(); });
    }

    var controller = {
      initialData: sources.map(function (trace) { return displayed(trace, true); }),
      getSources: getSources,
      render: render,
      setSeries: function (x, y) {
        sources = sources.map(function (trace, index) { return Object.assign({}, trace, { x: x[index], y: y[index] }); });
        return render();
      },
      replaceTrace: function (index, trace) { sources[index] = Object.assign({}, trace); return displayed(trace, false); },
      appendTrace: function (trace) { sources.push(Object.assign({}, trace)); return displayed(trace, false); },
      removeTrace: function (index) { sources.splice(index, 1); },
      bind: function () {
        selector = document.getElementById(target.id + "-sampling");
        status = document.getElementById(target.id + "-sampling-status");
        if (selector) selector.addEventListener("change", function () { native = selector.value === "native"; schedule(); });
        target.on("plotly_relayout", function (event) {
          if (resetting) return;
          if (event["xaxis.autorange"] === true) {
            // Plotly initially autoranges the cropped display. Restore the
            // entire spectrum before computing the double-click/reset extent.
            resetting = true;
            Promise.resolve(render()).then(function () {
              return Plotly.relayout(target, { "xaxis.autorange": true });
            }).finally(function () { resetting = false; });
          } else if (Object.keys(event).some(function (key) {
            return key.indexOf("xaxis.") === 0 || key === "yaxis.type" || key === "width" || key === "height";
          })) schedule();
        });
        target.on("plotly_restyle", function () { report(target.data); });
        if (typeof ResizeObserver !== "undefined") new ResizeObserver(schedule).observe(target);
        report(target.data);
      }
    };
    target.__spectrumSampling = controller;
    return controller;
  }

  return { sampleTrace: sampleTrace, create: create };
});
