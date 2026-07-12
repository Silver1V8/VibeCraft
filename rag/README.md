# rag/ — Console HARO Graph-RAG

Indicizzazione (core/indexing), retrieval ibrido e pipeline Explore → Canvas →
Propose (core/) esposti via FastAPI (api/). Entrypoint: `server.py`, `index.py`.

## Code index: aggiungere un nuovo linguaggio

L'estrazione dei simboli dal codice generato (`code/`) vive in
[code_index.py](code_index.py); i parser tree-sitter in
[code_index_ts.py](code_index_ts.py). L'interfaccia di un parser è una
funzione `(text: str, stem: str, suffix: str) -> list[tuple[kind, name, snippet]]`
dove `kind` è ad es. `function`/`class`/`component`, `name` è univoco nel file
e `snippet` è il contesto testuale usato per l'embedding (max ~1500 char).

Per aggiungere un linguaggio:

1. **Grammatica** — aggiungi il wheel della grammatica con `uv add
   tree-sitter-<lang>` (o usa `tree-sitter-language-pack`, già in dipendenza,
   se il wheel singolo non esiste: `get_parser("<lang>")`). Niente
   compilazione manuale: solo wheel precompilati.
2. **Parser** — implementa in `code_index_ts.py` una funzione con
   l'interfaccia sopra. Per linguaggi C-like spesso basta estendere
   `_DECL_KINDS`/`_walk_symbols`; per formati contenitore (vedi
   `svelte_symbols`) localizza i blocchi di codice con la grammatica del
   formato e ri-parsa il contenuto con la grammatica del linguaggio interno.
3. **Dispatch** — in `code_index.py` registra l'estensione in `CODE_EXTS`,
   mappa suffisso → linguaggio in `_PARSER_LANG`, imposta il default in
   `_PARSER_DEFAULTS` e aggiungi il ramo in `_extract`. Il flag
   `code_parsers.<lang>` in [rag_config.yaml](rag_config.yaml) permette di
   tornare a un'eventuale implementazione alternativa senza deploy.
4. **Test di equivalenza** — estendi
   [tests/test_ts_parser_equivalence.py](tests/test_ts_parser_equivalence.py)
   con un corpus del linguaggio: se sostituisci un parser esistente, il nuovo
   deve estrarre almeno tutti i simboli del vecchio (zero `persi`).

I parser regex storici (`_js_symbols`) restano come fallback d'emergenza
dietro flag; TODO datato in `code_index.py` per la loro rimozione.
