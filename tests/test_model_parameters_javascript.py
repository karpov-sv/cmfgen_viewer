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


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is required')
def test_ba_reuse_notice_updates_without_changing_controls():
    script=Path(__file__).resolve().parents[1]/'cmfgen_viewer/static/model_parameters.js'
    result=subprocess.run([shutil.which('node'),'-e',r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
function control(value) {return {value,listeners:{},classes:new Set(),
 addEventListener(name,fn){this.listeners[name]=fn;},
 classList:{toggle(name,enabled){enabled?this.owner.classes.add(name):this.owner.classes.delete(name);}}};}
const fields={COMP_BA:control('T'),N_FIX_BA:control('0'),FIX_BA:control('0.0')};
Object.values(fields).forEach(c=>c.classList.owner=c);
const notice={hidden:true},badges=[{hidden:true},{hidden:true}];
const form={elements:{namedItem(name){return fields[name.replace('quick_value:','')]||null;}},
 querySelector(selector){return selector==='[data-ba-reuse-notice]'?notice:null;},
 querySelectorAll(){return badges;}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{
 addEventListener(){},querySelectorAll(selector){return selector==='[data-quick-parameter-form]'?[form]:[];}}});
assert.equal(notice.hidden,false);assert(fields.N_FIX_BA.classes.has('border-warning'));
assert(badges.every(b=>!b.hidden));
for(const value of ['1','','nonsense']) {
 fields.N_FIX_BA.value=value;fields.N_FIX_BA.listeners.input();
 assert.equal(notice.hidden,true);assert(!fields.N_FIX_BA.classes.has('border-warning'));
}
fields.N_FIX_BA.value='0D0';fields.N_FIX_BA.listeners.input();assert.equal(notice.hidden,false);
fields.COMP_BA.value='F';fields.COMP_BA.listeners.change();assert.equal(notice.hidden,true);
assert.equal(fields.FIX_BA.value,'0.0');
''',str(script)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is required')
def test_solver_notices_share_rules_and_update_without_changing_values():
    import json
    from cmfgen_viewer.solver_notices import SOLVER_NOTICES
    script=Path(__file__).resolve().parents[1]/'cmfgen_viewer/static/model_parameters.js'
    result=subprocess.run([shutil.which('node'),'-e',r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const rules=JSON.parse(process.argv[2]);
function control(value) {const classes=new Set();return {value,classes,listeners:{},
 addEventListener(name,fn){this.listeners[name]=fn;},classList:{toggle(name,on){on?classes.add(name):classes.delete(name);}}};}
const initial={DO_LAM_AUTO:'F',DO_LAM_IT:'T',MAX_LAM:'1D12',FIX_T:'T',DO_NG:'F',RELAX:'0.25'};
const forms=[],states=[];
for(const file of ['VADAT','IN_ITS','ADJUST_CORRECTIONS']) {
 const selected=rules.filter(r=>r.file===file),fields={};
 selected.forEach(r=>fields[r.key]=control(initial[r.key]));
 const notices=selected.map(r=>({hidden:true,dataset:{solverNotice:r.id,solverRule:JSON.stringify(r.conditions),
  solverKey:r.key,solverTone:r.tone}}));
 const badges=selected.map(r=>({hidden:true,dataset:{solverBadge:r.id}}));
 const group={querySelectorAll(){return notices;}};
 forms.push({elements:{namedItem(name){return fields[name.replace('quick_value:','')]||null;}},
  querySelector(selector){return selector==='[data-solver-notices]'?group:null;},querySelectorAll(){return badges;}});
 states.push({selected,fields,notices,badges});
}
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{document:{addEventListener(){},
 querySelectorAll(selector){return selector==='[data-quick-parameter-form]'?forms:[];}}});
for(const state of states) {
 state.selected.forEach((rule,i)=>{
  const field=state.fields[rule.key],notice=state.notices[i],badge=state.badges[i];
  assert.equal(field.value,initial[rule.key]);assert.equal(notice.hidden,false);assert.equal(badge.hidden,false);
  assert(field.classes.has('border-'+rule.tone));
  field.value=rule.conditions[0].op==='eq'?(initial[rule.key]==='T'?'F':'T'):'1';
  field.listeners.input();assert.equal(notice.hidden,true);assert.equal(badge.hidden,true);
  assert(!field.classes.has('border-'+rule.tone));
  field.value=initial[rule.key];field.listeners.change();assert.equal(notice.hidden,false);
  if(rule.conditions[0].op!=='eq') {
   for(const value of ['','NaN','Infinity','bad']) {
    field.value=value;field.listeners.input();assert.equal(notice.hidden,true);
   }
  }
 });
}
''',str(script),json.dumps(SOLVER_NOTICES)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
