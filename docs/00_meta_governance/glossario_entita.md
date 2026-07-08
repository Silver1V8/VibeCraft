---
id: "glossario-entita-v1.0"
title: "Glossario Entità — Single Source of Truth del Modello Dati"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-01"
status: "ENFORCED"
classification: "DATA_DICTIONARY"
path: "docs/00_meta_governance/glossario_entita.md"
source_document: "ANALISI_FUNZIONALE.md v1.0.0"
authors:
  - role: "Senior Data Engineer"
  - role: "Knowledge Graph Engineer"
graph_rag:
  node_type: "DATA_DICTIONARY"
  node_id: "glossario-entita-v1.0"
  entity_count: 5
  entities:
    - "EVENTO"
    - "UTENTE"
    - "RICHIESTA"
    - "NOTIFICA"
    - "AUDIT_LOG"
  edges:
    - type: "DERIVA_DA"
      target: "ANALISI_FUNZIONALE"
      sections: ["0.2", "4.2", "4.3"]
    - type: "VINCOLA"
      target: "TUTTI_I_MODULI_APPLICATIVI"
    - type: "DIPENDE_DA"
      target: "safeguards-security-v1.2"
    - type: "REFERENZIATO_DA"
      target: "PARTE_1_PORTALE_UTENTE"
    - type: "REFERENZIATO_DA"
      target: "PARTE_2_WORKFLOW_APPROVAZIONE"
    - type: "REFERENZIATO_DA"
      target: "PARTE_3_PANNELLO_ADMIN"
    - type: "DEFINISCE"
      target: "SCHEMA_LOGICO_APPLICATIVO"
tags:
  - data-dictionary
  - entity
  - domain-model
  - graph-rag
  - single-source-of-truth
  - local-first
  - iron-memory
  - evento
  - utente
  - richiesta
  - notifica
  - audit-log
  - integrity
  - concurrency
  - workflow
---

# Glossario Entità — Single Source of Truth del Modello Dati
## `VibeCraft` — Sistema di Gestione Eventi Aziendali

> **Nota per l'AI Coding Agent e il sistema Graph RAG**
>
> Questo documento è il **dizionario dati canonico** del progetto. Ogni entità è descritta come nodo atomico e autosufficiente. Tutte le relazioni tra entità, tutti i vincoli di integrità e tutte le regole di business che operano direttamente sul dato sono centralizzate qui. In caso di conflitto tra questo documento e qualsiasi altra fonte di contesto sullo schema dei dati, questo documento ha la precedenza.
>
> Le regole citate (`[REGOLA-XXX-NN]`) sono archi espliciti nel grafo verso il nodo corrispondente dell'`ANALISI_FUNZIONALE.md`. Il sistema Graph RAG deve privilegiare il recupero congiunto di questa scheda entità e delle regole ad essa collegate per rispondere a query sul dato.

---

## Indice delle Entità

| Entità | Ruolo nel sistema | Owner primario | Tipo di ciclo di vita |
|---|---|---|---|
| [`EVENTO`](#entità-evento) | Catalogo opportunità formative | `ADMIN_HR` / `ADMIN_IT` | Managed (CRUD con soft-delete) |
| [`UTENTE`](#entità-utente) | Anagrafica e identità di sistema | `ADMIN_IT` | Managed (attivazione/revoca) |
| [`RICHIESTA`](#entità-richiesta) | Pratica di partecipazione con workflow | `DIPENDENTE` / `MANAGER` | State-machine (4 stati terminali) |
| [`NOTIFICA`](#entità-notifica) | Comunicazione derivata da evento di stato | Sistema (automatica) | Append + aggiornamento `stato_consegna` |
| [`AUDIT_LOG`](#entità-audit_log) | Tracciamento immutabile delle mutazioni | Sistema (automatica) | Append-only assoluto |

---

## Mappa ERD sintetica

```
UTENTE ||--o{ RICHIESTA : "sottomette (richiedente_id)"
UTENTE ||--o{ RICHIESTA : "decide (manager_id)"
UTENTE ||--o{ EVENTO    : "crea (creato_da)"
EVENTO ||--o{ RICHIESTA : "riceve (evento_id)"
RICHIESTA ||--o{ NOTIFICA  : "genera (richiesta_id)"
RICHIESTA ||--o{ AUDIT_LOG : "traccia (entita_id)"
UTENTE    }o--o{ AUDIT_LOG  : "agisce (attore_id, nullable)"
```

---

## Entità: `EVENTO`

**Definizione:** Un evento formativo o professionale esterno all'azienda per il quale i dipendenti possono richiedere la partecipazione tramite una `RICHIESTA`. È l'oggetto centrale del catalogo gestito dagli amministratori. Rappresenta sia l'offerta formativa (dati descrittivi) sia il contenitore di disponibilità (posti) e la dimensione finanziaria (costo, budget).

**Owner primario:** `ADMIN_HR` (creazione, modifica, archiviazione), `ADMIN_IT` (eliminazione logica).

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Univoco nel sistema. Generato automaticamente alla creazione. Immutabile dopo la creazione. |
| `titolo` | `VARCHAR(150)` | **Sì** | Lunghezza massima 150 caratteri. Non può essere stringa vuota. |
| `descrizione` | `TEXT` | **Sì** | Lunghezza massima 5000 caratteri. Non può essere stringa vuota. |
| `data_inizio` | `TIMESTAMPTZ` | **Sì** | Deve essere futura rispetto al momento della creazione dell'evento. |
| `data_fine` | `TIMESTAMPTZ` | **Sì** | Deve essere successiva a `data_inizio`. Il sistema rigetta `data_fine ≤ data_inizio`. |
| `luogo` | `VARCHAR` | **Sì** | Indirizzo fisico completo (città + via) oppure il valore letterale `"Online"`. Non può essere stringa vuota. |
| `posti_totali` | `INTEGER` | **Sì** | Deve essere `> 0`. Immutabile dopo la prima `RICHIESTA` associata all'evento. |
| `posti_residui` | `INTEGER` | **Sì** | Campo gestito dal sistema, non editabile manualmente dall'utente. Formula operativa: `posti_totali − COUNT(RICHIESTA WHERE evento_id = id AND stato = 'APPROVATA')`. Soggetto a lock transazionale per la scrittura (vedi `[REGOLA-CONC-01]`). Constraint database: `CHECK (posti_residui >= 0 AND posti_residui <= posti_totali)`. |
| `costo_unitario` | `NUMERIC(10,2)` | **Sì** | In EUR. Può essere `0` (evento gratuito). Non può essere negativo. |
| `budget_allocato` | `NUMERIC(10,2)` | No | Budget massimo aziendale destinato a questo specifico evento. Se assente (`NULL`), il campo non viene mostrato nell'interfaccia utente. Se presente, deve essere `≥ 0`. |
| `scadenza_iscrizioni` | `TIMESTAMPTZ` | **Sì** | Deve essere strettamente `< data_inizio`. Superata questa soglia, nessuna nuova `RICHIESTA` può essere creata per questo evento (blocco automatico di sistema). |
| `locandina_url` | `VARCHAR` | No | URL assoluto dell'immagine caricata sul sistema di storage. Formati accettati al caricamento: PNG, JPG, WebP. Dimensione massima file: 5 MB. Il campo viene popolato dal sistema dopo l'upload; non è editabile manualmente. |
| `stato` | `ENUM` | **Sì** | Valori ammessi: `ATTIVO`, `ARCHIVIATO`, `ELIMINATO`. Default alla creazione: `ATTIVO` (o equivalente "bozza" se salvato incompleto). Solo `ADMIN_IT` può portare lo stato a `ELIMINATO` logico; `ADMIN_HR` può portarlo solo ad `ARCHIVIATO`. |
| `creato_da` | `UUID` FK → `UTENTE.id` | **Sì** | Riferimento all'`UTENTE` con ruolo `ADMIN_HR` o `ADMIN_IT` che ha creato l'evento. Immutabile dopo la creazione. |
| `creato_il` | `TIMESTAMPTZ` | **Sì** | Timestamp di creazione. Generato automaticamente dal sistema. Immutabile. Include timezone. |
| `aggiornato_il` | `TIMESTAMPTZ` | **Sì** | Timestamp dell'ultima modifica a qualsiasi campo dell'entità. Aggiornato automaticamente dal sistema ad ogni `UPDATE`. Include timezone. |

---

### Relazioni

- `EVENTO ||--o{ RICHIESTA` — Un `EVENTO` può ricevere zero o più `RICHIESTA`. Ogni `RICHIESTA` appartiene a esattamente un `EVENTO`. La relazione è mediata da `RICHIESTA.evento_id` (FK). La cancellazione fisica di un `EVENTO` con `RICHIESTA` associate è bloccata a livello di FK constraint (`ON DELETE RESTRICT`).

- `UTENTE ||--o{ EVENTO` (crea) — Un `UTENTE` con ruolo `ADMIN` può creare zero o più `EVENTO`. Ogni `EVENTO` ha esattamente un creatore, referenziato da `EVENTO.creato_da`.

---

### Vincoli di Integrità e Regole Correlate

| Codice regola | Sorgente AFU | Effetto sul dato |
|---|---|---|
| `[REGOLA-EV-01]` | Sezione 0.2 | Un `EVENTO` con `stato = ARCHIVIATO` non può ricevere nuove `RICHIESTA`. Il sistema rigetta qualsiasi tentativo di `INSERT` su `RICHIESTA` che referenzia un `EVENTO` non `ATTIVO`. |
| `[REGOLA-EV-02]` | Sezione 0.2 | Se `NOW() >= scadenza_iscrizioni`, il sistema blocca automaticamente nuove prenotazioni indipendentemente dal valore di `posti_residui`. Il blocco è a livello applicativo (verifica server-side), non a livello di constraint DB. |
| `[REGOLA-EV-03]` | Sezione 0.2 | `posti_residui` non può mai assumere valore `< 0`. Questo vincolo è enforced sia da constraint `CHECK` a livello DB sia da logica applicativa transazionale. |
| `[REGOLA-INT-02]` | Sezione 4.3 | **Coerenza temporale**: `scadenza_iscrizioni` deve essere sempre `< data_inizio`. Un record `EVENTO` con `scadenza_iscrizioni ≥ data_inizio` non è valido. Deve essere rigettato al momento della scrittura (INSERT o UPDATE). |
| `[REGOLA-INT-03]` | Sezione 4.3 | **Non eliminabilità referenziale**: un `EVENTO` referenziato da almeno una `RICHIESTA` (in qualsiasi stato) non può essere eliminato fisicamente con `DELETE`. L'unica operazione ammessa è il soft-delete logico (`UPDATE stato = 'ARCHIVIATO'` o `'ELIMINATO'`). |
| `[REGOLA-INT-06]` | Sezione 4.3 | **Atomicità del decremento posti**: l'aggiornamento di `posti_residui` e la scrittura della `RICHIESTA` correlata devono avvenire nella stessa transazione database con lock pessimistico (`SELECT ... FOR UPDATE`). Non è mai ammesso un aggiornamento di `posti_residui` disgiunto dalla scrittura della `RICHIESTA`. |
| `[REGOLA-INT-07]` | Sezione 4.3 | **Non negatività**: `0 ≤ posti_residui ≤ posti_totali` deve essere soddisfatto in ogni istante. Qualunque operazione che violi questo intervallo deve essere respinta a livello di transazione con rollback, non solo segnalata a livello applicativo. |
| `[REGOLA-CONC-01]` → `[REGOLA-CONC-06]` | Sezione 2.3 | Il campo `posti_residui` è il target del meccanismo di lock pessimistico transazionale per gestire la concorrenza sull'ultimo posto disponibile. Il controllo e il decremento di `posti_residui` devono avvenire dentro un `SELECT ... FOR UPDATE` sulla riga `EVENTO`, serializzando le operazioni concorrenti. |
| `[REGOLA-CRUD-01]` | Sezione 3.2 | Alla creazione, tutti i campi obbligatori devono essere validati prima della pubblicazione dell'evento (il campo `stato` deve passare a `ATTIVO`). Una bozza con campi incompleti ha `stato ≠ ATTIVO`. |
| `[REGOLA-CRUD-03]` | Sezione 3.2 | L'upload del campo `locandina_url` accetta esclusivamente PNG, JPG, WebP con dimensione massima 5 MB. Un formato o dimensione non valida deve essere rigettata prima che il file venga trasmesso al sistema di storage. |
| `[REGOLA-CRUD-04]` | Sezione 3.2 | La transizione `stato → ELIMINATO` è riservata a `ADMIN_IT`. La transizione `stato → ARCHIVIATO` è disponibile a `ADMIN_HR` e `ADMIN_IT`. Nessun altro ruolo può modificare lo stato dell'evento. |
| `[REGOLA-CRUD-05]` | Sezione 3.2 | Un `EVENTO` con almeno una `RICHIESTA` associata (in qualunque stato, incluso `ANNULLATA`) non può essere eliminato fisicamente. Può essere solo archiviato. Questo vincolo si applica anche ad `ADMIN_IT`. |

---

## Entità: `UTENTE`

**Definizione:** Qualsiasi persona fisica che accede al sistema tramite autenticazione Google OAuth con un account del dominio `@progettopa.it`. Il ruolo assegnato determina integralmente le funzionalità accessibili e le azioni permesse sull'intero sistema. È l'entità di identità centrale, referenziata da `RICHIESTA`, `EVENTO`, `NOTIFICA` e `AUDIT_LOG`.

**Owner primario:** `ADMIN_IT` (gestione ruoli, attivazione/disattivazione).

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Univoco nel sistema. Generato automaticamente alla prima autenticazione riuscita. Immutabile. |
| `email` | `VARCHAR` | **Sì** | Deve appartenere al dominio `@progettopa.it` (verificato server-side post-OAuth, non solo client-side). Univoca nel sistema (`UNIQUE constraint`). Immutabile dopo la creazione (l'email è il riferimento identitario stabile). Constraint DB suggerito: `CHECK (email LIKE '%@progettopa.it')`. |
| `nome` | `VARCHAR` | **Sì** | Derivato automaticamente dal profilo Google OAuth al momento della prima autenticazione. Aggiornabile manualmente da `ADMIN_IT`. Non può essere stringa vuota. |
| `cognome` | `VARCHAR` | **Sì** | Derivato automaticamente dal profilo Google OAuth al momento della prima autenticazione. Aggiornabile manualmente da `ADMIN_IT`. Non può essere stringa vuota. |
| `avatar_url` | `VARCHAR` | No | URL dell'immagine profilo Google. Derivato dal profilo OAuth. Può essere `NULL` se l'account Google non ha immagine profilo. Non viene validato nella forma (URL esterno Google). |
| `ruolo` | `ENUM` | **Sì** | Valori ammessi: `DIPENDENTE`, `MANAGER`, `ADMIN_HR`, `ADMIN_IT`. Default alla prima autenticazione: `DIPENDENTE`. L'elevazione a qualsiasi altro ruolo richiede un'azione manuale esplicita da parte di un `ADMIN_IT`. Un `UTENTE` ha esattamente un ruolo in ogni istante (nessun ruolo composito). |
| `attivo` | `BOOLEAN` | **Sì** | Default: `true`. Se `false`, l'utente non può accedere ad alcuna funzionalità del sistema, incluse sessioni già aperte (revoca immediata, verificata ad ogni request autenticata). La disattivazione è un'azione di `ADMIN_IT`. |
| `creato_il` | `TIMESTAMPTZ` | **Sì** | Timestamp della prima autenticazione OAuth riuscita (primo login). Generato automaticamente. Immutabile. Include timezone. |
| `ultimo_accesso` | `TIMESTAMPTZ` | No | Timestamp aggiornato ad ogni login riuscito. Può essere `NULL` in contesti di migrazione dati. Non immutabile (viene aggiornato ad ogni accesso). |

---

### Relazioni

- `UTENTE ||--o{ RICHIESTA` (sottomette) — Un `UTENTE` con ruolo `DIPENDENTE` può creare zero o più `RICHIESTA`. Ogni `RICHIESTA` ha esattamente un `richiedente_id` che punta a un `UTENTE`. La relazione è mediata da `RICHIESTA.richiedente_id`.

- `UTENTE ||--o{ RICHIESTA` (decide) — Un `UTENTE` con ruolo `MANAGER` può approvare o rifiutare zero o più `RICHIESTA`. Ogni `RICHIESTA` ha al massimo un `manager_id` (può essere `NULL` finché `stato = IN_ATTESA`). La relazione è mediata da `RICHIESTA.manager_id`.

- `UTENTE ||--o{ EVENTO` (crea) — Un `UTENTE` con ruolo `ADMIN_HR` o `ADMIN_IT` può creare zero o più `EVENTO`. Ogni `EVENTO` ha esattamente un `UTENTE` creatore referenziato da `EVENTO.creato_da`.

- `UTENTE ||--o{ NOTIFICA` (riceve) — Un `UTENTE` può ricevere zero o più `NOTIFICA`. La relazione è mediata da `NOTIFICA.destinatario_id`.

- `UTENTE }o--o{ AUDIT_LOG` (agisce) — Un `UTENTE` può essere l'attore di zero o più record `AUDIT_LOG`. La relazione è mediata da `AUDIT_LOG.attore_id`, che può essere `NULL` per azioni automatiche di sistema.

---

### Vincoli di Integrità e Regole Correlate

| Codice regola | Sorgente AFU | Effetto sul dato |
|---|---|---|
| `[REGOLA-UT-01]` | Sezione 0.2 | Solo email con dominio `@progettopa.it` possono essere presenti nella tabella `UTENTE`. La verifica del dominio avviene server-side dopo il callback OAuth, prima di qualsiasi `INSERT` o `UPDATE` sulla tabella. Email di altri domini devono essere rigettate con errore esplicito `DOMAIN_NOT_ALLOWED`, senza creare record. |
| `[REGOLA-UT-02]` | Sezione 0.2 | Un `UTENTE` con `attivo = false` non può accedere ad alcuna funzionalità. Il campo `attivo` deve essere verificato ad ogni richiesta autenticata (non solo al login). La verifica deve essere eseguita su database primario, non su cache con lag potenziale. |
| `[REGOLA-UT-03]` | Sezione 0.2 | Il ruolo di default per ogni nuovo `UTENTE` è `DIPENDENTE`. L'elevazione di ruolo è un'azione manuale eseguita esclusivamente da `ADMIN_IT`. Nessun meccanismo automatico o auto-elevazione è ammessa. |
| `[REGOLA-AUTH-01]` | Sezione 1.1 | Il dominio `@progettopa.it` è l'unico dominio autorizzato. La verifica deve includere il campo `email_verified = true` dal token Google, non solo il dominio. |
| `[REGOLA-AUTH-02]` | Sezione 1.1 | `UTENTE.attivo = false` implica invalidazione immediata di tutte le sessioni attive dell'utente, non attesa della scadenza naturale del token. Il campo `attivo` è soggetto a verifica ad ogni request, con TTL cache massimo di 30 secondi. |
| `[REGOLA-AUTH-03]` | Sezione 1.1 | Il redirect post-autenticazione è sempre verso `/eventi`. Non è configurabile per utente. |
| `[REGOLA-AUTH-04]` | Sezione 1.1 | Il token di sessione ha durata massima di 8 ore. Alla scadenza viene eseguito re-login silenzioso se la sessione Google è attiva; altrimenti redirect a `/login`. |

---

## Entità: `RICHIESTA`

**Definizione:** La pratica formale sottomessa da un `UTENTE` con ruolo `DIPENDENTE` per richiedere l'autorizzazione a partecipare a un `EVENTO`. È l'entità centrale del workflow di approvazione e la principale fonte di eventi per `NOTIFICA` e `AUDIT_LOG`. Il suo ciclo di vita è governato da una macchina a stati finita con quattro stati, di cui tre terminali.

**Owner primario:** `DIPENDENTE` (creazione), `MANAGER` (transizioni di approvazione/rifiuto), `ADMIN_HR` (override), Sistema (transizioni automatiche).

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Univoco nel sistema. Generato automaticamente alla sottomissione. Immutabile. |
| `evento_id` | `UUID` FK → `EVENTO.id` | **Sì** | Riferimento all'`EVENTO` target. Al momento della creazione, l'`EVENTO` referenziato deve avere `stato = ATTIVO` e `posti_residui > 0` e `NOW() < scadenza_iscrizioni`. FK con `ON DELETE RESTRICT` (l'evento non può essere eliminato finché questa richiesta esiste). |
| `richiedente_id` | `UUID` FK → `UTENTE.id` | **Sì** | Riferimento all'`UTENTE` che sottomette la richiesta. Deve avere `ruolo = DIPENDENTE` al momento della creazione. Immutabile dopo la creazione. |
| `motivazione` | `TEXT` | **Sì** | Lunghezza minima 50 caratteri. Lunghezza massima 2000 caratteri. Non può essere stringa vuota o solo spazi bianchi. Classificato come PII: non deve essere trasmesso a sistemi esterni non autorizzati (vedi `[SAFEGUARD-SEC-04]` del Design Contract). |
| `necessita_alloggio` | `BOOLEAN` | **Sì** | Default: `false`. Indica se il dipendente richiede sistemazione alberghiera. Non ha effetti automatici sul workflow: è un dato informativo per il Manager. |
| `note_aggiuntive` | `TEXT` | No | Lunghezza massima 500 caratteri. Campo libero opzionale. Può essere `NULL`. Classificato come PII. |
| `stato` | `ENUM` | **Sì** | Valori ammessi: `IN_ATTESA`, `APPROVATA`, `RIFIUTATA`, `ANNULLATA`. Default alla creazione: `IN_ATTESA`. La macchina a stati ammette solo le transizioni: `IN_ATTESA → APPROVATA` (Manager), `IN_ATTESA → RIFIUTATA` (Manager), `IN_ATTESA → ANNULLATA` (Dipendente). `APPROVATA`, `RIFIUTATA`, `ANNULLATA` sono stati terminali (nessuna ulteriore transizione automatica). L'override da `ADMIN_HR` può forzare qualsiasi stato ma deve essere tracciato. |
| `commento_manager` | `TEXT` | **Condizionale** | **Obbligatorio se e solo se `stato = RIFIUTATA`**. Deve essere `NOT NULL` e non-vuoto quando lo stato è `RIFIUTATA`. Deve essere `NULL` per tutti gli altri stati. Il sistema rigetta qualsiasi tentativo di scrivere `stato = RIFIUTATA` senza `commento_manager` valorizzato. Classificato come PII. |
| `manager_id` | `UUID` FK → `UTENTE.id` | No | Riferimento all'`UTENTE` con ruolo `MANAGER` che ha eseguito la decisione. `NULL` quando `stato = IN_ATTESA` (nessun manager ha ancora interagito). Popolato atomicamente insieme alla transizione di stato. |
| `data_decisione` | `TIMESTAMPTZ` | No | Timestamp della transizione di stato da `IN_ATTESA` a qualsiasi altro stato. `NULL` quando `stato = IN_ATTESA`. Popolato atomicamente dal sistema con `NOW()` al momento della transizione. Include timezone. Immutabile dopo il popolamento. |
| `creata_il` | `TIMESTAMPTZ` | **Sì** | Timestamp della sottomissione della richiesta. Generato automaticamente. Immutabile. Include timezone. Usato come campo di ordinamento default nella lista "Le mie richieste" (discendente). |
| `aggiornata_il` | `TIMESTAMPTZ` | **Sì** | Timestamp dell'ultimo aggiornamento a qualsiasi campo dell'entità. Aggiornato automaticamente dal sistema ad ogni `UPDATE`. Include timezone. |

---

### Relazioni

- `RICHIESTA }o--|| EVENTO` — Ogni `RICHIESTA` appartiene a esattamente un `EVENTO` (`evento_id NOT NULL`). Un `EVENTO` può avere zero o più `RICHIESTA`.

- `RICHIESTA }o--|| UTENTE` (richiedente) — Ogni `RICHIESTA` è sottomessa da esattamente un `UTENTE` (`richiedente_id NOT NULL`). Un `UTENTE` può avere zero o più `RICHIESTA` come richiedente.

- `RICHIESTA }o--o| UTENTE` (manager) — Ogni `RICHIESTA` può essere processata da al massimo un `UTENTE` con ruolo `MANAGER` (`manager_id` nullable). Un `MANAGER` può processare zero o più `RICHIESTA`.

- `RICHIESTA ||--o{ NOTIFICA` — Ogni `RICHIESTA` genera zero o più `NOTIFICA` nel corso del suo ciclo di vita. Ogni `NOTIFICA` appartiene a esattamente una `RICHIESTA` (`richiesta_id NOT NULL`).

- `RICHIESTA ||--o{ AUDIT_LOG` — Ogni transizione di stato di una `RICHIESTA` genera esattamente un record `AUDIT_LOG`. Ogni record `AUDIT_LOG` di tipo `RICHIESTA` è associato a esattamente una `RICHIESTA` (`entita_id = RICHIESTA.id`, `entita_tipo = 'RICHIESTA'`).

---

### Macchina a Stati (ciclo di vita completo)

```
[CREAZIONE] ──────────────────────────────► IN_ATTESA
                                                │
                        ┌───────────────────────┤
                        │                       │
              (Manager approva)       (Dipendente annulla)
                        │                       │
                        ▼                       ▼
                   APPROVATA              ANNULLATA [terminale]
                   [terminale]
                        
              (Manager rifiuta)
                        │
                        ▼
                   RIFIUTATA [terminale]

Override ADMIN_HR: qualsiasi stato → qualsiasi stato (tracciato su AUDIT_LOG)
```

**Effetti collaterali per stato:**

| Transizione | Effetto su `posti_residui` | Notifiche generate | Audit log |
|---|---|---|---|
| Creazione → `IN_ATTESA` | Nessuno | `NUOVA_RICHIESTA` → Manager | Sì |
| `IN_ATTESA` → `APPROVATA` | Decremento atomico `-1` | `APPROVAZIONE` → Dipendente | Sì |
| `IN_ATTESA` → `RIFIUTATA` | Nessuno | `RIFIUTO` → Dipendente | Sì |
| `IN_ATTESA` → `ANNULLATA` | Nessuno | Nessuna | Sì |
| Override `ADMIN_HR` | Varia (verifica posti se → `APPROVATA`) | Nessuna (automatica) | Sì (`azione = OVERRIDE_MANUALE`) |

---

### Vincoli di Integrità e Regole Correlate

| Codice regola | Sorgente AFU | Effetto sul dato |
|---|---|---|
| `[REGOLA-RQ-01]` | Sezione 0.2 | Un `UTENTE` non può avere più di una `RICHIESTA` con `stato IN ('IN_ATTESA', 'APPROVATA')` per lo stesso `EVENTO` nello stesso istante. Tentativo di INSERT duplicato deve essere rigettato. |
| `[REGOLA-RQ-02]` | Sezione 0.2 | Impossibile creare una `RICHIESTA` se `EVENTO.posti_residui = 0` al momento della verifica server-side. Il controllo avviene dentro la transazione con lock pessimistico. |
| `[REGOLA-RQ-03]` | Sezione 0.2 | Impossibile creare una `RICHIESTA` se `NOW() >= EVENTO.scadenza_iscrizioni`. |
| `[REGOLA-RQ-04]` | Sezione 0.2 | `commento_manager` è obbligatorio se e solo se `stato = RIFIUTATA`. Qualsiasi altra combinazione (campo presente con stato diverso da `RIFIUTATA`, o campo assente con `stato = RIFIUTATA`) costituisce un dato non valido da rigettare. |
| `[REGOLA-INT-01]` | Sezione 4.3 | **Unicità composita**: la coppia `(richiedente_id, evento_id)` non può avere più di un record con `stato IN ('IN_ATTESA', 'APPROVATA')`. Implementato come partial unique index sul database: `UNIQUE (richiedente_id, evento_id) WHERE stato IN ('IN_ATTESA', 'APPROVATA')`. |
| `[REGOLA-INT-05]` | Sezione 4.3 | **Coerenza commento di rifiuto**: il constraint logico `(stato = 'RIFIUTATA' ↔ commento_manager IS NOT NULL AND commento_manager != '')` deve essere garantito sia a livello applicativo sia tramite trigger DB. |
| `[REGOLA-INT-06]` | Sezione 4.3 | **Atomicità**: la scrittura di `RICHIESTA` (INSERT o UPDATE stato) e l'aggiornamento di `EVENTO.posti_residui` devono avvenire nella stessa transazione. Mai due operazioni separate. |
| `[REGOLA-WF-01]` | Sezione 2.1 | `APPROVATA`, `RIFIUTATA`, `ANNULLATA` sono stati terminali. Nessuna transizione automatica successiva è ammessa senza override esplicito `ADMIN_HR`. |
| `[REGOLA-WF-02]` | Sezione 2.1 | La transizione verso `ANNULLATA` è eseguibile esclusivamente dal `DIPENDENTE` richiedente e solo quando `stato = IN_ATTESA`. |
| `[REGOLA-WF-03]` | Sezione 2.1 | Ogni transizione di stato genera obbligatoriamente un record `AUDIT_LOG` con `valore_precedente` e `valore_nuovo`. La scrittura dell'`AUDIT_LOG` avviene nella stessa transazione della transizione di stato. |
| `[REGOLA-VAL-01]` | Sezione 2.3 | Blocco server-side della creazione se `posti_residui = 0`. Il controllo non è delegabile al solo frontend. |
| `[REGOLA-VAL-02]` | Sezione 2.3 | Blocco server-side della creazione se `NOW() >= scadenza_iscrizioni`. |
| `[REGOLA-VAL-03]` | Sezione 2.3 | Blocco server-side se esiste già una `RICHIESTA` attiva `(IN_ATTESA, APPROVATA)` per la stessa coppia `(richiedente_id, evento_id)`. |
| `[REGOLA-VAL-04]` | Sezione 2.3 | Blocco dell'approvazione Manager se `posti_residui` è diventato `0` tra il caricamento della coda e il click "Approva" (race condition inter-manager). |
| `[REGOLA-CONC-01]` → `[REGOLA-CONC-06]` | Sezione 2.3 | Il meccanismo di lock pessimistico (`SELECT ... FOR UPDATE` su `EVENTO`) serializza le scritture concorrenti su `RICHIESTA` che coinvolgono `posti_residui`. Nessuna prenotazione provvisoria lato client è ammessa come sostituto. |
| `[REGOLA-OVR-01]` | Sezione 3.3 | L'override manuale dello stato da parte di `ADMIN_HR` è ammesso su qualsiasi `RICHIESTA`, inclusi stati terminali. |
| `[REGOLA-OVR-02]` | Sezione 3.3 | Un override verso `APPROVATA` deve rieseguire il controllo `posti_residui > 0` prima di confermare. Se i posti sono esauriti, l'override è bloccato. |
| `[REGOLA-OVR-03]` | Sezione 3.3 | Ogni override genera un record `AUDIT_LOG` con `azione = OVERRIDE_MANUALE` e `attore_id` dell'`ADMIN_HR`. Non è mai ammesso un override silenzioso. |
| `[REGOLA-PERS-03]` | Sezione 1.5 | L'annullamento (`IN_ATTESA → ANNULLATA`) da parte del Dipendente genera un record `AUDIT_LOG` e ricalcola `posti_residui`. L'effetto su `posti_residui` avviene atomicamente nella stessa transazione. |

---

## Entità: `NOTIFICA`

**Definizione:** Un messaggio automatico generato dal sistema in risposta a un cambio di stato di una `RICHIESTA`. Rappresenta una comunicazione uscente verso uno specifico `UTENTE` su uno specifico canale. Non è editabile dall'utente né dall'amministratore: è un artefatto puramente derivato e gestito dal sistema. Il suo stato (`stato_consegna`) viene aggiornato dal sistema di delivery asincrono.

**Owner primario:** Sistema (generazione automatica). Nessun ruolo umano crea o modifica `NOTIFICA` direttamente.

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Univoco nel sistema. Generato automaticamente alla creazione. Immutabile. |
| `richiesta_id` | `UUID` FK → `RICHIESTA.id` | **Sì** | Riferimento alla `RICHIESTA` che ha innescato la notifica. Non può essere `NULL`. Immutabile. FK con `ON DELETE RESTRICT` (la richiesta non può essere eliminata fisicamente se esistono notifiche associate, ma questa è già coperta dalla non-eliminabilità referenziale dell'`EVENTO`). |
| `destinatario_id` | `UUID` FK → `UTENTE.id` | **Sì** | Riferimento all'`UTENTE` che deve ricevere la notifica. Non può essere `NULL`. Immutabile. |
| `canale` | `ENUM` | **Sì** | Valori ammessi: `EMAIL`, `SLACK`, `IN_APP`. Immutabile dopo la creazione. Un singolo evento trigger può generare più record `NOTIFICA` (uno per canale). |
| `tipo` | `ENUM` | **Sì** | Valori ammessi: `NUOVA_RICHIESTA`, `APPROVAZIONE`, `RIFIUTO`, `SCADENZA_IMMINENTE`. Determina il template del messaggio e le variabili dinamiche da iniettare. Immutabile dopo la creazione. |
| `stato_consegna` | `ENUM` | **Sì** | Valori ammessi: `IN_CODA`, `CONSEGNATA`, `FALLITA`. Default alla creazione: `IN_CODA`. Aggiornato dal sistema di delivery asincrono. Transizioni ammesse: `IN_CODA → CONSEGNATA`, `IN_CODA → FALLITA`. Nessun retry automatico dopo `FALLITA` (richiede intervento manuale). |
| `tentativo_n` | `INTEGER` | **Sì** | Contatore dei tentativi di invio eseguiti. Default: `0`. Incrementato ad ogni tentativo. Valore massimo: `3`. Al raggiungimento del limite con `stato_consegna = FALLITA`, viene generato un alert per `ADMIN_IT`. Non può essere negativo. |
| `inviata_il` | `TIMESTAMPTZ` | No | Timestamp della consegna riuscita. `NULL` fino a `stato_consegna = CONSEGNATA`. Popolato automaticamente dal sistema di delivery. Include timezone. Immutabile dopo il popolamento. |
| `creata_il` | `TIMESTAMPTZ` | **Sì** | Timestamp della creazione del record. Generato automaticamente. Immutabile. Include timezone. |

---

### Relazioni

- `NOTIFICA }o--|| RICHIESTA` — Ogni `NOTIFICA` è generata da esattamente una `RICHIESTA` (`richiesta_id NOT NULL`). Una `RICHIESTA` può generare zero o più `NOTIFICA` nel suo ciclo di vita (una per ogni evento trigger, per ogni canale).

- `NOTIFICA }o--|| UTENTE` (destinatario) — Ogni `NOTIFICA` ha esattamente un `UTENTE` destinatario (`destinatario_id NOT NULL`). Un `UTENTE` può ricevere zero o più `NOTIFICA`.

---

### Matrice Trigger → Notifiche Generate

| Trigger | Destinatario | Canali | `tipo` |
|---|---|---|---|
| `RICHIESTA` creata (stato → `IN_ATTESA`) | `MANAGER` del richiedente | `EMAIL`, `SLACK`, `IN_APP` | `NUOVA_RICHIESTA` |
| `RICHIESTA` → `APPROVATA` | `DIPENDENTE` richiedente | `EMAIL`, `IN_APP` | `APPROVAZIONE` |
| `RICHIESTA` → `RIFIUTATA` | `DIPENDENTE` richiedente | `EMAIL`, `IN_APP` | `RIFIUTO` |
| `EVENTO.scadenza_iscrizioni` tra 48h | `MANAGER` con richieste pendenti | `SLACK` | `SCADENZA_IMMINENTE` |

*Ogni riga della matrice può generare più record `NOTIFICA` (uno per canale). Il trigger `NUOVA_RICHIESTA` su tre canali genera 3 record `NOTIFICA` distinti.*

---

### Vincoli di Integrità e Regole Correlate

| Codice regola | Sorgente AFU | Effetto sul dato |
|---|---|---|
| `[REGOLA-NOTIF-SYS-01]` | Sezione 2.4 | Il campo `tentativo_n` è limitato a `3`. Al terzo tentativo fallito, `stato_consegna` deve essere impostato a `FALLITA` e deve essere generato un alert per `ADMIN_IT`. Nessun quarto tentativo automatico. |
| `[REGOLA-NOTIF-SYS-02]` | Sezione 2.4 | Le variabili dinamiche dei template (es. `{{evento.titolo}}`, `{{manager.nome}}`) sono popolate al momento dell'invio dal record `RICHIESTA` corrente, non da snapshot precedenti. Questo implica che il sistema di delivery deve avere accesso a `RICHIESTA`, `EVENTO` e `UTENTE` nel momento dell'invio. |
| `[REGOLA-NOTIF-SYS-03]` | Sezione 2.4 | Il sistema di delivery delle `NOTIFICA` è **asincrono** rispetto alla transazione di cambio stato della `RICHIESTA`. Un fallimento di delivery non deve mai causare il rollback della transazione di approvazione/rifiuto. La `NOTIFICA` viene inserita nella coda (`IN_CODA`) dentro la transazione di cambio stato; l'invio effettivo avviene fuori transazione. |
| `[REGOLA-NOTIF-01]` | Sezione 1.5 | Ogni cambio di stato di una `RICHIESTA` genera almeno una `NOTIFICA` con `canale = IN_APP` verso il `DIPENDENTE` richiedente. Il badge numerico nella topbar riflette il count di `NOTIFICA` con `stato_consegna != 'LETTA'` (se si implementa campo `letta`). |
| `[REGOLA-NOTIF-02]` | Sezione 1.5 | Le `NOTIFICA` con `canale = IN_APP` si manifestano anche come toast nella UI (durata 5s, dismissibile). Il comportamento del toast è gestito dalla UI, non dal record `NOTIFICA` in DB. |
| `[REGOLA-NOTIF-04]` | Sezione 1.5 | Il pannello notifiche visualizza le ultime 50 `NOTIFICA` con `destinatario_id = UTENTE_CORRENTE`, ordinate per `creata_il` discendente. Il limite di 50 è applicato a livello di query, non è un vincolo del dato. |

---

## Entità: `AUDIT_LOG`

**Definizione:** Registro immutabile e append-only di ogni cambio di stato o modifica significativa alle entità del sistema. Garantisce la tracciabilità completa e non ripudiabile delle azioni di tutti gli attori (umani e automatici). È l'entità con i vincoli di integrità più stringenti del sistema: nessun `UPDATE` né `DELETE` è mai ammesso, a nessun livello di privilegio.

**Owner primario:** Sistema (scrittura esclusivamente automatica). Nessun ruolo umano interagisce direttamente con `AUDIT_LOG` in scrittura.

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Univoco nel sistema. Generato automaticamente. Immutabile. |
| `entita_tipo` | `ENUM` | **Sì** | Valori ammessi: `RICHIESTA`, `EVENTO`, `UTENTE`. Indica il tipo di entità che ha subito la modifica. Immutabile dopo la creazione. |
| `entita_id` | `UUID` | **Sì** | ID dell'entità modificata (`RICHIESTA.id`, `EVENTO.id`, o `UTENTE.id`). Non è una FK enforced a livello DB (per preservare la traccia anche se l'entità dovesse essere successivamente rimossa logicamente). Immutabile dopo la creazione. |
| `attore_id` | `UUID` FK → `UTENTE.id` | No | Riferimento all'`UTENTE` che ha eseguito l'azione. Può essere `NULL` se l'azione è automatica di sistema (es. scadenza automatica, job schedulato, azione di sistema). La FK è soft (il record di audit deve sopravvivere anche se l'`UTENTE` venisse disattivato). |
| `azione` | `VARCHAR` | **Sì** | Stringa che descrive l'azione eseguita. Valori esempi documentati: `STATO_CAMBIATO`, `CAMPO_MODIFICATO`, `OVERRIDE_MANUALE`. Deve essere non-vuota. Immutabile. |
| `valore_precedente` | `JSONB` | No | Snapshot JSON del valore del campo o dello stato prima della modifica. `NULL` per operazioni di creazione (nessun valore precedente). Immutabile dopo la creazione. |
| `valore_nuovo` | `JSONB` | No | Snapshot JSON del valore del campo o dello stato dopo la modifica. `NULL` per operazioni di eliminazione logica (nessun nuovo valore applicativo). Immutabile dopo la creazione. |
| `timestamp` | `TIMESTAMPTZ` | **Sì** | Timestamp dell'azione, con timezone. Generato automaticamente con `NOW()` al momento dell'`INSERT`. Immutabile. Include timezone per garantire la correttezza in ambienti multi-timezone. |
| `ip_address` | `VARCHAR` | No | Indirizzo IP del client che ha originato la richiesta. Presente per azioni umane (quando `attore_id IS NOT NULL`). `NULL` per azioni automatiche di sistema. Non è un dato PII critico ai fini del sistema, ma è classificato come dato di telemetria soggetto alle restrizioni di trasmissione del `[SAFEGUARD-SEC-04]`. |

---

### Relazioni

- `AUDIT_LOG }o--o| UTENTE` (attore) — Ogni record `AUDIT_LOG` può avere al massimo un `UTENTE` come attore (`attore_id` nullable). Un `UTENTE` può aver generato zero o più record `AUDIT_LOG`.

- `AUDIT_LOG` è referenziato implicitamente da `RICHIESTA`, `EVENTO`, `UTENTE` tramite `(entita_tipo, entita_id)`. Non esiste una FK esplicita per garantire che il log sopravviva anche a modifiche logiche dell'entità originaria.

---

### Vincoli di Integrità e Regole Correlate

| Codice regola | Sorgente AFU | Effetto sul dato |
|---|---|---|
| `[REGOLA-AUDIT-01]` | Sezione 2.5 | Ogni cambio di `stato` di una `RICHIESTA` genera obbligatoriamente un record `AUDIT_LOG`. La scrittura è sincrona (nella stessa transazione) rispetto alla transizione di stato. |
| `[REGOLA-AUDIT-02]` | Sezione 2.5 | I record `AUDIT_LOG` non sono mai modificabili né eliminabili da alcun ruolo, incluso `ADMIN_IT`. La tabella è **append-only assoluta**. |
| `[REGOLA-AUDIT-03]` | Sezione 2.5 | Ogni override manuale `ADMIN_HR` genera un record `AUDIT_LOG` con `azione = 'OVERRIDE_MANUALE'` e `attore_id` dell'amministratore. |
| `[REGOLA-INT-04]` | Sezione 4.3 | **Immutabilità dell'audit**: nessuna operazione `UPDATE` o `DELETE` è ammessa sulla tabella `AUDIT_LOG`, nemmeno a livello di privilegio database per l'utenza applicativa. L'utenza applicativa deve avere solo i grant `INSERT` e `SELECT` su questa tabella. Richiede anche un trigger database di protezione (`BEFORE UPDATE OR DELETE`). |
| `[REGOLA-WF-03]` | Sezione 2.1 | Ogni transizione di stato della `RICHIESTA` (incluso override) genera obbligatoriamente un record `AUDIT_LOG` con `valore_precedente` e `valore_nuovo` popolati con gli snapshot degli stati coinvolti. |
| `[REGOLA-CLEAN-07]` | Sezione 6.3 AFU | Ogni operazione che genera un record `AUDIT_LOG` deve farlo **all'interno della stessa transazione** che modifica l'entità tracciata. Un fallimento della scrittura su `AUDIT_LOG` deve causare il rollback dell'intera transazione (inclusa la modifica dell'entità). |
| `[SAFEGUARD-AUD-01]` | Design Contract | Tre livelli di enforcement dell'immutabilità: (1) REVOKE `UPDATE`, `DELETE` sull'utenza applicativa, (2) trigger DB `BEFORE UPDATE OR DELETE`, (3) metodi di modifica assenti nell'interfaccia del repository applicativo. |
| `[SAFEGUARD-AUD-02]` | Design Contract | La scrittura su `AUDIT_LOG` deve avvenire dentro la stessa transazione dell'entità padre. Un fallimento nella scrittura di `AUDIT_LOG` causa rollback dell'intera transazione. |

---

## Appendice: Mappa Completa dei Vincoli Cross-Entità

Questa sezione sintetizza i vincoli che coinvolgono **più di una entità simultaneamente**, utili al Graph RAG per il retrieval di regole che attraversano i confini di una singola entità.

| Vincolo | Entità coinvolte | Regola/i |
|---|---|---|
| Decremento atomico posti | `RICHIESTA` + `EVENTO` | `[REGOLA-INT-06]`, `[REGOLA-CONC-01]`→`[REGOLA-CONC-06]` |
| Unicità richiedente/evento | `RICHIESTA` + `UTENTE` + `EVENTO` | `[REGOLA-INT-01]`, `[REGOLA-RQ-01]`, `[REGOLA-VAL-03]` |
| Non-eliminabilità evento con richieste | `EVENTO` + `RICHIESTA` | `[REGOLA-INT-03]`, `[REGOLA-CRUD-05]` |
| Audit sincrono con transazione | `AUDIT_LOG` + qualsiasi entità mutata | `[REGOLA-WF-03]`, `[REGOLA-AUDIT-01]`, `[REGOLA-CLEAN-07]` |
| Commento obbligatorio al rifiuto | `RICHIESTA` (campo condizionale) | `[REGOLA-INT-05]`, `[REGOLA-RQ-04]`, `[REGOLA-MGR-03]` |
| Scadenza iscrizioni < data inizio | `EVENTO` (coerenza interna) | `[REGOLA-INT-02]` |
| Override con controllo posti | `RICHIESTA` + `EVENTO` + `UTENTE` | `[REGOLA-OVR-02]`, `[REGOLA-VAL-01]` |
| Consegna notifica asincrona | `NOTIFICA` + `RICHIESTA` | `[REGOLA-NOTIF-SYS-03]` |
| Dominio email esclusivo | `UTENTE` (constraint di identità) | `[REGOLA-UT-01]`, `[REGOLA-AUTH-01]` |
| Revoca sessione immediata | `UTENTE` (campo `attivo`) | `[REGOLA-UT-02]`, `[REGOLA-AUTH-02]` |

---

*Fine del documento — `docs/00_meta_governance/glossario_entita.md` v1.0.0*
