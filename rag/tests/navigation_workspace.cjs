// Browser reale, API simulate: nessun modello o agente viene eseguito.
// Avviare uvicorn server:app --lifespan off --port 9876, poi node tests/navigation_workspace.cjs.
// Richiede Playwright disponibile tramite NODE_PATH; usa Edge installato su Windows.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', msg => { if (msg.text().includes('Content Security Policy')) errors.push(msg.text()); });
    let finishAsk, finishAgent;
    let intakeComplete = false, intakeCount = 0;
    let askCount = 0, agentCount = 0, agentHasKey = false;
    await page.route('**/ask', async route => {
      askCount++;
      await new Promise(resolve => { finishAsk = resolve; });
      await route.fulfill({ contentType: 'application/x-ndjson', body:
        JSON.stringify({ type: 'delta', text: 'Risposta ' }) + '\n' +
        JSON.stringify({ type: 'result', value: { answer: 'Risposta mantenuta', qdrant_scores: [] } }) + '\n' });
    });
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url());
      let body = {};
      if (url.pathname === '/api/projects') body = { projects: [{ id: 'legacy', name: 'Legacy', legacy: true,
        index_status: 'ready', stale: false, index_version: 'navigation-version' }], read_only: false };
      if (url.pathname === '/api/projects/legacy') body = { id: 'legacy', name: 'Legacy', legacy: true,
        index_status: 'ready', stale: false, index_version: 'navigation-version' };
      if (url.pathname === '/api/pipeline/agent/run') {
        agentCount++;
        agentHasKey = !!route.request().headers()['x-api-key'];
        await new Promise(resolve => { finishAgent = resolve; });
        return route.fulfill({ contentType: 'application/x-ndjson', body:
          JSON.stringify({ type: 'text', text: 'Output agente mantenuto' }) + '\n' +
          JSON.stringify({ type: 'result', is_error: false }) + '\n' });
      }
      if (url.pathname === '/api/graph/all') body = { nodes: [], edges: [] };
      if (url.pathname === '/api/intake/staged') body = { items: [] };
      if (url.pathname === '/api/intake/generate') {
        intakeCount++;
        body = { job_id: 'navigation-job', status: 'running' };
      }
      if (url.pathname === '/api/intake/generate/navigation-job') body = {
        job_id: 'navigation-job', status: intakeComplete ? 'completed' : 'running', result: { staged: [] } };
      if (url.pathname === '/api/pipeline/dev-types') body = { dev_types: [] };
      if (url.pathname === '/api/pipeline/agent/runners') body = {
        runners: [{ id: 'claude', label: 'Claude', available: true, models: [], modes: ['suggest', 'oneshot'] }], max_attempts: 1 };
      if (url.pathname === '/api/pipeline/status') body = { files: {}, dev_type: '' };
      if (url.pathname === '/api/pipeline/file') return route.fulfill(url.searchParams.get('name') === 'spec.md'
        ? { json: { content: '# Specifica di prova' } } : { status: 404, json: {} });
      if (url.pathname === '/api/pipeline/gate') body = {
        validation_id: null, gate: { allowed: true, reasons: [], warnings: [] }, structural_findings: [], point_decisions: [] };
      if (url.pathname === '/api/pipeline/final-prompt') body = { final_prompt: 'Prompt di prova' };
      await route.fulfill({ json: body });
    });
    await page.goto(process.env.VIBECRAFT_TEST_URL || 'http://127.0.0.1:9876/');
    await page.evaluate(() => setApiKey('navigation-test-key'));
    const consolePage = page.frameLocator('iframe[data-workspace-page="/"]');
    await consolePage.locator('#question-input').fill('Domanda da conservare');
    await consolePage.locator('#ask-btn').click();
    await page.waitForFunction(() => document.querySelector('iframe').contentDocument.getElementById('ask-btn').disabled);
    await consolePage.locator('.app-nav a[href^="/pipeline?project="]').click();
    const pipeline = page.frameLocator('iframe[data-workspace-page="/pipeline"]');
    await pipeline.locator('#feature-name-input').fill('feature-da-conservare');
    assert.equal(typeof finishAsk, 'function');
    finishAsk();
    await consolePage.locator('#answer-text').waitFor({ state: 'attached' });
    await page.waitForFunction(() => document.querySelector('iframe[data-workspace-page="/"]').contentDocument.getElementById('answer-text').textContent === 'Risposta mantenuta');
    await pipeline.locator('.app-nav a[href^="/?project="]').click();
    assert.equal(await consolePage.locator('#question-input').inputValue(), 'Domanda da conservare');
    assert.equal(await consolePage.locator('#answer-text').textContent(), 'Risposta mantenuta');
    await consolePage.locator('.app-nav a[href^="/pipeline?project="]').click();
    await pipeline.locator('#load-feature-btn').click();
    await page.waitForFunction(() => document.querySelector('iframe[data-workspace-page="/pipeline"]').contentDocument.getElementById('files-control-list').textContent.includes('explore.md'));
    await pipeline.locator('[data-click="goToStep"][data-arg="3"]').click();
    await pipeline.locator('[data-click="approveSpec"]').click();
    await pipeline.locator('#agent-mode-select').selectOption('oneshot');
    await pipeline.locator('#agent-run-btn').click();
    await page.waitForFunction(() => document.querySelector('iframe[data-workspace-page="/pipeline"]').contentDocument.getElementById('agent-run-btn').disabled);
    await pipeline.locator('.app-nav a[href^="/intake?project="]').click();
    const intake = page.frameLocator('iframe[data-workspace-page="/intake"]');
    const intakeInput = intake.locator('textarea').first();
    await intakeInput.fill('Bozza Intake mantenuta');
    await intake.locator('#gen-btn').click();
    assert.equal(typeof finishAgent, 'function');
    finishAgent();
    await page.waitForFunction(() => !document.querySelector('iframe[data-workspace-page="/pipeline"]').contentDocument.getElementById('agent-run-btn').disabled);
    await intake.locator('.app-nav a[href^="/pipeline?project="]').click();
    intakeComplete = true;
    await page.waitForFunction(() => document.querySelector('iframe[data-workspace-page="/intake"]').contentDocument.getElementById('gen-status').textContent === 'Generazione completata.');
    assert.equal(await pipeline.locator('#feature-name-input').inputValue(), 'feature-da-conservare');
    assert.match(await pipeline.locator('#agent-output').textContent(), /Output agente mantenuto/);
    await page.goBack();
    await intakeInput.waitFor({ state: 'visible' });
    assert.equal(await intakeInput.inputValue(), 'Bozza Intake mantenuta');
    assert.equal(await intake.locator('#gen-status').textContent(), 'Generazione completata.');
    await page.goForward();
    await pipeline.locator('#agent-output').waitFor({ state: 'visible' });
    await pipeline.locator('#theme-switcher').selectOption('classic');
    await pipeline.locator('.app-nav a[href^="/?project="]').click();
    assert.equal(await consolePage.locator('#theme-switcher').inputValue(), 'classic');
    assert.equal(askCount, 1);
    assert.equal(agentCount, 1);
    assert.equal(intakeCount, 1);
    assert.equal(agentHasKey, true);
    assert.equal(await page.locator('#workspace-pages iframe').count(), 3);
    let failOnce = true;
    await page.route('**/infografica?*workspace=1*', route => {
      if (failOnce) { failOnce = false; return route.fulfill({ status: 503, body: 'Unavailable' }); }
      return route.continue();
    });
    await consolePage.locator('.app-nav a[href^="/infografica?project="]').click();
    await page.locator('#workspace-retry').waitFor({ state: 'visible' });
    assert.equal(await consolePage.locator('#question-input').inputValue(), 'Domanda da conservare');
    await page.locator('#workspace-retry').click();
    const infographic = page.frameLocator('iframe[data-workspace-page="/infografica"]');
    await infographic.locator('.app-nav a[href^="/?project="]').click();
    assert.equal(await consolePage.locator('#answer-text').textContent(), 'Risposta mantenuta');
    assert.deepEqual(errors, []);
    console.log('OK: Console e agente continuano fuori pagina; Intake, cronologia, tema e API key conservati; nessuna violazione CSP.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
