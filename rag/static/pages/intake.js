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

    /* Markdown → HTML: mdToHtml / excelText vivono in /static/shared.js (R7). */

    function formatDate(iso) {
      if (!iso) return '';
      try {
        const loc = (typeof currentLang === 'function' && currentLang() === 'en') ? 'en-GB' : 'it-IT';
        return new Date(iso).toLocaleString(loc);
      } catch (e) { return iso; }
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

      if (!descrizione) { status.textContent = t('intake.gen.errNeedDesc'); status.className = 'status msg-err'; return; }

      btn.disabled = true;
      status.className = 'status';
      status.textContent = t('intake.gen.statusStarting');

      let job;
      try {
        const res = await fetch('/api/intake/generate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ descrizione, n_file: nFile, categoria_suggerita: categoria }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`)); }
        job = data;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.err.prefix', { msg: e.message }); btn.disabled = false; return;
      }

      status.textContent = t('intake.gen.statusRunning');
      while (job.status === 'pending' || job.status === 'running') {
        await new Promise(r => setTimeout(r, 1500));
        try {
          const res = await fetch(`/api/intake/generate/${job.job_id}`);
          const data = await res.json().catch(() => ({}));
          // 404: job scartato dal registro (retention) o server riavviato — mai "completata".
          if (res.ok) job = data;
          else if (res.status === 404) job = { status: 'failed', error: apiErrorMessage(data.detail, t('intake.err.jobGone')) };
          /* altri errori HTTP: ritenta al prossimo giro */
        } catch (e) { /* rete instabile: ritenta al prossimo giro */ }
      }

      btn.disabled = false;
      if (job.status === 'failed') {
        status.className = 'status msg-err'; status.textContent = t('intake.gen.jobFailed', { err: job.error || t('intake.err.unknown') });
        return;
      }

      status.className = 'status msg-ok'; status.textContent = t('intake.gen.statusDone');
      const r = job.result || {};
      const scartatiHtml = (r.scartati || []).map(s =>
        `<div class="msg-err">· ${t('intake.gen.docDiscarded', { n: s.indice, reason: escapeHtml(s.motivo) })}</div>`).join('');
      const lat = r.latency || {};
      result.innerHTML = `
        <div class="file-row">
          <span class="badge badge-ok">${t('intake.gen.badgeGenerated', { n: r.n_generati || 0 })}</span>
          <span class="badge ${r.n_scartati ? 'badge-err' : 'badge-ok'}">${t('intake.gen.badgeDiscarded', { n: r.n_scartati || 0 })}</span>
          <span class="status">${t('intake.gen.latency', { retrieval: lat.retrieval_ms ?? '?', generation: lat.generation_ms ?? '?', total: lat.total_ms ?? '?' })}</span>
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
      row.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="status">${t('intake.import.uploading')}</span>`;
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
          el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="badge badge-ok">${t('intake.import.inStaging')}</span>`
            + `<span class="status">${escapeHtml(engineLabel(m))}</span>`
            + (avvisi ? `<span class="badge badge-err">⚠ ${t(avvisi === 1 ? 'intake.import.warningOne' : 'intake.import.warningMany', { n: avvisi })}</span>` : '');
          refreshStaging();
        } else {
          el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="msg-err">${escapeHtml(apiErrorMessage(data.detail, `HTTP ${res.status}`))}</span>`;
        }
      } catch (e) {
        const el = document.getElementById(rowId);
        if (el) el.innerHTML = `<span class="name">${escapeHtml(file.name)}</span><span class="msg-err">${escapeHtml(t('intake.import.connError', { msg: e.message }))}</span>`;
      }
    }

    /* Motore effettivo della conversione, dai metadata dello staging (core/intake_convert.py).
       Un fallback dopo un errore di Docling non si presenta mai come conversione Docling. */
    function engineLabel(m) {
      const v = m.versione_motore ? ` ${m.versione_motore}` : '';
      const n = m.normalizzazione;
      const prima = n ? t('intake.engine.normalizedPrefix', {
        from: String(n.da).toUpperCase(), to: String(n.a).toUpperCase(), ver: n.versione || 'LibreOffice',
      }) : '';
      if (m.motore === 'nativo') return t('intake.engine.native');
      if (m.motore === 'markitdown' && m.fallback) return t('intake.engine.markitdownFallback', { prefix: prima, ver: v });
      if (m.motore === 'openpyxl' || m.motore === 'xlrd') return t('intake.engine.excel', { engine: m.motore, ver: v });
      if (m.motore === 'docling') return t('intake.engine.docling', { prefix: prima, ver: v });
      if (m.motore === 'markitdown') return t('intake.engine.markitdown', { prefix: prima, ver: v });
      return t('intake.engine.unknown');
    }

    function conversionInfoHtml(data) {
      const m = data.metadata || {};
      const righe = [`<p><strong>${t('intake.conv.label')}</strong> ${escapeHtml(engineLabel(m))}.</p>`];
      righe.push(`<p>${t('intake.conv.original', { name: escapeHtml(m.source_filename || data.filename || '') })}`
        + (m.sha256 ? ` · SHA-256 <code title="${escapeHtml(m.sha256)}">${escapeHtml(m.sha256.slice(0, 12))}…</code>` : '')
        + ` · ${t('intake.conv.keptInStaging')}</p>`);
      if (m.normalizzazione) {
        const n = m.normalizzazione;
        righe.push(`<p>${t('intake.conv.normalization', {
          from: escapeHtml(String(n.da).toUpperCase()),
          to: escapeHtml(String(n.a).toUpperCase()),
          ver: escapeHtml(n.versione || 'LibreOffice'),
        })}</p>`);
      }
      if (m.pdf) {
        righe.push(`<p>${t('intake.conv.pdf', {
          pages: m.pdf.pagine,
          pagesWord: m.pdf.pagine === 1 ? t('intake.conv.pageOne') : t('intake.conv.pageMany'),
          noText: m.pdf.pagine_senza_testo,
          ocr: m.pdf.ocr ? t('intake.yes') : t('intake.no'),
        })}</p>`);
      }
      if (m.fallback) {
        righe.push(`<p class="msg-err">⚠ ${t('intake.conv.fallbackReason', { reason: escapeHtml(m.fallback.motivo || '') })}</p>`);
      }
      const avvisi = m.avvisi || [];
      if (avvisi.length) {
        righe.push(`<ul aria-label="${t('intake.conv.warningsAria')}">${avvisi.map(a => `<li class="msg-err">⚠ ${escapeHtml(a)}</li>`).join('')}</ul>`);
      }
      if (data.approve_error) {
        righe.push(`<p class="msg-err">${t('intake.conv.approveError', {
          when: escapeHtml(formatDate(data.approve_error.at)),
          err: escapeHtml(data.approve_error.errore || ''),
        })}</p>`);
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
      status.textContent = t('intake.staging.loading'); status.className = 'status';
      try {
        const res = await fetch('/api/intake/staged');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const staged = data.staged || [];
        if (!staged.length) {
          list.innerHTML = `<div class="empty-state">${t('intake.staging.empty')}</div>`;
        } else {
          list.innerHTML = staged.map(entry => `
            <div class="staged-item">
              <span class="badge badge-${['generated', 'brief'].includes(entry.source) ? entry.source : 'imported'}">${entry.source}</span>
              <span class="name">${escapeHtml(entry.filename || entry.id)}</span>
              <span class="status">${escapeHtml(engineLabel(entry.metadata || {}))} · ${formatDate(entry.staged_at)}</span>
              <button type="button" data-click="openPreview" data-arg="${escapeHtml(entry.id)}" class="btn btn-secondary">${t('intake.staging.previewBtn')}</button>
            </div>`).join('');
        }
        status.textContent = t('intake.staging.count', { n: staged.length });
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.staging.loadError', { msg: e.message });
      }
    }

    let _previewId = null;
    async function openPreview(id) {
      _previewId = id;
      const detail = document.getElementById('staging-detail');
      detail.style.display = 'block';
      detail.innerHTML = `<p class="status">${t('intake.staging.previewLoading')}</p>`;
      detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      try {
        const res = await fetch(`/api/intake/staged/${encodeURIComponent(id)}/preview`);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));

        const suggested = suggestFilename(data.filename);
        const raffinato = !!(data.files || {}).markdown_raw;
        detail.innerHTML = `
          <h3>${escapeHtml(data.filename || id)}${raffinato ? ` <span class="badge badge-generated">${t('intake.staging.refined')}</span>` : ''}</h3>
          ${conversionInfoHtml(data)}
          <div class="md-preview prose-text">${mdToHtml(data.markdown || '', ['openpyxl', 'xlrd'].includes(data.metadata?.motore) && !raffinato)}</div>
          <p class="status">${t('intake.staging.approveHint')}</p>
          <div class="review-controls">
            <button type="button" data-click="refineStaged" data-arg="${escapeHtml(id)}" class="btn btn-secondary" title="${t('intake.staging.refineTitle')}">✨ ${raffinato ? t('intake.staging.refineAgain') : t('intake.staging.refineLlm')}</button>
          </div>
          <div class="review-controls">
            <label class="field">${t('intake.staging.categoriaLabel')}
              <select id="preview-categoria"></select>
            </label>
            <label class="field">${t('intake.staging.filenameLabel')}
              <input id="preview-nomefile" type="text" value="${escapeHtml(suggested)}" />
            </label>
            <button type="button" data-click="approveStaged" data-arg="${escapeHtml(id)}" class="btn btn-primary">${t('intake.staging.approveBtn')}</button>
            <label class="field">${t('intake.staging.rejectReasonLabel')}
              <input id="preview-motivo" type="text" placeholder="${t('intake.staging.rejectReasonPh')}" />
            </label>
            <button type="button" data-click="rejectStaged" data-arg="${escapeHtml(id)}" class="btn btn-danger">${t('intake.staging.rejectBtn')}</button>
          </div>
          <div id="preview-result" role="status" aria-live="polite"></div>`;
        populateCategorySelect(document.getElementById('preview-categoria'), '04_knowledge_informative');
      } catch (e) {
        detail.innerHTML = `<p class="msg-err">${t('intake.staging.previewError', { msg: escapeHtml(e.message) })}</p>`;
      }
    }

    function closePreview() {
      _previewId = null;
      const detail = document.getElementById('staging-detail');
      detail.style.display = 'none';
      detail.innerHTML = '';
    }

    /* Approva e Rifiuta non disabilitavano nulla durante la chiamata: un doppio
       click su Approva produceva due richieste di scrittura in docs/. La
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
      out.className = 'status'; out.textContent = t('intake.staging.approving');
      try {
        const res = await fetch(`/api/intake/staged/${encodeURIComponent(id)}/approve`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ categoria, nome_file: nomeFile }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));
        out.className = 'msg-ok';
        out.textContent = t('intake.staging.approved', { categoria, nomeFile });
        window.parent.refreshIndexStatus?.(selectedProjectId());
        refreshStaging();
        setTimeout(closePreview, 1500);
      } catch (e) {
        out.className = 'msg-err'; out.textContent = t('intake.err.prefix', { msg: e.message });
      } finally {
        setReviewBusy(false);
      }
    }

    /* Raffinazione LLM: job async (decine di chiamate al modello su un documento lungo),
       si interroga lo stato come per la generazione. A fine job si riapre l'anteprima, che
       ora mostra il markdown raffinato — il grezzo resta comunque in staging. */
    async function refineStaged(id) {
      const out = document.getElementById('preview-result');
      out.className = 'status'; out.textContent = t('intake.staging.refineStarted');
      try {
        const res = await fetch(`/api/intake/staged/${encodeURIComponent(id)}/refine`, { method: 'POST' });
        const job = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(job.detail, `HTTP ${res.status}`));

        while (true) {
          await new Promise(r => setTimeout(r, 3000));
          const poll = await fetch(`/api/intake/refine/${job.job_id}`);
          const stato = await poll.json().catch(() => ({}));
          if (!poll.ok) throw new Error(apiErrorMessage(stato.detail, `HTTP ${poll.status}`));
          if (stato.status === 'failed') throw new Error(stato.error || t('intake.staging.refineFailed'));
          if (stato.status === 'done') {
            const s = (stato.result || {}).refine || {};
            out.className = 'msg-ok';
            const motivi = [];
            if (s.windows_too_short) motivi.push(t('intake.staging.windowsShort', { n: s.windows_too_short }));
            if (s.windows_too_long) motivi.push(t('intake.staging.windowsLong', { n: s.windows_too_long }));
            out.textContent = t('intake.staging.refineDone', {
              secs: s.elapsed_seconds ?? '?',
              windows: s.windows ?? '?',
              extra: motivi.length ? t('intake.staging.refineExtra', { kept: s.windows_kept_raw, reasons: motivi.join(', ') }) : '',
            });
            setTimeout(() => openPreview(id), 1200);
            return;
          }
          out.textContent = t('intake.staging.refineRunning');
        }
      } catch (e) {
        out.className = 'msg-err'; out.textContent = t('intake.err.prefix', { msg: e.message });
      }
    }

    async function rejectStaged(id) {
      if (reviewInFlight) return;
      const motivo = document.getElementById('preview-motivo').value.trim();
      const out = document.getElementById('preview-result');
      setReviewBusy(true);
      out.className = 'status'; out.textContent = t('intake.staging.rejecting');
      try {
        const res = await fetch(`/api/intake/staged/${encodeURIComponent(id)}/reject`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ motivo }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));
        out.className = 'msg-ok'; out.textContent = t('intake.staging.rejected');
        refreshStaging();
        setTimeout(closePreview, 1000);
      } catch (e) {
        out.className = 'msg-err'; out.textContent = t('intake.err.prefix', { msg: e.message });
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
      status.className = 'status'; status.textContent = t('intake.project.browsing');
      try {
        const res = await fetch('/api/intake/project/browse-path', { method: 'POST' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));
        if (data.path) {
          document.getElementById('prj-path').value = data.path;
          invalidateProjectPlan();
          status.className = 'status'; status.textContent = '';
        } else {
          status.className = 'status'; status.textContent = t('intake.project.browseCancelled');
        }
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.err.prefix', { msg: e.message });
      } finally {
        btn.disabled = false;
      }
    }

    /* Target dell'import = sottocartelle di code/ del progetto, dallo stesso endpoint
       della tendina "Tipo di sviluppo" della Pipeline. Prima erano backend/frontend/
       logicAgent scritti qui: un progetto nuovo, o con ambiti diversi, non poteva importare. */
    async function loadImportTargets(selected) {
      const select = document.getElementById('prj-target');
      const keep = selected ?? select.value;
      let targets = [];
      try {
        const res = await fetch('/api/pipeline/dev-types');
        if (res.ok) targets = (await res.json()).dev_types || [];
      } catch (e) { /* elenco non disponibile: resta il messaggio sotto */ }
      select.innerHTML = targets.length
        ? targets.map(tv => `<option value="${escapeHtml(tv)}">${escapeHtml(tv)}</option>`).join('')
        : `<option value="">${t('intake.project.noTargets')}</option>`;
      if (targets.includes(keep)) select.value = keep;
      select.disabled = !targets.length;
    }

    async function addImportTarget() {
      const input = document.getElementById('prj-new-target');
      const btn = document.getElementById('prj-new-target-btn');
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      btn.disabled = true;
      try {
        const res = await fetch('/api/pipeline/dev-types', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));
        input.value = '';
        await loadImportTargets(data.dev_type);
        invalidateProjectPlan();
        await refreshProjectImports();
        toast(t('intake.project.targetAdded', { name: data.dev_type }), 'success');
      } catch (e) {
        toast(t('intake.project.targetAddError', { msg: e.message }), 'error');
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

      if (!path) { status.className = 'status msg-err'; status.textContent = t('intake.project.errNeedPath'); return; }
      if (!target) { status.className = 'status msg-err'; status.textContent = t('intake.project.errNeedTarget'); return; }
      status.className = 'status'; status.textContent = t('intake.project.planning');
      try {
        const res = await fetch('/api/intake/project/plan', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path, target }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));

        currentProjectPlanId = data.plan_id;
        const tot = data.totali || {};
        status.className = 'status msg-ok';
        status.textContent = t('intake.project.planReady', { mode: data.mode });
        result.innerHTML = `
          <div class="file-row">
            <span class="badge badge-ok">${t('intake.project.badgeNew', { n: tot.nuovi ?? 0 })}</span>
            <span class="badge badge-imported">${t('intake.project.badgeIdentical', { n: tot.identici ?? 0 })}</span>
            <span class="badge ${tot.conflitti ? 'badge-err' : 'badge-ok'}">${t('intake.project.badgeConflicts', { n: tot.conflitti ?? 0 })}</span>
            <span class="badge badge-generated">${t('intake.project.badgeExcluded', { n: tot.esclusi ?? 0 })}</span>
            <span class="status">${t('intake.project.modeLabel', { mode: escapeHtml(data.mode) })}</span>
          </div>
          ${tot.conflitti ? `<div class="msg-err" style="margin-top:6px">${t('intake.project.conflictsNote')}</div>` : ''}
          ${renderPathList(t('intake.project.listConflicts'), data.conflitti, 'msg-err')}
          ${renderPathList(t('intake.project.listNew'), data.nuovi, 'msg-ok')}
          ${renderPathList(t('intake.project.listExcluded'), data.esclusi, 'status')}`;
        document.getElementById('prj-apply-btn').disabled = false;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.err.prefix', { msg: e.message });
      }
    }

    async function applyProjectImport() {
      if (!currentProjectPlanId) return;
      const status = document.getElementById('prj-status');
      const out = document.getElementById('prj-apply-result');
      const btn = document.getElementById('prj-apply-btn');
      btn.disabled = true;
      status.className = 'status'; status.textContent = t('intake.project.applying');
      try {
        const res = await fetch('/api/intake/project/apply', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plan_id: currentProjectPlanId }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));

        currentProjectPlanId = null;  // un piano applicato non è riutilizzabile
        status.className = 'status msg-ok'; status.textContent = t('intake.project.applied');
        // Il progetto appena importato entra nell'elenco e viene preselezionato.
        refreshProjectImports();
        document.getElementById('prj-brief-status').textContent =
          t('intake.project.briefAfterImport', { target: data.target });
        const tot = data.totali || {};
        const reindexTxt = data.reindex ? JSON.stringify({
          reindexed_docs: data.reindex.reindexed_docs, upserted_chunks: data.reindex.upserted_chunks,
          version: data.reindex.version,
        }) : (data.reindex_error ? t('intake.project.reindexFailed', { err: data.reindex_error }) : t('intake.project.reindexNone'));
        out.innerHTML = `
          <div class="file-row">
            <span class="badge badge-ok">${t('intake.project.badgeCopied', { n: tot.copiati ?? 0 })}</span>
            <span class="status">${t('intake.project.backupLabel')}: ${data.backup ? `<code>${escapeHtml(data.backup)}</code>` : t('intake.project.backupNone')}</span>
          </div>
          <div class="status" style="margin-top:6px">${t('intake.project.reindexLabel')}: ${escapeHtml(reindexTxt)}</div>
          ${data.avviso ? `<div class="msg-err" style="margin-top:6px">⚠ ${escapeHtml(data.avviso)}</div>` : ''}`;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.err.prefix', { msg: e.message });
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
      if (!target) { select.innerHTML = `<option value="">${t('intake.project.noScope')}</option>`; return; }
      let imports = [];
      try {
        const res = await fetch(`/api/intake/project/imports?target=${encodeURIComponent(target)}`);
        if (res.ok) imports = (await res.json()).imports || [];
      } catch (e) { /* elenco non disponibile: resta il placeholder */ }
      if (!imports.length) {
        select.innerHTML = `<option value="">${t('intake.project.noImportsIn', { target: escapeHtml(target) })}</option>`;
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
      status.textContent = t('intake.project.briefStarting', {
        target, progetto: progetto || t('intake.project.lastImport'),
      });

      let job;
      try {
        const res = await fetch('/api/intake/project/brief', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target, progetto: progetto || null }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) { throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`)); }
        job = data;
      } catch (e) {
        status.className = 'status msg-err'; status.textContent = t('intake.err.prefix', { msg: e.message });
        btn.disabled = false; return;
      }

      status.textContent = t('intake.project.briefRunning');
      while (job.status === 'pending' || job.status === 'running') {
        await new Promise(r => setTimeout(r, 1500));
        try {
          const res = await fetch(`/api/intake/project/brief/${job.job_id}`);
          const data = await res.json().catch(() => ({}));
          // 404: job scartato dal registro (retention) o server riavviato — mai "completata".
          if (res.ok) job = data;
          else if (res.status === 404) job = { status: 'failed', error: apiErrorMessage(data.detail, t('intake.err.jobGone')) };
          /* altri errori HTTP: ritenta al prossimo giro */
        } catch (e) { /* rete instabile: ritenta al prossimo giro */ }
      }

      btn.disabled = false;
      if (job.status === 'failed') {
        status.className = 'status msg-err';
        status.textContent = t('intake.project.briefFailed', { err: job.error || t('intake.err.unknown') });
        return;
      }

      const r = job.result || {};
      status.className = 'status msg-ok';
      status.textContent = t('intake.project.briefDone', { target, progetto: r.progetto || progetto });
      const lat = r.latency || {};
      const scartatiHtml = (r.scartati || []).map(s =>
        `<div class="msg-err">· ${t('intake.project.discarded', { reason: escapeHtml(s.motivo) })}</div>`).join('');
      out.innerHTML = `
        <div class="file-row">
          <span class="badge badge-ok">${t('intake.project.badgeInStaging', { n: r.n_generati || 0 })}</span>
          <span class="badge ${r.n_scartati ? 'badge-err' : 'badge-ok'}">${t('intake.gen.badgeDiscarded', { n: r.n_scartati || 0 })}</span>
          <span class="status">${t('intake.project.briefLatency', { generation: lat.generation_ms ?? '?', total: lat.total_ms ?? '?' })}</span>
        </div>
        ${r.avviso ? `<div class="msg-err" style="margin-top:6px">⚠ ${escapeHtml(r.avviso)}</div>` : ''}
        ${scartatiHtml}`;
      if (r.n_generati) refreshStaging();
    }

    /* ──────────── Bootstrap ──────────── */
    populateCategorySelect(document.getElementById('gen-categoria'), '04_knowledge_informative');
    document.getElementById('prj-brief-status').textContent = t('intake.project.briefHint');
    refreshStaging();
    loadImportTargets().then(refreshProjectImports);
    document.getElementById('prj-new-target').addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); retainWorkspaceTask(addImportTarget()).catch(error => console.error(error)); }
    });

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      addImportTarget: () => addImportTarget(),
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

    window.onLangChange = function () {
      refreshStaging();
      if (_previewId && document.getElementById('staging-detail')?.style.display === 'block') {
        openPreview(_previewId);
      }
      const brief = document.getElementById('prj-brief-status');
      if (brief && !brief.classList.contains('msg-err') && !brief.classList.contains('msg-ok')) {
        brief.textContent = t('intake.project.briefHint');
      }
      loadImportTargets().then(refreshProjectImports);
    };
