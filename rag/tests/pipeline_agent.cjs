// Codice reale del template: selezione modalità, contratto inviato e arresto su errore.
// Eseguire con: node tests/pipeline_agent.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../templates/pipeline.unified.html'), 'utf8');
const functions = html.slice(html.indexOf('    async function fetchFinalPrompt('), html.indexOf('    function getFeatureName('))
  + html.slice(html.indexOf('    async function runWithAgent('), html.indexOf('    /* ──────────── CONSUMER NDJSON'));

async function check(mode, unavailable = false) {
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
      return { ok: true, body: { getReader: () => ({ read: async () => ({ done: true }) }) } };
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
      prompt: `CONTRATTO ${mode}`, mode, model: 'sonnet',
    });
  }
  assert.equal(nodes['agent-run-btn'].disabled, false);
}

(async () => {
  for (const mode of ['suggest', 'agentic', 'oneshot']) await check(mode);
  await check('agentic', true);
  console.log('Pipeline: modalità e prompt coerenti; nessun avvio se manca il contratto.');
})().catch(error => { console.error(error); process.exitCode = 1; });
