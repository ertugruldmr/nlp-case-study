// Real-browser click-through of the baseline pdf-debugger.html run, driven over CDP
// against an already-running Chrome (see browser-smoke.mjs for the connection pattern).
// This closes the gap every prior checkpoint flagged: verification so far was curl/HTTP
// only, never an actual browser session. Requires: app server on FTLINK_DEMO_BASE_URL
// (default 8199) and Chrome headless with --remote-debugging-port=9223 already running.
import fs from 'node:fs';
import path from 'node:path';

const cdpBase = process.argv[2] || 'http://127.0.0.1:9223';
const appBase = process.env.FTLINK_DEMO_BASE_URL || 'http://127.0.0.1:8199';
const shotDir = process.argv[3] || './evidence-shots-baseline';

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
  fs.writeFileSync(`${shotDir}/${name}.png`, Buffer.from(data, 'base64'));
}

await send('Page.enable');
await send('Runtime.enable');
await send('DOM.enable');
await wait(1200);

const result = {};

result.initialRun = await evaluate('state.run?.run_id');
result.pageLabel = await evaluate("document.querySelector('#pageLabel')?.textContent");
await screenshot('01-baseline-review-loaded');

result.reviewRelations = await evaluate("document.querySelectorAll('.relbtn').length");
await evaluate("document.querySelectorAll('.relbtn')[0]?.click()");
await wait(150);
result.relationSelected = await evaluate('state.selected');
await screenshot('02-baseline-relation-selected');

await evaluate("document.querySelector('#stok')?.click()");
await wait(150);
result.stokSelected = await evaluate('state.selected');
await screenshot('03-baseline-known-error-stok');

await evaluate("document.querySelector('[data-mode=\"debug\"]')?.click()");
await wait(150);
result.debugMode = await evaluate("document.querySelector('#content')?.textContent?.includes('Evidence trace')");
await screenshot('04-baseline-debug-mode');

await evaluate("document.querySelector('[data-mode=\"json\"]')?.click()");
await wait(150);
result.jsonMode = await evaluate("document.querySelector('#content')?.textContent?.includes('Loaded result.json')");
await screenshot('05-baseline-json-mode');

await evaluate("document.querySelector('[data-mode=\"review\"]')?.click()");
await wait(150);

// Page navigation
await evaluate("document.querySelector('#next')?.click()");
await wait(300);
result.pageAfterNext = await evaluate("document.querySelector('#pageLabel')?.textContent");
await screenshot('06-baseline-next-page');

// Open the configuration workbench (the entry point for a new/unseen PDF)
await evaluate("document.querySelector('#config')?.click()");
await wait(300);
result.workbenchOpen = await evaluate("document.querySelector('#workbenchDialog')?.open");
await screenshot('07-baseline-workbench-open');
result.presetOptions = await evaluate(
  "[...document.querySelectorAll('#wbPreset option')].map(o => o.value)"
);
await evaluate("document.querySelector('#workbenchDialog')?.close()");

console.log(JSON.stringify(result, null, 2));

await fetch(`${cdpBase}/json/close/${target.id}`);
socket.close();
