---
id: "vibe-coding-workflow-v1.0"
title: "Linee Guida di Co-Sviluppo AI & Vibe Coding Framework"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-06"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/04_knowledge_informative/vibe_coding_workflow.md"
source_document: "ANALISI_FUNZIONALE.md"
authors:
  - role: "AI Workflow Engineer"
  - role: "Solution Architect"
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "vibe-coding-workflow-v1.0"
  edges:
    - type: "DERIVA_DA"
      target: "ANALISI_FUNZIONALE"
      sections: ["6.1", "6.2", "6.3", "6.4"]
    - type: "REQUISITO_METODOLOGICO"
      target: "TUTTI_I_COMPITI_DI_SVILUPPO"
    - type: "INTEGRA"
      target: "glossario-entita-v1.0"
    - type: "INTEGRA"
      target: "safeguards-security-v1.0"
tags:
  - methodology
  - vibe-coding
  - human-in-the-loop
  - clean-code
  - token-optimization
  - workflow
  - cursor
  - claude-code
---

# Linee Guida di Co-Sviluppo AI & VibeCraft Framework
## `VibeCraft` — Protocollo Metodologico Operativo

> **⚠️ DIRETTIVA TASSATIVA PER L'AI CODING AGENT (Cursor / Claude Code)**
>
> Questo documento definisce il **Framework Metodologico di Sviluppo**. Non descrive le funzioni del software, ma governa in modo stringente il tuo comportamento operativo sul filesystem locale e le modalità di interazione con lo sviluppatore umano.
> 
> Sei obbligato ad agire secondo i principi del **Prompt-Driven Development regolato**. Devi interrompere l'esecuzione e richiedere una validazione umana esplicita ad ogni Checkpoint HITL (Human-in-the-loop) qui catalogato. Non ti è permesso bypassare, ignorare o auto-approvare alcuna transizione di task.

---

## Sezione 1 — Protocollo Human-in-the-Loop (HITL)

Il ciclo di vita dello sviluppo locale è rigidamente interrotto da checkpoint sequenziali. L'assenza di risposta o il silenzio dell'operatore non costituiscono mai un'approvazione implicita.

### `[REGOLA-HITL-01]` Checkpoint 1 — Approvazione del Piano di Implementazione
* **Trigger di Blocco:** Ricezione di un nuovo task di sviluppo o richiesta di modifica. Prima di toccare qualsiasi riga di codice, devi fermarti.
* **Azione Umana Richiesta:** Il supervisore deve analizzare, modificare e approvare esplicitamente il piano d'azione.
* **Input da Fornire al Supervisore:** Un elenco sintetico e atomico contenente:
  1. Le entità del Glossario coinvolte.
  2. Le regole di business dell'AFU applicate.
  3. L'albero esatto dei file che intendi creare o modificare.
  4. Eventuali scelte architetturali lasciate libere dalle specifiche.
* **Guardrail:** Se l'essere umano suboptimalizza o corregge il piano, devi rigenerarlo integrando i feedback. È fatto divieto assoluto di procedere alla scrittura del codice senza un messaggio umano di validazione esplicita.

### `[REGOLA-HITL-02]` Checkpoint 2 — Revisione del Codice Generato
* **Trigger di Blocco:** Completamento della scrittura del codice relativo a una singola funzionalità coerente (es. completamento del solo controller, prima di passare ai test).
* **Azione Umana Richiesta:** Ispezione del codice sorgente e code review.
* **Input da Fornire al Supervisore:** Presentazione del `git diff` completo, pulito e isolato del task appena eseguito.
* **Guardrail:** Non sono ammesse implementazioni cumulative o "a cascata" di più funzionalità senza checkpoint intermedi. Se l'utente richiede modifiche strutturali, devi applicarle sullo stesso file prima di procedere oltre.

### `[REGOLA-HITL-03]` Checkpoint 3 — Validazione dei Test Automatici
* **Trigger di Blocco:** Scrittura dei test unitari ed esecuzione della suite di test locali.
* **Azione Umana Richiesta:** Verifica della copertura dei casi limite e approvazione dell'esito del test runner.
* **Input da Fornire al Supervisore:** Report dell'esito dei test (green/red status) e codice sorgente dei casi di test generati.
* **Guardrail:** Ogni test deve verificare esplicitamente una regola numerata dell'AFU (con focus primario sulla concorrenza delle sezioni 2.3 e 4.3). Il compito è considerato incompleto finché la suite di test non è verificata con successo dall'operatore.

### `[REGOLA-HITL-04]` Checkpoint 4 — Test di Integrazione tra Moduli
* **Trigger di Blocco:** Integrazione cross-modulo o sottomissione di modifiche che impattano l'interazione tra Portale, Workflow o Admin.
* **Azione Umana Richiesta:** Validazione del flusso end-to-end simulato o reale.
* **Input da Fornire al Supervisore:** Log di integrazione, schemi di chiamata API aggiornati e documentazione degli impatti cross-modulo.
* **Guardrail:** Il merge o l'avanzamento logico verso il completamento del macro-modulo è congelato fino alla firma visiva umana.

### `[REGOLA-HITL-05]` Checkpoint 5 — Sign-Off Umano Finale
* **Trigger di Blocco:** Completamento dell'intero modulo e preparazione per il deployment locale o in staging.
* **Azione Umana Richiesta:** Dichiarazione formale di chiusura del ciclo di sviluppo.
* **Input da Fornire al Supervisore:** Checklist finale di conformità rispetto a tutte le regole delle Parti 0-5 dell'AFU.
* **Guardrail:** L'applicazione non può essere considerata pronta o distribuibile senza l'approvazione finale esplicita del supervisore.

### `[REGOLA-HITL-06]` Enforcement del Blocco Rigido
In nessun caso l'AI deve auto-approvare un proprio checkpoint o procedere oltre un checkpoint senza una risposta esplicita e positiva dell'essere umano. Il silenzio dell'utente o l'assenza di risposta non costituisce approvazione implicita.

---

## Sezione 2 — Standard di Scrittura Codice e Token Optimization

Direttive tecniche obbligatorie per garantire la pulizia, la modularità e il controllo dei costi della pipeline LLM.

### `[REGOLA-CLEAN-01]` Tracciabilità Bidirezionale nei Commenti
Ogni singola funzione, classe, metodo o blocco di controllo logico che implementa direttamente una o più regole di business numerate dell'AFU deve riportare nel proprio commento di intestazione il riferimento esplicito al codice della regola.

### `[REGOLA-CLEAN-02]` Limite Dinamico di Lunghezza del Corpo Funzione
Nessuna funzione o metodo deve superare la soglia tassativa delle 40 righe effettive di corpo, escludendo dal conteggio i commenti descrittivi e le righe vuote di spaziatura. Qualora la logica superi questo limite, sei obbligato a scomporre l'algoritmo in sotto-funzioni isolate dotate di nomi puramente semantici.

### `[REGOLA-CLEAN-03]` Allineamento Terminologico Rigido
È fatto divieto assoluto di introdurre termini linguistici o sinonimi non presenti nella documentazione ufficiale. I nomi di variabili, funzioni, database entity, colonne, rotte e classi devono ereditare la denominazione esatta del Glossario (es. usare esclusivamente `posti_residui`, è vietato usare `availableSeats`, `remainingSpots` o `posti_rimasti`).

### `[REGOLA-CLEAN-04]` Estrazione dei Magic Numbers e Parametrizzazione
Nessun valore costante o parametro numerico letterale deve comparire inline nel codice applicativo. Ogni valore statico (es. la soglia numerica '3' delle card o le 8 ore di scadenza della sessione) deve essere estratto in costanti nominate all'inizio del file o all'interno di file di configurazione dedicati.

### `[REGOLA-CLEAN-05]` Isolamento delle Regele di Business
La logica di validazione delle regole di business e l'enforcement dei vincoli logici devono essere interamente separati e disaccoppiati dal layer di presentazione dell'interfaccia utente (UI) e dal layer di persistenza dei dati (Repository/ORM). È vietato annidare regole decisionali dentro event handler del frontend o dentro query SQL grezze.

### `[REGOLA-CLEAN-06]` Unicità dell'Ambiente Transazionale per il Lock
Ogni operazione di database legata alla gestione della concorrenza deve essere racchiusa in un'unica ed esplicita funzione transazionale atomica server-side. La transazione non deve mai essere frammentata, sospesa o distribuita su più chiamate asincrone distinte o promesse non concatenate, al fine di evitare race condition.

### `[REGOLA-CLEAN-07]` Co-transazionalità Sincrona dell'Audit Log
La scrittura del record nella tabella `AUDIT_LOG` deve avvenire obbligatoriamente all'interno della medesima ed identica transazione database che applica la mutazione dello stato sull'entità tracciata. Il fallimento della scrittura dell'audit log deve provocare il rollback immediato della transazione di business.

### `[REGOLA-CLEAN-08]` Disaccoppiamento Asincrono delle Notifiche
Il sistema di invio e delivery delle notifiche (Email, Slack) deve essere totalmente isolato e asincrono rispetto alla transazione di database principale. Un eventuale blocco, timeout o fallimento di rete dei provider di notifica non deve mai propagarsi all'indietro o invalidare la transazione di approvazione o sottomissione della richiesta.

### `[REGOLA-CLEAN-09]` Divieto di Segreti Hardcoded
Nessun segreto, credenziale, o chiave di accesso (es. credenziali OAuth Google, token Slack/Email) deve comparire hardcoded nel codice sorgente in nessuna fase dello sviluppo, nemmeno temporaneamente o a scopo di test locale. Ogni configurazione sensibile deve essere agganciata esclusivamente tramite iniezione di variabili d'ambiente (`.env`) gestite localmente.

---

## Sezione 3 — Gestione delle Deviazioni (Edge Cases)

Protocollo di comportamento per l'agente in caso di imprevisti tecnici o lacune informative.

### `[REGOLA-DEV-01]` Supremazia dell'Analisi Funzionale
Questo documento costituisce la fonte di verità suprema del progetto. In presenza di discrepanze, conflitti logici o ambiguità tra il codice sorgente preesistente nel codebase e una regola descritta nell'AFU, l'agente deve fermarsi e dare la precedenza assoluta alla regola documentata.

### `[REGOLA-DEV-02]` Divieto di Iniziativa Funzionale Autonoma
È vietato introdurre funzionalità accessorie, campi aggiuntivi, ruoli utente o logiche di workflow che non siano esplicitamente decretate nelle sezioni delle Parti 0-5 del progetto. L'agente non deve fare assunzioni basate su preferenze personali o interpretazioni estensive.

### `[REGOLA-DEV-03]` Interruzione per Vuoto di Specifica (Edge Cases)
Qualora durante la scrittura del codice l'agente incontri una casistica limite, un errore tecnico o un comportamento non normato dalle specifiche, ha l'obbligo di:
1. Sospendere immediatamente lo sviluppo della funzionalità impattata.
2. Aprire una segnalazione strutturata descrivendo all'utente il vuoto logico riscontrato.
3. Proporre un ventaglio di soluzioni candidate tecnicamente percorribili.
È tassativamente vietato procedere basandosi su assunzioni implicite.

### `[REGOLA-DEV-04]` Tracciamento delle Deviazioni Approvate
Ogni deroga o modifica alle regole dell'AFU formalmente approvata dall'operatore umano deve essere registrata all'interno del codice sorgente sotto forma di commento di edonistica di progetto. Se la deviazione altera la logica del sistema, l'agente deve richiedere o assistere l'utente nell'aggiornamento del file Markdown dell'AFU per preservare la sincronizzazione del Graph RAG.

---

## Riepilogo delle Regele per l'Iniezione del Contesto

| Identificatore | Tipo di Regola | Vincolo Operativo Core |
|---|---|---|
| `[REGOLA-DEV-01]` | Architetturale | L'AFU supera sempre il codice preesistente in caso di conflitto. |
| `[REGOLA-DEV-02]` | Architetturale | Divieto di inventare feature o campi non esplicitati nell'AFU. |
| `[REGOLA-HITL-01]` | Checkpoint | Richiedere ok sul piano prima di toccare i file. |
| `[REGOLA-HITL-02]` | Checkpoint | Richiedere ok sul diff di ogni singola funzione coerente. |
| `[REGOLA-HITL-03]` | Checkpoint | Bloccare il task se i test automatici non sono green ed approvati. |
| `[REGOLA-HITL-04]` | Checkpoint | Validazione umana obbligatoria sui flussi di integrazione cross-modulo. |
| `[REGOLA-HITL-05]` | Checkpoint | Sign-off esplicito del supervisore per considerare pronto un modulo. |
| `[REGOLA-HITL-06]` | Checkpoint | Il silenzio dell'utente NON è mai un'approvazione. |
| `[REGOLA-CLEAN-01]` | Clean Code | Inserire i tag delle regole (es. `// Implementa REGOLA-XXX`) nei commenti. |
| `[REGOLA-CLEAN-02]` | Clean Code | Massimo 40 righe per function, altrimenti scomposizione obbligatoria. |
| `[REGOLA-CLEAN-03]` | Clean Code | Usare solo i termini del Glossario (es. `posti_residui`). |
| `[REGOLA-CLEAN-04]` | Clean Code | Estrarre costanti per tutti i magic numbers del codice. |
| `[REGOLA-CLEAN-05]` | Clean Code | Isolare la business logic da UI e database persistence layer. |
| `[REGOLA-CLEAN-06]` | Clean Code | Unica funzione transazionale server-side per i lock pessimistici. |
| `[REGOLA-CLEAN-07]` | Clean Code | Inserimento AUDIT_LOG sincrono e nella stessa transazione della modifica. |
| `[REGOLA-CLEAN-08]` | Clean Code | Invio notifiche asincrono ed esterno rispetto alla transazione DB. |
| `[REGOLA-CLEAN-09]` | Clean Code | Divieto totale di credenziali inline, usare solo environment injection. |
| `[REGOLA-DEV-03]` | Deviazione | Stop immediato se si trova un caso non coperto e proposta opzioni. |
| `[REGOLA-DEV-04]` | Deviazione | Allineamento del file AFU se la deviazione viene approvata. |

---

*Fine del documento — `docs/04_knowledge_informative/vibe_coding_workflow.md` v1.0.0*