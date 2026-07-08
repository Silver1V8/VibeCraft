---
id: "matrice-permessi-v1.0"
title: "Matrice dei Permessi — Authorization Policy RBAC"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-01"
status: "ENFORCED"
classification: "AUTHORIZATION_POLICY"
path: "docs/00_meta_governance/matrice_permessi.md"
source_document: "ANALISI_FUNZIONALE.md v1.0.0"
source_section: "0.4 — Attori e Matrice dei Permessi"
authors:
  - role: "Senior IAM Specialist"
  - role: "Context Engineer"
graph_rag:
  node_type: "AUTHORIZATION_POLICY"
  node_id: "matrice-permessi-v1.0"
  roles:
    - "DIPENDENTE"
    - "MANAGER"
    - "ADMIN_HR"
    - "ADMIN_IT"
  funzionalita_count: 13
  edges:
    - type: "DERIVA_DA"
      target: "ANALISI_FUNZIONALE"
      section: "0.4"
    - type: "REFERENZIA"
      target: "glossario-entita-v1.0"
      note: "I permessi operano sulle entità EVENTO, RICHIESTA, UTENTE, NOTIFICA, AUDIT_LOG"
    - type: "INTEGRA"
      target: "safeguards-security-v1.2"
      note: "Le regole SAFEGUARD-SEC-01 e SAFEGUARD-SEC-02 sono prerequisiti di autenticazione a questo modello RBAC"
    - type: "VINCOLA"
      target: "PARTE_1_PORTALE_UTENTE"
      note: "Funzionalità accessibili a DIPENDENTE e MANAGER"
    - type: "VINCOLA"
      target: "PARTE_2_WORKFLOW_APPROVAZIONE"
      note: "Funzionalità di approvazione accessibili a MANAGER e ADMIN_HR"
    - type: "VINCOLA"
      target: "PARTE_3_PANNELLO_ADMIN"
      note: "Funzionalità amministrative accessibili a ADMIN_HR e ADMIN_IT"
    - type: "IMPLEMENTATO_DA"
      target: "MIDDLEWARE_AUTORIZZAZIONE"
      note: "Ogni arco PUÒ_ESEGUIRE/NON_PUÒ_ESEGUIRE corrisponde a un guard applicativo"
  rbac_edges_count: 52
tags:
  - authorization
  - rbac
  - iam
  - permissions
  - roles
  - graph-rag
  - authorization-policy
  - single-source-of-truth
  - dipendente
  - manager
  - admin-hr
  - admin-it
  - access-control
---

# Matrice dei Permessi — Authorization Policy RBAC
## `VIBECRAFT` — Sistema di Gestione Eventi Aziendali

> **Nota per l'AI Coding Agent e il sistema Graph RAG**
>
> Questo documento è la **fonte di verità canononica per il modello di autorizzazione** del progetto. La Sezione 3 (Mapping degli Archi del Grafo) costituisce la lista completa e non ambigua di tutti i 52 archi RBAC del sistema, da cui deve essere derivata **ogni** decisione di accesso nell'applicazione. In caso di discrepanza tra questo documento e qualsiasi implementazione middleware, questo documento prevale. Ogni arco `—[PUÒ_ESEGUIRE]→` corrisponde a un gate da aprire; ogni arco `—[NON_PUÒ_ESEGUIRE]→` corrisponde a un gate da bloccare con risposta HTTP 403.
>
> Il modello di autorizzazione è **ruolo-singolo**: ogni `UTENTE` ha esattamente un ruolo in ogni istante. Non esistono ruoli compositi o ereditarietà gerarchica implicita tra ruoli, ad eccezione della relazione esplicita documentata nella sezione 1.2 (`MANAGER` eredita le capacità del Portale Utente di `DIPENDENTE`).

---

## 1. Profili degli Attori

### 1.1 — `DIPENDENTE`

**Descrizione del ruolo:** L'attore di base del sistema. Rappresenta il lavoratore aziendale che fruisce del catalogo eventi formativi e gestisce il proprio ciclo di richiesta di partecipazione. È il ruolo assegnato di default a ogni nuovo `UTENTE` al momento della prima autenticazione.

**Ambito di visibilità dei dati:**

- **`EVENTO`:** visibilità completa del catalogo pubblico — tutti gli `EVENTO` con `stato = ATTIVO` e `data_inizio` futura. Non può vedere eventi con `stato = ARCHIVIATO` o `ELIMINATO`.
- **`RICHIESTA`:** visibilità esclusivamente delle proprie `RICHIESTA` (dove `richiedente_id = UTENTE.id` corrente). Non può vedere le `RICHIESTA` di altri dipendenti in nessuna circostanza, nemmeno in forma aggregata o anonimizzata.
- **`NOTIFICA`:** visibilità esclusivamente delle proprie `NOTIFICA` (dove `destinatario_id = UTENTE.id` corrente), visualizzate nell'area in-app.
- **`UTENTE`:** nessuna visibilità sui profili altrui. Accede solo al proprio profilo (avatar, nome, email) tramite la UI.
- **`AUDIT_LOG`:** nessuna visibilità. Il log di audit è completamente opaco per questo ruolo.
- **`BUDGET_ANNUO`:** nessuna visibilità sui dati finanziari aggregati.

**Confini operativi stringenti — cosa `DIPENDENTE` NON può fare:**

- ❌ Non può vedere né accedere alle `RICHIESTA` di altri dipendenti, nemmeno se riferite allo stesso `EVENTO`.
- ❌ Non può modificare lo stato della propria `RICHIESTA` dopo la sottomissione, ad eccezione dell'annullamento (solo se `stato = IN_ATTESA`).
- ❌ Non può modificare i campi `motivazione`, `necessita_alloggio`, `note_aggiuntive` di una `RICHIESTA` già sottomessa.
- ❌ Non può creare, modificare, archiviare o eliminare `EVENTO`.
- ❌ Non può approvare o rifiutare alcuna `RICHIESTA`, inclusa la propria.
- ❌ Non può effettuare override dello stato di una `RICHIESTA`.
- ❌ Non può accedere alla coda di approvazione del workflow.
- ❌ Non può accedere al Pannello Admin in nessuna delle sue sezioni.
- ❌ Non può esportare dati in formato CSV/Excel.
- ❌ Non può visualizzare la dashboard Analytics e i dati di budget.
- ❌ Non può visualizzare l'Audit Trail.
- ❌ Non può gestire utenti, assegnare ruoli o disattivare account.

**Regole correlate:** `[REGOLA-UT-03]` (ruolo di default), `[REGOLA-AUTH-01]` (accesso vincolato al dominio), `[REGOLA-AUTH-02]` (verifica `attivo` ad ogni request).

---

### 1.2 — `MANAGER`

**Descrizione del ruolo:** Sovrintende il Portale Utente con le stesse capacità operative del `DIPENDENTE` e aggiunge in esclusiva la gestione della coda di approvazione del workflow. La relazione gerarchica con il proprio team è la base per determinare quali `RICHIESTA` può processare: il `MANAGER` vede solo le richieste dei dipendenti del **proprio team organizzativo**, non di tutti i dipendenti del sistema.

**Ambito di visibilità dei dati:**

- **`EVENTO`:** identico al `DIPENDENTE` — catalogo pubblico completo degli eventi attivi.
- **`RICHIESTA` (come richiedente):** identico al `DIPENDENTE` — solo le proprie richieste nell'Area Personale.
- **`RICHIESTA` (come approvatore):** visibilità di tutte le `RICHIESTA` con `stato = IN_ATTESA` sottomesse dai membri del **proprio team** (relazione gerarchica derivata dall'anagrafica `UTENTE`). Non può vedere le richieste di team altrui.
- **`NOTIFICA`:** identico al `DIPENDENTE` — solo le proprie notifiche in-app. Riceve in aggiunta notifiche `NUOVA_RICHIESTA` via Email e Slack per le richieste del suo team.
- **`UTENTE`:** visibilità limitata ai nominativi del proprio team, visibili nella coda di approvazione (nome, cognome, dipartimento). Non ha accesso alla gestione anagrafica degli utenti.
- **`AUDIT_LOG`:** nessuna visibilità diretta.
- **`BUDGET_ANNUO`:** nessuna visibilità sui dati finanziari aggregati.

**Confini operativi stringenti — cosa `MANAGER` NON può fare:**

- ❌ Non può vedere le `RICHIESTA` di dipendenti appartenenti a team diversi dal proprio.
- ❌ Non può creare, modificare, archiviare o eliminare `EVENTO`.
- ❌ Non può effettuare override manuale dello stato di una `RICHIESTA` (questa prerogativa è esclusiva di `ADMIN_HR`).
- ❌ Non può accedere al Pannello Admin in nessuna delle sue sezioni.
- ❌ Non può esportare dati in formato CSV/Excel.
- ❌ Non può visualizzare la dashboard Analytics e i dati di budget.
- ❌ Non può visualizzare l'Audit Trail.
- ❌ Non può gestire utenti, assegnare ruoli o disattivare account.
- ❌ Non può approvare la propria `RICHIESTA` come Manager (conflitto di interesse non ammesso dal modello di dati: `richiedente_id ≠ manager_id` sulla stessa `RICHIESTA`).

**Regole correlate:** `[REGOLA-MGR-01]` (visibilità limitata al proprio team), `[REGOLA-MGR-02]` (approvazione con singolo click), `[REGOLA-MGR-03]` (rifiuto con commento obbligatorio).

---

### 1.3 — `ADMIN_HR`

**Descrizione del ruolo:** Amministratore con focus su reportistica, gestione del catalogo eventi e supervisione trasversale del workflow di approvazione. Ha potere di intervento su qualsiasi `RICHIESTA` del sistema tramite l'override manuale. Accede al Pannello Admin ma con un profilo di visibilità orientato alle persone e ai processi, non alla gestione tecnica dell'infrastruttura.

**Ambito di visibilità dei dati:**

- **`EVENTO`:** visibilità completa del catalogo, inclusi eventi archiviati. Può creare, modificare e archiviare eventi. Non può eliminare fisicamente gli eventi (prerogativa di `ADMIN_IT`).
- **`RICHIESTA`:** visibilità globale di **tutte** le `RICHIESTA` del sistema, in qualsiasi stato, per qualsiasi dipendente, filtrabile per evento, stato, dipendente e intervallo date. È l'unico ruolo con questa visibilità trasversale nominativa.
- **`NOTIFICA`:** non riceve notifiche in-app operative del workflow (approvazione, rifiuto). La sua interazione con le notifiche è indiretta, tramite la vista globale delle richieste.
- **`UTENTE`:** visibilità nominativa dei dipendenti tramite la tabella delle richieste. Non ha accesso alla gestione tecnica degli account (attivazione/disattivazione, cambio ruolo): questa è prerogativa di `ADMIN_IT`.
- **`AUDIT_LOG`:** accesso in lettura completo. Può visualizzare, filtrare e consultare l'intera storia delle mutazioni del sistema.
- **`BUDGET_ANNUO`:** visibilità completa dei KPI finanziari: budget consumato, budget residuo, tasso di saturazione, trend mensile. Riceve alert quando il budget residuo scende sotto la soglia del 15%.

**Confini operativi stringenti — cosa `ADMIN_HR` NON può fare:**

- ❌ Non può eliminare fisicamente `EVENTO` dal sistema (può solo archiviare).
- ❌ Non può gestire gli account utente: non può attivare, disattivare o cambiare il ruolo di un `UTENTE`. Questa prerogativa è esclusiva di `ADMIN_IT`.
- ❌ Non può ricevere notifiche in-app standard del workflow (approvazione/rifiuto): il suo canale operativo è il Pannello Admin, non il Portale Utente.
- ❌ Non può sottomettere `RICHIESTA` di partecipazione a eventi in qualità di richiedente (il ruolo di `ADMIN_HR` è amministrativo, non partecipativo).
- ❌ Non può approvare o rifiutare `RICHIESTA` tramite il workflow standard del Manager (può solo forzare stati tramite override, che è un'azione distinta e tracciata).

**Regole correlate:** `[REGOLA-ADM-01]`, `[REGOLA-ADM-02]`, `[REGOLA-OVR-01]`, `[REGOLA-OVR-02]`, `[REGOLA-OVR-03]`, `[REGOLA-EXP-01]`, `[REGOLA-ANL-01]`, `[REGOLA-ANL-03]`.

---

### 1.4 — `ADMIN_IT`

**Descrizione del ruolo:** Amministratore con focus sulla gestione tecnica del catalogo e dell'anagrafica utenti. Ha i massimi privilegi sul sistema in termini di gestione dell'infrastruttura applicativa, ma è deliberatamente privato della visibilità nominativa sulle richieste individuali dei dipendenti, per ragioni di separazione dei ruoli e privacy.

**Ambito di visibilità dei dati:**

- **`EVENTO`:** visibilità e controllo completi — può creare, modificare, archiviare **ed eliminare** eventi. L'eliminazione fisica è consentita solo per eventi senza `RICHIESTA` associate.
- **`RICHIESTA`:** **nessuna visibilità nominativa** sulle richieste individuali dei dipendenti. Può accedere ai soli dati aggregati e anonimi tramite la dashboard Analytics. Questa limitazione è intenzionale e non bypassabile: separa la gestione tecnica dalla gestione dei dati personali dei dipendenti.
- **`NOTIFICA`:** nessuna visibilità sulle notifiche individuali del workflow. Riceve alert di sistema (es. fallimento consegna notifica al terzo tentativo, violazione di integrità dati) tramite canali infrastrutturali separati dall'applicazione.
- **`UTENTE`:** visibilità e controllo completi sull'anagrafica — può attivare/disattivare account e modificare il ruolo di qualsiasi `UTENTE`. È l'unico ruolo autorizzato a elevare un altro utente a `MANAGER`, `ADMIN_HR` o `ADMIN_IT`.
- **`AUDIT_LOG`:** accesso in lettura completo. Anche se l'`ADMIN_IT` ha i massimi privilegi applicativi, non può scrivere, modificare o eliminare record dell'`AUDIT_LOG` (immutabilità assoluta garantita anche contro questo ruolo).
- **`BUDGET_ANNUO`:** visibilità dei KPI aggregati (budget consumato/residuo, trend) ma senza la visibilità nominativa sulle singole approvazioni che compongono il totale.

**Confini operativi stringenti — cosa `ADMIN_IT` NON può fare:**

- ❌ Non può accedere alla vista nominativa delle `RICHIESTA` individuali dei dipendenti. Questa è la separazione fondamentale rispetto ad `ADMIN_HR`.
- ❌ Non può effettuare override manuale dello stato di una `RICHIESTA` (prerogativa esclusiva di `ADMIN_HR`).
- ❌ Non può esportare i dati nominativi dei partecipanti in formato CSV/Excel.
- ❌ Non può approvare o rifiutare `RICHIESTA` tramite il workflow standard.
- ❌ Non può ricevere notifiche in-app standard del workflow.
- ❌ Non può modificare o eliminare record dell'`AUDIT_LOG`, nonostante disponga dei massimi privilegi applicativi. L'immutabilità dell'audit trail è enforced anche contro `ADMIN_IT` tramite revoca dei grant `UPDATE` e `DELETE` sull'utenza DB applicativa (vedi `[SAFEGUARD-AUD-01]`).

**Regole correlate:** `[REGOLA-ADM-01]`, `[REGOLA-ADM-02]`, `[REGOLA-CRUD-04]`, `[REGOLA-INT-04]`, `[SAFEGUARD-AUD-01]`.

---

## 2. Matrice dei Permessi

> Fonte: Sezione 0.4.2 dell'`ANALISI_FUNZIONALE.md`. Ogni cella è un arco del grafo RBAC esplicitato nella Sezione 3 di questo documento.

| # | Funzionalità | DIPENDENTE | MANAGER | ADMIN_HR | ADMIN_IT |
|---|---|:---:|:---:|:---:|:---:|
| F-01 | Visualizza catalogo eventi | ✅ | ✅ | ✅ | ✅ |
| F-02 | Sottomette richiesta | ✅ | ✅ | ❌ | ❌ |
| F-03 | Visualizza proprie richieste | ✅ | ✅ | ❌ | ❌ |
| F-04 | Riceve notifiche in-app | ✅ | ✅ | ❌ | ❌ |
| F-05 | Vede coda approvazione | ❌ | ✅ | ✅ | ❌ |
| F-06 | Approva / Rifiuta richiesta | ❌ | ✅ | ❌ | ❌ |
| F-07 | Override stato richiesta | ❌ | ❌ | ✅ | ❌ |
| F-08 | Crea / Modifica evento | ❌ | ❌ | ✅ | ✅ |
| F-09 | Elimina evento | ❌ | ❌ | ❌ | ✅ |
| F-10 | Gestisce utenti e ruoli | ❌ | ❌ | ❌ | ✅ |
| F-11 | Esporta dati CSV/Excel | ❌ | ❌ | ✅ | ❌ |
| F-12 | Visualizza analytics budget | ❌ | ❌ | ✅ | ✅ |
| F-13 | Visualizza audit log | ❌ | ❌ | ✅ | ✅ |

**Conteggio archi per tipo:**

| Tipo arco | Conteggio totale |
|---|---|
| `—[PUÒ_ESEGUIRE]→` | 21 |
| `—[NON_PUÒ_ESEGUIRE]→` | 31 |
| **Totale archi RBAC** | **52** |

**Distribuzione permessi per ruolo:**

| Ruolo | Funzionalità concesse | Funzionalità negate |
|---|---|---|
| `DIPENDENTE` | 4 (F-01, F-02, F-03, F-04) | 9 (F-05÷F-13) |
| `MANAGER` | 6 (F-01, F-02, F-03, F-04, F-05, F-06) | 7 (F-07÷F-13) |
| `ADMIN_HR` | 7 (F-01, F-05, F-07, F-08, F-11, F-12, F-13) | 6 (F-02, F-03, F-04, F-06, F-09, F-10) |
| `ADMIN_IT` | 6 (F-01, F-08, F-09, F-10, F-12, F-13) | 7 (F-02, F-03, F-04, F-05, F-06, F-07, F-11) |

---

## 3. Mapping degli Archi del Grafo (RBAC Edges)

> Questa sezione è il cuore del documento per il sistema Graph RAG. Ogni blocco rappresenta una funzionalità come nodo del grafo e i quattro archi uscenti verso i ruoli. La dichiarazione di arco è la fonte autoritativa da cui derivare ogni guard applicativo. L'ID funzionalità (`F-NN`) è l'identificatore stabile referenziabile da altri nodi del grafo.

---

### `F-01` — Visualizza catalogo eventi

**Descrizione:** Accesso alla Dashboard Eventi (`/eventi`) con visualizzazione delle card degli `EVENTO` con `stato = ATTIVO` e `data_inizio` futura. Include la visualizzazione dei badge di stato (disponibile, sold out, iscrizioni chiuse, ultimi posti) e del contatore `posti_residui`.

**Entità coinvolte:** `EVENTO` (lettura), `UTENTE` (identità del richiedente).

**Regole correlate:** `[REGOLA-DASH-01]` → `[REGOLA-DASH-07]`, `[REGOLA-DET-01]` → `[REGOLA-DET-04]`.

- `(DIPENDENTE)` —[**PUÒ_ESEGUIRE**]→ `Visualizza catalogo eventi`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Visualizza catalogo eventi`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Visualizza catalogo eventi`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Visualizza catalogo eventi`

> **Nota RBAC:** È l'unica funzionalità universalmente concessa a tutti i ruoli. Il contenuto visualizzato è identico per tutti: solo gli `EVENTO` con `stato = ATTIVO`. Nessun ruolo vede eventi archiviati o eliminati nella Dashboard pubblica.

---

### `F-02` — Sottomette richiesta

**Descrizione:** Accesso al Form di Prenotazione (`/eventi/:id/richiedi`) e invio di una nuova `RICHIESTA` con `stato = IN_ATTESA`. Include la compilazione dei campi `motivazione`, `necessita_alloggio`, `note_aggiuntive` e il submit che innesca il workflow di approvazione.

**Entità coinvolte:** `RICHIESTA` (scrittura INSERT), `EVENTO` (lettura + lock transazionale su `posti_residui`), `NOTIFICA` (generazione automatica `NUOVA_RICHIESTA`), `AUDIT_LOG` (INSERT automatico).

**Regole correlate:** `[REGOLA-FORM-01]` → `[REGOLA-FORM-04]`, `[REGOLA-RQ-01]` → `[REGOLA-RQ-03]`, `[REGOLA-VAL-01]` → `[REGOLA-VAL-03]`, `[REGOLA-CONC-01]` → `[REGOLA-CONC-06]`.

- `(DIPENDENTE)` —[**PUÒ_ESEGUIRE**]→ `Sottomette richiesta`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Sottomette richiesta`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Sottomette richiesta`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Sottomette richiesta`

> **Nota RBAC:** `ADMIN_HR` e `ADMIN_IT` non possono sottomettere richieste di partecipazione. Il loro ruolo è esclusivamente amministrativo. Un tentativo di accesso al form di prenotazione da parte di questi ruoli deve restituire HTTP 403.

---

### `F-03` — Visualizza proprie richieste

**Descrizione:** Accesso all'Area Personale (`/mie-richieste`) con visualizzazione della lista delle proprie `RICHIESTA` filtrata per `richiedente_id = UTENTE.id` corrente. Include la visualizzazione dei badge di stato, del commento manager in caso di rifiuto, e la funzione di annullamento per richieste `IN_ATTESA`.

**Entità coinvolte:** `RICHIESTA` (lettura, filtro per `richiedente_id`), `NOTIFICA` (lettura `canale = IN_APP`), `EVENTO` (lettura campi descrittivi).

**Regole correlate:** `[REGOLA-PERS-01]` → `[REGOLA-PERS-03]`, `[REGOLA-NOTIF-01]` → `[REGOLA-NOTIF-04]`.

- `(DIPENDENTE)` —[**PUÒ_ESEGUIRE**]→ `Visualizza proprie richieste`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Visualizza proprie richieste`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza proprie richieste`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza proprie richieste`

> **Nota RBAC:** `ADMIN_HR` e `ADMIN_IT` non hanno un'Area Personale nell'applicazione. Il loro punto di accesso per monitorare le `RICHIESTA` è il Pannello Admin (F-05), non questa vista personale. Un tentativo di accesso a `/mie-richieste` da parte di questi ruoli deve restituire HTTP 403.

---

### `F-04` — Riceve notifiche in-app

**Descrizione:** Visualizzazione del badge numerico sulla campanella nella topbar, apertura del pannello notifiche con le ultime 50 `NOTIFICA` con `destinatario_id = UTENTE.id` corrente, visualizzazione dei toast per cambi di stato in tempo reale. Include il meccanismo di mark-as-read.

**Entità coinvolte:** `NOTIFICA` (lettura, filtro per `destinatario_id`, UPDATE `stato_consegna` per mark-as-read).

**Regole correlate:** `[REGOLA-NOTIF-01]` → `[REGOLA-NOTIF-04]`.

- `(DIPENDENTE)` —[**PUÒ_ESEGUIRE**]→ `Riceve notifiche in-app`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Riceve notifiche in-app`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Riceve notifiche in-app`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Riceve notifiche in-app`

> **Nota RBAC:** `ADMIN_HR` e `ADMIN_IT` non ricevono notifiche in-app del workflow applicativo. Ricevono invece alert di sistema (es. fallimento delivery notifica, violazione integrità) tramite canali infrastrutturali separati, non modellati in questa matrice.

---

### `F-05` — Vede coda approvazione

**Descrizione:** Accesso alla sezione Coda di Approvazione (`/approvazioni`) con visualizzazione delle `RICHIESTA` con `stato = IN_ATTESA`. Per il `MANAGER`, la vista è filtrata alle richieste del proprio team. Per `ADMIN_HR`, la vista è globale su tutte le richieste in attesa del sistema (parte della sua vista globale F-07).

**Entità coinvolte:** `RICHIESTA` (lettura, filtro per `stato = IN_ATTESA`), `UTENTE` (lettura dati richiedente — nome, cognome, dipartimento), `EVENTO` (lettura dati evento).

**Regole correlate:** `[REGOLA-MGR-01]`, `[REGOLA-MGR-02]`, `[REGOLA-MGR-03]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Vede coda approvazione`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Vede coda approvazione`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Vede coda approvazione`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Vede coda approvazione`

> **Nota RBAC — Distinzione intra-ruolo:** Il `MANAGER` vede solo le richieste del **proprio team** (`WHERE team_id = MANAGER.team_id`). `ADMIN_HR` vede **tutte** le richieste in attesa del sistema (nessun filtro per team). Questa è una differenza di **scope dei dati**, non di permesso binario: entrambi hanno `PUÒ_ESEGUIRE`, ma con predicati di visibilità diversi. Il guard applicativo deve applicare il filtro corretto in base al ruolo del richiedente.

---

### `F-06` — Approva / Rifiuta richiesta

**Descrizione:** Esecuzione delle azioni "Approva" (transizione `IN_ATTESA → APPROVATA`) e "Rifiuta" (transizione `IN_ATTESA → RIFIUTATA`) sulle `RICHIESTA` della coda. Il rifiuto richiede la compilazione obbligatoria del campo `commento_manager`. Entrambe le azioni innescano notifiche verso il `DIPENDENTE` e un record `AUDIT_LOG`.

**Entità coinvolte:** `RICHIESTA` (UPDATE `stato`, `manager_id`, `data_decisione`, `commento_manager`), `EVENTO` (UPDATE `posti_residui` per approvazione, con lock `SELECT ... FOR UPDATE`), `NOTIFICA` (INSERT automatico), `AUDIT_LOG` (INSERT automatico).

**Regole correlate:** `[REGOLA-MGR-02]`, `[REGOLA-MGR-03]`, `[REGOLA-RQ-04]`, `[REGOLA-WF-01]`, `[REGOLA-WF-03]`, `[REGOLA-CONC-01]` → `[REGOLA-CONC-06]`, `[REGOLA-INT-06]`, `[SAFEGUARD-TXN-01]`, `[SAFEGUARD-TXN-02]`, `[SAFEGUARD-TXN-05]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Approva / Rifiuta richiesta`
- `(MANAGER)` —[**PUÒ_ESEGUIRE**]→ `Approva / Rifiuta richiesta`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Approva / Rifiuta richiesta`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Approva / Rifiuta richiesta`

> **Nota RBAC critica:** `ADMIN_HR` NON può usare questa funzionalità: il suo meccanismo di intervento sulle `RICHIESTA` è esclusivamente tramite `F-07` (Override stato richiesta), che è un'azione distinta, più potente e con tracciamento differenziato (`azione = OVERRIDE_MANUALE`). Il `MANAGER` può usare solo `F-06` (workflow standard); non ha accesso a `F-07`. Questa separazione è intenzionale.

---

### `F-07` — Override stato richiesta

**Descrizione:** Capacità di forzare lo stato di qualsiasi `RICHIESTA` del sistema verso qualsiasi valore dell'enum `stato`, incluso il superamento di stati terminali (`APPROVATA`, `RIFIUTATA`). Ogni esercizio di questo permesso genera obbligatoriamente un record `AUDIT_LOG` con `azione = OVERRIDE_MANUALE`. Per una transizione override verso `APPROVATA`, deve essere rieseguita la verifica `posti_residui > 0`.

**Entità coinvolte:** `RICHIESTA` (UPDATE forzato `stato`), `EVENTO` (verifica e UPDATE `posti_residui` se override → `APPROVATA`), `AUDIT_LOG` (INSERT obbligatorio con `azione = OVERRIDE_MANUALE`).

**Regole correlate:** `[REGOLA-OVR-01]`, `[REGOLA-OVR-02]`, `[REGOLA-OVR-03]`, `[REGOLA-WF-01]` (eccezione esplicita), `[SAFEGUARD-TXN-01]` (applicato anche all'override).

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Override stato richiesta`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Override stato richiesta`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Override stato richiesta`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Override stato richiesta`

> **Nota RBAC:** Questo è il permesso con distribuzione più ristretta tra quelli non-universali: solo 1 ruolo su 4 può eseguirlo. `ADMIN_IT`, pur avendo i massimi privilegi tecnici del sistema, è esplicitamente escluso da questa funzionalità per separare la gestione tecnica dall'intervento sui processi HR.

---

### `F-08` — Crea / Modifica evento

**Descrizione:** Accesso al form di creazione (`/admin/eventi/nuovo`) e modifica (`/admin/eventi/:id/modifica`) degli `EVENTO`. Include la compilazione di tutti i campi dell'entità `EVENTO`, il salvataggio in bozza e la pubblicazione (transizione `stato → ATTIVO`). Include anche l'upload della locandina.

**Entità coinvolte:** `EVENTO` (INSERT per creazione, UPDATE per modifica), `UTENTE` (lettura `creato_da` per associazione), `AUDIT_LOG` (INSERT automatico per ogni modifica).

**Regole correlate:** `[REGOLA-CRUD-01]` → `[REGOLA-CRUD-03]`, `[REGOLA-INT-02]` (coerenza temporale), `[REGOLA-EV-01]` → `[REGOLA-EV-03]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Crea / Modifica evento`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Crea / Modifica evento`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Crea / Modifica evento`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Crea / Modifica evento`

---

### `F-09` — Elimina evento

**Descrizione:** Capacità di eseguire il soft-delete logico con `stato → ELIMINATO` su un `EVENTO`. L'eliminazione fisica con `DELETE` su database è bloccata se esistono `RICHIESTA` associate (qualsiasi stato). Questa funzionalità estende `F-08` aggiungendo la transizione distruttiva non reversibile.

**Entità coinvolte:** `EVENTO` (UPDATE `stato = ELIMINATO` oppure DELETE se e solo se `COUNT(RICHIESTA) = 0`), `AUDIT_LOG` (INSERT automatico).

**Regole correlate:** `[REGOLA-CRUD-04]`, `[REGOLA-CRUD-05]`, `[REGOLA-INT-03]`, `[SAFEGUARD-AUD-03]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Elimina evento`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Elimina evento`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Elimina evento`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Elimina evento`

> **Nota RBAC:** Il permesso di eliminazione è il più esclusivo del sistema: un solo ruolo su quattro. `ADMIN_HR` può **archiviare** gli eventi (incluso nell'ambito di `F-08`) ma **non eliminarli**. Il guard applicativo deve distinguere tra l'azione "Archivia" (permessa a `ADMIN_HR` e `ADMIN_IT` tramite `F-08`) e l'azione "Elimina" (permessa solo ad `ADMIN_IT` tramite `F-09`).

---

### `F-10` — Gestisce utenti e ruoli

**Descrizione:** Accesso alla gestione dell'anagrafica `UTENTE`: attivazione e disattivazione degli account (`UTENTE.attivo`), modifica del ruolo (`UTENTE.ruolo`), visualizzazione della lista completa degli utenti. Include la capacità di elevare un utente a qualsiasi ruolo, compreso `ADMIN_HR` o `ADMIN_IT`.

**Entità coinvolte:** `UTENTE` (UPDATE `attivo`, UPDATE `ruolo`, SELECT lista completa), `AUDIT_LOG` (INSERT automatico per ogni modifica).

**Regole correlate:** `[REGOLA-UT-02]`, `[REGOLA-UT-03]`, `[REGOLA-AUTH-02]` (la disattivazione ha effetto immediato su sessioni attive), `[SAFEGUARD-SEC-02]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Gestisce utenti e ruoli`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Gestisce utenti e ruoli`
- `(ADMIN_HR)` —[**NON_PUÒ_ESEGUIRE**]→ `Gestisce utenti e ruoli`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Gestisce utenti e ruoli`

> **Nota RBAC:** Anche questo permesso è esclusivo di un solo ruolo. La separazione tra `ADMIN_HR` (gestisce richieste e processi) e `ADMIN_IT` (gestisce utenti e infrastruttura) è un principio architetturale deliberato di separazione dei ruoli (Separation of Duties). `ADMIN_HR` **non può** disattivare o modificare account utente: questa capacità rimane esclusiva di `ADMIN_IT`.

---

### `F-11` — Esporta dati CSV/Excel

**Descrizione:** Generazione e download del file di export delle `RICHIESTA` filtrate per evento, stato e intervallo date. Il file contiene le 8 colonne fisse definite nella specifica: nome, email, evento, data evento, stato richiesta, data richiesta, necessità alloggio, costo evento. Il formato è CSV (UTF-8 con BOM) o XLSX nativo. Il naming del file segue il pattern `export_richieste_{stato}_{YYYYMMDD}`.

**Entità coinvolte:** `RICHIESTA` (SELECT con filtri), `UTENTE` (lettura campi nome, cognome, email), `EVENTO` (lettura campi titolo, data, costo).

**Regole correlate:** `[REGOLA-EXP-01]`, `[REGOLA-EXP-02]`, `[REGOLA-EXP-03]`, `[SAFEGUARD-SEC-04]` (il file di export è dato PII nominativo: non può essere trasmesso a endpoint cloud non autorizzati).

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Esporta dati CSV/Excel`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Esporta dati CSV/Excel`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Esporta dati CSV/Excel`
- `(ADMIN_IT)` —[**NON_PUÒ_ESEGUIRE**]→ `Esporta dati CSV/Excel`

> **Nota RBAC:** `ADMIN_IT` non può esportare dati nominativi, coerentemente con la sua esclusione dalla visibilità delle `RICHIESTA` individuali (`F-05` negato). Questo blinda la separazione: `ADMIN_IT` non può aggirare la mancanza di visibilità sulle richieste individuali tramite il meccanismo di export.

---

### `F-12` — Visualizza analytics budget

**Descrizione:** Accesso alla Dashboard Analytics del Pannello Admin con visualizzazione dei KPI: budget consumato, budget residuo, saturazione media degli eventi, tasso di approvazione, trend mensile delle richieste approvate. Include il grafico a donut della saturazione del budget formativo annuo e la barra di progressione. Il badge di allerta per budget residuo < 15% è visibile in questa sezione.

**Entità coinvolte:** `BUDGET_ANNUO` (lettura KPI aggregati), `RICHIESTA` (aggregazione per trend), `EVENTO` (aggregazione per saturazione).

**Regole correlate:** `[REGOLA-ANL-01]`, `[REGOLA-ANL-02]`, `[REGOLA-ANL-03]`, `[SAFEGUARD-TXN-05]` (il dato `budget_annuo.residuo` è la fonte operativa da leggere).

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza analytics budget`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza analytics budget`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Visualizza analytics budget`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Visualizza analytics budget`

> **Nota RBAC — Distinzione intra-ruolo:** Entrambi `ADMIN_HR` e `ADMIN_IT` hanno `PUÒ_ESEGUIRE`, ma con **profili di dato diversi**: `ADMIN_HR` vede i KPI finanziari con la possibilità di drill-down nominativo sulle singole approvazioni che compongono il totale. `ADMIN_IT` vede solo i dati aggregati anonimi, senza accesso ai dettagli nominativi. Il guard applicativo deve filtrare i dati esposti in base al ruolo, anche all'interno della stessa route.

---

### `F-13` — Visualizza audit log

**Descrizione:** Accesso alla vista dell'`AUDIT_LOG` con ricerca e filtro per entità, attore, azione e intervallo temporale. Permesso di lettura (SELECT) esclusivo: nessun ruolo umano può scrivere, modificare o eliminare record dell'`AUDIT_LOG` tramite l'interfaccia applicativa.

**Entità coinvolte:** `AUDIT_LOG` (SELECT con filtri), `UTENTE` (risoluzione `attore_id` → nominativo per la UI).

**Regole correlate:** `[REGOLA-AUDIT-01]`, `[REGOLA-AUDIT-02]`, `[REGOLA-INT-04]`, `[SAFEGUARD-AUD-01]`, `[SAFEGUARD-AUD-02]`.

- `(DIPENDENTE)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza audit log`
- `(MANAGER)` —[**NON_PUÒ_ESEGUIRE**]→ `Visualizza audit log`
- `(ADMIN_HR)` —[**PUÒ_ESEGUIRE**]→ `Visualizza audit log`
- `(ADMIN_IT)` —[**PUÒ_ESEGUIRE**]→ `Visualizza audit log`

> **Nota RBAC critica:** Il permesso `F-13` è esclusivamente di **lettura**. Anche `ADMIN_IT`, che ha accesso a questa funzionalità, non può scrivere o modificare l'`AUDIT_LOG`. L'immutabilità dell'audit trail è un vincolo orthogonale al modello RBAC: non è controllato dai permessi applicativi ma enforced a livello di grant database (`REVOKE UPDATE, DELETE`) e trigger DB. Vedere `[SAFEGUARD-AUD-01]`.

---

## Appendice: Indice Inverso (Ruolo → Funzionalità Concesse)

> Utile per il Graph RAG: permette di rispondere a query del tipo "cosa può fare ADMIN_HR?" recuperando direttamente i nodi funzionalità collegati al nodo ruolo con arco `PUÒ_ESEGUIRE`.

### `DIPENDENTE` —[PUÒ_ESEGUIRE]→

- `F-01` Visualizza catalogo eventi
- `F-02` Sottomette richiesta
- `F-03` Visualizza proprie richieste
- `F-04` Riceve notifiche in-app

### `MANAGER` —[PUÒ_ESEGUIRE]→

- `F-01` Visualizza catalogo eventi
- `F-02` Sottomette richiesta *(in quanto eredita le capacità di DIPENDENTE per il Portale Utente)*
- `F-03` Visualizza proprie richieste *(eredita)*
- `F-04` Riceve notifiche in-app *(eredita)*
- `F-05` Vede coda approvazione *(solo richieste del proprio team)*
- `F-06` Approva / Rifiuta richiesta *(solo richieste del proprio team)*

### `ADMIN_HR` —[PUÒ_ESEGUIRE]→

- `F-01` Visualizza catalogo eventi
- `F-05` Vede coda approvazione *(visibilità globale su tutto il sistema)*
- `F-07` Override stato richiesta
- `F-08` Crea / Modifica evento *(incluso archiviazione, esclusa eliminazione)*
- `F-11` Esporta dati CSV/Excel
- `F-12` Visualizza analytics budget *(con drill-down nominativo)*
- `F-13` Visualizza audit log

### `ADMIN_IT` —[PUÒ_ESEGUIRE]→

- `F-01` Visualizza catalogo eventi
- `F-08` Crea / Modifica evento
- `F-09` Elimina evento *(solo se zero RICHIESTA associate)*
- `F-10` Gestisce utenti e ruoli
- `F-12` Visualizza analytics budget *(solo dati aggregati anonimi)*
- `F-13` Visualizza audit log *(sola lettura)*

---

*Fine del documento — `docs/00_meta_governance/matrice_permessi.md` v1.0.0*
