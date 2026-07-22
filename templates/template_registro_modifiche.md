---
id: "meta-change-log-v1.0"
title: "Registro delle Modifiche"
project: "NOME_PROGETTO"
version: "1.0.0"
date: "AAAA-MM-GG"
status: "ENFORCED"
classification: "METADATA"
path: "docs/00_meta_governance/change_log.md"
authority: 0.90
changelog:
  - version: "1.0.0"
    date: "AAAA-MM-GG"
    changes:
      - "Apertura del registro"
graph_rag:
  node_type: "DOCUMENT"
  node_id: "meta-change-log-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "DERIVA_DA"
      target: "policy-versionamento-documentale-v1.0"
tags:
  - metadata
  - change-log
  - governance
  - versioning
---

# Registro delle Modifiche
## NOME_PROGETTO

Storico delle revisioni della Knowledge Base di questo progetto.

Le **regole** di versionamento non stanno qui: sono normate una volta sola in [`docs/00_meta_governance/policy_versionamento_documentale.md`](../docs/00_meta_governance/policy_versionamento_documentale.md). Questo file contiene esclusivamente lo **storico**, che è l'unica parte non riusabile fra progetti.

---

## Storico delle Versioni Rilasciate

### Versione X.Y.Z (GG Mese AAAA)
* **Autore:** Nome (Ruolo)
* **File Modificati:**
  * `docs/percorso/del/file.md`
* **Regole Impattate:** `[REGOLA-XXX-NN]`, `[SAFEGUARD-YYY-NN]`
* **Descrizione Modifiche:** *(motivazione sintetica: perché la modifica è stata fatta, non cosa è cambiato — quello lo dice il diff)*

---

### Versione 1.0.0 (GG Mese AAAA)
* **Autore:** Nome (Ruolo)
* **File Modificati:**
  * *(elenco dei documenti del rilascio iniziale)*
* **Regole Impattate:** —
* **Descrizione Modifiche:** Rilascio iniziale del nucleo di governance.

---

## Promemoria operativo

- Il `version` del frontmatter va incrementato **nello stesso commit** che modifica il corpo del documento (`[REGOLA-DEV-03]`), altrimenti l'ingestion incrementale rigetta il file con `VERSION_NOT_BUMPED`.
- Una riga di questo registro senza la corrispondente voce `changelog` nel frontmatter del documento modificato è un disallineamento: la storia deve viaggiare col documento (`[REGOLA-DEV-04]`).
