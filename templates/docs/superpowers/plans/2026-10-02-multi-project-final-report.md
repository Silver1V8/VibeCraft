# VibeCraft multi-progetto — report finale del PM

Data: 5 ottobre 2026. **Stato: sviluppo degli otto task completato, review indipendente Astra PASS, nessun finding bloccante aperto.**

Branch: `codex/multi-project`. Worktree: `C:/Users/Silve/.codex/worktrees/multi-project/vibecraft`.
Baseline: `34b46dfeabcff05820240a1241baae1a215d3e1b`. Commit finale di implementazione/integrazione: **`43f31a424bd64ee87cd18ed4cc21f60e754ede16`**. Il presente report e l'annotazione del ledger sono una consegna documentale successiva, senza ulteriori modifiche prodotto.

## Risultato implementato

Una sola applicazione gestisce progetti con contesti immutabili e ID espliciti. Registry atomico, manifest validati, directory code/docs/changes/database e namespace Qdrant separano i dati. Il progetto legacy viene registrato in-place mantenendo percorsi, artefatti e collection; il bootstrap non indicizza il corpus.

API, retrieval/cache/grafo/snapshot, intake/import, pipeline/validazioni/gate, storico valutazioni e job catturano il progetto originario. Snapshot residenti limitati a due, risorse pesanti condivise e inizializzate a richiesta, writer serializzati; le query di B restano disponibili durante una build di A. Rollback, retention, lease e GC usano il namespace del singolo progetto.

La console crea/apre/seleziona progetti, conserva selezione per scheda e identità degli iframe, mantiene il target durante stream/job/retry e riusa lo stile esistente. CLI `--project` e MCP `VIBECRAFT_PROJECT_ID` hanno selezione esplicita; senza selettore conservano il solo legacy. SDK/local applicano guard di lettura/scrittura per code, segreti, `.git`, link e progetti esterni.

Docker usa un volume progetti persistente e scrivibile da UID10001; i mount legacy restano. Liveness autenticata `/api/health/live` funziona anche senza indice e Qdrant. Con bind remoto la registrazione accetta soltanto root canoniche senza link strettamente sotto `VIBECRAFT_PROJECTS_DIR`; percorsi host arbitrari e browse nativo richiedono bind locale. Questa decisione rende utilizzabile l'apertura in Docker mantenendo il confine dei percorsi.

Non sono state aggiunte dipendenze product, framework UI, scheduler o ricerca fra progetti. Non sono stati eseguiti push, merge o pubblicazione.

## Accettazione e prove

| Criterio | Evidenza pertinente | Stato finale |
|---|---|---|
| AC1 creazione/apertura e quattro directory distinte | API registry; browser reale Nuovo/Apri, fixture temporanee A/B/C/D | PASS |
| AC2 query/file omonimi, cache/grafo/reload isolati | Suite runtime/retrieval; integrazione HTTP/Qdrant ALPHA/BETA stessa query/path/versione | PASS |
| AC3 build/delta/rollback/GC A preservano B | Suite storage/lease/versioni; integrazione confronta CURRENT, hash, alias, vettori e integrità B | PASS |
| AC4 feature, gate, import, storico e job separati | Suite workflow; import plan A sotto B404; gate A non ammette B; job A trattenuto e query B attiva | PASS |
| AC5 schede, stream, retry e target originario | Node projects_workspace/navigation; browser reale A→B→A, identità catturata e limite frame attivi | PASS |
| AC6 agenti, CLI e MCP stesso progetto | Suite tools/CLI/MCP; scrittura local reale A-only; guard Linux con link effettivi | PASS con ruling native-launch |
| AC7 console senza indice e guasti espliciti | Suite API/runtime/health; Docker vuoto, Qdrant down, liveness200 | PASS |
| AC8 legacy in-place | Registry/artifact checksum e compatibilità legacy; nessun corpus utente usato | PASS su fixture |
| AC9 persistenza Docker e security/reader | Smoke Docker UID10001, restart byte-identico registry, autenticazione/reader e managed-root boundary | PASS con limiti build |
| AC10 lint/suite/Qdrant/browser/review | Gate finali sotto; review indipendente Astra PASS | PASS con limiti ambientali |

## Verifiche

Gate finale Python: **2348 passed, 20 skipped, 15 warning di deprecazione Docling in359.39s, exit0**. Ruff: **all checks passed**. Esecuzione da `rag/` con `uv run --frozen --no-sync --active`, interpreter/venv esistente riusato senza sync o modifiche al lockfile. Entrambi `QDRANT_URL` e `VIBECRAFT_TEST_QDRANT_URL` puntano al container dedicato su loopback58123; i flag REQUIRE_QDRANT/DOCLING/LIBREOFFICE sono1. Docling opera offline con asset locali e hash verificati; le conversioni Docling/LibreOffice e Qdrant non sono saltate.

Skip esatti: uno `test_project_api.py:299`, diciassette `test_project_indexing.py:193`, uno `test_project_lock_confinement.py:81`, uno `test_project_tools.py:378`; tutti dovuti ai privilegi file-symlink Windows. Le prove Linux complementari eseguono link effettivi senza skip.

Comandi finali, da worktree/rag con l'ambiente sopra e `VIBECRAFT_INTEGRATION_BROWSER=1`:

```powershell
uv run --frozen --no-sync --active ruff check .
uv run --frozen --no-sync --active pytest -rs
```

PM e reviewer hanno letto il riepilogo grezzo del gate completo; worker ha verificato session53857 terminata exit0. Il log `multi-project-tasks/task8-full-pytest-candidate.log` è conservato nella directory ignorata dei task. Il reviewer ha eseguito autonomamente integrazione HTTP/Qdrant/browser: uno pass in19.02s.

Le prove precedenti includono:

- Task4: 824 pass, zero skip; conversioni Docling reali, review e regressioni corrette.
- Task5: review 65 pass/1 skip Windows filelink; prova PM Linux 20 pass/zero skip con link di file, directory e ancestor effettivi. Un fixture Git reale verifica Read e scansioni sicure disponibili.
- Storage/runtime: prova Linux complementare 35 casi pass/zero skip con link effettivi.
- Task7: API/distribuzione 49 pass/1 skip Windows, sei casi indipendenti pass/zero skip; tre profili Compose validati e smoke Docker effettivo. Container candidato, volume e immagine overlay del Task7 rimossi dopo le prove.
- Task8: sette check Node pass (intake_excel_preview, pipeline_dryrun_escape, dashboard_graph_escape, workflow_errors, pipeline_runner_capability, pipeline_agent, projects_workspace); navigation_workspace su uvicorn reale pass; integrazione HTTP/Qdrant/browser inclusa nel gate finale; gate ordinato mirato272 pass/1 skip61.85s.

Il primo full gate Task8 ha riportato 2339 pass, cinque failure e19 skip filelink Windows. Le failure erano adattatori storici del contesto/reload/stream e classificazione local-bind della registrazione, aggiornati preservando le assertions di sicurezza. Una fixture HTTP installava un override durante il primo import dell'app: il nuovo test d'integrazione ha rilevato l'interferenza, corretta nella fixture senza bypass dell'admission reale; il test verifica ora gli override vuoti. Due test logging ripristinano handler/livello evitando stderr catturato già chiuso. Un gate intermedio avviato troppo presto è stato interrotto al57% senza risultato completo. Solo il gate finale sopra costituisce la verifica completa accettata.

La review finale ha riprodotto un P1 reale nel writer lock: una junction sostituita dopo la cattura del contesto poteva aprire/lockare un file di B e poi troncargli i byte diagnostici. Il PM ha aggiunto guard di file/ogni antenato prima di mkdir/open, controllo dopo mkdir e `O_NOFOLLOW` su POSIX; reader lease e diagnostica usano lo stesso guard. Prove TDD reali e compatibilità lock: PM Windows13 pass/1 skip7.17s, PM Linux14 pass/zero skip11.24s; reviewer Windows13 pass/1 skip7.44s. Il reviewer ha segnalato uno skip troppo ampio, ristretto dal PM al solo WinError1314. Il reviewer non ha scritto prodotto o test. Nessuna immunità generale alle sostituzioni filesystem concorrenti avversarie è dichiarata.

## Limiti verificabili

- Codex/Cursor integrati restano disabilitati prima di Popen finché l'isolamento delle letture non è verificato. Prompt export e MCP esterno con ID fisso restano disponibili; SDK/local sono utilizzabili. Scansioni SDK di un subtree che contiene `.git`, segreti o link sono negate; Read e scansioni di directory sicure restano disponibili.
- Windows non dispone del privilegio file-symlink: gli skip sono espliciti e coperti da prove Linux complementari. Queste prove montano il sorgente corrente in un runtime CPU già disponibile, non rappresentano un'immagine nuova costruita interamente dal lock.
- Docker è stato provato con overlay del runtime CPU esistente: UID, directory, auth, health, persistenza e sorgente corrente effettivi. Un build Dockerfile completo con installazione frozen da zero e l'esecuzione remota GitHub Actions non sono stati effettuati.
- Sono state confrontate163 versioni base installate con uv.lock; identità degli artefatti/wheel e installazione pulita da zero non sono stabilite. Il lock product non è stato cambiato.
- I provider del gate finale sono simulati ai confini. Una prova RED precedente del Task5 applicava una patch Popen inefficace e ha causato startup nativo/prewarm HTTP400 e rifiuto autenticazione Cursor; non è stata osservata esecuzione modello o fatturazione, ma non si afferma assenza di rete o effetti host. La patch efficace e i guard failclosed sono poi stati verificati. Un precedente test ometteva QDRANT_URL e poteva tentare lettura di compatibilità6333 prima di essere interrotto; non vi è evidenza di mutation del corpus. Tutti i gate successivi hanno entrambi gli URL dedicati.
- La verifica read-only del checkout originale conferma HEAD, elenco modifiche preesistenti e hash del piano iniziale invariati; non è un confronto byte-per-byte di tutti i dati privati. I test usano solo fixture del worktree/temp e collection dedicate, senza reindex/cancellazione del corpus utente.
- La prima versione non include eliminazione, spostamento o rinomina progetti, ACL per progetto o embedding differenti. Le build ordinary delta non vuote ricostruiscono il candidato completo; le operazioni legacy supportano la policy esistente. Startup lazy non effettua repair/GC automatici: maintenance esplicita.

## Tracciabilità

Piano: `2026-10-02-multi-project.md`. Ledger persistente: `2026-10-02-multi-project-progress.md`. Report e review: `multi-project-tasks/task-*-report.md` e report review selezionati. Log grezzi, fixture di quarantena e pacchetti di dispatch sono conservati nella directory ignorata dei task; non contengono corpus reale e non vengono forzati nello stage.

Commit Task1 `9e48d987c00b3925be4b6d16869fb4d939786efc`; Task2 `436b90872500244a9279ff278badcc1b139fbfc2`; Task3 `edfbbe4`; Task6 `9fac4180e74166bd183341515c618622c8339d0a`; adapter5 `4223b84d066af61aa4dd9c11150f2b7c0a0b5cca`; Task4 `dde1ef92be99c5c5d15926634bfed9c1288b91fe`; Task5 `24c7eb078080d69f6256c7a195c6895dc5600d2a`; Task7 `06c7626d8183834b30476d3fe92a4fe3945c2f03`; Task8 `43f31a424bd64ee87cd18ed4cc21f60e754ede16` (14 file esatti, incluse review e accettazione).

Il PM ha verificato worktree pulito dopo il commit di implementazione. Il container Qdrant dedicato `vibecraft-multi-project-test-20261002`, ID `7645a0589b279047d90127e171a211d9af4aedfbf71aab1716eb66cc73a2b45d`, era privo di mount: verificato ID/nome, fermato e rimosso per ID esatto, assenza confermata. Solo servizi/dati di prova propri sono stati puliti. Il runtime CPU esistente, log/report ignorati e asset di modello nel worktree sono conservati; nessun server del worker rimane attivo.

Branch e worktree restano disponibili per l'utente. Nessun push, merge, PR o publish è stato effettuato.
