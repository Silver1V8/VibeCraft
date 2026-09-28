// Il codice reale della dashboard (in /static/pages/dashboard.js, era nel template) che mette dati del corpus in HTML:
// tooltip del grafo 3D (nodeLabel/linkLabel di 3d-force-graph finiscono in innerHTML) e
// lista dei punteggi. Eseguito con escapeHtml di /static/shared.js, senza browser.
// La relazione di un arco è una stringa libera del frontmatter (graph_rag.edges[].type).
// Uso: node tests/dashboard_graph_escape.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = fs.readFileSync(path.join(__dirname, '../static/pages/dashboard.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8');
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
  graph3d: null,
  ForceGraph3D: () => () => chain,
  themeVar: (_, fallback) => fallback || '#000',
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
