"""Check initialization form behavior without requiring a browser install."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required")
def test_selecting_pop_enables_prerequisites_only_on_user_change():
    script = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/model_parameters.js"
    result = subprocess.run([shutil.which("node"), "-e", r'''
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const source = fs.readFileSync(process.argv[1], "utf8");
function control(value) {
  return {value, listeners: {}, addEventListener(name, callback) {this.listeners[name] = callback;}};
}
// Initialization must work even when luminosity scaling is unavailable.
for (const checkbox of [null, {disabled: true}]) {
  for (const initial of ["", "F", "T"]) {
    const fields = {DC_METH: control("POP"), LIN_INT: control(initial), POP_SCALE: control(initial)};
    const form = {elements: {namedItem: name => fields[name.replace("quick_value:", "")]},
                  querySelector: () => checkbox};
    const other = {elements: {namedItem: () => null}, querySelector: () => null};
    vm.runInNewContext(source, {document: {
      addEventListener() {}, querySelectorAll: () => [form, other]
    }});
    assert.equal(fields.LIN_INT.value, initial, "loading must preserve inputs");
    assert.equal(fields.POP_SCALE.value, initial);
    fields.DC_METH.value = "R";
    fields.DC_METH.listeners.change();
    assert.equal(fields.LIN_INT.value, initial, "other methods must preserve switches");
    assert.equal(fields.POP_SCALE.value, initial);
    fields.DC_METH.value = "POP";
    fields.DC_METH.listeners.change();
    assert.equal(fields.LIN_INT.value, "T");
    assert.equal(fields.POP_SCALE.value, "T");
    fields.DC_METH.value = "ED";
    fields.DC_METH.listeners.change();
    assert.equal(fields.LIN_INT.value, "T", "switching away must retain reviewable values");
    assert.equal(fields.POP_SCALE.value, "T");
  }
}
''', str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is required')
def test_structure_form_only_enables_inputs_for_selected_operation():
    script=Path(__file__).resolve().parents[1]/'cmfgen_viewer/static/model_parameters.js'
    result=subprocess.run([shutil.which('node'),'-e',r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const operation={value:'update',addEventListener(type,fn){this.change=fn;}};
function panel(modes){return {dataset:{structureFor:modes},hidden:false,controls:[{disabled:false}],
  querySelectorAll(){return this.controls;}};}
const panels=[panel('update'),panel('new_nd'),panel('insert'),panel('insert outer'),panel('radii')];
const form={elements:{namedItem(){return operation;}},querySelectorAll(){return panels;}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{
  addEventListener(){},querySelectorAll(selector){return selector==='[data-structure-form]'?[form]:[];}}});
for(const mode of ['update','new_nd','insert','outer','radii','sigma']){
 operation.value=mode;operation.change();
 for(const p of panels){const visible=p.dataset.structureFor.split(' ').includes(mode);
  assert.equal(p.hidden,!visible);assert.equal(p.controls[0].disabled,!visible);}
}
''',str(script)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
