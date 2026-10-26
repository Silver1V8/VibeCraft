// API simulate, template/static reali, nessun provider. NODE_PATH deve includere Playwright.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const http = require('node:http');
const { t } = require('./i18n_stub.cjs');

async function intakeApprovalChecks() {
  const source = fs.readFileSync(path.join(__dirname, '../static/pages/intake.js'), 'utf8');
  const code = source.slice(source.indexOf('    let reviewInFlight'), source.indexOf('    /* Raffinazione LLM'));
  const nodes = {
    'preview-categoria': { value: '04_knowledge_informative' },
    'preview-nomefile': { value: 'one.md' }, 'preview-result': {},
  };
  const calls = [], refreshed = [], timers = [];
  let ok = true;
  const context = vm.createContext({
    t,
    document: { getElementById: id => nodes[id], querySelectorAll: () => [] },
    window: { parent: { refreshIndexStatus: id => refreshed.push(id) } },
    selectedProjectId: () => 'project-A', refreshStaging() {}, closePreview() {},
    apiErrorMessage: detail => detail, setTimeout: fn => timers.push(fn),
    fetch: async (url, options) => {
      calls.push({ url, options });
      return { ok, json: async () => ok ? { status: 'approved', reindex: {} } : { detail: 'File esistente' } };
    },
  });
  vm.runInContext(code, context);
  await context.approveStaged('one');
  nodes['preview-nomefile'].value = 'two.md';
  await context.approveStaged('two');
  assert.deepEqual(refreshed, ['project-A', 'project-A']);
  assert.deepEqual(calls.map(call => call.url), ['/api/intake/staged/one/approve', '/api/intake/staged/two/approve']);
  assert.match(nodes['preview-result'].textContent, /Aggiorna indice/);
  assert.equal(nodes['preview-result'].className, 'msg-ok');
  ok = false;
  await context.approveStaged('three');
  assert.equal(nodes['preview-result'].className, 'msg-err');
  assert.equal(refreshed.length, 2);
  assert.equal(timers.length, 2);
  console.log('OK intake: approvazioni separate, stato aggiornato sul progetto del frame, nessun reindex automatico.');
}

async function fetchChecks() {
  const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8');
  const source = shared.slice(shared.indexOf('const API_KEY_STORAGE'), shared.indexOf('const prefersReducedMotion'));
  const calls = [];
  let retry = false, promptProject, promptHeaders, promptUrl;
  const location = { href: 'http://localhost/?project=legacy', origin: 'http://localhost' };
  const storage = new Map();
  const context = vm.createContext({ URL, Request, Headers, AbortController, Promise, location, t,
    localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    sessionStorage: { getItem: () => 'legacy' },
    document: { baseURI: location.href, querySelector: () => null },
    window: { location, frameElement: null, prompt: () => {
      location.href = 'http://localhost/?project=' + 'b'.repeat(32);
      promptProject = location.href;
      if (promptHeaders) promptHeaders.set('X-VibeCraft-Project', 'b'.repeat(32));
      if (promptUrl) promptUrl.href = 'https://external.example/api/pipeline/status';
      return 'retry-key';
    }, fetch: async (input, init) => {
      const request = new Request(input instanceof URL ? input.href : typeof input === 'string' ? new URL(input, location.origin) : input, init);
      calls.push({ request, body: request.method === 'POST' ? await request.text() : null });
      return { status: retry && calls.length === 1 ? 401 : 200 };
    } },
  });
  vm.runInContext(source, context);
  await context.window.fetch('/api/pipeline/status');
  assert.equal(calls[0].request.headers.get('X-VibeCraft-Project'), 'legacy');
  calls.length = 0;
  retry = true;
  const controller = new AbortController();
  const req = new Request('http://localhost/api/pipeline/file', {
    method: 'POST', body: 'request-body', headers: { 'Content-Type': 'text/plain', 'X-Custom': 'kept' }, signal: controller.signal,
  });
  await context.window.fetch(req);
  assert.ok(promptProject);
  assert.equal(calls.length, 2);
  for (const call of calls) {
    assert.equal(call.body, 'request-body');
    assert.equal(call.request.headers.get('X-Custom'), 'kept');
    assert.equal(call.request.headers.get('X-VibeCraft-Project'), 'legacy');
  }
  controller.abort();
  assert.ok(calls.every(call => call.request.signal.aborted));
  calls.length = 0;
  promptHeaders = new Headers({ 'X-VibeCraft-Project': 'a'.repeat(32) });
  await context.window.fetch('/api/pipeline/file', { method: 'POST', body: 'init-body', headers: promptHeaders });
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.body === 'init-body' && call.request.headers.get('X-VibeCraft-Project') === 'a'.repeat(32)));
  retry = false;
  await context.window.fetch(new URL('http://localhost/api/pipeline/status'), { headers: { 'X-VibeCraft-Project': 'a'.repeat(32) } });
  assert.equal(calls.at(-1).request.headers.get('X-VibeCraft-Project'), 'a'.repeat(32));
  calls.length = 0;
  retry = true;
  location.href = 'http://localhost/?project=' + 'a'.repeat(32);
  promptUrl = new URL('http://localhost/api/pipeline/status');
  await context.window.fetch(promptUrl);
  assert.equal(promptUrl.origin, 'https://external.example');
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.request.url === 'http://localhost/api/pipeline/status'),
    'URL mutated during 401 must keep the captured target for both attempts');
  assert.ok(calls.every(call => call.request.headers.get('X-VibeCraft-Project') === 'a'.repeat(32)));
  assert.ok(calls.every(call => call.request.headers.get('X-API-Key')));
  promptUrl = null;
  retry = false;
  await context.window.fetch(new URL('https://example.test/api/pipeline/status'));
  assert.equal(calls.at(-1).request.headers.get('X-VibeCraft-Project'), null);
  assert.equal(calls.at(-1).request.headers.get('X-API-Key'), null);
  await context.window.fetch('/api/projects');
  assert.equal(calls.at(-1).request.headers.get('X-VibeCraft-Project'), null);
  console.log('OK fetch: string/URL/Request, body/header/signal, retry originario, URL esterna e management globale.');
}

async function queryErrorChecks() {
  const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8');
  const dashboard = fs.readFileSync(path.join(__dirname, '../static/pages/dashboard.js'), 'utf8');
  const analysis = fs.readFileSync(path.join(__dirname, '../static/pages/graph_analysis.js'), 'utf8');
  const sharedHelpers = shared.slice(shared.indexOf('function escapeHtml('), shared.indexOf('/* ──────────── THEME VAR'));
  const submit = dashboard.slice(dashboard.indexOf('    async function submitQuery()'), dashboard.indexOf('    /* Submit on Ctrl+Enter.'));
  const impact = analysis.slice(analysis.indexOf('    async function loadImpact()'), analysis.indexOf('    let rippleNodes'));
  const graphQuery = analysis.slice(analysis.indexOf('    async function loadRelations()'),
    analysis.indexOf('    let lastImpactData'));
  for (const [status, detail, expected] of [
    [409, { code: 'project_not_indexed', message: 'Project has no index.' }, 'Project has no index.'],
    [503, { code: 'project_storage_error', message: 'Project storage unavailable.' }, 'Project storage unavailable.'],
    [400, 'Legacy error', 'Legacy error'],
    [500, undefined, 'HTTP 500'],
  ]) {
    const nodes = {};
    const node = id => nodes[id] ||= { value: id === 'question-input' ? 'Question' : '5', textContent: '',
      classList: { add() {}, remove() {} } };
    let loading;
    const context = vm.createContext({ document: { getElementById: node }, console, t,
      showLoader: value => { loading = value; }, setStatus() {}, showAnswerPanel() {},
      fetch: async () => ({ ok: false, status, json: async () => ({ detail }) }),
    });
    vm.runInContext(sharedHelpers + submit + impact + graphQuery, context);
    await context.submitQuery();
    assert.equal(node('answer-text').textContent, '❌ Errore: ' + expected, 'Dashboard project error must be readable');
    assert.equal(loading, false);
    await context.loadImpact();
    assert.equal(node('ripple-status').textContent, '❌ ' + expected, 'Graph impact project error must be readable');
    await context.loadRelations();
    assert.equal(node('rel-status').textContent, '❌ ' + expected, 'Graph relations project error must be readable');
  }
  console.log('OK query errors: dashboard/graph, 409 no index, 503 storage, legacy string e HTTP fallback.');
}

async function browserChecks() {
  const { chromium } = require('playwright');
  const root = path.join(__dirname, '..');
  const streams = new Map();
  let localBind = true;
  const templates = { '/': 'dashboard.unified.html', '/pipeline': 'pipeline.unified.html', '/intake': 'intake.unified.html',
    '/analysis': 'graph_analysis.unified.html', '/eval': 'eval_trend.unified.html', '/infografica': 'infografica.unified.html' };
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/ask') {
      const project = req.headers['x-vibecraft-project'];
      res.setHeader('Content-Type', 'application/x-ndjson');
      res.write(JSON.stringify({ type: 'delta', text: `First chunk ${project}` }) + '\n');
      streams.set(project, () => res.end(JSON.stringify({ type: 'result', value: { answer: `Answer ${project}`, qdrant_scores: [] } }) + '\n'));
      return;
    }
    const file = url.pathname.startsWith('/static/') ? path.join(root, url.pathname.slice(1))
      : path.join(root, 'templates', url.searchParams.get('workspace') === '1' ? templates[url.pathname] || 'workspace.html' : 'workspace.html');
    if (!file.startsWith(root) || !fs.existsSync(file)) { res.writeHead(404); return res.end(); }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'");
    const content = fs.readFileSync(file);
    res.end(file.endsWith('.html') ? content.toString().replace('<head>', `<head><meta name="vibecraft-local-bind" content="${localBind}">`).replace('<html lang="it">', '<html lang="it" data-theme="matrix">') : content);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  try {
    const context = await browser.newContext();
    const A = 'legacy', B = 'b'.repeat(32), C = 'c'.repeat(32);
    const projects = [{ id: A, legacy: false, name: '<img src=x onerror=alert(1)>', index_status: 'ready', stale: false, index_version: '1' },
      { id: B, name: 'B', index_status: 'not_indexed', stale: null, index_version: null },
      { id: C, name: 'C', index_status: 'indexing', stale: true, index_version: '1' }];
    const errors = [], requests = [];
    let readOnly = false, finishJob = false, queryError;
    let indexFinished = false, indexStartError = false, indexPollError = false, indexReloadReady = false;
    let indexResultStatus = 'completed';
    let invalidMapResponse = false;
    const indexPosts = [];
    context.on('page', page => { page.on('pageerror', error => errors.push(error.message));
      page.on('console', msg => { if (msg.text().includes('Content Security Policy')) errors.push(msg.text()); }); });
    await context.route('**/ask', async route => {
      const project = route.request().headers()['x-vibecraft-project'];
      requests.push({ path: '/ask', project });
      if (queryError) return route.fulfill({ status: queryError.status, json: { detail: queryError.detail } });
      await route.continue();
    });
    await context.route('**/api/**', async route => {
      const request = route.request(), url = new URL(request.url());
      requests.push({ path: url.pathname, project: request.headers()['x-vibecraft-project'] });
      if (queryError && ['/api/graph/query', '/api/graph/impact', '/api/graph/semantic-map'].includes(url.pathname)) {
        return route.fulfill({ status: queryError.status, json: { detail: queryError.detail } });
      }
      let body = {};
      if (url.pathname === '/api/index/reindex' && request.method() === 'POST') {
        indexPosts.push({ project: request.headers()['x-vibecraft-project'], body: request.postDataJSON() });
        if (indexStartError) return route.fulfill({ status: 409, json: { detail: { message: 'Indice occupato' } } });
        body = { job_id: 'index-job', status: 'running' };
      }
      if (url.pathname === '/api/reindex/index-job') {
        if (indexPollError) return route.fulfill({ status: 503, json: { detail: 'Servizio temporaneamente indisponibile' } });
        body = { status: indexFinished ? indexResultStatus : 'running', reload_status: indexReloadReady ? 'completed' : 'pending' };
        if (indexFinished && indexReloadReady && indexResultStatus === 'completed') Object.assign(projects.find(p => p.id === request.headers()['x-vibecraft-project']), { index_status: 'ready', stale: false });
      }
      if (url.pathname === '/api/graph/semantic-map') body = invalidMapResponse ? {} : { points: [
        { id: 'a#0', doc_id: 'a', x: -0.5, y: 0.5, community: 0 },
        { id: 'b#0', doc_id: 'b', x: 0.5, y: -0.5, community: 1 },
      ], duplicates: [] };
      if (url.pathname === '/api/projects' && request.method() === 'GET') body = { projects, read_only: readOnly };
      else if (url.pathname === '/api/projects' || url.pathname === '/api/projects/register') {
        const data = request.postDataJSON();
        if (data.name === 'bad') return route.fulfill({ status: 409, json: { detail: { code: 'conflict', message: 'Nome non disponibile' } } });
        body = { id: 'd'.repeat(32), name: data.name || 'Opened', index_status: 'not_indexed', stale: null, index_version: null };
        projects.push(body);
      } else if (url.pathname.startsWith('/api/projects/')) body = projects.find(p => p.id === url.pathname.split('/').at(-1));
      if (url.pathname === '/api/intake/project/browse-path') body = { path: 'C:\\mounted\\existing' };
      if (url.pathname === '/api/graph/all') body = { nodes: [], edges: [] };
      if (url.pathname === '/api/intake/staged') body = { items: [] };
      if (url.pathname === '/api/intake/generate') body = { job_id: 'project-job', status: 'running' };
      if (url.pathname === '/api/intake/generate/project-job') body = { job_id: 'project-job', status: finishJob ? 'completed' : 'running', result: { staged: [] } };
      await route.fulfill({ json: body || {} });
    });
    const page = await context.newPage(), other = await context.newPage();
    await page.goto(base + '/?project=' + A);
    await other.goto(base + '/?project=' + B);
    await page.waitForFunction(id => document.getElementById('project-select').value === id, A);
    await other.waitForFunction(id => document.getElementById('project-select').value === id, B);
    assert.equal(await page.locator('#project-select').inputValue(), A);
    assert.equal(await other.locator('#project-select').inputValue(), B);
    assert.equal(await page.locator('#project-select option').first().textContent(), projects[0].name);
    assert.equal(await page.locator('#project-bar img').count(), 0);
    const frameA = page.frameLocator(`iframe[data-project-id="${A}"][data-workspace-page="/"]`);
    await frameA.locator('#question-input').fill('A question');
    await frameA.locator('#ask-btn').click();
    await page.waitForFunction(id => document.querySelector('iframe').contentDocument.getElementById('answer-text').textContent === `First chunk ${id}`, A);
    assert.equal(await page.locator('iframe').evaluate(frame => frame.contentWindow.workspaceIsBusy()), true);
    await page.locator('#project-home').click();
    await page.locator('#project-welcome').waitFor();
    assert.equal(await page.locator('#workspace-pages iframe').count(), 1);
    assert.equal(await page.locator('iframe').evaluate(frame => frame.contentWindow.workspaceIsBusy()), true);
    assert.equal(await page.locator('#project-list img').count(), 0);
    await page.locator(`#project-list button[data-arg="${A}"]`).click();
    assert.equal(await frameA.locator('#question-input').inputValue(), 'A question');
    await page.locator('#project-select').selectOption(B);
    const frameB = page.frameLocator(`iframe[data-project-id="${B}"][data-workspace-page="/"]`);
    await frameB.locator('#question-input').fill('B question');
    await frameB.locator('#ask-btn').click();
    await page.waitForFunction(id => document.querySelector(`iframe[data-project-id="${id}"]`).contentDocument.getElementById('answer-text').textContent === `First chunk ${id}`, B);
    await page.locator('#project-select').selectOption(C);
    await page.locator('#workspace-message').filter({ hasText: 'operazioni' }).waitFor();
    assert.equal(await page.locator('#project-select').inputValue(), B);
    assert.equal(await page.locator('#workspace-pages iframe').count(), 2);
    streams.get(A)();
    await page.waitForFunction(id => document.querySelector(`iframe[data-project-id="${id}"]`).contentDocument.getElementById('answer-text')?.textContent === `Answer ${id}`, A);
    assert.equal(await frameB.locator('#question-input').inputValue(), 'B question');
    await page.locator('#project-select').selectOption(A);
    assert.equal(await frameA.locator('#question-input').inputValue(), 'A question');
    await page.locator('#workspace-nav a').filter({ hasText: 'Intake' }).click();
    const intakeA = page.frameLocator(`iframe[data-project-id="${A}"][data-workspace-page="/intake"]`);
    await intakeA.locator('#gen-descrizione').fill('Job A');
    await intakeA.locator('#gen-btn').click();
    await intakeA.locator('#gen-status').filter({ hasText: 'Generazione in corso' }).waitFor();
    await page.locator('#project-select').selectOption(B);
    await page.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, B);
    await page.locator('#project-select').selectOption(C);
    await page.locator('#workspace-message').filter({ hasText: 'operazioni' }).waitFor();
    assert.equal(await page.locator('#project-select').inputValue(), B);
    finishJob = true;
    await page.waitForFunction(id => document.querySelector(`iframe[data-project-id="${id}"][data-workspace-page="/intake"]`).contentDocument.getElementById('gen-status').textContent === 'Generazione completata.', A);
    streams.get(B)();
    await page.waitForFunction(id => !document.querySelector(`iframe[data-project-id="${id}"][data-workspace-page="/"]`).contentDocument.getElementById('ask-btn').disabled, B);
    await page.goBack();
    await page.waitForFunction(id => document.getElementById('project-select').value === id, A);
    await page.goForward();
    await page.waitForFunction(id => document.getElementById('project-select').value === id, B);
    await page.locator('#project-select').selectOption(C);
    await page.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, C);
    assert.equal(new Set(await page.locator('iframe').evaluateAll(frames => frames.map(f => f.dataset.projectId))).size, 2);
    await page.reload();
    await page.waitForFunction(id => document.getElementById('project-select').value === id, C);
    assert.equal(await page.locator('#project-select').inputValue(), C);
    assert.equal(await other.locator('#project-select').inputValue(), B);
    await other.reload();
    await other.waitForFunction(id => document.getElementById('project-select').value === id, B);
    assert.equal(await other.locator('#project-select').inputValue(), B);
    await other.goto(base);
    await other.locator('#project-welcome').waitFor();
    assert.equal(new URL(other.url()).searchParams.has('project'), false);
    assert.equal(await other.locator('iframe').count(), 0);
    await other.locator(`#project-list button[data-arg="${B}"]`).click();
    await other.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, B);
    const chooser = await context.newPage();
    await chooser.emulateMedia({ reducedMotion: 'no-preference' });
    await chooser.goto(base);
    await chooser.locator('#project-welcome').waitFor();
    const rain = chooser.locator('#matrix-rain');
    assert.equal(await rain.count(), 1, 'The welcome screen must include the shared rain canvas');
    await rain.waitFor({ state: 'visible' });
    await chooser.waitForFunction(() => {
      const canvas = document.getElementById('matrix-rain');
      const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
      return pixels.some((value, index) => index % 4 === 1 && value > pixels[index - 1]);
    });
    const rainChanges = () => rain.evaluate(async canvas => {
      const before = canvas.toDataURL();
      await new Promise(resolve => setTimeout(resolve, 150));
      return canvas.toDataURL() !== before;
    });
    assert.equal(await rainChanges(), true, 'Rain on must animate the welcome background');
    await chooser.locator('#motion-toggle').click();
    assert.equal(await rainChanges(), false, 'Rain off must stop the animation');
    await chooser.locator('#motion-toggle').click();
    assert.equal(await rainChanges(), true, 'Rain must resume when switched back on');
    await chooser.locator('#theme-switcher').selectOption('classic');
    await rain.waitFor({ state: 'hidden' });
    assert.equal(await rainChanges(), false, 'Classic theme must stop the animation');
    await chooser.emulateMedia({ reducedMotion: 'reduce' });
    await chooser.locator('#theme-switcher').selectOption('matrix');
    await rain.waitFor({ state: 'visible' });
    assert.equal(await rainChanges(), true, 'Explicit Rain on must override reduced motion');
    assert.equal(await chooser.locator('#project-list button').count(), 3);
    assert.equal(await chooser.locator('#project-list img').count(), 0, 'Project names must remain text on the welcome screen');
    await chooser.locator('#project-search').fill('nessun risultato');
    await chooser.locator('#project-list-empty').filter({ hasText: 'Nessun progetto' }).waitFor();
    assert.equal(await chooser.locator('#project-list button').count(), 0);
    assert.equal(await chooser.locator('iframe').count(), 0);
    await chooser.close();
    await page.locator('#project-select').selectOption(B);
    const indexButton = page.locator('#project-index-update');
    await indexButton.filter({ hasText: 'Crea indice' }).waitFor();
    await indexButton.click();
    assert.equal(await indexButton.isDisabled(), true);
    await page.waitForFunction(() => document.getElementById('project-index-status').textContent.includes('Indicizzazione'));
    assert.deepEqual(indexPosts.at(-1), { project: B, body: { full: true } });
    await page.locator('#project-select').selectOption(A);
    await indexButton.waitFor({ state: 'hidden' });
    indexPollError = true;
    await page.locator('#toast-host').filter({ hasText: 'Servizio temporaneamente indisponibile' }).waitFor();
    await page.locator('#project-select').selectOption(B);
    assert.equal(await indexButton.isDisabled(), true, 'Polling errors must not permit duplicate index jobs');
    await page.locator('#project-select').selectOption(A);
    indexPollError = false;
    const pendingReload = page.waitForResponse(async response => new URL(response.url()).pathname === '/api/reindex/index-job'
      && (await response.json()).status === 'completed' && (await response.json()).reload_status === 'pending');
    indexFinished = true;
    await pendingReload;
    await page.locator('#project-select').selectOption(B);
    await page.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, B);
    assert.equal(await indexButton.isDisabled(), true, 'Completion must wait for the new snapshot to be loaded');
    await page.locator('#project-select').selectOption(A);
    indexReloadReady = true;
    await page.locator('#toast-host').filter({ hasText: 'Indice aggiornato' }).waitFor();
    assert.equal(await indexButton.isVisible(), false, 'Background completion must not change the selected project');
    assert.ok(requests.filter(r => r.path === '/api/reindex/index-job').every(r => r.project === B));
    projects[0].stale = true;
    await page.evaluate(() => refreshIndexStatus());
    await indexButton.filter({ hasText: 'Aggiorna indice' }).waitFor();
    indexStartError = true;
    await indexButton.click();
    await page.locator('#toast-host').filter({ hasText: 'Indice occupato' }).waitFor();
    assert.equal(await indexButton.isEnabled(), true);
    assert.deepEqual(indexPosts.at(-1), { project: A, body: {} });
    indexStartError = false;
    await indexButton.click();
    await indexButton.waitFor({ state: 'hidden' });
    await page.locator('#project-select').selectOption(C);
    await page.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, C);
    assert.equal(await indexButton.isDisabled(), true, 'An existing index job must disable the action');
    await page.locator('#project-select').selectOption(B);
    await page.waitForFunction(id => new URL(location.href).searchParams.get('project') === id, B);
    projects[1].stale = null;
    await page.evaluate(() => refreshIndexStatus());
    assert.equal(await indexButton.isVisible(), true, 'Unknown alignment must allow updating the index');
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.setViewportSize({ width: 1280, height: 720 });
    if (process.env.VIBECRAFT_SCREENSHOT_DIR) {
      const output = process.env.VIBECRAFT_SCREENSHOT_DIR;
      fs.mkdirSync(output, { recursive: true });
      const visual = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
      const samples = projects.map((project, index) => ({ ...project,
        name: ['VibeCraft', 'Portale clienti', 'Servizi API'][index], root: `C:\\Progetti\\${['vibecraft', 'portale-clienti', 'servizi-api'][index]}` }));
      await visual.route('**/api/**', route => {
        const pathname = new URL(route.request().url()).pathname;
        const body = pathname === '/api/projects' ? { projects: samples, read_only: false }
          : samples.find(project => pathname === '/api/projects/' + project.id) || {};
        return route.fulfill({ json: body });
      });
      const preview = await visual.newPage();
      preview.on('pageerror', error => errors.push(error.message));
      await preview.goto(base);
      await preview.locator('#project-list button').first().waitFor();
      for (const theme of ['classic', 'matrix']) {
        await preview.locator('#theme-switcher').selectOption(theme);
        // Il CSS reduced-motion conserva transizioni di 0.01ms: attendere il paint
        // effettivo evita screenshot con font nuovo e colori del frame precedente.
        await preview.waitForFunction(background => getComputedStyle(document.body).backgroundColor === background,
          theme === 'classic' ? 'rgb(2, 6, 23)' : 'rgb(4, 20, 10)', { timeout: 3000 });
        const font = await preview.locator('body').evaluate(body => getComputedStyle(body).fontFamily);
        assert.ok(font.includes(theme === 'classic' ? 'Inter' : 'JetBrains Mono'), 'Welcome must inherit the app typography');
        const palette = await preview.evaluate(() => ({
          token: getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim(),
          background: getComputedStyle(document.body).backgroundColor,
        }));
        assert.equal(palette.token, theme === 'classic' ? '#020617' : '#04140a', JSON.stringify(palette));
        assert.equal(palette.background, theme === 'classic' ? 'rgb(2, 6, 23)' : 'rgb(4, 20, 10)', JSON.stringify(palette));
        await preview.screenshot({ path: path.join(output, `welcome-${theme}.png`) });
      }
      await preview.locator('#theme-switcher').selectOption('classic');
      await preview.waitForFunction(() => getComputedStyle(document.body).backgroundColor === 'rgb(2, 6, 23)');
      await preview.setViewportSize({ width: 390, height: 844 });
      assert.equal(await preview.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Mobile welcome must not overflow');
      await preview.screenshot({ path: path.join(output, 'welcome-mobile.png') });
      await preview.setViewportSize({ width: 1280, height: 900 });
      await preview.locator(`#project-list button[data-arg="${A}"]`).click();
      await preview.frameLocator('iframe').locator('#question-input').waitFor();
      await preview.evaluate(() => setUiTheme('classic'));
      assert.equal(await preview.locator('#workspace-theme').isVisible(), true, 'The theme control lives in the workspace shell');
      assert.equal(await preview.frameLocator('iframe').locator('#theme-switcher, .app-nav').count(), 0, 'Pages must not duplicate shell controls');
      assert.ok((await preview.locator('#project-select').evaluate(el => getComputedStyle(el).fontFamily)).includes('Inter'));
      await preview.screenshot({ path: path.join(output, 'workspace-classic.png') });
      await preview.setViewportSize({ width: 390, height: 844 });
      assert.equal(await preview.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, 'Mobile project bar must not overflow');
      await preview.screenshot({ path: path.join(output, 'workspace-mobile.png') });
      await preview.locator('#project-home').click();
      await preview.goBack();
      await preview.frameLocator('iframe').locator('#question-input').waitFor();
      assert.equal(await preview.locator('#project-welcome').isVisible(), false);
      await preview.goForward();
      await preview.locator('#project-welcome').waitFor();
      await visual.close();
    }
    const unknown = await context.newPage();
    await unknown.goto(base + '/?project=' + 'e'.repeat(32));
    await unknown.locator('#workspace-message').filter({ hasText: 'Progetto non disponibile' }).waitFor();
    assert.equal(await unknown.locator('iframe').count(), 0);
    await unknown.close();
    await page.locator('#project-new').click();
    await page.locator('#project-input').fill('bad');
    await page.locator('#project-submit').click();
    await page.locator('#project-error').filter({ hasText: 'Nome non disponibile' }).waitFor();
    await page.locator('#project-input').fill('Created');
    await page.locator('#project-input').press('Enter');
    await page.waitForFunction(() => document.getElementById('project-select').selectedOptions[0]?.textContent === 'Created');
    await page.locator('#project-open').click();
    await page.locator('#project-browse').click();
    await page.waitForFunction(() => document.getElementById('project-input').value === 'C:\\mounted\\existing');
    assert.equal(await page.locator('#project-input').inputValue(), 'C:\\mounted\\existing');
    await page.locator('#project-submit').click();
    await page.waitForFunction(() => document.getElementById('project-select').selectedOptions[0]?.textContent === 'Opened');
    const errorPage = await context.newPage();
    await errorPage.goto(base + '/?project=' + B);
    const errorDashboard = errorPage.frameLocator(`iframe[data-project-id="${B}"][data-workspace-page="/"]`);
    for (const [status, code, message] of [[409, 'project_not_indexed', 'Project has no index.'],
      [503, 'project_storage_error', 'Project storage unavailable.']]) {
      queryError = { status, detail: { code, message } };
      await errorDashboard.locator('#question-input').fill('Unavailable project');
      await errorDashboard.locator('#ask-btn').click();
      await errorDashboard.locator('#answer-text').filter({ hasText: '❌ Errore: ' + message }).waitFor();
      assert.equal(await errorDashboard.locator('#ask-btn').isDisabled(), false);
    }
    await errorPage.locator('#workspace-nav a[href*="/analysis"]').click();
    const errorAnalysis = errorPage.frameLocator(`iframe[data-project-id="${B}"][data-workspace-page="/analysis"]`);
    await errorAnalysis.locator('#map-status').filter({ hasText: 'Project storage unavailable.' }).waitFor();
    queryError = null;
    invalidMapResponse = true;
    await errorAnalysis.locator('[data-click="loadSemanticMap"]').click();
    await errorAnalysis.locator('#map-status').filter({ hasText: 'Dati della mappa non validi' }).waitFor();
    await errorAnalysis.locator('#map-canvas').evaluate(() => window.dispatchEvent(new Event('resize')));
    invalidMapResponse = false;
    await errorAnalysis.locator('[data-click="loadSemanticMap"]').click();
    await errorAnalysis.locator('#map-status').filter({ hasText: '2 documenti' }).waitFor();
    assert.ok(await errorAnalysis.locator('#map-canvas').evaluate(canvas => canvas.width > 0 && canvas.getContext('2d')
      .getImageData(0, 0, canvas.width, canvas.height).data.some((value, index) => index % 4 === 3 && value > 0)), 'Semantic map must draw visible points');
    projects[1].stale = false;
    queryError = { status: 409, detail: { code: 'project_vectors_missing', message: 'Ricostruisci indice' } };
    await errorAnalysis.locator('[data-click="loadSemanticMap"]').click();
    await errorAnalysis.locator('#map-status').filter({ hasText: 'Ricostruisci indice' }).waitFor();
    await errorPage.evaluate(() => refreshIndexStatus());
    await errorPage.locator('#project-index-update').filter({ hasText: 'Ricostruisci indice' }).waitFor();
    queryError = null;
    await errorPage.locator('#project-index-update').click();
    assert.deepEqual(indexPosts.at(-1), { project: B, body: { full: true } });
    await errorPage.locator('#project-index-update').waitFor({ state: 'hidden' });
    projects[1].stale = true;
    await errorPage.evaluate(() => refreshIndexStatus());
    indexResultStatus = 'completed_not_promoted';
    await errorPage.locator('#project-index-update').click();
    await errorPage.locator('#toast-host').filter({ hasText: 'non attivato' }).waitFor();
    assert.equal(await errorPage.locator('#project-index-update').isEnabled(), true);
    queryError = { status: 503, detail: { code: 'project_storage_error', message: 'Project storage unavailable.' } };
    await errorAnalysis.locator('#node-search').fill('same.md');
    await errorAnalysis.locator('[data-click="selectSearchedNode"]').click();
    await errorAnalysis.locator('#rel-status').filter({ hasText: '❌ Project storage unavailable.' }).waitFor();
    queryError = { status: 409, detail: { code: 'project_not_indexed', message: 'Project has no index.' } };
    await errorAnalysis.locator('[data-click="selectSearchedNode"]').click();
    await errorAnalysis.locator('#ripple-status').filter({ hasText: '❌ Project has no index.' }).waitFor();
    queryError = null;
    await errorPage.close();
    readOnly = true;
    await page.reload();
    await page.waitForFunction(() => document.getElementById('project-new').disabled);
    assert.equal(await page.locator('#project-open').isDisabled(), true);
    assert.equal(await page.locator('#project-index-update').isVisible(), false, 'Reader mode must hide index writes');
    await page.locator('#project-home').click();
    assert.equal(await page.locator('#welcome-new').isDisabled(), true);
    assert.equal(await page.locator('#welcome-open').isDisabled(), true);
    await page.locator('#project-read-only').waitFor();
    projects.length = 0;
    readOnly = false;
    const empty = await context.newPage();
    await empty.goto(base);
    await empty.locator('#project-list-empty').filter({ hasText: 'Nessun progetto' }).waitFor();
    assert.equal(await empty.locator('iframe').count(), 0);
    await empty.locator('#welcome-open').click();
    await empty.locator('#project-browse').click();
    await empty.waitForFunction(() => document.getElementById('project-input').value === 'C:\\mounted\\existing');
    assert.equal(await empty.locator('#project-input').inputValue(), 'C:\\mounted\\existing');
    await empty.locator('#project-input').press('Escape');
    assert.equal(await empty.locator('#project-dialog').isVisible(), false);
    assert.equal(await empty.locator('#welcome-open').evaluate(button => button === document.activeElement), true);
    localBind = false;
    const remote = await context.newPage();
    await remote.goto(base);
    await remote.locator('#welcome-open').click();
    assert.equal(await remote.locator('#project-browse').isVisible(), false);
    assert.match(await remote.locator('#project-help').textContent(), /sottocartelle.*gestita.*\/app\/projects/);
    await remote.locator('#project-input').fill('/app/projects/mounted-existing');
    await remote.locator('#project-submit').click();
    await remote.waitForFunction(() => !document.getElementById('project-dialog').open);
    assert.ok(requests.some(r => r.path === '/api/projects/register'));
    assert.ok(requests.filter(r => r.path === '/api/intake/generate/project-job').every(r => r.project === A));
    assert.ok(requests.filter(r => r.path === '/api/projects' || r.path === '/api/intake/project/browse-path').every(r => !r.project));
    assert.deepEqual(errors, []);
    console.log('OK browser: welcome/rain, schede/direct/refresh/history, create/open/error/reader/zero-project, XSS/CSP, stream/job A/B, indice isolato e limite attivo.');
    if (process.argv.includes('--navigation')) {
      const { spawn } = require('node:child_process');
      await new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [path.join(__dirname, 'navigation_workspace.cjs')], {
          stdio: 'inherit', env: { ...process.env, VIBECRAFT_TEST_URL: base },
        });
        child.on('error', reject);
        child.on('exit', code => code === 0 ? resolve() : reject(new Error('navigation exit ' + code)));
      });
    }
  } finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
}

async function reindexChecks() {
  const pipeline = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
  // Stati + etichette i18n, poi solo pollReindexJob (notifyReindexDone resta stub nel context).
  const labels = pipeline.slice(
    pipeline.indexOf('    const _TERMINAL_REINDEX_STATES'),
    pipeline.indexOf('    async function notifyReindexDone('),
  );
  const poll = pipeline.slice(
    pipeline.indexOf('    function pollReindexJob('),
    pipeline.indexOf('    async function copyFinalPrompt('),
  );
  const timers = [], replies = [];
  let active = 0;
  const context = vm.createContext({
    t,
    setTimeout: callback => timers.push(callback),
    sessionRevision: 0,
    retainWorkspaceTask: promise => { active++; promise.finally(() => active--); },
    fetch: async () => replies.shift(), notifyReindexDone() {},
  });
  vm.runInContext(labels + poll, context);
  const box = { textContent: '', scrollHeight: 0 };
  context.pollReindexJob('test-job', box);
  assert.equal(active, 1);
  replies.push({ ok: false, status: 503 });
  await timers.shift()();
  assert.equal(active, 1);
  assert.equal(timers.length, 1);
  replies.push({ ok: true, json: async () => ({ status: 'running' }) });
  await timers.shift()();
  assert.equal(active, 1);
  replies.push({ ok: true, json: async () => ({ status: 'completed' }) });
  await timers.shift()();
  assert.equal(active, 0);
  context.pollReindexJob('missing-job', box);
  replies.push({ ok: false, status: 404 });
  await timers.shift()();
  assert.equal(active, 0);
  assert.equal(timers.length, 0);
  console.log('OK reindex: frame residente fra poll/errori temporanei, rilascio soltanto a termine/404.');
}

(async () => {
  if (process.argv.includes('--query-only')) return queryErrorChecks();
  await fetchChecks(); await queryErrorChecks(); await reindexChecks(); await intakeApprovalChecks();
  if (!process.argv.includes('--fetch-only')) await browserChecks();
})()
  .catch(error => { console.error(error); process.exitCode = 1; });
