# Task 1 — review indipendente

Base: `720f776`; implementazione staged del pacchetto `task-1-review-package.md`. Codice stabile confermato dal PM. Review del 2 ottobre 2026.

## Verdict

- **Spec: CHANGES REQUIRED** — un caso di isolamento legacy non coperto.
- **Quality: CHANGES REQUIRED** — correggere il controllo condiviso di overlap e aggiungere una regressione mirata; nessun'altra finding bloccante nel perimetro letto.

## Finding

### [P1] Proteggere anche lo staging legacy quando è esterno al database

**File:** `rag/core/projects.py:295` (insieme `protected` usato da `_append`).

Il controllo protegge `code_dir`, `docs_dir`, `changes_dir` e `database_dir` del legacy, ma omette `staging_dir`. La configurazione esistente permette esattamente questa separazione: `VIBECRAFT_DATABASE_DIR` sposta il database, mentre `INTAKE_STAGING_DIR` mantiene il percorso storico sotto `rag/` (`rag/core/config.py:496`). Un manifest valido nella directory di staging, o in una sua sottodirectory, può quindi essere registrato come progetto ordinario. La sua root e i suoi dati ricadono nello storage operativo di legacy, violando il requisito di staging separato e la conservazione dei percorsi custom legacy.

**Riproduzione eseguita:** con `TemporaryDirectory`, legacy con database `custom-database/` e staging `legacy/rag/database/staging/`, bootstrap attivato da un `graph.json` temporaneo; scritto un manifest con ID `a` × 32 nello staging e chiamato `store.register(stage)`. La registrazione riesce e restituisce:

```text
registered_root_equals_legacy_staging: True
registered_ids: ['legacy', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']
```

**Correzione minima:** includere `existing.staging_dir` nei percorsi legacy protetti dallo stesso controllo bidirezionale. Testare almeno staging esterno al database, sua sottodirectory e registry invariato al rifiuto (409).

## Verifiche e copertura

- Letti brief, diff fornito e report implementatore; approfondimenti limitati a configurazione/verification e primitive atomic/lock per i rischi nominati.
- ID/root canonici, duplicate ID/root, JSON corrotto/versioni sconosciute e chiavi duplicate: fallimento esplicito senza sostituire il registry. Mutazioni protette dal writer lock OS e scrittura atomica esistenti.
- `create` deriva layout e collection dall'ID; nomi con HTML sono metadati. Reader non crea storage e rifiuta create/register. Bootstrap legacy non scrive manifest o artefatti del corpus e rispetta un registry vuoto già esistente.
- Override confinati ai blocchi ammessi; copia profonda della configurazione e argv verification validati. La configurazione corrente non espone un validatore strutturato più forte per authority/retrieval/eval da riusare. Nessun rilievo aggiuntivo su questo punto.
- Symlink/junction delle root, directory principali e registry vengono rifiutati; nessuna pretesa aggiunta di protezione contro sostituzioni concorrenti da parte di processi locali privilegiati.
- DI del constructor e campi `ProjectError` approvati. Dipendenza da atomic helpers accettata; i task successivi devono evitare il ciclo runtime `artifacts -> projects`, come già registrato dal PM.

## Limiti ed esecuzione

Non rilanciata la suite: 28 test mirati e Ruff verdi risultano dal report implementatore; suite completa ancora in esecuzione al momento della review. Eseguita soltanto la riproduzione sopra, con l'interprete 3.14.6 esistente, `PYTHONPATH` al worktree e dati temporanei. Nessuna modifica al codice o a Git, nessun commit, nessun subagente.

Un primo tentativo `uv run --frozen python -` ha iniziato a creare `rag/.venv` nel worktree ed è stato subito interrotto; nessuna suite o installazione completata. Il PM è stato informato e gestisce l'eventuale scaffold. Tutti i comandi hanno usato un workdir esplicito nel worktree isolato; l'originale è stato usato soltanto come percorso dell'interprete esistente.
