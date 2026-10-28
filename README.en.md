<p align="center">
  <img src="rag/static/vibecraft-logo.svg" width="880" alt="VibeCraft, local Graph RAG">
</p>

<p align="center">
  <em>Cites the rule that applies, not the text that sounds most like your question.</em>
</p>

<p align="center">
  <a href="https://github.com/Silver1V8/VibeCraft/releases"><img src="https://img.shields.io/github/v/release/Silver1V8/VibeCraft?style=flat-square&labelColor=04140a&color=0f3d20&label=release" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-0f3d20?style=flat-square&labelColor=04140a" alt="Apache-2.0 license"></a>
  <img src="https://img.shields.io/badge/python-3.14-0f3d20?style=flat-square&labelColor=04140a" alt="Python 3.14">
  <img src="https://img.shields.io/badge/100%25-local-0f3d20?style=flat-square&labelColor=04140a" alt="100% local">
  <img src="https://img.shields.io/badge/Qdrant%20%C2%B7%20Ollama%20%C2%B7%20BGE--M3-0f3d20?style=flat-square&labelColor=04140a" alt="Qdrant, Ollama, BGE-M3">
  <a href="https://github.com/Silver1V8/VibeCraft/pkgs/container/vibecraft"><img src="https://img.shields.io/badge/image-GHCR-0f3d20?style=flat-square&labelColor=04140a" alt="Image on GHCR"></a>
</p>

<p align="center">
  <img src="assets/readme/hero.en.svg" width="880" alt="Generic RAG versus VibeCraft: a generic RAG cites the methodology note because it is most similar to the question; VibeCraft weighs authority and cites the spec that sets the rule.">
</p>

<p align="center">
  <strong>Adversarial cases right at rank 1: from 0 of 5 to 4 of 5.</strong><br>
  <strong>recall@1 0.690 → 0.741 &middot; recall@10 0.983 → 1.000</strong><br>
  <sub>Same system with authority nearly off (α 0.1) and calibrated (α 0.3), 58-case golden set, 7 September 2026 (S11). Held out, at k=1: +0.038, positive on 5 seeds out of 5. <a href="#numbers">Details</a>.</sub>
</p>

<p align="center">
  <sub><a href="README.md">Italiano</a> &middot; English</sub>
</p>

---

You know it. The methodology note: well written, discursive, full of the right words. It explains the rule better than the document that set it. And that is exactly why an ordinary RAG cites it instead of the rule.

**VibeCraft knows who is in charge.** It is a Graph-RAG console for document governance: it indexes normative documents and the code that should implement them, and when it answers it weighs how authoritative each source is, which one prevails when two contradict each other, and how far to trust the graph path that led there.

Everything runs locally. Your documents never leave the machine.

## Numbers

The golden set contains **adversarial** cases, built on purpose: in each one a low-authority source (a methodology note, an unclassified historical file) is closer to the question than the rule that answers it. Each one is verified by running the query. They are the test a generic RAG fails by design.

| Measured 7 September 2026, 58 cases | recall@1 | recall@2 | recall@5 | recall@10 | adversarial at rank 1 |
|---|---|---|---|---|---|
| Authority nearly off (α 0.1) | 0.690 | 0.862 | 0.948 | 0.983 | **0 of 5** |
| **Authority calibrated (α 0.3), in production** | **0.741** | 0.862 | **0.966** | **1.000** | **4 of 5** |

α was not picked by gut feeling: a joint grid of 2,160 points, 5-fold × 5 seeds, with the winner confirmed held out. And sometimes the measurement said no: full multiplication (α 1), the one the governing rule prescribed, cost 15 points of recall@5. The rule was amended, not the numbers. Full story in [ADR 0002](rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md) (Italian) and in the `authority:` block of [rag_config.yaml](rag/rag_config.yaml).

**Answers are grounded in sources, not guaranteed.** Citations, partial results, and open points still need checking, and retrieval does not promise it found everything the corpus contains.

## How it works

<p align="center">
  <img src="assets/readme/flow.en.svg" width="880" alt="Two flows. /ask: question, hybrid retrieval, ColBERT rerank, authority multiplier, graph with path trust, answer with sources; structural questions go straight to the graph. /pipeline: Explore, Canvas, Propose, Validate, Archive.">
</p>

- **Declared authority.** Every document declares its class and weight in its frontmatter. The weight goes into the ranking formula, not just the UI. Freshness is not authority: a recent date makes nobody win.
- **Precedence.** When two documents contradict each other, the one named by the precedence declaration wins.
- **Path trust.** Every graph edge has a nature (structural, curated, inferred), and a source reached through a fragile path counts for less.
- **The graph answers on its own.** "What relationships does X have", "what is impacted if I change Y": answered from the graph, without calling the LLM.
- **From question to change.** The pipeline takes a change from interview to a spec with Gherkin scenarios. The agent starts in agentic mode only after the current contract has passed validation.

## What's inside

| | |
|---|---|
| **`/ask`** | hybrid retrieval (dense + lexical + ColBERT rerank) re-weighted by authority, plus the code that implements the retrieved sections |
| **Pipeline** | Explore → Canvas → Propose → Validate → Archive, grounded in normative documents; the canvas learns from archived reviews |
| **Intake & Import** | local conversion with preview and staging review: Docling for PDF, Excel read directly, MarkItDown, LibreOffice for DOC/PPT |
| **Maps** | graph map, Semantic Map, and Impact Ripple over the corpus and the indexed code |
| **Projects** | separate projects with their own folders, indexes, and Qdrant namespaces |
| **Agents** | Claude Code and Ollama built in; Codex and Cursor via prompt export and external MCP |
| **MCP** | read-only local server: retrieval, code search, graph queries |
| **Index** | blue/green versions, eval gate before promotion, verified rollback, copy-on-write delta |

## Who it is for, and who it is not for

| It fits if | It does not fit if |
|---|---|
| the corpus is normative and layered, and the answer lives across documents that may contradict each other | the documents are few and everyone already knows them |
| you need a **verifiable** answer, with the source and the weight that made it win | you need a fast conversational assistant |
| data must not leave the machine | an external service is fine |

On `/ask` it keeps a short per-project thread with accumulated citations: it is not a general chatbot. It does not query several projects together and has no per-user permissions. It is meant to run locally or on a controlled network.

## Quick start

With Docker, from the repository root:

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# The API key is required in Docker. If .env already exists, add only the variable.
docker run --rm python:3.14-slim python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

docker compose --profile cpu up -d qdrant ollama
docker compose exec ollama ollama pull qwen3.5:9b      # 6.6 GB, once
docker compose --profile cpu up -d
```

Then open **http://127.0.0.1:8000**. The console asks for the key on first visit and remembers it in that browser.

You do not need your own documents to try it: the initial project already contains a [governance baseline](templates/docs/README.en.md) ready to index.

```bash
docker compose --profile cpu run --rm app-cpu python index.py   # downloads bge-m3, 4.3 GB
```

NVIDIA GPU, Ollama on the host, native install, the ready-made GHCR image, updates, and migrations: **[INSTALL.en.md](INSTALL.en.md)**. If something does not start, `uv run python scripts/doctor.py` from `rag/` checks everything and prints the fix for each problem.

## Requirements, without sugarcoating

| | |
|---|---|
| Download | about **11 GB**: `bge-m3` 4.3 GB + `qwen3.5:9b` 6.6 GB, plus the Docling models for PDF |
| Recommended disk | ~20 GB |
| NVIDIA GPU | optional, but it changes a lot: embedding at 46 chunks/s versus **1 chunk/s** on CPU |
| Full indexing (612 items) | ~13 s with a GPU, **~10 min** on CPU |

Without a GPU everything works. Reindexing becomes something to do calmly, but questions stay usable: query embedding costs about a second, inside the ~30 s the local LLM needs to answer anyway.

## Security

- Listens on **`127.0.0.1`** by default: reachable only from this machine.
- If you expose it on a network, set `VIBECRAFT_API_KEY`: features that only make sense locally switch themselves off, and the key protects the rest.
- `Host` header checked against DNS rebinding, no iframes, Content-Security-Policy with no inline scripts.
- Every HTTP route and MCP tool is mapped in [SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md).

## Documentation

| | |
|---|---|
| [INSTALL.en.md](INSTALL.en.md) | install, projects, updates, scalability, configuration, MCP, and security in detail |
| [Guided walkthrough](rag/static/manuale/percorso-guidato.en.html) | a real case from start to finish, for people deciding whether to adopt it |
| [User manual](rag/static/manuale/manuale-utente.en.html) | the console controls, chapter by chapter |
| [rag/README.en.md](rag/README.en.md) | architecture, retrieval, pipeline, indexing |
| [rag/adr/](rag/adr/README.en.md) | architectural decisions and why |
| [archive/README.en.md](archive/README.en.md) | historical measurement evidence: not the product, and there is a [light clone](INSTALL.en.md#before-cloning) that skips it |
| `/infografica` | with the server running, the query flow illustrated |

## FAQ

**Do my documents leave the machine?**
Not with Ollama. The provider is chosen per step in `rag_config.yaml`: if a step uses Claude, that step's context goes to the provider.

**Does it work without a GPU?**
Yes. Questions stay as fast as the LLM; it is the full reindex that goes from seconds to minutes.

**My documents are badly written. Will it fix them?**
No. VibeCraft makes them findable, not better. Badly written documents, badly written answers.

**Why isn't a normal RAG enough?**
Because in a normative corpus the text that explains a rule uses the same vocabulary as the one that sets it, and it is more discursive. It wins the semantic comparison and loses the one that matters.

**Why Python 3.14?**
Not for the features. On Windows a `>=3.12` lock forks `onnxruntime` and bloats the lockfile. uv downloads 3.14 by itself. Decision in [DISTRIBUTION.md](rag/adr/DISTRIBUTION.md).

**Can I trust the answers blindly?**
No, and be wary of any system that tells you otherwise. Answers carry their sources on purpose: check them.

## License

[Apache-2.0](LICENSE). The model weights downloaded at runtime (`bge-m3`, `qwen3.5`) each have their own license: check it before commercial use.

<sub>Documented status: `main`, 28 October 2026.</sub>
