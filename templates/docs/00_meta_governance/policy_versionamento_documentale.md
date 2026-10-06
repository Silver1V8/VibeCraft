---
id: "policy-versionamento-documentale-v1.0"
title: "Policy — Versionamento e Tracciamento della Knowledge Base"
project: "cross-project"
scope: "cross-project"
version: "1.0.0"
date: "2026-07-22"
status: "ENFORCED"
classification: "METADATA"
path: "docs/00_meta_governance/policy_versionamento_documentale.md"
authority: 0.90
changelog:
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Estratto il nucleo generico da change_log.md (sezioni 1-2): regole di versionamento e tracciamento"
      - "Scartato lo storico delle versioni del progetto di origine, non riusabile"
      - "Aggiunto il template di riga di changelog e il contratto del frontmatter"
reuse:
  parameters:
    - "<<REGISTRO_MODIFICHE>>: percorso del file che ospita lo storico del progetto"
  instantiation: "Questo documento è la POLICY, valida invariata su ogni progetto. Lo STORICO di ciascun progetto vive in un file separato (<<REGISTRO_MODIFICHE>>) che non va mai promosso a baseline cross-progetto."
graph_rag:
  node_type: "DOCUMENT"
  node_id: "policy-versionamento-documentale-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "VINCOLA"
      target: "TUTTI_I_DOCUMENTI_DELLA_KNOWLEDGE_BASE"
    - type: "CONNESSA_A"
      target: "spec-graph-rag-ingestion-v2.0"
tags:
  - metadata
  - change-log
  - governance
  - versioning
  - cross-project
  - baseline
---

# Policy — Versionamento e Tracciamento della Knowledge Base
## Baseline Cross-Progetto

---

## 1. Obiettivo e Controllo del Versionamento

Questa policy definisce come vanno versionati e tracciati i documenti normativi, tecnici e metodologici che costituiscono una Knowledge Base indicizzata. Lo scopo è garantire tracciabilità delle revisioni, integrità dei riferimenti incrociati e sincronizzazione con l'indicizzatore Graph-RAG, prevenendo disallineamenti di versione fra il database vettoriale e il grafo.

**Separazione fondamentale:** questo file è la **policy** ed è riusabile invariato. Lo **storico** delle modifiche di uno specifico progetto è un artefatto locale, vive in `<<REGISTRO_MODIFICHE>>`, e non va mai promosso a baseline cross-progetto: è la parte che invecchia e che non si riusa.

---

## 2. Regole di Gestione delle Versioni

### [REGOLA-DEV-01] Obbligatorietà del versionamento semantico
- **Descrizione:** Tutti i documenti devono adottare il versionamento semantico a tre cifre (`X.Y.Z`):
  - `X` (Major): cambiamenti architetturali o riscritture strutturali dei vincoli. Una nuova Major invalida gli assunti di chi citava la versione precedente.
  - `Y` (Minor): aggiunta di nuove specifiche di funzionalità o nuove regole, retrocompatibili.
  - `Z` (Patch): correzioni di refactoring o formattazione che non alterano i contratti.
- **Effetto in caso di violazione (Failure Mode):** L'indicizzatore solleva un warning di non conformità sintattica in fase di validazione.
- **Entità Target:** Nessuna.

### [REGOLA-DEV-02] Tracciamento dei blocchi modificati
- **Descrizione:** Ogni riga del registro di modifica deve contenere: data di rilascio, versione assegnata, autore dell'aggiornamento, elenco esatto dei file modificati, motivazione sintetica della variazione con i tag delle regole impattate.
- **Effetto in caso di violazione (Failure Mode):** Perdita della correlazione storica e potenziale generazione di archi incoerenti nel grafo.
- **Entità Target:** Nessuna.

### [REGOLA-DEV-03] Version bump contestuale alla modifica
- **Descrizione:** Il campo `version` del frontmatter va incrementato **nello stesso commit** che modifica il corpo del documento. Un bump differito produce una finestra in cui l'indice contiene chunk che non corrispondono più al file sorgente.
- **Effetto in caso di violazione (Failure Mode):** La pipeline di ingestion incrementale rigetta il documento con `VERSION_NOT_BUMPED` (vedi `[REGOLA-VAL-09]` della spec di ingestion).
- **Entità Target:** Nessuna.

### [REGOLA-DEV-04] Changelog inline nel frontmatter
- **Descrizione:** Ogni documento porta nel proprio frontmatter un blocco `changelog` con le voci delle versioni rilasciate. Il registro centralizzato aggrega, non sostituisce: se il documento viene copiato in un altro progetto, la sua storia lo accompagna.
- **Effetto in caso di violazione (Failure Mode):** Un documento riusato altrove perde la motivazione delle proprie scelte e viene reinterpretato per assunzione.
- **Entità Target:** Nessuna.

---

## 3. Contratto del Frontmatter

Campi obbligatori su ogni documento indicizzato:

| Campo | Obbligatorio | Significato |
|---|---|---|
| `id` | **Sì** | Identificatore univoco del documento, versionato |
| `title` | **Sì** | Titolo leggibile |
| `project` | **Sì** | Nome del progetto, oppure `cross-project` per le baseline riusabili |
| `scope` | **Sì** | `cross-project` per le baseline; assente o di progetto altrimenti |
| `version` | **Sì** | Versionamento semantico `X.Y.Z` |
| `status` | **Sì** | `ENFORCED`, `DRAFT`, `ARCHIVED`, `DEPRECATED` |
| `classification` | **Sì** | Determina il peso di autorità nel ranking |
| `authority` | **Sì** | Coefficiente moltiplicativo di autorità della fonte |
| `path` | **Sì** | Percorso reale del file — **deve coincidere con la posizione effettiva** |
| `graph_rag.node_id` | **Sì** | Identificatore del nodo, **univoco su tutto il corpus** |
| `changelog` | **Sì** | Storia delle versioni del documento |
| `reuse` | Solo baseline | Parametri da istanziare e istruzioni di riuso |

> **Due errori che il corpus di origine conteneva davvero, da non ripetere:**
> 1. Un documento con `path:` che puntava a un file diverso da sé stesso.
> 2. Due documenti distinti con lo stesso `graph_rag.node_id` — collisione che rende ambigui gli archi del grafo.
>
> Entrambi vanno intercettati in fase di Discovery, non in review.

---

## 4. Template di Riga del Registro

Da usare in `<<REGISTRO_MODIFICHE>>`:

```markdown
### Versione X.Y.Z (GG Mese AAAA)
* **Autore:** Nome (Ruolo)
* **File Modificati:**
  * `percorso/del/file.md`
* **Regole Impattate:** `[REGOLA-XXX-NN]`, `[SAFEGUARD-YYY-NN]`
* **Descrizione Modifiche:** motivazione sintetica della variazione.
```

---

## 5. Scenari Comportamentali BDD (Gherkin)

```gherkin
Scenario: Validazione automatica del registro durante il commit
  Dato uno sviluppatore che ha completato l'aggiornamento di un documento normativo
  E ha correttamente incrementato il campo version nel frontmatter
  Quando l'indicizzatore analizza il registro delle modifiche in fase di Discovery
  Allora verifica la presenza di una riga corrispondente alla nuova versione rilasciata
  E valida che la versione riportata coincida con il metadato del file modificato
  E registra l'esito della validazione storica
```

```gherkin
Scenario: Blocco per modifica senza version bump
  Dato un documento il cui corpo è stato modificato
  E il cui campo version nel frontmatter è rimasto invariato
  Quando viene lanciata la pipeline di ingestion incrementale
  Allora la pipeline si arresta sollevando VERSION_NOT_BUMPED
  E l'indice resta sull'ultima versione coerente del documento
```

```gherkin
Scenario: Rilevamento di frontmatter con path incoerente
  Dato un documento il cui campo path non coincide con la sua posizione reale
  Quando l'indicizzatore esegue la fase di Discovery
  Allora il documento viene segnalato come PATH_MISMATCH
  E non viene indicizzato finché il frontmatter non è allineato
```

---

*Fine del documento — baseline cross-progetto v1.0.0*
