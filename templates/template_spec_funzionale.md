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

> **Formato obbligatorio, unico e senza varianti.** Vale per ogni scenario di ogni spec, qualunque sia la feature. Questo documento è la fonte normativa; il resto della catena la esegue: il prompt di generazione (`rag/prompts/spec.md`) la insegna al modello, `core.spec_format.normalize_spec` la **ricostruisce** in modo deterministico su ciò che il modello produce, e il validatore (`pipeline.check_bdd_semantics`) controlla ciò che la normalizzazione non può garantire — un solo `GIVEN`/`WHEN`/`THEN` per scenario, presenza del caso negativo, assenza di dettagli implementativi.
>
> Il normalizzatore riscrive la **forma**, mai il contenuto: se la struttura non è ricostruibile senza inventare, fallisce con un errore esplicito invece di indovinare.
>
> - un blocco ` ```gherkin ` **per ciascuno** scenario: mai un unico blocco che ne contiene più di uno, mai uno scenario fuori da un blocco;
> - keyword in **MAIUSCOLO e in inglese**: `GIVEN` / `WHEN` / `THEN` / `AND`;
> - prima riga del blocco: `SCENARIO: S<nn> - <titolo breve>`, numerazione progressiva (`S01`, `S02`, …) nell'ordine in cui gli scenari compaiono nel documento;
> - poi i passi, uno per riga, indentati di **2 spazi**, nell'ordine `GIVEN` → `AND` (opzionali) → `WHEN` → `AND` (opzionali) → `THEN` → `AND` (opzionali);
> - **un solo** `GIVEN`, **un solo** `WHEN` e **un solo** `THEN` per scenario: ogni condizione aggiuntiva si esprime con `AND`, mai con un secondo `GIVEN`/`WHEN`/`THEN`;
> - testo dei passi in italiano, indicativo presente, terza persona, senza dettagli implementativi (niente nomi di classi, tabelle o endpoint se non sono un requisito funzionale);
> - valori letterali fra virgolette doppie;
> - una sola asserzione per riga: niente passi discorsivi o su più frasi;
> - dentro il blocco non va nient'altro che la riga `SCENARIO` e i passi: nessun commento, nessun testo libero.

```gherkin
SCENARIO: S01 - Nome dello scenario nominale
  GIVEN una precondizione verificabile
  AND una seconda precondizione
  WHEN avviene l'azione che si vuole normare
  THEN si osserva l'esito atteso
  AND l'invariante della [REGOLA-XXX-01] risulta rispettata
```

```gherkin
SCENARIO: S02 - Nome dello scenario negativo
  GIVEN una precondizione che viola il vincolo
  WHEN viene tentata l'operazione
  THEN il sistema la rifiuta con l'errore previsto
  AND nessuna mutazione di stato viene persistita
```

> Il percorso negativo non è opzionale: `[REGOLA-TEST-03]` richiede che l'enforcement sia dimostrato, non solo il caso lecito. Per ogni funzionalità servono **almeno due** scenari, un caso nominale e un caso negativo o di errore.

---

## 6. Riepilogo delle Regole

| ID | Vincolo operativo core |
|---|---|
| `[REGOLA-XXX-01]` | *(una riga)* |
| `[REGOLA-XXX-02]` | *(una riga)* |
