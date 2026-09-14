# EVOLUZIONE — piano misurato, non implementazione

## 1. Data, commit e metodo

**Data delle misure e dell'approvazione:** 2026-09-08. **Commit:**
`011e264c554895c651f0eba1dccb74bc4dc10f74`, ramo `main`.
**Stato:** piano presentato in chat e approvato dal manutentore prima della scrittura.
L'approvazione autorizza questo documento e il collegamento in `adr/README.md`;
**non autorizza l'esecuzione degli interventi né risolve le forcelle della sezione 7**.

**Metodo:** lettura del codice e dei registri, comandi locali, risoluzioni uv senza
installazione, interrogazioni di Qdrant/Ollama/FastAPI, eval, pytest, benchmark e
conversioni in memoria. Ogni numero sotto è un output della sessione, un calcolo
esplicitamente descritto, oppure una soglia **proposta** per l'esecuzione futura.
I riferimenti `file:riga` sono relativi alla root del repository e al commit sopra.
Le fonti pubbliche sono state consultate il 2026-09-08 soltanto per metadati di
distribuzione, modelli e prezzi: nessuna richiesta a un provider remoto con il corpus.

Non è stato aperto un branch, eseguito un commit, un push, una PR o un intervento su
GitHub. Non sono stati modificati codice applicativo, dipendenze, configurazione,
corpus o indice. `rag/eval/results/history.jsonl` aveva già tre righe aggiunte rispetto
a git all'inizio: sono rimaste intatte. I report delle misure sono stati mantenuti
nella conversazione e sono registrati qui, senza scritture in `eval/`.

### Ambiente effettivamente misurato

| Voce | Riscontro della sessione | Provenienza |
|---|---|---|
| Sistema | Windows, PowerShell, workspace `C:\Users\Silve\Desktop\vibecraft` | Ambiente della sessione |
| Python | CPython **3.14.6** | `uv run --no-sync python -B scripts/doctor.py` |
| uv | **0.11.28**, build `ebf0f43d7` | `uv --version` |
| GPU | NVIDIA GeForce RTX 3070 Ti, **8192 MiB** | `nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv` |
| RAM | **33.553.300 KiB** visibili, circa 32 GiB; **15.675.668 KiB** liberi nella lettura durante il benchmark | `Get-CimInstance Win32_OperatingSystem` |
| Disco | **200,2 GiB liberi** al preflight | `scripts/doctor.py` |
| Qdrant | **1.18.2**, commit `44ad62f8cd69642be5afa6441612525e24a0d063` | `GET http://127.0.0.1:6333/` |
| Ollama | **0.33.3** | `GET http://127.0.0.1:11434/api/version` |
| Modello installato | Solo **qwen3.5:9b**, Q4_K_M, digest `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7` | `GET /api/tags` su Ollama |
| Finestra Ollama in uso | **16384** | `GET /api/ps`, coerente con `rag/rag_config.yaml` |
| Embedder | `BAAI/bge-m3`, già in cache, CPU nel server | Doctor e log di boot; `rag/api/deps.py:385` |
| torch / onnxruntime | **2.13.0+cu126 / 1.29.0** installati | `importlib.metadata.version` |
| transformers / mcp / typer | **5.15.1 / 2.1.0 / 0.27.1** installati | `importlib.metadata.version` |
| Tag e distanza | `v0.1.0` risolve a `a716f480312dfb833cce519e53c6eb8ec2ace8c4`; **60 commit** fino a HEAD | `git rev-parse 'v0.1.0^{}'`, `git rev-list --count v0.1.0..HEAD` |

Qdrant di VibeCraft e il server erano spenti. È stato avviato il container esistente
`vibecraft-qdrant-1`, sul volume `vibecraft_qdrant_storage`, poi il server locale.
Un altro container chiamato `qdrant`, sul volume `rag-stack_qdrant_storage`, era già
acceso: **non è l'istanza misurata** e non è stato toccato. Alla fine sono stati
arrestati soltanto server e container avviati per le prove; Ollama è rimasto acceso.

### Vincoli confermati e perimetro

- **Python >=3.14, ruff py314**, Apache-2.0 e pin torch: `rag/pyproject.toml:14`,
  `rag/pyproject.toml:36` e relativa configurazione ruff. La decisione su Python resta
  quella di S8; non è stata rieseguita la forcella 3.12. Le condizioni di riapertura
  sono in `rag/adr/AUDIT.md:4144`.
- **8 GiB VRAM:** l'embedder interattivo resta CPU. Nessun modello aggiuntivo viene
  messo sulla GPU senza liberare quello residente (`rag/api/deps.py:385`).
- **Confine locale:** niente corpus a un giudice remoto, come S8 punto 13
  (`rag/adr/AUDIT.md:4173`). Il riuso via MCP e il corpus intero hanno forcelle
  esplicite: l'approvazione del piano non vale come consenso al trasferimento.
- **Un solo manutentore:** niente orchestrazione multi-agent o LlamaIndex; valgono
  i trigger di `rag/adr/0001-multi-agent-scartato.md`.
- **A6 invariata:** non si propone di tracciare il contenuto per-installazione.
  L'aumento dei non tracciati è una misura del corpus, non un difetto da correggere
  (`rag/adr/AUDIT.md:3975`).
- **Nessuna ottimizzazione prima di una baseline salvata**, nessuna calibrazione
  isolata di parametri accoppiati. Negli interventi 1–4 restano **alpha 0.3, tetto
  grafo 3, peso sezione 0.92** (`rag/rag_config.yaml:142`, `:230`, `:231`).

## 2. Fase 0 — verifiche eseguite

### 0.1 — Docling: il comando richiesto non esiste, la catena non è neutra

Output effettivo, da `rag/`:

```text
uv add --dry-run docling
error: unexpected argument '--dry-run' found

Usage: uv.exe add [OPTIONS] <PACKAGES|--requirements <REQUIREMENTS>>
```

**Premessa ritirata:** questa versione di uv non offre `add --dry-run`. Non è stato
usato `uv add` senza il flag: avrebbe modificato il progetto.

Alternativa nativa eseguita, senza installazione:

```text
uv pip install --dry-run -r pyproject.toml docling
Resolved 161 packages in 5.41s
Would download 31 packages
Would uninstall 1 package
Would install 32 packages
```

Versioni candidate: Docling **2.126.0**, docling-core **2.95.0**, docling-ibm-models
**4.0.2**, docling-parse **7.17.0**. Il solo pacchetto già presente sostituito è
`typer 0.27.1 -> 0.26.8`. L'extra per la pipeline VLM è stato verificato separatamente:

```text
uv pip install --dry-run -r pyproject.toml "docling[vlm]"
Resolved 163 packages in 344ms
Would download 33 packages
Would uninstall 1 package
Would install 34 packages
 + antlr4-python3-runtime==4.9.3
 + av==18.1.0
 + colorlog==6.12.0
 + doclang==0.7.3
 + docling==2.126.0
 + docling-core==2.95.0
 + docling-ibm-models==4.0.2
 + docling-parse==7.17.0
 + docling-slim==2.126.0
 + faker==40.38.0
 + filetype==1.2.0
 + jsonref==1.1.0
 + latex2mathml==3.81.1
 + mail-parser==4.6.4
 + marko==2.2.4
 + mpire==2.10.2
 + omegaconf==2.3.1
 + opencv-python==5.0.0.93
 + polyfactory==3.3.0
 + pyclipper==1.4.0
 + pydantic-settings==2.15.0
 + pylatexenc==2.11
 + python-oxmsg==0.0.2
 + qwen-vl-utils==0.0.14
 + rapidocr==3.9.2
 + rtree==1.4.1
 + semchunk==3.2.5
 + shapely==2.1.2
 + tabulate==0.10.0
 + torchvision==0.28.0
 + tree-sitter-c==0.24.2
 + tree-sitter-python==0.25.0
 - typer==0.27.1
 + typer==0.26.8
 + websockets==16.1.1
```

Nel dry-run nativo **torch e onnxruntime non sono sostituiti**. `av` e
`qwen-vl-utils` sono le due aggiunte rispetto a Docling senza extra VLM.
Il lock attuale ha **156 record `package`**, non circa 494. Contiene onnxruntime
1.29.0 e due record torch, 2.13.0 da PyPI e 2.13.0+cu126 dall'indice CUDA,
con marker distinti. Conteggio ottenuto con `tomllib` su `rag/uv.lock`.

#### Verifica cross-platform

Per ogni piattaforma è stata eseguita una risoluzione di controllo e una con
`docling` passato su stdin, senza file di output:

```text
uv pip compile pyproject.toml - --python-version 3.14 --python-platform <piattaforma> --no-header --no-annotate --color never
```

| Piattaforma | Solo progetto | Progetto + Docling | Riscontro |
|---|---:|---:|---|
| x86_64-pc-windows-msvc | 130 pacchetti | 162 | Entrambe risolvono, onnxruntime 1.29.0 |
| x86_64-unknown-linux-gnu | 146 | 178 | Entrambe risolvono, torch 2.13.0+cu126, onnxruntime 1.29.0 |
| aarch64-unknown-linux-gnu | 146 | 178 | Entrambe risolvono, torch 2.13.0+cu126, onnxruntime 1.29.0 |
| aarch64-pc-windows-msvc | Fallisce | Fallisce | torch 2.13.0 senza wheel win_arm64: limite già nella baseline |
| aarch64-apple-darwin, target implicito 13 | Fallisce | Fallisce | wheel torch richiede macOS 14: limite del target del comando |
| x86_64-apple-darwin | Fallisce | Fallisce | torch senza wheel macOS Intel: limite già nella baseline |

Queste sono **risoluzioni fresche**, non un diff del lock. In particolare, il
compile cross-Windows ha stampato `torch==2.13.0`, mentre l'ambiente nativo ha
`2.13.0+cu126`: non certifica l'invariante dei marker CUDA. Non sono installazioni
su sei sistemi e non sono una risoluzione universale del futuro `uv.lock`.

Con `MACOSX_DEPLOYMENT_TARGET=14.0`, progetto + `docling[vlm]` su Apple Silicon
risolve a **168 pacchetti**, con torch 2.13.0, onnxruntime 1.29.0 e Transformers
**5.16.1**. Il vincolo sull'attuale Transformers è stato poi isolato:

```text
# stdin: docling[vlm]==2.126.0 e transformers==5.15.1
uv pip compile pyproject.toml - --python-version 3.14 --python-platform aarch64-apple-darwin --no-header --no-annotate --color never

× No solution found when resolving dependencies:
╰─▶ Because docling-slim[models-vlm-inline]==2.126.0 depends on one of:
        transformers{sys_platform == 'darwin'}>=4.42.0,<5.0.dev0
        transformers{sys_platform == 'darwin'}>=5.4.dev0,<5.9.dev0
        transformers{sys_platform == 'darwin'}>=5.16.dev0
    and docling[vlm]==2.126.0 depends on
    docling-slim[models-vlm-inline]==2.126.0, we can conclude that
    docling[vlm]==2.126.0 depends on one of:
        transformers>=4.42.0,<5.0.dev0
        transformers>=5.4.dev0,<5.9.dev0
        transformers>=5.16.dev0

    And because rag depends on docling[vlm]==2.126.0 and
    transformers==5.15.1, we can conclude that your requirements are
    unsatisfiable.
```

Senza fissare la versione di Docling, lo stesso esperimento con Transformers
5.15.1 risolve scegliendo **Docling 2.96.1 e docling-parse 6.2.0**. Quello sarebbe
un altro esperimento: non vale come compatibilità di Docling 2.126.0.

I metadati PyPI di docling-parse 7.17.0 elencano queste wheel cp314:

```text
docling_parse-7.17.0-cp314-cp314-macosx_14_0_arm64.whl
docling_parse-7.17.0-cp314-cp314-manylinux_2_26_aarch64.manylinux_2_28_aarch64.whl
docling_parse-7.17.0-cp314-cp314-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
docling_parse-7.17.0-cp314-cp314-win_amd64.whl
docling_parse-7.17.0-cp314-cp314-win_arm64.whl
```

Fonte: [PyPI docling-parse 7.17.0](https://pypi.org/project/docling-parse/7.17.0/)
e lettura dei metadati JSON PyPI in sessione. MacOS Intel manca; Windows AMD64,
Linux e Apple Silicon >=14 hanno la wheel del parser. La catena completa resta
da installare e testare nei rispettivi ambienti.

Docling, docling-parse e docling-ibm-models dichiarano MIT nei metadati PyPI;
[Granite Docling](https://huggingface.co/ibm-granite/granite-docling-258M) dichiara
Apache-2.0. Non è stato completato un audit delle licenze delle 33 aggiunte,
dei pesi o delle librerie incluse nei binari: resta un cancello, non un via libera.

### 0.2 — Stato reale e versioni recuperabili

Il primo doctor ha riportato Python, Ollama, cache embedding, GPU e disco disponibili,
ma Qdrant irraggiungibile. Dopo l'avvio del container e del server:

```text
uv run --no-sync python -B index.py --index-status
{
  "indexed": true,
  "stale": true,
  "version": "2026-09-07T15:21:33.161558+00:00",
  "created_at": "2026-09-07T15:21:33.161558+00:00",
  "embedding_model": "BAAI/bge-m3",
  "documents": 248,
  "changed": [
    "+ 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf",
    "+ 02_specs_normative/mockups/catalogo_mockup_normativi.pdf"
  ]
}
```

`--check-integrity` ha segnalato **un problema: indice stale**, due aggiunti,
zero rimossi, zero modificati. I suoi flag erano:

```text
ok=false
stale=true
artifacts_corrupted=false
qdrant_mismatch=false
qdrant_unreachable=false
qdrant_alias.state=aligned
expected=actual=vibecraft_events__v20260907T151549
docs_git.state=instantiated
docs_git.tracked=16
docs_git.untracked: 26 path
```

L'unica istanziazione dichiarata resta `docs/00_meta_governance/safeguards_security.md`.
I 26 non tracciati sono i 24 Markdown locali e i due PDF nuovi. La provenienza
del report enumera il **disco**: la frase dell'eval «+26 NON tracciati (nell'indice,
assenti da git)» non prova che i due PDF siano nell'indice. Il confronto con
`doc_hashes` e `chunks.json` dimostra che sono assenti.

Estratto effettivo di `GET /api/health`:

```json
{
  "status": "degraded",
  "reasons": ["indice stale: 2 file cambiati rispetto al manifest"],
  "snapshot": {
    "loaded": true,
    "version": "v20260907T151549",
    "age_seconds": null,
    "graph_nodes": 931,
    "graph_edges": 1303,
    "chunks": 248
  },
  "dependencies": {"qdrant": true, "ollama": true},
  "last_alert": null,
  "eval": {
    "key": "recall@2",
    "last_recall": 0.8275862068965517,
    "trend": "down",
    "history_points": 47,
    "min_recall": 0.75
  }
}
```

Il valore `eval` proviene dallo storico già presente; la nuova misura indipendente
è in 0.3. Lettura in memoria di manifest e sidecar:

```text
INDEX {"version": "v20260907T151549", "manifest_documents": 248,
       "source_docs": 40, "code_files": 196, "chunks": 248,
       "nodes": 931, "edges": 1303, "symbols": 452}
```

**Il campo `documents` del manifest vale 248, ma i documenti sorgente sono 40.**
Per i conteggi si sono usati rispettivamente `len(doc_hashes)`, `len(chunks.json)`,
nodi/archi di `graph.json`, `len(code.json)` e `len(code_hashes)`.

`core.artifacts.list_versions()` ha restituito cinque versioni. Per tutte è stato
eseguito `assert_rollback_target_has_vectors`, senza cambiare `CURRENT` o alias:

```text
ROLLBACK_PREFLIGHT_OK v20260907T115228
ROLLBACK_PREFLIGHT_OK v20260907T142924
ROLLBACK_PREFLIGHT_OK v20260907T145734
ROLLBACK_PREFLIGHT_OK v20260907T150309
ROLLBACK_PREFLIGHT_OK v20260907T151549
DEFAULT_ROLLBACK_TARGET v20260907T150309
EXPLICIT_REFERENCE_TARGET v20260907T142924
```

Le collection hanno tutte nome `vibecraft_events__<versione>`.
`rollback_shares_collection_with_later_versions(versione)` ha restituito `[]`
per ciascuna. Questa è una verifica delle precondizioni del rollback, **non un
rollback eseguito**. Riferimenti: `rag/core/artifacts.py:176`, `:245`;
`rag/core/indexing.py:456`, `:525`.

### 0.3 — Baseline di retrieval, test e latenza

Le forme `python eval/run.py` e `python eval/run_multihop.py` hanno entrambe fallito:

```text
ModuleNotFoundError: No module named 'core'
```

Sono state quindi eseguite le forme a modulo. `--no-sync` usa l'ambiente già
installato; `-B` evita bytecode nuovo; `--no-save` preserva `eval/`:

```text
uv run --no-sync python -B -m eval.run --no-save
casi: 58 | k=[1, 2, 5, 10]
recall@1       = 70.7%
recall@2       = 82.8%
recall@5       = 94.8%
recall@10      = 100.0%  SATURA
source_in_top3 = 89.7%
mrr            = 0.811
PASS (recall@2 = 0.828, soglia = 0.75)

sottoinsieme avversariale: 5 casi
recall@1 = 80.0%, recall@2/5/10 = 100.0%, mrr = 0.900

uv run --no-sync python -B -m eval.run_multihop --no-save
casi: 14 | k=10 | recall media A = 0.854 | A riusciti = 9/14 | B exact = 6/6
PASS (recall media A >= 0.85, attese strutturali tutte soddisfatte)
```

| Metrica | Riferimento del prompt, v20260907T142924 | Misura su v20260907T151549 | Scarto |
|---|---:|---:|---:|
| Recall@1 | 0.741 | 0.707 | -0.034, due casi su 58 |
| Recall@2 | 0.862 | 0.828 | -0.034, due casi su 58 |
| Recall@5 | 0.966 | 0.948 | -0.018, un caso su 58 |
| Recall@10 | 1.000 | 1.000 | zero, ma metrica satura |
| Multihop A, k=10 | circa 0.890 | 0.854 | circa -0.036 |

**Riscontro, non diagnosi causale:** l'indice e il corpus sono diversi. Non è
dimostrata una regressione del codice; è dimostrato che i riferimenti del prompt
non sono la baseline di questa installazione. Il multihop passa di poco la soglia
0.85 (`rag/rag_config.yaml:517`). Non la si abbassa per far passare una candidata.

Suite eseguita con `PYTHONUTF8=1`, `VIBECRAFT_REQUIRE_QDRANT=1`,
`HF_HUB_OFFLINE=1`, senza cache pytest nel repository:

```text
uv run --no-sync python -B -m pytest -o addopts= -q -p no:cacheprovider

FAILED tests/test_golden_attribution.py::test_archivio_dichiara_di_essere_storico_quando_lo_e
AssertionError: archivio su v20260907T094225, CURRENT è v20260907T151549:
superseded_by dice 'v20260907T142924'

1 failed, 1341 passed in 114.97s (0:01:54)

uv run --no-sync ruff check --no-cache .
All checks passed!
```

**Zero skip.** È scattato il controllo di storicità di
`rag/tests/test_golden_attribution.py:83`; non si dichiara la suite verde perché
il comando ruff successivo è riuscito. Lo scarto rispetto ai 1321–1342 passati
attesi è un fallimento, non un test mancante.

#### Benchmark senza mutazioni dell'indice

Il CLI `scripts/bench.py` chiama sempre `bench_incremental_noop` e salva in
`eval/results/` (`rag/scripts/bench.py:276`, `:289`). Con i due PDF nuovi,
`POST /api/reindex` **non sarebbe un noop**. Sono state chiamate in memoria,
in sequenza e dopo la fine del giudice, le funzioni esistenti `bench_retrieve`,
`bench_ask`, `bench_semantic_map`; nessun monkeypatch del sorgente, nessun report
su disco, nessun full rebuild. L'embedder del server era già caldo e le dieci
domande non erano state inviate prima a `/ask` in quel processo server.

```text
retrieve: n=10, p50_ms=528.65, p95_ms=745.96
ask: n=10, p50_latency_total_ms=21063.67, p95_latency_total_ms=38073.82
     max_latency_total_ms=38203.93
     avg_latency_retrieval_ms=521.45
     avg_latency_generation_ms=22420.95
     avg_latency_total_ms=23245.4
     avg_latency_total_ms_client=23256.58
     wall_s=232.6
GENERATION_P50_MS 20181.21
GENERATION_P95_MS 37267.8605
semantic_map: n=1, latency_ms=294.87, n_points=248, truncated=false
incremental_noop: skipped, indice stale
full_rebuild: skipped, sessione di piano
```

Campioni `/ask`, in ordine dei primi dieci casi del golden set; valori in ms:

| Caso | Retrieval | Generazione | Totale server | Totale client |
|---:|---:|---:|---:|---:|
| 1 | 502.47 | 26417.57 | 27230.62 | 27241.90 |
| 2 | 527.10 | 10710.69 | 11569.54 | 11580.23 |
| 3 | 481.38 | 37439.18 | 38203.93 | 38215.15 |
| 4 | 543.25 | 9427.30 | 10251.46 | 10265.82 |
| 5 | 503.70 | 36491.76 | 37289.10 | 37303.90 |
| 6 | 571.64 | 13944.85 | 14896.73 | 14905.69 |
| 7 | 489.58 | 32076.18 | 32834.53 | 32844.68 |
| 8 | 591.48 | 37058.47 | 37914.80 | 37925.48 |
| 9 | 515.56 | 11623.09 | 12436.04 | 12446.32 |
| 10 | 488.33 | 9020.37 | 9827.23 | 9836.68 |

Con dieci campioni il p95 è vicino al massimo, non una stima della coda sotto
carico. Il p50 di generazione **20.18 s** non supera i 60 s di S8/N1
(`rag/adr/AUDIT.md:4026`). Non si promettono 529 ms per una risposta sintetizzata:
quello è il retrieval, al quale il chiamante MCP aggiungerà la propria inferenza.

### 0.4 — PDF e dimensione del corpus

Enumerazione con lo stesso filtro `DOC_EXTS` del loader: **40 .md, 2 .pdf,
0 .docx, 0 .xlsx**. L'intera cartella contiene anche 15 SVG, un HTML e due
`.gitkeep`: non fanno parte di quel filtro, ma fanno parte del backup integrale.

Lettura con `read_document`, chunking con `chunk_markdown`, confronto dei doc_id
con `chunks.json`; nessuna indicizzazione:

| PDF, relativo a docs/ | Byte | Pagine | Caratteri estratti pypdf | H2 | Chunk loader | Chunk nell'indice |
|---|---:|---:|---:|---:|---:|---:|
| `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` | 4658 | 2 | 1300 | 0 | 1, documento intero | **0** |
| `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` | 5312 | 2 | 1798 | 0 | 1, documento intero | **0** |

Entrambi: metadata `{}`, peso calcolato con `_authority_weight({}) = 0.3`.
Il percorso grezzo è confermato (`rag/core/chunking.py:75`, `:82`, `:160`);
**è ritirata l'affermazione che questi PDF pesino già nel ranking**.
Se si applicasse oggi il chunker a tutte le fonti su disco, produrrebbe 250 chunk:
è un conteggio del loader, non una build né una promozione effettuata.

Le seconde pagine sono state renderizzate **in memoria** con pypdfium2 e
ispezionate visivamente. Il registro diagrammi ha **5 righe dati × 4 colonne**,
quello mockup **11 × 5**: in tutto **75 celle dati e 9 intestazioni**. Questo è
il campione manuale di partenza; non include le tabelle complesse dei benchmark
pubblici e non ne misura la qualità.

`convert_to_markdown` di produzione, inclusa `intake_clean`, è stato chiamato
in memoria sui due PDF:

| Misura MarkItDown | Diagrammi | Mockup |
|---|---:|---:|
| Caratteri Markdown | 1612 | 1722 |
| Heading `##` | 0 | 0 |
| Righe contenenti pipe | 12 | 0 |
| Tabelle complete con righe/colonne della fonte | 0 | 0 |
| Finestre di input per refine | 1 | 1 |

La prima tabella è frammentata: intestazione tabellare seguita da righe miste di
prosa e piccoli frammenti. La seconda è linearizzata. **0/2 tabelle complete non
significa zero testo estratto**. Un esempio dall'output effettivo della prima:

```text
| File | Area | Finalita | Formato / peso |
| ---- | ---- | -------- | -------------- |
diag_0_3_modules_relations_map Architettura Mappa delle relazioni fra i moduli del sistema. SVG
| .svg | | | 46.4 KB |
| ---- | --- | --- | ------- |
```

SHA-256 dei Markdown prodotti in memoria:

```text
diagrammi 292006d5fe0b17ac65fa8045a5c2648986215d3ff3a28051852cba766303971e
mockup    eeb54c8f13334bfe1f9b5ec7be649a10e08d966c67446b4e0dc4732d1d5aa246
```

Anche `refine_markdown(convert_to_markdown(...).markdown, source_filename=...)`
è stato eseguito in memoria, con Ollama locale, dopo il benchmark:

```text
diagrammi: {"windows": 1, "windows_kept_raw": 0, "windows_too_short": 0,
            "windows_too_long": 0, "chars_in": 1612, "chars_out": 1355,
            "elapsed_seconds": 8.1}
mockup:    {"windows": 1, "windows_kept_raw": 0, "windows_too_short": 0,
            "windows_too_long": 0, "chars_in": 1722, "chars_out": 2601,
            "elapsed_seconds": 15.0}
```

**0/2 finestre scartate** è una baseline della forbice, non una certificazione
di assenza di congetture: la condizione è sulla lunghezza
(`rag/core/intake_refine.py:337`). Non è stata fatta una validazione cella-per-cella
del testo raffinato. Il journal di staging aveva zero record; le prove non lo
hanno popolato. I tre golden YAML esistenti contengono zero riferimenti `.pdf`:
non esiste una misura di recall specifica di questi PDF da riusare.

#### Corpus intero: conteggio e stima, separati

Metodo: per ciascuna fonte ammessa da `DOC_EXTS`, `read_document`; somma dei
caratteri dei corpi. Per i Markdown, seconda somma includendo il frontmatter;
per i PDF si usa il testo estratto, non i byte binari. Output:

```text
body_chars=365865
full_document_chars=412530
body_tokens_len_div3=121955
full_tokens_len_div3=137510
source_h2=209
predicted_chunks=250
indexed_chunk_chars=377414
indexed_chunk_tokens_len_div3=125804
```

Il testo dei chunk indicizzati ripete intestazioni e non contiene i PDF; non è
un'altra misura del medesimo payload. `len(prompt)//3` è l'euristica effettiva
del guardrail (`rag/core/llm.py:73`), **non il tokenizer di Claude**. Il conteggio
Claude del futuro payload completo, inclusi etichette, prompt e strumenti, non
è stato ottenuto: inviarlo all'endpoint remoto violerebbe il confine non ancora
autorizzato. La skill `claude-api`, richiesta nel prompt, non è stata trovata
fra le skill locali; sono state consultate le fonti ufficiali in sostituzione.

### 0.5 — Attribuzione: S14 si riproduce

```text
uv run --no-sync python -B -u -m eval.attribution --repeats 3 --no-save

giudice: ollama/qwen3.5:9b
archivio: golden_attribution.yaml
indice v20260907T094225, SUPERATO da v20260907T142924

accordo col verdetto umano : 20/24   positivi 15/17   NEGATIVI 5/7
ripetibilità (3 giudizi/record): unanimi 24/24
accordo BINARIO (corretta/sbagliata): 22/24
falsi allarmi 2/17   negativi mancati 0/7
il giudice NON concorda su ogni record: non è pronto (criterio S6)
```

Exit 1 del criterio di qualità, non indisponibilità dell'harness. Stessi quattro
disaccordi: `attr-05-remote-inference run 2`, `attr-07-subtitle-heading run 2`,
`attr-07-subtitle-heading run 3`, `attr-08-name-substitution run 2`.

Sono **72 giudizi su 24 record storici**, non 24 risposte nuove del server. Il
risultato in-sample non diventa una misura dell'attribuzione su v20260907T151549.
La provenienza obsoleta stampata dall'archivio è proprio il problema visto dalla
suite. R29 resta condizionato: `/api/tags` mostra un solo modello, quindi il
trigger «secondo modello installato» di `rag/adr/AUDIT.md:4189` non è scattato.

### 0.6 — Premesse ritirate e limiti della verifica

| Premessa del prompt | Riscontro e conseguenza |
|---|---|
| Il riferimento v20260907T142924 descrive l'installazione corrente | CURRENT è v20260907T151549, corpus e recall diversi: si salva questa baseline e si riallinea prima del confronto |
| Circa 180 chunk e nove documenti locali | 248 chunk indicizzati; 26 fonti su disco non tracciate; A6 non cambia |
| Circa 494 pacchetti nel lock | 156 record package; le aggiunte VLM native sono 33 più una sostituzione |
| `uv add --dry-run` è disponibile | Non supportato in uv 0.11.28; usati pip dry-run e compile, dichiarandone i limiti |
| I PDF entrano già nel ranking come un chunk | Il loader lo farebbe, ma entrambi sono ancora fuori indice |
| Refine diventerà opzionale grazie a Docling | È già opt-in: `rag/core/intake_convert.py:126`, `rag/templates/intake.unified.html:504` |
| Finestre non scartate equivalgono a riscrittura corretta | Il test di lunghezza non prova la correttezza; servono confronto con la fonte e controllo umano |
| `--check-graph` è economico e zero embedding | `rag/core/indexing.py:2042` ri-embedda il corpus per il grafo di riferimento; comando avviato e interrotto, nessun verdetto |
| Il benchmark incrementale è sempre noop | Due PDF aggiunti renderebbero reale il delta: non eseguito |
| MCP rende immediatamente disponibile il testo di `/api/retrieve` | La route restituisce ranking e metadati, senza testo né versione top-level (`rag/api/routes_retrieval.py:600`, `rag/core/retrieval.py:387`) |
| Non esiste MCP nel progetto in nessuna forma | Nessun server applicativo trovato con la ricerca `docling|granite|fastmcp|mcp.server` nei sorgenti; l'SDK mcp 2.1.0 è però già una transitiva di claude-agent-sdk nel lock |

Non sono stati eseguiti: installazione Docling, audit completo licenze transitive,
smoke nativo Linux/macOS, CI GitHub, build container CPU, calibrazione S11,
rollback reale, backup esterno, nuovo giudice, conteggio token remoto, notturno
con remediation. Non sono prerequisiti dichiarati superati per il solo fatto
che esista il comando. La suite locale e il controllo economico d'integrità
sono stati invece eseguiti, con gli esiti negativi espliciti sopra.

## 3. Verdetto

L'architettura locale e il giudice come schermo reggono alle prove; la baseline
del prompt non descrive più l'installazione. Prima degli interventi servono
un corpus/indice coerente e il riallineamento della dichiarazione storica
dell'archivio: oggi integrità e suite non sono verdi. Docling resta adottabile
dietro i cancelli di qualità e dipendenze, con un conflitto VLM/Transformers
misurato su macOS. MCP evita la sintesi locale, ma richiede testo e provenienza
espliciti; non fa scattare N1 se non espone `/ask`.

## 4. Il piano

**Ordine approvato:** prerequisiti -> R.0 -> 1 -> 2 -> 5 -> 7.
R29 (4) e corpus intero (3) sono rami condizionati: non bloccano gli altri
interventi mentre manca il modello o l'autorizzazione. L'intervento 6 non è una
voce autonoma. Nessuna dipendenza tecnica impone di installare un giudice o
trasferire dati per poter eseguire il test di scala.

Sforzi **stimati**, non cronometrazioni: **S** circa una giornata; **M** 2–3;
**L** 4–8. Sono esclusi download, attese native e batch lunghi. Ogni intervento
si esegue su un branch aperto dal manutentore, con la propria baseline nominata.
Le soglie sotto sono criteri proposti e approvati per il piano, non risultati
già ottenuti. Un `NON_APPLICARE` conserva misura, configurazione e ragione.

### P0 — Una baseline coerente prima di cambiare il sistema

**Sforzo S. Dipendenze:** backup R.0 prima di qualunque riallineamento del corpus.
**Rete attiva:** stato git preservato, hash, cinque versioni e precheck R.2;
nessuna ricalibrazione.

**Perimetro:** dichiarazione `summary.superseded_by` in
`rag/eval/golden_attribution.yaml`, controllata da
`rag/tests/test_golden_attribution.py:83`; comandi esistenti di index ed eval.
Questa è attività dell'esecuzione futura: nessuna di queste righe è stata
modificata per scrivere il piano.

- [ ] Dopo il backup, rendere esplicito l'ingresso dei due PDF mediante il percorso
  attuale e un **full rebuild**, con gate bloccante. Non usare un incrementale.
- [ ] Aggiornare la sola dichiarazione di storicità alla versione effettiva dopo
  l'esito della promozione. Conservare record, risposte e `index_version` originale:
  aggiornare un'etichetta non riproduce l'archivio.
- [ ] Salvare versione/collection, hash delle fonti e della configurazione, runtime,
  risultati di integrità, suite, recall, multihop e benchmark.
- [ ] Separare la baseline dei 40 documenti indicizzati qui dalla nuova baseline
  delle fonti riallineate. Non attribuire a Docling il miglioramento ottenuto
  soltanto rendendo recuperabile una fonte prima assente.

**Chiusura:** indice non stale, suite senza fallimenti né skip con Qdrant,
baseline salvata, soglie esistenti rispettate. Se il full rebuild non viene
promosso, CURRENT resta quello verificato qui e il prerequisito resta aperto.
**Abbandono/sospensione:** gate fallito o confronto non riproducibile; prima si
registra e si diagnostica, senza abbassare soglie o cambiare pesi.
**Costo nascosto:** la revisione dell'archivio resta umana e storica; il contenuto
per-installazione non diventa distribuibile per averlo descritto nei risultati.
**Ritorno:** R.2 per indice, R.1 per documentazione. **Riapertura:** nuova
promozione o modifica del corpus prima che inizi l'intervento seguente.

### 1 — Docling nell'intake e nel loader PDF

**Sforzo L. Dipendenze:** P0, backup verificato R.0, scelta di compatibilità macOS
in sezione 7 prima di modificare la catena dell'applicazione.
**Rete attiva:** R.0 + branch R.1 + lock R.3 + configurazione R.4; collection
candidata distinta e gate R.2 quando si prova il retrieval.

**Perimetro previsto:**

| File e punto | Modifica futura |
|---|---|
| `rag/core/intake_convert.py:41`, `:82` | Conservare `ConversionResult(markdown, metadata)`; selezione del motore e fallback dichiarato |
| `rag/core/chunking.py:75`, `:82` | Rendere selezionabile la conversione dei PDF del percorso diretto, riusando il convertitore |
| `rag/core/intake_refine.py:337` | Riusare statistiche e confronto delle finestre; nessuna nuova riscrittura obbligatoria |
| `rag/core/intake.py:422`, `:450`, `:470` | Verificare collisioni anche all'interno del lock prima della scrittura; conservare rifiuto e rollback su errore |
| `rag/rag_config.yaml:541`, `rag/core/config.py` | Selettori dei motori, caricamento dei valori, log della scelta |
| `rag/pyproject.toml:14`, `rag/uv.lock` | Solo catena accettata dal preflight e dall'audit licenze |
| `rag/tests/test_intake_convert.py`, `rag/tests/test_torch_platform_pin.py` | Conversione/fallback e invarianti di piattaforma; casi del loader e delle collisioni nei rispettivi test |

**Forma minima:** Docling è il secondo motore; MarkItDown resta disponibile.
Granite gira localmente su **CPU** nel primo esperimento. Il peso di 258M parametri
non è una misura di VRAM in esecuzione: memoria, tempo di caricamento e conversione
vanno registrati. La documentazione distingue la pipeline VLM dai modelli delle
altre pipeline: [Docling Vision Models](https://docling-project.github.io/docling/usage/vision_models/).
Non scambiare un risultato della pipeline standard/TableFormer per una misura di
Granite. Registrare pipeline, revisioni dei pesi, opzioni e versioni.

La conversione modifica la struttura del testo, **non la sua autorità**. I PDF
letti direttamente mantengono metadata assenti e peso 0.3 finché manca una
dichiarazione umana. La governance passa dall'approvazione intake; non si assegna
un peso normativo in base al formato o alla cartella. Non produrre automaticamente
una copia Markdown accanto al PDF creando due fonti indicizzate equivalenti.

#### 1c — Cancello prima dell'integrazione applicativa

Il primo campione è l'intero perimetro PDF attuale: **due cataloghi, quattro
pagine, due tabelle**. Prima del confronto si congelano copie locali, SHA-256,
trascrizione delle celle e segmentazione attesa. La preparazione delle fixture e
l'esperimento isolato precedono il codice che integra Docling nell'app.

| Misura | Baseline ottenuta | Criterio di chiusura proposto |
|---|---|---|
| Tabelle complete | 0/2 con MarkItDown | **2/2**, righe e colonne corrette |
| Celle | 75 celle dati, 9 intestazioni verificate sulle pagine | **75/75 dati e 9/9 intestazioni corretti**, nessun valore inventato; normalizzazioni degli a-capo dichiarate prima |
| Sezioni | 0 heading H2 in entrambi gli output | H2 corrispondenti alla segmentazione umana preregistrata sulle pagine; nessun titolo inventato; numero per documento registrato |
| Refine | 0/2 finestre scartate, una sola corsa | Ripetere sugli output candidati e registrare troppo corte/lunghe, anche se zero; non usarlo come surrogato della fedeltà |
| Retrieval PDF | Nessun caso PDF nel golden, PDF assenti dall'indice attuale | Almeno **8 domande**, quattro per PDF, con la stessa presenza delle fonti in baseline e candidata, senza perdite sulle attese fissate |
| Retrieval generale | P0 deve fissare il riferimento coerente | Nessuna perdita sul golden esistente rispetto a P0; gate invariati |
| Attribuzione | Schermo disponibile, non metrica autonoma | Stesse domande e modello di risposta; schermo più lettura umana, nessuna nuova attribuzione errata nel campione verificato |

Le attese PDF sono un **supplemento locale**, fuori dal golden condiviso, con fonti
identificate da hash. Inserire in `eval/golden_set.yaml` documenti non tracciati
come attesi farebbe scattare il trigger A6 (`rag/adr/AUDIT.md:4013`): non è la
soluzione prevista. Non si propone di committare i cataloghi per aggirarlo.

**1d, riscontro ritirato:** refine è già facoltativo. Il premio verificabile è
ottenere il parsing richiesto **senza ricorrervi**, mantenendolo come azione
esplicita. La prima misura della forbice, zero scarti, dimostra proprio perché
contare gli scarti da solo non basta.

**Criterio di abbandono:** `NON_APPLICARE` se falliscono struttura/celle,
compaiono valori inventati, peggiorano retrieval o attribuzione, oppure la
catena non supera licenze, suite e piattaforme. Fermare l'integrazione diretta
se cambia torch o si rompono i marker CUDA. Il conflitto Transformers/macOS
non si risolve abbassando Python: aggiornamento controllato solo con la scelta
esplicita della sezione 7, altrimenti **valutazione di intake in container
separato**. Questa alternativa richiede misure proprie prima di essere adottata.

**Costo nascosto:** 33 aggiunte native con VLM, typer sostituito, possibile
variazione Transformers, test delle operazioni torchvision oltre al solo import,
licenze di PyAV e delle librerie nei binari, cache dei modelli, CPU, review del
testo e manutenzione di due motori. Il MIT del pacchetto principale non certifica
la catena. Baseline, fallback ed errori devono registrare il motore effettivo.

**Interruttori proposti, non ancora presenti:** `intake.conversion_engine:
"markitdown"` spegne Docling nell'intake; `retrieval.pdf_conversion_engine: ""`
mantiene il loader PDF storico. Riavvio dei processi che leggono la configurazione,
nessuna reindicizzazione per disattivare l'uso futuro. **Non annullano** testo
già scritto o un indice costruito con altro parsing: per quelli R.0/R.2.

**Condizione di riapertura:** nuovo layout/formato PDF, revisione di parser/pesi,
oppure superamento misurato del cancello che ha prodotto `NON_APPLICARE`.
Il risultato sui due cataloghi non autorizza una dichiarazione generale sulle
tabelle complesse né rende vere le percentuali di benchmark citate nel prompt.

### 2 — MCP locale, tre tool di sola lettura

**Sforzo M. Dipendenze:** baseline coerente P0; nessuna dipendenza tecnica da
Docling. **Rete attiva:** branch R.1, suite, hash configurazione R.4; R.2 resta
disponibile, ma l'adattatore non scrive l'indice.

**Perimetro:** nuovo `rag/mcp_server.py`; dichiarazione diretta dell'SDK MCP in
`rag/pyproject.toml` se usato; `rag/api/routes_retrieval.py:600`, `:685`;
`rag/api/routes_graph.py:68`; `rag/SECURITY_SURFACE.md`; nuovo test dell'adattatore
e test dei contratti HTTP. L'SDK 2.1.0 è già installato transitivamente, non un
server VibeCraft esistente.

Tre tool con nomi espliciti: retrieval documentale, ricerca dei simboli di codice,
query del grafo. **stdio** per il client locale; adattatore sottile verso gli
endpoint HTTP su loopback, senza secondo embedder, accesso Qdrant diretto o
duplicazione del ranking. La scelta stdio è coerente con il trasporto locale
della [specifica MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).

**Parte che manca:** `/api/retrieve` dà doc_id/chunk_id, classe, autorità e punteggi,
ma non il corpo né `index_version` top-level. Aggiungere un'opzione per testo
limitato e troncamento dichiarato, più la versione dello **stesso snapshot** usato
per il ranking. Default compatibile con l'eval corrente. Etichette costruite con
`source_label`, ordine e precedenze conservati; niente riordino nell'adattatore.
Risultati del grafo troppo grandi richiedono limiti espliciti, non tagli silenziosi
che trasformino un elenco parziale in una risposta di assenza.

**Sicurezza:** sola lettura effettiva, non soltanto annotazione `readOnlyHint`.
Niente tool di scrittura, shell, intake, reindex, `/ask` o bridge agentico.
URL backend fissato/validato come locale, non fornibile come argomento del tool.
Credenziali ereditate dall'ambiente, mai nel testo dei tool o nei log. Conservare
`require_api_key` per le route lette; nessuna modifica o aggiramento di
`require_api_key_strict` (`rag/api/deps.py:62`, `:72`). L'autenticazione locale
stdio è il confine di processo/utente, non un nuovo endpoint pubblico.

`agent_bridge.py` ha tre modalità di fiducia e il confinamento PreToolUse
(`rag/agent_bridge.py:12`, `:147`), ma non va incorporato nell'adattatore.
La superficie HTTP corrente dichiara 57 route; `SECURITY_SURFACE.md` va aggiornato
per testo opzionale e accesso MCP anche se stdio non aggiunge una porta HTTP.
Il riepilogo di sicurezza deve distinguere il numero delle route dalle superfici
non HTTP, senza gonfiare o nascondere il conteggio.

**Chiusura:** stessi identificatori e ordinamento di HTTP, testo e versione
coerenti, zero chiamate Ollama, zero mutazioni, input invalidi rifiutati, errori
backend comprensibili, credenziali assenti dalle risposte. **Overhead MCP p95
<=100 ms**, soglia proposta su 30 chiamate abbinate HTTP/MCP, stessa macchina e
stesso indice. Il limite non è una nuova promessa di latenza della sintesi.

**Abbandono:** richiede duplicare il core, altera autorità/precedenze, espone
scritture, perde provenienza o non rispetta il budget misurato dell'adattatore.
**Costo nascosto:** testo e limiti d'output sono contratto pubblico, test del
trasporto e su Windows, dipendenza MCP resa esplicita, aggiornamento sicurezza.

**Spegnimento:** adattatore disabilitato/non avviato; eventuale flag proposto
`mcp.enabled: 0`. Nessun rebuild. **Riapertura:** secondo trasporto/client che
richiede una superficie diversa o necessità dimostrata di nuovi tool.

**N1:** non si riapre per questo perimetro: il trigger è un secondo consumatore
di `/ask`, non un client di `/api/retrieve`. Se in futuro si aggiunge `/ask`,
N1 va rivalutata esplicitamente, senza implementare streaming in coda al lavoro.
Il p50 di generazione qui misurato è sotto 60 s. L'LLM locale esce dal percorso
documentale MCP: rimane retrieval ~529 ms p50 **più la sintesi del chiamante**.
Se quel chiamante è remoto, anche gli estratti attraversano il confine: forcella
separata nella sezione 7, nessuna autorizzazione implicita.

### 4 — R29: giudice diverso dal giudicato, solo al trigger

**Sforzo M. Dipendenze:** un secondo modello installato; prompt e archivio
congelati; record nuovi etichettati da un umano. **Rete attiva:** R.4 per override
del giudice, hash del dataset e del prompt; nessuna promozione necessaria per
validare l'archivio. R29 è chiusa come decisione, non riaperta da questo piano.

**Perimetro futuro:** override `llm_settings.purposes.judge` nella configurazione;
`rag/eval/attribution.py:261`, `:365`, `:428` e un insieme locale di validazione
separato. Nessuna nuova taratura del prompt sui 24 record di S12.

Il prossimo tentativo resta **qwen3.5:27b locale**, come S8. La
[scheda Ollama](https://ollama.com/library/qwen3.5:27b) consultata riporta
27.8B, Q4_K_M, circa **17 GB**: non risiede integralmente negli 8 GiB della GPU.
La RAM disponibile rende necessario misurare la configurazione reale, non
dedurre il throughput dal numero dei parametri. Liberare il 9b dalla GPU;
nella validazione offline arrestare il server/embedder quando non necessari.
Nessun terzo modello residente, nessun download effettuato in questa sessione.

**Protocollo e costo:** 24 record × 3 giudizi = **72 chiamate** per il riferimento
storico. Aggiungere **24 record mai usati nella taratura**, almeno **8 negativi**,
con etichette umane fissate prima di vedere il giudice: altre 72, **144 totali**.
Registrare digest, quantizzazione, temperatura, contesto, tempo e memoria.
Il runtime del 27b è **non misurato**: eseguire prima un pilot cronometato e
calcolare `tempo_caricamento + numero_giudizi * tempo_medio_osservato`, dichiarando
l'incertezza della stima. Il budget massimo del batch va concordato prima di
eseguirlo; nessuna spesa API, energia e occupazione della macchina non sono zero.

**Chiusura proposta:** migliorare 20/24 e ottenere negativi storici 7/7; sul nuovo
insieme, accordo completo e unanimità per dichiarare superato il criterio rigoroso
S6. Un guadagno parziale resta uno schermo: non si promuove a metrica automatica
per il solo fatto di essere migliore del 9b. Poi si usa il modo live per le
promozioni che toccano corpus/ranking, distinguendolo dalla validazione del giudice.

**Abbandono:** regressione, negativi mancati, instabilità o costo oltre il budget
preregistrato. Conservare risultato e limitazioni; nessun provider remoto come
fallback automatico. **Costo nascosto:** costruzione dei negativi, lettura umana,
RAM/CPU e indisponibilità temporanea dell'inferenza interattiva.
**Spegnimento:** rimuovere/svuotare l'override judge per tornare al riferimento,
senza reindicizzare. **Riapertura:** nuovo modello o nuovo insieme di validazione;
il trigger iniziale non è scattato oggi (`rag/adr/AUDIT.md:4189`).

### 3 — Corpus intero, sospeso sul confine dei dati

**Sforzo M. Dipendenze:** decisione esplicita della sezione 7, baseline P0,
campione di attribuzione umano separato. **Rete attiva:** R.4, budget e limite
finestra prima della chiamata; corpus e indice non vengono riscritti.

**Perimetro futuro:** `rag/core/router.py:62`, `rag/core/retrieval.py:154`, `:170`,
`:866`; ramo di risposta in `rag/api/routes_retrieval.py`; configurazione e test
di selezione, prompt e budget. La strategia usa una versione coerente del corpus,
una sola copia del contenuto per fonte, etichette della scala di autorità
esistente e precedenze esplicite. Non basta concatenare testo e sperare che il
modello deduca la gerarchia dalla prosa; è il riscontro A3 documentato dal codice.

**Calcolo attuale:** 365.865 caratteri di corpo, 412.530 includendo frontmatter
Markdown; **121.955–137.510 token secondo l'euristica caratteri/3**, non un
intervallo statistico né il conteggio Claude. La finestra Ollama configurata a
16.384 non basta con questa stima. Non si cambia `num_ctx` per farla entrare
senza un nuovo esperimento hardware.

La documentazione ufficiale consultata l'8 settembre dichiara per **Sonnet 5**
1M token di contesto, $2/M input e $10/M output. Scenario illustrativo:
137.510 token input e 2.000 output = **$0,29502 senza cache**, escluso l'overhead
aggiuntivo. Con lo stesso input cacheabile, $0,363775 alla scrittura cache di 5
minuti e $0,047502 su cache hit, sempre con 2.000 output. Sono **calcoli su una
stima di token**, non costi misurati né budget approvati. Il payload reale deve
comprendere prompt, etichette, strumenti, domanda e spazio di risposta.
Fonti: [modelli](https://platform.claude.com/docs/en/models/overview),
[prezzi](https://platform.claude.com/docs/en/about-claude/pricing).

Il [conteggio token ufficiale](https://platform.claude.com/docs/en/build-with-claude/token-counting)
dipende dal modello e richiede l'invio del payload: non è stato invocato.
La selezione della strategia resta spenta finché manca il consenso, anche se
la finestra pubblicizzata è sufficiente. Prezzi e finestre si riverificano alla
data di esecuzione, senza riusare questi numeri come listino permanente.

**Chiusura:** dopo il consenso, contare il payload reale e lasciare margine per
risposta/overhead; confrontare corpus intero e retrieval con **lo stesso modello
di sintesi**, domande e corpus, così il cambio di modello non diventa il merito
della strategia. Preservare etichette/precedenze; nessuna regressione d'attribuzione
sul set umano separato; beneficio osservabile e costo entro un tetto concordato.

**Abbandono:** confine non autorizzato, limite di spesa o finestra superati,
nessun vantaggio misurabile oppure attribuzione peggiore. **Costo nascosto:**
trasferimento del corpus, token ripetuti, cache invalidata dai cambi, revisione
della sicurezza, conteggio per modello e confronto umano.
**Spegnimento proposto:** `retrieval.full_corpus_max_tokens: 0`, con riavvio,
senza reindicizzare. **Riapertura:** consenso esplicito oppure disponibilità
locale di una finestra utile e di hardware verificati. Il diniego al giudice
remoto non viene aggirato chiamando lo stesso trasferimento «strategia».

### 5 — Scala: arbitrato a 10.000 chunk

**Sforzo L. Dipendenze:** baseline P0, corpus sperimentale separato e verificato.
**Rete attiva:** R.1/R.4, namespace Qdrant e artefatti dell'esperimento separati
dalla produzione, nessuna promozione automatica né candidato collegato all'alias
produttivo. Proteggere le versioni R.2 dalla retention prima dei batch.

**Perimetro futuro:** harness isolato sotto `rag/eval/`;
`rag/eval/calibrate_authority.py:78` e `rag/eval/calibrate_graph_context.py:1`;
configurazione soltanto dopo esito positivo e decisione del manutentore.

Scala di riferimento **248 -> 1.000 -> 10.000 chunk**. Dopo P0 registrare anche
il numero effettivo della nuova baseline: 248 è quello misurato oggi, non un
vincolo che impone di rimuovere fonti dal corpus riallineato. Aggiungere
distrattori pertinenti, restatement e fonti in conflitto con autorità dichiarate;
non moltiplicare copie identiche per ottenere soltanto un numero di punti.

**Protocollo:** congelare corpus, seed e domande; separare per famiglie di fonti
e conflitti, evitando parafrasi della stessa famiglia fra training e held-out.
Ripetere i quattro assi S11 (9 alpha × 6 default × 5 unclassified × 8 pesi di
sezione = **2160 punti**) con **5-fold × 5 seed**, k=1/2/5 e validazione separata.
Conservare l'incumbent nei pareggi, come il calibratore corrente. Misurare
separatamente il taglio del contesto grafo **associato** alla candidata.

**Precisazione del riferimento:** `graph_context_max_chunks` non è un asse
della griglia a 2160 punti; S11 lo ha verificato col proprio harness, dopo il
cambio di alpha (`rag/eval/calibrate_authority.py:23`,
`rag/adr/AUDIT.md:3305`). Nessuna calibrazione isolata di alpha/peso sezione.

Registrare recall e conflitti anche **prima** del reranking: la fonte scartata
dal recupero dei candidati non viene salvata da alpha. `FETCH_CANDIDATES=50`
nel calibratore è un limite da osservare, non da allargare silenziosamente
durante il confronto. Cronometrare raccolta candidati, griglia, memoria e
occupazione delle collection; separare costo embedding da costo della CV.

**Chiusura proposta:** guadagno held-out **>=0,015**, positivo su tutti i seed,
nessuna perdita ai k superiori né nei conflitti normativi del set separato;
report leggibile anche se il sistema non tiene la scala. Mantenere l'allarme
di saturazione: un k saturo non è prova di stabilità dell'arbitrato.

**Abbandono:** leakage, metriche sature, beneficio instabile, guadagno solo
in-sample o peggioramento dell'attribuzione. Scrivere `NON_APPLICARE`, con
distribuzione e limiti; non alzare alpha per salvare il risultato.
**Costo nascosto:** generazione/revisione del sintetico, CPU/GPU di embedding,
spazio e più corpus da mantenere. Il sintetico non certifica ogni corpus reale.
**Spegnimento:** esperimento separato non avviato; produzione invariata. Se una
configurazione viene adottata, ripristino **dell'intera tupla baseline**, riavvio,
nessuna reindicizzazione per i soli pesi; R.2 se si è anche cambiato corpus/indice.
**Riapertura:** crescita reale, nuova distribuzione dei conflitti o nuova
evidenza che supera il cancello fallito. Multi-utente non è un obiettivo.

### 6 — Latenza: nessuna voce autonoma

**Non pianificata.** MCP senza `/ask` non apre il trigger «secondo client»;
il p50 di generazione misurato è **20,18 s**, non oltre 60 s. Anche rinunciando
a MCP, queste misure non autorizzano a riaprire N1 come ottimizzazione generica.
**Riapertura:** una delle due condizioni scritte in `rag/adr/AUDIT.md:4026`.
Alla riapertura si salva una nuova baseline e si rivaluta la decisione;
streaming non equivale automaticamente a meno tempo di generazione.

### 7 — Schema di governance come specifica pubblicabile

**Sforzo M. Dipendenze:** nessuna dipendenza tecnica dagli esperimenti di scala;
è posto dopo nella sequenza di lavoro approvata. **Rete attiva:** branch R.1,
test di conformità isolati, validatore opt-in, nessuna reindicizzazione.

**Perimetro proposto:** `rag/spec/governance/1.0.0.md`, schema macchina accanto
alla specifica, `rag/scripts/validate_governance.py`, relativo test di conformità.
Sono file dell'esecuzione futura, non creati da questa sessione.
Fonti del contratto: `docs/00_meta_governance/policy_versionamento_documentale.md:85`,
`rag/core/chunking.py:13`, `:200`, `rag/core/retrieval.py:59`, `:106`, `:736`.

Descrivere `authority`, `classification`, status, alias e archi `graph_rag.edges`,
compreso `SUPERA_IN_PRIORITÀ`, senza introdurre una scala alternativa. Distinguere
**conformità normativa** e **tolleranza del loader corrente**: il fallback su un
valore invalido non significa che il valore sia conforme. Documentare il
trattamento dei target simbolici e dei cicli in accordo con il codice, non
inventare divieti o garanzie che il sistema non verifica.

SemVer: major per incompatibilità, minor per estensioni compatibili, patch per
chiarimenti senza nuova semantica. Il validatore seleziona esplicitamente la
versione; un corpus terzo non deve importare dati o servizi di VibeCraft.
Riusare YAML/Pydantic/NetworkX già disponibili; evitare una nuova dipendenza
per una capacità già presente. Eseguire controlli sintattici, valori ammessi,
identificatori e relazioni con errori `file/campo/motivo`, senza Ollama o Qdrant.

**Chiusura:** corpus dimostrativo indipendente, casi conformi e non conformi
verificati, exit nonzero sulle violazioni, istruzioni d'adozione riproducibili;
nessuna regola chiamata «garantita» senza un controllo corrispondente. Non
includere l'istanza locale di safeguards né altre fonti per-installazione.

**Abbandono:** la specifica richiede di esporre il corpus locale, oppure presenta
comportamenti desiderati come se fossero implementati. In quel caso restringere
il contratto al verificato, registrando esplicitamente il limite.
**Costo nascosto:** compatibilità fra versioni, fixture, documentazione delle
eccezioni e distinzione fra schema statico e controlli semantici sul corpus.
**Spegnimento:** validatore non invocato/opt-in; nessun impatto sull'indice.
**Riapertura:** modifica incompatibile del contratto oppure primo corpus terzo
non rappresentabile. «Pubblicabile» non autorizza una pubblicazione remota.

## 5. Fase R — rollback per livello

### R.0 — Prima di tutto, il corpus che git non può recuperare

**Precondizione obbligatoria dell'intervento 1 e di P0:** copia integrale di
`docs/` fuori dal repository, con data e verifica di inventario/SHA-256, inclusi
SVG/HTML e ogni fonte non tracciata. I non tracciati sono **26 oggi**; il backup
deve seguire il filesystem effettivo, non il numero scritto nel prompt.

Comandi **prescritti per l'esecuzione**, dalla root; non eseguiti in questa
sessione perché l'unico nuovo file autorizzato era il piano:

```powershell
$backupDocs = Join-Path (Split-Path (Get-Location) -Parent) ("vibecraft-docs-backup-" + (Get-Date -Format yyyyMMdd-HHmmss))
if (Test-Path -LiteralPath $backupDocs) { throw "Destinazione backup già presente" }
Copy-Item -LiteralPath .\docs -Destination $backupDocs -Recurse -ErrorAction Stop
```

Prima di contare sul backup, confrontare percorsi relativi e hash di **tutti**
i file fra fonte e copia, e conservarne il manifest con gli artefatti locali
dell'esperimento. Una copia riuscita senza confronto non chiude la precondizione.
Prima del ripristino verificare i percorsi assoluti, fermare intake/scrittori e
conservare a parte anche il corpus fallito per diagnosi. Il ripristino deve
eliminare la differenza del corpus candidato, non soltanto copiare sopra
lasciando i file nuovi; riallineare poi indice e corpus tramite R.2 o full rebuild.

`approve()` rifiuta una destinazione già presente **prima** del lock
(`rag/core/intake.py:450`). La scrittura è `target.write_text` **sotto** lock
(`:470`), senza un secondo controllo nello stesso blocco. Il rifiuto normale
non prova quindi la protezione da una collisione comparsa durante l'attesa.
Se il reindex solleva un errore, il codice rimuove il file appena scritto:
anche questo non è un backup delle fonti preesistenti. Il test della collisione
in attesa è parte dell'intervento 1, non una modifica eseguita qui.

### R.1 — Git: un branch per intervento

Il manutentore apre, per esempio, `evoluzione/docling`, `evoluzione/mcp`,
`evoluzione/scala`, `evoluzione/governance`. Nessun lavoro diretto su main.
Registrare il commit di partenza di ciascun ramo: `011e264` è il riferimento
delle misure, non il futuro punto di ritorno di tutti i rami.

```text
git switch -c evoluzione/docling
```

Per abbandonare il solo ramo, dopo aver conservato risultati e lavoro utile e
controllato che nessuna modifica altrui vada perduta:

```text
git switch main
git branch -D evoluzione/docling
```

Sono comandi **documentati, non eseguiti**. `git switch` non risolve un working
tree sporco e la cancellazione del branch non recupera file locali.
`rag/database/` non viene riavvolto da git; `docs/` contiene file non tracciati
e una copia istanziata. Per entrambi servono le reti dedicate.

S8/R16 ha deciso il ruleset su main con `test` obbligatorio. La sua applicazione
è manuale e non è stata verificata su GitHub in questa sessione locale
(`rag/adr/AUDIT.md:4201`). Il tag v0.1.0, 60 commit prima, non è un sostituto
della baseline dell'intervento.

### R.2 — Indice: blue/green e i suoi limiti

CLI verificata nel sorgente `rag/index.py:47`; destinazioni validate in 0.2,
nessuna mutazione di prova. Da `rag/`:

```text
uv run python index.py --rollback
uv run python index.py --rollback v20260907T142924
```

Oggi il primo comando sceglierebbe **v20260907T150309**. Il secondo ha una
collection target presente. La CLI sposta CURRENT e riallinea l'alias Qdrant,
senza build. Nell'esecuzione futura scegliere una versione esplicita quando
«precedente» non significa «baseline verificata».

1. **Collection target mancante:** il precheck rifiuta prima di modificare CURRENT.
   Se Qdrant è irraggiungibile, la CLI può saltare il precheck e procedere con il
   solo rollback locale: in questa fase non usare quel caso come recupero coerente;
   ristabilire Qdrant e verificare alias/vettori. Se i vettori sono persi, serve
   un full rebuild.
2. **Incrementali in place:** non riavvolgono i punti Qdrant della stessa lineage.
   Leggere `rollback_shares_collection_with_later_versions`, non ignorarne l'avviso
   (`rag/core/indexing.py:525`). Qui tutte le cinque versioni hanno collection
   distinte; ciò non garantisce le versioni che nasceranno dopo.
3. **Gate prima della promozione:** `blocking: true`, `k: 2`, `min_recall: 0.75`
   (`rag/rag_config.yaml:464`, `:498`, `:499`; `rag/core/eval_gate.py:121`). Se
   blocca una candidata full, CURRENT non si è mosso: non serve un rollback.
4. **Retention:** default 5 (`rag/core/artifacts.py:202`). Altre build possono
   eliminare proprio la baseline. Prima dei batch fissare una retention sufficiente
   al numero di candidate e verificare che la collection target sia ancora presente;
   un backup dei soli sidecar non conserva i vettori Qdrant.

Durante questa fase preferire sempre **full rebuild con collection distinta**.
Dopo un ritorno verificare CURRENT, alias, integrità, snapshot del server e
qualità: il fatto che il comando sia rapido non rende coerente un corpus diverso.

### R.3 — Dipendenze: diff prima del commit, ripristino dal riferimento giusto

In questa sessione `uv.lock` e `pyproject.toml` non sono cambiati. In esecuzione:
prima dry-run disponibile in 0.1; poi, soltanto nel branch autorizzato, modifica
della dipendenza e **ispezione del lock universale risultante**:

```text
# dalla root, dopo la modifica futura
git diff --stat -- rag/uv.lock
git diff -- rag/pyproject.toml rag/uv.lock
```

I conteggi di `uv pip compile` non sostituiscono questo controllo. Non accettare
un ripiego di versione Docling non dichiarato, né confondere una risoluzione
riuscita con import e conversione riusciti sulle piattaforme native.

Per annullare modifiche **non committate** dei due file, dalla root:

```text
git checkout -- rag/pyproject.toml rag/uv.lock
```

Poi da `rag/`:

```text
uv sync --frozen
```

Se il cambiamento è già committato, `git checkout --` ripristinerebbe il commit
già modificato: usare invece il **commit baseline esplicito** del ramo per
entrambi i file, poi sync frozen, oppure tornare al ramo di partenza. Non
azzerare cambiamenti del manutentore insieme a quelli dell'intervento.

**Accettazione della catena:** suite completa, zero fallimenti e zero skip con
Qdrant; ruff pulito; `scripts/ci.sh` non regredisce; test
`rag/tests/test_torch_platform_pin.py` verdi; smoke native e immagine CPU da
checkout pulito. Non usare «1321+» per tollerare test rimossi: la raccolta locale
oggi comprende **1342 test**, uno fallito per l'archivio, da chiudere in P0.
Vanno conservati i cinque test Qdrant reali richiesti dalla CI e il job
`macos-nativo` di `.github/workflows/ci.yml`.

### R.4 — Configurazione calibrata e interruttori

Valori congelati per 1–4: **boost_alpha 0.3**, **graph_context_max_chunks 3**,
**section_restatement_weight 0.92**. Solo il protocollo congiunto della sezione
5 può motivare una revisione; il ritorno ripristina la tupla di riferimento,
non un asse scelto dopo aver visto la regressione.

| Funzione futura | Valore/azione di spegnimento | Limite del ritorno |
|---|---|---|
| Docling intake | `intake.conversion_engine: "markitdown"` | Non ripristina documenti già approvati |
| Conversione alternativa PDF diretti | `retrieval.pdf_conversion_engine: ""` | Non ripristina un indice costruito con altro parsing |
| MCP | Adattatore non avviato; se introdotto, `mcp.enabled: 0` | Il client perde i tool, il server HTTP resta indipendente |
| Corpus intero | `retrieval.full_corpus_max_tokens: 0` | Non revoca dati già trasferiti: il consenso deve precedere l'uso |
| Giudice 27b | Override judge rimosso/vuoto | Riporta al 9b, non cambia i risultati storici già prodotti |
| Scala / validatore | Esperimento o CLI non invocati | Nessun effetto produttivo di default |

Sono convenzioni **proposte**, non chiavi già implementate. I valori di config
sono caricati dai processi: spegnere mediante config può richiedere un riavvio,
ma non reindicizzazione. Gli effetti già persistiti richiedono R.0/R.2.

Hash SHA-256 misurati prima e dopo le prove, confermati prima della scrittura:

```text
rag/rag_config.yaml
289195009d8e0f20dfec93a93ff4b82927e75626f6de1ca842bf224f1b31512d
rag/pyproject.toml
9df03682e0253665dd5c15b8080f2fa35cf95776116319eec35c9f11ac37a324
rag/uv.lock
528b9c17f9bd091071b795a1b5a678d47dc50d161f9fa31a8d121e2e9f992d9f
rag/eval/results/history.jsonl
a8574912d5bd3e70866aceb5cd8626a1a9deecf0cc02a2d66b56c2c0a67d71d7
```

### R.5 — Rete esistente: usarla conoscendone le scritture

Dopo ogni intervento, e prima di considerarlo chiuso: integrità, suite, lint,
recall/multihop e controlli d'attribuzione pertinenti. Dopo il riallineamento
eseguire anche il notturno, oltre alla sua normale periodicità. I comandi
diagnostici di sola lettura già usati da questa macchina sono:

```text
uv run --no-sync python -B index.py --index-status
uv run --no-sync python -B index.py --check-integrity
uv run --no-sync python -B -m eval.run --no-save
uv run --no-sync python -B -m eval.run_multihop --no-save
uv run --no-sync python -B -m eval.attribution --repeats 3 --no-save
```

Durante l'esecuzione degli interventi, usare anche il salvataggio dei report
autorizzato per quella fase; qui `--no-save` serviva a rispettare il perimetro
documentale della sessione. Il presente documento conserva la baseline misurata,
ma prima di ottimizzare si raccolgono anche i report macchina del P0 coerente.

**Avvertenza verificata nel codice, non ipotetica:**
`rag/scripts/nightly_consistency.sh` e la variante PowerShell possono accodare
reindex/full rebuild, scrivere alert e inviare un webhook. Sul corpus stale
attuale eseguirebbero una remediation: non sono stati lanciati. Nella fase di
esecuzione eseguirli dopo integrità pulita/full rebuild, con webhook esterni
disabilitati per mantenere il perimetro locale; leggere i log e gli alert di
`GET /api/health`. Se fallisce l'integrità, diagnosticare prima di innescare
automaticamente un incrementale che riduca la protezione blue/green.

`--check-graph` è il controllo profondo, con embedding: pianificarne costo e
assenza di carichi concorrenti, non presentarlo come check economico. Il test
economico è `--check-integrity`. `scripts/ci.sh` esegue `uv sync --frozen`, lint
e suite: non è stato lanciato integralmente perché qui non si sincronizza
l'ambiente. La CI remota, il container CPU e macOS restano verifiche future,
senza operazioni GitHub implicite in questa approvazione.

### R.6 — Quando fermarsi

Ogni sezione del piano contiene il proprio criterio di abbandono. Non
compensare un fallimento cambiando una soglia dopo averlo visto; salvare
baseline, candidata, protocollo e verdetto `NON_APPLICARE`. Il risultato
negativo è riutilizzabile soltanto se dichiara **quando va rimisurato**:
nuovo layout, nuova catena compatibile, nuovo modello, consenso esplicito o
distribuzione reale diversa, secondo la sezione corrispondente.

## 6. Cosa non è pianificato / cosa non è stato fatto

- **Implementazione in questa sessione:** nessuna. Solo questo piano e il suo
  collegamento nel README ADR; i file elencati negli interventi sono futuri.
- **Riapertura generalizzata di S8:** nessuna. N1 resta chiusa; R29 attende il
  secondo modello; A6 resta accettata. Il fallimento del controllo di storicità
  e l'indice stale sono prerequisiti concreti, non una nuova discussione di A6.
- **Streaming come ottimizzazione autonoma:** escluso per trigger non scattati.
- **Abbassamento di Python, modifica isolata dei pesi, indicizzazione incrementale
  come scorciatoia:** esclusi dai vincoli e dalla protezione del rollback.
- **Marker, LlamaIndex, Langfuse self-hosted, sostituzione Ollama con vLLM:** restano
  esclusi secondo le decisioni del mandato; nessuna nuova evidenza è stata
  raccolta per ribaltarle.
- **bge-reranker-large in produzione:** non previsto. Un test offline resta
  ammissibile con ipotesi propria, baseline e protocollo congiunto; nessuna
  installazione o prova del reranker è stata eseguita. Non si usa la vecchia
  giustificazione di alpha 0.1 superata da S11.
- **Connettori SaaS, ACL per documento, multi-tenancy, chat generalista:** fuori
  perimetro, senza un requisito emerso dalle misure.
- **Tracciare i contenuti locali per rendere verdi i test:** escluso da A6.
- **Nuovo giudice remoto, invio degli estratti MCP o del corpus intero:** non
  eseguiti e non autorizzati dall'approvazione del piano.
- **Backup, branch, rollback, download modelli, installazione Docling, build,
  publish o GitHub:** non eseguiti. I comandi di ritorno sono prescritti e
  controllati nel sorgente/precheck; non vengono descritti come prove di restore.
- **Percentuali esterne di accuratezza PDF:** non usate come baseline locale.
  Il campione misurato sono i due cataloghi; nessuna conclusione sul 97,9% o
  su un confronto di velocità non riprodotto su questa macchina.

## 7. Le forcelle aperte — decisioni del manutentore

L'approvazione del piano **non risponde** a queste domande. Finché non arriva
una scelta esplicita, il ramo dipendente resta spento; non si interpreta il
silenzio come consenso. Non sono tre nuove voci da aggiungere automaticamente
ai registri chiusi: sono le condizioni di esecuzione di questa fase.

| # | Domanda sì/no | Se sì | Se no / senza risposta | Condizione di riapertura |
|---|---|---|---|---|
| F1 | **Autorizzi l'invio del corpus completo a un provider remoto per l'intervento 3?** | Definire provider e tetto di spesa, contare il payload reale e fare il confronto controllato | Strategia spenta; niente token-counting remoto del corpus | Consenso esplicito o finestra locale utile verificata |
| F2 | **Autorizzi un client MCP a inoltrare gli estratti a un modello remoto?** | Documentare il perimetro dei dati esposto al chiamante e provarlo con client autorizzato | MCP soltanto per chiamanti che mantengono il dato locale; niente trasferimento implicito | Nuova autorizzazione sul perimetro degli estratti |
| F3 | **Autorizzi, nel futuro ramo Docling, un aggiornamento controllato di Transformers per macOS, subordinato ai gate?** | Provare una catena esplicita e testata, conservando Python e pin/marker torch | Nessun aggiornamento della catena dell'app; valutare intake in container separato con misure proprie | Catena compatibile senza variazione o nuova autorizzazione |

R29 non aggiunge una quarta scelta sul modello: **il prossimo tentativo locale
27b è già deciso in S8**. Attende il trigger e la misura di costo; non viene
installato come effetto collaterale della scrittura del piano.


## Resoconto P0 e R.0 — 2026-09-08

**Verdetto: PASS.** Esecuzione limitata a P0/R.0 su `codex/evoluzione-p0`,
HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`. Nessun branch, commit, push o PR
creato. Le misure iniziali sopra sono conservate byte per byte come prefisso.
`AGENTS.md` non trovato nella root, nei percorsi genitori controllati o nella
ricerca ricorsiva del repository (anche fuori sandbox).

### Stato iniziale e conservazione

Preesistenti: modifiche a `rag/adr/README.md` e tre righe in
`rag/eval/results/history.jsonl`; non tracciati `.agents/`,
`.claude/settings.local.json`, `rag/adr/EVOLUZIONE.md`, `skills-lock.json`, `tmp/`.
Preservati. Lo storico riceve soltanto nuove righe dagli strumenti esistenti;
il prefisso originario è verificato byte per byte. Nessun ranking, parser,
dipendenza o parametro calibrato modificato. Hash finali in `verification.json`.

Backup esterno: `C:\Users\Silve\Desktop\vibecraft-p0-backup-20260908-152239`.
Corpus completo: **60 file**, inclusi SVG/HTML e tutte le fonti non tracciate;
inventario con dimensioni e SHA-256 in `docs-manifest.json`, confronto integrale
fonte/copia e ricostruzione in `restore-rehearsal/docs` riusciti.
La copia `restore-rehearsal/docs-index-start` conserva i file non indicizzabili
e riproduce le **40 fonti** del manifest iniziale per SHA-256; esclude solo i due
PDF aggiunti, che rimangono nella copia completa. Questo distingue il ritorno
all'indice vecchio dal ripristino del corpus completo a 42 fonti.

Cinque versioni iniziali verificate: collection presenti, conteggi esatti,
precheck rollback, nessuna condivisione con lineage successive, sidecar NPZ
leggibili e copie identiche per hash. Retention **15** via
`VIBECRAFT_INDEX_KEEP` nei processi di rebuild/server/notturno; nessuna versione
iniziale eliminata. È una protezione della sessione, non un pin permanente:
esportare di nuovo la variabile prima dei futuri batch e dimensionarla al loro
numero. Snapshot Qdrant esterni della versione iniziale e della nuova baseline,
entrambi verificati contro il checksum SHA-256 fornito dal server; sidecar di
entrambe conservati fuori repository. Non è stato effettuato uno swap di prova
in produzione né un restore Qdrant: sono verificati i prerequisiti, la copia
del corpus e la leggibilità degli artefatti.

### Indice e risultati

- Prima: `v20260907T151549`, 40 fonti / 248 chunk, stale per i due PDF.
- Dopo: `v20260908T132451`, collection `vibecraft_events__v20260908T132451`, **42 fonti / 250 chunk**,
  **935 nodi / 1305 archi**, entrambi i PDF nel manifest e nei chunk.
- Full rebuild con parser pypdf corrente e gate bloccante, exit 0, promosso;
  durata **395.66 s**. Durante l'avvio il 9b
  Ollama era residente e contendeva VRAM; scaricato alle 15:30:35 locali senza
  cambiare configurazione. La durata include questa contesa e non rappresenta
  una misura isolata del costo di embedding.
- Solo `summary.superseded_by` aggiornato a `v20260908T132451` (e commento della
  stessa riga). Archivio, risposte, altre etichette e `index_version`
  `v20260907T094225` conservati; nessuna nuova misura di attribuzione implicita.
- Integrità iniziale post-build e finale: exit 0, non stale, alias allineato.
- Suite: **1342 passed, zero failure, zero skip**, 97.48 s, Qdrant obbligatorio.
- Lint: `All checks passed!`.
- Retrieval, 58 casi: recall@1 **0.706897**, @2 **0.827586**,
  @5 **0.948276**, @10 **1.000000** (saturo),
  source_in_top3 **0.896552**, MRR **0.811371**.
  Gate @2 >=0.75 rispettato. Multihop: **0.854**, **9/14 A**, **6/6 B exact**,
  soglia 0.85 e attese strutturali rispettate. Valori completi nei JSON.
- Benchmark, stesse funzioni e dieci query del piano: retrieve p50/p95
  **507.1/530.25 ms**;
  ask totale p50/p95 **18726.09/34439.44 ms**;
  generazione p50/p95 **17919.97/33697.70 ms**;
  semantic-map **308.72 ms**, 250 punti, non troncata.
  Embedder server CPU caldo, Ollama ricaricato a 16384 prima delle query.
  Nessun benchmark incrementale: stesso protocollo iniziale, nessun incrementale
  autorizzato. Il full rebuild è misurato dal comando P0, non ripetuto dal bench.
- Notturno eseguito dopo integrità pulita, webhook disabilitato,
  `UV_NO_SYNC=1`, `PYTHONDONTWRITEBYTECODE=1`: esiti e contratti nei log.
  Health finale: `ok`; consultare `health-after.json` per gli alert.

Non si attribuisce a Docling alcun effetto: non è stato installato o usato.
Il golden esistente non contiene casi specifici per questi PDF. Il p95 su dieci
campioni resta vicino al massimo e non descrive la coda sotto carico.

### Comandi e artefatti riproducibili

Baseline identificabile: `C:\Users\Silve\Desktop\vibecraft\rag\eval\results\p0_20260908-152239`.
I report eval/multihop datati sono anche copiati qui; `commands.json` registra
argv, exit code e durata, `runtime.json` registra Python e pacchetti,
`preflight.json` inventari e precheck, `index.json` manifest e chunk PDF,
`benchmark.json` i campioni, `verification.json` gli invarianti finali.
Helper della sessione in `tmp/p0_prepare.py`, `tmp/p0_measure.py`,
`tmp/p0_finalize.py`; non sono codice applicativo. Non rilanciarli ciecamente:
usano destinazioni uniche e richiedono lo stato della sessione.

Comandi da `rag/`, ambiente già installato:

```text
uv run --no-sync python -B index.py
uv run --no-sync python -B index.py --check-integrity
uv run --no-sync python -B -m pytest -o addopts= -q -p no:cacheprovider
uv run --no-sync ruff check --no-cache .
uv run --no-sync python -B -m eval.run
uv run --no-sync python -B -m eval.run_multihop
pwsh -NoProfile -File scripts/nightly_consistency.ps1
```

Suite con `PYTHONUTF8=1`, `HF_HUB_OFFLINE=1`, `VIBECRAFT_REQUIRE_QDRANT=1`.
Gli helper invocano direttamente lo stesso interprete selezionato da
`uv run --no-sync`; benchmark via `scripts.bench.bench_retrieve`, `bench_ask`,
`bench_semantic_map`. `scripts/ci.sh` non eseguito: sincronizzerebbe dipendenze;
lint e suite equivalenti eseguiti senza sync. Nessuna CI remota/container CPU/macOS.

### Procedura di ritorno

1. Fermare server, intake e altri writer; verificare percorsi assoluti sotto
   `C:\Users\Silve\Desktop\vibecraft` e il backup sopra. Conservare il corpus
   candidato in una nuova directory esterna, senza cancellare modifiche altrui.
2. Per tornare alla baseline coerente P0, sostituire l'intera directory `docs/`
   con `backup/docs`, confrontare inventario/hash e usare `v20260908T132451`.
   Per tornare alla versione iniziale usare invece la copia verificata
   `backup/restore-rehearsal/docs-index-start` e `v20260907T151549`.
   Non copiare sopra lasciando file aggiuntivi. Il backup completo conserva i PDF.
3. Esportare `VIBECRAFT_INDEX_KEEP=15` (o superiore per ulteriori candidate).
   Verificare sidecar, disponibilità Qdrant, nome collection, conteggi e precheck.
   Se una collection è persa, ripristinare il relativo snapshot Qdrant verificato
   con la stessa versione server e i sidecar corrispondenti prima del rollback;
   in alternativa full rebuild. Non accettare il fallback di solo rollback locale.
4. Da `rag/`: `uv run --no-sync python -B index.py --rollback VERSIONE_ESPLICITA`.
   Riallineare la sola dichiarazione `summary.superseded_by` alla versione attiva,
   mantenendo archivio e index_version. Non ripristinare l'intero working tree.
5. Verificare CURRENT, alias, integrità; riavviare il server e verificare snapshot,
   retrieval e multihop. Nessun ritorno è dichiarato concluso solo perché la CLI
   termina. I comandi di rollback qui sono documentati, non eseguiti.

Fase chiusa qui: nessun intervento 1–7 avviato.

Chiusura operativa: server di prova arrestato; container vibecraft-qdrant-1 riportato allo stato iniziale spento, altro Qdrant non toccato; Ollama resta acceso con il 9b ricaricato. Prima di usare la baseline o eseguire il ritorno avviare il container VibeCraft. Ramo/HEAD finali invariati; git diff --check exit 0. Nessun AGENTS.md disponibile.


## Verifica di fattibilità delle dipendenze Docling — 2026-09-08

**Verdetto: PASS**, con prerequisiti e una decisione di licenza che spetta al
manutentore. Ambito eseguito: **soltanto** la fattibilità della catena di
dipendenze. Nessun pilot, nessuna fixture, nessuna conversione di PDF, nessuna
integrazione applicativa, nessuna misura di qualità del parsing. Il cancello 1c
resta interamente da attraversare.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push o PR. `rag/pyproject.toml` e `rag/uv.lock`
verificati **invariati** a fine sessione (`git diff --quiet`). `AGENTS.md` non
esiste nel repository: confermata la ricerca ricorsiva già registrata in P0.

Preesistenti preservate: `rag/adr/README.md`, `rag/eval/golden_attribution.yaml`,
`rag/eval/results/history.jsonl`, e i non tracciati `rag/adr/EVOLUZIONE.md`,
`rag/eval/results/p0_20260908-152239/`, `skills-lock.json`, `tmp/`.
**Nota non attribuibile a questa verifica:** durante la sessione `.gitignore` è
stato modificato dall'esterno (aggiunta della riga `.agents/`, mtime 16:06), e
`.agents/` è passato da non tracciato a ignorato. Non è una modifica di questa
verifica; è stata lasciata intatta e viene segnalata perché altera `git status`
rispetto allo stato iniziale registrato in P0.

### Ambiente sperimentale isolato

Venv `uv` dedicato **fuori dal repository**, nella scratchpad di sessione:
`…\scratchpad\docling-feas\venv`. Nessuna installazione nell'ambiente
dell'applicazione, nessun `uv add`, nessun `uv sync`, nessuna scrittura del lock.
Cache Hugging Face reindirizzata a `…\scratchpad\docling-feas\hf-home`
per le letture di metadati (una lettura di `config.json` è finita nella cache
utente prima del reindirizzamento: è l'unico residuo fuori scratchpad).
Qdrant, Ollama e il server non sono stati avviati: non servono a questa verifica.

### La combinazione candidata, esplicita e senza backtracking

Docling è stato **pinnato** (`docling[vlm]==2.126.0`) in ogni risoluzione e nella
installazione. Dove il pin non era soddisfacibile la risoluzione è stata lasciata
fallire: nessun ripiego su un'altra versione di Docling è stato accettato come
prova. Il tentativo P0 senza pin, che scivolava su Docling 2.96.1, non è stato
riusato.

| Componente | Versione candidata | Rispetto all'app |
|---|---|---|
| Python | CPython **3.14.6**, win_amd64 | invariata |
| uv | **0.11.28** | invariata |
| docling | **2.126.0**, extra `[vlm]` | nuova |
| docling-slim | **2.126.0** | nuova |
| docling-core | **2.95.0** | nuova |
| docling-ibm-models | **4.0.2** | nuova |
| docling-parse | **7.18.0** | nuova |
| transformers | **5.15.1** | **INVARIATA** |
| tokenizers | **0.22.2** | invariata |
| torch | **2.13.0+cu126** (indice CUDA, marker intatti) | **INVARIATA** |
| torchvision | **0.28.0+cpu** (da PyPI) | nuova |
| onnxruntime | **1.29.0** | **INVARIATA** |
| typer | **0.26.8** | **declassata** da 0.27.x |
| Granite Docling | `ibm-granite/granite-docling-258M` @ `982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe`, Apache-2.0, 529,9 MB | **non scaricato** |

**Il pin su `docling` non pinna la catena.** `docling==2.126.0` fissa
`docling-slim==2.126.0`, ma lascia intervalli su `docling-parse>=7.16.0,<8.0.0`,
`docling-core>=2.91.0,<3.0.0`, `docling-ibm-models>=4.0.2,<5`. È esattamente il
motivo per cui P0 aveva registrato docling-parse **7.17.0** e oggi la stessa
risoluzione dà **7.18.0**: il parser si è mosso sotto un pin che sembrava fermo.
L'unità riproducibile è il file di requisiti completo salvato negli artefatti,
non la riga `docling==2.126.0`.

**Granite: `revision="main"`.** Le spec di Docling (`GRANITEDOCLING_TRANSFORMERS`,
`GRANITEDOCLING_MLX`, `GRANITEDOCLING_VLLM`, `GRANITEDOCLING_2STAGE_TRANSFORMERS`)
puntano tutte al ref mobile `main`, non a un commit. La revisione sopra è stata
risolta e registrata qui; il pilot deve passarla esplicitamente, altrimenti i pesi
possono cambiare fra due esecuzioni senza che nulla nel lock lo segnali.

### Piattaforme: risoluzione, wheel, test effettivi — tre cose diverse

**(a) Risoluzione teorica** — `uv pip compile`, pin esplicito, Python 3.14.
Il controllo *senza* Docling è stato eseguito su ogni target per non attribuire a
Docling limiti già presenti nella baseline.

| Target | Solo progetto | + `docling[vlm]==2.126.0` | Esito |
|---|---:|---:|---|
| x86_64-pc-windows-msvc | 130 | **164** | entrambe risolvono |
| x86_64-unknown-linux-gnu | 146 | **180** | entrambe risolvono |
| aarch64-unknown-linux-gnu | 146 | **180** | entrambe risolvono |
| aarch64-apple-darwin, `MACOSX_DEPLOYMENT_TARGET=14.0` | 127 | **168** | risolvono; solo con transformers libera (vedi F3) |
| aarch64-pc-windows-msvc | **fallisce** | **fallisce** | torch senza wheel win_arm64 — **limite di baseline** |
| x86_64-apple-darwin | **fallisce** | **fallisce** | torch senza wheel macOS Intel — **limite di baseline** |
| aarch64-apple-darwin, target implicito 13 | **fallisce** | **fallisce** | wheel torch richiede macOS 14 — **limite del comando** |

Le tre righe che falliscono falliscono **identicamente con e senza Docling**, e
sul medesimo pacchetto: `torch`. **Docling non toglie nessuna piattaforma che il
progetto avesse già.**

**(b) Disponibilità wheel** — metadati PyPI, tag cp314/abi3/universal2.

| Pacchetto | win_amd64 | win_arm64 | linux x86_64 | linux aarch64 | mac arm64 | mac x86_64 | sdist |
|---|---|---|---|---|---|---|---|
| docling / -core / -slim / -ibm-models | pura | pura | pura | pura | pura | pura | sì |
| docling-parse 7.18.0 | sì | sì | sì | sì | sì | **no** | sì |
| opencv-python 5.0.0.93 | sì | **no** | sì | sì | sì | sì | sì |
| av 18.1.0 | sì | sì | sì | sì | sì | sì | sì |
| shapely 2.1.2 | sì | **no** | sì | sì | sì | sì | sì |
| pyclipper 1.4.0 | sì | **no** | sì | sì | sì | sì | sì |
| rtree 1.4.1 | sì | sì | sì | sì | sì | sì | sì |
| rapidocr 3.9.2 | pura | pura | pura | pura | pura | pura | no |
| torchvision 0.28.0 | sì | **no** | sì | sì | sì | **no** | no |
| onnxruntime 1.29.0 | sì | sì | sì | sì | sì | **no** | no |

I buchi su win_arm64 e macOS Intel cadono su piattaforme che **già non risolvono**
per torch: non aggiungono una perdita, la confermano.

**(c) Test nativi realmente eseguiti — una sola piattaforma.**
`x86_64-pc-windows-msvc`, CPython 3.14.6, la macchina di questa sessione.
Linux e macOS hanno **soltanto** (a) e (b): nessuna installazione, nessun import,
nessun test è stato eseguito lì. Non vanno riportati come verificati.

| Prova nativa (solo Windows x86_64) | Esito |
|---|---|
| Installazione dei 164 pacchetti nel venv isolato | **exit 0** |
| Versioni risolte = combinazione candidata, nessun backtracking | **confermato** |
| `import docling`, `DocumentConverter` | OK, 31 formati, 29,7 s a freddo |
| `docling.pipeline.vlm_pipeline` e `standard_pdf_pipeline` | OK |
| 9 backend Docling che importano `transformers` | **9/9 OK con transformers 5.15.1** |
| Simboli transformers richiesti da Docling (`AutoModelForImageTextToText`, `StopStringCriteria`, …) | **nessuno mancante** |
| `idefics3` in `CONFIG_MAPPING`; `AutoConfig` di Granite | OK → `Idefics3Config` |
| `MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING_NAMES["idefics3"]` | `Idefics3ForConditionalGeneration` |
| `docling_parse` (binario nativo) | import OK |
| torchvision **operazioni**, non solo import: `nms` + `Resize` su CPU | OK |
| torchvision `nms` su **CUDA** | **FALLISCE**, `NotImplementedError` |
| torch CUDA: `is_available`, matmul su GPU | OK, marker CUDA intatti |
| onnxruntime provider | `AzureExecutionProvider`, `CPUExecutionProvider` |
| Import di **tutti** i moduli applicativi sotto la catena candidata | **33/33** (`core/` + `api/`) |

**Il difetto trovato: `torch 2.13.0+cu126` con `torchvision 0.28.0+cpu`.**
`[tool.uv.sources]` dirotta sull'indice CUDA **solo `torch`**, non `torchvision`,
che quindi arriva da PyPI nella variante CPU. Torch resta CUDA e funziona; ma le
operazioni compilate di torchvision (`nms` e simili) **non esistono sul backend
CUDA** e sollevano `NotImplementedError`. Il primo esperimento del piano è su CPU,
quindi non è bloccante oggi; diventa un difetto silenzioso appena una pipeline
Docling provasse a usare torchvision su GPU. Non è stato corretto: correggerlo
significa toccare `[tool.uv.sources]`, cioè le dipendenze applicative.

### Diff delle dipendenze, dimensioni, requisiti

Windows x86_64, baseline **130** → candidata **164**: **34 aggiunte**, nessuna
rimozione, **una declassata**.

```text
antlr4-python3-runtime 4.9.3   av 18.1.0            colorlog 6.12.0
doclang 0.7.3                  docling 2.126.0      docling-core 2.95.0
docling-ibm-models 4.0.2       docling-parse 7.18.0 docling-slim 2.126.0
faker 40.38.0                  filetype 1.2.0       jsonref 1.1.0
latex2mathml 3.81.1            mail-parser 4.6.4    marko 2.2.4
mpire 2.10.2                   omegaconf 2.3.1      opencv-python 5.0.0.93
pluggy 1.6.0                   polyfactory 3.3.0    pyclipper 1.4.0
pydantic-settings 2.15.0       pylatexenc 2.11      python-oxmsg 0.0.2
qwen-vl-utils 0.0.14           rapidocr 3.9.2       rtree 1.4.1
semchunk 3.2.5                 shapely 2.1.2        tabulate 0.10.0
torchvision 0.28.0             tree-sitter-c 0.24.2 tree-sitter-python 0.25.0
websockets 16.1.1
declassato: typer 0.27.x -> 0.26.8
```

**`torch` e `onnxruntime` non sono sostituiti**, su nessun target che risolve.

**Il declassamento di typer ha una causa precisa e un rischio basso:**
`docling-core` richiede `typer<0.27.0,>=0.12.5`. `typer` **non è dichiarato** in
`rag/pyproject.toml` e **non è importato da nessun file** dell'applicazione
(0 riscontri in `--include=*.py`): arriva come transitiva di `transformers`.
Nessuna superficie applicativa dipende dalla differenza 0.27.1 → 0.26.8.

**Dimensioni misurate**

| Voce | Valore |
|---|---|
| Download aggiuntivo, wheel win_amd64 delle 34 nuove | **123,2 MB** |
| di cui opencv-python / av / rapidocr / docling-parse | 44,0 / 28,5 / 27,3 / 12,2 MB |
| Venv applicativo attuale (`rag/.venv`) | **4813 MB** |
| Venv candidato (app + `docling[vlm]`) | **5285 MB** |
| **Delta su disco** | **+472 MB** |
| Pesi Granite Docling 258M, **non scaricati** | **+529,9 MB** (`model.safetensors` 515,1 MB) |
| Più pesanti fra i nuovi, su disco | cv2 113 MB, av.libs 63 MB, docling_parse 37 MB, rapidocr 32 MB |

Costo totale realistico del solo pilot su questa macchina: **circa 1,0 GB**
fra dipendenze e pesi, oltre alla cache uv (già 12 GB).

### Audit delle licenze: pacchetti, transitive e binari

Rilevate dai metadati `dist-info` dei **164 pacchetti effettivamente installati**,
non dalla sola dichiarazione di Docling.

**Livello pacchetto: nessun copyleft introdotto.** Tutte e 34 le aggiunte sono
permissive — MIT, BSD-2/3-Clause o Apache-2.0. I tre riscontri copyleft/ignoti
dell'ambiente (`certifi` MPL-2.0, `tqdm` MPL-2.0 AND MIT, `flagembedding` senza
licenza dichiarata) sono **preesistenti**, non attribuibili a Docling.

**Livello binario: qui c'è il riscontro che il piano teneva come cancello.**
La wheel di **`av` 18.1.0** — pacchetto BSD-3-Clause — spedisce 25 DLL:

- FFmpeg 8.x (`libavcodec` 62, `libavutil` 60, …). La stringa di configurazione
  incorporata **non contiene `--enable-gpl`**, contiene `--enable-version3`, e
  FFmpeg si auto-dichiara **«LGPL version 3 or later»**. Letta dal binario
  installato via `av._core.library_meta`, non dedotta dai nomi dei file.
- **`libx264-165.dll` e `libx265.dll`**, che sono **GPL-2.0-or-later**, presenti
  nella wheel come DLL separate (`--enable-libx264 --enable-libx265` senza
  `--enable-gpl`: FFmpeg 8 le carica come moduli esterni, così il core resta LGPL).
- `libiconv-2.dll` (LGPL-2.1) e il runtime MinGW `libgcc_s_seh` / `libstdc++` /
  `libwinpthread` (GPL-3 **con** GCC Runtime Library Exception).

Gli altri binari sono puliti: `opencv-python` Apache-2.0 (113 MB, con
`LICENSE-3RD-PARTY` incluso), `docling-parse` MIT, `shapely`/`rtree`/`pyclipper`
BSD/MIT sopra GEOS, libspatialindex e Clipper.

**Come entra il GPL, e come si evita.** La catena è
`docling[vlm]` → `docling-slim[models-vlm-inline]` → `qwen-vl-utils` → `av`.
Due riscontri limitano la portata:

1. **`av` non viene mai caricato.** Importando `docling.pipeline.vlm_pipeline`,
   `standard_pdf_pipeline` e `DocumentConverter`, `av` **non** compare in
   `sys.modules`; non compare nemmeno importando `qwen_vl_utils`, che lo carica
   in modo pigro e solo per i frame video. Le DLL GPL stanno su disco, inerti
   rispetto alla conversione di PDF.
2. **Senza l'extra `[vlm]` spariscono.** `docling==2.126.0` senza extra risolve a
   **162** pacchetti, e le due che mancano rispetto ai 164 sono esattamente
   `av` e `qwen-vl-utils`. Docling espone `GRANITEDOCLING_OLLAMA`: Granite può
   girare sull'Ollama **già presente**, senza l'extra VLM e senza i binari GPL.
   Non è gratis: sarebbe un secondo modello su 8 GiB di VRAM, contro il vincolo
   «nessun modello aggiuntivo sulla GPU senza liberare quello residente»
   (`rag/api/deps.py:385`), e va misurato prima di essere scelto.

**Cosa questo non decide.** Usare software GPL in locale non fa scattare obblighi:
la GPL agisce sulla distribuzione. VibeCraft è Apache-2.0 e «si esegue dal
sorgente, non è un pacchetto che si costruisce» (`rag/pyproject.toml:6`). Ma il
repository ha un Dockerfile, e **pubblicare un'immagine che contiene quelle DLL è
distribuzione**. Se e come procedere è una scelta del manutentore, con la stessa
natura delle forcelle della sezione 7; non viene aggiunta lì d'ufficio, e il
silenzio non vale come consenso. La verifica si ferma al riscontro.

### F3 resta aperta — ma il vincolo è più stretto di come era formulato

Il conflitto Transformers **non esiste fuori da macOS**, ed è stato isolato sui
metadati reali di `docling-slim` 2.126.0, extra `models-vlm-inline`:

```text
transformers >=4.42.0,<6.0.0, !=5.0.*,!=5.1.*,!=5.2.*,!=5.3.*,!=5.13.0        ; sys_platform != "darwin"
transformers >=4.42.0,<6.0.0, !=5.0.*..!=5.3.*, !=5.9.*, !=5.10.*..!=5.15.*   ; sys_platform == "darwin"
```

La banda esclusa **solo su darwin** copre 5.9–5.15, e ci cade dentro proprio la
5.15.1 dell'app. Conseguenze verificate:

- **Windows e Linux:** `docling[vlm]==2.126.0` + `transformers==5.15.1` risolve
  (164 / 180 pacchetti) **e funziona in esecuzione** — i 9 backend importano,
  `idefics3` è mappato, `AutoConfig` di Granite costruisce. **F3 non serve** su
  queste piattaforme: nessun aggiornamento della catena dell'app è necessario.
- **macOS arm64:** il pin 5.15.1 rende le richieste insoddisfacibili; senza pin
  risolve a **transformers 5.16.1** (168 pacchetti, torch 2.13.0, onnxruntime 1.29.0).

**Il dettaglio che riformula la domanda:** la baseline *senza Docling*, risolta
oggi da zero, sceglie anch'essa **transformers 5.16.1** su ogni target. La 5.15.1
non è un vincolo del progetto — `transformers` non è dichiarata in
`rag/pyproject.toml`, arriva come transitiva di `flagembedding` senza specificatore
— è semplicemente ciò che `uv.lock` ha congelato. Quindi F3 non è «aggiornare
Transformers per far entrare Docling»: è «lasciare che un normale rinfresco del
lock faccia ciò che farebbe comunque».

**Proposta concreta per F3, se il manutentore la autorizza** (non applicata):
pinnare `transformers==5.16.1` in `rag/pyproject.toml` — dichiarandola esplicita
invece di lasciarla transitiva — conservando Python 3.14, il pin `torch==2.13.0`
e i marker CUDA di `[tool.uv.sources]`, e subordinando la modifica ai gate:
suite verde con Qdrant, `ruff`, integrità indice, retrieval e multihop senza
perdite rispetto a P0. **Non verificata qui:** 5.16.1 non è stata installata né
provata contro `flagembedding`/`sentence-transformers`, e l'embedder `BAAI/bge-m3`
non è stato ricaricato. Sarebbe il primo lavoro del ramo F3, non un suo esito.

**Alternativa isolata prevista dal piano.** Se F3 resta un «no», macOS non è
comunque persa: il target `aarch64-apple-darwin` fallisce già sulla baseline per
torch, quindi il ramo Docling non peggiora nulla, e la valutazione dell'intake in
container separato resta l'opzione — con misure proprie, che non sono state prese.

### Limiti di questa verifica

- **Una sola piattaforma provata davvero.** Windows x86_64. Linux e macOS hanno
  risoluzione e wheel, non esecuzione.
- **Nessuna conversione.** Nessun PDF aperto, nessuna tabella, nessuna cella,
  nessun heading, nessun confronto con MarkItDown. Il cancello 1c è intatto.
- **Granite non scaricato né caricato.** Verificati la revisione, la licenza, la
  dimensione e il fatto che `transformers` 5.15.1 ne costruisce la configurazione.
  **Non** verificati: caricamento dei pesi, memoria a runtime, tempo, qualità.
  I 258M parametri restano un numero di targa, non una misura di RAM/VRAM.
- **`docling-parse` si è mosso** da 7.17.0 (P0) a 7.18.0 in un giorno, sotto un
  pin di `docling` fermo. Chi rilancia senza il file di requisiti salvato può
  ottenere una terza versione.
- **Nessun test applicativo eseguito.** Solo import: `pytest` avrebbe richiesto
  Qdrant, e la suite non è stata lanciata sotto la catena candidata.
- **Il declassamento di typer non è stato provato in esecuzione**, solo escluso
  per assenza di uso applicativo.
- Cache uv già a 12 GB: i 123 MB di download non sono il costo totale su disco.

### Istruzioni riproducibili

Artefatti: `rag/eval/results/dep_docling_20260908-160000/` — `summary.json` (tutti
i riscontri con hash SHA-256 degli altri file), `requirements-candidate-win_amd64.txt`
(la catena pinnata: **è questa** l'unità riproducibile), `requirements-baseline-win_amd64.txt`,
`requirements-candidate-mac_arm64-F3.txt`, `diff-dipendenze-win_amd64.txt`,
`licenses.txt`, `install.log`, `pin-vlm.txt`, `pin-vlm-tf5151.txt`.
SHA-256 della risoluzione candidata: `8937248ed5dc2f8463c6bc79af3a88bd9f5a9ebc171ff679e288f96bada672fe`.

Da `rag/`, con un percorso `$ISO` **fuori dal repository**:

```text
# risoluzioni, nessuna installazione (il pin deve poter fallire)
printf 'docling[vlm]==2.126.0\ntransformers==5.15.1\n' > $ISO/pin.txt
uv pip compile pyproject.toml $ISO/pin.txt --python-version 3.14 \
  --python-platform x86_64-pc-windows-msvc --no-header --no-annotate --color never
# controllo senza Docling, per non attribuirgli limiti di baseline
uv pip compile pyproject.toml --python-version 3.14 --python-platform <target> ...
# macOS: serve MACOSX_DEPLOYMENT_TARGET=14.0, altrimenti fallisce torch, non Docling

# ambiente isolato
uv venv --python 3.14 $ISO/venv
VIRTUAL_ENV=$ISO/venv uv pip install -r pyproject.toml -r $ISO/pin.txt

# prove native
$ISO/venv/Scripts/python.exe -c "import docling; from docling.document_converter import DocumentConverter"
$ISO/venv/Scripts/python.exe -c "import torch;from torchvision.ops import nms;nms(torch.rand(2,4).cuda(),torch.rand(2).cuda(),.5)"
$ISO/venv/Scripts/python.exe -c "import av;print(av._core.library_meta['libavcodec']['license'])"
```

`uv add --dry-run` non esiste in uv 0.11.28: la premessa era già stata ritirata in
P0 e non è stata riusata. **Non** eseguire `uv add`, `uv sync` o `uv lock` dalla
root del progetto: modificherebbero la catena applicativa.

### Verdetto e prerequisiti per il pilot

**PASS.** La catena di dipendenze è fattibile sulla piattaforma di sviluppo, e i
criteri di abbandono di 1c che riguardano le dipendenze **non sono scattati**:
torch non cambia, i marker CUDA reggono, onnxruntime non cambia, nessuna
piattaforma viene persa rispetto alla baseline, nessun copyleft entra a livello di
pacchetto, e — riscontro non previsto dal piano — **transformers non deve cambiare**
su Windows e Linux. Non è un PASS del cancello 1c, che riguarda struttura, celle,
sezioni, retrieval e attribuzione e resta interamente aperto.

Prerequisiti prima di aprire il pilot:

1. **Decisione di licenza sui binari GPL in `av`** (x264/x265 nella wheel). Le tre
   uscite sono: accettare (uso locale, DLL mai caricate); rinunciare all'extra
   `[vlm]` e far girare Granite su Ollama, pagando la VRAM; oppure escludere la
   pubblicazione di immagini Docker che le contengano. Serve una scelta esplicita.
2. **Pinnare la revisione di Granite** a `982fe3b4…` invece del `main` di default,
   e registrarla insieme a pipeline e opzioni.
3. **Pinnare l'intera catena** dal file di requisiti salvato, non da
   `docling==2.126.0`: `docling-parse` si è già mosso una volta.
4. **Decidere F3** solo per macOS, sapendo che la 5.15.1 non è un vincolo del
   progetto ma un residuo del lock. Su Windows/Linux nessuna decisione è necessaria.
5. **Registrare il difetto torchvision `+cpu`** e vincolare il primo esperimento a
   CPU, come il piano già prevede, finché non si decide se dirottare anche
   `torchvision` sull'indice CUDA — che è una modifica alle dipendenze applicative.
6. **Backup R.0 e branch R.1** prima di qualunque scrittura: qui non è stato
   toccato nulla, ma il pilot scrive.
7. **Suite applicativa sotto la catena candidata**, con Qdrant, non eseguita qui.

Fase chiusa qui: verifica delle dipendenze conclusa, **integrazione non iniziata**.


## Pilot Docling e qualità dei PDF — 2026-09-08

**Verdetto: BLOCCATO.** Sei righe del cancello 1c su sette sono state misurate e
**nessuna di esse fallisce**: struttura, celle e sezioni sono superate in modo
netto, e il retrieval non perde nulla rispetto a P0. Il cancello resta però
chiuso per due motivi che non dipendono dalle misure riuscite: è comparso **un
valore fabbricato fuori dalle tabelle**, che il criterio di abbandono di 1c
nomina esplicitamente e che questa sessione non interpreta al posto del
manutentore; e la riga **attribuzione non è stata misurata**. Non è un
`NON_APPLICARE`: nessun criterio misurato è fallito.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push o PR. `rag/pyproject.toml` e `rag/uv.lock`
verificati invariati (`git diff --quiet`). `AGENTS.md` non esiste nel repository:
ricerca ricorsiva ripetuta, conferma P0 e sessione 2. Preesistenti conservate:
`.gitignore`, `rag/adr/README.md`, `rag/eval/golden_attribution.yaml`,
`rag/eval/results/history.jsonl` (le righe preesistenti sono intatte; questa
sessione ne ha **appesa una** via `eval.run_multihop`, vedi sotto), e i non
tracciati `rag/adr/EVOLUZIONE.md`,
`rag/eval/results/p0_20260908-152239/`, `rag/eval/results/dep_docling_20260908-160000/`,
`skills-lock.json`, `tmp/`. Il venv `[vlm]` della sessione 2 **non è stato alterato**.

Artefatti: `rag/eval/results/pilot_docling_20260908-170030/`.

### Gli input sono gli stessi della baseline

SHA-256 confrontati con `doc_hashes` del manifest di P0 (`index.json`,
indice `v20260908T132451`): **identici**, nessun documento è cambiato.

| PDF | Byte | SHA-256 | vs baseline |
|---|---:|---|---|
| `…/diagrams/catalogo_diagrammi_normativi.pdf` | 4658 | `9c0d51c5…3c56f91f` | invariato |
| `…/mockups/catalogo_mockup_normativi.pdf` | 5312 | `443ecfca…a00aa1b2` | invariato |

I due percorsi di produzione, richiamati in memoria, **riproducono P0 alla cifra**:
loader 1300 / 1798 caratteri, 1 chunk documento-intero ciascuno con gli stessi
`chunk_id` dell'indice; MarkItDown 1612 / 1722 caratteri con SHA-256
`292006d5…6303971e` e `eeb54c8f…2d1d5aa246`, gli stessi registrati in 0.4.
La baseline è quindi confrontabile, non ricostruita a occhio.

### Prima verifica: Granite gira **senza** l'extra `[vlm]`

**Sì, ed è stato provato con una conversione reale, non con import.**

`uv pip compile` con `docling==2.126.0` (nessun extra) + `transformers==5.15.1`
risolve **162** pacchetti contro i 164 della sessione 2. Il `diff` fra i due file
di requisiti ha **esattamente due righe**, entrambe in meno:

```text
< av==18.1.0
< qwen-vl-utils==0.0.14
```

Nient'altro si muove: `docling-parse` resta 7.18.0, `transformers` 5.15.1,
`torch` 2.13.0+cu126, `torchvision` 0.28.0+cpu, `onnxruntime` 1.29.0,
`typer` 0.26.8 declassata. Venv isolato **fuori dal repository** nella scratchpad
di sessione; installazione **exit 0**; `uv pip freeze` **identico riga per riga**
alla risoluzione salvata. `importlib.util.find_spec` conferma `av` e
`qwen_vl_utils` **assenti dall'ambiente**, non solo non importati.

Poi la prova che serviva davvero — conversione dei due PDF con
`VlmPipeline` + `GRANITEDOCLING_TRANSFORMERS` su **CPU esplicita**:

```text
status              ConversionStatus.SUCCESS (entrambi i documenti)
av in sys.modules            False
qwen_vl_utils in sys.modules False
backend caricato    transformers.models.idefics3 (7 moduli)
```

**Le DLL GPL di `av` non sono sul disco affatto**, non «presenti ma inerti».
Il venv candidato scende da 5285 MB (sessione 2, con `[vlm]`) a **5155 MB**:
−130 MB, coerenti con `av.libs` 63 MB più il resto.

**L'extra non cambia l'output, ed è misurato.** Lo stesso script è stato eseguito
anche nel venv `[vlm]` della sessione 2 — riusato in sola lettura, senza
rimuovere nulla, per conservare il confronto riproducibile. I due ambienti
producono file **identici byte per byte**, sia in Markdown sia in DocTags:

```text
diagrammi  3c5be08127b52d023b92f2ac59872b1362c1d77de267b2180beb3a7aeb46756b   (novlm == vlm)
mockup     25af5e148c384a9a025fe3062f01244c6e53bde714904b9fc43c38925d9885f2   (novlm == vlm)
```

Non è un'inferenza dalla catena: sono due esecuzioni reali confrontate.

**Riproducibilità fra esecuzioni: verificata a parte.** La conversione è stata
**rieseguita nel venv senza `[vlm]`, con la revisione pinnata, in un processo
nuovo**. I tre insiemi di output — run 1 senza `[vlm]`, run 2 senza `[vlm]`,
run nell'ambiente `[vlm]` — sono **tutti byte per byte identici**, sia in
Markdown sia in DocTags:

| File | run 1 (no-vlm) | run 2 (no-vlm) | run `[vlm]` |
|---|---|---|---|
| `granite_diagrammi.md` | `3c5be08127b5…` | `3c5be08127b5…` | `3c5be08127b5…` |
| `granite_diagrammi.doctags.txt` | `fb32d5c16192…` | `fb32d5c16192…` | `fb32d5c16192…` |
| `granite_mockup.md` | `25af5e148c38…` | `25af5e148c38…` | `25af5e148c38…` |
| `granite_mockup.doctags.txt` | `e0ddb0058554…` | `e0ddb0058554…` | `e0ddb0058554…` |

Il punteggio del cancello si riproduce identico su run 2: **2/2 tabelle,
75/75 celle dati, 9/9 intestazioni**. Con `temperature=0.0` il determinismo era
atteso, ma finché non lo si misura resta un'assunzione: ora è un riscontro.

**Il pin della revisione è effettivo, e c'è una prova indipendente.** Nella cache
esiste **un solo snapshot**, quello di `982fe3b4…`, e **non esiste alcun file
`refs/main`**: il ref mobile non è mai stato risolto. Con `HF_HUB_OFFLINE=1`, se
Docling avesse usato il proprio default `main` la corsa sarebbe fallita — come in
effetti fallì al primo tentativo, quando lo snapshot era incompleto. La spec
espone `revision = 982fe3b4…` contro il default `main` di Docling.

*Nota sugli hash*: `granite_report_run2.json` riporta per il Markdown lo SHA-256
della **stringa in memoria** (LF), non del file su disco (CRLF su Windows). Non è
confrontabile con `sha256sum`; i valori della tabella sopra sono quelli dei file.
Per i DocTags il campo è invece calcolato sui byte del file e coincide.

Questa è la combinazione usata per il pilot. **Non risolve la forcella licenze**
del prerequisito 1 della sessione 2: la rimuove dal ramo Transformers, senza
dire nulla su altri percorsi.

### Ambiente e riferimento completo del modello

| Voce | Valore |
|---|---|
| Piattaforma | `x86_64-pc-windows-msvc`, CPython 3.14.6, uv 0.11.28 |
| Catena | file di requisiti a 162 pacchetti negli artefatti — **è quella** l'unità riproducibile, non `docling==2.126.0` |
| Modello | `ibm-granite/granite-docling-258M` @ **`982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe`**, Apache-2.0 |
| Revisione | risolta oggi da `main`: **coincide** con quella registrata dalla sessione 2; passata esplicitamente, non lasciata al ref mobile |
| Peso | repo 529,9 MB; `model.safetensors` 515,1 MB; cache di sessione 506 MB |
| Pipeline | `VlmPipeline`, spec `GRANITEDOCLING_TRANSFORMERS`, `InferenceFramework.TRANSFORMERS`, `AUTOMODEL_IMAGETEXTTOTEXT`, risposta `DOCTAGS` |
| Opzioni | `scale=2.0`, `max_new_tokens=8192`, `temperature=0.0`, prompt `"Convert this page to docling."` |
| Acceleratore | `AcceleratorDevice.CPU`, `num_threads=4`; `torch.get_num_threads()=3` |
| torch | 2.13.0+cu126, `cuda_available=True` **ma non usata**: il difetto torchvision `+cpu` della sessione 2 resta non toccato |

### Verità di riferimento: i numeri della baseline reggono, ma erano incompleti

Le quattro pagine sono state renderizzate con pypdfium2 (scale 3, 1786×2526) e
**lette come immagini**, con ritagli 2× sulle celle ambigue. Il livello di testo
del PDF non è stato usato per costruire la verità.

**I 75/9 sono confermati**: registro diagrammi 5×4 = 20 celle dati + 4
intestazioni, registro mockup 11×5 = 55 + 5. Totale **75 celle dati, 9 di
intestazione, 2 tabelle**.

Due riscontri che la baseline non aveva registrato:

1. **Pagina 1 di entrambi i documenti contiene una terza struttura tabellare**,
   «Regole di organizzazione», 3×2 senza riga di intestazione. La formula «due
   tabelle» contava solo i registri di pagina 2. Misurata a parte: **non altera i
   criteri 75/9**, fissati prima di questa sessione.
2. **`diag_6_2_hitl_checkpoints.svg.svg` ha davvero due estensioni** nella fonte
   (verificato su ritaglio 2×). Normalizzarla a `.svg` conta come valore alterato.

Normalizzazioni **dichiarate prima della misura** (N1 soft-wrap di colonna,
N2 cella «Formato / peso» a due valori logici, N3 confronto letterale con
`Finalita` senza accento, N4 markup ignorato, N5 doppia estensione intoccabile).

### Confronto sui medesimi input

| Misura | Loader PDF attuale (pypdf) | Intake attuale (MarkItDown) | **Docling/Granite grezzo** | Granite + refine |
|---|---:|---:|---:|---:|
| Tabelle complete | **0/2** | **0/2** | **2/2** | **2/2** |
| Celle dati corrette | 0/75 | 0/75 | **75/75** | **75/75** |
| Celle di intestazione | 0/9 | 0/9 | **9/9** | **9/9** |
| Heading per documento | 0 | 1, dal nome file | **4**, tutti livello 2 | 5, di cui 2 inventati |
| Titoli inventati | 0 | 1 (`catalogo_…_normativi`) | **0** | 2 (`Scopo`, titolo alterato) |
| Contenuto fuori tabella | **12/12 e 12/12** | 12/12 e 10/12 | 12/12 e **8/12** | 9/12 e **5/12** |
| Arredo di pagina residuo | 3/3 | 3/3 | **0/3** | **0/3** |
| Domande PDF derivabili | **0/8** | **0/8** | **6/8** | **6/8** |

Nessuno dei due percorsi attuali produce una tabella: pypdf linearizza le celle
una per riga, MarkItDown emette per il solo registro diagrammi una riga di
intestazione corretta seguita da prosa e separatori spuri, e per il mockup
nemmeno quella. **I valori ci sono quasi tutti in entrambi; è l'associazione a
mancare**, ed è esattamente ciò che le domande misurano.

### I difetti del candidato, che le tabelle non mostrano

Fuori dai due registri, Granite ha prodotto tre alterazioni **verificate a
livello di DocTags**, quindi del modello e non dell'esportazione:

1. **Valore fabbricato.** Nella pagina 1 del mockup, dove la fonte ha la banda
   `11` / `4` / `SVG + HTML`, Granite emette
   `<code><loc_52><loc_142>…<_SQL_>REGOLE DI ORGANIZZAZIONE</code>`: una stringa
   in maiuscolo che **in quella forma non compare da nessuna parte nella pagina**,
   classificata come blocco di codice SQL. I tre valori reali **spariscono**.
2. **`interfacce` → `interface`** nel corpo di pagina 1 del mockup.
3. **`[schermata]` → `[schemata]`** nella prima regola del mockup.

Entrambi i percorsi attuali **conservano correttamente** `interfacce` e
`schermata`; pypdf conserva anche tutti i valori della banda. Su questa pagina
la baseline è più fedele del candidato.

Un quarto riscontro è **comune ai tre motori** e non è imputabile a Docling:
l'a-capo di colonna dentro i nomi di file sopravvive come spazio
(`diag_0_3_modules_relations_map .svg`). N1 lo perdona nel confronto, ma il
nome **non è utilizzabile alla lettera** a valle: viene dal livello di testo del
PDF, non dal parser.

### Refine: zero scarti, e contenuto perso lo stesso

Eseguito localmente con `core/intake_refine` e Ollama `qwen3.5:9b`,
`window_chars=5000` da `rag_config.yaml`, sull'output **grezzo** del candidato:

```text
diagrammi: {"windows":1,"windows_kept_raw":0,"windows_too_short":0,"windows_too_long":0,
            "chars_in":1582,"chars_out":1499,"elapsed_seconds":10.3}
mockup:    {"windows":1,"windows_kept_raw":0,"windows_too_short":0,"windows_too_long":0,
            "chars_in":2184,"chars_out":2131,"elapsed_seconds":15.6}
```

**0/2 finestre scartate, di nuovo** — e nel frattempo il refine ha **cancellato
l'intera banda KPI dei diagrammi** (`5`, `1`, `artefatti cartella sorgente
formato`), che nel grezzo c'era; ha **inventato** l'heading `Scopo` e i titoli
`Catalogo diagrammi normativi` e `Catalogo mockup normative` (la fonte dice
`Catalogo diagrammi` e `Catalogo mockup`); ha **inventato le intestazioni**
`# | Regola | Descrizione` per una tabella che nella fonte non ne ha. I due
registri sono invece **passati intatti**: 75/75 anche dopo il refine.

Questa è la dimostrazione operativa di 1d: contare gli scarti non misura la
fedeltà. Il premio previsto dal piano — **ottenere il parsing richiesto senza
ricorrere al refine** — è stato ottenuto: il grezzo vale già 75/75.

### Tempi, memoria, risorse

| Misura | Valore |
|---|---:|
| `import docling` | 6,91 s |
| Costruzione del `DocumentConverter` | 0,06 s |
| **1ª conversione** (diagrammi, 2 pagine) | **284,5 s** |
| 2ª conversione nello stesso processo (mockup, 2 pagine) | 290,6 s |
| Ripetizione su diagrammi, modello già caldo | **273,7 s** |
| Ripetizione su mockup | 301,2 s |
| **Caricamento iniziale, per differenza** | **≈ 11 s** su ~285 |
| RSS: avvio → dopo import → **picco** | 21,3 → 701,9 → **1756,0 MB** |
| Download pesi, prima volta | 103 s |

**Il caricamento non è il costo**: è l'inferenza. Circa **142 s per pagina** su
CPU, contro **0,1 s per documento** dei due percorsi attuali — un fattore
dell'ordine di **3000×**. Su questo corpus (4 pagine) sono ~19 minuti; la stessa
misura non si estrapola a un corpus grande senza rifarla, e la GPU non è stata
provata perché `torchvision` è la ruota `+cpu` (difetto della sessione 2, non
corretto qui: correggerlo tocca `[tool.uv.sources]`).

### Qdrant: caduto a metà sessione, tornato prima della fine

Per buona parte del pilot Qdrant **non ha risposto**: container `Up 7 hours` ma
senza porte pubblicate (`PortBindings` malformato `{invalid IP 6333}`, nessun
listener su 6333) e `/readyz` muto **anche dall'interno del container**.
`health-before.json` di P0 lo dava `true` alle 15:24. Questa sessione **non ha
avviato né arrestato alcun processo preesistente**; il riscontro dello stato
degradato resta in `logs/qdrant-stato.txt`.

Verso la fine della sessione è comparso un **secondo** container,
`vibecraft-qdrant-1`, con la porta correttamente pubblicata su
`127.0.0.1:6333` — **non avviato da questa sessione**. Da quel momento le righe
di retrieval sono tornate misurabili e **sono state misurate**, invece di
restare dichiarate impossibili.

### Retrieval generale: nessuna perdita rispetto a P0

Server RAG avviato **da questa sessione** (e arrestato alla fine), indice
`v20260908T132451`, 250 chunk, 935 nodi, 1305 archi — gli stessi di P0.
`eval.run` lanciato con `--no-save` e **senza** `--check-regression`:
`eval/results/history.jsonl` verificato **invariato** per hash e numero di righe
(134) prima e dopo quel comando.

**`eval.run_multihop` invece ha appeso una riga**, e va detto perché il file era
già modificato rispetto a git. Non ha un interruttore per evitarlo: la scrittura
dello storico è parte dichiarata del suo funzionamento (`eval/run_multihop.py:28`).
Il file è passato da **134 a 135 righe**. La riga aggiunta è
`{"timestamp":"2026-09-08T15:13:52…","source":"multihop","multihop_recall@10":0.8538961038961039,"multihop_graph_exact":1.0}`
— **identica nei valori** alla precedente: nessuna deriva, solo un secondo
campione della stessa misura. **Non è stata rimossa**: cancellare un record di
eval autentico per far tornare un'affermazione del resoconto sarebbe peggio
dell'averlo scritto. Le modifiche preesistenti del manutentore sono intatte;
questa riga è in coda, ed è attribuibile a questa sessione.

| Metrica | P0 | Pilot | Esito |
|---|---:|---:|---|
| recall@1 | — | 70,7 % | — |
| **recall@2** | **0,827586** | **0,828** | **invariata** |
| recall@5 | — | 94,8 % | — |
| source_in_top3 | — | 89,7 % | — |
| mrr | — | 0,811 | — |
| **multihop, recall media A** | **0,854** | **0,854** | **invariata** |
| **multihop, B exact** | **6/6** | **6/6** | **invariata** |
| gate `--assert-min 0.75` | PASS | **PASS** | invariato |

Il pilot **non tocca l'indice**, quindi il risultato atteso era proprio questo:
serve come prova che nulla è stato mosso, non come merito del candidato.

### Retrieval PDF: nessuna perdita, ma la misura è satura

Quattro collection **sperimentali** `pilot_docling_<motore>`, create con
`qdrant-client` direttamente. Nessun alias, nessuna promozione, nessun contatto
con `vibecraft_events*`. Chunking con il `chunk_markdown` **di produzione**;
embedder `BAAI/bge-m3` **su CPU**, per non sfrattare Ollama dagli 8 GiB.

**Portata dichiarata**: solo vettore **denso**. Niente sparse, niente ColBERT,
niente re-ranking di grafo, niente pesi di autorità. È un proxy più stretto
della riga come è formulata, e va letto come tale.

| Motore | Chunk | Fonte attesa in top-3 | Risposta ancorata nel top-3 |
|---|---:|---:|---:|
| Loader PDF (pypdf) | 2 | **8/8** | 8/8 |
| Intake (MarkItDown) | 2 | **8/8** | 7/8 |
| **Docling/Granite grezzo** | 8 | **8/8** | **8/8** |
| Granite + refine | 10 | **8/8** | 6/8 |

**La presenza delle fonti è identica fra baseline e candidata: nessuna perdita.**
La riga del cancello è soddisfatta nella sua richiesta letterale.

Ma va detto che cosa **non** dimostra. Con **due soli documenti** nella
collection, «la fonte giusta è nel top-3» è vera quasi per costruzione: la
misura è **satura** e non discrimina fra i motori, nello stesso senso in cui
l'harness di eval segnala da sé le proprie metriche sature. E i baseline
producono **un unico chunk per documento**: l'intero documento viene recuperato
in blocco, quindi «risposta ancorata» per loro è quasi automatica. Le due
perdite reali (MarkItDown senza `2.4`, refine senza `artefatti` e
`aree funzionali`) sono perdite **di contenuto** avvenute in conversione, non
fallimenti di recupero.

L'unico riscontro non banale: Granite segmenta in **4 chunk per documento**
invece di 1, e **resta 8/8** — la sezionatura non ha spezzato l'ancoraggio.

### L'attribuzione resta non misurata

La riga chiede «stesse domande e modello di risposta; schermo più lettura
umana». I due PDF **non sono nell'indice di produzione** (0 chunk, confermato in
0.4 e ancora oggi) e le collection sperimentali non sono collegate a `/ask`:
non esiste, senza costruirlo, un percorso che produca risposte attribuite su
queste otto domande. **Non le viene assegnato un PASS**, e non lo riceve per
analogia dalle righe vicine.

### Esito riga per riga del cancello 1c

| Riga | Esito | Riscontro |
|---|---|---|
| Tabelle complete | **PASS** | 2/2, righe e colonne corrette |
| Celle | **PASS** | 75/75 dati, 9/9 intestazioni, nessun valore inventato **dentro le tabelle**; normalizzazioni dichiarate prima |
| Sezioni | **PASS con riserva** | 4 heading per documento, corrispondenti alla segmentazione preregistrata, **0 inventati**; gerarchia però **appiattita** a un solo livello |
| Refine | **ESEGUITO E REGISTRATO** | 0 scarti su entrambi, ripetuto sugli output candidati; non usato come misura di fedeltà, e infatti ha perso contenuto |
| Retrieval PDF | **PASS, misura satura** | fonte attesa in top-3: **8/8 baseline = 8/8 candidata**, nessuna perdita; ma 2 documenti non discriminano |
| Retrieval generale | **PASS** | recall@2 0,828, multihop A 0,854, B exact 6/6 — **identici a P0**; `run_multihop` ha appeso una riga a `history.jsonl` (134→135), coi medesimi valori |
| Attribuzione | **NON MISURATO** | i PDF non sono nell'indice e le collection sperimentali non sono collegate a `/ask` |

Il criterio di abbandono dice `NON_APPLICARE` anche se «**compaiono valori
inventati**». Dentro le tabelle non ne compaiono. Fuori dalle tabelle **sì**: il
blocco `REGOLE DI ORGANIZZAZIONE` classificato come SQL, al posto di tre valori
reali. Le due letture — la riga «Celle», che è esplicitamente sulle celle, e la
clausola di abbandono, che non è qualificata — portano a esiti diversi. **La
scelta fra le due è del manutentore**, non di questa sessione, che si ferma al
riscontro e non riscrive il criterio dopo aver visto i numeri.

### Limiti

- **Una sola piattaforma**: Windows x86_64. Linux e macOS restano senza esecuzione.
- **Retrieval misurato solo sul vettore denso**, in collection sperimentali con
  due documenti: misura satura, non discriminante, e non è lo stack di produzione.
- **Attribuzione non misurata.**
- **Suite applicativa non eseguita** sotto la catena candidata: la catena
  candidata vive in un venv isolato e `pytest` gira contro quello dell'applicazione.
- **Quattro pagine, due layout, generati dallo stesso template.** Il risultato
  non autorizza una dichiarazione generale sulle tabelle complesse, né rende
  vere le percentuali di benchmark pubbliche.
- **GPU non provata**, per il difetto `torchvision +cpu` ereditato.
- La misura di completezza per token corti (`4`, `5`, `11`) è affidabile solo
  con confine di parola: la prima passata, più permissiva, è conservata negli
  artefatti accanto a quella corretta.

### Decisioni aperte e prerequisiti per la sessione 4

1. **Licenze**: la forcella della sessione 2 **si restringe** — senza `[vlm]` i
   binari GPL non entrano nemmeno su disco, e Granite gira lo stesso. Resta da
   decidere formalmente, ma l'opzione «rinunciare all'extra» ora ha una misura.
2. **La fabbricazione contro la clausola di abbandono**: decisione del manutentore.
3. **Attribuzione** e **suite applicativa sotto la catena candidata**: le due
   verifiche rimaste. Per l'attribuzione serve decidere *dove* indicizzare i PDF
   convertiti senza toccare la produzione. Da notare che i due container Qdrant
   ora coesistono (`qdrant` degradato, `vibecraft-qdrant-1` sano): va sistemato
   prima di misurare qualunque altra cosa.
4. **Costo di conversione**: 142 s/pagina su CPU. Prima di integrare, decidere se
   Docling è il motore di **default** o un motore **opt-in per i soli PDF con
   tabelle**, e se dirottare `torchvision` sull'indice CUDA — che è una modifica
   alle dipendenze applicative, non del pilot.
5. **F3 resta aperta** per macOS, invariata.

**Il PASS strutturale non autorizza la promozione.** L'integrazione applicativa
non è iniziata: nessun file di `core/`, `api/`, `rag_config.yaml`,
`pyproject.toml` o `uv.lock` è stato toccato.

## Pilot StandardPdfPipeline — 2026-09-09

**Verdetto: NON_APPLICARE** per questa configurazione, distinto dal pilot
Granite precedente. Su `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
Docling 2.126.0 `StandardPdfPipeline`, backend `ThreadedDoclingParseDocumentBackend`,
CPU, OCR disattivato e TableFormer ACCURATE con cell matching hanno prodotto
2/2 tabelle, 75/75 celle dati e 9/9 intestazioni, offline e identiche byte per
byte in due processi nuovi. La candidata conserva i valori che Granite aveva
perso e non inventa il blocco SQL, ma crea l'H2 non preregistrato `SVG + HTML`
e conserva solo per posizione l'associazione delle bande KPI: 6/8 domande sono
derivabili. Il criterio sezioni del cancello 1c fallisce; retrieval, attribuzione,
golden generale e suite applicativa non sono stati eseguiti dopo l'abbandono.
Nessuna integrazione, modifica all'indice o collection. Prove, catena, revisioni,
pesi, hash, output e limiti sono in
`rag/eval/results/pilot_docling_standard_20260909-095127/RESOCONTO.md`.

## Pilot Docling — candidato finale, gerarchia nativa — 2026-09-09

**Verdetto: BLOCCATO**, con una sola verifica mancante e il materiale per
sbloccarla già pronto. Tutti i criteri tecnici misurabili in sessione sono
superati; resta l'**attribuzione**, che il cancello 1c vuole «schermo più
**lettura umana**» e che un agente non può firmare al posto del manutentore.
Non è `NON_APPLICARE`: nessun criterio misurato è fallito.

**Perimetro:** riguarda il percorso su **documenti rigenerati con il template
corretto**, non i PDF originali immutabili né PDF esterni generici.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push, PR. `AGENTS.md` assente.
Artefatti: `rag/eval/results/pilot_docling_finale_20260909-110000/`.

### La gerarchia si risolve con uno stage nativo, non con codice nostro

Cercata prima nel sorgente installato, come previsto: esiste
`docling/models/stages/heading_hierarchy/`, con `HeadingHierarchyOptions` già
cablate in `StandardPdfPipeline`, **disattivate per default**. Assegnano il
rango con precedenza bookmark → numerazione → **stile**. I nostri PDF non hanno
segnalibri né numerazione: decide lo stile (25 / 16 / 11 pt del template), cioè
un'informazione verificabile della fonte.

Le uniche due differenze rispetto alla configurazione congelata sono dichiarate:
`heading_hierarchy_options.enabled=True` e `generate_parsed_pages=True`.

| | livello | atteso |
|---|---|---|
| `Catalogo diagrammi` / `Catalogo mockup` | **1** | titolo del documento |
| `Regole di organizzazione` | **2** | stesso rango di Registro |
| `Registro dei file` | **2** | stesso rango di Regole |
| `Percorso sorgente` | **3** | rango inferiore |

`scripts/check_hierarchy_rule.py` lascia tre assert superati: la regola tiene su
un PDF con **vocabolario estraneo ai cataloghi**; due intestazioni di stile
**identico** ricevono lo **stesso** livello invece di essere ordinate a caso;
e con `use_style=False` la gerarchia **collassa**, il che prova che il segnale
operativo è lo stile e non un default fortunato.

### Input nuovi, tenuti separati dagli originali

Candidati `e34c1366…77cc542` (diagrammi) e `7725b280…4a2832b` (mockup), contro
gli originali `9c0d51c5…` e `443ecfca…`, che restano nel corpus **non toccati**.
Un assert del verificatore fallisce se il candidato legge un originale.
Domande, celle, normalizzazioni N1–N5 e soglie sono copiate **senza modifiche**.

### Fedeltà, riproducibilità, risorse

2/2 tabelle, **75/75** celle dati, **9/9** intestazioni, **8/8** domande
derivabili, 4/4 titoli attesi, **0** inventati, gerarchia corretta, nessun
contenuto fabbricato; `interfacce`, `[schermata]`, `11`, `4`, `SVG + HTML` tutti
presenti. I 3 frammenti mancanti sono **arredo** di pagina. Controllo visivo
delle quattro pagine eseguito.

Registrato perché visibile a valle, benché il criterio congelato sia soddisfatto:
le tre coppie KPI restano corrette e adiacenti ma **due condividono un
paragrafo** (`1 cartella sorgente SVG formato`). Nessun valore perso, nessuna
coppia rotta: è raggruppamento di reading-order.

Due esecuzioni offline in processi nuovi: Markdown e JSON **identici byte per
byte**. Tempi 13,5 / 4,8 s (run 1) e 12,7 / 4,2 s (run 2). **RSS picco 1588 MB**
con **campionamento continuo a 0,05 s** — metodo dichiarato, non un massimo a
pochi checkpoint.

### Retrieval e attribuzione con la pipeline applicativa completa

Due stack sperimentali sullo **stesso corpus** (42 documenti, i due PDF corretti
in **entrambi**) e stessi parametri calibrati; unica differenza, come i PDF
vengono letti — 14 righe in `_read_pdf` della **sola copia sandbox** del
candidato, con la conversione cercata per SHA-256. `rag/core/chunking.py` del
repository verificato invariato.

Separazione: Qdrant sperimentale su `:6401` (container avviato e poi arrestato
da questa sessione), collection `pilot_baseline_events` / `pilot_candidate_events`,
porte 8101/8102, `database/` e `docs/` in sandbox fuori dal repository. Il
container Qdrant preesistente era di nuovo senza porta pubblicata: **non è stato
riavviato né rimosso**.

| Misura | baseline (pypdf) | candidato (Docling) |
|---|---:|---:|
| recall@2 / mrr | 82,8 % / 0,811 | 82,8 % / 0,811 |
| multihop recall A / B exact | 0,854 / 6/6 | 0,854 / 6/6 |
| fonte attesa in top-10 (8 domande) | **8/8** | **8/8** |
| risposte con tutti i valori attesi | **7/8** | **8/8** |

Golden e multihop identici fra gli stack e identici a P0: il golden non contiene
i PDF, quindi vale come **non regressione**, non come merito. Sul supplemento
PDF il candidato non perde nulla e l'unica risposta incompleta è del **baseline**.

**L'attribuzione resta pendente.** Il giudice N3 archiviato non è qualificato a
certificare risposte nuove (20/24 in-sample, non supera S6) e sostituirlo con un
altro modello è vietato. È stata fatta la verifica **deterministica** dei passi
citati e la lettura puntuale; il pacchetto per il manutentore è in
`review/PACCHETTO_REVISIONE.md`, con due punti segnalati (`pdf-diag-4` attribuisce
la banda KPI alla sezione sbagliata; `pdf-mock-3` descrive la schermata con
dettagli presi da un documento di specifica).

### Suite, compatibilità, licenze

Suite sotto la catena candidata su codice applicativo **non modificato**:
**1339 passati, 3 falliti**. La stessa suite, stesso sandbox, sotto la catena
**applicativa** dà gli **stessi 3 fallimenti**: sono artefatti dello stato
sperimentale (indice a versione unica, collection rinominata, archivio
attribuzione che punta all'indice di produzione), **non** causati da Docling.
`ruff` pulito sugli script; `--check-integrity` exit 0.

`torch 2.13.0+cu126`, marker CUDA, `onnxruntime`, `transformers`, ranking e
parametri calibrati **invariati**. Il gruppo dev ha aggiunto solo `pytest`,
`ruff`, `iniconfig`.

**Licenze migliorate rispetto alle sessioni precedenti:** i pesi effettivi sono
`docling-layout-heron` **apache-2.0** e `docling-models` (TableFormer ACCURATE)
**cdla-permissive-2.0**. **Granite non è usato** e la catena resta **senza
`[vlm]`**: i binari GPL di `av` non sono nemmeno su disco. La forcella licenze
della Sessione 2 **non si applica** a questa configurazione.

Test nativi eseguiti **solo** su `x86_64-pc-windows-msvc`. Linux e macOS restano
con risoluzione e wheel, non esecuzione.

### Esiti precedenti conservati

Granite (`NON_APPLICARE`, contenuto inventato) e StandardPdfPipeline sui PDF
originali (`NON_APPLICARE`, falso titolo e associazioni KPI perse) **restano
tali**: questa sessione non li ribalta, cambia gli **input**.

### Cosa manca, e cosa andrà implementato dopo un PASS

Manca **solo** la lettura di attribuzione del manutentore. Dopo un PASS
andranno implementati: il template corretto e la rigenerazione dei cataloghi con
nuova baseline; Docling come secondo motore con la configurazione sopra e i pesi
pinnati; gli interruttori `intake.conversion_engine` e
`retrieval.pdf_conversion_engine`; la dipendenza dichiarata dal file di
requisiti congelato, non da `docling==2.126.0`. Il difetto `torchvision +cpu`
resta aperto e irrilevante finché il motore gira su CPU.

Dettaglio completo, script, manifest, output e inventario SHA-256 in
`rag/eval/results/pilot_docling_finale_20260909-110000/RESOCONTO.md`.

## Pilot Docling — chiusura: audit, schermo citazioni, suite, attribuzione — 2026-09-09

**Verdetto: BLOCCATO**, e non per una firma mancante. Il resoconto precedente
diceva «manca solo la lettura umana»: **non era sostenuto**. Rimisurando su tre
passate per stack è emerso un **difetto di risposta confermato e riproducibile**
(`pdf-diag-3` fallisce 0/3 in **tutti** gli stack), e la correzione generale
tentata è **NON_APPLICARE**.

Perimetro invariato: **documenti rigenerati con il template corretto**, non i
PDF originali immutabili né PDF esterni generici.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push, PR. `AGENTS.md` assente.
Artefatti: `rag/eval/results/pilot_docling_chiusura_20260909-160000/` (94 file).

### Cinque cose distinte

| | esito |
|---|---|
| conversione Docling | **verificata**, riusata dopo controllo di integrità e corrispondenza |
| correzione del template | prerequisito, **non ancora implementata in produzione** |
| correzione generale di generazione (variante di prompt) | **NON_APPLICARE** |
| qualità e attribuzione finali | 7/8 stabile ovunque; **un difetto confermato**; sezione imperfetta in **entrambi** gli stack |
| autorizzazione all'integrazione | **non concessa** |

### Tre difetti negli STRUMENTI della sessione precedente

1. **Estrattore delle citazioni ri-scritto peggio.** `eval_stack.py` usava
   `[«"']([^«»"']{12,200})[»"']`: l'apostrofo ASCII come **delimitatore**, cioè
   ogni elisione italiana (`l'`, `dell'`, `all'`) apriva o chiudeva una
   citazione — da lì `) dedicata all`. Soglia in caratteri anziché in parole.
   **12 delle 15 «citazioni» archiviate erano artefatti di parsing.** Corretto
   riusando `eval.attribution.quoted_spans`, che il repository ha già e che
   `tests/test_attribution.py` copre; chiamanti verificati prima.
   `scripts/check_citazioni.py`: 7 casi su 7 (apostrofi interni, virgolette
   doppie, caporali, Markdown, delimitatore non chiuso, chiusura orfana,
   citazione inventata che **resta** non verificabile).
2. **Il corpus di verifica non conteneva i PDF.** La mappa dei chunk cercava un
   campo `chunk_id` che in `chunks.json` è la **chiave**: restava vuota, ogni
   `testo` archiviato è `""`, e i PDF non entravano mai nel corpus. Nessuna
   citazione tratta da un PDF poteva risultare verificata. Riletti i chunk
   dall'indice davvero interrogato, una citazione del baseline passa da
   `unverifiable` a `verified`.
3. **«8/8 completa» era un `in` su sottostringa**, con `["5", "1"]` come valori
   attesi di `pdf-diag-4`: due cifre nude.

Audit completo delle **sedici** risposte archiviate su sette assi separati in
`audit/AUDIT_MISURE_PRECEDENTI.md`. Originali intatti: inventario di 61 file,
zero alterati.

### La suite è verde, senza toccare un'asserzione

| suite | test | falliti | saltati |
|---|---:|---:|---:|
| catena **candidata** (`venv-novlm`) | 1342 | **0** | **0** |
| catena **applicativa** | 1342 | **0** | **0** |
| catena applicativa **+ variante** | 1342 | **1** | 0 |

Le tre cause erano tutte **ambientali**, riprodotte prima di correggere:
la fixture del reconciler nomina `vibecraft_events__*` alla lettera mentre
l'alias è parametrizzato (`parse_qdrant_collection_version` → `None` con la
collection rinominata); il test di rollback ha bisogno di una versione
**precedente**; l'archivio N3 portava il `superseded_by` della produzione.
Correzioni: **istanza Qdrant propria per stack** (porta e volume) invece della
rinomina — l'isolamento è per endpoint —, indice costruito **due volte**,
`superseded_by` coerente col sandbox. Nessuno skip, nessun xfail, nessuna
asserzione toccata; `core/retrieval.py`, `core/chunking.py` e `rag_config.yaml`
dei sandbox byte-identici al repository. `VIBECRAFT_REQUIRE_QDRANT=1`, quindi
**zero saltati** significa che i test con Qdrant reale sono girati davvero.

### `pdf-diag-3`: causa accertata, e non è Docling

Sonda diagnostica (prove **aggiuntive**, domande congelate intatte): chiedendo
«quanti **KB** occupa il file…» o «il valore della colonna «Formato / peso»…»,
**entrambi** gli stack rispondono **19.5 KB**. Il dato c'è, è nel contesto, è
recuperabile: la conversione ha fatto il suo lavoro.

Con la parola «peso» nella domanda congelata, **nessuno dei due stack** risponde
in **nessuna** delle tre passate: agganciano «peso» alla scala di autorevolezza e
concludono `0.30` / `0.87` / `0.90`, o dichiarano il dato assente. La forma è
quella di `[CLASSE-FONTI]` in `core/retrieval.py`. **Collisione lessicale nella
generazione**, identica nei due stack.

Stessa natura per `pdf-diag-4`: il PDF produce **un solo chunk**, la sua
`section` è `Catalogo diagrammi` e l'intestazione di blocco è corretta — la
risposta la cita testualmente e poi attribuisce la banda KPI a «Regole di
organizzazione» (che nel Markdown viene **dopo**) e a un «Indice operativo» che
non esiste. Non segmentazione, non metadati: **generazione**.

### Variante `[ATTRIBUZIONE-DICHIARATA]` — NON_APPLICARE

Correzione minima e generale: restringere l'**ambito** di `[CLASSE-FONTI]` (la
graduatoria governa i vincoli, non i dati che una fonte riporta sui propri
artefatti) e vincolare l'indicazione del luogo all'intestazione di blocco.
Nessuna regola sui due PDF, nessun riferimento al golden, nessun cambio di
ranking o parametri calibrati, nessun modello remoto, nessuna governance rimossa.

1. **Non corregge il difetto**: `pdf-diag-3` resta 0/3 in entrambi gli stack.
2. **Non sposta l'attribuzione** oltre la variabilità dello strumento.
3. **Sfonda un budget dichiarato**:
   `test_costo_fisso_del_prompt_entro_il_budget` fallisce, prompt fisso da ~1000
   a **~1180 token stimati** — il budget che esiste perché la crescita del prompt
   portò `/ask` al 104% di `num_ctx` (A1).

Miglioramento registrato ma insufficiente: documento atteso nominato **21/24**
contro 15/24 e 17/24. **L'esito NON_APPLICARE resta** anche se una variante
successiva superasse i controlli.

### Confronto finale, tre passate per stack

Cache di `/ask` **spenta** (`VIBECRAFT_ASK_CACHE_SIZE=0`): `cached: false` su
tutte e 96 le risposte. Tutte le passate conservate.

| misura (24 = 8 domande × 3 passate) | baseline | candidato |
|---|---|---|
| valori attesi presenti | **21/24** | **21/24** |
| fonte attesa nel contesto inviato | **24/24** | **24/24** |
| documento atteso nominato | 17/24 | 15/24 |
| dato presente dichiarato assente | `pdf-diag-3` | `pdf-diag-3` |
| sezione attribuita male | 4 domande | 3 domande |
| astensioni · errori di trasporto · troncamenti | 0 · 0 · 0 | 0 · 0 · 0 |
| passate instabili | **0** | **0** |
| golden `recall@2` · multihop A · B exact | 0.828 · 0.854 · 6/6 | 0.828 · 0.854 · 6/6 |

**Il «candidato 8/8 contro baseline 7/8» della sessione precedente era una
passata singola fortunata**: su tre passate i due stack sono **7/8 entrambi**,
con la stessa domanda mancante. Golden e multihop identici fra loro e a P0: non
regressione, non merito.

I nove «troncamenti» segnalati dal predicato grezzo sono, all'ispezione, risposte
**complete** che finiscono con una riga di tabella o con `46.4 KB`: predicato
corretto, **zero troncamenti**.

### Lo schermo di attribuzione, e i suoi limiti

Non è il giudice N3 (nessun modello giudica; l'archivio storico **non** è usato
come prova). Conta se la risposta nomina il documento normativo per **nome o per
classe** — il repository considera valido «nella specifica [REQUIREMENTS]»
(`normalize_verdict`). Esiti: 5/8, 5/8, 5/8, 4/8 nelle quattro configurazioni.

**Limite dichiarato**: una passata su otto casi. Con lo strumento letterale
superato, lo stesso stack ha dato 3, 3, 3 e 5 in quattro esecuzioni identiche:
variabilità ±2/8. Lo schermo **non rileva regressioni** attribuibili a Docling o
alla variante e **non ha la risoluzione per certificare** alcunché. La prima
versione contava solo i nomi di file e dava 3/8 al candidato contro 7/8 al
baseline: sarebbe stata una conclusione falsa — misurava lo **stile**.

### Che cosa manca, esattamente

1. **Una decisione del manutentore su `pdf-diag-3`**: un dato che una fonte
   riporta sui propri artefatti deve poter essere risposto anche quando la
   parola della domanda collide col lessico di governance? Se sì, la correzione
   va progettata dentro il budget del prompt fisso o fuori dal prompt; se no, va
   dichiarato che l'Ispettore di Governance non risponde a domande di dato.
2. **La lettura umana dell'attribuzione** (`review/PACCHETTO_REVISIONE.md`): sei
   domande segnalate in cima, tutte le risposte di tutte le passate, la sezione
   **effettiva** dal contesto realmente inviato.
3. **L'implementazione del template corretto** con nuova baseline.

### Isolamento e stato del repository

Due istanze Qdrant sperimentali con porta e volume propri (`:6401`, `:6402`);
produzione (`:6333`) **mai contattata**, container `qdrant`,
`vibecraft-qdrant-1` e `neo4j` **mai riavviati né rimossi**. Al termine:
stesso identico insieme di file modificati e non tracciati di inizio sessione,
più la sola nuova directory datata; hash invariati per `core/retrieval.py`,
`core/chunking.py`, `rag_config.yaml`, `golden_attribution.yaml`,
`golden_set.yaml`, `pyproject.toml`, `uv.lock`; `history.jsonl` invariato (135
righe, `57b1eecdd1c23983`) — golden e multihop con `--no-save`, dentro i sandbox.
`ruff` pulito su tutti gli script.

Dettaglio completo in
`rag/eval/results/pilot_docling_chiusura_20260909-160000/RESOCONTO.md`.


## Correzione peso/Authority e attribuzione — 2026-09-09

**Verdetto: BLOCCATO — REVISIONE UMANA PENDENTE**, e non per una firma mancante:
resta un **difetto confermato**. Perimetro: solo ambiente isolato; nulla
integrato in produzione. Ramo `codex/evoluzione-p0`, HEAD
`011e264c554895c651f0eba1dccb74bc4dc10f74`, invariato. `AGENTS.md` assente.
Resoconto completo, artefatti e inventario SHA-256 in
`rag/eval/results/fix_attribuzione_20260909-183000/`.

I due verdetti restano distinti, e nessuno autorizza l'integrazione:

| perimetro | esito |
|---|---|
| **correzione generale** (variante V2 del prompt) | tecnicamente eleggibile — budget rispettato, nessuna regressione misurata, netto miglioramento dell'attribuzione al documento — ma **non risolve `pdf-diag-3`** |
| **percorso Docling** sui documenti rigenerati | invariato: Docling non causa e non corregge i due difetti, identici nei due parser |

### La correzione: riscrittura di `[CLASSE-FONTI]`, non un blocco nuovo

Causa accertata di D1: `[CLASSE-FONTI]` interpola numeri nudi
(`NORMS (0.80) > METHODOLOGY (0.50)`) **senza mai dire che cosa misurino**, e
ordina di attribuire «un vincolo, una soglia, una severita'» alla fonte piu'
autorevole. Alla domanda «con quale peso?» il modello offre il coefficiente.

La variante V2 **riscrive quel testo** (7 righe sostituite da 7, diff esatto in
`diff/variante_v2.diff`): i numeri graduano **solo le fonti**; valori, quantita',
dimensioni, formati e unita' **si leggono nel testo del blocco**; la provenienza
si indica **con l'intestazione**, senza nominare sezioni che non dichiara, con
ripiego sul **solo documento** quando la sezione non e' determinabile.
`[PRECEDENZA-FONTI]`, `[CITAZIONE-VERIFICABILE]`, `[REGOLA-ASTENSIONE]`,
`[FONTE-CODICE]` e `[REGOLA-DIZIONARIO-RIGIDO]` **invariate alla lettera**.

**Budget: 954 → 987 token stimati su 1000.** E' la **stima ~3 caratteri/token**
del progetto, **non un conteggio esatto**. E' la differenza decisiva rispetto a
`[ATTRIBUZIONE-DICHIARATA]` (~1180 token), che resta **NON_APPLICARE** e non e'
stata riattivata.

Vincolo scoperto: `test_build_ask_prompt_snapshot_testuale` fotografa alla
lettera il prompt **base**, quindi la correzione vive **interamente** dentro
`[CLASSE-FONTI]`. **Limite dichiarato:** con fonti tutte sullo stesso livello
`authority_scale` restituisce `[]` e la regola non compare — innocuo per D1,
lacuna reale per l'attribuzione di sezione. Tutte e otto le domande congelate
hanno contesti a piu' classi, verificato.

### Controlli di governance preregistrati (10 casi, nomi e valori estranei ai cataloghi)

Tre passate per prompt. **Originale 25/30, variante 27/30.** L'unico segnale
sopra il rumore e' **G10 — collisione peso/Authority: 0/3 → 2/3**: il difetto e'
riprodotto e **stabile** col prompt originale, e la correzione lo **riduce senza
eliminarlo**. G8/G9 oscillano di ±1 in entrambe le direzioni (variabilita' dello
strumento). Nessuna regressione su precedenze, autorevolezza richiesta, dato
assente e istruzioni malevole: **3/3 in entrambi**. La soluzione non converte
ogni domanda con «peso» in una domanda di dimensione — G3 e G4 restano 3/3 e G2
(peso **fisico** in kg) migliora.

Due **falsi negativi dello strumento** trovati e corretti (G7 segnava FAIL una
risposta che *citava* l'iniezione rifiutandola; G6 cercava la sezione come
sottostringa nel corpo invece che in posizione di attribuzione). Storico
conservato, tutte le configurazioni rivalutate uniformemente.

### Confronto fattoriale — 4 configurazioni × 3 passate × 8 domande congelate

Domande, attese e soglie invariate (`sha256 22eede74…`, identico alle due
sessioni precedenti). Corpus dei due sandbox identico (60 file, 0 differenze):
l'unica variabile e' il parser. Cache di `/ask` spenta, `cached: false` su tutte
e 96 le risposte, tutte conservate.

| misura (24 = 8 × 3) | A pypdf+orig | B docling+orig | C pypdf+V2 | D docling+V2 |
|---|---:|---:|---:|---:|
| valori attesi presenti | 22/24 | 21/24 | 22/24 | 21/24 |
| fonte attesa nel contesto | 24/24 | 24/24 | 24/24 | 24/24 |
| **documento atteso nominato** | 13/24 | 14/24 | **21/24** | **17/24** |
| dato presente dichiarato assente | diag-3, mock-4 | diag-3 | diag-3 | diag-3 |
| affermazioni di sezione errate | 5 | 5 | 6 | 5 |
| astensioni · errori · troncamenti | 0·0·0 | 0·0·0 | 0·0·0 | 0·0·0 |

**`pdf-diag-3` non e' risolto.** `19.5 KB` compare in 1/3 passate di A (ma
etichettato «Peso (Authority)», cioe' la citazione incidentale che il criterio
congelato esclude), 0/3 di B, 1/3 di C, 0/3 di D. Il nome a doppia estensione
`.svg.svg` e' conservato **12/12**. La passata **C p1** e' il caso limite —
associa il file a «Formato / peso: SVG, 19.5 KB» e nomina il documento, poi
aggiunge un paragrafo che nega un valore di *authority* — e il giudizio spetta al
manutentore.

**`pdf-diag-4` non si riproduce**, nemmeno in A e B con le istruzioni originali:
valori corretti 12/12, nessuna attribuzione a «Regole di organizzazione», nessuna
«Indice operativo». Non e' un effetto della correzione: e' un **difetto
instabile**, e va registrato come tale.

**Attribuzione di sezione: la correzione non funziona** (5·5·6·5). Segnalato, non
corretto, un **sospetto difetto dello strumento** — alcune voci hanno
`sezione_dichiarata == sezione_reale` e trattano come «valore non trovato»
l'etichetta di classe (`[SENZA CLASSE]`, `CODICE ESISTENTE`).

**Retrieval invariato:** golden `recall@2` **0.828** e multihop **0.854 · 6/6**,
identici in A, B **e C** — quest'ultima eseguita apposta per **provare** che la
variante non tocca il retrieval invece di dedurlo. Identici a P0.

**Suite: 1342 test, 0 falliti, 0 errori, 0 saltati** in tutte e quattro le
configurazioni, con `VIBECRAFT_REQUIRE_QDRANT=1`. Nessuna asserzione modificata,
nessuno skip o xfail aggiunto. `ruff`: pulito. Sandbox ripristinati byte-esatti.

### Isolamento e conservazione

Due Qdrant sperimentali con porta e volume propri (`:6401`, `:6402`), avviati e
riarrestati da questa sessione; produzione (`:6333`) **mai contattata**; `qdrant`,
`vibecraft-qdrant-1` e `neo4j` non toccati. PDF dei sandbox rigenerati, con hash
**distinti** da quelli di produzione. Undici invarianti applicativi confrontati
prima/dopo: **tutti invariati**, `history.jsonl` fermo a **135 righe**. Il
repository al termine ha lo stesso insieme di file di inizio sessione piu' la
sola nuova directory datata.

### Che cosa manca

La **lettura umana** dei punti elencati in `review/DA_CONTROLLARE.md`: il caso
limite `C p1` di `pdf-diag-3`, le affermazioni di sezione, il sospetto difetto
dello strumento, il nome alterato di `pdf-mock-4`, e la conferma che le nuove
citazioni del documento in C siano sostenute. Senza, il verdetto resta
**BLOCCATO**; e un'approvazione non annullerebbe i difetti gia' dimostrati.


## Generazione e attribuzione — diagnosi conclusiva — 2026-09-09 (sera)

**Verdetto: BLOCCATO**, e la decisione mancante si chiama con precisione: ridurre
il contesto che `/ask` invia (`CODE_CONTEXT_TOTAL_SNIPPETS`,
`GRAPH_CONTEXT_MAX_CHUNKS`, `GOVERNED_MAX_CHUNKS` — parametri calibrati, fuori
perimetro) oppure adottare un modello con miglior richiamo su contesto lungo
(R29). **Non e' una firma mancante**, e non viene chiesta una revisione umana per
sanarlo. Artefatti in `rag/eval/results/fix_generazione_20260909-200000/`.
Ramo `codex/evoluzione-p0`, HEAD `011e264c…`, invariato. `AGENTS.md` assente.

### `pdf-diag-3` non e' correggibile dal prompt, ed e' misurato

Otto formulazioni provate una alla volta (W1, W2, x1–x5, piu' la serializzazione
E1), tutte non risolutive, tutte fallite **allo stesso modo**. La causa non e' la
formulazione:

| contesto inviato | prompt (token stimati) | `19.5 KB` nella risposta |
|---|---:|---|
| solo il blocco del PDF | 1 541 | **3/3** |
| PDF + 2 blocchi | 2 906 | 2/3 |
| PDF + 4 | 4 953 | 1/3 |
| PDF + 8 | 6 940 | 1/3 |
| PDF + 22 (reale) | 11 616 | **0/3** |

Con il **prompt originale, invariato**, il modello risponde correttamente appena
il contesto scende. Togliere un singolo blocco non corregge (README 0/3, Authority
Boost 1/3, codice 0/3); riordinare non corregge (E1 0/3). Il blocco del PDF
contiene la tabella con l'intestazione `| … | Formato / peso |` e la riga con
`SVG 19.5 KB`: il contesto non e' la causa, la sua **dimensione** lo e'.

Composizione del contesto: la fonte che risponde e' il **4,7 %** (pypdf) o
**6,2 %** (Docling) del totale; il **20 %** e' codice TypeScript scelto per
prossimita' nel grafo, non per pertinenza alla domanda.

### I due difetti hanno cause diverse

**D2, attribuzione di sezione — causa nel contesto, e diversa per parser.** pypdf
produce `… § (documento)` (`core/chunking.py:172,197`): nessuna sezione e'
dichiarata, quindi nessuna affermazione di sezione e' sostenibile e il modello ne
inventa una. Docling dichiara `§ Catalogo diagrammi`, corretta. Con lo schermo
corretto Docling **dimezza** gli errori di sezione (2 contro 5).

**D1, peso/Authority — causa nella diluizione**, sopra.

### Lo schermo delle sezioni era difettoso: riprodotto, corretto, record aggiornato

`assi.controlla_sezioni` trattava le **etichette di classe** delle intestazioni di
blocco (`[SENZA CLASSE]`, `CODICE ESISTENTE`, `METHODOLOGY`) come «valori
attribuiti alla sezione»: un'affermazione di sezione **corretta** risultava
errata. Quattro casi minimi lo riproducono (3/7 sullo strumento vecchio), lo
schermo corretto passa 7/7 con tre controlli di non regressione, e
`classifica_riferimento()` separa ora classe · documento · sezione · citazione ·
descrizione.

Rivalutate uniformemente le 96 risposte archiviate del confronto A/B/C/D:

| cfg | presenza | documento | sez. err. vecchio | sez. err. corretto |
|---|---|---|---:|---:|
| A pypdf + originali | 22/24 | 13/24 | 5 | **5** |
| B Docling + originali | 21/24 | 14/24 | 5 | **2** |
| C pypdf + V2 | 22/24 | 21/24 | 6 | **6** |
| D Docling + V2 | 21/24 | 17/24 | 5 | **2** |

**21 → 15: sei erano artefatti**, tutti nelle configurazioni Docling. La
conclusione precedente («la correzione non migliora l'attribuzione di sezione»)
era in parte un artefatto dello strumento.

### W1 — NON_APPLICARE, perche' regressiva

W1 tocca il prompt **base** (autorizzato in questa sessione): «rispondi alla
domanda posta» al posto di «estrai contratti e vincoli», regola di provenienza
legata all'intestazione di blocco, `[CLASSE-FONTI]` riscritta. Ridondanze rimosse
prima di aggiungere testo; budget **954 → 994 token stimati** su 1000 (stima, non
conteggio esatto). Snapshot aggiornato correttamente e verificato a parte —
suite 1342/0/0 con snapshot aggiornato, 1 solo fallimento (lo snapshot stesso)
senza.

Migliora gli assi di attribuzione (documento 18→20/24, errori di sezione 9→7) ma
**regredisce la governance**: 22/30 contro 25/30 dell'originale, con `G9`
(grandezza in una fonte poco autorevole) che crolla **3/3 → 0/3**, e `G10` che
resta 0/3. Per il criterio dichiarato e' **NON_APPLICARE**, non «tecnicamente
eleggibile». Il batch fattoriale non e' stato eseguito su di essa: il mandato
vieta grandi batch su una variante che fallisce il controllo mirato.

Restano NON_APPLICARE e non riattivate `[ATTRIBUZIONE-DICHIARATA]` e V2.

### Suite, lint, invarianti

1342 test, **0 falliti, 0 saltati** su sandbox baseline e candidato con
`VIBECRAFT_REQUIRE_QDRANT=1`; 1342/0/0 anche con W1 + snapshot aggiornato.
Nessuna asserzione indebolita, nessuno skip o xfail. `ruff` pulito. Sandbox
ripristinati byte-esatti. Invarianti applicativi confrontati prima/dopo: tutti
invariati; `history.jsonl` fermo a 135 righe; Qdrant di produzione mai contattato.

### La proposta, e l'avvertenza

Subordinare il blocco `CODICE ESISTENTE` alla pertinenza rispetto alla **domanda**
invece che alla prossimita' nel grafo (`api/routes_retrieval.py:493`) toglierebbe
~20 % del contesto — ma **da solo non basta**: senza codice `pdf-diag-3` resta
0/3. Servirebbe scendere verso ~3 k token, cioe' toccare anche
`GOVERNED_MAX_CHUNKS` e `GRAPH_CONTEXT_MAX_CHUNKS`. Questi sono accoppiati ad
`AUTHORITY_BOOST_ALPHA` nella griglia congiunta di S11: abbassarne uno per far
passare una domanda, senza rifare la griglia e senza rimisurare golden e multihop,
sarebbe esattamente il difetto che S11 ha chiuso.


## Selezione del contesto di /ask — 2026-09-10

**Verdetto: BLOCCATO**, e la decisione mancante e' cambiata rispetto a ieri
perche' le prove di oggi hanno **confutato** la causa che avevo indicato.
Serve decidere se autorizzare una modifica **mirata a `[CLASSE-FONTI]`**: e' la
sola leva che le misure sostengono ancora, e sta fuori dall'autorizzazione di
questa sessione (prompt congelato all'originale). Artefatti in
`rag/eval/results/sel_contesto_20260910-090000/`. Ramo `codex/evoluzione-p0`,
HEAD `011e264c…`, invariato. `AGENTS.md` assente. Nulla integrato.

### Tre correzioni alla mappa dei parametri

1. **`governed_max_chunks` non tocca `/ask`**: sta solo in `routes_pipeline.py`
   (canvas/propose). I blocchi semantici di `/ask` li governa `top_k`. Ieri gli
   attribuivo il ~66 % del contesto di `/ask`: sbagliato.
2. **I tetti di composizione non sono assi della griglia S11.** Il sorgente di
   `eval/calibrate_authority.py` lo scrive: quattro assi, **tutti pesi di
   ranking**, e «`graph_context_max_chunks` NON e' in questa griglia». Hanno un
   harness proprio (`eval/calibrate_graph_context.py`). Ieri dicevo che toccarli
   avrebbe richiesto di rifare la griglia congiunta: non e' vero.
3. **`top_k` ha default 5** (`api/models.py:19`); l'harness del pilot usa **10**.
   Tutte le misure di contesto delle sessioni precedenti sono al doppio del
   default di produzione.

### L'ipotesi «diluizione del contesto» e' CONFUTATA

| configurazione | prompt (token stimati) | `pdf-diag-3` |
|---|---:|---|
| `top_k` 10, attuale | 11 443 | 0/3 |
| `top_k` 10 + S2 | 9 297 | 0/3 |
| `top_k` 5 (default produzione) | 8 502 | 0/3 |
| `top_k` 5 + S2 | 6 260 | 0/3 |
| diagnostico aggressivo (`top_k` 3, grafo 1, niente codice) | **3 440** | **0/3** |

Ieri l'ablazione dava 3/3 a ~1 500 token: ma quella selezione era **privilegiata**
— teneva il solo blocco del PDF, cioe' sapeva gia' quale fonte rispondeva. Con
una selezione **legittima** alla stessa taglia il difetto resta. L'ipotesi era un
artefatto della sonda e va ritirata.

**Cio' che resta, a parita' di contesto** (6 260 token): con `[CLASSE-FONTI]`
`19.5 KB` 0/3 e coefficiente 3/3; **senza** la scala, `19.5 KB` **2/3** e
coefficiente 1/3. La scala consegna al modello un numero gia' pronto per quel
documento (`SENZA CLASSE` → 0.30), e lui lo offre come «peso».

### S2 — pertinenza sul ponte IMPLEMENTS: verificata, senza regressioni, non risolutiva

`/ask` ha due rami di codice: quello **semantico** ha gia' un pavimento di
pertinenza alla domanda (0.45); il **ponte IMPLEMENTS** filtra solo sul **peso
dell'arco**. Misurato: sulle 8 domande PDF il codice viene **10 su 10** dal ponte
e **0** dal ramo semantico; su golden e multihop il ramo semantico ne porta 8 su
12 — quel codice serve.

S2 applica al ponte **lo stesso segnale e la stessa funzione** del ramo semantico
(`search_code_symbols` ristretta con `subset_idx`). Diff **additivo: 47 righe, 0
rimosse**. Default **0.0 = disattivato**, contesto byte-identico alla produzione.
Soglia scelta **0.35** su golden/multihop, non sulle domande PDF: a 0.45 si
perderebbero 4 blocchi di codice sul golden e 3 sul multihop.

**Invariante:** il testo documentale del contesto e' byte-identico a S0 in **74
contesti su 74**. S2 non puo' far uscire una fonte documentale dalla finestra.

Il controllo preregistrato **S1** (ridurre i tetti) taglia **meno** (27 407 contro
25 313 caratteri) e costa un blocco via grafo: il guadagno di S2 non e' «meno
contesto», e' «contesto piu' pertinente». **S3** (pavimento sul ramo grafo) e' un
**no-op** su questo corpus a 0.3 e 0.5: scartata.

**Un difetto mio, trovato dalla suite.** La prima versione scartava i simboli
**senza vettore denso**, che non sono valutabili: due test comportamentali sono
diventati rossi. Il filtro ora e' **fail-open** sui non valutabili, e i test sono
tornati verdi **correggendo il filtro, non le asserzioni**. Controllo eseguibile
dedicato: 7/7.

### Regressioni

golden `recall@2` **0.828 PASS** e multihop **0.854 · 6/6 PASS** (percorso reale,
identici a S0 e a P0); copertura golden **58/58** invariata; holdout separato di 7
domande nuove — comportamento del codice, ponte spec→codice, fattuale a classe
singola e a classi diverse, multi-documento, dato assente — **14/14 con S0 e
14/14 con S2**; suite **1342/0/0** sia con S2 spenta sia attiva; `ruff` pulito;
budget del prompt **954/1000** (invariato, prompt congelato). Parametri S11 non
toccati. Produzione mai contattata; `history.jsonl` fermo a 135 righe.

Latenza: mediane 3,3–4,3 s fra le quattro configurazioni, con variabilita' fra
passate dello stesso ordine della differenza. **Non e' un guadagno leggibile** e
non viene presentato come tale.


## Tentativo di chiusura a PASS — 2026-09-10 (pomeriggio)

**Esito: PASS non raggiunto, e non dichiarato.** Con l'autorizzazione a modificare
in modo mirato `[CLASSE-FONTI]` ho provato **17 varianti di prompt** su due taglie
di contesto: nessuna soddisfa il criterio congelato di `pdf-diag-3`. Artefatti in
`rag/eval/results/pass_20260910-140000/`. Ramo `codex/evoluzione-p0`, HEAD
`011e264c…`, invariato. Prompt di produzione non modificato.

### Il tetto delle varianti di prompt

Massimo raggiunto: **2/3 sulla presenza del valore**, **0 passate** che
soddisfano il criterio. Le risposte migliori trovano e associano correttamente il
dato, ma lo presentano come dettaglio dentro una conclusione che nega:

> «… e' **diag_6_2_hitl_checkpoints.svg.svg** … Tuttavia, il contesto **non
> riporta** un peso (authority) … La tabella elenca solo: … **Formato/peso
> (dimensione file): `19.5 KB`**»

E' la «citazione incidentale mentre la conclusione parla di Authority» che il
criterio esclude: lo schermo la conta come fallimento e ha ragione.

### La famiglia che va meglio e' esclusa per due ragioni verificabili

Le varianti «scala senza numeri» arrivano a 2/3, e vanno scartate perche':
1. rompono un test **comportamentale** — `tests/test_ask_authority_prompt.py:67`
   asserisce `"NORMS (0.80) > METHODOLOGY (0.50)" in prompt`;
2. tolgono una capacita' di governance misurata — il caso **G3** chiede la classe
   prevalente **e il suo coefficiente**, che senza numeri non e' disponibile.

### La causa, isolata definitivamente

Diagnostico di soffitto: tolti dal contesto i due blocchi che **insegnano la
glossa** «peso = autorevolezza» — `README.md § Contenuto` (tabella
documento→authority) e `spec_graph_rag_ingestion.md § 4. Requisiti di Retrieval e
Authority Boost` (che **definisce** «il peso della classe»):

| condizione | contesto | `19.5 KB` |
|---|---:|---|
| senza i due blocchi + scala senza numeri + regola campo | 4 273 tok | **3/3** |
| senza i due blocchi, **prompt ORIGINALE** | 4 213 tok | **2/3** |

**Decidono quei due blocchi, non il prompt e non la taglia del contesto.** Ma non
sono escludibili da alcuna regola generale di pertinenza: sono recuperati *perche'
la domanda contiene «peso»* e rispetto a quel token sono pertinenti. Escluderli
richiederebbe di conoscere in anticipo l'accezione voluta, cioe' la risposta
attesa. Verificato anche che `README.md § Contenuto` **non** e' un blocco
passeggero (non compare fra i cinque piu' frequenti in nessuna delle tre serie):
il retrieval e' corretto, e' il **lessico del corpus** a essere ambiguo.

### Che cos'e' il difetto

Una **collisione di termini nel corpus**: il catalogo intitola la colonna
«Formato / peso» e ci mette `SVG 19.5 KB`; il corpus normativo usa «peso» per il
coefficiente di autorevolezza e lo definisce in una spec REQUIREMENTS. `pdf-diag-2`,
che chiede «formato **e** peso», **passa** stabilmente: nominare anche il formato
toglie l'ambiguita'.

### Le vie che restano, tutte fuori dal mio perimetro

1. **disambiguare il corpus** (colonna del catalogo o glossario, che il sistema
   gia' usa con `[REGOLA-DIZIONARIO-RIGIDO]`) — tocca template e PDF di produzione;
2. **cambiare il modello che risponde** — escluso dal mandato (R29 riguarda il
   giudice, non chi risponde);
3. **ri-scopare il cancello**, registrando `pdf-diag-3` come limite noto —
   cambia il criterio, e cambiarlo per far passare il caso e' vietato.

Resta acquisito **S2** (pertinenza sul ponte IMPLEMENTS): verificata, senza
regressioni, non risolutiva. E resta il **diagnostico di soffitto**, che rende
inutile riprovare varianti di prompt: il tetto e' noto e la causa e' altrove.


## Via 1 — disambiguazione del corpus: eseguita e refutata — 2026-09-10 (sera)

**Esito: NON_APPLICARE per la via 1; PASS non raggiunto.** Ma la sessione chiude
una domanda aperta e **refuta il diagnostico di soffitto** della mattina: la
parola ambigua nel corpus **non era la causa**. Artefatti in
`rag/eval/results/corpus_disambigua_20260910-170000/`. Produzione mai toccata,
sandbox riportato allo stato di partenza.

### Tre forme, sempre piu' forti

**A — qualificare il termine.** «peso» → «peso di autorevolezza» nelle due sole
righe che lo usavano nudo (`spec_graph_rag_ingestion.md`), piu' una voce nel
glossario dei sinonimi. **Peggiora**: il modello riprende la frase nuova e la
applica all'artefatto («il peso di autorevolezza di questo diagramma e' 0.30»).
La voce di glossario **non arriva mai in finestra**: quel chunk non e' recuperato
per questa domanda. Ritirata byte per byte.

**B — rinominare la colonna del catalogo.** `«Formato / peso»` →
`«Formato / peso (dimensione file)»`, con la parola «peso» che **resta** perche'
la domanda congelata la usa. Cataloghi rigenerati col generatore vero e
reindicizzati: **1/3**. Due riscontri tecnici utili: il catalogo **vive dentro la
cartella che inventaria** e rigenerandolo si aggiungerebbe come sesto artefatto
(l'originale fu generato prima di esistere); e pagina 2 e' rimasta **identica**,
41 righe dati sui diagrammi e 85 sui mockup confrontate una per una — nessuna
deriva dell'inventario, `19.5 KB`/`46.4 KB`/`3.4 KB` al loro posto.

**C — una parola, un concetto.** Tolta «peso» dall'accezione di autorevolezza in
**tutto** il corpus, sostituita con `Authority` (il nome che il progetto usa gia'
nei metadati, nella tabella del README e nel codice). Controllo automatico: **0
residui**. **0/3**, e le risposte peggiorano in chiarezza: il modello deriva
`0.30` **senza appoggiarsi ad alcun testo del corpus**.

### La prova decisiva

Corpus completamente disambiguato, stesso contesto, unica variabile la scala:

| condizione | prompt | `19.5 KB` | coefficiente | pulite |
|---|---:|---|---|---|
| corpus pulito **+ `[CLASSE-FONTI]`** | 9 303 tok | 0/3 | 3/3 | 0/3 |
| corpus pulito, **senza scala** | 9 081 tok | **2/3** | 1/3 | **1/3** |

**La causa e' la scala di `[CLASSE-FONTI]` nel prompt**, che consegna
`SENZA CLASSE (0.30)` per il documento stesso su cui verte la domanda.

**Correzione al resoconto della mattina:** avevo attribuito la glossa ai blocchi
`README.md § Contenuto` e `spec_graph_rag_ingestion.md § 4` perche' togliendoli
si arrivava a 3/3. Era una lettura sbagliata: togliendo il README spariva anche
la sua **tabella numerica** di Authority, ma la sorgente del numero e' la scala.
Con corpus pulito e scala presente il difetto e' identico.

### Perche' chiude anche le altre vie

Togliere i numeri dalla scala e' l'unica leva che sposta l'ago, e resta bloccata
da `tests/test_ask_authority_prompt.py:67` (test comportamentale che asserisce
`"NORMS (0.80) > METHODOLOGY (0.50)"`) e dal caso **G3**, che chiede la classe
prevalente **e il coefficiente**. E anche pagando quel prezzo si arriva a **1/3
pulite**, non a 3/3: non e' un PASS comunque.

### Ripristino

Corpus ritirato byte per byte (4 file), PDF riportati ai candidati `sourcefix`
(`e34c1366…`, `7725b280…`), indice in **rollback** a `v20260909T101204`,
integrita' `ok` e non stale. Le tre versioni create qui restano in
`database/versions/` non promosse. Produzione, prompt, codice, parametri
calibrati e domande congelate invariati; `history.jsonl` fermo a 135 righe.
