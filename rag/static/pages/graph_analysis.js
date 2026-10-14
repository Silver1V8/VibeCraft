/* Script della pagina graph_analysis.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
    /* themeVar / startMatrixRain / stopMatrixRain: vedi /static/shared.js */

    /* Palette community/tipo lette a runtime dal tema attivo (Punto 3 contratto):
       niente più array hardcoded, si rileggono a ogni ridisegno del canvas. */
    function getCommunityColors() {
      return Array.from({ length: 10 }, (_, i) => themeVar(`--community-${i}`, '#5a7a66'));
    }
    function getTypeColors() {
      return {
        document: themeVar('--type-document', '#4da3ff'),
        entity:   themeVar('--type-entity',   '#00ff41'),
        code:     themeVar('--type-code',     '#ffb648'),
      };
    }

    /* THEME SWITCHER: setUiTheme e la sync iniziale vivono in /static/shared.js.
       Qui aggiungo solo il redraw specifico: i canvas sono bitmap e vanno
       ridisegnati esplicitamente coi nuovi colori del tema. */
    window.onThemeChange = function () {
      drawSemanticMap();
      renderLegend();
      renderDuplicates();
      if (lastImpactData) drawRipple(lastImpactData);
    };

    function fitCanvas(canvas) {
      const dpr = window.devicePixelRatio || 1;
      const cssW = canvas.clientWidth, cssH = canvas.clientHeight || parseInt(canvas.getAttribute('height'));
      canvas.width = cssW * dpr; canvas.height = cssH * dpr;
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return { ctx, W: cssW, H: cssH };
    }

    /* ══════════ SEMANTIC MAP ══════════ */
    let mapPoints = [];   // {id, sx, sy, community, is_bridge}
    let mapData = null;
    let selectedNode = '';      // nodo del pannello di destra (doc_id, entità o simbolo)
    let highlightedDup = null;  // coppia simile evidenziata sulla mappa

    // Solo i gruppi più grandi hanno un colore proprio: la palette ne ha 10 e oltre si
    // ripetevano (gruppo 0 e 10 dello stesso verde). Gli altri e i documenti isolati
    // restano nel colore neutro, con una voce di legenda sola.
    const MAX_COLORED_COMMUNITIES = 8;
    function communityColor(community, colors, muted) {
      return community >= 0 && community < MAX_COLORED_COMMUNITIES ? colors[community] : muted;
    }
    function communityLabel(community) {
      if (community < 0) return 'senza gruppo';
      return mapData?.communities?.find(c => c.id === community)?.label || `gruppo ${community + 1}`;
    }

    async function loadSemanticMap() {
      const status = document.getElementById('map-status');
      status.textContent = 'Caricamento…';
      try {
        const res = await fetch('/api/graph/semantic-map');
        if (!res.ok) {
          const error = await res.json().catch(() => ({ detail: 'HTTP ' + res.status }));
          if (error.detail?.code === 'project_vectors_missing') window.parent.reportProjectIndexIssue?.(selectedProjectId());
          throw new Error(apiErrorMessage(error.detail, 'HTTP ' + res.status));
        }
        const data = await res.json();
        if (!Array.isArray(data.points)) throw new Error('Dati della mappa non validi. Premi Ricarica.');
        mapData = data;
        highlightedDup = null;
        if (!mapData.points || mapData.points.length === 0) {
          status.textContent = mapData.note || 'Nessun documento da proiettare.';
          drawSemanticMap();
          return;
        }
        // I punti sono SEZIONI: prima l'etichetta diceva "384 documenti" per 50 documenti.
        const documents = mapData.documents ?? new Set(mapData.points.map(p => p.doc_id)).size;
        const pairs = (mapData.duplicates || []).length;
        status.textContent = `${mapData.points.length} sezioni di ${documents} documenti · `
          + `${pairs} ${pairs === 1 ? 'coppia simile' : 'coppie simili'}`;
        drawSemanticMap();
        renderLegend();
        renderDuplicates();
      } catch (e) {
        status.textContent = '❌ ' + e.message;
      }
    }

    function drawSemanticMap() {
      const canvas = document.getElementById('map-canvas');
      const { ctx, W, H } = fitCanvas(canvas);
      ctx.clearRect(0, 0, W, H);
      if (!mapData || !mapData.points.length) return;
      const communityColors = getCommunityColors();
      const mutedNode = themeVar('--muted-node-color', '#5a7a66');
      const dupLineColor = themeVar('--dup-line-color', 'rgba(255,110,224,0.7)');
      const selectColor = themeVar('--body-text', '#d8ffe4');
      const pad = 34;
      const toScreen = (x, y) => [pad + (x + 1) / 2 * (W - 2 * pad), pad + (1 - (y + 1) / 2) * (H - 2 * pad)];

      mapPoints = mapData.points.map(p => {
        const [sx, sy] = toScreen(p.x, p.y);
        return { ...p, sx, sy };
      });
      const byId = Object.fromEntries(mapPoints.map(p => [p.id, p]));
      const dups = mapData.duplicates || [];

      // Linee delle coppie simili (dietro ai punti); quella evidenziata più spessa.
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = dupLineColor;
      dups.forEach((d, i) => {
        const a = byId[d.a], b = byId[d.b];
        if (!a || !b) return;
        ctx.lineWidth = i === highlightedDup ? 3 : 1.2;
        ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke();
      });
      ctx.restore();

      // Punti
      const pair = highlightedDup !== null && dups[highlightedDup] ? [dups[highlightedDup].a, dups[highlightedDup].b] : [];
      for (const p of mapPoints) {
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.is_bridge ? 7 : 4.5, 0, Math.PI * 2);
        ctx.fillStyle = communityColor(p.community, communityColors, mutedNode); ctx.fill();
        if (p.is_bridge) { ctx.lineWidth = 2; ctx.strokeStyle = '#ffffff'; ctx.stroke(); }
        // Anello largo sulle sezioni del nodo selezionato e sulla coppia evidenziata.
        const marked = (selectedNode && p.doc_id === selectedNode) ? selectColor : pair.includes(p.id) ? dupLineColor : null;
        if (marked) {
          ctx.beginPath(); ctx.arc(p.sx, p.sy, 10, 0, Math.PI * 2);
          ctx.lineWidth = 2; ctx.strokeStyle = marked; ctx.stroke();
        }
      }
    }

    function renderLegend() {
      const communityColors = getCommunityColors();
      const mutedNode = themeVar('--muted-node-color', '#5a7a66');
      const dupTextColor = themeVar('--dups-b-color', '#ff6ee0');
      const sizes = {};
      mapPoints.forEach(p => { sizes[p.community] = (sizes[p.community] || 0) + 1; });
      const communities = Object.keys(sizes).map(Number).filter(c => c >= 0 && c < MAX_COLORED_COMMUNITIES).sort((a, b) => a - b);
      const parts = communities.map(c => {
        const info = mapData?.communities?.find(x => x.id === c);
        const detail = `${info?.documents ?? '?'} documenti, ${sizes[c]} sezioni`
          + (info?.entities?.length ? ` · entità più citate: ${info.entities.join(', ')}` : '');
        return `<span title="${escapeHtml(detail)}"><i class="dot" style="background:${communityColors[c]}"></i> ${escapeHtml(communityLabel(c))}</span>`;
      });
      if (Object.keys(sizes).some(c => Number(c) < 0 || Number(c) >= MAX_COLORED_COMMUNITIES)) {
        parts.push(`<span><i class="dot" style="background:${mutedNode}"></i> altri gruppi o nessuno</span>`);
      }
      parts.push('<span><i class="dot" style="background:#fff"></i> documento ponte (anello bianco)</span>');
      parts.push(`<span style="color:${dupTextColor}">— — coppia simile</span>`);
      document.getElementById('map-legend').innerHTML = parts.join('');
    }

    // Le prime 5 coppie visibili, le altre in un elenco richiudibile: erano ~1.000 px di righe.
    const DUPS_VISIBLE = 5;
    function renderDuplicates() {
      if (!mapData) return;
      const dups = mapData.duplicates || [];
      const el = document.getElementById('map-dups');
      const mutedText = themeVar('--muted-text', '#4dbf6e');
      if (!dups.length) { el.innerHTML = ''; return; }
      const row = (d, i) => `<button type="button" data-click="highlightDuplicate" data-arg="${i}" aria-pressed="${i === highlightedDup}">`
        + `• ${escapeHtml(d.a)} ↔ ${escapeHtml(d.b)} <span style="color:${mutedText}">(sim ${d.sim})</span></button>`;
      el.innerHTML = '<b>Sezioni molto simili in documenti diversi</b> (clicca per vederle sulla mappa):'
        + dups.slice(0, DUPS_VISIBLE).map(row).join('')
        + (dups.length > DUPS_VISIBLE ? `<details><summary>Mostra le altre ${dups.length - DUPS_VISIBLE}</summary>`
          + dups.slice(DUPS_VISIBLE).map((d, i) => row(d, i + DUPS_VISIBLE)).join('') + '</details>' : '');
    }

    function highlightDuplicate(index) {
      highlightedDup = highlightedDup === index ? null : index;
      drawSemanticMap();
      renderDuplicates();
      document.getElementById('map-canvas').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Hover + click sulla mappa
    (function () {
      const canvas = document.getElementById('map-canvas');
      const tip = document.getElementById('map-tooltip');
      function nearest(mx, my) {
        let best = null, bd = 100;
        for (const p of mapPoints) {
          const d = (p.sx - mx) ** 2 + (p.sy - my) ** 2;
          if (d < bd) { bd = d; best = p; }
        }
        return best;
      }
      canvas.addEventListener('mousemove', e => {
        const r = canvas.getBoundingClientRect();
        const p = nearest(e.clientX - r.left, e.clientY - r.top);
        if (p) {
          const mutedText = themeVar('--muted-text', '#4dbf6e');
          tip.style.display = 'block';
          tip.style.left = (e.clientX - r.left + 12) + 'px';
          tip.style.top = (e.clientY - r.top + 12) + 'px';
          tip.innerHTML = `${escapeHtml(p.id)}<br><span style="color:${mutedText}">${escapeHtml(communityLabel(p.community))}${p.is_bridge ? ' · PONTE' : ''}</span>`;
          canvas.style.cursor = 'pointer';
        } else { tip.style.display = 'none'; canvas.style.cursor = 'default'; }
      });
      canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
      canvas.addEventListener('click', e => {
        const r = canvas.getBoundingClientRect();
        const p = nearest(e.clientX - r.left, e.clientY - r.top);
        if (p) retainWorkspaceTask(selectNode(p.doc_id)).catch(error => console.error(error));
      });
    })();

    /* ══════════ NODO SELEZIONATO ══════════
       Un'unica selezione per mappa, ricerca, elenco delle relazioni e ripple: il pannello
       mostra relazioni e propagazione dell'impatto dello stesso nodo, uno accanto all'altro. */
    async function loadNodeList() {
      try {
        const res = await fetch('/api/graph/all');
        if (!res.ok) return;
        const data = await res.json();
        const dl = document.getElementById('nodes-list');
        dl.innerHTML = data.nodes.map(n => `<option value="${escapeHtml(n.id)}">`).join('');
      } catch (e) { /* best-effort */ }
    }

    async function selectNode(id) {
      if (!id) return;
      selectedNode = id;
      document.getElementById('node-search').value = id;
      document.getElementById('node-empty').hidden = true;
      document.getElementById('node-detail').hidden = false;
      document.getElementById('node-name').textContent = id;
      drawSemanticMap();
      await Promise.all([loadRelations(), loadImpact()]);
    }

    async function loadRelations() {
      const node = document.getElementById('node-search').value.trim();
      const status = document.getElementById('rel-status');
      const list = document.getElementById('node-relations');
      if (!node) { status.textContent = 'Scegli un nodo.'; return; }
      status.textContent = 'Lettura…';
      try {
        // target esplicito: il backend non deve indovinare il nodo dal testo della domanda.
        const res = await fetch('/api/graph/query?q=' + encodeURIComponent('relazioni di ' + node)
          + '&target=' + encodeURIComponent(node));
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(apiErrorMessage(err.detail, 'HTTP ' + res.status));
        }
        const d = await res.json();
        const rows = [...(d.out || []).map(e => ['→', e.relation, e.to]), ...(d.in || []).map(e => ['←', e.relation, e.from])];
        status.textContent = `· ${rows.length}`;
        list.innerHTML = rows.length
          ? rows.map(([dir, rel, other]) => `<li><span class="rel">${dir} ${escapeHtml(rel || 'collegato a')}</span>`
              + `<button type="button" data-click="selectNode" data-arg="${escapeHtml(other)}">${escapeHtml(other)}</button></li>`).join('')
          : '<li><span class="rel">Nessuna relazione diretta.</span></li>';
      } catch (e) {
        status.textContent = '❌ ' + e.message;
        list.innerHTML = '';
      }
    }

    let lastImpactData = null;
    async function loadImpact() {
      const node = document.getElementById('node-search').value.trim();
      const depth = document.getElementById('ripple-depth').value;
      const status = document.getElementById('ripple-status');
      if (!node) { status.textContent = 'Scegli un nodo.'; return; }
      status.textContent = 'Calcolo…';
      try {
        const res = await fetch(`/api/graph/impact?node=${encodeURIComponent(node)}&depth=${depth}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'HTTP ' + res.status }));
          throw new Error(apiErrorMessage(err.detail, 'HTTP ' + res.status));
        }
        const data = await res.json();
        status.textContent = `· ${data.nodes.length - 1} nodi toccati · per anello: ${data.rings.slice(1).join(', ') || '0'}`;
        lastImpactData = data;
        drawRipple(data);
      } catch (e) {
        status.textContent = '❌ ' + e.message;
      }
    }

    let rippleNodes = [];
    function drawRipple(data) {
      const canvas = document.getElementById('ripple-canvas');
      const { ctx, W, H } = fitCanvas(canvas);
      ctx.clearRect(0, 0, W, H);
      const typeColors = getTypeColors();
      const mutedNode = themeVar('--muted-node-color', '#5a7a66');
      const ringGuideColor = themeVar('--ring-guide-color', 'rgba(31,92,56,0.7)');
      const rippleEdgeColor = themeVar('--ripple-edge-color', 'rgba(120,255,160,0.18)');
      const textColor = themeVar('--body-text', '#d8ffe4');
      const fontFamily = themeVar('--canvas-font-family', 'monospace');
      const cx = W / 2, cy = H / 2;
      const maxRing = Math.max(1, data.rings.length - 1);
      const maxR = Math.min(W, H) / 2 - 24;
      const ringRadius = i => (i / maxRing) * maxR;

      // Anelli guida
      ctx.save();
      ctx.setLineDash([3, 4]); ctx.strokeStyle = ringGuideColor; ctx.lineWidth = 1;
      for (let i = 1; i < data.rings.length; i++) {
        ctx.beginPath(); ctx.arc(cx, cy, ringRadius(i), 0, Math.PI * 2); ctx.stroke();
      }
      ctx.restore();

      // Posiziona i nodi per anello
      const perRing = {};
      data.nodes.forEach(n => { (perRing[n.ring] = perRing[n.ring] || []).push(n); });
      const pos = {};
      Object.keys(perRing).forEach(ring => {
        const r = parseInt(ring);
        const arr = perRing[ring];
        if (r === 0) { arr.forEach(n => pos[n.id] = [cx, cy]); return; }
        arr.forEach((n, k) => {
          const ang = (k / arr.length) * Math.PI * 2 - Math.PI / 2;
          pos[n.id] = [cx + Math.cos(ang) * ringRadius(r), cy + Math.sin(ang) * ringRadius(r)];
        });
      });

      // Archi
      ctx.strokeStyle = rippleEdgeColor; ctx.lineWidth = 1;
      for (const e of data.edges) {
        const a = pos[e.from], b = pos[e.to];
        if (a && b) { ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
      }

      // Nodi
      rippleNodes = [];
      for (const n of data.nodes) {
        const [x, y] = pos[n.id];
        const isCenter = n.ring === 0;
        const color = typeColors[n.type] || mutedNode;
        ctx.beginPath(); ctx.arc(x, y, isCenter ? 9 : 5, 0, Math.PI * 2);
        ctx.fillStyle = color; ctx.fill();
        if (isCenter) { ctx.lineWidth = 2.5; ctx.strokeStyle = '#fff'; ctx.stroke(); }
        rippleNodes.push({ ...n, sx: x, sy: y });
      }
      // Etichetta del centro
      ctx.fillStyle = textColor; ctx.font = `12px ${fontFamily}`; ctx.textAlign = 'center';
      ctx.fillText(data.center.length > 30 ? data.center.slice(0, 28) + '…' : data.center, cx, cy - 16);
    }

    (function () {
      const canvas = document.getElementById('ripple-canvas');
      const tip = document.getElementById('ripple-tooltip');
      function nearest(e) {
        const r = canvas.getBoundingClientRect();
        const mx = e.clientX - r.left, my = e.clientY - r.top;
        let best = null, bd = 120;
        for (const n of rippleNodes) {
          const d = (n.sx - mx) ** 2 + (n.sy - my) ** 2;
          if (d < bd) { bd = d; best = n; }
        }
        return { best, mx, my };
      }
      canvas.addEventListener('mousemove', e => {
        const { best, mx, my } = nearest(e);
        if (best) {
          const mutedText = themeVar('--muted-text', '#4dbf6e');
          tip.style.display = 'block';
          tip.style.left = (mx + 12) + 'px'; tip.style.top = (my + 12) + 'px';
          tip.innerHTML = `${escapeHtml(best.id)}<br><span style="color:${mutedText}">${escapeHtml(best.type)}${best.kind ? ' · ' + escapeHtml(best.kind) : ''} · anello ${best.ring}</span>`;
          canvas.style.cursor = 'pointer';
        } else { tip.style.display = 'none'; canvas.style.cursor = 'default'; }
      });
      canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
      canvas.addEventListener('click', e => {
        const { best } = nearest(e);
        if (best && best.id !== selectedNode) retainWorkspaceTask(selectNode(best.id)).catch(error => console.error(error));
      });
    })();

    /* escapeHtml vive in /static/shared.js (escapa anche l'apice singolo): la copia
       locale, dichiarata dopo, la sovrascriveva con una versione che non lo gestiva. */

    document.getElementById('node-search').addEventListener('keydown', e => {
      if (e.key === 'Enter') retainWorkspaceTask(selectNode(e.target.value.trim())).catch(error => console.error(error));
    });

    window.addEventListener('resize', () => { drawSemanticMap(); if (lastImpactData) drawRipple(lastImpactData); });
    loadSemanticMap();
    loadNodeList();

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      highlightDuplicate: el => highlightDuplicate(Number(el.dataset.arg)),
      loadImpact: () => loadImpact(),
      loadSemanticMap: () => loadSemanticMap(),
      selectNode: el => selectNode(el.dataset.arg),
      selectSearchedNode: () => selectNode(document.getElementById('node-search').value.trim()),
    });
