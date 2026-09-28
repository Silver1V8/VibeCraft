# F5 — review indipendente delle misure full e della migrazione storica

**Verdetto: APPROVATO per misure, migrazione e parità del retrieval paired nel perimetro misurato; F5 finale ancora aperta per la verifica I/O F6.** Non ho eseguito modelli, benchmark o test; ho confrontato i JSON e i campioni raw già prodotti.

## Full candidate pre/post

Le due run terminano con `exit_code=0`, `status=completed` e senza errore del sampler. Entrambe costruiscono 32 documenti, 64 chunk e 28.659 token ColBERT, con 0 code chunk; `CURRENT` e l'alias base restano assenti, e gate e promozione sono esclusi. Le verifiche post-run attestano corpus e configurazione immutati (a eccezione del nome collection tra le run), codice congelato immutato, candidate integre e conteggi uguali. I file verificati del codice congelato sono rispettivamente 267 e 284, coerenti con due snapshot di codice distinti.

| Misura build | NPZ pre | NPY post | Variazione |
| --- | ---: | ---: | ---: |
| Tempo | 859,160 s | 487,775 s | −43,23% |
| Picco RSS campionato | 6.910.664.704 B | 3.384.897.536 B | −51,02% |
| Picco USS campionato | 5.462.532.096 B | 1.881.829.376 B | −65,55% |
| Picco private campionato | 8.534.343.680 B | 4.952.924.160 B | −41,96% |

Ho ricalcolato i tre picchi dai campioni `process.jsonl` del PID workload **dentro** `build_started_monotonic`–`build_ended_monotonic`: coincidono con `resources.json`, rispettivamente su 4.487 e 2.865 campioni. PID, limiti temporali e conteggi di campioni corrispondono ai result. Qdrant e host sono misurati separatamente e non sommati alla memoria del processo. I picchi sono limiti inferiori campionati; contatori I/O e CPU sono differenze fra campioni, non volumi fisici. Il confronto è **una run reale per variante**, con formato e raggruppamento dell'encoding cambiati insieme: non attribuisce causalmente il guadagno al solo formato né stima variabilità, capacità massima, readiness, gate o pubblicazione.

I 64 ID/payload Qdrant corrispondono, ma i digest dei punti differiscono (`12cd44a9…` pre, `11ad1fed…` post). Il [diagnostico numerico](phase5-full-numeric-parity-report.md) lo spiega con scostamenti effettivi nei vettori dense, sparse e ColBERT: massimo assoluto rispettivamente 2,31×10⁻⁷, 2,466×10⁻⁶ e 6,1035×10⁻⁵ per ColBERT. Il replay cached di una query su 64 ID più un ID mancante produce gli stessi 65 punteggi arrotondati e lo stesso ordine completo. È un controllo dello scoring ColBERT, non della pipeline completa (query encoding, Qdrant, grafo e fusione); il cambio di batching è una spiegazione plausibile, non una causa isolata dimostrata. La prova paired completa è riportata sotto.

## Migrazione storica NPZ→NPY

La run locale riporta `status=completed`, codice di uscita `0` e stderr vuoto. Le sette sorgenti ammesse hanno identici hash e byte nelle mappe `before`, `copied` e `after`; la provenienza del replay è registrata tramite SHA-256. Il candidato `v20260921T131054` viene pubblicato temporaneamente in `CURRENT`, validato come layout NPY con **257 array esatti e 112.429 righe token** e hash profondi, poi il rollback ripristina `v20260911T155042`. I ranking NPZ, NPY e dopo rollback coincidono per 32 candidati cached più il mancante (`None`). Il perimetro registrato è solo artefatti locali; il nome collection nel manifest storico è metadato, senza contatto Qdrant o nuovo modello.

Questa migrazione dimostra la conversione esatta di **artefatti già esistenti**, distinta dai due rebuild full che hanno introdotto piccoli scostamenti numerici. Non estendo la parità cached della migrazione al retrieval full appena ricostruito.

Fonti principali: [pre result](../../eval-results/sidecar_fullmemory_pre_20260921/evidence/result.json), [pre resources](../../eval-results/sidecar_fullmemory_pre_20260921/evidence/resources.json), [post result](../../eval-results/sidecar_fullmemory_post_20260921/evidence/result.json), [post resources](../../eval-results/sidecar_fullmemory_post_20260921/evidence/resources.json), [comparison](../../eval-results/sidecar_npy_20260921/evidence/full-comparison.json), [migration result](../../eval-results/sidecar_migration_20260921/workload/result.json).

## Controllo pre-run del retrieval paired

**APPROVATO per l'esecuzione controllata** del [driver](../../eval-results/sidecar_npy_20260921/evidence/full_retrieval_parity.py). Il driver verifica stato e manifest congelati, hash degli artefatti delle due candidate, layout NPZ/NPY e nome esatto delle collection fisiche; prima di caricare il modello controlla il digest Qdrant di entrambe. Impone endpoint dedicato `127.0.0.1:16333`, modello offline CPU e `PYTHONHASHSEED=0`. Per ciascuna delle tre query usa una sola codifica reale condivisa, poi il `hybrid_search` canonico su entrambe le candidate, registrando i candidati dense/sparse, punteggi e ranking finale. Il wrapper consente solo `query_points` sulle rispettive collection. L'output resta nella directory evidence, senza promozione o scrittura Qdrant. La NPY si apre direttamente per non creare una lease nella sorgente congelata e viene chiusa in `finally`. La prova copre tre query e top-3, non l'intero spazio delle query né altri endpoint.

## Esito reale del retrieval paired

Il [JSON della prova](../../eval-results/sidecar_npy_20260921/evidence/full-retrieval-parity.json) contiene tre query, `top_k=3` e le versioni/collection/digest delle due candidate attese (64 punti ciascuna). Per tutte e tre le query gli ID e l'ordine dei candidati dense e sparse coincidono; sono identici anche i tre risultati finali completi, incluso il breakdown restituito da `hybrid_search` (`final_ranking_exact=true`). I candidati raw non sono uguali byte per byte (`dense_candidate_hits_exact=false`, `sparse_candidate_hits_exact=false`), coerentemente con gli scostamenti float già rilevati; non li presento come parità numerica esatta. Il numero di hit dense è 10 per query; sparse è 9 nella prima query e 10 nelle altre due, su entrambe le candidate.

**Verdetto bounded: APPROVATO.** La parità funzionale è dimostrata per queste tre query e il percorso canonico `hybrid_search` fino ai top-3, con un encoding della query condiviso nella coppia. Non prova equivalenza per tutte le query, endpoint HTTP o carichi concorrenti. Il gate finale U05 resta subordinato alla misura dei byte I/O del delta in F6.
