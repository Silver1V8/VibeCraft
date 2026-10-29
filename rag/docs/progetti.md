Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Progetti separati

## Progetti separati

Una sola installazione gestisce progetti con contesti e snapshot separati.
La console crea/apre/seleziona il progetto per scheda; modelli e client Qdrant
restano condivisi, mentre root, codice, documenti, pipeline e indice sono distinti.
La shell e il registry sono disponibili senza indice. Risorse pesanti e snapshot
si caricano a richiesta; la cache conserva al massimo due snapshot residenti,
mantenendo le lease delle richieste già in corso. Avvio e lettura non riparano
alias né eseguono GC: le operazioni writer fanno la manutenzione.

```text
<VIBECRAFT_PROJECTS_DIR>/        # default <installazione>/projects
  projects.json                # registry atomico e protetto da lock
  <id>/
    project.yaml               # schema_version, id, name, settings opzionali
    code/
    docs/
    changes/
    database/
      CURRENT
      versions/
      staging/
      pipeline/
      eval/
      reindex_jobs.jsonl
```

Il nome visualizzato non costruisce percorsi; l'ID è stabile. `project.yaml`
consente override validati di authority, retrieval, eval e verification. Root,
collection, segreti, endpoint e modello embedding rimangono sotto il controllo
dell'installazione. Tutti i progetti usano lo stesso modello embedding.

### Identità nelle API, CLI e MCP

| Operazione | Contratto |
|---|---|
| Elenco e stato | `GET /api/projects`, `GET /api/projects/<id>` |
| Creazione | `POST /api/projects`, JSON `{"name":"Nome progetto"}` |
| Apertura | `POST /api/projects/register`, JSON `{"root":"percorso-assoluto"}` |
| API del progetto | Header `X-VibeCraft-Project: <id>` su `/ask` e sulle API dati |
| Navigazione | `?project=<id>`, selezione in sessionStorage per scheda |
| CLI indice | `index.py --project <id>` |
| MCP esterno | `VIBECRAFT_PROJECT_ID=<id>`, catturato all'avvio della sessione |

Le richieste senza header usano **soltanto** il progetto registrato `legacy`;
mai il primo disponibile o l'ultimo scelto nel browser. Header malformato: 422;
ID sconosciuto: 404; selezione assente senza legacy: 409 `project_required`;
indice assente: 409 `project_not_indexed`; storage o risorse guasti: 503.
Restano validi auth, Host guard, CSP e controlli cross-site.

Metadati indice: `not_indexed`, `ready`, `indexing`, `error`, più `stale`
quando calcolabile. `/api/health/live` misura il processo, `/api/health` il
progetto selezionato e le dipendenze, `/api/health/deps` solo Qdrant/Ollama
(l'indicatore nella barra della shell, ogni 30 s). Creare un progetto non lo indicizza.

La pipeline conserva nel browser una bozza per progetto e feature: intervista,
input non inviato, editor, ambito e passo corrente. Dopo refresh o riapertura
carica prima i file server e propone «Ripristina bozza locale» oppure
«Scarta bozza e usa file server». Il ripristino è esplicito, non scrive sul server e non recupera
autorizzazioni, validazioni o esecuzioni dell'agente. L'interfaccia mostra
l'ultimo salvataggio locale e segnala storage browser indisponibile o corrotto.
Le bozze non sono sincronizzate fra dispositivi e vengono perse cancellando i dati del sito.
Finché una bozza attende la scelta, chat ed editor sono in sola lettura e il campo
dell'intervista lo dice; il tipo di sviluppo resta selezionabile e il ripristino lo
sostituisce solo se la bozza ne aveva uno.

Il tipo di sviluppo è una sottocartella reale di `code/` del progetto
(`GET /api/pipeline/dev-types`). **Aggiungi** la crea con `POST /api/pipeline/dev-types`,
JSON `{"name":"..."}`: un solo componente `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, nomi
riservati Windows rifiutati, idempotente senza distinzione di maiuscole. Pipeline e
import di Intake usano la stessa regola (`core/projects.py`).

Da `rag/`, con l'ID ricavato dalla console o da `GET /api/projects`:

```bash
uv run python index.py --project <id>
uv run python index.py --project <id> --index-status
uv run python index.py --project <id> --check-integrity
uv run python index.py --project <id> --incremental
uv run python index.py --project <id> --rollback [VERSIONE]
```

`[VERSIONE]` indica un argomento opzionale, non va digitato letteralmente.
Le nuove collection usano alias `vibecraft_<id>` e nomi fisici
`vibecraft_<id>__<version>`. Il delta **non vuoto di un nuovo progetto è
copy-on-write**: una nuova collection dedicata riceve i punti invariati del padre e
si ri-embeddano solo i sorgenti cambiati; se il padre non è riusabile si ripiega sul
full rebuild (`fallback_reason`). Un no-op non carica embedding né riscrive l'indice.
Ogni candidata conserva la propria collection e il rollback riattiva quella
versione. Il golden set è `<root>/eval/golden.yaml`, lo storico vive in
`database/eval/`; un golden mancante può lasciare passare il gate come non valutato.
Le CLI `eval.run` e `eval.run_multihop` restituiscono exit 3 per una suite assente o vuota;
il controllo notturno la segnala come non valutata.
I job HTTP sono serializzati nel processo per contenere RAM/VRAM, con writer lock
per progetto anche fra processi. Richieste, callback e stream conservano il target
originario: selezionare B non sposta un job di A.

### Legacy, Docker e limiti

Il progetto iniziale usa `<VIBECRAFT_PROJECTS_DIR>/legacy/`, con manifest e layout
ordinari. Il primo avvio writer copia e verifica in quella root `docs/` e `code/` alla
radice dell'installazione se contengono file, altrimenti `templates/docs/` e
`templates/code/` (clone locale pulito; l'immagine Docker le porta in `/app/docs` e
`/app/code`), senza modelli, Qdrant o build. Gli altri progetti nuovi restano vuoti. Il reader non
inizializza il registro. Un registro già vuoto resta vuoto.
L'indice scansiona soltanto docs/code del progetto selezionato, anche per ID `legacy`.

Con dati storici compare `project_migration_required`: ferma server e altri writer,
poi da `rag/` esegui `uv run --frozen python -m scripts.migrate_project_layout`.
La copia conserva gli originali; un indice esistente richiede Qdrant ed embedding,
e un full rebuild verificato prima della pubblicazione. Pipeline e staging vengono
copiati; le validazioni storiche richiedono nuova validazione. Registro originale:
`projects/projects.v1.backup.json` quando presente; checkpoint:
`projects/.legacy-migration.json`. Ripeti lo stesso comando per riprendere;
`--repair` ripara soltanto il candidato proprio dopo interruzione CURRENT/alias.
Costi e ripristino: [migrazione](../../INSTALL.md#migrare-uninstallazione-esistente).

Gli esempi senza `--project` selezionano soltanto il `legacy` registrato.
Il suo indice è immutabile come gli altri: delta non vuoto con candidata completa,
gate, alias e rollback separati. I paragrafi sui formati piatti e delta mutabili
descrivono gli indici storici conservati per diagnostica.

Con bind locale, Apri può registrare una root VibeCraft esterna; con bind remoto
accetta solo root senza link strettamente sotto `VIBECRAFT_PROJECTS_DIR`, prima di
leggere il manifest. Docker monta `vibecraft_projects:/app/projects`: per aprire
un progetto host monta la root sotto `/app/projects/<cartella>`. Il dialogo nativo
è disponibile solo con bind locale. Backup: registry, root registrate e relative
collection Qdrant, con scritture ferme. Pesi dei modelli condivisi nell'installazione.

Il reader richiede `VIBECRAFT_ROLE=reader`, `VIBECRAFT_INDEX_MODE=immutable` e chiave
API anche su loopback; registry preparato dal writer e API mutanti disabilitate.
Per creare/importare e per i dettagli Docker: [istruzioni principali](../../INSTALL.md#progetti-separati).

Avvio in-app disponibile per Claude SDK, Ollama locale e Codex **agentic** solo
dopo prova di isolamento scrittura (`native_sandbox`). Suggest/oneshot Codex e
Cursor restano `native_read_isolation_unverified`; prompt export e MCP esterno
rimangono disponibili. Sono supportati eliminazione (destroy sulle root gestite;
unregister sulle root esterne), rinomina del solo nome visualizzato (id e percorso fissi) e
filtro dell'elenco progetti per nome o id (`?q=`). Restano fuori: spostamento/migrazione
dell'id, ricerca cross-project sul corpus, ACL per progetto o embedding differenti.

Indicizzazione, retrieval, pipeline e importazione sono esposti da FastAPI.
Entrypoint: `server.py`, `index.py`, `mcp_server.py`; decisioni architetturali in
[adr/](../adr/README.md). I benchmark datati sotto restano misure del percorso legacy.

