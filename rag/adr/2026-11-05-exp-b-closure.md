# Chiusura EXP-B (passaggio correttivo) — 2026-11-05

Non sostituisce `eval/failures/README.md` né ADR 0001. Collegato da
`docs/eval-e-ci.md`. Istruzione: chiudere formalmente gli opzionali del piano eval.

## Decisione

**NON ABILITARE** `retrieval.corrective_pass.enabled` in produzione.

Resta `false` in `rag_config.yaml`. Il prototipo `follow_ref` in
`core/corrective.py` resta disponibile solo per esperimento appaiato futuro.

## Perché non è un GO

1. Il registro `eval/failures/retrieval_misses_register.json` deriva dalla run
   storica `p0_20260908-152239`, non da una verifica corrente post-calibrazione.
2. Nessun esperimento appaiato (flag on vs off) su fallimenti **attuali** con
   criterio di successo fissato prima della misura.
3. EXP-C conferma il router deterministico; EXP-D/E restano NO-GO — non c’è
   pressione a «compensare» con un passaggio correttivo acceso.

## Riaprire solo se

- Esiste un registro di miss **corrente** (stessa config frozen del transfer /
  golden), e
- Un confronto appaiato pre-registrato mostra guadagno netto senza regressioni
  su recall@1 / astensione, e
- Il GO è esplicito in un ADR o in `eval-e-ci.md`.

Fino ad allora: **flag-off**.
