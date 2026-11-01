---
name: reindex-full
description: Full rebuild sicuro dell'indice — riavvio del server PRIMA del rebuild, POST reindex full, poll del job, esito eval gate e versione promossa
disable-model-invocation: true
---

# /reindex-full — rebuild completo dell'indice

Un full rebuild usa il codice importato al boot del server: se lanci il reindex senza
riavviare, gira con la versione vecchia di `core/indexing.py` e butti ~10 minuti di embedding
(build ~600-635 s su questo corpus). L'ordine sotto non è negoziabile.

## Passi

1. **Stop** del server sulla porta 8000 (preview_stop se avviato con preview_start, altrimenti
   ferma il processo in ascolto su 8000).
2. **Start** con preview_start `{name: "vibecraft-rag"}` (esegue `rag/scripts/run_server.ps1`,
   che carica `rag/.env.local`).
3. **Attendi** `GET http://127.0.0.1:8000/api/health` → 200 (il boot richiede ~10 s; poll ogni 2 s,
   massimo 60 s).
4. **Avvia** il rebuild. La chiave sta in `rag/.env.local` (`VIBECRAFT_API_KEY`): leggila nello
   stesso comando, senza stamparla né ripeterla in chat.

   ```bash
   KEY=$(grep -E '^VIBECRAFT_API_KEY=' rag/.env.local | cut -d= -f2-) && curl -s -X POST http://127.0.0.1:8000/api/index/reindex -H "X-API-Key: $KEY" -H "Origin: http://127.0.0.1:8000" -H "Content-Type: application/json" -d '{"full": true}'
   ```

   Risposta 202 con `job_id` (con `"queued": true` se c'era già un job: quel job_id è il pending).
5. **Poll** `GET /api/reindex/<job_id>` ogni 30 s fino a uno stato terminale:
   `completed`, `completed_not_promoted`, `failed`. Usa Monitor o un ciclo con timeout, non sleep
   lunghi in foreground.
6. **Esito**: riporta stato, durata, risultato dell'eval gate e la versione attiva da
   `GET /api/index/versions` (`current`). Se `completed_not_promoted`, la versione è stata
   costruita ma l'eval gate l'ha respinta: NON promuoverla a mano, riporta le metriche e fermati.
   Se `failed`, leggi il log del server (preview_logs) per il motivo.

Rollback disponibile via `POST /api/index/rollback`, solo su richiesta esplicita.
