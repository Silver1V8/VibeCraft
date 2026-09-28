# Evidenze delle valutazioni

## Scalabilità sidecar — 21 settembre 2026

Implementazione integrata in `3eda61a`: ColBERT NPY per documento, letture a
richiesta, riuso dei file invariati e misure del delta reale.

| Evidenza | Cosa dimostra |
|---|---|
| [Reader](../../../archive/eval-results/sidecar_readers_20260921/evidence/summary.csv) | Nell'esperimento I/O, incremento USS al caricamento: 233.312.256 byte eager NPZ contro 528.384 byte NPY; non è la memoria dell'intero servizio |
| [Full e migrazione](../../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE5.md) | Picco RSS 6,436 → 3,152 GiB su 32 documenti / 64 chunk; una prova per variante. Migrazione degli array persistiti esatta |
| [Delta e compromessi](../../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md) | 150 prove per versione; a N=100/k=100 documenti, mediana 15,934 → 58,099 s fino allo snapshot pronto |
| [Curve T(N,k)](../../../archive/eval-results/sidecar_npy_20260921/evidence/phase6-summary/summary.md) | Mediane e intervalli per documenti, codice e misto; differenze rispetto al no-op |
| [Retention](../../../archive/eval-results/sidecar_retention_20260921/evidence/retention-summary.md) | Riuso degli hard link, lettori protetti e spazio fisico deduplicato su NTFS |

Il codice misurato è `708a142`, confrontato con `0f479b2`; la revisione finale
corregge l'attribuzione delle scritture NPY da `parsing_embedding` a `save_hash`.
I breakdown storici conservano il limite documentato in PHASE6; totali, byte e
risorse non sono stati ricalcolati. Non sono misure di qualità delle risposte LLM.
Corpus e hardware limitano la generalizzazione: nessun crossover delta/full,
capacità massima o soglia universale di sharding dimostrati.

## Valutazioni Propose e conservazione delle evidenze

**Fase 2 chiusa, 14 settembre 2026:** [resoconto finale dei tre giri Propose](FASE2_PROPOSE_20260914.md).
Alla chiusura: miglioramento qualitativo non dimostrato; V3 non adottata, V4 respinta.
Il resoconto include la riserva sul perimetro FE3-F4, da applicare anche ai
conteggi FE3 riportati più sotto. Nessuno starter o pilot avviato.

**Passaggio successivo:** V3 adottata in `a8b2416`, con limite noto sui confini
delle funzionalità. [Confronto strutturale dopo l'adozione](propose_adopted_v3_20260914/evidence/RESULTS.md):
sei risposte nuove contro le sei `bd87bd7^` conservate, senza giudizio sostanziale.
Il prompt attuale include anche il resoconto advisory: non isola la sola modifica
sulle ambiguità. Il resoconto finale conserva i tre giri precedenti e include
ora l'esito successivo: più punti dichiarati senza calo dei conteggi strutturali;
qualità sostanziale non rivalutata. I punti dichiarati nel testo erano 6/6,
ma il parser ne riconosceva solo 2/6 come resoconti validi. Corretto il
riconoscimento dei titoli numerati: ora 5/6 valid e 1/6 invalid per JSON
malformato, senza riparazioni automatiche. [Ricalcolo](propose_adopted_v3_20260914/evidence/PARSER_RECHECK.json).

`history.jsonl` conserva gli eventi aggregati della pagina `/eval`. I dati che
permettono di esaminarli vivono in `<run>/evidence/`. Fuori da quella cartella gli
artefatti restano locali: non basta l'estensione JSON per renderli evidenze.

Per ogni run conservare metriche aggregate e per caso, risposte, fonti e verdetti,
parametri/prompt e comando usato, versioni di modello, indice, corpus e codice
quando disponibili. Un dato non registrato va dichiarato mancante, mai ricostruito
come se fosse stato misurato. Prima di aggiungere un evento allo storico,
pubblicare le sue evidenze e documentarne il collegamento tramite timestamp UTC,
versione dell'indice e tipo di valutazione (`source`).

Pesi di modelli, cache, copie del codice/corpus e intermedi rigenerabili restano
fuori da `evidence/`. I log diagnostici restano locali; quando un log è l'unica
prova di un gate, conservarne le righe pertinenti con numero di riga e hash del
file originale. Le evidenze di attribuzione richiedono anche il testo e le fonti:
un punteggio aggregato da solo non consente di rivedere il verdetto.

## Conservazione dei run del 7–11 settembre 2026

Le 17 cartelle preesistenti sono state conservate senza rieseguire le valutazioni
e senza cancellare gli originali. Ogni `EVIDENCE_MANIFEST.json` elenca origine,
percorso della copia, dimensione e SHA-256, oltre ai file lasciati locali.
I percorsi `path` sono relativi a questa cartella; `source` alla root del repo.
`.gitattributes` preserva i byte delle prove anche nei checkout Windows.

Gli script storici sono archiviati come `.py.txt`, `.sh.txt`, `.ps1.txt` o
`.cjs.txt`: sono prove del procedimento, non codice applicativo da eseguire o
scoprire con lint/pytest. Comandi e report mantengono i riferimenti all'ambiente
originale; riprodurli richiede ricostituire i percorsi e disporre delle versioni
indicate. Le copie non attestano che quell'ambiente sia ancora disponibile.

Non tutte queste run producono eventi in `history.jsonl`: molte misurano parsing,
attribuzione, contesto o conversione. Non vanno confuse con il retrieval generale
né considerate una misura delle recenti modifiche al prompt di pipeline.

## Collegamento degli 11 eventi del 7–11 settembre 2026

Ogni record di questo gruppo in `history.jsonl` dichiara `evidence`: `full` per
un report per caso disponibile (5), `partial` per un estratto del gate senza
dettaglio per caso (2), `none` quando non è stata rintracciata una prova
indipendente (4). `full` descrive la disponibilità del report, non certifica la
riproducibilità dell'ambiente né la qualità della risposta. I record precedenti
senza questo campo non sono stati classificati: l'assenza non significa `full`.
Alla verifica del 14 settembre 2026, lo storico contiene 137 record: solo questi
11 sono classificati e gli altri 126 non lo sono. La suddivisione 5 / 2 / 4 e
qualsiasi riepilogo basato sul campo `evidence` descrivono quindi soltanto il
sottoinsieme classificato, non l'intero storico.

Gli orari seguenti sono UTC. I report dell'8 settembre usano l'ora locale italiana
(UTC+2); il nome `153456` precede di circa un secondo l'append dello storico.
Le associazioni si basano su orario, tipo e metriche, non sul solo nome della
cartella. I cinque report per caso non registrano direttamente `index_version`:
la versione indicata è quella dell'evento nello storico, coerente con i resoconti
P0/pilot; questa correlazione non sostituisce un identificatore salvato nella run.
`history.jsonl` non contiene attualmente un riferimento al report.

| Evento UTC | Indice | Prova conservata | Copertura |
|---|---|---|---|
| 07/09 14:58:11 gate | `v20260907T145734` | Nessun report autonomo rintracciato | Solo evento aggregato locale; mancano prove indipendenti del gate |
| 07/09 15:09:38 gate | `v20260907T150309` | Nessun report autonomo rintracciato | Solo evento aggregato locale; mancano prove indipendenti del gate |
| 07/09 15:21:51 gate | `v20260907T151549` | Nessun report autonomo rintracciato | Solo evento aggregato locale; mancano prove indipendenti del gate |
| 08/09 13:31:15 gate | `v20260908T132451` | [Estratto del log originale](p0_20260908-152239/evidence/gate_log_excerpt.json) | Recall@2, soglia, numero casi e promozione; nessun dettaglio per caso del gate |
| 08/09 13:34:47 eval.run | `v20260908T132451` | [Report retrieval](p0_20260908-152239/evidence/original_eval/eval_20260908_153447.json) | Report per caso |
| 08/09 13:34:57 multihop | `v20260908T132451` | [Report multihop](p0_20260908-152239/evidence/original_eval/multihop_20260908_153456.json) | Report per caso |
| 08/09 13:39:02 eval.run | `v20260908T132451` | [Report retrieval](p0_20260908-152239/evidence/original_eval/eval_20260908_153902.json) | Report per caso |
| 08/09 13:39:12 multihop | `v20260908T132451` | [Report multihop](p0_20260908-152239/evidence/original_eval/multihop_20260908_153912.json) | Report per caso |
| 08/09 15:13:52 multihop | `v20260908T132451` | [Report multihop](../../../archive/eval-results/pilot_docling_20260908-170030/evidence/out/multihop_20260908_171352.json) | Report per caso |
| 10/09 12:18:45 gate | `v20260910T121150` | [Estratto del log originale](../../../archive/eval-results/verifica_finale_20260910/evidence/gate_log_excerpt.json) | Recall@2, soglia, numero casi e promozione; nessun dettaglio per caso del gate |
| 11/09 15:54:05 gate | `v20260911T155042` | Nessun report autonomo rintracciato | Solo evento aggregato locale; mancano prove indipendenti del gate |

Le quattro lacune non sono state riempite duplicando lo storico o rieseguendo
oggi il codice: nessuna delle due operazioni produrrebbe la prova della run
storica. I quattro eventi sono conservati con `evidence: "none"`, senza
attribuire loro prove o verifiche che non abbiamo recuperato.

## Giudice di attribuzione — concordanza sul campione di taratura

Il risultato storico 20/24 è una concordanza sui medesimi 24 record usati per
tarare il prompt del giudice, attraverso sei varianti, come documentato in
[AUDIT, S14](../../adr/AUDIT.md). Non è una stima di accuratezza su casi nuovi:
non va usato come affidabilità del giudice, limite di errore o base per le
conclusioni della Fase 2. Resta esclusivamente un risultato di taratura.

Una futura stima di accuratezza richiede record con verdetti umani indipendenti,
mai usati per scegliere o modificare il prompt, e il congelamento del giudice
prima della valutazione. I risultati del giudice restano separati dai
[verdetti umani archiviati](../golden_attribution.yaml): questa nota non li
modifica e non certifica la loro validità sull'indice attuale.

## Ablazione Propose del 14 settembre 2026 — confronto descrittivo

Confrontati i file interi di `rag/prompts/spec.md` in `bd87bd7^` e `bd87bd7`,
su FE3 e LA2 con tre ripetizioni per combinazione (12 risposte), Canvas e fonti
congelati e lo stesso modello. Le due modifiche di `bd87bd7` — assunzioni
dichiarate/punti aperti e numero di scenari per funzionalità — sono misurate
insieme: questo confronto non ne separa gli effetti e non misura MCP o il gate.

Evidenze: [protocollo](../../../archive/eval-results/propose_ablation_20260914/evidence/PROTOCOL.md),
[nota di metodo](../../../archive/eval-results/propose_ablation_20260914/evidence/HUMAN_REVIEW.md),
[schede FE3](../../../archive/eval-results/propose_ablation_20260914/evidence/REVIEW_FE3.md),
[schede LA2](../../../archive/eval-results/propose_ablation_20260914/evidence/REVIEW_LA2.md),
[chiave](../../../archive/eval-results/propose_ablation_20260914/evidence/AFTER_REVIEW/KEY.json) e
[misure provider](../../../archive/eval-results/propose_ablation_20260914/evidence/AFTER_REVIEW/MEASUREMENTS.json).
La nota di metodo e le intestazioni delle schede sono state completate prima
dell'apertura della chiave. La revisione è umana con assistenza di Claude;
ordine di accesso alle fonti diverso fra FE3 e LA2, 13 rilievi sul protocollo
e 3 affermazioni non valutabili restano limiti espliciti della misura.

| Conteggio | `bd87bd7^` | `bd87bd7` |
|---|---:|---:|
| Ambiguità preregistrate dichiarate, FE3 + LA2 | 0 / 27 | 3 / 27 |
| FE3: F elencate nel campo nominale e negativo coperti | 7 | 2 |
| LA2: F elencate nel campo nominale e negativo coperti | 6 | 4 |
| FE3: affermazioni supported / valutabili | 18 / 28 | 19 / 25 |
| FE3: unsupported / conflicted / not_assessable | 4 / 6 / 0 | 4 / 2 / 0 |
| LA2: affermazioni supported / valutabili | 18 / 34 | 13 / 33 |
| LA2: unsupported / conflicted / not_assessable | 2 / 14 / 2 | 1 / 19 / 1 |
| Intestazioni SCENARIO per risposta, su entrambe le feature | 7 in 6/6 risposte | 4 in 6/6 risposte |

Le ambiguità sono sommate sulle tre ripetizioni: 9 opportunità FE3 e 18 LA2
per gruppo, non 27 dubbi distinti. La copertura elencata scende FE3 7→2 e
LA2 6→4; sono conteggi letterali dei campi delle schede, con le riserve già
annotate (P06 su F2; P07 su F1 e F5), non coperture complete certificate né
scenari soddisfatti da codice. Il rapporto supported/valutabili e il numero di
conflicted vanno in direzioni opposte sulle due feature; i conteggi delle
affermazioni restano separati da copertura e omissioni.

La separazione 7/4 nel numero di scenari è netta su tutte le risposte. FE3 ha
quattro funzionalità attese e LA2 cinque: il minimo teorico sarebbe 8 e 10
scenari rispettivamente, salvo casi irrisolti dichiarati. Il conteggio degli
scenari può spiegare il calo di copertura indipendentemente dalla modifica
sulle assunzioni e sui punti aperti; è un'ipotesi da verificare, non una causa
isolata da questa ablazione. Il prompt contiene la regola esplicita per
funzionalità, ma anche il richiamo «Per la copertura che eccede i 4 scenari»
senza ripeterne l'ambito. Nessuna correzione del prompt o nuova generazione
è stata effettuata per questa registrazione.

Il riepilogo P08 è stato corretto da 7/9 a 6/9 supported, conformemente alle
nove righe della sua tabella (6 supported, 2 unsupported, 1 conflicted);
nessun verdetto atomico è cambiato. I file meccanici in AFTER_REVIEW conservano
lo stato precedente alla revisione: i conteggi umani sopra provengono dalle
schede aggiornate. Nessuno starter o pilot avviato.

## Punto aperto — cache condivisa dei prossimi pilot Docling

I circa 701 MB di pesi trovati nella run del pilot isolato non derivano dal
percorso applicativo attuale: [lo script storico](../../../archive/eval-results/pilot_docling_standard_20260909-095127/evidence/run_standard.py.txt)
riceveva `artifacts_path` come argomento e [il report della run](../../../archive/eval-results/pilot_docling_standard_20260909-095127/evidence/run2/run_report.json)
lo colloca in `pilot_docling_standard_20260909-095127/artifacts`.
L'applicazione usa già `intake.docling.models_dir`, configurato come
`rag/database/models/docling`, e verifica gli SHA-256 prima del caricamento
(`core/intake_convert.py`). Nessun peso è stato spostato.

Prima del prossimo pilot verificare che riusi quel percorso condiviso e che le
revisioni richieste coincidano con quelle fissate in `scripts/docling_models.py`
e con gli hash attesi dal pilot. Da `rag/`, `scripts/docling_models.py --verifica`
controlla i pesi applicativi senza scaricarli; non certifica da solo la compatibilità
di un pilot che richieda revisioni diverse. Registrare nella nuova evidenza percorso
risolto, revisioni e hash effettivi, verificando che la run non contenga nuove copie
dei pesi. Se servono revisioni diverse, prevedere una cache condivisa distinta per
revisione senza sovrascrivere i pesi applicativi. Verifica dei prossimi pilot ancora
da eseguire; nessuna migrazione o modifica al loro codice in questo intervento.
