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
assert.equal(air[1].vacuum, 1215.67); // UV input stays vacuum.
assert.equal(api.parseCustomLines('1e309\n1e-999\nNaN\n1e3junk', 'air').lines.length, 0);

function setup(id) {
  for (const name of ['show','group','medium','labels','zoom','custom','custom-medium','custom-status']) elements[id + '-lines-' + name] = new Element();
  const get = name => elements[id + '-lines-' + name];
  get('show').checked = get('labels').checked = true;
  get('group').value = 'custom'; get('medium').value = 'vacuum'; get('custom-medium').value = 'vacuum';
  get('zoom').appendChild(new Element('full'));
  const target = {id, layout: {shapes: [{name:'fit-bound'}], annotations: [{name:'other'}], xaxis: {}, yaxis: {}},
    _fullLayout: {xaxis: {type:'linear', range:[4000,7000], _length:1000}, yaxis: {type:'linear',range:[0,3]}},
    data: [{x:[1000,4000,5000,6000,7000,8000],y:[1,2,1,2,1,2]}], on() {}};
  const redshift = {value:'0.01'};
  api.bind(target, {redshiftInput:redshift});
  return {target,get,redshift};
}
function flush() { let count=0; while(frames.length) { frames.shift()(); assert(++count < 50, 'No refresh loop'); } }
const first = setup('first'); flush();
first.get('custom').value = '5000 My line\n6000, <b>Custom</b>\n-1 invalid';
first.get('custom').handlers.input(); flush();
assert.equal(first.get('custom').attrs['aria-invalid'], 'true');
assert(first.get('custom-status').textContent.includes('Ignored invalid rows: 3'));
const markers = () => first.target.layout.shapes.filter(shape => shape.name === 'cmfgen-spectral-line');
assert.deepEqual(markers().map(shape => shape.x0), [5050,6060]);
assert(first.target.layout.shapes.some(shape => shape.name === 'fit-bound'));
assert(first.target.layout.annotations.some(note => note.name === 'other'));
assert(first.target.layout.annotations.some(note => note.text === '&lt;b&gt;Custom&lt;/b&gt;'));
let customGroup = first.get('zoom').children.find(child => child.label === 'Custom lines');
assert.equal(customGroup.children.length, 2);
first.get('zoom').value = customGroup.children[0].value;
first.get('zoom').handlers.change();
assert.deepEqual(Array.from(first.target._fullLayout.xaxis.range), [4900,5200]);
first.target._fullLayout.xaxis.range = [4000,7000];
first.get('group').value = 'hydrogen'; first.get('group').handlers.change(); flush();
assert(!markers().some(shape => shape.x0 === 5050));
first.get('group').value = 'all'; first.get('group').handlers.change(); flush();
assert(markers().some(shape => shape.x0 === 5050));
const second = setup('second'); flush();
assert.equal(second.get('custom').value, first.get('custom').value); // Reuse saved browser lines.
first.get('custom-medium').value = 'air'; first.get('custom-medium').handlers.change(); flush();
assert.equal(second.get('custom-medium').value, 'air'); // Other plots update in place.
assert(markers().some(shape => shape.x0 > 5050 && shape.x0 < 5052));
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
assert(markers().some(shape => shape.x0 === 5151));
// Unavailable browser storage never prevents editing or initialization.
window.localStorage.getItem = () => {throw Error('Storage denied');};
window.localStorage.setItem = () => {throw Error('Storage denied');};
const third = setup('third'); flush();
third.get('custom').value = '5000 Still usable'; third.get('custom').handlers.input(); flush();
assert(third.target.layout.annotations.some(note => note.text === 'Still usable'));
console.log('PASS custom line parsing, invalid rows, media, UV, redshift, groups, zoom, escaping, persistence, synchronization, and blocked storage');
