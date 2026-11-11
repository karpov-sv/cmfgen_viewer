const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../cmfgen_viewer/static/diagnostic_plots.js'), 'utf8'), {window});
const observed = [{x:[99,100,101,102,103],y:[9,1,.5,1,9]}];
const model = {x:[98,100.5,101.5,104], y:[20,.8,.8,20]};
const original = JSON.stringify({observed,model});
const result = window.CmfgenDiagnosticPlots.windowPlot({min:100,max:102}, observed, model, 'air',
  [{min:101.8,max:103},{min:95,max:99}],
  [{wavelength:101,label:'<He I>',color:'#123'},{wavelength:105,label:'Outside'}], 'normalized');
assert.deepEqual(Array.from(result.data[0].x), [100,101,102]);
assert.deepEqual(Array.from(result.data[1].x), [98,100.5,101.5,104]);
assert.deepEqual(Array.from(result.layout.xaxis.range), [100,102]);
assert.equal(result.layout.shapes.length,2);
assert.equal(result.layout.shapes[0].x0,101.8);
assert.equal(result.layout.shapes[0].x1,102);
assert.equal(result.layout.shapes[1].x0,101);
assert.equal(result.layout.annotations[0].text,'&lt;He I&gt;');
assert(result.layout.yaxis.range[1]<2, 'Model neighbors outside the window must not set the vertical range');
assert.equal(JSON.stringify({observed,model}),original, 'Plotting must preserve native data');
const vacuum = window.CmfgenDiagnosticPlots.windowPlot({min:100,max:102}, observed, model, 'vacuum', [], [], 'both');
assert(vacuum.layout.xaxis.title.text.includes('vacuum'));
assert.equal(vacuum.layout.yaxis.title.text,'Flux');
assert.equal(vacuum.data[0].x.length,3, 'Keep every native observed sample in the interval');
console.log('PASS diagnostic plots preserve native samples, include model neighbors, clip exclusions and markers, and escape labels');
