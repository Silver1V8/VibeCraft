# Review indipendente — driver F2

**Conformità: NEEDS_FIXES. Qualità: NEEDS_FIXES.** Review statica nel perimetro F2; nessun modello, container o benchmark avviato. I 34 test Windows e Linux e Ruff passati sono riportati dal worker/PM, non rieseguiti qui.

## Must fix prima della run reale

1. **Database iniziale non vuoto accettato.** `rag/scripts/bench_delta.py:94-98,206-208,358-381` valida che `rag/database` sia nel checkout, ma controlla il vuoto solo per `docs/` e `code/`. Un `CURRENT`/manifest residuo può far ereditare al bootstrap incrementale una collection parent preesistente e scrivere su quella lineage, mentre il preflight esclude soltanto il nome della collection configurata. Rifiutare un database iniziale con artefatti/manifest/CURRENT prima della generazione del corpus o del bootstrap; lasciare al massimo file tecnici esplicitamente innocui se necessari. Aggiungere un test di guard che provi il rifiuto prima di ogni scrittura.

2. **Alias Qdrant preesistente non controllato.** `bench_delta.py:361-366` usa `get_collections()`, che enumera collection fisiche, ma non gli alias. Se il nome configurato esiste già come alias verso un'altra collection dedicata, il controllo di freschezza passa; il bootstrap senza manifest può usare quell'alias e mutare vettori di una run precedente. Verificare anche gli alias sul Qdrant dedicato e rifiutare il nome richiesto se già occupato, prima di creare corpus o avviare il child. Un test fake con alias omonimo rende osservabile il caso.

## Contratti verificati

Il ramo `bench.py --real-delta` evita l'import anticipato di `eval.run` e lascia il benchmark ordinario separato. Checkout/output sono ancorati a `rag/eval/results/<run>`, con path canonical e rifiuto dei link/reparse nei percorsi esistenti; config, docs, code e database devono risolvere nel checkout. Il child aggiunge il solo `checkout/rag` prima degli import core. Le mutazioni sostituiscono byte con uguale lunghezza e scelgono file distinti; `k>N` è errore. Il bootstrap incrementale diretto, seguito da job no-op HTTP di verifica, rispetta il ruling PM per il server che non parte senza indice.

Per ogni campione il driver attende writer e reader, salva job e query, controlla reload/token, conteggi docs/code, stato corrente e integrità, poi ripristina sorgenti, artefatti/CURRENT e snapshot Qdrant sotto writer lock. Fingerprint e digest paginato di punti/payload/vettori verificano il ritorno alla baseline; restore fallito invalida e ferma la run. I 200 con risultati vuoti durante l'update restano come degrado misurato. CSV usa mediana/min/max e differenza abbinata al no-op; non dichiara p95 o crossover full. Snapshot/recover su volume nativo resta da confermare nel run F2 reale; il preflight PM prova il contratto client, non il workload completo.

**Test del finally:** `rag/tests/test_bench_delta.py:104` prova byte e artefatti reali chiamando `_restore_files` direttamente dopo una mutazione simulata. Non prova ancora che un'eccezione nel corpo del campione attraversi davvero il `finally` di `run`. Il worker sta completando questa prova; va verificata prima di chiudere la review, senza estendere la suite.
