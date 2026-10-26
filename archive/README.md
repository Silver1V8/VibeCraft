Italiano | [English](README.en.md)

# Archivio

Materiale storico di sviluppo: nessun codice a runtime lo legge, non entra nell'immagine
Docker (`Dockerfile` copia solo `rag/`, `docs/` e `code/`; questa cartella resta comunque
fuori dal contesto di build, vedi `.dockerignore`) e non serve per far girare i test.
È conservato per tracciabilità — decisioni e misure passate restano verificabili — senza
appesantire gli alberi che si consultano di continuo (`rag/adr/`, `rag/eval/results/`).

## Contenuto

- `adr/sidecar-work/` — i checkpoint (brief/report/review) di una singola iniziativa ADR
  (scalabilità del sidecar ColBERT), spostati qui dall'ex `rag/adr/sidecar-work/`. Le
  sintesi che ne derivano restano in `rag/adr/` (es. `SCALABILITA_SIDECAR_DELTA*.md`).
- `adr/AUDIT.md`, `adr/RESIDUI.md`, `adr/EVOLUZIONE.md` — la cronaca chiusa a settembre
  2026, spostata il 25 ottobre 2026. I numeri di riga non sono cambiati: una citazione
  `rag/adr/AUDIT.md:4013` nelle evidenze si legge nello stesso punto di `adr/AUDIT.md`.
  Quelle citazioni non sono state riscritte.
- `adr/0002-prompts/` — i prompt con cui è stato eseguito l'ADR 0002. La decisione resta
  in `rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md`.
- `adr/horizontal-bench/` — le run del 28 settembre 2026. Una run nuova si scrive ancora
  sotto `rag/adr/horizontal-bench/`.
- `eval-results/<run>/` — le run di valutazione con una cartella `evidence/` (~119 MB
  totali), spostate dall'ex `rag/eval/results/<run>/`. Ogni run mantiene la propria
  struttura interna invariata. `*/evidence/** -text` in `eval-results/.gitattributes`
  preserva i byte originali e gli hash SHA-256 anche con `core.autocrlf` attivo, come
  faceva `rag/eval/results/.gitattributes` per l'albero originale.

## Cosa NON è qui

`rag/eval/results/history.jsonl` (letto da `rag/core/eval_history.py` dietro la pagina
`/eval` e `GET /api/eval-history`), `rag/eval/results/README.md`,
`rag/eval/results/FASE2_PROPOSE_20260914.md` e gli altri file sciolti (calibrazioni,
baseline, bench) restano dove sono: sono piccoli, e alcuni sono letti o scritti da
codice applicativo. In `rag/adr/` restano le decisioni ancora citate dal codice e dai
README: l'indice, `0001`, `0002`, `PIPELINE_GATE.md`, `DISTRIBUTION.md`, e le sintesi
delle iniziative già chiuse. Non ci stanno più l'audit, i residui, il piano di
evoluzione, i prompt di 0002 e le run di `horizontal-bench`.

## Link

I documenti spostati qui puntano ancora, dove possibile, ai file citati nel resto del
repository con percorsi relativi aggiornati alla nuova posizione; i riferimenti a righe
di codice o commit restano testo, non link, come nell'originale.

## Archivio congelato

Il contenuto è conservato come testimonianza, non per essere rieseguito: i file di
evidenza sono byte per byte quelli originali (anche dove un loro link relativo interno
non risolve più dalla nuova posizione) e gli script di riproduzione (`*.py`, `*.py.txt`)
presuppongono la vecchia posizione `rag/eval/results/<run>/evidence/` — per esempio
`Path(__file__).parents[4]` per arrivare a `rag/`, o run sorelle cercate accanto alla
propria cartella. Per rieseguirli vanno riportati temporaneamente in quella posizione.
Nuove run si generano in `rag/eval/results/`, non qui: per questo l'archivio non ha il
`.gitignore` con la whitelist delle evidenze che regola quell'albero.
