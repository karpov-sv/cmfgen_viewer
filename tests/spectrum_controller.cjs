/* Exercise shared control wiring and trace ownership without a browser/CDN. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const transforms = require('../cmfgen_viewer/static/spectrum_transforms.js');

async function check(mode) {
  const elements = new Map();
  function element(id, value = '') {
    const listeners = {};
    const classes = new Set();
    const el = {
      value, open: false, textContent: '',
      classList: { toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); } },
      addEventListener(name, fn) { listeners[name] = fn; },
      dispatch(name) { listeners[name]?.(); },
      classes
    };
    elements.set(id, el);
    return el;
  }
  const config = { plot_id: 'test', mode };
  element('test');
  for (const [name, value] of Object.entries({
    redshift: '0', velocity: '0', broadening: '0', ebv: '0', distance: '1',
    reset_transform: '', transform_hint: '', x_scale: 'linear', y_scale: 'linear'
  })) {
    config[name + '_id'] = name;
    element(name, value);
  }
  const settings = element('test-transforms');
  const baseData = [
    { x: [4900, 5000, 5100], y: [1, 0.2, 1] },
    { x: [4900, 5000, 5100], y: [1, 1, 1] },
    { x: [4900, 5000, 5100], y: [2, 3, 2] }
  ];
  const original = JSON.stringify(baseData);
  const targets = ['model', 'model', 'observed'];
  let series;
  let frame;
  const sampling = { setSeries(x, y) { series = { x, y }; } };
  const context = {
    document: { getElementById(id) { return elements.get(id); } },
    CmfgenSpectrumTransforms: transforms,
    CmfgenSpectrumControls: { createPlot() { return { sampling, ready: Promise.resolve() }; } }
  };
  context.window = {
    requestAnimationFrame(fn) { frame = fn; return 1; },
    cancelAnimationFrame() { frame = null; }
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    '../cmfgen_viewer/static/spectrum_viewer.js'), 'utf8'), context);
  const viewer = context.window.CmfgenSpectrumViewer.create(config, {
    baseData, transformTargets: targets, shouldBroaden(index) { return index === 0; }
  });
  await viewer.ready;
  function flush() { const next = frame; frame = null; next?.(); }
  flush();
  const get = name => elements.get(name);
  get('velocity').value = '120';
  get('velocity').dispatch('input');
  assert(Math.abs(Number(get('redshift').value) - 120 / 299792.458) < 1e-10);
  get('broadening').value = '10000';
  get('broadening').dispatch('input');
  get('ebv').value = '0.2';
  get('distance').value = '2';
  flush();
  for (let index = 0; index < 2; index++) {
    const expected = transforms.transformSeries(baseData[index].x, baseData[index].y, {
      mode, redshift: Number(get('redshift').value), ebv: 0.2, distance_kpc: 2,
      broadening_km_s: index === 0 ? 10000 : 0
    });
    assert.deepEqual(Array.from(series.x[index]), expected[0]);
    assert.deepEqual(Array.from(series.y[index]), expected[1]);
  }
  assert.deepEqual(Array.from(series.x[2]), baseData[2].x);
  assert.deepEqual(Array.from(series.y[2]), baseData[2].y);
  assert.equal(JSON.stringify(baseData), original, 'Native trace arrays must remain intact');

  const validSeries = JSON.stringify(series);
  get('distance').value = '0';
  get('distance').dispatch('input');
  flush();
  assert.equal(JSON.stringify(series), validSeries, 'Invalid input must not replace plotted data');
  assert(settings.open, 'Validation errors must reveal collapsed settings');
  assert(get('transform_hint').classes.has('text-danger'));
  get('reset_transform').dispatch('click');
  flush();
  assert.equal(get('redshift').value, '0');
  assert.equal(get('velocity').value, '0');
  assert.equal(get('distance').value, '1');
  assert(!get('transform_hint').classes.has('text-danger'));

  // Grid-fit adapters mutate their trace arrays after plot initialization.
  baseData.push({ x: [5000, 5100], y: [4, 5] });
  targets.push('observed');
  viewer.scheduleTransforms();
  flush();
  assert.deepEqual(Array.from(series.y[3]), [4, 5]);
}

Promise.all(['both', 'normalized'].map(check)).catch(error => {
  console.error(error);
  process.exitCode = 1;
});
