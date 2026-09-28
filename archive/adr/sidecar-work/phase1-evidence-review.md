# Review indipendente — evidenze F1

**Esito: evidenze reali valide per l'uscita F1/U-01, con un limite esplicito su F1-03.** Review di `PHASE1.md`, summary, risultato e bootstrap grezzi, e `process.jsonl`; nessun benchmark avviato.

| Punto | Verifica |
|---|---|
| F1-01 | I job contengono coda, lock, build, init modello, scan/hash, load, parsing/embedding, Qdrant, relink, save/hash, promote e reload. I valori della tabella coincidono con i raw: no-op snapshot pronto 2,62875 s; delta 4,18727 s. I timestamp di creazione/fine restano nei job. |
| F1-02 | Entrambi i job sono `completed`, con `reload_status=completed` e `published_token`. Nel delta il token coincide con `result.version`; il no-op è `result.noop=true`. La readiness usa il tempo dalla creazione del job, non il solo fine build. |
| F1-03 | Il JSONL contiene 285 campioni più un record finale Qdrant. Origine monotona del driver e timestamp monotoni del sampler permettono l'allineamento; i massimi della sintesi corrispondono ai campioni attribuiti. RSS, privata e USS non sono sommati; Qdrant ha cgroup/cache/limite separati. Il reload di 11–15 ms non ha una misura di picco autonomo: è più breve dell'intervallo osservato (mediana 146 ms), limite dichiarato correttamente. |
| F1-04 | Il raw conserva corpus/fingerprint (4 file, hash iniziale=finale), modello/cache locale e parametri; bootstrap: 3 documenti, 9 chunk, 343 token ColBERT, 1 file codice; delta: solo `prenotazioni.md`, 1 documento, 3 chunk, 114 token. Le tre query sequenziali restituiscono 3 risultati ciascuna. I byte I/O sono contatori cumulativi di processo, non traffico fisico; token codice `null` ha motivazione esplicita. Provenienza di codice, driver e corpus è elencata nella sintesi. |
| F1-05 | I raw del run dimostrano readiness reale; il caso callback bloccata e la lettura del journal storico sono coperti dalle regressioni precedenti citate nella matrice F1, non sono riprovati da questa calibrazione. Non attribuire loro una nuova prova sperimentale. |

L'uscita U-01 richiede un JSON che distingua i costi misurati e il momento della pubblicazione: i job grezzi lo forniscono. Il vecchio dato di 4,8 s non viene riutilizzato come baseline. Il run ha exit 0, tre query riuscite, writer attesi, server spento e sorgenti ripristinati byte per byte; l'indice finale resta al delta come dichiarato. È una sola prova con corpus sintetico N=3, non una curva T(N,k) né una misura di capacità.

**Precisazione editoriale:** in `rag/eval/results/sidecar_20260915/evidence/PHASE1.md`, la frase che attribuisce il residuo del wall time a «overhead del framework e rilascio del modello» va letta come ipotesi: i raw provano solo che il breakdown non esaurisce la build, non separano quelle due cause. Una formulazione «resta tempo non attribuito dal breakdown» sarebbe rigorosa. Questo e il picco reload non isolabile sono gli unici limiti materiali trovati nel perimetro.
