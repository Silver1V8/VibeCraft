# Fase 4 — confronto reale dei lettori ColBERT

Core 0f479b2; driver 199cd78. Windows/Ryzen5800X/32GiB, CPU4thread, BAAI/bge-m3 offline, PYTHONHASHSEED=0. Ambiente e fingerprint in pm-preflight.json; fonti ricontrollate in post-run-integrity.json. Budget prodotto non definiti: nessuna soglia di capacità o budget coperto dichiarato.

## Metodo e parità

15 processi freschi I/O (3 reader × 5) e 15 processi freschi retrieval completo, tutti exit0, sampler senza errori. Storico: 42 documenti,257 chunk,112429 token,fp16 dimensione1024. Replay:32 candidati fissi più missing e una query realmente codificata, prima lettura più5 ripetizioni nello stesso processo. È I/O/scoring canonico, non ricerca completa. Full: baseline F3 mixedN100 (50 documenti/50 chunk più50 filecode), tre query realmente codificate per processo, Qdrant16333 dedicato e hybrid_search canonico, senza LLM. Codifica separata dai tempi retrieval sotto. Il corpus full è molto più piccolo dello storico.

Array identici per257chunkstorici e50F3. Score/ranking identici fra tutti30worker, incluso rank_sections_by_relevance e missing=None. Parità concorrente:48letture per ciascun reader sullo storico e sul corpusF3. Selfcheck separato Windows e Linux con2array artificiali:vecchio snapshot resta invariato mentre una nuova generazione differente viene pubblicata. Non è una prova della retention produttiva futura.

CacheOS non controllata: prima lettura non significa discofreddo. Tutti i reader percorrono lo stesso controllo baseline; cinque repliche danno min/mediana/max, non p95 affidabile.

## I/O storico: tempi e memoria

| Reader | Load s mediana [min,max] | Prima s mediana [min,max] | Calda s mediana delle mediane | Incremento USS al load MiB | Picco USS assoluto campionato MiB |
|---|---:|---:|---:|---:|---:|
| eager | 0.774897 [0.773609,0.782328] | 0.076107 [0.075192,0.080281] | 0.075686 | 222.50 | 320.72 |
| lazy | 0.002956 [0.002720,0.003049] | 0.266916 [0.257678,0.267267] | 0.258859 | 0.57 | 105.24 |
| npy | 0.000366 [0.000360,0.000391] | 0.141166 [0.138051,0.148557] | 0.138842 | 0.50 | 100.80 |

USS misura memoria residente privata; private_bytes Windows misura commit privato ed è conservato in resources.json. Picchi campionati durante l’intero worker (inclusi import) sono limiti inferiori, non delta di load. Nessuna somma RSS fra processi. Mappe/file sono conteggi a punti di controllo: a fine load tutti517mappe; eager/NPY3file, lazy4file. Non dimostrano un picco di mappe durante richieste concorrenti. Le memmap NPY vengono chiuse prima di restituire la copia del chunk.

Contatori I/O di processo, non traffico fisico: mediana load eager195895059B/lazy287982B/NPY31232B; durante6passaggi eager0B/lazy272760832B/NPY50331648B. Mmap e cacheOS possono far divergere questi contatori dal dispositivo fisico.

## Retrieval completo sul corpus F3 piccolo

| Query | Eager s mediana [min,max] | Lazy NPZ s mediana [min,max] | NPY s mediana [min,max] |
|---|---:|---:|---:|
| prenotazione evento posti | 0.016055 [0.014181,0.037407] | 0.034541 [0.018248,0.045242] | 0.023075 [0.022381,0.033866] |
| pagamenti accettati | 0.013818 [0.010786,0.030597] | 0.030485 [0.013998,0.038329] | 0.040339 [0.020168,0.048675] |
| notifiche prenotazione | 0.022167 [0.011412,0.026249] | 0.027039 [0.016905,0.051898] | 0.040551 [0.026308,0.050906] |

I tempi escludono encode, registrato nei raw full-*.json, e load del reader. Ogni query è eseguita una volta per processo, quindi questa tabella non è una curva calda della stessa query. Eager è il più rapido in questo corpus; NPY supera lazy solo nella prima delle tre query. Il vantaggio del replay storico non si trasferisce automaticamente al retrieval completo. Il modello è caricato prima della baseline memoria full; il picco campionato dell’intero worker include modello e import. Qdrant è invariato fra reader: osservazioni complete di cgroup/cache/memoria server in full-process.jsonl, comprendenti tutte le collection sperimentali conservate, senza attribuirle a un reader.

## Conversione e spazio

Conversione storica per documento, senza concatenazione del corpus. NPZ originale195738149B;42NPY piùindice230291200B logici (+17.65%). Tempo1.932s dell’intero processo campionato, inclusi import/verifica/hash; non è un tempo puro di conversione né di reindex. Raw conversion-process.* separati. Inventario NTFS in disk-allocation.json: NPZ195739648B allocati; NPY230420480B allocati, deduplicati per identità file. Sono allocazioni dei dati, escluse directory e metadati del filesystem. Il helper usa FileStandardInfo.AllocationSize, verificato con hard link su Windows e Linux (rispettivi selfcheck separati). La baselineF3 restaimmutata; nessuna scrittura Qdrant.

## Decisione PM: procedere con F5 NPY, review delle evidenze approvata

NPY mantiene il caricamento sotto1MiB incrementale di USS come NPZ lazy e riduce la mediana calda del replay storico da0.259a0.139s (circa46%). Eager richiede circa222.5MiB incrementali al load per questo corpus ed è più rapido durante il rerank. NPY comporta maggiore spazio logico e, sul piccolo corpus full,7–27ms circa in più per ricerca rispetto a eager: sono costi osservati, non dichiarati accettabili rispetto a un budget inesistente.

Per l’obiettivo già autorizzato di lettura a richiesta su macchine diverse, si sceglie NPY per documento. NPZ lazy resta un prototipo sperimentale: evita la materializzazione ma paga decompressione a ogni accesso e conserva la riscrittura globale. La decisione non dichiara un miglioramento del reindex: F5 deve implementare e verificare riuso immutabile/encoding limitato; F6 deve misurarli. Nessun secondo backend permanente, nessuna cache illimitata o sharding. Reader legacy NPZ mantenuto solo per compatibilità e rollback.

F5 segue il piano già approvato: indice/file validati senza pickle, lifecycle crossprocess e retention veritiera prima di abilitare il lazyreader, migrazione candidata verificata prima di CURRENT, full/delta e rollback equivalenti. Se queste garanzie non passano, nessuna promozione della migrazione.
