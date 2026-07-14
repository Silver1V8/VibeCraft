---
id: "norm-spec-tech-backend-v1.0"
title: "Specifica Tecnologica — Backend"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-14"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/spec_tech_backend.md"
authority: 0.85
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "norm-spec-tech-backend-v1.0"
  scope: "Stack tecnologico, pattern architetturali e struttura di cartelle del progetto Backend"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "DERIVA_DA"
      target: "norm-coding-standards-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-frontend-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-logic-agent-v1.0"
tags:
  - norms
  - architecture
  - backend
  - dotnet
  - aspnetcore
---

# Specifica Tecnologica — Backend
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Direzione Architetturale

Per il perimetro applicativo del Portale richieste e prenotazioni eventi aziendali, lo stack raccomandato per il Backend è **.NET 10 + ASP.NET Core Web API + PostgreSQL**, strutturato come **modular monolith**. Si evitano deliberatamente architetture a microservizi completi e agenti LLM: aumenterebbero la complessità operativa senza un vantaggio proporzionato per un'applicazione interna di questo perimetro.

---

## 2. Stack Tecnologico

| Area | Tecnologia | Uso |
|---|---|---|
| Runtime | .NET 10 + ASP.NET Core Web API | API REST, logica di dominio, autorizzazione e report |
| Linguaggio | C# | Coerenza enterprise, tooling, test e competenze disponibili |
| Database | PostgreSQL | Dati transazionali: eventi, richieste, budget, audit e outbox |
| ORM | Entity Framework Core | Mapping, migrazioni, query e transazioni |
| Validazione | FluentValidation | Validazione centralizzata dei comandi |
| Command/Query | MediatR (opzionale) | Handler e pipeline comportamentali |
| Contratti API | OpenAPI/Swagger | Documentazione e generazione client TypeScript |
| Storage file | MinIO o Azure Blob Storage | Locandine e allegati fuori dal database |
| Osservabilità | Serilog + OpenTelemetry | Log strutturati, metriche e tracing |
| Cache opzionale | Redis | Cache catalogo e rate limiting distribuito |

---

## 3. Modalità di Utilizzo

- Il Backend è la **source of truth** per utenti, ruoli, catalogo, richieste, budget, capienza, audit ed export.
- Eseguire la verifica di capienza e budget solo durante l'approvazione e all'interno di una transazione atomica.
- Proteggere la concorrenza tramite optimistic concurrency sull'evento/budget; usare lock mirati solo nel flusso critico se necessario.
- Pubblicare gli eventi di integrazione tramite Outbox nella stessa transazione della modifica di dominio.

---

## 4. Design Pattern

- **Modular Monolith:** un deployable, con confini di dominio chiari e moduli indipendenti.
- **DDD leggero:** aggregate principali `Event`, `BookingRequest` e `TrainingBudget`.
- **Vertical Slice Architecture:** endpoint, command/query, validator, handler e test organizzati per funzionalità.
- **CQRS pragmatico:** separare letture e scritture senza introdurre Event Sourcing.
- **Command pattern:** `CreateBookingRequest`, `ApproveBookingRequest`, `RejectBookingRequest` e `PublishEvent`.
- **Specification pattern:** filtri e criteri riutilizzabili per eventi, richieste e report.
- **Policy-based authorization:** policy `CanManageEvent`, `CanApproveRequest` e `CanViewTeamRequests`.
- **Transactional Outbox:** modifica del dominio ed evento persistiti insieme.
- **Audit Log immutabile:** utente, timestamp, azione, commento e correlation ID per ogni cambio stato.

---

## 5. Struttura del Progetto

```
backend/
  src/
    Portal.Api/
    Portal.Application/
      Features/
        Events/
        BookingRequests/
        Approvals/
        Reporting/
        Users/
    Portal.Domain/
      Events/
      BookingRequests/
      Budgets/
      Shared/
    Portal.Infrastructure/
      Persistence/
      Identity/
      Storage/
      Messaging/
      Export/
    Portal.Contracts/
      Requests/
      Responses/
      IntegrationEvents/
  tests/
    Portal.Domain.Tests/
    Portal.Application.Tests/
    Portal.IntegrationTests/
```

---

## 6. Contratti Condivisi

Il Backend mantiene il progetto `Portal.Contracts`, condiviso tramite pacchetto interno con il Logic Agent. Per il Frontend, il contratto viene esposto tramite OpenAPI, da cui viene generato il client TypeScript.

**Condividere:** DTO API, eventi versionati, enum di stato, `correlationId`, `messageId` e `occurredAt`.

**Non condividere:** entity EF Core, `DbContext`, repository, logica di dominio o accesso diretto al database dal Logic Agent.

```
Portal.Contracts/
  IntegrationEvents/
  ApiContracts/
  ErrorContracts/
  Shared/
```

---

## 7. Decisione Finale

La soluzione raccomandata per il Backend è **.NET 10/ASP.NET Core/PostgreSQL**, integrata con il Frontend Next.js/TypeScript e con il Logic Agent .NET Worker/RabbitMQ/MassTransit. La combinazione è adatta a un contesto enterprise, containerizzabile, facilmente testabile e sufficientemente semplice da evolvere senza adottare microservizi prematuramente.
