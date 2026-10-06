# Task 2 — Re-review circoscritta delle correzioni

**Verdetto Spec: PASS nello scope dei fix round 1 e 2. Quality: PASS.** Nessun finding P1/P2 residuo nei percorsi corretti esaminati. I tre finding della review precedente e il rischio aggiunto dal PM sui file degli artefatti sono chiusi sul codice revisionato.

Confronto: implementazione originale staged → working tree, pacchetto `task-2-fixes-review-package.md`; letti anche i due append finali di `task-2-report.md`. Review read-only di codice/Git; unico file scritto in questo round: il presente report. Nessun commit, stage, modifica codice o nuova suite.

## Esito per finding

| Finding | Esito | Evidenza nel codice e nei test |
|---|---|---|
| P1: delta altera i vettori della versione in lease | Chiuso | `immutable_index_active` rende ordinari i progetti immutable; il delta conserva il controllo no-op, poi riusa il full build prima di qualsiasi ramo di mutazione in-place. La collection candidata e il manifest appartengono alla nuova versione. Il test aggiunto interroga realmente v1, alias v2 e rollback: score +1, -1, +1; verifica inoltre B invariato, ColBERT v1, marker e manifest. |
| P1: golden attraverso junction A→B | Chiuso | `gate_promotion` controlla file golden e tutti gli antenati con is_symlink/is_junction e confinement risolto, prima del loader tollerante e fuori dal blocco fail-open. I test coprono il componente eval e il percorso golden.yaml. Golden normalmente assente conserva la policy prevista. |
| P2: CURRENT=legacy nei progetti ordinari | Chiuso | Il resolver rifiuta il sentinel per ordinary; il lettore del token valida il resolver e il caricamento esplicito passa anch'esso dalla validazione. Test per token, current, version_dir, artifact_dir e load. None e contesto legacy mantengono il sentinel storico. |
| PM: file CURRENT/manifest/sidecar collegati, retention e integrity | Chiuso nel codice | `_project_artifact_path` verifica il singolo file, tutti gli antenati e l'appartenenza al database. È usato da token, manifest, loader, hashing, marker, promote/rollback e migrazione. Il loader valida prima di `_pick` e code_json/code_npz e rilascia la lease in caso di rifiuto. List/retention validano i path prima di rmtree. Integrity valida chunks/NPZ prima delle letture dirette, anche dopo un errore di hashing. |

La scelta minima del delta è esplicita e autorizzata dal PM: per ordinary un delta effettivo ricostruisce tutti i sorgenti, inclusi quelli fuori changed_paths; changed_paths decide soltanto se avviare il rebuild. Il ramo legacy in-place e il comportamento legacy immutable restano separati. Il costo di embedding completo è documentato e marcato con commento ponytail; nessuna nuova dipendenza o implementazione di copy-on-write.

## Verifiche e limite Windows

Evidenza implementatore letta, senza riesecuzione da parte del reviewer:

- Fix round 1: **406 passed in 74.27s**, nessuno skip, incluse query Qdrant reali sul server di prova dedicato e regressioni legacy.
- Fix round 2 finale: **301 passed, 17 skipped in 80.18s**. I 17 skip sono tentativi reali di creazione di symlink FILE falliti con WinError 1314, mancanza del privilegio CreateSymbolicLink. Le corrispondenti junction ai percorsi dei file, la retention e le prove Qdrant reale passano.
- Ruff e diff-check dichiarati verdi dall'implementatore. Il reviewer ha eseguito indipendentemente `git diff --check` sui quattro file del fix: nessun errore whitespace; soltanto avvisi Git LF→CRLF.

Le junction non costituiscono una prova end-to-end equivalente a veri symlink di file: il codice controlla entrambi, ma il ramo is_symlink FILE richiede ancora l'esecuzione dei test su un host che ne consenta la creazione. Questo è un limite di verifica esplicito, non una simulazione né un finding residuo nel codice. Portare questi 17 casi al gate Linux/host abilitato di Task 8.

## Identità del codice revisionato

Git blob hash dei file working tree al termine della lettura:

- artifacts.py: `47dce07d2eb8b6619f68795263152108892db228`
- eval_gate.py: `a3443a4bd239669a075c077ef2d3cbad13be68f3`
- indexing.py: `117507053985ebba2342ca0cdf2ab434c77783cf`
- test_project_indexing.py: `a7ff0a916af9f541239d9f6c3e0eddda2bc020ca`

Approvazione limitata ai fix richiesti e alle regressioni introdotte da quel delta. Restano i carry-forward già attribuiti a Task 3 per ranking/evaluate_recall e diagnostiche Razor, la propagazione dei contesti nei task dipendenti e la review integrata finale Task 8. Nessuna estensione implicita del verdetto a quei componenti.
