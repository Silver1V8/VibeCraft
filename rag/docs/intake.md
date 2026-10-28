Italiano | [English](../README.en.md)

> Documentazione operativa sotto `rag/docs/`: **non** è corpus RAG (il corpus è `docs/` del progetto). Stesso schema degli ADR. Italiano canonico; l'inglese resta un indice breve in `rag/README.en.md`.

[← Indice operativo](../README.md)

# Intake & Import

## Intake & Import: ingresso controllato della conoscenza

La pagina **`/intake`** ([templates/intake.unified.html](../templates/intake.unified.html),
route in [api/routes_pages.py](../api/routes_pages.py)) è l'unico ingresso di nuova
conoscenza — documenti e progetti — nel sistema. Il principio non negoziabile è lo
**staging con review**: nulla entra in `docs/` o nell'indice senza un'approvazione
esplicita dalla pagina. Il ciclo vive in [core/intake.py](../core/intake.py) e nelle
route [api/routes_intake.py](../api/routes_intake.py) (`/api/intake/*`, auth `X-API-Key`
come il resto), e usa lo stesso writer lock dell'indicizzazione. L'approvazione dei
documenti salva i file; il pulsante **Aggiorna indice** avvia l'indicizzazione dopo la review.

**Cinque flussi, un solo staging** (`database/staging/`, con journal append-only
`intake.jsonl`):

- **Genera con Ollama** (`POST /api/intake/generate`, [core/doc_generation.py](../core/doc_generation.py)):
  fino a `intake.generation_max_files` documenti markdown grounded nel Graph RAG
  (hybrid_search) e nelle lezioni delle canvas review; ogni file è validato
  (parse + chunking) prima di entrare in staging.
- **Importa documenti** (`POST /api/intake/docs`, [core/intake_convert.py](../core/intake_convert.py)):
  upload multipart convertito in Markdown **in locale** e messo in staging accanto
  all'originale. Il motore segue una matrice esplicita, misurata sulla versione installata:

  | formato | motore |
  |---|---|
  | `.md` | nativo (solo decodifica) |
  | `.pdf` | **Docling** 2.126.0 se `intake.docling.enabled`, altrimenti MarkItDown |
  | `.xlsx`, `.xls` | lettura diretta dell'originale: **openpyxl** 3.1.5, **xlrd** 2.0.2 ([core/intake_excel.py](../core/intake_excel.py)) |
  | DOCX, PPTX, HTML/HTM, TXT, CSV, JSON, XML, EPUB, MSG | MarkItDown 0.1.7 |
  | DOC, PPT | **LibreOffice** headless → DOCX, PPTX, poi la riga del formato moderno |

  La scelta viene da un confronto sugli stessi input, dopo il cleaner reale, con attese
  scritte prima (`archive/eval-results/verifica_finale_20260910/`). Fogli di calcolo
  (`archive/eval-results/excel_diretto_20260911/RESOCONTO.md`): MarkItDown passa da pandas, che svuota
  le celle «NA», «N/A», «null» e scrive `7.0` e `NaN`; Docling divide in più tabelle una riga
  con celle vuote intermedie; LibreOffice arrotonda a 15 cifre i numeri degli XLS e trasforma i
  booleani in numeri. La lettura diretta produce, per foglio, intervalli di celle con le
  coordinate originali (una colonna vuota in tutto il foglio separa gli intervalli, una riga
  vuota i blocchi: nessuna intestazione o tabella dedotta) e i valori memorizzati, senza
  ricalcolo né formato di visualizzazione; formati, celle unite, commenti, collegamenti e testo
  dall'aspetto numerico sono elencati per foglio, formule, disegni e grafici esclusi hanno un
  avviso. Nessun ripiego: file illeggibile, protetto o oltre 1.000.000 di celle da
  rappresentare = errore esplicito. DOCX ambiguo (Docling migliore
  con lo stile Title, peggiore con un titolo in Heading 1): resta MarkItDown. PPTX: MarkItDown
  conserva le note del relatore. CSV: Docling fallisce sul `;` latin-1. HTML ed EPUB alla
  pari. DOC e PPT (`intake.libreoffice`): LibreOffice porta una COPIA al formato moderno,
  con un profilo temporaneo nuovo per ogni conversione (macro spente, collegamenti esterni mai
  aggiornati, nessun ricalcolo delle formule, albero di processi terminato al timeout), poi
  decide la riga del formato moderno; senza LibreOffice DOC e PPT danno un errore. Mai il
  LibreOffice interno di Docling (profilo predefinito:
  misurato, scarica le immagini collegate). Sui formati moderni LibreOffice non migliora nulla
  e non viene usato (`archive/eval-results/libreoffice_20260910/`). Un contenitore non valido (DOCX,
  PPTX, XLSX, EPUB non ZIP; DOC, XLS, PPT senza la struttura OLE attesa; MSG senza firma OLE) è
  un errore, non un documento di byte grezzi; un OOXML o XLS cifrato è «protetto da password».
  Configurazione dei PDF, quella del pilot finale:
  `StandardPdfPipeline`, CPU esplicita, TableFormer ACCURATE con cell matching, testo del
  backend, gerarchia dei titoli dallo stile, niente VLM né servizi remoti. I pesi stanno in
  `intake.docling.models_dir`, fissati a revisioni note e verificati per SHA-256 al primo uso:
  `uv run python scripts/docling_models.py` li scarica, `--verifica` li controlla. Solo un
  PDF con pagine senza testo selezionabile (scansione) passa dall'OCR locale RapidOCR; un
  PDF digitale mai. Se Docling non è disponibile (dipendenza, pesi) o fallisce, il PDF passa
  da MarkItDown con un **fallback dichiarato** (`metadata.fallback` e un avviso nella
  preview), mai presentato come conversione equivalente; una scansione senza Docling è un
  errore, non un documento vuoto. Motore, versione, fallback, avvisi e, per i PDF, pagine,
  pagine senza testo e uso dell'OCR arrivano alla preview; motore, versione ed eventuale
  fallback anche nel campo `intake` del frontmatter. Le immagini non entrano in `docs/`:
  Docling non le esporta, e i riferimenti a immagini locali di MarkItDown (PPTX, HTML) si
  tolgono con un avviso — l'originale resta in staging. La whitelist resta la nostra
  (`intake.allowed_formats`); estensione e dimensione (`intake.max_upload_mb`) sono validate
  PRIMA di leggere l'intero body in memoria, e un duplicato (stesso SHA-256 di un documento
  staged o approvato) è rifiutato prima della conversione. Le conversioni Docling sono seriali
  nel processo e girano nel threadpool, mai sull'event loop; `intake.docling.timeout_seconds`
  limita un documento (oltre, risultato parziale dichiarato come INCOMPLETO).
  L'uscita di MarkItDown passa **sempre** per
  [core/intake_clean.py](../core/intake_clean.py), che toglie l'arredo di impaginazione del
  sorgente — testate e piè di pagina ripetuti a ogni pagina, numeri di pagina, indici coi
  puntini di guida, immagini base64, sillabazione e a-capo di giustificazione. È pulizia
  **deterministica e idempotente**: nessuna parola di contenuto viene persa (su un PDF
  istituzionale toglie comunque il 20-60% del dump). Senza, tutto quel rumore finisce
  identico nei chunk del RAG. L'uscita di Docling, già strutturata e senza testate né piè di
  pagina, passa solo per `normalize_markdown` (NFC, caratteri invisibili, righe vuote): le
  regole di arredo toglierebbero righe di contenuto, come un valore KPI isolato.
- **Raffina con LLM** (`POST /api/intake/staged/{id}/refine`,
  [core/intake_refine.py](../core/intake_refine.py)): passo **opt-in** del ciclo di review che
  trasforma il dump del convertitore in una spec strutturata — sezioni `##` (l'unità di
  chunking), tabelle per gli elenchi di campi, blocchi di codice per XML/XSD — più un
  frontmatter **semantico** dedotto dal documento (`title`, `document_type`, `domain`,
  `tags`), che `approve` fonde in coda ai campi normativi senza mai sovrascriverli. Job
  async (pattern S3) perché su un documento lungo sono decine di chiamate al modello
  (~2 min per finestra su GPU locale). Due guardrail contro il rischio vero di questo
  passo, che è tradire il documento: si raffina a **finestre**
  (`intake.refine.window_chars`, ben sotto `num_ctx` — oltre, Ollama tronca in silenzio) e
  una finestra la cui riscrittura esce dalla **forbice di lunghezza** viene **scartata** a
  favore del testo pulito. Troppo corta significa che il modello ha riassunto (e un
  riassunto perde requisiti); troppo lunga che ha commentato o ipotizzato invece di
  riformattare — su una fonte frammentaria tende a riempire i buchi con congetture
  ("inferito", "potrebbe riferirsi") che in un documento normativo sono peggio del testo
  grezzo. Il tetto **dipende dalla forma della fonte**: la prosa sta sotto
  `max_output_ratio`, mentre le fonti dense (alberi di classi, elenchi di campi — righe
  mediamente più corte di `dense_line_chars`) hanno diritto a `max_output_ratio_dense`,
  perché diventando tabelle con una colonna di descrizione crescono di 3-4× senza che una
  parola sia stata inventata. Il markdown grezzo resta in staging accanto al raffinato:
  rieseguire il refine riparte sempre da quello, mai dalla riscrittura.
- **Review staging** (`GET /api/intake/staged`, `.../preview`, `POST .../approve`,
  `POST .../reject`): preview del markdown, poi **approve** (scrive
  `docs/<categoria>/<nome_file>` con frontmatter conforme, sotto writer lock del
  progetto, senza reindex) o **reject** (motivo nel journal, file spostati
  in `staging/rejected/`, mai cancellati). `approve` **non sovrascrive MAI** un file
  esistente in `docs/`, e il documento composto deve passare parse/chunking PRIMA di
  qualunque scrittura. Sotto writer lock ricontrolla che il documento sia ancora in staging
  e che la destinazione sia libera e crea il file in modo esclusivo. Puoi approvare più
  documenti e poi premere **Aggiorna indice** una sola volta: fino ad allora l'indice
  resta sulla versione precedente, con lo stato **da aggiornare**. Se l'indicizzazione
  fallisce, i file approvati restano in `docs/` per un nuovo tentativo. Anche `reject` e
  la scrittura finale della raffinazione passano dallo stesso writer lock, ricontrollando lo
  stato: un rifiuto o una raffinazione arrivati tardi non toccano un documento già
  approvato. In `docs/` entra
  solo il `.md` composto; l'originale resta in `staging/docs/` (o `staging/rejected/`).
  Ogni pubblicazione dell'app in `docs/` è un `.md` — l'approve dell'intake e la copia storica
  della canvas review all'archive —, ma l'app non può impedire scritture manuali esterne.
  L'aggiornamento esplicito considera anche le altre modifiche/rimozioni presenti
  nei sorgenti del progetto. Il PDF ancora su disco resta una fonte
  distinta anche quando si approva un `.md` derivato.
- **Pesi di Docling, Docker e CI**: i pesi (layout, TableFormer, RapidOCR, ~540 MB) non sono
  nel repository né nell'immagine. In locale: `uv run python scripts/docling_models.py`
  (scarica alle revisioni fissate e verifica gli SHA-256; `--verifica` controlla soltanto).
  In Docker vanno nel volume dell'indice: `docker compose --profile cpu run --rm app-cpu
  python scripts/docling_models.py`. L'immagine include le librerie native di OpenCV e
  `fonts-liberation`: senza font, i PDF con font non incorporati venivano resi diversamente e
  il layout declassava un titolo. In CI il job `test` recupera i pesi da una cache chiavata
  sugli hash dei file che dichiarano revisioni e SHA, li riverifica e gira con
  `VIBECRAFT_REQUIRE_DOCLING=1` (senza pesi i test falliscono, non saltano); il job `docker`
  converte davvero un PDF, una scansione, DOC, PPT, XLSX e XLS nell'immagine costruita.
- **Importa progetto da path** (`POST /api/intake/project/plan` + `.../apply`,
  [core/project_import.py](../core/project_import.py)): import di un progetto locale in
  `code/<target>` (una sottocartella esistente di `code/`, es. `backend`, `frontend`,
  `logicAgent`, oppure una nuova creata dalla pagina) col pattern **plan/apply**.
  Il plan è un **dry-run puro** (zero scritture) che classifica i file in
  nuovi/identici/conflitti/esclusi (esclusioni riusate da `CODE_EXCLUDED_DIRS`).
  Semantica **additiva e non distruttiva, vincolante**: cartella vuota → bootstrap
  (copia tutto il copiabile); cartella popolata → additivo (copia SOLO i file nuovi;
  i file esistenti con contenuto diverso sono **conflitti**, riportati nel piano e
  **mai applicati**). `apply` fa un backup zip della cartella target, copia solo i
  nuovi, rifiuta un piano **stale** (fingerprint del target cambiato dopo l'anteprima)
  e reindicizza il codice in delta (avviso esplicito se serve un full rebuild per i
  code-link). **Mai una sovrascrittura, mai una cancellazione** di un file esistente
  in `code/`.

**Project brief** (`POST /api/intake/project/brief`, [core/project_brief.py](../core/project_brief.py)):
dopo un import riuscito, genera via Ollama una sintesi architetturale del progetto
(componenti, entrypoint, dipendenze, mappa simboli→spec dagli archi `IMPLEMENTS` del
grafo, aree candidate a refactoring), **grounded sui dati reali del grafo** — mai
inventati. Precondizione: un import `applied` per quel target/progetto nel journal
(altrimenti 409); grafo senza simboli → esito con avviso, mai un crash. Il brief
entra in staging come ogni altro documento (`source "brief"`) e passa dalla stessa
review S2: **nessun percorso diretto verso `docs/`**.

L'unità del brief è il **progetto**, non il target. `target` è un bucket
(`backend`/`frontend`/`logicAgent`) e l'import è additivo, quindi `code/backend/` può
ospitare più progetti affiancati (`GD102_WSGDAProtocolloManager` **e**
`GD172_WSProtocollo`): un grounding filtrato per solo `dev_type` prende i simboli di
tutti, e il tetto `_MAX_SIMBOLI_NEL_PROMPT` riempie il prompt col primo in ordine di
`id` — il brief chiesto per un progetto descrive l'altro. Il campo `progetto` della
richiesta seleziona la cartella sotto `code/<target>/`; **omesso vale l'ultimo progetto
importato** in quel target, mai "tutto il bucket". `GET /api/intake/project/imports`
elenca i progetti importati (dal journal) per popolare la scelta nella pagina.

Nel prompt i simboli sono un **campione scelto, non un troncamento**. Un progetto reale
ne ha migliaia (`GD172_WSProtocollo`: 4100 simboli in 309 file) e nel contesto di
qwen3.5:9b ne stanno decine: `simboli[:80]` su una lista ordinata per path mostrava solo
le cartelle iniziali in ordine alfabetico e, dei 337 endpoint, solo quelli che iniziano
per A. `seleziona_simboli` fa invece **un giro per file** (una `Reference.cs` generata da
1650 simboli vale come ogni altro file) e dentro ciascuno prende prima ciò che ha valore
architetturale (`_RANGO_KIND`: tipi ed entrypoint prima delle property, a parità di
natura vince il grado nel sottografo), campionando **a passo costante** le fasce
omogenee troppo lunghe — così le 337 operazioni SOAP si attraversano tutte invece di
fermarsi alla A. Accanto al campione il prompt porta i **conteggi per modulo, completi**:
sono l'unico grounding che copre il 100% del progetto, e il prompt dice esplicitamente al
modello che l'elenco dei simboli è parziale. I tetti del prompt sono **in caratteri**
(`_BUDGET_CHAR_*`), non solo in voci: la lunghezza di una riga dipende dai path del
progetto, e con soli tetti a voci il prompt usciva a ~48.000 caratteri (~13.700 token) —
dentro `num_ctx 16384` a stento, con Ollama che taglia l'eccedenza **dall'inizio**, cioè
proprio le istruzioni. Ora resta sotto i ~6.500 token, il resto della finestra è per la
risposta.

Le **regole di formato** del prompt sono istruzioni per il modello, non garanzie: prima
della validazione l'output passa da `normalize_generated_markdown`
([core/doc_generation.py](../core/doc_generation.py)), che ripara i tre modi ricorrenti in
cui il contorno del documento esce sbagliato — documento avvolto in un fence
```` ```markdown ````, frontmatter aperto e **mai chiuso**, frontmatter non caricabile
come YAML — senza toccare il corpo. Il frontmatter generato è materiale di passaggio
(quello conforme lo ricalcola l'`approve`), quindi un contorno rotto non costa più
l'intero documento; resta scartato solo ciò che non ha un corpo utilizzabile, col motivo
nel journal. In parallelo il parser di indicizzazione riconosce il frontmatter **solo**
come blocco ben formato `---`…`---` in cima al file (`core.chunking.split_frontmatter`,
confronto per riga): un blocco non chiuso vale come assente, non inghiotte più il corpo
del documento nel YAML.

