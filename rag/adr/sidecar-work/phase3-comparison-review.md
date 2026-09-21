# Review indipendente — aggregatore F3 pre/post

**Verdetto dopo fix: APPROVATO per l'aggregatore F3.** Review statica di `compare_delta.py` e prova leggera con le coppie reali docs N10/N30 già concluse. Le altre famiglie post erano in corso: F3/U-03 non è dichiarata chiusa. Nessun benchmark, modello o container avviato.

## Findings

1. **Configurazione: chiuso.** `rag/eval/results/sidecar_20260915/evidence/compare_delta.py:66-70` rifiuta parametri non-collection diversi e collection uguali; il self-check negativo lo copre. L'etichetta ora dice esplicitamente «run parameters verified; dedicated collection differs». Il report distingue questo controllo dal confronto del YAML normalizzato che il PM conserverà separatamente.

2. **Risorse: chiuso.** `compare_delta.py:51-59` ricalcola dal `process.jsonl` tramite `summarize_resources.summarize`, che rifiuta sampler fallito; verifica poi source, parametri, PID e corrispondenza esatta delle chiavi `(k,repeat)`. Se il raw manca, restituisce `null` con limite «not provided», senza inventare zero o mediana.

## Verifiche positive

`load()` richiede nove famiglie standard, cinque ripetizioni per k, job/reload/token validi e restore verificato; smoke/fixture sono esclusi dalla run reale. `corpus()` confronta path relativi docs/code, SHA-256 e byte; `compare_pair()` confronta conteggio e digest dei punti Qdrant, conteggi docs/code/chunk/token e preserva `code_tokens_processed=null` quando presente su entrambi i lati. T è il tempo journal fino a snapshot pronto; il cambiamento è mediana post meno mediana pre, mentre ΔT è calcolato per ripetizione contro il no-op della stessa run. I query summary sono separati per endpoint e dichiarano correttamente la finestra HTTP, che non prova overlap writer per ogni richiesta. `resource_summary()` conserva `null` se non ha valori, senza convertirlo in zero.

Le coppie docs N10 e N30 passano anche dopo il fix i controlli di corpus, punti, conteggi, parametri e raw sampler; le righe calcolate danno no-op mediano 2,627→0,018 s (N10) e 2,581→0,035 s (N30). Le misure delta assolute restano distinte dal ΔT abbinato; nessun crossover, budget o p95 è inferito.
