/* Script della pagina infografica.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
      /* themeVar / startMatrixRain / stopMatrixRain: vedi /static/shared.js.
         Al cambio tema shared.js invoca window.onThemeChange -> ridisegna Mermaid. */
      window.onThemeChange = function () { renderMermaidDiagram(); };

      /* ──────────── MERMAID: diagramma ricostruito a runtime dai colori del tema ──────────── */
      let mermaidRenderSeq = 0;
      function buildMermaidSource() {
        const userFill = themeVar('--mm-user-fill'),         userStroke = themeVar('--mm-user-stroke'),         userText = themeVar('--mm-user-text');
        const apiFill  = themeVar('--mm-fastapi-fill'),       apiStroke  = themeVar('--mm-fastapi-stroke'),      apiText  = themeVar('--mm-fastapi-text');
        const qFill    = themeVar('--mm-qdrant-fill'),        qStroke    = themeVar('--mm-qdrant-stroke'),       qText    = themeVar('--mm-qdrant-text');
        const nxFill   = themeVar('--mm-networkx-fill'),      nxStroke   = themeVar('--mm-networkx-stroke'),     nxText   = themeVar('--mm-networkx-text');
        const olFill   = themeVar('--mm-ollama-fill'),        olStroke   = themeVar('--mm-ollama-stroke'),       olText   = themeVar('--mm-ollama-text');
        const font     = themeVar('--mm-font', 'ui-sans-serif, system-ui');

        return `%%{init: {'theme': 'base', 'themeVariables': { 'fontFamily': '${font}'}}}%%
graph TD
    classDef user fill:${userFill},stroke:${userStroke},stroke-width:2px,color:${userText};
    classDef fastapi fill:${apiFill},stroke:${apiStroke},stroke-width:2px,color:${apiText};
    classDef qdrant fill:${qFill},stroke:${qStroke},stroke-width:2px,color:${qText};
    classDef networkx fill:${nxFill},stroke:${nxStroke},stroke-width:2px,color:${nxText};
    classDef ollama fill:${olFill},stroke:${olStroke},stroke-width:2px,color:${olText};

    U["Utente / App"]:::user
    S("FastAPI: api/routes_retrieval.py<br>Rotta POST /ask (X-API-Key)"):::fastapi
    RT{"core/router.py (M2)<br>domanda strutturale?"}:::fastapi
    GA[("NetworkX: graph_ops.graph_query<br>risposta diretta nodi/archi<br>status: graph_answer · no LLM")]:::networkx
    V{"Embedding bge-m3<br>dense + sparse"}:::fastapi
    Q[("Qdrant server (Docker)<br>Ricerca ibrida Top-K<br>fusione per rank")]:::qdrant
    NPY[("Sidecar ColBERT NPY<br>su disco, per documento")]:::fastapi
    CB{"Rerank ColBERT locale<br>+ peso autorità<br>+ precedenza fra fonti"}:::fastapi
    G[("NetworkX (graph.json)<br>Espansione BFS + fiducia sul cammino<br>seed = doc dei chunk")]:::networkx
    C["Contesto chunk-aware:<br>testo delle SEZIONI recuperate<br>+ struttura del grafo"]:::fastapi
    O{"core/llm.py · purpose ask<br>provider da config<br>(Ollama / Claude)"}:::ollama
    R["JSON: answer + graph_context<br>+ breakdown ranking + latency"]:::user

    U -->|"Domanda JSON"| S
    S -->|"0. Router deterministico"| RT
    RT -->|"strutturale → graph"| GA
    GA -->|"graph_result"| R
    RT -->|"altrimenti → hybrid"| V
    V -->|"1. Vettori Domanda"| Q
    Q -->|"2. Candidati Top-K"| CB
    NPY -->|"Chunk richiesti"| CB
    CB -->|"3. Chunk ri-ordinati"| G
    G -->|"4. Nodi Estesi"| C
    C -->|"5. Prompt Rigido + Fascicolo"| O
    O -->|"6. Testo Sintetizzato"| S
    S -->|"7. Ritorno payload"| R`;
      }

      async function renderMermaidDiagram() {
        const container = document.getElementById('rag-mermaid');
        const seq = ++mermaidRenderSeq;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'base',
          themeVariables: {
            primaryColor: themeVar('--mm-primary'),
            primaryTextColor: themeVar('--mm-primary-text'),
            primaryBorderColor: themeVar('--mm-primary-border'),
            lineColor: themeVar('--mm-line'),
            secondaryColor: themeVar('--mm-secondary'),
            tertiaryColor: themeVar('--mm-tertiary'),
            edgeLabelBackground: themeVar('--mm-edge-bg'),
            background: themeVar('--mm-bg'),
            fontFamily: themeVar('--mm-font', 'ui-sans-serif, system-ui'),
            fontSize: '15px',
          },
          // Spaziatura di default (~50px) comprimeva gli 11 nodi in una colonna
          // stretta: piu respiro fra un livello e l'altro del flusso TD.
          flowchart: { nodeSpacing: 40, rankSpacing: 65, padding: 12 },
        });
        const source = buildMermaidSource();
        try {
          const { svg } = await mermaid.render('rag-mermaid-svg-' + seq, source);
          if (seq === mermaidRenderSeq) container.innerHTML = svg;
        } catch (e) {
          container.innerHTML = `<p style="color:#f87171">Errore nel rendering del diagramma: ${escapeHtml(e.message)}</p>`;
        }
      }

      /* ──────────── KPI REALI DA /api/health ────────────
         La pagina descriveva il sistema senza mostrarne un solo dato: nessuna
         metrica, nessuna fonte, nessuna evidenza. Dodici blocchi che dichiarano
         capacita non generano fiducia — questi numeri si, perche vengono
         dall'indice vivo e cambiano insieme a lui. */
      /* `href` opzionale: dove esiste una pagina che approfondisce il dato, la
         card ci porta. Erano dodici blocchi senza una sola azione possibile. */
      function kpiCard(etichetta, valore, nota, tono, href) {
        const colori = { ok: 'text-emerald-700', warn: 'text-orange-700', bad: 'text-pink-600', neutro: 'text-slate-800' };
        // La dimensione segue la lunghezza: un identificatore di versione non
        // sta in 143px a 24px di corpo, e a 375px la card sforava.
        const v = String(valore);
        const corpo = v.length > 13 ? 'text-base' : v.length > 8 ? 'text-xl' : 'text-2xl';
        const dentro = `
          <div class="text-xs uppercase tracking-widest text-slate-500 mb-1">${escapeHtml(etichetta)}</div>
          <div class="${corpo} font-bold font-mono break-words ${colori[tono] || colori.neutro}">${escapeHtml(v)}</div>
          ${nota ? `<div class="text-xs text-slate-500 mt-1 break-words">${escapeHtml(nota)}</div>` : ''}`;
        const base = 'bg-white glass-card rounded-xl p-4 border-t-4 border-slate-700 block min-w-0';
        return href
          ? `<a href="${href}" class="${base} no-underline hover-lift">${dentro}
               <div class="text-xs text-blue-700 mt-2">Apri →</div></a>`
          : `<div class="${base}">${dentro}</div>`;
      }

      async function caricaKpi() {
        const grid = document.getElementById('kpi-grid');
        const stato = document.getElementById('kpi-stato');
        try {
          const res = await fetch('/api/health');
          if (!res.ok) throw new Error('HTTP ' + res.status);
          const h = await res.json();
          const snap = h.snapshot || {}, ev = h.eval || {}, dep = h.dependencies || {};
          const nf = n => (typeof n === 'number' ? n.toLocaleString('it-IT') : '—');
          const recall = typeof ev.last_recall === 'number'
            ? (ev.last_recall * 100).toFixed(1) + '%' : '—';
          const trend = { up: '↑ in salita', down: '↓ in discesa', flat: '→ stabile' }[ev.trend] || ev.trend || '';
          // Il tono segue la soglia dell'eval-gate, che ora arriva NEL PAYLOAD (A2b): era
          // scritta a mano come 0.9 mentre il gate stava gia' a 0.75, quindi la dashboard
          // poteva colorare di rosso una recall che il gate accettava senza riserve.
          const soglia = typeof ev.min_recall === 'number' ? ev.min_recall : 0.9;
          const tonoRecall = typeof ev.last_recall !== 'number' ? 'neutro'
                           : ev.last_recall >= soglia ? 'ok' : 'bad';

          grid.innerHTML = [
            kpiCard(ev.key || 'recall', recall, trend + ' · ' + (ev.history_points ?? 0) + ' misurazioni', tonoRecall, '/eval'),
            kpiCard('Nodi nel grafo', nf(snap.graph_nodes), nf(snap.graph_edges) + ' archi', 'neutro', '/analysis'),
            kpiCard('Sezioni indicizzate', nf(snap.chunks), 'chunk con vettori ColBERT', 'neutro', '/'),
            kpiCard('Versione CURRENT', snap.version || '—', (h.manifest && h.manifest.stale) ? 'manifest da aggiornare' : 'manifest allineato',
                    (h.manifest && h.manifest.stale) ? 'warn' : 'ok'),
            kpiCard('Qdrant', dep.qdrant ? 'raggiungibile' : 'non raggiungibile', 'database vettoriale', dep.qdrant ? 'ok' : 'bad'),
            kpiCard('Ollama', dep.ollama ? 'raggiungibile' : 'non raggiungibile', 'LLM locale', dep.ollama ? 'ok' : 'bad'),
          ].join('');

          stato.textContent = 'stato: ' + (h.status || '—');
          stato.className = 'text-xs font-mono ' +
            (h.status === 'ok' ? 'text-emerald-700' : h.status === 'degraded' ? 'text-orange-700' : 'text-slate-500');
        } catch (e) {
          grid.innerHTML = `<p class="text-sm col-span-full text-slate-600">Stato non disponibile (${escapeHtml(e.message)}).
            <button class="btn btn-secondary" style="margin-left:.5rem" data-click="caricaKpi">Riprova</button></p>`;
          stato.textContent = '';
        }
      }

      document.addEventListener('DOMContentLoaded', () => { renderMermaidDiagram(); caricaKpi(); });

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      caricaKpi: () => caricaKpi(),
    });
