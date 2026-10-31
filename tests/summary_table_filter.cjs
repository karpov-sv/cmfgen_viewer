const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
  constructor(value = '') {
    this.value = value; this.handlers = {}; this.dataset = {}; this.hidden = false;
    this.classList = {contains: () => false, add() {}, remove() {}, toggle() {}};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  querySelector() { return null; }
  closest() { return null; }
  focus() { this.focused = true; }
  on(name, fn) { this.handlers[name] = fn; }
}
const ids = ['summary-table', 'summary-name-filter', 'summary-name-filter-clear',
  'summary-name-filter-status', 'summary-no-matches', 'summary-scatter-plot',
  'summary-scatter-plot-xcol', 'summary-scatter-plot-ycol',
  'summary-scatter-plot-xscale', 'summary-scatter-plot-yscale',
  'summary-scatter-plot-selection-clear', 'summary-scatter-plot-selection-status'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
const rows = ['Bstar3000', 'Bstar3100', '[He].star', 'Other'].map((name, i) => {
  const row = new Element();
  row.dataset = {col0: name, col1: String(i + 1), col2: String(30000 + i * 1000),
    modelPath: (i === 3 ? 'archive/' : 'grid/') + name, modelUrl: '/view/' + name};
  row.checked = true; // Filtering must not modify comparison selections.
  return row;
});
const headers = ['MODEL', 'LSTAR', 'T_*'].map((label, i) => {
  const header = new Element(); header.dataset = {column: String(i), label, type: i ? 'number' : 'string'};
  return header;
});
const table = elements['summary-table'];
table.tBodies = [{querySelectorAll: () => rows, appendChild() {}}];
table.querySelectorAll = () => headers;
elements['summary-scatter-plot-xcol'].value = '2';
elements['summary-scatter-plot-ycol'].value = '1';
const plot = elements['summary-scatter-plot'];
const Plotly = {
  react(target, data) { target.data = data; },
  update() {}, restyle() {}
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../cmfgen_viewer/static/summary_table.js'), 'utf8'), {
  document: {getElementById: id => elements[id] || null,
    createDocumentFragment: () => ({appendChild() {}})},
  window: {Plotly}, Plotly
});
const field = elements['summary-name-filter'];
function filter(pattern) { field.value = pattern; field.handlers.input(); }
function visible() { return rows.filter(row => !row.hidden).map(row => row.dataset.col0); }
assert.equal(visible().length, 4);
filter('bstar'); assert.deepEqual(visible(), ['Bstar3000', 'Bstar3100']);
filter('Bstar?1*'); assert.deepEqual(visible(), ['Bstar3100']);
filter('archive/*'); assert.deepEqual(visible(), ['Other']);
filter('[he].'); assert.deepEqual(visible(), ['[He].star']); // Regex punctuation stays literal.
filter('missing'); assert.equal(visible().length, 0);
assert.equal(elements['summary-no-matches'].hidden, false);
assert.equal(elements['summary-name-filter-status'].textContent, '0 of 4 models shown');
filter('  '); assert.equal(visible().length, 4);
filter('Bstar*');
plot.handlers.plotly_selected({points: [{customdata: [1, '/view/Bstar3100']}, {customdata: [2, '/view/[He].star']}]});
assert.deepEqual(visible(), ['Bstar3100']);
headers[1].handlers.click(); // Sorting preserves the intersected filters and row identity.
assert.deepEqual(visible(), ['Bstar3100']);
elements['summary-scatter-plot-selection-clear'].handlers.click();
assert.deepEqual(visible(), ['Bstar3000', 'Bstar3100']);
plot.handlers.plotly_selected({points: [{customdata: [1, '/view/Bstar3100']}]});
elements['summary-name-filter-clear'].handlers.click();
assert.deepEqual(visible(), ['Bstar3100']); // Clear name leaves the plot filter active.
assert.equal(field.focused, true);
plot.handlers.plotly_deselect();
assert.equal(visible().length, 4);
filter('no-match');
field.handlers.keydown({key: 'Escape', preventDefault() {}});
assert.equal(visible().length, 4);
assert.equal(elements['summary-name-filter-clear'].disabled, true);
assert(rows.every(row => row.checked));
console.log('PASS model name/path filtering, wildcards, literals, counts, sorting, combined filters, and clear/Escape');
