// Codice reale del template: selezione modalità, contratto inviato e arresto su errore.
// Eseguire con: node tests/pipeline_agent.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../templates/pipeline.unified.html'), 'utf8');
const functions = html.slice(html.indexOf('    async function fetchFinalPrompt('), html.indexOf('    function getFeatureName('))
  + html.slice(html.indexOf('    function openPointsSummary('), html.indexOf('    /* ──────────── STEP 4:'))
  + html.slice(html.indexOf('    async function saveMdFile('), html.indexOf('    /* Ctrl+Enter'));

async function check(mode, unavailable = false, event = null) {
  const requests = [];
  const errors = [];
  const nodes = {
    'agent-mode-select': { value: mode }, 'agent-model-select': { value: 'sonnet' },
    'agent-run-btn': { disabled: false }, 'agent-output': { style: {}, textContent: '' },
  };
  const context = vm.createContext({
    URLSearchParams, TextDecoder, featureName: 'feat', devType: 'frontend',
    window: { _finalPrompt: 'PROMPT ESTERNO', __VIBECRAFT_AGENT_API_KEY__: 'synthetic' },
    document: { getElementById: id => nodes[id] },
    toast: message => errors.push(message), confirmDialog: async () => true,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url.startsWith('/api/pipeline/final-prompt')) return {
        ok: !unavailable, json: async () => unavailable
          ? { detail: 'Contratto non disponibile' } : { final_prompt: `CONTRATTO ${mode}` },
      };
      // Due chunk, nessun newline finale: verifica anche l'ultimo evento.
      const bytes = Buffer.from(event ? JSON.stringify(event) : '');
      const chunks = [bytes.subarray(0, 8), bytes.subarray(8)];
      return { ok: true, body: { getReader: () => ({ read: async () => chunks.length
        ? { done: false, value: chunks.shift() } : { done: true } }) } };
    },
  });
  vm.runInContext(functions, context);
  await context.runWithAgent();
  const params = new URLSearchParams(requests[0].url.split('?')[1]);
  assert.equal(params.get('consumer'), 'agent');
  assert.equal(params.get('mode'), mode);
  assert.equal(params.get('dev_type'), 'frontend');
  if (unavailable) {
    assert.equal(requests.length, 1); // Nessun agent/run col prompt esterno.
    assert.deepEqual(errors, ['Contratto non disponibile']);
  } else {
    assert.equal(requests[1].url, '/api/pipeline/agent/run');
    assert.deepEqual(JSON.parse(requests[1].options.body), {
      prompt: `CONTRATTO ${mode}`, mode, model: 'sonnet', feature: 'feat',
    });
  }
  assert.equal(nodes['agent-run-btn'].disabled, false);
  return nodes['agent-output'].textContent;
}

async function checkSave(change) {
  const nodes = {'spec-md-editor': {value: 'spec iniziale'},
    'spec-open-points-status': {textContent: 'Modifiche non salvate'}};
  let release;
  const context = vm.createContext({featureName: 'feature-iniziale',
    document: {getElementById: id => nodes[id]}, refreshFilesControl: async () => {},
    toast: message => assert.fail(message), fetch: () => new Promise(resolve => {release = resolve;})});
  vm.runInContext(functions, context);
  const pending = context.saveMdFile('spec.md', 'spec-md-editor');
  if (change === 'edit') nodes['spec-md-editor'].value = 'spec modificata';
  if (change === 'feature') context.featureName = 'altra-feature';
  release({ok: true, json: async () => ({open_points_status: 'valid', open_points: []})});
  await pending;
  assert.match(nodes['spec-open-points-status'].textContent,
    change ? /Modifiche non salvate/ : /Terminato senza punti aperti/);
}

(async () => {
  for (const mode of ['suggest', 'agentic', 'oneshot']) await check(mode);
  await check('agentic', true);
  for (const status of ['missing', 'invalid', 'valid']) {
    const text = await check('suggest', false, {type: 'result', open_points_status: status,
      ...(status === 'valid' ? {open_points: []} : {})});
    assert.match(text, new RegExp({missing: 'Resoconto assente', invalid: 'Resoconto malformato',
      valid: 'Terminato senza punti aperti'}[status]));
    if (status !== 'valid') assert.doesNotMatch(text, /Terminato senza punti aperti|✅ Completato/);
    assert.match(text, /advisory/);
  }
  const blocked = await check('suggest', false, {type: 'result', open_points_status: 'valid',
    open_points: [{id: 'OP-001', reason: 'no_new_evidence', original_question: 'Chi può accedere?', question: 'Quali ruoli?'}]});
  assert.match(blocked, /OP-001 · no_new_evidence · Chi può accedere/);
  assert.doesNotMatch(blocked, /Terminato senza punti aperti/);
  assert.match(await check('suggest'), /Stream interrotto senza risultato finale/);
  for (const change of ['', 'edit', 'feature']) await checkSave(change);
  console.log('Pipeline: modalità, resoconti missing/invalid/valid e stream interrotto verificati.');
})().catch(error => { console.error(error); process.exitCode = 1; });
