# Verifica finale — Docling nell'intake, motori per formato, indice — 2026-09-10

Ramo `codex/docling-intake`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74` (invariato: nessun
commit, push, PR o merge). `AGENTS.md` assente (ricerca ricorsiva). Preservate le modifiche
preesistenti del manutentore (`rag/adr/README.md`, `golden_attribution.yaml`, `history.jsonl`,
parte di `.gitignore`) e la **rimozione dei 18 non-Markdown da `docs/`**: nessun file ripristinato.
Script, fixture e log di questa verifica sono in questa cartella; nessun documento di prova è
entrato nel `docs/` reale.

## 1. Problemi trovati e corretti

Ogni difetto è stato **riprodotto prima** di correggerlo, con un test sul codice reale.

| # | difetto | origine | come è stato riprodotto | correzione |
|---|---|---|---|---|
| 1 | `reject` fuori dal writer lock: un rifiuto arrivato durante un `approve` spostava in `rejected/` i file di un documento appena pubblicato | codice esistente | test di concorrenza (fallito) | `core/intake.reject` sotto writer lock, stato ricontrollato dentro |
| 2 | la raffinazione conclusa dopo un `approve` appendeva un record `staged` e **riapriva** il documento | codice esistente | test di concorrenza (fallito) | scrittura finale e journal di `core/intake_refine` sotto writer lock, con ricontrollo |
| 3 | **reindex ristretto (approve) dimenticava le cancellazioni non elaborate**: il manifest perdeva i documenti rimossi, i loro punti restavano in Qdrant, l'integrità diceva «ok» e nessuna sincronizzazione li vedeva più | codice esistente (`incremental_index` + `changed_paths`) | scenario in sandbox (tabella §7) e test di regressione (fallito) | `incremental_index` scrive nel manifest ciò che l'indice contiene: voci precedenti + sole modifiche elaborate |
| 4 | DOCX, PPTX, XLS, EPUB, MSG corrotti diventavano un «documento» fatto dei loro byte grezzi | MarkItDown (ripiego su testo) | confronto formati | controllo del contenitore (ZIP / firma OLE) → errore 422 chiaro |
| 5 | la rimozione dei link a immagini locali cancellava `![..](..)` anche dove è testo della fonte (TXT, blocchi di codice) | mio, sessione precedente | confronto formati | solo per i formati che producono asset, mai dentro un blocco di codice |
| 6 | MarkItDown scartava le immagini incorporate (data URI) senza avviso | codice esistente | test | avviso con il numero di immagini non incluse |
| 7 | XLSX: MarkItDown (pandas) svuota le celle «NA», «N/A», «null», scrive `7.0` e `NaN` | MarkItDown | confronto formati | XLSX instradato a Docling, un `##` per foglio dall'albero del documento |
| 8 | PDF protetto da password segnalato come «illeggibile o danneggiato» | mio | flusso API | messaggio esplicito «PDF protetto da password» |
| 9 | timeout di Docling riportato come «Markdown vuoto» | mio | timeout reale (0,05 s) | il motivo del fallback nomina il timeout |
| 10 | senza H1 il titolo del frontmatter ricadeva sul nome del file (Docling parte da `##`) | codice esistente | test | titolo di livello più alto presente |
| 11 | Linux: un titolo declassato a testo | immagine senza font | dump strutturale Windows/Linux (§3) | `fonts-liberation` nell'immagine |
| 12 | CI senza alcuna conversione Docling reale | workflow | lettura | pesi in cache verificati, `VIBECRAFT_REQUIRE_DOCLING=1`, smoke nell'immagine |

Controllato e **non** difettoso: le «figure» rilevate da Docling sul catalogo originale non
contengono testo (le sole parole del livello testo assenti dal Markdown sono l'arredo di
pagina); S2 usa `search_code_symbols` condiviso, conserva ordine e simboli non valutabili, a
0.0 non viene invocato (verificato byte per byte contro HEAD nella sessione precedente).

## 2. Confronto dei motori per formato

Fixture sintetiche generate da `scripts/confronto_formati.py` e `confronto_formati_2.py`, attese
scritte nel codice prima degli output, ciascun motore lungo il percorso reale dell'intake
(cleaner compreso). Output in `formati/` e `formati2/`. Nessun documento inviato a servizi remoti.

| formato | Docling 2.126.0 | MarkItDown 0.1.7 | scelta | motivo |
|---|---|---|---|---|
| MD | — | — | **nativo** | nessuna conversione |
| PDF digitale | 3/3 (tabella completa, titoli) | 2/3 (titoli persi; nel pilot 0/2 tabelle) | **Docling** | struttura |
| PDF scansione | 1/1 (OCR locale) | 0/1 (nessun testo) | **Docling** | solo Docling fa OCR |
| PDF misto | 2/2 | 1/2 | **Docling** | OCR solo sulle pagine senza testo |
| DOCX | 7/8 e 4/5 | 6/8 e 5/5 | **MarkItDown** | ambiguo: Docling meglio con stile Title e intestazione di tabella, peggio con titolo in Heading 1 (lo porta a `##`); si conserva il percorso attuale |
| PPTX | 4/6 | 5/6 | **MarkItDown** | conserva le note del relatore e la numerazione delle slide; entrambi appiattiscono il sottolivello |
| XLSX | 6/8 grezzo (nomi dei fogli persi); **7/8 per foglio** | 5/6 e 5/8 | **Docling per foglio** | MarkItDown altera i dati; unico limite residuo di Docling: le date escono con `00:00:00` |
| XLS | non disponibile (richiede LibreOffice) | 4/4 | **MarkItDown** | supporto |
| HTML UTF-8 | 8/8 | 8/8 | **MarkItDown** | pari |
| HTML latin-1 | 8/8 con meta charset, 0/1 senza (il backend decodifica in UTF-8) | 8/8 e 1/1 | **MarkItDown** | encoding |
| CSV `,` | 4/4 | 4/4 | **MarkItDown** | pari |
| CSV `;` latin-1 | errore | 2/2 | **MarkItDown** | robustezza |
| TXT | 1/3 (interpretato come Markdown) | 3/3 dopo la correzione #5 | **MarkItDown** | verbatim |
| EPUB | 4/4 | 4/4 | **MarkItDown** | pari |
| JSON, XML | non supportati (solo varianti USPTO/JATS/Docling) | 1/1 | **MarkItDown** | supporto |
| MSG | supportato dal backend email | percorso attuale | **MarkItDown** | **non verificato**: nessuno strumento locale sa scrivere un `.msg` |

Tempi mediani per conversione (dopo il caricamento): MarkItDown 0,018 s, Docling 0,017 s sui
formati d'ufficio; PDF Docling 3–7 s a documento. Memoria: il primo import di Docling costa
~550 MB di RSS, i convertitori PDF ~1,6 GB ciascuno. PDF protetto, DOCX/PPTX corrotti, XLSX
vuoto: errore chiaro in entrambi i percorsi dopo le correzioni. Quello che il Markdown non
rappresenta (immagini, grafici, diagrammi) è dichiarato negli avvisi, mai sostituito da un
segnaposto.

## 3. Windows e Linux

| prova | Windows x86_64 | Linux x86_64 (immagine CPU) |
|---|---|---|
| pacchetti, pesi, thread, BLAS | docling 2.126.0, torch `+cu126`, stessi SHA | docling 2.126.0, torch `+cpu`, stessi SHA |
| fixture PDF, senza font di sistema | titoli 4/4 | «Note operative» → testo (confidenza 0,58), tutte le confidenze 0,54–0,78 |
| con `fonts-liberation` | — | etichette uguali a Windows, confidenze 0,77–0,97; **Markdown identico byte per byte** |

La causa è la **conversione**, non la serializzazione: l'immagine slim non ha font, e i PDF con
font non incorporati venivano resi con un ripiego. Le confidenze restano diverse da Windows
(0,92–0,98): i risultati non sono dichiarati identici in generale, solo sulla fixture.
Non verificati: Linux aarch64, macOS arm64 (solo il job CI esistente di torch), immagine GPU.

## 4. Docker

- Build completa del target `cpu` da questo working tree: riuscita; immagine 5,39 GB; nessun
  pacchetto `nvidia-*` o `triton`; `torch 2.13.0+cpu`, `torchvision 0.28.0+cpu`; librerie OpenCV e
  `fonts-liberation` presenti.
- Nell'immagine: `import server, index`; pesi montati nel percorso previsto e verificati per
  SHA-256; conversione PDF digitale (con `#### Note operative`), scansione con OCR e XLSX su
  Docling, senza fallback (`docker/smoke/`).
- Avvio (`docker/avvio/`): rete, Qdrant e volume dedicati; indice costruito DENTRO l'immagine su un corpus ridotto (bge-m3 su CPU, cache dell'host in sola lettura), server avviato, `/api/health` 200 con chiave, upload di un PDF via API convertito da Docling senza fallback, preview, approvazione con reindex delta e promozione di versione. Risorse rimosse a fine prova.

## 5. CI

Configurata, **non eseguita su GitHub** (nessun push). Job `test`: librerie native, cache dei pesi
chiavata sugli hash di `core/intake_convert.py` e `scripts/docling_models.py`, download e
verifica con lo script (exit 1 se un peso manca o differisce), suite con
`VIBECRAFT_REQUIRE_QDRANT=1` e `VIBECRAFT_REQUIRE_DOCLING=1`. Job `docker`: stessa cache, poi
conversioni reali nell'immagine costruita. Verificato in locale: YAML valido; download **da
zero** alle revisioni fissate con SHA-256 corrispondenti (5/5, `pesi/`); lo script del passo
Docling eseguito nell'immagine (`docker/smoke/`).

## 6. S2 sulle risposte

`scripts/s2_risposte.py`: holdout (7 domande: codice, ponte specifica→codice, fattuali, multi-
documento, dato assente) — **non più un insieme mai visto** —, indice `v20260908T132451`,
qwen3.5:9b, temperatura 0,1, top_k 5, cache spenta, 3 passate. Risposte, contesti, codice e
fonti in `s2/s2_risposte.json`.

| soglia | risposte corrette |
|---|---|
| 0.0 | 21/21 |
| 0.35 | 21/21 |

Nessuna regressione: la soglia attiva resta 0.35. S2 non riguarda e non risolve `pdf-diag-3`.

## 7. Corpus e indice

Scenario in sandbox (codice copiato, `docs/`, `database/` e Qdrant dedicati, `indice/`):

| passo | prima della correzione #3 | dopo |
|---|---|---|
| `.md` approvati via intake | PDF 1+1 punti, integrità **ok** (falso) | PDF 1+1 punti, integrità **stale** |
| sincronizzazione | PDF 1+1 punti, restano per sempre | PDF **0+0**, nodi rimossi, 0 duplicati, integrità ok |

Stato reale prima della sincronizzazione: 40 file indicizzabili in `docs/`, manifest con 42;
codice invariato (196 file); piano **0 aggiunte, 0 modifiche, 2 rimozioni** (i due cataloghi
PDF rimossi dal manutentore, 1 punto ciascuno su 250). Backup verificato prima di scrivere:
`C:\Users\Silve\Desktop\vibecraft-index-backup-20260910-140113` (`database/` senza pesi, 50
file, SHA-256 confrontati; snapshot di tutte e 6 le collection versionate e degli alias).

Sincronizzazione: full rebuild su collection nuova, gate di valutazione attivo,
`VIBECRAFT_INDEX_KEEP=7` per non eliminare versioni. Esito: `v20260910T121150`, 248 chunk da 40
documenti, gate recall@2 0,828 ≥ 0,75, integrità OK non stale, alias allineato, 0 punti e 0
nodi dei PDF rimossi, 248 chunk = 248 punti, 0 duplicati, 7 versioni conservate, versione di
ritorno `v20260908T132451` recuperabile (manifest e collection con i suoi 250 punti).

Rimisura dopo la sincronizzazione (corpus cambiato: i numeri storici non sono la baseline):
golden PASS — recall@1 70,7%, recall@2 82,8%, recall@5 94,8%, MRR 0,811 (58 casi); multihop PASS — recall media A 0,854, B exact 6/6. Invariati rispetto alla misura precedente: i due PDF rimossi non erano fra le attese del golden. `history.jsonl` invariato (`--no-save`, hash prima/dopo).

Staging reale preparato per il manutentore, **non approvato**: `catalogo_diagrammi_normativi.pdf`
(`70c581550d3e`) e `catalogo_mockup_normativi.pdf` (`b180d8adb347`), rigenerati col template
corretto, convertiti con Docling senza fallback né avvisi.

## 8. Flusso completo

API (sandbox2, `e2e/e2e_api_v2.json`): Markdown nativo, PDF digitale, scansione, PDF misto,
XLSX (Docling), PPTX, DOCX, HTML latin-1, CSV, EPUB (MarkItDown) in staging; vuoto 422,
corrotto 422, DOCX rotto 422, PDF protetto 422, `.exe` 415, duplicato 409. Stesso documento
approvato due volte in contemporanea `[200, 409]`; due documenti sullo stesso nome
`[200, 409]`, il perdente approvato poi su un nome libero. `docs/` invariato prima dell'approve;
dopo, solo `.md`; originali con SHA-256 identico; nessun riferimento ad asset; punti Qdrant per
ogni nuovo documento. Timeout reale: fallback dichiarato. UI (sandbox2): upload dalla pagina
di XLSX, CSV, XLS, TXT, XML, JSON, HTML con motore corretto per riga; preview XLSX con fogli e
celle «NA»; approvazione e rifiuto; testo della pagina aggiornato. Il pannello Browser era
nascosto: le azioni sono state eseguite con le funzioni che i pulsanti invocano
(`openPreview`, `approveStaged`, `rejectStaged`), non con clic reali.

## 9. Test e lint

Suite completa finale con `VIBECRAFT_REQUIRE_QDRANT=1` e `VIBECRAFT_REQUIRE_DOCLING=1`:
**1408 passati, 0 falliti, 0 saltati** (`suite_finale_2.log`). La corsa precedente
(`suite_finale.log`) aveva 1 fallito: `test_archivio_dichiara_di_essere_storico_quando_lo_e`,
per il cambio di `CURRENT` dopo la sincronizzazione; corretto aggiornando `superseded_by`
(§7), senza toccare l'asserzione. Nuovi test: formati e contenitori (`test_intake_docling.py`), concorrenza di
reject/refine (`test_intake_staging.py`), manifest del delta ristretto
(`test_incremental_indexing.py`), generatore (`tmp/pdfs/test_build_file_catalogs.py`, 9/9 in
ambiente effimero). Ruff pulito sul codice da consegnare e sugli script di questa cartella;
restano 34 riscontri negli script sperimentali preesistenti `eval/results/pilot_docling_*` e 9 in due script di prova della sessione precedente (`implementazione_migliorie_20260910/scripts/`), non codice da consegnare.

**Scritture autentiche negli storici**: una riga in `rag/eval/results/history.jsonl`, scritta
dal gate di valutazione alla promozione della sincronizzazione (`2026-09-10T12:18:45Z`,
`v20260910T121150`, recall@2 0,828, `source: gate`); conservata. Aggiornato
`superseded_by` in `rag/eval/golden_attribution.yaml` alla nuova versione attiva, come
prescrive il file stesso (era la stessa riga già modificata dal manutentore dopo P0): senza,
`test_archivio_dichiara_di_essere_storico_quando_lo_e` falliva per il cambio di `CURRENT`.

## 10. File

Codice e configurazione: `rag/core/intake.py`, `rag/core/intake_convert.py`,
`rag/core/intake_clean.py`, `rag/core/intake_refine.py`, `rag/core/indexing.py`,
`rag/core/retrieval.py`, `rag/core/config.py`, `rag/api/routes_retrieval.py`,
`rag/rag_config.yaml`, `rag/templates/intake.unified.html`, `rag/pyproject.toml`, `rag/uv.lock`,
`rag/scripts/docling_models.py`, `Dockerfile`, `.github/workflows/ci.yml`, `.gitignore`,
`tmp/pdfs/build_file_catalogs.py`. Test: `rag/tests/test_intake_docling.py`,
`test_intake_staging.py`, `test_incremental_indexing.py`, `test_code_link_filter.py`,
`test_ask_unified_llm.py`, `test_torch_platform_pin.py`, fixture `tabelle_titoli.pdf`,
`tmp/pdfs/test_build_file_catalogs.py`. Documentazione: `rag/README.md`,
`rag/adr/NOTA_IMPLEMENTAZIONE_MIGLIORIE.md`, questo resoconto. Dati: `rag/eval/golden_attribution.yaml`
(una riga), `rag/eval/results/history.jsonl` (una riga, dal gate). Fuori dal repo: backup
`C:\Users\Silve\Desktop\vibecraft-docs-backup-20260910-100353` e
`C:\Users\Silve\Desktop\vibecraft-index-backup-20260910-140113`; pesi in
`rag/database/models/docling/` (esclusi da git); cataloghi rigenerati in `output/pdf/`.
Questa sessione e la precedente insieme: 23 file tracciati modificati (1772 righe aggiunte,
163 tolte), fra cui le modifiche preesistenti del manutentore.

## 11. Limiti e attività umane residue

- **Approvare o rifiutare** i due cataloghi in staging. Il loro «Percorso sorgente» indica la
  cartella del backup R.0, perché gli SVG non sono più in `docs/`; e gli SVG non sono un formato
  ammesso dall'intake. Rigenerarli dopo aver deciso dove vivono le sorgenti.
- CI mai eseguita su GitHub; job macOS invariato; immagine GPU e Linux aarch64 non verificati.
- MSG non verificato; DOCX resta su MarkItDown per esito ambiguo; date XLSX con `00:00:00`.
- Confidenze del layout diverse fra Windows e Linux anche con i font.
- 6 snapshot Qdrant creati da questa sessione restano anche dentro lo storage di Qdrant (oltre
  alle copie scaricate nel backup): si possono eliminare quando il backup non serve più.
- `pdf-diag-3` non affrontato.

## 12. Rollback

- **Indice**: `uv run --no-sync python -B index.py --rollback v20260908T132451` (versione e
  collection presenti); se una collection mancasse, ripristinarla dallo snapshot del backup.
- **S2**: `retrieval.code_link_min_question_score: 0.0`, riavvio.
- **Motori**: `intake.docling.enabled: false` riporta **PDF e XLSX** a MarkItDown (riavvio); per
  tornare al solo PDF su Docling, togliere `"xlsx"` da `DOCLING_FORMATS` in `core/intake_convert.py`.
- **Codice**: le correzioni 1–3 sono indipendenti; annullarle significa riaprire i difetti
  riprodotti dai rispettivi test.
- **Dipendenze**: copie pre-modifica in `../implementazione_migliorie_20260910/baseline/`.
- **Docker/CI**: le righe aggiunte in `Dockerfile` e `.github/workflows/ci.yml` sono isolate.
