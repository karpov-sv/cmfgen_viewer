const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('cmfgen_viewer/static/model_runtime.js', 'utf8');

class Element {
  constructor() {
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.textContent = '';
    this.listeners = {};
    this.classes = new Set();
    this.classList = {toggle: (name, on) => on ? this.classes.add(name) : this.classes.delete(name)};
  }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  closest() { return null; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  querySelector(selector) {
    this.parts ||= {};
    return this.parts[selector] ||= new Element();
  }
}

function setup(initiallyActive = [false], fields = [], summaries = [], href = 'http://localhost/workflow') {
  fields.forEach(field => { field.closest ||= () => null; });
  const monitors = initiallyActive.map((active, index) => {
    const monitor = new Element();
    monitor.dataset = {runtimeActive: String(active), runtimeKey: String(index)};
    return monitor;
  });
  const subscriptions = new Map();
  const events = new Map();
  const timers = [];
  let reloads = 0;
  vm.runInNewContext(source, {
    document: {
      querySelectorAll: selector => selector === '[data-model-runtime-url]' ? monitors
        : selector === '[data-workflow-runtime-summary]' ? summaries
        : selector.startsWith('.workflow-page form') ? fields : [],
      createElement: () => new Element(),
      createTextNode: text => ({textContent: text}),
      addEventListener: (name, callback) => events.set(name, callback),
    },
    window: {
      CmfgenLiveUpdates: {subscribe: (key, callback) => subscriptions.set(key, callback)},
      setTimeout: callback => { timers.push(callback); return timers.length; },
      location: {href, replace: url => {
        assert.equal(url, href.split('#')[0]);
        reloads++;
      }},
    },
  });
  return {
    monitors,
    finish(stage) { events.get('cmfgen:runner-finished')({detail: {stage}}); },
    update(active, available = true, index = 0, phase = 'CMFGEN', diagnostics, extra = {}) {
      subscriptions.get('runtime:' + index)({active, monitoring_available: available, phase_label: phase, diagnostics, ...extra});
    },
    flush() { while (timers.length) timers.shift()(); },
    get pending() { return timers.length; },
    get reloads() { return reloads; },
  };
}

const idle = setup();
idle.update(false);
idle.update(false);
assert.equal(idle.pending, 0, 'Idle snapshots must not reload the page');
idle.update(true);
idle.update(true, true, 0, 'CMF_FLUX');
assert.equal(idle.pending, 0, 'Changing running phases must not reload');
idle.update(false);
idle.update(false);
assert.equal(idle.pending, 1, 'Completion must schedule exactly one refresh');
idle.flush();
assert.equal(idle.reloads, 1);

const loadedActive = setup([true]);
loadedActive.update(false);
loadedActive.flush();
assert.equal(loadedActive.reloads, 1, 'Detect completion before the first live snapshot');

const denied = setup([true]);
denied.update(false, false);
assert.equal(denied.pending, 0, 'Unavailable monitoring is not completion');
denied.update(false, true);
denied.flush();
assert.equal(denied.reloads, 1, 'Remember the run across a monitoring interruption');

const simultaneous = setup([true, true]);
simultaneous.update(false, true, 0);
simultaneous.update(false, true, 1);
assert.equal(simultaneous.pending, 1, 'Coalesce multiple monitors');
simultaneous.flush();
assert.equal(simultaneous.reloads, 1);

const runner = setup();
runner.finish('lte');
runner.finish('hydro');
assert.equal(runner.pending, 1, 'Coalesce runner completion notifications');
runner.flush();
assert.equal(runner.reloads, 1, 'Refresh on runner completion even without observed native activity');

for (const anchor of ['lte-run', 'hydro-run', 'result-review']) {
  const anchored = setup([true], [], [], `http://localhost/workflow?file=VADAT#${anchor}`);
  anchored.update(false);
  anchored.flush();
  assert.equal(anchored.reloads, 1, 'Stage links must refresh HTML rather than navigate to a fragment');
}

const both = setup([true]);
both.update(false);
both.finish('main');
assert.equal(both.pending, 1, 'Native and runner completion must share one refresh');
both.flush();
assert.equal(both.reloads, 1);

const hydroField = {tagName: 'INPUT', type: 'text', value: '10'};
const hydroEditing = setup([false, false], [hydroField]);
hydroEditing.monitors[0].dataset.runtimeKey = 'lte:model';
hydroEditing.monitors[1].dataset.runtimeKey = 'hydro:model';
const hydroSection = {open: false};
hydroEditing.monitors[1].closest = () => hydroSection;
hydroField.value = '20';
hydroEditing.finish('hydro');
hydroEditing.flush();
assert.equal(hydroEditing.reloads, 0, 'Runner completion must preserve unsaved control edits');
assert.equal(hydroEditing.monitors[0].children.length, 0, 'Show the notice on the completed stage');
assert.equal(hydroEditing.monitors[1].children.at(-1).children.at(-1).textContent, 'Refresh results');
assert.ok(hydroSection.open, 'Reveal the unsaved-edit notice even if the stage was collapsed');

const runnerField = {tagName: 'INPUT', type: 'text', value: '10', closest: () => ({})};
const settingsOnly = setup([false], [runnerField]);
runnerField.value = '20';
settingsOnly.finish('lte');
settingsOnly.flush();
assert.equal(settingsOnly.reloads, 1, 'Run options must not block refreshing model results');

for (const field of [
  {tagName: 'INPUT', type: 'text', value: '10'},
  {tagName: 'INPUT', type: 'checkbox', checked: false},
  {tagName: 'SELECT', options: [{selected: true}, {selected: false}]},
]) {
  const editing = setup([true], [field]);
  if (field.tagName === 'SELECT') field.options[0].selected = false;
  else if (field.type === 'checkbox') field.checked = true;
  else field.value = '20';
  editing.update(false);
  editing.flush();
  assert.equal(editing.reloads, 0, 'Retain unsaved form edits');
  const notice = editing.monitors[0].children.at(-1);
  const button = notice.children.at(-1);
  assert.equal(button.textContent, 'Refresh results');
  button.listeners.click();
  assert.equal(editing.reloads, 1, 'Allow manual refresh with unsaved edits');
}
console.log('Workflow completion refresh checks passed.');

const compact = setup();
compact.monitors[0].dataset.runtimeCompact = 'true';
compact.update(false);
assert.ok(compact.monitors[0].classes.has('runtime-idle'));
compact.update(true);
assert.ok(!compact.monitors[0].classes.has('runtime-idle'));
compact.update(false, false);
assert.ok(!compact.monitors[0].classes.has('runtime-idle'), 'Keep unavailable monitoring visible');

const summary = new Element();
summary.dataset = {workflowRuntimeSummary: '0', workflowOutputReady: 'true'};
const output = setup([false], [], [summary]);
output.update(false, true, 0, 'LTE', []);
assert.equal(summary.textContent, 'Output ready · not running');
assert.equal(summary.className, 'badge bg-success');
output.update(true, true, 0, 'LTE', [{status: 'running'}]);
assert.equal(summary.textContent, 'Running now · LTE');
output.update(false, false, 0, 'LTE', []);
assert.equal(summary.textContent, 'Output ready · monitoring unavailable');
assert.equal(summary.className, 'badge bg-secondary');
summary.dataset.workflowOutputReady = 'false';
output.update(false, true, 0, 'LTE', []);
assert.equal(summary.textContent, 'Not running');

const counter = setup();
counter.update(false, true, 0, 'LTE', [{status: 'ready'}], {
  kind: 'lte', progress: {label: 'LTE frequency integration', percent: 99.3,
    detail: 'Frequency 118,000 of 118,866', metrics: []},
});
const heading = counter.monitors[0].parts['[data-runtime-progress]'].children[0].children[0].children[0];
assert.equal(heading.textContent, 'Last logged LTE frequency counter: ');
