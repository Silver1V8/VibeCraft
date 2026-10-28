<p align="center">
  <img src="rag/static/vibecraft-logo.svg" width="880" alt="VibeCraft, Graph RAG locale">
</p>

<p align="center">
  <em>Cita la norma che vale, non quella che somiglia di più.</em>
</p>

<p align="center">
  <a href="https://github.com/Silver1V8/VibeCraft/releases"><img src="https://img.shields.io/github/v/release/Silver1V8/VibeCraft?style=flat-square&labelColor=04140a&color=0f3d20&label=release" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licenza-Apache--2.0-0f3d20?style=flat-square&labelColor=04140a" alt="Licenza Apache-2.0"></a>
  <img src="https://img.shields.io/badge/python-3.14-0f3d20?style=flat-square&labelColor=04140a" alt="Python 3.14">
  <img src="https://img.shields.io/badge/100%25-locale-0f3d20?style=flat-square&labelColor=04140a" alt="100% locale">
  <img src="https://img.shields.io/badge/Qdrant%20%C2%B7%20Ollama%20%C2%B7%20BGE--M3-0f3d20?style=flat-square&labelColor=04140a" alt="Qdrant, Ollama, BGE-M3">
  <a href="https://github.com/Silver1V8/VibeCraft/pkgs/container/vibecraft"><img src="https://img.shields.io/badge/immagine-GHCR-0f3d20?style=flat-square&labelColor=04140a" alt="Immagine su GHCR"></a>
</p>

<p align="center">
  <img src="assets/readme/hero.it.svg" width="880" alt="RAG generico contro VibeCraft: il RAG generico cita la metodologia perché somiglia di più alla domanda; VibeCraft pesa l'autorità e cita la specifica che stabilisce la regola.">
</p>

<p align="center">
  <strong>Casi avversariali giusti al primo posto: da 0 su 5 a 4 su 5.</strong><br>
  <strong>recall@1 0,690 → 0,741 &middot; recall@10 0,983 → 1,000</strong><br>
  <sub>Stesso sistema con l'autorità quasi spenta (α 0,1) e calibrata (α 0,3), golden set di 58 casi, 7 settembre 2026 (S11). Fuori campione, a k=1: +0,038, positivo su 5 seed su 5. <a href="#i-numeri">Dettagli</a>.</sub>
</p>

<p align="center">
  <sub>Italiano &middot; <a href="README.en.md">English</a></sub>
</p>

---

Lo conosci. È il documento di metodologia: scritto bene, discorsivo, pieno delle parole giuste. Spiega la regola meglio di chi l'ha stabilita. Ed è proprio per questo che un RAG qualunque cita lui al posto della norma.

**VibeCraft sa chi comanda.** È una console Graph-RAG per la governance documentale: indicizza i documenti normativi e il codice che dovrebbe implementarli, e quando risponde pesa quanto è autorevole ogni fonte, quale prevale quando due si contraddicono e quanto ci si può fidare del cammino sul grafo che l'ha portata lì.

Tutto gira in locale. I documenti non escono dalla macchina.

## I numeri

Il golden set contiene casi **avversariali**, costruiti apposta: per ognuno una fonte a bassa autorità (una nota di metodologia, un file storico senza classificazione) somiglia alla domanda più della norma che risponde. Ognuno è verificato eseguendo la query. Sono il test che un RAG generico sbaglia per costruzione.

| Misura del 7 settembre 2026, 58 casi | recall@1 | recall@2 | recall@5 | recall@10 | avversariali al primo posto |
|---|---|---|---|---|---|
| Autorità quasi spenta (α 0,1) | 0,690 | 0,862 | 0,948 | 0,983 | **0 su 5** |
| **Autorità calibrata (α 0,3), in produzione** | **0,741** | 0,862 | **0,966** | **1,000** | **4 su 5** |

α non è stato scelto a intuito: griglia congiunta di 2.160 punti, 5-fold × 5 seed, con il vincitore confermato fuori campione. E a volte la misura ha detto di no: la moltiplicazione piena (α 1), quella che la norma prescriveva, costava 15 punti di recall@5. Si è emendata la norma, non i numeri. Storia completa in [ADR 0002](rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md) e nel blocco `authority:` di [rag_config.yaml](rag/rag_config.yaml).

**Le risposte sono ancorate alle fonti, non garantite.** Citazioni, risultati parziali e punti aperti restano da verificare, e il retrieval non promette di aver trovato tutto ciò che il corpus contiene.

## Come funziona

<p align="center">
  <img src="assets/readme/flow.it.svg" width="880" alt="Due flussi. /ask: domanda, retrieval ibrido, rerank ColBERT, moltiplicatore di autorità, grafo con fiducia sul cammino, risposta con fonti; le domande strutturali vanno direttamente al grafo. /pipeline: Explore, Canvas, Propose, Validate, Archive.">
</p>

- **Autorità dichiarata.** Ogni documento dichiara la sua classe e il suo peso nel frontmatter. Il peso entra nella formula del ranking, non solo nell'interfaccia. La freschezza non è autorità: una data recente non fa vincere nessuno.
- **Precedenza.** Quando due documenti si contraddicono, vince quello che la dichiarazione di precedenza indica.
- **Fiducia sul cammino.** Ogni arco del grafo ha una natura (strutturale, curata, inferita), e una fonte raggiunta per un cammino fragile pesa meno.
- **Il grafo risponde da solo.** «Quali relazioni ha X», «cosa impatta se modifico Y»: risposte dal grafo, senza chiamare l'LLM.
- **Dalla domanda alla modifica.** La pipeline porta un cambiamento dall'intervista alla specifica con scenari Gherkin. L'agente parte in modalità agentic solo dopo che il contratto corrente ha passato la validazione.

## Cosa c'è dentro

| | |
|---|---|
| **`/ask`** | retrieval ibrido (denso + lessicale + rerank ColBERT) ripesato per autorità, più il codice che implementa le sezioni recuperate |
| **Pipeline** | Explore → Canvas → Propose → Validate → Archive, ancorata ai documenti normativi; il canvas impara dalle review archiviate |
| **Intake & Import** | conversione locale con anteprima e review in staging: Docling per i PDF, Excel letto direttamente, MarkItDown, LibreOffice per DOC/PPT |
| **Mappe** | mappa del grafo, Semantic Map e Impact Ripple sul corpus e sul codice indicizzato |
| **Progetti** | progetti separati con cartelle, indici e namespace Qdrant propri |
| **Agenti** | Claude Code e Ollama integrati; Codex e Cursor con export del prompt e MCP esterno |
| **MCP** | server locale di sola lettura: retrieval, ricerca nel codice, interrogazione del grafo |
| **Indice** | versioni blue/green, eval gate prima della promozione, rollback verificato, delta copy-on-write |

## Per chi è, e per chi no

| Conviene se | Non conviene se |
|---|---|
| il corpus è normativo e stratificato, e la risposta sta in più documenti che possono contraddirsi | i documenti sono pochi e tutti li conoscono già |
| serve una risposta **verificabile**, con la fonte e il peso che l'ha fatta vincere | serve un assistente conversazionale rapido |
| i dati non devono uscire dalla macchina | va bene un servizio esterno |

Su `/ask` tiene un filo breve per progetto con le citazioni accumulate: non è un chatbot generico. Non interroga più progetti insieme e non ha permessi per utente. Nasce per girare in locale o su una rete controllata.

## Avvio rapido

Con Docker, dalla radice del repository:

```bash
git clone https://github.com/Silver1V8/VibeCraft.git
cd VibeCraft

# La chiave API è obbligatoria in Docker. Se .env esiste già, aggiungi solo la variabile.
docker run --rm python:3.14-slim python -c "import secrets; print('VIBECRAFT_API_KEY=' + secrets.token_urlsafe(32))" > .env

docker compose --profile cpu up -d qdrant ollama
docker compose exec ollama ollama pull qwen3.5:9b      # 6,6 GB, una volta sola
docker compose --profile cpu up -d
```

Poi apri **http://127.0.0.1:8000**. La console chiede la chiave al primo accesso e la ricorda in quel browser.

Non servono documenti tuoi per provarlo: il progetto iniziale contiene già una [baseline di governance](templates/docs/README.md) da indicizzare.

```bash
docker compose --profile cpu run --rm app-cpu python index.py   # scarica bge-m3, 4,3 GB
```

GPU NVIDIA, Ollama sull'host, installazione nativa, immagine pronta su GHCR, aggiornamenti e migrazioni: **[INSTALL.md](INSTALL.md)**. Se qualcosa non parte, `uv run python scripts/doctor.py` da `rag/` controlla tutto e per ogni problema stampa il rimedio.

## Requisiti, senza indorare la pillola

| | |
|---|---|
| Download | circa **11 GB**: `bge-m3` 4,3 GB + `qwen3.5:9b` 6,6 GB, più i modelli Docling per i PDF |
| Disco consigliato | ~20 GB |
| GPU NVIDIA | facoltativa, ma cambia molto: embedding a 46 chunk/s contro **1 chunk/s** su CPU |
| Indicizzazione completa (612 elementi) | ~13 s con GPU, **~10 min** su CPU |

Senza GPU funziona tutto. Reindicizzare diventa un'operazione da fare con calma, ma le domande restano usabili: l'embedding della query costa circa un secondo, dentro i ~30 s che l'LLM locale impiega comunque a rispondere.

## Sicurezza

- Ascolta su **`127.0.0.1`** per default: raggiungibile solo da questa macchina.
- Se lo esponi in rete, imposta `VIBECRAFT_API_KEY`: le funzioni che hanno senso solo in locale si spengono da sole, il resto lo protegge la chiave.
- Header `Host` verificato contro il DNS rebinding, niente iframe, Content-Security-Policy senza script inline.
- Ogni rotta HTTP e ogni tool MCP sono mappati in [SECURITY_SURFACE.md](rag/SECURITY_SURFACE.md).

## Documentazione

| | |
|---|---|
| [INSTALL.md](INSTALL.md) | installazione, progetti, aggiornamenti, scalabilità, configurazione, MCP e sicurezza in dettaglio |
| [Percorso guidato](rag/static/manuale/percorso-guidato.html) | un caso reale dall'inizio alla fine, per chi deve decidere se adottarlo |
| [Manuale utente](rag/static/manuale/manuale-utente.html) | i controlli della console, capitolo per capitolo |
| [rag/README.md](rag/README.md) | architettura, retrieval, pipeline, indicizzazione |
| [rag/adr/](rag/adr/README.md) | le decisioni architetturali e il perché |
| [archive/README.md](archive/README.md) | le evidenze storiche delle misure: non è il prodotto, e c'è un [clone leggero](INSTALL.md#prima-di-clonare) che le salta |
| `/infografica` | con il server acceso, il flusso di interrogazione illustrato |

I manuali esistono anche in inglese: [guided walkthrough](rag/static/manuale/percorso-guidato.en.html), [user manual](rag/static/manuale/manuale-utente.en.html).

## FAQ

**I miei documenti escono dalla macchina?**
No, con Ollama. Il provider si sceglie per singolo step in `rag_config.yaml`: se uno step usa Claude, il contesto di quello step va al provider.

**Funziona senza GPU?**
Sì. Le domande restano veloci quanto l'LLM; è il reindex completo che passa da secondi a minuti.

**I miei documenti sono scritti male. Li sistema?**
No. VibeCraft li rende trovabili, non li migliora. Documenti scritti male, risposte scritte male.

**Perché non basta un RAG normale?**
Perché in un corpus normativo il testo che spiega una regola usa lo stesso vocabolario di quello che la stabilisce, ed è più discorsivo. Vince il confronto semantico e perde quello che conta.

**Perché Python 3.14?**
Non per le feature. Su Windows un lock a `>=3.12` biforca `onnxruntime` e gonfia il lockfile. uv scarica da sé la 3.14. Decisione in [DISTRIBUTION.md](rag/adr/DISTRIBUTION.md).

**Posso fidarmi ciecamente delle risposte?**
No, e diffida di qualunque sistema che ti dica il contrario. Le risposte portano le fonti apposta: controllale.

## Licenza

[Apache-2.0](LICENSE). I pesi dei modelli scaricati a runtime (`bge-m3`, `qwen3.5`) hanno ciascuno la propria licenza: verificala prima di un uso commerciale.

<sub>Stato documentato: `main`, 28 ottobre 2026.</sub>
