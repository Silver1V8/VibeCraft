/* Script della pagina dashboard.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
    /* themeVar / startMatrixRain / stopMatrixRain: vedi /static/shared.js */

    /* ──────────── PANNELLO SINISTRO RIDIMENSIONABILE ────────────
       Drag orizzontale sull'handle fra <aside id="left-panel"> e la sezione del
       grafo, con larghezza persistita in localStorage.
       Rispetto alla versione precedente: Pointer Events al posto dei soli eventi
       mouse (copre anche penna e touch), listener di move/up registrati SOLO
       durante il drag invece che permanentemente su window, e supporto tastiera
       (←/→, Home/Fine) perché l'handle era regolabile solo col mouse. */
    (function initPanelResizer() {
      const panel = document.getElementById('left-panel');
      const resizer = document.getElementById('panel-resizer');
      if (!panel || !resizer) return;

      const STORAGE_KEY = 'haro-left-panel-width';
      const MIN_WIDTH = 260;
      const MAX_WIDTH = 720;
      const STEP = 24;

      const clamp = (w) => Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w));

      function applyWidth(width, persist) {
        const w = clamp(width);
        panel.style.width = w + 'px';
        resizer.setAttribute('aria-valuenow', String(w));
        resizer.setAttribute('aria-valuemin', String(MIN_WIDTH));
        resizer.setAttribute('aria-valuemax', String(MAX_WIDTH));
        if (persist) localStorage.setItem(STORAGE_KEY, String(w));
      }

      const saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
      applyWidth(Number.isFinite(saved) ? saved : panel.offsetWidth || 384, false);

      function onPointerMove(e) {
        applyWidth(e.clientX - panel.getBoundingClientRect().left, false);
      }
      function onPointerUp() {
        window.removeEventListener('pointermove', onPointerMove);
        window.removeEventListener('pointerup', onPointerUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        applyWidth(parseInt(panel.style.width, 10), true);
      }
      resizer.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        window.addEventListener('pointermove', onPointerMove);
        window.addEventListener('pointerup', onPointerUp);
      });

      resizer.addEventListener('keydown', (e) => {
        const current = parseInt(panel.style.width, 10) || panel.offsetWidth;
        let next = null;
        if (e.key === 'ArrowLeft')  next = current - STEP;
        else if (e.key === 'ArrowRight') next = current + STEP;
        else if (e.key === 'Home')  next = MIN_WIDTH;
        else if (e.key === 'End')   next = MAX_WIDTH;
        if (next === null) return;
        e.preventDefault();
        applyWidth(next, true);
      });
    })();

    let network = null;
    let currentNodes = new vis.DataSet();
    let currentEdges = new vis.DataSet();
    let lastQueryGraphData = null;  // { nodes, edges, seedNodes } dell'ultima query /ask

    /* ──────────── VISTA 2D/3D ──────────── */
    let graphViewMode  = '3d';   // '2d' (vis.js) oppure '3d' (3d-force-graph / WebGL) — 3D di default
    let graph3d        = null;   // istanza ForceGraph3D, creata al primo uso
    let lastGraphNodes = [];     // ultimo array di nodi renderizzato (per il toggle di vista)
    let lastGraphEdges = [];     // ultimo array di archi renderizzato
    let lastVisOptions = null;   // ultime opzioni vis.Network usate (fisica), riusate al ritorno al 2D

    /* ──────────── REASONS: COLORAZIONE CROMATICA ────────────
       Ogni pilastro REASONS ha un colore semantico. I documenti vengono assegnati
       a un pilastro leggendo il campo `classification` del loro frontmatter YAML;
       le entità estratte ([UTENTE], [EVENTO], …) sono per definizione "Entities".

       I colori NON sono più costanti hardcoded: vengono dai token --pillar-*, così
       seguono il tema attivo (prima erano 7 tinte sature identiche nei due temi, e
       in Matrix il grafo diventava un arcobaleno estraneo al resto della pagina).
       `code` è il canale NON cromatico: finisce nell'etichetta del nodo, così il
       pilastro resta distinguibile anche senza percepire il colore. */
    const REASONS_PILLARS = {
      requirements: { label: 'Requirements', code: 'REQ' },
      entities:     { label: 'Entities',     code: 'ENT' },
      approach:     { label: 'Approach',     code: 'APP' },
      structure:    { label: 'Structure',    code: 'STR' },
      operations:   { label: 'Operations',   code: 'OPS' },
      norms:        { label: 'Norms',        code: 'NRM' },
      safeguards:   { label: 'Safeguards',   code: 'SAF' },
    };
    const REASONS_DEFAULT = { label: 'Non classificato', code: '—' };

    /* Costruisce l'oggetto colore vis.js del pilastro leggendo i token del tema.
       themeVar() è in cache e si azzera al cambio tema, quindi qui non c'è il
       costo di un getComputedStyle per nodo. */
    function pillarPalette(key) {
      const name = (key && REASONS_PILLARS[key]) ? key : 'default';
      const bg = themeVar(`--pillar-${name}-bg`, '#1a241e');
      const bd = themeVar(`--pillar-${name}-bd`, '#7a9488');
      return { background: bg, border: bd, highlight: { background: bd, border: bd } };
    }

    // Dal valore `classification` dello YAML al pilastro REASONS. Il match è per
    // parole chiave, così anche classificazioni future ricadono nel pilastro
    // corretto senza toccare il codice.
    function pillarKey(classification, type) {
      if (type === 'entity') return 'entities';   // le entità estratte sono il pilastro Entities
      const c = (classification || '').toUpperCase();
      if (!c) return null;
      if (/(REQUIRE|SPEC|BDD|USE_CASE|USER_STORY|FUNCTIONAL)/.test(c)) return 'requirements';
      if (/(DICTIONARY|GLOSSAR|ENTITY|DOMAIN|DATA_MODEL)/.test(c))     return 'entities';
      if (/(METHODOLOG|APPROACH|STRATEGY)/.test(c))                    return 'approach';
      if (/(ARCHITECT|STRUCTURE|MODULE|SCHEMA|DIAGRAM|BLUEPRINT)/.test(c)) return 'structure';
      if (/(WORKFLOW|OPERATION|PROCESS|STATE_MACHINE|RUNTIME|PIPELINE)/.test(c)) return 'operations';
      if (/(AUTHORIZATION|PERMISSION|POLICY|NORM|RULE|GOVERNANCE|COMPLIANCE)/.test(c)) return 'norms';
      if (/(SAFEGUARD|SECURITY|IRON_MEMORY|CONTRACT|INTEGRITY|PRIVACY|AUDIT)/.test(c)) return 'safeguards';
      return null;
    }

    // Restituisce l'oggetto colore vis.js per il pilastro del nodo.
    function pillarColor(classification, type) {
      return pillarPalette(pillarKey(classification, type));
    }

    // Codice breve del pilastro, usato come prefisso dell'etichetta del nodo:
    // è la ridondanza non cromatica che rende il pilastro leggibile anche a chi
    // non distingue le tinte.
    function pillarCode(classification, type) {
      const key = pillarKey(classification, type);
      return (key && REASONS_PILLARS[key] ? REASONS_PILLARS[key] : REASONS_DEFAULT).code;
    }

    // Popola la legenda dei pilastri REASONS (sovrapposta al grafo).
    // Mostra il codice oltre al pallino: la legenda non è più solo cromatica.
    function renderReasonsLegend() {
      const box = document.getElementById('reasons-legend-items');
      if (!box) return;
      box.innerHTML = Object.entries(REASONS_PILLARS).map(([key, p]) =>
        `<span class="flex items-center gap-1.5">
           <span class="w-2.5 h-2.5 rounded-full inline-block shrink-0" style="background:${pillarPalette(key).border}"></span>
           <span class="font-mono text-slate-400">${p.code}</span> ${escapeHtml(p.label)}
         </span>`).join('');
    }

    /* ──────────── UTILITIES ──────────── */
    function setStatus(state) {
      const dot  = document.getElementById('status-dot');
      const text = document.getElementById('status-text');
      const map = {
        idle:    { color:'bg-slate-500',  label:'In attesa' },
        loading: { color:'bg-amber-400',  label:'Elaborazione…' },
        success: { color:'bg-emerald-400',label:'Risposta ricevuta' },
        error:   { color:'bg-red-400',    label:'Errore' },
      };
      const s = map[state] || map.idle;
      dot.className  = `w-2 h-2 rounded-full ${s.color}`;
      text.textContent = s.label;
    }

    /* Il contatore parte e si ferma con il loader — sempre azzerato all'avvio, sempre
       fermato nel finally di submitQuery(): un intervallo lasciato vivo continuerebbe a
       contare sotto la risposta già arrivata. */
    let loaderTimer = null;

    function showLoader(show) {
      document.getElementById('loader').classList.toggle('hidden', !show);
      document.getElementById('ask-btn').disabled = show;

      const elapsed = document.getElementById('loader-elapsed');
      clearInterval(loaderTimer);
      loaderTimer = null;
      if (!show) { elapsed.textContent = ''; return; }
      const t0 = Date.now();
      elapsed.textContent = '0s';
      loaderTimer = setInterval(() => {
        elapsed.textContent = `${Math.round((Date.now() - t0) / 1000)}s`;
      }, 1000);
    }

    /* ──────────── STATO DI ERRORE DEL PANNELLO GRAFO ────────────
       Empty, loading ed error sono stati DELLO STESSO contenitore: mostrarne uno
       nasconde gli altri, così il pannello non resta mai ambiguo. */
    function showGraphError(message, onRetry) {
      const box = document.getElementById('graph-error');
      document.getElementById('graph-empty').style.display = 'none';
      document.getElementById('graph-error-detail').textContent = message || 'Errore sconosciuto.';
      const retry = document.getElementById('graph-error-retry');
      retry.onclick = () => { hideGraphError(); if (typeof onRetry === 'function') onRetry(); };
      box.style.display = '';
    }
    function hideGraphError() {
      document.getElementById('graph-error').style.display = 'none';
    }

    function fitGraph() {
      if (graphViewMode === '3d') {
        if (graph3d) graph3d.zoomToFit(500, 40);
      } else if (network) {
        network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } });
      }
    }

    /* ──────────── RENDERER GENERICO (dispatcha su 2D o 3D) ──────────── */
    function renderGraph(nodes, edges, visOptions) {
      lastGraphNodes = nodes;
      lastGraphEdges = edges;
      if (visOptions) lastVisOptions = visOptions;

      currentNodes = new vis.DataSet(nodes);
      currentEdges = new vis.DataSet(edges);

      if (graphViewMode === '3d') {
        render3D(nodes, edges);
      } else {
        render2D(nodes, edges, lastVisOptions);
      }

      document.getElementById('graph-counter').textContent =
        `${nodes.length} nodi · ${edges.length} archi`;
      updateGraphHint();
    }

    function render2D(nodes, edges, visOptions) {
      const container = document.getElementById('graph-canvas');
      const data = { nodes: currentNodes, edges: currentEdges };
      if (network) {
        network.setData(data);
        network.setOptions(visOptions);
      } else {
        network = new vis.Network(container, data, visOptions);
        attachTooltipListeners();
      }
      scheduleFit();
    }

    function resize3DCanvas() {
      if (!graph3d) return;
      const el = document.getElementById('graph-canvas-3d');
      graph3d.width(el.clientWidth || 300).height(el.clientHeight || 300);
    }

    function render3D(nodes, edges) {
      const nodeById = new Map(nodes.map(n => [n.id, n]));
      const graphData = {
        nodes: nodes.map(n => ({
          id: n.id,
          nodeId: n.nodeId,
          label: n.label,
          nodeType: n.nodeType,
          description: n.description,
          pillar: n.pillar,
          color: (n.color && (n.color.border || n.color.background)) || '#94a3b8',
          val: Math.max(1, (n.size || 12) / 4),
        })),
        links: edges.map(e => ({
          source: e.from,
          target: e.to,
          label: e.label || '',
          color: (e.color && e.color.color) || '#4dbf6e',
        })),
      };

      if (!graph3d) {
        const el = document.getElementById('graph-canvas-3d');
        graph3d = ForceGraph3D()(el)
          .backgroundColor('rgba(0,0,0,0)')
          .nodeLabel(n => makeTooltipHtml(n.nodeId || n.id, n.description || ''))
          .nodeColor('color')
          .nodeVal('val')
          .linkColor('color')
          // linkLabel finisce in innerHTML del tooltip di 3d-force-graph (come nodeLabel):
          // la label è la relazione dell'arco, stringa libera del frontmatter del corpus.
          .linkLabel(l => escapeHtml(l.label || ''))
          .linkWidth(0.6)
          .linkDirectionalArrowRelPos(1)
          .onNodeClick(n => renderNodeDetails(n.id))
          .onBackgroundClick(() => closeNodeDetails())
          .showNavInfo(false);
        resize3DCanvas();
        window.addEventListener('resize', resize3DCanvas);
      }

      /* Degradazione per grafi grandi: sopra qualche migliaio di nodi le frecce
         direzionali sono geometria aggiuntiva per ogni arco e la simulazione,
         se non le si dà un tetto, continua a girare indefinitamente. Il
         cooldown limitato congela il layout dopo un numero fisso di tick: si
         perde l'assestamento perfetto, si guadagna una pagina che risponde. */
      const grande = nodes.length > 2000;
      graph3d
        .linkDirectionalArrowLength(grande ? 0 : 3.5)
        .linkOpacity(grande ? 0.18 : 0.35)
        .warmupTicks(grande ? 40 : 0)
        .cooldownTicks(grande ? 120 : Infinity);

      graph3d.graphData(graphData);
      resize3DCanvas();
      scheduleFit();
    }

    /* Adatta la vista al grafo appena disegnato: senza, il layout partiva dal centro con
       lo zoom di default e un grafo di centinaia di nodi restava un puntino in mezzo. */
    let fitTimer = 0;
    function scheduleFit() {
      clearTimeout(fitTimer);
      fitTimer = setTimeout(() => fitGraph(), 1500);
    }
    const GRAPH_HINT = {
      '3d': 'Trascina per ruotare · rotellina per lo zoom · tasto destro per spostare · clic su un nodo per i dettagli',
      '2d': 'Trascina per spostare · rotellina per lo zoom · clic su un nodo per i dettagli',
    };
    function updateGraphHint() {
      document.getElementById('graph-hint').textContent = lastGraphNodes.length ? GRAPH_HINT[graphViewMode] : '';
    }

    /* `rerender: false` serve a chi sta per disegnare comunque un grafo nuovo
       (showFullGraph): senza, si ridisegnerebbe prima il grafo VECCHIO nella
       nuova vista e subito dopo quello nuovo — lavoro doppio su decine di
       migliaia di nodi. */
    function setGraphViewMode(mode, rerender = true) {
      if (mode === graphViewMode) return;
      graphViewMode = mode;

      document.getElementById('view-mode-2d-btn').classList.toggle('active', mode === '2d');
      document.getElementById('view-mode-3d-btn').classList.toggle('active', mode === '3d');
      document.getElementById('view-mode-2d-btn').setAttribute('aria-pressed', String(mode === '2d'));
      document.getElementById('view-mode-3d-btn').setAttribute('aria-pressed', String(mode === '3d'));
      document.getElementById('graph-canvas').style.display    = (mode === '2d') ? '' : 'none';
      document.getElementById('graph-canvas-3d').style.display = (mode === '3d') ? '' : 'none';

      if (rerender && lastGraphNodes.length) {
        if (mode === '3d') render3D(lastGraphNodes, lastGraphEdges);
        else render2D(lastGraphNodes, lastGraphEdges, lastVisOptions);
      }
      updateGraphHint();
    }

    /* ──────────── TAB SWITCHER ────────────
       Prima riscriveva `className` per intero con una stringa di 12 utility:
       qualunque classe aggiunta al markup (responsive, stato) veniva distrutta al
       primo switch. Ora tocca solo `is-active` e gli attributi ARIA. */
    const TAB_ORDER = ['answer', 'graph', 'context', 'json'];
    const TAB_BTN   = { answer: 'tab-answer-btn',   graph: 'tab-graph-btn',   context: 'tab-context-btn',   json: 'tab-json-btn' };
    const TAB_PANEL = { answer: 'tab-answer-panel', graph: 'tab-graph-panel', context: 'tab-context-panel', json: 'tab-json-panel' };

    function switchTab(tab) {
      TAB_ORDER.forEach(p => {
        const btn = document.getElementById(TAB_BTN[p]);
        const isActive = (p === tab);
        document.getElementById(TAB_PANEL[p]).style.display = isActive ? '' : 'none';
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-selected', String(isActive));
        // Roving tabindex: dentro un tablist si entra con Tab e ci si sposta con
        // le frecce, quindi solo il tab attivo è raggiungibile con Tab.
        btn.tabIndex = isActive ? 0 : -1;
      });

      // Controlli grafo: visibili solo nel tab Mappa
      document.getElementById('graph-controls').style.display = (tab === 'graph') ? '' : 'none';

      // Forza il ridisegno del grafo (2D o 3D) quando si torna al tab Mappa
      if (tab === 'graph') {
        setTimeout(() => {
          if (network) network.redraw();
          if (graph3d) resize3DCanvas();
        }, 60);
      }
    }

    /* Navigazione con le frecce fra i tab (pattern ARIA tablist). */
    (function initTabKeyboard() {
      TAB_ORDER.forEach((tab, i) => {
        document.getElementById(TAB_BTN[tab]).addEventListener('keydown', e => {
          let next = null;
          if (e.key === 'ArrowRight') next = TAB_ORDER[(i + 1) % TAB_ORDER.length];
          else if (e.key === 'ArrowLeft') next = TAB_ORDER[(i - 1 + TAB_ORDER.length) % TAB_ORDER.length];
          else if (e.key === 'Home') next = TAB_ORDER[0];
          else if (e.key === 'End') next = TAB_ORDER[TAB_ORDER.length - 1];
          if (!next) return;
          e.preventDefault();
          switchTab(next);
          document.getElementById(TAB_BTN[next]).focus();
        });
      });
      switchTab('graph');   // imposta tabindex e ARIA coerenti al primo paint
    })();

    /* ──────────── GRAPH MODE HELPERS ──────────── */
    function setGraphMode(mode) {
      const title      = document.getElementById('graph-title');
      const badge      = document.getElementById('graph-mode-badge');
      const restoreBtn = document.getElementById('restore-graph-btn');

      if (mode === 'full') {
        title.textContent = 'Grafo completo';
        document.getElementById('graph-expand-btn').style.display = 'none';
        badge.classList.remove('hidden');
        badge.classList.add('flex');
        // Mostra "Ripristina" solo se esiste un grafo contestuale salvato
        restoreBtn.style.display = lastQueryGraphData ? '' : 'none';
      } else {
        title.textContent = 'Grafo contestuale';
        badge.classList.add('hidden');
        badge.classList.remove('flex');
        restoreBtn.style.display = 'none';
      }
    }

    let contextExpanded = false;
    function toggleContextExpand() {
      contextExpanded = !contextExpanded;
      restoreContextualGraph();
    }

    /* ──────────── RIPRISTINO GRAFO CONTESTUALE ──────────── */
    function restoreContextualGraph() {
      if (!lastQueryGraphData) return;
      const { nodes, edges, seedNodes } = lastQueryGraphData;
      buildGraph(nodes, edges, seedNodes);
      fitGraph();
    }

    /* ──────────── FULL GRAPH ──────────── */
    async function showFullGraph() {
      const btn = document.getElementById('full-graph-btn');
      btn.disabled = true;
      btn.innerHTML = `
        <svg class="w-3.5 h-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
        </svg>
        Caricamento…`;
      setStatus('loading');

      try {
        const res = await fetch('/api/graph/all');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        document.getElementById('graph-empty').style.display = 'none';
        hideGraphError();
        setGraphMode('full');

        /* Il grafo completo parte in 3D. Non è solo una preferenza estetica:
           vis.js in 2D stabilizza il layout sul main thread e su un knowledge
           base di oltre 10.000 nodi blocca la pagina per decine di secondi,
           mentre 3d-force-graph gira su WebGL e regge il carico. La vista 2D
           resta a un click per chi la preferisce, e il grafo contestuale —
           poche decine di nodi — continua a usare la vista attiva. */
        setGraphViewMode('3d', false);

        document.getElementById('reasons-legend').style.display = '';
        closeNodeDetails();

        const nodeFont  = themeVar('--node-font', '#eafff0');
        const edgeColor = themeVar('--edge-full', '#145c2c');
        const edgeHi    = themeVar('--edge-full-hi', '#4dbf6e');
        const edgeFont  = themeVar('--edge-full-font', '#2ea34f');

        const nodes = data.nodes.map(n => {
          const isDoc = n.type === 'document';
          const color = pillarColor(n.classification, n.type);
          const shortLabel = n.id.length > 22 ? n.id.substring(0, 20) + '…' : n.id;
          return {
            id: n.id,
            // Il codice del pilastro prefissa l'etichetta: è il canale NON
            // cromatico che rende il pilastro leggibile anche a chi non
            // distingue le tinte (il colore da solo non basta).
            label: `[${pillarCode(n.classification, n.type)}] ${shortLabel}`,
            nodeId: n.id,
            nodeType: n.type,
            classification: n.classification || '',
            pillar: pillarKey(n.classification, n.type),
            description: n.description || '',
            color,
            font: { color: nodeFont, size:11, face:'Inter, sans-serif' },
            shape: isDoc ? 'box' : 'ellipse',
            borderWidth: 1.5,
            size: isDoc ? 18 : 12,
          };
        });

        const edges = data.edges.map((e, i) => ({
          id: i,
          from: e.from,
          to: e.to,
          label: e.relation || '',
          arrows: { to:{ enabled:true, scaleFactor:0.6 } },
          color: { color: edgeColor, highlight: edgeHi },
          font: { color: edgeFont, size:9, align:'middle', strokeWidth:0 },
          smooth: { type:'dynamic' },
        }));

        const options = {
          physics: {
            enabled: true,
            barnesHut: {
              gravitationalConstant: -6000,
              springLength: 160,
              springConstant: 0.025,
              damping: 0.25,
            },
            stabilization: { iterations: 400 },
          },
          interaction: { hover:true, tooltipDelay:150, keyboard:true, zoomView:true },
          layout: { improvedLayout: nodes.length < 300 },
        };

        renderGraph(nodes, edges, options);
        setStatus('success');
        setTimeout(fitGraph, 600);

      } catch (e) {
        // L'errore resta NEL pannello che ha fallito: prima finiva nella card
        // "Risposta LLM", dove sembrava l'output del modello.
        setStatus('error');
        showGraphError(e.message, showFullGraph);
      } finally {
        btn.disabled = false;
        btn.innerHTML = `
          <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/><path stroke-linecap="round" d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20"/>
          </svg>
          Visualizza grafo completo`;
      }
    }

    /* ──────────── TOOLTIP (shared) ────────────
       nodeId e description arrivano dai documenti indicizzati e finivano in
       innerHTML SENZA escape (sia nel tooltip 2D sia come nodeLabel del 3D):
       un documento caricato da /intake con markup nella descrizione veniva
       eseguito qui. escapeHtml è in /static/shared.js. */
    function makeTooltipHtml(nodeId, description) {
      const mutedColor = themeVar('--tooltip-muted', '#4dbf6e');
      const safeId = escapeHtml(nodeId);
      if (!description) {
        // Nodo senza descrizione: tooltip minimalista con solo l'ID
        return `<div style="font-size:var(--text-xs);color:${mutedColor};max-width:280px;word-break:break-all">${safeId}</div>`;
      }

      const isRule    = /^REGOLA-/.test(nodeId);
      // Regole → viola  |  Termini di glossario → ciano smeraldo
      const accent    = isRule ? themeVar('--tooltip-rule-accent', '#5eeed4') : themeVar('--tooltip-term-accent', '#34d399');
      const divider   = isRule ? themeVar('--tooltip-rule-divider', '#0a4a3d') : themeVar('--tooltip-term-divider', '#1a3d32');
      const label     = isRule ? 'Regola normativa' : 'Termine di glossario';
      const descColor = themeVar('--tooltip-desc', '#c8f5d4');

      return `
        <div style="max-width:300px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;padding-bottom:5px;border-bottom:1px solid ${divider}">
            <span style="font-size:var(--text-xs);font-weight:700;letter-spacing:.08em;text-transform:uppercase;
                         color:${accent}">${label}</span>
            <span style="font-size:var(--text-xs);font-weight:700;color:${accent}">${safeId}</span>
          </div>
          <div style="font-size:var(--text-sm);line-height:1.6;color:${descColor}">${escapeHtml(description)}</div>
        </div>`;
    }

    function attachTooltipListeners() {
      const tooltip = document.getElementById('node-tooltip');
      network.on('hoverNode', params => {
        const node = currentNodes.get(params.node);
        if (!node) return;
        tooltip.innerHTML = makeTooltipHtml(node.nodeId || node.id, node.description || '');
        tooltip.classList.remove('hidden');
      });
      network.on('blurNode', () => tooltip.classList.add('hidden'));
      document.getElementById('graph-canvas').addEventListener('mousemove', e => {
        tooltip.style.left = (e.clientX + 14) + 'px';
        tooltip.style.top  = (e.clientY - 8)  + 'px';
      });
      // Click su un nodo → pannello dettagli; click sul vuoto → chiude
      network.on('click', params => {
        if (params.nodes && params.nodes.length) {
          renderNodeDetails(params.nodes[0]);
        } else {
          closeNodeDetails();
        }
      });
    }

    /* ──────────── PANNELLO DETTAGLI NODO (click) ──────────── */
    function closeNodeDetails() {
      const panel = document.getElementById('node-details');
      if (panel) panel.style.display = 'none';
      if (network) network.unselectAll();
    }

    function renderNodeDetails(nodeId) {
      const node = currentNodes.get(nodeId);
      if (!node) return;

      const isDoc = node.nodeType === 'document' || node.shape === 'box';
      document.getElementById('nd-title').textContent = node.nodeId || nodeId;

      // Badge: tipo + pilastro REASONS
      const badges = [
        `<span class="px-2 py-0.5 rounded-full border border-slate-600 text-slate-300">${isDoc ? '▢ Documento' : '◯ Entità'}</span>`,
      ];
      const p = node.pillar && REASONS_PILLARS[node.pillar];
      if (p) {
        // Il colore del pilastro vive nei token del tema (pillarPalette), non in
        // REASONS_PILLARS: leggerlo da p.color lanciava un TypeError e lasciava il
        // pannello a metà su ogni nodo classificato.
        const bd = pillarPalette(node.pillar).border;
        badges.push(
          `<span class="px-2 py-0.5 rounded-full" style="color:${bd};border:1px solid ${bd};background:${bd}1a">${p.label}</span>`
        );
      }
      if (node.classification) {
        badges.push(`<span class="px-2 py-0.5 rounded-full border border-slate-700 text-slate-400 font-mono">${escapeHtml(node.classification)}</span>`);
      }
      document.getElementById('nd-badges').innerHTML = badges.join('');

      // Descrizione
      const desc = node.description || '';
      document.getElementById('nd-desc').innerHTML = desc
        ? escapeHtml(desc)
        : '<span class="text-slate-400 italic">Nessuna descrizione disponibile.</span>';

      // Connessioni (archi entranti/uscenti nel grafo corrente)
      const conns = [];
      currentEdges.forEach(e => {
        if (e.from === nodeId) conns.push({ arrow: '→', rel: e.label || '', other: e.to });
        else if (e.to === nodeId) conns.push({ arrow: '←', rel: e.label || '', other: e.from });
      });
      const wrap = document.getElementById('nd-conn-wrap');
      const list = document.getElementById('nd-connections');
      if (conns.length) {
        list.innerHTML = conns.map(c => {
          const rel = c.rel ? `<span class="text-slate-400">${escapeHtml(c.rel)}</span> ` : '';
          return `<div class="truncate" title="${escapeHtml(c.other)}"><span class="text-slate-400">${c.arrow}</span> ${rel}<span class="text-slate-200">${escapeHtml(c.other)}</span></div>`;
        }).join('');
        wrap.classList.remove('hidden');
      } else {
        wrap.classList.add('hidden');
      }

      document.getElementById('node-details').style.display = '';
    }

    /* ──────────── GRAPH RENDERER ──────────── */
    function buildGraph(expandedNodes, graphEdges, seedNodes) {
      document.getElementById('graph-empty').style.display = 'none';
      hideGraphError();
      setGraphMode('contextual');

      document.getElementById('reasons-legend').style.display = '';
      closeNodeDetails();

      const seedSet = new Set(seedNodes || []);
      // Di default solo i documenti trovati e i loro vicini diretti (contextExpanded per
      // tutti): cambia SOLO la vista, il contesto dato all'LLM resta quello di bfs_depth.
      const allCount = expandedNodes.length;
      if (!contextExpanded && seedSet.size) {
        const keep = new Set(seedSet);
        for (const e of graphEdges || []) {
          if (seedSet.has(e.from)) keep.add(e.to);
          if (seedSet.has(e.to)) keep.add(e.from);
        }
        expandedNodes = expandedNodes.filter(n => keep.has(n.id));
        graphEdges = (graphEdges || []).filter(e => keep.has(e.from) && keep.has(e.to));
      }
      const expandBtn = document.getElementById('graph-expand-btn');
      expandBtn.style.display = (contextExpanded || expandedNodes.length < allCount) ? '' : 'none';
      expandBtn.textContent = contextExpanded ? 'Solo i vicini diretti' : `Mostra tutti i ${allCount} nodi`;
      const nodeFont  = themeVar('--node-font', '#eafff0');
      const edgeColor = themeVar('--edge-ctx', '#1f7a3d');
      const edgeHi    = themeVar('--edge-ctx-hi', '#4dbf6e');
      const edgeFont  = themeVar('--edge-ctx-font', '#4dbf6e');

      // expandedNodes è ora una lista di oggetti {id, type, description, classification}
      const nodes = expandedNodes.map(n => {
        const nodeId = n.id;
        const isDoc  = n.type === 'document';
        const isSeed = seedSet.has(nodeId);

        // Colore per pilastro REASONS (dal campo classification); la forma continua
        // a distinguere documenti (box) ed entità (ellisse).
        const color = pillarColor(n.classification, n.type);

        const shortLabel = nodeId.length > 22 ? nodeId.substring(0, 20) + '…' : nodeId;

        return {
          id: nodeId,
          // Codice del pilastro come prefisso: canale non cromatico, vedi showFullGraph.
          label: `[${pillarCode(n.classification, n.type)}] ${shortLabel}`,
          nodeId: nodeId,
          nodeType: n.type,
          classification: n.classification || '',
          pillar: pillarKey(n.classification, n.type),
          description: n.description || '',
          color: color,
          font: { color: nodeFont, size: 12, face: 'Inter, sans-serif' },
          shape: isDoc ? 'box' : 'ellipse',
          borderWidth: isSeed ? 3 : 1.5,
          shadow: isSeed ? { enabled: true, color:'rgba(59,130,246,0.5)', size:10 } : false,
          size: isSeed ? 20 : 14,
        };
      });

      const edges = (graphEdges || []).map((e, i) => ({
        id: i,
        from: e.from,
        to: e.to,
        label: e.relation || '',
        arrows: { to: { enabled: true, scaleFactor: 0.7 } },
        color: { color: edgeColor, highlight: edgeHi },
        font: { color: edgeFont, size: 10, align: 'middle', strokeWidth: 0 },
        smooth: { type: 'dynamic' },
      }));

      const options = {
        physics: {
          enabled: true,
          barnesHut: { gravitationalConstant: -4000, springLength: 120, springConstant: 0.04, damping: 0.2 },
          stabilization: { iterations: 200 },
        },
        interaction: {
          hover: true,
          tooltipDelay: 150,
          navigationButtons: false,
          keyboard: true,
          zoomView: true,
        },
        layout: { improvedLayout: true },
      };

      renderGraph(nodes, edges, options);
    }

    /* ──────────── SCORES RENDERER ──────────── */
    function renderScores(scores) {
      const card = document.getElementById('scores-card');
      const list = document.getElementById('scores-list');
      if (!scores || scores.length === 0) { card.classList.add('hidden'); return; }

      list.innerHTML = '';
      const maxScore = Math.max(...scores.map(s => s.score));
      const fmt = v => (v === null || v === undefined) ? '—' : (typeof v === 'number' ? v.toFixed(3) : escapeHtml(v));
      scores.forEach(s => {
        const pct = maxScore > 0 ? (s.score / maxScore * 100).toFixed(1) : 0;
        const short = (s.doc_id || '—').length > 36
          ? (s.doc_id || '—').substring(0, 34) + '…'
          : (s.doc_id || '—');
        // doc_id proviene dai documenti indicizzati (il nome file è scelto
        // dall'utente in fase di approvazione da /intake): va sempre escapato.
        list.insertAdjacentHTML('beforeend', `
          <div class="group">
            <div class="flex justify-between items-center mb-1">
              <span class="text-xs text-slate-300 truncate max-w-[220px]" title="${escapeHtml(s.doc_id)}">${escapeHtml(short)}</span>
              <span class="text-xs font-mono ml-2 shrink-0" style="color:var(--score-value)">${s.score.toFixed(4)}</span>
            </div>
            <div class="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div class="score-bar h-full rounded-full" style="width:${pct}%;background:linear-gradient(90deg,var(--score-grad-start),var(--score-grad-end))"></div>
            </div>
            <div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs font-mono text-slate-400">
              <span title="Dense (semantica)">D ${fmt(s.dense_score)}</span>
              <span title="Sparse (lessicale)">S ${fmt(s.sparse_score)}</span>
              <span title="ColBERT (token-per-token)">CB ${fmt(s.colbert_score)}</span>
              <span title="Autorità della sorgente" class="text-blue-400">A ${fmt(s.authority)}</span>
            </div>
          </div>
        `);
      });
      card.classList.remove('hidden');
    }

    /* ──────────── JSON PANEL RENDERER ────────────
       escapeHtml vive in /static/shared.js: era duplicata qui, in
       graph_analysis e in intake con tre implementazioni divergenti (questa non
       gestiva l'apice singolo). */
    /* Ultima risposta mostrata nel pannello JSON: renderJsonPanel cuoce i colori nell'HTML
       con themeVar(), quindi al flip di tema il pannello resterebbe con la palette vecchia
       fino alla query successiva. Il ridisegno lo rifà con i token del tema nuovo. */
    let lastJsonPanelData = null;

    function renderJsonPanel(data) {
      const gc          = data.graph_context || {};
      const scores      = data.qdrant_scores  || [];
      const precedences = data.precedences    || [];
      const seedNodes   = gc.seed_nodes        || [];
      const expNodes    = gc.expanded_nodes    || [];
      const graphEdges  = gc.graph_edges       || [];
      const answer      = data.answer          || '—';
      const elapsed     = data.elaboration_seconds ?? data.elapsed_seconds;
      const status      = data.status          || '—';

      const divider     = themeVar('--json-divider', '#04140a');
      const accent      = themeVar('--json-accent', '#1f7a3d');
      const muted       = themeVar('--json-muted', '#145c2c');
      const scoreLabel  = themeVar('--score-label', '#4dbf6e');
      const scoreGradS  = themeVar('--score-grad-start', '#00e639');
      const scoreGradE  = themeVar('--score-grad-end',   '#10b981');
      const scoreValue  = themeVar('--score-value',      '#34d399');
      const chipBg      = themeVar('--chip-bg', '#062e14');
      const chipBorder  = themeVar('--chip-border', '#0a3d1f');
      const chipColor   = themeVar('--chip-color', '#39ffe0');
      const statBg      = themeVar('--stat-bg', '#03170a');
      const statNumber  = themeVar('--stat-number', '#7dffa0');
      const ragJsonBg   = themeVar('--rag-json-bg', '#000000');
      const descColor   = themeVar('--tooltip-desc', '#c8f5d4');

      /* ── Badge header ── */
      /* Gli stati che /ask puo' restituire, ciascuno col proprio significato: "abstained"
         (A16) e' la sicurezza che funziona e "graph_answer" un successo pieno — colorarli
         di rosso col vecchio `status === 'success' ? verde : rosso` li faceva leggere come
         guasti. Ambra = non ha risposto, ed e' corretto cosi'.
         I colori sono `var(--status-*)` scritte nello style inline, NON lette con
         themeVar(): una CSS variable si risolve a ogni ridisegno, quindi il badge segue
         il flip di tema senza che nulla lo ri-renderizzi. */
      const STATUS_STYLE = {
        success:        { tone:'ok',      label:'success — risposta generata' },
        graph_answer:   { tone:'ok',      label:'graph_answer — risposta dal grafo' },
        abstained:      { tone:'warn',    label:'abstained — non ha risposto, ed e’ corretto' },
        no_results:     { tone:'neutral', label:'no_results — nulla di pertinente in indice' },
        no_graph_nodes: { tone:'neutral', label:'no_graph_nodes — trovato in Qdrant, assente nel grafo' },
      };
      const st = STATUS_STYLE[status] || { tone:'err', label:status };
      document.getElementById('json-status-badge').innerHTML =
        `<span style="padding:2px 9px;border-radius:20px;background:var(--status-${st.tone}-bg);color:var(--status-${st.tone}-fg);font-weight:700">${escapeHtml(st.label)}</span>` +
        (elapsed != null ? `&nbsp;<span style="color:${accent}">${elapsed}s</span>` : '');

      /* ── LEFT: Qdrant scores ── */
      const maxScore = scores.length ? Math.max(...scores.map(s => s.score)) : 1;
      const scoresHtml = scores.length
        ? scores.map(s => {
            const pct   = maxScore > 0 ? (s.score / maxScore * 100).toFixed(1) : 0;
            const label = (s.doc_id || '—').length > 32
              ? s.doc_id.substring(0, 30) + '…' : (s.doc_id || '—');
            return `<div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:3px">
                <span style="font-size:var(--text-xs);color:${scoreLabel};font-family:ui-monospace,monospace" title="${escapeHtml(s.doc_id)}">${escapeHtml(label)}</span>
                <span style="font-size:var(--text-xs);font-family:ui-monospace,monospace;color:${scoreValue};margin-left:8px;white-space:nowrap">${s.score.toFixed(4)}</span>
              </div>
              <div style="height:3px;background:${divider};border-radius:2px;overflow:hidden">
                <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,${scoreGradS},${scoreGradE})"></div>
              </div>
            </div>`;
          }).join('')
        : `<span style="color:${muted};font-size:var(--text-xs)">Nessun risultato</span>`;

      /* ── LEFT: seed nodes chips ── */
      const seedHtml = seedNodes.map(n =>
        `<span style="display:inline-block;margin:2px 3px;padding:2px 8px;border-radius:4px;
                background:${chipBg};border:1px solid ${chipBorder};color:${chipColor};font-size:var(--text-xs);
                font-family:ui-monospace,monospace">${escapeHtml(n)}</span>`
      ).join('') || `<span style="color:${muted};font-size:var(--text-xs)">—</span>`;

      /* ── LEFT: raw RAG JSON (context_text escluso) ── */
      const ragData = {
        qdrant_scores: scores,
        /* Precedenze dichiarate fra fonti che hanno riordinato il ranking (S4): quasi sempre
           vuoto. Sta qui perche' un riordino silenzioso non e' spiegabile — chi legge deve
           poter vedere PERCHE' un documento e' sceso. */
        ...(precedences.length ? { precedences } : {}),
        graph_context: {
          seed_nodes:     seedNodes,
          expanded_nodes: expNodes,
          graph_edges:    graphEdges,
        },
      };
      const ragJson = JSON.stringify(ragData, null, 2);

      document.getElementById('json-rag-col').innerHTML = `
        <div style="margin-bottom:18px">
          <div style="font-size:var(--text-xs);font-weight:700;letter-spacing:.09em;text-transform:uppercase;
                      color:${muted};margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid ${divider}">
            Retrieval Semantico &middot; Qdrant
          </div>
          ${scoresHtml}
        </div>
        <div style="margin-bottom:18px">
          <div style="font-size:var(--text-xs);font-weight:700;letter-spacing:.09em;text-transform:uppercase;
                      color:${muted};margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid ${divider}">
            Espansione Grafo &middot; NetworkX
          </div>
          <div style="margin-bottom:10px">
            <div style="font-size:var(--text-xs);color:${accent};margin-bottom:5px;text-transform:uppercase;letter-spacing:.06em">Nodi seed</div>
            <div>${seedHtml}</div>
          </div>
          <div style="display:flex;gap:10px;margin-top:12px">
            <div style="flex:1;text-align:center;padding:8px 4px;background:${statBg};border-radius:8px;border:1px solid ${divider}">
              <div style="font-size:20px;font-weight:700;color:${statNumber};font-family:ui-monospace,monospace;line-height:1">${expNodes.length}</div>
              <div style="font-size:var(--text-xs);color:${muted};text-transform:uppercase;letter-spacing:.06em;margin-top:3px">espansi</div>
            </div>
            <div style="flex:1;text-align:center;padding:8px 4px;background:${statBg};border-radius:8px;border:1px solid ${divider}">
              <div style="font-size:20px;font-weight:700;color:${statNumber};font-family:ui-monospace,monospace;line-height:1">${graphEdges.length}</div>
              <div style="font-size:var(--text-xs);color:${muted};text-transform:uppercase;letter-spacing:.06em;margin-top:3px">archi</div>
            </div>
          </div>
        </div>
        <div>
          <div style="font-size:var(--text-xs);font-weight:700;letter-spacing:.09em;text-transform:uppercase;
                      color:${muted};margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid ${divider}">
            Dati JSON Grezzi &middot; RAG
          </div>
          <pre id="rag-json-box" style="margin:0;padding:10px 12px;border-radius:8px;
               background:${ragJsonBg};border:1px solid ${divider};
               font-size:var(--text-xs);line-height:1.6;font-family:'JetBrains Mono',ui-monospace,monospace;
               color:${chipColor};white-space:pre;overflow-x:auto;overflow-y:auto;
               max-height:240px">${escapeHtml(ragJson)}</pre>
        </div>`;

      /* ── RIGHT: LLM answer ── */
      document.getElementById('json-llm-col').innerHTML = `
        <div style="font-size:var(--text-xs);font-weight:700;letter-spacing:.09em;text-transform:uppercase;
                    color:${muted};margin-bottom:12px;padding-bottom:6px;border-bottom:1px solid ${divider}">
          Risposta generata
        </div>
        <div style="font-size:12.5px;line-height:1.75;color:${descColor};white-space:pre-wrap;
                    word-break:break-word;font-family:Inter,ui-sans-serif,sans-serif">
          ${escapeHtml(answer)}
        </div>`;
    }

    /* ASK_STREAM_PARSER_START */
    function createAskStreamParser(onEvent) {
      const decoder = new TextDecoder();
      let buffer = '';
      let terminal = false;

      function parseLine(line) {
        if (!line.trim()) return;
        if (terminal) throw new Error('Dati ricevuti dopo l’evento terminale.');
        const event = JSON.parse(line);
        if (!event || !['meta', 'delta', 'result', 'error'].includes(event.type)) {
          throw new Error('Evento streaming /ask non valido.');
        }
        onEvent(event);
        if (event.type === 'result' || event.type === 'error') terminal = true;
      }

      return {
        push(chunk, done) {
          buffer += decoder.decode(chunk, { stream: !done });
          let newline;
          while ((newline = buffer.indexOf('\n')) !== -1) {
            parseLine(buffer.slice(0, newline));
            buffer = buffer.slice(newline + 1);
          }
          if (done) {
            parseLine(buffer);
            buffer = '';
            if (!terminal) throw new Error('Stream /ask terminato senza evento terminale.');
          }
          return terminal;
        },
      };
    }
    /* ASK_STREAM_PARSER_END */

    /* Risposta dal grafo (router deterministico, status "graph_answer"): non ha un campo
       `answer` testuale e finiva in "(nessuna risposta)". Forme da core.graph_ops.graph_query. */
    function graphAnswerText(g) {
      if (!g) return '';
      const lines = g.intent === 'impatto'
        ? (g.rings || []).map((ring, i) => `${i ? 'Distanza ' + i : 'Nodo'}: ${ring.join(', ')}`)
        : g.intent === 'relazioni'
          ? [...(g.out || []).map(e => `→ ${e.relation} ${e.to}`), ...(g.in || []).map(e => `← ${e.relation} ${e.from}`)]
          : (g.answer || []).map(item => `• ${item}`);
      return `${g.count ?? lines.length} risultati (${g.intent}${g.target ? ': ' + g.target : ''})\n${lines.join('\n')}`;
    }

    /* La risposta sta nella scheda "Risposta" dell'area grande: la si mostra (e ci si
       sposta) al primo token, al risultato e anche sull'errore, che altrimenti
       resterebbe in una scheda nascosta. */
    const ANSWER_CLASS = 'answer-md prose-text flex-1 min-h-0 overflow-y-auto px-6 py-4 text-sm text-slate-200 leading-relaxed';
    function showAnswerPanel() {
      document.getElementById('answer-empty').classList.add('hidden');
      document.getElementById('answer-card').classList.remove('hidden');
      switchTab('answer');
    }
    // Markdown reso al massimo una volta per frame durante lo streaming: a ogni token
    // si rigenera tutto il testo, ma solo quando il browser sta per ridisegnare.
    let answerFrame = 0;
    function renderAnswerMarkdown(text) {
      cancelAnimationFrame(answerFrame);
      answerFrame = requestAnimationFrame(() => {
        const answerText = document.getElementById('answer-text');
        answerText.className = ANSWER_CLASS;
        answerText.innerHTML = renderMarkdown(text);
      });
    }

    function renderAskResult(data) {
      /* ── ANSWER ── */
      const answerText = document.getElementById('answer-text');
      cancelAnimationFrame(answerFrame);
      if (data.answer) {
        answerText.className = ANSWER_CLASS + ' answer-appear';
        answerText.innerHTML = renderMarkdown(data.answer);
      } else {
        // Risposta dal grafo o vuota: testo semplice, a righe.
        answerText.className = ANSWER_CLASS + ' answer-appear whitespace-pre-wrap';
        answerText.textContent = graphAnswerText(data.graph_result) || '(nessuna risposta)';
      }
      void answerText.offsetWidth; // reflow per restart animation

      const elapsed = data.elaboration_seconds ?? data.elapsed_seconds;
      const badge   = document.getElementById('elapsed-badge');
      badge.textContent = elapsed != null ? `⏱ ${elapsed}s` : '';
      showAnswerPanel();

      /* ── GRAPH ── */
      const gc = data.graph_context || {};
      const expandedNodes = gc.expanded_nodes || [];
      const graphEdges    = gc.graph_edges    || [];
      const seedNodes     = gc.seed_nodes     || [];

      if (expandedNodes.length > 0) {
        contextExpanded = false;
        // Salva i dati in memoria per il ripristino istantaneo
        lastQueryGraphData = { nodes: expandedNodes, edges: graphEdges, seedNodes };
        buildGraph(expandedNodes, graphEdges, seedNodes);
      }

      /* ── PROMPT CONTEXT ── */
      const contextText = gc.context_text || '';
      document.getElementById('raw-context-box').textContent =
        contextText || 'Nessun testo di contesto disponibile.';
      document.getElementById('context-chars').textContent =
        contextText ? `${contextText.length.toLocaleString('it-IT')} caratteri` : '';

      /* ── JSON RESPONSE ── */
      lastJsonPanelData = data;   // per il ridisegno al cambio di tema (onThemeChange)
      renderJsonPanel(data);

      /* ── SCORES ── */
      renderScores(data.qdrant_scores);
      setStatus('success');
    }

    /* ──────────── MAIN QUERY ──────────── */
    async function submitQuery() {
      const question = document.getElementById('question-input').value.trim();
      if (!question) {
        document.getElementById('question-input').focus();
        return;
      }

      const topK    = parseInt(document.getElementById('top-k').value)     || 5;
      const _bfsRaw = parseInt(document.getElementById('bfs-depth').value);
      const bfsDep  = Number.isNaN(_bfsRaw) ? 2 : _bfsRaw;

      // Reset UI
      document.getElementById('answer-card').classList.add('hidden');
      document.getElementById('scores-card').classList.add('hidden');
      showLoader(true);
      setStatus('loading');

      try {
        const res = await fetch('/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, top_k: topK, bfs_depth: bfsDep, stream: true }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(apiErrorMessage(err.detail, `HTTP ${res.status}`));
        }

        if (!res.body) throw new Error('Il browser non supporta lo streaming della risposta.');
        const reader = res.body.getReader();
        let readerFinished = false;
        let finalData = null;
        let streamedAnswer = '';
        const parser = createAskStreamParser(event => {
          if (event.type === 'delta') {
            if (!streamedAnswer) showAnswerPanel();
            streamedAnswer += event.text || '';
            renderAnswerMarkdown(streamedAnswer);
          } else if (event.type === 'result') {
            finalData = event.value;
          } else if (event.type === 'error') {
            throw new Error(apiErrorMessage(event.detail, 'Errore durante lo streaming /ask.'));
          }
        });

        try {
          while (true) {
            const { value, done } = await reader.read();
            parser.push(value, done);
            if (done) {
              readerFinished = true;
              break;
            }
          }
        } finally {
          if (!readerFinished) await reader.cancel().catch(() => {});
        }
        renderAskResult(finalData);
      } catch (e) {
        const answerText = document.getElementById('answer-text');
        answerText.textContent = `❌ Errore: ${e.message}`;
        answerText.classList.add('text-red-400');
        showAnswerPanel();
        setStatus('error');
      } finally {
        showLoader(false);
      }
    }

    /* Submit on Ctrl+Enter.
       showLoader() disabilita #ask-btn, ma questa scorciatoia chiamava
       submitQuery() direttamente, scavalcando il bottone: si potevano accodare
       N query premendo Ctrl+Invio ripetutamente. */
    document.getElementById('question-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        // click() e non submitQuery(): passa dal dispatcher (guardia servizi) e un
        // pulsante disabilitato non riceve il click.
        document.getElementById('ask-btn').click();
      }
    });

    /* ──────────── REDRAW AL CAMBIO TEMA ────────────
       shared.js invoca window.onThemeChange dopo il flip. La dashboard non lo
       definiva, quindi cambiando tema il grafo restava con i colori vecchi
       finché non si rilanciava una query: i colori dei nodi e degli archi sono
       cotti dentro al DataSet di vis.js, non letti dal CSS. */
    window.onThemeChange = function () {
      renderReasonsLegend();
      if (lastJsonPanelData) renderJsonPanel(lastJsonPanelData);
      if (lastGraphNodes.length) {
        const refreshed = lastGraphNodes.map(n => ({
          ...n,
          color: pillarColor(n.classification, n.nodeType),
          font: { ...(n.font || {}), color: themeVar('--node-font', '#eafff0') },
        }));
        renderGraph(refreshed, lastGraphEdges, lastVisOptions);
      }
    };

    /* Popola la legenda dei pilastri REASONS al caricamento */
    renderReasonsLegend();

    /* ──────────── STATO DEL PROGETTO ────────────
       Ex fascia KPI dell'Infografica. Il colore non è l'unico canale: ogni valore ha
       anche il testo ("non raggiungibile", "da aggiornare"). */
    async function loadProjectStatus() {
      const list = document.getElementById('project-status-list');
      const row = (label, value, note, tone, href) => {
        const item = document.createElement('div');
        const dt = document.createElement('dt');
        dt.className = 'text-slate-400';
        dt.textContent = label;
        const dd = document.createElement(href ? 'a' : 'dd');
        dd.className = 'block font-mono text-sm text-slate-100 break-words';
        if (href) dd.href = href;
        dd.textContent = value;
        if (tone) dd.style.color = `var(--color-${tone})`;
        item.append(dt, dd);
        if (note) {
          const small = document.createElement('div');
          small.className = 'text-slate-400';
          small.textContent = note;
          item.append(small);
        }
        return item;
      };
      try {
        const res = await fetch('/api/health');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const h = await res.json();
        const snap = h.snapshot || {}, ev = h.eval || {}, dep = h.dependencies || {};
        const nf = n => (typeof n === 'number' ? n.toLocaleString('it-IT') : '—');
        const trend = { up: '↑ in salita', down: '↓ in discesa', flat: '→ stabile' }[ev.trend] || '';
        // Soglia dell'eval-gate dal payload, non scritta a mano.
        const soglia = typeof ev.min_recall === 'number' ? ev.min_recall : 0.9;
        const stale = h.manifest && h.manifest.stale;
        list.replaceChildren(
          row(ev.key || 'recall', typeof ev.last_recall === 'number' ? (ev.last_recall * 100).toFixed(1) + '%' : '—',
              trend, typeof ev.last_recall !== 'number' ? null : ev.last_recall >= soglia ? 'success' : 'danger', '/eval'),
          row('Grafo', nf(snap.graph_nodes) + ' nodi', nf(snap.graph_edges) + ' archi', null, '/analysis'),
          row('Sezioni indicizzate', nf(snap.chunks), null, null),
          row('Versione indice', snap.version || '—', stale ? 'da aggiornare' : 'allineata', stale ? 'warning' : null),
          row('Qdrant', dep.qdrant ? 'raggiungibile' : 'non raggiungibile', null, dep.qdrant ? 'success' : 'danger'),
          row('Ollama', dep.ollama ? 'raggiungibile' : 'non raggiungibile', null, dep.ollama ? 'success' : 'danger'),
        );
      } catch (e) {
        const item = document.createElement('div');
        item.className = 'col-span-2 text-slate-400';
        item.textContent = `Stato non disponibile (${e.message}).`;
        list.replaceChildren(item);
      }
    }
    window.loadProjectStatus = loadProjectStatus;  // la shell lo richiama dopo un reindex
    loadProjectStatus();

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      closeNodeDetails: () => closeNodeDetails(),
      fitGraph: () => fitGraph(),
      restoreContextualGraph: () => restoreContextualGraph(),
      setGraphViewMode: el => setGraphViewMode(el.dataset.arg),
      showFullGraph: () => showFullGraph(),
      submitQuery: () => submitQuery(),
      toggleContextExpand: () => toggleContextExpand(),
      askExample: el => {
        // Scrive la domanda di esempio nel campo e la invia dal pulsante, così valgono
        // la guardia dei servizi e il blocco durante una query già in corso.
        document.getElementById('question-input').value = el.textContent.trim();
        document.getElementById('ask-btn').click();
      },
      switchTab: el => switchTab(el.dataset.arg),
      loadProjectStatus: () => loadProjectStatus(),
    });
