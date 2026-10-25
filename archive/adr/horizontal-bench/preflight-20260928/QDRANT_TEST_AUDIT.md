# Incidente di isolamento dei test — 28 settembre 2026

Due esecuzioni di `tests/test_qdrant_blue_green.py` hanno usato involontariamente il servizio operativo `vibecraft-qdrant-1`, esposto su `127.0.0.1:6333`. Il primo run era la baseline PM prima di P2; il secondo era la verifica storage P2. La fixture preesistente rilevava automaticamente il servizio tramite `QDRANT_URL`, con default 6333. Questo ha violato il vincolo di non scrivere sui servizi operativi, anche se i test usavano nomi dedicati.

## Prova e ambito

Ispezione esclusivamente in lettura tramite `docker logs`. L'estratto `qdrant-test-side-effects.log` conserva tutte le righe nelle finestre UTC 07:44:20–29 e 08:06:20–29. Le richieste osservate vanno da 07:44:23.743 a 07:44:26.650 e da 08:06:23.006 a 08:06:25.819. Il log mostra creazione/eliminazione collection, modifiche alias, upsert e delete di punti.

Nomi osservati (prefisso comune `_test_blue_green_`):

- `scaffolding_a`, `scaffolding_b`, `scaffolding_alias`;
- `legacy_collision`, `legacy_collision_target`;
- `ensure_physical`, `ensure_alias`;
- `delete_physical`, `delete_alias`;
- `dangling_physical`.

Gli endpoint sono `/collections/<nome>`, `/collections/aliases`, `/collections/<nome>/points`, `/points/delete`, `/points/count` e `/points/scroll`. Il corpo delle chiamate alias non è nel log HTTP; i cinque test corrispondenti nel sorgente specificano i nomi dedicati sopra. I log mostrano DELETE conclusivi 200 sulle collection fisiche create. Nessun cleanup operativo è stato eseguito durante l'audit.

La verifica successiva della root, esclusivamente in lettura alle 08:09:15 UTC, è in `operational-readonly-check.json`: CURRENT `v20260922T095110`, collection `vibecraft_events__v20260922T095110`, alias coerente, 286 chunk e 286 punti con gli stessi `chunk_id`, zero mancanti/extra/duplicati. Certifica questa consistenza attuale di identificatori, conteggi e alias; non dimostra che lo storico sia rimasto invariato, non confronta i vettori e non certifica l'assenza generale di residui.

Test coinvolti: `test_alias_semantics_against_real_qdrant`, `test_real_qdrant_rejects_alias_with_same_name_as_existing_collection`, `test_real_qdrant_rejects_create_collection_on_an_alias_name`, `test_real_qdrant_delete_by_filter_resolves_the_alias`, `test_real_qdrant_delete_collection_invalidates_its_aliases`.

## Correzione

Le verifiche successive impostano esplicitamente `QDRANT_URL=http://127.0.0.1:16333` con il container dedicato fermo, `HF_HUB_OFFLINE=1` e `TRANSFORMERS_OFFLINE=1`. La fixture viene corretta per richiedere un endpoint di test esplicitamente autorizzato, senza ricadere sul servizio configurato per l'applicazione. Nessun altro intervento è stato eseguito sul Qdrant operativo durante l'audit.
