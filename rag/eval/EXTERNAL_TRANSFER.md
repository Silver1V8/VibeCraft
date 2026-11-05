# Trasferimento esterno

Strumento: `scripts/external_transfer.py`. Modulo: `eval/external_transfer.py`.

Qui si misura se la configurazione **già fissata** regge su un corpus che il sistema non ha mai visto. Non è la calibrazione interna del golden set di questo repository, e non serve a scegliere parametri.

Collegato da `docs/eval-e-ci.md`. Affianca `EXTERNAL_CORPUS_CRITERIA.md` e `EXTERNAL_CORPUS_SHORTLIST.md`. Aggiornato su istruzione utente di allineare la tabella di stato al run `asvs-4.0.3-20261105` (non sostituisce il protocollo di misura sotto).

## Stato

| Pezzo | Stato |
|---|---|
| Protocollo e controllo del manifest | implementato |
| Definizioni di Recall@k e MRR, e il codice che le calcola | implementato, testato su fixture |
| Corpus di terzi autorizzato | **C1 OWASP ASVS 4.0.3** (`eval/external/manifest.json`; originali fuori repo in `projects/external_asvs/originals/`) |
| Verifica umana delle risposte attese | **fatta** (`$ilver`, 2026-11-05): 12 casi in `projects/external_asvs/metadata/cases_test.json` |
| Misura di trasferimento | **misurato** run `asvs-4.0.3-20261105` (config frozen, `--used-for-tuning no`): Recall@5/10 **1.0**, MRR **0.883**, astensione **2/2** |
| Validazione | **non validato** (misurare ≠ validare; set piccolo e a un capitolo/domanda) |

Copia in-repo del report: [external/transfer_asvs-4.0.3-20261105.json](external/transfer_asvs-4.0.3-20261105.json). Evidenza operativa completa (casi + `retrieved` + `/ask`) resta sotto `projects/external_asvs/metadata/` (fuori da questo checkout git).

Un corpus sintetico non va creato per far diventare verde lo strumento. Senza `--cases` / senza human-verified lo stato torna `in attesa` o `bloccato` come da protocollo sotto.

## Quando un corpus è indipendente

Tutte queste condizioni, nel manifest, insieme:

- `terza_parte: true`;
- `provenienza`, `versione`, `licenza`, `autorizzazione`: stringhe non vuote. L'autorizzazione è il permesso di usare quel corpus, non una frase del tipo "generato per il test";
- `originali_conservati: true` e `metadati_aggiunti_separati: true` (ciò che aggiungiamo noi sta fuori dagli originali e si può risalire);
- `generated`, `scritto_per_il_sistema` e `costruito_per_favorire_il_sistema` dichiarati `false`. Una chiave assente, o la stringa `"false"`, non basta.

Manca una sola: lo stato è `bloccato` e il corpus non si chiama indipendente. Un corpus scritto per questo sistema, anche se grande, non lo è.

## Prima della misura, non durante

Congelare configurazione e criteri prima del test. Tre insiemi disgiunti: sviluppo, tuning, test. Il test non si usa per scegliere soglie, α, pesi di autorità o il linking. La prima misura è il trasferimento della configurazione corrente, senza ricalibrarla. Un tuning sul corpus esterno è un altro esperimento, e non usa le domande del test.

Controlli sul test, prima di calcolare:

- domande duplicate dopo normalizzazione degli spazi: lo strumento le segnala e blocca la misura. Le parafrasi e le quasi-copie non le decide lui: le guarda un umano;
- per ogni domanda: fonti attese, conflitti, riformulazioni, e i casi in cui la risposta giusta è astenersi;
- un umano verifica le risposte attese. Senza quel segno lo stato resta `in attesa di annotazioni` e i numeri non si calcolano.

## Definizioni

- **Recall@k binaria.** Sulle sole domande con almeno una fonte attesa: 1 se almeno una di quelle fonti è fra le prime k, altrimenti 0. Poi la media. Non è `|attese ∩ primi k| / |attese|`. k va dichiarato (lo strumento riporta 5 e 10).
- **MRR.** Sulle stesse domande: media di `1/rank` della prima fonte attesa, con rank che parte da 1. Se non c'è, 0.
- **Astensione.** Solo sulle domande annotate `no_answer`, e solo su quelle con il campo booleano `answered` (il sistema ha risposto?). Le fonti recuperate non contano: il retriever restituisce sempre i primi k. Le domande senza `answered` stanno in `senza_esito`. Non entra nel denominatore di Recall@k né di MRR.
- **Attribuzione e autorità della fonte.** Si contano a parte, solo dove un umano ha detto quale fonte e quale autorità erano quelle giuste. Lo strumento non ha ancora quel conteggio: senza quelle etichette non si inventa.
- **Correttezza della risposta.** Solo se la risposta è annotata. Un giudice automatico non sostituisce quel giudizio, e non va presentato come se lo fosse.
- **Collegamento norma–codice.** Solo se c'è codice pertinente e un giudizio umano sull'arco. Non si trasferisce qui il tasso di errore di un altro sistema, né la precisione degli IMPLEMENTS di questo repository (vedi `LINK_AUDIT.md`).

Un risultato `misurato` richiede anche almeno un caso utilizzabile, `run_id`, split `test`, configurazione congelata, e `--used-for-tuning no` dichiarato: se il flag manca, le domande contano come usate per il tuning. `validato` resta falso: misurare una run non è validare il sistema. I numeri pubblici non si aggiornano da una run senza quel `run_id` e senza il manifest.

## Limiti della run corrente (non negoziabili in lettura)

- Set di 12 domande (10 con fonte + 2 `no_answer`), una fonte attesa tipicamente = un capitolo ASVS: claim di trasferimento **debole** finché non c'è un set più duro/ampio human-verified.
- `validato: false` è l'esito corretto del protocollo, non un bug dello strumento.

## Set più duro (misurato, non validato)

Casi human-verified (`$ilver`, 2026-11-05):
`projects/external_asvs/metadata/cases_hard_test.json` (12 casi: cross-chapter,
parafrasi, near-miss, conflitti, `no_answer`).

Run `asvs-hard-20261105` (config frozen, `--used-for-tuning no`):
Recall@5/@10 **1.0**, MRR **0.933**, astensione **2/2**.
Report in-repo: [external/transfer_asvs-hard-20261105.json](external/transfer_asvs-hard-20261105.json).
`validato` resta **false**.
