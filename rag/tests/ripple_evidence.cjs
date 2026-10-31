// Legenda e elenco degli archi dell'Impact Ripple. I metadati arrivano dall'API e
// possono contenere testo del frontmatter: non devono diventare HTML.
// Uso: node tests/ripple_evidence.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { t } = require('./i18n_stub.cjs');

const page = fs.readFileSync(path.join(__dirname, '../static/pages/graph_analysis.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8').replace(/\r\n/g, '\n');
function slice(src, start, end) {
  const a = src.indexOf(start), b = src.indexOf(end, a + 1);
  assert.ok(a >= 0 && b > a, `marcatori non trovati: ${start} … ${end}`);
  return src.slice(a, b);
}
const escapeCode = slice(shared, 'function escapeHtml(', '\n}\n') + '\n}\n';
const code = slice(page, '    /* ── impact evidence (fase 1) ── */', '    /* ── fine impact evidence ── */');

const HOSTILE = '<img src=x onerror=alert(1)>';
const els = {};
function el(id) {
  return els[id] ||= { innerHTML: '', textContent: '', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
}
const context = vm.createContext({ t, document: { getElementById: el }, escapeHtml: null });
vm.runInContext(escapeCode + code, context);

const data = {
  nodes: [
    { id: 'centro', ring: 0 },
    { id: 'vicino', ring: 1 },
    { id: HOSTILE, ring: 2 },
  ],
  edges: [
    { from: 'centro', to: 'vicino', relation: 'PART_OF', nature: 'structural', weight: null, reliability: 1, provenance: null },
    {
      from: 'vicino', to: HOSTILE, relation: HOSTILE, nature: 'inferred',
      weight: 0.99, reliability: 0.8, provenance: HOSTILE,
    },
    { from: 'centro', to: HOSTILE, relation: 'MENTIONS', nature: null, weight: null, reliability: null, provenance: null },
  ],
};
context.renderRippleDetails(data);
const html = el('ripple-edges').innerHTML;
assert.ok(!html.includes('<' + 'img'), 'un valore ostile non diventa un tag');
assert.ok(html.includes('&' + 'lt;img'), 'il testo ostile resta visibile, escapato');
assert.ok(html.includes('inferita'), 'un peso alto non cambia la natura inferita');
assert.ok(html.includes('non specificata'), 'la natura assente non diventa curata o verificata');
assert.ok(html.includes('0.99'));
assert.ok(html.includes('non una probabilità'));
assert.equal(el('ripple-caveat').textContent.includes('non rende verificato il percorso'), true);
assert.ok(el('ripple-edge-legend').innerHTML.includes('edge-inferred'));
assert.ok(el('ripple-edge-legend').innerHTML.includes('anche se il punteggio è alto'));

const far = { id: HOSTILE, ring: 2 };
const approach = context.rippleApproachText(far, data);
assert.equal(approach.includes(HOSTILE), true);
assert.equal(approach.includes('inferita'), true);
assert.equal(approach.includes('non specificata'), false);
assert.equal(approach.includes('non verifica il percorso'), true);
assert.equal(context.edgeNatureKind('verified'), 'unspecified');
assert.equal(context.edgeNatureKind('inferred'), 'inferred');

console.log('OK ripple evidence: natura, punteggi, legacy e escape.');
