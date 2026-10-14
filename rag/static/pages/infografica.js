/* Script della pagina infografica.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
      /* themeVar / startMatrixRain / stopMatrixRain: vedi /static/shared.js.
         Al cambio tema shared.js invoca window.onThemeChange -> ridisegna Mermaid. */
      window.onThemeChange = function () { renderMermaidDiagram(); };

      /* ──────────── MERMAID: diagramma ricostruito a runtime dai colori del tema ──────────── */
      let mermaidRenderSeq = 0;
      let mermaidRenderPending = true;
      let mermaidRendering = false;
      mermaid.initialize({ startOnLoad: false });
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
    K{"Cache /ask (LRU in-process)<br>progetto + versione + domanda"}:::fastapi
    V{"Embedding bge-m3 su CPU<br>dense + sparse + ColBERT"}:::fastapi
    Q[("Qdrant server (Docker)<br>Ricerca ibrida Top-K<br>fusione per rank")]:::qdrant
    NPY[("Sidecar ColBERT NPY<br>su disco, per documento")]:::fastapi
    CB{"Rerank ColBERT locale<br>+ peso autorità<br>+ precedenza fra fonti"}:::fastapi
    CS[("Ricerca nel codice<br>vettori dei simboli (code.npz)<br>in memoria")]:::fastapi
    G[("NetworkX (graph.json)<br>Espansione BFS + fiducia sul cammino<br>seed = doc dei chunk")]:::networkx
    C["Contesto chunk-aware:<br>testo delle SEZIONI recuperate<br>+ codice pertinente + struttura del grafo"]:::fastapi
    O{"core/llm.py · purpose ask<br>provider da config<br>(Ollama / Claude)"}:::ollama
    R["JSON: answer + graph_context<br>+ breakdown ranking + latency"]:::user

    U -->|"Domanda JSON"| S
    S -->|"0. Router deterministico"| RT
    RT -->|"strutturale → graph"| GA
    GA -->|"graph_result"| R
    RT -->|"altrimenti → hybrid"| K
    K -->|"già chiesta: risposta servita"| R
    K -->|"nuova domanda"| V
    V -->|"1. Vettori Domanda"| Q
    Q -->|"2. Candidati Top-K"| CB
    NPY -->|"Chunk richiesti"| CB
    V -->|"2b. Vettore denso"| CS
    CS -->|"Simboli pertinenti"| C
    CB -->|"3. Chunk ri-ordinati"| G
    G -->|"4. Nodi Estesi"| C
    C -->|"5. Prompt Rigido + Fascicolo"| O
    O -->|"6. Testo Sintetizzato"| S
    S -->|"7. Ritorno payload"| R`;
      }

      async function renderMermaidDiagram() {
        const container = document.getElementById('rag-mermaid');
        mermaidRenderPending = true;
        // La shell carica srcdoc nascosti: Mermaid richiede geometria reale per le frecce.
        if (mermaidRendering || !container.getBoundingClientRect().width) return;
        mermaidRenderPending = false;
        mermaidRendering = true;
        const seq = ++mermaidRenderSeq;
        const renderId = 'rag-mermaid-svg-' + seq;
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
          const { svg } = await mermaid.render(renderId, source);
          if (!container.getBoundingClientRect().width) mermaidRenderPending = true;
          if (!mermaidRenderPending) container.innerHTML = svg;
        } catch (e) {
          if (!container.getBoundingClientRect().width) mermaidRenderPending = true;
          if (!mermaidRenderPending) container.innerHTML = `<p style="color:#f87171">Errore nel rendering del diagramma: ${escapeHtml(e.message)}</p>`;
        } finally {
          // Mermaid lascia il proprio wrapper nel body quando il layout fallisce.
          document.getElementById('d' + renderId)?.remove();
          mermaidRendering = false;
          if (mermaidRenderPending) renderMermaidDiagram();
        }
      }

      document.addEventListener('DOMContentLoaded', () => {
        new ResizeObserver(entries => {
          if (!entries[0].contentRect.width) mermaidRenderPending = true;
          else if (mermaidRenderPending && !mermaidRendering) renderMermaidDiagram();
        }).observe(document.getElementById('rag-mermaid'));
        // Un frame nascosto sospende ResizeObserver; al ritorno può avere la stessa larghezza.
        if (window.frameElement) new MutationObserver(() => renderMermaidDiagram())
          .observe(window.frameElement, { attributes: true, attributeFilter: ['hidden'] });
        renderMermaidDiagram();
      });
