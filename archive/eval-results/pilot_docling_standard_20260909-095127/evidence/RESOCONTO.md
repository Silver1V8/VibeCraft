# Pilot Docling StandardPdfPipeline — 2026-09-09

**Verdetto: NON_APPLICARE.** Esperimento isolato completato fino al primo criterio di abbandono; nessuna integrazione applicativa eseguita.

## Perimetro e integrità

- Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`; `AGENTS.md` assente.
- Modifiche preesistenti preservate. Nessun branch, commit, push, PR, modifica a corpus/configurazione/dipendenze/codice/indice di produzione.
- Input SHA-256 invariati rispetto al pilot precedente: diagrammi `9c0d51c52710efbd87aaf8599d7bde09e93ceefbdc206ad35c311d993c56f91f`; mockup `443ecfca8c8ab4fb706bf518c725e80272e52dfdc4b75b6759fb7d04a00aa1b2`.
- Verità e 8 domande copiate senza modifiche da `pilot_docling_20260908-170030/truth/`; restano N1–N5, inclusa la doppia estensione.

## Catena effettiva

Ambiente isolato senza `[vlm]` della Sessione 3: CPython 3.14.6; Docling 2.126.0, docling-core 2.95.0, docling-ibm-models 4.0.2, docling-parse 7.18.0, onnxruntime 1.29.0, torch 2.13.0+cu126. Freeze completo in `dependencies-freeze.txt`.

- Pipeline: `docling.pipeline.standard_pdf_pipeline.StandardPdfPipeline`.
- Backend PDF esplicito: `docling.backend.docling_parse_backend.ThreadedDoclingParseDocumentBackend`.
- Layout effettivo: engine Transformers, `docling-project/docling-layout-heron`, `main` risolto a `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8`; `model.safetensors` SHA-256 `00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c` (171,658,996 byte).
- TableFormer: `docling-project/docling-models`, tag `v2.3.0` risolto a `fc0f2d45e2218ea24bce5045f58a389aed16dc23`; variante ACCURATE, SHA-256 `2a7d6c924b3cd12fb99a09280ca9c33a89c5d60b93253617d2e088c1a40374d9` (212,758,388 byte).
- Il downloader layout ha conservato anche l'alternativa ONNX `40bde044036bb181c130ddf6c51792187268748f`, ma non è il motore effettivo: SHA-256 `59c81a3a2923042d85034ffc487f8f47e4854117e879aef89b2b9f728fb4922a`.
- Opzioni effettive: OCR false, table structure true, backend text forzato, TableFormer ACCURATE con cell matching, CPU/4 thread, code/formula/picture description/picture classification false, remote services false. Il dump completo è in `run2/run_report.json`; il campo base `table_structure_options` serializza `{}`, quindi lo script registra separatamente tipo, mode e `do_cell_matching` effettivi.
- Nessun Granite, VLM o refine usato. Le opzioni inattive mantengono spec di default nel dump, ma i relativi stage sono disabilitati.

## Fedeltà

| Misura | pypdf | MarkItDown | Granite grezzo | StandardPdfPipeline |
|---|---:|---:|---:|---:|
| Tabelle del cancello | 0/2 | 0/2 | 2/2 | **2/2** |
| Celle dati corrette | 0/75 | 0/75 | 75/75 | **75/75** |
| Intestazioni corrette | 0/9 | 0/9 | 9/9 | **9/9** |
| Frammenti fuori tabella, diagrammi | 15/15 | 15/15 | 12/15 | **12/15** |
| Frammenti fuori tabella, mockup | 15/15 | 14/15 | 9/15 | **12/15** |
| Domande derivabili | 0/8 | 0/8 | 6/8 | **6/8** |

I tre frammenti mancanti per documento sono arredo (`Vibecraft - inventario normativo`, `Pagina 1`, `Pagina 2`), non contenuto informativo. Standard conserva `interfacce`, `[schermata]`, `11`, `4`, `SVG + HTML`, entrambe le bande KPI e non contiene il blocco SQL inventato da Granite. Tuttavia:

1. `SVG + HTML` viene promosso a H2 nel mockup: heading non presente nella segmentazione umana preregistrata, quindi fallisce il criterio “nessun titolo inventato”.
2. Le bande KPI sono linearizzate (`11`, `4`, poi etichette; analogo nei diagrammi), perdendo l'associazione esplicita valore-etichetta: le due domande KPI non sono derivabili secondo la regola congelata.
3. Il Markdown introduce spazi interni da soft-wrap (`Autenticazion e`, `dashb oard`, `.sv g`); N1 li tollera e lo scoring cella-per-cella resta 75/75, ma l'output letterale non è adatto come nome file senza normalizzazione dichiarata.

Non sono emersi contenuti testuali fabbricati equivalenti al blocco SQL di Granite; il fallimento è di gerarchia e associazione.

## Riproducibilità, tempo e memoria

Entrambe le esecuzioni sono processi nuovi e offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) con lo stesso `artifacts_path`. Markdown e JSON strutturati sono identici byte per byte tra run 1 e run 2:

- diagrammi Markdown `a7c87149c2171f19f50e759e4e48373365f9c1b91e075b0c019440b50c6eb6c9`; JSON `3afecc2eef1472955e23c9e886bd909e97df7a5f07c3bd22b2704038c9b10b86`;
- mockup Markdown `4f5ede6cbddbbcfe91bbe2cc9f2af687055a931e1ff4958dee73498957fafd53`; JSON `3e1ce1be6a83c34a6c0ccf8bfd708bbc6a562d13cb76669b0f107789c8d3c7ce`.

Nessuna normalizzazione del JSON è servita e non sono comparsi campi variabili negli originali esportati. I report di esecuzione differiscono legittimamente per tempi/RSS.

| Processo | diagrammi (2 pagine) | mockup (2 pagine) | init converter | RSS massimo osservato |
|---|---:|---:|---:|---:|
| run 1, pesi freddi nel processo | 38.301 s (19.151 s/pag.) | 5.530 s (2.765 s/pag.) | 0.068 s | 1,391.7 MB |
| run 2, nuovo processo/cache OS calda | 12.266 s (6.133 s/pag.) | 4.043 s (2.021 s/pag.) | 0.062 s | 1,387.7 MB |
| Granite archiviato | 284.5 s | 290.6 s | 0.06 s | 1,756.0 MB |

L'RSS è il massimo osservato ai checkpoint dello script, non un campionamento continuo del vero picco; il criterio era già fallito e non è stata aggiunta una terza corsa solo per raffinare questa misura.

## Cancello e controlli fermati

Il criterio 1c impone `NON_APPLICARE` se falliscono sezioni/struttura/celle o compaiono valori inventati. Struttura e celle passano; sezioni e 8/8 domande no. Come richiesto, ci si è fermati prima delle verifiche costose non più necessarie alla decisione.

- Retrieval PDF: non eseguito; sola derivabilità conversionale 6/8.
- Retrieval golden generale: non eseguito.
- Attribuzione con modello di risposta: non eseguita.
- Suite applicativa/Qdrant: non eseguita; nessun endpoint, alias, indice o collection interrogato o modificato.
- Nessun container o processo persistente avviato; nessuna collection sperimentale rimasta.
- Nessuna verifica Linux/macOS o audit licenze completo aggiuntivo: il fallimento di fedeltà chiude già questa configurazione.

Inventario completo, dimensioni e SHA-256: `artifact_inventory.json`. Script minimi: `run_standard.py`, `score_standard.py`, `score_testo.py`, `score_domande.py`.
