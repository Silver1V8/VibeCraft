const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const functions = source.slice(source.indexOf('    async function fetchFinalPrompt('), source.indexOf('    function getFeatureName('))
  + source.slice(source.indexOf('    let agentRunners ='), source.indexOf('    /* ──────────── CONSUMER NDJSON'))
  + source.slice(source.indexOf('    function copyFinalPrompt(') >= 0 ? source.indexOf('    function copyFinalPrompt(') : source.indexOf('    async function copyFinalPrompt('), source.indexOf('    /* ──────────── DRY-RUN'));
const reason = 'native_read_isolation_unverified: Avvio integrato non disponibile; esporta il prompt.';
const metadata = [{id:'codex',label:'Codex CLI',installed:true,export_available:true,available:false,
  unavailable_reason:reason,unavailable_code:'native_read_isolation_unverified',modes:['suggest','oneshot'],models:[]}];
const select = (value, options = []) => ({value,options,textContent:'',add(option){this.options.push(option);}});
const nodes = {'agent-runner-select':select('codex'),'agent-model-select':select(''),
  'agent-mode-select':select('suggest',[{value:'suggest'},{value:'agentic'},{value:'oneshot'}]),
  'agent-attempts-select':select('1'),'agent-run-btn':{disabled:false,title:''},
  'final-prompt-box':{textContent:'OLD'},'agent-output':{style:{},textContent:''}};
const calls = [], copied = [], errors = [];
const context = vm.createContext({URLSearchParams,featureName:'same',devType:'backend',
  TextDecoder, localStorage:{getItem:()=>''},refreshGateReview:async()=>{},
  validationRefs:new Map(),blockedAttempts:new Map(),openPointsSummary:()=>'',consumeNdjson:async()=>{},
  Option: function(text,value){this.text=text;this.value=value;this.disabled=false;},
  document:{getElementById:id=>nodes[id]}, window:{_finalPrompt:'OLD'},
  navigator:{clipboard:{writeText:async text=>copied.push(text)}},setTimeout:()=>{},
  apiErrorMessage:value=>String(value),toast:text=>errors.push(text),
  fetch:async(url,options)=>{calls.push({url,options}); return {ok:true,json:async()=>
    url.includes('/runners') ? {runners:metadata,max_attempts:1} : {final_prompt:'PROJECT A EXTERNAL'}};}});
vm.runInContext(functions,context);
(async()=>{
  await context.loadRunners();
  assert.equal(nodes['agent-runner-select'].options[0].disabled,false,'native export chooser remains reachable');
  assert.ok(nodes['agent-runner-select'].options[0].text.includes(reason));
  assert.equal(nodes['agent-run-btn'].disabled,true);
  assert.equal(nodes['agent-run-btn'].title,reason);
  await context.runWithAgent();
  assert.ok(!calls.some(c=>c.url==='/api/pipeline/agent/run'));
  assert.deepEqual(errors,[reason]);
  await context.copyFinalPrompt({textContent:'Copia'});
  const request = calls.find(c=>c.url.includes('/final-prompt'));
  const params = new URLSearchParams(request.url.split('?')[1]);
  assert.equal(params.get('runner'),'codex');
  assert.equal(params.get('consumer'),'external');
  assert.equal(params.get('mode'),'suggest');
  assert.deepEqual(copied,['PROJECT A EXTERNAL']);
  metadata.push({id:'local',label:'Local',available:true,export_available:true,modes:['suggest'],models:['model']},
    {id:'claude',label:'Claude',available:true,export_available:true,modes:['suggest'],models:['sonnet']});
  let release;
  context.fetch = async(url,options)=>{
    calls.push({url,options});
    if (url.includes('/runners')) return {ok:true,json:async()=>({runners:metadata,max_attempts:1})};
    if (url.includes('/final-prompt')) return {ok:true,json:async()=>({final_prompt:'PROJECT A'})};
    return new Promise(resolve=>{release=()=>resolve({ok:true,body:{getReader:()=>({read:async()=>({done:true})})}});});
  };
  await context.loadRunners();
  nodes['agent-runner-select'].value='local';
  context.onRunnerChange();
  const pending = context.runWithAgent();
  let rejected;
  pending.catch(error=>{rejected=error;});
  for (let turn=0; turn<20 && !release; turn++) await Promise.resolve();
  if (rejected) throw rejected;
  assert.ok(release,'run reaches pending fetch');
  assert.equal(nodes['agent-run-btn'].disabled,true);
  for (const id of ['claude','codex','local']) {
    nodes['agent-runner-select'].value=id;
    context.onRunnerChange();
    assert.equal(nodes['agent-run-btn'].disabled,true,'selector change cannot re-enable active Run');
  }
  const runCalls = calls.filter(c=>c.url==='/api/pipeline/agent/run').length;
  await context.runWithAgent();
  assert.equal(calls.filter(c=>c.url==='/api/pipeline/agent/run').length,runCalls,'no second launch while pending');
  release();
  await pending;
  assert.equal(nodes['agent-run-btn'].disabled,false);
  console.log('Runner capability: native export reachable, Run disabled and explicit reason, fixed external prompt request');
})().catch(error=>{console.error(error);process.exitCode=1;});
