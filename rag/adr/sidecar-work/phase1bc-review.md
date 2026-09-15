# Review indipendente — unità 1b + 1c

Ambito: diff congelato `phase1bc-review.diff` (quattro file) e nuovi `tests/test_index_timings.py`, `scripts/bench_process.py`, `tests/test_bench_process.py`. Esclusi fase 1a e relativo fix parallelo. I report autore sono stati verificati come affermazioni, non assunti come prova.

## Verdetto conformità al brief: NON CONFORME

Sono presenti i campi richiesti, il collector è additivo e opzionale, i conteggi ColBERT derivano dagli array reali, `psutil` è solo dev, il subprocess usa argv senza shell e le assenze principali sono rappresentate con `null`. Restano violazioni dei contratti su semantica delle fasi, cadenza del sampler, evidenze d'errore e shutdown senza orfani.

## Verdetto qualità/correttezza: RICHIEDE CORREZIONI

### [P1] Lo shutdown non è graceful e può lasciare figli orfani

- File: `rag/scripts/bench_process.py:148-159`, chiamate a `:186-191`.
- `_stop_workload()` invia `psutil.Process(pid).terminate()` al solo processo root e, dopo 5 secondi, `kill()` ancora al solo root. Su Windows `terminate()` è già una terminazione forzata; inoltre i figli scoperti durante il campionamento non vengono conservati né arrestati. Un launcher che crea server/worker può quindi morire lasciando processi figli e possibili scritture attive.
- Viola esplicitamente “richiesta graceful, evitare orphan process e non killare immediatamente eventuali scritture”. Serve una strategia per gruppo/albero di processi, con primo segnale realmente graceful sulla piattaforma e kill dell'intero albero solo come fallback.

### [P1] Il campionamento Qdrant blocca la cadenza dell'intero sampler

- File: `rag/scripts/bench_process.py:105-133`, invocazione sincrona a `:145` dentro il ciclo `:178-185`.
- Ogni campione Qdrant esegue serialmente almeno cinque/sei `docker exec` (`find`, `status`, `smaps_rollup`, tre file cgroup), ciascuno con timeout 10 s. Durante queste chiamate non vengono campionati neppure workload e sistema. L'opzione dichiarata “Qdrant ogni 1 s” può quindi introdurre buchi di molti secondi e perdere proprio i picchi brevi di boot/query/reload che lo strumento deve misurare.
- Correzione minima: una sola lettura container per tick (script `sh` read-only che restituisce tutti i dati) oppure raccolta Qdrant disaccoppiata; pianificare il tick rispetto alla deadline precedente per evitare drift cumulativo.

### [P2] `relink` e `promote` includono lavoro assegnato ad altre fasi

- File: `rag/core/indexing.py:810-844` e `:1880-1923`: il timer `relink` racchiude `collect_code_symbols`, `embed_symbols` / `_apply_code_delta` e quindi parsing/embedding del codice. Quel tempo viene poi sottratto da `parsing_embedding`.
- File: `rag/core/indexing.py:951-981`: nel percorso full diretto con `promote=True`, `promote` comprende anche `gate_promotion`; non esiste un campo `eval_gate` separato nel collector. Solo la route con `promote=False` separa l'eval.
- Le metriche risultano internamente non sovrapposte, ma semanticamente errate rispetto al brief e al report: costo embedding codice attribuito a relink e costo eval CLI attribuito a promote. Questo falserebbe confronti e decisioni successive. Separare i timer nei due percorsi, mantenendo il contratto opzionale del collector.

### [P2] Un errore di avvio non salva il report richiesto

- File: `rag/scripts/bench_process.py:172-176`; la gestione errori inizia solo dopo `Popen()` e `psutil.Process()`.
- Comando inesistente, permesso negato o errore iniziale psutil propagano prima del `try`: non vengono scritti JSON conclusivo, `sampler_error` ed exit code. Il brief richiede di segnalare eccezioni e salvare evidenze parziali. Anche il test degli errori/uscita manca: i tre test coprono solo subprocess riuscito e parser.
- Portare avvio e acquisizione root nella gestione che finalizza sempre il report; aggiungere un test focused con comando non avviabile.

## Verifiche

- Non ho ripetuto le suite dichiarate (`1b: 87 passed`, `1c: 3 passed`) né usato Qdrant, rete, modello o benchmark pesanti.
- L'incidente del primo `basetemp` 1c è un errore dell'harness operatore e non è classificato come difetto del sampler.
- I finding derivano da flusso e ordine delle chiamate; non richiedono test di capacità per essere confermati.

## Prossimo passo

Correggere i quattro contratti, aggiungere test focused per albero shutdown e avvio fallito, poi eseguire le suite owned e i workload reali del PM.
