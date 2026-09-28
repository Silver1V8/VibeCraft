# Preflight reale — 28 settembre 2026

Prova isolata su Windows, 32 GiB RAM, 6 processori logici, RTX 3070 Ti 8 GiB; driver 616.92. Ollama 0.34.4, modello qwen3.5:9b (digest 6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7), context4096, temperatura0, think=false, massimo16 token di output nella sonda. Due richieste HTTP lanciate insieme verso localhost21434.

## Esito

Entrambe le richieste hanno risposto200, ma le inferenze sono seriali: il motore forza un solo slot per qwen35 malgrado OLLAMA_NUM_PARALLEL=2. Il log riporta il motivo e mostra solo slot0, con rilascio fra task5 e task14. I tempi HTTP sovrapposti NON provano batching o esecuzione parallela. Dati raw in `ollama-overlap.json`, estratto del log in `ollama-evidence.log`.

Fonte primaria: https://github.com/ollama/ollama/blob/main/server/sched.go (verificata il28/09/2026): qwen35 e qwen35moe sono nella lista che impone numParallel=1. Il gate di due inferenze simultanee non e soddisfatto con la combinazione installata. Cambiare modello/backend richiede una scelta ulteriore; nessun download o migrazione eseguito.

La sonda era inizialmente predisposta come CPU con CUDA_VISIBLE_DEVICES=-1, ma OLLAMA_VULKAN=true ereditato ha attivato la GPU:34/34 layer offloaded, size_vram5435828468. I dati vanno interpretati come GPU Vulkan, mai CPU. Nessun confronto prima/dopo, nessun percentile attendibile da soli due campioni.

## Baseline applicativa

Sorgente ea0cf91425a5d01b39ed821c714cd397a6e0d2b0 estratta nel laboratorio ignorato `rag/database/qdrant_data/horizontal-lab/baseline`. Corpus dedicato di prova sui prestiti bibliotecari:1documento,5chunk,6nodi,5archi. Indicizzazione reale BGEM3 CPU, Qdrant1.19.0 isolato su16333; collection horizontal_bench__v20260928T073137. Eval gate corpus produzione disattivato solo nella configurazione di questo laboratorio; contesto4096/temperatura0 da mantenere uguali nel confronto. Nessun accesso in scrittura a database operativi.

Avvio baseline HTTP localhost18000 rifiutato dalla revisione automatica con messaggio `blocked by policy`, senza motivazione specifica. Non tentato aggiramento. Matrice HTTP k=1,4,8, confronto candidate/baseline, TTFT e memoria per reader NON eseguiti. I dati presenti sono solo preflight, non una verifica end-to-end.
