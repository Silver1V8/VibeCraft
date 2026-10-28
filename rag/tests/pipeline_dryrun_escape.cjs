// Il codice reale del pannello dry-run e della tendina dev-types (in /static/pages/pipeline.js, era nel template),
// eseguito con escapeHtml di /static/shared.js e un DOM finto, senza browser né dipendenze.
// Titoli e nomi del corpus (anche importati da file esterni), note e messaggi d'errore del
// server finivano in innerHTML senza escape: un titolo `<img onerror=…>` veniva eseguito.
// Uso: node tests/pipeline_dryrun_escape.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { t } = require('./i18n_stub.cjs');

const template = fs.readFileSync(path.join(__dirname, '../static/pages/pipeline.js'), 'utf8');
const shared = fs.readFileSync(path.join(__dirname, '../static/shared.js'), 'utf8').replace(/\r\n/g, '\n');
function slice(src, start, end) {
  const a = src.indexOf(start), b = src.indexOf(end, a + 1);
  assert.ok(a >= 0 && b > a, `marcatori non trovati: ${start} … ${end}`);
  return src.slice(a, b);
}
const escapeCode = slice(shared, 'function escapeHtml(', '\n}\n') + '\n}\n';
const errorCode = slice(shared, 'function apiErrorMessage(', '\n}\n') + '\n}\n';
const dryRunCode = slice(template, '    async function runCanvasDryRun(', '    /* ──────────── AGENT CONTEXT');
const devTypesCode = slice(template, '    async function loadDevTypes(', '    function markStepDone(');

const HOSTILE = '<img src=x onerror=alert(1)>';

function makeContext(response) {
  const els = {};
  const el = id => (els[id] ||= { id, innerHTML: '', value: '', disabled: false, focus() {},
    // Specchio minimo di DOMTokenList: add/remove (storico) + contains/toggle
    // usati da runCanvasDryRun per is-compact quando la review Canvas è aperta.
    classList: {
      _c: new Set(id === 'review-canvas' ? ['hidden'] : []),
      add(name) { this._c.add(name); },
      remove(name) { this._c.delete(name); },
      contains(name) { return this._c.has(name); },
      toggle(name, force) {
        const on = force === undefined ? !this._c.has(name) : !!force;
        if (on) this._c.add(name); else this._c.delete(name);
        return on;
      },
    } });
  const context = vm.createContext({
    t,
    featureName: '', devType: 'backend', sessionRevision: 0,
    ensurePipelineFeature: async () => true,
    getFeatureName: () => 'feature-x',
    updateChatControls() {},  // guida dell'intervista: fuori dal pezzo sotto esame
    document: { getElementById: el },
    fetch: async () => response,
  });
  vm.runInContext(escapeCode + errorCode + dryRunCode + devTypesCode, context);
  return { context, el };
}
const ok = data => ({ ok: true, json: async () => data });

// Controllo di base: escapeHtml copre anche le virgolette (serve per i valori in attributo).
{
  const { context } = makeContext(ok({}));
  assert.equal(context.escapeHtml(`<a href="x" title='y'>&`), '&lt;a href=&quot;x&quot; title=&#39;y&#39;&gt;&amp;');
}

async function main() {
  // 1. Sorgenti e documenti normativi con markup nei campi del corpus: restano testo.
  {
    const { context, el } = makeContext(ok({
      sources: [{ doc_id: `doc${HOSTILE}.md`, section: `Titolo ${HOSTILE}`, branch: `dominio${HOSTILE}`,
                  dense_score: 0.5, sparse_score: null, colbert_score: `n/d${HOSTILE}`, authority: 1 }],
      governed_docs: [{ doc_id: `regola${HOSTILE}.md`, authority: 0.9, chars: 120 }],
    }));
    await context.runCanvasDryRun();
    const html = el('dryrun-body').innerHTML;
    assert.ok(!html.includes('<img'), html);
    assert.ok(html.includes('doc&lt;img src=x onerror=alert(1)&gt;.md'), html);
    assert.ok(html.includes(' § Titolo &lt;img src=x onerror=alert(1)&gt;'), html);
    assert.ok(html.includes('[dominio&lt;img src=x onerror=alert(1)&gt;]'), html);
    assert.ok(html.includes('regola&lt;img src=x onerror=alert(1)&gt;.md'), html);
  }
  // 2. Input innocuo: markup risultante identico a quello di prima della correzione.
  {
    const { context, el } = makeContext(ok({
      sources: [{ doc_id: 'guida.md', section: 'Intro', branch: 'tecnico',
                  dense_score: 0.5, sparse_score: null, colbert_score: 0.25, authority: 1 }],
      governed_docs: [{ doc_id: 'regole.md', authority: 0.9, chars: 120 }],
    }));
    await context.runCanvasDryRun();
    const html = el('dryrun-body').innerHTML;
    assert.ok(html.includes('<span class="font-mono truncate"><span class="text-blue-400">[tecnico]</span> guida.md § Intro</span>'
      + '<span class="font-mono text-slate-400 shrink-0">D 0.500 · S — · CB 0.250 · A 1.000</span>'), html);
    assert.ok(html.includes('px-2 py-0.5">regole.md <span class="text-blue-400">A 0.900</span> · 120 char</span>'), html);
  }
  // 3. Nota del server (contiene il testo di un'eccezione) e messaggio d'errore HTTP.
  {
    const { context, el } = makeContext(ok({ sources: [], governed_docs: [], note: `Retrieval fallito: ${HOSTILE}` }));
    await context.runCanvasDryRun();
    const html = el('dryrun-body').innerHTML;
    assert.equal(html, '<span class="text-amber-400">Retrieval fallito: &lt;img src=x onerror=alert(1)&gt;</span>');
  }
  {
    const { context, el } = makeContext({ ok: false, status: 400, json: async () => ({ detail: HOSTILE }) });
    await context.runCanvasDryRun();
    const html = el('dryrun-body').innerHTML;
    assert.equal(html, '<span class="text-red-400">❌ &lt;img src=x onerror=alert(1)&gt;</span>');
  }
  // 4. Tendina dev-types: il nome di cartella va sia nell'attributo value sia nel testo.
  {
    const { context, el } = makeContext(ok({ dev_types: ['backend', `x" onmouseover="alert(1)`, HOSTILE] }));
    await context.loadDevTypes();
    const html = el('dev-type-select').innerHTML;
    assert.ok(!html.includes('<img') && !html.includes('" onmouseover'), html);
    assert.ok(html.includes('<option value="backend">backend</option>'), html);
    assert.ok(html.includes('<option value="x&quot; onmouseover=&quot;alert(1)">'), html);
  }
  console.log('Dry-run e dev-types: dati del corpus, note ed errori restano testo, markup innocuo invariato');
}

main().catch(err => { console.error(err); process.exit(1); });
