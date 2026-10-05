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
        if (!mapData.points || mapData.points.length === 0) {
          status.textContent = mapData.note || 'Nessun documento da proiettare.';
          drawSemanticMap();
          return;
        }
        status.textContent = `${mapData.points.length} documenti · ${(mapData.duplicates || []).length} coppie sospette`;
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
      const pad = 34;
      const toScreen = (x, y) => [pad + (x + 1) / 2 * (W - 2 * pad), pad + (1 - (y + 1) / 2) * (H - 2 * pad)];

      mapPoints = mapData.points.map(p => {
        const [sx, sy] = toScreen(p.x, p.y);
        return { ...p, sx, sy };
      });
      const byId = Object.fromEntries(mapPoints.map(p => [p.id, p]));

      // Linee dei duplicati (dietro ai punti)
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = dupLineColor;
      ctx.lineWidth = 1.2;
      for (const d of (mapData.duplicates || [])) {
        const a = byId[d.a], b = byId[d.b];
        if (a && b) { ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke(); }
      }
      ctx.restore();

      // Punti
      for (const p of mapPoints) {
        const color = p.community >= 0 ? communityColors[p.community % communityColors.length] : mutedNode;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, p.is_bridge ? 7 : 4.5, 0, Math.PI * 2);
        ctx.fillStyle = color; ctx.fill();
        if (p.is_bridge) { ctx.lineWidth = 2; ctx.strokeStyle = '#ffffff'; ctx.stroke(); }
      }
    }

    function renderLegend() {
      const communityColors = getCommunityColors();
      const dupTextColor = themeVar('--dups-b-color', '#ff6ee0');
      const communities = [...new Set(mapPoints.map(p => p.community))].filter(c => c >= 0).sort((a, b) => a - b);
      const parts = communities.map(c =>
        `<span><i class="dot" style="background:${communityColors[c % communityColors.length]}"></i> community ${c}</span>`);
      parts.push('<span><i class="dot" style="background:#fff"></i> nodo ponte (anello bianco)</span>');
      parts.push(`<span style="color:${dupTextColor}">— — coppia duplicata</span>`);
      document.getElementById('map-legend').innerHTML = parts.join('');
    }

    function renderDuplicates() {
      if (!mapData) return;
      const dups = mapData.duplicates || [];
      const el = document.getElementById('map-dups');
      const mutedText = themeVar('--muted-text', '#4dbf6e');
      if (!dups.length) { el.innerHTML = ''; return; }
      el.innerHTML = '<b>Potenziali duplicati (alta similarità, non collegati):</b>' +
        dups.map(d => `<div>• ${escapeHtml(d.a)} ↔ ${escapeHtml(d.b)} <span style="color:${mutedText}">(sim ${d.sim})</span></div>`).join('');
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
          tip.innerHTML = `${escapeHtml(p.id)}<br><span style="color:${mutedText}">community ${p.community}${p.is_bridge ? ' · PONTE' : ''}</span>`;
          canvas.style.cursor = 'pointer';
        } else { tip.style.display = 'none'; canvas.style.cursor = 'default'; }
      });
      canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
      canvas.addEventListener('click', e => {
        const r = canvas.getBoundingClientRect();
        const p = nearest(e.clientX - r.left, e.clientY - r.top);
        if (!p) return;
        // Impact Ripple: prepara e calcola l'impatto del documento cliccato (senza rubare lo scroll).
        document.getElementById('ripple-node').value = p.doc_id;
        loadImpact();
        // Collegamento mappa → Query deterministica: interroga le relazioni del documento cliccato
        // e porta l'utente al pannello con la risposta (lettura diretta di nodi/archi, nessun LLM).
        const gq = document.getElementById('gq-input');
        gq.value = 'relazioni di ' + p.doc_id;
        runGraphQuery(p.doc_id);
        document.getElementById('section-query').scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    })();

    /* ══════════ IMPACT RIPPLE ══════════ */
    async function loadNodeList() {
      try {
        const res = await fetch('/api/graph/all');
        if (!res.ok) return;
        const data = await res.json();
        const dl = document.getElementById('nodes-list');
        dl.innerHTML = data.nodes.map(n => `<option value="${escapeHtml(n.id)}">`).join('');
      } catch (e) { /* best-effort */ }
    }

    let lastImpactData = null;
    async function loadImpact() {
      const node = document.getElementById('ripple-node').value.trim();
      const depth = document.getElementById('ripple-depth').value;
      const status = document.getElementById('ripple-status');
      if (!node) { status.textContent = 'Inserisci un nodo.'; return; }
      status.textContent = 'Calcolo…';
      try {
        const res = await fetch(`/api/graph/impact?node=${encodeURIComponent(node)}&depth=${depth}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'HTTP ' + res.status }));
          throw new Error(apiErrorMessage(err.detail, 'HTTP ' + res.status));
        }
        const data = await res.json();
        status.textContent = `${data.nodes.length} nodi impattati · anelli: [${data.rings.join(', ')}]`;
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
      const maxR = Math.min(W, H) / 2 - 40;
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
      canvas.addEventListener('mousemove', e => {
        const r = canvas.getBoundingClientRect();
        const mx = e.clientX - r.left, my = e.clientY - r.top;
        let best = null, bd = 120;
        for (const n of rippleNodes) {
          const d = (n.sx - mx) ** 2 + (n.sy - my) ** 2;
          if (d < bd) { bd = d; best = n; }
        }
        if (best) {
          const mutedText = themeVar('--muted-text', '#4dbf6e');
          tip.style.display = 'block';
          tip.style.left = (mx + 12) + 'px'; tip.style.top = (my + 12) + 'px';
          tip.innerHTML = `${escapeHtml(best.id)}<br><span style="color:${mutedText}">${escapeHtml(best.type)}${best.kind ? ' · ' + escapeHtml(best.kind) : ''} · anello ${best.ring}</span>`;
        } else { tip.style.display = 'none'; }
      });
      canvas.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
    })();

    /* escapeHtml vive in /static/shared.js (escapa anche l'apice singolo): la copia
       locale, dichiarata dopo, la sovrascriveva con una versione che non lo gestiva. */

    /* ══════════ QUERY DETERMINISTICA ══════════ */
    // `target` opzionale: id di nodo esplicito (es. click su un punto della Semantic Map).
    // Quando presente, il backend salta l'euristica di match testuale e usa questo nodo.
    async function runGraphQuery(target) {
      const q = document.getElementById('gq-input').value.trim();
      const status = document.getElementById('gq-status');
      const out = document.getElementById('gq-out');
      if (!q) { status.textContent = 'Scrivi una domanda.'; return; }
      status.textContent = 'Interrogazione…';
      try {
        let url = '/api/graph/query?q=' + encodeURIComponent(q);
        if (target) url += '&target=' + encodeURIComponent(target);
        const res = await fetch(url);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(apiErrorMessage(err.detail, 'HTTP ' + res.status));
        }
        const d = await res.json();
        status.textContent = `intent: ${d.intent}` + (d.count !== undefined ? ` · ${d.count}` : '');
        out.style.display = 'block';
        out.textContent = JSON.stringify(d, null, 2);
      } catch (e) { status.textContent = '❌ ' + e.message; }
    }
    document.getElementById('gq-input').addEventListener('keydown', e => { if (e.key === 'Enter') runGraphQuery(); });

    /* ══════════ CANVAS QUALITY ══════════ */
    const FIDELITY_STYLE = {
      alto:        { color: 'var(--type-entity)',   label: 'alto' },
      medio:       { color: 'var(--community-3)',   label: 'medio' },
      basso:       { color: 'var(--community-6)',   label: 'basso' },
      sconosciuto: { color: 'var(--muted-node-color)', label: '?' },
    };
    async function loadCanvasQuality() {
      const status = document.getElementById('cq-status');
      status.textContent = 'Caricamento…';
      try {
        const res = await fetch('/api/canvas-quality');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const d = await res.json();
        if (!d.total_reviews) {
          status.textContent = 'Nessuna canvas review ancora: archivia una change per popolare il pannello.';
          document.getElementById('cq-trend').innerHTML = '';
          document.getElementById('cq-divergences').innerHTML = '';
          return;
        }
        const c = d.fidelity_counts;
        status.textContent = `${d.total_reviews} review · fedeltà: ${c.alto} alto / ${c.medio} medio / ${c.basso} basso`;
        // Trend (dalla più vecchia alla più recente): un pallino colorato per change.
        document.getElementById('cq-trend').innerHTML = d.trend.map(t => {
          const s = FIDELITY_STYLE[t.fidelity] || FIDELITY_STYLE.sconosciuto;
          return `<span><i class="dot" style="background:${s.color}"></i> ${escapeHtml(t.feature)} (${s.label})</span>`;
        }).join('');
        const el = document.getElementById('cq-divergences');
        el.innerHTML = d.top_divergences.length
          ? '<b>Divergenze più frequenti:</b>' + d.top_divergences.map(x =>
              `<div>• ${escapeHtml(x.text)}${x.count > 1 ? ` <b>×${x.count}</b>` : ''}</div>`).join('')
          : '<b>Nessuna divergenza registrata nelle review.</b>';
      } catch (e) {
        status.textContent = '❌ ' + e.message;
      }
    }

    window.addEventListener('resize', () => { drawSemanticMap(); });
    loadSemanticMap();
    loadNodeList();
    loadCanvasQuality();

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      loadCanvasQuality: () => loadCanvasQuality(),
      loadImpact: () => loadImpact(),
      loadSemanticMap: () => loadSemanticMap(),
      runGraphQuery: () => runGraphQuery(),
    });
