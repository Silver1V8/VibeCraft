// Regression: real pipeline code must retain local work across page instances,
// without hiding newer server files or mixing projects/features/late responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
function page(storage, project = 'alpha', server = {}) {
  const nodes = {}, requests = [], warnings = [];
  function element() {
    let text = '';
    const classes = new Set();
    return {value: '', hidden: false, disabled: false, children: [], options: [], listeners: {}, style: {},
      classList: {add: key => classes.add(key), remove: key => classes.delete(key),
        toggle(key, enabled) { if (enabled ?? !classes.has(key)) classes.add(key); else classes.delete(key); },
        contains: key => classes.has(key)},
      addEventListener(type, fn) { this.listeners[type] = fn; },
      appendChild(child) { this.children.push(child); }, add(child) { this.options.push(child); },
      set textContent(value) { text = value; this.children = []; }, get textContent() { return text; },
      focus() {}, scrollIntoView() {}, setAttribute() {},
    };
  }
  const node = id => nodes[id] ||= element();
  const context = vm.createContext({URLSearchParams, URL, Date, console, setTimeout, clearTimeout, TextDecoder,
    selectedProjectId: () => project, localStorage: storage,
    document: {getElementById: node, createElement: element, querySelectorAll: () => []},
    window: {addEventListener() {}, __VIBECRAFT_AGENT_API_KEY__: 'SECRET-NEVER-PERSIST'},
    location: {href: 'http://localhost/pipeline'},
    escapeHtml: String, toast: text => warnings.push(text), apiErrorMessage: String,
    retainWorkspaceTask: p => p, registerActions() {},
    confirmDialog: async () => true,
    fetch: async (url, options) => {
      requests.push({url, options});
      const parsed = new URL(url, 'http://localhost');
      let body = {};
      if (parsed.pathname.endsWith('/runners')) return {ok: false};
      if (parsed.pathname.endsWith('/dev-types')) body = {dev_types: ['backend']};
      if (parsed.pathname.endsWith('/status')) body = {files: {}, dev_type: 'backend'};
      if (parsed.pathname.endsWith('/file')) {
        const content = server[parsed.searchParams.get('name')];
        return {ok: content !== undefined, json: async () => ({content})};
      }
      if (parsed.pathname.endsWith('/gate')) body = {gate: {allowed: false}, point_decisions: []};
      if (parsed.pathname.endsWith('/final-prompt')) body = {final_prompt: 'server prompt'};
      if (parsed.pathname.endsWith('/explore/turn')) {
        if (server.turn) return server.turn();
        body = {history: 'model conversation', ai_response: '<img src=x onerror=alert(1)> risposta'};
      }
      if (parsed.pathname.endsWith('/stream') && server.stream) return server.stream();
      return {ok: true, json: async () => body};
    },
  });
  vm.runInContext(source, context);
  return {context, node, nodes, requests, warnings,
    async load(name) { node('feature-name-input').value = name; await context.loadFeatureStatus(); },
    async input(id, value) { node(id).value = value; await node(id).listeners.input?.({target: node(id)}); },
  };
}
function storage() {
  const data = new Map();
  return {data, getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key)};
}
async function browserRecovery() {
  // Optional real DOM check with the already-installed host browser; no download.
  const {chromium} = require('playwright');
  const browser = await chromium.launch({headless: true, ...(process.platform === 'win32' ? {channel: 'msedge'} : {})});
  try {
    const context = await browser.newContext();
    let serverCanvas = 'Canvas server', posts = 0;
    await context.route('http://pipeline.test/**', async route => {
      const url = new URL(route.request().url());
      if (url.pathname.startsWith('/api/')) {
        if (route.request().method() === 'POST') posts++;
        let body = {};
        if (url.pathname.endsWith('/dev-types')) body = {dev_types: ['backend']};
        if (url.pathname.endsWith('/runners')) return route.fulfill({status: 503, json: {}});
        if (url.pathname.endsWith('/status')) body = {files: {canvas: true}, dev_type: 'backend'};
        if (url.pathname.endsWith('/file')) return route.fulfill(url.searchParams.get('name') === 'canvas.md'
          ? {json: {content: serverCanvas}} : {status: 404, json: {}});
        if (url.pathname.endsWith('/gate')) body = {gate: {allowed: false, reasons: []}, point_decisions: []};
        if (url.pathname.endsWith('/explore/turn')) body = {history: 'browser history', ai_response: '<img src=x onerror=alert(1)> risposta'};
        return route.fulfill({json: body});
      }
      const file = url.pathname === '/pipeline' ? '../templates/pipeline.unified.html'
        : url.pathname.startsWith('/static/') ? '..' + url.pathname : null;
      if (!file) return route.fulfill({status: 404, body: ''});
      const mime = file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
      return route.fulfill({contentType: mime, body: fs.readFileSync(path.join(__dirname, file))});
    });
    let tab = await context.newPage();
    const errors = []; tab.on('pageerror', error => errors.push(error.message));
    await tab.goto('http://pipeline.test/pipeline?project=alpha');
    await tab.locator('#feature-name-input').fill('browser-feature');
    await tab.locator('#load-feature-btn').click();
    await tab.waitForFunction(() => !document.querySelector('#dev-type-select').disabled);
    await tab.locator('#dev-type-select').selectOption('backend');
    await tab.locator('[data-click="goToStep"][data-arg="1"]').click();
    await tab.locator('#chat-input').fill('Browser interview');
    await tab.locator('#chat-send-btn').click();
    await tab.waitForFunction(() => document.querySelector('#chat-log').children.length === 2);
    await tab.locator('#chat-input').fill('Browser unsent');
    await tab.locator('[data-click="goToStep"][data-arg="2"]').click();
    await tab.locator('#canvas-md-editor').fill('Browser draft');
    const sent = posts;
    serverCanvas = 'Newer server canvas';
    await tab.close();
    tab = await context.newPage(); tab.on('pageerror', error => errors.push(error.message));
    await tab.goto('http://pipeline.test/pipeline?project=alpha');
    await tab.locator('#session-restore-btn').waitFor({state: 'visible'});
    assert.equal(await tab.locator('#canvas-md-editor').inputValue(), 'Newer server canvas');
    await tab.locator('#session-restore-btn').click();
    assert.equal(await tab.locator('#canvas-md-editor').inputValue(), 'Browser draft');
    assert.equal(await tab.locator('#chat-input').inputValue(), 'Browser unsent');
    assert.equal(await tab.locator('#chat-log img').count(), 0);
    assert.deepEqual(await tab.locator('#chat-log > div').allTextContents(), ['Browser interview', '<img src=x onerror=alert(1)> risposta']);
    assert.equal(posts, sent, 'browser restore never posts');
    await tab.goto('http://pipeline.test/pipeline?project=beta');
    assert.equal(await tab.locator('#feature-name-input').inputValue(), '');
    assert.deepEqual(errors, []);
    console.log('Pipeline recovery: Edge real DOM, page closure, server conflict, safe chat, project isolation passed.');
  } finally {await browser.close();}
}
(async () => {
  const saved = storage();
  const first = page(saved);
  await first.load('payments');
  first.node('dev-type-select').value = 'backend'; first.context.onDevTypeChange();
  first.node('chat-input').value = 'Requisiti pagamento'; await first.context.sendExploreTurn();
  await first.input('chat-input', 'Domanda non inviata');
  await first.input('canvas-md-editor', 'Canvas locale');
  await first.input('spec-md-editor', 'Spec locale');
  first.context.goToStep(3);
  assert.ok(saved.data.size > 0, 'conversation and edits must be persisted before refresh');
  assert.ok(![...saved.data.values()].join('').includes('SECRET-NEVER-PERSIST'));

  const resumed = page(saved, 'alpha', {'canvas.md': 'Canvas server nuovo', 'spec.md': 'Spec server nuova'});
  await settle(); await settle();
  assert.equal(resumed.node('feature-name-input').value, 'payments');
  assert.equal(resumed.node('canvas-md-editor').value, 'Canvas server nuovo', 'new server version stays visible until explicit restore');
  assert.equal(resumed.node('session-restore-btn').hidden, false);
  resumed.context.restorePipelineDraft();
  assert.equal(resumed.node('canvas-md-editor').value, 'Canvas locale');
  assert.equal(resumed.node('spec-md-editor').value, 'Spec locale');
  assert.equal(resumed.node('chat-input').value, 'Domanda non inviata');
  assert.equal(vm.runInContext('exploreHistory', resumed.context), 'model conversation');
  assert.match(vm.runInContext('interviewLog', resumed.context), /Requisiti pagamento/);
  assert.equal(vm.runInContext('currentStep', resumed.context), 3);
  assert.equal(resumed.node('chat-log').children[1].textContent, '<img src=x onerror=alert(1)> risposta');
  assert.equal(resumed.requests.filter(r => r.options?.method === 'POST').length, 0, 'restore never changes server');
  assert.match(resumed.node('session-status').textContent, /locale/i);

  const otherProject = page(saved, 'beta'); await settle();
  await otherProject.load('payments');
  assert.equal(otherProject.node('chat-input').value, '');
  assert.equal(otherProject.node('canvas-md-editor').value, '');
  await resumed.load('other-feature');
  assert.equal(resumed.node('chat-log').children.length, 0);
  assert.equal(resumed.node('spec-md-editor').value, 'Spec server nuova');
  await resumed.load('payments'); resumed.context.restorePipelineDraft();
  assert.equal(resumed.node('chat-input').value, 'Domanda non inviata');

  let release;
  const delayed = page(storage(), 'alpha', {turn: () => new Promise(resolve => {release = resolve;})});
  await delayed.load('first');
  delayed.node('dev-type-select').value = 'backend'; delayed.context.onDevTypeChange();
  delayed.node('chat-input').value = 'late response';
  const sending = delayed.context.sendExploreTurn(); await settle();
  await delayed.load('second');
  release({ok: true, json: async () => ({history: 'OLD', ai_response: 'OLD'})}); await sending;
  assert.equal(delayed.node('chat-log').children.length, 0, 'late reply must not enter another feature');
  assert.equal(vm.runInContext('exploreHistory', delayed.context), '');

  let deliver;
  const streaming = page(storage(), 'alpha', {stream: () => ({ok: true, body: {getReader: () => ({
    read: () => new Promise(resolve => {deliver = resolve;})})}})});
  await streaming.load('stream-A');
  const drift = streaming.context.runDriftCheck(); await settle();
  await streaming.load('stream-B');
  deliver({done: false, value: Buffer.from(JSON.stringify({type: 'result', value: '✅ NESSUN DRIFT A'}) + '\n')});
  await settle(); deliver({done: true}); await drift;
  assert.equal(vm.runInContext('stepStates[4]', streaming.context), 'pending', 'old stream cannot complete another feature');
  assert.equal(streaming.node('drift-report-box').textContent, '');
  for (const id of ['drift-report-card', 'archive-report-card', 'final-prompt-card', 'gate-comparison']) {
    assert.ok(streaming.node(id).classList.contains('hidden'), `${id} must not show previous feature`);
  }
  const interrupted = page(storage(), 'alpha', {stream: () => ({ok: true, body: {getReader: () => ({read: async () => ({done: true})})}})});
  await interrupted.load('archive'); await interrupted.context.runArchive();
  assert.equal(vm.runInContext('stepStates[5]', interrupted.context), 'failed', 'archive requires its terminal event');

  const denied = page({getItem() {throw new Error('denied');}, setItem() {throw new Error('full');}});
  await settle(); await denied.load('usable'); await denied.input('chat-input', 'still editable');
  assert.equal(denied.node('chat-input').value, 'still editable');
  assert.match(denied.node('session-status').textContent, /non disponibile|non salvata/i);
  denied.context.window.__VIBECRAFT_AGENT_API_KEY__ = '';
  denied.node('agent-mode-select').value = 'agentic';
  await denied.context.runWithAgent();
  assert.equal(vm.runInContext('agentRunning', denied.context), false, 'denied key storage must release agent controls');
  assert.equal(denied.node('agent-run-btn').disabled, false);
  assert.match(denied.node('agent-output').textContent, /Errore/);
  vm.runInContext("gateReview = {feature: 'usable', data: {spec_hash: 'hash'}}", denied.context);
  for (const [id, value] of Object.entries({'decision-status': 'accepted', 'decision-point': 'p1', 'decision-reason': 'reviewed', 'decision-by': 'user'})) denied.node(id).value = value;
  await denied.context.recordPointDecision();
  assert.equal(denied.node('decision-submit').disabled, false);
  assert.match(denied.warnings.at(-1), /denied/);
  const corrupt = storage();
  for (const [key, value] of saved.data) corrupt.data.set(key, value.startsWith('{') ? '{broken' : value);
  const invalid = page(corrupt); await settle(); await settle();
  assert.match(invalid.node('session-status').textContent, /non valida|corrott/i);
  console.log('Pipeline recovery: refresh, explicit restore, project/feature isolation, stale replies, unavailable/corrupt storage passed.');
  if (process.env.VIBECRAFT_SESSION_BROWSER === '1') await browserRecovery();
})().catch(error => {console.error(error); process.exitCode = 1;});
