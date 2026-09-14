# Evidenze delle valutazioni

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

## Collegamento delle 11 aggiunte pendenti allo storico

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
| 08/09 15:13:52 multihop | `v20260908T132451` | [Report multihop](pilot_docling_20260908-170030/evidence/out/multihop_20260908_171352.json) | Report per caso |
| 10/09 12:18:45 gate | `v20260910T121150` | [Estratto del log originale](verifica_finale_20260910/evidence/gate_log_excerpt.json) | Recall@2, soglia, numero casi e promozione; nessun dettaglio per caso del gate |
| 11/09 15:54:05 gate | `v20260911T155042` | Nessun report autonomo rintracciato | Solo evento aggregato locale; mancano prove indipendenti del gate |

Le quattro lacune non sono state riempite duplicando lo storico o rieseguendo
oggi il codice: nessuna delle due operazioni produrrebbe la prova della run
storica. Prima del commit dello storico occorre decidere se conservarle come
eventi storici con questa limitazione dichiarata o recuperare i report originali.
