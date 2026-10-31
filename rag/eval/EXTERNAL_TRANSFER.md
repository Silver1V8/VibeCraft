# Trasferimento esterno

Strumento: `scripts/external_transfer.py`. Modulo: `eval/external_transfer.py`.

Qui si misura se la configurazione **già fissata** regge su un corpus che il sistema non ha mai visto. Non è la calibrazione interna del golden set di questo repository, e non serve a scegliere parametri.

## Stato

| Pezzo | Stato |
|---|---|
| Protocollo e controllo del manifest | implementato |
| Definizioni di Recall@k e MRR, e il codice che le calcola | implementato, testato su fixture |
| Corpus di terzi autorizzato | assente. Stato: bloccato |
| Verifica umana delle risposte attese | in attesa di annotazioni |
| Misura di trasferimento | non misurato |
| Validazione | non validato |

`scripts/external_transfer.py` senza argomenti esce 2. Il percorso di default `eval/external/manifest.json` non esiste. Non va creato un corpus sintetico per far diventare verde quel comando.

## Quando un corpus è indipendente

Tutte queste condizioni, nel manifest, insieme:

- `terza_parte: true`;
- `provenienza`, `versione`, `licenza`, `autorizzazione`: stringhe non vuote. L'autorizzazione è il permesso di usare quel corpus, non una frase del tipo "generato per il test";
- `originali_conservati: true` e `metadati_aggiunti_separati: true` (ciò che aggiungiamo noi sta fuori dagli originali e si può risalire);
- `generated`, `scritto_per_il_sistema` e `costruito_per_favorire_il_sistema` non sono true.

Manca una sola: lo stato è `bloccato` e il corpus non si chiama indipendente. Un corpus scritto per questo sistema, anche se grande, non lo è.

## Prima della misura, non durante

Congelare configurazione e criteri prima del test. Tre insiemi disgiunti: sviluppo, tuning, test. Il test non si usa per scegliere soglie, α, pesi di autorità o il linking. La prima misura è il trasferimento della configurazione corrente, senza ricalibrarla. Un tuning sul corpus esterno è un altro esperimento, e non usa le domande del test.

Controlli sul test, prima di calcolare:

- domande duplicate dopo normalizzazione degli spazi: lo strumento le segnala e blocca la misura. Le parafrasi e le quasi-copie non le decide lui: le guarda un umano;
- per ogni domanda: fonti attese, conflitti, riformulazioni, e i casi in cui la risposta giusta è astenersi;
- un umano verifica le risposte attese. Senza quel segno lo stato resta `in attesa di annotazioni` e i numeri non si calcolano.

## Definizioni, se un giorno il manifest c'è

- **Recall@k binaria.** Sulle sole domande con almeno una fonte attesa: 1 se almeno una di quelle fonti è fra le prime k, altrimenti 0. Poi la media. Non è `|attese ∩ primi k| / |attese|`. k va dichiarato (lo strumento riporta 5 e 10).
- **MRR.** Sulle stesse domande: media di `1/rank` della prima fonte attesa, con rank che parte da 1. Se non c'è, 0.
- **Astensione.** Solo sulle domande annotate `no_answer`. Non entra nel denominatore di Recall@k né di MRR.
- **Attribuzione e autorità della fonte.** Si contano a parte, solo dove un umano ha detto quale fonte e quale autorità erano quelle giuste. Lo strumento non ha ancora quel conteggio: senza quelle etichette non si inventa.
- **Correttezza della risposta.** Solo se la risposta è annotata. Un giudice automatico non sostituisce quel giudizio, e non va presentato come se lo fosse.
- **Collegamento norma–codice.** Solo se c'è codice pertinente e un giudizio umano sull'arco. Non si trasferisce qui il tasso di errore di un altro sistema, né la precisione degli IMPLEMENTS di questo repository (quella, finché le schede non sono compilate, è `precisione non ancora misurata`: vedi `LINK_AUDIT.md`).

Un risultato `misurato` richiede anche `run_id`, split `test`, configurazione congelata, e `used_for_tuning` falso. `validato` resta falso: misurare una run non è validare il sistema. I numeri pubblici non si aggiornano da una run senza quel `run_id` e senza il manifest.
