"""Plot themes follow Bootstrap without changing scientific data or view state."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_plot_theme_preserves_layout_and_updates_existing_plots():
    script = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/plot_theme.js"
    result = subprocess.run([shutil.which("node"), "-e", r'''
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
let dark = true, changed;
const palettes = {
  dark: {'--bs-body-bg':'#212529', '--bs-body-color':'#dee2e6',
    '--bs-border-color':'#495057', '--bs-border-color-translucent':'rgba(255,255,255,0.15)',
    '--bs-link-color':'#6ea8fe'},
  light: {'--bs-body-bg':'#fff', '--bs-body-color':'#212529',
    '--bs-border-color':'#dee2e6', '--bs-border-color-translucent':'rgba(0,0,0,0.175)',
    '--bs-link-color':'#0d6efd'}
};
const original = {template:'plotly_white', xaxis:{type:'log',range:[1,3],title:{text:'Radius'}},
  yaxis2:{overlaying:'y',side:'right'}, font:{size:14}, legend:{orientation:'h'},
  annotations:[{text:'Line',x:1,y:2}], uirevision:'keep'};
const before = JSON.stringify(original);
const plots = [{layout:original, data:[{x:[10,100],y:[1,2]}]}, {layout:{}}, {}];
const updates = [], restyles = [];
const window = {
  matchMedia: () => ({addEventListener: (event, callback) => { changed = callback; }}),
  Plotly:{restyle:(plot, update, indexes) => {
    restyles.push(update);
    for (const index of indexes) for (const [path, value] of Object.entries(update)) {
      const [key, property] = path.split('.');
      plot.data[index][key][property] = value;
    }
    return Promise.resolve();
  }, relayout:(plot, update) => {updates.push({plot,update}); return Promise.resolve();}}
};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'), {window, Set,
  document:{body:{},querySelectorAll:()=>plots},
  getComputedStyle:()=>({backgroundColor:palettes[dark?'dark':'light']['--bs-body-bg'],
    color:palettes[dark?'dark':'light']['--bs-body-color'],
    getPropertyValue:key=>palettes[dark?'dark':'light'][key]})});
const themed = window.CmfgenPlotTheme.layout(original);
assert.equal(themed.paper_bgcolor,'#212529');
assert.equal(themed.plot_bgcolor,'#212529');
assert.equal(themed.font.color,'#dee2e6');
assert.equal(themed.font.size,14);
assert.equal(themed.xaxis.type,'log');
assert.deepEqual(themed.xaxis.range,[1,3]);
assert.equal(themed.yaxis2.overlaying,'y');
assert.equal(themed.yaxis2.color,'#dee2e6');
assert.equal(themed.legend.orientation,'h');
assert.equal(JSON.stringify(original),before,'theme must not mutate source layouts');
dark = false;
changed();
assert.equal(updates.length,2,'update every initialized plot');
for (const {update} of updates) {
  assert.equal(update.paper_bgcolor,'#fff');
  assert.equal(update.plot_bgcolor,'#fff');
  assert.equal(update['font.color'],'#212529');
  assert.equal(update['xaxis.gridcolor'],'rgba(128,128,128,0.2)');
  assert(!Object.keys(update).some(key=>/range|autorange|type|selection|uirevision/.test(key)),
    'live theme updates must preserve zoom, scales and selections');
}
assert.equal(JSON.stringify(original),before);
assert.deepEqual(plots[0].data,[{x:[10,100],y:[1,2]}]);
dark = true;
changed();
assert.equal(updates.at(-1).update.paper_bgcolor,'#212529');
assert.equal(window.CmfgenPlotTheme.background(),'#212529');
const observed = {meta:{transform_target:'observed'}, x:[5000,6000], y:[1,2],
  marker:{color:'#212529',symbol:'circle-open',size:8}, line:{color:'#212529',width:1.2},
  error_x:{array:[100,200],color:'rgba(33,37,41,0.45)'},
  error_y:{array:[0.1,0.2],color:'rgba(33,37,41,0.45)'}};
const originalObserved = JSON.stringify(observed);
const visible = window.CmfgenPlotTheme.trace(observed);
for (const key of ['line','marker','error_x','error_y']) assert.equal(visible[key].color,'#dee2e6');
assert.equal(visible.marker.symbol,'circle-open');
assert.equal(visible.marker.size,8);
assert.equal(visible.error_y.array,observed.error_y.array);
assert.equal(JSON.stringify(observed),originalObserved,'preserve native traces');
const model = {meta:{transform_target:'model'},line:{color:'red'}};
assert.equal(window.CmfgenPlotTheme.trace(model),model,'preserve model colors');
let afterplot, bindings = 0;
const uploadPlot = {layout:{}, data:[JSON.parse(originalObserved),model],
  on:(event, callback) => {afterplot=callback; bindings++;}};
plots.push(uploadPlot);
window.CmfgenPlotTheme.bind(uploadPlot);
window.CmfgenPlotTheme.bind(uploadPlot);
assert.equal(bindings,1,'bind only once');
assert.equal(uploadPlot.data[0].marker.color,'#dee2e6');
const restyleCount = restyles.length;
afterplot();
assert.equal(restyles.length,restyleCount,'must not create an afterplot loop');
dark=false;
changed();
assert.equal(uploadPlot.data[0].marker.color,'#212529');
assert.equal(uploadPlot.data[0].line.color,'#212529');
assert.equal(uploadPlot.data[0].error_y.color,'#212529');
dark=true;
changed();
assert.equal(uploadPlot.data[0].marker.color,'#dee2e6');
// Sampling can restore the original error-bar style after a zoom.
uploadPlot.data[0].error_y.color='rgba(33,37,41,0.45)';
afterplot();
assert.equal(uploadPlot.data[0].error_y.color,'#dee2e6');
// An upload added after the first render must also inherit the active theme.
uploadPlot.data.push(JSON.parse(originalObserved));
afterplot();
assert.equal(uploadPlot.data[2].marker.color,'#dee2e6');
assert.deepEqual(uploadPlot.data[0].error_y.array,[0.1,0.2]);
assert.equal(model.line.color,'red');
''', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
