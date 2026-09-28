# Fedeltà Excel — chiusura 2026-09-11

**Esito complessivo: NON_APPLICARE.** Il candidato ricompone le righe sparse e conserva
le coordinate, ma non supera tutti i criteri richiesti. La suite verde non sostituisce
il gate di fedeltà. Il candidato è nel working tree, non committato e non approvato
per l'uso sul corpus. Nessun commit, push, merge, deploy o riavvio dell'applicazione.

Lavoro iniziato il 10 settembre, ripreso l'11 dopo il ripristino del limite di utilizzo;
il nome della directory mantiene la data iniziale. Ramo invariato `codex/docling-intake`,
HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`. Nessun `AGENTS.md` trovato negli antenati
o nei percorsi interessati. `status.before.txt` registra il working tree iniziale,
già ampiamente modificato: il diff rispetto a HEAD **non** è il diff di questa sessione.

## 1. Perché NON_APPLICARE

Due controlli indipendenti impediscono il PASS:

1. **Tabelle affiancate:** il candidato produce una griglia A:E unica per due tabelle
   originali distinte A1:B2 e D1:E2, anche quando sono dichiarate come oggetti Table nel
   workbook. La colonna C vuota è conservata, ma questo prova la posizione delle celle,
   non la separazione delle tabelle. Il caso era corretto in Docling: è una regressione.
   `strict_gate.py --baseline` termina con 0; `strict_gate.py` termina con 1.
   Prove: `strict-baseline.json`, `strict-candidate.json`.
2. **Valori originali di SOLVSAMP.XLS:** 69 celle cambiano già nella normalizzazione
   LibreOffice: 55 differenze nelle ultime cifre numeriche e 14 booleani `True` → `1`.
   Quest'ultimo cambiamento riguarda A23/D23–A29/D29 del foglio «Portafoglio titoli».
   Esempio numerico, «Panoramica» B5: `3591.5525890622844` → `3591.55258906228`.
   Il candidato conserva esattamente tutte le celle dell'XLSX normalizzato, ma ciò non
   basta a dichiarare fedeltà all'XLS originale. Le differenze di normalizzazione sono
   presenti anche nella baseline e sono registrate separatamente. Nessuna tolleranza
   numerica, equiparazione booleano/intero o esclusione dal gate è stata introdotta.

La riga «Totale» non resta ambigua nel candidato. Il verdetto negativo dipende dai due
controlli sopra: nessun punteggio aggregato compensa un requisito fallito.

## 2. Causa riprodotta e percorso completo

Letti nota di implementazione, resoconto LibreOffice, script `fixture.py`, `attese.py`,
`esperimento.py`, test intake, fixture e Markdown delle precedenti prove. Il backend
**installato** è Docling 2.126.0, openpyxl 3.1.5. Verificato il sorgente locale
`docling/backend/msexcel_backend.py` e `docling/datamodel/backend_options.py`.

Percorso iniziale:

1. `convert_to_markdown`: validazione del contenitore; XLS con stream OLE valido passa
   a `_normalize_legacy`, usando una copia e un profilo LibreOffice temporaneo blindato.
2. `MsExcelDocumentBackend` legge l'XLSX con `openpyxl.load_workbook(data_only=True)`:
   legge risultati memorizzati, non esegue formule. Un risultato assente appare vuoto.
3. `_find_data_tables` e `_find_table_bounds` cercano componenti connesse con una BFS
   nelle quattro direzioni. `gap_tolerance=0` separa A7, C7 e E7:F7 quando B7/D7 sono vuote.
   Le celle unite sono trattate mediante ancore e intervalli, non come nuovi valori.
4. `_convert_xlsx_docling` serializza ogni gruppo-foglio con `MarkdownDocSerializer`,
   aggiungendo il nome del foglio. Esporta quindi le tre tabelle già frammentate.
5. `normalize_markdown` normalizza Unicode/newline: non crea né ripara le associazioni.
   `stage_document` salva quel Markdown; preview e approve lo riusano.

Il problema precede il cleaner. La presenza separata di «Totale», `10` e `1500.5` non
dimostra che la relazione fra celle sia sopravvissuta.

Opzioni supportate ispezionate: `gap_tolerance`, `treat_singleton_as_text`, `sheet_names`,
`parse_charts`, `render_chart_images`. Nessuna separa la tolleranza orizzontale da quella
verticale. La prova con `ExcelFormatOption(backend_options=MsExcelBackendOptions(
gap_tolerance=1))` conferma il danno: in `formati2/fixture/registro.xlsx` la tabella
«Riepilogo / Totale» entra sotto le intestazioni «Codice / Stato / Quantità / Data».
Artefatto: `gap1/04-registro.xlsx.md`. L'opzione non è stata adottata globalmente.

## 3. Candidato implementato e prima/dopo

`core/intake_excel.py` usa openpyxl già installato. Legge formule/tipi e valori memorizzati
con due viste dello stesso workbook; non esegue due convertitori. Emette coordinate
originali, tutte le colonne fra gli estremi del foglio, blocchi separati da righe vuote,
intervalli delle celle unite e valore soltanto nell'ancora. Non riconosce etichette,
nomi di file o coordinate speciali della fixture.

Il percorso condiviso nel candidato è **XLSX → openpyxl**, **XLS → LibreOffice → XLSX →
openpyxl**. PDF e altri formati conservano i motori precedenti. `intake.docling.enabled`
controlla ora solo PDF. Metadati: `motore=openpyxl`, versione installata, SHA e formato
dell'originale; normalizzazione LibreOffice dichiarata per XLS. Un errore di openpyxl
produce `ConversionError`, senza un ripiego su pandas che altererebbe i valori. Il fallback
XLS→MarkItDown quando LibreOffice manca resta quello preesistente, dichiarato e non
equivalente al percorso verificato.

**Prima**, `registro_excel.xlsx`, dopo il cleaner:

```markdown
| Totale   |
|----------|

| 10   |
|------|

| 1500.5   | 2401   |
|----------|--------|
```

**Dopo**, stesso file, dopo il cleaner:

```markdown
### A7:F7

| Riga | A | B | C | D | E | F |
| --- | --- | --- | --- | --- | --- | --- |
| 7 | Totale |  | 10 |  | 1500.5 | 2401 |
```

Le intestazioni originali rimangono nella riga 2, sulle stesse colonne A:F. Per
`registro.xlsx` la riga è invece `7 | Totale | vuoto | 999 | vuoto | 1500.5 | vuoto`:
`999` è il risultato memorizzato obsoleto, non viene sostituito con `10`; F7 non diventa
`2401`. L'avviso identifica `Registro!F7` come formula senza risultato memorizzato.

Nel caso **verticale** precedentemente corretto, `formati2/registro.xlsx`, il candidato
mantiene due blocchi: A1:D4 e A6:D7. «Riepilogo / Totale» resta una riga originale del
secondo blocco. Il confronto **orizzontale** aggiunto in `strict_gate.py` fallisce invece
come descritto al §1. Non è stato presentato come superato dal test delle sole coordinate.

Date: si usa il tipo della cella e `is_datetime(number_format)`. Solo un datetime a
mezzanotte con formato di sola data viene reso come data ISO. Timestamp, orari e il
letterale `00:00:00` restano completi. Test distinto con tutti e quattro i casi.
Preservati stringhe `NA/N/A/null`, zeri e zeri iniziali; il formato numerico semplice
`00000` conserva lo zero padding. Non è un'implementazione completa dei formati Excel.

La review ha riprodotto e fatto correggere due difetti di escaping: marcatore `#` finale
nei nomi dei fogli e interpretazione di caratteri letterali nella preview. Escaping in
un unico passaggio; la preview Excel decodifica le sole entità generate e torna a fare
escape HTML, mostrando tabelle e celle senza eseguire markup della fonte. Il test Node
usa le funzioni reali estratte dal template, incluso un input HTML ostile.

## 4. Attese e confronto

`tests/test_intake_excel.py` è stato scritto prima della modifica: `red.log` documenta
6 fallimenti, inclusi entrambi gli XLSX originali. Le attese della riga 7 vengono lette
e verificate sul workbook originale prima della conversione. I casi aggiunti coprono
etichetta «Residuo Ω» in C7, posizione spostata, tabelle verticali distinte, più fogli e
foglio vuoto, unioni, formule con/senza cache, stringa che inizia con `=` ma non è una
formula, letterali, date/orari, delimitatori Markdown, testo a capo e spazi marginali.

`compare.py` legge gli originali **prima** della conversione: openpyxl per XLSX, xlrd
per XLS. Il controllo confronta ogni valore con le coordinate foglio/riga/colonna,
controlla valori estranei, celle duplicate, nomi e ordine dei fogli e associazioni di riga.
Intercetta il risultato della normalizzazione già eseguita per attribuire le differenze
al livello corretto, senza una seconda normalizzazione per importazione. Le viste della
baseline senza coordinate sono valutate sulle associazioni di riga; i suoi fallimenti
includono anche differenze di presentazione della data e titoli fuori tabella, quindi
il loro numero non è un punteggio confrontabile né un criterio di promozione.

| originale | confronto esatto candidato/originale |
|---|---|
| LibreOffice fixture `registro.xlsx` | superato, 30 celle; cache 999 e F7 assente |
| `registro_excel.xlsx` | superato, 31 celle; cache 10/1500.5/2401 |
| `registro.xls` autentico Excel 16 | superato, 31 celle |
| `rete.xlsx` | superato, formule prive di cache segnalate |
| `formati2/fixture/registro.xlsx` | superato, due blocchi verticali distinti |
| `formati/fixture/budget.xlsx` | superato, formula senza cache segnalata |
| `formati/fixture/budget.xls` | superato |
| `tests/fixtures/intake/legacy.xls` | superato |
| Microsoft Office `PROTTPLN.XLS` | superato; campione piccolo, una cella non vuota |
| Microsoft Office `SOLVSAMP.XLS` | **fallito**, 69 differenze originate nella normalizzazione |
| due Table esplicite A1:B2 e D1:E2 | **fallito**, unica tabella Markdown nel candidato |

I campioni Microsoft sono quelli installati in Office16 (`SAMPLES/SOLVSAMP.XLS` e
`1040/PROTTPLN.XLS`), montati in sola lettura. Non sono stati usati documenti personali.
Le fixture esistenti non sono state rigenerate o modificate.

## 5. Verifiche eseguite

| verifica | risultato effettivo |
|---|---|
| test mirati Excel/intake sull'host, prima degli ultimi casi aggiunti | 126 passati, 5 skip: LibreOffice assente (`targeted.log`) |
| test Excel finali sull'host | 10 passati, 1 skip: API XLS richiede LibreOffice (`host-excel-final.log`) |
| suite completa finale, container CPU con Git, Qdrant dedicato, Docling e LibreOffice obbligatori | **1438 passati, 0 falliti, 0 skip**, 15 warning di deprecazione delle dipendenze, 154,99 s (`suite-container-final.log`) |
| preview/approve XLSX e XLS in sandbox | passati nella suite: SHA originale, contenuto preview, frontmatter e solo `.md` pubblicato; reindex stub, nessun indice reale |
| renderer effettivo della preview | test Node passato (`preview-green.log`); niente sessione browser con clic reali in questa sessione |
| `uv sync --frozen` | 164 pacchetti verificati, lock e dipendenze invariati (`sync.log`) |
| Ruff su tutti i file Python di questa modifica | passato (`lint-changed.log`) |
| `ruff check .` | **43 segnalazioni preesistenti** negli script storici di `eval/results/implementazione_migliorie_*` e `pilot_docling_*`, fuori dai file modificati (`lint-all.log`) |
| gate rigoroso tabelle indipendenti | baseline PASS; candidato **NON_APPLICARE**, exit 1 |
| gate rigoroso valori originali | candidato **NON_APPLICARE**, exit 1 su SOLVSAMP |
| ripetibilità | baseline 10/10 e candidato 10/10 Markdown byte-identici fra due processi/container nuovi; UTF-8, LF, nessun CR (`verification.json`) |
| corpus, staging e CURRENT | 56 hash invariati, nessun file aggiunto; cataloghi compresi (`protected.before.json`, `verification.json`) |

La prima suite in container aveva 11 fallimenti causati dal bind `0.0.0.0` dell'immagine
anziché quello locale atteso dai test e 9 skip per Git assente. Ambiente corretto senza
cambiare le asserzioni. Un'esecuzione intermedia ha inoltre intercettato il doppio
escaping delle entità, poi corretto e verificato con la suite finale completa.

La suite completa sull'host era stata respinta dalla revisione automatica per il rischio
di scrivere nello stato protetto. È stata eseguita nell'ambiente isolato: nessun mount
di `docs/`, staging o CURRENT reali; solo sorgenti e pesi in sola lettura. Qdrant v1.19.0
effimero su rete dedicata, nessuna porta host. I test LibreOffice obbligatori sono quindi
stati eseguiti dove LibreOffice è effettivamente presente, non conteggiati come skip validi.

**Prestazioni**, prima esecuzione finale (seconda nei JSON; misure diagnostiche, non un
benchmark controllato, perché parte della suite girava contemporaneamente):

| caso | baseline secondi / picco RSS albero MB | candidato secondi / picco RSS albero MB |
|---|---|---|
| primo XLSX, avvio a freddo del convertitore | 3,58 / 520,9 | 0,03 / 190,3 |
| XLSX successivi | circa 0,02 / 521,9 | 0,01–0,02 / 190,8 |
| `registro.xls`, incluso LibreOffice | 1,49 / 758,0 | 1,50 / 426,6 |
| `SOLVSAMP.XLS`, incluso LibreOffice | 1,92 / 761,2 | 1,60 / 429,7 |

RSS campionato ogni 10 ms sull'intero albero di processi: non è la sola memoria
incrementale del parser. Nessuna regressione evidente di tempo/memoria nel campione;
questo non compensa i fallimenti di fedeltà.

## 6. Comandi e CI

Comandi dall'host, salvo `cd rag` dove indicato:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
cd rag
uv sync --frozen
.\.venv\Scripts\python.exe -B -m pytest tests/test_intake_excel.py -rs
.\.venv\Scripts\python.exe -B -m ruff check .
node tests/intake_excel_preview.cjs
.\.venv\Scripts\python.exe -B eval/results/excel_fidelity_20260910/strict_gate.py --baseline
.\.venv\Scripts\python.exe -B eval/results/excel_fidelity_20260910/strict_gate.py
```

Banco completo riproducibile dalla radice:

```powershell
& rag/eval/results/excel_fidelity_20260910/run_comparison.ps1
# Ripetizioni del solo candidato dopo l'ultimo fix:
& rag/eval/results/excel_fidelity_20260910/run_comparison.ps1 -Runs candidate1,candidate2
docker build -f rag/eval/results/excel_fidelity_20260910/Dockerfile.tests -t vibecraft-excel-tests:20260910 rag/eval/results/excel_fidelity_20260910
```

Lo script del confronto contiene tutti i mount e usa `--network none`. La suite usa la
stessa immagine CPU, con Git aggiunto solo nell'immagine di test e i moduli Python di
pytest già installati sull'host copiati in `tmp/excel-test-runtime` e montati in sola
lettura. Variabili: `PYTHONPATH=/testdeps:/app/rag`, `VIBECRAFT_HOST=127.0.0.1`,
`QDRANT_URL=http://excel-fidelity-qdrant:6333`, `VIBECRAFT_REQUIRE_QDRANT=1`,
`VIBECRAFT_REQUIRE_DOCLING=1`, `VIBECRAFT_REQUIRE_LIBREOFFICE=1`.
Comando nel container: `python -B -m pytest -rs -p no:cacheprovider`.
Montati `core`, `api`, `templates`, `tests`, `eval`, `rag_config.yaml` del working tree
e i soli pesi `database/models/docling`, tutti in sola lettura. Nessun rebuild del
target CPU completo: dipendenze/runtime sono quelli dell'immagine CPU già disponibile;
i sorgenti correnti sono verificati attraverso i mount.

**CI remota non eseguita.** Il controllo dell'11 settembre (`remote-ci.json`) trova il
workflow CI attivo, ma nessun ramo remoto `codex/docling-intake`. Le modifiche non sono
committate né pubblicate: un dispatch avrebbe verificato codice differente. Nessun push.
Il workflow locale ora comprende il test della preview, il gate rigoroso di non-fusione
e smoke reali XLSX/XLS con verifica dell'intera riga. Corretto anche lo stdin `-i` del
comando Docker con heredoc: senza, Python non riceveva lo script di smoke.
**Con questo candidato il gate di non-fusione deve fallire**; non è stato disabilitato.

Retrieval e indicizzazione non modificati da questa sessione. Nessun benchmark retrieval
rieseguito; i loro unit test fanno parte della suite ordinaria.

## 7. File, limiti e rollback

Contributi di questa sessione, oltre agli artefatti in questa directory:

- nuovo `rag/core/intake_excel.py`: candidato di serializzazione;
- `rag/core/intake_convert.py`: routing Excel condiviso, rimozione del vecchio adattatore
  Excel Docling; PDF/legacy non Excel conservati;
- nuovo `rag/tests/test_intake_excel.py`, aggiornamenti circoscritti ai test Excel in
  `test_intake_docling.py` e `test_intake_libreoffice.py`;
- nuovo `rag/tests/intake_excel_preview.cjs`, renderer Excel e metadati in
  `rag/templates/intake.unified.html`;
- `.github/workflows/ci.yml`: regressione, gate rigoroso e smoke del motore effettivo;
- commenti di `rag/rag_config.yaml`, matrice in `rag/README.md` e nota
  `rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md` allineati allo stato del candidato.

Limiti residui: fusione di tabelle orizzontali; normalizzazione XLS non identica nei tipi
e nella precisione; formati numerici Excel personalizzati non emulati completamente;
immagini/grafici esclusi con avviso; scansione rettangolare con rifiuto esplicito oltre
1.000.000 di celle dichiarate per foglio (nessun troncamento). Il fallback XLS senza
LibreOffice resta quello storico, con perdita dichiarata; non è promosso a percorso fedele.

**Rollback:** rimuovere soltanto i contributi di questa sessione, non fare checkout/reset
del repository sporco. `intake_convert.before.txt` è la copia esatta del convertitore
all'inizio, comprensiva delle modifiche preesistenti: ripristinandolo si torna a XLSX
Docling e XLS→LibreOffice→Docling. Ripristinare insieme le aspettative Excel e i relativi
controlli CI/UI; il nuovo modulo openpyxl diventa inutilizzato e può essere rimosso.
`intake.docling.enabled=false` **non** annulla il candidato Excel. Nessuna migrazione
di documenti o reindicizzazione serve per il rollback del codice.

I 18 file rimossi intenzionalmente da `docs/` non sono stati ripristinati. Gli hash del
corpus attuale e dello staging sono invariati. I cataloghi **07aefc94ceea** e
**9f6505d3cf48** restano separati da questa verifica: nessuna approvazione, rifiuto o
modifica; **revisione umana ancora necessaria**.

A fine verifica sono stati rimossi il container `excel-fidelity-qdrant`, la rete
`excel-fidelity-ci` e `tmp/excel-test-runtime`; restano l'immagine di test e gli artefatti.
Per ricreare il runtime pytest, copiare dal venv locale i pacchetti Python `_pytest`,
`pytest`, `pluggy`, `iniconfig`, `pygments`, le relative directory `.dist-info` e `py.py`
nella directory temporanea poi montata su `/testdeps`. Nessuna nuova dipendenza di
produzione è stata aggiunta. `candidate-code-sha256.json` identifica i file verificati;
`intake_convert.session.diff` isola il cambiamento del convertitore dalla baseline già
modificata. L'ultimo controllo riconferma i 56 hash e `CURRENT=v20260910T121150`.
