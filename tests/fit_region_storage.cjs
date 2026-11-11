const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const storage = new Map();
let blocked = false;
const window = {localStorage: {
  getItem(key) { if (blocked) throw Error('unavailable'); return storage.get(key) || null; },
  setItem(key, value) { if (blocked) throw Error('unavailable'); storage.set(key, value); }
}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../cmfgen_viewer/static/fit_region_storage.js'), 'utf8'), {window});
function field(value='') {
  const handlers = {};
  return {value, maxLength:16000, addEventListener(name, fn) {handlers[name]=fn;},
    edit(text, event='input') {this.value=text; handlers[event]();}};
}
function form(token, extra={}) {
  const options = {token, windows:field(), exclusions:field(), ...extra};
  window.CmfgenFitRegionStorage.bind(options);
  return options;
}
let changed=0;
const first=form('one', {onChange(){changed++;}});
first.windows.edit('He I, 4450, 4490\n');
first.exclusions.edit('Telluric, 6860, 6970', 'change');
assert.equal(changed,2);
const restored=form('one');
assert.equal(restored.windows.value, first.windows.value);
assert.equal(restored.exclusions.value, first.exclusions.value);
assert.equal(form('other').windows.value,'', 'Uploads must retain separate drafts');
restored.windows.edit('');
assert.equal(form('one').windows.value,'', 'Clearing a field must persist');
// The existing zoom buttons emit input/change events after appending bounds.
restored.windows.edit('4450, 4490', 'change');
assert.equal(form('one').windows.value,'4450, 4490');
form('one', {windows:field('Running fit, 4500, 4600'), exclusions:field(''),
  authoritative:['windows','exclusions']});
assert.equal(form('one').windows.value,'Running fit, 4500, 4600');
assert.equal(form('one').exclusions.value,'');
form('one', {windows:field(''), authoritative:['windows']});
assert.equal(form('one').windows.value,'', 'Explicit blank URL value must override a saved draft');
storage.set('cmfgen-fit-regions-v1:bad','{malformed');
assert.equal(form('bad').windows.value,'');
storage.set('cmfgen-fit-regions-v1:bad',JSON.stringify({windows:'x'.repeat(16001),exclusions:42}));
assert.equal(form('bad').windows.value,'');
assert.equal(form('bad').exclusions.value,'');
storage.set('cmfgen-fit-regions-v1:bad','[]');
assert.equal(form('bad').windows.value,'');
blocked=true;
const fallback=form('one');
fallback.windows.edit('Manual, 5000, 5100');
assert.equal(fallback.windows.value,'Manual, 5000, 5100');
window.CmfgenFitRegionStorage.bind({token:'photometry'});
console.log('PASS per-upload region persistence, clearing, zoom edits, URL/job precedence, and unavailable/malformed storage');
