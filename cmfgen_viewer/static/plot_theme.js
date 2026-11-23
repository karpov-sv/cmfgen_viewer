/* Use the page's computed colors, as in lcserver/static/plot_theme.js. */
(function () {
  "use strict";

  function background() {
    return getComputedStyle(document.body).backgroundColor;
  }

  function colors() {
    var css = getComputedStyle(document.body);
    return {
      background: background(),
      text: css.color,
      border: css.getPropertyValue("--bs-border-color").trim(),
      grid: "rgba(128,128,128,0.2)",
      accent: css.getPropertyValue("--bs-link-color").trim()
    };
  }

  function axisColors(theme) {
    return { color: theme.text, gridcolor: theme.grid,
      zerolinecolor: theme.border, linecolor: theme.border };
  }

  function layout(source) {
    source = source || {};
    var theme = colors();
    var result = Object.assign({}, source, {
      paper_bgcolor: theme.background,
      plot_bgcolor: theme.background,
      font: Object.assign({}, source.font, { color: theme.text }),
      modebar: Object.assign({}, source.modebar, {
        bgcolor: theme.background, color: theme.text, activecolor: theme.accent
      }),
      legend: Object.assign({}, source.legend, { bgcolor: theme.background,
        font: Object.assign({}, source.legend && source.legend.font, { color: theme.text }) }),
      hoverlabel: Object.assign({}, source.hoverlabel, { bgcolor: theme.background,
        bordercolor: theme.border,
        font: Object.assign({}, source.hoverlabel && source.hoverlabel.font, { color: theme.text }) })
    });
    var axes = new Set(["xaxis", "yaxis"]);
    Object.keys(source).filter(function (key) { return /^[xy]axis\d*$/.test(key); })
      .forEach(function (key) { axes.add(key); });
    axes.forEach(function (key) {
      result[key] = Object.assign({}, source[key], axisColors(theme));
    });
    return result;
  }

  function trace(source) {
    if (!source.meta || source.meta.transform_target !== "observed") return source;
    var result = Object.assign({}, source);
    var color = colors().text;
    ["line", "marker", "error_x", "error_y"].forEach(function (key) {
      if (source[key]) result[key] = Object.assign({}, source[key], { color: color });
    });
    return result;
  }

  function recolorTraces(plot) {
    (plot.data || []).forEach(function (source, index) {
      var themed = trace(source);
      var update = {};
      ["line", "marker", "error_x", "error_y"].forEach(function (key) {
        if (source[key] && source[key].color !== themed[key].color) {
          update[key + ".color"] = themed[key].color;
        }
      });
      if (Object.keys(update).length) window.Plotly.restyle(plot, update, [index]);
    });
  }

  function bind(plot) {
    if (plot.__themeBound) return;
    plot.__themeBound = true;
    // Sampling, transformations and newly added uploads may restore source styles.
    plot.on("plotly_afterplot", function () { recolorTraces(plot); });
    recolorTraces(plot);
  }

  window.CmfgenPlotTheme = { layout: layout, background: background, trace: trace, bind: bind };

  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function () {
    if (!window.Plotly) return;
    document.querySelectorAll(".js-plotly-plot").forEach(function (plot) {
      if (!plot.layout) return;
      var themed = layout(plot.layout);
      var update = {};
      ["paper_bgcolor", "plot_bgcolor", "font.color", "modebar.bgcolor", "modebar.color",
        "modebar.activecolor", "legend.bgcolor", "legend.font.color", "hoverlabel.bgcolor",
        "hoverlabel.bordercolor", "hoverlabel.font.color"].forEach(function (path) {
        update[path] = path.split(".").reduce(function (value, key) { return value[key]; }, themed);
      });
      Object.keys(themed).filter(function (key) { return /^[xy]axis\d*$/.test(key); })
        .forEach(function (key) {
          ["color", "gridcolor", "zerolinecolor", "linecolor"].forEach(function (property) {
            update[key + "." + property] = themed[key][property];
          });
        });
      // Only change appearance: retain zoom, selections, scales and trace data.
      window.Plotly.relayout(plot, update);
      recolorTraces(plot);
    });
  });
})();
