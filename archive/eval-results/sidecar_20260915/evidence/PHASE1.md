# Fase 1 — calibrazione reale, 21 settembre 2026

La seconda run è completata (exit0): bootstrap incrementale, boot HTTP, tre query, no-op e delta di un documento, pubblicazione e shutdown. Non è una curva di capacità. Corpus sintetico: 3 documenti, 9 chunk, 343 token ColBERT, 1 file codice. CPU Ryzen 5800X, Windows 11, 32 GiB; modello BAAI/bge-m3 in cache locale, quattro thread, cache OS non controllata, una query per volta.

## Tempi osservati

| Costo (secondi) | No-op | Delta1 |
|---|---:|---:|
| Coda | 0,00063 | 0,00078 |
| Writer lock | 0,01341 | 0,00606 |
| Build | 2,60079 | 4,16438 |
| Inizializzazione modello | 2,17712 | 2,10495 |
| Scan/hash | 0,00191 | 0,00178 |
| Load | 0 | 0,00730 |
| Parsing/embedding | 0 | 1,34571 |
| Qdrant | 0 | 0,11296 |
| Relink | 0 | 0,00056 |
| Save/hash | 0 | 0,10382 |
| Promote | 0 | 0,00844 |
| Reload | 0,01100 | 0,01479 |
| Snapshot pronto dalla creazione job | **2,62875** | **4,18727** |

Il breakdown non esaurisce il wall time della build: resta tempo non attribuito separatamente. Delta: un documento realmente modificato, 3 chunk e 114 token elaborati; token pubblicato uguale alla versione risultante. No-op verificato, nessuna richiesta fusa. Boot applicativo 2,528s dopo gli import/check; bootstrap in processo nuovo 18,619s, non equivalente a un full rebuild con gate.

## Memoria e I/O

Campioni processo richiesti ogni 100ms: intervallo osservato mediano146ms, massimo595ms, 285 campioni. Picchi campionati del server nel delta: RSS3972,91MiB, memoria privata impegnata6477,43MiB, USS1415,98MiB. Sono misure diverse, non sommabili. Qdrant separato: RSS51,79MiB, privata49,95MiB, cgroup57,80MiB (cache30,93MiB inclusa), limite sperimentale1GiB. Il limite del container non è un budget prodotto.

I contatori I/O nel JSON sono cumulativi per processo, non byte fisici del disco. Il reload dura meno dell'intervallo di campionamento: non se ne isola un picco autonomo. Cache totale Windows non separatamente osservata; cache cgroup Qdrant disponibile. GPU non utilizzata. Token codice null perché l'output dell'encoder non espone il conteggio. I campioni sono limiti inferiori dei picchi reali, non precisione garantita a100ms.

## Evidenze e riproducibilità

- `calibration-20260921-r2/phase1d-result.json`: eventi, job, query, fingerprint e shutdown.
- `calibration-20260921-r2/phase1d-bootstrap.json`: contatori e tempi bootstrap reale.
- `calibration-20260921-r2-process.json/jsonl`: sampler, processi, RAM/swap, Qdrant, I/O e CPU.
- `calibration-20260921-r2-summary.json`: riepilogo, hash codice/driver e limiti.
- `environment-20260921.json`, `calibration-corpus-config.zip`, `METHOD.md`: ambiente e corpus riproducibile.

Codice sperimentale: e8d8940 più `bootstrap-alias-code.diff`. La prima run `calibration-20260921` resta fallita e conservata: il fresh bootstrap creava una collection fisica che il reconciler tentava erroneamente di ricreare come alias. Regression red/green, 85 test Windows e stessa suite Linux exit0, review indipendente approvata; seconda run conferma il fix reale.

Il vecchio container dedicato è fermo e conservato come `sidecar-0628-qdrant-failed-calibration`, dati in sandbox/qdrant. La seconda run usa `sidecar-0628-qdrant` IDd3925ae83db66bb7f76fb53c09d62ebdc5d469be043514c1b9e79fe9b717101f e storage sandbox/qdrant-r2. Nessuna risorsa operativa modificata. Sorgenti finali identici ai byte iniziali, writer terminati e server spento; indice finale non ripristinato, come dichiarato per questa calibrazione. Fase2 dovrà ripristinare sia file sia indice prima di ciascuna prova.
