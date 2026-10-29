const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { t } = require('./i18n_stub.cjs');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8');
const intake = fs.readFileSync(path.join(__dirname, '../static/pages/intake.js'), 'utf8');
const pipeline = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const helpers = shared.slice(shared.indexOf('function escapeHtml('), shared.indexOf('/* ──────────── THEME VAR'));
const generation = intake.slice(intake.indexOf('    async function startGeneration('), intake.indexOf('    /* ──────────── (b) IMPORTA'));
const upload = intake.slice(intake.indexOf('    async function uploadOneFile('), intake.indexOf('    /* Motore effettivo'));
const prompt = pipeline.slice(pipeline.indexOf('    async function fetchFinalPrompt('), pipeline.indexOf('    function getFeatureName('));
async function check(status, detail, polling = false) {
  const nodes = {};
  for (const id of ['gen-descrizione','gen-nfile','gen-categoria','gen-btn','gen-status','gen-result','import-results']) {
    nodes[id] = { value: id === 'gen-descrizione' ? 'Request A' : '1', textContent: '', innerHTML: '', appendChild(row) { nodes[row.id] = row; } };
  }
  let call = 0;
  const context = vm.createContext({ URLSearchParams, Promise, Math, t,
    FormData: class { append() {} },
    setTimeout: fn => fn(),
    document: { getElementById: id => nodes[id], createElement: () => ({ innerHTML: '' }) },
    refreshStaging() { throw new Error('Failed job must not refresh success'); },
    fetch: async () => {
      call++;
      if (polling && call === 1) return { ok: true, json: async () => ({ status: 'pending', job_id: 'A-job' }) };
      return { ok: false, status, json: async () => ({ detail }) };
    },
  });
  vm.runInContext(helpers + generation + upload + prompt, context);
  await context.startGeneration();
  const message = typeof detail === 'string' ? detail : detail.message;
  assert.equal(nodes['gen-status'].textContent, (polling ? 'Job fallito: ' : 'Errore: ') + message);
  assert.equal(nodes['gen-btn'].disabled, false);
  if (polling) return;
  await assert.rejects(context.fetchFinalPrompt('same-feature', '', 'external'), error => error.message === message);
  await context.uploadOneFile({ name: '<img src=x onerror=alert(1)>.txt' });
  const html = Object.values(nodes).find(node => node.id?.startsWith('import-row-')).innerHTML;
  assert.ok(html.includes(context.escapeHtml(message)));
  assert.ok(!html.includes('<img') && !html.includes('<script') && !html.includes('[object Object]'));
}
(async () => {
  for (const [status, detail] of [[409,{ code:'project_not_indexed', message:'Indicizza il progetto A.' }], [503,{code:'project_storage_error', message:'Storage A non disponibile.'}], [503,'<script>alert("unsafe")</script>']]) await check(status, detail);
  await check(404, {code:'job_not_found', message:'Job A non più disponibile.'}, true);
  console.log('Workflow API errors: generation, pipeline prompt, upload and polling passed (409/503/404; XSS preserved).');
})().catch(error => { console.error(error); process.exitCode = 1; });
