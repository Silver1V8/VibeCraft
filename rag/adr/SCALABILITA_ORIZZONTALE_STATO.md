# Stato — scalabilità orizzontale

## Checkpoint 2026-09-22 — audit concluso, gate root

- Workspace: `C:/Users/Silve/.codex/worktrees/horizontal-scaling/vibecraft`.
- Branch: `codex/horizontal-scaling`; base `ea0cf91425a5d01b39ed821c714cd397a6e0d2b0`.
- [x] Audit codice: Sol runtime; Terra benchmark; consolidamento PM Astra.
- [x] Specifica e piano in `rag/adr/SCALABILITA_ORIZZONTALE{,_PIANO}.md`.
- [ ] Review/gate root prima del codice prodotto.
- [ ] P0 benchmark e baseline isolata.
- [ ] P1 pin collection, ammissione e streaming.
- [ ] P2 reader/writer e immutabilità locale.
- [ ] P3 misure reali k=1,4,8, review e consegna.

Nessun codice prodotto modificato; nessun server/modello avviato; nessun DB operativo toccato. La fattibilità del software è positiva; capacità hardware e beneficio prestazionale sono ancora da misurare. Async LLM e semaforo embedding2 esistono già. Replica iniziale stessa macchina: dati versione RO, coordinamento lease RW. Cross-host non ancora supportato. Incrementale rifiutato esplicitamente nel profilo immutable; full richiesto.

Ultima quota PM dopo audit/documenti: 9% residua (91% usata), uso consentito, nessun spend control. Margine prima dello stop: 4 punti percentuali; avviare solo P0 circoscritto, non fanout core. Ricontrollare prima di ogni fase/fanout e dopo. Stop <=5% in qualsiasi finestra, uso vietato o spendControlReached; ripresa solo >=15% in tutte e uso consentito. Non consumare reset/acquistare crediti. Heartbeat gestito dalla root.

## Ripresa

1. Leggere quota live, stato Git, spec e piano; nessun affidamento alle percentuali storiche.
2. Ottenere esito review root; procedere fase più piccola sostenibile, senza riconferma generica utente già autorizzato.
3. Eseguire test dalla directory `rag` nel worktree con `C:/Users/Silve/Desktop/vibecraft/rag/.venv/Scripts/python.exe -m pytest ...` come nel piano. Dataset e servizi devono essere isolati.
4. Aggiornare qui commit, test/benchmark eseguiti, raw/provenienza e ciò che manca prima di ogni sospensione.

## Evidenze

- `git rev-parse HEAD`: base sopra.
- `git switch -c codex/horizontal-scaling`: riuscito.
- Audit statico: `/ask` omette collection_name; boot ripara alias+GC; ReindexManager può scrivere journal all'import; descrizioni/fallback prompt leggono docs live; incrementale muta collection in place; lease file RW locale.
- Nessun benchmark runtime eseguito in fase audit. Vecchio p50 sequenziale non utilizzato come prova.

- Verifica documenti: copertura spec↔P0/P1/P2/P3 riletta; piano include proxy/auth, lease→manifest→collection e distinzione concorrenza HTTP/inferenza. Solo tre nuovi Markdown previsti.
