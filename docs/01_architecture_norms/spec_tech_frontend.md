---
id: "norm-spec-tech-frontend-v1.0"
title: "Specifica Tecnologica — Frontend"
project: "VibeCraft — Sistema di Gestione Eventi Aziendali"
version: "1.0.0"
date: "2026-07-14"
status: "ENFORCED"
classification: "NORMS"
path: "docs/01_architecture_norms/spec_tech_frontend.md"
authority: 0.85
graph_rag:
  node_type: "ARCHITECTURE"
  node_id: "norm-spec-tech-frontend-v1.0"
  scope: "Stack tecnologico, pattern architetturali e struttura di cartelle del progetto Frontend"
  databases: ["Qdrant", "NetworkX"]
  embedding_model: "BGE-M3"
  reranker: "ColBERT"
  edges:
    - type: "DERIVA_DA"
      target: "norm-coding-standards-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-backend-v1.0"
    - type: "CONNESSA_A"
      target: "norm-spec-tech-logic-agent-v1.0"
tags:
  - norms
  - architecture
  - frontend
  - nextjs
  - react
---

# Specifica Tecnologica — Frontend
## VibeCraft — Sistema di Gestione Eventi Aziendali

---

## 1. Direzione Architetturale

Per il perimetro applicativo del Portale richieste e prenotazioni eventi aziendali, lo stack raccomandato per il Frontend è **Next.js + React + TypeScript**, come parte di un modular monolith full .NET/React affiancato da un Worker separato per workflow e notifiche. Si evitano deliberatamente architetture a microservizi completi e agenti LLM lato Frontend: aumenterebbero la complessità operativa senza un vantaggio proporzionato per un'applicazione interna di questo perimetro.

---

## 2. Stack Tecnologico

| Area | Tecnologia | Uso |
|---|---|---|
| Framework | Next.js + React + TypeScript | Portale dipendenti, area Manager e area amministrativa |
| UI | Tailwind CSS + shadcn/ui | Design system consistente, accessibile e rapido da implementare |
| Form | React Hook Form + Zod | Gestione e validazione tipizzata delle richieste |
| Dati | TanStack Query | Chiamate REST, cache e invalidazione dopo azioni utente |
| Autenticazione | Auth.js + Google OAuth/OIDC | Accesso con Google Workspace; controllo email verificata e dominio @progettopa.it |
| Grafici | Recharts | Grafico budget formativo |
| Test | Vitest + Testing Library + Playwright | Test unitari, componenti ed end-to-end |

---

## 3. Modalità di Utilizzo

- Gestire il rendering del catalogo, il form di richiesta, l'area personale e le interfacce Manager/Admin.
- Applicare validazioni UX nel browser; la validazione decisiva resta nel Backend.
- Nascondere le azioni non consentite in base al ruolo, senza considerarlo un controllo di sicurezza.
- Usare un client API tipizzato, preferibilmente generato dalla specifica OpenAPI del Backend.

---

## 4. Design Pattern

- **Feature-based architecture:** moduli `events`, `booking-requests`, `approvals` e `admin`.
- **Container/Presentational Components:** pagine e hook gestiscono i dati; i componenti UI ricevono solo props.
- **API Client pattern:** gestione centralizzata di autenticazione, errori e chiamate HTTP.
- **Separazione Server/Client Components:** Server Components per le letture iniziali, Client Components solo per interazioni, form e grafici.
- **Route Guards:** middleware per sessione e dominio email; l'autorizzazione definitiva resta gestita dal Backend.

---

## 5. Struttura del Progetto

```
frontend/
  src/
    app/
      login/
      eventi/
      richieste/
      manager/
      admin/
    features/
      auth/
      events/
      booking-requests/
      approvals/
      reporting/
    components/
      ui/
      shared/
      layout/
    lib/
      api/
      auth/
      validation/
    hooks/
    types/
```

---

## 6. Contratti Condivisi

Il contratto tra Frontend e Backend è esposto tramite OpenAPI, a partire dal quale viene generato il client TypeScript consumato dal Frontend. Il Frontend non definisce autonomamente i contratti di dominio: consuma esclusivamente quanto pubblicato dal Backend.

---

## 7. Decisione Finale

La soluzione raccomandata per il Frontend è **Next.js/TypeScript**, integrata con il Backend .NET 10/ASP.NET Core/PostgreSQL e con il Logic Agent .NET Worker/RabbitMQ/MassTransit. La combinazione è adatta a un contesto enterprise, containerizzabile, facilmente testabile e sufficientemente semplice da evolvere senza adottare microservizi prematuramente.

---

## 8. Direttive UI/UX e Coerenza Visiva

La realizzazione grafica del Frontend DEVE essere stilisticamente simile e congruente con l’identità visiva del sito istituzionale di Progetto PA, https://www.progettopa.it, adottandone linguaggio visivo, tono, percezione istituzionale e coerenza complessiva di brand.

In particolare, il Frontend DEVE:
- mantenere un’impostazione grafica sobria, professionale e istituzionale, evitando soluzioni visive eccessivamente promozionali, playful o consumer-oriented;
- risultare coerente con palette colori, contrasti, tipografia percepita, spaziature, stile dei componenti e gerarchia visiva del sito Progetto PA;
- trasmettere continuità con l’ecosistema digitale aziendale, così che il Portale appaia come prodotto interno della stessa identità organizzativa e non come applicazione visivamente disallineata;
- usare Tailwind CSS e shadcn/ui come base implementativa, ma con personalizzazione del tema per riflettere il più possibile l’identità visuale del sito Progetto PA;
- privilegiare pattern UI chiari, accessibili e lineari, coerenti con un contesto enterprise destinato a dipendenti, manager e amministratori;
- evitare stili generici da dashboard template, gradienti superflui, animazioni invasive, colori troppo saturi o componenti visivamente non congruenti con il contesto istituzionale aziendale.

La coerenza grafica con il sito Progetto PA costituisce un vincolo di progettazione Frontend e deve riflettersi nel tema globale, nei layout, nella libreria dei componenti condivisi e nelle pagine principali (`login`, `eventi`, `richieste`, `manager`, `admin`).

Prima dell’implementazione definitiva, è raccomandata la definizione di un piccolo layer di design tokens condivisi (`colors`, `radius`, `shadow`, `font`, `spacing`) derivati dall’analisi del sito Progetto PA, da applicare sopra il design system tecnico scelto.