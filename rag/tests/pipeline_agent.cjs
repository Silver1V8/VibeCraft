// Codice reale della pagina (/static/pages/pipeline.js): selezione modalità, contratto inviato e arresto su errore.
// Eseguire con: node tests/pipeline_agent.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8');
const errorHelper = shared.slice(shared.indexOf('function apiErrorMessage('), shared.indexOf('/* ──────────── THEME VAR'));
const functions = html.slice(html.indexOf('    async function fetchFinalPrompt('), html.indexOf('    function getFeatureName('))
  + html.slice(html.indexOf('    function gateApiError('), html.indexOf('    /* ──────────── ESECUZIONE CON CLAUDE AGENT SDK'))
  + html.slice(html.indexOf('    function openPointsSummary('), html.indexOf('    /* ──────────── STEP 4:'))
  + html.slice(html.indexOf('    async function saveMdFile('), html.indexOf('    /* Ctrl+Enter'));

async function check(mode, unavailable = false, event = null, blockStatus = null, validationId = 'val-server') {
  const requests = [];
  const errors = [];
  const nodes = {
    'agent-mode-select': { value: mode }, 'agent-model-select': { value: 'sonnet' },
    'agent-runner-select': { value: 'claude' },
    'agent-attempts-select': { value: '1' },
    'agent-run-btn': { disabled: false }, 'agent-output': { style: {}, textContent: '' },
  };
  for (const id of ['gate-status','gate-decisions','gate-comparison']) nodes[id] = {textContent:'',children:[],appendChild(n){this.children.push(n);}};
  const denial = {allowed:false,validation_id:'val-server',attempt_id:'attempt-blocked',
    reasons:[{code:'contract_changed',message:'Contratto cambiato',action:'user_action',next_step:'Rivalida',changed:['canvas','spec']},
      {code:'sources_unavailable',message:'Fonti indisponibili',action:'operator_action',next_step:'Ripristina indice',changed:['policy.md']}],
    warnings:[{code:'unreviewed_corpus_changes',message:'Pertinenza non rivalutata',changed:['other.md']}]};
  const context = vm.createContext({
    URLSearchParams, TextDecoder, featureName: 'feat', devType: 'frontend',
    window: { _finalPrompt: mode === 'agentic' ? '' : 'PROMPT ESTERNO', __VIBECRAFT_AGENT_API_KEY__: 'synthetic' },
    document: { getElementById: id => nodes[id],createElement:()=>({textContent:'',appendChild(){}}) },
    toast: message => errors.push(message), confirmDialog: async () => true,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url.startsWith('/api/pipeline/gate')) return {ok:true,json:async()=>({
        validation_id:validationId,comparison:null,gate:{allowed:false,reasons:[],warnings:[]},point_decisions:[],structural_findings:[]})};
      if (url.startsWith('/api/pipeline/final-prompt')) return {
        ok: !unavailable, json: async () => unavailable
          ? { detail: 'Contratto non disponibile' } : { final_prompt: `CONTRATTO ${mode}` },
      };
      if (blockStatus) return {ok:false,status:blockStatus,json:async()=>({detail:denial})};
      // Due chunk, nessun newline finale: verifica anche l'ultimo evento.
      const bytes = Buffer.from(event ? JSON.stringify(event) : '');
      const chunks = [bytes.subarray(0, 8), bytes.subarray(8)];
      return { ok: true, body: { getReader: () => ({ read: async () => chunks.length
        ? { done: false, value: chunks.shift() } : { done: true } }) } };
    },
  });
  vm.runInContext(errorHelper + functions, context);
  await context.runWithAgent();
  const promptRequest = requests.find(r=>r.url.startsWith('/api/pipeline/final-prompt'));
  if (mode === 'agentic') assert.equal(promptRequest,undefined);
  else {
    const params = new URLSearchParams(promptRequest.url.split('?')[1]);
    assert.equal(params.get('consumer'), 'agent');
    assert.equal(params.get('mode'), mode);
    assert.equal(params.get('dev_type'), 'frontend');
    assert.equal(params.get('runner'), 'claude');
  }
  const runs = () => requests.filter(r=>r.url==='/api/pipeline/agent/run');
  if (unavailable) {
    assert.equal(runs().length, 0); // Nessun agent/run col prompt esterno.
    assert.deepEqual(errors, ['Contratto non disponibile']);
  } else {
    assert.deepEqual(JSON.parse(runs()[0].options.body), {
      ...(mode === 'agentic' ? {} : {prompt:`CONTRATTO ${mode}`}), mode, runner: 'claude', model: 'sonnet', feature: 'feat',validation_id:validationId, max_attempts: 1,
    });
  }
  if (blockStatus) {
    for (const text of ['contract_changed','user_action','operator_action','Rivalida','Ripristina indice','canvas','spec','policy.md','other.md','attempt-blocked']) {
      assert.ok(nodes['agent-output'].textContent.includes(text),text);
    }
    await context.runWithAgent();
    assert.equal(JSON.parse(runs().at(-1).options.body).retry_of_attempt_id,'attempt-blocked');
    context.featureName='another-feature';
    await context.runWithAgent();
    assert.equal('retry_of_attempt_id' in JSON.parse(runs().at(-1).options.body),false);
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
  await check('suggest', true);
  await check('agentic',false,null,null,null); // Il server decide anche con riferimento assente.
  for (const status of [409,503]) await check('agentic',false,null,status);
  for (const mode of ['suggest','oneshot']) {
    const advisory=await check(mode,false,{type:'gate',attempt_id:'advisory-attempt',gate:{allowed:false,
      reasons:[{code:'validation_missing',message:'Validazione assente',action:'user_action',next_step:'Valida'}],
      warnings:[{message:'Pertinenza non rivalutata',changed:['other.md']}]}});
    assert.match(advisory,/validation_missing/); assert.match(advisory,/Pertinenza non rivalutata.*other.md/);
    assert.match(advisory,/advisory-attempt/);
  }
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
