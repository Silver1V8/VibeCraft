# Fase 3 — confronto reale dopo le correzioni

## Esito

Ripetute tutte le150prove F2: nove famiglie,30celle×5, senza errori né ripristini falliti. Codice post congelato0f479b2; prima914a170, driver precedente17ce3ca. Formato NPZ e scoring invariati. Review codice F3-01..04 approvata; Windows277test passati, Linux268passati/9skipGit dichiarati. Il confronto conferma una forte riduzione dei no-op, mentre non dimostra una riduzione generale del tempo dei delta con contenuto.

Stesso hardware/runtime/modelloCPU4thread/concorrenza/corpus/mutazioni di PHASE2.md. Container QdrantF2 e volume preservati fermi; F3 in nuovo volumeDocker nativo, stessa immagine1.19.0/1GiB/2CPU/porta16333, stesso ordine probe/smoke/famiglie. Anche F3 conserva le collection precedenti: memoria Qdrant è dell’intero server, non della sola famiglia. Prova reale snapshot in qdrant-native-f3-snapshot-probe.json; codice/config hash in phase3-prepared-environment.json.

Configurazioni YAML effettive identiche salvo nomecollection e terminatori di riga: phase3-config-comparison.json. Corpus SHA/byte normalizzati e digest completi dei punti Qdrant identici nelle9coppie, verificati dall’aggregatore. Anche array code.npz delle9baseline uguali elemento per elemento: phase3-code-vector-parity.json. Le configurazioni non sono soltanto parametri nominali della run.

## No-op: snapshot già corretto

| Modo | N | T prima mediana s | T dopo mediana s | intervallo dopo s | riduzione osservata |
|---|---:|---:|---:|---:|---:|
| code | 10 | 2.64096 | 0.01873 | 0.01293–0.02575 | 99.29% |
| docs | 10 | 2.62664 | 0.01753 | 0.01066–0.02431 | 99.33% |
| mixed | 10 | 2.65984 | 0.02008 | 0.01360–0.02537 | 99.25% |
| code | 30 | 2.64353 | 0.03970 | 0.01865–0.04095 | 98.50% |
| docs | 30 | 2.58107 | 0.03542 | 0.01616–0.04093 | 98.63% |
| mixed | 30 | 2.64308 | 0.03506 | 0.01399–0.04038 | 98.67% |
| code | 100 | 2.61430 | 0.06292 | 0.05927–0.06393 | 97.59% |
| docs | 100 | 2.73860 | 0.06312 | 0.03452–0.06756 | 97.70% |
| mixed | 100 | 2.63790 | 0.04613 | 0.03707–0.06672 | 98.25% |

Per tutte le45prove no-op post: init_model=0 e reload_duration=0, snapshot_token realmente servito uguale al token pubblicato e alla baseline. Non è stato anticipato il momento di readiness. Il tempoHTTP resta circa0.5s per il polling del driver e viene separato da T nel journal. Il caso snapshotstale conserva callback/reload e relativo errore: coperto dai test, non confuso con questi no-op allineati.

## Delta con contenuto

| Modo N100 | k | T prima mediana s | T dopo mediana s | variazione mediana s |
|---|---:|---:|---:|---:|
| code | 1 | 3.565 | 3.450 | -0.115 |
| code | 10 | 5.645 | 5.577 | -0.068 |
| code | 100 | 19.017 | 18.804 | -0.213 |
| docs | 1 | 3.761 | 3.768 | +0.008 |
| docs | 10 | 5.493 | 5.636 | +0.144 |
| docs | 100 | 15.588 | 15.934 | +0.346 |
| mixed | 1 | 3.681 | 3.770 | +0.089 |
| mixed | 10 | 5.885 | 6.202 | +0.317 |
| mixed | 100 | 19.046 | 19.132 | +0.086 |

Modello dedicato e calcolo embedding restano necessari per nuovo contenuto. Le differenze sono piccole e non uniformi rispetto al forte guadagno no-op; cinque ripetizioni e cache OS non controllata non sostengono una conclusione di accelerazione o regressione generale. La differenza abbinata T(k)−T(0) aumenta in molti casi perché il no-op non carica più il modello: non è «solo embedding» né un peggioramento equivalente del delta assoluto.

[Confronto completo](phase3-comparison/comparison.md), [CSV con min/max, breakdown, risorse e query per endpoint](phase3-comparison/comparison.csv), [JSON](phase3-comparison/comparison.json). [Curve post SVG](phase3-summary/summary.svg), [PDF](phase3-summary/summary.pdf), [tabella post](phase3-summary/summary.md). Assi k categoriali, stessa convenzioneF2. PM ha verificato la rasterizzazione del grafico.

## Memoria e query

| Modo | N | max RSS prima/dopo MiB | max USS prima/dopo MiB | query prima/dopo | vuote prima/dopo |
|---|---:|---:|---:|---:|---:|
| docs | 10 | 4090.50/4083.18 | 1531.30/1524.02 | 55/62 | 29/29 |
| docs | 30 | 4103.48/4083.57 | 1562.59/1529.09 | 64/66 | 0/0 |
| docs | 100 | 4158.74/4148.17 | 1600.59/1588.55 | 217/213 | 132/130 |
| code | 10 | 4084.54/4067.19 | 1525.14/1507.81 | 63/72 | 0/0 |
| code | 30 | 4078.13/4083.54 | 1527.41/1524.16 | 67/70 | 0/0 |
| code | 100 | 4133.65/4135.86 | 1614.30/1592.23 | 271/275 | 0/0 |
| mixed | 10 | 4100.91/4071.19 | 1541.12/1517.69 | 63/69 | 10/9 |
| mixed | 30 | 4105.19/4084.32 | 1545.36/1531.43 | 70/73 | 0/0 |
| mixed | 100 | 4191.48/4173.31 | 1630.18/1618.39 | 266/271 | 37/37 |

Sono massimi campionati del singolo server Python, non somme RSS e non picchi assoluti. USS residente privata differisce da private committed Windows; entrambe restano nei raw. Sampler richiesto0.1s, intervalloeffettivo registrato; la memoria del brevissimo no-op non è isolabile a quella frequenza. I/O è di processo, non traffico fisico disco; cache OS/host non controllata o non osservabile.

Le query sono richieste avviate attorno alla finestra HTTP: l’ultima può terminare dopo il polling, e non ogni richiesta ha una sovrapposizione dimostrata con la build. Cambiando durata, cambia il numero di query; per il misto si confrontano endpoint separati nelJSON/CSV, senza normalizzare le frequenze. RisposteHTTP200vuote restano degrado, nessunHTTPerror osservato; niente budget di degrado inventato.

## Decisione e prossima fase

F3 elimina il lavoro evitabile dei no-op, libera riferimenti al primo snapshot e limita il buffer temporaneo degli hash. Su questo corpus brevissimo non isola un beneficio rilevante di memoria dei grandi sidecar: F4 userà anche i257chunk/112429token storici già copiati e verificati, confrontando eagerNPZ, NPZa richiesta e NPYperdocumento. Nessun budget prodotto definito permette di dichiarare coperta una capacità target o di chiudere quel confronto. Nessuna decisione NPY/Qdrant/sharding anticipata.

Review indipendente delle evidenze: rag/adr/sidecar-work/phase3-evidence-review.md. Nessuna soglia universale, p95 stabile o crossoverfull.
