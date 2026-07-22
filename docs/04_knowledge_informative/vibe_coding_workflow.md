---
id: "vibe-coding-workflow-baseline-v2.0"
title: "Linee Guida di Co-Sviluppo AI & Vibe Coding Framework (Baseline Cross-Progetto)"
project: "cross-project"
scope: "cross-project"
version: "2.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/04_knowledge_informative/vibe_coding_workflow.md"
authority: 0.90
changelog:
  - version: "2.0.0"
    date: "2026-07-22"
    changes:
      - "Riscrittura cross-progetto: rimossi gli agganci al dominio prenotazione eventi"
      - "'AFU' sostituita da <<SPEC_NORMATIVA>>: la fonte di verità è ora un parametro, non un file specifico"
      - "Regole di clean code trasferite a coding_standards.md per eliminare la duplicazione di identificatori"
      - "Aggiunta Sezione 0 — Contratto di Istanziazione"
reuse:
  parameters:
    - "<<SPEC_NORMATIVA>>: documento che costituisce la fonte di verità funzionale del progetto"
    - "<<GLOSSARIO_PROGETTO>>: documento della terminologia canonica"
    - "<<MODULI_APPLICATIVI>>: elenco dei macro-moduli fra cui avviene l'integrazione"
  instantiation: "Copiare il file, compilare la Sezione 0, sostituire ogni <<PARAMETRO>>. Gli identificatori [REGOLA-HITL-NN] e [REGOLA-DEV-NN] devono restare stabili."
graph_rag:
  node_type: "METHODOLOGY"
  node_id: "vibe-coding-workflow-baseline-v2.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "REQUISITO_METODOLOGICO"
      target: "TUTTI_I_COMPITI_DI_SVILUPPO"
    - type: "CONNESSA_A"
      target: "coding-standards-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "safeguards-security-baseline-v2.0"
tags:
  - methodology
  - vibe-coding
  - human-in-the-loop
  - workflow
  - cross-project
  - baseline
  - cursor
  - claude-code
---

# Linee Guida di Co-Sviluppo AI & Vibe Coding Framework
## Baseline Cross-Progetto — Protocollo Metodologico Operativo

> **⚠️ DIRETTIVA TASSATIVA PER L'AI CODING AGENT (Cursor / Claude Code)**
>
> Questo documento definisce il **Framework Metodologico di Sviluppo**. Non descrive le funzioni di un software: governa il tuo comportamento operativo sul filesystem e le modalità di interazione con lo sviluppatore umano.
>
> Sei obbligato ad agire secondo i principi del **Prompt-Driven Development regolato**. Devi interrompere l'esecuzione e richiedere una validazione umana esplicita a ogni Checkpoint HITL qui catalogato. Non ti è permesso bypassare, ignorare o auto-approvare alcuna transizione di task.

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<SPEC_NORMATIVA>>` | Documento che è fonte di verità funzionale | *(da compilare)* |
| `<<GLOSSARIO_PROGETTO>>` | Documento della terminologia canonica | *(da compilare)* |
| `<<MODULI_APPLICATIVI>>` | Macro-moduli fra cui avviene l'integrazione | *(da compilare)* |

Finché `<<SPEC_NORMATIVA>>` non è compilato, l'agente non ha una fonte di verità dichiarata: in questa condizione ogni ambiguità va portata all'umano ai sensi di `[REGOLA-DEV-03]`, mai risolta per assunzione.

---

## Sezione 1 — Protocollo Human-in-the-Loop (HITL)

Il ciclo di vita dello sviluppo è rigidamente interrotto da checkpoint sequenziali. L'assenza di risposta o il silenzio dell'operatore non costituiscono mai un'approvazione implicita.

### `[REGOLA-HITL-01]` Checkpoint 1 — Approvazione del Piano di Implementazione
* **Trigger di Blocco:** Ricezione di un nuovo task di sviluppo o richiesta di modifica. Prima di toccare qualsiasi riga di codice, devi fermarti.
* **Azione Umana Richiesta:** Il supervisore analizza, modifica e approva esplicitamente il piano d'azione.
* **Input da Fornire al Supervisore:** Un elenco sintetico e atomico contenente:
  1. Le entità di `<<GLOSSARIO_PROGETTO>>` coinvolte.
  2. Le regole di business di `<<SPEC_NORMATIVA>>` applicate.
  3. L'albero esatto dei file che intendi creare o modificare.
  4. Le scelte architetturali lasciate libere dalle specifiche.
* **Guardrail:** Se l'umano corregge il piano, devi rigenerarlo integrando i feedback. È vietato procedere alla scrittura del codice senza validazione esplicita.

### `[REGOLA-HITL-02]` Checkpoint 2 — Revisione del Codice Generato
* **Trigger di Blocco:** Completamento del codice relativo a una singola funzionalità coerente (es. il solo controller, prima dei test).
* **Azione Umana Richiesta:** Ispezione del codice sorgente e code review.
* **Input da Fornire al Supervisore:** Il `git diff` completo, pulito e isolato del task appena eseguito.
* **Guardrail:** Non sono ammesse implementazioni cumulative o "a cascata" di più funzionalità senza checkpoint intermedi.

### `[REGOLA-HITL-03]` Checkpoint 3 — Validazione dei Test Automatici
* **Trigger di Blocco:** Scrittura dei test unitari ed esecuzione della suite locale.
* **Azione Umana Richiesta:** Verifica della copertura dei casi limite e approvazione dell'esito del test runner.
* **Input da Fornire al Supervisore:** Report dell'esito (green/red) e codice sorgente dei test generati.
* **Guardrail:** Ogni test deve verificare esplicitamente una regola numerata di `<<SPEC_NORMATIVA>>`, con priorità ai percorsi concorrenti e transazionali. Il task è incompleto finché la suite non è verificata dall'operatore.

### `[REGOLA-HITL-04]` Checkpoint 4 — Test di Integrazione tra Moduli
* **Trigger di Blocco:** Integrazione cross-modulo o modifiche che impattano l'interazione fra `<<MODULI_APPLICATIVI>>`.
* **Azione Umana Richiesta:** Validazione del flusso end-to-end simulato o reale.
* **Input da Fornire al Supervisore:** Log di integrazione, schemi di chiamata API aggiornati, documentazione degli impatti cross-modulo.
* **Guardrail:** Il merge è congelato fino alla firma umana.

### `[REGOLA-HITL-05]` Checkpoint 5 — Sign-Off Umano Finale
* **Trigger di Blocco:** Completamento dell'intero modulo e preparazione per il deployment locale o in staging.
* **Azione Umana Richiesta:** Dichiarazione formale di chiusura del ciclo di sviluppo.
* **Input da Fornire al Supervisore:** Checklist finale di conformità rispetto a `<<SPEC_NORMATIVA>>`.
* **Guardrail:** Nessun modulo è distribuibile senza approvazione finale esplicita.

### `[REGOLA-HITL-06]` Enforcement del Blocco Rigido
In nessun caso l'AI deve auto-approvare un proprio checkpoint o procedere oltre senza una risposta esplicita e positiva dell'essere umano. Il silenzio dell'utente non costituisce approvazione implicita.

---

## Sezione 2 — Standard di Scrittura del Codice

Le regole di clean code (limite dimensionale delle funzioni, gestione delle eccezioni, tagging delle regole nei docstring, magic number, isolamento della business logic, allineamento terminologico) sono normate in un unico punto: **`docs/01_architecture_norms/coding_standards.md`**, identificatori `[REGOLA-CLEAN-01]` … `[REGOLA-CLEAN-07]`.

> **Nota di versione:** la v1.0 di questo documento duplicava quelle regole con una numerazione `[REGOLA-CLEAN-*]` divergente da quella di `coding_standards.md` — stesso identificatore, regola diversa. La duplicazione è stata rimossa: `coding_standards.md` è l'unica fonte. Non reintrodurre regole di stile qui.

Restano di competenza di questo documento i vincoli metodologici che non riguardano la forma del codice ma il **processo**:

### `[REGOLA-PROC-01]` Co-transazionalità dell'audit
La scrittura del record di audit avviene nella stessa transazione che muta l'entità tracciata; il fallimento dell'audit provoca il rollback. Invariante normata in `[SAFEGUARD-AUD-02]`.

### `[REGOLA-PROC-02]` Disaccoppiamento asincrono delle notifiche
L'invio di notifiche verso provider esterni deve essere isolato e asincrono rispetto alla transazione di database principale. Un timeout o un fallimento di rete del provider non deve mai propagarsi all'indietro invalidando la transazione di business.

### `[REGOLA-PROC-03]` Unicità dell'ambiente transazionale
Ogni operazione legata alla gestione della concorrenza deve essere racchiusa in un'unica funzione transazionale atomica server-side. La transazione non deve mai essere frammentata su più chiamate asincrone distinte. Invariante normata in `[SAFEGUARD-TXN-01]` e `[SAFEGUARD-TXN-02]`.

---

## Sezione 3 — Gestione delle Deviazioni (Edge Cases)

### `[REGOLA-DEV-01]` Supremazia della specifica normativa
`<<SPEC_NORMATIVA>>` costituisce la fonte di verità del progetto. In presenza di discrepanze o conflitti fra il codice preesistente e una regola documentata, l'agente deve fermarsi e dare precedenza assoluta alla regola documentata.

### `[REGOLA-DEV-02]` Divieto di iniziativa funzionale autonoma
È vietato introdurre funzionalità accessorie, campi aggiuntivi, ruoli utente o logiche di workflow non esplicitamente previsti da `<<SPEC_NORMATIVA>>`. L'agente non fa assunzioni basate su preferenze personali o interpretazioni estensive.

### `[REGOLA-DEV-03]` Interruzione per vuoto di specifica
Se durante la scrittura del codice l'agente incontra una casistica limite o un comportamento non normato, ha l'obbligo di:
1. Sospendere lo sviluppo della funzionalità impattata.
2. Aprire una segnalazione strutturata descrivendo il vuoto logico riscontrato.
3. Proporre un ventaglio di soluzioni candidate tecnicamente percorribili.

È vietato procedere su assunzioni implicite.

### `[REGOLA-DEV-04]` Tracciamento delle deviazioni approvate
Ogni deroga approvata dall'operatore umano deve essere registrata nel codice sorgente come commento esplicito. Se la deviazione altera la logica di sistema, l'agente deve aggiornare — o assistere l'utente nell'aggiornare — `<<SPEC_NORMATIVA>>`, per preservare la sincronizzazione del Graph RAG.

---

## Riepilogo delle Regole per l'Iniezione del Contesto

| Identificatore | Tipo | Vincolo operativo core |
|---|---|---|
| `[REGOLA-DEV-01]` | Architetturale | La specifica normativa supera sempre il codice preesistente. |
| `[REGOLA-DEV-02]` | Architetturale | Divieto di inventare feature o campi non specificati. |
| `[REGOLA-DEV-03]` | Deviazione | Stop immediato su caso non coperto, con proposta di opzioni. |
| `[REGOLA-DEV-04]` | Deviazione | Allineare la specifica se la deviazione viene approvata. |
| `[REGOLA-HITL-01]` | Checkpoint | Ok sul piano prima di toccare i file. |
| `[REGOLA-HITL-02]` | Checkpoint | Ok sul diff di ogni funzionalità coerente. |
| `[REGOLA-HITL-03]` | Checkpoint | Task bloccato se i test non sono green e approvati. |
| `[REGOLA-HITL-04]` | Checkpoint | Validazione umana sui flussi di integrazione cross-modulo. |
| `[REGOLA-HITL-05]` | Checkpoint | Sign-off esplicito per considerare pronto un modulo. |
| `[REGOLA-HITL-06]` | Checkpoint | Il silenzio dell'utente NON è mai approvazione. |
| `[REGOLA-PROC-01]` | Processo | Audit co-transazionale con la mutazione. |
| `[REGOLA-PROC-02]` | Processo | Notifiche asincrone e isolate dalla transazione DB. |
| `[REGOLA-PROC-03]` | Processo | Una sola funzione transazionale atomica per i lock. |

---

*Fine del documento — baseline cross-progetto v2.0.0*
