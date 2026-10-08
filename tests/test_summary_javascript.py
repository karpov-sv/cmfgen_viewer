"""Browser progress reporting and reconnect/expired-job handling."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
MODULE = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/summary_job.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for JavaScript checks")


def run_browser(scenario):
    script = r"""
const fs = require('fs'), vm = require('vm');
const scenario = process.argv[2], elements = {}, timers = [], requests = [];
let reloads = 0;
function element(id) {
  if (!elements[id]) elements[id] = {textContent:'', style:{}, disabled:false, hidden:true,
    classList:{add() {elements[id].hidden=true;}, remove() {elements[id].hidden=false;}},
    parentElement:{setAttribute(key,value) {elements[id][key]=value;}}};
  return elements[id];
}
element('summary-job').dataset={status:'running',statusUrl:'/bulk/summary/test/status'};
const job={status:scenario==='completed'?'completed':'running',status_label:'Stopping',
  processed:2,total:5,updated:1,reused:1,skipped_count:0,failed_count:0,
  phase:'Saving summary',current_entry:'model_a',elapsed_seconds:3,progress_percent:40,cancel_requested:true};
const window={
  location:{reload() {reloads++;}},
  setTimeout(fn, delay) {timers.push(delay);return timers.length;},
  fetch(url, options) {
    requests.push({url,options});
    if (scenario==='network-error') return Promise.reject(new Error('offline'));
    return Promise.resolve({status:scenario==='missing'?404:200,ok:scenario!=='missing',
      json:()=>Promise.resolve({ok:true,job})});
  }
};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),{window,document:{getElementById:element}});
setImmediate(()=>process.stdout.write(JSON.stringify({elements,timers,requests,reloads})));
"""
    result = subprocess.run([NODE, "-e", script, str(MODULE), scenario], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_browser_updates_counts_current_folder_progress_and_cancel_state():
    result = run_browser("running")
    assert result["elements"]["summary-job-counts"]["textContent"].startswith("2/5 folders; updated: 1, reused: 1")
    assert result["elements"]["summary-job-current"]["textContent"] == "Saving summary: model_a"
    assert result["elements"]["summary-job-progress"]["style"]["width"] == "40%"
    assert result["elements"]["summary-job-cancel"]["disabled"]
    assert result["timers"] == [1500]
    assert result["requests"][0]["options"]["cache"] == "no-store"


def test_browser_reloads_results_when_processing_finishes():
    result = run_browser("completed")
    assert result["reloads"] == 1
    assert not result["timers"]


def test_browser_retries_network_failures_without_resubmitting():
    result = run_browser("network-error")
    assert not result["elements"]["summary-job-connection"]["hidden"]
    assert "Do not resubmit" in result["elements"]["summary-job-connection"]["textContent"]
    assert result["timers"] == [5000]
    assert result["reloads"] == 0


def test_browser_reports_missing_job_and_stops_polling():
    result = run_browser("missing")
    assert "server restarted" in result["elements"]["summary-job-connection"]["textContent"]
    assert result["elements"]["summary-job-cancel"]["disabled"]
    assert result["elements"]["summary-job-status"]["textContent"] == "Unavailable"
    assert not result["timers"]
