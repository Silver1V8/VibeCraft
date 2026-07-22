---
id: "spec-AREA-v1.0"
title: "Specifica Normativa — TITOLO_AREA"
project: "NOME_PROGETTO"
version: "1.0.0"
date: "AAAA-MM-GG"
status: "ENFORCED"
classification: "REQUIREMENTS"
path: "docs/02_specs_normative/spec_AREA.md"
authority: 0.87
changelog:
  - version: "1.0.0"
    date: "AAAA-MM-GG"
    changes:
      - "Rilascio iniziale della specifica"
graph_rag:
  node_type: "OPEN_SPEC"
  node_id: "spec-AREA-v1.0"
  scope: "Requisiti e vincoli del modulo TITOLO_AREA"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "EREDITA_VINCOLI"
      target: "safeguards-security-baseline-v2.0"
    - type: "REFERENZIA"
      target: "glossario-entita-v1.0"
tags:
  - requirements
  - open-spec
---

# Specifica Normativa — TITOLO_AREA
## NOME_PROGETTO

> Il nome del file deve rispettare il pattern `spec_*.md`: è così che l'indicizzatore lo registra come nodo `OPEN_SPEC` (`[REGOLA-INT-01]`).

---

## 1. Obiettivo e Ambito di Applicazione

*(Cosa copre questa specifica e, altrettanto importante, cosa non copre. Un ambito non delimitato produce sovrapposizioni fra specifiche e regole contraddittorie.)*

**Fuori ambito:** *(elencare esplicitamente ciò che è normato altrove, con il riferimento al documento competente)*

---

## 2. Regole

> **Formato obbligatorio.** Ogni regola apre con un identificatore `[PREFISSO-CATEGORIA-NN]` conforme alla tassonomia (`[REGOLA-VAL-07]`) e riporta sempre le tre voci sottostanti. Il **Failure Mode** non è decorativo: è la parte che dice al test cosa deve verificare.

### [REGOLA-XXX-01] Titolo sintetico della regola
- **Descrizione:** *(Il vincolo, in forma prescrittiva e verificabile. "Il sistema deve…", non "il sistema dovrebbe…". Se una regola non è verificabile da un test, non è una regola: è un'intenzione.)*
- **Effetto in caso di violazione (Failure Mode):** *(Cosa si rompe concretamente. Serve al test e all'analisi d'impatto.)*
- **Entità Target:** `` `ENTITA_A` `` *(oppure: Nessuna)*

### [REGOLA-XXX-02] Titolo sintetico della regola
- **Descrizione:**
- **Effetto in caso di violazione (Failure Mode):**
- **Entità Target:**

---

## 3. Vincoli di Validazione

| Campo | Vincolo | Errore restituito | Regola |
|---|---|---|---|
| `campo` | *(vincolo)* | `VALIDATION_FAILED` | `[REGOLA-XXX-01]` |

> I codici di errore devono esistere nel catalogo di `docs/01_architecture_norms/api_error_contract.md` o esservi aggiunti.

---

## 4. Interazioni con Altri Moduli

| Modulo | Natura dell'interazione | Sincrona / Asincrona |
|---|---|---|
| *(modulo)* | *(cosa scambiano)* | *(quale delle due)* |

---

## 5. Scenari Comportamentali BDD (Gherkin)

> Ogni scenario qui presente **deve** avere un test corrispondente (`[REGOLA-TEST-05]`). Uno scenario senza test è documentazione che mente.

```gherkin
Scenario: Nome dello scenario nominale
  Dato una precondizione verificabile
  E una seconda precondizione
  Quando avviene l'azione che si vuole normare
  Allora si osserva l'esito atteso
  E l'invariante della [REGOLA-XXX-01] risulta rispettata
```

```gherkin
Scenario: Nome dello scenario negativo
  Dato una precondizione che viola il vincolo
  Quando viene tentata l'operazione
  Allora il sistema la rifiuta con l'errore previsto
  E nessuna mutazione di stato viene persistita
```

> Il percorso negativo non è opzionale: `[REGOLA-TEST-03]` richiede che l'enforcement sia dimostrato, non solo il caso lecito.

---

## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-XXX-01]` | *(una riga)* |
| `[REGOLA-XXX-02]` | *(una riga)* |
