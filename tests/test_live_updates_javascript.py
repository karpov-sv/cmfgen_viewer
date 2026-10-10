"""One reconnecting event connection serves all panels and pauses when hidden."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
STATIC = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


def test_shared_stream_reconnect_visibility_delivery_and_navigation_rendering():
    script = r"""
const fs = require('fs'), vm = require('vm');
const streams = [], timers = new Map(), events = {}, elements = {};
let id = 0, fetches = 0;
function element() {
  return {children: [], dataset: {}, style: {}, textContent: '', classes: new Set(),
    setAttribute() {}, getAttribute() {return '/tasks/status';},
    appendChild(c) {this.children.push(c);}, removeChild() {this.children.shift();},
    get firstChild() {return this.children[0];},
    classList: {add() {}, remove() {}}};
}
const document = {hidden: false, readyState: 'loading', currentScript: {dataset: {eventsUrl: '/tasks/events'}},
  getElementById(key) {return elements[key] || (elements[key] = element());},
  createElement: element, addEventListener(key, fn) {(events[key] ||= []).push(fn);}};
class EventSource {
  constructor(url) {this.url = url; this.events = {}; streams.push(this);}
  addEventListener(event, fn) {this.events[event] = fn;}
  close() {this.closed = true;}
}
const window = {EventSource, location: {href: 'http://localhost/models/'},
  setTimeout(fn, delay) {timers.set(++id, {fn, delay}); return id;},
  clearTimeout(id) {timers.delete(id);},
  addEventListener: document.addEventListener,
  fetch() {fetches++; return Promise.resolve({ok:true,json:()=>Promise.resolve({tasks:[]})});}};
const context = {window, document, EventSource, URL};
vm.runInNewContext(fs.readFileSync(process.argv[1] + '/live_updates.js','utf8'), context);
vm.runInNewContext(fs.readFileSync(process.argv[1] + '/background_tasks.js','utf8'), context);
const runtimes = [];
window.CmfgenLiveUpdates.subscribe('runtime:lte:model_a', value => runtimes.push(value));
window.CmfgenLiveUpdates.subscribe('runtime:hydro:model_a', value => runtimes.push(value));
const flushTimers = () => {const pending=[...timers.values()];timers.clear();pending.forEach(t=>t.fn());};
const emit = (name) => (events[name] || []).forEach(fn => fn({}));
flushTimers();
if (streams.length) throw new Error('Opened before deferred panel subscriptions');
emit('DOMContentLoaded');
streams[0].onopen();
streams[0].events.tasks({data:JSON.stringify({tasks:[{title:'Fit'}]})});
const startedCount = elements['background-task-count'].textContent;
streams[0].events.runtime({data:JSON.stringify({key:'lte:model_a',runtime:{active:true}})});
streams[0].events.tasks({data:JSON.stringify({tasks:[]})});
const completedCount = elements['background-task-count'].textContent;
emit('cmfgen:background-tasks-changed');
const healthyFetches = fetches;
streams[0].onerror();
const fallbackFetches = fetches;
streams[0].onopen();
document.hidden = true; emit('visibilitychange');
const closed = streams[0].closed;
document.hidden = false; emit('visibilitychange');
streams[1].onopen();
streams[1].events.runtime({data:JSON.stringify({key:'hydro:model_a',runtime:{active:false}})});
emit('pagehide');
setImmediate(() => process.stdout.write(JSON.stringify({
  urls:streams.map(s=>s.url), startedCount, completedCount, runtimes,
  healthyFetches, fallbackFetches, closed, finalClosed:streams[1].closed,
  timers:timers.size
})));
"""
    result = subprocess.run([NODE, "-e", script, str(STATIC)], capture_output=True,
                            text=True, check=True)
    state = json.loads(result.stdout)
    assert len(state["urls"]) == 2
    assert all("runtime=lte%3Amodel_a" in url and "runtime=hydro%3Amodel_a" in url
               for url in state["urls"])
    assert state["startedCount"] == "1"
    assert state["completedCount"] == "0"
    assert state["runtimes"] == [{"active": True}, {"active": False}]
    assert state["healthyFetches"] == 0
    assert state["fallbackFetches"] == 1
    assert state["closed"] and state["finalClosed"]
    assert state["timers"] == 0
