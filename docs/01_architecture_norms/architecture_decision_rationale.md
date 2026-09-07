---
id: "norm-architecture-decision-rationale-v1.0"
title: "Motivazione Architetturale Condivisa — Modular Monolith vs Microservizi/Agenti LLM"
project: "cross-project"
version: "1.0.0"
date: "2026-07-28"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/architecture_decision_rationale.md"
authority: 0.85
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "norm-architecture-decision-rationale-v1.0"
  scope: "Motivazione comune alla base delle scelte di stack tecnologico di Frontend, Backend e Logic Agent"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "DERIVA_DA"
      target: "coding-standards-baseline-v2.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-frontend-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-backend-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-logic-agent-v1.0"
tags:
  - norms
  - architecture
  - decision-rationale
---

# Motivazione Architetturale Condivisa
## Baseline Cross-Progetto

---

## 1. Perimetro Applicativo

L'applicazione ospitata è un gestionale interno di scala e complessità di dominio contenute: un catalogo di risorse, un flusso di richiesta e approvazione, e un budget da tracciare. Il perimetro concreto è dichiarato dalle spec tecniche del progetto ospitante (`docs/05_project_specs/`, locali e non versionate in questo repo); qui conta solo la sua **scala**, perché è la scala — non il dominio — a reggere l'argomento delle sezioni seguenti.

## 2. Perché No Microservizi e No Agenti LLM

Si evitano deliberatamente architetture a microservizi completi e agenti LLM lato Frontend, Backend o Logic Agent: per un perimetro applicativo di questa scala, aumenterebbero la complessità operativa (deployment, osservabilità, versionamento dei contratti, latenza di rete) senza un vantaggio proporzionato. Il Logic Agent, in particolare, nonostante il nome è un orchestratore deterministico di side-effect e non un agente LLM.

## 3. Perché Modular Monolith

Un modular monolith con confini di dominio chiari (Frontend Next.js/React/TypeScript, Backend .NET 10/ASP.NET Core/PostgreSQL, Logic Agent .NET Worker/RabbitMQ/MassTransit) è containerizzabile, facilmente testabile e sufficientemente semplice da evolvere in futuro verso microservizi reali, se e quando il perimetro applicativo lo giustificherà.

---

Questo documento è la fonte unica della motivazione riportata in sintesi in [`spec_tech_frontend.md`](../05_project_specs/spec_tech_frontend.md) §1 e §7, [`spec_tech_backend.md`](../05_project_specs/spec_tech_backend.md) §1 e §7, e [`spec_tech_logic_agent.md`](../05_project_specs/spec_tech_logic_agent.md) §1 e §8. Eventuali revisioni della motivazione vanno applicate qui, non ricopiate nelle singole spec.
