"""Indicizzazione del codice generato (cartella code/) nel grafo della conoscenza.

Estrae i simboli (classi, funzioni, metodi, endpoint, componenti) dai file sotto
code/ e li collega ai documenti normativi con archi IMPLEMENTS calcolati per
similarità semantica, riusando lo stesso modello bge-m3 già caricato per l'indice.

Parser per linguaggio: stdlib `ast` per Python; tree-sitter (code_index_ts.py)
per TS/TSX/JS/JSX/Svelte, con le vecchie euristiche regex mantenute come fallback
d'emergenza dietro il flag `code_parsers.<lang>` in rag_config.yaml. HTML/CSS
restano nodi-file senza estrazione di simboli. Copre i linguaggi effettivamente
presenti nelle sottocartelle di code/ (backend, frontend, logicAgent): non esiste
(né è mai esistito) un parser Java/Quarkus/Kogito in questo repo.
"""

import ast
import re
from pathlib import Path

import numpy as np

# Estensioni considerate "codice sorgente" (allineate a quelle del check drift)
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".svelte", ".html", ".css",
             ".java", ".bpmn", ".bpmn2", ".dmn", ".cs", ".csproj"}
# File di progetto indicizzati per nome (non per estensione): dipendenze Java/.NET
CODE_FILENAMES = {"pom.xml", "build.gradle", "packages.config"}

_SNIPPET_LIMIT = 1500

# Pattern regex per i linguaggi in stile JS/TS (best-effort, non un parser completo)
_JS_PATTERNS = [
    ("function", re.compile(r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)")),
    ("class", re.compile(r"(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)")),
    ("function", re.compile(r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")),
]

_ENTITY_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_\-]{2,}")


def _snippet(text: str, node: ast.AST) -> str:
    seg = ast.get_source_segment(text, node)
    return (seg or "")[:_SNIPPET_LIMIT]


def _is_http_endpoint(node: ast.AST) -> bool:
    """True se la funzione ha un decoratore HTTP (es. @app.get, @router.post)."""
    for dec in getattr(node, "decorator_list", []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        attr = getattr(target, "attr", None) or getattr(target, "id", None)
        if attr and attr.lower() in ("get", "post", "put", "delete", "patch"):
            return True
    return False


def _py_symbols(text: str) -> list[tuple[str, str, str]]:
    """Estrae simboli Python (top-level + metodi di classe) via AST stdlib."""
    out: list[tuple[str, str, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "endpoint" if _is_http_endpoint(node) else "function"
            out.append((kind, node.name, _snippet(text, node)))
        elif isinstance(node, ast.ClassDef):
            out.append(("class", node.name, _snippet(text, node)))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "endpoint" if _is_http_endpoint(sub) else "method"
                    out.append((kind, f"{node.name}.{sub.name}", _snippet(text, sub)))
    return out


def _context_around(text: str, pos: int, span: int = 400) -> str:
    start = max(0, pos - 40)
    return text[start:start + span]


def _js_symbols(text: str, stem: str, suffix: str) -> list[tuple[str, str, str]]:
    """Estrae simboli JS/TS/Svelte con euristiche regex."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for kind, pattern in _JS_PATTERNS:
        for m in pattern.finditer(text):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            out.append((kind, name, _context_around(text, m.start())))
    if suffix == ".svelte":
        out.append(("component", stem, text[:_SNIPPET_LIMIT]))
    return out


# Linguaggio di configurazione (chiave di `code_parsers` in rag_config.yaml) per suffisso.
_PARSER_LANG = {
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".svelte": "svelte",
    ".java": "java",
    ".cs": "csharp",
}

# Default per linguaggio quando il flag è assente dal config: tree-sitter per i
# linguaggi migrati; il parser regex resta nel codice come fallback d'emergenza
# dietro flag (`code_parsers.<lang>: regex`).
# TODO(2026-07-12): rimuovere _js_symbols e i default "regex" alla prossima release,
# quando la migrazione tree-sitter sarà consolidata in produzione.
_PARSER_DEFAULTS = {"typescript": "treesitter", "javascript": "treesitter", "svelte": "treesitter",
                    "java": "treesitter", "csharp": "treesitter"}


def _parser_impl(lang: str) -> str:
    """Implementazione del parser per `lang`: "treesitter" (default per i linguaggi
    migrati) o "regex" (storica), scelta via `code_parsers.<lang>` in rag_config.yaml."""
    try:
        from core.config import CODE_PARSERS
        return CODE_PARSERS.get(lang, _PARSER_DEFAULTS.get(lang, "regex"))
    except Exception:
        return _PARSER_DEFAULTS.get(lang, "regex")


def _extract(suffix: str, text: str, stem: str, rel: str = "") -> list[tuple]:
    """Estrae i simboli di un file. Le tuple sono (kind, name, snippet) o
    (kind, name, snippet, meta) con meta={"deps": [...], "package": ...}."""
    if suffix == ".py":
        return _py_symbols(text)
    if suffix == ".java":
        # Unica implementazione (tree-sitter, nessun parser regex precedente):
        # il flag code_parsers.java esiste solo per uniformità di configurazione.
        from code_index_java import java_symbols
        return java_symbols(text, stem, suffix)
    if suffix == ".xml" and stem == "pom":
        from code_index_java import pom_symbols
        return pom_symbols(text, stem, suffix)
    if suffix == ".gradle":
        from code_index_java import gradle_symbols
        # il nome del progetto Gradle non è nel file: si usa la cartella che lo contiene
        project = rel.rsplit("/", 2)[-2] if rel.count("/") else ""
        return gradle_symbols(text, stem, suffix, project=project)
    if suffix in (".bpmn", ".bpmn2"):
        from code_index_java import bpmn_symbols
        return bpmn_symbols(text, stem, suffix)
    if suffix == ".dmn":
        from code_index_java import dmn_symbols
        return dmn_symbols(text, stem, suffix)
    # .NET (runtime-agnostico: identico su .NET Framework e Core/5+).
    # TODO(2026-07-12): Razor/.cshtml fuori scope (grammatica tree-sitter immatura,
    # servirà un parser dedicato stile svelte_symbols) e VB.NET non supportato.
    if suffix == ".cs":
        from code_index_csharp import csharp_symbols
        return csharp_symbols(text, stem, suffix)
    if suffix == ".csproj":
        from code_index_csharp import csproj_symbols
        return csproj_symbols(text, stem, suffix)
    if suffix == ".config" and stem == "packages":
        from code_index_csharp import packages_config_symbols
        project = rel.rsplit("/", 2)[-2] if rel.count("/") else ""
        return packages_config_symbols(text, stem, suffix, project=project)
    lang = _PARSER_LANG.get(suffix)
    if lang is not None and _parser_impl(lang) == "treesitter":
        # Svelte: la grammatica tree-sitter parsa il solo markup, ma il contenuto
        # degli <script> viene ri-parsato con la grammatica TypeScript, quindi il
        # test di equivalenza non mostra perdite rispetto al regex e la migrazione
        # è attiva anche qui (fallback: code_parsers.svelte: "regex").
        from code_index_ts import svelte_symbols, ts_symbols
        fn = svelte_symbols if suffix == ".svelte" else ts_symbols
        return fn(text, stem, suffix)
    if suffix in (".js", ".ts", ".tsx", ".jsx", ".svelte"):
        return _js_symbols(text, stem, suffix)
    if suffix == ".html":
        return [("template", stem, text[:_SNIPPET_LIMIT])]
    if suffix == ".css":
        return [("stylesheet", stem, text[:_SNIPPET_LIMIT])]
    return []


def collect_code_symbols(code_dir: Path) -> list[dict]:
    """Scansiona code/ e restituisce i simboli estratti, uno per elemento di codice."""
    symbols: list[dict] = []
    if not code_dir.exists():
        return symbols
    for path in sorted(code_dir.rglob("*")):
        if not (path.is_file() and (path.suffix in CODE_EXTS or path.name in CODE_FILENAMES)):
            continue
        rel = path.relative_to(code_dir).as_posix()
        dev_type = rel.split("/")[0] if "/" in rel else ""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for tup in _extract(path.suffix, text, path.stem, rel):
            kind, name, snippet = tup[0], tup[1], tup[2]
            meta = tup[3] if len(tup) > 3 else {}
            symbols.append({
                "id": f"{rel}::{name}",
                "name": name,
                "kind": kind,
                "file": rel,
                "dev_type": dev_type,
                "text": f"{kind} {name}\n{snippet}",
                "deps": sorted(set(meta.get("deps") or [])),
                "package": meta.get("package", ""),
            })
    return symbols


# Relazioni spec<->codice che dipendono dal CONTENUTO (versione) di un simbolo: vanno
# rimosse e ricalcolate quando il simbolo o lo spazio dei documenti cambia. NON toccano
# altri tipi di arco (es. MENTIONS doc->entità), che appartengono ai nodi-documento.
_CODE_LINK_RELATIONS = ("IMPLEMENTS", "REFERENCES", "DEPENDS_ON")


def add_symbol_nodes(G, symbols: list[dict]) -> None:
    """Inserisce (o aggiorna) i soli NODI di codice nel grafo, senza archi. Condiviso da
    full rebuild e incrementale: gli archi li calcola poi `link_symbols`."""
    for sym in symbols:
        attrs = dict(
            type="code",
            kind=sym["kind"],
            name=sym["name"],
            file=sym["file"],
            dev_type=sym["dev_type"],
        )
        if sym.get("package"):
            attrs["package"] = sym["package"]
        G.add_node(sym["id"], **attrs)


def embed_symbols(embed_model, symbols: list[dict]) -> np.ndarray:
    """Vettorializza (dense) il testo dei simboli. Restituisce una matrice [n x DENSE_DIM]
    allineata a `symbols` (vuota se non ci sono simboli)."""
    if not symbols:
        return np.zeros((0, 0), dtype=np.float32)
    out = embed_model.encode([s["text"] for s in symbols], batch_size=12, return_dense=True)
    return np.asarray(out["dense_vecs"], dtype=np.float32)


def _clear_code_link_edges(G, symbol_ids) -> None:
    """Rimuove dai simboli indicati i soli archi IMPLEMENTS/REFERENCES uscenti, così da
    poterli ricalcolare dalla versione corrente senza toccare il resto del grafo."""
    for sid in symbol_ids:
        if sid not in G:
            continue
        stale = [(sid, v) for _, v, d in G.out_edges(sid, data=True)
                 if d.get("relation") in _CODE_LINK_RELATIONS]
        G.remove_edges_from(stale)


def link_symbols(G, symbols: list[dict], sym_dense, doc_dense_vecs, doc_ids,
                 threshold: float = 0.45) -> int:
    """(Ri)calcola gli archi IMPLEMENTS (similarità dense verso il chunk-documento più
    simile) e REFERENCES (match deterministico sulle entità del glossario) per i `symbols`
    dati, che devono già essere nodi del grafo. Prima azzera i loro vecchi archi di questo
    tipo: è quindi idempotente e sicuro sia in full rebuild (grafo fresco) sia in
    incrementale (dove il simbolo/lo spazio-documenti può essere cambiato).

    Restituisce il numero di archi IMPLEMENTS creati."""
    if not symbols:
        return 0

    _clear_code_link_edges(G, [s["id"] for s in symbols])

    entity_nodes = {n for n, a in G.nodes(data=True) if a.get("type") == "entity"}
    for sym in symbols:
        for token in set(_ENTITY_TOKEN_RE.findall(sym["text"])):
            if token in entity_nodes:
                G.add_edge(sym["id"], token, relation="REFERENCES")

    # DEPENDS_ON: risoluzione best-effort per nome semplice (classe importata/iniettata,
    # artifactId, id di processo) verso gli altri nodi di codice del grafo. I nomi che
    # non risolvono (dipendenze esterne al progetto) vengono ignorati.
    name_to_id = {a["name"]: n for n, a in G.nodes(data=True)
                  if a.get("type") == "code" and a.get("name")}
    for sym in symbols:
        for dep in sym.get("deps") or []:
            target = name_to_id.get(dep)
            if target and target != sym["id"]:
                G.add_edge(sym["id"], target, relation="DEPENDS_ON")

    implements = 0
    sym_matrix = np.asarray(sym_dense, dtype=np.float32)
    if doc_ids is not None and doc_dense_vecs is not None and len(doc_ids) > 0 and sym_matrix.size:
        doc_matrix = np.asarray(doc_dense_vecs, dtype=np.float32)
        doc_norm = doc_matrix / (np.linalg.norm(doc_matrix, axis=1, keepdims=True) + 1e-8)
        sym_norm = sym_matrix / (np.linalg.norm(sym_matrix, axis=1, keepdims=True) + 1e-8)

        sims = sym_norm @ doc_norm.T  # [n_simboli x n_chunk-documento]
        best_idx = sims.argmax(axis=1)
        best_val = sims.max(axis=1)
        for i, sym in enumerate(symbols):
            if best_val[i] >= threshold:
                doc_id = doc_ids[int(best_idx[i])]
                if doc_id in G:
                    G.add_edge(sym["id"], doc_id, relation="IMPLEMENTS", weight=round(float(best_val[i]), 3))
                    implements += 1
    return implements


def add_code_graph(G, symbols: list[dict], embed_model, doc_ids: list[str],
                   doc_dense_vecs, threshold: float = 0.45) -> tuple[int, int]:
    """Aggiunge i nodi di codice al grafo e li collega ai documenti con archi
    IMPLEMENTS per similarità semantica (dense bge-m3), più archi REFERENCES
    deterministici verso le entità del glossario citate nel codice.

    Restituisce (numero_nodi_codice, numero_archi_implements)."""
    if not symbols:
        return 0, 0
    add_symbol_nodes(G, symbols)
    sym_dense = embed_symbols(embed_model, symbols)
    implements = link_symbols(G, symbols, sym_dense, doc_dense_vecs, doc_ids, threshold)
    return len(symbols), implements
