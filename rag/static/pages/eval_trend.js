/* Script della pagina eval_trend.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
    /* themeVar / startMatrixRain / stopMatrixRain / setUiTheme: vedi /static/shared.js */

    /* La metrica NON e' scelta qui: la decide il server, ed e' quella dell'eval-gate
       (A2b). Scriverla a mano nella pagina significava che il gate poteva spostarsi
       — 10 -> 5 -> 2, ogni volta perche' il k precedente era saturo — e questo grafico
       restava a mostrare una curva piatta a 1.000, cioe' un numero che non puo' scendere.
       Il fallback serve solo a un server piu' vecchio del payload. */
    let KEY = "recall@10";
    function recallOf(e) { return e.recall && e.recall[KEY]; }

    let lastData = null;
    window.onThemeChange = function () { if (lastData) render(lastData); };

    function render(data) {
      lastData = data;
      const s = data.summary || {};
      KEY = s.key || KEY;
      document.querySelectorAll(".chiave-recall").forEach(el => { el.textContent = KEY; });
      const rows = (data.history || []).filter(e => typeof recallOf(e) === "number");
      const trend = s.trend || "flat";
      const last = s.last_recall;
      renderCards(s, rows, trend, last);

      const chart = document.getElementById("chart");
      if (rows.length < 2) { chart.innerHTML = '<div class="empty">Servono almeno 2 valutazioni per un trend. Lancia <code>uv run python -m eval.run</code>.</div>'; return; }

      /* ── Asse X TEMPORALE ──
         Prima i punti erano spaziati per indice: un intervallo di tre mesi
         occupava lo stesso spazio di uno di un'ora, quindi la pendenza — cioe
         l'unica cosa che un grafico di trend deve comunicare — era falsa.
         Ordino per data e distribuisco sul tempo reale. */
      rows.sort((a, b) => tsOf(a) - tsOf(b));
      const t0 = tsOf(rows[0]), t1 = tsOf(rows[rows.length - 1]);
      const span = (t1 - t0) || 1;

      const W = 880, H = 320, padL = 46, padR = 14, padT = 16, padB = 44;
      const vals = rows.map(recallOf);

      /* Dominio Y: include sempre la soglia del gate, cosi si vede quanto
         margine c'e. Non si sfora l'1.0, perche la recall non puo superarlo e
         mostrarlo suggerirebbe spazio di crescita inesistente. */
      const soglia = sogliaGate(rows);
      let lo = Math.min(...vals, soglia == null ? 1 : soglia);
      lo = Math.max(0, lo - 0.05);
      const hi = 1.0;
      /* Tacche su valori tondi (70/80/90/100%, non 70/77/85/93%): passo "comodo" con
         al massimo 6 intervalli e minimo arrotondato per difetto a un suo multiplo. */
      const step = [0.05, 0.1, 0.2, 0.25].find(s => (hi - lo) / s <= 6) || 0.25;
      lo = Math.max(0, Math.floor(lo / step + 1e-9) * step);
      const ticks = Math.round((hi - lo) / step);

      const x = t => padL + (W - padL - padR) * ((t - t0) / span);
      const y = v => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo));

      // Griglia e etichette Y
      const grid = [];
      for (let t = 0; t <= ticks; t++) {
        const v = lo + step * t, yy = y(v);
        grid.push(`<line class="grid" x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"/>`);
        grid.push(`<text class="lbl" x="4" y="${yy + 4}">${(v * 100).toFixed(0)}%</text>`);
      }

      // Etichette X datate: 5 tacche equispaziate NEL TEMPO
      const xTicks = [];
      const nTick = 4;
      for (let i = 0; i <= nTick; i++) {
        const t = t0 + span * i / nTick, xx = x(t);
        xTicks.push(`<line class="grid" x1="${xx}" y1="${padT}" x2="${xx}" y2="${H - padB}"/>`);
        xTicks.push(`<text class="lbl" x="${xx}" y="${H - padB + 16}" text-anchor="middle">${fmtAsse(t, span)}</text>`);
      }

      // Linea di soglia del gate
      const thr = soglia == null ? '' :
        `<line class="threshold" x1="${padL}" y1="${y(soglia)}" x2="${W - padR}" y2="${y(soglia)}"/>` +
        `<text class="lbl" x="${W - padR}" y="${y(soglia) - 5}" text-anchor="end">soglia ${(soglia * 100).toFixed(0)}%</text>`;

      const path = rows.map((e, i) => `${i ? "L" : "M"}${x(tsOf(e)).toFixed(1)},${y(recallOf(e)).toFixed(1)}`).join(" ");

      /* Marker per FORMA, non per solo colore. */
      const marks = rows.map(e => {
        const cx = x(tsOf(e)), cy = y(recallOf(e));
        const t = `<title>${escapeHtml(descrizionePunto(e))}</title>`;
        if (e.source === "gate" && e.gate && e.gate.passed === false)
          return `<path class="mk-fail" d="M${cx - 4},${cy - 4}l8,8M${cx + 4},${cy - 4}l-8,8">${t}</path>`;
        if (e.source === "gate")
          return `<circle class="mk-gate" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.5">${t}</circle>`;
        return `<path class="mk-run" d="M${cx.toFixed(1)},${(cy - 4.5).toFixed(1)}l4.5,8h-9z">${t}</path>`;
      }).join("");

      const daA = `${fmtCompleto(t0)} – ${fmtCompleto(t1)}`;
      chart.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet"
             role="img" aria-label="Andamento di ${KEY} su ${rows.length} valutazioni fra ${daA}. Valore piu recente ${(recallOf(rows[rows.length-1]) * 100).toFixed(1)}%.">
        ${grid.join("")}
        ${xTicks.join("")}
        <line class="axis" x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}"/>
        <line class="axis" x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}"/>
        ${thr}
        <path class="line" d="${path}"/>
        ${marks}
      </svg>`;

      renderTabella(rows);
    }

    /* Card con il contesto per leggere il numero: quanto margine resta sulla soglia del
       gate, com'è andata l'ultima valutazione e la recall agli altri k. Prima c'erano
       valore, "flat" in inglese e il numero di punti, senza dire se 82,8% fosse tanto. */
    const TREND_LABEL = { up: "in salita", down: "in discesa", flat: "stabile" };
    function pct(v) { return (v * 100).toFixed(1).replace(".", ",") + "%"; }
    function renderCards(s, rows, trend, last) {
      const soglia = typeof s.min_recall === "number" ? s.min_recall : sogliaGate(rows);
      const ultimo = rows.slice().sort((a, b) => tsOf(a) - tsOf(b)).at(-1);
      const margine = last != null && soglia != null ? (last - soglia) * 100 : null;
      const noteRecall = margine == null ? "" : `<div class="note ${margine >= 0 ? "ok" : "ko"}">soglia del gate ${pct(soglia)}`
        + ` · margine ${margine >= 0 ? "+" : ""}${margine.toFixed(1).replace(".", ",")} punti</div>`;
      // Recall agli altri k: se quella del gate si avvicina al 100% il gate smette di distinguere le versioni.
      const perK = ultimo && ultimo.recall ? Object.keys(ultimo.recall)
        .sort((a, b) => Number(a.split("@")[1]) - Number(b.split("@")[1]))
        .map(k => `<span class="${k === KEY ? "is-gate" : ""}">${escapeHtml(k.replace("recall", ""))} ${pct(ultimo.recall[k])}</span>`).join("") : "";
      document.getElementById("cards").innerHTML = `
        <div class="card"><div class="k">${escapeHtml(KEY)} attuale</div>
          <div class="v">${last == null ? "—" : pct(last)}</div>${noteRecall}</div>
        <div class="card"><div class="k">andamento</div>
          <div class="v"><span class="badge ${trend}">${TREND_LABEL[trend] || escapeHtml(trend)}</span></div>
          <div class="note">${s.history_points ?? rows.length} valutazioni</div></div>
        ${ultimo ? `<div class="card"><div class="k">ultima valutazione</div>
          <div class="v v-small">${escapeHtml(new Date(tsOf(ultimo)).toLocaleDateString("it-IT", { day: "2-digit", month: "short", year: "numeric" }))}</div>
          <div class="note">${escapeHtml(esitoDi(ultimo))}${ultimo.n_cases ? ` · ${Number(ultimo.n_cases)} casi` : ""}</div></div>` : ""}
        ${perK ? `<div class="card" title="Recall dell'ultima valutazione ai diversi k: se quella del gate arriva al 100% il gate non distingue più una versione peggiore.">
          <div class="k">recall per k</div><div class="per-k">${perK}</div></div>` : ""}`;
    }

    /* ──────────── HELPER ──────────── */
    function tsOf(e) { const t = Date.parse(e.timestamp || ""); return Number.isNaN(t) ? 0 : t; }

    // La soglia del gate e la stessa per tutte le run: prendo l'ultima nota.
    function sogliaGate(rows) {
      for (let i = rows.length - 1; i >= 0; i--) {
        const v = rows[i].gate && rows[i].gate.min_recall;
        if (typeof v === "number") return v;
      }
      return null;
    }

    // Sotto le 48 ore mostra anche l'ora, altrimenti solo la data: su una
    // finestra di giorni cinque orari identici non direbbero nulla.
    function fmtAsse(t, span) {
      const d = new Date(t);
      const opts = span < 48 * 3600e3
        ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }
        : { day: "2-digit", month: "2-digit" };
      return d.toLocaleString("it-IT", opts);
    }
    function fmtCompleto(t) {
      return new Date(t).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
    }

    function esitoDi(e) {
      if (e.source === "gate" && e.gate && e.gate.passed === false) return "gate BLOCCATO";
      if (e.source === "gate") return "gate superato";
      return e.source || "eval";
    }
    function descrizionePunto(e) {
      return `${(recallOf(e) * 100).toFixed(1)}% · ${fmtCompleto(tsOf(e))} · ${esitoDi(e)}`
        + (e.version ? ` · ${e.version}` : "") + (e.commit ? ` · ${e.commit}` : "");
    }

    /* Accesso alternativo ai dati: un grafico non e leggibile da tastiera ne da
       screen reader, e i <title> SVG da soli non bastano. */
    function renderTabella(rows) {
      const box = document.getElementById("data-table");
      const righe = rows.slice().reverse().map(e => {
        const fallito = e.source === "gate" && e.gate && e.gate.passed === false;
        return `<tr class="${fallito ? "row-fail" : ""}">
          <td>${escapeHtml(fmtCompleto(tsOf(e)))}</td>
          <td>${(recallOf(e) * 100).toFixed(1)}%</td>
          <td>${escapeHtml(esitoDi(e))}</td>
          <td>${e.n_cases ? Number(e.n_cases) : "—"}</td>
          <td>${escapeHtml(e.version || "—")}</td>
          <td>${escapeHtml(e.commit || "—")}</td>
        </tr>`;
      }).join("");
      box.innerHTML = `<summary>Dati del grafico in tabella (${rows.length} valutazioni)</summary>
        <table>
          <thead><tr><th>Data</th><th>${KEY}</th><th>Esito</th><th>Casi</th><th>Versione</th><th>Commit</th></tr></thead>
          <tbody>${righe}</tbody>
        </table>`;
    }

    /* Prima l'errore veniva concatenato all'oggetto Error grezzo e non c'era
       modo di riprovare senza ricaricare la pagina. */
    function caricaStorico() {
      const chart = document.getElementById("chart");
      chart.innerHTML = '<div class="empty">Caricamento…</div>';
      fetch("/api/eval/history?limit=200")
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(render)
        .catch(e => {
          chart.innerHTML = `<div class="empty">Impossibile caricare lo storico: ${escapeHtml(e.message)}
            <br/><button type="button" class="btn btn-secondary" style="margin-top:.75rem" data-click="caricaStorico">Riprova</button></div>`;
        });
    }
    caricaStorico();

    /* ══════════ QUALITÀ DEI CANVAS (era in Analisi) ══════════
       Colori dai token semantici di shared.css, uguali nei due temi; il giudizio è
       comunque scritto accanto al pallino, non affidato al solo colore. */
    const FIDELITY_STYLE = {
      alto:        { color: 'var(--color-success)', label: 'alto' },
      medio:       { color: 'var(--color-warning)', label: 'medio' },
      basso:       { color: 'var(--color-danger)', label: 'basso' },
      sconosciuto: { color: 'var(--color-text-muted)', label: '?' },
    };
    // Oltre le prime 5 le divergenze stanno in un elenco richiudibile: erano 800 px di pagina.
    const CQ_VISIBLE = 5;
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
        // Il testo arriva dalle review in Markdown: inlineMd (shared.js) ne fa grassetto e
        // codice sopra un testo già escapato, invece di mostrare gli asterischi.
        const item = x => `<li><span class="cq-count" title="Ricorre in ${Number(x.count)} review">×${Number(x.count)}</span>`
          + `<span>${inlineMd(x.text)}</span></li>`;
        const top = d.top_divergences;
        document.getElementById('cq-divergences').innerHTML = top.length
          ? '<p class="cq-heading">Divergenze più frequenti</p><ul>' + top.slice(0, CQ_VISIBLE).map(item).join('') + '</ul>'
            + (top.length > CQ_VISIBLE ? `<details><summary>Mostra le altre ${top.length - CQ_VISIBLE}</summary><ul>`
              + top.slice(CQ_VISIBLE).map(item).join('') + '</ul></details>' : '')
          : '<p class="cq-heading">Nessuna divergenza registrata nelle review.</p>';
      } catch (e) {
        status.textContent = '❌ ' + e.message;
      }
    }
    loadCanvasQuality();

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      caricaStorico: () => caricaStorico(),
      loadCanvasQuality: () => loadCanvasQuality(),
    });
