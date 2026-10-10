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
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Chromium WebSocket connection timed out')), 15000);
    socket.addEventListener("open", () => { clearTimeout(timer); resolve(); }, { once: true });
    socket.addEventListener("error", event => {
      clearTimeout(timer);
      reject(new Error(event.message || 'Chromium WebSocket connection failed'));
    }, { once: true });
  });
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
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`Browser command timed out: ${method} ${JSON.stringify(params)}`));
      }, 15000);
      pending.set(id, {
        resolve: result => { clearTimeout(timer); resolve(result); },
        reject: error => { clearTimeout(timer); reject(error); }
      });
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

  async function checkSpectralLines(plotId) {
    const id = JSON.stringify(plotId);
    const plot = `document.getElementById(${id})`;
    const lines = `(${plot}.layout.shapes || []).filter(s => s.name === 'cmfgen-spectral-line')`;
    const labels = `(${plot}.layout.annotations || []).filter(a => a.name === 'cmfgen-spectral-line')`;
    async function change(suffix, property, value) {
      await evaluate(`(()=>{const input = document.getElementById(${id} + ${JSON.stringify(suffix)});
        input[${JSON.stringify(property)}] = ${JSON.stringify(value)};
        input.dispatchEvent(new Event('change'));})()`);
    }
    const baseline = await evaluate(`(()=>{const p=${plot}; return {
      data: JSON.stringify(p.__spectrumSampling.getSources()), range: p._fullLayout.xaxis.range,
      shapes: p.layout.shapes || [], annotations: p.layout.annotations || [],
      type: p.layout.xaxis.type, yRange: p._fullLayout.yaxis.range, yAutorange: p._fullLayout.yaxis.autorange
    };})()`);
    const z = await evaluate(`Number(document.getElementById(${id} + '-redshift')?.value || 0)`);
    const wavelengthRange = `(()=>{const axis=${plot}._fullLayout.xaxis;
      return axis.range.map(value => axis.type === 'log' ? Math.pow(10, value) : value);})()`;
    async function zoomTo(value, expected, tolerance = 1e-6) {
      await change('-lines-zoom', 'value', value);
      await waitFor(`${wavelengthRange}.every((value, index) => Math.abs(value - ${JSON.stringify(expected)}[index]) < ${tolerance})`);
      assert.equal(await evaluate(`document.getElementById(${id} + '-lines-zoom').value`), '');
    }
    await waitFor(`Array.from(document.getElementById(${id} + '-lines-zoom').options).some(o => o.textContent.startsWith('Hα'))`);
    const hAlphaPreset = await evaluate(`Array.from(document.getElementById(${id} + '-lines-zoom').options).find(o => o.textContent.startsWith('Hα')).value`);
    const fullRange = await evaluate(`(()=>{const wavelengths=${plot}.__spectrumSampling.getSources().filter(t => t.visible !== false && t.visible !== 'legendonly').flatMap(t => t.x);
      return [Math.min(...wavelengths), Math.max(...wavelengths)];})()`);
    assert(await evaluate(`!document.getElementById(${id} + '-lines-show').checked`));
    await zoomTo('optical', [3800, 7500]);
    await zoomTo(hAlphaPreset, [6564.614 * (1 + z) - 150, 6564.614 * (1 + z) + 150]);
    const lineFluxSpan = await evaluate(`(()=>{const range=${plot}._fullLayout.yaxis.range; return Math.abs(range[1]-range[0]);})()`);
    assert.equal(await evaluate(`${plot}.layout.xaxis.type`), baseline.type);
    // Air selection is available while the overlay is off and shifts the
    // preset center without modifying any spectrum data.
    await change('-lines-medium', 'value', 'air');
    await zoomTo(hAlphaPreset, [6562.801 * (1 + z) - 150, 6562.801 * (1 + z) + 150], 0.02);
    await change('-lines-medium', 'value', 'vacuum');
    await zoomTo('full', fullRange);
    assert(await evaluate(`(()=>{const range=${plot}._fullLayout.yaxis.range; return Math.abs(range[1]-range[0]) > ${lineFluxSpan};})()`), 'Whole-spectrum flux range should expand beyond a narrow line window');
    assert(await evaluate(`Array.from(document.getElementById(${id} + '-lines-zoom').options).find(o => o.textContent.startsWith('Lyα')).disabled`));
    await evaluate(`Plotly.relayout(${plot}, {'xaxis.range':${JSON.stringify(baseline.range)}}).then(() => null)`);
    await change('-lines-show', 'checked', true);
    await waitFor(`${lines}.length > 0`);
    assert.deepEqual(await evaluate(`${plot}._fullLayout.xaxis.range`), baseline.range);
    assert.equal(await evaluate(`JSON.stringify(${plot}.__spectrumSampling.getSources())`), baseline.data);
    await waitFor(`${lines}.some(s => Math.abs(s.x0 - ${6564.614 * (1 + z)}) < 1e-6)`);
    await waitFor(`${labels}.some(a => a.text === 'Hα')`);
    const hAlpha = await evaluate(`${labels}.find(a => a.text === 'Hα').x`);
    const expected = baseline.type === 'log' ? Math.log10(6564.614 * (1 + z)) : 6564.614 * (1 + z);
    assert(Math.abs(hAlpha - expected) < 1e-10, 'Label must match the axis convention');

    await change('-lines-group', 'value', 'hydrogen');
    await waitFor(`${labels}.length > 0 && ${labels}.every(a => !a.text.startsWith('He') && (a.text.startsWith('H') || a.text.startsWith('Pa') || a.text.startsWith('Br') || a.text.startsWith('Ly')))`);
    await change('-lines-medium', 'value', 'air');
    await waitFor(`${lines}.some(s => Math.abs(s.x0 - ${6562.801 * (1 + z)}) < 0.02)`);
    await change('-lines-labels', 'checked', false);
    await waitFor(`${labels}.length === 0`);
    assert(await evaluate(`${lines}.length > 0`));
    await change('-lines-medium', 'value', 'vacuum');
    await change('-lines-group', 'value', 'all');
    await change('-lines-labels', 'checked', true);

    await evaluate(`Plotly.relayout(${plot}, {'xaxis.type':'linear', 'xaxis.range':[6540, 6600]}).then(() => null)`);
    await waitFor(`${lines}.every(s => s.x0 >= 6540 && s.x0 <= 6600) && ${lines}.length > 0`);
    await waitFor(`${labels}.some(a => a.text === 'Hα' && Math.abs(a.x - ${6564.614 * (1 + z)}) < 1e-6)`);
    // Existing fit ranges replace layout.shapes. The overlay must restore its
    // markers while keeping these independently managed bounds/annotations.
    const fitShape = {type:'line', xref:'x', yref:'paper', x0:90000, x1:90000, y0:0, y1:1};
    const note = {text:'Existing annotation', x:6550, y:0.5, xref:'x', yref:'paper', showarrow:false};
    await evaluate(`Plotly.relayout(${plot}, {shapes:[${JSON.stringify(fitShape)}], annotations:[${JSON.stringify(note)}]}).then(() => null)`);
    await waitFor(`${lines}.length > 0 && ${plot}.layout.shapes.some(s => s.x0 === 90000)`);
    // The whole-spectrum preset uses data coverage, rather than fit markers.
    await zoomTo('full', fullRange);
    await zoomTo('optical', [3800, 7500]);
    await zoomTo(hAlphaPreset, [6564.614 * (1 + z) - 150, 6564.614 * (1 + z) + 150]);
    assert.equal(await evaluate(`${plot}.layout.xaxis.type`), 'linear');
    await change('-lines-show', 'checked', false);
    await waitFor(`${lines}.length === 0 && ${labels}.length === 0`);
    assert.deepEqual(await evaluate(`${plot}.layout.shapes`), [fitShape]);
    assert.deepEqual(await evaluate(`${plot}.layout.annotations`), [note]);
    assert.equal(await evaluate(`JSON.stringify(${plot}.__spectrumSampling.getSources())`), baseline.data);
    await evaluate(`Plotly.relayout(${plot}, {shapes:${JSON.stringify(baseline.shapes)},
      annotations:${JSON.stringify(baseline.annotations)}, 'xaxis.type':${JSON.stringify(baseline.type)},
      'xaxis.range':${JSON.stringify(baseline.range)}, 'xaxis.autorange':true,
      'yaxis.range':${JSON.stringify(baseline.yRange)}, 'yaxis.autorange':${JSON.stringify(baseline.yAutorange)}}).then(() => null)`);
  }

  async function checkSpectrumDetail(plotId) {
    const plot = `document.getElementById(${JSON.stringify(plotId)})`;
    const control = `document.getElementById(${JSON.stringify(plotId + '-sampling')})`;
    assert(await evaluate(`${plot}.__spectrumSampling.getSources()[0].x.length > 5000`));
    const count = await evaluate(`${plot}.__spectrumSampling.getSources()[0].x.length`);
    const initialType = await evaluate(`${plot}._fullLayout.xaxis.type`);
    await evaluate(`(()=>{const p=${plot}; return Plotly.relayout(p,
      {'xaxis.type':'linear', 'xaxis.range':[4900,5100], 'xaxis.autorange':false}).then(() => null);})()`);
    await waitFor(`${plot}.data[0].x.length < 1000`);
    assert(await evaluate(`(()=>{const p=${plot}, source=p.__spectrumSampling.getSources()[0];
      const expected=source.x.filter(x=>x>=4900 && x<=5100);
      const actual=p.data[0].x.filter(x=>x>=4900 && x<=5100);
      return JSON.stringify(expected)===JSON.stringify(actual) && p.data[0].line.simplify===false;
    })()`));
    // Panning restores a different native region, without touching the source.
    await evaluate(`Plotly.relayout(${plot}, {'xaxis.range':[6400,6600]}).then(() => null)`);
    await waitFor(`${plot}.data[0].x.some(x=>x>=6500) && !${plot}.data[0].x.some(x=>x>=4900 && x<=5100)`);
    await evaluate(`Plotly.relayout(${plot}, {'xaxis.autorange':true}).then(() => null)`);
    await waitFor(`${plot}.data[0].x[0] < 4100 && ${plot}.data[0].x.at(-1) > 6900`);
    await evaluate(`(()=>{const c=${control}; c.value='native'; c.dispatchEvent(new Event('change'));})()`);
    await waitFor(`${plot}.data[0].x.length === ${count}`);
    await evaluate(`(()=>{const c=${control}; c.value='adaptive'; c.dispatchEvent(new Event('change'));})()`);
    await waitFor(`${plot}.data[0].x.length <= 5000`);
    assert.equal(await evaluate(`${plot}.__spectrumSampling.getSources()[0].x.length`), count);
    await evaluate(`Plotly.relayout(${plot}, {'xaxis.type':${JSON.stringify(initialType)}, 'xaxis.autorange':true}).then(() => null)`);
  }

  async function checkVerticalZoom(plotId) {
    const plot = `document.getElementById(${JSON.stringify(plotId)})`;
    const select = `document.getElementById(${JSON.stringify(plotId + '-lines-zoom')})`;
    await evaluate(`window.verticalZoomOriginal = JSON.parse(JSON.stringify({data:${plot}.__spectrumSampling.getSources(), layout:${plot}.layout})); null`);
    const fixture = [
      {name:'Vertical zoom fixture', mode:'lines', x:[4000,6400,6500,6600,6750,7000], y:[1e6,2,2,4,4,1e6],
       error_y:{type:'data', visible:true, symmetric:false, array:[0,0,0.5,3,0,0], arrayminus:[0,0,1,0.5,0,0]}},
      {mode:'lines', visible:'legendonly', x:[6500,6600], y:[1e9,1e9]}
    ];
    await evaluate(`(()=>{const controller=${plot}.__spectrumSampling;
      controller.replaceTrace(0, ${JSON.stringify(fixture[0])});
      controller.appendTrace(${JSON.stringify(fixture[1])}); })()`);
    await evaluate(`Plotly.react(${plot}, ${JSON.stringify(fixture)}, Object.assign({}, window.verticalZoomOriginal.layout,
      {xaxis:{type:'linear'}, yaxis:{type:'linear'}})).then(() => null)`);
    async function replaceFixture(update) {
      await evaluate(`(()=>{const controller=${plot}.__spectrumSampling;
        controller.replaceTrace(0, Object.assign({}, controller.getSources()[0], ${JSON.stringify(update)}));
        return controller.render().then(() => null);})()`);
    }
    async function jump(expected) {
      await evaluate(`(()=>{const select=${select}; select.value=Array.from(select.options).find(o=>o.textContent.startsWith('Hα')).value;
        select.dispatchEvent(new Event('change'));})()`);
      await waitFor(`${plot}._fullLayout.yaxis.range.every((value,index)=>Math.abs(value-${JSON.stringify(expected)}[index])<1e-9)`);
    }
    // Distant peaks and hidden curves must not dominate the line window;
    // asymmetric error bars in the window must remain fully visible.
    await jump([0.7, 7.3]);
    await evaluate(`Plotly.relayout(${plot}, {'yaxis.type':'log'}).then(() => null)`);
    const upper = Math.log10(7);
    await jump([-upper * 0.05, upper * 1.05]);
    await replaceFixture({y:[2,2,2,2,2,2], error_y:{visible:false}});
    await jump([Math.log10(2) - 0.05, Math.log10(2) + 0.05]);
    await evaluate(`Plotly.relayout(${plot}, {'yaxis.type':'linear'}).then(() => null)`);
    await jump([1.9, 2.1]);
    await replaceFixture({y:[null,null,null,null,null,null]});
    await jump([1.9, 2.1]);
    // A sparse line crosses both window edges without any sample inside.
    await replaceFixture({x:[6400,6800], y:[2,10]});
    await jump([1.99228, 8.59228]);
    await replaceFixture({x:[4000,6400,6500,6600,6750,7000], y:[-1,0,null,4,0,-1]});
    await evaluate(`Plotly.relayout(${plot}, {'yaxis.type':'log'}).then(() => null)`);
    await jump([Math.log10(4) - 0.05, Math.log10(4) + 0.05]);
    await evaluate(`(()=>{const controller=${plot}.__spectrumSampling;
      controller.removeTrace(1); controller.replaceTrace(0, window.verticalZoomOriginal.data[0]);
      return Plotly.react(${plot}, window.verticalZoomOriginal.data, window.verticalZoomOriginal.layout)
        .then(() => controller.render()).then(() => null);})()`);
  }

  await open("/view/");
  assert(await evaluate('document.body.textContent.includes("model_a")'));
  for (const file of ["RVTJ", "OBSFLUX", "MOD_SUM"]) {
    await open(`/view/model_a/${file}`);
    assert(await evaluate(`document.body.textContent.includes(${JSON.stringify(file)})`));
    if (file === 'OBSFLUX') {
      await waitFor("!!document.getElementById('plotly-obsflux-combined').__spectralLinesBound");
      await checkSpectralLines('plotly-obsflux-combined');
      await checkSpectrumDetail('plotly-obsflux-combined');
    }
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
  await checkSpectralLines('final-spectrum-plot');
  await checkSpectrumDetail('final-spectrum-plot');
  await evaluate("document.getElementById('final-spectrum-plot-lines-show').click()");
  await evaluate('window.originalX = document.getElementById("final-spectrum-plot").__spectrumSampling.getSources()[0].x[0]');
  await evaluate('var input = document.getElementById("final-spectrum-plot-redshift"); input.value = "0.01"; input.dispatchEvent(new Event("input", {bubbles:true}))');
  await waitFor('Math.abs(document.getElementById("final-spectrum-plot").__spectrumSampling.getSources()[0].x[0] / window.originalX - 1.01) < 1e-8');
  await waitFor("document.getElementById('final-spectrum-plot').layout.shapes.some(s => Math.abs(s.x0 - 6564.614 * 1.01) < 1e-6)");
  await evaluate(`(()=>{const select=document.getElementById('final-spectrum-plot-lines-zoom');
    select.value=Array.from(select.options).find(o=>o.textContent.startsWith('Hα')).value;
    select.dispatchEvent(new Event('change'));})()`);
  await waitFor("document.getElementById('final-spectrum-plot')._fullLayout.xaxis.range.every((value,index)=>Math.abs(Math.pow(10,value)-(6564.614*1.01+(index===0?-150:150)))<1e-6)");
  await evaluate('var input = document.getElementById("final-spectrum-plot-yscale"); input.value = "linear"; input.dispatchEvent(new Event("change"))');
  await waitFor('document.getElementById("final-spectrum-plot").layout.yaxis.type === "linear"');
  await evaluate('document.getElementById("final-spectrum-plot").closest(".plotly-resizable").querySelector(".plot-resize-handle").scrollIntoView({block:"center"})');
  const handle = await evaluate('(()=>{const p=document.getElementById("final-spectrum-plot"); const c=p.closest(".plotly-resizable"); const r=c.querySelector(".plot-resize-handle").getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,height:c.getBoundingClientRect().height};})()');
  await command("Input.dispatchMouseEvent", { type: "mousePressed", x: handle.x, y: handle.y, button: "left", clickCount: 1 });
  await command("Input.dispatchMouseEvent", { type: "mouseMoved", x: handle.x, y: handle.y + 80, button: "left", buttons: 1 });
  await command("Input.dispatchMouseEvent", { type: "mouseReleased", x: handle.x, y: handle.y + 80, button: "left", clickCount: 1 });
  await waitFor(`document.getElementById("final-spectrum-plot").closest(".plotly-resizable").getBoundingClientRect().height > ${handle.height + 40}`);
  await evaluate('document.getElementById("final-spectrum-plot-reset-transform").click()');
  await waitFor('Math.abs(document.getElementById("final-spectrum-plot").__spectrumSampling.getSources()[0].x[0] / window.originalX - 1) < 1e-8');
  await waitFor("document.getElementById('final-spectrum-plot').layout.shapes.some(s => Math.abs(s.x0 - 6564.614) < 1e-6)");

  await open("/bulk/spectra/?selected_models=model_a&selected_models=model_b", "bulk-final-spectrum-plot");
  await checkSpectralLines('bulk-final-spectrum-plot');
  await checkSpectrumDetail('bulk-final-spectrum-plot');
  await evaluate('document.getElementById("bulk-final-spectrum-plot-toggle-final").click()');
  await waitFor('document.getElementById("bulk-final-spectrum-plot").data.filter(t=>t.meta.plot_role==="final").every(t=>t.visible==="legendonly")');
  await open(`/uploads/view/${uploadToken}`, "upload-spectrum-plot");
  await checkSpectralLines('upload-spectrum-plot');
  await checkSpectrumDetail('upload-spectrum-plot');
  await checkVerticalZoom('upload-spectrum-plot');
  await evaluate('var input = document.getElementById("upload-spectrum-plot-xscale"); input.value = "linear"; input.dispatchEvent(new Event("change"))');
  await waitFor('document.getElementById("upload-spectrum-plot").layout.xaxis.type === "linear"');
  assert(await evaluate('!!document.querySelector("#grid-fit-form")'));
  await evaluate(`for (const param of ["redshift", "broadening_km_s", "ebv"]) {
    for (const side of ["min", "max"]) {
      const input = document.querySelector('[name="fit_' + param + '_' + side + '"]');
      if (input) input.value = "0";
    }
  }
  const source = document.getElementById('grid-fit-source');
  source.value = 'bosz'; source.dispatchEvent(new Event('change'));
  document.getElementById('grid-fit-submit').click();`);
  await waitFor('document.getElementById("grid-fit-source").value === "bosz"');
  assert(await evaluate('!document.getElementById("grid-fit-bosz-resolution-note").classList.contains("d-none")'));
  assert(await evaluate('document.getElementById("grid-fit-tlusty-scale-note").classList.contains("d-none") === false'));
  await waitFor('!document.getElementById("grid-fit-result").classList.contains("d-none")');
  assert(await evaluate('document.getElementById("grid-fit-result-body").textContent.includes("ATLAS9 plane-parallel")'));
  await waitFor('document.getElementById("upload-spectrum-plot").data.some(t=>t.meta?.plot_role==="grid_fit_best")');
  await waitFor('!document.getElementById("grid-fit-submit").disabled');
  await evaluate(`const source = document.getElementById('grid-fit-source');
    source.value = 'phoenix'; source.dispatchEvent(new Event('change'));
    document.getElementById('grid-fit-submit').click();`);
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
  await new Promise(resolve => browser.exitCode !== null || browser.signalCode !== null ? resolve() : browser.once("exit", resolve));
  await rm(profile, { recursive: true, force: true });
}
