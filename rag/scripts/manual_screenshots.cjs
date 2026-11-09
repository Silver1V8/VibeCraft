// Rigenera gli screenshot di manuale-utente e percorso-guidato (static/manuale/*.html).
// Le catture vanno in --out come PNG; poi `scripts/embed_manual_screenshots.py` le converte
// in webp e le sostituisce nei quattro HTML (IT ed EN condividono le stesse immagini).
//
// Prerequisiti: server in ascolto (default http://127.0.0.1:8000), un progetto indicizzato e
// allineato (default Tetris), Ollama acceso per la domanda reale della Console. Playwright
// deve essere raggiungibile da NODE_PATH (stessa versione della CI, vedi docs/eval-e-ci.md).
//
//   NODE_PATH=<dir>/node_modules node scripts/manual_screenshots.cjs --out <dir> [--only s05,s13]
//
// Principi: dati reali del progetto ovunque sia possibile e senza scrivere nulla; le azioni che
// scriverebbero nel progetto (staging, import, archivio, agente) restano simulate con
// page.route, quindi una cattura non cambia mai i file né l'indice del progetto.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const argv = process.argv.slice(2);
const opt = (name, def) => { const i = argv.indexOf('--' + name); return i >= 0 ? argv[i + 1] : def; };
const OUT = path.resolve(opt('out', 'manual-shots'));
const BASE = opt('base', 'http://127.0.0.1:8000');
const PROJECT = opt('project', 'Tetris');
const ONLY = opt('only', '') ? opt('only', '').split(',') : null;
const W = 1600, H = 1000;
fs.mkdirSync(OUT, { recursive: true });

let browser;
const contexts = {};
async function context(scale) {
  if (!contexts[scale]) {
    contexts[scale] = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: scale,
      colorScheme: 'dark', locale: 'it-IT' });
    await contexts[scale].addCookies([{ name: 'ui_theme', value: 'classic', url: BASE }]);
  }
  return contexts[scale];
}

// Sostituisce nelle risposte di /api/projects lo stato che serve alla schermata.
function patchProjects(page, patch) {
  return page.route(/\/api\/projects(\/[^/?]+)?(\?.*)?$/, async route => {
    try {
      if (route.request().method() !== 'GET') return await route.continue();
      const response = await route.fetch();
      let body = await response.json();
      if (Array.isArray(body.projects)) body.projects = patch(body.projects, true);
      else if (body.id) body = patch([body], false)[0] ?? body;
      await route.fulfill({ response, json: body });
    } catch (_) { /* pagina chiusa a metà richiesta: la cattura è già finita */ }
  });
}
const aligned = list => list.map(p => ({ ...p, stale: false, stale_pending: false }));

async function open(scale, urlPath, { patch, before } = {}) {
  const page = await (await context(scale)).newPage();
  page.on('pageerror', e => console.log('  pageerror:', e.message));
  if (patch) await patchProjects(page, patch);
  if (before) await before(page);
  await page.goto(BASE + urlPath);
  await page.locator('#workspace-nav:not([hidden]), #project-welcome:not([hidden])').first().waitFor({ timeout: 20000 });
  return page;
}
// L'iframe visibile della pagina corrente (la shell ne tiene una per sezione).
async function frame(page, readySelector) {
  await page.waitForFunction(() => [...document.querySelectorAll('iframe')].some(f => !f.hidden && f.contentDocument?.body));
  const handle = await page.evaluateHandle(() => [...document.querySelectorAll('iframe')].find(f => !f.hidden && f.contentDocument?.body));
  const fr = await handle.asElement().contentFrame();
  if (readySelector) await fr.waitForSelector(readySelector, { timeout: 20000 });
  return fr;
}
const settle = (page, ms = 900) => page.waitForTimeout(ms);
const save = async (page, id, { el, clip } = {}) => {
  const file = path.join(OUT, id + '.png');
  if (el) await el.screenshot({ path: file });
  else await page.screenshot({ path: file, ...(clip ? { clip } : {}) });
  console.log('  ok', id);
};

// ---- Domanda reale della Console, registrata una volta e riusata dalle altre catture ----
const QUESTION = opt('question', 'Come funziona il punteggio e quando aumenta il livello?');
const askFixture = path.join(OUT, 'ask_fixture.ndjson');
async function mockAsk(page, { pending = false, fixture = askFixture } = {}) {
  await page.route('**/ask', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    if (pending) return new Promise(() => {}); // resta "in corso" per la cattura
    if (fs.existsSync(fixture)) return route.fulfill({ contentType: 'application/x-ndjson', body: fs.readFileSync(fixture, 'utf8') });
    const response = await route.fetch({ timeout: 300000 });
    const body = await response.text();
    fs.writeFileSync(fixture, body);
    await route.fulfill({ response, body });
  });
}
async function askedConsole(scale, { question = QUESTION, fixture = askFixture } = {}) {
  const page = await open(scale, `/?project=${PROJECT}`, { patch: aligned, before: p => mockAsk(p, { fixture }) });
  const fr = await frame(page, '#question-input');
  await fr.fill('#question-input', question);
  await fr.click('#ask-btn');
  await fr.waitForSelector('#answer-text:not(:empty)', { timeout: 300000 });
  await settle(page, 1500);
  return { page, fr };
}

const shots = {};

// ===================== Shell: benvenuto, finestre, barra =====================
shots.s01 = async () => {
  const page = await open(1, '/', { patch: () => [] });
  await settle(page); await save(page, 's01');
};
shots.s02 = async () => {
  const page = await open(1, '/', { patch: list => aligned(list).filter(p => ['legacy', PROJECT].includes(p.id)) });
  await settle(page); await save(page, 's02');
};
shots.s03 = async () => {
  const page = await open(1, '/', { patch: list => aligned(list).filter(p => ['legacy', PROJECT].includes(p.id)) });
  await page.getByRole('button', { name: /Nuovo progetto/ }).first().click();
  await page.locator('dialog[open] input, [role=dialog] input').first().fill('contabilita-2027');
  await settle(page, 500); await save(page, 's03');
};
shots.s04 = async () => {
  const page = await open(1, '/', { patch: list => aligned(list).filter(p => ['legacy', PROJECT].includes(p.id)) });
  await page.getByRole('button', { name: /Apri progetto/ }).first().click();
  await settle(page, 500); await save(page, 's04');
};
const barShot = (id, patch) => async () => {
  const page = await open(1, `/?project=${PROJECT}`, { patch });
  await frame(page); await settle(page, 1200);
  await save(page, id, { clip: { x: 0, y: 0, width: W, height: 156 } });
};
shots.s05 = barShot('s05', aligned);
shots.s06 = barShot('s06', list => aligned(list).map(p => ({ ...p, index_status: 'not_indexed', index_version: null })));
shots.s07 = barShot('s07', list => aligned(list).map(p => ({ ...p, index_status: 'indexing' })));
shots.s08 = barShot('s08', list => list.map(p => ({ ...p, stale: true, stale_pending: false })));
shots.s10 = async () => {
  // Stessa schermata nei due temi: l'embed compone metà Classico e metà Matrix.
  for (const theme of ['classic', 'matrix']) {
    const ctx = await context(1);
    await ctx.addCookies([{ name: 'ui_theme', value: theme, url: BASE }]);
    const page = await open(1, `/?project=${PROJECT}`, { patch: aligned });
    await frame(page, '#question-input'); await settle(page, 1800);
    await page.screenshot({ path: path.join(OUT, `s10_${theme}.png`) });
    await page.close();
  }
  await (await context(1)).addCookies([{ name: 'ui_theme', value: 'classic', url: BASE }]);
  console.log('  ok s10 (s10_classic.png + s10_matrix.png)');
};

// ===================== Console =====================
const consoleOpen = async (scale, { pending = false } = {}) => {
  const page = await open(scale, `/?project=${PROJECT}`, { patch: aligned, before: p => mockAsk(p, { pending }) });
  const fr = await frame(page, '#question-input'); await settle(page, 1200);
  return { page, fr };
};
shots.s13 = async () => { const { page } = await consoleOpen(1); await save(page, 's13'); };
const questionCard = fr => fr.locator('#left-panel > section, #left-panel > div').first();
shots.s15 = async () => {
  const { page, fr } = await consoleOpen(2);
  await fr.locator('summary:has-text("Opzioni avanzate"), details summary').first().click();
  await fr.fill('#question-input', QUESTION);
  await settle(page, 400); await save(page, 's15', { el: questionCard(fr) });
};
shots.s16 = async () => {
  const { page, fr } = await consoleOpen(2, { pending: true });
  await fr.fill('#question-input', QUESTION);
  await fr.click('#ask-btn'); await fr.waitForSelector('#loader:not(.hidden)', { timeout: 10000 }).catch(() => {});
  await settle(page, 2500);
  // Dal riquadro della domanda fino al caricamento (tre pallini + secondi), che sta sotto.
  const card = await questionCard(fr).boundingBox(), loader = await fr.locator('#loader').boundingBox();
  await save(page, 's16', { clip: { x: card.x, y: card.y, width: card.width, height: loader.y + loader.height - card.y + 12 } });
};
shots.s18 = async () => { const { page } = await askedConsole(1); await save(page, 's18'); };
shots.s19 = async () => {
  const { page, fr } = await askedConsole(2);
  const card = await fr.locator('#scores-card').boundingBox(), list = await fr.locator('#scores-list').boundingBox();
  await save(page, 's19', { clip: { x: card.x, y: card.y, width: card.width, height: list.y + list.height - card.y + 16 } });
};
shots.s20 = async () => {
  const { page, fr } = await consoleOpen(2);
  await save(page, 's20', { el: fr.locator('#project-status-list').locator('xpath=ancestor::section[1] | ancestor::div[1]').first() });
};
const graphShot = (id, mode, extra) => async () => {
  const { page, fr } = await askedConsole(1);
  await fr.click('#tab-graph-btn'); await settle(page, 1200);
  await fr.click(mode === '3d' ? '#view-mode-3d-btn' : '#view-mode-2d-btn'); await settle(page, 4000);
  if (extra) await extra(page, fr);
  await save(page, id);
};
shots.s21 = graphShot('s21', '3d');
shots.s22 = graphShot('s22', '2d');
shots.s23 = graphShot('s23', '2d', async (page, fr) => {
  // Seleziona il nodo con più connessioni (vis.Network + renderNodeDetails della pagina).
  const id = await fr.evaluate(() => {
    const ids = network.body.data.nodes.getIds();
    const top = ids.sort((a, b) => network.getConnectedNodes(b).length - network.getConnectedNodes(a).length)[0];
    network.selectNodes([top]); renderNodeDetails(top); return top;
  });
  console.log('   nodo:', id); await settle(page, 1200);
});
shots.s25 = async () => {
  const { page, fr } = await askedConsole(1);
  await fr.click('#tab-context-btn'); await settle(page, 800); await save(page, 's25');
};
shots.s26 = async () => {
  const { page, fr } = await askedConsole(1);
  await fr.click('#tab-json-btn'); await settle(page, 800); await save(page, 's26');
};

// Percorso guidato: l'ispezione di una domanda fuori corpus (risposta reale del modello, che si astiene).
shots.t05 = async () => {
  const { page, fr } = await askedConsole(1, { question: opt('offcorpus', 'Qual è la capitale della Francia?'),
    fixture: path.join(OUT, 'ask_fixture_offcorpus.ndjson') });
  await fr.click('#tab-json-btn'); await settle(page, 800); await save(page, 't05');
};

// ===================== Analisi =====================
shots.s63 = async () => {
  const page = await open(1, `/analysis?project=${PROJECT}`, { patch: aligned });
  await frame(page, '#map-canvas'); await settle(page, 3500); await save(page, 's63');
};
shots.s64 = async () => {
  const page = await open(2, `/analysis?project=${PROJECT}`, { patch: aligned });
  const fr = await frame(page, '#map-dups'); await settle(page, 3500);
  const b = await fr.locator('#map-dups').boundingBox(), sec = await fr.locator('#section-map').boundingBox();
  await save(page, 's64', { clip: { x: sec.x, y: b.y - 10, width: sec.width, height: b.height + 22 } });
};
const NODE = opt('node', 'game_design/generato-310bec76.md');
shots.s65 = async () => {
  const page = await open(2, `/analysis?project=${PROJECT}`, { patch: aligned });
  const fr = await frame(page, '#node-search'); await settle(page, 2500);
  await fr.fill('#node-search', NODE); await fr.locator('#node-search').press('Enter');
  await fr.click('#section-node button:has-text("Mostra")').catch(() => {});
  await settle(page, 2500); await save(page, 's65', { el: fr.locator('#section-node') });
};
shots.s66 = async () => {
  const page = await open(2, `/analysis?project=${PROJECT}`, { patch: aligned });
  const fr = await frame(page, '#node-search'); await settle(page, 2500);
  await fr.fill('#node-search', NODE); await fr.click('#section-node button:has-text("Mostra")').catch(() => {});
  await settle(page, 2500);
  const sec = await fr.locator('#section-node').boundingBox(), st = await fr.locator('#ripple-status').boundingBox();
  const cv = await fr.locator('#ripple-canvas').boundingBox();
  await save(page, 's66', { clip: { x: sec.x - 6, y: st.y - 14, width: sec.width + 12, height: cv.y + cv.height - st.y + 70 } });
};

// ===================== Eval e Guida =====================
// Tetris non ha ancora una cronologia di eval: la pagina mostra quella reale del progetto che ce l'ha.
const EVAL_SOURCE = opt('eval-source', 'legacy');
const evalHistory = page => page.route('**/api/eval/history*', async route => {
  try {
    const real = await (await fetch(`${BASE}/api/eval/history?limit=200`, { headers: { 'X-VibeCraft-Project': EVAL_SOURCE } })).json();
    await route.fulfill({ json: { ...real, project_id: PROJECT } });
  } catch (_) { /* pagina chiusa */ }
});
const evalOpen = async scale => {
  const page = await open(scale, `/eval?project=${PROJECT}`, { patch: aligned, before: evalHistory });
  const fr = await frame(page, '#cards'); await settle(page, 2500); return { page, fr };
};
shots.s67 = async () => { const { page } = await evalOpen(1); await save(page, 's67'); };
shots.s68 = async () => {
  const { page, fr } = await evalOpen(2);
  await fr.locator('#data-table > summary').click(); await settle(page, 500);
  await save(page, 's68', { el: fr.locator('#data-table') });
};
shots.s69 = async () => {
  const { page, fr } = await evalOpen(2);
  await save(page, 's69', { el: fr.locator('#cq-status').locator('xpath=ancestor::section[1] | ancestor::div[2]').first() });
};
shots.s70 = async () => {
  const page = await open(1, `/infografica?project=${PROJECT}`, { patch: aligned });
  await frame(page, '#rag-mermaid'); await settle(page, 2500); await save(page, 's70');
};
shots.s71 = async () => {
  const page = await open(1, `/infografica?project=${PROJECT}`, { patch: aligned });
  const fr = await frame(page, '#rag-mermaid'); await settle(page, 2500);
  await fr.evaluate(() => {
    const card = [...document.querySelectorAll('h3, h2')].find(h => /Indicizzatore/.test(h.textContent));
    (card?.closest('div, article, section') || document.getElementById('rag-mermaid')).scrollIntoView({ block: 'center' });
  });
  await settle(page, 600); await save(page, 's71');
};

// ===================== Intake (risposte del server simulate: nessuna scrittura) =====================
const iso = mins => new Date(Date.now() - mins * 60000).toISOString();
const FALLBACK_META = { motore: 'markitdown', versione_motore: '0.1.7', source_filename: 'specifica-sfide.pdf',
  sha256: '9f2c4e7a1b8d03c5a6e2f1d4b7c9a0e3f5d8b2c1a4e7f0936d5c8b1a2e4f7d90',
  fallback: { motivo: 'Docling non ha convertito il file: modelli non scaricati (scripts/fetch_docling_models.py).' },
  avvisi: ['PDF di 5 pagine, 1 senza testo selezionabile: OCR non disponibile in locale.'],
  pdf: { pagine: 5, pagine_senza_testo: 1, ocr: false } };
const STAGED = [
  { id: 'regole-gioco', filename: 'regole-gioco.md', source: 'imported', staged_at: iso(95), metadata: { motore: 'nativo' } },
  { id: 'tabella-punteggi', filename: 'tabella-punteggi.xlsx', source: 'imported', staged_at: iso(80),
    metadata: { motore: 'openpyxl', versione_motore: '3.1.5' } },
  { id: 'specifica-sfide', filename: 'specifica-sfide.pdf', source: 'imported', staged_at: iso(62), metadata: FALLBACK_META },
  { id: 'gen-4aadf158', filename: 'generato-4aadf158.md', source: 'generated', staged_at: iso(41), metadata: { motore: 'nativo' } },
  { id: 'gen-79cb819f', filename: 'generato-79cb819f.md', source: 'generated', staged_at: iso(40), metadata: { motore: 'nativo' } },
  { id: 'brief-game', filename: 'project-brief-game.md', source: 'brief', staged_at: iso(12), metadata: { motore: 'nativo' } },
];
const PREVIEW = { id: 'specifica-sfide', filename: 'specifica-sfide.pdf', metadata: FALLBACK_META, files: {},
  markdown: ['# Specifica delle sfide giornaliere', '', 'Documento di riferimento per le sfide che il gioco propone ogni giorno.', '',
    '| Sfida | Obiettivo | Ricompensa |', '|---|---|---|', '| Velocista | 40 righe in 3 minuti | 500 punti |',
    '| Combo | 3 Tetris consecutivi | 800 punti |', '', 'Le sfide si rinnovano ogni giorno alle 00:00, ora locale.'].join('\n') };
const intakeMocks = async page => {
  await page.route(/\/api\/intake\/staged(\?.*)?$/, r => r.fulfill({ json: { staged: STAGED } }).catch(() => {}));
  await page.route(/\/api\/intake\/staged\/[^/]+\/preview$/, r => r.fulfill({ json: PREVIEW }).catch(() => {}));
  await page.route('**/api/intake/docs', async route => {
    if (route.request().method() !== 'POST') return route.continue();
    const name = (/filename="([^"]+)"/.exec(route.request().postData() || '') || [])[1] || '';
    const answer = name === 'dettagli-test.pdf' ? { status: 409, json: { detail: 'Documento già in staging: SHA-256 identico a specifica-sfide.pdf.' } }
      : name === 'verbale-riunione.doc' ? { status: 422, json: { detail: 'Conversione non riuscita: per i file DOC serve LibreOffice, che non è installato.' } }
      : { json: { id: 'nuovo', filename: name, metadata: name.endsWith('.pdf') ? FALLBACK_META : { motore: 'nativo' } } };
    await route.fulfill(answer).catch(() => {});
  });
};
const intakeOpen = async scale => {
  const page = await open(scale, `/intake?project=${PROJECT}`, { patch: aligned, before: intakeMocks });
  const fr = await frame(page, '#section-staging .staged-item'); await settle(page, 1000); return { page, fr };
};
// Area sotto la barra e la navigazione, come gli originali da 1600x833.
const belowBar = async page => {
  const nav = await page.locator('#workspace-nav').boundingBox();
  const y = Math.ceil(nav.y + nav.height) + 1;
  return { x: 0, y, width: W, height: H - y };
};
const box = loc => loc.boundingBox();
shots.s29 = async () => { const { page } = await intakeOpen(1); await save(page, 's29'); };
shots.s30 = async () => {
  const { page, fr } = await intakeOpen(2);
  await fr.fill('#gen-descrizione', 'Regole di punteggio, livelli e combo del gioco, con esempi di calcolo.');
  const t = await box(fr.locator('#gen-descrizione')), b = await box(fr.locator('#gen-btn')), sec = await box(fr.locator('#section-genera'));
  await settle(page, 300);
  await save(page, 's30', { clip: { x: sec.x, y: t.y - 8, width: sec.width, height: b.y + b.height - t.y + 24 } });
};
shots.s32 = async () => {
  const { page, fr } = await intakeOpen(2);
  await fr.evaluate(() => document.getElementById('dropzone').classList.add('dragover'));
  const d = await box(fr.locator('#dropzone')), sec = await box(fr.locator('#section-importa'));
  await save(page, 's32', { clip: { x: sec.x, y: d.y - 14, width: sec.width, height: 260 } });
};
shots.s33 = async () => {
  const { page, fr } = await intakeOpen(1);
  const f = (name, type) => ({ name, mimeType: type, buffer: Buffer.from('x') });
  await fr.setInputFiles('#file-input', [f('regole-gioco.md', 'text/markdown'), f('specifica-sfide.pdf', 'application/pdf'),
    f('dettagli-test.pdf', 'application/pdf'), f('verbale-riunione.doc', 'application/msword')]);
  await settle(page, 1500);
  await fr.evaluate(() => document.getElementById('section-importa').scrollIntoView({ block: 'start' })); await settle(page, 400);
  await save(page, 's33', { clip: await belowBar(page) });
};
shots.s34 = async () => {
  const { page, fr } = await intakeOpen(2);
  await save(page, 's34', { el: fr.locator('#section-staging') });
};
const openDetail = async (scale, index = 2) => {
  const { page, fr } = await intakeOpen(scale);
  await fr.locator('#staging-list .staged-item').nth(index).locator('button').click();
  await fr.waitForSelector('#staging-detail .review-controls', { timeout: 10000 }); await settle(page, 800);
  return { page, fr };
};
shots.s35 = async () => {
  const { page, fr } = await openDetail(1);
  await fr.evaluate(() => document.getElementById('staging-detail').scrollIntoView({ block: 'start' })); await settle(page, 500);
  await save(page, 's35', { clip: await belowBar(page) });
};
const padded = async (loc, pad = 14) => {
  await loc.evaluate(el => el.scrollIntoView({ block: 'center' })); await loc.page().waitForTimeout(300);
  const b = await loc.boundingBox();
  return { x: Math.max(0, b.x - pad), y: Math.max(0, b.y - pad), width: b.width + 2 * pad, height: b.height + 2 * pad };
};
const reviewRow = fr => fr.locator('#staging-detail .review-controls').nth(1);
shots.s37 = async () => {
  const { page, fr } = await openDetail(2);
  await fr.fill('#preview-nomefile', 'specifica-sfide.md'); await settle(page, 300);
  await save(page, 's37', { clip: await padded(reviewRow(fr)) });
};
shots.s38 = async () => {
  const { page, fr } = await openDetail(2);
  await fr.fill('#preview-motivo', 'Duplicato: le sfide sono già descritte in regole-gioco.md'); await settle(page, 300);
  await save(page, 's38', { clip: await padded(reviewRow(fr)) });
};
const PLAN = (mode, tot, extra = {}) => ({ plan_id: 'piano-demo', mode, totali: tot,
  nuovi: ['Game/index.html', 'Game/style.css', 'Game/game.js', 'Game/board.js', 'Game/pieces.js', 'Game/README.md'],
  esclusi: ['Game/node_modules', 'Game/.git', 'Game/dist', 'Game/package-lock.json'], conflitti: [], ...extra });
const projectImport = async (scale, plan, apply) => {
  const { page, fr } = await intakeOpen(scale);
  await page.route('**/api/intake/project/plan', r => r.fulfill({ json: plan }).catch(() => {}));
  if (apply) await page.route('**/api/intake/project/apply', r => r.fulfill({ json: apply }).catch(() => {}));
  await fr.selectOption('#prj-target', { label: 'Game' }).catch(() => {});
  await fr.fill('#prj-path', 'C:\\progetti\\tetris-web'); return { page, fr };
};
shots.s39 = async () => {
  const { page, fr } = await projectImport(2, PLAN('bootstrap', {}));
  const p = await box(fr.locator('#prj-path')), sec = await box(fr.locator('#section-progetti'));
  await save(page, 's39', { clip: { x: sec.x, y: p.y - 26, width: sec.width, height: sec.y + sec.height - p.y + 34 } });
};
const importShot = (id, plan, apply) => async () => {
  const { page, fr } = await projectImport(1, plan, apply);
  await fr.click('#prj-plan-btn'); await fr.waitForSelector('#prj-plan-result .file-row', { timeout: 10000 });
  if (apply) { await fr.click('#prj-apply-btn'); await fr.waitForSelector('#prj-apply-result .file-row', { timeout: 10000 }); }
  await fr.evaluate(() => document.getElementById('section-progetti').scrollIntoView({ block: 'start' })); await settle(page, 600);
  await save(page, id, { clip: await belowBar(page) });
};
shots.s40 = importShot('s40', PLAN('bootstrap', { nuovi: 6, identici: 0, conflitti: 0, esclusi: 4 }));
shots.s41 = importShot('s41', PLAN('additive', { nuovi: 3, identici: 4, conflitti: 2, esclusi: 4 },
  { conflitti: ['Game/game.js', 'Game/style.css'], nuovi: ['Game/board.js', 'Game/pieces.js', 'Game/README.md'] }));
shots.s42 = importShot('s42', PLAN('bootstrap', { nuovi: 6, identici: 0, conflitti: 0, esclusi: 4 }),
  { target: 'Game', totali: { copiati: 6 }, backup: null, reindex: { reindexed_docs: 0, upserted_chunks: 0, version: 'v20261109T104113' } });

// ===================== Pipeline (feature reale; esecuzione agente, Drift e Archivio simulati) =====================
const FEATURE = opt('feature', 'gioco1');
const featureFile = name => fs.readFileSync(path.resolve(__dirname, '..', '..', 'projects', PROJECT, 'changes', FEATURE, name), 'utf8');
const pipelineOpen = async (scale, { feature, step, before } = {}) => {
  const page = await open(scale, `/pipeline?project=${PROJECT}`, { patch: aligned, before });
  const fr = await frame(page, '#feature-name-input'); await settle(page, 800);
  if (feature) {
    await fr.fill('#feature-name-input', feature); await fr.click('#load-feature-btn');
    await fr.waitForSelector('#files-control-list :text("pronto")', { timeout: 20000 }).catch(() => {});
    await settle(page, 1800);
  }
  if (step) { await fr.click('#step-btn-' + step); await settle(page, 1200); }
  return { page, fr };
};
const approveSpec = async (page, fr) => {
  await fr.click('#step-btn-3'); await settle(page, 800);
  await fr.locator('button[data-click="approveSpec"]').click();
  await fr.waitForSelector('#gate-status-summary:not(:empty)', { timeout: 20000 }); await settle(page, 1200);
};
const scrollTo = (fr, sel, block = 'start') => fr.evaluate(([s, b]) => document.querySelector(s).scrollIntoView({ block: b }), [sel, block]);
// Conferma di un dialogo di conferma (sta nella shell o nell'iframe).
const confirmDialogButton = async (fr, name) => {
  const btn = fr.locator('#confirm-host button').filter({ hasText: name }).first();
  await btn.waitFor({ timeout: 8000 }); return btn;
};
shots.s44 = async () => { const { page } = await pipelineOpen(1); await save(page, 's44'); };
shots.s45 = async () => {
  const { page, fr } = await pipelineOpen(2, { feature: FEATURE });
  await fr.evaluate(() => savePipelineDraft()); await settle(page, 400);
  await fr.click('#load-feature-btn'); await settle(page, 1800);
  await save(page, 's45', { el: fr.locator('#pipeline-aside') });
};
shots.s48 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 1 });
  await scrollTo(fr, '#chat-input', 'start'); await settle(page, 500);
  await save(page, 's48', { clip: await belowBar(page) });
};
shots.s49 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 1 });
  await save(page, 's49', { el: fr.locator('#review-explore') });
};
shots.s50 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 2 });
  await fr.click('#canvas-dryrun-btn');
  await fr.waitForFunction(() => { const b = document.getElementById('dryrun-body'); return b && b.textContent.length > 40 && !/Recupero/.test(b.textContent); },
    null, { timeout: 180000 });
  // L'elenco sta in un contenitore con scorrimento: per la cattura lo si mostra per intero.
  await fr.evaluate(() => document.querySelectorAll('#dryrun-card, #dryrun-body, #dryrun-body *').forEach(el => {
    el.style.maxHeight = 'none'; el.style.overflow = 'visible'; }));
  await settle(page, 1000);
  await save(page, 's50', { el: fr.locator('#dryrun-card') });
};
shots.s52 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 3 });
  await save(page, 's52', { el: fr.locator('#review-spec') });
};
shots.s53 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE });
  await approveSpec(page, fr);
  await fr.evaluate(() => { document.getElementById('validate-details-root').open = true; });
  await scrollTo(fr, '#validate-card', 'start'); await settle(page, 600);
  await save(page, 's53', { clip: await belowBar(page) });
};
shots.s54 = async () => {
  const before = page => page.route(/\/api\/pipeline\/gate\?/, async route => {
    try {
      const response = await route.fetch(); const body = await response.json();
      const canvas = featureFile('canvas.md'), spec = featureFile('spec.md');
      body.comparison = { validation_id: 'val-20261109-001',
        canvas: { current: canvas, validated: canvas.replace('Obiettivo', 'Scopo') },
        spec: { current: spec, validated: spec.split('\n').slice(0, -6).join('\n') } };
      await route.fulfill({ response, json: body });
    } catch (_) { /* pagina chiusa */ }
  });
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, before });
  await approveSpec(page, fr);
  await fr.evaluate(() => { document.getElementById('validate-details-root').open = true; });
  await fr.getByRole('button', { name: /Confronta con la versione validata/ }).click(); await settle(page, 1500);
  await scrollTo(fr, '#gate-comparison', 'start'); await settle(page, 500);
  await save(page, 's54', { clip: await belowBar(page) });
};
shots.s55 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE });
  await approveSpec(page, fr);
  const c = await box(fr.locator('#final-prompt-card'));
  await save(page, 's55', { clip: { x: c.x, y: c.y, width: c.width, height: Math.min(c.height, 520) } });
};
shots.s56 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE });
  await approveSpec(page, fr);
  await scrollTo(fr, '#agent-run-btn', 'end'); await settle(page, 500);
  await save(page, 's56', { clip: await belowBar(page) });
};
const agentMode = (fr, mode) => fr.evaluate(m => {
  const sel = document.getElementById('agent-mode-select');
  const opt = [...sel.options].find(o => new RegExp(m, 'i').test(o.value + o.textContent)); sel.value = opt.value;
  sel.dispatchEvent(new Event('change', { bubbles: true })); return opt.value;
}, mode);
shots.s57 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE });
  await approveSpec(page, fr);
  await agentMode(fr, 'agentic'); await fr.click('#agent-run-btn'); await settle(page, 1200);
  await save(page, 's57');
};
shots.s58 = async () => {
  const before = page => page.route('**/api/pipeline/agent/run', async route => {
    try {
      const real = await (await fetch(`${BASE}/api/pipeline/gate?feature=${FEATURE}`, { headers: { 'X-VibeCraft-Project': PROJECT } })).json();
      await route.fulfill({ status: 409, json: { detail: real.gate } });
    } catch (_) { /* pagina chiusa */ }
  });
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, before });
  await approveSpec(page, fr);
  await agentMode(fr, 'agentic'); await fr.click('#agent-run-btn');
  await (await confirmDialogButton(fr, /Continua/)).click(); await settle(page, 1500);
  await save(page, 's58', { el: fr.locator('#agent-output') });
};
const streamMock = lines => page => page.route(/\/api\/pipeline\/(drift\/check|archive)\/stream/, async route => {
  await route.fulfill({ contentType: 'application/x-ndjson', body: lines.map(line => JSON.stringify({ type: 'log', line })).join('\n') + '\n' }).catch(() => {});
});
shots.s59 = async () => {
  const before = streamMock(['Verifica del drift su gioco1: confronto fra specifica e codice in code/Game.',
    'Copertura dichiarata: 9 file, 122369 caratteri, 1 lotto; nessun file escluso.', 'Analisi del lotto 1/1 (9 file) tramite LLM...']);
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 4, before });
  await fr.click('#drift-check-btn'); await fr.waitForSelector('#drift-report-box:not(:empty)', { timeout: 10000 }); await settle(page, 800);
  await save(page, 's59', { el: fr.locator('#drift-report-card') });
};
shots.s60 = async () => {
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 5 });
  await fr.click('#archive-btn'); await settle(page, 1000);
  await save(page, 's60');
};
shots.s61 = async () => {
  const before = streamMock(['Spostamento di changes/gioco1 in changes/archive/gioco1...', 'Revisione finale del Canvas affidata al modello locale...',
    'Ricostruzione del grafo e dell\'indice in corso...']);
  const { page, fr } = await pipelineOpen(1, { feature: FEATURE, step: 5, before });
  await fr.click('#archive-btn'); await (await confirmDialogButton(fr, /Archivia/)).click();
  await fr.waitForSelector('#archive-report-box:not(:empty)', { timeout: 10000 }); await settle(page, 800);
  // Lo stream simulato non porta l'esito finale: per mostrare il passo "in corso" si toglie la riga d'errore che ne deriva.
  await fr.evaluate(() => { const b = document.getElementById('archive-report-box'); b.textContent = b.textContent.replace(/\s*❌[\s\S]*$/, ''); });
  await save(page, 's61', { el: fr.locator('#archive-report-card') });
};

(async () => {
  browser = await chromium.launch({ headless: true, args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const ids = (ONLY || Object.keys(shots));
  for (const id of ids) {
    if (!shots[id]) { console.log('sconosciuto:', id); continue; }
    console.log(id);
    try { await shots[id](); } catch (e) { console.log('  FALLITO', id, e.message.split('\n')[0]); }
    for (const ctx of Object.values(contexts)) for (const p of ctx.pages()) {
      await p.unrouteAll({ behavior: 'ignoreErrors' }).catch(() => {}); await p.close().catch(() => {});
    }
  }
  await browser.close();
})();
