const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = {}, frames = [], storage = new Map(), listeners = {};
class Element {
  constructor(value = '') { this.value = value; this.children = []; this.handlers = {}; this.checked = false; this.attrs = {}; this.classes = {}; this.classList = {toggle: (name, value) => {this.classes[name] = value;}}; }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  appendChild(child) { this.children.push(child); child.parent = this; }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  setAttribute(key, value) { this.attrs[key] = value; }
  querySelector() { return this.children.find(child => child.value === 'full'); }
}
const window = {
  localStorage: {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)},
  addEventListener(name, fn) { (listeners[name] ||= []).push(fn); },
  dispatchEvent(event) { (listeners[event.type] || []).forEach(fn => fn(event)); },
  requestAnimationFrame(fn) { frames.push(fn); return frames.length; }
};
const Plotly = { relayout(target, update) {
  for (const [key, value] of Object.entries(update)) {
    if (key.includes('.')) { const [axis, property] = key.split('.'); target.layout[axis][property] = value; target._fullLayout[axis][property] = value; }
    else target.layout[key] = value;
  }
  return Promise.resolve();
}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../cmfgen_viewer/static/spectral_lines.js'), 'utf8'), {
  window, document: {getElementById: id => elements[id] || null, createElement: () => new Element()}, Plotly,
  CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } }
});
const api = window.CmfgenSpectralLines;
let parsed = api.parseCustomLines('# comment\n5000 Label with spaces\n6.0D3, Comma label\n7000\n-1 bad\nInfinity bad\n3foo\n0\n', 'vacuum');
assert.equal(parsed.lines.length, 3);
assert.equal(parsed.lines[0].label, 'Label with spaces');
assert.equal(parsed.lines[1].vacuum, 6000);
assert.equal(parsed.lines[2].label, '7000 Å');
assert.deepEqual(Array.from(parsed.invalidRows), [5,6,7,8]);
const air = api.parseCustomLines('6562.8 Halpha\n1215.67 Lyalpha', 'air').lines;
assert(Math.abs(air[0].air - 6562.8) < 1e-8);
assert(air[0].vacuum > 6564);
const reference = api.referenceLines('air', 0.01).find(line => line.label === 'Hα');
assert(reference.wavelength > 6628 && reference.wavelength < 6629);
assert.equal(api.parseCustomLines('6562.8 Halpha').lines[0].vacuum, air[0].vacuum);
assert.equal(air[1].vacuum, 1215.67); // UV input stays vacuum.
assert.equal(api.parseCustomLines('1e309\n1e-999\nNaN\n1e3junk', 'air').lines.length, 0);

function setup(id) {
  for (const name of ['show','group','medium','labels','zoom','zoom-width','custom','custom-medium','custom-status']) elements[id + '-lines-' + name] = new Element();
  const get = name => elements[id + '-lines-' + name];
  elements[id + '-telluric-show'] = new Element();
  get('show').checked = get('labels').checked = true;
  get('group').value = 'custom'; get('medium').value = 'vacuum'; get('custom-medium').value = 'vacuum';
  get('zoom').appendChild(new Element('full'));
  const target = {id, layout: {shapes: [{name:'fit-bound'}], annotations: [{name:'other'}], xaxis: {}, yaxis: {}},
    _fullLayout: {xaxis: {type:'linear', range:[4000,7000], _length:1000}, yaxis: {type:'linear',range:[0,3]}},
    data: [{x:[1000,4000,5000,6000,7000,8000],y:[1,2,1,2,1,2]}], handlers: {},
    on(name, handler) { this.handlers[name] = handler; }};
  const redshift = {value:'0.01'};
  api.bind(target, {redshiftInput:redshift});
  return {target,get,redshift};
}
function flush() { let count=0; while(frames.length) { frames.shift()(); assert(++count < 50, 'No refresh loop'); } }
const first = setup('first'); flush();
function updateWindows(text, plotId='first') {
  window.dispatchEvent({type:'cmfgen:diagnostic-windows-changed',detail:{plotId,text}});
  flush();
}
function diagnosticGroup() { return first.get('zoom').children.find(child => child.label === 'Diagnostic windows'); }
updateWindows('He I, 4450, 4490\n4920, 4930\nOutside, 9000, 9100\nIncomplete, 4500\nBad, 5, 4\n, 5, 10');
assert.equal(diagnosticGroup().children.length,3);
assert.equal(diagnosticGroup().children[0].textContent,'He I · 4450–4490 Å');
assert.equal(diagnosticGroup().children[2].disabled,true);
first.get('zoom-width').value='10';
first.target.__spectrumDisplayRedshift=.01;
first.get('zoom').value='diagnostic-0'; first.get('zoom').handlers.change();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range),[4450,4490], 'Diagnostic bounds ignore line width and stellar redshift');
first.target._fullLayout.xaxis.type='log';
first.get('zoom').value='diagnostic-1'; first.get('zoom').handlers.change();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range),[Math.log10(4920),Math.log10(4930)]);
updateWindows('Changed, 4500, 4550');
assert.equal(diagnosticGroup().children.length,1);
updateWindows('Other plot, 5000, 5100','other');
assert.equal(diagnosticGroup().children[0].textContent,'Changed · 4500–4550 Å');
updateWindows('');
assert.equal(diagnosticGroup(),undefined);
first.target._fullLayout.xaxis.type='linear'; first.target._fullLayout.xaxis.range=[4000,7000];
first.target.__spectrumDisplayRedshift=0; first.get('zoom-width').value='';
assert.equal(first.get('custom-medium').value, 'air', 'New custom lists default to air');
first.get('custom-medium').value = 'vacuum'; first.get('custom-medium').handlers.change(); flush();
first.get('custom').value = '5000 My line\n6000, <b>Custom</b>\n-1 invalid';
first.get('custom').handlers.input(); flush();
assert.equal(first.get('custom').attrs['aria-invalid'], 'true');
assert(first.get('custom-status').textContent.includes('Ignored invalid rows: 3'));
const markers = () => first.target.layout.shapes.filter(shape => shape.name === 'cmfgen-spectral-line');
assert.deepEqual(markers().map(shape => shape.x0), [5000,6000]);
const zoomText = first.get('zoom').children.flatMap(group => group.children || []).map(option => option.textContent);
first.target.__spectrumDisplayRedshift = 0.01;
first.target.handlers.plotly_afterplot(); flush();
assert.deepEqual(markers().map(shape => shape.x0), [5050,6060], 'Stellar predictions follow source redshift');
assert.notDeepEqual(first.get('zoom').children.flatMap(group => group.children || []).map(option => option.textContent), zoomText);
first.target.__spectrumDisplayRedshift = 0; first.target.handlers.plotly_afterplot(); flush();
assert(first.target.layout.shapes.some(shape => shape.name === 'fit-bound'));
assert(first.target.layout.annotations.some(note => note.name === 'other'));
assert(first.target.layout.annotations.some(note => note.text === '&lt;b&gt;Custom&lt;/b&gt;'));
let customGroup = first.get('zoom').children.find(child => child.label === 'Custom lines');
assert.equal(customGroup.children.length, 2);
first.get('zoom').value = customGroup.children[0].value;
first.get('zoom').handlers.change();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [4850,5150]);
function jumpCustom() {
  first.get('zoom').value = customGroup.children[0].value;
  first.get('zoom').handlers.change();
}
first.get('zoom-width').value = '40'; jumpCustom();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [4980,5020]);
first.target._fullLayout.xaxis.type = 'log'; jumpCustom();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [Math.log10(4980),Math.log10(5020)]);
first.target._fullLayout.xaxis.type = 'linear';
first.get('zoom-width').value = '-10'; jumpCustom();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [Math.log10(4980),Math.log10(5020)], 'Invalid width leaves range unchanged');
first.get('zoom-width').value = ''; jumpCustom();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [4850,5150], 'Blank width uses 300 Å');
first.get('zoom-width').value = '40';
first.get('zoom').value = 'optical'; first.get('zoom').handlers.change();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [3800,7500], 'Width does not change range presets');
first.target._fullLayout.xaxis.range = [4000,7000];
first.get('group').value = 'hydrogen'; first.get('group').handlers.change(); flush();
assert(!markers().some(shape => shape.x0 === 5000));
first.get('group').value = 'all'; first.get('group').handlers.change(); flush();
assert(markers().some(shape => shape.x0 === 5000));
const second = setup('second'); flush();
assert.equal(second.get('custom').value, first.get('custom').value); // Reuse saved browser lines.
first.get('custom-medium').value = 'air'; first.get('custom-medium').handlers.change(); flush();
assert.equal(second.get('custom-medium').value, 'air'); // Other plots update in place.
assert(markers().some(shape => shape.x0 > 5000 && shape.x0 < 5002));
first.get('custom').value = ''; first.get('custom').handlers.input(); flush();
assert.equal(second.get('custom').value, '');
assert.equal(first.get('custom').attrs['aria-invalid'], 'false');
assert(!first.get('zoom').children.some(child => child.label === 'Custom lines'));
first.get('group').value = 'custom'; first.get('group').handlers.change(); flush();
assert.equal(markers().length, 0);
storage.set('cmfgen-custom-spectral-lines-v1', JSON.stringify({text:'5100 From another tab',medium:'vacuum'}));
window.dispatchEvent({type:'storage',key:'cmfgen-custom-spectral-lines-v1'}); flush();
assert.equal(first.get('custom').value, '5100 From another tab');
assert.equal(second.get('custom').value, '5100 From another tab');
assert(markers().some(shape => shape.x0 === 5100));

// Telluric bands can be toggled independently and share the observer-to-rest correction.
const telluric = elements['first-telluric-show'];
const bands = () => first.target.layout.shapes.filter(shape => shape.name === 'cmfgen-telluric-band');
const bandNotes = () => first.target.layout.annotations.filter(note => note.name === 'cmfgen-telluric-band');
assert.equal(bands().length, 0, 'Telluric overlay starts off');
first.target.data = [{x:[4000,25000], y:[1,1]}];
const nativeData = JSON.stringify(first.target.data);
first.target._fullLayout.xaxis.range = [6000,20000];
first.get('show').checked = false; first.get('show').handlers.change();
first.get('medium').value = 'air';
telluric.checked = true; telluric.handlers.change(); flush();
assert.equal(markers().length, 0);
assert.equal(bands().length, 8);
assert(bands().every(shape => shape.type === 'rect' && shape.layer === 'below'));
assert.equal(bands()[0].x0, 6270);
assert.equal(bands()[0].x1, 6335);
const fixedBands = JSON.stringify(bands());
first.redshift.value = 'invalid';
first.target.handlers.plotly_afterplot(); flush();
assert.equal(JSON.stringify(bands()), fixedBands, 'Invalid inputs do not change the last applied display frame');
first.target.__spectrumDisplayRedshift = 0.1;
first.target.handlers.plotly_afterplot(); flush();
assert.equal(JSON.stringify(bands()), fixedBands, 'Atmospheric guides remain in the fixed uploaded system as source redshift changes');
first.target.__spectrumDisplayRedshift = 0;
first.target.handlers.plotly_afterplot(); flush();
assert.equal(JSON.stringify(bands()), fixedBands, 'Reset recovers unshifted atmospheric guides');
first.get('medium').value = 'vacuum'; first.get('medium').handlers.change(); flush();
assert(bands()[0].x0 > 6271 && bands()[0].x0 < 6273);
first.get('medium').value = 'air'; first.get('medium').handlers.change();
first.target._fullLayout.xaxis.range = [7500,7650];
first.target.handlers.plotly_afterplot(); flush();
assert.equal(bands().length, 1);
assert.equal(bands()[0].x0, 7580);
assert.equal(bands()[0].x1, 7650, 'Shade only the visible part of a band');
assert(bandNotes().some(note => note.text === 'O₂ A'));
// Reversed logarithmic axes use data coordinates for shapes and log coordinates for labels.
first.target._fullLayout.xaxis.type = 'log';
first.target._fullLayout.xaxis.range = [Math.log10(20000), Math.log10(6000)];
first.target.handlers.plotly_afterplot(); flush();
assert.equal(bands().length, 8);
assert(bandNotes().every(note => note.x > Math.log10(6000) && note.x < Math.log10(20000)));
// Guides cannot extend native coverage during autorange.
first.target.data = [{x:[7500,7650], y:[1,1]}];
first.target._fullLayout.xaxis.type = 'linear';
first.target._fullLayout.xaxis.range = [7400,8000];
first.target.handlers.plotly_afterplot(); flush();
assert.equal(bands()[0].x1, 7650);
first.target.data = JSON.parse(nativeData);
telluric.checked = false; telluric.handlers.change(); flush();
assert.equal(bands().length, 0);
assert.equal(bandNotes().length, 0);
assert(first.target.layout.shapes.some(shape => shape.name === 'fit-bound'));
assert(first.target.layout.annotations.some(note => note.name === 'other'));
assert.equal(JSON.stringify(first.target.data), nativeData, 'Overlays never change spectrum vectors');
first.target._fullLayout.xaxis.range = [6000,10000];
first.get('group').value = 'all';
first.get('show').checked = true; first.get('show').handlers.change();
telluric.checked = true; telluric.handlers.change(); flush();
const stellarShapes = JSON.stringify(markers());
assert(markers().length > 0 && bands().length > 0);
telluric.checked = false; telluric.handlers.change(); flush();
assert.equal(JSON.stringify(markers()), stellarShapes, 'Disabling tellurics leaves stellar markers unchanged');
// Unavailable browser storage never prevents editing or initialization.
window.localStorage.getItem = () => {throw Error('Storage denied');};
window.localStorage.setItem = () => {throw Error('Storage denied');};
const third = setup('third'); flush();
third.get('custom').value = '5000 Still usable'; third.get('custom').handlers.input(); flush();
assert(third.target.layout.annotations.some(note => note.text === 'Still usable'));
console.log('PASS custom lines, redshifted reference wavelengths and zoom, independent telluric bands, air/vacuum, clipping, log axes, data preservation, and browser storage');
