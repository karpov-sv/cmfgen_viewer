// Run through test_browser_smoke.py against its isolated Flask fixture.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [baseUrl, uploadToken, chromium] = process.argv.slice(2);
const profile = await mkdtemp(join(tmpdir(), "cmfgen-browser-"));
const browser = spawn(chromium, ["--headless", "--no-sandbox", "--disable-dev-shm-usage",
  "--disable-gpu", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"]);
let socket;
try {
  const endpoint = await new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(() => reject(new Error(`Chromium startup timed out: ${output}`)), 15000);
    browser.stderr.on("data", chunk => {
      output += chunk;
      const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timer); resolve(match[1]); }
    });
    browser.on("error", reject);
  });
  socket = new WebSocket(endpoint);
  await new Promise(resolve => socket.addEventListener("open", resolve, { once: true }));
  let sequence = 0;
  let sessionId;
  const pending = new Map();
  const errors = [];
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails);
    if (pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(JSON.stringify(message.error)));
      else resolve(message.result);
    }
  });
  function command(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
  const { targetId } = await command("Target.createTarget", { url: "about:blank" });
  ({ sessionId } = await command("Target.attachToTarget", { targetId, flatten: true }));
  await command("Runtime.enable");
  await command("Page.enable");
  await command("Emulation.setDeviceMetricsOverride", { width: 1280, height: 1200, deviceScaleFactor: 1, mobile: false });
  async function evaluate(expression) {
    const result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  async function waitFor(expression) {
    const until = Date.now() + 15000;
    while (Date.now() < until) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Timed out: ${expression}; browser errors: ${JSON.stringify(errors)}`);
  }
  async function open(path, plotId) {
    await command("Page.navigate", { url: baseUrl + path });
    await waitFor(`location.pathname === ${JSON.stringify(path.split("?")[0])} && document.readyState === "complete"`);
    if (plotId) await waitFor(`!!document.getElementById(${JSON.stringify(plotId)})?.__plotResizeObserver`);
  }

  await open("/view/");
  assert(await evaluate('document.body.textContent.includes("model_a")'));
  for (const file of ["RVTJ", "OBSFLUX", "MOD_SUM"]) {
    await open(`/view/model_a/${file}`);
    assert(await evaluate(`document.body.textContent.includes(${JSON.stringify(file)})`));
  }
  const docHref = await evaluate('document.querySelector("[aria-labelledby=docs-dropdown] a").getAttribute("href")');
  await open(docHref);
  assert(await evaluate('document.querySelector("main").textContent.length > 100'));

  for (const [page, scope] of [["main-computation", "main"], ["lte-hydro", "lte-hydro"]]) {
    await open(`/model-actions/${page}/model_a`);
    const previewHref = await evaluate(`document.querySelector('a[href="/model-actions/plan/${scope}/model_a"]').getAttribute('href')`);
    await open(previewHref);
    assert(await evaluate('document.body.textContent.includes("Preview only")'));
    const plan = await evaluate(`fetch(location.pathname + '?format=json').then(r => r.json())`);
    assert.equal(plan.execution_available, false);
    assert(plan.steps.length >= 2);
  }
  await open("/model-actions/plan/flux/model_a");
  assert(await evaluate('document.body.textContent.includes("Legacy shell stage")'));

  await open("/spectrum/model_a", "final-spectrum-plot");
  await evaluate('window.originalX = document.getElementById("final-spectrum-plot").data[0].x[0]');
  await evaluate('var input = document.getElementById("final-spectrum-plot-redshift"); input.value = "0.01"; input.dispatchEvent(new Event("input", {bubbles:true}))');
  await waitFor('Math.abs(document.getElementById("final-spectrum-plot").data[0].x[0] / window.originalX - 1.01) < 1e-8');
  await evaluate('var input = document.getElementById("final-spectrum-plot-yscale"); input.value = "linear"; input.dispatchEvent(new Event("change"))');
  await waitFor('document.getElementById("final-spectrum-plot").layout.yaxis.type === "linear"');
  await evaluate('document.getElementById("final-spectrum-plot").closest(".plotly-resizable").querySelector(".plot-resize-handle").scrollIntoView({block:"center"})');
  const handle = await evaluate('(()=>{const p=document.getElementById("final-spectrum-plot"); const c=p.closest(".plotly-resizable"); const r=c.querySelector(".plot-resize-handle").getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,height:c.getBoundingClientRect().height};})()');
  await command("Input.dispatchMouseEvent", { type: "mousePressed", x: handle.x, y: handle.y, button: "left", clickCount: 1 });
  await command("Input.dispatchMouseEvent", { type: "mouseMoved", x: handle.x, y: handle.y + 80, button: "left", buttons: 1 });
  await command("Input.dispatchMouseEvent", { type: "mouseReleased", x: handle.x, y: handle.y + 80, button: "left", clickCount: 1 });
  await waitFor(`document.getElementById("final-spectrum-plot").closest(".plotly-resizable").getBoundingClientRect().height > ${handle.height + 40}`);
  await evaluate('document.getElementById("final-spectrum-plot-reset-transform").click()');
  await waitFor('Math.abs(document.getElementById("final-spectrum-plot").data[0].x[0] / window.originalX - 1) < 1e-8');

  await open("/bulk/spectra/?selected_models=model_a&selected_models=model_b", "bulk-final-spectrum-plot");
  await evaluate('document.getElementById("bulk-final-spectrum-plot-toggle-final").click()');
  await waitFor('document.getElementById("bulk-final-spectrum-plot").data.filter(t=>t.meta.plot_role==="final").every(t=>t.visible==="legendonly")');
  await open(`/uploads/view/${uploadToken}`, "upload-spectrum-plot");
  await evaluate('var input = document.getElementById("upload-spectrum-plot-xscale"); input.value = "linear"; input.dispatchEvent(new Event("change"))');
  await waitFor('document.getElementById("upload-spectrum-plot").layout.xaxis.type === "linear"');
  assert(await evaluate('!!document.querySelector("#grid-fit-form")'));
  await evaluate(`for (const param of ["redshift", "broadening_km_s", "ebv"]) {
    for (const side of ["min", "max"]) {
      const input = document.querySelector('[name="fit_' + param + '_' + side + '"]');
      if (input) input.value = "0";
    }
  }
  document.querySelector('[data-fit-source="bosz"]').click();`);
  await waitFor('document.getElementById("grid-fit-source").value === "bosz"');
  assert(await evaluate('!document.getElementById("grid-fit-bosz-resolution-note").classList.contains("d-none")'));
  assert(await evaluate('document.getElementById("grid-fit-tlusty-scale-note").classList.contains("d-none") === false'));
  await waitFor('!document.getElementById("grid-fit-result").classList.contains("d-none")');
  assert(await evaluate('document.getElementById("grid-fit-result-body").textContent.includes("ATLAS9 plane-parallel")'));
  await waitFor('document.getElementById("upload-spectrum-plot").data.some(t=>t.meta?.plot_role==="grid_fit_best")');
  await waitFor('!document.querySelector(\'[data-fit-source="phoenix"]\').disabled');
  await evaluate('document.querySelector(\'[data-fit-source="phoenix"]\').click()');
  await waitFor('document.getElementById("grid-fit-source").value === "phoenix"');
  assert(await evaluate('!document.getElementById("grid-fit-phoenix-resolution-note").classList.contains("d-none")'));
  await waitFor('!document.getElementById("grid-fit-result").classList.contains("d-none") && document.getElementById("grid-fit-result-body").textContent.includes("PHOENIX ACES")');
  assert(await evaluate('document.getElementById("grid-fit-result-body").textContent.includes("Interpolated by PHOENIX authors")'));
  assert(await evaluate('document.getElementById("grid-fit-result-body").textContent.includes("not a fit axis")'));
  await waitFor('document.getElementById("upload-spectrum-plot").data.some(t=>t.meta?.plot_role==="grid_fit_best" && t.name.includes("lte06000"))');
  assert.deepEqual(errors, []);
  console.log("Browser smoke passed: listing, parsed files, docs, workflow previews/JSON, spectrum controls, BOSZ/PHOENIX submission, result metadata, and overlays.");
} finally {
  if (socket) socket.close();
  browser.kill("SIGTERM");
  await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once("exit", resolve));
  await rm(profile, { recursive: true, force: true });
}
