// Il codice reale della dashboard (in /static/pages/dashboard.js, era nel template) che mette dati del corpus in HTML:
// tooltip del grafo 3D (nodeLabel/linkLabel di 3d-force-graph finiscono in innerHTML) e
// lista dei punteggi. Eseguito con escapeHtml di /static/shared.js, senza browser.
// La relazione di un arco è una stringa libera del frontmatter (graph_rag.edges[].type).
// Uso: node tests/dashboard_graph_escape.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { t } = require('./i18n_stub.cjs');

const template = fs.readFileSync(path.join(__dirname, '../static/pages/dashboard.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8').replace(/\r\n/g, '\n');
function slice(src, start, end) {
  const a = src.indexOf(start), b = src.indexOf(end, a + 1);
  assert.ok(a >= 0 && b > a, `marcatori non trovati: ${start} … ${end}`);
  return src.slice(a, b);
}
const escapeCode = slice(shared, 'function escapeHtml(', '\n}\n') + '\n}\n';
const code = [
  slice(template, '    function makeTooltipHtml(', '    function attachTooltipListeners('),
  slice(template, '    function resize3DCanvas(', '    /* `rerender: false`'),
  slice(template, '    function renderScores(', '    /* ──────────── JSON PANEL RENDERER'),
].join('\n');

const HOSTILE = '<img src=x onerror=alert(1)>';

// 3d-force-graph finto: registra gli accessor e li risolve come la libreria
// (stringa = nome della proprietà, funzione = chiamata sull'oggetto).
const accessors = {};
const chain = new Proxy({}, {
  get: (_, name) => (...args) => { if (args.length) accessors[name] = args[0]; return chain; },
});
const resolve = (acc, obj) => (typeof acc === 'function' ? acc(obj) : obj[acc]);

const els = {};
const context = vm.createContext({
  t,
  graph3d: null,
  ForceGraph3D: () => () => chain,
  themeVar: (_, fallback) => fallback || '#000',
  // render3D programma l'adattamento della vista (scheduleFit): qui non deve scattare.
  setTimeout: () => 0, clearTimeout() {},
  window: { addEventListener() {} },
  document: {
    getElementById: id => (els[id] ||= {
      id, innerHTML: '', clientWidth: 300, clientHeight: 300,
      classList: { add() {}, remove() {} },
      insertAdjacentHTML(_, html) { this.innerHTML += html; },
    }),
  },
});
vm.runInContext(escapeCode + code, context);

// 1. Grafo 3D: relazione dell'arco e id/descrizione del nodo restano testo nei tooltip.
context.render3D(
  [{ id: 'n1', nodeId: `REGOLA-1${HOSTILE}`, description: `desc ${HOSTILE}` }, { id: 'n2', nodeId: 'n2' }],
  [{ from: 'n1', to: 'n2', label: `dipende_da${HOSTILE}` }, { from: 'n2', to: 'n1', label: 'usa' }],
);
const link = resolve(accessors.linkLabel, { label: `dipende_da${HOSTILE}` });
assert.ok(!link.includes('<img'), link);
assert.equal(link, 'dipende_da&lt;img src=x onerror=alert(1)&gt;');
assert.equal(resolve(accessors.linkLabel, { label: 'usa' }), 'usa');   // relazione innocua invariata
assert.equal(resolve(accessors.linkLabel, {}), '');
const node = resolve(accessors.nodeLabel, { nodeId: `REGOLA-1${HOSTILE}`, description: `desc ${HOSTILE}` });
assert.ok(!node.includes('<img') && node.includes('desc &lt;img src=x onerror=alert(1)&gt;'), node);

// 2. Punteggi: doc_id e valori non numerici restano testo, i numeri formattati come prima.
context.renderScores([{ doc_id: `doc${HOSTILE}.md`, score: 0.5, dense_score: 0.25,
                        sparse_score: `n/d${HOSTILE}`, colbert_score: null, authority: 1 }]);
const scores = els['scores-list'].innerHTML;
assert.ok(!scores.includes('<img'), scores);
assert.ok(scores.includes('S n/d&lt;img src=x onerror=alert(1)&gt;</span>'), scores);
assert.ok(scores.includes('>D 0.250</span>') && scores.includes('>CB —</span>') && scores.includes('A 1.000</span>'), scores);
console.log('Dashboard: relazioni degli archi, nodi e punteggi del corpus restano testo nei tooltip e nella lista');

// Risposta dal grafo (status "graph_answer"): testo leggibile invece di "(nessuna risposta)".
const graphAnswerText = vm.runInNewContext(
  slice(template, '    function graphAnswerText(', '    function renderAskResult(') + '; graphAnswerText',
  { t },
);
assert.equal(graphAnswerText({ intent: 'documenti', answer: ['a.md', 'b.md'], count: 2 }), '2 risultati (documenti)\n• a.md\n• b.md');
assert.equal(graphAnswerText({ intent: 'relazioni', target: 'X', out: [{ relation: 'R', to: 'Y' }], in: [{ relation: 'S', from: 'Z' }], count: 2 }),
  '2 risultati (relazioni: X)\n→ R Y\n← S Z');
assert.equal(graphAnswerText({ intent: 'impatto', target: 'X', rings: [['X'], ['A', 'B']], count: 2 }), '2 risultati (impatto: X)\nNodo: X\nDistanza 1: A, B');
assert.equal(graphAnswerText(undefined), '');
console.log('Dashboard: le risposte dal grafo diventano testo (elenco, relazioni, anelli d\'impatto)');

// Risposta in Markdown (renderMarkdown di shared.js): struttura resa, HTML del modello sempre testo.
const renderMarkdown = vm.runInNewContext(
  slice(shared, 'function escapeHtml(', 'function apiErrorMessage(') + '; renderMarkdown');
const md = renderMarkdown('### Titolo\nTesto **forte** e `codice`.\n\n- uno\n- due\n\n1. primo\n\n```\n<b>x</b>\n```\n<img src=x onerror=alert(1)> [x](javascript:alert(1))');
assert.ok(md.includes('<h4>Titolo</h4>'), md);
assert.ok(md.includes('<strong>forte</strong>') && md.includes('<code>codice</code>'), md);
assert.ok(md.includes('<ul><li>uno</li><li>due</li></ul>') && md.includes('<ol><li>primo</li></ol>'), md);
assert.ok(md.includes('<pre><code>&lt;b&gt;x&lt;/b&gt;</code></pre>'), md);
assert.ok(!md.includes('<img') && !md.includes('href="javascript'), md);
assert.equal(renderMarkdown('```\naperto'), '<pre><code>aperto</code></pre>', 'blocco non chiuso durante lo streaming');
console.log('Dashboard: la risposta in Markdown è resa e il suo HTML resta testo');
