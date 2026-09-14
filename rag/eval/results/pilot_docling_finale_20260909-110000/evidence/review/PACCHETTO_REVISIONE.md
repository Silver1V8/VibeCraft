# Pacchetto di revisione umana — attribuzione delle risposte

Il cancello 1c chiede, per l'attribuzione, «schermo piu' **lettura umana**».
Il giudice N3 archiviato non e' qualificato a certificare risposte nuove
(20/24 in-sample, non supera S6) e il prompt vieta di sostituirlo con un altro
modello. Quindi **questo controllo resta pendente**: sotto c'e' tutto il
materiale per deciderlo, non una decisione gia' presa.

Per ogni domanda: risposta attesa, le due risposte reali, la fonte attesa e il
suo rango, e le citazioni fra virgolette con esito della verifica deterministica.

Domanda da porsi su ciascuna: **la risposta attribuisce il dato alla fonte
giusta?** Non basta che il dato sia corretto.

## pdf-diag-1

**Domanda:** Nel catalogo diagrammi, quale area e' associata al file diag_5_2_graph_rag_structure.svg?

**Risposta attesa:** Knowledge

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nel documento: * **File:** `diag_5_2_graph_rag_structure.svg` * **Area:** `Knowledge` * **Finalità:** Struttura del grafo e pipeline Graph RAG.
```

Nessuna citazione fra virgolette nella risposta.

### CANDIDATO (Docling)

```text
Nel catalogo diagrammi, l'area associata al file `diag_5_2_graph_rag_structure.svg` è **Knowledge**. Questa associazione è riportata testualmente nella tabella «Registro dei file» del documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: | File | Area | Finalita | Formato / peso | |--------------------------------------------|--------------|---------------------------------------------------------|------------------| | diag_5_2_graph_rag_structure.sv g | **Knowledge**| Struttura del grafo e pipeline Graph RAG. | SVG 11.2 KB |
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «Registro dei file» → —

---

## pdf-diag-2

**Domanda:** Nel catalogo diagrammi, qual e' il formato e il peso di diag_0_3_modules_relations_map.svg?

**Risposta attesa:** SVG, 46.4 KB

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Nel catalogo diagrammi, per il file `diag_0_3_modules_relations_map.svg`: * **Formato:** SVG * **Peso:** 46.4 KB Questi dati sono riportati nel documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` nella sezione "Registro dei file".
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «Registro dei file» → —

### CANDIDATO (Docling)

```text
Nel catalogo diagrammi, il file **diag_0_3_modules_relations_map .svg** ha il formato **SVG** e un peso di **46.4 KB**.
```

Nessuna citazione fra virgolette nella risposta.

---

## pdf-diag-3

**Domanda:** Quale diagramma del catalogo documenta i checkpoint human-in-the-loop, e con quale peso?

**Risposta attesa:** diag_6_2_hitl_checkpoints.svg.svg, 19.5 KB

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` — rango baseline 3, rango candidato 5

### BASELINE (pypdf)

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato come artefatto di tipo **Governance**. Secondo il contesto fornito: 1. Il file `04_knowledge_informative/vibe_coding_workflow.md` (classe `[METHODOLOGY]`) definisce i checkpoint (`[REGOLA-HITL-01]` a `[REGOLA-HITL-05]`). 2. Il file `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` elenca il diagramma `diag_6_2_hitl_checkpoints.svg.svg` con la finalità: "Checkpoint human-in-the-loop e punti di controllo". 3. La classe del documento che definisce i checkpoint è `[METHODOLOGY]`. Il peso (Authority) attribuito a questo vincolo/diagramma deriva dalla classe della fonte più autorevole che lo enuncia o lo descrive: * Il documento `04_knowledge_informative/vibe_coding_workflow.md` contiene la definizione dei checkpoint e ha la classe **`[METHODOLOGY]`**. * Nel README.md, la classe `[METHODOLOGY]` ha un valore di Authority di **0.90**. Pertanto, il diagramma è associato al peso **0.90** (ereditato dalla classe `METHODOLOGY` della fonte che lo descrive).
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «Checkpoint human-in-the-loop e punti di controllo» → —

### CANDIDATO (Docling)

```text
Il diagramma che documenta i checkpoint human-in-the-loop è **`diag_6_2_hitl_checkpoints.svg.svg`**, classificato nell'area **Governance**. Tuttavia, il contesto fornito **non riporta un valore di Authority (peso)** specifico per questo file nel catalogo `catalogo_diagrammi_normativi.pdf`. La tabella elenca solo: * File * Area * Finalità * Formato / peso (che indica la dimensione in KB, es. 19.5 KB, non il coefficiente di autorità). Di conseguenza, **nessuna fonte più autorevole** (come `METADATA`, `METHODOLOGY` o `REQUIREMENTS`) stabilisce un valore numerico di Authority per questo artefatto visivo nel corpus fornito. Il peso deve essere dedotto esclusivamente dalla classe del documento che lo contiene se presente, ma in questo caso il file è elencato sotto la sezione **[SENZA CLASSE]** del catalogo (come indicato dall'intestazione `--- 02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf § Catalogo diagrammi [SENZA CLASSE] ---`), e non vi sono altre fonti che assegnano un coefficiente di autorità a questo specifico file SVG. Pertanto, il contesto **non riporta** un vincolo o un valore di Authority per `diag_6_2_hitl_checkpoints.svg.svg`.
```

Nessuna citazione fra virgolette nella risposta.

---

## pdf-diag-4

**Domanda:** Quanti artefatti contiene il catalogo diagrammi e quante cartelle sorgente dichiara?

**Risposta attesa:** 5 artefatti, 1 cartella sorgente

**Fonte attesa:** `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e **1 cartella sorgente**. I dati estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf` sono: * **Artefatti:** 5 (elencati nella riga "5 artefatti" e successivamente nel registro dei file). * **Cartelle sorgente:** 1 (elencato nella riga "1 cartella sorgente"). Il percorso della singola cartella sorgente dichiarata è: `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\diagrams`.
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «e successivamente nel registro dei file). * **Cartelle sorgente:** 1 (elencato nella riga» → —

### CANDIDATO (Docling)

```text
Il contesto riporta che il catalogo diagrammi contiene **5 artefatti** e dichiara **1 cartella sorgente**. Ecco i dati estratti testualmente dal documento `02_specs_normative/diagrams/catalogo_diagrammi_normativi.pdf`: * **Numero di artefatti:** "5 artefatti" (citato nella sezione "Indice operativo"). * **Numero di cartelle sorgente:** "1 cartella sorgente SVG formato" (citato nella sezione "Regole di organizzazione"). * **Percorso della cartella sorgente:** `C:\Users\Silve\Desktop\vibecraft\docs\02\_specs\_normative\diagrams`. I 5 artefatti elencati sono: 1. `diag_0_3_modules_relations_map .svg` 2. `diag_2_1_workflow_state_machin e.svg` 3. `diag_2_3_concurrency_pessimisti c_lock.svg` 4. `diag_5_2_graph_rag_structure.sv g` 5. `diag_6_2_hitl_checkpoints.svg.sv g`
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «(citato nella sezione» → —
- `unverifiable` «). * **Numero di cartelle sorgente:**» → —
- `unverifiable` «(citato nella sezione» → —

---

## pdf-mock-1

**Domanda:** Nel catalogo mockup, quale numero di specifica e quale area sono associati a mockup_2_4_notifications_templates.svg?

**Risposta attesa:** spec 2.4, area Manager

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **specifiche 2.4** e all'**area Manager**. Questa associazione è confermata dal registro dei file nel documento `[SENZA CLASSE]`: * **File:** `mockup_2_4_notifications_templates.svg` * **Spec.:** `2.4` * **Area:** `Manager` * **Schermata:** Gestione template di notifica. Il vincolo di naming `[REGOLA-01]` (usare `mockup_[spec]_[ruolo]_[schermata]`) e la classificazione del ruolo `Manager` sono coerenti con quanto riportato nel contesto.
```

Nessuna citazione fra virgolette nella risposta.

### CANDIDATO (Docling)

```text
Nel catalogo mockup, il file `mockup_2_4_notifications_templates.svg` è associato alla **Specifica 2.4** e all'**Area Manager**. Questa associazione è riportata testualmente nella tabella "Registro dei file" del documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`: * **File:** `mockup_2_4_notifications_templates.svg` * **Spec.:** `2.4` * **Area:** `Manager`
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «**Area Manager**. Questa associazione è riportata testualmente nella tabella» → —

---

## pdf-mock-2

**Domanda:** Qual e' l'unico file del registro mockup in formato HTML e quanto pesa?

**Risposta attesa:** mockup_3_5_admin_dashboard_analytics.html, 3.4 KB

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`: * **File:** `mockup_3_5_admin_dashboard_analytics.html` * **Peso:** `3.4 KB` Questo dato è estratto testualmente dal blocco `[SENZA CLASSE]` del documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`, nella sezione "Registro dei file", dove l'unico elemento con formato HTML è elencato con il peso specificato sopra. Nessun altro file HTML compare nel contesto fornito.
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «Registro dei file» → —

### CANDIDATO (Docling)

```text
Il contesto riporta esattamente un unico file nel registro dei mockup con estensione `.html`. **File identificato:** * `mockup_3_5_admin_dashboard_analytics.html` **Peso riportato:** * `HTML 3.4 KB` (formato e peso indicati nella tabella del documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf`).
```

Nessuna citazione fra virgolette nella risposta.

---

## pdf-mock-3

**Domanda:** Che cosa mostra la schermata mockup_1_5_employee_personal_area.svg e a quale area appartiene?

**Risposta attesa:** Area personale del dipendente; area Dipendente

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` — rango baseline 10, rango candidato 2

### BASELINE (pypdf)

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: * Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``; * Gestire i record in fase di compilazione non ancora trasmessi; * Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'interfaccia si presenta come uno spazio centralizzato per monitorare le proprie partecipazioni e i feedback forniti dai manager senza la necessità di ricaricare la pagina (Single Page Application UX). Questa schermata appartiene all'**Area Personale Dipendente**.
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «**Area Personale** (o» → —
- `verified` «) dedicata all» → 02_specs_normative/spec_area_pers_1.5.md
- `unverifiable` «esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L» → —

### CANDIDATO (Docling)

```text
La schermata **mockup_1_5_employee_personal_area.svg** mostra l'**Area Personale del dipendente** (o "Profilo Utente") dedicata all'`` `UTENTE` `` registrato all'interno del portale VibeCraft. Questa interfaccia garantisce trasparenza assoluta, consentendo al dipendente di: * Monitorare lo storico e lo stato corrente di tutte le sue istanze di `` `RICHIESTA` ``. * Gestire i record in fase di compilazione non ancora trasmessi. * Ricevere riscontri immediati sull'esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L'area appartiene alla specifica normativa relativa all'**Area Personale Dipendente** (specificata nel file `02_specs_normative/spec_area_pers_1.5.md`). Il mockup è classificato come artefatto SVG con peso 31.4 KB e fa parte del catalogo dei mockup normativi (`02_specs_normative/mockups/catalogo_mockup_normativi.pdf`), dove viene associato alla specifica **1.5** e all'area funzionale **Dipendente**.
```

Citazioni fra virgolette, verifica deterministica:

- `unverifiable` «**Area Personale del dipendente** (o» → —
- `verified` «) dedicata all» → 02_specs_normative/spec_area_pers_1.5.md
- `unverifiable` «esito delle operazioni tramite un sistema standardizzato di notifiche popup (Toast). L» → —

---

## pdf-mock-4

**Domanda:** Quanti artefatti e quante aree funzionali dichiara il catalogo mockup, e in quali formati?

**Risposta attesa:** 11 artefatti, 4 aree funzionali, formati SVG + HTML

**Fonte attesa:** `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` — rango baseline 1, rango candidato 1

### BASELINE (pypdf)

```text
Il contesto riporta che il documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: * **Artefatti:** 11 * **Aree funzionali:** 4 * **Formati:** SVG e HTML Ecco il dettaglio degli artefatti elencati nel registro dei file del documento citato: | File | Spec. | Area | Schermata | Formato / peso | |---|---|---|---|---| | mockup_1_1_auth_login.svg | 1.1 | Autenticazione | Schermata di accesso. | SVG (21.3 KB) | | mockup_1_2_employee_dashboard.svg | 1.2 | Dipendente | Dashboard operativa del dipendente. | SVG (30.0 KB) | | mockup_1_3_event_details.svg | 1.3 | Dipendente | Dettaglio di un evento o una prenotazione. | SVG (18.4 KB) | | mockup_1_4_reservation_form.svg | 1.4 | Dipendente | Form di inserimento prenotazione. | SVG (23.4 KB) | | mockup_1_5_employee_personal_area.svg | 1.5 | Dipendente | Area personale del dipendente. | SVG (31.4 KB) | | mockup_2_2_manager_approval_queue.svg | 2.2 | Manager | Coda di approvazione del responsabile. | SVG (25.9 KB) | | mockup_2_4_notifications_templates.svg | 2.4 | Manager | Gestione template di notifica. | SVG (18.6 KB) | | mockup_3_2_admin_crud_events.svg | 3.2 | Admin | Gestione CRUD degli eventi. | SVG (27.4 KB) | | mockup_3_3_admin_global_monitor.svg | 3.3 | Admin | Monitoraggio globale amministrativo. | SVG (24.6 KB) | | mockup_3_4_admin_export_modal.svg | 3.4 | Admin | Finestra di esportazione dati. | SVG (12.2 KB) | | mockup_3_5_admin_dashboard_analytics.html | 3.5 | Admin | Dashboard analytics amministrativa. | HTML (3.4 KB) | **Nota sulla divergenza:** Il documento `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` elenca solo file con estensione `.svg` e un unico file `.html`. Tuttavia, la specifica `02_specs_normative/spec_area_pers_1.5.md` (classe `[REQUIREMENTS]`) menziona l'uso di HTML per i prototipi navigabili in generale, ma il catalogo specifico elenca solo questi 11 artefatti misti (10 SVG + 1 HTML). Non ci sono divergenze sui nomi dei file o sui formati tra le fonti citate nel contesto fornito.
```

Nessuna citazione fra virgolette nella risposta.

### CANDIDATO (Docling)

```text
Il contesto riporta che il file `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) dichiara esplicitamente: - **11 artefatti** - **4 aree funzionali** SVG + HTML formati. I dettagli specifici estratti dal contesto sono: | File | Area | Formato / peso | |---|---|---| | mockup_1_1_auth_login.svg | Autenticazione | SVG 21.3 KB | | mockup_1_2_employee_dashboard.svg | Dipendente | SVG 30.0 KB | | mockup_1_3_event_details.svg | Dipendente | SVG 18.4 KB | | mockup_1_4_reservation_form.svg | Dipendente | SVG 23.4 KB | | mockup_1_5_employee_personal_area.svg | Dipendente | SVG 31.4 KB | | mockup_2_2_manager_approval_queue.svg | Manager | SVG 25.9 KB | | mockup_2_4_notification_templates.svg | Manager | SVG 18.6 KB | | mockup_3_2_admin_crud_events.svg | Admin | SVG 27.4 KB | | mockup_3_3_admin_global_monitor.svg | Admin | SVG 24.6 KB | | mockup_3_4_admin_export_modal.svg | Admin | SVG 12.2 KB | | mockup_3_5_admin_dashboard_analytics.html | Admin | HTML 3.4 KB | **Nota sulla divergenza tra documento e codice:** Il contesto contiene anche il blocco `02_specs_normative/mockups/catalogo_mockup_normativi.pdf` (classe `[SENZA CLASSE]`) che elenca i file con nomi leggermente diversi rispetto alla tabella del testo (es. `mockup_1_5_employee_person al_area.svg` vs `mockup_1_5_employee_personal_area.svg`, `mockup_2_2_manager_approva l_queue.svg` vs `mockup_2_2_manager_approval_queue.svg`). Poiché il documento PDF è la fonte primaria per il catalogo, i nomi esatti dei file sono quelli riportati nella tabella del testo (con spaziature corrette), mentre le differenze di formattazione (spazi mancanti o errati) nel nome del file nel contesto indicano una discrepanza tra la rappresentazione testuale e il contenuto reale del file sorgente. Tuttavia, i vincoli tecnici (formati SVG/HTML, aree funzionali) sono coerenti in entrambe le fonti. **Vincoli estratti:** - **Regola di Naming**: Usa `mockup_[spec]_[ruolo]_[schermata]` (da `[SENZA CLASSE]`). - **Regole di organizzazione**: Raggruppa per `Dipendente`, `Manager` e `Admin`; mantieni SVG come riferimento statico e HTML per prototipi navigabili (da `[SENZA CLASSE]`). - **Tracciabilità**: Ogni modifica a un 
```

Nessuna citazione fra virgolette nella risposta.

---
