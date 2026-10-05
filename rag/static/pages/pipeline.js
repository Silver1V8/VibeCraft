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
      document.getElementById('dev-type-select').disabled = !!draft;
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
        sessionStatus(`Ultimo salvataggio locale: ${new Date(draft.savedAt).toLocaleString()}. Solo in questo browser.`);
      } catch (_) {
        sessionStatus('Bozza non salvata: memoria del browser non disponibile o piena. Salva i documenti sul server.');
      }
    }

    function offerPipelineDraft() {
      try {
        const raw = localStorage.getItem(draftKey(featureName));
        if (!raw) { sessionStatus('Le modifiche saranno salvate localmente in questo browser.'); return; }
        const draft = JSON.parse(raw);
        if (draft?.version !== 1 || draft.feature !== featureName || !Number.isFinite(Date.parse(draft.savedAt))
          || !Number.isInteger(draft.step) || draft.step < 1 || draft.step > 5
          || !['devType', 'exploreHistory', 'interviewLog', 'input'].every(key => typeof draft[key] === 'string')
          || !Array.isArray(draft.editors) || draft.editors.length !== 3 || !draft.editors.every(text => typeof text === 'string')
          || !Array.isArray(draft.messages) || !draft.messages.every(m => m && ['user', 'ai'].includes(m.role) && typeof m.text === 'string')) {
          throw new Error('invalid draft');
        }
        choosePipelineDraft(draft);
        sessionStatus(`Bozza locale del ${new Date(draft.savedAt).toLocaleString()}. Ora sono visibili i file server: ripristina la bozza negli editor oppure scartala per continuare. Operazioni interrotte non vengono riavviate.`);
      } catch (_) {
        sessionStatus('Bozza locale non valida o memoria del browser non disponibile. I file server restano utilizzabili.');
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
      document.getElementById('dev-type-select').value = draft.devType;
      devType = document.getElementById('dev-type-select').value;
      draftEditors.forEach((id, i) => {
        document.getElementById(id).value = draft.editors[i];
        setPanelVisible(['review-explore', 'review-canvas', 'review-spec'][i], !!draft.editors[i]);
        setStepState(i + 1, draft.editors[i] ? 'warning' : 'pending', draft.editors[i] ? 'bozza locale' : undefined);
      });
      document.getElementById('spec-open-points-status').textContent = 'Bozza locale: salva e verifica prima di procedere.';
      goToStep(draft.step);
      sessionLoading = false;
      sessionStatus(`Bozza locale ripristinata, salvata il ${new Date(draft.savedAt).toLocaleString()}. I file server non sono stati modificati.`);
    }

    function discardPipelineDraft() {
      if (!pendingDraft || sessionLoading) return;
      try { localStorage.removeItem(draftKey(featureName)); }
      catch (_) { sessionStatus('Impossibile scartare la bozza: memoria del browser non disponibile.'); return; }
      choosePipelineDraft(null);
      savePipelineDraft();
    }

    async function ensurePipelineFeature() {
      if (!getFeatureName()) { document.getElementById('feature-name-input').focus(); return false; }
      if (getFeatureName() !== featureName) await loadFeatureStatus();
      if (sessionLoading || pendingDraft) {
        toast('Attendi il caricamento e scegli se ripristinare o scartare la bozza locale.', 'error');
        return false;
      }
      return true;
    }

    async function resumePipelineSession() {
      let last;
      try { last = localStorage.getItem(lastFeatureKey); }
      catch (_) { sessionStatus('Recupero locale non disponibile: memoria del browser non accessibile.'); }
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
    }

    /* Popola la tendina con le sottocartelle reali di code/ (backend, frontend, logicAgent, ...). */
    async function loadDevTypes(selected) {
      const revision = sessionRevision;
      const select = document.getElementById('dev-type-select');
      try {
        const res = await fetch('/api/pipeline/dev-types');
        const data = await res.json();
        if (revision !== sessionRevision) return;
        const options = ['<option value="">— seleziona —</option>']
          .concat(data.dev_types.map(t => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`));
        select.innerHTML = options.join('');
      } catch (e) {
        if (revision !== sessionRevision) return;
        select.innerHTML = '<option value="">— errore caricamento —</option>';
      }
      if (selected) select.value = selected;
      devType = select.value;
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
        toast('Inserisci prima il nome della feature.', 'error');
        return;
      }
      currentStep = step;
      [1, 2, 3, 4, 5].forEach(i => {
        setPanelVisible(`panel-step-${i}`, i === step);
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
      pending: { glifo: n => String(n), stato: 'pending', label: 'in attesa' },
      current: { glifo: n => String(n), stato: 'current', label: 'in corso' },
      running: { glifo: () => '⋯',      stato: 'running', label: 'in esecuzione…' },
      done:    { glifo: () => '✓',      stato: 'done',    label: 'completato' },
      warning: { glifo: () => '⚠',      stato: 'warning', label: 'con avvisi' },
      failed:  { glifo: () => '✕',      stato: 'failed',  label: 'fallito' },
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
      badge.textContent = label || s.label;
      badge.className = `mt-1 text-xs font-mono step-badge-${s.stato}`;
      const line = document.getElementById(`step-line-${step}`);
      if (line) line.classList.toggle('done', state === 'done');
    }

    /* Manteniamo markStepDone come alias: è chiamato da parecchi punti e questo
       evita un refactor a tappeto per un rename. */
    function markStepDone(step, label) { setStepState(step, 'done', label || 'generato'); }

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
            <span class="${ok ? 'text-emerald-300' : 'text-slate-400'} font-semibold">${ok ? '✅ pronto' : '— assente'}</span>
          </div>`;
        }).join('');

        if (data.files.explore) markStepDone(1, 'generato');
        if (data.files.canvas) markStepDone(2, 'generato');
        if (data.files.spec) markStepDone(3, 'generato');

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
      document.getElementById('chat-send-btn').disabled = false;
      document.getElementById('chat-finish-btn').disabled = false;
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
      catch (_) { sessionStatus('Recupero locale non disponibile: memoria del browser non accessibile.'); }
    }

    /* ──────────── STEP 1: EXPLORE ──────────── */
    function appendChatBubble(role, text) {
      chatMessages.push({role, text});
      const log = document.getElementById('chat-log');
      const isUser = role === 'user';
      const bubble = document.createElement('div');
      bubble.className = `fade-in max-w-[80%] rounded-xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
        isUser ? 'self-end bg-blue-600 text-white' : 'self-start bg-slate-800 text-slate-100'
      }`;
      bubble.textContent = text;
      log.appendChild(bubble);
      log.scrollTop = log.scrollHeight;
    }

    async function sendExploreTurn() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!devType) { toast('Seleziona prima il tipo di sviluppo.', 'error'); return; }

      const input = document.getElementById('chat-input');
      const userInput = input.value.trim();
      if (!userInput) { input.focus(); return; }

      appendChatBubble('user', userInput);
      interviewLog += `**Utente:** ${userInput}\n\n`;
      input.value = '';
      savePipelineDraft();

      const sendBtn = document.getElementById('chat-send-btn');
      sendBtn.disabled = true;
      document.getElementById('explore-status').textContent = 'IA sta rispondendo…';

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
        appendChatBubble('ai', `❌ Errore: ${e.message}`);
        document.getElementById('explore-status').textContent = 'Errore di connessione';
      } finally {
        if (revision === sessionRevision) { sendBtn.disabled = false; input.focus(); }
      }
    }

    async function finishExplore() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!devType) { toast('Seleziona prima il tipo di sviluppo.', 'error'); return; }

      if (!interviewLog) {
        toast("Nessuna risposta registrata nell'intervista: scrivi almeno un turno prima di terminare.", 'error');
        return;
      }

      const btn = document.getElementById('chat-finish-btn');
      btn.disabled = true;
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
        markStepDone(1, 'generato');
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(`Errore nel salvataggio di explore.md: ${e.message}`, 'error');
      } finally {
        if (revision === sessionRevision) btn.disabled = false;
      }
    }

    function approveAndGoToCanvas() {
      goToStep(2);
    }

    /* ──────────── STEP 2: CANVAS ──────────── */
    async function generateCanvas() {
      if (!await ensurePipelineFeature()) return;
      const revision = sessionRevision;
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      if (!devType) { toast('Seleziona prima il tipo di sviluppo.', 'error'); return; }
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
        markStepDone(2, 'generato');
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(`Errore nella generazione del Canvas: ${e.message}`, 'error');
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
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      if (!devType) { toast('Seleziona prima il tipo di sviluppo.', 'error'); return; }
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
        markStepDone(3, 'generato');
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        toast(`Errore nella generazione delle specifiche: ${e.message}`, 'error');
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
      return gateMessages(detail).join('\n') || 'Richiesta non riuscita';
    }

    const validationRefs = new Map();
    const blockedAttempts = new Map();
    function gateMessages(gate) {
      return [...(gate.reasons || []), ...(gate.warnings || [])].map(item =>
        [item.code, item.action, item.message, item.next_step,
          item.changed?.length ? `Elementi cambiati: ${item.changed.join(', ')}` : ''].filter(Boolean).join(' · '));
    }

    function describeFinding(f) {
      const who = f.covered_by;
      const coverage = who ? `coperto da ${who.decision_id} · nome dichiarato: ${who.declared_by} · ${who.recorded_at} · origin_verified: false`
        : 'non esaminato / non coperto';
      return `${f.rule || f.kind} · ${f.message}\n${coverage}`;
    }

    function admissionSummary(gate) {
      if (gate?.allowed === true) return 'Avvio agentic: consentito';
      const reason = gate?.allowed === false
        ? (gate.reasons || []).map(item => item.message).filter(Boolean).join('; ') || 'motivo non disponibile'
        : 'stato del gate non disponibile';
      return `Avvio agentic: bloccato — ${reason}`;
    }

    function validationSummary(data) {
      const statuses = [data.checks?.structural?.status, data.checks?.semantic?.status];
      const checks = statuses.some(status => !['pass', 'fail'].includes(status)) ? 'non disponibili'
        : statuses.includes('fail') ? 'falliti' : 'superati';
      const lines = [`Controlli di validazione: ${checks}`, admissionSummary(data.gate),
        `Validazione ${data.validation_id}: ${data.status}`, data.validation_error || data.report || ''];
      lines.push(...(data.structural_findings || []).map(describeFinding));
      lines.push(...(data.semantic_findings || []).map(describeFinding));
      if (data.suggestions?.length) lines.push('Suggerimenti facoltativi — nessun effetto sul gate:\n'
        + data.suggestions.map(text => `• ${text}`).join('\n'));
      lines.push('Le lacune coperte da decisione non sono scenari soddisfatti.');
      if (data.scenario_scope?.off_scope?.length) lines.push('Rilievi euristici di pertinenza (advisory): ' + JSON.stringify(data.scenario_scope.off_scope));
      lines.push(...gateMessages(data.gate || {}));
      return lines.filter(Boolean).join('\n\n');
    }

    async function runValidate() {
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      const validatingFeature = featureName;
      const btn = document.getElementById('validate-btn');
      const box = document.getElementById('validate-report-box');
      btn.disabled = true;
      box.classList.remove('hidden');
      box.textContent = 'Validazione in corso…';
      try {
        const res = await fetch('/api/pipeline/validate', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({feature: validatingFeature})});
        const data = await res.json();
        if (featureName !== validatingFeature) return;
        if (!res.ok && data.status !== 'unavailable') throw new Error(gateApiError(data));
        validationRefs.set(validatingFeature, data.validation_id || null);
        box.textContent = validationSummary(data);
        document.getElementById('validate-structural').textContent = `Controlli: ${data.checks?.structural?.status || 'unavailable'} / ${data.checks?.semantic?.status || 'unavailable'}`;
        await refreshGateReview();
      } catch (e) {
        if (featureName === validatingFeature) box.textContent = `Validazione non disponibile: ${e.message}`;
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
          data.validation_id ? `Validazione: ${data.validation_id}` : 'Validazione assente.',
          `Stato resoconto: ${data.gate.open_points_status ?? 'non leggibile'}`,
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
      host.textContent = comparison ? `Confronto con la validazione ${comparison.validation_id}`
        : 'Confronto non disponibile: versione validata assente o non leggibile.';
      if (!comparison) return;
      for (const name of ['canvas', 'spec']) {
        const row = document.createElement('div');
        row.className = 'grid grid-cols-1 md:grid-cols-2 gap-2 my-2';
        for (const [key, label] of [['current', 'corrente salvato'], ['validated', 'validato']]) {
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
      element('p', "L'accettazione non è esposta agli strumenti dell'agente; non è certificata come decisione umana dalla credenziale condivisa.");
      if (!Array.isArray(data.point_decisions)) { element('p', 'Resoconto assente o invalido: correggilo prima di decidere.'); return; }
      if (!data.point_decisions.length) { element('p', 'Nessun punto aperto dichiarato.'); return; }
      for (const p of data.point_decisions) element('pre', `${p.point.id} · ${p.status}\n${JSON.stringify(p.point, null, 2)}` +
        (p.decision ? `\nDecisione ${p.decision.decision_id} · nome dichiarato ${p.decision.declared_by} · ${p.decision.recorded_at} · origin_verified: false\n${p.decision.motivation}` : ''));
      element('label', 'Punto esaminato').htmlFor = 'decision-point';
      const points = element('select', '', 'decision-point');
      points.add(new Option('Seleziona il punto esaminato', ''));
      for (const p of data.point_decisions) points.add(new Option(`${p.point.id}: ${p.point.question}`, p.point_hash));
      element('label', 'Decisione esplicita').htmlFor = 'decision-status';
      const status = element('select', '', 'decision-status');
      status.add(new Option('Seleziona la decisione', ''));
      status.add(new Option('Accetto la lacuna e procedo', 'accepted'));
      status.add(new Option('Registro la risoluzione', 'resolved'));
      element('label', 'Nome dichiarato (non identità verificata)', 'decision-by-label').htmlFor = 'decision-by';
      element('input', '', 'decision-by');
      element('label', 'Motivazione / risoluzione', 'decision-reason-label').htmlFor = 'decision-reason';
      element('textarea', '', 'decision-reason');
      element('p', 'Associazioni esplicite: seleziona solo i rilievi di copertura esaminati per questo punto. Nessuna selezione automatica.');
      for (const f of data.structural_findings.filter(f => f.associable)) {
        const label = element('label', '');
        const check = document.createElement('input'); check.type = 'checkbox'; check.value = f.finding_hash;
        check.className = 'coverage-association'; label.appendChild(check);
        label.appendChild(document.createTextNode(describeFinding(f)));
      }
      const submit = element('button', 'Registra decisione', 'decision-submit');
      submit.onclick = recordPointDecision;
    }

    async function recordPointDecision() {
      const review = gateReview;
      if (!review || review.feature !== featureName) return;
      const value = id => document.getElementById(id).value.trim();
      const status = value('decision-status'), point = value('decision-point');
      const motivation = value('decision-reason'), declaredBy = value('decision-by');
      const hashes = [...document.querySelectorAll('#gate-decisions .coverage-association:checked')].map(n => n.value);
      if (!point || !status || !motivation || !declaredBy) { toast('Seleziona punto e decisione, indica nome dichiarato e motivazione.', 'error'); return; }
      if (hashes.length && status !== 'accepted') { toast('Solo accepted può coprire un rilievo.', 'error'); return; }
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
        if (featureName === review.feature) { await refreshGateReview(); toast('Decisione registrata. Rivalida il contratto.'); }
      } catch (e) { toast(e.message, 'error'); }
      finally { btn.disabled = false; }
    }

    /* ──────────── ESECUZIONE CON CLAUDE AGENT SDK ──────────── */
    function openPointsSummary(data) {
      const limits = '\nRicerca advisory: novità delle evidenze e riuso degli ID non verificati; validità solo strutturale.';
      if (data.open_points_status === 'invalid') {
        return '❌ Resoconto malformato: ' + (data.open_points_error || 'schema non valido') + limits;
      }
      if (data.open_points_status !== 'valid') return '⚠ Resoconto assente: punti aperti non determinabili.' + limits;
      if (!Array.isArray(data.open_points)) return '❌ Resoconto malformato: open_points non è una lista.' + limits;
      if (!data.open_points.length) return 'Terminato senza punti aperti (dichiarazione dell’agente).' + limits;
      return `⚠ ${data.open_points.length} punti aperti dichiarati:\n` + data.open_points.map(p =>
        `${p.id} · ${p.reason} · ${p.original_question}\nDomanda attuale: ${p.question}`
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
        const option = new Option(r.available ? r.label : `${r.label} (${r.unavailable_reason || 'non installato'})`, r.id);
        option.disabled = !(r.export_available ?? r.available);
        select.add(option);
      }
      select.value = (agentRunners.find(r => r.available) || agentRunners[0] || {}).id || 'claude';
      onRunnerChange();
    }

    /* Opzioni della tendina "Tentativi", dal tetto dichiarato dal server: offrirne di più
       significherebbe far scegliere un numero che il server poi taglia in silenzio. */
    function fillAttempts(ceiling) {
      const select = document.getElementById('agent-attempts-select');
      const previous = select.value;
      const max = Math.max(1, Math.min(Number(ceiling) || 1, 10));
      select.textContent = '';
      for (let n = 1; n <= max; n++) {
        select.add(new Option(n === 1 ? '1 · nessun rilancio' : `${n} · rilancia se la suite è rossa`, String(n)));
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
        ? 'Rilanci automatici finché la suite dell\'ambito non passa'
        : 'Solo in modalità Agentic: le altre non scrivono codice da verificare';
    }

    function onRunnerChange() {
      const runner = agentRunners.find(r => r.id === document.getElementById('agent-runner-select').value);
      if (!runner) return;
      const models = document.getElementById('agent-model-select');
      models.textContent = '';
      if (!runner.models.length) models.add(new Option('Modello predefinito', ''));
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
      btn.title = runner?.available === false ? runner.unavailable_reason || 'Runner non disponibile.' : '';
    }

    async function runWithAgent() {
      if (agentRunning) return;
      const revision = sessionRevision;
      const mode = document.getElementById('agent-mode-select').value;
      const model = document.getElementById('agent-model-select').value;
      const runner = document.getElementById('agent-runner-select').value;
      const capability = agentRunners.find(r => r.id === runner);
      if (capability?.available === false) {
        toast(capability.unavailable_reason || 'Runner non disponibile.', 'error');
        return;
      }
      // Fuori da agentic la tendina è spenta e il server non verifica: chiedere rilanci
      // sarebbe una richiesta senza effetto.
      const attempts = mode === 'agentic' ? Number(document.getElementById('agent-attempts-select').value) || 1 : 1;
      // La modalità determina tool e contesto: niente fallback sul prompt HTTP esterno.
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      const runningFeature = featureName;
      await refreshGateReview();
      if (revision !== sessionRevision || featureName !== runningFeature) return;
      let prompt;
      try {
        if (mode !== 'agentic') prompt = await fetchFinalPrompt(runningFeature, devType, 'agent', mode, runner);
      } catch (err) { toast(err.message, 'error'); return; }
      if (mode === 'agentic' && !await confirmDialog(
        'La modalità Agentic scrive file nel progetto. Continuare?',
        { title: 'Modalità Agentic', confirmText: 'Continua', danger: true }
      )) return;
      if (revision !== sessionRevision || featureName !== runningFeature) return;

      if (agentRunning) return;
      agentRunning = true;
      const btn = document.getElementById('agent-run-btn');
      const out = document.getElementById('agent-output');
      btn.disabled = true;
      out.style.display = '';
      out.textContent = `⏳ Avvio ${runner} (${model || 'modello predefinito'}) in modalità "${mode}"…\n\n`;

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
            out.textContent += `Avvio bloccato dal server · validazione: ${gate.validation_id || 'assente'} · tentativo: ${gate.attempt_id || 'non registrato'}\n`;
            if (gate.retry_of_attempt_id) out.textContent += `Ripresa del tentativo: ${gate.retry_of_attempt_id}\n`;
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
              out.textContent += `Gate del server${mode === 'agentic' ? '' : ' (advisory)'} · validazione: ${ev.gate.validation_id || 'assente'} · tentativo: ${ev.attempt_id || 'non registrato'}\n`;
              out.textContent += gateMessages(ev.gate).join('\n') + '\n';
            } else if (ev.type === 'text') {
              out.textContent += ev.text + '\n';
            } else if (ev.type === 'tool_use') {
              out.textContent += `  🔧 [${ev.tool}]\n`;
            } else if (ev.type === 'result') {
              terminated = true;
              const secs = ev.duration_ms != null ? (ev.duration_ms / 1000).toFixed(1) + 's' : '—';
              const cost = ev.total_cost_usd != null ? '$' + ev.total_cost_usd.toFixed(4) : '—';
              out.textContent += `\n${ev.is_error ? '❌ Terminato con errore' : 'Esecuzione terminata'} · ${secs} · ${cost} · ${ev.num_turns ?? '—'} turni\n${openPointsSummary(ev)}\n`;
            } else if (ev.type === 'error') {
              terminated = true;
              out.textContent += `\n❌ Errore: ${ev.message}\n${openPointsSummary(ev)}\n`;
            } else if (ev.type === 'verification') {
              // Esito della suite ESEGUITA dal server: l'unica riga di questo output che non
              // riporta una dichiarazione dell'agente.
              const icona = ev.status === 'passed' ? '✅' : (ev.status === 'failed' ? '❌' : '⚠️');
              const comando = ev.command && ev.command.length ? ev.command.join(' ') : '—';
              out.textContent += `\n${icona} Verifica eseguita dal server · code/${ev.dev_type} · ${comando}`
                + ` · esito: ${ev.status}${ev.exit_code != null ? ` (exit ${ev.exit_code})` : ''}`
                + ` · ${ev.duration_seconds}s\n`;
              if (ev.reason) out.textContent += `   ${ev.reason}\n`;
              if (ev.status === 'unavailable') {
                out.textContent += '   La feature resta NON verificata: manca lo strumento di misura, non si ritenta.\n';
              }
              if (ev.output_tail) out.textContent += ev.output_tail.trimEnd() + '\n';
              if (ev.status === 'failed' && ev.attempts_left === 0) {
                out.textContent += '   Nessun tentativo rimasto: la feature resta NON verificata.\n';
              }
            } else if (ev.type === 'retry') {
              out.textContent += `\n🔁 Rilancio dell'agente con le failure in prompt · tentativo ${ev.attempt_id}`
                + ` (ripresa di ${ev.retry_of_attempt_id}) · ancora ${ev.attempts_left} dopo questo\n\n`;
            } else if (ev.type === 'retry_blocked') {
              terminated = true;
              out.textContent += `\n⚠️ Rilancio non effettuato: ${ev.detail}\n`;
            } else if (ev.type === 'verification_unrecorded') {
              out.textContent += `\n⚠️ Esito della verifica non registrato nel journal: ${ev.detail}\n`;
            }
            out.scrollTop = out.scrollHeight;
        });
        if (revision === sessionRevision && !terminated) throw new Error('Stream interrotto senza risultato finale');
      } catch (e) {
        if (revision !== sessionRevision) return;
        out.textContent += `\n❌ Errore: ${e.message}\n${openPointsSummary({})}\n`;
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
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
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
        const label = hadError || verdict.startsWith('❌') ? 'verifica fallita'
          : verdict.startsWith('⚠️ DRIFT') ? 'drift rilevato'
          : verdict.startsWith('⚠️ PUNTI APERTI') ? 'punti aperti da decidere'
          : clean ? 'verificato' : 'verifica incompleta';
        setStepState(4, clean ? 'done' : 'failed', label);
        if (!clean) toast(`Drift check: ${label}. Leggi il report.`, 'warning');
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent += `\n❌ Errore: ${e.message}`;
        setStepState(4, 'failed', 'verifica fallita');
        toast(`Verifica del drift fallita: ${e.message}`, 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('drift-loader', false); }
      }
    }

    /* ──────────── STEP 5: ARCHIVIAZIONE + RE-INDICIZZAZIONE (streaming) ──────────── */
    async function runArchive() {
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      const revision = sessionRevision;
      if (!await confirmDialog(
        `Archiviare la feature "${featureName}" e ricostruire il Graph RAG?\nLa cartella verrà spostata in changes/archive/ e l'operazione non è reversibile dall'interfaccia.`,
        { title: 'Archiviazione feature', confirmText: 'Archivia', danger: true }
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
          else if (ev.type === 'reloaded') box.textContent += '\n🔄 Indice ricaricato in memoria.\n';
          else if (ev.type === 'reindex_queued') {
            archived = true;
            box.textContent += `\n🔄 Re-indicizzazione accodata, job ${ev.job_id} (stato su /api/reindex/${ev.job_id}).\n`;
            pollReindexJob(ev.job_id, box);
          }
          else if (ev.type === 'error') { hadError = true; box.textContent += `\n❌ ${ev.message}\n`; }
          box.scrollTop = box.scrollHeight;
        });
        if (revision !== sessionRevision) return;
        if (!hadError && !archived) throw new Error('Stream interrotto senza conferma di archiviazione');
        setStepState(5, hadError ? 'failed' : 'done', hadError ? 'errori in archiviazione' : 'archiviato');
        await refreshFilesControl();
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent += `\n❌ Errore: ${e.message}`;
        setStepState(5, 'failed', 'archiviazione fallita');
        toast(`Archiviazione fallita: ${e.message}`, 'error');
      } finally {
        if (revision === sessionRevision) { btn.disabled = false; setPanelVisible('archive-loader', false); }
      }
    }

    /* ──────────── NOTIFICA A FINE RE-INDICIZZAZIONE (poll job in background) ──────────── */
    const _TERMINAL_REINDEX_STATES = ['completed', 'completed_not_promoted', 'failed', 'interrupted'];
    const _REINDEX_STATUS_LABELS = {
      completed: 'completata',
      completed_not_promoted: 'completata ma NON promossa (eval-gate sotto soglia)',
      failed: 'fallita',
      interrupted: 'interrotta',
    };

    async function notifyReindexDone(message, ok) {
      toast(message, ok ? 'success' : 'warning');
      if (typeof Notification === 'undefined') return;
      try {
        let perm = Notification.permission;
        if (perm === 'default') perm = await Notification.requestPermission();
        if (perm === 'granted') new Notification('VibeCraft — Re-indicizzazione', { body: message });
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
          box.textContent += `\n⚠ Impossibile verificare lo stato del job ${jobId}: ${e.message}\n`;
          box.scrollTop = box.scrollHeight;
          // Senza stato terminale il job può ancora lavorare: il frame resta residente.
          if (missing) finish(); else setTimeout(tick, POLL_MS);
          return;
        }
        if (revision !== sessionRevision) { finish(); return; }
        if (!_TERMINAL_REINDEX_STATES.includes(job.status)) { setTimeout(tick, POLL_MS); return; }
        const ok = job.status === 'completed';
        const label = _REINDEX_STATUS_LABELS[job.status] || job.status;
        const message = `Re-indicizzazione ${label} (job ${jobId}).`;
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
        btn.textContent = 'Copiato ✓';
        setTimeout(() => { btn.textContent = original; }, 1500);
      } catch (err) {
        toast(err.message, 'error');
        const original = btn.textContent;
        btn.textContent = 'Copia non riuscita';
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
      body.innerHTML = '<span class="text-slate-400">Recupero sorgenti…</span>';
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
          `<div class="flex justify-between gap-2 border-b border-slate-800 py-1"><span class="font-mono truncate">${s.branch ? `<span class="text-blue-400">[${escapeHtml(s.branch)}]</span> ` : ''}${escapeHtml(s.doc_id)}${s.section ? ' § ' + escapeHtml(s.section) : ''}</span><span class="font-mono text-slate-400 shrink-0">D ${fmt(s.dense_score)} · S ${fmt(s.sparse_score)} · CB ${fmt(s.colbert_score)} · A ${fmt(s.authority)}</span></div>`).join('') || '<span class="text-slate-400">nessuna sorgente</span>';
        const gov = (data.governed_docs || []).map(g =>
          `<span class="inline-block mr-2 mb-1 rounded border border-slate-700 px-2 py-0.5">${escapeHtml(g.doc_id)} <span class="text-blue-400">A ${fmt(g.authority)}</span> · ${g.chars} char</span>`).join('') || '<span class="text-slate-400">nessuno</span>';
        body.innerHTML = `<div class="mb-2"><div class="text-slate-400 mb-1">Retrieval (ranking ibrido):</div>${src}</div>
          <div><div class="text-slate-400 mb-1">Documenti normativi che verrebbero iniettati:</div>${gov}</div>`;
      } catch (e) {
        if (revision !== sessionRevision) return;
        body.innerHTML = `<span class="text-red-400">❌ ${escapeHtml(e.message)}</span>`;
      } finally { if (revision === sessionRevision) btn.disabled = false; }
    }

    /* ──────────── AGENT CONTEXT (blocco strutturato + confidence, Art. 1) ──────────── */
    async function loadAgentContext() {
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
      const revision = sessionRevision;
      const btn = document.getElementById('agent-context-btn');
      const wrap = document.getElementById('agent-context-wrap');
      const box = document.getElementById('agent-context-box');
      btn.disabled = true;
      wrap.classList.remove('hidden');
      box.textContent = '⏳ Costruzione del contesto…';
      try {
        const res = await fetch(`/api/pipeline/agent-context?feature=${encodeURIComponent(featureName)}&dev_type=${encodeURIComponent(devType)}`);
        if (!res.ok) { const e = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(apiErrorMessage(e.detail, `HTTP ${res.status}`)); }
        const data = await res.json();
        if (revision !== sessionRevision) return;
        document.getElementById('agent-confidence').textContent = `${data.confidence} (${data.confidence_label})`;
        box.textContent = data.text || '(vuoto)';
      } catch (e) {
        if (revision !== sessionRevision) return;
        box.textContent = `❌ Errore: ${e.message}`;
      } finally { if (revision === sessionRevision) btn.disabled = false; }
    }

    /* ──────────── EXPORT JSON del design contract ──────────── */
    async function exportBundle() {
      if (!featureName) { toast('Carica prima la feature.', 'error'); return; }
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
        toast(`Errore export: ${e.message}`, 'error');
      }
    }

    /* ──────────── SHARED: SAVE EDITED MD FILE ──────────── */
    async function saveMdFile(name, editorId) {
      if (!featureName) return;
      if (sessionLoading || pendingDraft) {
        toast('Scegli prima se ripristinare o scartare la bozza locale.', 'error');
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
        toast(`Errore nel salvataggio di ${name}: ${e.message}`, 'error');
      }
    }

    /* Ctrl+Enter per inviare in chat */
    document.getElementById('chat-input').addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) retainWorkspaceTask(sendExploreTurn()).catch(error => console.error(error));
    });

    /* Popola subito la tendina dei tipi di sviluppo, ancora prima di caricare una feature */
    resumePipelineSession();
    loadRunners();

    for (const id of [...draftEditors, 'chat-input']) {
      document.getElementById(id).addEventListener('input', savePipelineDraft);
    }
    document.getElementById('feature-name-input').addEventListener('change', () => retainWorkspaceTask(loadFeatureStatus()));

    /* Azioni dei pulsanti/campi (data-click / data-change / data-input): prima erano
       handler inline, vietati dalla CSP — vedi registerActions in /static/shared.js. */
    registerActions({
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
      specEdited: () => { document.getElementById('spec-open-points-status').textContent = '⚠ Modifiche non salvate: resoconto da verificare.'; },
      syncAttemptsAvailability: () => syncAttemptsAvailability(),
    });
