Italiano | [English](README.en.md)

> **Lingue della documentazione.** L'italiano è canonico. Dal 2026-10-28 il dettaglio
> operativo vive in [`docs/`](docs/) (fuori dal corpus RAG, come gli ADR); questo file
> è l'indice. L'inglese (`README.en.md`) è un indice breve che punta alle stesse pagine IT —
> niente doppia manutenzione del corpo.

# rag/ — Console Graph-RAG

**Stato documentato: `main`, 30 ottobre 2026.**
Il multi-progetto è in `main` dal 5 ottobre; il delta copy-on-write e l'embedding su GPU
dal 12. I manuali in console sono del 25. Dal 29 il grafo collega le chiamate HTTP del
frontend agli endpoint Minimal API del backend (archi `CALLS`, vedi
[Grafo, drift e code index](docs/grafo-e-code-index.md)) e il full rebuild libera la VRAM
tenuta da Ollama prima di embeddare su GPU (vedi
[Embedding](docs/indice-e-embedding.md#embedding-bge-m3-cpu-per-le-query-acceleratore-per-il-reindex)).
Dal 30 un menu **Impostazioni** sceglie i modelli LLM, locali, cloud o per attività, anche
Claude con l'abbonamento (vedi [LLM](docs/llm.md#menu-impostazioni-della-console-2026-10-30)),
e il giudice di attribuzione Claude chiude R29 (vedi [Eval](docs/eval-e-ci.md)).
I numeri di un gate restano quelli del giorno in cui sono stati misurati. Lo stesso stato
è in [`../README.md`](../README.md).

Le pagine sotto `docs/` spiegano *come* operare la console (progetti, reindex, eval,
indice, MCP). Non sono corpus: non vengono indicizzate.

## Indice operativo

| Pagina | Contenuto |
|---|---|
| [Progetti separati](docs/progetti.md) | `Progetti separati` |
| [LLM: layer unico, provider per step](docs/llm.md) | `LLM`; `Menu Impostazioni della console` |
| [Reindex automatico](docs/reindex.md) | `Reindex automatico` |
| [Intake & Import](docs/intake.md) | `Intake & Import` |
| [Eval del retrieval e CI](docs/eval-e-ci.md) | `Eval del retrieval`; `CI` |
| [Benchmark baseline](docs/benchmark.md) | `Benchmark baseline` |
| [Streaming e repliche locali](docs/streaming-repliche.md) | `Streaming e repliche locali opt-in` |
| [Artefatti dell'indice ed embedding](docs/indice-e-embedding.md) | `Artefatti dell'indice`; `Embedding (bge-m3)` |
| [Grafo, drift e code index](docs/grafo-e-code-index.md) | `Check drift (Step 4)`; `Esclusioni dalla scansione del codice generato`; `Estrazione entità`; `Code index` (incluso il ponte `CALLS` frontend→backend) |
| [Agenti, MCP e verifica multi-progetto](docs/agenti-e-mcp.md) | `L'indice come acceleratore per l'agente che scri`; `MCP locale di sola lettura`; `Verifica multi-progetto — 5 ottobre 2026` |

## Perché `rag/docs/` e non `docs/`

`docs/` alla root del progetto (o sotto ogni root registrata) è il **corpus** del Graph-RAG.
Mettere qui la guida operativa la farebbe entrare nel retrieval. Stesso motivo degli
[`adr/`](adr/README.md).

## Ancore stabili

I link storici verso ancore di questo README restano validi: ogni heading sotto punta
alla pagina spezzata corrispondente.

## Progetti separati

→ testo completo: [Progetti separati](docs/progetti.md).

## Embedding (bge-m3): CPU per le query, acceleratore per il reindex

→ testo completo: [Embedding (bge-m3): CPU per le query, acceleratore per il reindex](docs/indice-e-embedding.md#embedding-bge-m3-cpu-per-le-query-acceleratore-per-il-reindex).

### Delta reale isolato

→ testo completo: [Delta reale isolato](docs/benchmark.md#delta-reale-isolato).

## Artefatti dell'indice: formati sicuri, ispezionabili e versionati (blue/green)

→ testo completo: [Artefatti dell'indice: formati sicuri, ispezionabili e versionati (blue/green)](docs/indice-e-embedding.md#artefatti-dellindice-formati-sicuri-ispezionabili-e-versionati-bluegreen).

### Runner dell'agente: Claude, Ollama, Codex, Cursor

→ testo completo: [Runner dell'agente: Claude, Ollama, Codex, Cursor](docs/agenti-e-mcp.md#runner-dellagente-claude-ollama-codex-cursor).

## MCP locale di sola lettura

→ testo completo: [MCP locale di sola lettura](docs/agenti-e-mcp.md#mcp-locale-di-sola-lettura).

