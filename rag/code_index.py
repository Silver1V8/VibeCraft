"""Indicizzazione del codice generato (cartella code/) nel grafo della conoscenza.

Estrae i simboli (classi, funzioni, metodi, endpoint, componenti) dai file sotto
code/ e li collega ai documenti normativi con archi IMPLEMENTS calcolati per
similarità semantica, riusando lo stesso modello bge-m3 già caricato per l'indice.

Rispetto all'articolo (che usa tree-sitter per Java/Svelte), qui si usa il modulo
stdlib `ast` per Python ed euristiche regex leggere per JS/TS/Svelte/HTML/CSS:
nessuna dipendenza esterna aggiuntiva, e copertura dei linguaggi effettivamente
presenti nelle sottocartelle di code/ (backend, frontend, logicAgent).
"""

import ast
import re
from pathlib import Path

import numpy as np

# Estensioni considerate "codice sorgente" (allineate a quelle del check drift)
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".svelte", ".html", ".css"}

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


def _extract(suffix: str, text: str, stem: str) -> list[tuple[str, str, str]]:
    if suffix == ".py":
        return _py_symbols(text)
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
        if not (path.is_file() and path.suffix in CODE_EXTS):
            continue
        rel = path.relative_to(code_dir).as_posix()
        dev_type = rel.split("/")[0] if "/" in rel else ""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for kind, name, snippet in _extract(path.suffix, text, path.stem):
            symbols.append({
                "id": f"{rel}::{name}",
                "name": name,
                "kind": kind,
                "file": rel,
                "dev_type": dev_type,
                "text": f"{kind} {name}\n{snippet}",
            })
    return symbols


def add_code_graph(G, symbols: list[dict], embed_model, doc_ids: list[str],
                   doc_dense_vecs, threshold: float = 0.45) -> tuple[int, int]:
    """Aggiunge i nodi di codice al grafo e li collega ai documenti con archi
    IMPLEMENTS per similarità semantica (dense bge-m3), più archi REFERENCES
    deterministici verso le entità del glossario citate nel codice.

    Restituisce (numero_nodi_codice, numero_archi_implements)."""
    if not symbols:
        return 0, 0

    entity_nodes = {n for n, a in G.nodes(data=True) if a.get("type") == "entity"}

    # Aggiunge i nodi di codice
    for sym in symbols:
        G.add_node(
            sym["id"],
            type="code",
            kind=sym["kind"],
            name=sym["name"],
            file=sym["file"],
            dev_type=sym["dev_type"],
        )
        # Archi REFERENCES deterministici: il codice cita un'entità del glossario
        for token in set(_ENTITY_TOKEN_RE.findall(sym["text"])):
            if token in entity_nodes:
                G.add_edge(sym["id"], token, relation="REFERENCES")

    implements = 0
    if doc_ids is not None and doc_dense_vecs is not None and len(doc_ids) > 0:
        doc_matrix = np.asarray(doc_dense_vecs, dtype=np.float32)
        doc_norm = doc_matrix / (np.linalg.norm(doc_matrix, axis=1, keepdims=True) + 1e-8)

        out = embed_model.encode([s["text"] for s in symbols], batch_size=12, return_dense=True)
        sym_matrix = np.asarray(out["dense_vecs"], dtype=np.float32)
        sym_norm = sym_matrix / (np.linalg.norm(sym_matrix, axis=1, keepdims=True) + 1e-8)

        sims = sym_norm @ doc_norm.T  # [n_simboli x n_documenti]
        best_idx = sims.argmax(axis=1)
        best_val = sims.max(axis=1)
        for i, sym in enumerate(symbols):
            if best_val[i] >= threshold:
                doc_id = doc_ids[int(best_idx[i])]
                if doc_id in G:
                    G.add_edge(sym["id"], doc_id, relation="IMPLEMENTS", weight=round(float(best_val[i]), 3))
                    implements += 1

    return len(symbols), implements
