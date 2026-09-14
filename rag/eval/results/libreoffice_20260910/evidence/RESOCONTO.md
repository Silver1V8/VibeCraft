# Revisione finale, cataloghi in staging ed esperimento LibreOffice — 2026-09-10

Ramo `codex/docling-intake`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74` (invariato: nessun
commit, push, merge o deploy). `AGENTS.md` assente: cercato nel repository, nei sottoalberi e
nelle tre directory superiori, non creato. Modifiche preesistenti del manutentore e della sessione
precedente conservate; i 18 non-Markdown rimossi da `docs/` non sono stati ripristinati.

Riferimenti della sessione precedente **verificati, non rieseguiti**: il log
`verifica_finale_20260910/suite_finale_2.log` chiude con `1408 passed` e `exit=0`; `CURRENT` =
`v20260910T121150`, alias `vibecraft_events` → `vibecraft_events__v20260910T121150`, 248 punti
(contati ora su Qdrant). La suite di questa sessione è in §6.

Tre stati distinti, da non confondere:
- **PASS tecnico**: codice, test, container e flusso UI verificati (§6);
- **revisione umana dei cataloghi: ancora necessaria** (§3), nessuna approvazione eseguita;
- **integrazione su `main`: non eseguita**, CI GitHub mai lanciata.

## 1. Revisione del diff: problemi trovati e correzioni

Revisionati il codice effettivo e i chiamanti (non i soli resoconti): `core/intake.py`,
`core/intake_convert.py`, `core/intake_clean.py`, `core/intake_refine.py`, `core/indexing.py`,
`core/retrieval.py`, `api/routes_intake.py`, `api/routes_retrieval.py`, `core/config.py`,
`rag_config.yaml`, template, Dockerfile, CI, `pyproject.toml`. Ogni difetto è riprodotto prima
della correzione; la correzione sta nel punto condiviso.

| # | gravità | dove | scenario | conseguenza | correzione e test |
|---|---|---|---|---|---|
| 1 | **media** | `core/intake.py::_append_journal` (e scritture dirette in `intake_refine.py`, `doc_generation.py`) | uno stage che termina mentre un approve, un reject, una raffinazione o una generazione scrive il journal: su Windows due handle in append si sovrascrivono (misurato: 8 thread × 400 righe → 2.379–2.413 righe su 3.200, alcune corrotte) | riga `approved` persa → documento pubblicato che resta «staged» e non si può più approvare (409) né pulire; riga `staged` persa → file orfani con upload dichiarato riuscito | unico punto di scrittura con lock di processo + lock OS su `intake.jsonl.lock` (ordine fisso writer lock → journal); refine e generazione passano da lì. `test_append_concorrenti_al_journal_non_perdono_righe` |
| 2 | media-bassa | `core/intake_convert.py::_convert_xlsx_docling` | XLSX scritto da un programma (formule senza risultato memorizzato) | cella del totale vuota nel Markdown **senza alcun avviso** | conteggio delle formule senza valore memorizzato → avviso in preview; nessun ricalcolo. Test rafforzato + `test_xlsx_formula_con_valore_memorizzato_nessun_avviso` |
| 3 | bassa | `convert_to_markdown`, controllo del contenitore | DOCX/XLSX/PPTX protetti da password (Office li cifra in un contenitore OLE `EncryptedPackage`) | messaggio «file danneggiato o non è un DOCX valido» | messaggio «protetto da password (cifrato)». Test su fixture reale di Excel 16 (`protetto.xlsx`), 3 formati |
| 4 | media (contenuto) | `tmp/pdfs/build_file_catalogs.py` | nomi di file e aree più larghi della colonna fissa | Markdown dei cataloghi con identificatori spezzati («diag_0_3_modules_relations_map .svg», «Autenticazion e»): non si ritrovano | larghezza della colonna calcolata dal testo più lungo. `test_nomi_e_aree_reali_non_spezzati_a_meta` |
| 5 | media (contenuto) | stesso generatore, banda KPI | due celle vicine lette come un paragrafo | «1 cartella sorgente SVG formato»: associazione valore-etichetta ambigua | forma «Etichetta: valore» per ogni cella (le attese dei test sono aggiornate a questa forma, non allentate) |
| 6 | **alta per il significato** | stesso generatore | sorgente fuori dal corpus (backup R.0) | «Percorso sorgente» presentava il backup come collocazione delle risorse | vedi §3 |

Controllato e **non** difettoso:
- **S2** (`retrieval.filter_linked_code_by_question`): a 0.0 la route non la invoca (guardia
  `> 0`); a soglia attiva riusa `search_code_symbols` con `subset_idx` e `max_per_file=0` (pool
  = tutti i candidati), conserva l'ordine del ponte e tiene i simboli senza vettore o senza matrice.
- **Manifest incrementale**: con `changed_paths` scrive voci precedenti meno le cancellazioni
  elaborate più nuovi/modificati elaborati; una cancellazione non elaborata resta visibile come
  stale. Limite preesistente, non introdotto: un documento saltato per corpo vuoto viene
  registrato come indicizzato (come prima).
- **approve/reject/refine**: ricontrollo dello stato sotto writer lock, creazione esclusiva,
  rollback solo del file posseduto; preview senza lock ma con errore tipizzato se un reject
  sposta il file nel frattempo.

Limiti rilevati e **non** corretti (serve una decisione, non un bugfix):
- **XLSX, riga con celle vuote intermedie** (es. `Totale | vuoto | 10 | vuoto | 1500.5 | 2401`):
  Docling la divide in tabelle da una cella, e l'associazione del totale va persa. L'opzione
  `gap_tolerance=1` la ricompone, ma fonde nella prima tabella una seconda tabella separata da una
  riga vuota e ne scambia le intestazioni (misurato su `formati2/registro.xlsx`): scambia un
  difetto con un altro, quindi non l'ho adottata. MarkItDown conserva la riga ma altera i dati.
- Date XLSX/XLS con `00:00:00` (Docling e MarkItDown).
- `approve` scrive con `open("x")`: un crash a metà scrittura lascerebbe un file parziale
  (finestra minima, sotto writer lock).

## 2. Dipendenze, Docker, CI

Pin, lock, torchvision e Docker CPU come nella sessione precedente (verificati in lettura).
Novità di questa sessione: LibreOffice nel runtime Docker (§5) e in CI (§6). `olefile`, usato per
validare i binari legacy, arriva da `markitdown[...,outlook]==0.1.7`, già nelle dipendenze.

## 3. I due cataloghi in staging

**Stato iniziale**: `70c581550d3e` (`catalogo_diagrammi_normativi.pdf`) e `b180d8adb347`
(`catalogo_mockup_normativi.pdf`), staged, Docling senza avvisi. «Percorso sorgente» indicava
`C:\Users\Silve\Desktop\vibecraft-docs-backup-20260910-100353\…`. Gli originali del 7 settembre
indicavano invece `C:\Users\Silve\Desktop\vibecraft\docs\02_specs_normative\…`, oggi vuoto.

**Dove stanno davvero le risorse** (SHA-256 confrontati file per file, 5 SVG + 10 SVG + 1 HTML):
- non in `docs/` (nessun documento del corpus cita `diagrams/` o `mockups/`), né nel repository;
- nel backup R.0;
- in due copie **fuori dal repository e mai referenziate**, identiche per SHA:
  `C:\Users\Silve\Desktop\VibecraftProtocollo\{diagrams,mockups}` (cartella di un altro progetto,
  file del 7 settembre) e
  `C:\Users\Silve\Desktop\project-work-di-vibe-coding-2-main-docs\…\docs\02_specs_normative\…`
  (estrazione del 28 luglio).

Non c'è quindi una destinazione corrente e stabile nota all'applicazione. Non ho inventato una
collocazione e non ho scelto io una delle due copie: i cataloghi sono ora **esplicitamente storici**.

**Correzione alla fonte** (`tmp/pdfs/build_file_catalogs.py`), regola automatica: se la cartella
sorgente è fuori da `docs/`, allora titolo «… (storico)», un paragrafo «Inventario storico: le
risorse elencate non sono nel corpus corrente (docs/)…» e la sezione «Provenienza» al posto di
«Percorso sorgente»: «Copia conservata, non una collocazione corrente (…): <backup>». La
provenienza sta anche nel campo Subject dei metadati PDF dell'originale conservato in staging.
Con la sorgente dentro `docs/` il catalogo resta «corrente» con «Percorso sorgente». Test:
12/12 (`uv run --no-project --with reportlab==5.0.1 --with pypdf --with pypdfium2 --with pytest
python -m pytest tmp/pdfs/test_build_file_catalogs.py`), fra cui storico/corrente e nomi reali
non spezzati.

**Ciclo di vita dell'app** (nessuna modifica manuale a file o journal):
1. rigenerati da `…backup…\02_specs_normative` in `output/pdf/` (SHA `064ad61b…a61d`, `60403ffc…c58a`);
2. messi in staging con `core.intake.stage_document`, lo stesso codice dell'upload:
   **`07aefc94ceea`** (diagrammi) e **`9f6505d3cf48`** (mockup), Docling, nessun ripiego, nessun avviso;
3. `70c581550d3e` e `b180d8adb347` **rifiutati** con motivo «Sostituito da … Rifiuto tecnico
   della versione superata, non una decisione di review sul contenuto»: file conservati in
   `staging/rejected/`.

**Verifiche sul Markdown in staging**: artefatti 5 e 11 = righe del registro; cartelle 1; formati
«SVG» e «SVG + HTML»; aree funzionali 4 (Autenticazione compresa, non i 3 ruoli); il catalogo non
censisce sé stesso; titoli `##`/`###`/`####` coerenti; tabella regole 3×2 e registro 5×4 / 11×5
intatti; 16 nomi di file e 5 aree integri; pesi invariati rispetto agli originali; nessun link
(il catalogo non ne conteneva). Residuo del testo sorgente: «prefisso diag_ , seguito» (spazio
davanti alla virgola dal grassetto del template; testo invariato, non ne ho cambiato lo stile).

**Proposta per la revisione umana** (non eseguita):
- se il catalogo storico serve al corpus, approvare `07aefc94ceea` e `9f6505d3cf48`, per esempio in
  `03_changes_historical` (classe METADATA), con nomi `catalogo_diagrammi_storico` e
  `catalogo_mockup_storico`: la categoria dice che non sono norme vigenti;
- se le risorse torneranno nel corpus, decidere prima dove (gli SVG non sono un formato
  dell'intake), poi rigenerare con `--source` su quella cartella: il catalogo diventa «corrente»
  da solo;
- altrimenti rifiutarli: il contenuto resta nel backup R.0.

## 4. Esperimento LibreOffice

### Che cosa fa davvero Docling 2.126.0 con LibreOffice

Letto nel pacchetto installato (`docling/backend/docx/drawingml/utils.py`) e confermato dalla
documentazione ufficiale («Legacy binary Office formats (97–2004); requires LibreOffice»):
- **DOC, XLS, PPT**: i backend Word/Excel/PowerPoint chiamano `convert_to_modern_format`, che fa
  `soffice --headless --convert-to docx|xlsx|pptx` con un profilo temporaneo **vuoto, cioè coi
  default**, timeout 120 s, nessuna opzione su macro o collegamenti;
- **DOCX, XLSX, PPTX**: LibreOffice serve solo per rasterizzare forme DrawingML, immagini EMF/WMF
  e grafici (`render_chart_images`, spento). Tutto finisce in immagini che il nostro export non
  include. **Misurato**: l'uscita di Docling su DOCX/XLSX/PPTX è identica byte per byte con e
  senza LibreOffice installato (10/10 file). Installarlo non migliora Docling sui formati moderni.

### Ambiente, campioni, criteri

- Container sperimentale `vibecraft-lo-esperimento:20260910` = immagine CPU del working tree +
  `libreoffice-{writer,calc,impress}-nogui` (LibreOffice 25.2.3.2), sempre `--network none`,
  `core/` e configurazione montati in sola lettura (A è il percorso applicativo vero). Nessuna
  installazione né associazione di file sull'host.
- Fixture in `fixture/`, generate da `scripts/fixture.py` (python-docx, openpyxl, python-pptx),
  poi aperte e salvate da **Word, Excel e PowerPoint 16** (`scripts/office_legacy.ps1`): DOC,
  XLS e PPT sono veri binari OLE (stream `WordDocument`, `Workbook`, `PowerPoint Document`,
  applicazione creatrice Microsoft), **non** prodotti da LibreOffice, quindi nessun vantaggio da
  round trip. Nota a piè di pagina aggiunta da Word; varianti protette da password da Office.
- Campioni reali: `SOLVSAMP.XLS` e `PROTTPLN.DOC/PPT/XLS` distribuiti con Office (copiati fuori
  dal repository; salvate solo le metriche). I documenti personali trovati sul Desktop **non**
  sono stati usati.
- Attese **scritte prima** delle misure in `scripts/attese.py`: Word 14 controlli (gerarchia,
  paragrafi, liste, tabella, coppie campo-valore, cella unita, link, accenti, nota, duplicazioni);
  Excel 14 (fogli, cella unita una volta, intestazioni, zeri iniziali, NA/N/A/null, interi, date,
  seriali, decimali, percentuali, valori memorizzati delle formule letti con openpyxl/xlrd
  **prima** della conversione, accenti, NaN/None/Unnamed); PowerPoint 8 (titoli, ordine, testo,
  sottolivello, tabella, ordine di lettura, note, duplicazioni). Più validità del Markdown
  (colonne coerenti, separatore, niente HTML, righe duplicate). Nessun LLM come giudice.
- Varianti: **A** routing corrente; **B** Docling diretto (per i legacy = LibreOffice interno di
  Docling); **C** LibreOffice blindato → formato moderno → Docling; **D** LibreOffice blindato →
  formato moderno → MarkItDown. Mai via PDF.
- Profilo blindato (chiavi e default letti da `main.xcd` installato): `DisableMacrosExecution`
  true, `MacroSecurityLevel` 3, link di Calc 1 = mai, link di Writer 2 = mai, campi Writer non
  aggiornati, `OOXMLRecalcMode`/`ODFRecalcMode` 1 = nessun ricalcolo, `BlockUntrustedRefererLinks`
  true. Profilo nuovo per ogni esecuzione, cartella rimossa, gruppo di processi ucciso al timeout.

### Risultati (controlli superati; `err` = formato non ammesso dal routing corrente)

| file (produttore) | A corrente | B Docling | C LO→Docling | D LO→MarkItDown |
|---|---|---|---|---|
| manuale.docx (Word) | 12/14 | 11/14 | 12/14 | 12/14 |
| manuale.doc (Word) | err | 11/14 | 11/14 | **12/14** |
| specifica_word.docx | 4/4 | 3/4 | 3/4 | 4/4 |
| specifica_word.doc | err | 3/4 | 3/4 | **4/4** |
| registro.xlsx (openpyxl) | 12/14 | 12/14 | 12/14 | 10/14 |
| registro_excel.xlsx (Excel) | 12/14 | 12/14 | 12/14 | 11/14 |
| registro.xls (Excel) | 11/14 | 12/14 | **12/14** | 11/14 |
| rilascio.pptx | 7/8 | 6/8 | 6/8 | 7/8 |
| rilascio_pp.pptx (PowerPoint) | 7/8 | 6/8 | 6/8 | 7/8 |
| rilascio.ppt (PowerPoint) | err | 6/8 | 6/8 | **7/8** |

Che cosa c'è dietro i numeri:
- **DOCX**: MarkItDown (A, D) tiene la nota a piè di pagina ma tratta il titolo in stile Title
  come testo; Docling (C) ricostruisce la gerarchia ma perde la nota, ripete la cella unita
  («Periodo | Periodo») e attacca una tabella alla riga di elenco precedente. Nessuna variante
  domina: resta A. Tutte appiattiscono la lista annidata di python-docx.
- **DOC**: D produce lo **stesso Markdown** di A sul DOCX equivalente (a meno dell'id della nota).
- **XLSX**: C = A (stesso motore); D altera i dati (pandas). Il fallimento comune «valori
  memorizzati» è la frammentazione della riga Totale descritta in §1. Nessun ricalcolo: con
  `registro.xlsx` C legge 999 (memorizzato, obsoleto), non 10.
- **XLS**: A svuota NA/N/A/null, scrive `NaN` e `Unnamed: 1`; C conserva i letterali e i nomi dei
  fogli. `SOLVSAMP.XLS`: copertura dei testi di cella (xlrd) 0,978 in A (4.822 «NaN», 78
  «Unnamed»), **1,000 in C**; `PROTTPLN.XLS` 1,000 in entrambi.
- **PPTX/PPT**: MarkItDown conserva le note del relatore, Docling no. D sul PPT = A sul PPTX.
  `PROTTPLN.PPT` reale: **B fallisce**, C e D convertono.

**File problematici** (errore chiaro = eccezione con messaggio, nessun documento):
- vuoti: A errore ovunque; D converte XLS/PPT/XLSX/PPTX vuoti in «## Sheet1 |» o in una slide
  vuota. Nell'app il controllo «file vuoto» viene prima.
- **troncati** (intestazione OLE intatta): DOC e PPT danno errore in tutte le varianti; l'**XLS
  troncato viene convertito in byte spazzatura da B, C e D** (LibreOffice lo apre come testo).
  Da qui la validazione dello stream OLE prima di invocare LibreOffice.
- rinominati (DOCX chiamato `.doc`, XLSX chiamato `.xls`): LibreOffice e Docling li convertono;
  il routing lo rifiuta come l'XLS di oggi.
- protetti da password (DOC/XLS/PPT e DOCX/XLSX/PPTX): errore in ~1,1 s in tutte le varianti,
  nessun blocco, nessun processo residuo.

**Rete** (sonda HTTP sul loopback del container): DOCX con immagine collegata a
`http://127.0.0.1:8765/…` → **2 richieste GET col profilo predefinito**, 0 col profilo blindato;
XLSX con `WEBSERVICE` e collegamento esterno → 0 in entrambi. Il profilo predefinito è quello di B.

**Costi**: LibreOffice 1,29 s mediani per file (max 1,85 s; a freddo 1,9 s), picco RSS 231 MB
mediani (max 267 MB), 0 processi residui dopo ogni conversione e a fine corsa. MarkItDown/Docling
sui formati Office: 0,01–0,4 s. Immagine CPU: layer LibreOffice di **443 MB** non compressi
(1.512 → 1.671 MB nella misura di `docker image inspect`).

**Riproducibilità**: due container nuovi, stessi 40 Markdown **byte per byte** (LF, nessun CR);
ogni variante stabile su 3 ripetizioni nello stesso processo.

Artefatti: `fixture/` (con SHA in `out_lo_1/risultati.json`), `out_lo_1/`, `out_lo_2/`,
`out_base/` (immagine senza LibreOffice), `scripts/`, `docker/Dockerfile`. Comandi:

```
uv run --no-sync python -B eval/results/libreoffice_20260910/scripts/fixture.py eval/results/libreoffice_20260910/fixture
pwsh -File eval/results/libreoffice_20260910/scripts/office_legacy.ps1 eval/results/libreoffice_20260910/fixture
docker build -t vibecraft-lo-esperimento:20260910 eval/results/libreoffice_20260910/docker
docker run --rm --network none -v <rag>/core:/app/rag/core:ro -v <rag>/rag_config.yaml:/app/rag/rag_config.yaml:ro \
  -v <exp>/scripts:/esp/scripts:ro -v <exp>/fixture:/esp/fixture:ro -v <exp>/out_lo_1:/esp/out -v <campioni>:/esp/campioni:ro \
  vibecraft-lo-esperimento:20260910 python -B /esp/scripts/esperimento.py /esp/fixture /esp/out --campioni /esp/campioni
```

## 5. Decisione sul routing

| formato | baseline | miglior candidato | vantaggi | regressioni | costo | verdetto |
|---|---|---|---|---|---|---|
| DOCX | MarkItDown | — | nessuno: C scambia nota e cella unita con la gerarchia | — | — | **invariato** |
| XLSX | Docling | — | C = A | — | — | **invariato** |
| PPTX | MarkItDown | — | D = A | — | — | **invariato** |
| DOC | non ammesso (415) | **D**: LO blindato → DOCX → MarkItDown | supporto nuovo, = DOCX attuale (12/14, nota compresa) | — | ~1,3 s, 230 MB | **adottato** |
| XLS | MarkItDown | **C**: LO blindato → XLSX → Docling | letterali NA/N/A/null, niente NaN/Unnamed, fogli; SOLVSAMP 0,978 → 1,000 | riga Totale frammentata (come XLSX oggi) | ~1,2 s, 230 MB | **adottato** |
| PPT | non ammesso (415) | **D**: LO blindato → PPTX → MarkItDown | supporto nuovo, = PPTX attuale (note comprese) | — | ~1,2 s, 230 MB | **adottato** |

Regola unica e la più semplice: **LibreOffice solo per DOC, XLS e PPT**, per portarli al formato
moderno; poi decide la riga del formato moderno. Un solo convertitore in più, e solo sui file
legacy. Mai il LibreOffice interno di Docling (profilo predefinito: rete; PPT reale fallito).

Implementazione (`core/intake_convert.py`): `LEGACY_FORMATS`; validazione dello stream OLE prima
di LibreOffice (`_check_ole`); `_normalize_legacy` su una copia in una cartella temporanea,
profilo blindato nuovo per ogni conversione, albero di processi terminato al timeout
(`killpg` su POSIX, `taskkill /T` su Windows). `intake.libreoffice: {enabled, command,
timeout_seconds: 120}`; `doc` e `ppt` aggiunti a `allowed_formats`. Senza LibreOffice: l'XLS
ripiega su MarkItDown **dichiarandolo** (`fallback.da = "libreoffice"` e avviso), DOC e PPT danno
un errore che suggerisce di salvare come DOCX/PPTX. Metadati additivi: `normalizzazione:
{motore, versione, da, a}`, anche nel campo `intake` del frontmatter; `formato` e `sha256`
restano quelli dell'originale, conservato in staging come `.src.doc|xls|ppt`. In `docs/` entra
solo il `.md`. UI: formati, testo della pagina, etichetta del motore con la normalizzazione e
riga «Normalizzazione» nella preview. Dockerfile runtime: `libreoffice-{writer,calc,impress}-nogui`.
CI: stessi pacchetti nel job `test` con `VIBECRAFT_REQUIRE_LIBREOFFICE=1`; il job `docker`
converte DOC, XLS e PPT reali nell'immagine. Corpus esistente non migrato.

## 6. Verifiche

| verifica | esito |
|---|---|
| suite completa, host Windows, `VIBECRAFT_REQUIRE_QDRANT=1`, `VIBECRAFT_REQUIRE_DOCLING=1` | **1427 test: 0 falliti, 0 errori, 5 saltati** (JUnit `scratchpad/suite_2.xml`, `exit=0`); i 5 saltati sono i test con LibreOffice vero, non installabile sull'host |
| `tests/test_intake_libreoffice.py` nel container con LibreOffice, `VIBECRAFT_REQUIRE_LIBREOFFICE=1`, `--network none` | **14/14 passati**, nessuno saltato |
| immagine `vibecraft:cpu-20260910` costruita dal working tree | DOC→markitdown, XLS→docling, PPT→markitdown con normalizzazione, PDF con Docling, XLSX e XLS protetti: errore chiaro |
| generatore cataloghi | 12/12 |
| ruff | pulito su `core`, `tests`, script nuovi e generatore; restano i 43 riscontri preesistenti degli script sperimentali (`pilot_docling_*`, `implementazione_migliorie_20260910/scripts`) |
| golden/multihop/integrità | **non rieseguiti**: retrieval e indicizzazione non toccati in questa sessione |
| CI GitHub | **non eseguita** (nessun push); YAML modificato in locale |

Nota sulla prima corsa della suite: il log non conteneva la riga finale di pytest; l'ho rieseguita
registrando exit code e JUnit invece di dedurne l'esito.

**Flusso UI in sandbox**. Immagine `vibecraft:cpu-20260910`; rete, Qdrant, `docs/` (3 documenti
copiati) e `database/` dedicati; indice costruito nell'immagine. Nel container, un inoltro TCP
(`ui/proxy.py`) tiene il server sul loopback come nell'uso reale: senza, la porta pubblicata da
Docker arriva dal gateway e la UI senza chiave riceve 401.
- **Selezione dei file, unico passo simulato**: il pannello Browser non pilota il selettore
  nativo e Claude in Chrome non aveva browser collegati. I 5 file sono stati assegnati all'input
  `#file-input` della pagina, con lo stesso evento `change` di una scelta manuale.
- **Upload**: DOC, XLS e PPT in staging, con etichette come «DOC portato a DOCX da LibreOffice
  25.2.3.2, poi convertito con MarkItDown 0.1.7» (XLS «… con Docling 2.126.0»). `troncato.xls` →
  «file danneggiato o non è un XLS valido»; `protetto.xlsx` → «file protetto da password
  (cifrato)». `docs/` invariato.
- **Clic reali**:
  - Anteprima del PPT: riquadro «Conversione» con normalizzazione PPT→PPTX e SHA-256
    dell'originale, note del relatore nel Markdown. Motivo digitato, poi «Rifiuta»: journal
    `rejected` col motivo, file in `staging/rejected/`, `docs/` invariato.
  - Anteprima del DOC, poi «Approva» (nome proposto `legacy.md`, categoria 04): in `docs/` entra
    **solo** `04_knowledge_informative/legacy.md`. Il frontmatter riporta `formato: doc`, lo
    SHA-256 dell'originale e `normalizzazione` (libreoffice, doc→docx); l'originale resta in
    staging. `CURRENT` promosso a `v20260910T134152`; 3 punti Qdrant del documento (19 → 22).
  - Anteprima dell'XLS: NA/N/A/null e il foglio «Contatti città» presenti; riga Totale
    frammentata (limite in §1).
- Gli screenshot del pannello escono neri su questa pagina (difetto di cattura): le prove sono i
  testi letti dalla pagina e lo stato lato server.

**Stato reale dopo tutte le prove**, confrontato con la fotografia iniziale: `docs/` invariato
(42 file, SHA-256), `CURRENT` = `v20260910T121150`, 7 versioni con hash invariato, alias
`vibecraft_events` → `vibecraft_events__v20260910T121150` e 248 punti invariati, `history.jsonl`
invariato. Nel journal di staging solo le 4 righe dei cataloghi (§3). Risorse della sandbox
rimosse (container, rete, volume). Restano le immagini `vibecraft:cpu-20260910` e
`vibecraft-lo-esperimento:20260910`, eliminabili con `docker rmi`.

## 7. Limiti, rollback, file

**Limiti**: DOCX resta ambiguo; XLSX/XLS con righe dai vuoti intermedi frammentate e date con
`00:00:00`; la nota a piè di pagina si perde nei percorsi Docling (non adottati); MSG non
verificato; confidenze di layout Linux/Windows diverse; Linux aarch64, macOS e immagine GPU non
provati con LibreOffice; la protezione dalla rete dipende dal profilo (misurata su immagine
collegata, WEBSERVICE e collegamento esterno), non da un isolamento di rete del processo; i
campioni legacy sono pochi (4 prodotti da Office + 4 di Microsoft): il verdetto vale per questi.

**Rollback**:
- LibreOffice: `intake.libreoffice.enabled: false` → XLS torna su MarkItDown con avviso di
  ripiego, DOC/PPT errore esplicito; per non accettarli più, togliere `doc` e `ppt` da
  `allowed_formats`. Riavvio, nessuna reindicizzazione. Docker: togliere i tre pacchetti.
- Journal: la correzione è autonoma (`_append_journal`); annullarla riapre il difetto 1.
- Cataloghi: i superati sono in `staging/rejected/` e il PDF è ricaricabile (un rifiutato si può
  rimettere in staging).

**File modificati in questa sessione**: `rag/core/intake.py`, `rag/core/intake_convert.py`,
`rag/core/intake_refine.py`, `rag/core/doc_generation.py`, `rag/core/config.py`,
`rag/rag_config.yaml`, `rag/templates/intake.unified.html`, `rag/README.md`, `Dockerfile`,
`.github/workflows/ci.yml`, `.gitignore`, `tmp/pdfs/build_file_catalogs.py`,
`tmp/pdfs/test_build_file_catalogs.py`, `rag/tests/test_intake_staging.py`,
`rag/tests/test_intake_docling.py`, nuovo `rag/tests/test_intake_libreoffice.py`, fixture nuove
`rag/tests/fixtures/intake/{legacy.doc,legacy.xls,legacy.ppt,protetto.xls,protetto.xlsx}`,
`rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`, questa cartella. Dati: journal di staging (2 stage,
2 reject), `output/pdf/` (cataloghi rigenerati).
