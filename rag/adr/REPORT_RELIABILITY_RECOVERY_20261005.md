# Report affidabilità e recupero delle sessioni

Data: 5 ottobre 2026. Progetto: VibeCraft.

Sono state sviluppate le prime tre migliorie approvate: distinguere guasti e risultati vuoti nel retrieval, rendere rigoroso il gate dell'indice e recuperare il lavoro della pipeline dopo refresh o chiusura. Backup/restore e delta copy-on-write restano fuori ambito. Non sono state aggiunte dipendenze.

## Comportamento finale

### Retrieval

Il punto comune del retrieval governato solleva `RetrievalUnavailable` quando Qdrant, embedding o il testo di una fonte recuperata non sono disponibili. Una ricerca valida con zero risultati conserva il comportamento precedente.

Canvas, Propose, dry-run, agent-context ed export restituiscono HTTP 503 con un messaggio operativo sanitizzato. La generazione di Canvas e Spec completa il recupero obbligatorio prima di chiamare il modello o sovrascrivere documenti e metadati. I dettagli tecnici rimangono nel log del server. L'uso offline del helper Python dell'agente dichiara esplicitamente che il contesto normativo non è verificato; le lezioni accessorie del Canvas restano opzionali.

### Gate dell'indice

Il loader valida struttura del golden set, domande e matcher attesi. File assente o `cases: []` rappresentano una baseline non disponibile e consentono il bootstrap, con `evaluated: false`. Un file presente ma vuoto, YAML malformato o casi invalidi producono un errore distinto.

Con gate abilitato e `blocking: true`, un errore di caricamento o valutazione nega la promozione e lascia invariati `CURRENT` e l'alias di produzione. In modalità advisory la promozione è consentita con avviso. Un gate disattivato evita lettura e valutazione. Il report core espone `evaluated` ed `error_stage`; il report API del job distingue il guasto con `skipped: error` rispetto al bootstrap `no_golden_set`.

### Recupero della pipeline

Il browser conserva una bozza per progetto e feature: conversazione dell'intervista, storico del modello, input non inviato, ambito, passo ed editor Explore/Canvas/Spec. L'ultimo salvataggio locale è visibile.

Tornando allo stesso progetto, la pipeline propone l'ultima feature e carica prima i file server. «Ripristina bozza locale» recupera gli editor senza scrivere sul server; «Scarta bozza e usa file server» conserva la versione server. La scelta esplicita evita di nascondere nuove modifiche server. I messaggi recuperati vengono mostrati come testo.

Le risposte e gli stream tardivi della feature precedente non aggiornano quella corrente. Il cambio feature ripulisce report, prompt e pannelli transitori. Uno stream di archiviazione privo dell'evento terminale non viene mostrato come completato. Storage locale negato, pieno o corrotto produce un avviso; anche agente e decisioni liberano i controlli se la lettura della chiave fallisce.

Le bozze non includono chiavi API, autorizzazioni, riferimenti di validazione o stato di esecuzione dell'agente. Il ripristino non avvia generazioni, operazioni o scritture sul server.

## Agenti e revisione

| Ruolo | Modello | Responsabilità |
| --- | --- | --- |
| PM e integrazione frontend | GPT-6 Astra, reasoning high | Requisiti, separazione dei task, recovery, verifica finale dello scope e review backend |
| Sviluppatore retrieval | GPT-6.1 Sol, reasoning high | Errori condivisi e consumatori; review indipendente del gate |
| Sviluppatore gate | GPT-6.1 Sol, reasoning high | Validazione e politica di promozione; review indipendente del frontend |
| Coordinatore | Sessione principale | Worktree isolato, integrazione, suite completa, documentazione e consegna Git |

I modelli sono stati scelti in base alla complessità: Astra per le decisioni e l'integrazione UI asincrona, Sol per i flussi backend ben delimitati. Le review incrociate hanno trovato due problemi negli stream e un problema nello storage della chiave; tutti sono stati corretti e ricontrollati. Il frontend è stato rivisto da chi non lo aveva implementato.

## Verifiche

Le nuove regressioni sono state osservate fallire prima delle correzioni e passare dopo. Sono verificati anche zero risultati validi, baseline assente, gate advisory/disattivato, file server nuovi, feature omonime tra progetti, storage negato e stream incompleti.

| Verifica | Esito |
| --- | --- |
| Suite Python completa con Qdrant reale e browser integrativo | **2.429 passed, 25 skipped, zero failure**, in 395,84 secondi |
| Test saltati per limiti dell'ambiente | 20 per privilegi symlink Windows assenti; 5 per pesi Docling assenti nel checkout isolato |
| Retrieval, guasti HTTP e sicurezza | Verdi, incluso run focalizzato da 88 test |
| Gate | 45 test verdi; ulteriori 8 test progetto con Qdrant reale e in memoria verdi |
| Indicizzazione, integrità e timing | 179 test verdi dopo adeguamento della fixture sintetica |
| Ruff sull'intero `rag/` | Superato |
| Recovery Node e browser Edge reale | Superati |
| Workflow, validation, agent, runner capability e dry-run Node | Superati |
| Workspace multiprogetto in Edge | Superato: navigazione, iframe, stream/job A/B e isolamento |
| Sintassi JavaScript e controllo del diff | Superati |

La prima suite completa ha rilevato 13 fallimenti nelle fixture di indicizzazione: il fake Qdrant privo di `query_points` non poteva superare il nuovo gate bloccante. È stato esplicitato in un solo helper di test che quelle prove misurano l'indicizzazione, usando il seam positivo già adottato negli altri test. Le prove specifiche del gate continuano a impostare e verificare gli esiti negativi. Il codice di produzione e le assertion non sono stati indeboliti.

Comandi principali, eseguiti da `rag/` con l'ambiente Python esistente:

```text
PYTHONUTF8=1
VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:6333
VIBECRAFT_REQUIRE_QDRANT=1
VIBECRAFT_INTEGRATION_BROWSER=1
python -m pytest -rs
python -m ruff check .
node tests/pipeline_session_recovery.cjs
VIBECRAFT_SESSION_BROWSER=1 node tests/pipeline_session_recovery.cjs
node tests/projects_workspace.cjs
```

Per le prove browser `NODE_PATH` punta al runtime Playwright già disponibile; su Windows viene usato Edge. Il nuovo test recovery è aggiunto al workflow CI. Questa consegna non include una build Docker da zero o una verifica dei provider remoti: i provider delle prove sono simulati ai confini.

## Limiti e adozione

- Il recupero funziona nello stesso browser e origine, tornando al progetto. La schermata iniziale conserva la selezione dei progetti già prevista: non seleziona automaticamente l'ultimo progetto dopo la chiusura della scheda.
- Le bozze non sono sincronizzate tra dispositivi e si perdono cancellando i dati del sito. Le scritture dei documenti server richiedono i normali pulsanti di salvataggio.
- Stream ed esecuzioni interrotti non vengono riavviati automaticamente; lo stato del gate resta verificato dal server.
- Se un golden set presente è invalido, il gate bloccante richiede di correggerlo prima di promuovere l'indice. La baseline intenzionalmente vuota deve dichiarare `cases: []`.
- Le modifiche locali preesistenti del checkout principale sono escluse dal commit di questa consegna.

Specifica e piano: [design](reliability-recovery/design.md), [piano](reliability-recovery/plan.md). Commit e destinazione Git sono verificati nella risposta finale della consegna.
