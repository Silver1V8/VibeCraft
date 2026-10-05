# Gestione uniforme delle cartelle e degli indici dei progetti

Specifica proposta il 5 ottobre 2026, da approvare prima del piano di implementazione.

## Obiettivo concordato

Ogni progetto creato da VibeCraft deve avere una cartella dedicata sotto
`VIBECRAFT_PROJECTS_DIR`, compreso il progetto iniziale oggi chiamato legacy.
Documenti, codice, modifiche, staging, stato della pipeline e indice devono usare
lo stesso flusso dei progetti ordinari. Un clone pulito deve rispettare questa
regola fin dal primo avvio; l'installazione esistente deve poter migrare senza
perdere dati. PyCharm deve poter mostrare le cartelle effettive dei progetti.

## Problema verificato nel codice

`core/projects.py` registra automaticamente legacy nella root dell'installazione
quando trova documenti, codice o artefatti storici. `create()` crea invece i nuovi
progetti sotto `projects/<id>` con un manifest e cartelle dedicate.

La differenza riguarda anche il comportamento: `api/deps.py` riserva a legacy
uno stato globale; `core/artifacts.py` accetta artefatti flat e un profilo diverso;
`core/indexing.py` usa percorsi di aggiornamento diversi per legacy e progetti
ordinari. CLI e API senza selezione possono accedere ai percorsi globali.
La sola modifica del percorso nel registro non elimina queste differenze.

## Decisione proposta

Riutilizzare il layout, il contesto e gli snapshot immutabili dei progetti
ordinari. Conservare `legacy` come identificatore stabile del progetto iniziale,
così i collegamenti esistenti possono continuare a selezionarlo. L'identificatore
non determina privilegi, percorsi globali o un algoritmo di indicizzazione diverso.
I nuovi progetti continuano a ricevere gli ID UUID già usati.

Due alternative sono scartate: spostare solo le cartelle lascerebbe differenze
operative; assegnare un nuovo UUID al progetto iniziale richiederebbe anche una
rimappatura dei collegamenti senza beneficio funzionale.

```text
vibecraft/
  rag/                         applicazione e documentazione tecnica
  docs/                        baseline distribuita, usata come sorgente iniziale
  projects/
    projects.json              registro locale
    legacy/
      project.yaml
      code/
      docs/
      changes/
      database/
        versions/
        staging/
        pipeline/
        eval/
    <uuid>/
      project.yaml
      code/
      docs/
      changes/
      database/
```

Il percorso base resta configurabile e in Docker resta `/app/projects`.
Aprire una root VibeCraft esistente mantiene la registrazione della cartella
originale, con gli attuali vincoli locali/remoti: quella root deve comunque avere
il medesimo layout. I nuovi progetti e il progetto iniziale vengono creati nella
directory gestita. Non si introduce una copia automatica delle root esterne.

## Avvio da un clone pulito

Alla prima inizializzazione writer, con registro assente e baseline distribuita
disponibile, creare `projects/legacy` attraverso la stessa costruzione del layout
usata per gli altri progetti e copiarvi la baseline in `docs/`.
Il codice incluso in un clone pulito è soltanto uno scheletro: riprodurre le
cartelle previste senza inventare codice o documenti di dominio.
Se il registro manca ma esistono indice storico, modifiche, staging, stato
di pipeline o codice effettivo nella root, richiedere invece la migrazione.
Documenti locali eventualmente presenti nella sorgente `docs/` non vengono
scartati: anche la copia iniziale verifica inventario e hash e conserva gli
originali. Il manifest e il registro vengono pubblicati solo dopo la copia
completa; una preparazione interrotta deve essere riconoscibile e riprendibile.

La copia iniziale è una sola operazione: aggiornamenti dell'applicazione e
riavvii non sovrascrivono i documenti del progetto. Un registro già esistente e
vuoto resta vuoto. Senza baseline né dati storici, la console resta senza progetti
finché l'utente ne crea uno. Il bootstrap non scarica modelli, non chiama Qdrant
e non indicizza. Un reader non crea cartelle né modifica il registro.

La baseline nella root è materiale distribuito, non un secondo corpus attivo.
Gli altri nuovi progetti conservano il comportamento attuale di creazione vuota
e possono ricevere documenti attraverso Intake.

## Migrazione dell'installazione esistente

La migrazione è un comando writer esplicito, eseguito con server e altri writer
fermi. La lettura ordinaria del registro storico segnala la necessità di migrare
prima di servire quel progetto; non sposta dati durante una richiesta HTTP.

1. Leggere e validare registro, configurazione e percorsi storici effettivi,
   compresi database o staging configurati fuori dalla root. Acquisire i lock
   esistenti del registro e del writer; salvare una copia del registro originario.
2. Preparare `projects/legacy` senza pubblicarlo. Copiare `code/`, `docs/`,
   `changes/`, staging e stato persistente della pipeline dai percorsi storici.
   Trasferire le impostazioni per progetto ammesse dal manifest; i modelli e
   le impostazioni di installazione restano condivisi.
3. Confrontare inventario e hash dei file copiati con gli originali. Vietare
   symlink/junction e percorsi sovrapposti. Una destinazione preesistente non
   riconosciuta come copia della stessa migrazione causa un errore, non un merge.
4. Conservare intatti database storico, versioni e collection originali come
   recupero. Non rendere attivi nel nuovo database gli artefatti flat o gli indici
   che dichiarano la vecchia collection. Per un legacy già indicizzato eseguire
   una build ordinaria nel namespace `vibecraft_legacy`, verificare integrità e
   gate previsti e pubblicare la nuova root soltanto dopo il loro successo.
   Verificare prima che il namespace di destinazione non appartenga al vecchio
   indice o a un altro progetto: un conflitto interrompe la migrazione senza
   modificare alias o collection preesistenti. Il comando prevede esplicitamente
   costo e dipendenze della build; non la avvia un reader o una richiesta HTTP.
   Per un legacy privo di indice pubblicare il progetto come `not_indexed`.
5. Pubblicare atomicamente il registro aggiornato, conservando ID e nome del
   progetto. Registrare l'esito per rendere il comando ripetibile: dopo il
   successo una nuova esecuzione non ricopia e non ricostruisce.

Un errore di copia, verifica o build lascia intatti il registro originale e i
sorgenti. Lo stato della preparazione permette di riprendere la stessa migrazione
senza confonderla con una nuova cartella. I file originali restano la copia
recuperabile; la loro eliminazione e quella delle collection storiche non fanno
parte di questa modifica. Tornare alla vecchia versione richiede ripristinare il
registro salvato e usare i dati originali, con i processi fermi.

Lo storico di pipeline e staging viene conservato. Contratti o anteprime legati
al vecchio indice, ai vecchi percorsi o ad hash non più validi richiedono nuova
validazione; la migrazione non li approva automaticamente.

## Un solo flusso operativo

Il registro aggiornato distingue il formato storico da quello uniforme tramite
versione di schema. La versione storica resta leggibile per diagnostica e
migrazione; la nuova versione risolve tutte le root tramite `project.yaml`.
Il campo storico `legacy` non seleziona più un runtime speciale. La risposta API
lo mantiene temporaneamente a `false` per compatibilità con la UI corrente.

Le operazioni applicative ricevono sempre un `ProjectContext` risolto dal
registro. Il vecchio default `legacy`, dove necessario per compatibilità di API
e CLI, risolve lo stesso progetto ordinario; se manca, restituisce
`project_required` o un errore CLI esplicito. Non ripiega sulle cartelle della root.
MCP conserva la selezione per sessione; i job conservano il progetto di avvio.

Per tutti i progetti, runtime, cache, gate, job e journal sono isolati per ID.
Gli indici usano alias `vibecraft_<id>` e collection
`vibecraft_<id>__<version>`, con gli stessi controlli, snapshot immutabili e
rollback. Il delta conserva il comportamento ordinario attuale: nessun lavoro
se non cambia nulla, build completa quando occorre pubblicare modifiche.

L'indicizzatore scansiona solo `project.docs_dir` e `project.code_dir`,
ricorsivamente, con i filtri esistenti su formati, dipendenze e build.
`changes/`, `database/`, baseline di installazione e documentazione tecnica
non sono corpus aggiuntivi. Modelli, client e servizi esterni restano condivisi.

## Superficie della modifica

Il lavoro parte da registro e bootstrap in `core/projects.py`, prosegue con
risoluzione del progetto in CLI/API/MCP e rimuove le eccezioni operative nei
consumatori del contesto: runtime, artefatti, indexing, Qdrant, eval gate e agenti.
I riferimenti al formato storico delle versioni non vanno confusi con l'ID
del progetto: servono ancora per leggere i dati da migrare.

Aggiornare configurazione, Docker/Compose, script e istruzioni in README dove
presentano le cartelle globali come progetto attivo. Riutilizzare lock, scritture
atomiche, costruzione degli indici e test già presenti. Nessuna nuova dipendenza,
nessun sistema parallelo di progetti e nessuna modifica alla selezione per scheda.
Le modifiche locali preesistenti nel checkout restano fuori dai commit del lavoro.

## Criteri di accettazione

- Un clone pulito con baseline crea il progetto iniziale sotto `projects/legacy`,
  senza modelli o servizi esterni; un secondo avvio non modifica i suoi file.
- Progetto iniziale e due nuovi progetti hanno manifest e cartelle equivalenti,
  indici separati e lo stesso comportamento di build, delta, errore e rollback.
- Un file fuori da `docs/` e `code/` del target non entra nel suo indice.
- La migrazione copia tutti i dati previsti con hash corrispondenti, conserva gli
  originali e i link con ID `legacy`, e non cambia gli altri progetti registrati.
- Un legacy indicizzato viene pubblicato solo dopo verifica della nuova build;
  Qdrant assente, gate fallito, copia interrotta o destinazione in conflitto
  lasciano registro e dati originari recuperabili. Una ripresa non duplica i dati.
- Reader, registro corrotto e percorsi collegati continuano a fallire senza
  scritture o fallback. Richieste senza un progetto valido non leggono la root.
- I test esistenti di registro, API, workflow, isolamento e indexing vengono
  adattati al comportamento uniforme e restano verdi. I nuovi casi di bootstrap
  e migrazione usano root temporanee; non alterano i dati locali reali.

## Verifica della specifica

La specifica definisce bootstrap, compatibilità dell'ID, pubblicazione, recupero,
perimetro dell'indice e controlli di migrazione. L'implementazione e la migrazione
reale dei dati locali iniziano dopo approvazione della specifica e del piano.
