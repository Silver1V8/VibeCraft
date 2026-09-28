# Excel in Markdown per lettura diretta (XLSX openpyxl, XLS xlrd) — 2026-09-11

**Esito: PASS** per i criteri richiesti, sui 12 file verificati (§6), con i limiti del §8.
Il candidato del 10-11 settembre (**NON_APPLICARE**) non è stato preso come base approvata:
è archiviato in `candidato_non_applicare/` e le sue parti incompatibili sono state sostituite
(§2). Nessun commit, push, merge, deploy o riavvio dell'applicazione. La revisione umana dei
cataloghi `07aefc94ceea` e `9f6505d3cf48` resta separata: **non eseguita, non approvati**.

## 0. Stato di partenza e perimetro

- Ramo `codex/docling-intake`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74` (`branch-head.txt`),
  invariati. Nessun `AGENTS.md` nel repository né in `Desktop`, `Silve`, `Users`, `C:\`.
- Working tree già ampiamente modificato da sessioni precedenti: `status.before.txt` (765
  voci con `--untracked-files=all`). Il diff rispetto a HEAD **non** è il diff di questa sessione.
- I 10 file del candidato avevano esattamente gli SHA-256 di
  `../excel_fidelity_20260910/candidate-code-sha256.json`: il candidato era attivo.
- Stato protetto fotografato prima di ogni modifica (`protetti.py` → `protected.before.json`):
  corpus `docs/` (42 file), staging con i cataloghi e il journal (13), `CURRENT`, `history.jsonl`
  = 57 hash; i 56 della sessione precedente coincidono. I file rimossi intenzionalmente da
  `docs/` non sono stati ripristinati.

## 1. Cause dei difetti, riprodotte prima di modificare (`riproduzione.txt`)

1. **Fusione delle tabelle affiancate (candidato).** Ogni blocco usava tutte le colonne fra gli
   estremi del *foglio* e i blocchi erano separati solo da righe vuote: nessuna regola sulle
   colonne. A1:B2 e D1:E2 diventavano la tabella `A1:E2` (gate rigoroso: exit 1; con la
   baseline Docling exit 0).
2. **Associazione persa nella riga «Totale» (baseline Docling).** Il backend Excel di Docling
   cerca componenti connesse con `gap_tolerance=0`: `Totale | vuoto | 10 | vuoto | 1500.5 | 2401`
   diventa tre tabelle senza coordinate. `gap_tolerance=1` fonde invece tabelle separate da una
   riga vuota (prova della sessione precedente, `gap1/`).
3. **Normalizzazione XLS con LibreOffice.** Non è una questione di serializzazione: LibreOffice
   25.2.3.2 riscrive i *valori memorizzati* (15 cifre significative), cambia il *tipo* dei
   booleani e riscrive i *formati*. Dettaglio nel §5.

## 2. Il candidato precedente: archivio, parti rimosse e parti conservate

Archivio verificabile in `candidato_non_applicare/`: le 10 copie con `SHA256SUMS` (uguali a
`candidate-code-sha256.json`), `tracked_vs_HEAD.diff` (file tracciati),
`intake_convert.session.diff` e `intake_convert.before.txt` (il convertitore prima del
candidato) e `candidato_vs_finale.diff` (27 blocchi: che cosa è cambiato da allora). Nessun
reset, checkout o restore: sostituzioni selettive con Edit/Write.

| parte del candidato | esito | motivo |
|---|---|---|
| `core/intake_excel.py`: griglia min..max colonna del foglio | **sostituito** | causa della fusione (§1.1) |
| XLS → LibreOffice → XLSX → openpyxl | **rimosso** | altera valori, tipi e formati (§5) |
| ripiego XLS → MarkItDown senza LibreOffice, e il suo avviso | **rimosso** | percorso con perdite note (pandas) |
| escape con entità HTML anche per `_`, `*`, `#` | **sostituito** | `codice_articolo` diventava `codice&#95;articolo`: meno cercabile |
| `normalize_markdown` sull'uscita Excel | **rimosso** | toglie spazi unificatori e caratteri a larghezza zero dalle celle |
| valore «formattato» (`00000` → `00007`), data senza ora | **sostituito** | mostrava il formato come se fosse il valore (§3) |
| `iter_rows` sul rettangolo, rifiuto a 1M celle *dichiarate* | **sostituito** | un solo valore in XFD1048576 faceva rifiutare il file |
| booleani resi `True`/`False` in stile Python | **sostituito** | resi `TRUE`/`FALSE`, e il testo «TRUE» è elencato come testo |
| test Excel con attese del candidato, smoke CI con `convert_xlsx` | **sostituiti** | attese del vecchio contratto |
| decodifica delle sole entità nella preview | **sostituita** | ora decodifica gli escape backslash e divide solo sui `\|` non escapati |
| `DOCLING_FORMATS = {"pdf"}`, rimozione di `_convert_xlsx_docling` | **conservato** | codice Excel Docling rimasto inutilizzato |
| modalità Excel della preview (tabella, `th scope`), riquadro «Conversione» | **conservato** | |
| passi CI «Preview Excel» e gate rigoroso di non-fusione | **conservati** | il gate ora passa **senza essere modificato** |
| test di contenitore, cifratura, guasto di openpyxl senza ripiego | **conservati** | |

Le versioni di `test_intake_docling.py` e `test_intake_libreoffice.py` *precedenti* al candidato
(file non tracciati) non erano state salvate: dall'archivio si torna al candidato, non oltre.

## 3. Soluzione finale

**Percorso condiviso**: `convert_to_markdown` → `core/intake_excel.convert_excel(data, fmt)`;
XLSX con openpyxl 3.1.5, XLS con xlrd 2.0.2 (`EXCEL_FORMATS`). XLS non passa più da LibreOffice
(`LEGACY_FORMATS = {doc, ppt}`); il controllo dello stream OLE resta per tutti e tre. Staging,
errori, provenienza (SHA dell'originale), preview e approvazione sono quelli esistenti. Nessun
flag e nessun ripiego: un file illeggibile è una `ConversionError`. PDF, DOC, DOCX, PPT e PPTX
invariati.

**Contratto della rappresentazione** (docstring del modulo):
- una sezione `##` per foglio nell'ordine del workbook, compresi i vuoti («Nessuna cella con
  valore.») e i nascosti («Foglio nascosto.»); una legenda iniziale spiega le coordinate;
- ogni tabella Markdown è un **intervallo** `### A1:F5`: prima colonna il numero di riga,
  intestazioni = lettere di colonna. Nessuna intestazione dedotta;
- **regola geometrica, unica**: una colonna senza valori né unioni in tutto il foglio separa gli
  intervalli; dentro un intervallo di colonne, una riga vuota separa i blocchi. Ogni blocco usa
  tutte le colonne del suo intervallo, così una riga con celle vuote intermedie resta una riga
  allineata alle intestazioni. Nessuna parola chiave, soglia o coordinata speciale;
- **valore memorizzato**: formule mai ricalcolate (nessun salvataggio del workbook), numeri
  nella forma più breve che ridà esattamente il double, booleani `TRUE`/`FALSE`, errori col
  codice Excel, date e ore ISO (al millisecondo, la risoluzione di Excel; la sola data solo per
  la mezzanotte esatta con un formato di sola data), durate `36:00:00`;
- **formato visualizzato distinto dal valore**: i formati non generali sono elencati per foglio
  («Formati numerici del file, non applicati ai valori mostrati: «0%» F3; «00000» C5»): nessun
  renderer di Excel promesso, nessun valore alterato;
- **tipo ricostruibile**: il testo che sembrerebbe numero, data, booleano, errore o che è vuoto
  è elencato («Testo, non numero, data, booleano o errore: A3:A5, D9:F9»); il testo resta
  verbatim, così «00123», «NA», «N/A», «null» e «0» sono cercabili come sono;
- **celle unite**: valore solo nella cella iniziale, intervalli elencati;
- **escape CommonMark/GFM** in un solo passaggio: backslash davanti a `\`, `` ` ``, `*`, `[`, `]`,
  `<`, `>`, `|`, `~`, `&`; `_` solo al bordo delle parole, LF → `<br>`, CR e altri controlli → entità numeriche, spazi di bordo →
  entità. Verificato con un parser reale (markdown-it) sul valore letto indietro;
- commenti e collegamenti ipertestuali inclusi, ordinati per coordinata, con la cella.

**Formule e contenuti non di cella.** XLSX: due letture dello stesso file (valori memorizzati e
formule); avviso col numero di formule e, separato, l'elenco delle celle con formula **senza**
risultato memorizzato (vuote nel Markdown, nessun ricalcolo); un risultato memorizzato obsoleto
(registro.xlsx: C7 = 999) non è rilevabile e resta com'è. XLS: xlrd espone il risultato memorizzato ma
non il testo delle formule né quali celle ne hanno; il numero di formule è contato sui record
BIFF `FORMULA`. Disegni, immagini, grafici e oggetti incorporati sono segnalati (XLSX: parti del
pacchetto; XLS: record OBJ non di commento e sottoflussi grafico) e restano nell'originale.

**Limiti espliciti, mai troncamenti**: `MAX_XML_CELLS` = 2.000.000 celle nell'XML dei fogli
(anche solo formattate), contate a blocchi *prima* di caricare; `MAX_CELLS` = 1.000.000 celle da
rappresentare. Oltre: errore che lo dice. Le celle solo formattate non entrano nel Markdown.

**Metadati**: `motore` `openpyxl`/`xlrd`, `versione_motore`, `fallback: null`, nessuna
`normalizzazione`; preview con l'etichetta «celle lette direttamente dall'originale con …».

**Dipendenze**: `xlrd>=2.0.2` dichiarata diretta in `pyproject.toml` (importata dall'app; prima
solo transitiva di `markitdown[xls]`); `uv.lock` cambia in due righe di `requires`, nessuna nuova
risoluzione (`uv lock --check --offline`: ok). openpyxl era già diretta.

## 4. Esempi prima/dopo

Riga «Totale», `registro_excel.xlsx` (salvato da Excel):

```text
prima (Docling):            | Totale |      | 10 |      | 1500.5 | 2401 |   → tre tabelle
dopo:   ### A7:F7
        | Riga | A | B | C | D | E | F |
        | 7 | Totale |  | 10 |  | 1500.5 | 2401 |     (stesse colonne A:F della riga 2)
```

Tabelle affiancate (gate rigoroso invariato, ora exit 0, `strict-gate-diretto.json`):

```text
prima (candidato): ### A1:E2  | 1 | Voce | Euro |  | Persona | Anni |
dopo:              ### A1:B2  | 1 | Voce | Euro |      e      ### D1:E2  | 1 | Persona | Anni |
```

SOLVSAMP.XLS, «Panoramica» B5 e «Portafoglio titoli» riga 23 (Excel: 3591,5525890622844 e VERO):

```text
prima (LibreOffice → openpyxl): | 5 | Unità vendute | 3591.55258906228 | …    | 23 | 1 |  |  | 1 |
dopo  (xlrd):                   | 5 | Unità vendute | 3591.5525890622844 | …  | 23 | TRUE |  |  | TRUE |
```

Tipo e escape, fixture `casi_excel` (C9 errore, D9 testo): `| 9 | Errori | #DIV/0! | #N/A | #N/A |
TRUE | 0 |` con «Testo, non numero, …: D9:F9»; la cella `*grassetto* _x_ codice_articolo <b>&amp;`
diventa `\*grassetto\* \_x\_ codice_articolo \<b\>\&amp;` e il parser la rilegge identica.

## 5. Le 69 alterazioni (e le altre 80) della normalizzazione XLS

Riferimento: l'originale letto da **Excel 16** (`excel_oracle.ps1`: copia, sola lettura,
calcolo manuale impostato prima dell'apertura, macro disattivate, collegamenti non aggiornati;
hash dell'originale ricontrollato). Confronto campo per campo con lo stesso file dopo
LibreOffice (`normalizzati/`, `classifica_normalizzazione.py` → `classificazione_SOLVSAMP.json`).
Il confronto della sessione precedente guardava solo i valori: le differenze sono **149**, e le
69 sono tutte comprese.

| celle | origine | tipo | valore memorizzato | formato | testo visualizzato da Excel | formula |
|---:|---|---|---|---|---|---|
| 29 | 69 | invariato | **arrotondato a 15 cifre** | invariato | identico | identica |
| 4 | 69 | invariato | **arrotondato a 15 cifre** | riscritto | identico | identica |
| 22 | 69 | invariato | **arrotondato a 15 cifre** | riscritto | spazio finale in più | identica |
| 14 | 69 | **bool → numero** | TRUE → 1 | invariato | **VERO → 1** | identica |
| 40 | nuove | invariato | invariato | riscritto | identico | identica |
| 9 | nuove | invariato | invariato | riscritto | spazio finale in più | identica |
| 27 | nuove | invariato | invariato | riscritto (costanti) | identico | — |
| 4 | nuove | invariato | invariato | riscritto (costanti) | spazio finale in più | — |

- Le 69 sono **tutte celle con formula** (testo della formula identico dopo LibreOffice).
- **55 perdite di dati del valore memorizzato**: la differenza è entro mezza unità della 15ª cifra
  significativa (due casi di pareggio, …055 → …06, arrotondati half-up), ma il double non è più
  quello del file. Non è una differenza di serializzazione.
- **14 cambi di tipo** (booleano → numero) con cambio anche della visualizzazione (VERO → 1).
- **80 riscritture del formato** senza cambio di valore: `"L." #.##0;-"L." #.##0` →
  `"L. "#.##0;"-L. "#.##0` (visualizzazione identica) e `#.##0;-#.##0` →
  `[$-409]#.##0_);(#.##0)`, che aggiunge uno spazio finale e mette i negativi fra parentesi
  (35 celle con testo visualizzato diverso, compresi 22 delle 69).
- **Con la lettura diretta: 0 differenze.** xlrd legge i 5 XLS esattamente come Excel (tipo,
  valore bit per bit, unioni, nomi dei fogli; `verifica_xlrd.py`: SOLVSAMP 883 celle, PROTTPLN
  1, registro.xls 36, budget.xls 13, legacy.xls 36), e il banco del §6 conferma il Markdown.

## 6. Verifiche

| verifica | esito |
|---|---|
| banco indipendente `compare_diretto.py`, 12 file (10 del confronto precedente e fixture, più SOLVSAMP.XLS e PROTTPLN.XLS di Office), riferimento Excel 16 | **12/12 PASS** in 4 processi nuovi: 2 sull'host, 2 container CPU `--network none` |
| ripetibilità | **12/12 Markdown byte-identici** fra le 4 esecuzioni, solo LF, nessun CR |
| gate rigoroso della sessione precedente (`strict_gate.py`, non modificato) | **PASS, exit 0** |
| xlrd contro Excel, 5 XLS autentici | identici cella per cella |
| test mirati sull'host (`test_intake_excel` 25, Docling, LibreOffice, staging, convert) | 144 passati, 3 saltati: LibreOffice reale assente sull'host (DOC/PPT) |
| suite completa, container CPU con Git, LibreOffice, Docling e Qdrant 1.19 dedicato **obbligatori** | **1449 passati, 0 falliti, 0 saltati** (JUnit `suite-container-final.xml`), 15 warning di deprecazione delle dipendenze, 152,5 s; `test_intake_excel` 25/25. Una prima esecuzione, prima del controllo preventivo sull'XML, aveva dato 1448/0/0 (`suite-container.log`) |
| preview: funzioni reali del template eseguite da Node (`tests/intake_excel_preview.cjs`) | passato: celle, pipe escapati, a capo, HTML della fonte non eseguito |
| upload → preview → approvazione in sandbox (TestClient, `docs/` e staging temporanei), XLS e XLSX | nella suite: preview uguale all'originale, in `docs/` entra **solo** il `.md`, frontmatter con motore e SHA, originale in staging |
| ruff sui file di questa sessione | pulito |
| `ruff check .` (come `scripts/ci.sh`) | 43 segnalazioni **preesistenti**, tutte negli script storici `eval/results/implementazione_migliorie_20260910` (9), `pilot_docling_20260908-170030` (28), `pilot_docling_standard_20260909-095127` (6) |
| lock | `uv lock --check --offline` ok |
| stato protetto dopo tutte le prove | **invariato**: 57 hash (`protected.after.json` = `protected.before.json`), `CURRENT` = `v20260910T121150`; working tree: solo questa cartella e le due fixture nuove in più, nessun file sparito (`status.after.txt`) |

Prima esecuzione del banco: 5 file segnalati (`host_a_banco_da_correggere/`). Esaminati uno per
uno: erano limiti del **mio oracolo**, non del convertitore. Excel in calcolo manuale legge come
testo vuoto una formula senza risultato memorizzato, che il contratto lascia vuota con avviso;
`Range.Value(10)` non restituisce una data per orari e durate (D5 = 0 → «00:00:00», B10 = 1,5 →
«36:00:00», ricostruibili esattamente dal formato elencato). Il banco ora esclude quelle formule
dalle attese ma **pretende** che compaiano nell'avviso, e riconosce orari e durate dal testo
visualizzato da Excel. Non è stata introdotta alcuna tolleranza sui valori.

Test nuovi o riscritti (`tests/test_intake_excel.py`), letti con un parser CommonMark reale:
ogni cella della fixture alla sua coordinata e nessuna in più (XLS e XLSX), stesso Markdown dai
due formati, riga Totale in 4 file (compresa la cache obsoleta 999 e la formula senza
risultato), etichetta in altra posizione, affiancate e sovrapposte con e senza tabelle
dichiarate, escape e testo letterale (pipe, a capo, markup, backslash, spazi di bordo, U+2028,
«null», «N/A», «0012»), CR e controlli, formule senza risultato, intervallo XFD1048576 senza
scansione del rettangolo, formattazione residua, limiti espliciti, workbook senza valori, XLS e
XLSX protetti, stream XLS corrotto, XML XLSX corrotto, XLS senza LibreOffice, determinismo,
upload/preview/approvazione. La fixture `casi_excel.xls/.xlsx` è stata scritta con valori noti
(`crea_fixture.py`) e salvata da Excel 16 (`salva_con_excel.ps1`).

**Prestazioni** (`prestazioni.py`, un processo nuovo per file, host a riposo, RSS del processo;
il processo con le librerie caricate parte da ~155 MB):

| file | byte | secondi | picco RSS MB | Markdown byte |
|---|---:|---:|---:|---:|
| SOLVSAMP.XLS (Office) | 197.120 | 0,042 | 157,8 | 54.227 |
| PROTTPLN.XLS (Office) | 18.432 | 0,011 | 157,0 | 1.099 |
| casi_excel.xls | 33.792 | 0,015 | 155,1 | 2.687 |
| casi_excel.xlsx | 15.159 | 0,026 | 157,2 | 2.687 |
| registro_excel.xlsx | 9.765 | 0,021 | 157,2 | 1.447 |
| sintetico 100k celle (`prestazioni.py --genera`) | 391.110 | 2,03 | 256,4 | 644.144 |
| sintetico 990k celle, sotto il limite di 1M | 3.674.612 | 19,70 | 1.113,3 | 6.410.358 |

Misure in `prestazioni.jsonl`; stessa uscita (SHA del Markdown) di prima del controllo
preventivo, che su 990k celle costa meno della variabilità misurata (19,2 → 19,7 s).

Riferimento della sessione precedente (RSS dell'albero, non direttamente confrontabile):
SOLVSAMP con LibreOffice 1,60 s / 430 MB (candidato), 1,92 s / 761 MB (baseline).

**CI GitHub non eseguita**: le modifiche non sono committate né pubblicate, nessun push. In
locale sono stati aggiornati il job `docker` (DOC e PPT via LibreOffice; XLSX e XLS diretti, riga
con celle vuote intera, stesso Markdown da XLS e XLSX della fixture) e il commento del job
`test`. L'immagine Docker non è stata ricostruita: container e suite usano l'immagine CPU del 10
settembre (xlrd 2.0.2 e openpyxl 3.1.5 presenti, verificati) con i sorgenti attuali montati in
sola lettura. Benchmark retrieval non rieseguiti: ricerca e indicizzazione non sono cambiate.

## 7. Comandi

```powershell
cd rag
.\.venv\Scripts\python.exe -B -m pytest tests/test_intake_excel.py -rs
node tests/intake_excel_preview.cjs
.\.venv\Scripts\python.exe -B eval/results/excel_fidelity_20260910/strict_gate.py
# Oracolo (Excel 16 sull'host) e banco, da rag/:
pwsh -File eval/results/excel_diretto_20260911/excel_oracle.ps1 -OutDir eval/results/excel_diretto_20260911/oracolo_excel -Files <file...>
.\.venv\Scripts\python.exe -B eval/results/excel_diretto_20260911/compare_diretto.py <OUT> <SOLVSAMP.XLS> <PROTTPLN.XLS>
.\.venv\Scripts\python.exe -B eval/results/excel_diretto_20260911/verifica_xlrd.py <oracolo...>.excel.json
python -B eval/results/excel_diretto_20260911/classifica_normalizzazione.py <orig>.excel.json <norm>.excel.json OUT.json
```

Container del banco: `docker run --rm --network none` con `core`, `rag_config.yaml`, `eval`,
`tests` e i due campioni Microsoft montati in sola lettura, immagine `vibecraft:cpu-20260910`
(da Git Bash serve `MSYS_NO_PATHCONV=1`, altrimenti `/samples/…` diventa un percorso Windows:
successo davvero alla prima prova, ripetuta). Suite: stessa procedura della sessione precedente
(immagine `vibecraft-excel-tests:20260910`, pytest montato da `tmp/excel-test-runtime`, poi
rimosso), con in più `pyproject.toml` e `uv.lock` montati; Qdrant e rete effimeri rimossi.

## 8. Limiti effettivi

- **Regola geometrica**: un valore isolato nella colonna che separa due tabelle le mette nello
  stesso intervallo (coordinate conservate, nessun dato perso); una colonna vuota in tutto il
  foglio *dentro* una tabella la divide in due intervalli (stessi numeri di riga, associazione
  ricostruibile). Tabelle impilate senza riga vuota formano un blocco. Due tabelle dichiarate
  adiacenti senza colonna vuota restano nello stesso intervallo: nomi e intervalli sono elencati.
- **Formati**: non applicati; percentuali, valute e zeri iniziali numerici si ricostruiscono
  solo dal codice elencato. Date e ore al millisecondo. XLSX con date fuori dall'intervallo di
  Excel: errore (openpyxl le sostituirebbe con `#VALUE!`); XLS: resta il seriale.
- **Formule**: XLS senza testo delle formule; un risultato memorizzato obsoleto non è rilevabile.
- **Unioni**: in un XLSX scritto da un programma, un valore in una cella non iniziale di
  un'unione (Excel non lo mostra) viene scartato da openpyxl; xlrd lo conserva.
- **Non riportati**: formattazione, convalide, formattazione condizionale, nomi definiti, righe e
  colonne nascoste (non segnalate), definizioni delle pivot; grafici, immagini e oggetti solo
  segnalati. Il Markdown non passa da `normalize_markdown`: NBSP e caratteri a larghezza zero
  delle celle restano come nel file.
- **Risorse**: due letture complete di openpyxl, ~1,1 GB a 990k celle; `_cells` è un attributo
  privato di openpyxl 3.1 (versione fissata nel lock, coperto da test).
- **Campione**: 12 file (2 di Microsoft, 4 salvati da Excel 16 nelle sessioni precedenti, 2 della
  fixture nuova, 4 scritti da openpyxl). Il verdetto vale per questi e per i casi dei test.
- Preview verificata con le funzioni reali del template e con l'API; nessun clic in un browser
  in questa sessione (il pannello non esegue pagine locali). Dockerfile: `libreoffice-calc`
  resta installato; toglierlo richiede una ricostruzione e una verifica di DOC/PPT.

## 9. File e rollback selettivo

Modificati da questa sessione: `rag/core/intake_excel.py` (riscritto), `rag/core/intake_convert.py`
(instradamento Excel, `LEGACY_FORMATS`, ripiego XLS e `_NOMI_MOTORI` rimossi, docstring),
`rag/core/config.py` (commento), `rag/pyproject.toml` e `rag/uv.lock` (xlrd), `rag/rag_config.yaml`
(commenti), `rag/templates/intake.unified.html` (preview Excel, etichetta del motore, testo),
`rag/tests/test_intake_excel.py` e `rag/tests/intake_excel_preview.cjs` (riscritti),
`rag/tests/test_intake_docling.py` (intestazione e un'attesa sull'avviso),
`rag/tests/test_intake_libreoffice.py` (docstring, tolti i tre test XLS via LibreOffice),
nuove fixture `rag/tests/fixtures/intake/casi_excel.xls` e `.xlsx`, `.github/workflows/ci.yml`,
`Dockerfile` (commento), `rag/README.md`, `rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`, questa
cartella. Dati: nessuno (corpus, staging, cataloghi, `CURRENT`, indice e storico invariati).

**Rollback** (mai reset/checkout del working tree sporco; nessuna reindicizzazione necessaria:
i documenti approvati sono `.md`):
- al **candidato** NON_APPLICARE: ricopiare i 10 file da `candidato_non_applicare/` (nome con
  `_` al posto di `/`, verificare `SHA256SUMS`), togliere la riga `xlrd` da `pyproject.toml` e
  rieseguire `uv lock --offline`, togliere le fixture `casi_excel.*`, ripristinare i commenti di
  `config.py` e del `Dockerfile` (`git diff` mostra le righe);
- alla **baseline Docling** (XLSX Docling, XLS → LibreOffice → Docling): `intake_convert.before.txt`
  sul convertitore, togliere `core/intake_excel.py` e i test Excel; le versioni dei test non
  tracciati precedenti al candidato non esistono più (§2);
- non esiste un interruttore di configurazione: di proposito, nessun ripiego verso percorsi con
  perdite note.
