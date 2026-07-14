---
id: "norm-spec-tech-logic-agent-v1.0"
title: "Specifica Tecnologica — Logic Agent"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-14"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/spec_tech_logic_agent.md"
authority: 0.85
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "norm-spec-tech-logic-agent-v1.0"
  scope: "Stack tecnologico, pattern architetturali e struttura di cartelle del progetto Logic Agent"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "DERIVA_DA"
      target: "norm-coding-standards-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-backend-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-frontend-v1.0"
tags:
  - norms
  - architecture
  - logic-agent
  - worker
  - messaging
---

# Specifica Tecnologica — Logic Agent
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Direzione Architetturale

Per il perimetro applicativo del Portale richieste e prenotazioni eventi aziendali, lo stack raccomandato per il Logic Agent è **.NET 10 Worker Service + RabbitMQ + MassTransit**, come Worker separato dal Backend, dedicato a workflow e notifiche asincrone. Si evitano deliberatamente architetture a microservizi completi e agenti LLM: aumenterebbero la complessità operativa senza un vantaggio proporzionato per un'applicazione interna di questo perimetro.

> Nota terminologica: nonostante il nome, il Logic Agent **non è un agente LLM**. È un orchestratore deterministico di side-effect.

---

## 2. Stack Tecnologico

| Area | Tecnologia | Uso |
|---|---|---|
| Runtime | .NET 10 Worker Service | Elaborazioni asincrone, workflow e notifiche |
| Broker | RabbitMQ | Disaccoppiamento tra Backend e processi asincroni |
| Messaging | MassTransit | Consumer, retry, code, DLQ e Outbox |
| Scheduling | Quartz.NET | Reminder, chiusura iscrizioni e job periodici |
| Email | SMTP aziendale o Microsoft Graph | Notifiche istituzionali |
| Slack | Slack Web API o Incoming Webhook | Notifiche verso canali/utenti autorizzati |
| Persistenza | PostgreSQL | Inbox, outbox e log di consegna |
| Osservabilità | Serilog + OpenTelemetry | Correlation ID, log, metriche e tracing |

---

## 3. Modalità di Utilizzo

Il Logic Agent è un **orchestratore deterministico di side-effect**, non un agente LLM e non la sorgente di verità. Non deve approvare richieste né modificare direttamente posti e budget: tali operazioni restano sincrone e transazionali nel Backend.

- Consumare eventi: `BookingRequestCreated`, `BookingRequestApproved`, `BookingRequestRejected`, `BookingRequestCancelled` ed `EventRegistrationDeadlineReached`.
- Verificare la deduplicazione del messaggio tramite `messageId`.
- Selezionare template, destinatari e canali in base al tipo evento e al ruolo.
- Inviare email e/o Slack, registrando esito, timestamp e risposta del provider.
- Applicare retry agli errori temporanei e inviare i messaggi irrisolvibili in Dead Letter Queue.

---

## 4. Design Pattern

- **Transactional Outbox:** il Backend salva dati ed evento nella stessa transazione.
- **Inbox Pattern:** il Worker memorizza i `messageId` elaborati.
- **Idempotent Consumer:** messaggi duplicati non producono notifiche duplicate.
- **Adapter pattern:** implementazioni intercambiabili per email, Slack e futuri canali.
- **Strategy pattern:** scelta dinamica di canale, template e destinatari.
- **Retry con exponential backoff:** gestione di timeout e indisponibilità temporanee.
- **Dead Letter Queue:** isolamento dei messaggi falliti senza bloccare il flusso.
- **Circuit Breaker:** protezione verso provider esterni non disponibili.
- **Template Method:** pipeline comune di deduplicazione, rendering, invio e registrazione esito.

---

## 5. Struttura del Progetto

```
logic-agent/
  src/
    Portal.LogicAgent.Worker/
      Consumers/
      Jobs/
      Notifications/
        Channels/
        Templates/
        Strategies/
      Persistence/
      Monitoring/
  tests/
    Portal.LogicAgent.Tests/
    Portal.LogicAgent.IntegrationTests/
```

---

## 6. Contratti Condivisi

Il Logic Agent consuma il progetto `Portal.Contracts`, condiviso tramite pacchetto interno con il Backend.

**Condividere:** DTO API, eventi versionati, enum di stato, `correlationId`, `messageId` e `occurredAt`.

**Non condividere:** entity EF Core, `DbContext`, repository, logica di dominio o accesso diretto al database dal Logic Agent.

---

## 7. Infrastruttura Condivisa

Per lo sviluppo locale e il primo rilascio si utilizza Docker Compose, mantenendo PostgreSQL come database centrale, RabbitMQ per l'asincronia e MinIO per locandine/allegati.

```
docker-compose/
  frontend
  backend-api
  logic-agent
  postgresql
  rabbitmq
  minio
  redis (opzionale)
```

---

## 8. Decisione Finale

La soluzione raccomandata per il Logic Agent è **.NET Worker/RabbitMQ/MassTransit**, integrata con il Backend .NET 10/ASP.NET Core/PostgreSQL e con il Frontend Next.js/TypeScript. La combinazione è adatta a un contesto enterprise, containerizzabile, facilmente testabile e sufficientemente semplice da evolvere senza adottare microservizi prematuramente.
