// Real-browser "surprise PDF" click-through: opens the pdf-debugger workbench, sets a
// real file on the #wbFile input via CDP DOM.setFileInputFiles (the same primitive
// Playwright's page.setInputFiles uses under the hood -- a real file, not a curl upload),
// fills the configuration fields, clicks Run, and polls to completion or failure.
//
// Usage:
//   node browser-clickthrough-upload.mjs <pdfPath> <start> <end> <footnote> <controls> \
//     <label> <company> <periodEnd> <currency> <ocrLang> [shotDir] [cdpBase] [appBase]
//
// controls is a comma-separated string, e.g. "10,11" or "" for none.
import fs from 'node:fs';
import path from 'node:path';

const [
  ,, pdfPath, start, end, footnote, controls, label, company, periodEnd, currency, ocrLang,
  shotDirArg, cdpBaseArg, appBaseArg,
] = process.argv;

if (!pdfPath) {
  console.error('usage: node browser-clickthrough-upload.mjs <pdfPath> <start> <end> <footnote> <controls> <label> <company> <periodEnd> <currency> <ocrLang> [shotDir] [cdpBase] [appBase]');
  process.exit(2);
}

const absPdfPath = path.resolve(pdfPath);
if (!fs.existsSync(absPdfPath)) {
  console.error(`PDF not found: ${absPdfPath}`);
  process.exit(2);
}

const cdpBase = cdpBaseArg || 'http://127.0.0.1:9223';
const appBase = appBaseArg || process.env.FTLINK_DEMO_BASE_URL || 'http://127.0.0.1:8199';
const shotDir = shotDirArg || './evidence-shots-upload';

// Guard against accidentally writing screenshots into the sealed deliverable or a
// protected app checkpoint archive dir, regardless of what shotDir is passed.
const workspaceRoot = path.resolve(import.meta.dirname, '..');  // presentation-edition-v1/
const forbidden = [path.join(workspaceRoot, '..', 'v0'), path.join(workspaceRoot, 'app', 'dist')];
const absShotDir = path.resolve(shotDir);
if (forbidden.some(dir => absShotDir === dir || absShotDir.startsWith(dir + path.sep))) {
  console.error(`refusing to write screenshots into a protected directory: ${absShotDir}`);
  process.exit(2);
}
fs.mkdirSync(shotDir, { recursive: true });
const stem = path.basename(absPdfPath, '.pdf');

const target = await fetch(`${cdpBase}/json/new?${encodeURIComponent(appBase + '/pdf-debugger.html')}`, {
  method: 'PUT',
}).then(r => r.json());

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });

let messageId = 0;
const pending = new Map();
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const [resolve, reject] = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(JSON.stringify(message.error)));
  else resolve(message.result);
};
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++messageId;
    pending.set(id, [resolve, reject]);
    socket.send(JSON.stringify({ id, method, params }));
  });
}
const wait = ms => new Promise(r => setTimeout(r, ms));
async function evaluate(expression) {
  const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw new Error(JSON.stringify(response.exceptionDetails, null, 2));
  return response.result.value;
}
async function screenshot(name) {
  const { data } = await send('Page.captureScreenshot', { format: 'png' });
  fs.writeFileSync(`${shotDir}/${stem}-${name}.png`, Buffer.from(data, 'base64'));
}
function setValue(selector, value) {
  const escaped = JSON.stringify(String(value ?? ''));
  return evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); el.value = ${escaped}; el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change')); return el.value; })()`);
}

await send('Page.enable');
await send('Runtime.enable');
await send('DOM.enable');
await wait(1000);

const result = { pdfPath: absPdfPath, config: { start, end, footnote, controls, label, company, periodEnd, currency, ocrLang } };

// Open the workbench (this is also what materializes #wbFile in the DOM).
await evaluate("document.querySelector('#config')?.click()");
await wait(300);
result.workbenchOpenedBeforeUpload = await evaluate("document.querySelector('#workbenchDialog')?.open");
await evaluate("document.querySelector('#wbPreset').value='custom'; document.querySelector('#wbPreset').dispatchEvent(new Event('change'))");
await wait(100);
await screenshot('01-workbench-opened');

// Real file selection via CDP, not a synthetic File object -- this is the same
// primitive Playwright's setInputFiles uses.
const { root } = await send('DOM.getDocument', { depth: -1, pierce: true });
const { nodeId } = await send('DOM.querySelector', { nodeId: root.nodeId, selector: '#wbFile' });
if (!nodeId) throw new Error('#wbFile not found in DOM after opening workbench');
await send('DOM.setFileInputFiles', { files: [absPdfPath], nodeId });
await wait(300);

// Wait for the app's own read-only inspection (POST /api/debugger/inspect-pdf) to land.
let profile = null;
for (let i = 0; i < 60; i++) {
  profile = await evaluate('state.pendingPdfProfile');
  if (profile) break;
  await wait(500);
}
result.inspectedProfile = profile;
await screenshot('02-file-inspected');
if (!profile) {
  result.failedAt = 'inspect-pdf';
  console.log(JSON.stringify(result, null, 2));
  await fetch(`${cdpBase}/json/close/${target.id}`);
  socket.close();
  process.exit(1);
}

await setValue('#wbStart', start);
await setValue('#wbEnd', end);
await setValue('#wbFootnote', footnote);
await setValue('#wbControls', controls);
await setValue('#wbLabel', label);
await setValue('#wbCompany', company);
await setValue('#wbPeriod', periodEnd);
await setValue('#wbCurrency', currency);
await setValue('#wbOcrLang', ocrLang);
await screenshot('03-config-filled');

await evaluate("document.querySelector('#wbRun')?.click()");
await wait(500);
result.startStatus = await evaluate("document.querySelector('#wbStatus')?.textContent");
await screenshot('04-run-started');

// Poll for completion: either the app navigates away (success -> #extracted) or the
// status panel reports an error. Real OCR/model inference, so allow several minutes.
const deadline = Date.now() + 8 * 60 * 1000;
let finalState = 'timeout';
while (Date.now() < deadline) {
  await wait(3000);
  const href = await evaluate('location.href');
  if (href.includes('run=') && href.includes('#extracted')) { finalState = 'navigated'; result.finalHref = href; break; }
  const statusText = await evaluate("document.querySelector('#wbStatus')?.textContent");
  const statusClass = await evaluate("document.querySelector('#wbStatus')?.className");
  result.lastStatusText = statusText;
  if (statusClass && statusClass.includes('error')) { finalState = 'error'; break; }
}
result.finalState = finalState;
await screenshot('05-run-outcome');

if (finalState === 'navigated') {
  await wait(500);
  result.runId = await evaluate('state.run?.run_id');
  result.tables = await evaluate('state.run?.result?.tables?.length');
  result.rows = await evaluate('state.run?.result?.rows?.length');
  result.cells = await evaluate('state.run?.result?.cells?.length');
  result.relations = await evaluate('state.run?.result?.relations?.length');
  result.checksSummary = await evaluate(
    "(() => { const c = state.run?.result?.checks || []; const out = {}; c.forEach(x => out[x.status] = (out[x.status]||0)+1); return out; })()"
  );
  result.sourceSha256 = await evaluate('state.run?.result?.document?.source_sha256');
  // Click through: first relation (if any) and first cell on the page, plus the checks tab.
  const relCount = await evaluate("document.querySelectorAll('.relbtn').length");
  if (relCount > 0) {
    await evaluate("document.querySelectorAll('.relbtn')[0]?.click()");
    await wait(200);
    result.firstRelationSelected = await evaluate('state.selected');
  }
  await screenshot('06-extracted-clickthrough');
}

console.log(JSON.stringify(result, null, 2));

await fetch(`${cdpBase}/json/close/${target.id}`);
socket.close();
