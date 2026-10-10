"""Task navigation polls only while visible background work is active."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
SCRIPT = Path(__file__).resolve().parents[1] / "cmfgen_viewer/static/background_tasks.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required")


def run_navigation(scenario):
    harness = r"""
const fs = require('fs'), vm = require('vm');
const scenario = process.argv[2], timers = new Map(), events = {}, elements = {};
let calls = 0, nextTimer = 0, tasks = [], fail = false;
function element() {
  return {children: [], classList: {add() {}, remove() {}}, style: {},
    setAttribute() {}, getAttribute() {return '/tasks/status';},
    appendChild(child) {this.children.push(child);},
    removeChild() {this.children.shift();},
    get firstChild() {return this.children[0];}};
}
const document = {
  hidden: scenario === 'initial-hidden',
  getElementById(id) {return elements[id] || (elements[id] = element());},
  createElement: element,
  addEventListener(name, fn) {events[name] = fn;}
};
const window = {
  fetch() {
    calls++;
    return fail ? Promise.reject(new Error('offline')) :
      Promise.resolve({ok: true, json: () => Promise.resolve({tasks})});
  },
  setTimeout(fn, delay) {timers.set(++nextTimer, {fn, delay}); return nextTimer;},
  clearTimeout(id) {timers.delete(id);},
  addEventListener(name, fn) {events[name] = fn;}
};
const flush = () => new Promise(resolve => setImmediate(resolve));
const state = () => ({calls, delays: [...timers.values()].map(t => t.delay)});
(async () => {
  if (['finish', 'hidden', 'retry'].includes(scenario)) tasks = [{title: 'Fit'}];
  if (scenario === 'initial-error') fail = true;
  vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {window, document});
  await flush();
  const initial = state();
  if (scenario === 'finish' || scenario === 'retry') {
    tasks = [];
    fail = scenario === 'retry';
    const [id, timer] = [...timers.entries()][0];
    timers.delete(id);
    timer.fn();
  } else if (scenario === 'hidden') {
    document.hidden = true;
    events.visibilitychange();
    events['cmfgen:background-tasks-changed']();
    await flush();
    const hidden = state();
    document.hidden = false;
    events.visibilitychange();
    await flush();
    process.stdout.write(JSON.stringify({initial, hidden, final: state()}));
    return;
  } else if (scenario === 'new-task') {
    tasks = [{title: 'New fit'}];
    events['cmfgen:background-tasks-changed']();
  } else if (scenario === 'focus') {
    tasks = [{title: 'Fit from another tab'}];
    events.focus();
  } else if (scenario === 'initial-hidden') {
    document.hidden = false;
    events.visibilitychange();
  }
  await flush();
  process.stdout.write(JSON.stringify({initial, final: state()}));
})();
"""
    result = subprocess.run(
        [NODE, "-e", harness, str(SCRIPT), scenario],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("scenario", ["idle", "initial-error"])
def test_idle_navigation_does_not_keep_polling(scenario):
    result = run_navigation(scenario)
    assert result["final"] == {"calls": 1, "delays": []}


def test_navigation_stops_after_last_task_finishes():
    result = run_navigation("finish")
    assert result["initial"] == {"calls": 1, "delays": [1500]}
    assert result["final"] == {"calls": 2, "delays": []}


def test_hidden_tab_pauses_and_resumes_active_task_updates():
    result = run_navigation("hidden")
    assert result["hidden"] == {"calls": 1, "delays": []}
    assert result["final"] == {"calls": 2, "delays": [1500]}


@pytest.mark.parametrize("scenario", ["new-task", "focus"])
def test_idle_navigation_discovers_new_work_on_event_or_focus(scenario):
    result = run_navigation(scenario)
    assert result["initial"] == {"calls": 1, "delays": []}
    assert result["final"] == {"calls": 2, "delays": [1500]}


def test_initially_hidden_tab_waits_until_visible():
    result = run_navigation("initial-hidden")
    assert result["initial"] == {"calls": 0, "delays": []}
    assert result["final"] == {"calls": 1, "delays": []}


def test_active_navigation_retries_connection_failure():
    result = run_navigation("retry")
    assert result["final"] == {"calls": 2, "delays": [10000]}
