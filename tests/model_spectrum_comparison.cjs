const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

class Element {
  constructor(value = '') { this.value = value; this.handlers = {}; this.children = []; this.style = {}; this.dataset = {}; this.hidden = false; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  closest() { return this.row; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  change() { this.handlers.change(); }
  click() { this.handlers.click(); }
}
async function main() {
  const ids = ['model-spectrum-comparison', 'model-comparison-plot', 'comparison-canvas', 'comparison-status',
    'comparison-errors', 'comparison-mode', 'model-comparison-plot-xscale', 'model-comparison-plot-yscale',
    'comparison-clear', 'comparison-refresh', 'comparison-select-visible', 'summary-table'];
  const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
  const boxes = ['grid/a', 'other/a', 'missing', 'fourth'].map(value => { const box = new Element(value); box.row = { hidden: false }; return box; });
  const target = elements['model-comparison-plot']; target.id = 'model-comparison-plot';
  elements['summary-table'].querySelectorAll = () => boxes;
  elements['summary-table'].tBodies = [{}];
  elements['model-spectrum-comparison'].dataset.spectrumUrl = '/models/spectrum-data';
  elements['comparison-mode'].value = 'normalized';
  elements[target.id + '-xscale'].value = 'log';
  elements[target.id + '-yscale'].value = 'linear';
  let observer, requests = [], plots = [], created = 0;
  const context = {
    document: { getElementById: id => elements[id], createElement: () => new Element() },
    window: { Plotly: {}, location: { href: 'http://localhost/models/' } }, URL, console,
    MutationObserver: class { constructor(fn) { observer = fn; } observe() {} },
    fetch: url => new Promise(resolve => requests.push({ url, resolve })),
    Plotly: { Plots: { resize: async () => {} } },
    CmfgenSpectrumControls: { createPlot: () => {
      created++;
      return { ready: Promise.resolve(), sampling: { setTraces: async (traces, layout) => { plots.push(traces); target.data = traces; target.layout = layout; } } };
    } }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../cmfgen_viewer/static/model_spectrum_comparison.js'), 'utf8'), context);
  const flush = () => new Promise(resolve => setImmediate(resolve));
  function respond(request, error = false) {
    const mode = request.url.searchParams.get('mode');
    const trace = role => ({ x: [4000, 5000], y: [1, 2], line: {}, meta: { plot_role: role }, hovertemplate: '<extra></extra>' });
    request.resolve({ ok: !error, json: async () => error ? { error: 'No spectrum' } : {
      fin: 'obs_fin2', plot: { data: mode === 'both' ? [trace('final'), trace('continuum')] : [trace('final')],
        layout: { xaxis: {}, yaxis: {}, legend: {} }, config: {} }
    } });
  }
  assert.equal(requests.length, 0); // No eager parsing on page load.
  boxes[0].checked = true; boxes[0].change();
  boxes[1].checked = true; boxes[1].change();
  assert.equal(requests.length, 2); // Pending first request is shared.
  respond(requests[1]); await flush();
  assert.equal(plots.length, 0);
  respond(requests[0]); await flush();
  assert.equal(plots.at(-1).length, 2);
  assert.equal(created, 1);
  assert(plots.at(-1)[0].name.startsWith('grid/a'));
  assert(plots.at(-1)[1].name.startsWith('other/a'));
  assert.notEqual(plots.at(-1)[0].line.color, plots.at(-1)[1].line.color);
  plots.at(-1).forEach(trace => assert.match(trace.uid, /^[a-z0-9-]+$/));
  const color = plots.at(-1)[1].line.color;
  boxes[0].checked = false; boxes[0].change(); await flush();
  assert.equal(plots.at(-1).length, 1);
  assert.equal(plots.at(-1)[0].line.color, color);
  boxes[2].checked = true; boxes[2].change(); respond(requests.at(-1), true); await flush();
  assert.equal(plots.at(-1).length, 1);
  assert.equal(elements['comparison-errors'].children.length, 1);
  assert.equal(elements['comparison-errors'].hidden, false);
  boxes[2].checked = false;
  elements['comparison-mode'].value = 'both'; elements['comparison-mode'].change();
  respond(requests.at(-1)); await flush();
  assert.equal(plots.at(-1).length, 2);
  assert.equal(plots.at(-1)[0].line.color, plots.at(-1)[1].line.color);
  assert.equal(plots.at(-1)[1].line.dash, 'dot');
  assert.match(plots.at(-1)[1].uid, /^[a-z0-9-]+$/);
  assert.equal(elements[target.id + '-yscale'].value, 'log');
  elements['comparison-refresh'].click();
  const pending = requests.at(-1);
  elements['comparison-clear'].click(); await flush();
  respond(pending); await flush();
  assert.equal(plots.at(-1).length, 0); // Late responses cannot restore cleared traces.
  assert.equal(elements['comparison-canvas'].hidden, true);
  assert.equal(created, 1); // No repeated event binding on selection changes.
  boxes[0].row.hidden = true; observer();
  elements['comparison-select-visible'].checked = true;
  elements['comparison-select-visible'].change();
  assert.equal(boxes[0].checked, false);
  assert.equal(boxes[1].checked, true);
  assert.equal(boxes[2].checked, true);
  assert.equal(boxes[3].checked, true);
  requests.slice(-2).forEach(r => respond(r)); await flush();
  assert.equal(plots.at(-1).length, 6);
  console.log('PASS comparison selection, caching, race handling, partial failures, modes, colors, and filtering');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
