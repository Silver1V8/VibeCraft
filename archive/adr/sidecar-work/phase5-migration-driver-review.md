# Review pre-run indipendente — migrazione storica F5-06

**Verdetto dopo fix: APPROVATO per la run PM nel sandbox preparato.** Review statica del driver `migration_experiment.py`, del report e del contratto di `artifacts.migrate_colbert_npy()`; nessuna migrazione, modello o connessione Qdrant eseguita.

## Chiusura dei finding

1. `source_files()` usa la guardia di percorso condivisa, richiede esattamente i sette nomi previsti e rifiuta file non regolari/link. Il driver copia i sette singolarmente nel target nuovo sotto il database dedicato, confrontando SHA-256 e byte della sorgente prima/dopo e della copia. La prova non percorre più discendenti inattesi.
2. Prima del rollback, il driver richiede CURRENT sulla candidata, layout NPY esclusivo, digest profondi uguali al manifest, replay di 32 candidati più `missing=None`, e parità esatta degli array per tutti i **257** chunk e **112.429** token del corpus storico fisso. Registra conteggi, hash e token; dopo rollback richiede CURRENT NPZ e replay identico. La sorgente storica è ricontrollata alla fine.
3. Il selfcheck esercita ora le stesse funzioni `valid_collection()` e `validate_names()` usate dal run, con rifiuto di file extra; è sufficiente come guardia pura pre-run. La validazione degli artefatti reali spetta alla run PM.

## Contratti presenti

`delta.validate_paths()` vincola checkout/output a run dedicata, database vuoto e config locale; il driver richiede un prefisso collection di migrazione. Importa `core.artifacts` dal checkout dedicato e controlla `__file__`. La migrazione core è sotto writer lock, usa soltanto artefatti locali, confronta array fp16, verifica digest profondi e promuove una candidata separata; non istanzia il modello né il client Qdrant. Il manifest storico conserva un nome di collection operativo come metadato, ma questo percorso non lo interroga. Il ranking usa la query cached F4 e include `missing`; il rollback è sotto writer lock. Limite: il replay di 32 candidati non è retrieval completo né una misura di qualità universale.
