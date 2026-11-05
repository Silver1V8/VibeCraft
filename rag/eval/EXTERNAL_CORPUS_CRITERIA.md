# Criteri di selezione corpus indipendente (S-A2-0)

Stato: **C1 scelto e misurato** — OWASP ASVS 4.0.3 (`eval/external/manifest.json`).
Originali e metadati operativi fuori da questo checkout: `projects/external_asvs/`.
Vedi `EXTERNAL_TRANSFER.md` per la misura `asvs-4.0.3-20261105`.

Non sostituisce `EXTERNAL_TRANSFER.md`: lo affianca con criteri di selezione.
Collegato da `docs/eval-e-ci.md`.

## Condizioni obbligatorie (manifest)

Tutte insieme, come in `EXTERNAL_TRANSFER.md`:

- `terza_parte: true`
- `provenienza`, `versione`, `licenza`, `autorizzazione` non vuote
- `originali_conservati: true` e `metadati_aggiunti_separati: true`
- `generated` / `scritto_per_il_sistema` / `costruito_per_favorire_il_sistema` = `false`

## Preferenze di selezione

1. Dominio normativo o tecnico con sezioni citabili (non solo FAQ).
2. Licenza che consente indicizzazione locale e conservazione degli originali.
3. Dimensione gestibile su hardware locale (Qdrant + BGE-M3 + Ollama).
4. Q/A attese verificate da umani, con casi `no_answer`.
5. Nessuna sovrapposizione sostanziale col corpus `legacy` di sviluppo.

## Split

- `dev` / `tuning` / `test` disgiunti
- Prima misura: configurazione congelata, `--used-for-tuning no`
- Eventuale ricalibrazione = esperimento separato

## Misure (run `asvs-4.0.3-20261105`)

| Misura | Stato |
|---|---|
| Recall@5/@10, MRR | misurato (1.0 / 1.0 / 0.883) — set piccolo |
| Astensione su `no_answer` | misurato (2/2, via `/ask` → `answered=false`) |
| Attribuzione/autorità | non nello strumento + senza etichette |
| Correttezza risposta | non annotata oltre l'astensione |
| Precisione IMPLEMENTS esterna | N/A (ASVS senza codice progetto) |
| Validazione sistema | **no** (`validato: false`) |

## Prossimi passi (opzionali)

1. Set test più duro/ampio (parafrasi, conflitti di capitolo, multi-hop) ancora human-verified.
2. Non riusare le domande di test per tuning.
3. Non promuovere i numeri a “validato” senza protocollo di validazione separato.
