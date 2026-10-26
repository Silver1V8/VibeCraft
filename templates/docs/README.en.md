---
id: "docs-baseline-index-v1.0"
title: "Cross-Project Document Baseline Index"
project: "cross-project"
scope: "cross-project"
version: "1.2.0"
date: "2026-10-25"
status: "ENFORCED"
classification: "METADATA"
path: "docs/README.md"
authority: 0.75
changelog:
  - version: "1.2.0"
    date: "2026-10-25"
    changes:
      - "Aligned with code: two documents under 04_knowledge_informative were missing from the index; 03_changes_historical and superpowers/plans are indexed because docs/ has no folder exclusions; starting a project no longer copies this baseline by hand"
  - version: "1.1.0"
    date: "2026-07-22"
    changes:
      - "Documented docs/05_project_specs/ as the folder for project specs, without redirect toward 00-04"
  - version: "1.0.0"
    date: "2026-07-22"
    changes:
      - "Created the library index after removing documents tied to the event-booking domain"
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

English | [Italiano](README.md)

# Cross-Project Document Baseline

This folder does not document an application: it is the **reusable governance library** every new project starts from. Each document is free of references to a specific application domain and must be instantiated by filling in its own **Section 0 — Instantiation Contract**.

---

## Contents

| Document | What it governs | Class | Authority |
|---|---|---|---|
| [`00_meta_governance/safeguards_security.md`](00_meta_governance/safeguards_security.md) | 12 inviolable invariants: identity, concurrency, audit, secrets, PII privacy | `IRON_MEMORY` | 0.98 |
| [`00_meta_governance/definition_of_done.md`](00_meta_governance/definition_of_done.md) | Three-level compliance checklist and sign-off registration | `METADATA` | 0.90 |
| [`00_meta_governance/policy_versionamento_documentale.md`](00_meta_governance/policy_versionamento_documentale.md) | Semantic versioning, frontmatter contract, change tracking | `METADATA` | 0.90 |
| [`00_meta_governance/change_log.md`](00_meta_governance/change_log.md) | History of released documentation versions for this repository | `METADATA` | 0.90 |
| [`01_architecture_norms/coding_standards.md`](01_architecture_norms/coding_standards.md) | Structural metrics, exceptions, AST tagging, input validation, terminology | `METHODOLOGY` | 0.85 |
| [`01_architecture_norms/api_error_contract.md`](01_architecture_norms/api_error_contract.md) | Single error schema, HTTP status, versioning, pagination, idempotency | `NORMS` | 0.85 |
| [`01_architecture_norms/observability_standards.md`](01_architecture_norms/observability_standards.md) | Structured logs, correlation ID, PII redaction, metrics, alerting | `NORMS` | 0.85 |
| [`01_architecture_norms/testing_strategy.md`](01_architecture_norms/testing_strategy.md) | Test taxonomy, rule→test traceability, coverage gate | `NORMS` | 0.85 |
| [`01_architecture_norms/ui_ux_brand_directives.md`](01_architecture_norms/ui_ux_brand_directives.md) | Visual consistency, design tokens, AA accessibility | `NORMS` | 0.80 |
| [`01_architecture_norms/architecture_decision_rationale.md`](01_architecture_norms/architecture_decision_rationale.md) | Shared rationale: modular monolith vs microservices/LLM agents | `NORMS` | 0.85 |
| [`02_specs_normative/spec_graph_rag_ingestion.md`](02_specs_normative/spec_graph_rag_ingestion.md) | Ingestion pipeline: chunking, authority, delta ingestion | `REQUIREMENTS` | 0.87 |
| [`04_knowledge_informative/vibe_coding_workflow.md`](04_knowledge_informative/vibe_coding_workflow.md) | Human-in-the-Loop protocol and deviation handling | `METHODOLOGY` | 0.90 |
| [`04_knowledge_informative/graph_rag_ingestion_strategy.md`](04_knowledge_informative/graph_rag_ingestion_strategy.md) | Why the ingestion spec is built this way. Not a norm: do not cite it as a constraint | `METHODOLOGY` | undeclared: class weight applies, 0.5 |
| [`04_knowledge_informative/inferenza_locale_o_remota.md`](04_knowledge_informative/inferenza_locale_o_remota.md) | Trade-off between local and hosted model. Does not impose the data boundary | `METHODOLOGY` | 0.40 |

`03_changes_historical/` is not a norm. Today it contains `fe1-canvas-review.md`, an archival review, and it is indexed anyway.

`superpowers/plans/` is the development diary committed under this folder. It is not baseline. The indexer reads it anyway: on `docs/`, `source_files` receives no folders to skip (`rag/core/indexing.py`). A markdown file placed here competes in retrieval with the norms.

### Identifier families

| Prefix | Document that defines them |
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

## Placeholder convention

Every project-dependent point is marked `<<NOME_PARAMETRO>>` and declared in the frontmatter `reuse.parameters` block, as well as in Section 0 of the document.

Check that no unresolved placeholders remain before considering the baseline operational:

```bash
grep -rn "<<[A-Z_]*>>" docs/ | grep -v "reuse:" | grep -v "da compilare"
```

**Exclusion rule:** a constraint that does not apply to a project must be marked `NON APPLICABILE` with a written rationale in Section 0. Silent omission is not allowed: missing rationale equals an active constraint.

---

## How to start a new project

The console does not copy this baseline into every project. Projects created after the first start empty. On the first writer start, if the install does not already have `docs/` and `code/` at the root, VibeCraft copies `templates/docs/` and `templates/code/` into `projects/legacy/`. `template_*.md` files stay in `templates/` and do not enter the index.

For your own corpus, filled-in documents go under that project’s `docs/`, via Intake or already present in the root before first start. Then you index. This baseline’s golden set is not transferable: expectations point at these documents, not at domain ones.

1. Fill in **Section 0** of every document you keep and replace all `<<PARAMETRO>>`.
2. Add **domain-specific** documents. Skeletons are in [`templates/README.md`](../README.md) (`templates/README.md` in the repository, next to this baseline, not inside `docs/`):
   - entity glossary (project data dictionary);
   - permission matrix (project RBAC model);
   - backend, frontend, and worker technology specs;
   - functional specs `spec_*.md`;
   - project change register;
   - synonym → intent mapping, if the project exposes a natural-language interface.

   `docs/05_project_specs/` is the folder for project specs that do not follow the per-classification redirect of the other folders (00-04): put there everything project-specific that you do not want distributed across `00_meta_governance`/`01_architecture_norms`/`02_specs_normative` by `classification`. It is indexed automatically like the rest of `docs/`, with no extra configuration. The converse also holds: there is no folder to exclude.

---

## Stability constraints

- Identifiers `[REGOLA-*]` and `[SAFEGUARD-*]` are **graph keys**: deprecate, do not rename.
- `graph_rag.node_id` must be unique across the whole corpus (`[REGOLA-INT-06]`).
- The frontmatter `path` field must match the file’s real location.
- The `00_`…`04_` folder structure is part of the indexer’s classification contract: renaming it changes the authority weight of the documents it holds.
