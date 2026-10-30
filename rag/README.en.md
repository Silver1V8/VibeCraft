[Italiano](README.md) | English

> **Documentation languages.** Italian is canonical. From 2026-10-28 the operational
> detail lives under [`docs/`](docs/) (outside the RAG corpus, same reason as ADRs).
> This English file is a **short index** pointing at the Italian pages — no dual
> maintenance of the body text.

# rag/ — Graph-RAG console

**Documented state: `main`, 30 October 2026.**
Same status note as [`../README.md`](../README.md) / [`README.md`](README.md). New on the
29th: the graph links frontend HTTP calls to backend Minimal API endpoints (`CALLS` edges),
and a full rebuild frees the VRAM held by Ollama before embedding on GPU. New on the 30th: a
**Settings** menu picks LLM models (local, cloud or per activity, including Claude on your
subscription), and the Claude attribution judge closes R29.

Pages under `docs/` explain *how* to operate the console. They are not corpus and
are not indexed.

## Operational index (Italian canonical)

| Page | Topic |
|---|---|
| [Progetti](docs/progetti.md) | Separate projects |
| [LLM](docs/llm.md) | Single LLM layer, providers per step, Settings menu |
| [Reindex](docs/reindex.md) | Automatic reindex |
| [Intake](docs/intake.md) | Intake & Import |
| [Eval & CI](docs/eval-e-ci.md) | Retrieval eval, CI, attribution judge |
| [Benchmark](docs/benchmark.md) | Baseline benchmarks |
| [Streaming & replicas](docs/streaming-repliche.md) | Streaming and local opt-in replicas |
| [Index & embedding](docs/indice-e-embedding.md) | Blue/green artefacts and BGE-M3 |
| [Graph & code index](docs/grafo-e-code-index.md) | Drift, exclusions, entities, languages, frontend→backend `CALLS` |
| [Agents & MCP](docs/agenti-e-mcp.md) | Agent runner, read-only MCP |

## Stable anchors

Historical links into `README.md` still resolve via stubs there; prefer the pages above.

| Legacy anchor (on `README.md`) | Full text |
|---|---|
| `#embedding-bge-m3-…` | [indice-e-embedding.md](docs/indice-e-embedding.md#embedding-bge-m3-cpu-per-le-query-acceleratore-per-il-reindex) |
| `#delta-reale-isolato` | [benchmark.md](docs/benchmark.md#delta-reale-isolato) |
| `#artefatti-dellindice-…` | [indice-e-embedding.md](docs/indice-e-embedding.md#artefatti-dellindice-formati-sicuri-ispezionabili-e-versionati-bluegreen) |
| `#runner-dellagente-…` | [agenti-e-mcp.md](docs/agenti-e-mcp.md#runner-dellagente-claude-ollama-codex-cursor) |
| `#mcp-locale-di-sola-lettura` | [agenti-e-mcp.md](docs/agenti-e-mcp.md#mcp-locale-di-sola-lettura) |

## Why `rag/docs/` and not root `docs/`

Root / project `docs/` is the Graph-RAG **corpus**. Operational guides here would
pollute retrieval — same reason as [`adr/`](adr/README.md).
