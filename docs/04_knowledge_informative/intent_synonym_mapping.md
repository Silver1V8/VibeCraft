---
id: "intent-synonym-mapping-v1.0"
title: "Glossario Semantico dei Sinonimi e Intent Mapping"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-08"
status: "ENFORCED"
classification: "METHODOLOGY"
path: "docs/04_knowledge_informative/intent_synonym_mapping.md"
graph_rag:
  node_type: "SEMANTIC_MAPPING"
  node_id: "intent-synonym-mapping-v1.0"
  phase: "Fase 1 — /openspec-explore"
  resolution_strategy: "REASONS"
  edges:
    - type: "TRADUCE_PER_IL_RAG"
      target: "glossario-entita-v1.0"
      note: "Ogni sinonimo in questo file è un arco implicito verso il nodo entità o attributo corrispondente"
    - type: "APPLICA_TUTELATE_DA"
      target: "safeguards-security-v1.0"
      note: "Le operazioni mappate che toccano dati PII o transazioni critiche attivano automaticamente i safeguard corrispondenti"
    - type: "REQUISITO_METODOLOGICO"
      target: "vibe-coding-workflow-v1.0"
    - type: "REFERENZIA"
      target: "matrice-permessi-v1.0"
      note: "L'intent mapping deve verificare il ruolo RBAC prima di attivare qualsiasi nodo operativo"
    - type: "REFERENZIA"
      target: "ANALISI_FUNZIONALE_VIBE_CODING"
      sections: ["0.2", "1.4", "1.5", "2.1", "2.3", "3.2", "3.3"]
tags:
  - semantic-mapping
  - intent-mapping
  - synonym-glossary
  - graph-rag
  - nlp-bridge
  - vibe-coding
  - reasons-architecture
  - fase-1-explore
  - pii
  - rbac
  - state-machine
---

# Glossario Semantico dei Sinonimi e Intent Mapping
## VibeCraft — Sistema di Gestione Eventi Aziendali

> **Istruzione per il Graph RAG locale (Ollama — Fase 1 `/openspec-explore`)**
>
> Questo file è il **ponte semantico** tra il linguaggio naturale dell'utente e i nodi rigidi della Knowledge Base del progetto. Quando una query in linguaggio naturale entra nel sistema RAG, questo documento deve essere consultato **prima** di qualsiasi retrieval sui nodi operativi, per risolvere l'ambiguità lessicale e determinare l'intent canonico. Ogni riga della tabella è un arco implicito `(espressione_utente) —[RISOLVE_IN]→ (nodo_grafo)`. Il modello NON deve mai rispondere basandosi sull'espressione grezza dell'utente: deve prima tradurla nel termine canonico e poi navigare il grafo da quel nodo.

---

## 1. Mappatura Semantica dei Verbi e delle Azioni (Dizionario Operativo)

> **Nota di lettura:** La colonna "Regola AFU Vincolata" indica il codice regola che il sistema RAG deve recuperare e applicare come vincolo prima di dichiarare l'operazione eseguibile. Se la regola blocca l'operazione (es. `posti_residui = 0`), il sistema deve restituire il motivo del blocco usando la terminologia canonica del nodo `FAILURE_MODE` corrispondente nel safeguard, non un messaggio generico.

| Espressione o Frase Umana (Varianti) | Operazione Logica (Intent) | Entità / Attributi Target | Regola AFU Vincolata |
|---|---|---|---|
| "Voglio iscrivermi", "Mi iscrivo", "Come faccio a iscrivermi?", "Voglio andare al corso", "Voglio partecipare alla conferenza", "Faccio la prenotazione", "Mando la domanda", "Prenoto il posto", "Mi candido", "Inoltro la richiesta", "Partecipo?", "Posso venire?", "Come faccio ad andare?", "Registro la mia presenza", "Faccio richiesta di partecipazione" | `CREATE RICHIESTA` con `stato = IN_ATTESA` | `RICHIESTA` (INSERT): `evento_id`, `richiedente_id`, `motivazione` (min 50 chars), `necessita_alloggio`, `stato = IN_ATTESA` | `[REGOLA-RQ-01]` unicità coppia richiedente/evento; `[REGOLA-RQ-02]` `posti_residui > 0`; `[REGOLA-RQ-03]` `NOW() < scadenza_iscrizioni`; `[REGOLA-VAL-01]` `[REGOLA-VAL-02]` `[REGOLA-VAL-03]`; `[REGOLA-FORM-01]` validazione motivazione |
| "Voglio annullare", "Cancello l'iscrizione", "Non voglio più andare", "Ritiro la domanda", "Mi faccio da parte", "Annullo tutto", "Faccio marcia indietro", "Torno indietro", "Desisto", "Lascio perdere", "Non mi interessa più", "Rimuovimi dalla lista", "Cancellami", "Ho cambiato idea", "Rinuncio al corso" | `UPDATE RICHIESTA.stato = ANNULLATA` | `RICHIESTA` (UPDATE): `stato` → `ANNULLATA`; `EVENTO.posti_residui` (nessun rilascio se `stato` era `IN_ATTESA`); `AUDIT_LOG` (INSERT automatico) | `[REGOLA-WF-02]` solo da `IN_ATTESA`; solo il `richiedente_id` può eseguire; `[REGOLA-PERS-03]`; `[REGOLA-WF-03]` audit obbligatorio; errore se `stato ≠ IN_ATTESA` |
| "Approvo la richiesta", "Do il via libera", "Firmo la pratica", "Passo in verde", "Dico sì", "Autorizzo", "Confermo la partecipazione", "Assegno il posto", "Mando avanti", "Sblocco la richiesta", "Accetto", "Visto dal manager", "Vado a approvare", "La passo", "Il dipendente può andare", "Nessun problema, approvata" | `UPDATE RICHIESTA.stato = APPROVATA` con lock transazionale | `RICHIESTA` (UPDATE): `stato` → `APPROVATA`, `manager_id`, `data_decisione = NOW()`; `EVENTO` (UPDATE `posti_residui - 1`, `SELECT ... FOR UPDATE`); `BUDGET_ANNUO` (UPDATE `consumato + costo_unitario`, `residuo - costo_unitario`, `FOR UPDATE` dopo lock EVENTO); `NOTIFICA` (INSERT `APPROVAZIONE` → `DIPENDENTE`); `AUDIT_LOG` (INSERT) | `[REGOLA-MGR-02]`; `[REGOLA-CONC-01]`→`[REGOLA-CONC-06]` lock pessimistico; `[REGOLA-INT-06]` atomicità; `[REGOLA-INT-07]` non negatività; `[SAFEGUARD-TXN-01]` `[SAFEGUARD-TXN-02]` `[SAFEGUARD-TXN-05]`; `[REGOLA-VAL-04]` verifica posti post-lock |
| "Rifiuto la richiesta", "La bocco", "Non approvo", "Non do il permesso", "Mando indietro", "Dico no", "La rispedisco al mittente", "Non autorizzato", "Respingo la richiesta", "Non passa", "Blocked", "KO", "La pratica non va bene", "Non è idoneo", "La segnalo come rifiutata", "Non ci siamo" | `UPDATE RICHIESTA.stato = RIFIUTATA` con commento obbligatorio | `RICHIESTA` (UPDATE): `stato` → `RIFIUTATA`, `commento_manager` (NOT NULL, non vuoto), `manager_id`, `data_decisione = NOW()`; `NOTIFICA` (INSERT `RIFIUTO` → `DIPENDENTE`); `AUDIT_LOG` (INSERT) | `[REGOLA-MGR-03]` modale obbligatorio; `[REGOLA-RQ-04]` `commento_manager` obbligatorio se e solo se `RIFIUTATA`; `[REGOLA-INT-05]` coerenza condizionale; `[REGOLA-WF-03]` audit; `[REGOLA-WF-01]` stato terminale |
| "Creo un evento", "Carico un corso", "Aggiungo una conferenza", "Metto a catalogo", "Pubblico un nuovo evento", "Inserisco una formazione", "Apro le iscrizioni per", "Registro un evento", "Aggiungo al calendario formativo", "Nuovo evento", "Voglio creare una sessione", "Preparo l'offerta formativa", "Configuro un evento", "Metto online il corso" | `CREATE EVENTO` con `stato = ATTIVO` (o bozza se incompleto) | `EVENTO` (INSERT): `titolo`, `descrizione`, `data_inizio`, `data_fine`, `luogo`, `posti_totali`, `posti_residui = posti_totali`, `costo_unitario`, `budget_allocato`, `scadenza_iscrizioni`, `stato`, `creato_da`; `AUDIT_LOG` (INSERT) | `[REGOLA-CRUD-01]` campi obbligatori per pubblicazione; `[REGOLA-INT-02]` `scadenza_iscrizioni < data_inizio`; `[REGOLA-EV-03]` `posti_totali > 0`; `[REGOLA-CRUD-03]` upload locandina; permesso `F-08` solo `ADMIN_HR` o `ADMIN_IT` per `[matrice_permessi]` |
| "Archivio l'evento", "Tolgo l'evento dal catalogo", "Disattivo l'evento", "Metto in standby", "Non è più disponibile", "Chiudo le iscrizioni definitivamente", "Lo nascondo", "Non si può più iscrivere", "Termino l'evento", "Lo rendo invisibile", "Lo metto offline", "Ritiro l'evento" | `UPDATE EVENTO.stato = ARCHIVIATO` (soft delete) | `EVENTO` (UPDATE): `stato` → `ARCHIVIATO`; `AUDIT_LOG` (INSERT) | `[REGOLA-CRUD-04]` solo `ADMIN_IT` può `ELIMINATO`; `[REGOLA-CRUD-05]` se ha `RICHIESTA` associate, vietato `DELETE` fisico; `[REGOLA-INT-03]` non eliminabilità referenziale; `[REGOLA-EV-01]` nessuna nuova `RICHIESTA` su evento `ARCHIVIATO`; permesso `F-08` / `F-09` per `[matrice_permessi]` |
| "Elimina l'evento", "Cancella definitivamente", "Rimuovi dal sistema", "Voglio cancellarlo per sempre", "Butta via l'evento", "Fallo sparire", "Delete definitivo" | `UPDATE EVENTO.stato = ELIMINATO` oppure `DELETE` fisico (solo se zero `RICHIESTA` associate) | `EVENTO` (UPDATE logico `stato = ELIMINATO` o `DELETE` fisico); `AUDIT_LOG` (INSERT) | `[REGOLA-CRUD-04]` solo `ADMIN_IT`; `[REGOLA-CRUD-05]` blocco se `COUNT(RICHIESTA) > 0`; `[REGOLA-INT-03]` FK `ON DELETE RESTRICT`; `[SAFEGUARD-AUD-03]`; errore `EVENTO_DELETION_BLOCKED` se associazioni presenti |
| "Disattiva l'utente", "Sospendi l'account", "Revoca l'accesso", "Metti in blacklist", "Blocca il login", "Togligli i permessi", "Non deve più entrare", "Licenzia dal sistema", "Kicka l'utente", "Chiudi il suo account", "Impediscigli di accedere", "Freezalo", "Mettilo fuori", "Bandiscilo" | `UPDATE UTENTE.attivo = false` (revoca immediata sessioni attive) | `UTENTE` (UPDATE): `attivo` → `false`; invalidazione sessioni attive in session store; `AUDIT_LOG` (INSERT) | `[REGOLA-UT-02]` verifica `attivo` ad ogni request; `[REGOLA-AUTH-02]` revoca immediata non differita; `[SAFEGUARD-SEC-02]` max 30s TTL cache; permesso `F-10` solo `ADMIN_IT`; errore `ACCOUNT_DISABLED` su sessioni attive post-revoca |
| "Riattiva l'utente", "Sblocca l'account", "Restituiscigli l'accesso", "Fallo rientrare", "Reintegra nel sistema", "Togli la sospensione", "Rifai il login", "Riabilita" | `UPDATE UTENTE.attivo = true` | `UTENTE` (UPDATE): `attivo` → `true`; `AUDIT_LOG` (INSERT) | `[REGOLA-UT-03]` ruolo immutato dalla riattivazione salvo modifica esplicita; permesso `F-10` solo `ADMIN_IT`; nessuna notifica automatica all'utente riattivato |
| "Cambia il ruolo", "Promuovi a manager", "Fallo diventare admin", "Dai i permessi da HR", "Scala i privilegi", "Degrada il ruolo", "Togli i diritti di admin", "Metti come dipendente normale", "Aggiorna i suoi permessi", "Passalo a IT" | `UPDATE UTENTE.ruolo = [nuovo_ruolo]` | `UTENTE` (UPDATE): `ruolo` → `DIPENDENTE` / `MANAGER` / `ADMIN_HR` / `ADMIN_IT`; `AUDIT_LOG` (INSERT) | `[REGOLA-UT-03]` default `DIPENDENTE`; permesso `F-10` solo `ADMIN_IT`; nessuna auto-elevazione; effetto immediato su tutte le sessioni attive dell'utente |
| "Forza lo stato", "Override manuale", "Sblocca la pratica d'autorità", "Metti approvata a prescindere", "Bypassa il workflow", "Ignora le regole e approva", "Forzatura admin", "Cambia lo stato a mano", "Riapri la pratica chiusa", "Aggiusta lo stato", "Intervieni sulla richiesta" | `UPDATE RICHIESTA.stato = [qualsiasi]` con `azione = OVERRIDE_MANUALE` | `RICHIESTA` (UPDATE forzato `stato`); `EVENTO` (verifica e UPDATE `posti_residui` se override → `APPROVATA`); `BUDGET_ANNUO` (UPDATE se override → `APPROVATA` e `costo_unitario > 0`); `AUDIT_LOG` (INSERT `azione = OVERRIDE_MANUALE`, `attore_id = ADMIN_HR`) | `[REGOLA-OVR-01]` solo `ADMIN_HR`; `[REGOLA-OVR-02]` verifica `posti_residui > 0` se override → `APPROVATA`; `[REGOLA-OVR-03]` audit obbligatorio non silenzioso; `[SAFEGUARD-TXN-01]` lock applicato anche all'override; permesso `F-07` solo `ADMIN_HR` |
| "Esporta i dati", "Scarica la lista", "Fammi il CSV", "Voglio un Excel con i partecipanti", "Report dei partecipanti", "Stampa la lista", "Voglio la lista approvati", "Genera il file", "Download dei dati" | `SELECT RICHIESTA` con filtri → file CSV/XLSX | `RICHIESTA` (SELECT con filtri: evento, stato, date); `UTENTE` (JOIN per nome, email); `EVENTO` (JOIN per titolo, data, costo); output file con 8 colonne fisse | `[REGOLA-EXP-01]` solo `ADMIN_HR`; `[REGOLA-EXP-02]` formati CSV UTF-8 BOM o XLSX; `[REGOLA-EXP-03]` naming `export_richieste_{stato}_{YYYYMMDD}`; `[SAFEGUARD-SEC-04]` dati PII non trasmessi a endpoint cloud; permesso `F-11` solo `ADMIN_HR` |

---

## 2. Mappatura dei Sostantivi e dei Concetti di Business

> **Nota di lettura:** La colonna "Etichetta Sicurezza/PII" indica se il campo contiene dati personali soggetti alle restrizioni di `[SAFEGUARD-SEC-04]`. Quando il RAG recupera o cita questi campi in risposta a una query, deve anonimizzarli o segnalarli come soggetti a controllo di accesso prima di includerli nel Canvas.md. Il tag `PII-RESTRICTED` implica che il valore del campo non deve mai essere incluso in contesti inviati a LLM remoti.

| Termine Comune / Gergo | Definizione di Business | Riferimento Modello Dati Rigido | Etichetta Sicurezza / PII |
|---|---|---|---|
| "Posti liberi", "Posti disponibili", "Sedie rimaste", "Quanti posti ci sono", "Capienza residua", "Quanti ne mancano", "Spazi disponibili", "Slot liberi", "Quanti si possono ancora iscrivere", "Rimane posto?", "C'è ancora posto?", "Quanti ticket sono rimasti", "Disponibilità", "Availability" | Numero di posti ancora occupabili per un evento. Calcolato come `posti_totali − COUNT(RICHIESTA WHERE stato = APPROVATA)`. Non modificabile manualmente. Soggetto a lock pessimistico in scrittura. | `EVENTO.posti_residui` (INTEGER, CHECK >= 0, CHECK <= posti_totali) | `NON-PII` — dato tecnico aggregato. Visibile a tutti i ruoli autenticati nella Dashboard. |
| "Quanti posti ci sono in totale", "Capienza massima", "Dimensione dell'evento", "Massimo partecipanti", "Limite iscrizioni", "Cap", "Capienza totale" | Numero massimo di partecipanti consentiti per un evento. Immutabile dopo la prima `RICHIESTA` associata. | `EVENTO.posti_totali` (INTEGER, > 0) | `NON-PII` — dato descrittivo dell'evento. Visibile a tutti i ruoli. |
| "Prezzo", "Costo", "Quota d'iscrizione", "Soldi per il biglietto", "Quanto costa", "Tariffa", "Fee", "Importo", "Prezzo del biglietto", "Contributo", "Costo della formazione", "Ticket price", "Quanto devo pagare", "Spesa per l'evento" | Costo unitario del biglietto o della partecipazione a un evento, in EUR. Può essere 0 per eventi gratuiti. Usato per decrementare `BUDGET_ANNUO.residuo` al momento dell'approvazione. | `EVENTO.costo_unitario` (NUMERIC(10,2), >= 0, in EUR) | `NON-PII` — dato finanziario dell'evento. Visibile a tutti i ruoli. |
| "Budget rimasto", "Fondi disponibili", "Portafoglio aziendale", "Soldi per la formazione", "Budget formativo", "Quanto budget c'è", "Fondi residui", "Soldi rimasti", "Cassa della formazione", "Quanti soldi si possono ancora spendere", "Disponibilità finanziaria", "Plafond", "Quante risorse economiche rimangono" | Budget formativo aziendale annuo non ancora impegnato. Decrementato atomicamente a ogni approvazione (`costo_unitario > 0`). Soggetto a lock pessimistico (`FOR UPDATE` sulla riga anno corrente). Alert se scende sotto il 15% del totale. | `BUDGET_ANNUO.residuo` (NUMERIC(10,2), colonna di riga con `anno = CURRENT_YEAR`) | `RESTRICTED` — visibile solo a `ADMIN_HR` (con drill-down) e `ADMIN_IT` (solo aggregato). Non esporre a `DIPENDENTE` o `MANAGER`. |
| "Budget consumato", "Quanto abbiamo speso", "Spesa formativa", "Budget già impegnato", "Importo utilizzato", "Fondi già spesi", "Costi sostenuti", "Spese approvate fino ad ora" | Somma totale dei costi_unitario di tutte le RICHIESTA con stato = APPROVATA nell'anno corrente. Incrementato atomicamente a ogni approvazione. | `BUDGET_ANNUO.consumato` (NUMERIC(10,2)) | `RESTRICTED` — stessa visibilità di `BUDGET_ANNUO.residuo`. |
| "Budget totale annuo", "Tetto di spesa", "Budget annuale", "Quanto budget abbiamo in totale", "Dotazione formativa", "Fondo formazione annuo", "Limite di budget" | Budget formativo aziendale complessivo per l'anno fiscale corrente. Impostato dall'amministrazione all'inizio dell'anno. Non modificabile automaticamente dal workflow. | `BUDGET_ANNUO.totale` (NUMERIC(10,2)) | `RESTRICTED` — stessa visibilità di `BUDGET_ANNUO.residuo`. |
| "Motivazione", "Perché vuole andare", "Ragione del corso", "Perché partecipa", "Cosa ha scritto", "La giustificazione", "Il testo della richiesta", "Spiegazione della partecipazione", "Il motivo", "Cosa ha detto per giustificarsi", "Cos'ha scritto nel form", "La sua motivazione" | Testo libero compilato dal dipendente per giustificare la richiesta di partecipazione. Minimo 50 caratteri. Non modificabile dopo la sottomissione. Classificato PII. Non deve mai essere inviato a LLM remoti o sistemi di telemetria esterni. | `RICHIESTA.motivazione` (TEXT, min 50 chars, max 2000 chars) | `PII-RESTRICTED` — visibile solo al richiedente (Area Personale) e al Manager (coda approvazione). `ADMIN_HR` può vedere in vista globale. Mai trasmettere a endpoint non autorizzati. |
| "Spiegazione del rifiuto", "Note del capo", "Perché è stata bocciata", "Cosa ha scritto il manager", "Il commento del manager", "Motivazione del no", "Perché non ha passato", "La nota di rifiuto", "Cosa gli hanno detto", "Feedback del manager", "Il motivo del rifiuto" | Commento obbligatorio del Manager in caso di rifiuto. Visibile al dipendente richiedente nella sezione "Le mie richieste". Nullo per qualsiasi stato diverso da RIFIUTATA. | `RICHIESTA.commento_manager` (TEXT, NOT NULL e non vuoto se `stato = RIFIUTATA`, NULL altrimenti) | `PII-RESTRICTED` — visibile solo al richiedente e al Manager che lo ha scritto. `ADMIN_HR` può vedere in vista globale. |
| "Hotel", "Albergo", "Soggiorno", "Dormire fuori", "Ha bisogno di stare fuori", "Pernottamento", "Overnight", "Vuole l'alloggio", "Ha segnato che dorme lì", "Richiede sistemazione", "Necessità di hotel", "Fuori sede", "Si ferma", "Ha bisogno di una stanza" | Flag booleano che indica se il dipendente necessita di sistemazione alberghiera per partecipare all'evento. Dato informativo per il Manager, non determina automaticamente l'esito dell'approvazione. | `RICHIESTA.necessita_alloggio` (BOOLEAN, default false) | `NON-PII` (strettamente) — tuttavia fa parte del record `RICHIESTA` classificato come PII. Trattare con la stessa cautela di `RICHIESTA.motivazione`. |
| "Scadenza", "Deadline iscrizioni", "Entro quando ci si può iscrivere", "Termine per iscriversi", "Quando chiudono le iscrizioni", "Ultimo giorno per fare domanda", "Data limite", "Cutoff", "Fino a quando", "Entro quando", "Closing date" | Data e ora dopo le quali il sistema blocca automaticamente la creazione di nuove RICHIESTA per l'evento. Deve essere sempre antecedente a `data_inizio`. | `EVENTO.scadenza_iscrizioni` (TIMESTAMPTZ, MUST BE < `data_inizio`) | `NON-PII` — dato descrittivo dell'evento. Visibile a tutti i ruoli. |
| "Registro", "Storia delle modifiche", "Log", "Cronologia", "Traccia", "Chi ha fatto cosa", "Audit", "Tracciamento", "Chi ha firmato", "Storico", "Trail", "Chi ha cambiato lo stato", "Quando è stato approvato", "Traccia delle operazioni", "Cosa è successo", "Chi ha toccato la pratica" | Registro immutabile append-only di ogni mutazione significativa alle entità del sistema. Nessun UPDATE o DELETE ammesso su questa tabella da alcun ruolo. | `AUDIT_LOG` (tabella append-only): `entita_tipo`, `entita_id`, `attore_id`, `azione`, `valore_precedente` (JSONB), `valore_nuovo` (JSONB), `timestamp` (TIMESTAMPTZ) | `RESTRICTED` — leggibile solo da `ADMIN_HR` (F-13) e `ADMIN_IT` (F-13). Immutabile per tutti i ruoli incluso `ADMIN_IT`. |
| "Pratica", "Domanda", "Candidatura", "Richiesta di partecipazione", "Istanza", "Form inviato", "La mia richiesta", "La richiesta del dipendente", "Ticket di formazione", "Application", "Richiesta di formazione", "Domanda di iscrizione" | La pratica formale sottomessa da un dipendente per richiedere la partecipazione a un evento. Entità centrale del workflow. Ha una macchina a stati con 4 stati (IN_ATTESA, APPROVATA, RIFIUTATA, ANNULLATA). | `RICHIESTA` (entità): `id`, `evento_id`, `richiedente_id`, `motivazione`, `necessita_alloggio`, `note_aggiuntive`, `stato`, `commento_manager`, `manager_id`, `data_decisione`, `creata_il`, `aggiornata_il` | `PII-RESTRICTED` — il record nel complesso va trattato come PII per la presenza di `motivazione` e `commento_manager`. |
| "Stato della pratica", "A che punto è la richiesta", "Com'è messa la domanda", "È stata approvata?", "Quando la vedo verde?", "È ancora in attesa?", "L'ha firmata il manager?", "Esito della richiesta", "Che fine ha fatto", "Dove è arrivata" | Il valore corrente dell'attributo `stato` nella macchina a stati della RICHIESTA. | `RICHIESTA.stato` (ENUM: `IN_ATTESA`, `APPROVATA`, `RIFIUTATA`, `ANNULLATA`) | `NON-PII` — ma accessibile solo al richiedente, al suo manager, ad `ADMIN_HR`. |
| "Evento", "Corso", "Conferenza", "Training", "Formazione", "Workshop", "Seminario", "Webinar", "Summit", "Meet-up", "Evento formativo", "Opportunity", "Talk", "Sessione formativa" | Un'opportunità formativa o professionale pubblicata nel catalogo. Oggetto centrale gestito dagli amministratori. | `EVENTO` (entità): `id`, `titolo`, `descrizione`, `data_inizio`, `data_fine`, `luogo`, `posti_totali`, `posti_residui`, `costo_unitario`, `budget_allocato`, `scadenza_iscrizioni`, `locandina_url`, `stato`, `creato_da` | `NON-PII` — dati descrittivi pubblici. Visibile a tutti i ruoli autenticati. |
| "Utente", "Dipendente", "Persona", "Collega", "Chi si è iscritto", "Il richiedente", "Il collaboratore", "Il lavoratore", "Chi ha mandato la domanda", "Il mio account" | Qualsiasi persona fisica autenticata con account `@progettopa.it`. Il ruolo determina le funzionalità accessibili. | `UTENTE` (entità): `id`, `email`, `nome`, `cognome`, `avatar_url`, `ruolo`, `attivo`, `creato_il`, `ultimo_accesso` | `PII-RESTRICTED` — `nome`, `cognome`, `email` sono dati personali. Accesso differenziato per ruolo. `ADMIN_IT` ha visibilità completa. |
| "Manager", "Capo", "Responsabile", "Il mio capo", "Chi approva", "Il supervisore", "Chi decide", "Chi ha la firma", "Chi dà il via libera", "Chi gestisce le approvazioni" | Utente con `ruolo = MANAGER`. Processa le richieste del proprio team tramite la coda di approvazione. Non può creare eventi né effettuare override. | `UTENTE` (filtro): `ruolo = MANAGER` | `NON-PII` — il ruolo è informazione organizzativa. Il nominativo specifico del manager è PII-RESTRICTED se associato a una richiesta specifica. |
| "Admin", "Amministratore", "HR", "IT", "Chi gestisce il sistema", "Il responsabile HR", "Il team IT", "Chi ha i superpoteri", "L'amministratore di sistema" | Utenti con `ruolo = ADMIN_HR` o `ADMIN_IT`. Hanno accesso al Pannello Admin con funzionalità differenziate (vedere matrice permessi). | `UTENTE` (filtro): `ruolo IN (ADMIN_HR, ADMIN_IT)` | `NON-PII` — il ruolo è informazione organizzativa. |
| "Notifica", "Avviso", "Alert", "Messaggio", "Email ricevuta", "Slack", "Campanella", "Toast", "Pop-up del sistema", "Mi è arrivata una notifica", "Il sistema mi ha scritto" | Messaggio automatico generato dal sistema in risposta a un cambio di stato di una RICHIESTA. Inviato via EMAIL, SLACK o IN_APP. | `NOTIFICA` (entità): `id`, `richiesta_id`, `destinatario_id`, `canale` (EMAIL/SLACK/IN_APP), `tipo` (NUOVA_RICHIESTA/APPROVAZIONE/RIFIUTO/SCADENZA_IMMINENTE), `stato_consegna`, `tentativo_n`, `inviata_il` | `NON-PII` strettamente, ma può contenere riferimenti a record PII. Il payload della notifica non va trasmesso a sistemi esterni non autorizzati. |

---

## 3. Esempi di Interpretazione e Ripple del Grafo (Fase 1 Explore)

> **Istruzione per il Graph RAG:** Per ciascuno degli scenari seguenti, la query in linguaggio naturale dell'utente deve essere decomosta in: (1) risoluzione dei sinonimi tramite la Sezione 1 e 2 di questo file, (2) identificazione dell'intent canonico, (3) navigazione dei nodi e archi attivati, (4) recupero dei vincoli e safeguard applicabili prima di comporre il Canvas.md di risposta. L'ordine di attivazione dei nodi è prescrittivo: **Identità → Permesso → Regola → Safeguard → Dato → Risposta**.

---

> **Scenario 1 — Query semplice con blocco implicito**
>
> **Frase utente:** *"Voglio prenotare il posto per il Codemotion, c'è ancora posto?"*
>
> **Analisi dell'intent:**
> - Sinonimi risolti (Sezione 1): "prenotare il posto" → `CREATE RICHIESTA` con `stato = IN_ATTESA`; "c'è ancora posto" → `READ EVENTO.posti_residui`
> - Intent canonico: `VERIFICA_DISPONIBILITÀ` + (condizionale) `CREATE_RICHIESTA`
> - Ruolo richiesto: query implicita da `DIPENDENTE` o `MANAGER`
>
> **Nodi e archi attivati in sequenza:**
> 1. `(UTENTE_CORRENTE) —[HA_RUOLO]→ DIPENDENTE` → verifica permesso `F-02` da `matrice_permessi_v1.0` → **CONCESSO**
> 2. `(query "Codemotion") —[RISOLVE_IN]→ EVENTO.titolo LIKE '%Codemotion%'` → `SELECT EVENTO WHERE titolo LIKE ...`
> 3. `EVENTO —[ATTRIBUTO]→ posti_residui` → se `posti_residui > 0` E `NOW() < scadenza_iscrizioni` → **DISPONIBILE**
> 4. Verifica `[REGOLA-RQ-01]`: `SELECT RICHIESTA WHERE richiedente_id = UTENTE_CORRENTE AND evento_id = EVENTO.id AND stato IN ('IN_ATTESA','APPROVATA')` → se esiste già → **BLOCCO** con messaggio "Hai già una richiesta attiva per questo evento"
> 5. Se nessun blocco → attivazione nodo `FORM_PRENOTAZIONE` → riferimento a `[REGOLA-FORM-01]` (motivazione min 50 chars), `[REGOLA-INT-06]` (atomicità), `[SAFEGUARD-TXN-01]` (lock al submit)
> 6. Canvas.md: espone `EVENTO.titolo`, `EVENTO.posti_residui`, `EVENTO.scadenza_iscrizioni`, `EVENTO.costo_unitario`, link al form. Non espone `BUDGET_ANNUO` (non autorizzato per `DIPENDENTE`).

---

> **Scenario 2 — Query con race condition latente**
>
> **Frase utente:** *"Approvo la richiesta di Maya, è rimasto solo un posto."*
>
> **Analisi dell'intent:**
> - Sinonimi risolti (Sezione 1): "approvo la richiesta" → `UPDATE RICHIESTA.stato = APPROVATA`; "rimasto solo un posto" → `EVENTO.posti_residui = 1` → condizione di concorrenza critica
> - Intent canonico: `APPROVA_RICHIESTA` con `posti_residui = 1` → attiva automaticamente scenario `[REGOLA-CONC-01]`
> - Ruolo richiesto: `MANAGER`
>
> **Nodi e archi attivati in sequenza:**
> 1. `(UTENTE_CORRENTE) —[HA_RUOLO]→ MANAGER` → verifica permesso `F-06` → **CONCESSO** (solo per richieste del proprio team)
> 2. `(query "richiesta di Maya") —[RISOLVE_IN]→ RICHIESTA WHERE richiedente.nome LIKE '%Maya%' AND stato = 'IN_ATTESA' AND team_id = MANAGER.team_id`
> 3. Attivazione immediata `[SAFEGUARD-TXN-01]`: il nodo segnala che con `posti_residui = 1` l'operazione entra nel **path di concorrenza critica** → il Canvas.md deve avvertire che il submit avvierà `SELECT ... FOR UPDATE` su `EVENTO` e `BUDGET_ANNUO`
> 4. Attivazione `[SAFEGUARD-TXN-05]`: verifica `BUDGET_ANNUO.residuo >= EVENTO.costo_unitario` dentro la stessa transazione con lock (secondo lock, dopo `EVENTO`)
> 5. Nodi fallimento mappati: `[REGOLA-CONC-04]` → se al momento del lock `posti_residui = 0` → errore `POSTO_ESAURITO_CONCORRENZA` (HTTP 409); `[SAFEGUARD-TXN-05]` → se `BUDGET_ANNUO.residuo < costo_unitario` → errore `BUDGET_INSUFFICIENTE_CONCORRENZA` (HTTP 409)
> 6. Canvas.md: mostra `RICHIESTA` selezionata, `EVENTO.posti_residui` attuale (con warning "⚠️ Ultimo posto — operazione soggetta a lock transazionale"), `BUDGET_ANNUO.residuo` (visibile a `MANAGER`? No → non esporre), esito atteso se l'operazione va a buon fine.

---

> **Scenario 3 — Query amministrativa con PII implicita**
>
> **Frase utente:** *"Voglio vedere perché Giulia è stata bocciata e magari sbloccarla d'autorità."*
>
> **Analisi dell'intent:**
> - Sinonimi risolti (Sezione 1): "è stata bocciata" → `RICHIESTA.stato = RIFIUTATA`; "perché" → `RICHIESTA.commento_manager` (campo PII-RESTRICTED); "sbloccarla d'autorità" → `OVERRIDE_MANUALE` → `UPDATE RICHIESTA.stato` forzato
> - Intent canonico: `LEGGI_DETTAGLIO_RICHIESTA_RIFIUTATA` + (condizionale) `OVERRIDE_STATO_RICHIESTA`
> - Ruolo richiesto: `ADMIN_HR` (unico autorizzato a entrambe le operazioni)
>
> **Nodi e archi attivati in sequenza:**
> 1. `(UTENTE_CORRENTE) —[HA_RUOLO]→ ADMIN_HR` → verifica permesso `F-05` (coda globale) → **CONCESSO**; permesso `F-07` (override) → **CONCESSO**
> 2. `(query "Giulia") —[RISOLVE_IN]→ UTENTE WHERE nome LIKE '%Giulia%'` → recupero `RICHIESTA WHERE richiedente_id = UTENTE.id AND stato = 'RIFIUTATA'`
> 3. Campo `RICHIESTA.commento_manager` → etichetta `PII-RESTRICTED` attivata → il Canvas.md lo mostra **solo** perché il ruolo è `ADMIN_HR` (autorizzato); `[SAFEGUARD-SEC-04]` segnalato: il valore non va mai incluso in prompt verso LLM remoti
> 4. Intent "sbloccarla d'autorità" → attivazione nodo `OVERRIDE_MANUALE`: `[REGOLA-OVR-01]` (solo `ADMIN_HR`); `[REGOLA-OVR-02]` se override → `APPROVATA` deve rieseguire verifica `posti_residui > 0` con lock; `[REGOLA-OVR-03]` audit obbligatorio con `azione = OVERRIDE_MANUALE`
> 5. Attivazione `[SAFEGUARD-AUD-02]`: il record `AUDIT_LOG` deve essere scritto nella stessa transazione dell'override. Il Canvas.md mostra il campo `azione = OVERRIDE_MANUALE` come campo obbligatorio che verrà generato
> 6. Canvas.md: mostra `RICHIESTA` con `stato = RIFIUTATA`, `commento_manager` (con label "⚠️ Campo PII — visibile solo a ADMIN_HR"), pulsante override con warning sui vincoli di posti e budget, log audit che verrà generato.

---

> **Scenario 4 — Query ambigua con errore concettuale dell'utente**
>
> **Frase utente:** *"Il budget è finito, cancella tutti gli eventi così non spendono più niente."*
>
> **Analisi dell'intent:**
> - Sinonimi risolti (Sezione 1): "il budget è finito" → `BUDGET_ANNUO.residuo ≈ 0` o sotto soglia alert `[REGOLA-ANL-03]`; "cancella tutti gli eventi" → intent apparente: `DELETE EVENTO` (tutti); "non spendono più niente" → obiettivo: bloccare nuove approvazioni con costo
> - **Errore concettuale rilevato:** l'utente confonde "cancellare gli eventi" (eliminazione dati) con "bloccare nuove iscrizioni approvabili" (comportamento applicativo). La cancellazione degli eventi non blocca le approvazioni in corso; archiviarli sì. Inoltre, la cancellazione di eventi con RICHIESTA associate è vietata da `[REGOLA-CRUD-05]` e `[SAFEGUARD-AUD-03]`.
> - Intent canonico corretto (post-risoluzione): `VERIFICA_BUDGET_RESIDUO` + eventuale `UPDATE EVENTO.stato = ARCHIVIATO` (soft-delete selettivo, non delete di massa)
> - Ruolo richiesto: `ADMIN_HR` o `ADMIN_IT`
>
> **Nodi e archi attivati in sequenza:**
> 1. `(UTENTE_CORRENTE) —[HA_RUOLO]→ ADMIN_HR` → verifica permesso `F-09` (elimina evento) → `ADMIN_HR`: **NON CONCESSO**; `ADMIN_IT`: **CONCESSO** (ma con vincoli)
> 2. Attivazione nodo `ERRORE_CONCETTUALE`: il RAG deve **correggere** l'intent prima di procedere. Risposta obbligatoria: "La cancellazione fisica degli eventi non interrompe automaticamente le approvazioni. Considera invece: (a) archiviare gli eventi futuri per bloccare nuove iscrizioni, (b) attendere che il sistema rifiuti autonomamente le approvazioni per `BUDGET_INSUFFICIENTE_CONCORRENZA`."
> 3. Verifica `[REGOLA-CRUD-05]` + `[REGOLA-INT-03]`: `SELECT COUNT(*) FROM richiesta WHERE evento_id IN (SELECT id FROM evento)` → se `COUNT > 0` → `DELETE EVENTO` **BLOCCATO** per ogni evento con richieste associate. Il RAG segnala quali eventi possono essere eliminati fisicamente (zero richieste) e quali solo archiviati.
> 4. Attivazione `[SAFEGUARD-AUD-03]`: qualsiasi tentativo di `DELETE` su evento con richieste attiva `EVENTO_DELETION_BLOCKED` (HTTP 409).
> 5. Intent alternativo valido: `UPDATE EVENTO.stato = ARCHIVIATO` per tutti gli eventi ATTIVI senza RICHIESTA IN_ATTESA o APPROVATA → permesso `F-08` per `ADMIN_HR` → eseguibile con audit per ciascun evento modificato.
> 6. Canvas.md: mostra `BUDGET_ANNUO.residuo` attuale, lista eventi con count di RICHIESTA associate per ciascuno, raccomandazione di archiviarli anziché eliminarli, warning `[SAFEGUARD-AUD-03]` per quelli con richieste, elenco degli eventi eliminabili fisicamente (se presenti).
