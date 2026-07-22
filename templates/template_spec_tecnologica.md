---
id: "spec-tech-COMPONENTE-v1.0"
title: "Specifica Tecnologica — COMPONENTE"
project: "NOME_PROGETTO"
version: "1.0.0"
date: "AAAA-MM-GG"
status: "ENFORCED"
classification: "ARCHITECTURE"
path: "docs/01_architecture_norms/spec_tech_COMPONENTE.md"
authority: 0.85
changelog:
  - version: "1.0.0"
    date: "AAAA-MM-GG"
    changes:
      - "Rilascio iniziale della specifica tecnologica"
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "spec-tech-COMPONENTE-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "DERIVA_DA"
      target: "coding-standards-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "spec-tech-ALTRO_COMPONENTE-v1.0"
tags:
  - norms
  - architecture
---

# Specifica Tecnologica — COMPONENTE
## NOME_PROGETTO

---

## 1. Direzione Architetturale

*(Lo stack scelto in una frase, seguito da cosa si è deliberatamente evitato e perché. La parte sulle scelte scartate è quella che invecchia meglio: fra sei mesi nessuno ricorda perché non si è fatto diversamente, e qualcuno lo riproporrà.)*

**Deliberatamente evitato:** *(alternative scartate, con la ragione)*

---

## 2. Stack Tecnologico

| Area | Tecnologia | Uso |
|---|---|---|
| Runtime | | |
| Linguaggio | | |
| Database | | |
| ORM / accesso dati | | |
| Validazione | | |
| Contratti API | | |
| Storage file | | |
| Osservabilità | | |

> La colonna "Uso" va compilata: senza, la tabella diventa un elenco di nomi che non dice a cosa serve ciascuno né quando non usarlo.

---

## 3. Modalità di Utilizzo

- *(Qual è la source of truth di cosa)*
- *(Quali operazioni sono sincrone e transazionali, e quali no)*
- *(Cosa questo componente non deve mai fare)*

---

## 4. Design Pattern

- **Pattern:** *(nome)* — *(dove si applica e perché)*

> Elencare un pattern senza dire dove si applica lo rende inapplicabile. Se un pattern è nell'elenco ma non compare nel codice, va rimosso dall'elenco.

---

## 5. Struttura del Progetto

```
componente/
  src/
  tests/
```

---

## 6. Contratti Condivisi

**Da condividere:** *(DTO, eventi versionati, enum di stato, identificativi di correlazione)*

**Da non condividere:** *(entity dell'ORM, contesto di persistenza, repository, accesso diretto al database da altri componenti)*

> Questa distinzione è la più violata sotto pressione di consegna, ed è quella che determina se i componenti resteranno separabili.

---

## 7. Infrastruttura

```
docker-compose/
  <servizi>
```

*(Elencare i servizi necessari allo sviluppo locale e al primo rilascio.)*

---

## 8. Decisione Finale

*(La combinazione raccomandata in una frase, e su quali criteri è stata valutata: idoneità al contesto, testabilità, containerizzabilità, competenze disponibili in squadra.)*

---

## 9. Vincoli Ereditati

Questo componente eredita e non può derogare a:

- `docs/00_meta_governance/safeguards_security.md` — invarianti di sicurezza e integrità
- `docs/01_architecture_norms/coding_standards.md` — standard di codifica
- `docs/01_architecture_norms/api_error_contract.md` — contratto degli errori *(se espone API)*
- `docs/01_architecture_norms/observability_standards.md` — log, metriche, tracing
- `docs/01_architecture_norms/testing_strategy.md` — gate di qualità

> Se una scelta di stack rende impossibile rispettare un vincolo ereditato, il conflitto va risolto **prima** dell'implementazione, non aggirato a valle. Le regole di codifica devono restare agnostiche rispetto allo stack: i riferimenti tecnologici passano dal contratto di istanziazione, mai dal corpo della norma.
