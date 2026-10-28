Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Reindex automatico

## Reindex automatico: l'indice non invecchia mai

Due meccanismi tengono l'indice allineato al codebase senza intervento manuale:

**1. Reindex incrementale su webhook (durante il giorno).**
`POST /api/reindex` lancia un reindex incrementale in background e risponde
subito `202` con un `job_id`; `GET /api/reindex/{job_id}` ne riporta lo stato
(`queued`/`running`/`completed`/`failed`) col risultato o l'errore. A fine job
riuscito il server aggiorna grafo e chunk in memoria e apre il reader ColBERT
a richiesta tramite `reload_index_state` (api/deps.py). `GET /api/reindex` (senza id) elenca gli
ultimi `N` job (`?limit=`, default 20, più recente prima), utile per debug e UI.
Auth: `X-API-Key` come tutti i `/api/*`.

Lo storico dei job è **persistente ai riavvii**: ogni transizione di stato
(`created`/`completed`/`failed`) appende una riga JSON al journal append-only
`database/reindex_jobs.jsonl`. Al boot il `ReindexManager` ricostruisce lo storico
dal journal (l'ultima riga per `job_id` vince); i job rimasti `running` (crash a
metà) vengono marcati `interrupted`. Anche un `reload_status: pending` diventa
`interrupted` al riavvio: il processo di reload non sopravvive al crash, mentre
l'esito di una build già completata resta conservato. Il journal distingue durata
della build, durata del reload e tempo fino allo snapshot pronto; `completed` da
solo non certifica che il server stia già servendo la nuova versione.
Il file si auto-compatta quando supera ~1MB
(riscritto tenendo solo l'ultimo stato di ogni job) e **non va committato** (è in
`.gitignore`).

Il manager usa una **coda con coalescing** (`ReindexManager`, api/reindex.py):
al massimo un job in esecuzione + al massimo **un pending**. Se arriva una
richiesta mentre un reindex è in corso **non viene più rifiutata con `409`**: è
accodata in un unico slot pending e la risposta è `202` con
`{"job_id": <id del pending>, "queued": true}`. I `changed_paths` delle richieste
accodate vengono **fusi** (unione degli insiemi; una richiesta "completa" con
`changed_paths=None` assorbe tutto → incrementale su tutto). A fine job (successo
o fallimento) il pending parte automaticamente. Così due push GitLab ravvicinati
non si perdono più — il secondo evento si fonde nel pending invece di sparire.

**Un solo scrittore per costruzione.** Ogni scrittura degli artefatti dell'indice
dal server passa dalla coda del manager, che distingue due tipi di job (`kind` nel
`to_dict`/journal): `incremental` (delta) e `full` (`build_graph_and_index`,
ricostruzione completa, senza `changed_paths`). Un corpo `{"full": true}` su
`POST /api/reindex` accoda un full rebuild; anche l'archive (Step 5,
`/api/pipeline/archive[/stream]`) non ricostruisce più inline ma accoda un job
full e riporta il `job_id` al client (nello stream l'evento finale è
`{"type": "reindex_queued", "job_id": ...}`). Coalescing tra tipi: un full
**sussume** qualunque incrementale — se il pending è incremental e arriva un full,
il pending diventa full; se il pending è già full, ogni richiesta successiva vi si
fonde senza cambiarlo. La CLI (`python index.py`) invece scrive gli artefatti
direttamente, fuori dalla coda: con il server acceso preferisci `POST /api/reindex`
(eventualmente `{"full": true}`), che accoda invece di scrivere in place.

**Un solo scrittore anche cross-processo (writer lock).** CLI e server non si
corrompono più a vicenda: ogni ramo che SCRIVE gli artefatti — i comandi CLI di
scrittura (`index.py`: build, `--incremental`, `--archive`, `--rollback`,
`--migrate-colbert-npy`) e i job
del ReindexManager — gira per l'intera durata sotto un lock advisory a livello di
sistema operativo su `database/.writer.lock` ([core/writer_lock.py](../core/writer_lock.py):
`msvcrt.locking` su Windows, `fcntl.flock` su POSIX). Il mutex è il lock OS
sull'handle, che il kernel rilascia automaticamente alla morte del processo (crash
inclusi): nessun lock stale da ripulire, il file non viene mai cancellato. Se un
altro writer è attivo la CLI **fallisce subito** con un exit code dedicato
(`WriterLockBusyError`, messaggio con pid/timestamp del detentore) invece di
scrivere a metà — così un `python index.py` lanciato mentre il server reindicizza
non produce artefatti misti.

Configura il webhook GitLab (Settings → Webhooks) su **Push events** e/o
**Merge request events** puntando a `https://<host>/api/reindex`. Per esporre il
webhook in sicurezza imposta **entrambe** le variabili d'ambiente: `VIBECRAFT_API_KEY`
(header `X-API-Key`, richiesta per ogni accesso non locale) e `VIBECRAFT_GITLAB_TOKEN`
(header `X-Gitlab-Token`, il *Secret token* del webhook GitLab). Quando
`VIBECRAFT_GITLAB_TOKEN` è impostata, `POST /api/reindex` esige il token corretto
(confronto a tempo costante con `hmac.compare_digest`) **in aggiunta** a `X-API-Key`;
se non è impostata il comportamento resta invariato (solo `X-API-Key`). Il `<host>` del
webhook va anche ammesso nell'header `Host` (`VIBECRAFT_ALLOWED_HOSTS` o
`VIBECRAFT_BASE_URL`), altrimenti la richiesta riceve 400. Dal payload
push vengono estratti i path modificati
(`commits[].added/modified/removed`) e passati al plan del delta indexing per
limitare il lavoro ai soli file cambiati; un payload merge request (senza elenco
file) fa un incrementale completo su `docs/` + `code/`. È accettato anche un
override esplicito `{"paths": ["docs/x.md", ...]}` per trigger manuali. La
logica di estrazione è in [api/reindex.py](../api/reindex.py) (`extract_gitlab_paths`).

**2. Batch notturno ECONOMICO (check di integrità, zero embedding).**
Lo script notturno [scripts/nightly_consistency.ps1](../scripts/nightly_consistency.ps1)
(variante POSIX `.sh`) esegue `index.py --check-integrity`
(`check_index_integrity`, core/indexing.py): **niente modello di embedding,
niente costruzione, secondi di esecuzione**. Verifica che il manifest esista e
sia leggibile, confronta `doc_hashes`/`code_hashes` con gli hash correnti su
disco (differenze ⇒ indice **stale**), valida gli `artifact_hashes` contro i
file in `database/` (mancanti o hash diverso ⇒ artefatti **corrotti**/misti),
confronta le chiavi del sidecar ColBERT con i `chunk_id` di `chunks.json` (un chunk
senza multivettore rende `colbert_maxsim` non giudicabile e degrada il ranking in
silenzio — vedi `AUDIT.md`, A7) e confronta il conteggio dei punti Qdrant col numero
di chunk nel sidecar, verificando anche che la collection dichiarata dalla versione
attiva esista ancora. Lo stesso check è esposto come `GET /api/index/integrity`
(auth `X-API-Key`).

**Divergenza `docs/` ↔ git (campo `docs_git`).** I file di `docs/` sono marcati
`skip-worktree`, quindi le differenze fra la copia di lavoro e il committato sono
**invisibili a `git status` e `git diff`** — voluto, per non vedere il materiale di
dominio come "modifiche", ma significa che il corpus indicizzato può discostarsi dal
repository senza che nessuno se ne accorga. `observe_docs_git_divergence` confronta
l'hash del blob di `ls-tree HEAD` con `hash-object` sul file di lavoro (bypassa
l'indice git, che per gli skip-worktree è fermo al committato; `hash-object` applica
gli stessi filtri eol, quindi niente falsi positivi su checkout CRLF). È
**osservazione pura**, come `qdrant_alias`: non contribuisce mai a `ok`/`problems`,
perché una divergenza git **non si ripara re-indicizzando** — il reindex rileggerebbe
gli stessi file — e trattarla come problema farebbe scattare un full rebuild inutile a
ogni esecuzione. Quale corpus sia autoritativo è una decisione umana; il check la rende
solo visibile. Gli script notturni la stampano **sempre**, anche a integrità OK (è il
caso in cui resterebbe nascosta) e scrivono un alert.

**Istanziazione dichiarata ≠ difetto.** La baseline è fatta per essere istanziata sul
posto — `docs/README.md` prescrive di compilare la Sezione 0 e risolvere i
`<<PARAMETRO>>`, e `skip-worktree` esiste proprio perché quell'istanza non risulti come
"modifica". Un check che segnalasse anche quella non verrebbe più letto: il rumore
atteso seppellisce il segnale raro. Un documento che dichiara `instantiated_from:` nel
frontmatter è quindi classificato a parte — resta elencato e contato, ma non è un
problema, e non fa scattare l'alert notturno. Il marcatore è una dichiarazione umana con
lo stesso modello di fiducia di `authority:`: chi lo scrive per mascherare una divergenza
accidentale sta mentendo al proprio strumento, non aggirando un controllo. Un file
**sparito** dal disco non può dichiarare nulla e resta sempre una divergenza; un
frontmatter malformato non vale come dichiarazione (il caso ambiguo si risolve verso
`diverging`, che è il più prudente).

Stati: `aligned`, `instantiated` (solo differenze dichiarate), `diverging` (almeno una
non dichiarata — e ne basta una perché lo stato torni tale), `unavailable` (git assente,
non un repository, HEAD assente — mai un'eccezione).
In base al report lo script:
- **ok** → esce senza fare nulla;
- **stale** (solo sorgenti cambiate) → `POST /api/reindex` al server locale
  (`VIBECRAFT_SERVER_URL`, default `http://127.0.0.1:8000`, con `X-API-Key` da
  `VIBECRAFT_API_KEY`) così il delta passa dalla coda del ReindexManager; se il
  server è spento, fallback a `index.py --incremental`;
- **artefatti corrotti o Qdrant disallineato** → full rebuild (`index.py`).

**3. Batch settimanale profondo (guardrail anti-deriva).**
Il confronto esaustivo grafo incrementale vs full rebuild (`index.py
--check-graph`, che ri-embedda tutto in memoria) è declassato a settimanale:
[scripts/weekly_consistency.ps1](../scripts/weekly_consistency.ps1) (variante
POSIX `.sh`) lo esegue e, **solo se trova drift**, lancia un full rebuild che
riallinea tutto. Dopo il rebuild il server rileva il puntatore `database/CURRENT`
spostato (la promozione della nuova versione blue/green; per i layout legacy senza
CURRENT, l'mtime di `graph.json`) e ricarica gli artefatti alla prima richiesta
(`maybe_reload_graph`). Il caricamento gira in un thread del threadpool (l'event loop
continua a servire le altre richieste) ed è serializzato da un lock con doppio controllo
della versione: più richieste concorrenti, o una richiesta e il reload di fine job,
producono un solo caricamento.

Scheduling — Windows Task Scheduler:

```powershell
# nightly alle 03:00, weekly la domenica alle 04:00
schtasks /Create /TN "vibecraft-nightly" /SC DAILY  /ST 03:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\nightly_consistency.ps1"
schtasks /Create /TN "vibecraft-weekly"  /SC WEEKLY /D SUN /ST 04:00 `
  /TR "pwsh -File C:\path\to\rag\scripts\weekly_consistency.ps1"
```

cron:

```cron
0 3 * * *  /path/to/rag/scripts/nightly_consistency.sh >> /var/log/vibecraft-nightly.log 2>&1
0 4 * * 0  /path/to/rag/scripts/weekly_consistency.sh  >> /var/log/vibecraft-weekly.log  2>&1
```

