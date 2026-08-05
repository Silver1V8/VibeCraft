---
id: "spec-area-pers-v1.0"
title: "Specifica Normativa — Area Personale Dipendente"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-13"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_area_pers_1.5.md"
authority: 0.87
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-area-pers-v1.0"
  scope: "Definizione dei requisiti dell'area personale del dipendente, gestione richieste e feedback visivo (toast)"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-v1.2"
    - type: "VINCOLA"
      target: "entity::RICHIESTA"
    - type: "VINCOLA"
      target: "entity::UTENTE"
tags:
  - requirements
  - open-spec
  - personal-area
  - toast-notifications
  - request-management
---

# Specifica Normativa — Area Personale Dipendente

---

## 1. Obiettivo e Layout dell'Area Personale

La presente specifica definisce i requisiti funzionali, le logiche di visualizzazione e i vincoli visivi dell'Area Personale (o "Profilo Utente") dedicata all' `` `UTENTE` `` registrato all'interno del portale VibeCraft. Lo scopo di questo modulo è fornire uno spazio centralizzato in cui ciascun dipendente possa monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``, gestire i record in fase di compilazione non ancora trasmessi e ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast).

Questa schermata garantisce trasparenza assoluta, consentendo al dipendente di tenere traccia delle proprie partecipazioni e dei feedback forniti dai manager senza la necessità di ricaricare la pagina (Single Page Application UX).

---

## 2. Regole di Visibilità, Filtraggio e Gestione Bozze

### [REGOLA-PERS-01] Elenco filtrato delle proprie richieste
- **Descrizione:** L'interfaccia dell'Area Personale deve mostrare esclusivamente l'elenco delle istanze di `` `RICHIESTA` `` create dall' `` `UTENTE` `` correntemente autenticato. Il sistema deve fornire controlli interattivi sul Frontend per filtrare in tempo reale la tabella o lista in base allo stato ('BOZZA', 'IN_ATTESA_APPROVAZIONE', 'APPROVATA', 'RIFIUTATA', 'ANNULLATA').
- **Effetto in caso di violazione (Failure Mode):** Riscontro visivo di richieste appartenenti ad altri colleghi o visualizzazione cumulativa caotica non filtrabile.
- **Entità Target:** `` `RICHIESTA` ``, `` `UTENTE` ``

### [REGOLA-PERS-02] Eliminazione fisica delle bozze
- **Descrizione:** L'utente ha il diritto di eliminare in modo definitivo dal database una propria `` `RICHIESTA` `` a condizione esclusiva che questa si trovi in stato 'BOZZA'. L'operazione deve rimuovere fisicamente il record dal database transazionale.
- **Effetto in caso di violazione (Failure Mode):** Permanenza indefinita sul database di record fantasma orfani in stato di bozza, con conseguente spreco di spazio di archiviazione e potenziale confusione statistica.
- **Entità Target:** `` `RICHIESTA` ``

---

## 3. Vincoli Transazionali e Feedback Visivo (Toast)

### [REGOLA-NOTIF-01] Notifiche asincrone tramite Toast
- **Descrizione:** Qualsiasi azione scatenata dall'utente all'interno dell'Area Personale (cancellazione di una bozza, sottomissione di una richiesta o annullamento di un'iscrizione) deve produrre un feedback visivo immediato tramite una notifica Toast temporanea non bloccante. I Toast devono essere tipizzati:
  - **Verde (Successo):** Per operazioni andate a buon fine (es. "Bozza eliminata con successo").
  - **Rosso (Errore):** In caso di eccezioni o fallimento delle API (es. "Impossibile completare l'operazione: errore transazionale").
- **Effetto in caso di violazione (Failure Mode):** Mancanza di riscontro visivo immediato per l'utente, che potrebbe ripetere l'operazione nel dubbio che non sia stata elaborata.
- **Entità Target:** `` `RICHIESTA` ``

### [REGOLA-VAL-01] Inibizione eliminazione richieste sottomesse
- **Descrizione:** Se una `` `RICHIESTA` `` si trova in uno stato diverso da 'BOZZA' (ad esempio, 'IN_ATTESA_APPROVAZIONE' o 'APPROVATA'), il pulsante "Elimina" non deve essere visualizzato o deve risultare disattivato. L'utente può procedere esclusivamente all'annullamento della richiesta, regolato dalle limitazioni temporali della macchina a stati.
- **Effetto in caso di violazione (Failure Mode):** L'utente tenta di eliminare richieste già valutate dai manager o in attesa di esserlo, violando la consistenza dello storico dei flussi di audit aziendali.
- **Entità Target:** `` `RICHIESTA` ``

---

## 4. Scenari Comportamentali BDD (Gherkin)

### Capability: Navigazione Area Personale, Gestione Bozze e Feedback Toast

```gherkin
SCENARIO: S01 - Cancellazione di una bozza con notifica Toast di successo
  GIVEN un UTENTE autenticato posizionato all'interno della propria Area Personale
  AND un record RICHIESTA appartenente all'utente in stato 'BOZZA'
  WHEN l'utente fa click sul pulsante "Elimina" associato a questa bozza
  THEN il sistema rimuove fisicamente il record dal database in conformità con la [REGOLA-PERS-02]
  AND mostra un Toast verde di successo recante il messaggio "Bozza eliminata con successo"
  AND aggiorna dinamicamente la lista rimuovendo la riga senza ricaricare l'intera pagina
```

```gherkin
SCENARIO: S02 - Inibizione eliminazione su richieste sottomesse o approvate
  GIVEN un UTENTE autenticato posizionato nell'Area Personale
  AND un record RICHIESTA in stato 'IN_ATTESA_APPROVAZIONE' o 'APPROVATA'
  WHEN l'utente visualizza la riga associata a questa richiesta
  THEN l'interfaccia applica la [REGOLA-VAL-01]
  AND nasconde o disabilita il pulsante di eliminazione fisica
  AND mostra come unico controllo possibile l'azione "Annulla Richiesta" (soggetta a vincoli temporali)
```

```gherkin
SCENARIO: S03 - Visualizzazione Toast di errore per fallimento transazionale
  GIVEN un UTENTE autenticato che tenta di annullare una RICHIESTA approvata a meno di 5 giorni dall'evento
  WHEN l'utente invoca l'azione di annullamento sul client
  THEN il server rifiuta la transazione e restituisce un errore HTTP 422
  AND il client intercetta il fallimento applicando la [REGOLA-NOTIF-01]
  AND renderizza un Toast rosso di errore recante il messaggio "Impossibile annullare l'iscrizione a ridosso dell'evento"
```
