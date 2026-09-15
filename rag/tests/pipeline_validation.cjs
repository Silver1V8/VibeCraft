// Esegue le funzioni reali della UI: rilievi visibili, associazioni mai preselezionate.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../templates/pipeline.unified.html'), 'utf8');
const code = html.slice(html.indexOf('    function gateApiError('), html.indexOf('    /* ──────────── ESECUZIONE CON CLAUDE AGENT SDK'));
const nodes = {}, checks = [], requests = [], errors = [];
function node(tag) {
  let id, content = '';
  return {tag, value: '', checked: false, disabled: false, children: [], options: [], classList: {remove() {}},
    set id(value) {id = value; nodes[id] = this;}, get id() {return id;},
    set textContent(value) {content = value; if (id === 'gate-decisions') checks.length = 0; this.children = [];},
    get textContent() {return content;},
    add(option) {this.options.push(option);},
    appendChild(child) {this.children.push(child); if (child.type === 'checkbox') checks.push(child);}};
}
for (const id of ['gate-status', 'gate-decisions', 'gate-comparison', 'validate-btn', 'validate-report-box', 'validate-structural']) node('div').id = id;
const finding = {rule:'scenari_insufficienti', message:'Solo uno scenario', finding_hash:'finding-hash', associable:true, covered_by:null};
const data = {validation_id:'val-old', comparison:{validation_id:'val-old',
  canvas:{current:'<script>current canvas</script>',validated:'validated canvas'},
  spec:{current:'current spec',validated:'validated spec'}},
  spec_hash:'spec-hash', gate:{open_points_status:'valid', reasons:[], warnings:[]},
  structural_findings:[finding], point_decisions:[{point_hash:'point-hash', status:'unaddressed', point:{id:'OP-001', question:'Caso negativo?'}}]};
let responseStatus = 'passed';
const context = vm.createContext({URLSearchParams, featureName:'demo', JSON,
  Option: function(text, value) {this.text = text; this.value = value;},
  window:{__VIBECRAFT_AGENT_API_KEY__:'test'}, localStorage:{getItem:()=>null},
  document:{getElementById:id=>nodes[id], createElement:node, createTextNode:text=>({textContent:text}),
    querySelectorAll:()=>checks.filter(n=>n.checked)}, toast:message=>errors.push(message),
  fetch:async (url, options) => {
    requests.push({url, options});
    if (url === '/api/pipeline/validate') return {ok:responseStatus !== 'unavailable', json:async()=>({
      status:responseStatus, validation_id:'val-test', validation_error: responseStatus === 'unavailable' ? 'provider offline' : null,
      checks:{structural:{status:'pass'}, semantic:{status:responseStatus === 'unavailable' ? 'unavailable' : 'pass'}},
      structural_findings:[{...finding, covered_by:{decision_id:'dec-test',declared_by:'Nome dichiarato',recorded_at:'ora',origin_verified:false}}]})};
    return {ok:true, json:async()=>data};
  }});
vm.runInContext(code, context);
// Il caso reale passed/allowed divergenti deve essere leggibile senza conoscere il gate.
const realBlocked = JSON.parse(fs.readFileSync(path.join(__dirname,
  '../eval/results/gate_end_to_end_20260914/evidence/validate-2.response.txt'), 'utf8'));
assert.match(context.validationSummary(realBlocked), /Controlli di validazione: superati/);
assert.match(context.validationSummary(realBlocked), /Avvio agentic: bloccato — .*research/s);
for (const [status, label] of [['pass', 'superati'], ['fail', 'falliti'], ['unavailable', 'non disponibili']]) {
  const text = context.validationSummary({checks:{structural:{status:'pass'}, semantic:{status}},
    gate:{allowed:status === 'pass', reasons:[{message:'Motivo del blocco'}]}});
  assert.match(text, new RegExp(`Controlli di validazione: ${label}`));
  assert.match(text, status === 'pass' ? /Avvio agentic: consentito/ : /Avvio agentic: bloccato — Motivo del blocco/);
}
assert.match(context.validationSummary({}), /Avvio agentic: bloccato — stato del gate non disponibile/);
const withAdvice = context.validationSummary({checks:{structural:{status:'pass'},semantic:{status:'pass'}},
  gate:{allowed:true}, suggestions:['Consiglio <script>test</script>']});
assert.match(withAdvice, /Avvio agentic: consentito/);
assert.match(withAdvice, /Suggerimenti facoltativi — nessun effetto sul gate:\n• Consiglio <script>test<\/script>/);
assert.doesNotMatch(withAdvice, /non esaminato|coperto da/);
(async()=>{
  await context.refreshGateReview();
  assert.equal(checks.length,1);
  assert.equal(checks[0].checked,false);
  assert.equal(nodes['decision-status'].value,'');
  assert.match(nodes['gate-status'].textContent,/non esaminato/);
  assert.match(nodes['gate-status'].textContent,/val-old/);
  await context.compareValidatedVersion();
  function allText(n) {return [n.textContent, ...n.children.map(allText)].join('\n');}
  assert.match(allText(nodes['gate-comparison']), /<script>current canvas<\/script>/);
  assert.match(allText(nodes['gate-comparison']), /validated canvas/);
  assert.match(allText(nodes['gate-comparison']), /validated spec/);
  // Un edit non deve cambiare il riferimento al contratto che aveva passato i controlli.
  data.comparison.spec.current = 'edited spec';
  await context.refreshGateReview();
  assert.equal(new URLSearchParams(requests.at(-1).url.split('?')[1]).get('validation_id'), 'val-old');
  await context.recordPointDecision();
  assert.equal(requests.filter(r=>r.url.endsWith('/decision')).length,0);
  nodes['decision-point'].value='point-hash'; nodes['decision-status'].value='accepted';
  nodes['decision-by'].value='Nome dichiarato'; nodes['decision-reason'].value='Motivazione';
  checks[0].checked=true;
  await context.recordPointDecision();
  const body=JSON.parse(requests.find(r=>r.url.endsWith('/decision')).options.body);
  assert.deepEqual(body,{feature:'demo',spec_hash:'spec-hash',point_hash:'point-hash',status:'accepted',motivation:'Motivazione',
    declared_by:'Nome dichiarato',declared_origin:'ui',coverage_finding_hashes:['finding-hash']});
  assert.equal('origin_verified' in body,false);
  assert.equal(checks[0].checked,false); // il refresh non riaccetta per estensione
  await context.runValidate();
  assert.equal(new URLSearchParams(requests.at(-1).url.split('?')[1]).get('validation_id'), 'val-test');
  assert.match(nodes['validate-report-box'].textContent,/Solo uno scenario/);
  assert.match(nodes['validate-report-box'].textContent,/coperto da dec-test/);
  assert.match(nodes['validate-report-box'].textContent,/Nome dichiarato/);
  assert.match(nodes['validate-report-box'].textContent,/origin_verified: false/);
  assert.match(nodes['validate-report-box'].textContent,/non sono scenari soddisfatti/);
  responseStatus='unavailable';
  await context.runValidate();
  assert.match(nodes['validate-report-box'].textContent,/unavailable/);
  assert.match(nodes['validate-report-box'].textContent,/provider offline/);
  assert.doesNotMatch(html,/avvio non è ancora vincolato/i);
  assert.equal(nodes['validate-btn'].disabled,false);
  context.featureName='no-validation'; data.validation_id=null; data.comparison=null;
  await context.refreshGateReview();
  await context.compareValidatedVersion();
  assert.match(nodes['gate-status'].textContent,/Validazione assente/);
  assert.match(allText(nodes['gate-comparison']),/Confronto non disponibile/);
  assert.doesNotMatch(allText(nodes['gate-comparison']),/validated canvas|validated spec/);
  // Un refresh precedente alla rivalidazione non può ripristinare il vecchio riferimento.
  context.featureName='race'; let release;
  context.fetch=()=>new Promise(resolve=>{release=resolve;});
  const pending=context.refreshGateReview();
  vm.runInContext("validationRefs.set('race','val-new')",context);
  release({ok:true,json:async()=>({...data,validation_id:'val-stale'})});
  await pending;
  assert.equal(vm.runInContext("validationRefs.get('race')",context),'val-new');
  console.log('Pipeline validation UI checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
