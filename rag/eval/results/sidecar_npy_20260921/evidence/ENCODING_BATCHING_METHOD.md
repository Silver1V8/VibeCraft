# F6-03: studio isolato del raggruppamento encoder

Il driver `encoding_batching_study.py` usa **solo** i 100 documenti della baseline F3 `sidecar_delta_post_20260921_docs_n100`, non la copia NPY F6 in mutazione. Prima dell'esecuzione verifica per ogni file dimensione e SHA-256 registrati nel `result.json` F3, poi usa `read_document` e `chunk_markdown` canonici e richiede esattamente 100 chunk univoci, uno per documento. Verifica anche la query ColBERT già salvata. Il self-check è passato: 100 chunk, query 4×1024, gruppi attesi 1/100/9; nessun modello caricato.

La prova reale, **non eseguita**, caricherà una sola istanza BGE-M3 offline su CPU con quattro thread. Con gli stessi testi e le stesse opzioni di produzione (`batch_size=12`, `max_length=8192`, dense+sparse+ColBERT), misurerà solo il tempo dentro `model.encode` per tre varianti: una chiamata globale, una per documento, gruppi consecutivi fino a 12 chunk. Ciascuna variante ha un warmup completo non conteggiato e tre ripetizioni; l'ordine di partenza ruota tra le ripetizioni. Il caricamento del modello, il parse e l'analisi dei vettori sono fuori dal timer. Il JSON registrerà tempi di ogni ripetizione, numero effettivo di chiamate, dimensioni dei gruppi e shape/dtype di ogni chunk.

L'analisi confronterà senza tolleranze implicite valori dense, chiavi/valori sparse e ColBERT fp16 per ogni ID, con conteggi e scostamenti massimi. La query ColBERT cached verrà applicata agli stessi 100 ID più uno mancante con lo scorer canonico per confrontare punteggi e ranking. È un **replay dello scoring**, non retrieval completo. Nessuna collection Qdrant né file della baseline verrà modificato; l'unico output della prova è `batching-study.json` accanto al driver.

Comandi dalla directory `rag`:

```powershell
$env:PYTHONUTF8='1'; $env:PYTHONDONTWRITEBYTECODE='1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -B eval/results/sidecar_npy_20260921/evidence/encoding_batching_study.py --selfcheck
```

Dopo la review e solo quando le misure ufficiali/retention sono terminate:

```powershell
$env:PYTHONHASHSEED='0'; $env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'; $env:CUDA_VISIBLE_DEVICES='-1'
& 'C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe' -B eval/results/sidecar_npy_20260921/evidence/encoding_batching_study.py --run
```
