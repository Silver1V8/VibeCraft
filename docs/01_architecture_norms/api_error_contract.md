---
id: "api-error-contract-v1.0"
title: "Normativa — Contratto API e Modello degli Errori"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/api_error_contract.md"
authority: 0.85
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Creato per colmare un riferimento pendente: [REGOLA-CLEAN-02] impone codici HTTP standardizzati e i safeguard definiscono errori nominati, ma nessun documento ne normava la forma"
reuse:
  parameters:
    - "<<PREFISSO_API>>: prefisso di versione delle rotte (es. /api/v1)"
    - "<<FORMATO_ERRORE>>: schema di errore adottato (default: RFC 9457 Problem Details)"
    - "<<LIMITE_PAGINA>>: dimensione massima di pagina ammessa"
  inherited_parameters:
    - "<<ENTITA_TRANSAZIONE>> — definito in safeguards_security.md"
  instantiation: "Copiare il file, compilare la Sezione 0. I parametri ereditati si compilano una sola volta, nel contratto di istanziazione dei safeguard. Il catalogo degli errori in Sezione 4 va esteso, mai ridotto: gli errori nominati dai safeguard sono obbligatori."
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "api-error-contract-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "coding-standards-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "observability-standards-v1.0"
tags:
  - norms
  - api
  - rest
  - error-handling
  - versioning
  - cross-project
  - baseline
---

# Normativa — Contratto API e Modello degli Errori
## Baseline Cross-Progetto

---

## Sezione 0 — Contratto di Istanziazione

| Parametro | Significato | Valore nel progetto |
|---|---|---|
| `<<PREFISSO_API>>` | Prefisso di versione delle rotte | `/api/v1` *(default)* |
| `<<FORMATO_ERRORE>>` | Schema di errore adottato | RFC 9457 Problem Details *(default)* |
| `<<LIMITE_PAGINA>>` | Dimensione massima di pagina | `100` *(default)* |

> **Perché questo documento esiste:** `[REGOLA-CLEAN-02]` impone di rimappare ogni anomalia su codici HTTP standardizzati, e i safeguard nominano errori specifici (`DOMAIN_NOT_ALLOWED`, `ACCOUNT_DISABLED`, `RESOURCE_EXHAUSTED`, `ENTITY_DELETION_BLOCKED`, `VERSION_NOT_BUMPED`). Senza un contratto che ne definisca la **forma**, ogni endpoint inventa la propria e il client non può trattarli in modo uniforme.

---

## 1. Forma dell'Errore

### [REGOLA-API-01] Schema unico di errore
- **Descrizione:** Ogni risposta di errore, senza eccezioni, deve rispettare `<<FORMATO_ERRORE>>` e contenere almeno: un **codice simbolico stabile** (`code`), un messaggio leggibile (`detail`), lo status HTTP (`status`) e il `correlationId` della richiesta. Il codice simbolico è parte del contratto pubblico: i client vi si programmano sopra.
- **Effetto in caso di violazione (Failure Mode):** Il client è costretto a fare parsing del messaggio in linguaggio naturale; ogni riformulazione del testo diventa un breaking change silenzioso.
- **Entità Target:** Nessuna.

```json
{
  "type":    "https://example.org/errors/resource-exhausted",
  "title":   "Resource exhausted",
  "status":  409,
  "code":    "RESOURCE_EXHAUSTED",
  "detail":  "La risorsa richiesta non è più disponibile.",
  "instance": "/api/v1/…",
  "correlationId": "01J…"
}
```

### [REGOLA-API-02] Nessun dettaglio interno nel payload di errore
- **Descrizione:** Stack trace, query SQL, nomi di tabella, percorsi del filesystem e valori di variabili non compaiono mai nella risposta al client. Il dettaglio diagnostico vive nel log correlato dal `correlationId`.
- **Effetto in caso di violazione (Failure Mode):** Information disclosure sfruttabile per la ricognizione di un attaccante; possibile fuoriuscita di PII in violazione di `[SAFEGUARD-SEC-04]`.
- **Entità Target:** Nessuna.

### [REGOLA-API-03] Codici simbolici stabili e depreabili
- **Descrizione:** Un `code` si **depreca**, non si rinomina: vale la stessa regola di stabilità degli identificatori `[REGOLA-*]`. La deprecazione va annunciata nel changelog dell'API con una finestra di compatibilità dichiarata.
- **Effetto in caso di violazione (Failure Mode):** Rottura silenziosa dei client che gestivano il codice precedente.
- **Entità Target:** Nessuna.

---

## 2. Mappatura Semantica degli Status HTTP

### [REGOLA-API-04] Uso semanticamente corretto degli status
- **Descrizione:** Lo status HTTP deve riflettere la natura dell'errore secondo la tabella seguente. È vietato l'uso di `200` per esiti negativi e di `500` per errori prevedibili di dominio.

| Status | Quando | Esempio di `code` |
|---|---|---|
| `400` | Richiesta malformata, non interpretabile | `MALFORMED_REQUEST` |
| `401` | Identità assente o non valida | `UNAUTHENTICATED` |
| `403` | Identità valida ma non autorizzata | `DOMAIN_NOT_ALLOWED`, `ACCOUNT_DISABLED`, `FORBIDDEN` |
| `404` | Risorsa inesistente o non visibile all'attore | `NOT_FOUND` |
| `409` | Conflitto di stato o di concorrenza | `RESOURCE_EXHAUSTED`, `ENTITY_DELETION_BLOCKED`, `STATE_CONFLICT` |
| `422` | Sintassi valida, semantica di dominio invalida | `VALIDATION_FAILED` |
| `429` | Superamento del rate limit | `RATE_LIMITED` |
| `500` | Errore inatteso, non previsto dal dominio | `INTERNAL_ERROR` |

- **Effetto in caso di violazione (Failure Mode):** Retry automatici dei client su errori non ritentabili; monitoraggio che non distingue i guasti reali dagli esiti di dominio.
- **Entità Target:** Nessuna.

### [REGOLA-API-05] Indistinguibilità fra inesistente e non autorizzato
- **Descrizione:** Quando la sola esistenza di una risorsa è informazione riservata, la risposta deve essere `404`, non `403`. La scelta va documentata per endpoint: non è una decisione lasciata all'implementatore di turno.
- **Effetto in caso di violazione (Failure Mode):** Enumerazione delle risorse per differenza di status.
- **Entità Target:** Nessuna.

---

## 3. Versionamento, Paginazione e Idempotenza

### [REGOLA-API-06] Versione esplicita nel percorso
- **Descrizione:** Ogni rotta pubblica è esposta sotto `<<PREFISSO_API>>`. Le modifiche breaking richiedono una nuova versione; le aggiunte retrocompatibili no. Sono breaking: la rimozione di un campo, il restringimento di un tipo, un nuovo vincolo obbligatorio in input, un cambio di semantica a parità di firma.
- **Effetto in caso di violazione (Failure Mode):** Rottura dei client in produzione senza preavviso.
- **Entità Target:** Nessuna.

### [REGOLA-API-07] Paginazione obbligatoria sulle collezioni
- **Descrizione:** Nessun endpoint di collezione restituisce un insieme non limitato. La dimensione di pagina è limitata a `<<LIMITE_PAGINA>>` e l'ordinamento è **deterministico e totale** — un ordinamento non totale produce record duplicati o saltati fra pagine.
- **Effetto in caso di violazione (Failure Mode):** Degrado o esaurimento della memoria al crescere dei dati; risultati incoerenti in paginazione.
- **Entità Target:** Nessuna.

### [REGOLA-API-08] Idempotenza delle operazioni non sicure
- **Descrizione:** Gli endpoint che producono effetti non reversibili devono accettare una chiave di idempotenza fornita dal client e restituire il risultato della prima esecuzione in caso di replay. Requisito diretto della resilienza ai retry di rete.
- **Effetto in caso di violazione (Failure Mode):** Doppia esecuzione dell'effetto (doppio consumo di risorsa, doppio addebito) su retry del client o del proxy.
- **Entità Target:** `<<ENTITA_TRANSAZIONE>>`

---

## 4. Catalogo Minimo degli Errori

Obbligatori perché nominati dai safeguard: estendibile, non riducibile.

| `code` | Status | Safeguard di origine |
|---|---|---|
| `DOMAIN_NOT_ALLOWED` | 403 | `[SAFEGUARD-SEC-01]` |
| `ACCOUNT_DISABLED` | 403 | `[SAFEGUARD-SEC-02]` |
| `RESOURCE_EXHAUSTED` | 409 | `[SAFEGUARD-TXN-01]`, `[SAFEGUARD-TXN-04]` |
| `ENTITY_DELETION_BLOCKED` | 409 | `[SAFEGUARD-AUD-03]` |
| `VALIDATION_FAILED` | 422 | `[REGOLA-CLEAN-04]` |

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Il perdente di una race riceve un errore contrattuale
  Dato due richieste concorrenti sull'ultima unità di risorsa disponibile
  Quando entrambe raggiungono il percorso transazionale protetto da lock
  Allora una riceve 200 con la transazione applicata
  E l'altra riceve 409 con code RESOURCE_EXHAUSTED per [REGOLA-API-04]
  E la risposta contiene il correlationId della richiesta
  E la risposta non contiene stack trace né riferimenti allo schema del database
```

```gherkin
Scenario: Replay di una richiesta con chiave di idempotenza
  Dato un endpoint non sicuro invocato con una chiave di idempotenza
  E una prima esecuzione andata a buon fine
  Quando il client ritenta la stessa richiesta con la stessa chiave
  Allora il sistema restituisce il risultato della prima esecuzione
  E non produce un secondo effetto per [REGOLA-API-08]
```

---

## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-API-01]` | Schema di errore unico con `code` simbolico e `correlationId`. |
| `[REGOLA-API-02]` | Nessun dettaglio interno nel payload di errore. |
| `[REGOLA-API-03]` | I codici di errore si deprecano, non si rinominano. |
| `[REGOLA-API-04]` | Status HTTP semanticamente corretto; mai 200 su errore, mai 500 su errore di dominio. |
| `[REGOLA-API-05]` | `404` al posto di `403` quando l'esistenza è informazione riservata. |
| `[REGOLA-API-06]` | Versione esplicita nel percorso; le breaking change cambiano versione. |
| `[REGOLA-API-07]` | Paginazione obbligatoria con ordinamento totale e deterministico. |
| `[REGOLA-API-08]` | Chiave di idempotenza sulle operazioni non reversibili. |

---

*Fine del documento — baseline cross-progetto v1.0.0*
