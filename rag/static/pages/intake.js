/* Script della pagina intake.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
    /* Categorie docs/ ammesse da core.intake.CATEGORY_CLASSIFICATION (S2): whitelist
       fissa, non esposta da un endpoint dedicato (S4 non introduce nuove API). */
    const CATEGORIE = [
      ['00_meta_governance', '00 · Meta Governance'],
      ['01_architecture_norms', '01 · Architecture Norms'],
      ['02_specs_normative', '02 · Specs Normative'],
      ['03_changes_historical', '03 · Changes Historical'],
      ['04_knowledge_informative', '04 · Knowledge Informative'],
      ['05_project_specs', '05 · Project Specs'],
    ];

    function populateCategorySelect(select, defaultValue) {
      select.innerHTML = CATEGORIE.map(([value, label]) =>
        `<option value="${value}"${value === defaultValue ? ' selected' : ''}>${label}</option>`
      ).join('');
    }

    /* ──────────── Markdown → HTML minimale e sicuro ────────────
       Escapa TUTTO l'input prima di riconoscere qualunque costrutto: i tag prodotti
       sono solo quelli che questa funzione genera esplicitamente, mai markup annidato
       nel contenuto sorgente (niente XSS da un documento caricato/generato).
       escapeHtml vive in /static/shared.js (caricato in <head>): la copia locale era identica. */

    function inlineMd(text) {
      let t = escapeHtml(text);
      t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
      t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
      t = t.replace(/\*([^*]+)\*/g, '<em>$1</em>');
      t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
      return t;
    }

    function excelText(text) {
      // Excel (core/intake_excel.py): toglie solo gli escape del serializzatore (\X, &#N;, <br>)
      // in un unico passaggio, poi ri-escapa TUTTO: il markup della fonte resta testo.
      const decoded = String(text).replace(/\\([!-\/:-@\[-`{-~])|&#(\d+);|<br>/g, (m, punct, code) =>
        punct !== undefined ? punct
          : code !== undefined ? (Number(code) <= 0x10FFFF ? String.fromCodePoint(Number(code)) : m)
          : '\n');
      return escapeHtml(decoded).replace(/\n/g, '<br>');
    }

    function mdToHtml(md, excel = false) {
      const lines = String(md).replace(/\r\n/g, '\n').split('\n');
      const renderText = excel ? excelText : inlineMd;
      let html = '', inCode = false, codeBuf = [], inList = false, inTable = false;
      const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
      const closeTable = () => { if (inTable) { html += '</tbody></table>'; inTable = false; } };
      for (const raw of lines) {
        if (excel && raw.startsWith('|') && raw.endsWith('|')) {
          if (/^[| :\-]+$/.test(raw)) continue;
          // I pipe dei dati sono sempre `\|`: si divide solo sui delimitatori non escapati.
          const cells = raw.slice(1, -1).split(/(?<!\\)\|/).map(c => renderText(c.trim()));
          if (!inTable) {
            html += '<table><thead><tr>' + cells.map(c => `<th scope="col">${c}</th>`).join('') + '</tr></thead><tbody>';
            inTable = true;
          } else {
            html += '<tr>' + cells.map(c => `<td>${c}</td>`).join('') + '</tr>';
          }
          continue;
        }
        closeTable();
        if (raw.trim().startsWith('```')) {
          if (!inCode) { closeList(); inCode = true; codeBuf = []; }
          else { html += `<pre><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`; inCode = false; }
          continue;
        }
        if (inCode) { codeBuf.push(raw); continue; }
        let m = /^(#{1,6})\s+(.*)$/.exec(raw);
        if (m) { closeList(); const lvl = m[1].length; html += `<h${lvl}>${renderText(m[2])}</h${lvl}>`; continue; }
        if (/^\s*[-*]\s+/.test(raw)) {
          if (!inList) { html += '<ul>'; inList = true; }
          html += `<li>${renderText(raw.replace(/^\s*[-*]\s+/, ''))}</li>`;
          continue;
        }
        closeList();
        if (raw.trim() === '') continue;
        html += `<p>${renderText(raw)}</p>`;
      }
      closeList();
      closeTable();
      if (inCode) html += `<pre><code>${escapeHtml(codeBuf.join('\n'))}</code></pre>`;
      return html;
    }

    function formatDate(iso) {
      if (!iso) return '';
      try { return new Date(iso).toLocaleString('it-IT'); } catch (e) { return iso; }
    }

    /* ──────────── (a) GENERA CON OLLAMA ──────────── */
    async function startGeneration() {
      const descrizione = document.getElementById('gen-descrizione').value.trim();
      const nFile = parseInt(document.getElementById('gen-nfile').value, 10) || 1;
      const categoria = document.getElementById('gen-categoria').value;
      const btn = document.getElementById('gen-btn');
      const status = document.getElementById('gen-status');
      const result = document.getElementById('gen-result');
      result.innerHTML = '';

      if (!descrizione) { status.textContent = 'Descrivi prima lo sviluppo.'; status.className = 'status msg-err'; return; }

      btn.disabled = true;
      status.className = 'status';
      status.textContent = 'Avvio job di generazione…';

      let job;
      try {
        const res = await fetch('/api/intake/generate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ descrizione, n_file: nFile, categoria_suggerita: categoria }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { throw new Error(data.detail || `HTTP ${res.status}`); }
        job = data;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore: ${e.message}`; btn.disabled = false; return;
      }

      status.textContent = 'Generazione in corso (grounding + Ollama)…';
      while (job.status === 'pending' || job.status === 'running') {
        await new Promise(r => setTimeout(r, 1500));
        try {
          const res = await fetch(`/api/intake/generate/${job.job_id}`);
          const data = await res.json().catch(() => ({}));
          // 404: job scartato dal registro (retention) o server riavviato — mai "completata".
          if (res.ok) job = data;
          else if (res.status === 404) job = { status: 'failed', error: data.detail || 'job non più disponibile sul server' };
          /* altri errori HTTP: ritenta al prossimo giro */
        } catch (e) { /* rete instabile: ritenta al prossimo giro */ }
      }

      btn.disabled = false;
      if (job.status === 'failed') {
        status.className = 'status msg-err'; status.textContent = `Job fallito: ${job.error || 'errore sconosciuto'}`;
        return;
      }

      status.className = 'status msg-ok'; status.textContent = 'Generazione completata.';
      const r = job.result || {};
      const scartatiHtml = (r.scartati || []).map(s =>
        `<div class="msg-err">· documento #${s.indice}: ${escapeHtml(s.motivo)}</div>`).join('');
      const lat = r.latency || {};
      result.innerHTML = `
        <div class="file-row">
          <span class="badge badge-ok">${r.n_generati || 0} generati</span>
          <span class="badge ${r.n_scartati ? 'badge-err' : 'badge-ok'}">${r.n_scartati || 0} scartati</span>
          <span class="status">retrieval ${lat.retrieval_ms ?? '?'} ms · generazione ${lat.generation_ms ?? '?'} ms · totale ${lat.total_ms ?? '?'} ms</span>
        </div>
        ${scartatiHtml}`;
      refreshStaging();
    }

    /* ──────────── (b) IMPORTA DOCUMENTI ──────────── */
    const dropzone = document.getElementById('dropzone');
    ['dragover', 'dragenter'].forEach(evt => dropzone.addEventListener(evt, e => {
      e.preventDefault(); dropzone.classList.add('dragover');
    }));
    ['dragleave', 'drop'].forEach(evt => dropzone.addEventListener(evt, e => {
      e.preventDefault(); dropzone.classList.remove('dragover');
    }));
    dropzone.addEventListener('drop', e => {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
        onFilesPicked(e.dataTransfer.files);
      }
    });

    function onFilesPicked(fileList) {
      const files = Array.from(fileList || []);
      files.forEach(uploadOneFile);
      document.getElementById('file-input').value = '';
    }

    async function uploadOneFile(file) {
      const results = document.getElementById('import-results');
      const rowId = `import-row-${Math.random().toString(36).slice(2)}`;
      const row = document.createElement('div');
      row.className = 'file-row';
      row.id = rowId;
      row.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="status">caricamento e conversione in corso…</span>`;
      results.appendChild(row);

      const form = new FormData();
      form.append('file', file);
      try {
        const res = await fetch('/api/intake/docs', { method: 'POST', body: form });
        const data = await res.json().catch(() => ({}));
        const el = document.getElementById(rowId);
        if (res.ok) {
          const m = data.metadata || {};
          const avvisi = (m.avvisi || []).length;
          el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="badge badge-ok">in staging</span>`
            + `<span class="status">${escapeHtml(engineLabel(m))}</span>`
            + (avvisi ? `<span class="badge badge-err">⚠ ${avvisi} ${avvisi === 1 ? 'avviso' : 'avvisi'}: vedi anteprima</span>` : '');
          refreshStaging();
        } else {
          el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="msg-err">${escapeHtml(data.detail || `HTTP ${res.status}`)}</span>`;
        }
      } catch (e) {
        const el = document.getElementById(rowId);
        if (el) el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="msg-err">Errore di connessione: ${escapeHtml(e.message)}</span>`;
      }
    }

    /* Motore effettivo della conversione, dai metadata dello staging (core/intake_convert.py).
       Un fallback dopo un errore di Docling non si presenta mai come conversione Docling. */
    function engineLabel(m) {
      const v = m.versione_motore ? ` ${m.versione_motore}` : '';
      const n = m.normalizzazione;
      const prima = n ? `${String(n.da).toUpperCase()} portato a ${String(n.a).toUpperCase()} da ${n.versione || 'LibreOffice'}, poi ` : '';
      if (m.motore === 'nativo') return 'Markdown nativo, nessuna conversione';
      if (m.motore === 'markitdown' && m.fallback) return `${prima}MarkItDown${v} come ripiego: Docling non ha convertito il file`;
      if (m.motore === 'openpyxl' || m.motore === 'xlrd') return `celle lette direttamente dall'originale con ${m.motore}${v}`;
      if (m.motore === 'docling') return `${prima}convertito con Docling${v}`;
      if (m.motore === 'markitdown') return `${prima}convertito con MarkItDown${v}`;
      return 'motore non registrato';
    }

    function conversionInfoHtml(data) {
      const m = data.metadata || {};
      const righe = [`<p><strong>Conversione:</strong> ${escapeHtml(engineLabel(m))}.</p>`];
      righe.push(`<p>Originale <code>${escapeHtml(m.source_filename || data.filename || '')}</code>`
        + (m.sha256 ? ` · SHA-256 <code title="${escapeHtml(m.sha256)}">${escapeHtml(m.sha256.slice(0, 12))}…</code>` : '')
        + ` · conservato in staging, non viene pubblicato.</p>`);
      if (m.normalizzazione) {
        const n = m.normalizzazione;
        righe.push(`<p>Normalizzazione: ${escapeHtml(String(n.da).toUpperCase())} → ${escapeHtml(String(n.a).toUpperCase())} `
          + `con ${escapeHtml(n.versione || 'LibreOffice')} (in locale, profilo temporaneo, macro e collegamenti esterni disattivati).</p>`);
      }
      if (m.pdf) {
        righe.push(`<p>PDF: ${m.pdf.pagine} ${m.pdf.pagine === 1 ? 'pagina' : 'pagine'}, `
          + `${m.pdf.pagine_senza_testo} senza testo selezionabile · OCR locale: ${m.pdf.ocr ? 'sì' : 'no'}.</p>`);
      }
      if (m.fallback) {
        righe.push(`<p class="msg-err">⚠ Motivo del ripiego: ${escapeHtml(m.fallback.motivo || '')}</p>`);
      }
      const avvisi = m.avvisi || [];
      if (avvisi.length) {
        righe.push(`<ul aria-label="Avvisi della conversione">${avvisi.map(a => `<li class="msg-err">⚠ ${escapeHtml(a)}</li>`).join('')}</ul>`);
      }
      if (data.approve_error) {
        righe.push(`<p class="msg-err">Ultimo tentativo di approvazione non riuscito (${escapeHtml(formatDate(data.approve_error.at))}): `
          + `${escapeHtml(data.approve_error.errore || '')}. Nulla è stato pubblicato; puoi riprovare.</p>`);
      }
      return `<div class="conv-info">${righe.join('')}</div>`;
    }

    /* ──────────── (c) IN STAGING ──────────── */
    function suggestFilename(sourceFilename) {
      const stem = String(sourceFilename || 'documento').replace(/\.[^.]+$/, '');
      let slug = stem.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      if (!slug || !/^[a-z0-9]/.test(slug)) slug = 'd' + slug;
      return `${slug}.md`;
    }

    async function refreshStaging() {
      const status = document.getElementById('staging-status');
      const list = document.getElementById('staging-list');
      status.textContent = 'Caricamento…'; status.className = 'status';
      try {
        const res = await fetch('/api/intake/staged');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const staged = data.staged || [];
        if (!staged.length) {
          list.innerHTML = '<div class="empty-state">Niente in staging.</div>';
        } else {
          list.innerHTML = staged.map(entry => `
            <div class="staged-item">
              <span class="badge badge-${['generated', 'brief'].includes(entry.source) ? entry.source : 'imported'}">${entry.source}</span>
              <span class="name">${escapeHtml(entry.filename || entry.id)}</span>
              <span class="status">${escapeHtml(engineLabel(entry.metadata || {}))} · ${formatDate(entry.staged_at)}</span>
              <button data-click="openPreview" data-arg="${escapeHtml(entry.id)}" class="btn btn-secondary">🔎 Anteprima</button>
            </div>`).join('');
        }
        status.textContent = `${staged.length} documento/i in staging`;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore nel caricamento: ${e.message}`;
      }
    }

    async function openPreview(id) {
      const detail = document.getElementById('staging-detail');
      detail.style.display = 'block';
      detail.innerHTML = '<p class="status">Caricamento anteprima…</p>';
      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      try {
        const res = await fetch(`/api/intake/staged/${id}/preview`);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        const suggested = suggestFilename(data.filename);
        const raffinato = !!(data.files || {}).markdown_raw;
        detail.innerHTML = `
          <h3>${escapeHtml(data.filename || id)}${raffinato ? ' <span class="badge badge-generated">raffinato</span>' : ''}</h3>
          ${conversionInfoHtml(data)}
          <div class="md-preview">${mdToHtml(data.markdown || '', ['openpyxl', 'xlrd'].includes(data.metadata?.motore) && !raffinato)}</div>
          <p class="status">Approvando, in <code>docs/&lt;categoria&gt;/</code> viene scritto solo il file <code>.md</code> mostrato qui, con il frontmatter di governance.</p>
          <div class="review-controls">
            <button data-click="refineStaged" data-arg="${escapeHtml(id)}" class="btn btn-secondary" title="Riscrive il dump del convertitore come spec strutturata (sezioni, tabelle, blocchi di codice). Riesegubile: riparte sempre dal markdown grezzo.">✨ ${raffinato ? 'Raffina di nuovo' : 'Raffina con LLM'}</button>
          </div>
          <div class="review-controls">
            <label class="field">Categoria docs/
              <select id="preview-categoria"></select>
            </label>
            <label class="field">Nome file
              <input id="preview-nomefile" type="text" value="${escapeHtml(suggested)}" />
            </label>
            <button data-click="approveStaged" data-arg="${escapeHtml(id)}" class="btn btn-primary">✅ Approva</button>
            <label class="field">Motivo (rifiuto)
              <input id="preview-motivo" type="text" placeholder="opzionale" />
            </label>
            <button data-click="rejectStaged" data-arg="${escapeHtml(id)}" class="btn btn-danger">🚫 Rifiuta</button>
          </div>
          <div id="preview-result" role="status" aria-live="polite"></div>`;
        populateCategorySelect(document.getElementById('preview-categoria'), '04_knowledge_informative');
      } catch (e) {
        detail.innerHTML = `<p class="msg-err">Errore nell'anteprima: ${escapeHtml(e.message)}</p>`;
      }
    }

    function closePreview() {
      const detail = document.getElementById('staging-detail');
      detail.style.display = 'none';
      detail.innerHTML = '';
    }

    /* Approva e Rifiuta non disabilitavano nulla durante la chiamata: un doppio
       click su Approva produceva due scritture in docs/ e due reindex. La
       guardia vale per entrambi i bottoni della coppia, così un rifiuto non
       parte mentre un'approvazione è in volo. */
    let reviewInFlight = false;
    function setReviewBusy(busy, btn) {
      reviewInFlight = busy;
      document.querySelectorAll('#staging-detail .review-controls button')
        .forEach(b => { b.disabled = busy; });
      if (btn) btn.setAttribute('aria-busy', String(busy));
    }

    async function approveStaged(id) {
      if (reviewInFlight) return;
      const categoria = document.getElementById('preview-categoria').value;
      const nomeFile = document.getElementById('preview-nomefile').value.trim();
      const out = document.getElementById('preview-result');
      setReviewBusy(true);
      out.className = 'status'; out.textContent = 'Approvazione in corso…';
      try {
        const res = await fetch(`/api/intake/staged/${id}/approve`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ categoria, nome_file: nomeFile }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        const reindex = data.reindex || {};
        out.className = 'msg-ok';
        out.textContent = `Approvato → docs/${categoria}/${nomeFile} — reindex: ${JSON.stringify(reindex)}`;
        refreshStaging();
        setTimeout(closePreview, 1500);
      } catch (e) {
        out.className = 'msg-err'; out.textContent = `Errore: ${e.message}`;
      } finally {
        setReviewBusy(false);
      }
    }

    /* Raffinazione LLM: job async (decine di chiamate al modello su un documento lungo),
       si interroga lo stato come per la generazione. A fine job si riapre l'anteprima, che
       ora mostra il markdown raffinato — il grezzo resta comunque in staging. */
    async function refineStaged(id) {
      const out = document.getElementById('preview-result');
      out.className = 'status'; out.textContent = 'Raffinazione avviata: può richiedere alcuni minuti…';
      try {
        const res = await fetch(`/api/intake/staged/${id}/refine`, { method: 'POST' });
        const job = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(job.detail || `HTTP ${res.status}`);

        while (true) {
          await new Promise(r => setTimeout(r, 3000));
          const poll = await fetch(`/api/intake/refine/${job.job_id}`);
          const stato = await poll.json().catch(() => ({}));
          if (!poll.ok) throw new Error(stato.detail || `HTTP ${poll.status}`);
          if (stato.status === 'failed') throw new Error(stato.error || 'raffinazione fallita');
          if (stato.status === 'done') {
            const s = (stato.result || {}).refine || {};
            out.className = 'msg-ok';
            const motivi = [];
            if (s.windows_too_short) motivi.push(`${s.windows_too_short} riassunte`);
            if (s.windows_too_long) motivi.push(`${s.windows_too_long} gonfiate di commenti`);
            out.textContent = `Raffinato in ${s.elapsed_seconds ?? '?'}s — ${s.windows ?? '?'} finestre`
              + (motivi.length ? ` (${s.windows_kept_raw} tenute grezze: ${motivi.join(', ')})` : '');
            setTimeout(() => openPreview(id), 1200);
            return;
          }
          out.textContent = 'Raffinazione in corso…';
        }
      } catch (e) {
        out.className = 'msg-err'; out.textContent = `Errore: ${e.message}`;
      }
    }

    async function rejectStaged(id) {
      if (reviewInFlight) return;
      const motivo = document.getElementById('preview-motivo').value.trim();
      const out = document.getElementById('preview-result');
      setReviewBusy(true);
      out.className = 'status'; out.textContent = 'Rifiuto in corso…';
      try {
        const res = await fetch(`/api/intake/staged/${id}/reject`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ motivo }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        out.className = 'msg-ok'; out.textContent = 'Documento rifiutato.';
        refreshStaging();
        setTimeout(closePreview, 1000);
      } catch (e) {
        out.className = 'msg-err'; out.textContent = `Errore: ${e.message}`;
      } finally {
        setReviewBusy(false);
      }
    }

    /* ──────────── (d) IMPORTA PROGETTO DA PATH ────────────
       Applica attivo SOLO dopo un'anteprima riuscita; qualunque modifica a path o
       target invalida il piano corrente (la semantica anti-stale vera vive nel
       backend: fingerprint del target nel plan, ricontrollato all'apply). */
    let currentProjectPlanId = null;

    function invalidateProjectPlan() {
      currentProjectPlanId = null;
      document.getElementById('prj-apply-btn').disabled = true;
      document.getElementById('prj-plan-result').innerHTML = '';
      document.getElementById('prj-apply-result').innerHTML = '';
    }

    function renderPathList(title, paths, cssClass) {
      if (!paths || !paths.length) return '';
      const items = paths.map(p => `<li><code>${escapeHtml(p)}</code></li>`).join('');
      return `<details style="margin-top:8px"><summary class="${cssClass}" style="cursor:pointer">
        ${escapeHtml(title)} (${paths.length})</summary>
        <ul style="margin:6px 0 0;padding-left:20px;font-size:var(--text-size-sm)">${items}</ul></details>`;
    }

    async function browseProjectPath() {
      const status = document.getElementById('prj-status');
      const btn = document.getElementById('prj-browse-btn');
      btn.disabled = true;
      status.className = 'status'; status.textContent = 'Apertura esplora risorse…';
      try {
        const res = await fetch('/api/intake/project/browse-path', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        if (data.path) {
          document.getElementById('prj-path').value = data.path;
          invalidateProjectPlan();
          status.className = 'status'; status.textContent = '';
        } else {
          status.className = 'status'; status.textContent = 'Selezione annullata.';
        }
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore: ${e.message}`;
      } finally {
        btn.disabled = false;
      }
    }

    async function planProjectImport() {
      const path = document.getElementById('prj-path').value.trim();
      const target = document.getElementById('prj-target').value;
      const status = document.getElementById('prj-status');
      const result = document.getElementById('prj-plan-result');
      invalidateProjectPlan();

      if (!path) { status.className = 'status msg-err'; status.textContent = 'Indica il path del progetto.'; return; }
      status.className = 'status'; status.textContent = 'Anteprima in corso…';
      try {
        const res = await fetch('/api/intake/project/plan', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, target }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        currentProjectPlanId = data.plan_id;
        const t = data.totali || {};
        status.className = 'status msg-ok';
        status.textContent = `Anteprima pronta (modalità ${data.mode}).`;
        result.innerHTML = `
          <div class="file-row">
            <span class="badge badge-ok">${t.nuovi ?? 0} nuovi</span>
            <span class="badge badge-imported">${t.identici ?? 0} identici</span>
            <span class="badge ${t.conflitti ? 'badge-err' : 'badge-ok'}">${t.conflitti ?? 0} conflitti</span>
            <span class="badge badge-generated">${t.esclusi ?? 0} esclusi</span>
            <span class="status">modalità: ${escapeHtml(data.mode)}</span>
          </div>
          ${t.conflitti ? '<div class="msg-err" style="margin-top:6px">I conflitti non verranno MAI applicati: i file esistenti restano intatti.</div>' : ''}
          ${renderPathList('Conflitti', data.conflitti, 'msg-err')}
          ${renderPathList('Nuovi', data.nuovi, 'msg-ok')}
          ${renderPathList('Esclusi', data.esclusi, 'status')}`;
        document.getElementById('prj-apply-btn').disabled = false;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore: ${e.message}`;
      }
    }

    async function applyProjectImport() {
      if (!currentProjectPlanId) return;
      const status = document.getElementById('prj-status');
      const out = document.getElementById('prj-apply-result');
      const btn = document.getElementById('prj-apply-btn');
      btn.disabled = true;
      status.className = 'status'; status.textContent = 'Applicazione in corso (backup + copia + reindex)…';
      try {
        const res = await fetch('/api/intake/project/apply', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan_id: currentProjectPlanId }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);

        currentProjectPlanId = null;  // un piano applicato non è riutilizzabile
        status.className = 'status msg-ok'; status.textContent = 'Import applicato.';
        // Il progetto appena importato entra nell'elenco e viene preselezionato.
        refreshProjectImports();
        document.getElementById('prj-brief-status').textContent =
          `Genera il project brief del progetto importato in code/${data.target}/ (entra in staging, poi review).`;
        const t = data.totali || {};
        const reindexTxt = data.reindex ? JSON.stringify({
          reindexed_docs: data.reindex.reindexed_docs, upserted_chunks: data.reindex.upserted_chunks,
          version: data.reindex.version,
        }) : (data.reindex_error ? `fallito: ${data.reindex_error}` : 'nessun file copiato');
        out.innerHTML = `
          <div class="file-row">
            <span class="badge badge-ok">${t.copiati ?? 0} copiati</span>
            <span class="status">backup: ${data.backup ? `<code>${escapeHtml(data.backup)}</code>` : 'nessuno (cartella vuota)'}</span>
          </div>
          <div class="status" style="margin-top:6px">reindex: ${escapeHtml(reindexTxt)}</div>
          ${data.avviso ? `<div class="msg-err" style="margin-top:6px">⚠ ${escapeHtml(data.avviso)}</div>` : ''}`;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore: ${e.message}`;
      }
    }

    /* ──────────── (d-bis) PROJECT BRIEF ────────────
       Il brief è di un PROGETTO (una cartella sotto code/<target>/), non di un target:
       l'import è additivo, quindi in code/backend/ possono convivere più progetti e un
       brief "del backend" descriverebbe quello che capita per primo fra i simboli.
       L'elenco dei progetti viene dal journal degli import, che vive su disco e
       sopravvive al reload: legare il brief a una variabile di pagina lo rendeva
       irripetibile dopo un errore (bastava ricaricare per perdere il pulsante, e
       l'unico modo di riaverlo era rifare l'import). Il backend riverifica comunque il
       journal e risponde 409 se per quel target/progetto non c'è un import applicato.
       Job async col pattern della generazione: 202 + polling, esito con documento
       staged / scartati / avviso. */
    async function refreshProjectImports() {
      const target = document.getElementById('prj-target').value;
      const select = document.getElementById('prj-brief-progetto');
      let imports = [];
      try {
        const res = await fetch(`/api/intake/project/imports?target=${encodeURIComponent(target)}`);
        if (res.ok) imports = (await res.json()).imports || [];
      } catch (e) { /* elenco non disponibile: resta il placeholder */ }
      if (!imports.length) {
        select.innerHTML = `<option value="">(nessun import in code/${escapeHtml(target)}/)</option>`;
        return;
      }
      // Il più recente per ultimo nell'API: qui va in cima e preselezionato, perché è
      // quasi sempre quello che l'utente ha appena importato.
      const ordinati = imports.slice().reverse();
      select.innerHTML = ordinati.map((imp, i) =>
        `<option value="${escapeHtml(imp.progetto)}"${i === 0 ? ' selected' : ''}>${escapeHtml(imp.progetto)}</option>`
      ).join('');
    }

    async function startProjectBrief() {
      const target = document.getElementById('prj-target').value;
      const progetto = document.getElementById('prj-brief-progetto').value;
      const btn = document.getElementById('prj-brief-btn');
      const status = document.getElementById('prj-brief-status');
      const out = document.getElementById('prj-brief-result');
      out.innerHTML = '';
      btn.disabled = true;
      status.className = 'status';
      status.textContent = `Avvio brief per code/${target}/${progetto || '(ultimo import)'}…`;

      let job;
      try {
        const res = await fetch('/api/intake/project/brief', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, progetto: progetto || null }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { throw new Error(data.detail || `HTTP ${res.status}`); }
        job = data;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = `Errore: ${e.message}`;
        btn.disabled = false; return;
      }

      status.textContent = 'Brief in corso (grounding sul grafo + Ollama)…';
      while (job.status === 'pending' || job.status === 'running') {
        await new Promise(r => setTimeout(r, 1500));
        try {
          const res = await fetch(`/api/intake/project/brief/${job.job_id}`);
          const data = await res.json().catch(() => ({}));
          // 404: job scartato dal registro (retention) o server riavviato — mai "completata".
          if (res.ok) job = data;
          else if (res.status === 404) job = { status: 'failed', error: data.detail || 'job non più disponibile sul server' };
          /* altri errori HTTP: ritenta al prossimo giro */
        } catch (e) { /* rete instabile: ritenta al prossimo giro */ }
      }

      btn.disabled = false;
      if (job.status === 'failed') {
        status.className = 'status msg-err';
        status.textContent = `Job brief fallito: ${job.error || 'errore sconosciuto'}`;
        return;
      }

      const r = job.result || {};
      status.className = 'status msg-ok';
      status.textContent = `Brief completato per code/${target}/${r.progetto || progetto}.`;
      const lat = r.latency || {};
      const scartatiHtml = (r.scartati || []).map(s =>
        `<div class="msg-err">· scartato: ${escapeHtml(s.motivo)}</div>`).join('');
      out.innerHTML = `
        <div class="file-row">
          <span class="badge badge-ok">${r.n_generati || 0} in staging</span>
          <span class="badge ${r.n_scartati ? 'badge-err' : 'badge-ok'}">${r.n_scartati || 0} scartati</span>
          <span class="status">generazione ${lat.generation_ms ?? '?'} ms · totale ${lat.total_ms ?? '?'} ms</span>
        </div>
        ${r.avviso ? `<div class="msg-err" style="margin-top:6px">⚠ ${escapeHtml(r.avviso)}</div>` : ''}
        ${scartatiHtml}`;
      if (r.n_generati) refreshStaging();
    }

    /* ──────────── Bootstrap ──────────── */
    populateCategorySelect(document.getElementById('gen-categoria'), '04_knowledge_informative');
    refreshStaging();
    refreshProjectImports();

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      applyProjectImport: () => applyProjectImport(),
      approveStaged: el => approveStaged(el.dataset.arg),
      browseProjectPath: () => browseProjectPath(),
      invalidateProjectPlan: () => invalidateProjectPlan(),
      onFilesPicked: el => onFilesPicked(el.files),
      openPreview: el => openPreview(el.dataset.arg),
      pickFiles: () => document.getElementById('file-input').click(),
      planProjectImport: () => planProjectImport(),
      projectCategoryChanged: () => { invalidateProjectPlan(); refreshProjectImports(); },
      refineStaged: el => refineStaged(el.dataset.arg),
      refreshStaging: () => refreshStaging(),
      rejectStaged: el => rejectStaged(el.dataset.arg),
      startGeneration: () => startGeneration(),
      startProjectBrief: () => startProjectBrief(),
    });
