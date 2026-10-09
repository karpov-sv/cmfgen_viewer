const assert = require('node:assert/strict');
const sampling = require('../cmfgen_viewer/static/spectrum_sampling.js');
const transforms = require('../cmfgen_viewer/static/spectrum_transforms.js');

async function main() {
  const x = Array.from({length: 40001}, (_, i) => 3000 + i / 10);
  const y = x.map(() => 1);
  y[20003] = 0.01;
  y[20007] = 10;
  const trace = {mode: 'lines', x, y, line: {color: 'red'},
    error_y: {array: x.map((_, i) => i / 100000), arrayminus: x.map((_, i) => i / 200000), symmetric: false},
    text: x.map((_, i) => 'sample ' + i), customdata: x.map((_, i) => [i, -i])};
  const original = JSON.stringify(trace);
  for (const log of [false, true]) {
    const overview = sampling.sampleTrace(trace, null, log, 5000, false);
    assert(overview.x.length <= 5000 && overview.x.length < x.length);
    assert(overview.y.includes(0.01) && overview.y.includes(10));
    assert.equal(overview.x[0], x[0]);
    assert.equal(overview.x.at(-1), x.at(-1));
    assert.equal(overview.line.simplify, false);
    for (let i = 0; i < overview.x.length; i++) {
      const index = overview.customdata[i][0];
      assert.equal(overview.x[i], x[index]);
      assert.equal(overview.y[i], y[index]);
      assert.equal(overview.error_y.array[i], trace.error_y.array[index]);
      assert.equal(overview.error_y.arrayminus[i], trace.error_y.arrayminus[index]);
      assert.equal(overview.text[i], trace.text[index]);
    }
    for (const descending of [false, true]) {
      const source = descending ? {mode: 'lines', x: x.toReversed(), y: y.toReversed()} : trace;
      const detail = sampling.sampleTrace(source, [5010, 4990], log, 5000, false);
      assert.equal(detail.x.length, 205); // Native window plus crossing neighbours.
      assert(detail.y.includes(0.01) && detail.y.includes(10));
      for (let i = 1; i < detail.x.length; i++) {
        assert(Math.abs(Math.abs(detail.x[i] - detail.x[i - 1]) - 0.1) < 1e-9);
      }
    }
  }
  assert.equal(JSON.stringify(trace), original);
  const uncertain = {...trace, error_y: {...trace.error_y, array: trace.error_y.array.slice()}};
  uncertain.error_y.array[20009] = 100;
  assert(sampling.sampleTrace(uncertain, null, true, 5000, false).x.includes(x[20009]));
  assert.deepEqual(sampling.sampleTrace(trace, null, true, 5000, true).x, x);
  assert.equal(sampling.sampleTrace(trace, [8000, 9000], false, 5000, false).x.length, 0);
  assert.equal(sampling.sampleTrace({x: [1], y: [2]}, [5, 6], false, 5000, false).x.length, 0);
  assert.deepEqual(sampling.sampleTrace({x: [4000, 6000], y: [1, 2]}, [4900, 5100], true, 5000, false).x, [4000, 6000]);
  const gaps = {...trace, y: y.slice()};
  gaps.y[20004] = null;
  const overview = sampling.sampleTrace(gaps, null, true, 5000, false);
  assert(overview.x.includes(x[20004]) && overview.x.includes(x[20005]));
  assert.equal(overview.y[overview.x.indexOf(x[20004])], null);
  const photometry = {mode: 'markers', x: [4500, 6500], y: [1, 2], error_x: {array: [1000, 1000]}};
  assert.deepEqual(sampling.sampleTrace(photometry, [4900, 5100], false, 1, false).x, photometry.x);

  // Exercise controller events and async redraws without a browser. Sources
  // stay native through zoom, redshift/broadening, visibility, and reset.
  const controls = {};
  const frames = [];
  global.window = {requestAnimationFrame: callback => { frames.push(callback); return frames.length; }};
  global.document = {getElementById: id => controls[id] || null};
  const handlers = {};
  const target = {id: 'spectrum', layout: {xaxis: {type: 'log', autorange: true}},
    _fullLayout: {xaxis: {type: 'log', range: [Math.log10(3000), Math.log10(7000)]}},
    on: (event, callback) => { handlers[event] = callback; }};
  let modeChanged;
  controls['spectrum-sampling'] = {value: 'adaptive', addEventListener: (_, callback) => {modeChanged = callback;}};
  controls['spectrum-sampling-status'] = {textContent: ''};
  global.Plotly = {
    restyle: async (plot, update) => {
      for (let index = 0; index < plot.data.length; index++) {
        for (const [key, values] of Object.entries(update)) {
          const path = key.split('.');
          const value = Array.isArray(values) ? values[index] : values;
          if (path.length === 1) plot.data[index][key] = value;
          else {
            plot.data[index][path[0]] ||= {};
            plot.data[index][path[0]][path[1]] = value;
          }
        }
      }
      handlers.plotly_restyle?.(update);
    },
    relayout: async (plot, update) => {
      assert.equal(update['xaxis.autorange'], true);
      plot.layout.xaxis.autorange = true;
      plot._fullLayout.xaxis.range = [Math.log10(Math.min(...plot.data[0].x)), Math.log10(Math.max(...plot.data[0].x))];
      handlers.plotly_relayout(update);
    }
  };
  const controller = sampling.create(target, [trace], target.layout);
  target.data = controller.initialData;
  controller.bind();
  assert(controller.getSources()[0].x.length === x.length);
  assert(controls['spectrum-sampling-status'].textContent.includes('40,001 native'));
  async function flush() {
    while (frames.length) frames.shift()();
    await controller.render();
    await new Promise(resolve => setImmediate(resolve));
  }
  target.layout.xaxis.autorange = false;
  target._fullLayout.xaxis.range = [Math.log10(4990), Math.log10(5010)];
  handlers.plotly_relayout({'xaxis.range': target._fullLayout.xaxis.range});
  await flush();
  assert(target.data[0].x.length < 210 && target.data[0].y.includes(0.01));
  assert.equal(controller.getSources()[0].x.length, 40001);
  // Broadening uses the complete native interval before any viewport crop.
  const broadened = transforms.transformSeries(x, y, {mode: 'normalized', redshift: 0.01, broadening_km_s: 60});
  await controller.setSeries([broadened[0]], [broadened[1]]);
  const nativeSources = controller.getSources();
  assert.deepEqual(nativeSources[0].y, broadened[1]);
  for (let i = 0; i < target.data[0].x.length; i++) {
    const sourceIndex = nativeSources[0].x.indexOf(target.data[0].x[i]);
    assert.equal(target.data[0].y[i], broadened[1][sourceIndex]);
  }
  target.data[0].visible = 'legendonly';
  await controller.render();
  assert.equal(target.data[0].visible, 'legendonly');
  assert.equal(controller.getSources()[0].visible, 'legendonly');
  target.data[0].visible = true;
  target.layout.xaxis.autorange = true;
  handlers.plotly_relayout({'xaxis.autorange': true});
  await flush();
  assert(Math.abs(Math.pow(10, target._fullLayout.xaxis.range[0]) - x[0] * 1.01) < 1e-8);
  assert(Math.abs(Math.pow(10, target._fullLayout.xaxis.range[1]) - x.at(-1) * 1.01) < 1e-8);
  controls['spectrum-sampling'].value = 'native';
  modeChanged();
  await flush();
  assert.equal(target.data[0].x.length, x.length);
  target.data.push(controller.appendTrace({mode: 'lines', x, y, name: 'fit'}));
  await controller.render();
  assert.equal(target.data[1].x.length, x.length);
  controller.replaceTrace(1, {mode: 'lines', x: [4000, 5000, 6000], y: [2, 3, 4]});
  await controller.render();
  assert.deepEqual(target.data[1].y, [2, 3, 4]);
  controller.removeTrace(1);
  target.data.splice(1, 1);
  await controller.render();
  assert.equal(controller.getSources().length, 1);

  // Quick zoom coverage and vertical ranges must use native transformed data,
  // even when Plotly currently contains only a cropped, reduced display.
  class Element {
    constructor(value = '') { this.value = value; this.children = []; this.handlers = {}; this.checked = false; }
    addEventListener(name, callback) { this.handlers[name] = callback; }
    appendChild(child) { this.children.push(child); }
    querySelector() { return this.children[0]; }
  }
  for (const name of ['show', 'group', 'medium', 'labels', 'zoom']) controls['spectrum-lines-' + name] = new Element();
  controls['spectrum-lines-group'].value = 'all';
  controls['spectrum-lines-medium'].value = 'vacuum';
  const zoom = controls['spectrum-lines-zoom'];
  zoom.appendChild(new Element('full'));
  global.document.createElement = () => new Element();
  const fixture = {mode:'lines', x:[4000,6400,6500,6600,6750,7000], y:[1e6,2,2,4,4,1e6],
    error_y:{type:'data',visible:true,symmetric:false,array:[0,0,.5,3,0,0],arrayminus:[0,0,1,.5,0,0]}};
  controller.replaceTrace(0, fixture);
  target.data = [{mode:'lines', x:[6500,6600], y:[2,4]}];
  target.layout = {xaxis:{type:'linear',autorange:false}, yaxis:{type:'linear'}};
  target._fullLayout = {xaxis:{type:'linear',range:[6500,6600],_length:800}, yaxis:{type:'linear',range:[0,1e6]}};
  global.Plotly.relayout = async (plot, update) => {
    for (const [key, value] of Object.entries(update)) {
      const [axis, property] = key.split('.');
      if (property) {
        plot.layout[axis][property] = value;
        plot._fullLayout[axis][property] = value;
      } else plot.layout[key] = value;
    }
  };
  require('../cmfgen_viewer/static/spectral_lines.js');
  window.CmfgenSpectralLines.bind(target);
  while (frames.length) frames.shift()();
  const hAlpha = zoom.children.flatMap(group => group.children).find(option => option.textContent.startsWith('Hα'));
  assert.equal(hAlpha.disabled, false, 'Line outside the cropped display stays available');
  zoom.value = hAlpha.value;
  zoom.handlers.change();
  assert.deepEqual(target._fullLayout.yaxis.range, [0.7,7.3]);
  zoom.value = 'full';
  zoom.handlers.change();
  assert.deepEqual(target._fullLayout.xaxis.range, [4000,7000]);
  assert.deepEqual(controller.getSources()[0].y, fixture.y);
  console.log('Native spectrum sampling, aligned uncertainties, transforms, zoom/reset, visibility, and overlays passed.');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
