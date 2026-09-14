# ADR — Architecture Decision Records

Decisioni architetturali significative del progetto, con contesto,
motivazioni, conseguenze e trigger espliciti per riaprirle. Non sotto
`docs/` di proposito: `docs/` è il corpus indicizzato dal RAG, e un ADR lì
dentro inquinerebbe il retrieval.

| # | Titolo | Stato |
|---|--------|-------|
| [0001](0001-multi-agent-scartato.md) | Multi-agent supervisor scartato | Scartato (con trigger di riapertura) |
| [0002](0002-autorita-dichiarata-e-fiducia-sul-cammino.md) | Autorità dichiarata e fiducia sul cammino del grafo | Accettato ([piano di lavoro](0002-prompts/)) |

## Le altre tracce

Non ogni decisione entra in un ADR numerato: le tracce sotto raccolgono registri e piani —
misure, riscontri e lavoro futuro — non singole decisioni chiuse.
Vivono qui per la stessa ragione degli ADR sopra: sono cronaca di sviluppo, non corpus da
indicizzare.

| File | Cosa contiene |
|---|---|
| [`AUDIT.md`](AUDIT.md) | l'audit del progetto: run di misura, riscontri, indagini e le sessioni che li hanno chiusi |
| [`RESIDUI.md`](RESIDUI.md) | il backlog derivato dall'audit — cosa resta aperto, triato in sessioni con un prompt pronto |
| [`DISTRIBUTION.md`](DISTRIBUTION.md) | il piano di distribuzione: numeri, forcelle e decisioni sul packaging |
| [`EVOLUZIONE.md`](EVOLUZIONE.md) | il piano di evoluzione approvato: baseline locali, cancelli misurabili, rollback e forcelle ancora aperte |
| [`DOCLING_PIPELINE_ALTERNATIVA.md`](DOCLING_PIPELINE_ALTERNATIVA.md) | la proposta di pipeline Docling alternativa al pilot Granite, con configurazione e criteri di valutazione |
| [`NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`](NOTA_IMPLEMENTAZIONE_MIGLIORIE.md) | migliorie e bugfix emersi dal pilot Docling e indipendenti da esso: causa, diff, verifiche, rischio e rollback |
