---
id: "glossario-entita-v1.0"
title: "Glossario Entità — Single Source of Truth del Modello Dati"
project: "NOME_PROGETTO"
version: "1.0.0"
date: "AAAA-MM-GG"
status: "ENFORCED"
classification: "DATA_DICTIONARY"
path: "docs/00_meta_governance/glossario_entita.md"
authority: 0.95
changelog:
  - version: "1.0.0"
    date: "AAAA-MM-GG"
    changes:
      - "Rilascio iniziale del dizionario dati"
graph_rag:
  node_type: "DATA_DICTIONARY"
  node_id: "glossario-entita-v1.0"
  databases: ["Qdrant", "NetworkX"]
  entity_count: 0
  entities:
    - "ENTITA_A"
  edges:
    - type: "VINCOLA"
      target: "TUTTI_I_MODULI_APPLICATIVI"
    - type: "DIPENDE_DA"
      target: "safeguards-security-baseline-v2.0"
tags:
  - data-dictionary
  - entity
  - domain-model
  - single-source-of-truth
---

# Glossario Entità — Single Source of Truth del Modello Dati
## NOME_PROGETTO

> **Nota per l'AI Coding Agent e il sistema Graph RAG**
>
> Questo documento è il **dizionario dati canonico** del progetto. Ogni entità è descritta come nodo atomico e autosufficiente: relazioni, vincoli di integrità e regole di business che operano sul dato sono centralizzate qui. In caso di conflitto con qualsiasi altra fonte sullo schema dei dati, questo documento prevale.
>
> Le entità vanno scritte in `MAIUSCOLO` fra backtick: è la marcatura da cui il parser crea gli archi del grafo (`[REGOLA-INT-02]`).

---

## Indice delle Entità

| Entità | Ruolo nel sistema | Owner primario | Tipo di ciclo di vita |
|---|---|---|---|
| [`ENTITA_A`](#entità-entita_a) | *(ruolo in una riga)* | *(ruolo owner)* | *(Managed / State-machine / Append-only)* |

---

## Mappa ERD sintetica

```
ENTITA_A ||--o{ ENTITA_B : "relazione (chiave_esterna)"
```

---

## Entità: `ENTITA_A`

**Definizione:** *(cosa rappresenta nel dominio, in due o tre frasi. Non descrivere come è implementata: descrivere cosa significa per il business.)*

**Owner primario:** *(chi la crea, chi la modifica, chi la archivia)*

---

### Attributi

| Campo | Tipo dato | Obbligatorio | Vincoli logici |
|---|---|---|---|
| `id` | `UUID` | **Sì** | Chiave primaria. Immutabile dopo la creazione. |
| `campo_esempio` | `VARCHAR(150)` | **Sì** | *(vincolo esplicito: lunghezza, dominio di valori, invariante)* |
| `stato` | `ENUM` | **Sì** | Valori ammessi: *(elencare)*. Default alla creazione: *(valore)*. |
| `creato_il` | `TIMESTAMPTZ` | **Sì** | Immutabile. |

> Per ogni campo calcolato dal sistema, indicare la **formula operativa** e se è soggetto a lock transazionale.

---

### Vincoli di Integrità

| Vincolo | Livello di enforcement |
|---|---|
| *(constraint SQL)* | Database |
| *(invariante applicativa)* | Dominio |

---

### Transizioni di Stato

*(Se l'entità ha una macchina a stati, elencare le transizioni ammesse e chi può eseguirle. Ogni transizione non elencata è vietata.)*

| Da | A | Attore ammesso | Regola |
|---|---|---|---|
| *(stato)* | *(stato)* | *(ruolo)* | `[REGOLA-XXX-NN]` |

**Stati terminali:** *(elencare gli stati da cui non si esce)*

---

### Relazioni

| Verso | Cardinalità | Chiave | Comportamento alla cancellazione |
|---|---|---|---|
| `ENTITA_B` | 1:N | `entita_a_id` | `ON DELETE RESTRICT` — vedi `[SAFEGUARD-AUD-03]` |

---

### Classificazione Privacy

| Campo | Etichetta | Note |
|---|---|---|
| `campo_esempio` | `PII-RESTRICTED` / `RESTRICTED` / `NON-PII` | *(chi può vederlo, e se può uscire dal confine local-first)* |

> I campi marcati `PII-RESTRICTED` vanno riportati in `<<CAMPI_PII>>` nel contratto di istanziazione dei safeguard e nel sanitizer dei log (`[REGOLA-OBS-06]`).

---

## Entità: `ENTITA_B`

*(ripetere la struttura per ogni entità)*
