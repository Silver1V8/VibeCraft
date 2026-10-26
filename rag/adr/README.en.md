English | [Italiano](README.md)

# ADR — Architecture Decision Records

Significant architectural decisions for the project, with context,
motivations, consequences, and explicit triggers to reopen them. Not under
`docs/` on purpose: `docs/` is the corpus indexed by the RAG, and an ADR there
would pollute retrieval.

| # | Title | Status |
|---|--------|-------|
| [0001](0001-multi-agent-scartato.md) | Multi-agent supervisor discarded | Discarded (with reopen trigger) |
| [0002](0002-autorita-dichiarata-e-fiducia-sul-cammino.md) | Declared authority and trust along the graph path | Accepted and implemented. The table in the document is a snapshot from 18 August 2026, not today’s code. The [prompts](../../archive/adr/0002-prompts/) are the plan that was executed, not open work |

## Other traces

Not every decision becomes a numbered ADR: the traces below collect registers and plans —
measurements, findings, and future work — not single closed decisions.
They live here for the same reason as the ADRs above: they are development chronicle, not
corpus to index.

| File | What it contains |
|---|---|
| [`AUDIT.md`](../../archive/adr/AUDIT.md) | audit chronicle, in archive since 25 October 2026. Line numbers cited elsewhere remain those of the moved file |
| [`RESIDUI.md`](../../archive/adr/RESIDUI.md) | backlog derived from the audit, closed; same folder |
| [`DISTRIBUTION.md`](DISTRIBUTION.md) | the distribution plan: numbers, forks, and packaging decisions |
| [`EVOLUZIONE.md`](../../archive/adr/EVOLUZIONE.md) | September 2026 evolution plan, in archive |
| [`DOCLING_PIPELINE_ALTERNATIVA.md`](DOCLING_PIPELINE_ALTERNATIVA.md) | proposal for an alternative Docling pipeline to the Granite pilot, with configuration and evaluation criteria |
| [`NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`](NOTA_IMPLEMENTAZIONE_MIGLIORIE.md) | improvements and bug fixes from the Docling pilot and independent of it: cause, diff, checks, risk, and rollback |
| [`PIPELINE_GATE.md`](PIPELINE_GATE.md) | operational gate, end-to-end cycle verified on 15 September 2026, measurements, friction log, and open issues |

## Sidecar scalability — run of 21 September 2026

- [Original plan](SCALABILITA_SIDECAR_DELTA.md), kept as the requirements source.
- [Final matrix and decisions](SCALABILITA_SIDECAR_DELTA_MATRICE.md), with proof limits and conditional branches not activated.
- [Final results, curves, and trade-offs](../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md), with migration, retention, and batching study.

Integrated on `main` in `3eda61a`: per-document NPY and on-demand reads,
explicit NPZ migration, and real-delta benchmark. The final review corrected
write-time attribution and recovery of interrupted reloads.
Integration check: 1,767 tests passed on Windows (5 skipped for missing Docling
weights), 438 on Linux (9 skipped for missing Git, covered on Windows).
Memory savings are measured; many deltas on small documents can slow down.
Limited batching studied; sharding and ColBERT on Qdrant not activated.
To update an existing index follow the [operational procedure](../README.md#artefatti-dellindice-formati-sicuri-ispezionabili-e-versionati-bluegreen).
