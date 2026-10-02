# Task 2 — Review indipendente

Base: `9e48d987c00b3925be4b6d16869fb4d939786efc`. Review del codice staged e del report Task 2, nel worktree `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`. Nessuna modifica a codice, test o indice Git; unico file scritto: questo report.

## Verdetto Spec: FAIL — due P1 e un P2

### P1 — Il delta modifica la collection di uno snapshot ancora in uso

**Riferimenti:** `rag/core/indexing.py:1537`, `rag/core/indexing.py:1787`, `rag/core/indexing.py:1878`.

Un progetto ordinario eredita il percorso delta legacy: delete/upsert passano per l'alias attivo e il manifest della nuova versione eredita la collection fisica del padre. Il requisito di snapshot coerente con lease non è quindi rispettato: una richiesta su v1 conserva grafo/ColBERT v1 ma legge già i vettori v2. Il rollback a v1 ripristina solo gli artefatti locali. Questo limite era preesistente per legacy, ma viene ora applicato ai nuovi progetti senza una deroga nella specifica.

**Riproduzione indipendente:** ProjectRegistry temporaneo, Qdrant `:memory:`, Embed del test Task 2, gate disabilitato nel solo contesto. Full v1 con ALPHA (+1), `load_artifacts(retain_lease=True)`, delta v2 con BETA (-1), lettura della physical `A__v1`, rollback v1. Output verificato con assert:

```text
leased v1 ColBERT=1.0; v1 Qdrant after delta=-1.0; after rollback v1=-1.0
```

Il test A/B nuovo controlla i vettori di B dopo il delta A e il ColBERT dello snapshot A, ma non controlla che i vettori Qdrant di A/v1 restino quelli vecchi; usa inoltre ALPHA anche nella modifica, quindi il segno non cambia. Per i progetti ordinari serve pubblicazione su collection candidata distinta. Riutilizzare il full build quando arriva un delta è una possibile correzione minima; preservare la compatibilità legacy. L'uso dell'immutabilità richiede una decisione coerente anche sulla disponibilità del delta ordinario.

### P1 — Il golden set può attraversare una junction verso un altro progetto

**Riferimento:** `rag/core/eval_gate.py:156`.

Il path `<root>/eval/golden.yaml` viene passato al loader senza controllo di symlink/junction o confinement. La validazione del registry controlla `database/eval`, ma non `<root>/eval`. Una root A con junction `eval` verso `B/eval` viene accettata anche da `registry.get(A)`, poi il gate A usa i casi di B. Viola il requisito esplicito «mai valutare B con il golden set di A» e può consentire o bloccare una promozione sul corpus sbagliato.

**Riproduzione indipendente:** due progetti temporanei, B/eval/golden.yaml con `q: PRIVATE_B`, junction Windows A/eval → B/eval, nuova lettura A dal registry e `gate_promotion(project=A)`. Solo `evaluate_recall` sostituito per catturare gli argomenti; path resolution e lettura YAML reali. Assert conferma:

```text
registry accepts A/eval junction; A gate reads B golden: [{'q': 'PRIVATE_B', 'expected': ['private.md']}]
```

Rifiutare il collegamento/escape prima del loader fail-open, compreso un golden.yaml collegato. Il controllo deve produrre un errore di confinement, non convertirlo in golden assente. Verificare allo stesso confine anche i path destinazione della telemetria aggiunti dal task.

### P2 — CURRENT=legacy è valido anche per un progetto ordinario

**Riferimenti:** `rag/core/artifacts.py:151`, `rag/core/artifacts.py:184`.

`version_dir('legacy', project=ordinary)` restituisce database/, che esiste sempre. Di conseguenza `current_version` accetta il token e `load_artifacts` entra nel ramo flat storico senza segnalare il puntatore corrotto. Il sentinel deve essere ammesso solo per None/progetto legacy; per i progetti ordinari il requisito prevede un errore esplicito, senza fallback storico.

**Riproduzione indipendente:** scritto soltanto `CURRENT=legacy` nel database temporaneo di un progetto nuovo. `current_version(project=A)` e `load_artifacts(project=A).version` restituiscono entrambi `legacy`, senza eccezioni.

## Verdetto Quality: PASS per struttura e compatibilità, con le correzioni Spec sopra

- Contesto esplicito, nessun cambio globale di cwd/environment/config durante richieste, nessuna nuova dipendenza. Helper e lease esistenti riutilizzati.
- Naming Qdrant, GC e lock usano il namespace/database del progetto. Il GC filtra il prefisso esatto dell'alias e non il prefisso generico vibecraft_. Il test protegge anche un candidato non manifestato di A e una collection legacy temporanea.
- Artefatti, full build, staging ColBERT e fingerprint propagano project. ColbertWriter controlla gli antenati dello staging; source_files controlla prima delle letture e l'accesso ausiliario Razor riusa lo scanner.
- I doppi legacy nei test cambiano soltanto firma per accettare project; nessuna asserzione rimossa o indebolita. La fixture writer lock conserva il sandbox per None e usa il database temporaneo del contesto esplicito.
- `git diff --cached --check`: exit 0. Nessuna violazione stilistica concreta ulteriore.

## Evidenza dei test e limiti

Report implementatore letto dopo la disponibilità: gate mirato finale **397 passed in 69.29s**, nessuno skip, incluso Qdrant server dedicato sulla porta 49634; Ruff verde. Sono evidenze riportate dall'implementatore, non suite rieseguite dal reviewer.

Il reviewer ha eseguito soltanto le due riproduzioni inline descritte sopra (la prima include golden junction e CURRENT legacy; la seconda delta/lease/rollback), con exit 0 e assert dei comportamenti errati. Interprete `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe`, PYTHONPATH del worktree/rag, PYTHONUTF8=1, workdir esplicito del worktree. Tutti i dati erano in TemporaryDirectory; Qdrant solo in memoria. Junction rimossa come link con rmdir prima della pulizia temporanea, senza cancellare la destinazione. Nessun accesso a corpus o collection reali, nessuna suite ripetuta.

## Carry-forward approvati / fuori perimetro

- Task 3: hybrid_search, restatement_sections e ranking con settings del progetto, quindi propagazione del keyword da evaluate_recall. Golden/path/soglia/storico sono l'ownership Task 2; il ranking globale residuo è una dipendenza esplicita approvata e non genera un ulteriore blocco in questa review.
- Razor metadata: verificato che `_LAST_RAZOR_REPORT` resta globale e `razor_report()` non ha code_dir nella chiave. Caller attuali soltanto test e documentazione; nessun endpoint/runtime trovato. Pending Task 3 secondo il PM, da risolvere prima di esporlo per progetto.
- Runtime cache residenti, cattura contesto nei job e propagazione nei caller API/CLI/pipeline restano ai task dipendenti. Task 8 svolgerà il controllo integrato.
- Il limite delta in-place NON è considerato carry-forward approvato: è il P1 sopra, discusso separatamente con il PM.

Totale: Spec 2 P1 + 1 P2; Quality nessun finding indipendente aggiuntivo. Task 2 non approvabile nello stato revisionato.
