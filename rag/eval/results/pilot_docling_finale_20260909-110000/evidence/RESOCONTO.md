# Pilot Docling — candidato finale con gerarchia nativa — 2026-09-09

**Verdetto: BLOCCATO.** Tutti i criteri tecnici misurabili in questa sessione
sono **superati** — fedeltà, gerarchia, retrieval, risposte, suite,
compatibilità e licenze. Resta **una sola** verifica obbligatoria non
completabile da un agente: l'**attribuzione**, che il cancello 1c richiede
«schermo più **lettura umana**». Il pacchetto per quella lettura è pronto in
`review/PACCHETTO_REVISIONE.md`. Non è `NON_APPLICARE`: nessun criterio
misurato è fallito.

**Perimetro del verdetto:** il PASS che questa sessione prepara riguarda il
percorso su **documenti rigenerati con il template corretto**, non la
conversione affidabile dei PDF originali immutabili né di PDF esterni generici.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push o PR. `AGENTS.md` non esiste: ricerca
ricorsiva ripetuta e annotata.

## La soluzione concreta: uno stage nativo, non codice nostro

Il difetto residuo del pilot precedente era che **tutti i titoli uscivano H2**.
Prima di scrivere qualsiasi correzione ho cercato nel sorgente della versione
installata, come richiesto, e la soluzione esisteva già:
`docling/models/stages/heading_hierarchy/heading_hierarchy_model.py`, con
`HeadingHierarchyOptions` in `pipeline_options.py` e lo stage già cablato in
`StandardPdfPipeline` (righe 650 e 1044). **È disattivato per default**
(`enabled=False`) e `use_style` richiede `generate_parsed_pages=True`.

Assegna il rango con precedenza **bookmark → numerazione → stile** (dimensione
font, poi peso, corsivo, cassa). I nostri PDF non hanno né segnalibri né
numerazione: il segnale operativo è lo **stile**, cioè un'informazione
verificabile della fonte. Il template usa 25 / 16 / 11 pt: la gerarchia è
monotona nella dimensione.

Nessuna riga di codice aggiuntiva, nessuna regex sul Markdown, nessun LLM,
nessuna regola sui nomi dei file o sulle stringhe dei titoli.

Le **uniche due differenze** rispetto alla configurazione congelata del pilot
Standard sono dichiarate: `heading_hierarchy_options.enabled=True` e
`generate_parsed_pages=True`. Backend, pesi, opzioni tabellari e acceleratore
sono identici.

## Gerarchia: risolta e verificata separatamente da «nessun titolo inventato»

| | livello assegnato | atteso |
|---|---|---|
| `Catalogo diagrammi` / `Catalogo mockup` | **1** | titolo del documento |
| `Regole di organizzazione` | **2** | stesso rango di Registro |
| `Registro dei file` | **2** | stesso rango di Regole |
| `Percorso sorgente` | **3** | rango inferiore |

Identico su entrambi i documenti. In Markdown diventano `##` / `###` / `####`:
la gerarchia **relativa** è corretta: `docling-core` riserva `#` a `TitleItem` e
rende `SectionHeaderItem` di livello *N* come *N+1* cancelletti.

**Controllo eseguibile** — `scripts/check_hierarchy_rule.py`, tre assert, tutti
sul documento strutturato, tutti superati:

1. **Indipendenza dalle stringhe.** Su `fixture_gerarchia.pdf`, vocabolario
   estraneo ai cataloghi (*Manuale di manutenzione idraulica* / *Procedure di
   collaudo* / *Materiali ammessi* / *Nota di archiviazione*), la regola produce
   1 / 2 / 2 / 3. Un assert vieta esplicitamente il vocabolario dei cataloghi
   nella fixture.
2. **Ambiguità non risolta arbitrariamente.** Su `fixture_ambigua.pdf` due
   intestazioni con stile **identico** (*Temperature rilevate*, *Precipitazioni
   cumulate*) ricevono lo **stesso** livello 2. Se ne avesse ordinata una sopra
   l'altra, la gerarchia sarebbe inventata: l'assert fallirebbe.
3. **Ablazione.** Con `use_style=False` (e senza bookmark né numerazione) la
   gerarchia **collassa a un livello unico**. È la prova che il segnale
   operativo è lo stile della fonte, non un default fortunato.

## Input: nuovi, con hash propri

| | SHA-256 |
|---|---|
| diagrammi **originale** (corpus, non toccato) | `9c0d51c5…3c56f91f` |
| mockup **originale** (corpus, non toccato) | `443ecfca…a00aa1b2` |
| diagrammi **candidato** | `e34c1366…77cc542` |
| mockup **candidato** | `7725b280…4a2832b` |

`manifest/manifest_input_e_catena.json` tiene separati i due insiemi e un assert
del verificatore **fallisce** se il candidato legge per errore un originale.
Domande, risposte attese, celle, normalizzazioni N1–N5 e soglie sono **copiate
senza modifiche**: la correzione degli input non ha toccato i criteri.

## Fedeltà sui nuovi input — criteri congelati

Riusati i tre scorer del pilot Standard **senza modificarli** (`runpy`).

| Criterio | Esito |
|---|---|
| Tabelle del registro | **2/2** |
| Celle dati | **75/75** |
| Intestazioni tabellari | **9/9** |
| Domande derivabili dalla conversione | **8/8** |
| Titoli attesi presenti | **4/4** per documento |
| Titoli inventati | **0** |
| Gerarchia di rango | **corretta** (sopra) |
| Contenuto inventato | **nessuno** |
| `interfacce`, `[schermata]`, `11`, `4`, `SVG + HTML` | **tutti presenti** |
| Blocco SQL fabbricato da Granite | **assente** |
| Contenuto informativo fuori tabella | 12/12; i 3 mancanti sono **arredo** (testata e numeri di pagina), esclusi dall'export |

**Controllo visivo eseguito**: le quattro pagine candidate sono state
renderizzate e lette, e confrontate con il documento strutturato e il Markdown.

Un riscontro che il solo punteggio non mostra, e che va detto: **le tre coppie
KPI restano corrette e adiacenti, ma due condividono un paragrafo**. Il
Markdown rende `5 artefatti` da solo e poi `1 cartella sorgente SVG formato`
(analogamente `11 artefatti` / `4 aree funzionali SVG + HTML formati`). Nessun
valore è perso o alterato e nessuna coppia è rotta — è un raggruppamento di
reading-order, non un errore di associazione. Il criterio congelato è
soddisfatto; il fatto è registrato perché è visibile a valle.

I soft-wrap dei nomi in tabella (`diag_0_3_modules_relations_map .svg`) restano
quelli già tollerati da N1 e **comuni a tutti i motori**: vengono dal livello di
testo del PDF, non dal parser.

## Riproducibilità, tempi, memoria

Due esecuzioni in **processi nuovi, offline** (`HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`), stessi pesi locali. Markdown e JSON **identici byte
per byte**:

```text
candidate_diagrammi.md    ba3b282a6dc19bc9…      candidate_diagrammi.json  9298937f1944aaf0…
candidate_mockup.md       b90bd7656bb3ee57…      candidate_mockup.json     60d14e0214bb68a4…
```

Nessun campo variabile è comparso negli export; i due `run_report.json`
differiscono legittimamente solo per tempi e memoria.

| | run 1 | run 2 |
|---|---:|---:|
| init converter | 0,061 s | 0,061 s |
| diagrammi (2 pagine) | 13,462 s | 12,712 s |
| mockup (2 pagine) | 4,841 s | 4,178 s |
| **RSS picco** | **1588,0 MB** | **1588,9 MB** |
| RSS mediana | 910,0 MB | 895,9 MB |

**Metodo di memoria dichiarato:** campionamento continuo su thread separato,
intervallo 0,05 s (277 e 253 campioni). **Non** è un massimo osservato a pochi
checkpoint, come era invece la misura del pilot Standard precedente.

## Retrieval e attribuzione — pipeline applicativa completa

Due stack sperimentali **confrontabili**, che leggono lo **stesso corpus**
(42 documenti, con i due PDF **corretti** in entrambi) e gli **stessi parametri
calibrati**. Unica differenza: come vengono letti i PDF.

**Separazione dalla produzione, verificata:**

| | produzione | esperimento |
|---|---|---|
| Qdrant | `:6333` (container altrui, **mai toccato**) | `:6401`, container `vibecraft-pilot-qdrant` avviato da questa sessione |
| collection/alias | `vibecraft_events` | `pilot_baseline_events`, `pilot_candidate_events` |
| porte server | 8000 | 8101, 8102 |
| `database/`, `docs/` | repository | copie sandbox fuori dal repository |

Il container Qdrant preesistente risultava di nuovo senza porta pubblicata
(`PortBindings` malformato `{invalid IP 6333}`): **non l'ho riavviato né
rimosso**, come richiesto; ho avviato il mio.

L'unica differenza di codice fra i due stack è **14 righe** in `_read_pdf` della
**sola copia sandbox** del candidato, che legge la conversione Docling cercata
per SHA-256 del PDF (fuori da quei due hash resta `pypdf`).
`rag/core/chunking.py` del repository è verificato **invariato**.

| Misura | baseline (pypdf) | candidato (Docling) |
|---|---:|---:|
| recall@1 / **@2** / @5 | 70,7 % / **82,8 %** / 94,8 % | 70,7 % / **82,8 %** / 94,8 % |
| source_in_top3 / mrr | 89,7 % / 0,811 | 89,7 % / 0,811 |
| multihop: recall A / B exact | 0,854 / **6/6** | 0,854 / **6/6** |
| gate golden e multihop | PASS | PASS |
| **fonte attesa in top-10** (8 domande PDF) | **8/8** | **8/8** |
| **risposte con tutti i valori attesi** | **7/8** | **8/8** |
| chunk totali / chunk PDF | 250 / 2 | 250 / 2 |

Golden generale e multihop sono **identici fra i due stack e identici a P0**:
il golden non contiene i PDF, quindi il risultato atteso era proprio questo —
vale come prova di **non regressione**, non come merito del candidato.

Sul supplemento PDF il candidato **non perde nulla e migliora**: l'unica
risposta incompleta è del **baseline** (`pdf-diag-3`, manca `19.5 KB`). I ranghi
si muovono nei due sensi: candidato migliore su `pdf-mock-3` (2 contro 10),
peggiore su `pdf-diag-3` (5 contro 3).

Le risposte sono state prodotte dal **modello locale** configurato, con cache
disattivata (`VIBECRAFT_ASK_CACHE_SIZE=0`), e lette una per una contro le fonti.
Query, risposte, fonti con rango, chunk, versione indice e configurazione sono
in `out/eval_baseline.json` e `out/eval_candidate.json`.

### Perché l'attribuzione resta pendente

Il cancello chiede «schermo più **lettura umana**». Il giudice N3 archiviato non
è qualificato a certificare risposte nuove — 20/24 in-sample, non supera S6 — e
il prompt vieta di sostituirlo con un altro modello o un provider remoto per
aggirare il limite. **Una valutazione dell'agente non equivale a
un'approvazione umana**, quindi non attribuisco un PASS a questa riga.

Ciò che è stato fatto e che il revisore trova già pronto: verifica
**deterministica** (un `in` su file, nessun LLM) dei passi fra virgolette contro
i documenti del corpus, e la mia lettura puntuale. Due punti che meritano
l'occhio del manutentore:

- `pdf-diag-4`, candidato: il dato è corretto ma la risposta attribuisce
  `1 cartella sorgente SVG formato` alla sezione «Regole di organizzazione»,
  mentre nella fonte è la banda KPI.
- `pdf-mock-3`, entrambi: la risposta descrive la schermata con dettagli che
  vengono da un documento di specifica, non dal registro del catalogo.

Pacchetto: `review/PACCHETTO_REVISIONE.md`.

## Suite, lint, integrità, compatibilità

**Suite sotto la catena candidata**, su codice applicativo **non modificato**,
con Qdrant obbligatorio: **1339 passati, 3 falliti**. Per separare la causa ho
eseguito la **stessa** suite, nello **stesso** sandbox, sotto la catena
**applicativa**: **stessi 3 fallimenti**. Non sono causati da Docling — sono
artefatti dello stato sperimentale:

- `test_index_rollback_local_failure…`: il sandbox ha **una sola** versione
  d'indice, quindi il rollback non ha una precedente (409 invece di 404);
- `test_reconciler_never_writes…`: il test è accoppiato a `COLLECTION_NAME` e
  cerca `vibecraft_events__v1/v2`, che nel sandbox non esistono;
- `test_archivio_dichiara_di_essere_storico…`: `golden_attribution.yaml` dichiara
  `superseded_by: v20260908T132451`, cioè l'indice di **produzione**, mentre il
  CURRENT del sandbox è `v20260909T091355`.

Altri controlli: `ruff check` sugli script sperimentali **pulito**;
`index.py --check-integrity` sullo stack candidato **exit 0**.

**Compatibilità.** `torch 2.13.0+cu126` e i marker CUDA di `[tool.uv.sources]`
**invariati**; `onnxruntime 1.29.0` e `transformers 5.15.1` invariati; ranking e
parametri calibrati **non toccati** (`rag_config.yaml` del repository invariato;
nel sandbox differisce per la **sola** riga `collection_name`). L'aggiunta del
gruppo dev all'ambiente sperimentale ha introdotto **solo** `pytest 9.1.1`,
`ruff 0.16.6`, `iniconfig 2.3.0`: nessuna versione preesistente è cambiata.

**Licenze dei pesi effettivamente usati** — e qui il quadro **migliora**
rispetto alle sessioni precedenti:

| Peso | Revisione | Licenza |
|---|---|---|
| `docling-project/docling-layout-heron` | `8f39ad3c…` | **apache-2.0** |
| `docling-project/docling-models` (TableFormer ACCURATE) | `fc0f2d45…` | **cdla-permissive-2.0** |

**Granite non è usato da questo candidato**, e la catena resta quella **senza
`[vlm]`**: i binari GPL di `av` non sono nemmeno su disco. La forcella licenze
aperta dalla Sessione 2 **non si applica** a questa configurazione.

**Piattaforme.** Risoluzione, disponibilità wheel e test nativi restano tre cose
distinte: i test nativi sono stati eseguiti **solo** su `x86_64-pc-windows-msvc`.
Linux e macOS hanno risoluzione e wheel dalla Sessione 2, **non** esecuzione, e
non vanno riportati come verificati. I due pesi aggiunti sono file di modello,
non estensioni native: non introducono vincoli di piattaforma nuovi.

## Esiti storici conservati

- **Granite** (`pilot_docling_20260908-170030`): contenuto inventato →
  `NON_APPLICARE`, esito **conservato**, non riclassificato.
- **StandardPdfPipeline sui PDF originali** (`pilot_docling_standard_20260909-095127`):
  falso titolo `SVG + HTML` e associazioni KPI perse → `NON_APPLICARE`, esito
  **conservato**. Questa sessione non lo ribalta: cambia gli **input**.

## Scritture fuori dagli artefatti

Nessuna. `eval.run` e `eval.run_multihop` sono stati eseguiti **dai sandbox**,
quindi hanno scritto nei loro `eval/results` isolati; `history.jsonl` del
repository è verificato **invariato**. Nessun contatto con l'alias, le
collection o gli artefatti dell'indice di produzione.

## Cosa manca per il PASS

**Una sola cosa: la lettura di attribuzione del manutentore**, su
`review/PACCHETTO_REVISIONE.md`. Se quella lettura non rileva nuove attribuzioni
errate nel campione, tutti i criteri obbligatori applicabili risultano superati
e il verdetto diventa PASS **nel perimetro dichiarato in testa**.

## Se il verdetto diventerà PASS, andrà implementato

1. **Il template corretto** in `tmp/pdfs/build_file_catalogs.py`, la
   rigenerazione dei due cataloghi e una **nuova baseline con i nuovi hash**
   prima di qualunque cancello successivo.
2. **Docling come secondo motore**, con `StandardPdfPipeline`,
   `heading_hierarchy_options.enabled=True` e `generate_parsed_pages=True`,
   backend `ThreadedDoclingParseDocumentBackend`, pesi pinnati alle revisioni
   sopra, CPU, catena **senza `[vlm]`**.
3. **Gli interruttori già previsti dal piano**: `intake.conversion_engine` e
   `retrieval.pdf_conversion_engine`, con MarkItDown e pypdf che restano
   disponibili e il motore effettivo registrato nei log.
4. **La dipendenza applicativa**: aggiungere Docling a `pyproject.toml`/`uv.lock`
   con il file di requisiti congelato, non con `docling==2.126.0`.
5. **Il difetto `torchvision +cpu`** della Sessione 2 resta aperto: irrilevante
   finché il motore gira su CPU, da decidere prima di qualunque uso GPU.
