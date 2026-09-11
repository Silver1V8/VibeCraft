# Nota di implementazione — migliorie e bugfix emersi dal pilot Docling

## Excel per lettura diretta — 2026-09-11: PASS

Resoconto, prove, oracolo e rollback: `rag/eval/results/excel_diretto_20260911/RESOCONTO.md`.
Questa sezione prevale su quelle successive, compresa la «Fedeltà Excel» qui sotto.

- **Percorso**: XLSX → openpyxl 3.1.5, XLS → xlrd 2.0.2, entrambi sull'originale
  (`core/intake_excel.py`); nessuna normalizzazione LibreOffice per XLS, nessun ripiego.
  LibreOffice resta solo per DOC e PPT; PDF, DOCX e PPTX invariati.
- **Cause**: il candidato usava le colonne dell'intero foglio (tabelle affiancate fuse);
  Docling spezza le righe con celle vuote; LibreOffice arrotonda a 15 cifre i valori
  memorizzati degli XLS, trasforma i booleani in numeri e riscrive i formati: **149
  differenze** su SOLVSAMP rispetto all'originale letto da Excel 16, fra cui le 69 già note
  (55 valori arrotondati, 14 booleani; tutte formule) e 80 formati riscritti.
- **Contratto**: una sezione per foglio; intervalli di celle con coordinate (colonna vuota in
  tutto il foglio = separazione; riga vuota = nuovo blocco); valori memorizzati senza ricalcolo
  né formato; formati, celle unite, testo dall'aspetto tipizzato, commenti e collegamenti
  elencati; avvisi per formule, formule senza risultato e oggetti esclusi; limiti espliciti
  (2M celle nell'XML prima di caricare, 1M celle rappresentate).
- **Verifiche**: banco indipendente con riferimento Excel 16, 12/12 PASS in 4 processi (host e
  container) con Markdown byte-identici; gate di non-fusione della sessione precedente PASS senza
  modifiche; suite in container con LibreOffice, Docling e Qdrant obbligatori: 1449 passati, 0 falliti, 0 saltati.
  Corpus, staging, cataloghi e `CURRENT` invariati. CI GitHub non eseguita, nessun commit/push.
- **Limiti principali**: regola geometrica (un valore isolato nella colonna di separazione unisce
  due intervalli; una colonna vuota in tutto il foglio divide una tabella); formati non applicati;
  testo delle formule XLS non disponibile; ~1,1 GB a 990k celle. Cataloghi `07aefc94ceea` e
  `9f6505d3cf48`: revisione umana ancora necessaria, non approvati.

## Fedeltà Excel — 2026-09-11: NON_APPLICARE (superata dalla sezione precedente)

Resoconto, attese, output e log: `rag/eval/results/excel_fidelity_20260910/RESOCONTO.md`.
Questa sezione descrive il **candidato non committato nel working tree**, non un backend
approvato per il corpus, e prevale sulle matrici storiche successive.

- Causa riprodotta prima della modifica: Docling 2.126.0 segmenta per celle connesse e
  divide «Totale | vuoto | 10 | vuoto | 1500.5 | 2401» in tre tabelle. `gap_tolerance=1`
  fonde invece le due tabelle indipendenti del caso `formati2`: non adottato.
- Candidato: XLSX → openpyxl 3.1.5; XLS → LibreOffice → XLSX → stesso serializzatore.
  Coordinate e celle vuote esplicite; nessun ricalcolo, nessuna deduzione dei valori,
  cache obsolete preservate e formule senza cache segnalate. Preview e metadati coerenti.
- **NON_APPLICARE**: conserva la riga problematica, ma riunisce tabelle affiancate in una
  griglia unica; il nuovo gate rigoroso lo respinge. Inoltre SOLVSAMP.XLS presenta 69
  differenze originate già in LibreOffice (55 numeriche, 14 booleani True → 1). Nessuna
  tolleranza aggiunta per trasformare questi risultati in PASS.
- Verifiche: suite finale isolata CPU con LibreOffice, Docling e Qdrant dedicato obbligatori:
  **1438 passati, zero skip**; preview testata con le funzioni JavaScript effettive; due
  processi nuovi producono 10/10 Markdown byte-identici per baseline e candidato.
  Ruff dei file modificati pulito; `ruff check .` conserva 43 riscontri negli script storici.
  Suite verde e gate di fedeltà fallito sono esiti distinti.
- Corpus, CURRENT e staging: 56 hash invariati. Nessun commit, push, merge, deploy o
  riavvio dell'applicazione. CI remota non eseguita: queste modifiche non sono disponibili
  sul remoto. Cataloghi `07aefc94ceea` e `9f6505d3cf48` invariati, review umana separata.
- Rollback del candidato: ripristinare soltanto i contributi di questa sessione, usando
  `intake_convert.before.txt` per il convertitore e le aspettative/CI/UI corrispondenti;
  non resettare il working tree preesistente. Il flag Docling non disattiva più XLSX
  nel candidato. Dettagli e limiti nel resoconto.

## Revisione finale, cataloghi e LibreOffice — 2026-09-10 (sera)

Resoconto completo, prove, script e comandi: `rag/eval/results/libreoffice_20260910/RESOCONTO.md`.
Questa sezione prevale sulle successive dove le contraddice (in particolare: XLS non è più su
MarkItDown quando LibreOffice è disponibile).

- **Difetti corretti** (riprodotti, poi corretti nel punto condiviso, con test):
  - append concorrenti al journal di staging perse su Windows: una riga `approved` persa
    lasciava in staging un documento già pubblicato. Ora un unico punto di scrittura con lock;
  - XLSX con formule senza valore memorizzato: la cella vuota ora ha un avviso;
  - DOCX/XLSX/PPTX protetti da password: ora «protetto da password», non più «danneggiato»;
  - generatore dei cataloghi: nomi e aree non più spezzati, KPI «Etichetta: valore», catalogo
    storico quando la sorgente è fuori da `docs/`.
- **Matrice dei motori**: DOC → LibreOffice → DOCX → MarkItDown; XLS → LibreOffice → XLSX →
  Docling; PPT → LibreOffice → PPTX → MarkItDown. DOCX, XLSX e PPTX invariati: LibreOffice non li
  migliora, e Docling produce byte identici con o senza LibreOffice installato.
  - LibreOffice gira con un profilo blindato nuovo per ogni file, su una copia, dopo aver validato
    lo stream OLE; al timeout si termina l'albero di processi.
  - Mai il LibreOffice interno di Docling: profilo predefinito, e misurato scarica le immagini
    collegate.
  - Senza LibreOffice: l'XLS ripiega su MarkItDown dichiarandolo; DOC e PPT danno un errore
    esplicito.
  - LibreOffice è nel runtime Docker (+443 MB) e in CI.
- **Cataloghi**: in staging **`07aefc94ceea`** e **`9f6505d3cf48`**, esplicitamente storici (le
  risorse esistono solo nel backup R.0 e in due copie fuori dal repository mai referenziate).
  Rifiutate con motivo tecnico le versioni superate `70c581550d3e` e `b180d8adb347`.
  **Revisione umana ancora necessaria**; proposta nel resoconto, §3.
- **Verifiche**:
  - suite: 1427 test, 0 falliti, 0 errori, 5 saltati (i test con LibreOffice vero, 14/14 nel
    container con requisito obbligatorio);
  - smoke dell'immagine CPU;
  - UI in sandbox con clic reali (solo la selezione dei file è simulata sull'input della pagina);
  - corpus, `CURRENT`, versioni, alias e punti reali invariati.

  Golden/multihop non rieseguiti: retrieval e indicizzazione non toccati.
- **Non fatto**: nessun commit, push, merge o deploy; CI GitHub mai eseguita; corpus esistente
  non migrato.

## Chiusura — 2026-09-10 (verifica finale)

Resoconto completo, prove e script: `rag/eval/results/verifica_finale_20260910/RESOCONTO.md`.
Questa sezione prevale su quella successiva dove la contraddice.

- **Matrice definitiva dei motori** (confronto per formato sugli stessi input, dopo il cleaner
  reale): MD nativo; **PDF e XLSX su Docling**; DOCX, PPTX, XLS, HTML/HTM, TXT, CSV, JSON,
  XML, EPUB, MSG su MarkItDown. XLSX passa a Docling perché MarkItDown (pandas) svuota le celle
  «NA»/«N/A»/«null» e scrive `7.0`/`NaN`; i nomi dei fogli si recuperano dall'albero del
  documento. DOCX resta su MarkItDown per esito ambiguo. MSG non verificato (nessuna fixture
  generabile in locale).
- **Difetti corretti** dopo averli riprodotti: `reject` e fine della raffinazione ora sotto
  writer lock con ricontrollo dello stato; il reindex ristretto dell'approve **non dimentica
  più le cancellazioni non elaborate** (prima: punti orfani invisibili a integrità e
  sincronizzazione); contenitori binari corrotti rifiutati invece che convertiti in byte
  grezzi; sintassi immagine conservata in TXT e nei blocchi di codice; immagini incorporate
  scartate da MarkItDown dichiarate; PDF protetto e timeout con messaggi espliciti; titolo del
  frontmatter dal titolo di livello più alto.
- **Linux**: la perdita del titolo di quarto livello era di conversione (immagine senza font);
  con `fonts-liberation` il Markdown della fixture è identico a Windows, le confidenze del
  layout no. Immagine CPU costruita e provata (import, pesi, PDF, OCR, XLSX, avvio).
- **CI**: Docling verificato davvero nei job `test` e `docker` (pesi in cache verificati per
  SHA-256, `VIBECRAFT_REQUIRE_DOCLING=1`). Configurata, non eseguita su GitHub.
- **S2 sulle risposte**: 21/21 a 0.0 e a 0.35 sull'holdout (non più inedito); soglia 0.35 confermata.
- **Indice riallineato** al corpus reale dopo backup verificato: full rebuild `v20260910T121150`,
  integrità non stale, i due cataloghi PDF rimossi dal manutentore non sono più nell'indice;
  versione di ritorno `v20260908T132451` intatta. I cataloghi rigenerati sono in staging, in
  attesa di approvazione del manutentore.

## Esito dell'implementazione — 2026-09-10

Ramo `codex/docling-intake`, creato da `codex/evoluzione-p0` a HEAD
`011e264c554895c651f0eba1dccb74bc4dc10f74` conservando tutte le modifiche preesistenti.
Nessun commit, push o PR. `AGENTS.md` assente. Prove, script e log in
`rag/eval/results/implementazione_migliorie_20260910/`. Questa sezione descrive il
comportamento **realmente implementato** e prevale sugli esempi sperimentali più sotto.

### 1. S2 — pertinenza alla domanda sul ponte IMPLEMENTS: attiva a 0.35

- Codice: `core/retrieval.filter_linked_code_by_question` riusa `search_code_symbols` con
  `subset_idx` ristretto ai simboli del ponte; conserva l'ordine del ponte, tiene i simboli
  senza vettore denso (non valutabili) e, senza matrice del codice, non scarta nulla.
  `api/routes_retrieval.ask_rag` la chiama solo con soglia > 0 e registra gli scarti nel log.
- **Fallback del codice `0.0`** (`core/config.CODE_LINK_MIN_QUESTION_SCORE`); **valore
  effettivo del YAML `0.35`** (`retrieval.code_link_min_question_score`).
- Verifica sul corpus corrente, in-process e in sola lettura (niente lifespan, quindi niente
  riparazione dell'alias né GC), LLM sostituito da uno stub, confronto con la versione di
  HEAD di `routes_retrieval.py` (`scripts/verifica_s2.py`):

  | insieme | top_k | 0.0 byte-identico a HEAD | testo documentale invariato 0.0→0.35 | copertura 0.0 / 0.35 |
  |---|---:|---:|---:|---|
  | golden | 5 | 58/58 | 58/58 | doc 58/58, sezione 57/57 in entrambe |
  | golden | 10 | 58/58 | 58/58 | doc 58/58, sezione 58/58 in entrambe |
  | multihop | 5 | 8/8 | 8/8 | doc 8/8, sezione 3/3 in entrambe |
  | multihop | 10 | 8/8 | 8/8 | doc 7/7, sezione 5/5 in entrambe |
  | holdout | 5 e 10 | 7/7 | 7/7 | fonte attesa nel contesto 6/6 in entrambe (il 7° è il dato assente) |

  Blocchi di codice mediani 12→12 (il tetto complessivo si riempie di altri simboli
  pertinenti); quota dal ponte 4,5→4 sul golden. Holdout in generazione **non** rieseguito:
  la verifica è di composizione del contesto, non delle risposte.
- Test sul codice reale: `tests/test_code_link_filter.py` (pertinenti, non pertinenti, non
  valutabili, senza matrice, nessun candidato, ordine, soglia 0 = stessa lista) e quattro casi
  `/ask` in `tests/test_ask_unified_llm.py` (ortogonale escluso solo a soglia attiva con
  prompt byte-identico fuori dal blocco codice; collegamento spec→codice a coseno 0.4 tenuto;
  simbolo senza vettore tenuto a 0.99; a 0.0 il filtro non viene invocato).

### 2. Generatore dei cataloghi (`tmp/pdfs/build_file_catalogs.py`)

- Un'unica lista `artifacts()` alimenta registro e banda KPI; esclusi per **percorso
  risolto** solo gli output del generatore (`output/pdf/…`) e le copie pubblicate note
  accanto alle sorgenti; un `catalogo_*_v2.pdf` legittimo resta censito.
- Banda KPI: ogni coppia valore-etichetta in una sola cella in stile `cover` (corpo), mai
  `title`. Valori derivati: artefatti, cartelle sorgente, formati (più frequente per primo:
  `SVG + HTML`), e per i mockup le **aree funzionali** dichiarate (4, Autenticazione compresa),
  non i ruoli (3). Singolare/plurale dal conteggio. Cartella sorgente assente = errore.
- Invariati: dati degli artefatti, doppia estensione `diag_6_2_hitl_checkpoints.svg.svg`,
  colonna «Formato / peso». Nuovi `--source`/`--out`; uscita predefinita `output/pdf/`.
- Test `tmp/pdfs/test_build_file_catalogs.py` (9/9, ambiente effimero
  `uv run --no-project --with reportlab==5.0.1 --with pypdf --with pypdfium2 --with pytest`,
  perché reportlab non è una dipendenza dell'app): regola del template con valori estranei,
  concordanza KPI/registro, aree non ruoli, rigenerazioni ripetute senza auto-inclusione,
  PDF legittimo con nome simile, aggiunta/rimozione, singolare, sorgente assente, PDF reso.
- Rigenerazione reale dalla copia R.0 (sola lettura) in `output/pdf/`: pagina 2 identica
  riga per riga agli originali (42/42 e 86/86), unica differenza la riga «Percorso
  sorgente»; resa visiva della banda controllata (`out/catalogo_*.p1.png`). **Nessun PDF del
  corpus è stato sostituito.** In sandbox il catalogo rigenerato, importato dall'intake, dà
  `5 artefatti` e `1 cartella sorgente SVG formato` (due coppie nello stesso paragrafo per
  ordine di lettura, come nel pilot), mentre l'originale mostra ancora valori ed etichette
  separati: la pubblicazione nel corpus va fatta col rigenerato, via intake e review.

### 3. Docling nell'intake

Stesso percorso di prima: upload → `convert_to_markdown` → staging (originale + `.md`) →
preview → approve/reject → reindex delta. Nessun secondo flusso, loader di `docs/` invariato.

| formato | motore | perché |
|---|---|---|
| `.md` | nativo | invariato |
| `.pdf` | Docling 2.126.0 (`intake.docling.enabled: true`) | verificato dal pilot e qui |
| DOCX, PPTX, XLSX, XLS, HTML/HTM, TXT, CSV, JSON, XML, EPUB, MSG | MarkItDown 0.1.7 | misurato: con Docling DOCX abbassa i titoli di un livello (il chunker divide a `##`), XLSX perde il nome dei fogli, HTML latin-1 perde gli accenti; PPTX nessun beneficio misurabile su un campione |
| altri | errore 415 | whitelist invariata |

- PDF: `StandardPdfPipeline`, `ThreadedDoclingParseDocumentBackend`, CPU esplicita, TableFormer
  ACCURATE + cell matching, `force_backend_text`, `heading_hierarchy` + `generate_parsed_pages`,
  niente VLM/Granite, niente arricchimenti, `enable_remote_services=False`,
  `document_timeout = intake.docling.timeout_seconds` (300). Export con
  `escape_underscores=False` (gli identificatori restano `diag_0_3_…`, non `diag\_0\_3\_…`) e
  senza segnaposto d'immagine. Output sui cataloghi corretti **identico** a quello del pilot.
- Digitale o scansione: `pypdf` conta il testo di ogni pagina **prima** della conversione. Solo
  se una pagina ha meno di 20 caratteri si accende l'OCR locale RapidOCR (onnxruntime,
  PP-OCRv6, lingua `it`); mai su un PDF digitale. Scansione sintetica della fixture:
  similarità 0,998 col digitale, tabella e accenti corretti. Pagina bianca → errore
  «nessun testo estraibile»; Docling dà `SUCCESS` con 0 caratteri, quindi il controllo è nostro.
- Pesi congelati e verificati per SHA-256 al primo uso (`intake_convert.DOCLING_WEIGHTS`,
  `OCR_WEIGHTS`); `scripts/docling_models.py` li scarica alle revisioni fissate
  (layout Heron `8f39ad3c…`, docling-models v2.3.0 `fc0f2d45…`, RapidOCR 3.9.2) e con
  `--verifica` li controlla. Posizione: `rag/database/models/docling/` (esclusa da git).

  | peso | SHA-256 |
  |---|---|
  | layout Heron `model.safetensors` | `00333a43…29e0c` |
  | TableFormer ACCURATE | `2a7d6c92…374d9` |
  | RapidOCR det / rec / cls | `090f04ab…f94f` / `6f327246…4884` / `e47acedf…215c` |

- Convertitori lazy (uno per modalità OCR, ~1,6 GB RSS), creazione e conversioni sotto un
  lock di processo: PDF seriali; l'upload gira nel threadpool, non blocca l'event loop.
- Contratto additivo: `ConversionResult` invariato, metadata storici invariati più `motore`,
  `versione_motore`, `fallback` (`null` o `{da, motivo}`), `avvisi`, e per i PDF Docling
  `pdf: {pagine, pagine_senza_testo, ocr}`. Motore, versione e fallback anche nel campo
  `intake` del frontmatter. Routing a MarkItDown = `fallback: null`; guasto o indisponibilità
  di Docling (import, pesi mancanti o alterati, esito `failure`, Markdown vuoto da un PDF con
  testo) = MarkItDown con fallback e avviso esplicito; se anche MarkItDown non estrae nulla,
  errore che riporta entrambi i motivi. Esito parziale e timeout = avviso «INCOMPLETO».
- Cleaner: sull'uscita Docling non si applica `clean_markdown` (toglierebbe un KPI isolato
  «11» o una riga di tabella con puntini), ma solo `normalize_markdown` (NFC, invisibili, righe
  vuote). MarkItDown invariato. Refine resta un'azione esplicita della review.
- Immagini: Docling non le esporta e l'avviso ne riporta il numero; i riferimenti a immagini
  locali di MarkItDown (`![](Picture1.jpg)` dei PPTX, `<img src>` relativi degli HTML) si
  tolgono con avviso. Mai link a file temporanei; nessun segnaposto spacciato per contenuto.
- UI `templates/intake.unified.html`: testo su conversione locale, motori, originale in staging,
  review obbligatoria e solo `.md` in `docs/`; riga di upload con motore e numero di avvisi;
  preview con riquadro «Conversione» (motore e versione, originale e SHA-256, pagine/OCR,
  motivo del ripiego, avvisi, ultimo tentativo di approvazione fallito); `aria-live` su
  esiti di upload e review.
- Duplicato controllato **prima** della conversione e di nuovo sotto un lock subito prima
  della scrittura in staging.

### 4. Solo Markdown in `docs/` dalle pubblicazioni dell'app

Percorsi che scrivono in `docs/`, verificati nel codice: `intake.approve` (sempre e solo il
`.md` composto: `relazione.pdf` diventa `relazione.pdf.md`; originali in `staging/docs/` o
`staging/rejected/`) e la copia storica della canvas review all'archive
(`core/indexing.py`, `…-canvas-review.md`). Generazione Ollama e project brief passano da
`stage_document` come `.md`; import progetti scrive in `code/`, pipeline in `changes/`.
L'app non può impedire scritture manuali esterne. Categoria, frontmatter, classe da
governance (`CATEGORY_CLASSIFICATION`) e authority di default invariati: nessuna authority
dipende dal formato.

**Inventario dei non-Markdown preesistenti** (baseline delle 10:03, 18 file): in
`docs/02_specs_normative/diagrams/` il catalogo PDF e 5 SVG, in `…/mockups/` il catalogo PDF,
10 SVG e 1 HTML. Alle 10:12 li ha **rimossi il manutentore** («li rimetterò con l'intake»):
nessuna migrazione è stata fatta da questa implementazione. Sono nel backup R.0
`C:\Users\Silve\Desktop\vibecraft-docs-backup-20260910-100353` (verificato per SHA-256).
L'indice di produzione contiene ancora i due cataloghi PDF: `--check-integrity` segnala
«stale: 2 rimossi». Nota per la reimportazione: SVG non è fra i formati ammessi dall'intake.

### 5. Approvazione sicura

Sotto writer lock: ricontrollo dello stato `staged`, composizione e validazione, creazione
**esclusiva** (`open(..., "x")`), reindex, journal. Se il reindex fallisce si rimuove il
file solo se è ancora byte per byte quello scritto dalla richiesta; il documento resta
`staged` con `approve_error` nel journal, riprovabile. Test: doppia approvazione concorrente
dello stesso documento, due documenti verso lo stesso nome, destinazione creata durante
l'attesa, reindex fallito + retry, rollback che non tocca un file cambiato da altri, rifiuto
(originale conservato). Limite: un reindex che fallisce dopo aver scritto punti Qdrant può
lasciarli orfani; ritentare l'approve li riscrive con id deterministici, altrimenti vedi rollback.

### 6. Dipendenze e piattaforme

- Lock: 156 → 188 pacchetti; 31 aggiunte della catena Docling senza `[vlm]` (niente `av`,
  niente binari GPL), `typer 0.27.1 → 0.26.8`, `torchvision` in due varianti; torch,
  onnxruntime, transformers, tokenizers invariati. Famiglia docling fissata alle versioni del
  pilot (`docling 2.126.0`, `-core 2.95.0`, `-parse 7.18.0`, `-ibm-models 4.0.2`).
- **torchvision**: il «percorso CPU» del pilot vale solo su Windows. Su Linux la wheel PyPI è
  `0.28.0+cu130` accanto a torch `2.13.0+cu126`, e all'import torchvision solleva
  `RuntimeError` sui major CUDA diversi (letto nel sorgente della wheel). Lo snippet di questa
  nota, applicato com'era, **non aveva effetto**: `[tool.uv.sources]` vale solo per dipendenze
  dirette. Correzione: `torchvision==0.28.0` diretta, con la stessa sorgente e lo stesso
  marcatore di torch → `0.28.0+cu126` su linux x86_64/aarch64 e win_amd64, PyPI su macOS arm64.
  Su Windows ora `nms` gira su CPU **e** CUDA; Docling resta su CPU esplicita. Nuovi test in
  `tests/test_torch_platform_pin.py`.
- Dockerfile: target `cpu` installa torch e torchvision insieme dall'indice cpu; runtime con
  `libxcb1 libgl1 libglib2.0-0`, senza le quali `import docling` fallisce su
  `python:3.14-slim` (`libxcb.so.1`) e l'intake ripiega su MarkItDown, dichiarandolo.
- Verificato davvero: Windows x86_64 (tutto) e **Linux x86_64 in container**, percorso del
  target cpu (sync del lock, `nms`, conversione Docling della fixture). Differenza misurata su
  Linux: il titolo di quarto livello «Note operative» esce come testo; tabella e altri titoli
  identici. **Non verificati**: Linux aarch64, macOS arm64, target `gpu`, build dell'immagine
  Docker completa. win_arm64 e macOS Intel non risolvono già alla baseline (torch).

### 7. Verifiche

| verifica | esito |
|---|---|
| suite completa, `VIBECRAFT_REQUIRE_QDRANT=1` e `VIBECRAFT_REQUIRE_DOCLING=1` | **1389 passati, 0 falliti, 0 saltati** (1342 preesistenti + 47 nuovi), config finale con S2 a 0.35 |
| baseline prima delle modifiche | 1342 passati, 0 falliti, 0 saltati |
| ruff sul codice tracciato e sui file nuovi | pulito; 34 riscontri solo in script sperimentali preesistenti non tracciati di `eval/results/pilot_docling_*` |
| golden (`eval.run --no-save`) | PASS, recall@2 = 0,828 |
| multihop (`eval.run_multihop --no-save`) | PASS, recall media A = 0,854, B exact 6/6 |
| `index.py --check-integrity` | alias allineato; stale per i 2 cataloghi PDF rimossi dal manutentore |
| `history.jsonl` | invariato (hash prima/dopo) |
| flusso API in sandbox (Qdrant dedicato, `docs/` e `database/` propri) | `.md` nativo, PDF con tabelle, scansione, DOCX, HTML: staged; vuoto 422, corrotto 422, `.exe` 415, duplicato 409; `docs/` invariato prima dell'approve; dopo, solo 4 `.md`; originali presenti con SHA-256 identico; nessun riferimento a file; punti Qdrant per ogni nuovo documento; doppio approve concorrente `[200, 409]`; nome occupato 409; rifiuto 200 |
| flusso UI in sandbox | upload dalla pagina (catalogo originale, scansione, HTML, vuoto, corrotto, `.exe`), errori leggibili, preview con motore e avvisi, rifiuto del catalogo originale con motivo, approvazione del rigenerato in `02_specs_normative` |
| produzione durante le prove | `docs/` invariato salvo la rimozione del manutentore; `CURRENT`, versioni, collection e alias Qdrant invariati |

Il golden condiviso non è stato toccato; le fixture del pilot sono usate solo in locale.
**`pdf-diag-3` non è risolto e non era in questo perimetro**; prompt, modello, authority,
precedenze e ranking non sono stati modificati.

### 8. Rollback

- **S2**: `retrieval.code_link_min_question_score: 0.0` in `rag_config.yaml`, riavvio del
  server. Nessuna reindicizzazione.
- **Intake su MarkItDown**: `intake.docling.enabled: false`, riavvio. I documenti già
  approvati restano come sono (sono `.md` in `docs/`).
- **Dipendenze**: le versioni precedenti sono in
  `rag/eval/results/implementazione_migliorie_20260910/baseline/` (`pyproject.toml.prima`,
  `uv.lock.prima`, hash uguali ai riferimenti R.4). Copiarle su `rag/pyproject.toml` e
  `rag/uv.lock`, poi da `rag/` `uv sync --frozen`; ripristinare anche le righe del
  `Dockerfile`. I pesi in `rag/database/models/` restano inerti e si possono eliminare a mano.
- **Pubblicazione fallita**: il file creato viene rimosso da `approve` e il documento resta in
  staging (`approve_error` nel journal): correggere la causa e riapprovare. Se l'indice resta
  incoerente: `uv run --no-sync python -B index.py --check-integrity`, poi
  `index.py --rollback <versione>` o full rebuild (R.2 di `EVOLUZIONE.md`); `docs/` si
  ripristina dal backup R.0 con la procedura di confronto per SHA-256.

## Revisione del 2026-09-10 e nuovo perimetro autorizzato

Il manutentore richiede ora l'implementazione delle migliorie applicabili e di
Docling nel flusso **Importa documenti**. Questa revisione prepara il lavoro:
nessun codice applicativo o documento del corpus è stato modificato qui.
Le prescrizioni di questa sezione prevalgono sugli esempi sperimentali sotto.

- **S2:** il fallback del codice è `0.0`, ma `s2.diff` imposta il YAML a
  **0.35**: applicare quel diff attiva il filtro. Implementare prima con YAML
  `0.0`, verificare il no-op, poi verificare e attivare `0.35` sul corpus corrente.
  Conservare i simboli non valutabili e l'ordine del ponte. Un diff additivo e
  una suite verde non sostituiscono una review del codice e della soglia.
- **Cataloghi:** correggere insieme banda KPI e censimento. Escludere per
  percorso risolto gli output effettivi del generatore, incluse copie pubblicate
  note; non escludere indiscriminatamente `catalogo_*.pdf`. Derivare da un'unica
  lista i conteggi degli artefatti, formati, cartelle e aree secondo il significato
  di ogni KPI. Non confondere aree con ruoli. Testare rigenerazioni ripetute,
  aggiunta/rimozione di artefatti e un PDF legittimo con nome simile al catalogo.
- **Destinazione cataloghi:** produrre i PDF fuori da `docs/` (il generatore ha
  già `output/pdf/`), quindi importarli in staging. Nessuna nuova copia PDF in
  `docs/`. Non rinominare la doppia estensione esistente e non cambiare la
  colonna «Formato / peso» nell'ambito di questi bugfix.
- **Strumenti del pilot:** conservare le correzioni nei relativi harness,
  riusando `quoted_spans` e la mappa chunk corretta. Non duplicare nell'app
  difetti che esistevano soltanto negli strumenti sperimentali.
- **torchvision:** diventa un controllo attuale se entra con Docling. Preferire
  il percorso CPU già provato; se il lock include torchvision, verificare la
  combinazione di wheel e piattaforme. Non applicare ciecamente uno snippet
  CUDA né promettere GPU funzionante sulla base del solo import.
- **graph_context_min_ratio:** nessuna modifica; il pilot non ha mostrato
  beneficio. Nessuna modifica a prompt, modello o ranking per `pdf-diag-3`.

### Docling soltanto nell'intake

Percorso verificato nel codice: `stage_document` in `core/intake.py` chiama
`convert_to_markdown` in `core/intake_convert.py`; salva originale e `.md` nello
staging; `approve` compone il frontmatter e promuove il documento dopo review.
Estendere questo percorso, senza introdurre Docling nel loader di `docs/`.

1. Markdown nativo resta nativo. Docling è il motore preferito per i formati
   supportati e verificati dalla versione installata; MarkItDown resta per gli
   altri formati già ammessi. Definire una matrice esplicita e testata; non
   equiparare supporto dichiarato e qualità verificata. Nessuna regressione della
   whitelist o della gestione degli encoding.
2. Per PDF usare StandardPdfPipeline, CPU, TableFormer ACCURATE, cell matching,
   testo backend e gerarchia nativa con parsed pages, come nel pilot finale.
   Niente Granite/VLM/refine automatico. PDF digitali e scansioni vanno distinti:
   provare OCR locale per le scansioni o segnalare un errore/limite esplicito;
   mai considerare conversione riuscita una scansione vuota o parziale senza
   avviso. Congelare catena e pesi effettivi, non solo il pin Docling.
3. Riutilizzare ConversionResult e i metadata esistenti in modo additivo:
   motore effettivo, versione, hash originale, eventuale fallback e avvisi
   arrivano alla preview. Fallback per formato non supportato è routing;
   fallback dopo errore va dichiarato, non deve nascondere perdita di struttura.
4. **Ogni nuova pubblicazione gestita dall'app in docs/ è `.md`.** Originali,
   immagini estratte e altri binari restano fuori da docs/. Non produrre link
   a temporanei o segnaposto spacciati per contenuto. Review manuale, validazioni
   di governance e reindicizzazione restano obbligatorie.
5. La regola è prospettica: i non-Markdown già presenti vengono inventariati,
   non cancellati, spostati o convertiti in massa. Una migrazione richiede un
   piano separato per riferimenti, artefatti SVG/HTML, backup e duplicazioni.
   Non si promette di impedire scritture manuali esterne al filesystem.
6. Dentro il writer lock ricontrollare stato staged e destinazione libera;
   evitare sovrascritture con creazione esclusiva, e assicurare che rollback
   e journal descrivano solo la scrittura posseduta dalla richiesta. Verificare
   due approvazioni concorrenti dello stesso ID e di ID diversi sullo stesso
   nome, oltre al fallimento di reindicizzazione.
7. Verificare il cleaner sulla nuova uscita strutturata: non applicare alla cieca
   trasformazioni che eliminano titoli, tabelle, codice o KPI. Il refine resta
   opzionale e distinto dalla conversione.
8. Aggiornare `templates/intake.unified.html`, API/preview e documentazione:
   upload → conversione locale → review → Markdown in docs/. Usare i limiti e
   il meccanismo di lavoro esistenti; conversioni pesanti non devono bloccare
   l'event loop. Testare dipendenza/pesi mancanti, timeout e errori recuperabili.

### Accettazione e ordine di implementazione

S2 separata; poi bugfix generatore; quindi dipendenze/conversione intake e
approvazione sicura. Il rifiuto del precedente pilot end-to-end resta valido:
questa è una nuova richiesta di intake con review, non la sua approvazione
retroattiva. Non dichiarare risolto `pdf-diag-3`.

Test significativi del codice definitivo (non una replica della logica in uno
script), suite con Qdrant obbligatorio, lint, golden/multihop e integrità.
Verificare l'intero flusso mediante API e UI, anche con Markdown nativo,
formato instradato a MarkItDown, PDF digitale con tabelle e scansione.
Confermare che prima dell'approvazione docs/ sia invariato, dopo vi entri solo
il `.md`, e rifiuto/errore non pubblichino nulla. Usare fixture sintetiche o
sandbox per le pubblicazioni di test, non caricare documenti di prova nel corpus.

Le misure 1342/0/0 e i punteggi sotto sono riferimenti storici, non risultati
garantiti del nuovo codice. I comandi [V] possono scrivere nello storico:
usare `--no-save` dove disponibile e dichiarare gli altri effetti, senza
cancellare valutazioni autentiche. Proteggere baseline e backup prima di
qualsiasi pubblicazione o reindicizzazione. Nessun commit, push o PR implicito.

**2026-09-10** · ramo di partenza `codex/evoluzione-p0`, HEAD
`011e264c554895c651f0eba1dccb74bc4dc10f74`.

Questa nota raccoglie ciò che è emerso **incidentalmente** durante la verifica di
fattibilità del pilot Docling, ed è **indipendente** dal pilot stesso. Il pilot
resta NON_APPLICARE per `pdf-diag-3` (vedi `EVOLUZIONE.md`, sezioni del 9 e 10
settembre): nulla di quanto segue lo risolve, e nulla di quanto segue ne dipende.

**Che cos'è:** una nota di implementazione — causa, diff, precondizioni,
verifiche, rischio, rollback. **Che cosa non è:** un'autorizzazione. Nessuna di
queste modifiche è stata portata in produzione; tutte sono state provate in
sandbox isolati.

## Riepilogo e ordine consigliato

| # | intervento | maturità | rischio | dove |
|---|---|---|---|---|
| **1** | `code_link_min_question_score` — pertinenza sul ponte IMPLEMENTS | **verificata end-to-end** | basso (default = no-op) | `api/routes_retrieval.py`, `core/config.py`, `rag_config.yaml` |
| **2** | banda KPI del generatore cataloghi | **corretta e provata** su PDF rigenerati | medio (rigenera PDF) | `tmp/pdfs/build_file_catalogs.py` |
| **3** | il catalogo inventaria sé stesso + conteggi KPI hardcoded | **riprodotta**, filtro provato | medio (stesso file di #2) | `tmp/pdfs/build_file_catalogs.py` |
| **4** | `torchvision` fuori dall'indice CUDA | **latente**, non attivo oggi | nullo finché non entra | `rag/pyproject.toml` |
| **5** | `graph_context_min_ratio` spento | **misurata: no-op oggi** | — | nessuna azione |

**Ordine:** 1 da solo (è indipendente e a rischio più basso). 2 e 3 insieme,
perché toccano lo stesso file e la stessa rigenerazione. 4 solo quando/se
`torchvision` diventa una dipendenza. 5 nessuna azione, solo memoria.

## Precondizioni comuni

- ramo dedicato, mai `main`;
- backup del corpus prima di #2/#3 (procedura R.0 di `EVOLUZIONE.md`);
- Qdrant raggiungibile e `VIBECRAFT_REQUIRE_QDRANT=1` per le suite: senza, i test
  di integrazione **saltano** invece di fallire e il verde non vuol dire nulla;
- da `rag/`, ambiente già installato (`uv run --no-sync`, niente `uv sync`).

Blocco di verifica riusato da tutti gli interventi, d'ora in poi **[V]**:

```bash
uv run --no-sync python -B -m pytest tests -q -p no:cacheprovider
uv run --no-sync ruff check --no-cache .
uv run --no-sync python -B -m eval.run
uv run --no-sync python -B -m eval.run_multihop
uv run --no-sync python -B index.py --check-integrity
```

Riferimenti attesi, misurati più volte fra il 2026-09-08 e il 2026-09-10:
suite **1342 passati, 0 falliti, 0 saltati**; `ruff` pulito; golden
`recall@2 = 0.828` (soglia 0.75); multihop `recall media A = 0.854`, `B exact 6/6`;
integrità `ok`, non stale. Il budget del prompt fisso (**954 token stimati / 1000**)
è già dentro la suite, in `tests/test_ask_prompt_cost.py`.

---

# 1. Pertinenza alla domanda sul ponte IMPLEMENTS

## Causa

`/ask` inietta codice da **due rami**:

| ramo | funzione | ordina per | filtro di pertinenza **alla domanda** |
|---|---|---|---|
| semantico | `search_code_symbols` (`routes_retrieval.py:209`) | coseno domanda→simbolo | **sì**, `code_search_min_score` = 0.45 |
| ponte IMPLEMENTS | `collect_implementing_code` (`:492`) | somiglianza codice→spec | **no**, solo `code_context_min_weight` sull'**arco** |

Il ponte risale gli archi `IMPLEMENTS` dalle sezioni recuperate: sceglie per
**prossimità nel grafo**, e su una domanda che non parla di codice inietta
comunque il suo tetto pieno.

## Evidenza

Sonda in-process (LLM sostituito da stub, nessuna generazione), mediane, `top_k=10`:

| insieme | blocchi codice totali | di cui dal ramo semantico |
|---|---:|---:|
| 8 domande sui cataloghi | 10 | **0** |
| golden (58 casi) | 12 | 8 |
| multihop (8 catene) | 12 | 8 |

Sulle domande documentali **tutto** il codice arriva dal ponte e il ramo che
valuta la pertinenza ne fa entrare zero; su golden e multihop il ramo semantico
ne porta 8 su 12 — **quel codice serve e non va tolto**. Composizione del
contesto su quelle domande: ~20 % è codice TypeScript che nessuna regola ha mai
giudicato pertinente alla domanda.

## Modifica

Applica al ponte **lo stesso segnale e la stessa funzione** del ramo semantico,
ristretta con `subset_idx` ai soli simboli che il ponte propone: nessuna formula
duplicata, nessun segnale che in produzione non esista.

**`core/config.py`** — dopo `CODE_CONTEXT_TOTAL_SNIPPETS`:

```python
# Pavimento di coseno DOMANDA->simbolo applicato al ramo IMPLEMENTS
# (collect_implementing_code), che filtra solo sul peso dell'ARCO e quindi puo'
# iniettare codice pertinente alla spec recuperata ma non alla domanda. Stesso segnale e
# stessa funzione del ramo semantico (search_code_symbols), ristretta ai simboli che il
# ponte propone. 0.0 = disattivato: il contesto torna identico a prima.
CODE_LINK_MIN_QUESTION_SCORE: float = float(
    _retrieval_cfg.get("code_link_min_question_score", 0.0))
```

**`api/routes_retrieval.py`** — importare la costante e, fra `linked_code` e
`merge_code_context` (`:492`–`:499`):

```python
    scartati_ponte: list[dict] = []
    if CODE_LINK_MIN_QUESTION_SCORE > 0 and linked_code and query_encoding is not None:
        # Solo i simboli VALUTABILI passano dal filtro. Un simbolo senza vettore denso non
        # è in `code_ids`, quindi il coseno non esiste per lui: l'assenza del segnale non è
        # una prova di irrilevanza, e scartarlo sarebbe escludere per mancanza di dati.
        posizione = {sid: i for i, sid in enumerate(snap.code_ids)}
        valutabili = [c for c in linked_code if c["symbol_id"] in posizione]
        righe = [posizione[c["symbol_id"]] for c in valutabili]
        pertinenti: set[str] = set()
        if righe:
            pertinenti = {c["symbol_id"] for c in await run_in_threadpool(
                retrieval.search_code_symbols, query_encoding["dense"], snap.code_store,
                max_snippets=len(righe), min_score=CODE_LINK_MIN_QUESTION_SCORE,
                max_per_file=0, code_ids=snap.code_ids, code_matrix=snap.code_matrix,
                subset_idx=righe,
            )}
        scartati_ponte = [{"symbol_id": c["symbol_id"], "file": c["file"], "name": c["name"],
                           "peso_arco": c.get("weight"), "motivo": "coseno domanda→simbolo",
                           "soglia": CODE_LINK_MIN_QUESTION_SCORE}
                          for c in valutabili if c["symbol_id"] not in pertinenti]
        if scartati_ponte:
            logger.info(
                "ask code_link_filter request_id=%s soglia=%s proposti=%d valutabili=%d "
                "tenuti=%d scartati=%s", request_id, CODE_LINK_MIN_QUESTION_SCORE,
                len(linked_code), len(valutabili), len(linked_code) - len(scartati_ponte),
                ",".join(s["symbol_id"] for s in scartati_ponte))
        esclusi = {s["symbol_id"] for s in scartati_ponte}
        linked_code = [c for c in linked_code if c["symbol_id"] not in esclusi]
```

**`rag_config.yaml`** — sotto `code_context_total_snippets`:

```yaml
  # Pavimento di coseno DOMANDA->simbolo sul ponte IMPLEMENTS.
  # 0.0 = disattivato (comportamento identico a prima).
  code_link_min_question_score: 0.35
```

Diff completo e applicabile: `rag/eval/results/sel_contesto_20260910-090000/diff/s2.diff`
(**47 righe aggiunte, 0 rimosse**, 3 file).

## Il `fail-open` non è un dettaglio

La prima stesura scartava anche i simboli **senza vettore denso**, che non sono
valutabili perché il coseno per loro non esiste. Due test comportamentali sono
diventati rossi
(`test_ask_inietta_codice_trovato_solo_dalla_ricerca_semantica`,
`test_ask_cappa_chunk_e_snippet_oltre_il_tetto`). **Erano i test ad avere
ragione**: l'assenza del segnale non è prova di irrilevanza. Sono tornati verdi
correggendo il filtro, non toccando le asserzioni. Chi reimplementa deve
conservare quel ramo, ed è il primo caso del controllo eseguibile.

## Perché 0.35 e non 0.45

Sweep completo, blocchi di codice mediani:

| soglia | cataloghi | golden | multihop |
|---:|---:|---:|---:|
| 0.00 | 10 | 12 | 12 |
| **0.35** | **3** | **12** | **12** |
| 0.40 | 1 | 10 | 12 |
| 0.45 | 0 | 8 | 9 |

0.45 — la soglia del ramo semantico — azzererebbe il codice sulle domande
documentali ma costerebbe 4 blocchi al golden e 3 al multihop: **codice che
quelle domande usano**. 0.35 è il punto di massima selettività a copertura
invariata, scelto su golden/multihop.

## Verifiche

Oltre a **[V]**:

- **controllo della regola**, 7 casi (soglia 0 = no-op, ortogonale scartato,
  simbolo senza vettore che resta, ordine del ponte conservato, nessun candidato,
  solo non valutabili): `rag/eval/results/sel_contesto_20260910-090000/scripts/check_s2.py`
  → atteso **7/7**. Va portato in `tests/` come test vero al momento
  dell'implementazione;
- **no-op a 0.0**: con la soglia a `0.0` il contesto deve essere **byte-identico**
  a prima. Verificato su 8 contesti su 8;
- **invariante documentale**: il testo dei blocchi documentali non cambia a
  nessuna soglia. Verificato su **74 contesti su 74** (8 cataloghi + 58 golden +
  8 multihop);
- **copertura**: golden 58/58 e multihop invariati (`scripts/copertura.py`, che
  riusa `esito_caso`/`blocchi_del_contesto` di `eval/calibrate_graph_context.py`);
- **holdout separato** di 7 domande nuove — comportamento del codice, ponte
  spec→codice, fattuale a classe singola e a classi diverse, multi-documento,
  dato assente: **14/14 prima e 14/14 dopo**.

## Rischio e rollback

Rischio basso: additivo, e il default `0.0` lo disattiva. Rollback = riportare
`code_link_min_question_score` a `0.0` in `rag_config.yaml` e riavviare; non
serve reindicizzare, perché la modifica agisce sulla **composizione del contesto
a runtime**, non sull'indice.

**Limite dichiarato:** misurato su golden (58), multihop (8), holdout (7) e suite
(1342). È un campione, non una garanzia generale.

---

# 2. Banda KPI del generatore cataloghi

## Causa

`tmp/pdfs/build_file_catalogs.py`, `build_diagrams` e `build_mockups`: la banda
KPI costruisce i **valori** come una riga di tre celle in stile `title`, poi
aggiunge le tre **etichette** come paragrafi separati centrati verticalmente.

```python
story.append(Table([[P("5", s["title"]), P("1", s["title"]), P("SVG", s["title"])]], ...))
story.extend([Spacer(1, 4*mm), P("artefatti", s["cover"]),
              P("cartella sorgente", s["cover"]), P("formato", s["cover"]), Spacer(1, 14*mm)])
```

Le etichette **non sono allineate** sotto le rispettive colonne: l'associazione
valore→etichetta è **posizionale**, non strutturale. A valle, l'estrattore
conserva i valori ma raggruppa le etichette e assegna a `SVG + HTML` la classe
`section_header` — **un falso titolo** nel documento indicizzato.

## Modifica

Ogni coppia definita dal template diventa **un'unica cella di corpo**, mai un
titolo:

```python
def kpi_band(pairs, styles):
    # Ogni coppia definita dal template e' un unico paragrafo/cella di CORPO, mai un titolo.
    cells = [P(f"{value} {label}", styles["cover"]) for value, label in pairs]
    return Table([cells], colWidths=[55 * mm] * len(cells), style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), .5, TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6 * mm),
    ]))
```

con `pairs = [("5", "artefatti"), ("1", "cartella sorgente"), ("SVG", "formato")]`
per i diagrammi e `[("11", "artefatti"), ("4", "aree funzionali"),
("SVG + HTML", "formati")]` per i mockup — **da derivare**, vedi #3.

Implementazione già scritta e provata:
`rag/eval/results/pilot_docling_sourcefix_20260909/build_candidates.py`.

## Verifiche

- **regola del template con altri valori**, non le risposte attese: costruire la
  banda con coppie diverse (es. `[("27","elementi"), ("9","gruppi")]`) e
  pretendere `["27 elementi", "9 gruppi"]` e stile `cover` su ogni cella. È il
  controllo che distingue «il template è corretto» da «questo PDF è corretto»;
- **nessun falso titolo**: nel documento convertito, `SVG + HTML` non deve avere
  classe `section_header`;
- rendering delle pagine e ispezione visiva (i PNG li produce già lo script);
- **[V]** dopo la reindicizzazione.

## Rischio e rollback

Medio: **cambia i byte dei PDF**, quindi hash nuovi, reindicizzazione
obbligatoria e baseline di retrieval da rifare. Fare backup R.0 prima. Rollback =
ripristinare i PDF dal backup e `index.py --rollback <versione>`.

---

# 3. Il catalogo inventaria sé stesso, e i conteggi KPI sono scritti a mano

## Causa

Due difetti che si nascondono a vicenda, **nello stesso file di #2**.

**(a)** `build_diagrams` fa il glob dell'intera cartella senza filtri:

```python
source = SOURCE / "diagrams"
files = sorted(source.rglob("*"))
files = [p for p in files if p.is_file()]
```

e `catalogo_diagrammi_normativi.pdf` **vive dentro
`docs/02_specs_normative/diagrams/`**, insieme ai 5 SVG. Alla prossima
rigenerazione il catalogo si aggiunge come **sesto artefatto**, con area
«Da classificare». L'originale non lo fa solo perché fu generato **prima di
esistere**.

**(b)** i conteggi della banda KPI sono **costanti scritte a mano** (`P("5", …)`)
mentre il registro è generato dal filesystem: le due metà possono divergere in
silenzio, ed è esattamente ciò che accadrebbe al punto (a) — registro a 6 righe,
banda che dice «5 artefatti».

**Non è teorico:** rigenerando il 2026-09-10 è successo, ed è per questo che è
stato trovato. Riscontro nel log: righe nuove `catalogo_diagrammi_normativi.pdf`
e `Da classificare` in pagina 2.

## Modifica

**(a)** escludere il catalogo dal proprio censimento:

```python
files = [p for p in sorted(source.rglob("*")) if p.is_file()
         and p.resolve() not in generated_output_paths]
```

`generated_output_paths` deve contenere i percorsi risolti degli output e delle
copie pubblicate note, non un pattern sui nomi di PDF legittimi.

**(b)** derivare i conteggi dalla stessa lista, invece di scriverli; esempio
per i diagrammi (per i mockup le aree derivano dai metadati degli artefatti):

```python
pairs = [(str(len(files)), "artefatti"),
         (str(len({p.parent for p in files})), "cartella sorgente"),
         (" + ".join(sorted({p.suffix.lstrip('.').upper() for p in files})), "formato")]
```

Se si preferisce non derivarli subito, il minimo indispensabile è **un assert**
che li confronti con la lista: un conteggio che mente è peggio di un conteggio
assente.

Filtro già scritto e provato (`senza_se_stesso`) in
`rag/eval/results/corpus_disambigua_20260910-170000/scripts/build_disambigua.py`,
insieme al confronto riga-per-riga di pagina 2 che protegge dalla deriva
dell'inventario.

## Verifiche

- **pagina 2 invariata** rispetto al PDF precedente, riga per riga, esclusa la
  sola intestazione modificata: verificato su **41 righe dati** (diagrammi) e
  **85** (mockup). Nessuna dimensione cambiata — `19.5 KB`, `46.4 KB`, `3.4 KB`
  tutte al loro posto;
- il registro **non contiene** `catalogo_*.pdf`;
- banda KPI e registro **concordano** sul numero di artefatti;
- **[V]** dopo la reindicizzazione.

## Rischio e rollback

Come #2: rigenera i PDF. Da fare **nello stesso intervento di #2**, con un solo
backup, una sola reindicizzazione e una sola nuova baseline.

---

# 4. `torchvision` fuori dall'indice CUDA — latente

## Causa

`rag/pyproject.toml`, `[tool.uv.sources]` dirotta sull'indice `pytorch-cu126`
**solo `torch`**. Se `torchvision` entrasse come dipendenza arriverebbe da PyPI
nella variante `+cpu`: le sue operazioni compilate (`nms` e simili) sollevano
`NotImplementedError` sul backend CUDA, **mentre `torch.cuda.is_available()`
resta `True`** — un difetto silenzioso.

Misurato il 2026-09-08 in ambiente isolato: `torch 2.13.0+cu126` con
`torchvision 0.28.0+cpu`; `nms` su CPU funziona, su CUDA fallisce; `matmul` su
GPU funziona (la catena torch è sana).

## Stato

**Latente, non attivo:** `torchvision` **non è oggi una dipendenza** del progetto
(verificato). Nessun intervento necessario adesso.

## Quando servirà

Il giorno in cui `torchvision` entra (oggi lo porterebbe Docling), aggiungere in
`[tool.uv.sources]` la stessa voce di `torch`, con lo **stesso marker**:

```toml
torchvision = [
    { index = "pytorch-cu126", marker = "sys_platform == 'linux' or (sys_platform == 'win32' and platform_machine == 'AMD64')" },
]
```

e verificare che `tests/test_torch_platform_pin.py` continui a passare: quel test
esiste proprio per gli invarianti di piattaforma dei pin torch.

**Verifica di merito, non solo di import:** eseguire un'operazione compilata su
CUDA (`torchvision.ops.nms` su tensori `.cuda()`), non limitarsi a
`import torchvision`. È la differenza fra «si installa» e «funziona».

---

# 5. `graph_context_min_ratio` è spento — nessuna azione

`retrieval.graph_context_min_ratio` è un pavimento di pertinenza **relativo** al
miglior punteggio ColBERT della domanda, già progettato e implementato
(`routes_retrieval.py:379`), ma impostato a **0.0 = disattivato**.

**Misurato:** a 0.3 e a 0.5 produce contesti **identici** a oggi su tutti e tre
gli insiemi (cataloghi, golden, multihop) — stessi caratteri, stessi blocchi. Le
sezioni raggiunte via grafo stanno tutte sopra il 50 % del miglior punteggio
della loro domanda, quindi il pavimento non taglia nulla.

**Nessuna azione.** Va tenuto a mente come leva già pronta se un domani
l'espansione di grafo peggiora: è il posto giusto, ed è calibrabile con
`eval/calibrate_graph_context.py`.

---

# Correzioni di documentazione, non di codice

Emerse leggendo il sorgente, e utili a chi lavorerà su questi parametri.

1. **`governed_max_chunks` non tocca `/ask`.** Compare solo in
   `api/routes_pipeline.py` (canvas/propose). Il numero di blocchi semantici di
   `/ask` è governato da `top_k` della richiesta. Alcuni resoconti precedenti
   glielo attribuivano: è sbagliato.
2. **I tetti di composizione non sono assi della griglia S11.** Il sorgente di
   `eval/calibrate_authority.py` lo scrive: la griglia congiunta ha **quattro
   assi, tutti pesi di ranking** (`boost_alpha`, `default_weight`,
   `unclassified_weight`, `section_restatement_weight`), e
   «`graph_context_max_chunks` NON è in questa griglia». I tetti hanno un harness
   proprio. Resta vera la dipendenza **documentata** in `rag_config.yaml:322`: il
   tetto grafo salì a 3 quando alpha passò a 0.3 — direzione nota, non
   co-calibrazione.
3. **`top_k` ha default 5** (`api/models.py:19`, cap 20), mentre l'harness del
   pilot usa **10**: tutte le misure di contesto delle sessioni di settembre sono
   al **doppio** del default di produzione. Va detto ogni volta che si cita una
   di quelle cifre.
4. **`diag_6_2_hitl_checkpoints.svg.svg`** ha davvero la doppia estensione sul
   filesystem. Sembra un salvataggio accidentale, ma rinominarlo cambierebbe
   catalogo, indice e risposta attesa della domanda congelata: è una **decisione**,
   non una pulizia da fare di passaggio.

---

# Che cosa questa nota NON propone

- Non risolve `pdf-diag-3`: le varianti provate non hanno superato il criterio.
  Questi campioni non dimostrano un tetto assoluto del modello né una causa
  unica; la scala è uno dei fattori per cui sono state raccolte evidenze.
- Non tocca prompt, ranking, `authority`, precedenze o parametri calibrati.
- L'autorizzazione successiva riguarda Docling nell'intake con review, come
  specificato nella revisione in apertura; non il loader PDF né la migrazione
  automatica del corpus esistente.
