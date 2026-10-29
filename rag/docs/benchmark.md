Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Benchmark baseline

## Benchmark baseline

[scripts/bench.py](../scripts/bench.py) misura le latenze delle vie critiche (server
acceso) e salva uno snapshot in `eval/results/bench_<timestamp UTC>.json`:

```bash
uv run python scripts/bench.py                    # senza full rebuild (default)
uv run python scripts/bench.py --url http://127.0.0.1:8000
uv run python scripts/bench.py --with-rebuild      # accoda anche un full rebuild (lento: minuti)
```

Per il carico concorrente read-only di `/ask`, che non esegue reindex, usare il percorso
separato con un servizio isolato e una provenienza del server distinta dal checkout client.
Per questa cohort avviare il server dedicato con `VIBECRAFT_ASK_CACHE_SIZE=0`:

```bash
uv run python scripts/bench.py --concurrency-bench --url http://127.0.0.1:18000 \
  --concurrency 1 4 8 --requests 30 --warmup 3 --response-mode json \
  --queries adr/horizontal-bench/queries.json --out adr/horizontal-bench/run \
  --metadata adr/horizontal-bench/server-metadata.json --cache-cohort cache-off --timeout 300
```

Scrive raw JSONL e un summary per ogni livello; cache off e cache calda vanno eseguite in
cohort distinte e dichiarate con `--cache-cohort`. In modalità stream,
`--cancel-probes 3` aggiunge tre sonde per k che chiudono la risposta dopo il primo
testo, salvate separatamente dai percentili principali. `--sample-gpu` abilita il
campionamento opzionale della memoria GPU dell’intero dispositivo condiviso;
`--api-pid` e `--engine-pid` campionano RSS del processo e dei suoi figli.

Cosa misura, in ordine: `GET /api/retrieve` su 10 query del golden-set (p50/p95);
`POST /ask` su 10 query del golden-set (p50/p95/max del totale + medie del
breakdown — vedi nota sotto); `GET
/api/graph/semantic-map` (latenza end-to-end + `truncated`); un reindex incrementale
NO-OP reale (nessun file toccato: misura solo l'overhead fisso del job, dal journal
`GET /api/reindex`); un full rebuild, **solo con `--with-rebuild`** (di default
`skipped`, è un'operazione lunga e costosa). Se una dipendenza è giù la sezione
corrispondente è `skipped` con motivo: il bench è una **misurazione**, mai un gate —
exit code sempre 0.

**Nota sui campi di latenza di `/ask`:** dal F3 il breakdown è **anche nella
risposta JSON**, non solo nel log strutturato di fine richiesta (osservabilità M3,
vedi [api/routes_retrieval.py](../api/routes_retrieval.py)): `/ask` restituisce
`latency: {retrieval_ms, generation_ms, total_ms}` accanto a `request_id` e
`index_version`. Il bench legge questi campi dalla risposta e, per robustezza,
affianca `avg_latency_total_ms_client` misurato lato client.

### Budget di latenza di `/ask` — misurato, non stimato

Baseline del **2026-09-04** — run locale `bench_20260904T075210Z`, il cui JSON **non è
versionato** (vedi `eval/results/.gitignore`: i numeri della baseline vivono qui e nel
messaggio di commit). Server locale, `qwen3.5:9b` su RTX 3070 Ti, `top_k` di default
(5), cache di `/ask` fredda, 10 query del golden-set:

| | valore |
|---|---|
| `p50` totale | **24.1 s** |
| `p95` totale | **32.0 s** |
| max osservato | 33.7 s |
| media retrieval | 0,50 s |
| media generation | 22,2 s |

**Dove va il tempo: il 97,8% è la generazione LLM.** Il retrieval — dense + sparse +
rerank ColBERT + espansione sul grafo, cioè tutto ciò che questo repository
implementa — pesa mezzo secondo su trenta. Ogni lavoro di latenza che non tocchi il
modello o l'hardware ha quindi un tetto del 2,2%: è il numero da rileggere prima di
ottimizzare il ranking "perché sembra lento".

Il p95 su 10 campioni sta di fatto sul massimo osservato — è un limite del campione,
non della misura, e va letto come "l'attesa peggiore vista in questa run", non come un
percentile stabile. La console non lascia comunque quell'attesa muta: il loader di
`/ask` conta i secondi trascorsi, così 30 secondi restano distinguibili da un blocco.
Questa baseline storica precede lo **streaming incrementale** e misura il JSON unico
con risposta, contesto grafo e punteggi. Non misura il tempo al primo testo della
modalità streaming descritta sotto, né il carico concorrente.

### Delta reale isolato

La modalità `--real-delta` genera un corpus sintetico in un checkout dedicato con
`docs/`, `code/` e `rag/database/` inizialmente vuoti. Il checkout deve essere
esattamente `rag/eval/results/<run>/sandbox/experiment`; la collection Qdrant deve
iniziare con `sidecar_0628_`. Server e Qdrant usano solo `127.0.0.1:18000` e
`127.0.0.1:16333`. Eseguire un processo fresco per ciascuna delle nove famiglie
`N=10,30,100 × docs,code,mixed`, con output e collection nuovi per famiglia:

```bash
python -B scripts/bench.py --real-delta --checkout C:/path/to/rag/eval/results/<run>/sandbox/experiment --output-dir C:/path/to/rag/eval/results/<run>/delta-output --n 10 --mode docs --k 0,1,10 --repeats 5
```

Per `N=100` aggiungere `100` a `--k`; `k>N` fallisce. Il driver avvia bootstrap
incrementale e server HTTP reali, poi per ogni campione verifica job, readiness,
integrità e query concorrenti. Ripristina byte sorgenti, artefatti e snapshot
Qdrant prima del campione seguente. `result.json` conserva eventi monotoni,
journal e campioni anche se la run fallisce; `summary.csv` contiene mediana/min/max
e differenze abbinate `T(N,k)-T(N,0)`. Il restore I/O resta fuori dal tempo
misurato. L'esecuzione richiede il runtime/modello offline e il container Qdrant
dedicati documentati in `../archive/adr/sidecar-work/phase2-report.md`; il comando ordinario
sopra resta il benchmark del servizio esistente.

### Risultati sidecar del 21 settembre 2026

Le [curve prima/dopo](../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md)
coprono 30 celle e 150 prove valide per versione: cinque ripetizioni per
combinazione di N, k e corpus. Su Windows/CPU a quattro thread, N=100 e k=100,
la mediana fino allo snapshot pronto passa da 15,934 a 58,099 s per i documenti,
da 18,804 a 19,497 s per il codice e da 19,132 a 38,602 s per il misto.
L'encoding per documento penalizza i delta numerosi di piccoli testi.

La [prova full](../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE5.md), su un corpus
diverso di 32 documenti / 64 chunk, riduce RSS massimo campionato da 6,436 a
3,152 GiB e USS da 5,087 a 1,753 GiB. Una sola prova per variante, formato e
raggruppamento dell'encoding cambiati insieme: non isola l'effetto del formato.
Non va confrontata con i delta per ricavare una soglia full/incrementale.

Per k=1, a N=100 documenti, il writer scrive 51.328 byte NPY e riusa 99 file
tramite hard link; sono byte logici, non traffico fisico del disco. Il batching
limitato è solo uno studio; sharding e multivettori Qdrant non sono attivati.
La [matrice finale](../adr/SCALABILITA_SIDECAR_DELTA_MATRICE.md) documenta le decisioni.

Nel codice delle misure storiche le scritture NPY per documento erano incluse in
`parsing_embedding`. La revisione integrata su main le attribuisce a `save_hash`,
inclusi fsync e hash, sia nel full sia nel delta. I raw storici non sono stati
riscritti: i totali restano validi, il breakdown conserva questo limite.

**Regola:** nessuna ottimizzazione di retrieval, chunking, ranking o indicizzazione
senza prima confrontare un bench "prima" e uno "dopo" — la sensazione che qualcosa
sia più veloce non sostituisce un numero salvato in `eval/results/`.

I test pytest ([tests/test_bench.py](../tests/test_bench.py)) coprono solo la
**meccanica** dello script (percentili, aggregazione, polling del journal, struttura
del JSON) con un server finto (`httpx2.MockTransport`): le latenze vere restano il
comando qui sopra, da eseguire ed allegare alla PR.

