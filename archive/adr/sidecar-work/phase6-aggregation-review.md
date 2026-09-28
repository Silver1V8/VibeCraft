# F6 — review statica aggregatore delta NPY

**Verdetto finale: APPROVATO per l'uso dopo il completamento delle nove famiglie.** Nessuna run F6 incompleta è stata aggregata o rieseguita. Ho letto `summarize_npy_delta.py`, il metodo dichiarato e il validatore `compare_delta.load` riusato. Le due modifiche a `compare_delta.py` sono soltanto intestazioni; i controlli di completamento, 5 repliche per k, restore, token, corpus/config e digest Qdrant restano invariati.

## Finding

1. **CHIUSO — contatori obbligatori k>0.** La prima versione di [`summarize_npy_delta.py`](../../eval-results/sidecar_npy_20260921/evidence/summarize_npy_delta.py) ammetteva cinque `None` per un contatore richiesto. Il fix introduce `REQUIRED_COUNTS` e valida presenza e coerenza delle chiavi in tutte le cinque repliche. A k>0 i contatori richiesti devono essere numerici, finiti e non negativi; solo `code_tokens_processed=None` è ammesso con motivo esplicito non vuoto. A k=0 possono essere null soltanto `chunks_indexed` e `colbert_tokens_indexed` oltre al code token motivato. Il selfcheck negativo esercita chiavi/valori mancanti, quello positivo conserva `written_bytes=0` per il caso solo codice; il worker riferisce `--selfcheck` exit 0. Riesame statico del fix: nessuna regressione osservata.

## Resto del perimetro

`compare_delta.load` richiede nove famiglie standard complete, combinazioni k e cinque ripetizioni per k, sample validi e ripristinati, job/reload completati e token coerente. L'aggregatore non scrive output prima di validare tutte le sorgenti. Per I/O ColBERT k>0 rifiuta block assente, campi mancanti, valori non finiti/negativi; quindi **zero scritto nei delta solo codice è accettato come zero**, mentre il no-op senza writer resta `null` con motivo. Le nove fasi sono richieste con chiavi esatte e tempi finiti; T usa `snapshot_ready_duration_seconds`. I byte linkati/copied sono dichiarati dimensioni logiche, non contatori I/O del processo; gli hash ereditati sono conteggio file. Nessuna mediana p95, capacità o beneficio causale viene inventata.

Fonti: [metodo](../../eval-results/sidecar_npy_20260921/evidence/NPY_DELTA_SUMMARY_METHOD.md), [piano aggregazione](phase6-aggregation-plan.md), [validatore riusato](../../eval-results/sidecar_20260915/evidence/compare_delta.py).
