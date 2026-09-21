# F6 — curve finali, costo del delta e decisioni

Codice misurato `708a142`, confronto con F3 `0f479b2`. Le nove famiglie documenti/codice/misto × N=10/30/100 contengono **150 prove reali valide e ripristinate**, 30 celle con cinque ripetizioni. I 45 no-op non inizializzano il modello e non ricaricano lo snapshot. Il corpus sintetico, i conteggi e i digest dei punti di baseline coincidono esattamente con F3; configurazione uguale salvo collection dedicata. Verificati dopo le run anche 284 file di codice per checkout, config e corpus ripristinato: `phase6-input-verification.json`.

## Risultato e compromessi

Il nuovo formato consente letture a richiesta, scritture ColBERT attribuite ai documenti modificati e riuso immutabile dei file. **Non accelera ogni delta.** Sul corpus di documenti piccoli l'encoding per documento rallenta le modifiche numerose; il percorso del solo codice cambia poco. La precedente misura full su testi più lunghi aveva ridotto tempo e picco memoria, ma non è una prova di vantaggio su ogni distribuzione di testi.

| N=100, k=100; mediana di cinque prove | F3 NPZ | F5 NPY | Intervallo NPY min–max |
| --- | ---: | ---: | ---: |
| Documenti | 15,934 s | 58,099 s | 54,220–61,506 s |
| Codice | 18,804 s | 19,497 s | 19,366–21,702 s |
| Misto | 19,132 s | 38,602 s | 36,847–40,561 s |

`T` arriva allo snapshot pronto, non al solo termine della build. La differenza abbinata T(k)−T(0) non è il solo embedding. Le mediane delle fasi non sono componenti causali indipendenti da sottrarre. Non si presenta il p95 di cinque campioni come percentile stabile.

- [Tabelle e confronto prima/dopo](phase6-comparison/comparison.md), con JSON/CSV e risorse/query per cella.
- [Curve e intervalli completi](phase6-summary/summary.md), [grafico PDF](phase6-summary/summary.pdf), [SVG](phase6-summary/summary.svg). PDF rasterizzato e controllato visivamente: assi, intervalli e legenda leggibili.
- [Byte del writer e profilo delle fasi](npy-delta-summary.md); JSON contiene mediane/minimi/massimi, conteggi e motivi dei null.

## Granularità del writer

Per k=1 nei documenti, N=10/30/100, i byte NPY scritti sono sempre **51.328**: cambia un solo documento. A N=100 vengono riusati con hard link 5.626.240 byte logici degli altri 99 file, senza copie. Con k=10 sono scritti 550.144 byte, mentre 90 file vengono riusati; con k=100 si scrivono tutti i 5.677.568 byte. Anche il misto attribuisce i byte ai soli documenti cambiati; il delta solo codice non scrive ColBERT. Copie fallback osservate: zero; il fallback è verificato dai test, non misurato come prestazione in questa serie NTFS.

Questi sono byte logici dei file gestiti dal writer, non contatori di I/O del processo né traffico fisico del disco. I no-op che non emettono statistiche writer restano null con motivo esplicito. Gli hash ereditati non vengono riletti nel delta ordinario; il controllo profondo esplicito resta disponibile. Grafo, JSON, dense/code, indice dei file, scan e operazioni di versione rimangono globali: nessuna promessa O(k) per l'intero job.

## Query concorrenti e risorse

Il reader usa le stesse query/pausa e modalità della baseline. Si conservano tempi e conteggi per endpoint, senza normalizzare arbitrariamente finestre diverse. Le risposte HTTP 200 vuote sono degrado osservato. La riduzione delle risposte vuote durante l'aggiornamento non equivale a snapshot storici Qdrant: la collection incrementale rimane mutata in place.

Nelle 150 prove F6: **1.804 query**, 1.092 retrieve e 712 code; nessun errore HTTP, **20 risposte retrieve vuote**. F3 aveva 1.171 osservazioni e 205 risposte vuote, ma finestre e numero di query differiscono: non è un confronto causale normalizzato. Le latenze per cella e i tempi delle singole richieste restano nei CSV/JSON e nei raw.

RSS, USS e memoria private restano distinti per processo; i picchi campionati sono limiti inferiori. Qdrant è misurato separatamente nell'istanza dedicata con 1 GiB e 2 CPU, senza sommare RSS condivisi. La serie accumula collection sperimentali precedenti, come la baseline. Cache OS non svuotata; BAAI/bge-m3 cached/offline, CPU a quattro thread, Windows 11/Ryzen 5800X/circa 32 GiB RAM. Non è una misura GPU o di altri computer.

## Retention reale

La run `sidecar_retention_20260921` esegue cinque k=1 consecutivi senza ripristino, keep=3 e query concorrenti. Un secondo processo mantiene una lease e rilegge la versione iniziale anche dopo che questa esce dalle ultime tre: fingerprint invariato in ogni step. Dopo la chiusura del processo, il prune rimuove realmente quella versione e ne restano tre. I raw includono PID e intervalli monotoni, manifest/hash, CURRENT, conteggi e inventario fisico a ogni passo e dopo il prune. Codice della copia frozen ed experiment immutato.

Il conteggio fisico NTFS deduplica l'identità dei file hard-linkati, non somma le dimensioni logiche delle versioni. Esclude directory/MFT e spazio del server Qdrant. La prova riguarda lifecycle degli artefatti locali, non rollback storico della collection Qdrant. I test di lease/cancellazione sono passati anche su Linux; questa misura cumulativa è Windows.

| Retention | Versioni presenti | Byte logici sommati | Byte allocati deduplicati |
| --- | ---: | ---: | ---: |
| Baseline | 1 | 588.344 | 626.984 |
| Dopo cinque delta, lettore ancora aperto | 4 | 2.360.970 | 1.057.712 |
| Dopo chiusura e prune | 3 | 1.776.041 | 844.504 |

Le 19 query di questa prova non hanno prodotto errori o risultati vuoti. Il picco campionato del processo principale è RSS 4.008,414 MiB, USS 1.467,680 MiB e private 6.518,410 MiB; il lettore separato usa rispettivamente 59,289/43,641/142,336 MiB. Sono metriche diverse e non vanno sommate. [Riepilogo completo e finestre per step](../../sidecar_retention_20260921/evidence/retention-summary.md), con JSON e raw nella stessa run.

## Studio reale F6-03: batching

La prova isolata usa i 100 testi immutati della baseline F3, un solo modello cached CPU4, un warmup completo per variante e tre ripetizioni con ordine ciclico. Misura solo `model.encode`: esclude modello, parse, Qdrant, scrittura, gate e query concorrenti. Non sostituisce le curve T(N,k).

| Raggruppamento | Chiamate encode | Mediana | Min–max |
| --- | ---: | ---: | ---: |
| Globale, 100 chunk | 1 | 7,408 s | 7,166–7,425 s |
| Un documento per chiamata | 100 | 27,337 s | 26,952–27,730 s |
| Gruppi di massimo 12 chunk | 9 | 13,404 s | 13,243–13,534 s |

La frequenza delle chiamate e il loro raggruppamento hanno quindi un costo misurato su questo corpus. FlagEmbedding esegue anche una forward preliminare per adattare il batch a ogni chiamata; non si attribuisce tutto il costo a questa sola operazione. I gruppi da 12 riducono il tempo di encoding rispetto al per-documento, mantenendo in questa prova vettori esattamente uguali alla variante globale. Il per-documento cambia 87 valori ColBERT fp16 in 53 chunk, massimo 3,0517578125e-5; dense e sparse coincidono. Il replay della query cached sui 100 ID più il mancante dà gli stessi score/ranking in tutte le coppie. La parità vettoriale riguarda la prima ripetizione misurata; non è retrieval completo o equivalenza universale.

Dati: [batching-study.json](batching-study.json), [metodo e comando](ENCODING_BATCHING_METHOD.md). Decisione PM: un futuro intervento sul throughput deve partire da gruppi limitati di documenti, con nuova verifica di memoria, parità e T(N,k). Questo studio **non implementa** tale ottimizzazione e non attribuisce i suoi tempi al codice NPY misurato. Non si introduce sharding per compensare il costo delle chiamate all'encoder.

## Rami condizionali e capacità

Con k=100 documenti, parsing/embedding occupa una mediana di 52,189 s sui 58,099 s fino a readiness; scan/hash è 0,184 s e save/hash 0,398 s. Nel misto domina ancora parsing/embedding (33,883 s); sul solo codice 16,504 s. Per k=1 pesano circa 2,2 s di inizializzazione modello, mentre il save dei documenti cresce fino a 0,645 s a N=100. I costi globali restano visibili ma non dominano questi carichi.

- **F6-03:** studio batching completato con risultati e decisione sopra. Non domina scan/hash o save, quindi non si implementa un percorso changed_paths né ulteriore granularità dei sidecar in questa fase.
- **F6-04:** pilot ColBERT Qdrant non attivato: le misure non indicano file/rerank locale come limite dominante dei delta. Non viene introdotto un secondo backend permanente.
- **F6-05:** sharding non attivato: non esistono budget concordati violati né un requisito di isolamento per progetto dimostrato.
- **F6-02:** l'utente ha confermato budget non definiti e destinazione a macchine diverse. Si pubblicano curve per l'hardware osservato; nessuna soglia universale, capacità massima o budget rispettato viene dichiarato.
- **X-01:** nessun incrocio delta/full dichiarato. Le candidate full F5 escludono gate/promozione e usano un corpus diverso: non vengono confrontate con questi T(N,k) per dedurre un crossover.

Le run ufficiali, la migrazione, la retention e lo studio F6-03 sono concluse; non sono simulate. La review finale delle evidenze è riportata in `rag/adr/sidecar-work/phase6-evidence-review.md`; la matrice conserva i limiti e i rami non attivati.
