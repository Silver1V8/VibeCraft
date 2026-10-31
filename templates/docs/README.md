---
id: "docs-baseline-index-v1.0"
title: "Indice della Baseline Documentale Cross-Progetto"
project: "cross-project"
scope: "cross-project"
version: "1.3.0"
date: "2026-10-31"
status: "ENFORCED"
classification: "METADATA"
path: "docs/README.md"
authority: 0.75
changelog:
  - version: "1.3.0"
    date: "2026-10-31"
    changes:
      - "fe1-canvas-review e superpowers/plans non fanno più parte della baseline di partenza: sono in archive/baseline-reports. I progetti già creati non vengono modificati."
  - version: "1.2.0"
    date: "2026-10-25"
    changes:
      - "Allineato al codice: due documenti di 04_knowledge_informative erano assenti dall'indice; 03_changes_historical e superpowers/plans sono indicizzati perché docs/ non ha esclusioni di cartella; l'avvio di un progetto non copia più questa baseline a mano"
  - version: "1.1.0"
    date: "2026-07-22"
    changes:
      - "Documentata docs/05_project_specs/ come cartella dedicata alle spec di progetto, senza redirect verso 00-04"
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Creato l'indice della libreria dopo la rimozione dei documenti legati al dominio prenotazione eventi"
graph_rag:
  node_type: "DOCUMENT"
  node_id: "docs-baseline-index-v1.0"
  databases: ["Qdrant", "NetworkX"]
  edges:
    - type: "CONTIENE"
      target: "safeguards-security-baseline-v2.0"
    - type: "CONTIENE"
      target: "coding-standards-baseline-v2.0"
    - type: "CONTIENE"
      target: "vibe-coding-workflow-baseline-v2.0"
    - type: "CONTIENE"
      target: "spec-graph-rag-ingestion-v2.0"
    - type: "CONTIENE"
      target: "policy-versionamento-documentale-v1.0"
    - type: "CONTIENE"
      target: "ui-ux-brand-directives-v1.0"
tags:
  - metadata
  - index
  - cross-project
  - baseline
---

Italiano | [English](README.en.md)

# Baseline Documentale Cross-Progetto

Questa cartella non documenta un'applicazione: è la **libreria di governance riusabile** da cui parte ogni nuovo progetto. Ogni documento è privo di riferimenti a un dominio applicativo specifico e va istanziato compilando la propria **Sezione 0 — Contratto di Istanziazione**.

---

## Contenuto

| Documento | Cosa norma | Classe | Authority |
|---|---|---|---|
| [`00_meta_governance/safeguards_security.md`](00_meta_governance/safeguards_security.md) | 12 invarianti inviolabili: identità, concorrenza, audit, segreti, privacy PII | `IRON_MEMORY` | 0.98 |
| [`00_meta_governance/definition_of_done.md`](00_meta_governance/definition_of_done.md) | Checklist di conformità a tre livelli e registrazione del sign-off | `METADATA` | 0.90 |
| [`00_meta_governance/policy_versionamento_documentale.md`](00_meta_governance/policy_versionamento_documentale.md) | Versionamento semantico, contratto del frontmatter, tracciamento delle modifiche | `METADATA` | 0.90 |
| [`00_meta_governance/change_log.md`](00_meta_governance/change_log.md) | Storico delle versioni rilasciate della documentazione di questo repository | `METADATA` | 0.90 |
| [`01_architecture_norms/coding_standards.md`](01_architecture_norms/coding_standards.md) | Metriche strutturali, eccezioni, tagging AST, validazione input, terminologia | `METHODOLOGY` | 0.85 |
| [`01_architecture_norms/api_error_contract.md`](01_architecture_norms/api_error_contract.md) | Schema unico di errore, status HTTP, versionamento, paginazione, idempotenza | `NORMS` | 0.85 |
| [`01_architecture_norms/observability_standards.md`](01_architecture_norms/observability_standards.md) | Log strutturati, correlation ID, redazione PII, metriche, alerting | `NORMS` | 0.85 |
| [`01_architecture_norms/testing_strategy.md`](01_architecture_norms/testing_strategy.md) | Tassonomia dei test, tracciabilità regola→test, gate di copertura | `NORMS` | 0.85 |
| [`01_architecture_norms/ui_ux_brand_directives.md`](01_architecture_norms/ui_ux_brand_directives.md) | Coerenza visiva, design token, accessibilità AA | `NORMS` | 0.80 |
| [`01_architecture_norms/architecture_decision_rationale.md`](01_architecture_norms/architecture_decision_rationale.md) | Motivazione condivisa: modular monolith vs microservizi/agenti LLM | `NORMS` | 0.85 |
| [`02_specs_normative/spec_graph_rag_ingestion.md`](02_specs_normative/spec_graph_rag_ingestion.md) | Pipeline di ingestion: chunking, authority, delta ingestion | `REQUIREMENTS` | 0.87 |
| [`04_knowledge_informative/vibe_coding_workflow.md`](04_knowledge_informative/vibe_coding_workflow.md) | Protocollo Human-in-the-Loop e gestione delle deviazioni | `METHODOLOGY` | 0.90 |
| [`04_knowledge_informative/graph_rag_ingestion_strategy.md`](04_knowledge_informative/graph_rag_ingestion_strategy.md) | Perché la spec di ingestion è fatta così. Non è una norma: non va citata come vincolo | `METHODOLOGY` | non dichiarata: vale il peso di classe, 0.5 |
| [`04_knowledge_informative/inferenza_locale_o_remota.md`](04_knowledge_informative/inferenza_locale_o_remota.md) | Trade-off fra modello locale e modello ospitato. Non impone il confine dei dati | `METHODOLOGY` | 0.40 |

`03_changes_historical/` non è una norma. È il posto delle change archiviate di un progetto. La review `fe1-canvas-review.md` non è una norma: sta in `archive/baseline-reports/` e non entra nel seme dei progetti nuovi. Un progetto già creato che la contiene non viene modificato da questo spostamento.

`superpowers/plans/` era il diario di sviluppo del tool. Non è baseline. È stato tolto dal seme e messo in `archive/baseline-reports/superpowers/plans/`. L'indicizzatore non ha una lista di cartelle da saltare: un markdown rimesso sotto `docs/` tornerebbe nel retrieval.

### Famiglie di identificatori

| Prefisso | Documento che le definisce |
|---|---|
| `SAFEGUARD-SEC/TXN/AUD-*` | `safeguards_security.md` |
| `REGOLA-CLEAN-*` | `coding_standards.md` |
| `REGOLA-HITL/PROC/DEV-*` | `vibe_coding_workflow.md` |
| `REGOLA-API-*` | `api_error_contract.md` |
| `REGOLA-OBS-*` | `observability_standards.md` |
| `REGOLA-TEST-*` | `testing_strategy.md` |
| `REGOLA-UI-*` | `ui_ux_brand_directives.md` |
| `REGOLA-DOD-*` | `definition_of_done.md` |
| `REGOLA-VAL/INT/WF-*` | `spec_graph_rag_ingestion.md` |

---

## Convenzione dei segnaposto

Ogni punto che dipende dal progetto è marcato `<<NOME_PARAMETRO>>` ed è dichiarato nel blocco `reuse.parameters` del frontmatter, oltre che nella Sezione 0 del documento.

Verifica che non restino segnaposto non risolti prima di considerare la baseline operativa:

```bash
grep -rn "<<[A-Z_]*>>" docs/ | grep -v "reuse:" | grep -v "da compilare"
```

**Regola di esclusione:** un vincolo non applicabile a un progetto va marcato `NON APPLICABILE` con motivazione scritta in Sezione 0. L'omissione silenziosa non è ammessa: l'assenza di motivazione equivale a vincolo attivo.

---

## Come si avvia un nuovo progetto

La console non copia questa baseline in ogni progetto. I progetti creati dopo il primo nascono vuoti. Al primo avvio in scrittura, se l'installazione non ha già `docs/` e `code/` alla radice, VibeCraft copia `templates/docs/` e `templates/code/` in `projects/legacy/`. I file `template_*.md` restano in `templates/` e non entrano nell'indice.

Per un corpus proprio i documenti compilati vanno in `docs/` di quel progetto, da Intake oppure già presenti nella root prima del primo avvio. Poi si indicizza. Il golden set di questa baseline non è trasferibile: le attese puntano a questi documenti, non a quelli del dominio.

1. Compilare la **Sezione 0** di ogni documento che si tiene e sostituire tutti i `<<PARAMETRO>>`.
2. Aggiungere i documenti **specifici del dominio**. Gli scheletri sono in [`templates/README.md`](../README.md) (`templates/README.md` nel repository, accanto a questa baseline, non dentro `docs/`):
   - glossario delle entità (dizionario dati del progetto);
   - matrice dei permessi (modello RBAC del progetto);
   - specifiche tecnologiche di backend, frontend e worker;
   - specifiche funzionali `spec_*.md`;
   - registro delle modifiche del progetto;
   - mappatura sinonimi → intent, se il progetto espone un'interfaccia in linguaggio naturale.

   `docs/05_project_specs/` è la cartella dedicata alle specifiche di progetto che non seguono il redirect per-classification delle altre cartelle (00-04): ci va tutto ciò che è specifico del progetto e non si vuole distribuire fra `00_meta_governance`/`01_architecture_norms`/`02_specs_normative` in base alla `classification`. È indicizzata automaticamente come il resto di `docs/`, senza bisogno di configurazione aggiuntiva. Vale anche il contrario: non esiste una cartella da escludere.

---

## Vincoli di stabilità

- Gli identificatori `[REGOLA-*]` e `[SAFEGUARD-*]` sono **chiavi di grafo**: si depreca, non si rinomina.
- `graph_rag.node_id` deve essere univoco su tutto il corpus (`[REGOLA-INT-06]`).
- Il campo `path` del frontmatter deve coincidere con la posizione reale del file.
- La struttura di cartelle `00_`…`04_` è parte del contratto di classificazione dell'indicizzatore: rinominarla cambia il peso di autorità dei documenti che contiene.
