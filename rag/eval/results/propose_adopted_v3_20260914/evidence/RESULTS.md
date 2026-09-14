# V3 adottata contro bd87bd7^ — conteggi descrittivi

Sei nuove risposte del prompt a8b2416 e sei vecchie riutilizzate. Nessuna revisione sostanziale.
F toccata non equivale a caso nominale/negativo coperto o scenario soddisfatto.
FE3-F4 ha perimetro ambiguo: presenza separata, assenza NON conteggiata come lacuna.
Mappatura letta dall'assistente; conteggi non equivalgono a verdetti umani.

| Feature | Gruppo | Campione | Scenari | F toccate (FE3: solo F1–F3) | FE3-F4 | Sezione PA | Punti dichiarati | Stato report runtime |
|---|---|---|---:|---|---|---|---:|---|
| FE3 | bd87bd7^ | P11 | 7 | F1, F2, F3 | no | no | 0 | missing |
| FE3 | bd87bd7^ | P03 | 7 | F1, F2, F3 | no | no | 0 | missing |
| FE3 | bd87bd7^ | P06 | 7 | F1, F2, F3 | no | no | 0 | missing |
| FE3 | current | fe3_current_r1 | 7 | F1, F2, F3 | no | sì | 1 | valid |
| FE3 | current | fe3_current_r2 | 7 | F1, F2, F3 | no | sì | 1 | valid |
| FE3 | current | fe3_current_r3 | 7 | F1, F2, F3 | no | sì | 1 | missing |
| LA2 | bd87bd7^ | P02 | 7 | F1, F2, F3, F4 | — | no | 0 | missing |
| LA2 | bd87bd7^ | P09 | 7 | F1, F2, F3, F4 | — | no | 0 | missing |
| LA2 | bd87bd7^ | P07 | 7 | F1, F2, F3, F4, F5 | — | no | 0 | missing |
| LA2 | current | la2_current_r1 | 8 | F1, F2, F3, F4 | — | sì | 1 | missing |
| LA2 | current | la2_current_r2 | 10 | F1, F2, F3, F4 | — | sì | 1 | missing |
| LA2 | current | la2_current_r3 | 8 | F1, F2, F3, F4, F5 | — | sì | 1 | missing |

Punti dichiarati conta record, non domande interne o dubbi correttamente dichiarati.
Zero con sezione assente significa zero dichiarazioni osservate, non un report valido con [].
Un titolo numerato può avere record JSON leggibili ma risultare missing al parser applicativo:
la forma canonica richiede esattamente `## Punti aperti`. Non si correggono gli output.

LA2 current r2: il punto dichiarato è contato per lettura (un record OP-001), ma il JSON
manca della graffa finale. Non è un resoconto valido; nota conservata in MAPPING.json.

Il prompt attuale include conteggio V3, nota sul limite e resoconto strutturato advisory.
Il confronto con bd87bd7^ NON isola la sola modifica sulle ambiguità, né elimina la deriva fra lotti.
Protocollo e fonti sono congelati; riserva F4 applicata simmetricamente senza riscrivere le schede storiche.

Durata delle sei generazioni: 177.312 secondi.

[Protocollo](PROTOCOL.md) · [Addendum](ADDENDUM.md) · [Manifest](manifest.json) · [Risposte nuove](responses/) · [Mappatura](MAPPING.json) · [Conteggi](STRUCTURAL.json) · [Verifica](VERIFICATION.json)
