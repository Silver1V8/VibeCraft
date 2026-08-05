---
id: "spec-monitor-admin-v1.0"
title: "Specifica Normativa — Pannello di Monitoraggio ed Audit Log"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_monitor_admin_3.3.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-monitor-admin-v1.0"
  scope: "Definizione dei requisiti per la visualizzazione dell'audit log e tracciabilità delle operazioni amministrative"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::AUDIT_LOG"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - admin-panel
  - monitoring
  - audit-log
  - security
---

# Specifica Normativa — Pannello di Monitoraggio ed Audit Log

---

## 1. Obiettivo e Logica di Tracciamento (Audit Log)

La presente specifica definisce i requisiti funzionali, le logiche di visualizzazione e i criteri di sicurezza del Pannello di Monitoraggio ed Audit Log di VibeCraft. Lo scopo principale di questo modulo è fornire agli amministratori HR e ai responsabili della sicurezza dell'informazione una vista unificata e in sola lettura su tutte le operazioni che modificano lo stato del database. L'interfaccia deve garantire l'assoluta integrità della catena di tracciabilità delle azioni eseguite all'interno dell'applicazione.

Ogni singola operazione di creazione, modifica, approvazione o cancellazione logica che coinvolga le entità core deve generare un record strutturato all'interno dell' `` `AUDIT_LOG` ``.

---

## 2. Regole di Tracciamento e Immutabilità

### [REGOLA-AUDIT-01] Scrittura sincrona e immutabilità del log
- **Descrizione:** Ogni transazione di business andata a buon fine (ad esempio, l'approvazione di una `RICHIESTA` o la pubblicazione di un `EVENTO`) deve inserire in modo sincrono un record associato nell' `` `AUDIT_LOG` ``. Una volta inserito, un record del log non può essere modificato, aggiornato (`UPDATE`) o rimosso (`DELETE`) da alcun utente o processo del database, inclusi gli amministratori.
- **Effetto in caso di violazione (Failure Mode):** Tentativi di alterazione sollevano un'eccezione di database bloccante a livello hardware/trigger, preservando l'immutabilità dello storico.
- **Entità Target:** `` `AUDIT_LOG` ``

### [REGOLA-AUDIT-02] Sola lettura e query di filtro temporale
- **Descrizione:** L'interfaccia del Pannello di Monitoraggio deve operare rigorosamente in sola lettura (`Read-Only`). Essa deve fornire controlli avanzati per filtrare i record dell' `` `AUDIT_LOG` `` in base all'intervallo temporale, all'identificativo dell' `` `UTENTE` `` operatore, all'entità target e alla tipologia di azione (es. `INSERT`, `UPDATE`, `TRANSITION`).
- **Effetto in caso di violazione (Failure Mode):** Visualizzazione caotica o non strutturata dei log, compromettendo le attività ispettive e i controlli post-incidente.
- **Entità Target:** `` `AUDIT_LOG` ``

---

## 3. Autorizzazioni ed Allarmi di Sicurezza

### [REGOLA-AUTH-01] Restrizione di accesso esclusivo (RBAC)
- **Descrizione:** L'accesso alla dashboard di monitoraggio alla rotta `/admin/audit` e la possibilità di effettuare chiamate API di lettura sui log sono privilegi riservati esclusivamente agli utenti che possiedono il ruolo di 'ADMIN' o 'SECURITY_AUDITOR' all'interno del record `` `UTENTE` ``. Qualsiasi richiesta proveniente da account dipendenti o manager deve essere intercettata dai middleware e bloccata con errore 403 Forbidden.
- **Effetto in caso di violazione (Failure Mode):** Accesso non autorizzato ai log di audit, con rischio di tracciamento indebito delle attività altrui ed esposizione di dati riservati.
- **Entità Target:** `` `UTENTE` ``

### [REGOLA-VAL-01] Rilevamento e logging delle eccezioni di sicurezza
- **Descrizione:** Ogni volta che il sistema respinge una transazione per violazione dei vincoli di sicurezza (es. tentativi di double-booking protetti da `[REGOLA-CONC-01]` o tentativi di transizione illegale `[REGOLA-VAL-01]`), il server deve generare un log di severità `WARNING` o `CRITICAL` inserendolo all'istante nell' `` `AUDIT_LOG` ``.
- **Effetto in caso di violazione (Failure Mode):** Mancanza di visibilità su attacchi informatici o anomalie strutturali applicative ripetute.
- **Entità Target:** `` `AUDIT_LOG` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Monitoraggio e Ispezione di Sicurezza dei Log di Audit

```gherkin
SCENARIO: S01 - Consultazione corretta dei log di audit da parte dell'amministratore
  GIVEN un Amministratore HR autenticato sulla console di monitoraggio
  WHEN imposta il filtro per l'entità RICHIESTA e la tipologia di azione "TRANSITION"
  THEN la console visualizza in ordine cronologico inverso tutti i record di audit corrispondenti
  AND verifica che per ciascun record sia visibile l'ID dell'UTENTE operatore, la data, l'ora e il payload modificato
  AND l'interfaccia si presenta in modalità di sola lettura senza alcun pulsante di modifica o cancellazione
```

```gherkin
SCENARIO: S02 - Blocco di un dipendente che tenta l'accesso non autorizzato ai log
  GIVEN un dipendente UTENTE autenticato con ruolo comune
  WHEN tenta di inviare una richiesta GET HTTP all'endpoint protetto /api/v1/admin/audit
  THEN il middleware di sicurezza applica la [REGOLA-AUTH-01]
  AND rifiuta la connessione restituendo un codice di stato HTTP 403 Forbidden
  AND inserisce un record di allarme di sicurezza con severità "WARNING" nell' `AUDIT_LOG`
```

```gherkin
SCENARIO: S03 - Tracciamento automatico sincrono di una transizione di stato critica
  GIVEN un record RICHIESTA in stato 'BOZZA'
  WHEN il manager approva la richiesta facendola transizionare in 'APPROVATA'
  THEN il server aggiorna lo stato sul database
  AND inietta simultaneamente un nuovo record nell' `AUDIT_LOG` con i dettagli dell'operazione
  AND il log viene reso immediatamente consultabile nella console di monitoraggio degli amministratori
```
