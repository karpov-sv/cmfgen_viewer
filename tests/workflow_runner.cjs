const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('cmfgen_viewer/static/workflow_runner.js', 'utf8');

function element() {
  const classes = new Set();
  return {dataset: {}, listeners: {}, classes,
    classList: {
      remove: name => classes.delete(name),
      toggle: (name, on) => on ? classes.add(name) : classes.delete(name),
    },
    addEventListener(name, fn) { this.listeners[name] = fn; },
  };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const snapshot = (active, status = active ? 'running' : 'succeeded') => ({
  job_id: 'job', stages: ['lte'], active, status, status_label: status,
  status_class: 'bg-secondary', can_cancel: active, created_epoch: Date.now() / 1000,
  created_label: 'today', stage_label: 'LTE', sequence_label: 'LTE', progress_label: 'progress',
});

function setup({initialJobs = [], initialActive = true, compact = false, delayHistory = false, stage = 'lte'} = {}) {
  let active = initialActive, unavailable = false, count = 0;
  let releaseHistory;
  const historyReady = new Promise(resolve => {releaseHistory = resolve;});
  const parts = Object.fromEntries(['run', 'error', 'details', 'stop', 'job', 'state', 'stage', 'elapsed', 'output',
    ...(!compact ? ['progress'] : [])
  ].map(name => [name, element()]));
  const panel = element();
  const section = {};
  panel.dataset = {stage, label: stage, model: 'model', runnerUrl: '/run'};
  panel.querySelector = selector => parts[selector.match(/data-inline-(\w+)/)[1]] || null;
  const combined = element();
  combined.dataset = {inlineSequence:'main,flux', inlineToken:'combined-token', inlineLabel:'main + spectra'};
  panel.querySelectorAll = () => stage === 'main' ? [parts.run, combined] : [parts.run];
  panel.closest = () => section;
  const events = [], requests = [], confirmations = [], timers = new Map(), listeners = {};
  const document = {
    hidden: false,
    querySelectorAll: () => [panel],
    addEventListener: (name, fn) => {listeners[name] = fn;},
    dispatchEvent: event => events.push(event),
  };
  vm.runInNewContext(source, {
    document, window: {confirm: message => {confirmations.push(message); return true;}}, Date,
    CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
    FormData: class extends Map {constructor() {super([['stage_sequence',stage], ['start_token','single-token'], ['iterations','3'], ['threads','2']]);}},
    URLSearchParams,
    setTimeout: fn => {timers.set(++count, fn); return count;},
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => {
      requests.push({url, method: options.method || 'GET', body:options.body});
      if (url === '/run') return {ok:true, json:async () => {
        if (options.method === 'POST') return {job_id:'job', status_url:'/runner-jobs/job?format=json'};
        if (delayHistory) await historyReady;
        return {jobs:initialJobs};
      }};
      if (url.includes('/cancel')) return {ok:true, json:async () => ({stopping:true})};
      if (unavailable) throw new Error('Viewer restarting');
      return {ok:true, json:async () => snapshot(active)};
    },
  });
  return {
    parts, combined, events, requests, confirmations, section,
    async restoreHistory() { releaseHistory(); await settle(); },
    set active(value) {active = value;},
    set unavailable(value) {unavailable = value;},
    get pending() {return timers.size;},
    async launch(submitter) {
      await panel.listeners.submit({target:{matches:()=>true}, submitter, preventDefault() {}});
      await settle();
    },
    async tick() {
      const callbacks = [...timers.values()]; timers.clear();
      callbacks.forEach(fn => fn()); await settle();
    },
    async visible(value) {
      document.hidden = !value;
      listeners.visibilitychange(); await settle();
    },
  };
}

(async () => {
  for (const compact of [false, true]) {
    const quick = setup({initialActive:false, compact});
    await settle(); await quick.launch();
    assert.equal(quick.events.length, 1, 'Completion before the first status response must refresh');
    assert.equal(quick.events[0].type, 'cmfgen:runner-finished');
    assert.equal(quick.events[0].detail.stage, 'lte');
    assert.equal(quick.pending, 0, 'Finished jobs stop polling');
    assert.equal(quick.parts.run.disabled, false);
    assert.ok(quick.parts.stop.classes.has('d-none'));
  }
  const running = setup();
  await settle(); await running.launch();
  assert.equal(running.events.length, 0);
  assert.equal(running.pending, 1);
  assert.ok(running.section.open);
  running.unavailable = true;
  await running.tick();
  assert.equal(running.events.length, 0, 'A disconnected viewer is not completion');
  assert.equal(running.pending, 1, 'Reconnect while an active job is saved');
  running.unavailable = false; running.active = false;
  await running.tick();
  assert.equal(running.events.length, 1);
  await running.visible(true);
  assert.equal(running.events.length, 1, 'Do not repeat completion after visibility changes');

  const hidden = setup({initialJobs:[snapshot(true)], compact:true});
  await settle(); await hidden.visible(false);
  hidden.active = false;
  assert.equal(hidden.events.length, 0);
  await hidden.visible(true);
  assert.equal(hidden.events.length, 1, 'Catch completion while the page was hidden');
  assert.equal(hidden.pending, 0);

  const history = setup({initialJobs:[snapshot(false)]});
  await settle();
  assert.equal(history.events.length, 0, 'Old completed jobs must not create reload loops');
  assert.equal(history.pending, 0);

  const slowHistory = setup({initialJobs:[snapshot(false)], delayHistory:true, compact:true});
  await slowHistory.launch();
  await slowHistory.restoreHistory();
  assert.equal(slowHistory.events.length, 0, 'Stale history must not finish a newly launched job');
  assert.equal(slowHistory.pending, 1, 'Keep polling the new job after a delayed history response');
  assert.equal(slowHistory.parts.run.disabled, true);
  assert.ok(!slowHistory.parts.stop.classes.has('d-none'));
  slowHistory.active = false;
  await slowHistory.tick();
  assert.equal(slowHistory.events.length, 1);

  const combined = setup({stage:'main'});
  await settle(); await combined.launch(combined.combined);
  const request = combined.requests.find(r=>r.method==='POST');
  assert.equal(request.body.get('stage_sequence'), 'main,flux');
  assert.equal(request.body.get('start_token'), 'combined-token');
  assert.equal(request.body.get('iterations'), '3');
  assert.match(combined.confirmations[0], /Start main \+ spectra/);
  assert.ok(combined.parts.run.disabled && combined.combined.disabled);
  combined.active = false;
  await combined.tick();
  assert.ok(!combined.parts.run.disabled && !combined.combined.disabled);
  console.log('Workflow runner completion checks passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
