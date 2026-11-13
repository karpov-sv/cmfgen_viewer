"""Cache-maintenance progress must refresh final results, including anchored URLs."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
MODULE = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/system.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for JavaScript checks")


@pytest.mark.parametrize("status", ["running", "completed", "failed"])
@pytest.mark.parametrize("current_job", ["test", "other"])
def test_cache_progress_loads_final_results(status, current_job):
    script = r"""
const fs = require('fs'), vm = require('vm');
const status = process.argv[2], currentJob = process.argv[3];
const timers = [], replacements = [], requests = [];
let reloads = 0;
const attributes = {'data-status':'running', 'data-status-url':'/system/cache/job/test',
  'data-return-url':'/system/?job=test#model-cache'};
const elements = {
  'cache-maintenance-job': {getAttribute: key => attributes[key]},
  'cache-maintenance-progress': {style:{}},
  'cache-maintenance-detail': {classList:{add(){}}}
};
const window = {
  location: {href:'http://localhost/system/?job='+currentJob+'#model-cache',
    reload(){reloads++;}, replace(url){replacements.push(url);}},
  setTimeout(fn, delay){timers.push({fn,delay});},
  fetch(url, options){
    requests.push({url,options});
    return Promise.resolve({ok:true,json:()=>Promise.resolve({job:{
      status,phase:'Refreshing',processed:3,total:4,progress_percent:75,current_entry:'model_a'
    }})});
  }
};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),
  {window, URL, document:{getElementById:id=>elements[id]}});
timers.shift().fn();
setImmediate(()=>process.stdout.write(JSON.stringify({reloads,replacements,requests,
  timers:timers.map(t=>t.delay),elements})));
"""
    result = subprocess.run([NODE, "-e", script, str(MODULE), status, current_job],
                            text=True, capture_output=True, check=True, timeout=10)
    state = json.loads(result.stdout)
    assert state["requests"][0]["options"]["cache"] == "no-store"
    if status == "running":
        assert state["timers"] == [1000]
        assert state["elements"]["cache-maintenance-progress"]["style"]["width"] == "75.0%"
        assert state["reloads"] == 0
        assert not state["replacements"]
    else:
        assert not state["timers"]
        assert state["reloads"] == (1 if current_job == "test" else 0)
        assert state["replacements"] == ([] if current_job == "test" else
                                         ["http://localhost/system/?job=test#model-cache"])
