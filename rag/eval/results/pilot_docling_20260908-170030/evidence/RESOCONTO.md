
## Pilot Docling e qualità dei PDF — 2026-09-08

**Verdetto: BLOCCATO.** Sei righe del cancello 1c su sette sono state misurate e
**nessuna di esse fallisce**: struttura, celle e sezioni sono superate in modo
netto, e il retrieval non perde nulla rispetto a P0. Il cancello resta però
chiuso per due motivi che non dipendono dalle misure riuscite: è comparso **un
valore fabbricato fuori dalle tabelle**, che il criterio di abbandono di 1c
nomina esplicitamente e che questa sessione non interpreta al posto del
manutentore; e la riga **attribuzione non è stata misurata**. Non è un
`NON_APPLICARE`: nessun criterio misurato è fallito.

Ramo `codex/evoluzione-p0`, HEAD `011e264c554895c651f0eba1dccb74bc4dc10f74`,
invariato. Nessun branch, commit, push o PR. `rag/pyproject.toml` e `rag/uv.lock`
verificati invariati (`git diff --quiet`). `AGENTS.md` non esiste nel repository:
ricerca ricorsiva ripetuta, conferma P0 e sessione 2. Preesistenti conservate:
`.gitignore`, `rag/adr/README.md`, `rag/eval/golden_attribution.yaml`,
`rag/eval/results/history.jsonl` (le righe preesistenti sono intatte; questa
sessione ne ha **appesa una** via `eval.run_multihop`, vedi sotto), e i non
tracciati `rag/adr/EVOLUZIONE.md`,
`rag/eval/results/p0_20260908-152239/`, `rag/eval/results/dep_docling_20260908-160000/`,
`skills-lock.json`, `tmp/`. Il venv `[vlm]` della sessione 2 **non è stato alterato**.

Artefatti: `rag/eval/results/pilot_docling_20260908-170030/`.

### Gli input sono gli stessi della baseline

SHA-256 confrontati con `doc_hashes` del manifest di P0 (`index.json`,
indice `v20260908T132451`): **identici**, nessun documento è cambiato.

| PDF | Byte | SHA-256 | vs baseline |
|---|---:|---|---|
| `…/diagrams/catalogo_diagrammi_normativi.pdf` | 4658 | `9c0d51c5…3c56f91f` | invariato |
| `…/mockups/catalogo_mockup_normativi.pdf` | 5312 | `443ecfca…a00aa1b2` | invariato |

I due percorsi di produzione, richiamati in memoria, **riproducono P0 alla cifra**:
loader 1300 / 1798 caratteri, 1 chunk documento-intero ciascuno con gli stessi
`chunk_id` dell'indice; MarkItDown 1612 / 1722 caratteri con SHA-256
`292006d5…6303971e` e `eeb54c8f…2d1d5aa246`, gli stessi registrati in 0.4.
La baseline è quindi confrontabile, non ricostruita a occhio.

### Prima verifica: Granite gira **senza** l'extra `[vlm]`

**Sì, ed è stato provato con una conversione reale, non con import.**

`uv pip compile` con `docling==2.126.0` (nessun extra) + `transformers==5.15.1`
risolve **162** pacchetti contro i 164 della sessione 2. Il `diff` fra i due file
di requisiti ha **esattamente due righe**, entrambe in meno:

```text
< av==18.1.0
< qwen-vl-utils==0.0.14
```

Nient'altro si muove: `docling-parse` resta 7.18.0, `transformers` 5.15.1,
`torch` 2.13.0+cu126, `torchvision` 0.28.0+cpu, `onnxruntime` 1.29.0,
`typer` 0.26.8 declassata. Venv isolato **fuori dal repository** nella scratchpad
di sessione; installazione **exit 0**; `uv pip freeze` **identico riga per riga**
alla risoluzione salvata. `importlib.util.find_spec` conferma `av` e
`qwen_vl_utils` **assenti dall'ambiente**, non solo non importati.

Poi la prova che serviva davvero — conversione dei due PDF con
`VlmPipeline` + `GRANITEDOCLING_TRANSFORMERS` su **CPU esplicita**:

```text
status              ConversionStatus.SUCCESS (entrambi i documenti)
av in sys.modules            False
qwen_vl_utils in sys.modules False
backend caricato    transformers.models.idefics3 (7 moduli)
```

**Le DLL GPL di `av` non sono sul disco affatto**, non «presenti ma inerti».
Il venv candidato scende da 5285 MB (sessione 2, con `[vlm]`) a **5155 MB**:
−130 MB, coerenti con `av.libs` 63 MB più il resto.

**L'extra non cambia l'output, ed è misurato.** Lo stesso script è stato eseguito
anche nel venv `[vlm]` della sessione 2 — riusato in sola lettura, senza
rimuovere nulla, per conservare il confronto riproducibile. I due ambienti
producono file **identici byte per byte**, sia in Markdown sia in DocTags:

```text
diagrammi  3c5be08127b52d023b92f2ac59872b1362c1d77de267b2180beb3a7aeb46756b   (novlm == vlm)
mockup     25af5e148c384a9a025fe3062f01244c6e53bde714904b9fc43c38925d9885f2   (novlm == vlm)
```

Non è un'inferenza dalla catena: sono due esecuzioni reali confrontate.

**Riproducibilità fra esecuzioni: verificata a parte.** La conversione è stata
**rieseguita nel venv senza `[vlm]`, con la revisione pinnata, in un processo
nuovo**. I tre insiemi di output — run 1 senza `[vlm]`, run 2 senza `[vlm]`,
run nell'ambiente `[vlm]` — sono **tutti byte per byte identici**, sia in
Markdown sia in DocTags:

| File | run 1 (no-vlm) | run 2 (no-vlm) | run `[vlm]` |
|---|---|---|---|
| `granite_diagrammi.md` | `3c5be08127b5…` | `3c5be08127b5…` | `3c5be08127b5…` |
| `granite_diagrammi.doctags.txt` | `fb32d5c16192…` | `fb32d5c16192…` | `fb32d5c16192…` |
| `granite_mockup.md` | `25af5e148c38…` | `25af5e148c38…` | `25af5e148c38…` |
| `granite_mockup.doctags.txt` | `e0ddb0058554…` | `e0ddb0058554…` | `e0ddb0058554…` |

Il punteggio del cancello si riproduce identico su run 2: **2/2 tabelle,
75/75 celle dati, 9/9 intestazioni**. Con `temperature=0.0` il determinismo era
atteso, ma finché non lo si misura resta un'assunzione: ora è un riscontro.

**Il pin della revisione è effettivo, e c'è una prova indipendente.** Nella cache
esiste **un solo snapshot**, quello di `982fe3b4…`, e **non esiste alcun file
`refs/main`**: il ref mobile non è mai stato risolto. Con `HF_HUB_OFFLINE=1`, se
Docling avesse usato il proprio default `main` la corsa sarebbe fallita — come in
effetti fallì al primo tentativo, quando lo snapshot era incompleto. La spec
espone `revision = 982fe3b4…` contro il default `main` di Docling.

*Nota sugli hash*: `granite_report_run2.json` riporta per il Markdown lo SHA-256
della **stringa in memoria** (LF), non del file su disco (CRLF su Windows). Non è
confrontabile con `sha256sum`; i valori della tabella sopra sono quelli dei file.
Per i DocTags il campo è invece calcolato sui byte del file e coincide.

Questa è la combinazione usata per il pilot. **Non risolve la forcella licenze**
del prerequisito 1 della sessione 2: la rimuove dal ramo Transformers, senza
dire nulla su altri percorsi.

### Ambiente e riferimento completo del modello

| Voce | Valore |
|---|---|
| Piattaforma | `x86_64-pc-windows-msvc`, CPython 3.14.6, uv 0.11.28 |
| Catena | file di requisiti a 162 pacchetti negli artefatti — **è quella** l'unità riproducibile, non `docling==2.126.0` |
| Modello | `ibm-granite/granite-docling-258M` @ **`982fe3b40f2fa73c365bdb1bcacf6c81b7184bfe`**, Apache-2.0 |
| Revisione | risolta oggi da `main`: **coincide** con quella registrata dalla sessione 2; passata esplicitamente, non lasciata al ref mobile |
| Peso | repo 529,9 MB; `model.safetensors` 515,1 MB; cache di sessione 506 MB |
| Pipeline | `VlmPipeline`, spec `GRANITEDOCLING_TRANSFORMERS`, `InferenceFramework.TRANSFORMERS`, `AUTOMODEL_IMAGETEXTTOTEXT`, risposta `DOCTAGS` |
| Opzioni | `scale=2.0`, `max_new_tokens=8192`, `temperature=0.0`, prompt `"Convert this page to docling."` |
| Acceleratore | `AcceleratorDevice.CPU`, `num_threads=4`; `torch.get_num_threads()=3` |
| torch | 2.13.0+cu126, `cuda_available=True` **ma non usata**: il difetto torchvision `+cpu` della sessione 2 resta non toccato |

### Verità di riferimento: i numeri della baseline reggono, ma erano incompleti

Le quattro pagine sono state renderizzate con pypdfium2 (scale 3, 1786×2526) e
**lette come immagini**, con ritagli 2× sulle celle ambigue. Il livello di testo
del PDF non è stato usato per costruire la verità.

**I 75/9 sono confermati**: registro diagrammi 5×4 = 20 celle dati + 4
intestazioni, registro mockup 11×5 = 55 + 5. Totale **75 celle dati, 9 di
intestazione, 2 tabelle**.

Due riscontri che la baseline non aveva registrato:

1. **Pagina 1 di entrambi i documenti contiene una terza struttura tabellare**,
   «Regole di organizzazione», 3×2 senza riga di intestazione. La formula «due
   tabelle» contava solo i registri di pagina 2. Misurata a parte: **non altera i
   criteri 75/9**, fissati prima di questa sessione.
2. **`diag_6_2_hitl_checkpoints.svg.svg` ha davvero due estensioni** nella fonte
   (verificato su ritaglio 2×). Normalizzarla a `.svg` conta come valore alterato.

Normalizzazioni **dichiarate prima della misura** (N1 soft-wrap di colonna,
N2 cella «Formato / peso» a due valori logici, N3 confronto letterale con
`Finalita` senza accento, N4 markup ignorato, N5 doppia estensione intoccabile).

### Confronto sui medesimi input

| Misura | Loader PDF attuale (pypdf) | Intake attuale (MarkItDown) | **Docling/Granite grezzo** | Granite + refine |
|---|---:|---:|---:|---:|
| Tabelle complete | **0/2** | **0/2** | **2/2** | **2/2** |
| Celle dati corrette | 0/75 | 0/75 | **75/75** | **75/75** |
| Celle di intestazione | 0/9 | 0/9 | **9/9** | **9/9** |
| Heading per documento | 0 | 1, dal nome file | **4**, tutti livello 2 | 5, di cui 2 inventati |
| Titoli inventati | 0 | 1 (`catalogo_…_normativi`) | **0** | 2 (`Scopo`, titolo alterato) |
| Contenuto fuori tabella | **12/12 e 12/12** | 12/12 e 10/12 | 12/12 e **8/12** | 9/12 e **5/12** |
| Arredo di pagina residuo | 3/3 | 3/3 | **0/3** | **0/3** |
| Domande PDF derivabili | **0/8** | **0/8** | **6/8** | **6/8** |

Nessuno dei due percorsi attuali produce una tabella: pypdf linearizza le celle
una per riga, MarkItDown emette per il solo registro diagrammi una riga di
intestazione corretta seguita da prosa e separatori spuri, e per il mockup
nemmeno quella. **I valori ci sono quasi tutti in entrambi; è l'associazione a
mancare**, ed è esattamente ciò che le domande misurano.

### I difetti del candidato, che le tabelle non mostrano

Fuori dai due registri, Granite ha prodotto tre alterazioni **verificate a
livello di DocTags**, quindi del modello e non dell'esportazione:

1. **Valore fabbricato.** Nella pagina 1 del mockup, dove la fonte ha la banda
   `11` / `4` / `SVG + HTML`, Granite emette
   `<code><loc_52><loc_142>…<_SQL_>REGOLE DI ORGANIZZAZIONE</code>`: una stringa
   in maiuscolo che **in quella forma non compare da nessuna parte nella pagina**,
   classificata come blocco di codice SQL. I tre valori reali **spariscono**.
2. **`interfacce` → `interface`** nel corpo di pagina 1 del mockup.
3. **`[schermata]` → `[schemata]`** nella prima regola del mockup.

Entrambi i percorsi attuali **conservano correttamente** `interfacce` e
`schermata`; pypdf conserva anche tutti i valori della banda. Su questa pagina
la baseline è più fedele del candidato.

Un quarto riscontro è **comune ai tre motori** e non è imputabile a Docling:
l'a-capo di colonna dentro i nomi di file sopravvive come spazio
(`diag_0_3_modules_relations_map .svg`). N1 lo perdona nel confronto, ma il
nome **non è utilizzabile alla lettera** a valle: viene dal livello di testo del
PDF, non dal parser.

### Refine: zero scarti, e contenuto perso lo stesso

Eseguito localmente con `core/intake_refine` e Ollama `qwen3.5:9b`,
`window_chars=5000` da `rag_config.yaml`, sull'output **grezzo** del candidato:

```text
diagrammi: {"windows":1,"windows_kept_raw":0,"windows_too_short":0,"windows_too_long":0,
            "chars_in":1582,"chars_out":1499,"elapsed_seconds":10.3}
mockup:    {"windows":1,"windows_kept_raw":0,"windows_too_short":0,"windows_too_long":0,
            "chars_in":2184,"chars_out":2131,"elapsed_seconds":15.6}
```

**0/2 finestre scartate, di nuovo** — e nel frattempo il refine ha **cancellato
l'intera banda KPI dei diagrammi** (`5`, `1`, `artefatti cartella sorgente
formato`), che nel grezzo c'era; ha **inventato** l'heading `Scopo` e i titoli
`Catalogo diagrammi normativi` e `Catalogo mockup normative` (la fonte dice
`Catalogo diagrammi` e `Catalogo mockup`); ha **inventato le intestazioni**
`# | Regola | Descrizione` per una tabella che nella fonte non ne ha. I due
registri sono invece **passati intatti**: 75/75 anche dopo il refine.

Questa è la dimostrazione operativa di 1d: contare gli scarti non misura la
fedeltà. Il premio previsto dal piano — **ottenere il parsing richiesto senza
ricorrere al refine** — è stato ottenuto: il grezzo vale già 75/75.

### Tempi, memoria, risorse

| Misura | Valore |
|---|---:|
| `import docling` | 6,91 s |
| Costruzione del `DocumentConverter` | 0,06 s |
| **1ª conversione** (diagrammi, 2 pagine) | **284,5 s** |
| 2ª conversione nello stesso processo (mockup, 2 pagine) | 290,6 s |
| Ripetizione su diagrammi, modello già caldo | **273,7 s** |
| Ripetizione su mockup | 301,2 s |
| **Caricamento iniziale, per differenza** | **≈ 11 s** su ~285 |
| RSS: avvio → dopo import → **picco** | 21,3 → 701,9 → **1756,0 MB** |
| Download pesi, prima volta | 103 s |

**Il caricamento non è il costo**: è l'inferenza. Circa **142 s per pagina** su
CPU, contro **0,1 s per documento** dei due percorsi attuali — un fattore
dell'ordine di **3000×**. Su questo corpus (4 pagine) sono ~19 minuti; la stessa
misura non si estrapola a un corpus grande senza rifarla, e la GPU non è stata
provata perché `torchvision` è la ruota `+cpu` (difetto della sessione 2, non
corretto qui: correggerlo tocca `[tool.uv.sources]`).

### Qdrant: caduto a metà sessione, tornato prima della fine

Per buona parte del pilot Qdrant **non ha risposto**: container `Up 7 hours` ma
senza porte pubblicate (`PortBindings` malformato `{invalid IP 6333}`, nessun
listener su 6333) e `/readyz` muto **anche dall'interno del container**.
`health-before.json` di P0 lo dava `true` alle 15:24. Questa sessione **non ha
avviato né arrestato alcun processo preesistente**; il riscontro dello stato
degradato resta in `logs/qdrant-stato.txt`.

Verso la fine della sessione è comparso un **secondo** container,
`vibecraft-qdrant-1`, con la porta correttamente pubblicata su
`127.0.0.1:6333` — **non avviato da questa sessione**. Da quel momento le righe
di retrieval sono tornate misurabili e **sono state misurate**, invece di
restare dichiarate impossibili.

### Retrieval generale: nessuna perdita rispetto a P0

Server RAG avviato **da questa sessione** (e arrestato alla fine), indice
`v20260908T132451`, 250 chunk, 935 nodi, 1305 archi — gli stessi di P0.
`eval.run` lanciato con `--no-save` e **senza** `--check-regression`:
`eval/results/history.jsonl` verificato **invariato** per hash e numero di righe
(134) prima e dopo quel comando.

**`eval.run_multihop` invece ha appeso una riga**, e va detto perché il file era
già modificato rispetto a git. Non ha un interruttore per evitarlo: la scrittura
dello storico è parte dichiarata del suo funzionamento (`eval/run_multihop.py:28`).
Il file è passato da **134 a 135 righe**. La riga aggiunta è
`{"timestamp":"2026-09-08T15:13:52…","source":"multihop","multihop_recall@10":0.8538961038961039,"multihop_graph_exact":1.0}`
— **identica nei valori** alla precedente: nessuna deriva, solo un secondo
campione della stessa misura. **Non è stata rimossa**: cancellare un record di
eval autentico per far tornare un'affermazione del resoconto sarebbe peggio
dell'averlo scritto. Le modifiche preesistenti del manutentore sono intatte;
questa riga è in coda, ed è attribuibile a questa sessione.

| Metrica | P0 | Pilot | Esito |
|---|---:|---:|---|
| recall@1 | — | 70,7 % | — |
| **recall@2** | **0,827586** | **0,828** | **invariata** |
| recall@5 | — | 94,8 % | — |
| source_in_top3 | — | 89,7 % | — |
| mrr | — | 0,811 | — |
| **multihop, recall media A** | **0,854** | **0,854** | **invariata** |
| **multihop, B exact** | **6/6** | **6/6** | **invariata** |
| gate `--assert-min 0.75` | PASS | **PASS** | invariato |

Il pilot **non tocca l'indice**, quindi il risultato atteso era proprio questo:
serve come prova che nulla è stato mosso, non come merito del candidato.

### Retrieval PDF: nessuna perdita, ma la misura è satura

Quattro collection **sperimentali** `pilot_docling_<motore>`, create con
`qdrant-client` direttamente. Nessun alias, nessuna promozione, nessun contatto
con `vibecraft_events*`. Chunking con il `chunk_markdown` **di produzione**;
embedder `BAAI/bge-m3` **su CPU**, per non sfrattare Ollama dagli 8 GiB.

**Portata dichiarata**: solo vettore **denso**. Niente sparse, niente ColBERT,
niente re-ranking di grafo, niente pesi di autorità. È un proxy più stretto
della riga come è formulata, e va letto come tale.

| Motore | Chunk | Fonte attesa in top-3 | Risposta ancorata nel top-3 |
|---|---:|---:|---:|
| Loader PDF (pypdf) | 2 | **8/8** | 8/8 |
| Intake (MarkItDown) | 2 | **8/8** | 7/8 |
| **Docling/Granite grezzo** | 8 | **8/8** | **8/8** |
| Granite + refine | 10 | **8/8** | 6/8 |

**La presenza delle fonti è identica fra baseline e candidata: nessuna perdita.**
La riga del cancello è soddisfatta nella sua richiesta letterale.

Ma va detto che cosa **non** dimostra. Con **due soli documenti** nella
collection, «la fonte giusta è nel top-3» è vera quasi per costruzione: la
misura è **satura** e non discrimina fra i motori, nello stesso senso in cui
l'harness di eval segnala da sé le proprie metriche sature. E i baseline
producono **un unico chunk per documento**: l'intero documento viene recuperato
in blocco, quindi «risposta ancorata» per loro è quasi automatica. Le due
perdite reali (MarkItDown senza `2.4`, refine senza `artefatti` e
`aree funzionali`) sono perdite **di contenuto** avvenute in conversione, non
fallimenti di recupero.

L'unico riscontro non banale: Granite segmenta in **4 chunk per documento**
invece di 1, e **resta 8/8** — la sezionatura non ha spezzato l'ancoraggio.

### L'attribuzione resta non misurata

La riga chiede «stesse domande e modello di risposta; schermo più lettura
umana». I due PDF **non sono nell'indice di produzione** (0 chunk, confermato in
0.4 e ancora oggi) e le collection sperimentali non sono collegate a `/ask`:
non esiste, senza costruirlo, un percorso che produca risposte attribuite su
queste otto domande. **Non le viene assegnato un PASS**, e non lo riceve per
analogia dalle righe vicine.

### Esito riga per riga del cancello 1c

| Riga | Esito | Riscontro |
|---|---|---|
| Tabelle complete | **PASS** | 2/2, righe e colonne corrette |
| Celle | **PASS** | 75/75 dati, 9/9 intestazioni, nessun valore inventato **dentro le tabelle**; normalizzazioni dichiarate prima |
| Sezioni | **PASS con riserva** | 4 heading per documento, corrispondenti alla segmentazione preregistrata, **0 inventati**; gerarchia però **appiattita** a un solo livello |
| Refine | **ESEGUITO E REGISTRATO** | 0 scarti su entrambi, ripetuto sugli output candidati; non usato come misura di fedeltà, e infatti ha perso contenuto |
| Retrieval PDF | **PASS, misura satura** | fonte attesa in top-3: **8/8 baseline = 8/8 candidata**, nessuna perdita; ma 2 documenti non discriminano |
| Retrieval generale | **PASS** | recall@2 0,828, multihop A 0,854, B exact 6/6 — **identici a P0**; `run_multihop` ha appeso una riga a `history.jsonl` (134→135), coi medesimi valori |
| Attribuzione | **NON MISURATO** | i PDF non sono nell'indice e le collection sperimentali non sono collegate a `/ask` |

Il criterio di abbandono dice `NON_APPLICARE` anche se «**compaiono valori
inventati**». Dentro le tabelle non ne compaiono. Fuori dalle tabelle **sì**: il
blocco `REGOLE DI ORGANIZZAZIONE` classificato come SQL, al posto di tre valori
reali. Le due letture — la riga «Celle», che è esplicitamente sulle celle, e la
clausola di abbandono, che non è qualificata — portano a esiti diversi. **La
scelta fra le due è del manutentore**, non di questa sessione, che si ferma al
riscontro e non riscrive il criterio dopo aver visto i numeri.

### Limiti

- **Una sola piattaforma**: Windows x86_64. Linux e macOS restano senza esecuzione.
- **Retrieval misurato solo sul vettore denso**, in collection sperimentali con
  due documenti: misura satura, non discriminante, e non è lo stack di produzione.
- **Attribuzione non misurata.**
- **Suite applicativa non eseguita** sotto la catena candidata: la catena
  candidata vive in un venv isolato e `pytest` gira contro quello dell'applicazione.
- **Quattro pagine, due layout, generati dallo stesso template.** Il risultato
  non autorizza una dichiarazione generale sulle tabelle complesse, né rende
  vere le percentuali di benchmark pubbliche.
- **GPU non provata**, per il difetto `torchvision +cpu` ereditato.
- La misura di completezza per token corti (`4`, `5`, `11`) è affidabile solo
  con confine di parola: la prima passata, più permissiva, è conservata negli
  artefatti accanto a quella corretta.

### Decisioni aperte e prerequisiti per la sessione 4

1. **Licenze**: la forcella della sessione 2 **si restringe** — senza `[vlm]` i
   binari GPL non entrano nemmeno su disco, e Granite gira lo stesso. Resta da
   decidere formalmente, ma l'opzione «rinunciare all'extra» ora ha una misura.
2. **La fabbricazione contro la clausola di abbandono**: decisione del manutentore.
3. **Attribuzione** e **suite applicativa sotto la catena candidata**: le due
   verifiche rimaste. Per l'attribuzione serve decidere *dove* indicizzare i PDF
   convertiti senza toccare la produzione. Da notare che i due container Qdrant
   ora coesistono (`qdrant` degradato, `vibecraft-qdrant-1` sano): va sistemato
   prima di misurare qualunque altra cosa.
4. **Costo di conversione**: 142 s/pagina su CPU. Prima di integrare, decidere se
   Docling è il motore di **default** o un motore **opt-in per i soli PDF con
   tabelle**, e se dirottare `torchvision` sull'indice CUDA — che è una modifica
   alle dipendenze applicative, non del pilot.
5. **F3 resta aperta** per macOS, invariata.

**Il PASS strutturale non autorizza la promozione.** L'integrazione applicativa
non è iniziata: nessun file di `core/`, `api/`, `rag_config.yaml`,
`pyproject.toml` o `uv.lock` è stato toccato.
