---
id: "spec-mgr-panel-v1.0"
title: "Specifica Normativa — Pannello Manager e Gestione Approvazioni"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_mgr_panel_2.2.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-mgr-panel-v1.0"
  scope: "Definizione dei requisiti e dei vincoli del pannello di approvazione/rifiuto dedicato ai manager"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::BUDGET_ANNUO"
tags:
  - requirements
  - open-spec
  - manager-panel
  - approvals
  - budget-validation
---

# Specifica Normativa — Pannello Manager e Gestione Approvazioni
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Obiettivo e Layout del Pannello di Approvazione

La presente specifica definisce i requisiti funzionali, le autorizzazioni di accesso e le logiche transazionali del Pannello Manager (o "Console di Approvazione") all'interno del sistema VibeCraft. Lo scopo di questo modulo è fornire ai responsabili di dipartimento una plancia di controllo centralizzata per esaminare in tempo reale le istanze di `RICHIESTA` sottomesse dai propri collaboratori, valutare l'impatto economico residuo sul `BUDGET_ANNUO` del dipartimento ed eseguire azioni di approvazione o rifiuto motivato in modo sicuro e tracciato.

L'interfaccia si articola in una vista tabellare ordinata per data di sottomissione, evidenziando le richieste che necessitano di attenzione immediata per evitare la scadenza dei termini di iscrizione degli eventi.

---

## 2. Regole di Visibilità e Restrizioni di Dipartimento

### [REGOLA-MGR-01] Compartimentazione della coda richieste per dipartimento
- **Descrizione:** Il Pannello Manager deve mostrare esclusivamente le istanze di `RICHIESTA` create da utenti `UTENTE` che appartengono al medesimo dipartimento aziendale del manager autenticato. Un manager non deve in alcun caso visualizzare, ispezionare o valutare richieste provenienti da unità organizzative diverse dalla propria.
- **Effetto in caso di violazione (Failure Mode):** Accesso non autorizzato a dati personali e violazione dei confini di gestione della struttura gerarchica aziendale.
- **Entità Target:** `RICHIESTA`, `UTENTE`

### [REGOLA-MGR-02] Motivazione obbligatoria in caso di rifiuto
- **Descrizione:** L'azione di rifiuto di una `RICHIESTA` (transizione verso lo stato 'RIFIUTATA') richiede obbligatoriamente l'inserimento di una nota testuale esplicativa da parte del manager, con una lunghezza minima di 10 caratteri e massima di 250 caratteri. Il sistema deve impedire la sottomissione del rifiuto se il campo di nota è vuoto o insufficiente.
- **Effetto in caso di violazione (Failure Mode):** Rigetto di iscrizioni senza motivazioni formali tracciate, con conseguente impossibilità di audit interno sul comportamento dei manager.
- **Entità Target:** `RICHIESTA`

---

## 3. Gestione del Budget ed Autorizzazioni Ruolo

### [REGOLA-VAL-01] Validazione capienza budget all'approvazione
- **Descrizione:** All'istante del click su "Approva", il sistema deve calcolare preventivamente se il costo unitario dell' `EVENTO` associato è coperto dal saldo attualmente disponibile del `BUDGET_ANNUO` dipartimentale. Se il budget residuo è insufficiente, l'azione di approvazione deve essere bloccata immediatamente.
- **Effetto in caso di violazione (Failure Mode):** Sforamento dei tetti di spesa dipartimentali prefissati e violazione dei vincoli di allocazione finanziaria dell'amministrazione.
- **Entità Target:** `BUDGET_ANNUO`, `EVENTO`

### [REGOLA-AUTH-01] Controllo dei permessi di accesso al pannello (RBAC)
- **Descrizione:** L'accesso alla rotta `/manager` e l'esecuzione degli endpoint API di approvazione/rifiuto sono strettamente riservati agli utenti che possiedono il ruolo formale di 'MANAGER' o 'ADMIN' all'interno dell'attributo ruolo dell' `UTENTE` autenticato. Tentativi di accesso da parte di dipendenti comuni devono essere intercettati dai middleware di sicurezza.
- **Effetto in caso di violazione (Failure Mode):** Escalation dei privilegi e approvazione fraudolenta di richieste da parte di utenti non autorizzati.
- **Entità Target:** `UTENTE`

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Coda di Approvazione e Validazione Transazionale dei Manager

```gherkin
Scenario: Approvazione con successo di una richiesta e decremento budget
  Dato un MANAGER del dipartimento "Sviluppo" autenticato sulla Console di Approvazione
  E una RICHIESTA in stato 'IN_ATTESA_APPROVAZIONE' inviata da un dipendente del dipartimento "Sviluppo"
  E l'EVENTO associato ha un costo di 200 euro e il BUDGET_ANNUO del dipartimento ha un saldo residuo di 1000 euro
  Quando il manager fa click sul pulsante "Approva"
  Allora il sistema valida i permessi mediante la [REGOLA-AUTH-01]
  E verifica la disponibilità dei fondi mediante la [REGOLA-VAL-01]
  E imposta lo stato della RICHIESTA su 'APPROVATA'
  E decrementa il saldo del BUDGET_ANNUO a 800 euro
  E genera un tracciamento immutabile nell' `AUDIT_LOG`
```

```gherkin
Scenario: Blocco approvazione per superamento del budget dipartimentale
  Dato un MANAGER del dipartimento "Marketing" autenticato sulla Console
  E una RICHIESTA in stato 'IN_ATTESA_APPROVAZIONE' per un EVENTO con costo unitario di 500 euro
  E il BUDGET_ANNUO del dipartimento "Marketing" ha un saldo residuo di soli 300 euro
  Quando il manager tenta di approvare la richiesta
  Allora il sistema intercetta la violazione finanziaria mediante la [REGOLA-VAL-01]
  E interrompe l'approvazione senza modificare lo stato del record
  E mostra un avviso bloccante a schermo recante il messaggio "Impossibile approvare: budget dipartimentale insufficiente"
```

```gherkin
Scenario: Rifiuto di una richiesta con nota motivazionale valida
  Dato un MANAGER autenticato che esamina una richiesta nella propria coda
  Quando inserisce la nota "Incompatibile con le scadenze del team" e clicca su "Rifiuta"
  Allora il sistema verifica la conformità con la [REGOLA-MGR-02]
  E aggiorna lo stato della RICHIESTA in 'RIFIUTATA'
  E invia una NOTIFICA automatica di aggiornamento al dipendente richiedente
```