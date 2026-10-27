"""Optional correction history is lazy, reversible and safe across async toggles."""
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which('node') is None, reason='Node.js is required')
def test_optional_history_toggle_and_fetch_races():
    script=Path(__file__).resolve().parents[1]/'cmfgen_viewer/static/model_convergence.js'
    result=subprocess.run([shutil.which('node'),'-e',r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8');
const current={name:'Current',x:[10],y:[1]},earlier={name:'Earlier',x:[1,2],y:[4,3]};
const luminosity={name:'Luminosity',x:[10],y:[0.1]},oldLuminosity={name:'Earlier luminosity',x:[1,2],y:[-2,0]};
function setup(fetcher,stored=false,empty=false) {
 const renders=[],status={textContent:''},toggle={checked:false,dataset:{historyUrl:'/history',historyPreference:'model'},
  addEventListener(name,callback){this[name]=callback;}};
 const panels=[{hidden:false},{hidden:false}];
 const target={dataset:{modelConvergencePlot:'0'},closest(selector){return selector==='[data-convergence-panel]'?panels[0]:null;}};
 const second={dataset:{modelConvergencePlot:'1'},closest(selector){return selector==='[data-convergence-panel]'?panels[1]:null;}};
 let calls=0;const storage=new Map(stored?[['cmfgen:correction-history:model','1']]:[]);
 vm.runInNewContext(code,{document:{getElementById(){return {textContent:JSON.stringify([
  {history_key:'data',data:empty?[]:[current],layout:{},config:{}},
  {history_key:'luminosity_data',data:empty?[]:[luminosity],layout:{},config:{}}])};},
  querySelector(selector){return selector==='[data-correction-history-toggle]'?toggle:status;},
  querySelectorAll(){return [target,second];}},
  fetch(...args){calls++;return fetcher(...args);},window:{
   Plotly:{newPlot(){return Promise.resolve();},react(target,data){renders.push(JSON.parse(JSON.stringify(data)));}},
   localStorage:{getItem(key){return storage.get(key);},setItem(key,value){storage.set(key,value);}}}});
 return {toggle,status,renders,panels,get calls(){return calls;}};
}
const response={ok:true,json(){return Promise.resolve({data:[earlier],luminosity_data:[oldLuminosity],run_count:1,record_count:2,note:'Separate runs',limited:false});}};
(async()=>{
 const empty=setup(()=>Promise.resolve(response),false,true);
 assert(empty.panels.every(panel=>panel.hidden),'empty current panels start hidden');
 empty.toggle.checked=true;await empty.toggle.change();
 assert(empty.panels.every(panel=>!panel.hidden),'history reveals both panels');
 empty.toggle.checked=false;await empty.toggle.change();
 assert(empty.panels.every(panel=>panel.hidden),'turning history off hides empty panels again');
 const state=setup(()=>Promise.resolve(response));
 assert.equal(state.calls,0,'history must not load by default');
 assert(state.panels.every(panel=>!panel.hidden),'current points remain visible without history');
 state.toggle.checked=true;await state.toggle.change();
 assert.deepEqual(state.renders.at(-1),[oldLuminosity,luminosity]);
 assert.equal(state.calls,1);assert.deepEqual(state.renders.at(-2),[earlier,current]);
 state.toggle.checked=false;await state.toggle.change();assert.deepEqual(state.renders.at(-2),[current]);
 assert.deepEqual(state.renders.at(-1),[luminosity]);
 state.toggle.checked=true;await state.toggle.change();assert.equal(state.calls,1,'reuse loaded data');
 assert.deepEqual(state.renders.at(-2),[earlier,current]);
 let finish;const raced=setup(()=>new Promise(resolve=>finish=resolve));
 raced.toggle.checked=true;const loading=raced.toggle.change();
 raced.toggle.checked=false;await raced.toggle.change();finish(response);await loading;
 assert.equal(raced.toggle.checked,false);assert.deepEqual(raced.renders.at(-2),[current]);
 const failed=setup(()=>Promise.reject(new Error('unavailable')));
 failed.toggle.checked=true;await failed.toggle.change();assert.equal(failed.toggle.checked,false);
 assert(failed.status.textContent.includes('retry'));
 failed.toggle.checked=true;await failed.toggle.change();assert.equal(failed.calls,2);
 const remembered=setup(()=>Promise.resolve(response),true);
 await new Promise(setImmediate);assert.equal(remembered.calls,1);assert.equal(remembered.toggle.checked,true);
 assert.deepEqual(remembered.renders.at(-2),[earlier,current]);
})().catch(error=>{console.error(error);process.exitCode=1;});
''',str(script)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
