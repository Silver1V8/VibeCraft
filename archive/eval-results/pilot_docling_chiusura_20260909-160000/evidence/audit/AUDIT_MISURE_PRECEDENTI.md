# Audit delle misure prodotte il 2026-09-09 (`pilot_docling_finale_20260909-110000`)

Rivalutazione di **tutte e sedici** le risposte archiviate — otto baseline e otto
candidato — non solo di quelle già segnalate. Gli originali restano intatti
(`out/verifica_riuso.json`: inventario di 61 file, zero alterati); le nuove
valutazioni stanno in `audit/audit_finale_20260909-110000.json` e sono prodotte
da `scripts/audit_risposte.py`, rieseguibile.

Domande, risposte attese, celle, normalizzazioni e soglie **non sono state
toccate**. L'asse A riproduce alla lettera il controllo storico proprio per
rendere visibile quanto valga da solo.

## Tre difetti negli strumenti di misura, non solo nelle risposte

### 1. Lo schermo delle citazioni estraeva frammenti privi di senso

`eval_stack.py` aveva **ri-scritto** l'estrattore invece di riusare quello che il
repository ha già:

| | espressione | apostrofo `'` |
|---|---|---|
| `eval_stack.py` (sessione precedente) | `[«"']([^«»"']{12,200})[»"']` | **delimitatore** |
| `eval/attribution.py` (repository) | `[«"“]([^»"”]{20,}?)[»"”]` | non delimitatore |

In italiano l'apostrofo ASCII è segno di elisione **dentro** le parole — `l'area`,
`dell'utente`, `all'interno` — quindi ogni elisione apriva o chiudeva una
citazione. Da `l'**Area Personale** (o "Profilo Utente") dedicata all'…` lo
schermo ricavava due frammenti, fra cui il famigerato `) dedicata all`. Secondo
difetto: la soglia era in **caratteri** (≥12), non in **parole**, quindi
accettava frammenti privi di contenuto proposizionale.

Effetto sulle misure: su 15 «citazioni» archiviate, **12 erano artefatti di
parsing**. E `) dedicata all` risultava `verified`, cioè un frammento senza
significato veniva contato come citazione verificata.

Correzione: **riuso** di `eval.attribution.quoted_spans` (`scripts/citazioni.py`),
già coperto da `tests/test_attribution.py`. Chiamanti verificati prima di
toccare qualunque cosa: `check_citations` nell'harness N3 e quel test. Nessuna
modifica al repository. Controllo minimo in `scripts/check_citazioni.py`, sette
casi superati: apostrofi interni, virgolette doppie, caporali, Markdown,
delimitatore aperto e non chiuso, chiusura orfana, citazione inventata che
**resta** `unverifiable`.

### 2. Il corpus di verifica non conteneva i PDF

Difetto indipendente e più grave, trovato leggendo l'archivio:

```python
_it = _raw.values() if isinstance(_raw, dict) else _raw
for _c in _it:
    if isinstance(_c, dict) and _c.get("chunk_id"):   # <-- sempre None
        CHUNKS[_c["chunk_id"]] = _c.get("text", "")
```

In `chunks.json` il `chunk_id` è la **chiave** del dizionario, non un campo del
valore (i campi sono `doc_id`, `section`, `text`). La mappa restava vuota,
quindi:

- ogni `testo` di chunk archiviato in `eval_*.json` è la stringa vuota — verificato: `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` caratteri sulle dieci fonti di `pdf-mock-4`;
- la riga che inseriva i PDF nel corpus di verifica (`corpus[_cid] = _txt`) non veniva mai eseguita;
- quindi **nessuna citazione tratta dal PDF poteva risultare verificata**.

Riletti i chunk dall'indice davvero interrogato (copia archiviata in
`audit/indice_precedente_<stack>/`, con assert sulla versione), la citazione
`Checkpoint human-in-the-loop e punti di controllo` del baseline passa da
`unverifiable` a `verified`. Il verdetto «citazioni non verificabili» della
sessione precedente era in parte un artefatto dello strumento.

### 3. «8/8 completa» misurava una sottostringa, non una risposta

`pdf-diag-4` chiedeva `5 artefatti, 1 cartella sorgente` e i valori attesi erano
`["5", "1"]`: due cifre nude, che come sottostringa combaciano con qualunque
numero di qualunque parola. Rimisurato con confini di parola (asse B) l'esito qui
non cambia — ma la misura precedente non lo dimostrava, lo assumeva.

## Le sedici risposte, asse per asse

`A` valori attesi presenti (sottostringa, misura storica) · `B` stessa cosa con
confini di parola · `cit` citazioni prima→dopo la correzione (e quante
verificate) · `doc` la risposta nomina il documento atteso · `sez` affermazioni
di sezione errate · `id` identificatori assenti dal contesto · `dng` dato
presente dichiarato assente.

### baseline (pypdf)

| domanda | A | B | cit | doc | rango | sez | id | dng |
|---|---|---|---|---|---|---|---|---|
| pdf-diag-1 | ok | ok | 0→0 (0) | no | 1 | 0 | — | no |
| pdf-diag-2 | ok | ok | 1→0 (0) | sì | 1 | **1** | — | no |
| pdf-diag-3 | **manca `19.5 KB`** | **manca** | 1→1 (**1**) | sì | 3 | 0 | — | no |
| pdf-diag-4 | ok | ok | 1→1 (0) | sì | 1 | 0 | — | no |
| pdf-mock-1 | ok | ok | 0→0 (0) | no | 1 | 0 | — | no |
| pdf-mock-2 | ok | ok | 1→0 (0) | sì | 1 | **1** | — | no |
| pdf-mock-3 | ok | ok | 3→0 (0) | no | **10** | 0 | — | no |
| pdf-mock-4 | ok | ok | 0→0 (0) | sì | 1 | 0 | — | no |

### candidato (Docling)

| domanda | A | B | cit | doc | rango | sez | id | dng |
|---|---|---|---|---|---|---|---|---|
| pdf-diag-1 | ok | ok | 1→0 (0) | sì | 1 | 0 | — | no |
| pdf-diag-2 | ok | ok | 0→0 (0) | no | 1 | 0 | — | no |
| pdf-diag-3 | ok | ok | 0→0 (0) | sì | **5** | 0 | — | **SÌ** |
| pdf-diag-4 | ok | ok | 3→1 (0) | sì | 1 | **2** | — | no |
| pdf-mock-1 | ok | ok | 1→0 (0) | sì | 1 | 0 | — | no |
| pdf-mock-2 | ok | ok | 0→0 (0) | sì | 1 | 0 | — | no |
| pdf-mock-3 | ok | ok | 3→0 (0) | sì | 2 | 0 | — | no |
| pdf-mock-4 | ok | ok | 0→0 (0) | sì | 1 | 0 | **1** | no |

Totali: citazioni **7→2** (baseline) e **8→1** (candidato); documento atteso
nominato 5/8 e 7/8.

## I quattro punti sollevati, verificati uno per uno

### `pdf-diag-4` — la banda KPI attribuita alla sezione sbagliata: **confermato**

Nel Markdown candidato l'ordine è: titolo `## Catalogo diagrammi`, poi la frase
introduttiva, poi `5 artefatti` e `1 cartella sorgente SVG formato`, e **solo
dopo** `### Regole di organizzazione`. La risposta scrive:

- «`5 artefatti` (citato nella sezione "Indice operativo")» → `sezione_inesistente`; le intestazioni reali sono `Catalogo diagrammi`, `Regole di organizzazione`, `Registro dei file`, `Percorso sorgente`. «Indice operativo» sono le prime due parole della frase introduttiva, non un titolo.
- «`1 cartella sorgente SVG formato` (citato nella sezione "Regole di organizzazione")» → `valore_in_altra_sezione`, effettiva: `Catalogo diagrammi`.

**Dove nasce l'errore.** Non nella segmentazione: il PDF produce **un solo
chunk**, `…catalogo_diagrammi_normativi.pdf#00-catalogo-diagrammi`. Non nei
metadati di sezione: quel chunk porta `section = "Catalogo diagrammi"`, che è
corretto, e l'intestazione di blocco che il modello riceve è
`--- …catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---`
— la risposta stessa la cita testualmente. L'errore nasce nella **generazione**:
il modello scende a sotto-sezioni che l'intestazione non dichiara e ne indovina
l'ordine.

Il baseline non commette questo errore su `pdf-diag-4`, ma su `pdf-diag-2` e
`pdf-mock-2` attribuisce alla sezione «Registro dei file» un dato che viene da un
testo **senza alcuna intestazione**: il suo chunk è `#00-documento`, sezione
`(documento)`. Il baseline non fa attribuzione di sezione migliore: ne fa una
non sostenibile dalla fonte che ha.

### `pdf-diag-3` — «peso» letto come Authority: **confermato, in entrambi gli stack**

- **baseline**: nomina il file giusto, poi conclude «il diagramma è associato al peso **0.90** (ereditato dalla classe METHODOLOGY)». `19.5 KB` non compare: la misura storica lo segnava già come mancante (è il 7/8).
- **candidato**: nomina il file giusto e scrive `19.5 KB` **in un inciso**, dentro la spiegazione di che cosa contiene la colonna, e poi conclude: «il contesto **non riporta** un vincolo o un valore di Authority per `diag_6_2_hitl_checkpoints.svg.svg`».

Il controllo di sottostringa vede `19.5 KB` e segna «completa». Lo schermo del
diniego (`G`) vede insieme: valori attesi **presenti nel contesto** e frasi
`nessuna fonte` / `non riporta` nella risposta → `contraddizione_da_leggere`.
Un dato presente dichiarato assente non è una risposta completa.

**Conseguenza sul confronto precedente:** il «candidato 8/8 contro baseline 7/8»
non regge. Su `pdf-diag-3` **nessuno dei due** risponde alla domanda posta.

La causa non è Docling — è comune ai due stack. Il retrieval porta in cima
`vibe_coding_workflow.md § Protocollo Human-in-the-Loop` (0.90) e
`spec_graph_rag_ingestion.md § Requisiti di Retrieval e Authority Boost` (0.87);
il PDF arriva 3º (baseline) e 5º (candidato). E `[CLASSE-FONTI]`
(`core/retrieval.py`) enuncia una graduatoria di autorevolezza **con pesi
numerici** e chiude con «se un vincolo è enunciato SOLO da una fonte meno
autorevole, riportalo dicendo esplicitamente che nessuna fonte più autorevole lo
stabilisce» — che è, parola per parola, la forma che entrambe le risposte
assumono. La parola «peso» della domanda viene agganciata alla scala di classe.

### `pdf-mock-3` — la specifica aggiuntiva: **non è un errore, ed è la provenienza a distinguere**

Entrambi descrivono la schermata usando `02_specs_normative/spec_area_pers_1.5.md`,
che è legittimamente nel contesto. La differenza è nella dichiarazione:

- il **candidato** nomina la spec (`specificata nel file 02_specs_normative/spec_area_pers_1.5.md`) **e** riporta l'associazione del catalogo (`specifica 1.5`, `area funzionale Dipendente`), cioè la risposta attesa;
- il **baseline** non nomina né la spec né il catalogo, e conclude «Area Personale Dipendente» fondendo il nome della schermata con l'area. Il catalogo gli arriva al **rango 10**.

Nessuna citazione fra virgolette di `pdf-mock-3` è verificabile in nessuno dei
due stack, in entrambi i casi perché sono parafrasi, non citazioni — dopo la
correzione dell'estrattore, i tre «passi» spariscono del tutto.

### `pdf-mock-4` — nomi, affermazioni aggiuntive, troncamento

- **Nome sbagliato**: il candidato scrive `mockup_2_4_notification_templates.svg` (senza la `s`). Il contesto porta `mockup_2_4_notifications_templates.svg`. Non è l'artefatto di spaziatura del layout PDF: dopo aver ricomposto gli spazi il nome **resta assente**. Un identificatore alterato in una risposta che deve elencare artefatti.
- **Affermazione aggiuntiva non sostenuta**: il candidato scrive che i nomi «esatti» sono quelli della sua tabella e che quelli del PDF mostrano «una discrepanza tra la rappresentazione testuale e il contenuto reale del file sorgente». È un'inferenza sul file sorgente che il contesto non sostiene; e la tabella che dichiara corretta è quella dove ha appena sbagliato un nome. Anche il baseline aggiunge una «nota sulla divergenza» non richiesta, ma la chiude dicendo che divergenze non ce ne sono.
- **Troncamento**: nessuno. Entrambe le risposte terminano su una frase chiusa; l'asse dedicato (`finisce_a_meta`) è negativo. La riga `4 aree funzionali SVG + HTML formati` del candidato non è un troncamento: è la resa del raggruppamento di reading-order già registrato nella sessione precedente.

## Che cosa resta valido dell'archivio

Ranghi di retrieval, testi integrali delle risposte, tempi, versioni di indice e
`health` non sono toccati da nessuno dei tre difetti: sono registrati dalla
risposta HTTP. Restano validi e sono la base di questo audit. Ciò che va
scartato è il conteggio delle citazioni, il loro esito, e la lettura di
«completezza» come sinonimo di «risposta corretta».
