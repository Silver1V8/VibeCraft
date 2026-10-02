# Task 1 — fix round 1, review mirata

## Verdict

**Spec: PASS. Quality: PASS.** P1 precedente risolto; nessuna nuova regressione individuata nel delta esaminato.

## Finding precedente: addressed

`rag/core/projects.py:295`: `existing.staging_dir` ora appartiene ai percorsi legacy protetti. Il controllo già esistente confronta entrambe le direzioni con `is_relative_to`, quindi rifiuta root uguali allo staging, sue discendenti e sue antenate, anche quando il database legacy è altrove. Il rifiuto precede `_write` e conserva il 409 `project_conflict`.

La regressione parametrizzata `test_registered_roots_cannot_overlap_external_legacy_staging` copre antenato e discendente dello staging esterno e verifica i byte del registry invariati. Il caso di uguaglianza segue direttamente lo stesso controllo inclusivo di `Path.is_relative_to`.

## Guardia directory database: addressed

`rag/core/projects.py:143`: la validazione include ora `database/versions`, `database/pipeline` e `database/eval`, riusando `_unlinked` e il controllo del tipo directory. La lista `paths` passata al constructor del contesto resta invariata: nessuna modifica all'ordine o al contratto di `ProjectContext`.

Poiché la guardia è in `_manifest`, vale sia per la registrazione sia per get/list successivi. La regressione parametrizzata sostituisce ogni directory con una junction/symlink esterna dopo la creazione e verifica il 503 in riapertura. Le directory assenti restano ammesse, come nel comportamento precedente.

## Evidenza e limiti

Letti soltanto `task-1-fix-1-package.md` e il report implementatore aggiornato; nessuna estensione della review generale. Il report documenta i cinque red precedenti alla correzione e 33 test verdi dopo il delta. Il PM ha inoltre comunicato una verifica indipendente: **33 passed in 6.54s**, **Ruff All checks passed**. Non ho rilanciato la suite né eseguito altre riproduzioni: le modifiche risolvono direttamente le condizioni già riprodotte e hanno regressioni mirate.

Nessuna nuova finding nel perimetro del fix. Rimangono i limiti della review originaria e la verifica d'integrazione completa affidata al PM. Nessuna modifica al codice/Git, nessun subagente o commit.
