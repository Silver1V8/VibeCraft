/* Script della pagina pipeline.unified.html, servito da /static/pages/ (era inline nel
   template): la CSP della console vieta gli script inline (vedi
   api/deps.CONTENT_SECURITY_POLICY). Indentazione lasciata com'era nel template. */
    /* startMatrixRain / stopMatrixRain: vedi /static/shared.js */

    let currentStep = 1;
    let exploreHistory = "";
    let interviewLog = "";
    let featureName = "";
    let devType = "";
    let sessionRevision = 0;
    let sessionLoading = false;
    let pendingDraft = null;
    let chatMessages = [];
    const draftEditors = ['explore-md-editor', 'canvas-md-editor', 'spec-md-editor'];
    const draftProject = selectedProjectId();
    const lastFeatureKey = `vibecraft:pipeline:last:${JSON.stringify(draftProject)}`;
    const draftKey = feature => `vibecraft:pipeline:1:${JSON.stringify([draftProject, feature])}`;

    function sessionStatus(message) {
      document.getElementById('session-status').textContent = message;
    }

    function choosePipelineDraft(draft) {
      pendingDraft = draft;
      for (const id of ['session-restore-btn', 'session-discard-btn']) {
        document.getElementById(id).hidden = !draft;
      }
      for (const id of [...draftEditors, 'chat-input']) document.getElementById(id).readOnly = !!draft;
      /* La tendina resta usabile anche con una bozza in sospeso: disabilitata, senza
         stile che lo mostri, i tipi appena aggiunti sembravano non comparire. Il
         ripristino sovrascrive la scelta solo se la bozza ne aveva una. */
      document.getElementById('dev-type-select').disabled = false;
      updateChatControls();
    }

    /* Intervista: "Invia" si attiva solo con nome feature e tipo di sviluppo, "Termina"
       solo dopo almeno un turno. Prima entrambi erano sempre cliccabili e il motivo del
       rifiuto arrivava dopo, come toast. Il nome basta scritto: l'invio carica la feature
       da sé (ensurePipelineFeature). Finché la conversazione è vuota, al posto del
       riquadro vuoto c'è la guida con i tre passi e il loro stato. */
    let sendBusy = false, finishBusy = false;
    function updateChatControls() {
      const named = !!getFeatureName();
      const typed = !!devType;
      const blocked = sessionLoading || !!pendingDraft;
      const reason = !named ? t('pipeline.chat.needName')
        : !typed ? t('pipeline.chat.needType')
        : blocked ? t('pipeline.chat.needDraftChoice') : '';
      const send = document.getElementById('chat-send-btn');
      const finish = document.getElementById('chat-finish-btn');
      send.disabled = sendBusy || !!reason;
      send.title = reason;
      finish.disabled = finishBusy || sendBusy || !!reason || !interviewLog;
      finish.title = reason || (interviewLog ? '' : t('pipeline.chat.needAnswer'));
      /* Con una bozza in attesa il campo è in sola lettura: lo si dice lì, altrimenti
         sembra un campo rotto. */
      document.getElementById('chat-input').placeholder = pendingDraft
        ? t('pipeline.chat.placeholderDraft')
        : t('pipeline.explore.chatPlaceholder');
      const started = chatMessages.length > 0;
      setPanelVisible('chat-guide', !started);
      setPanelVisible('chat-log', started);
      const steps = [['guide-step-feature', named], ['guide-step-type', typed], ['guide-step-answer', false]];
      const next = steps.find(([, done]) => !done)[0];
      steps.forEach(([id, done], index) => {
        const step = document.getElementById(id);
        step.classList.toggle('is-done', done);
        step.classList.toggle('is-next', id === next);
        document.getElementById(`${id}-mark`).textContent = done ? '✓' : String(index + 1);
        document.getElementById(`${id}-state`).textContent = done ? t('pipeline.guide.done')
          : id === next && id === 'guide-step-answer' && pendingDraft ? t('pipeline.guide.chooseDraft')
          : id === next ? t('pipeline.guide.todo') : '';
      });
    }

    /* Un passo della guida porta al campo da compilare. Senza tipi di sviluppo nel
       progetto la tendina è vuota: si va al campo che ne crea uno. */
    function focusGuideStep(id) {
      const select = document.getElementById('dev-type-select');
      const target = id === 'dev-type-select' && select.options.length <= 1
        ? document.getElementById('dev-type-new-input')
        : id === 'chat-input' && pendingDraft ? document.getElementById('session-restore-btn')
        : document.getElementById(id);
      target.scrollIntoView({ block: 'nearest' });
      target.focus();
    }

    function savePipelineDraft() {
      if (!featureName || sessionLoading || pendingDraft) return;
      const draft = {version: 1, feature: featureName, savedAt: new Date().toISOString(),
        devType, step: currentStep, exploreHistory, interviewLog, messages: chatMessages,
        input: document.getElementById('chat-input').value,
        editors: draftEditors.map(id => document.getElementById(id).value)};
      try {
        localStorage.setItem(draftKey(featureName), JSON.stringify(draft));
        localStorage.setItem(lastFeatureKey, featureName);
        sessionStatus(t('pipeline.session.lastSave', { when: new Date(draft.savedAt).toLocaleString() }));
      } catch (_) {
        sessionStatus(t('pipeline.session.saveFailed'));
      }
    }

    function offerPipelineDraft() {
      try {
        const raw = localStorage.getItem(draftKey(featureName));
        if (!raw) { sessionStatus(t('pipeline.session.willSaveLocal')); return; }
        const draft = JSON.parse(raw);
        if (draft?.version !== 1 || draft.feature !== featureName || !Number.isFinite(Date.parse(draft.savedAt))
          || !Number.isInteger(draft.step) || draft.step < 1 || draft.step > 5
          || !['devType', 'exploreHistory', 'interviewLog', 'input'].every(key => typeof draft[key] === 'string')
          || !Array.isArray(draft.editors) || draft.editors.length !== 3 || !draft.editors.every(text => typeof text === 'string')
          || !Array.isArray(draft.messages) || !draft.messages.every(m => m && ['user', 'ai'].includes(m.role) && typeof m.text === 'string')) {
          throw new Error('invalid draft');
        }
        choosePipelineDraft(draft);
        sessionStatus(t('pipeline.session.draftOffer', { when: new Date(draft.savedAt).toLocaleString() }));
      } catch (_) {
        sessionStatus(t('pipeline.session.draftInvalid'));
      }
    }

    function restorePipelineDraft() {
      if (!pendingDraft || sessionLoading) return;
      const draft = pendingDraft;
      choosePipelineDraft(null);
      sessionLoading = true;
      exploreHistory = draft.exploreHistory;
      interviewLog = draft.interviewLog;
      chatMessages = [];
      document.getElementById('chat-log').textContent = '';
      for (const message of draft.messages) appendChatBubble(message.role, message.text);
      document.getElementById('chat-input').value = draft.input;
      if (draft.devType) document.getElementById('dev-type-select').value = draft.devType;
      devType = document.getElementById('dev-type-select').value;
      draftEditors.forEach((id, i) => {
        document.getElementById(id).value = draft.editors[i];
        setPanelVisible(['review-explore', 'review-canvas', 'review-spec'][i], !!draft.editors[i]);
        setStepState(i + 1, draft.editors[i] ? 'warning' : 'pending', draft.editors[i] ? t('pipeline.step.localDraft') : undefined);
      });
      document.getElementById('spec-open-points-status').textContent = t('pipeline.session.draftSpecHint');
      goToStep(draft.step);
      sessionLoading = false;
      updateChatControls();
      sessionStatus(t('pipeline.session.draftRestored', { when: new Date(draft.savedAt).toLocaleString() }));
    }

    function discardPipelineDraft() {
      if (!pendingDraft || sessionLoading) return;
      try { localStorage.removeItem(draftKey(featureName)); }
      catch (_) { sessionStatus(t('pipeline.session.discardFailed')); return; }
      choosePipelineDraft(null);
      savePipelineDraft();
    }

    async function ensurePipelineFeature() {
      if (!getFeatureName()) { document.getElementById('feature-name-input').focus(); return false; }
      if (getFeatureName() !== featureName) await loadFeatureStatus();
      if (sessionLoading || pendingDraft) {
        toast(t('pipeline.session.waitDraft'), 'error');
        return false;
      }
      return true;
    }

    async function resumePipelineSession() {
      let last;
      try { last = localStorage.getItem(lastFeatureKey); }
      catch (_) { sessionStatus(t('pipeline.session.localUnavailable')); }
      if (last && !getFeatureName()) {
        document.getElementById('feature-name-input').value = last;
        await loadFeatureStatus();
      } else await loadDevTypes();
    }

    /* Prompt finale della feature, chiesto al server invece di ricostruito qui.
       Il template è deterministico (nessun LLM) ma ha DUE forme — "external" per Claude
       Code/Cursor, che possono interrogare l'indice via HTTP, e "agent" per l'esecuzione
       in-app, che usa MCP secondo la modalità — e viveva in due copie, Python e JS: la
       copia JS era già rimasta indietro di una frase rispetto a core/pipeline.py. Una sola
       sorgente di verità, interrogabile: GET /api/pipeline/final-prompt. */
    async function fetchFinalPrompt(feature, devTypeValue, consumer, mode = 'agentic', runner = 'claude') {
      const params = new URLSearchParams({ feature, dev_type: devTypeValue || '', consumer, mode, runner });
      const res = await fetch(`/api/pipeline/final-prompt?${params}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(apiErrorMessage(err.detail, `HTTP ${res.status}`));
      }
      return (await res.json()).final_prompt;
    }

    function getFeatureName() {
      return document.getElementById('feature-name-input').value.trim();
    }

    function onDevTypeChange() {
      devType = document.getElementById('dev-type-select').value;
      savePipelineDraft();
      updateChatControls();
    }

    /* Popola la tendina con le sottocartelle reali di code/ (backend, frontend, logicAgent, ...). */
    async function loadDevTypes(selected) {
      const revision = sessionRevision;
      const select = document.getElementById('dev-type-select');
      try {
        const res = await fetch('/api/pipeline/dev-types');
        const data = await res.json();
        if (revision !== sessionRevision) return;
        const options = [`<option value="">${t('pipeline.feature.selectPlaceholder')}</option>`]
          .concat(data.dev_types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`));
        select.innerHTML = options.join('');
      } catch (e) {
        if (revision !== sessionRevision) return;
        select.innerHTML = `<option value="">${t('pipeline.feature.loadError')}</option>`;
      }
      if (selected) select.value = selected;
      devType = select.value;
      updateChatControls();
    }

    /* Crea code/<nome> sul server: su un progetto nuovo è l'unico modo di avere un ambito da scegliere. */
    async function addDevType() {
      const input = document.getElementById('dev-type-new-input');
      const btn = document.getElementById('dev-type-add-btn');
      const name = input.value.trim();
      if (!name) { input.focus(); return; }
      btn.disabled = true;
      try {
        const res = await fetch('/api/pipeline/dev-types', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(apiErrorMessage(data.detail, `HTTP ${res.status}`));
        input.value = '';
        const select = document.getElementById('dev-type-select');
        await loadDevTypes(select.disabled ? devType : data.dev_type);
        if (!select.disabled) onDevTypeChange();
        toast(t('pipeline.feature.devTypeAdded', { name: data.dev_type }), 'success');
      } catch (e) {
        toast(t('pipeline.feature.devTypeAddError', { msg: e.message }), 'error');
      } finally {
        btn.disabled = false;
      }
    }

    /* Mostra/nasconde un pannello flex-col in modo atomico: 'hidden' e 'flex'
       non sono mai presenti insieme, per non dipendere dall'ordine con cui
       Tailwind genera le utility (altrimenti la cascata decide chi vince). */
    function setPanelVisible(id, visible) {
      const el = document.getElementById(id);
      el.classList.toggle('hidden', !visible);
      el.classList.toggle('flex', visible);
    }

    /* ──────────── STEPPER NAVIGATION ──────────── */
    function goToStep(step) {
      if (!featureName && step !== 1) {
        toast(t('pipeline.feature.needName'), 'error');
        return;
      }
      currentStep = step;
      [1, 2, 3, 4, 5].forEach(i => {
        setPanelVisible(`panel-step-${i}`, i === step);
        const stepButton = document.getElementById(`step-btn-${i}`);
        if (i === step) stepButton?.setAttribute?.('aria-current', 'step'); else stepButton?.removeAttribute?.('aria-current');
        // Non si sovrascrive uno stato TERMINALE (completato, con avvisi,
        // fallito): prima ogni navigazione riscriveva il className di tutti i
        // pallini, quindi un passo già completato tornava grigio appena si
        // andava altrove — restava il glifo ✓ ma con i colori di "in attesa".
        const stato = stepStates[i];
        if (stato === 'done' || stato === 'warning' || stato === 'failed') return;
        setStepState(i, i === step ? 'current' : 'pending');
      });
      savePipelineDraft();
    }

    /* ──────────── STATO DEI PASSI ────────────
       Lo stepper conosceva due soli stati: corrente (blu) e completato (verde).
       Mancavano "in esecuzione", "con avvisi" e "fallito" — e markStepDone
       veniva chiamato al COMPLETAMENTO dello stream, non al successo: un drift
       check pieno di disallineamenti marcava comunque il passo ✓ verde. Lo
       stepper mentiva, ed è il posto peggiore dove farlo, perché è l'unica
       sintesi dello stato della feature.

       Ogni stato ha glifo + colore + etichetta testuale: non dipende dal colore,
       il che conta doppio in Matrix dove il verde è anche il colore di sfondo. */
    /* Le classi sono quelle STATICHE definite nel <style> di questa pagina
       (.step-dot-* / .step-badge-*), non utility Tailwind: vedi il commento
       accanto alle regole per il motivo. */
    const STEP_STATES = {
      pending: { glifo: n => String(n), stato: 'pending', labelKey: 'pipeline.step.pending' },
      current: { glifo: n => String(n), stato: 'current', labelKey: 'pipeline.step.current' },
      running: { glifo: () => '⋯',      stato: 'running', labelKey: 'pipeline.step.running' },
      done:    { glifo: () => '✓',      stato: 'done',    labelKey: 'pipeline.step.done' },
      warning: { glifo: () => '⚠',      stato: 'warning', labelKey: 'pipeline.step.warning' },
      failed:  { glifo: () => '✕',      stato: 'failed',  labelKey: 'pipeline.step.failed' },
    };

    /* Stato corrente di ogni passo: serve a goToStep per non calpestare gli
       stati terminali durante la navigazione. */
    const stepStates = { 1: 'current', 2: 'pending', 3: 'pending', 4: 'pending', 5: 'pending' };

    function setStepState(step, state, label) {
      const s = STEP_STATES[state] || STEP_STATES.pending;
      stepStates[step] = state;
      const dot = document.getElementById(`step-dot-${step}`);
      dot.className = `w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 step-dot-${s.stato}`;
      dot.textContent = s.glifo(step);
      const badge = document.getElementById(`step-badge-${step}`);
      badge.textContent = label || t(s.labelKey);
      badge.className = `block text-xs font-mono step-badge-${s.stato}`;
      const line = document.getElementById(`step-line-${step}`);
      if (line) line.classList.toggle('done', state === 'done');
    }

    /* Manteniamo markStepDone come alias: è chiamato da parecchi punti e questo
       evita un refactor a tappeto per un rename. */
    function markStepDone(step, label) { setStepState(step, 'done', label || t('pipeline.step.generated')); }

    /* ──────────── FILE CONTROL PANEL ──────────── */
    async function refreshFilesControl() {
      if (!featureName) return;
      const revision = sessionRevision;
      try {
        const res = await fetch(`/api/pipeline/status?feature=${encodeURIComponent(featureName)}`);
        if (!res.ok) return;
        const data = await res.json();
        if (revision !== sessionRevision) return;
        const list = document.getElementById('files-control-list');
        const rows = [
          ['explore', 'explore.md', 1],
          ['canvas', 'canvas.md', 2],
          ['spec', 'spec.md', 3],
        ];
        list.innerHTML = rows.map(([key, fname]) => {
          const ok = data.files[key];
          return `<div class="flex items-center justify-between rounded-lg border ${ok ? 'border-emerald-900 bg-emerald-950/40' : 'border-slate-800 bg-slate-950'} px-3 py-2">
            <span class="font-mono text-slate-300">${fname}</span>
            <span class="${ok ? 'text-emerald-300' : 'text-slate-400'} font-semibold">${ok ? t('pipeline.files.ready') : t('pipeline.files.missing')}</span>
          </div>`;
        }).join('');

        if (data.files.explore) markStepDone(1);
        if (data.files.canvas) markStepDone(2);
        if (data.files.spec) markStepDone(3);

        document.getElementById('feature-folder-hint').textContent = `changes/${data.feature_folder}/`;
        await refreshGateReview();
      } catch (e) { /* silenzioso: pannello di controllo best-effort */ }
    }

    /* ──────────── LOAD / RESUME FEATURE ──────────── */
    async function loadFeatureStatus() {
      const name = getFeatureName();
      if (!name) { document.getElementById('feature-name-input').focus(); return; }
      savePipelineDraft();
      const revision = ++sessionRevision;
      sessionLoading = true;
      choosePipelineDraft(null);
      for (const id of [...draftEditors, 'chat-input']) document.getElementById(id).readOnly = true;
      document.getElementById('dev-type-select').disabled = true;
      featureName = name;
      exploreHistory = interviewLog = '';
      chatMessages = [];
      document.getElementById('chat-log').textContent = '';
      document.getElementById('chat-input').value = '';
      document.getElementById('explore-status').textContent = '';
      updateChatControls();
      document.getElementById('canvas-generate-btn').disabled = false;
      document.getElementById('propose-generate-btn').disabled = false;
      for (const id of draftEditors) document.getElementById(id).value = '';
      for (const id of ['review-explore', 'review-canvas', 'review-spec', 'canvas-loader', 'propose-loader']) setPanelVisible(id, false);
      for (const id of ['final-prompt-card', 'validate-card', 'validate-report-box', 'gate-comparison', 'drift-report-card', 'archive-report-card', 'dryrun-card', 'agent-context-wrap']) document.getElementById(id).classList.add('hidden');
      for (const id of ['drift-report-box', 'archive-report-box', 'agent-output', 'gate-status', 'gate-decisions', 'gate-comparison']) document.getElementById(id).textContent = '';
      for (const id of ['drift-loader', 'archive-loader']) setPanelVisible(id, false);
      for (const id of ['drift-check-btn', 'archive-btn', 'canvas-dryrun-btn', 'agent-context-btn']) document.getElementById(id).disabled = false;
      window._finalPrompt = '';
      document.getElementById('final-prompt-box').textContent = '';
      for (let step = 1; step <= 5; step++) setStepState(step, 'pending');

      // Recupera il tipo di sviluppo eventualmente già salvato per questa feature
      // e ripopola la tendina di conseguenza, prima di ricostruire il prompt finale.
      let savedDevType = "";
      try {
        const statusRes = await fetch(`/api/pipeline/status?feature=${encodeURIComponent(featureName)}`);
        if (statusRes.ok) savedDevType = (await statusRes.json()).dev_type || "";
      } catch (e) { /* best-effort */ }
      if (revision !== sessionRevision) return;
      await loadDevTypes(savedDevType);
      if (revision !== sessionRevision) return;

      // Prova a recuperare eventuali file già generati per riprendere la review
      document.getElementById('spec-open-points-status').textContent = openPointsSummary({});
      let furthestStep = 1;
      for (const [fname, editorId, reviewId, step] of [
        ['explore.md', 'explore-md-editor', 'review-explore', 1],
        ['canvas.md', 'canvas-md-editor', 'review-canvas', 2],
        ['spec.md', 'spec-md-editor', 'review-spec', 3],
      ]) {
        try {
          const res = await fetch(`/api/pipeline/file?feature=${encodeURIComponent(featureName)}&name=${fname}`);
          if (res.ok) {
            const data = await res.json();
            if (revision !== sessionRevision) return;
            document.getElementById(editorId).value = data.content;
            setPanelVisible(reviewId, true);
            furthestStep = step;

            if (fname === 'spec.md') {
              document.getElementById('spec-open-points-status').textContent = openPointsSummary(data);
              // Best-effort: se il prompt non si recupera, il resto della review si carica
              // comunque (la card resta vuota e si ripopola rigenerando le specifiche).
              try {
                const finalPrompt = await fetchFinalPrompt(featureName, devType, 'external');
                if (revision !== sessionRevision) return;
                window._finalPrompt = finalPrompt;
                document.getElementById('final-prompt-box').textContent = finalPrompt;
              } catch (err) { /* prompt non recuperabile, ignora */ }
            }
          }
        } catch (e) { /* file non presente, ignora */ }
        if (revision !== sessionRevision) return;
      }

      // Riprende automaticamente dall'ultimo step con contenuto già generato,
      // altrimenti il pannello popolato resterebbe nascosto dietro allo step 1.
      goToStep(furthestStep);

      await refreshFilesControl();
      if (revision !== sessionRevision) return;
      sessionLoading = false;
      choosePipelineDraft(null);
      offerPipelineDraft();
      try { localStorage.setItem(lastFeatureKey, name); }
      catch (_) { sessionStatus(t('pipeline.session.localUnavailable')); }
    }

    /* ──────────── STEP 1: EXPLORE ──────────── */
    function appendChatBubble(role, text) {
      chatMessages.push({role, text});
      const log = document.getElementById('chat-log');
      const isUser = role === 'user';
      const bubble = document.createElement('div');
      bubble.className = `fade-in prose-text max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
        isUser ? 'self-end bg-blue-600 text-white' : 'self-start bg-slate-800 text-slate-100'
      }`;
      bubble.textContent = text;
      log.appendChild(bubble);
      updateChatControls();
      log.scrollTop = log.scrollHeight;
    }

    async function sendExploreTurn() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!devType) { toast(t('pipeline.feature.needDevType'), 'error'); return; }

      const input = document.getElementById('chat-input');
      const userInput = input.value.trim();
      if (!userInput) { input.focus(); return; }

      appendChatBubble('user', userInput);
      interviewLog += `**Utente:** ${userInput}\n\n`;
      input.value = '';
      savePipelineDraft();

      sendBusy = true;
      updateChatControls();
      document.getElementById('explore-status').textContent = t('pipeline.explore.aiThinking');

      try {
        const res = await fetch('/api/pipeline/explore/turn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature_name: featureName, history: exploreHistory, user_input: userInput, dev_type: devType }),
        });
        if (!res.ok) throw new Error(apiErrorMessage((await res.json()).detail, `HTTP ${res.status}`));
        const data = await res.json();
        if (revision !== sessionRevision) return;
        exploreHistory = data.history;
        appendChatBubble('ai', data.ai_response);
        interviewLog += `**IA:** ${data.ai_response}\n\n`;
        savePipelineDraft();
        document.getElementById('explore-status').textContent = '';
      } catch (e) {
        if (revision !== sessionRevision) return;
        appendChatBubble('ai', t('pipeline.err.prefix', { msg: e.message }));
        document.getElementById('explore-status').textContent = t('pipeline.explore.connError');
      } finally {
        if (revision === sessionRevision) { sendBusy = false; updateChatControls(); input.focus(); }
      }
    }

    async function finishExplore() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!devType) { toast(t('pipeline.feature.needDevType'), 'error'); return; }

      if (!interviewLog) {
        toast(t('pipeline.explore.needTurn'), 'error');
        return;
      }

      finishBusy = true;
      updateChatControls();
      try {
        const res = await fetch('/api/pipeline/explore/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature_name: featureName, interview_log: interviewLog, dev_type: devType }),
        });
        if (!res.ok) throw new Error(apiErrorMessage((await res.json()).detail, `HTTP ${res.status}`));
        const data = await res.json();
        if (revision !== sessionRevision) return;
        document.getElementById('explore-md-editor').value = data.content;
        savePipelineDraft();
        setPanelVisible('review-explore', true);
        markStepDone(1);
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(t('pipeline.explore.saveError', { msg: e.message }), 'error');
      } finally {
        if (revision === sessionRevision) { finishBusy = false; updateChatControls(); }
      }
    }

    function approveAndGoToCanvas() {
      goToStep(2);
    }

    /* ──────────── STEP 2: CANVAS ──────────── */
    async function generateCanvas() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      if (!devType) { toast(t('pipeline.feature.needDevType'), 'error'); return; }
      const btn = document.getElementById('canvas-generate-btn');
      btn.disabled = true;
      setPanelVisible('canvas-loader', true);
      setPanelVisible('review-canvas', false);

      try {
        const res = await fetch('/api/pipeline/canvas/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature_name: featureName, dev_type: devType }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(apiErrorMessage(err.detail, `HTTP ${res.status}`));
        }
        const data = await res.json();
        if (revision !== sessionRevision) return;
        document.getElementById('canvas-md-editor').value = data.content;
        savePipelineDraft();
        setPanelVisible('review-canvas', true);
        markStepDone(2);
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(t('pipeline.canvas.genError', { msg: e.message }), 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('canvas-loader', false); }
      }
    }

    function approveAndGoToPropose() {
      goToStep(3);
    }

    /* ──────────── STEP 3: PROPOSE ──────────── */
    async function generatePropose() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      if (!devType) { toast(t('pipeline.feature.needDevType'), 'error'); return; }
      const btn = document.getElementById('propose-generate-btn');
      btn.disabled = true;
      setPanelVisible('propose-loader', true);
      setPanelVisible('review-spec', false);
      document.getElementById('final-prompt-card').classList.add('hidden');

      try {
        const res = await fetch('/api/pipeline/propose/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature_folder: featureName, dev_type: devType }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(apiErrorMessage(err.detail, `HTTP ${res.status}`));
        }
        const data = await res.json();
        if (revision !== sessionRevision) return;
        document.getElementById('spec-md-editor').value = data.content;
        savePipelineDraft();
        document.getElementById('spec-open-points-status').textContent = openPointsSummary(data);
        setPanelVisible('review-spec', true);
        document.getElementById('final-prompt-box').textContent = data.final_prompt;
        window._finalPrompt = data.final_prompt;
        markStepDone(3);
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(t('pipeline.propose.genError', { msg: e.message }), 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('propose-loader', false); }
      }
    }

    function approveSpec() {
      document.getElementById('validate-card').classList.remove('hidden');
      document.getElementById('final-prompt-card').classList.remove('hidden');
      document.getElementById('final-prompt-card').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      refreshGateReview();
    }

    /* ──────────── VALIDAZIONE GOVERNANCE (pre-apply) ──────────── */
    function gateApiError(data) {
      const detail = data.detail || data.gate || data;
      if (typeof detail === 'string') return detail;
      return gateMessages(detail).join('\n') || t('pipeline.gate.requestFailed');
    }

    const validationRefs = new Map();
    const blockedAttempts = new Map();
    function gateMessages(gate) {
      return [...(gate.reasons || []), ...(gate.warnings || [])].map(item =>
        [item.code, item.action, item.message, item.next_step,
          item.changed?.length ? t('pipeline.gate.changed', { items: item.changed.join(', ') }) : ''].filter(Boolean).join(' · '));
    }

    function describeFinding(f) {
      const who = f.covered_by;
      const coverage = who ? t('pipeline.gate.coveredBy', { id: who.decision_id, by: who.declared_by, at: who.recorded_at })
        : t('pipeline.gate.uncovered');
      return `${f.rule || f.topic || f.kind} · ${f.message}\n${coverage}`;
    }

    function admissionSummary(gate) {
      if (gate?.allowed === true) return t('pipeline.gate.agenticAllowed');
      const reason = gate?.allowed === false
        ? (gate.reasons || []).map(item => item.message).filter(Boolean).join('; ') || t('pipeline.gate.reasonMissing')
        : t('pipeline.gate.statusMissing');
      return t('pipeline.gate.agenticBlocked', { reason });
    }

    function validationSummary(data) {
      const statuses = [data.checks?.structural?.status, data.checks?.semantic?.status];
      const checks = statuses.some(status => !['pass', 'fail'].includes(status)) ? t('pipeline.validate.checksUnavailable')
        : statuses.includes('fail') ? t('pipeline.validate.checksFailed') : t('pipeline.validate.checksPassed');
      const lines = [t('pipeline.validate.checksLine', { checks }), admissionSummary(data.gate),
        t('pipeline.validate.validationLine', { id: data.validation_id, status: data.status }), data.validation_error || data.report || ''];
      lines.push(...(data.structural_findings || []).map(describeFinding));
      lines.push(...(data.semantic_findings || []).map(describeFinding));
      if (data.suggestions?.length) lines.push(t('pipeline.validate.suggestionsHeader') + '\n'
        + data.suggestions.map(text => `• ${text}`).join('\n'));
      lines.push(t('pipeline.validate.gapsNote'));
      if (data.scenario_scope?.off_scope?.length) lines.push(t('pipeline.validate.offScope') + ' ' + JSON.stringify(data.scenario_scope.off_scope));
      lines.push(...gateMessages(data.gate || {}));
      return lines.filter(Boolean).join('\n\n');
    }

    async function runValidate() {
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      const validatingFeature = featureName;
      const btn = document.getElementById('validate-btn');
      const box = document.getElementById('validate-report-box');
      btn.disabled = true;
      box.classList.remove('hidden');
      box.textContent = t('pipeline.validate.running');
      try {
        const res = await fetch('/api/pipeline/validate', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({feature: validatingFeature})});
        const data = await res.json();
        if (featureName !== validatingFeature) return;
        if (!res.ok && data.status !== 'unavailable') throw new Error(gateApiError(data));
        validationRefs.set(validatingFeature, data.validation_id || null);
        box.textContent = validationSummary(data);
        document.getElementById('validate-structural').textContent = t('pipeline.validate.checksStatus', { structural: data.checks?.structural?.status || 'unavailable', semantic: data.checks?.semantic?.status || 'unavailable' });
        await refreshGateReview();
      } catch (e) {
        if (featureName === validatingFeature) box.textContent = t('pipeline.validate.unavailable', { msg: e.message });
      } finally { btn.disabled = false; }
    }

    let gateReview = null;
    async function refreshGateReview() {
      if (!featureName) return;
      const reviewingFeature = featureName;
      gateReview = null;
      document.getElementById('gate-decisions').textContent = '';
      document.getElementById('gate-comparison').textContent = '';
      try {
        const params = new URLSearchParams({feature: reviewingFeature});
        const selected = validationRefs.get(reviewingFeature);
        if (selected) params.set('validation_id', selected);
        const res = await fetch('/api/pipeline/gate?' + params);
        const data = await res.json();
        if (featureName !== reviewingFeature || validationRefs.get(reviewingFeature) !== selected) return;
        if (!res.ok) throw new Error(gateApiError(data));
        if (!selected) validationRefs.set(reviewingFeature, data.validation_id || null);
        gateReview = {data, feature: reviewingFeature};
        document.getElementById('gate-status').textContent = [
          admissionSummary(data.gate),
          data.validation_id ? t('pipeline.gate.validationId', { id: data.validation_id }) : t('pipeline.gate.validationAbsent'),
          t('pipeline.gate.openPointsStatus', { status: data.gate.open_points_status ?? t('pipeline.gate.unreadable') }),
          ...gateMessages(data.gate),
          ...(data.structural_findings || []).map(describeFinding),
        ].join('\n');
        renderDecisionEditor(data);
      } catch (e) {
        if (featureName === reviewingFeature) document.getElementById('gate-status').textContent = e.message;
      }
    }

    async function compareValidatedVersion() {
      await refreshGateReview();
      const host = document.getElementById('gate-comparison');
      const comparison = gateReview?.feature === featureName ? gateReview.data.comparison : null;
      host.textContent = comparison ? t('pipeline.gate.comparisonWith', { id: comparison.validation_id })
        : t('pipeline.gate.comparisonMissing');
      if (!comparison) return;
      for (const name of ['canvas', 'spec']) {
        const row = document.createElement('div');
        row.className = 'grid grid-cols-1 md:grid-cols-2 gap-2 my-2';
        for (const [key, label] of [['current', t('pipeline.gate.currentSaved')], ['validated', t('pipeline.gate.validated')]]) {
          const column = document.createElement('div');
          const title = document.createElement('p'); title.textContent = `${name}.md · ${label}`;
          const text = document.createElement('pre'); text.textContent = comparison[name][key];
          text.className = 'whitespace-pre-wrap break-words bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-72 overflow-auto';
          column.appendChild(title); column.appendChild(text); row.appendChild(column);
        }
        host.appendChild(row);
      }
    }

    function renderDecisionEditor(data) {
      const host = document.getElementById('gate-decisions');
      host.textContent = '';
      function element(tag, text, id) {
        const node = document.createElement(tag);
        if (text) node.textContent = text;
        if (id) node.id = id;
        host.appendChild(node);
        return node;
      }
      element('p', t('pipeline.decision.disclaimer'));
      if (!Array.isArray(data.point_decisions)) { element('p', t('pipeline.decision.reportInvalid')); return; }
      if (!data.point_decisions.length) { element('p', t('pipeline.decision.noOpenPoints')); return; }
      for (const p of data.point_decisions) element('pre', `${p.point.id} · ${p.status}\n${JSON.stringify(p.point, null, 2)}` +
        (p.decision ? `\n${t('pipeline.decision.recorded', { id: p.decision.decision_id, by: p.decision.declared_by, at: p.decision.recorded_at })}\n${p.decision.motivation}` : ''));
      element('label', t('pipeline.decision.pointLabel')).htmlFor = 'decision-point';
      const points = element('select', '', 'decision-point');
      points.add(new Option(t('pipeline.decision.selectPoint'), ''));
      for (const p of data.point_decisions) points.add(new Option(`${p.point.id}: ${p.point.question}`, p.point_hash));
      element('label', t('pipeline.decision.statusLabel')).htmlFor = 'decision-status';
      const status = element('select', '', 'decision-status');
      status.add(new Option(t('pipeline.decision.selectStatus'), ''));
      status.add(new Option(t('pipeline.decision.accept'), 'accepted'));
      status.add(new Option(t('pipeline.decision.resolve'), 'resolved'));
      element('label', t('pipeline.decision.byLabel'), 'decision-by-label').htmlFor = 'decision-by';
      element('input', '', 'decision-by');
      element('label', t('pipeline.decision.reasonLabel'), 'decision-reason-label').htmlFor = 'decision-reason';
      element('textarea', '', 'decision-reason');
      element('p', t('pipeline.decision.assocNote'));
      for (const f of data.structural_findings.filter(f => f.associable)) {
        const label = element('label', '');
        const check = document.createElement('input'); check.type = 'checkbox'; check.value = f.finding_hash;
        check.className = 'coverage-association'; label.appendChild(check);
        label.appendChild(document.createTextNode(describeFinding(f)));
      }
      const submit = element('button', t('pipeline.decision.submit'), 'decision-submit');
      submit.onclick = recordPointDecision;
    }

    async function recordPointDecision() {
      const review = gateReview;
      if (!review || review.feature !== featureName) return;
      const value = id => document.getElementById(id).value.trim();
      const status = value('decision-status'), point = value('decision-point');
      const motivation = value('decision-reason'), declaredBy = value('decision-by');
      const hashes = [...document.querySelectorAll('#gate-decisions .coverage-association:checked')].map(n => n.value);
      if (!point || !status || !motivation || !declaredBy) { toast(t('pipeline.decision.needFields'), 'error'); return; }
      if (hashes.length && status !== 'accepted') { toast(t('pipeline.decision.onlyAccepted'), 'error'); return; }
      const btn = document.getElementById('decision-submit'); btn.disabled = true;
      const headers = {'Content-Type': 'application/json'};
      try {
        const key = window.__VIBECRAFT_AGENT_API_KEY__ || localStorage.getItem('vibecraft_agent_api_key');
        if (key) headers['X-API-Key'] = key;
        const res = await fetch('/api/pipeline/open-points/decision', {method: 'POST', headers,
          body: JSON.stringify({feature: review.feature, spec_hash: review.data.spec_hash, point_hash: point,
            status, motivation, declared_by: declaredBy, declared_origin: 'ui', coverage_finding_hashes: hashes})});
        const data = await res.json();
        if (!res.ok) throw new Error(gateApiError(data));
        if (featureName === review.feature) { await refreshGateReview(); toast(t('pipeline.decision.saved')); }
      } catch (e) { toast(e.message, 'error'); }
      finally { btn.disabled = false; }
    }

    /* ──────────── ESECUZIONE CON CLAUDE AGENT SDK ──────────── */
    function openPointsSummary(data) {
      const limits = '\n' + t('pipeline.openPoints.limits');
      if (data.open_points_status === 'invalid') {
        return '❌ ' + t('pipeline.openPoints.malformed', { err: data.open_points_error || t('pipeline.openPoints.schemaInvalid') }) + limits;
      }
      if (data.open_points_status !== 'valid') return '⚠ ' + t('pipeline.openPoints.absent') + limits;
      if (!Array.isArray(data.open_points)) return '❌ ' + t('pipeline.openPoints.notList') + limits;
      if (!data.open_points.length) return t('pipeline.openPoints.none') + limits;
      return '⚠ ' + t('pipeline.openPoints.count', { n: data.open_points.length }) + ':\n' + data.open_points.map(p =>
        `${p.id} · ${p.reason} · ${p.original_question}\n${t('pipeline.openPoints.currentQ')}: ${p.question}`
      ).join('\n') + limits;
    }

    // Runner dal server (/api/pipeline/agent/runners): disponibilità reale, modelli e modalità
    // ammesse. Se la chiamata fallisce restano le opzioni statiche di Claude Code.
    let agentRunners = [];
    let agentRunning = false;
    async function loadRunners() {
      try {
        const res = await fetch('/api/pipeline/agent/runners');
        if (!res.ok) return;
        const body = await res.json();
        agentRunners = body.runners;
        fillAttempts(body.max_attempts);
      } catch { return; }
      const select = document.getElementById('agent-runner-select');
      select.textContent = '';
      for (const r of agentRunners) {
        const option = new Option(r.available ? r.label : `${r.label} (${r.unavailable_reason || t('pipeline.agent.notInstalled')})`, r.id);
        option.disabled = !(r.export_available ?? r.available);
        select.add(option);
      }
      select.value = (agentRunners.find(r => r.available) || agentRunners[0] || {}).id || 'claude';
      onRunnerChange();
    }

    /* Opzioni della tendina "Tentativi", dal tetto dichiarato dal server: offrirne di più
       significherebbe far scegliere un numero che il server poi taglia in silenzio. */
    let _attemptsCeiling = 1;
    function fillAttempts(ceiling) {
      const select = document.getElementById('agent-attempts-select');
      const previous = select.value;
      if (ceiling != null) _attemptsCeiling = ceiling;
      const max = Math.max(1, Math.min(Number(_attemptsCeiling) || 1, 10));
      select.textContent = '';
      for (let n = 1; n <= max; n++) {
        select.add(new Option(n === 1 ? t('pipeline.agent.attemptOne') : t('pipeline.agent.attemptN', { n }), String(n)));
      }
      select.value = (Number(previous) >= 1 && Number(previous) <= max) ? previous : '1';
    }

    /* Il rilancio si appoggia alla suite eseguita dal server, che gira solo dopo un run
       agentic: nelle altre modalità non c'è codice nuovo da provare, e la tendina resta
       spenta invece di promettere qualcosa che non accadrà. */
    function syncAttemptsAvailability() {
      const agentic = document.getElementById('agent-mode-select').value === 'agentic';
      const select = document.getElementById('agent-attempts-select');
      select.disabled = !agentic;
      select.title = agentic
        ? t('pipeline.agent.attemptsTitle')
        : t('pipeline.agent.attemptsDisabled');
    }

    function onRunnerChange() {
      const runner = agentRunners.find(r => r.id === document.getElementById('agent-runner-select').value);
      if (!runner) return;
      const models = document.getElementById('agent-model-select');
      models.textContent = '';
      if (!runner.models.length) models.add(new Option(t('pipeline.agent.defaultModel'), ''));
      for (const m of runner.models) models.add(new Option(m, m));
      const modes = document.getElementById('agent-mode-select');
      for (const o of modes.options) o.disabled = !runner.modes.includes(o.value);
      if (!runner.modes.includes(modes.value)) modes.value = runner.modes[0];
      syncAttemptsAvailability();
      syncRunnerAvailability();
    }

    function syncRunnerAvailability() {
      const runner = agentRunners.find(r => r.id === document.getElementById('agent-runner-select').value);
      const btn = document.getElementById('agent-run-btn');
      btn.disabled = agentRunning || runner?.available === false;
      btn.title = runner?.available === false ? runner.unavailable_reason || t('pipeline.agent.runnerUnavailable') : '';
    }

    async function runWithAgent() {
      if (agentRunning) return;
      const revision = sessionRevision;
      const mode = document.getElementById('agent-mode-select').value;
      const model = document.getElementById('agent-model-select').value;
      const runner = document.getElementById('agent-runner-select').value;
      const capability = agentRunners.find(r => r.id === runner);
      if (capability?.available === false) {
        toast(capability.unavailable_reason || t('pipeline.agent.runnerUnavailable'), 'error');
        return;
      }
      // Fuori da agentic la tendina è spenta e il server non verifica: chiedere rilanci
      // sarebbe una richiesta senza effetto.
      const attempts = mode === 'agentic' ? Number(document.getElementById('agent-attempts-select').value) || 1 : 1;
      // La modalità determina tool e contesto: niente fallback sul prompt HTTP esterno.
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      const runningFeature = featureName;
      await refreshGateReview();
      if (revision !== sessionRevision || featureName !== runningFeature) return;
      let prompt;
      try {
        if (mode !== 'agentic') prompt = await fetchFinalPrompt(runningFeature, devType, 'agent', mode, runner);
      } catch (err) { toast(err.message, 'error'); return; }
      if (mode === 'agentic' && !await confirmDialog(
        t('pipeline.agent.confirmBody'),
        { title: t('pipeline.agent.confirmTitle'), confirmText: t('pipeline.agent.confirmOk'), danger: true }
      )) return;
      if (revision !== sessionRevision || featureName !== runningFeature) return;

      if (agentRunning) return;
      agentRunning = true;
      const btn = document.getElementById('agent-run-btn');
      const out = document.getElementById('agent-output');
      btn.disabled = true;
      out.style.display = '';
      out.textContent = t('pipeline.agent.starting', { runner, model: model || t('pipeline.agent.defaultModel'), mode }) + '\n\n';

      // X-API-Key richiesta sempre (anche da localhost) per questo endpoint — vedi
      // api/deps.py::require_api_key_strict. Il server la inietta da solo a ogni
      // caricamento della pagina (inject_agent_api_key, SOLO per client locali) in
      // window.__VIBECRAFT_AGENT_API_KEY__: niente piu' da fare a mano dopo un riavvio.
      // localStorage resta come fallback (es. se in futuro servisse impostarla a mano
      // da console: localStorage.setItem('vibecraft_agent_api_key', '...')).
      const headers = { 'Content-Type': 'application/json' };

      try {
        const apiKey = window.__VIBECRAFT_AGENT_API_KEY__ || localStorage.getItem('vibecraft_agent_api_key') || '';
        if (apiKey) headers['X-API-Key'] = apiKey;
        const res = await fetch('/api/pipeline/agent/run', {
          method: 'POST',
          headers,
          body: JSON.stringify({ prompt, mode, runner, model, feature: runningFeature,
            max_attempts: attempts,
            validation_id: validationRefs.get(runningFeature) || null,
            ...(blockedAttempts.has(runningFeature) ? {retry_of_attempt_id: blockedAttempts.get(runningFeature)} : {}) }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          if (revision !== sessionRevision) return;
          const gate = err.detail;
          if ([409, 503].includes(res.status) && gate?.allowed === false) {
            if (gate.attempt_id) blockedAttempts.set(runningFeature, gate.attempt_id);
            out.textContent += t('pipeline.agent.blocked', { validation: gate.validation_id || t('pipeline.gate.absent'), attempt: gate.attempt_id || t('pipeline.agent.attemptUnrecorded') }) + '\n';
            if (gate.retry_of_attempt_id) out.textContent += t('pipeline.agent.retryOf', { id: gate.retry_of_attempt_id }) + '\n';
            out.textContent += gateMessages(gate).join('\n') + '\n';
            return;
          }
          throw new Error(gateApiError(err));
        }
        blockedAttempts.delete(runningFeature);

        let terminated = false;
        await consumeNdjson(res, ev => {
            if (revision !== sessionRevision) return;
            if (ev.type === 'gate') {
              out.textContent += t(mode === 'agentic' ? 'pipeline.agent.gate' : 'pipeline.agent.gateAdvisory', { validation: ev.gate.validation_id || t('pipeline.gate.absent'), attempt: ev.attempt_id || t('pipeline.agent.attemptUnrecorded') }) + '\n';
              out.textContent += gateMessages(ev.gate).join('\n') + '\n';
            } else if (ev.type === 'text') {
              out.textContent += ev.text + '\n';
            } else if (ev.type === 'tool_use') {
              out.textContent += `  🔧 [${ev.tool}]\n`;
            } else if (ev.type === 'result') {
              terminated = true;
              const secs = ev.duration_ms != null ? (ev.duration_ms / 1000).toFixed(1) + 's' : '—';
              const cost = ev.total_cost_usd != null ? '$' + ev.total_cost_usd.toFixed(4) : '—';
              out.textContent += '\n' + t(ev.is_error ? 'pipeline.agent.endedError' : 'pipeline.agent.endedOk', { secs, cost, turns: ev.num_turns ?? '—' }) + '\n' + openPointsSummary(ev) + '\n';
            } else if (ev.type === 'error') {
              terminated = true;
              out.textContent += '\n' + t('pipeline.err.prefix', { msg: ev.message }) + '\n' + openPointsSummary(ev) + '\n';
            } else if (ev.type === 'verification') {
              // Esito della suite ESEGUITA dal server: l'unica riga di questo output che non
              // riporta una dichiarazione dell'agente.
              const icona = ev.status === 'passed' ? '✅' : (ev.status === 'failed' ? '❌' : '⚠️');
              const comando = ev.command && ev.command.length ? ev.command.join(' ') : '—';
              out.textContent += '\n' + t('pipeline.agent.verification', { icon: icona, type: ev.dev_type, command: comando, status: ev.status, exit: ev.exit_code != null ? ` (exit ${ev.exit_code})` : '', secs: ev.duration_seconds }) + '\n';
              if (ev.reason) out.textContent += `   ${ev.reason}\n`;
              if (ev.status === 'unavailable') {
                out.textContent += '   ' + t('pipeline.agent.verifyUnavailable') + '\n';
              }
              if (ev.output_tail) out.textContent += ev.output_tail.trimEnd() + '\n';
              if (ev.status === 'failed' && ev.attempts_left === 0) {
                out.textContent += '   ' + t('pipeline.agent.noAttemptsLeft') + '\n';
              }
            } else if (ev.type === 'retry') {
              out.textContent += '\n' + t('pipeline.agent.retry', { id: ev.attempt_id, of: ev.retry_of_attempt_id, left: ev.attempts_left }) + '\n\n';
            } else if (ev.type === 'retry_blocked') {
              terminated = true;
              out.textContent += '\n⚠️ ' + t('pipeline.agent.retryBlocked', { detail: ev.detail }) + '\n';
            } else if (ev.type === 'verification_unrecorded') {
              out.textContent += '\n⚠️ ' + t('pipeline.agent.verifyUnrecorded', { detail: ev.detail }) + '\n';
            }
            out.scrollTop = out.scrollHeight;
        });
        if (revision === sessionRevision && !terminated) throw new Error(t('pipeline.agent.streamInterrupted'));
      } catch (e) {
        if (revision !== sessionRevision) return;
        out.textContent += '\n' + t('pipeline.err.prefix', { msg: e.message }) + '\n' + openPointsSummary({}) + '\n';
      } finally {
        agentRunning = false;
        syncRunnerAvailability();
      }
    }

    /* ──────────── CONSUMER NDJSON (streaming drift/archive) ──────────── */
    async function consumeNdjson(res, onEvent) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) { if (line.trim()) onEvent(JSON.parse(line)); }
      }
      if (buffer.trim()) onEvent(JSON.parse(buffer));
    }

    /* ──────────── STEP 4: VERIFICA DEL DRIFT (streaming) ──────────── */
    async function runDriftCheck() {
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      const revision = sessionRevision;
      const btn = document.getElementById('drift-check-btn');
      const box = document.getElementById('drift-report-box');
      btn.disabled = true;
      setPanelVisible('drift-loader', true);
      setStepState(4, 'running');
      let hadError = false;
      box.textContent = '';
      document.getElementById('drift-report-card').classList.remove('hidden');
      try {
        const res = await fetch('/api/pipeline/drift/check/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature: featureName }),
        });
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        if (revision === sessionRevision) setPanelVisible('drift-loader', false);
        // Il verdetto dipende da cosa è passato nello stream, non dal fatto che
        // lo stream sia finito: prima bastava che terminasse per marcare il passo
        // ✓ completato, anche con disallineamenti gravi dentro al report.
        // Il report (evento 'result') inizia con il verdetto calcolato da core/drift.py:
        // solo "✅ NESSUN DRIFT" conta come verificato.
        let verdict = '';
        await consumeNdjson(res, ev => {
          if (revision !== sessionRevision) return;
          if (ev.type === 'log') box.textContent += ev.line + '\n';
          else if (ev.type === 'result') verdict = String(ev.value || '');
          else if (ev.type === 'error') { hadError = true; box.textContent += `\n❌ ${ev.message}\n`; }
          box.scrollTop = box.scrollHeight;
        });
        if (revision !== sessionRevision) return;
        const clean = !hadError && verdict.startsWith('✅');
        const label = hadError || verdict.startsWith('❌') ? t('pipeline.drift.failed')
          : verdict.startsWith('⚠️ DRIFT') ? t('pipeline.drift.detected')
          : verdict.startsWith('⚠️ PUNTI APERTI') ? t('pipeline.drift.openPoints')
          : clean ? t('pipeline.drift.verified') : t('pipeline.drift.incomplete');
        setStepState(4, clean ? 'done' : 'failed', label);
        if (!clean) toast(t('pipeline.drift.toastWarn', { label }), 'warning');
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent += '\n' + t('pipeline.err.prefix', { msg: e.message });
        setStepState(4, 'failed', t('pipeline.drift.failed'));
        toast(t('pipeline.drift.toastFail', { msg: e.message }), 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('drift-loader', false); }
      }
    }

    /* ──────────── STEP 5: ARCHIVIAZIONE + RE-INDICIZZAZIONE (streaming) ──────────── */
    async function runArchive() {
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      const revision = sessionRevision;
      if (!await confirmDialog(
        t('pipeline.archive.confirmBody', { name: featureName }),
        { title: t('pipeline.archive.confirmTitle'), confirmText: t('pipeline.archive.confirmOk'), danger: true }
      )) return;
      if (revision !== sessionRevision) return;

      const btn = document.getElementById('archive-btn');
      const box = document.getElementById('archive-report-box');
      btn.disabled = true;
      setPanelVisible('archive-loader', true);
      setStepState(5, 'running');
      let hadError = false;
      let archived = false;
      box.textContent = '';
      document.getElementById('archive-report-card').classList.remove('hidden');
      try {
        const res = await fetch('/api/pipeline/archive/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature: featureName }),
        });
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        if (revision === sessionRevision) setPanelVisible('archive-loader', false);
        await consumeNdjson(res, ev => {
          if (revision !== sessionRevision) return;
          if (ev.type === 'log') box.textContent += ev.line + '\n';
          else if (ev.type === 'reloaded') box.textContent += '\n🔄 ' + t('pipeline.archive.reloaded') + '\n';
          else if (ev.type === 'reindex_queued') {
            archived = true;
            box.textContent += '\n🔄 ' + t('pipeline.archive.reindexQueued', { id: ev.job_id }) + '\n';
            pollReindexJob(ev.job_id, box);
          }
          else if (ev.type === 'error') { hadError = true; box.textContent += `\n❌ ${ev.message}\n`; }
          box.scrollTop = box.scrollHeight;
        });
        if (revision !== sessionRevision) return;
        if (!hadError && !archived) throw new Error(t('pipeline.archive.streamInterrupted'));
        setStepState(5, hadError ? 'failed' : 'done', hadError ? t('pipeline.archive.errors') : t('pipeline.archive.done'));
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent += '\n' + t('pipeline.err.prefix', { msg: e.message });
        setStepState(5, 'failed', t('pipeline.archive.failed'));
        toast(t('pipeline.archive.toastFail', { msg: e.message }), 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('archive-loader', false); }
      }
    }

    /* ──────────── NOTIFICA A FINE RE-INDICIZZAZIONE (poll job in background) ──────────── */
    const _TERMINAL_REINDEX_STATES = ['completed', 'completed_not_promoted', 'failed', 'interrupted'];
    function reindexStatusLabel(status) {
      const map = {
        completed: 'pipeline.reindex.completed',
        completed_not_promoted: 'pipeline.reindex.notPromoted',
        failed: 'pipeline.reindex.failed',
        interrupted: 'pipeline.reindex.interrupted',
      };
      return map[status] ? t(map[status]) : status;
    }

    async function notifyReindexDone(message, ok) {
      toast(message, ok ? 'success' : 'warning');
      if (typeof Notification === 'undefined') return;
      try {
        let perm = Notification.permission;
        if (perm === 'default') perm = await Notification.requestPermission();
        if (perm === 'granted') new Notification(t('pipeline.reindex.notifyTitle'), { body: message });
      } catch (_e) { /* Notification bloccata/non disponibile: il toast basta comunque. */ }
    }

    function pollReindexJob(jobId, box) {
      const revision = sessionRevision;
      const POLL_MS = 4000;
      let finish;
      retainWorkspaceTask(new Promise(resolve => { finish = resolve; }));
      const tick = async () => {
        if (revision !== sessionRevision) { finish(); return; }
        let job, missing = false;
        try {
          const res = await fetch(`/api/reindex/${jobId}`);
          if (!res.ok) {
            missing = res.status === 404;
            throw new Error(`HTTP ${res.status}`);
          }
          job = await res.json();
        } catch (e) {
          if (revision !== sessionRevision) { finish(); return; }
          box.textContent += '\n⚠ ' + t('pipeline.reindex.pollError', { id: jobId, msg: e.message }) + '\n';
          box.scrollTop = box.scrollHeight;
          // Senza stato terminale il job può ancora lavorare: il frame resta residente.
          if (missing) finish(); else setTimeout(tick, POLL_MS);
          return;
        }
        if (revision !== sessionRevision) { finish(); return; }
        if (!_TERMINAL_REINDEX_STATES.includes(job.status)) { setTimeout(tick, POLL_MS); return; }
        const ok = job.status === 'completed';
        const label = reindexStatusLabel(job.status);
        const message = t('pipeline.reindex.doneMsg', { label, id: jobId });
        box.textContent += `\n${ok ? '✅' : '⚠'} ${message}\n`;
        box.scrollTop = box.scrollHeight;
        notifyReindexDone(message, ok);
        finish();
      };
      setTimeout(tick, POLL_MS);
    }

    async function copyFinalPrompt(btn) {
      try {
        const runner = document.getElementById('agent-runner-select').value;
        const mode = document.getElementById('agent-mode-select').value;
        const text = await fetchFinalPrompt(featureName, devType, 'external', mode, runner);
        await navigator.clipboard.writeText(text);
        const original = btn.textContent;
        btn.textContent = t('pipeline.prompt.copied');
        setTimeout(() => { btn.textContent = original; }, 1500);
      } catch (err) {
        toast(err.message, 'error');
        const original = btn.textContent;
        btn.textContent = t('pipeline.prompt.copyFailed');
        setTimeout(() => { btn.textContent = original; }, 1500);
      }
    }

    /* ──────────── DRY-RUN CANVAS (nessun token speso) ──────────── */
    async function runCanvasDryRun() {
      const name = getFeatureName();
      if (!name) { document.getElementById('feature-name-input').focus(); return; }
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      const btn = document.getElementById('canvas-dryrun-btn');
      const card = document.getElementById('dryrun-card');
      const body = document.getElementById('dryrun-body');
      btn.disabled = true;
      card.classList.remove('hidden');
      body.innerHTML = `<span class="text-slate-400">${t('pipeline.canvas.dryrunLoading')}</span>`;
      try {
        const res = await fetch('/api/pipeline/canvas/dry-run', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature_name: featureName, dev_type: devType }),
        });
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        const data = await res.json();
        if (revision !== sessionRevision) return;
        if (data.note) { body.innerHTML = `<span class="text-amber-400">${escapeHtml(data.note)}</span>`; return; }
        const fmt = v => (v === null || v === undefined) ? '—' : (typeof v === 'number' ? v.toFixed(3) : escapeHtml(v));
        // `branch` distingue il ramo di dominio da quello tecnico (scoping per dev_type):
        // senza, due sezioni con punteggi simili sembrerebbero venire dalla stessa domanda.
        // doc_id e section sono nomi e titoli del corpus (anche importati da file esterni),
        // branch e note/e.message arrivano dal server: tutto passa da escapeHtml (shared.js),
        // altrimenti un titolo `<img onerror=…>` verrebbe eseguito in questo pannello.
        const src = (data.sources || []).map(s =>
          `<div class="flex justify-between gap-2 border-b border-slate-800 py-1"><span class="font-mono truncate">${s.branch ? `<span class="text-blue-400">[${escapeHtml(s.branch)}]</span> ` : ''}${escapeHtml(s.doc_id)}${s.section ? ' § ' + escapeHtml(s.section) : ''}</span><span class="font-mono text-slate-400 shrink-0">D ${fmt(s.dense_score)} · S ${fmt(s.sparse_score)} · CB ${fmt(s.colbert_score)} · A ${fmt(s.authority)}</span></div>`).join('') || `<span class="text-slate-400">${t('pipeline.canvas.noSources')}</span>`;
        const gov = (data.governed_docs || []).map(g =>
          `<span class="inline-block mr-2 mb-1 rounded border border-slate-700 px-2 py-0.5">${escapeHtml(g.doc_id)} <span class="text-blue-400">A ${fmt(g.authority)}</span> · ${g.chars} char</span>`).join('') || `<span class="text-slate-400">${t('pipeline.canvas.none')}</span>`;
        body.innerHTML = `<div class="mb-2"><div class="text-slate-400 mb-1">${t('pipeline.canvas.retrieval')}</div>${src}</div>
          <div><div class="text-slate-400 mb-1">${t('pipeline.canvas.governed')}</div>${gov}</div>`;
      } catch (e) {
        if (revision !== sessionRevision) return;
        body.innerHTML = `<span class="text-red-400">❌ ${escapeHtml(e.message)}</span>`;
      } finally { if (revision === sessionRevision) btn.disabled = false; }
    }

    /* ──────────── AGENT CONTEXT (blocco strutturato + confidence, Art. 1) ──────────── */
    async function loadAgentContext() {
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      const revision = sessionRevision;
      const btn = document.getElementById('agent-context-btn');
      const wrap = document.getElementById('agent-context-wrap');
      const box = document.getElementById('agent-context-box');
      btn.disabled = true;
      wrap.classList.remove('hidden');
      box.textContent = t('pipeline.prompt.contextLoading');
      try {
        const res = await fetch(`/api/pipeline/agent-context?feature=${encodeURIComponent(featureName)}&dev_type=${encodeURIComponent(devType)}`);
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        const data = await res.json();
        if (revision !== sessionRevision) return;
        document.getElementById('agent-confidence').textContent = `${data.confidence} (${data.confidence_label})`;
        box.textContent = data.text || t('pipeline.prompt.empty');
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent = t('pipeline.err.prefix', { msg: e.message });
      } finally { if (revision === sessionRevision) btn.disabled = false; }
    }

    /* ──────────── EXPORT JSON del design contract ──────────── */
    async function exportBundle() {
      if (!featureName) { toast(t('pipeline.feature.loadFirst'), 'error'); return; }
      try {
        const res = await fetch(`/api/pipeline/export?feature=${encodeURIComponent(featureName)}&dev_type=${encodeURIComponent(devType)}`);
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `${data.feature_folder || 'feature'}.contract.json`;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        toast(t('pipeline.prompt.exportError', { msg: e.message }), 'error');
      }
    }

    /* ──────────── SHARED: SAVE EDITED MD FILE ──────────── */
    async function saveMdFile(name, editorId) {
      if (!featureName) return;
      if (sessionLoading || pendingDraft) {
        toast(t('pipeline.session.chooseDraft'), 'error');
        return;
      }
      const savingFeature = featureName;
      const content = document.getElementById(editorId).value;
      try {
        const res = await fetch('/api/pipeline/file/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ feature: savingFeature, name, content }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (name === 'spec.md') {
          const data = await res.json();
          if (featureName === savingFeature && document.getElementById(editorId).value === content) {
            document.getElementById('spec-open-points-status').textContent = openPointsSummary(data);
          }
        }
        await refreshFilesControl();
      } catch (e) {
        toast(t('pipeline.review.saveError', { name, msg: e.message }), 'error');
      }
    }

    /* Ctrl+Enter per inviare in chat */
    document.getElementById('chat-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) retainWorkspaceTask(sendExploreTurn()).catch(error => console.error(error));
    });

    document.getElementById('dev-type-new-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); retainWorkspaceTask(addDevType()).catch(error => console.error(error)); }
    });

    /* Popola subito la tendina dei tipi di sviluppo, ancora prima di caricare una feature */
    resumePipelineSession();
    loadRunners();

    for (const id of [...draftEditors, 'chat-input']) {
      document.getElementById(id).addEventListener('input', savePipelineDraft);
    }
    document.getElementById('feature-name-input').addEventListener('change', () => retainWorkspaceTask(loadFeatureStatus()));
    document.getElementById('feature-name-input').addEventListener('input', updateChatControls);
    document.getElementById('session-status').textContent = t('pipeline.session.draftsLocalOnly');
    updateChatControls();

    window.onLangChange = function () {
      updateChatControls();
      for (let i = 1; i <= 5; i++) setStepState(i, stepStates[i]);
      if (featureName) refreshFilesControl();
      else {
        const list = document.getElementById('files-control-list');
        if (list) list.innerHTML = `<p class="text-slate-400">${t('pipeline.files.empty')}</p>`;
      }
      if (!pendingDraft && !sessionLoading) {
        document.getElementById('session-status').textContent = t('pipeline.session.draftsLocalOnly');
      }
      if (gateReview) renderDecisionEditor(gateReview.data);
      syncAttemptsAvailability();
      fillAttempts();
      const specStatus = document.getElementById('spec-open-points-status');
      if (specStatus && !document.getElementById('spec-md-editor').value) {
        specStatus.textContent = openPointsSummary({});
      }
    };

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
      addDevType: () => addDevType(),
      focusGuideStep: el => focusGuideStep(el.dataset.arg),
      restorePipelineDraft: () => restorePipelineDraft(),
      discardPipelineDraft: () => discardPipelineDraft(),
      approveAndGoToCanvas: () => approveAndGoToCanvas(),
      approveAndGoToPropose: () => approveAndGoToPropose(),
      approveSpec: () => approveSpec(),
      compareValidatedVersion: () => compareValidatedVersion(),
      copyFinalPrompt: el => copyFinalPrompt(el),
      exportBundle: () => exportBundle(),
      finishExplore: () => finishExplore(),
      generateCanvas: () => generateCanvas(),
      generatePropose: () => generatePropose(),
      goToStep: el => goToStep(Number(el.dataset.arg)),
      loadAgentContext: () => loadAgentContext(),
      loadFeatureStatus: () => loadFeatureStatus(),
      onDevTypeChange: () => onDevTypeChange(),
      onRunnerChange: () => onRunnerChange(),
      refreshGateReview: () => refreshGateReview(),
      runArchive: () => runArchive(),
      runCanvasDryRun: () => runCanvasDryRun(),
      runDriftCheck: () => runDriftCheck(),
      runValidate: () => runValidate(),
      runWithAgent: () => runWithAgent(),
      saveMdFile: el => saveMdFile(el.dataset.arg, el.dataset.arg2),
      sendExploreTurn: () => sendExploreTurn(),
      specEdited: () => { document.getElementById('spec-open-points-status').textContent = t('pipeline.review.unsaved'); },
      syncAttemptsAvailability: () => syncAttemptsAvailability(),
    });
