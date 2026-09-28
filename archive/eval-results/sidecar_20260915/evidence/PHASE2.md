# Fase 2 — baseline reale T(N,k)

## Metodo ed esito

150 prove reali valide, 30 celle con cinque ripetizioni ciascuna: N=10/30/100, documenti/codice/misto, k=0/1/10 e k=100 solo a N=100. Tutti i nove processi sono terminati exit0, con ripristino verificato di file, database locale, CURRENT e punti/payload/vettori Qdrant dopo ciascuna prova. Bootstrap incrementale reale seguito da job HTTP di verifica, il cui job_id è conservato; non viene presentato come full rebuild HTTP.

Core congelato `914a170`, driver `17ce3ca`; archive/config hash in `phase2-prepared-environment.json`. Ryzen 5800X, Windows11, circa32GiB, Python3.14.6/NumPy2.5.2, BAAI/bge-m3 revision5617a9f61b028005a4858fdac845db406aefb181, CPU quattro thread, offline. Qdrant1.19.0 image057ee3a8..., volume Docker nativo, limite1GiB/2CPU, porta16333; un solo lettore query concorrente, tre domande fisse. Nessun corpus/collection operativo modificato.

Corpus sintetico breve: stessa formula ciclica di tre lunghezze; ogni file ha una modifica indicizzabile VarianteA→VarianteB con byte invariati. Misto divide N a metà fra Markdown e Python. I conteggi token codice non sono esposti dall’encoder e restano null con motivo; hash/simboli/file modificati ne attestano il lavoro. Questa distribuzione non rappresenta il corpus storico di42documenti/112429token: non si estrapola capacità.

## Corpus e contesa

| Modo | N file | byte sorgenti | chunk docs | token ColBERT | query nella finestra osservata | risposte vuote | errori HTTP | max RSS server MiB osservato | max USS MiB osservato |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| docs | 10 | 665 | 10 | 268 | 55 | 29 | 0 | 4090.50 | 1531.30 |
| docs | 30 | 2010 | 30 | 821 | 64 | 0 | 0 | 4103.48 | 1562.59 |
| docs | 100 | 6695 | 100 | 2766 | 217 | 132 | 0 | 4158.74 | 1600.59 |
| code | 10 | 1015 | 0 | 0 | 63 | 0 | 0 | 4084.54 | 1525.14 |
| code | 30 | 3060 | 0 | 0 | 67 | 0 | 0 | 4078.13 | 1527.41 |
| code | 100 | 10195 | 0 | 0 | 271 | 0 | 0 | 4133.65 | 1614.30 |
| mixed | 10 | 840 | 5 | 133 | 63 | 10 | 0 | 4100.91 | 1541.12 |
| mixed | 30 | 2535 | 15 | 406 | 70 | 0 | 0 | 4105.19 | 1545.36 |
| mixed | 100 | 8445 | 50 | 1376 | 266 | 37 | 0 | 4191.48 | 1630.18 |

La risposta vuota HTTP200 è degrado osservato e resta nel raw; non viene mascherata come query riuscita con contenuto. La collection Qdrant nei casi solo codice è vuota per disegno: i simboli sono nei sidecar code. Le risposte baseline contengono risultati. Nessun requisito di degrado massimo è stato definito, quindi non si dichiara conformità a un budget.

## Curve ed attribuzione

T è `job.snapshot_ready_duration_seconds`, dal journal monotono, inclusi coda/lock e readiness. Durata HTTP separata. [Tabella completa](phase2-summary/summary.md), [CSV](phase2-summary/summary.csv), [grafico SVG esportabile](phase2-summary/summary.svg), [PDF](phase2-summary/summary.pdf). Grafico verificato anche tramite rasterizzazione PDF; assi k categoriali, non lineari: 0,1,10,100 hanno spaziatura uguale. Differenze T(N,k)−T(N,0) abbinate per ripetizione, non «solo embedding». Min/max descrivono cinque prove, non p95 stabile.

| Modo N100 | k | init modello mediana s | scan/hash s | load s | parsing/embedding s | save/hash s | reload s |
|---|---:|---:|---:|---:|---:|---:|---:|
| docs | 0 | 2.2019 | 0.0176 | 0.0000 | 0.0000 | 0.0000 | 0.0824 |
| docs | 1 | 2.1161 | 0.0172 | 0.0646 | 0.5712 | 0.2826 | 0.1437 |
| docs | 10 | 2.1078 | 0.0242 | 0.0598 | 2.3453 | 0.2848 | 0.0919 |
| docs | 100 | 2.1583 | 0.1210 | 0.0508 | 11.9783 | 0.2853 | 0.1463 |
| code | 0 | 2.1615 | 0.0180 | 0.0000 | 0.0000 | 0.0000 | 0.0214 |
| code | 1 | 2.2344 | 0.0196 | 0.0181 | 0.6761 | 0.0823 | 0.0289 |
| code | 10 | 2.2049 | 0.0257 | 0.0196 | 2.8010 | 0.0890 | 0.0286 |
| code | 100 | 2.1845 | 0.1123 | 0.0121 | 16.2602 | 0.0822 | 0.0348 |
| mixed | 0 | 2.1266 | 0.0182 | 0.0000 | 0.0000 | 0.0000 | 0.0521 |
| mixed | 1 | 2.1802 | 0.0190 | 0.0409 | 0.5849 | 0.2071 | 0.0544 |
| mixed | 10 | 2.1261 | 0.0292 | 0.0416 | 2.8947 | 0.2040 | 0.1006 |
| mixed | 100 | 2.1570 | 0.1116 | 0.0302 | 15.8452 | 0.2042 | 0.0775 |

Le mediane delle fasi non si sommano necessariamente alla mediana di T; il tempo non attribuito resta tale. Sul corpus breve il no-op paga circa2.2s di inizializzazione del modello; a k=100 cresce soprattutto parsing/embedding. Questo motiva F3 già prevista, senza dedurre che hash o sidecar siano irrilevanti su corpus maggiori.

## Limiti e riproducibilità

- `resources.json` di ciascuna famiglia riporta latenza query min/mediana/max, picchi e contatori per campione; `process.jsonl` conserva tutti i campioni esterni. RSS non è sommato fra processi. Private Windows è memoria committed, USS è residente privata: non sono intercambiabili.
- Intervallo richiesto0.1s, intervalli effettivi registrati; picchi campionati sono limiti inferiori. I/O di processo non equivale a I/O fisico del disco; gli estremi non campionati sono esclusi. Il reload può essere più breve di un intervallo, senza picco separato affidabile.
- Qdrant misura tutto il server dedicato, con probe, smoke e collection sperimentali precedenti conservate. Non è memoria della sola famiglia. Cache OS non controllata; cache host totale non disponibile. CPU soltanto, nessuna misura GPU.
- F1 usava un bind mount Windows; F2 usa volume nativo dopo prova di restore. Non confrontare numericamente i due ambienti come prima/dopo F3.
- Tutti i sorgenti sintetici sono riproducibili da `scripts/bench_delta.py`; corpus hash/byte, query, mutazioni, eventi, job e integrità sono nel result.json. Bootstrap e snapshot nativo sono reali. Fixture di formato e smoke sono esclusi dalle150prove.
- Nessuna soglia universale e nessun incrocio incrementale/full: budget prodotto non definiti e full non eseguito. F3 deve ripetere le stesse150prove; F4 resta necessario per il reader a richiesta.

Verifica indipendente: `rag/adr/sidecar-work/phase2-evidence-review.md`. Test driver:36Windows e36Linux. Nessuna migrazione di formato in questa fase.

Precisazione temporale: il reader parte attorno alla richiesta HTTP e può completare l’ultima query dopo il ritorno del polling. Le latenze includono queste richieste sovrapposte; non si afferma che ogni query ricada interamente nella build misurata dal journal.
