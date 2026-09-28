# Pacchetto di revisione umana — pilot Docling, chiusura

Il cancello 1c chiede, per l'attribuzione, «schermo piu' **lettura umana**».
Gli schermi automatici stanno tutti qui sotto, con il loro esito; la lettura
e' quella che manca e che nessuno strumento di questa sessione puo' firmare.

Il giudice N3 archiviato NON e' usato: non e' qualificato a certificare risposte
nuove (20/24 in-sample, non supera S6) e il suo archivio storico non e' prova
dell'attribuzione di queste risposte.

**Come leggere.** Per ogni domanda: la fonte e la sezione EFFETTIVE (dal contesto
inviato al modello, non da cio' che la risposta dichiara), l'estratto pertinente,
poi ogni passata di ogni stack con l'esito dei controlli. Le domande su cui un
controllo automatico ha trovato qualcosa sono elencate qui sotto, e sono quelle
da leggere per prime.

## Punti che richiedono giudizio umano

- **pdf-diag-2** — sezione attribuita male (baseline)
- **pdf-diag-3** — dato presente dichiarato assente (baseline); dato presente dichiarato assente (candidate); identificatore non sostenuto dal contesto (candidate); sezione attribuita male (baseline); sezione attribuita male (candidate); valori attesi mancanti ['19.5 KB'] (baseline, tutte le passate); valori attesi mancanti ['19.5 KB'] (candidate, tutte le passate)
- **pdf-diag-4** — identificatore non sostenuto dal contesto (baseline); sezione attribuita male (candidate)
- **pdf-mock-2** — sezione attribuita male (baseline); sezione attribuita male (candidate)
- **pdf-mock-3** — sezione attribuita male (baseline)
- **pdf-mock-4** — identificatore non sostenuto dal contesto (candidate)

---

## pdf-diag-1

**Domanda:** Nel catalogo diagrammi, quale area e' associata al file diag_5_2_graph_rag_structure.svg?

**Risposta attesa (congelata):** Knowledge

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---
# 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf
## Catalogo diagrammi
Indice operativo per classificare, consultare e mantenere gli artefatti visuali normativi.

5 artefatti

1 cartella sorgente SVG formato

### Regole di organizzazione

| 1. Naming        | Mantieni il prefisso diag_ , seguito da area o sezione e da un nome descrittivo in snake_case.                   |
|------------------|------------------------------------------------------------------------------------------------------------------|
| 2. Posizione     | Conserva qui solo diagrammi normativi; bozze e fonti editabili vanno in una sottocartella source .               |
```

### baseline — passata 1

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nel documento: * **File:** `diag_5_2_graph_rag_structure.svg` * **Area:** `Knowledge` * **Finalità:** Struttura del grafo e pipeline Graph RAG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 11.2s


### baseline — passata 2

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nel documento: - **File:** `diag_5_2_graph_rag_structure.svg` - **Area:** `Knowledge` - **Finalità:** Struttura del grafo e pipeline Graph RAG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.2s


### baseline — passata 3

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nel documento: * **File:** `diag_5_2_graph_rag_structure.svg` * **Area:** `Knowledge` * **Finalità:** Struttura del grafo e pipeline Graph RAG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.0s


### candidate — passata 1

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nella tabella «Registro dei file» del documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: | File | Area | Finalita | Formato / peso | |--------------------------------------------|--------------|---------------------------------------------------------|------------------| | diag_5_2_graph_rag_structure.sv g | **Knowledge**| Struttura del grafo e pipeline Graph RAG. | SVG 11.2 KB |
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 9.1s


### candidate — passata 2

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata nel registro dei file del documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`, dove la riga relativa a tale file specifica: - **File:** `diag_5_2_graph_rag_structure.sv g` (con spazio e errore di battitura nel nome originale del file come riportato nel contesto) - **Area:** `Knowledge` - **Finalita:** Struttura del grafo e pipeline Graph RAG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.9s


### candidate — passata 3

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata nel registro dei file del documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: | File | Area | Finalita | Formato / peso | |--------------------------------------------|--------------|---------------------------------------------------------|------------------| | diag_5_2_graph_rag_structure.sv g | **Knowledge**| Struttura del grafo e pipeline Graph RAG. | SVG 11.2 KB |
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.9s


---

## pdf-diag-2  ⚠

**Domanda:** Nel catalogo diagrammi, qual e' il formato e il peso di diag_0_3_modules_relations_map.svg?

**Risposta attesa (congelata):** SVG, 46.4 KB

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`

**Da decidere:** sezione attribuita male (baseline)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---
# 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf
## Catalogo diagrammi
Indice operativo per classificare, consultare e mantenere gli artefatti visuali normativi.

5 artefatti

1 cartella sorgente SVG formato

### Regole di organizzazione

| 1. Naming        | Mantieni il prefisso diag_ , seguito da area o sezione e da un nome descrittivo in snake_case.                   |
|------------------|------------------------------------------------------------------------------------------------------------------|
| 2. Posizione     | Conserva qui solo diagrammi normativi; bozze e fonti editabili vanno in una sottocartella source .               |
```

### baseline — passata 1

```text
Nel catalogo diagrammi, per il file `diag_0_3_modules_relations_map.svg`: * **Formato:** SVG * **Peso:** 46.4 KB Questi dati sono riportati nel documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` nella sezione "Registro dei file".
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 6.3s

  - sezione dichiarata «Registro dei file» → `sezione_inesistente`

### baseline — passata 2

```text
Nel catalogo diagrammi (`02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`), per il file `diag_0_3_modules_relations_map.svg`: * **Formato:** SVG * **Peso:** 46.4 KB
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 2.3s


### baseline — passata 3

```text
Nel catalogo diagrammi, per il file `diag_0_3_modules_relations_map.svg`: * **Formato:** SVG * **Peso:** 46.4 KB Questi dati sono riportati testualmente nel registro dei file del documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` (classe `[SENZA CLASSE]`).
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 2.6s


### candidate — passata 1

```text
Nel catalogo diagrammi, il file `diag_0_3_modules_relations_map .svg` ha il formato **SVG** e un peso di **46.4 KB**.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 5.8s


### candidate — passata 2

```text
Nel catalogo diagrammi, il file `diag_0_3_modules_relations_map .svg` ha il formato **SVG** e un peso di **46.4 KB**.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 1.8s


### candidate — passata 3

```text
Nel catalogo diagrammi, il file `diag_0_3_modules_relations_map .svg` ha il formato **SVG** e un peso di **46.4 KB**.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 1.8s


---

## pdf-diag-3  ⚠

**Domanda:** Quale diagramma del catalogo documenta i checkpoint human-in-the-loop, e con quale peso?

**Risposta attesa (congelata):** diag_6_2_hitl_checkpoints.svg.svg, 19.5 KB

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`

**Da decidere:** dato presente dichiarato assente (baseline); dato presente dichiarato assente (candidate); identificatore non sostenuto dal contesto (candidate); sezione attribuita male (baseline); sezione attribuita male (candidate); valori attesi mancanti ['19.5 KB'] (baseline, tutte le passate); valori attesi mancanti ['19.5 KB'] (candidate, tutte le passate)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---
# 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf
## Catalogo diagrammi
Indice operativo per classificare, consultare e mantenere gli artefatti visuali normativi.

5 artefatti

1 cartella sorgente SVG formato

### Regole di organizzazione

| 1. Naming        | Mantieni il prefisso diag_ , seguito da area o sezione e da un nome descrittivo in snake_case.                   |
|------------------|------------------------------------------------------------------------------------------------------------------|
| 2. Posizione     | Conserva qui solo diagrammi normativi; bozze e fonti editabili vanno in una sottocartella source .               |
```

### baseline — passata 1

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato come artefatto di tipo **Governance**. Il suo peso (Authority) è determinato dalla classe della fonte da cui proviene il vincolo o la descrizione del diagramma. Nel contesto fornito, il file `04_knowledge_informative/vibe_coding_workflow.md` (che descrive i checkpoint HITL) ha la classe **[METHODOLOGY]** con un'autorevolezza di **0.90**. Poiché il catalogo (`catalogo_diagrammi_normativi.pdf`) è classificato come **[SENZA CLASSE]** (peso 0.30), ma funge da inventario e non stabilisce i vincoli operativi dei checkpoint, l'autorevolezza del diagramma per quanto riguarda la definizione dei checkpoint HITL deriva dalla fonte che li enuncia: `vibe_coding_workflow.md`. Pertanto, il peso è **0.90**.
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 3) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: SI · status: success, cached: False, 8.5s


### baseline — passata 2

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato come artefatto di tipo **Governance**. Secondo la tabella «Registro dei file» nel documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`, questo file ha una finalità specifica: illustrare i "Checkpoint human-in-the-loop e punti di controllo". Per quanto riguarda il **peso** (autorità), il contesto non assegna un valore numerico diretto a questo diagramma specifico. Tuttavia, applicando la [REGOLA-ASTENSIONE] inversa e la gerarchia delle fonti: 1. Il file è elencato nel documento `catalogo_diagrammi_normativi.pdf` che ha la classe **[SENZA CLASSE]** (peso 0.30). 2. La specifica tecnica che definisce i checkpoint (`04_knowledge_informative/vibe_coding_workflow.md`) ha la classe **[METHODOLOGY]** (peso 0.90) e cita esplicitamente le regole `[REGOLA-HITL-01]` fino a `[REGOLA-HITL-05]`. 3. Poiché il diagramma è un artefatto visivo che illustra una specifica già classificata come `METHODOLOGY`, l'autorevolezza del contenuto rappresentato dal diagramma deriva dalla fonte testuale che lo descrive e lo utilizza (`vibe_coding_workflow.md`). Pertanto, il vincolo di autorità applicabile al contenuto documentato dal diagramma è **0.90**, derivante dalla classe **[METHODOLOGY]** della specifica `04_knowledge_informative/vibe_coding_workflow.md` che definisce i checkpoint citati nel diagramma.
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 3) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 1/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 7.9s

  - sezione dichiarata «Registro dei file» → `sezione_inesistente`
  - citazione `verified` «Checkpoint human-in-the-loop e punti di controllo» → 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf#00-documento

### baseline — passata 3

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato come artefatto di tipo **Governance**. Secondo il contesto fornito: 1. Il file `diag_6_2_hitl_checkpoints.svg.svg` è elencato nel catalogo diagrammi (`02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`) con la finalità "Checkpoint human-in-the-loop e punti di controllo" e formato SVG. 2. La classe della fonte per questo file è **SENZA CLASSE** (indicata come `[SENZA CLASSE]` nel blocco del contesto relativo al PDF). Il peso (Authority) attribuito a questo diagramma è **0.30**. **Motivazione del calcolo del peso:** La regola di autorità stabilisce che il peso decresce in questa gerarchia: `METADATA` (0.90) > `METHODOLOGY` (0.90) > `REQUIREMENTS` (0.87) > `NORMS` (0.85) > **`SENZA CLASSE` (0.30)**. Poiché il file del catalogo diagrammi è esplicitamente etichettato come `[SENZA CLASSE]`, non può ereditare il peso di altre classi (come `METHODOLOGY` o `REQUIREMENTS`) anche se i checkpoint stessi sono descritti in documenti di quelle classi. Il vincolo tecnico richiede di attribuire il peso alla fonte che enuncia l'artefatto visivo, e quella fonte è classificata come "SENZA CLASSE". **Nota sulla divergenza:** Sebbene i checkpoint (`[REGOLA-HITL-01]`...`[REGOLA-HITL-05]`) siano definiti nel documento `vibe_coding_workflow.md` (classe `[METHODOLOGY]`, peso 0.90), il diagramma specifico che li *documenta* visivamente è contenuto in un file di catalogo privo di classe esplicita. Pertanto, per quanto riguarda l'artefatto grafico stesso, il peso rimane 0.30.
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 3) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 1/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 9.1s

  - citazione `verified` «Checkpoint human-in-the-loop e punti di controllo» → 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf#00-documento

### candidate — passata 1

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato nell'area **Governance** con la finalità di illustrare "Checkpoint human-in-the-loop e punti di controllo". Per quanto riguarda il peso (Authority), il contesto non riporta un valore numerico esplicito per questo file specifico nel blocco `README.md`. Tuttavia, applicando la **[REGOLA-ASTENSIONE]** inversa (non astensione totale ma attribuzione basata sulla fonte dichiarata): 1. Il file è elencato in `catalogo_diagrammi_normativi.pdf` con la classe **`SENZA CLASSE`**. 2. Nel blocco `README.md`, i documenti senza classe esplicita o non classificati nella tabella principale hanno un'autorevolezza dichiarata di **0.30** (vedi riga: "Un vincolo... va attribuiti alla fonte PIÙ autorevole che li enuncia... SENZA CLASSE (0.30)"). 3. Poiché il file è solo elencato nel catalogo e non citato come fonte primaria di regole in altri documenti con una classe superiore, si applica la classe dichiarata nel catalogo: **`SENZA CLASSE`** con peso **0.30**. Sebbene i checkpoint vengano definiti nei documenti `[METHODOLOGY]` (peso 0.90) e `[REQUIREMENTS]` (peso 0.87), il diagramma stesso, come artefatto visivo catalogato senza classificazione specifica oltre a "SENZA CLASSE", porta il peso della sua fonte dichiarata nel catalogo. **Risposta sintetica:** * **Diagramma:** `diag_6_2_hitl_checkpoints.svg.svg` * **Peso (Authority):** 0.30 (fonte: `catalogo_diagrammi_normativi.pdf`, classe `SENZA CLASSE`).
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 5) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 1/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: SI · status: success, cached: False, 11.8s

  - citazione `verified` «Checkpoint human-in-the-loop e punti di controllo» → 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf#00-catalogo-diagrammi
  - citazione `unverifiable` «Un vincolo... va attribuiti alla fonte PIÙ autorevole che li enuncia... SENZA CLASSE (0.30)»

### candidate — passata 2

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, contenuto nella cartella sorgente `C:\Users\Silve\Desktop\vibecraft\docs\02\_specs\_normative\diagrams`. Questo file ha la seguente classificazione e peso: * **File:** `diag_6_2_hitl_checkpoints.svg.svg` * **Area:** Governance * **Finalità:** Checkpoint human-in-the-loop e punti di controllo. * **Classe della fonte:** SENZA CLASSE (0.30) **Motivazione del peso:** Secondo la regola `[CLASSE-FONTI]`, l'autorevolezza decresce così: `METADATA` > `METHODOLOGY` > `REQUIREMENTS` > `NORMS` > **`SENZA CLASSE`**. Poiché il file è classificato come `SENZA CLASSE`, il suo peso è **0.30**. Il documento che definisce i contenuti di questi checkpoint (`[REGOLA-HITL-01]` a `[REGOLA-HITL-05]`) è invece `vibe_coding_workflow.md`, classificato come `METHODOLOGY` (peso 0.90), ma la domanda chiede specificamente il diagramma del catalogo.
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 5) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 6.1s


### candidate — passata 3

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato nell'area **Governance** con la finalità di illustrare "Checkpoint human-in-the-loop e punti di controllo". Per quanto riguarda il **peso** (Authority), il contesto non riporta un valore numerico esplicito per questo diagramma specifico. Tuttavia, applicando la [REGOLA-ASTENSIONE] inversa (attribuzione al peso della fonte più autorevole che lo enuncia o ne fa parte): 1. Il file si trova nella cartella `02_specs_normative/diagrams/`. 2. La tabella "Tassonomia delle cartelle" in `spec_graph_rag_ingestion.md` (classe **REQUIREMENTS**) stabilisce che i documenti in `docs/02_specs_normative/` hanno la classificazione tipica **`REQUIREMENTS`**. 3. Il blocco README.md assegna a tutti i documenti della classe **`REQUIREMENTS`** un valore di Authority pari a **0.87**. Pertanto, il diagramma ha un peso di **0.87**, derivato dalla classificazione `REQUIREMENTS` assegnata alla cartella contenente il file.
```

Controlli: valori attesi: MANCANO ['19.5 KB'] · fonte attesa nel contesto: si (rango 5) · documento nominato: no · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 1/0 · identificatori non sostenuti: ['3.  Il blocco README.md'] · dato presente dichiarato assente: SI · status: success, cached: False, 5.8s

  - sezione dichiarata «Tassonomia delle cartelle» → `sezione_inesistente`
  - citazione `verified` «Checkpoint human-in-the-loop e punti di controllo» → 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf#00-catalogo-diagrammi

---

## pdf-diag-4  ⚠

**Domanda:** Quanti artefatti contiene il catalogo diagrammi e quante cartelle sorgente dichiara?

**Risposta attesa (congelata):** 5 artefatti, 1 cartella sorgente

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`

**Da decidere:** identificatore non sostenuto dal contesto (baseline); sezione attribuita male (candidate)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---
# 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf
## Catalogo diagrammi
Indice operativo per classificare, consultare e mantenere gli artefatti visuali normativi.

5 artefatti

1 cartella sorgente SVG formato

### Regole di organizzazione

| 1. Naming        | Mantieni il prefisso diag_ , seguito da area o sezione e da un nome descrittivo in snake_case.                   |
|------------------|------------------------------------------------------------------------------------------------------------------|
| 2. Posizione     | Conserva qui solo diagrammi normativi; bozze e fonti editabili vanno in una sottocartella source .               |
```

### baseline — passata 1

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e **1 cartella sorgente**. Ecco i dettagli estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Artefatti:** Il testo dichiara esplicitamente "5 artefatti" nell'indice operativo. * Elenco degli artefatti (file): 1. `diag_0_3_modules_relations_map.svg` 2. `diag_2_1_workflow_state_machineme.svg` 3. `diag_2_3_concurrency_pessimistic_lock.svg` 4. `diag_5_2_graph_rag_structure.svg` 5. `diag_6_2_hitl_checkpoints.svg.svg` * **Cartelle sorgente:** Il testo dichiara esplicitamente "1 cartella sorgente". * Percorso indicato: `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\diagrams`. Nessun altro numero di artefatti o cartelle è menzionato in questo specifico documento.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: ['diag_2_1_workflow_state_machineme.svg'] · dato presente dichiarato assente: no · status: success, cached: False, 9.5s

  - citazione `unverifiable` «nell'indice operativo.
    *   Elenco degli artefatti (file):
        1.  `diag_0_3_modules_relations_map.svg`
        2»

### baseline — passata 2

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e **1 cartella sorgente**. Ecco i dettagli estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` (§ 1): * **Artefatti:** "5 artefatti" * **Cartelle sorgente:** "1 cartella sorgente" I nomi degli artefatti elencati nel registro dei file sono: 1. `diag_0_3_modules_relations_map.svg` 2. `diag_2_1_workflow_state_machineme.svg` (nome troncato nel testo originale) 3. `diag_2_3_concurrency_pessimistic_lock.svg` 4. `diag_5_2_graph_rag_structure.svg` 5. `diag_6_2_hitl_checkpoints.svg.svg` Il percorso della cartella sorgente dichiarato è: `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\diagrams`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: ['diag_2_1_workflow_state_machineme.svg'] · dato presente dichiarato assente: no · status: success, cached: False, 5.0s


### baseline — passata 3

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e **1 cartella sorgente**. Ecco i dettagli estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Artefatti:** 5 * Identificatori: `diag_0_3_modules_relations_map.svg`, `diag_2_1_workflow_state_machine.svg`, `diag_2_3_concurrency_pessimistic_lock.svg`, `diag_5_2_graph_rag_structure.svg`, `diag_6_2_hitl_checkpoints.svg`. * **Cartelle sorgente:** 1 * Percorso: `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\diagrams`
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 4.0s


### candidate — passata 1

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e dichiara **1 cartella sorgente**. Ecco i dati estratti testualmente dal blocco `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Numero di artefatti:** "5 artefatti" * **Numero di cartelle sorgenti:** "1 cartella sorgente SVG formato"
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 6.7s

  - citazione `unverifiable` «*   **Numero di cartelle sorgenti:**»

### candidate — passata 2

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e dichiara **1 cartella sorgente**. Ecco i dati estratti testualmente dal blocco `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Numero di artefatti:** "5 artefatti" * **Numero di cartelle sorgenti:** "1 cartella sorgente SVG formato"
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 2.6s

  - citazione `unverifiable` «*   **Numero di cartelle sorgenti:**»

### candidate — passata 3

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e dichiara **1 cartella sorgente**. Ecco i dettagli estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Artefatti:** Il testo afferma esplicitamente "5 artefatti" nella sezione introduttiva. * **Cartelle sorgenti:** La tabella "Registro dei file" elenca 5 file specifici (es. `diag_0_3_modules_relations_map .svg`, `diag_2_1_workflow_state_machin e.svg`, ecc.). La sezione "Regole di organizzazione", riga 2, specifica: "Conserva qui solo diagrammi normativi; bozze e fonti editabili vanno in una sottocartella source ." * **Percorso sorgente:** Il contesto indica un unico percorso per i file SVG: `C:\Users\Silve\Desktop\vibecraft\docs\02\_specs\_normative\diagrams`. Pertanto, il catalogo dichiara 5 artefatti e fa riferimento a 1 cartella sorgente principale (con una sottocartella `source` menzionata come destinazione per le bozze, ma non elencata come contenitore di artefatti nel registro).
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 3 · citazioni verificate/non verificabili: 0/2 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 5.9s

  - sezione dichiarata «Registro dei file» → `valore_non_trovato`
  - sezione dichiarata «Registro dei file» → `valore_in_altra_sezione` (effettiva: ['Regole di organizzazione'])
  - sezione dichiarata «Regole di organizzazione» → `valore_non_trovato`
  - citazione `unverifiable` «nella sezione introduttiva.
*   **Cartelle sorgenti:** La tabella»
  - citazione `unverifiable` «elenca 5 file specifici (es. `diag_0_3_modules_relations_map .svg`, `diag_2_1_workflow_state_machin e.svg`, ecc.). La se»

---

## pdf-mock-1

**Domanda:** Nel catalogo mockup, quale numero di specifica e quale area sono associati a mockup_2_4_notifications_templates.svg?

**Risposta attesa (congelata):** spec 2.4, area Manager

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup [SENZA CLASSE] ---
# 02_specs_normative/mockups/catalogo_mockup_normativi.pdf
## Catalogo mockup
Indice operativo delle interfacce di riferimento collegate alle specifiche normative.

11 artefatti

4 aree funzionali SVG + HTML formati

### Regole di organizzazione

| 1. Naming        | Usa mockup_[spec]_[ruolo]_[schermata] ; il numero deve coincidere con la specifica associata.                     |
|------------------|-------------------------------------------------------------------------------------------------------------------|
| 2. Ruoli         | Raggruppa per Dipendente, Manager e Admin; mantieni SVG come riferimento statico e HTML per prototipi navigabili. |
```

### baseline — passata 1

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **specifica 2.4** e all'**area Manager**. Questa associazione è confermata dai dati riportati nel documento `[SENZA CLASSE]`: * **File:** `mockup_2_4_notifications_templates.svg` * **Spec.:** `2.4` * **Area:** `Manager` * **Schermata:** Gestione template di notifica.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 5.8s


### baseline — passata 2

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **specifica 2.4** e all'**area Manager**. Questa associazione è confermata dal registro dei file nel documento `[SENZA CLASSE]`: * **File:** `mockup_2_4_notifications_templates.svg` * **Spec.:** `2.4` * **Area:** `Manager` * **Schermata:** Gestione template di notifica. La specifica normativa corrispondente è definita in `[REQUIREMENTS]` come `02_specs_normative/spec_notifications_2.4.md`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.6s


### baseline — passata 3

```text
Nel catalogo mockup, il file **mockup_2_4_notifications_templates.svg** è associato alla **specifica 2.4** e all'**area Manager**. Questa associazione è confermata dal registro dei file nel documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` [SENZA CLASSE], che elenca: * **File:** mockup_2_4_notifications_templates.svg * **Spec.:** 2.4 * **Area:** Manager * **Schermata:** Gestione template di notifica La specifica normativa corrispondente è definita in `02_specs_normative/spec_notifications_2.4.md` [REQUIREMENTS] come "Sistema di Notifiche".
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.8s


### candidate — passata 1

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **Specifica 2.4** e all'**Area Manager**. Ecco i dettagli estratti testualmente dal contesto: * **Numero di specifica:** `2.4` (estratto dalla colonna "Spec." della tabella del file). * **Area:** `Manager` (estratto dalla colonna "Area" della stessa tabella). * **File completo:** `mockup_2_4_notifications_templates.svg`. Fonte primaria: `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (blocco `[SENZA CLASSE]`).
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 7.0s

  - citazione `unverifiable` «della tabella del file).
*   **Area:** `Manager` (estratto dalla colonna»

### candidate — passata 2

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **Specifica 2.4** e all'**Area Manager**. Questi dati sono estratti testualmente dalla tabella «Registro dei file» nel documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`: | File | Spec. | Area | Schermata | Formato / peso | |--------------------------------------------|---------|-----------------|--------------------------------------------|------------------| | mockup_2_4_notifications_tem plates.svg | 2.4 | Manager | Gestione template di notifica. | SVG 18.6 KB | Nessun altro documento o codice nel contesto fornisce informazioni diverse o aggiuntive su questi attributi specifici per questo file.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 4.1s


### candidate — passata 3

```text
Nel catalogo mockup, il file **mockup_2_4_notifications_templates.svg** è associato alla **Spec. 2.4** e all'**Area Manager**. Questi dati sono estratti testualmente dalla tabella «Registro dei file» presente nel documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (CLASSE: [SENZA CLASSE]): | File | Spec. | Area | Schermata | Formato / peso | |--------------------------------------------|---------|-----------------|--------------------------------------------|------------------| | mockup_2_4_notifications_tem plates.svg | 2.4 | Manager | Gestione template di notifica. | SVG 18.6 KB |
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 4.1s


---

## pdf-mock-2  ⚠

**Domanda:** Qual e' l'unico file del registro mockup in formato HTML e quanto pesa?

**Risposta attesa (congelata):** mockup_3_5_admin_dashboard_analytics.html, 3.4 KB

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`

**Da decidere:** sezione attribuita male (baseline); sezione attribuita male (candidate)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup [SENZA CLASSE] ---
# 02_specs_normative/mockups/catalogo_mockup_normativi.pdf
## Catalogo mockup
Indice operativo delle interfacce di riferimento collegate alle specifiche normative.

11 artefatti

4 aree funzionali SVG + HTML formati

### Regole di organizzazione

| 1. Naming        | Usa mockup_[spec]_[ruolo]_[schermata] ; il numero deve coincidere con la specifica associata.                     |
|------------------|-------------------------------------------------------------------------------------------------------------------|
| 2. Ruoli         | Raggruppa per Dipendente, Manager e Admin; mantieni SVG come riferimento statico e HTML per prototipi navigabili. |
```

### baseline — passata 1

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** `3.4 KB` Questo dato è estratto testualmente dal blocco `[SENZA CLASSE]` del documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`, nella sezione "Registro dei file", dove la riga specifica: `mockup_3_5_admin_dashboard_analytics.html | 3.5 | Admin | Dashboard analytics amministrativa. | HTML | 3.4 KB`. Nessun altro file con estensione `.html` è presente nell'elenco fornito nel contesto.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 7.2s

  - sezione dichiarata «Registro dei file» → `sezione_inesistente`

### baseline — passata 2

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** `3.4 KB` Questo dato è estratto testualmente dal blocco `[SENZA CLASSE]` del documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`, nella sezione "Registro dei file", dove la riga specifica: `mockup_3_5_admin_dashboard_analytics.html | 3.5 | Admin | Dashboard analytics amministrativa. | HTML | 3.4 KB`. Nessun altro file con estensione `.html` è presente nell'elenco fornito nel contesto.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.7s

  - sezione dichiarata «Registro dei file» → `sezione_inesistente`

### baseline — passata 3

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** 3.4 KB Tutti gli altri file elencati nel documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` sono in formato SVG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 2.5s


### candidate — passata 1

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** 3.4 KB Tutti gli altri file elencati nel contesto hanno estensione `.svg`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 5.8s


### candidate — passata 2

```text
Il contesto riporta un **unico** file del registro mockup in formato HTML. Ecco i dettagli estratti testualmente dal contesto: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** `HTML 3.4 KB` **Fonte del vincolo:** Il blocco «CODICE ESISTENTE» relativo al file `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (§ Catalogo mockup) elenca questo specifico artefatto nella tabella "Registro dei file", indicando che è l'unico con estensione `.html` e peso `3.4 KB`. Tutti gli altri 10 artefatti elencati nello stesso contesto hanno estensione `.svg`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.9s

  - sezione dichiarata «Registro dei file» → `valore_non_trovato`

### candidate — passata 3

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** 3.4 KB Tutti gli altri file elencati nel documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` sono in formato SVG.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 2.5s


---

## pdf-mock-3  ⚠

**Domanda:** Che cosa mostra la schermata mockup_1_5_employee_personal_area.svg e a quale area appartiene?

**Risposta attesa (congelata):** Area personale del dipendente; area Dipendente

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`

**Da decidere:** sezione attribuita male (baseline)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup [SENZA CLASSE] ---
# 02_specs_normative/mockups/catalogo_mockup_normativi.pdf
## Catalogo mockup
Indice operativo delle interfacce di riferimento collegate alle specifiche normative.

11 artefatti

4 aree funzionali SVG + HTML formati

### Regole di organizzazione

| 1. Naming        | Usa mockup_[spec]_[ruolo]_[schermata] ; il numero deve coincidere con la specifica associata.                     |
|------------------|-------------------------------------------------------------------------------------------------------------------|
| 2. Ruoli         | Raggruppa per Dipendente, Manager e Admin; mantieni SVG come riferimento statico e HTML per prototipi navigabili. |
```

### baseline — passata 1

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato nel portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: 1. Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``. 2. Gestire i record in fase di compilazione non ancora trasmessi. 3. Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'area appartiene alla specifica normativa relativa all'**Area Personale Dipendente** (specificata in `02_specs_normative/spec_area_pers_1.5.md`).
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 10) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 7.7s


### baseline — passata 2

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: 1. Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` `. 2. Gestire i record in fase di compilazione non ancora trasmessi. 3. Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'area appartiene alla specifica normativa definita nel file **02_specs_normative/spec_area_pers_1.5.md**, sezione "Obiettivo e Layout dell'Area Personale", classificata come **[REQUIREMENTS]**. Il mockup è elencato nel documento **02_specs_normative/mockups/catalogo_mockup_normativi.pdf** (pagina 2, registro dei file) con i seguenti dettagli: * **File:** `mockup_1_5_employee_personal_area.svg` * **Spec.:** `1.5` * **Area:** `Dipendente` * **Schermata:** `Area personale del dipendente.` * **Formato / peso:** `SVG`, `31.4 KB` * **Percorso sorgente:** `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\mockups` La schermata è parte delle "4 aree funzionali" del sistema, specificamente quella relativa al ruolo di **DIPENDENTE**.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 10) · documento nominato: si · sezioni dichiarate errate: 1 · citazioni verificate/non verificabili: 0/2 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 7.4s

  - sezione dichiarata «Obiettivo e Layout dell» → `sezione_inesistente`
  - citazione `unverifiable` «) dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft.

Questa interfaccia garantisce trasparenza a»
  - citazione `unverifiable` «, classificata come **[REQUIREMENTS]**.

Il mockup è elencato nel documento **02_specs_normative/mockups/catalogo_mockup»

### baseline — passata 3

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: * Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``; * Gestire i record in fase di compilazione non ancora trasmessi; * Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'interfaccia si presenta come uno spazio centralizzato in cui ciascun dipendente può tenere traccia delle proprie partecipazioni e dei feedback forniti dai manager senza la necessità di ricaricare la pagina (Single Page Application UX). Questa schermata appartiene all'**Area Personale Dipendente**, definita nella specifica normativa `` `02_specs_normative/spec_area_pers_1.5.md` ``.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 10) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 4.9s


### candidate — passata 1

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale del dipendente** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: 1. Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` `. 2. Gestire i record in fase di compilazione non ancora trasmessi. 3. Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'area appartiene funzionalmente all'**Area Personale Dipendente** (o "Profilo Utente"), come definito nella specifica normativa § 1. Obiettivo e Layout dell'Area Personale.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 2) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 8.1s

  - citazione `unverifiable` «) dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft.

Questa interfaccia garantisce trasparenza a»

### candidate — passata 2

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale del dipendente** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato nel portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: * Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``; * Gestire i record in fase di compilazione non ancora trasmessi; * Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'area appartiene funzionalmente all'area **Dipendente** e fa parte della specifica normativa definita nel file **02_specs_normative/spec_area_pers_1.5.md**. Nel registro dei mockup, il file è classificato come segue: * **File:** `mockup_1_5_employee_personal_area.svg` * **Spec.:** `1.5` * **Area:** `Dipendente` * **Schermata:** `Area personale del dipendente` * **Formato / peso:** `SVG 31.4 KB` Il percorso sorgente per il file è: `C:\Users\Silve\Desktop\vibecraft\docs\02\_specs\_normative\mockups`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 2) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 6.3s


### candidate — passata 3

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale del dipendente** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: * Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``; * Gestire i record in fase di compilazione non ancora trasmessi; * Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). La schermata appartiene all'area funzionale **Dipendente** e fa parte della specifica normativa definita nel file `02_specs_normative/spec_area_pers_1.5.md`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 2) · documento nominato: no · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 4.2s


---

## pdf-mock-4  ⚠

**Domanda:** Quanti artefatti e quante aree funzionali dichiara il catalogo mockup, e in quali formati?

**Risposta attesa (congelata):** 11 artefatti, 4 aree funzionali, formati SVG + HTML

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`

**Da decidere:** identificatore non sostenuto dal contesto (candidate)

**Sezione effettiva nel contesto** (intestazione di blocco): `02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup`

**Estratto pertinente del contesto inviato:**

```text
--- 02_specs_normative/mockups/catalogo_mockup_normativi.pdf § Catalogo mockup [SENZA CLASSE] ---
# 02_specs_normative/mockups/catalogo_mockup_normativi.pdf
## Catalogo mockup
Indice operativo delle interfacce di riferimento collegate alle specifiche normative.

11 artefatti

4 aree funzionali SVG + HTML formati

### Regole di organizzazione

| 1. Naming        | Usa mockup_[spec]_[ruolo]_[schermata] ; il numero deve coincidere con la specifica associata.                     |
|------------------|-------------------------------------------------------------------------------------------------------------------|
| 2. Ruoli         | Raggruppa per Dipendente, Manager e Admin; mantieni SVG come riferimento statico e HTML per prototipi navigabili. |
```

### baseline — passata 1

```text
Il contesto riporta che il documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: - **11 artefatti** - **4 aree funzionali** - Formati: **SVG + HTML** Ecco l'elenco completo degli artefatti e delle aree funzionali estratti testualmente dal registro dei file del contesto, con i rispettivi formati: ### Artefatti (11 totali) | File | Spec. | Area | Schermata | Formato / Peso | |---|---|---|---|---| | `mockup_1_1_auth_login.svg` | 1.1 | Autenticazione | Schermata di accesso. | SVG (21.3 KB) | | `mockup_1_2_employee_dashboard.svg` | 1.2 | Dipendente | Dashboard operativa del dipendente. | SVG (30.0 KB) | | `mockup_1_3_event_details.svg` | 1.3 | Dipendente | Dettaglio di un evento o una prenotazione. | SVG (18.4 KB) | | `mockup_1_4_reservation_form.svg` | 1.4 | Dipendente | Form di inserimento prenotazione. | SVG (23.4 KB) | | `mockup_1_5_employee_personal_area.svg` | 1.5 | Dipendente | Area personale del dipendente. | SVG (31.4 KB) | | `mockup_2_2_manager_approval_queue.svg` | 2.2 | Manager | Coda di approvazione del responsabile. | SVG (25.9 KB) | | `mockup_2_4_notifications_templates.svg` | 2.4 | Manager | Gestione template di notifica. | SVG (18.6 KB) | | `mockup_3_2_admin_crud_events.svg` | 3.2 | Admin | Gestione CRUD degli eventi. | SVG (27.4 KB) | | `mockup_3_3_admin_global_monitor.svg` | 3.3 | Admin | Monitoraggio globale amministrativo. | SVG (24.6 KB) | | `mockup_3_4_admin_export_modal.svg` | 3.4 | Admin | Finestra di esportazione dati. | SVG (12.2 KB) | | `mockup_3_5_admin_dashboard_analytics.html` | 3.5 | Admin | Dashboard analytics amministrativa. | HTML (3.4 KB) | ### Aree Funzionali (4 totali) Il documento elenca le aree funzionali associate ai ruoli e alle specifiche: 1. **Autenticazione** (Spec. 1.1) 2. **Dipendente** (Spec. 1.2, 1.3, 1.4, 1.5) 3. **Manager** (Spec. 2.2, 2.4) 4. **Admin** (Spec. 3.2, 3.3, 3.4, 3.5) ### Vincoli e Regole di Organizzazione estratti dal contesto: - **Naming**: `mockup_[spec]_[ruolo]_[schermata]` (il numero deve coincidere con la specifica associata). - **Ruoli**: Raggruppa per `DIPENDENTE`, `MANAGER` e `ADMIN`. - **Formati**: Mantenere `SVG` come riferimento statico e `HTML` per prototipi navigabili. - **Tracciabilità**: Ogni modifica a un flusso UX deve essere riconciliata con la specifica e annotata nel changelog del progetto.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 17.9s


### baseline — passata 2

```text
Il contesto riporta che il documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: - **11 artefatti** - **4 aree funzionali** - Formati: **SVG** e **HTML**. Ecco il dettaglio degli artefatti e delle aree funzionali estratti testualmente dal registro dei file contenuto nel documento citato: ### Artefatti (11 totali) I nomi dei file elencati sono: 1. `mockup_1_1_auth_login.svg` 2. `mockup_1_2_employee_dashboard.svg` 3. `mockup_1_3_event_details.svg` 4. `mockup_1_4_reservation_form.svg` 5. `mockup_1_5_employee_personal_area.svg` 6. `mockup_2_2_manager_approval_queue.svg` 7. `mockup_2_4_notifications_templates.svg` 8. `mockup_3_2_admin_crud_events.svg` 9. `mockup_3_3_admin_global_monitor.svg` 10. `mockup_3_4_admin_export_modal.svg` 11. `mockup_3_5_admin_dashboard_analytics.html` ### Aree Funzionali (4 totali) Derivate dai prefissi numerici dei file e dalle descrizioni: 1. **Autenticazione** (Area 1, es. `mockup_1_*`) 2. **Dipendente** (Area 1, es. `mockup_1_2`, `mockup_1_3`, `mockup_1_4`, `mockup_1_5`) 3. **Manager** (Area 2, es. `mockup_2_*`) 4. **Admin** (Area 3, es. `mockup_3_*`) ### Formati - **SVG**: utilizzato per i mockup statici (es. `mockup_1_1_auth_login.svg`). - **HTML**: utilizzato per la dashboard analytics amministrativa (`mockup_3_5_admin_dashboard_analytics.html`).
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 9.2s


### baseline — passata 3

```text
Il contesto riporta che il documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (CLASSE: [SENZA CLASSE]) dichiara esplicitamente **11 artefatti** e **4 aree funzionali**. Per quanto riguarda i formati, il contesto elenca due tipi specifici per gli artefatti del catalogo mockup: * **SVG**: utilizzato per 10 file (es. `mockup_1_1_auth_login.svg`, `mockup_2_2_manager_approval_queue.svg`, ecc.). * **HTML**: utilizzato per 1 file (`mockup_3_5_admin_dashboard_analytics.html`). Il contesto non menziona altri formati per questo specifico catalogo (come PDF o immagini raster), limitandosi a questi due.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 3.9s


### candidate — passata 1

```text
Il contesto riporta che il file `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: * **Artefatti:** 11 artefatti. * **Aree funzionali:** 4 aree funzionali. * **Formati:** SVG e HTML. Il contesto elenca i seguenti file nel registro dei file, confermando la presenza di entrambi i formati (SVG per la maggior parte, HTML per un singolo file): | File | Formato / peso | |---|---| | mockup_1_1_auth_login.svg | SVG 21.3 KB | | mockup_1_2_employee_dashb oard.svg | SVG 30.0 KB | | mockup_1_3_event_details.svg | SVG 18.4 KB | | mockup_1_4_reservation_form. svg | SVG 23.4 KB | | mockup_1_5_employee_person al_area.svg | SVG 31.4 KB | | mockup_2_2_manager_approva l_queue.svg | SVG 25.9 KB | | mockup_2_4_notifications_tem plates.svg | SVG 18.6 KB | | mockup_3_2_admin_crud_even ts.svg | SVG 27.4 KB | | mockup_3_3_admin_global_mo nitor.svg | SVG 24.6 KB | | mockup_3_4_admin_export_mo dal.svg | SVG 12.2 KB | | mockup_3_5_admin_dashboard _analytics.html | HTML 3.4 KB | Pertanto, il catalogo dichiara **11 artefatti** distribuiti in **4 aree funzionali**, utilizzando i formati **SVG** e **HTML**.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/0 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 11.1s


### candidate — passata 2

```text
Il contesto riporta che il file `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: - **11 artefatti** - **4 aree funzionali** - Formati: **SVG + HTML** Ecco la tabella completa estratta dal contesto che elenca i 11 artefatti con le rispettive aree e formati: | File | Spec. | Area | Schermata | Formato / peso | |---|---|---|---|---| | mockup_1_1_auth_login.svg | 1.1 | Autenticazion e | Schermata di accesso. | SVG 21.3 KB | | mockup_1_2_employee_dashb oard.svg | 1.2 | Dipendente | Dashboard operativa del dipendente. | SVG 30.0 KB | | mockup_1_3_event_details.svg | 1.3 | Dipendente | Dettaglio di un evento o una prenotazione. | SVG 18.4 KB | | mockup_1_4_reservation_form. svg | 1.4 | Dipendente | Form di inserimento prenotazione. | SVG 23.4 KB | | mockup_1_5_employee_person al_area.svg | 1.5 | Dipendente | Area personale del dipendente. | SVG 31.4 KB | | mockup_2_2_manager_approva l_queue.svg | 2.2 | Manager | Coda di approvazione del responsabile. | SVG 25.9 KB | | mockup_2_4_notifications_tem plates.svg | 2.4 | Manager | Gestione template di notifica. | SVG 18.6 KB | | mockup_3_2_admin_crud_even ts.svg | 3.2 | Admin | Gestione CRUD degli eventi. | SVG 27.4 KB | | mockup_3_3_admin_global_mo nitor.svg | 3.3 | Admin | Monitoraggio globale amministrativo. | SVG 24.6 KB | | mockup_3_4_admin_export_mo dal.svg | 3.4 | Admin | Finestra di esportazione dati. | SVG 12.2 KB | | mockup_3_5_admin_dashboard _analytics.html | 3.5 | Admin | Dashboard analytics amministrativa. | HTML 3.4 KB | **Nota sulla divergenza tra documento e codice:** Il contesto contiene anche un blocco `CODICE ESISTENTE` relativo a `frontend/package.json`. Questo file di configurazione elenca le dipendenze (`next`, `react`, `tailwindcss`, ecc.) ma **non elenca né dichiara esplicitamente** i nomi dei 11 artefatti mockup, né il conteggio "11 artefatti", né la distinzione tra "4 aree funzionali" come fatto dal documento PDF. Pertanto, per quanto riguarda il conteggio degli artefatti e le aree funzionali, si fa riferimento esclusivamente al documento `catalogo_mockup_normativi.pdf`.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/1 · identificatori non sostenuti: nessuno · dato presente dichiarato assente: no · status: success, cached: False, 12.4s

  - citazione `unverifiable` «, né la distinzione tra»

### candidate — passata 3

```text
Il contesto riporta che il file `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: * **11 artefatti** (specificati nella riga "11 artefatti" dell'indice operativo). * **4 aree funzionali** (specificate nella riga "4 aree funzionali SVG + HTML formati"). * I formati sono **SVG** e **HTML**. Ecco il dettaglio degli artefatti e dei relativi formati estratti dalla tabella «Registro dei file» del contesto: | File | Formato | |---|---| | mockup_1_1_auth_login.svg | SVG | | mockup_1_2_employee_dashboard.svg | SVG | | mockup_1_3_event_details.svg | SVG | | mockup_1_4_reservation_form.svg | SVG | | mockup_1_5_employee_personal_area.svg | SVG | | mockup_2_2_manager_approval_queue.svg | SVG | | mockup_2_4_notification_templates.svg | SVG | | mockup_3_2_admin_crud_events.svg | SVG | | mockup_3_3_admin_global_monitor.svg | SVG | | mockup_3_4_admin_export_modal.svg | SVG | | mockup_3_5_admin_dashboard_analytics.html | HTML | **Nota sulla divergenza:** Il contesto elenca 11 file nel «Registro dei file», ma la riga di sintesi dell'indice afferma "4 aree funzionali". La tabella raggruppa i file per area funzionale (Autenticazione, Dipendente, Manager, Admin), confermando che i 11 artefatti coprono queste 4 aree.
```

Controlli: valori attesi: tutti presenti · fonte attesa nel contesto: si (rango 1) · documento nominato: si · sezioni dichiarate errate: 0 · citazioni verificate/non verificabili: 0/2 · identificatori non sostenuti: ['mockup_2_4_notification_templates.svg'] · dato presente dichiarato assente: no · status: success, cached: False, 7.8s

  - citazione `unverifiable` «dell'indice operativo).
*   **4 aree funzionali** (specificate nella riga»
  - citazione `unverifiable` «).
*   I formati sono **SVG** e **HTML**.

Ecco il dettaglio degli artefatti e dei relativi formati estratti dalla tabel»

---

## Risposte integrali

Ogni risposta di ogni passata, con il contesto inviato per intero, sta in
`out/eval_<stack>_p<passata>.json`. Nessuna e' stata omessa da questo pacchetto.
