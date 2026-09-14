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
for (const id of ['gate-status', 'gate-decisions', 'validate-btn', 'validate-report-box', 'validate-structural']) node('div').id = id;
const finding = {rule:'scenari_insufficienti', message:'Solo uno scenario', finding_hash:'finding-hash', associable:true, covered_by:null};
const data = {spec_hash:'spec-hash', gate:{open_points_status:'valid', reasons:[], warnings:[]},
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
(async()=>{
  await context.refreshGateReview();
  assert.equal(checks.length,1);
  assert.equal(checks[0].checked,false);
  assert.equal(nodes['decision-status'].value,'');
  assert.match(nodes['gate-status'].textContent,/non esaminato/);
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
  assert.match(nodes['validate-report-box'].textContent,/Solo uno scenario/);
  assert.match(nodes['validate-report-box'].textContent,/coperto da dec-test/);
  assert.match(nodes['validate-report-box'].textContent,/Nome dichiarato/);
  assert.match(nodes['validate-report-box'].textContent,/origin_verified: false/);
  assert.match(nodes['validate-report-box'].textContent,/non sono scenari soddisfatti/);
  responseStatus='unavailable';
  await context.runValidate();
  assert.match(nodes['validate-report-box'].textContent,/unavailable/);
  assert.match(nodes['validate-report-box'].textContent,/provider offline/);
  assert.match(nodes['validate-report-box'].textContent,/avvio non è ancora vincolato/);
  assert.equal(nodes['validate-btn'].disabled,false);
  console.log('Pipeline validation UI checks passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
