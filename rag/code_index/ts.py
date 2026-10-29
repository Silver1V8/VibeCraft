"""Parser tree-sitter per i linguaggi frontend (TypeScript/TSX, JavaScript/JSX,
Svelte) — unica implementazione: il vecchio parser regex (`code_index._js_symbols`)
è stato rimosso (A12, 2026-09-03) dopo 53 giorni senza incidenti dalla migrazione.

Espone la stessa forma di ritorno di quel parser — lista di tuple (kind, name,
snippet) — invocata direttamente da `code_index._extract` per i suffissi
.ts/.tsx/.js/.jsx/.svelte. Python resta su stdlib `ast` (già un parser vero),
HTML/CSS restano nodi-file senza simboli.

Svelte: la grammatica tree-sitter-svelte parsa solo il markup e lascia il
contenuto di <script> come `raw_text`; qui il blocco script viene ri-parsato
con la grammatica TypeScript (che accetta anche JS), così i simboli dello
script sono estratti con un AST vero invece che con regex sull'intero file.
"""

import re

from tree_sitter import Language, Parser
import tree_sitter_javascript as _tsjs
import tree_sitter_typescript as _tsts
from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

_LANGUAGES = {
    ".ts": Language(_tsts.language_typescript()),
    ".tsx": Language(_tsts.language_tsx()),
    ".js": Language(_tsjs.language()),
    ".jsx": Language(_tsjs.language()),
}

# Nodi il cui campo `name` identifica direttamente un simbolo top-level o annidato.
_DECL_KINDS = {
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "class_declaration": "class",
}

# Valori di un variable_declarator che rendono la variabile una "funzione"
# (il regex copriva solo `const nome = (...) =>`; qui anche function expression).
_FN_VALUE_TYPES = {"arrow_function", "function_expression", "generator_function"}


def _context_around(src: bytes, start_byte: int, span: int = _CONTEXT_SPAN) -> str:
    begin = max(0, start_byte - 40)
    return src[begin:begin + span].decode("utf-8", errors="ignore")


def _decl(node):
    """(kind, nodo-nome) se `node` dichiara un simbolo, altrimenti None."""
    kind = _DECL_KINDS.get(node.type)
    if kind is not None:
        name_node = node.child_by_field_name("name")
        return (kind, name_node) if name_node is not None else None
    if node.type == "variable_declarator":
        name_node = node.child_by_field_name("name")
        value_node = node.child_by_field_name("value")
        if (name_node is not None and name_node.type == "identifier"
                and value_node is not None and value_node.type in _FN_VALUE_TYPES):
            return "function", name_node
        return None
    if node.type in ("function_expression", "generator_function"):
        # function expression nominata (`const f = function nominata() {}`):
        # il regex la vede tramite `function\s+nome`, quindi la emettiamo anche qui
        name_node = node.child_by_field_name("name")
        return ("function", name_node) if name_node is not None else None
    return None


def _walk_symbols(src: bytes, lang: Language) -> list[tuple[str, str, str]]:
    """Estrae (kind, name, snippet) da sorgente JS/TS con la grammatica data.
    Come il parser regex: dedup per nome (vince la prima occorrenza) e snippet
    di contesto attorno alla dichiarazione."""
    tree = Parser(lang).parse(src)

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(kind: str, name_node, decl_start: int) -> None:
        name = src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore")
        if name and name not in seen:
            seen.add(name)
            out.append((kind, name, _context_around(src, decl_start)))

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        found = _decl(node)
        if found is not None:
            add(found[0], found[1], node.start_byte)
        # ordine di visita: figli in ordine di sorgente (stack LIFO -> reversed)
        stack.extend(reversed(node.children))

    return out


# Chiamate HTTP con path letterale: `backendFetch("/api/x")`, `fetch(`/api/x/${id}`)`,
# `http.post("/api/x", body)`. frontend.resolve_http_calls le abbina agli endpoint del backend.
_HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
_SUBSTITUTION_RE = re.compile(r"\$\{[^}]*\}")
_HOLE = "\x00"


def _call_path(raw: str) -> str | None:
    """Path normalizzato di un letterale: un'interpolazione che occupa un intero segmento
    diventa `*`; una attaccata a testo (`/requests${query}`) è una query string e chiude il
    path. None se il letterale non è un path assoluto (`/...`)."""
    if not raw.startswith("/"):
        return None
    segs = []
    for seg in raw.split("?", 1)[0].split("#", 1)[0].split("/"):
        if not seg:
            continue
        if _HOLE not in seg:
            segs.append(seg)
        elif seg.startswith(_HOLE):
            segs.append("*")
        else:
            segs.append(seg.split(_HOLE, 1)[0])
            break
    return "/" + "/".join(segs) if segs else None


def _call_method(call, src: bytes) -> str:
    """Metodo HTTP della chiamata: dal nome (`http.post`), da `{ method: "POST" }` nel
    secondo argomento, GET se non ce n'è; '' se non deducibile (init non letterale)."""
    fn = call.child_by_field_name("function")
    if fn is not None and fn.type == "member_expression":
        prop = fn.child_by_field_name("property")
        if prop is not None and src[prop.start_byte:prop.end_byte].decode("utf-8", "ignore") in _HTTP_METHODS:
            return src[prop.start_byte:prop.end_byte].decode("utf-8", "ignore").upper()
    args = call.child_by_field_name("arguments").named_children
    if len(args) < 2:
        return "GET"
    if args[1].type != "object":
        return ""
    for pair in args[1].named_children:
        key = pair.child_by_field_name("key") if pair.type == "pair" else None
        if key is not None and src[key.start_byte:key.end_byte].decode("utf-8", "ignore").strip("'\"") == "method":
            value = pair.child_by_field_name("value")
            if value is not None and value.type == "string":
                return src[value.start_byte + 1:value.end_byte - 1].decode("utf-8", "ignore").upper()
            return ""
    return "GET"


def http_calls_by_symbol(text: str, suffix: str) -> dict[str, list[str]]:
    """{simbolo: ["METHOD /path", ...]} per le chiamate con path letterale, attribuite al
    simbolo dichiarato più interno che le contiene (stesse regole di _walk_symbols). Le
    chiamate a livello di modulo, fuori da ogni simbolo, non hanno a chi appartenere."""
    src = text.encode("utf-8")
    tree = Parser(_LANGUAGES.get(suffix, _LANGUAGES[".ts"])).parse(src)
    calls: dict[str, set[str]] = {}
    stack = [(tree.root_node, None)]
    while stack:
        node, owner = stack.pop()
        if (found := _decl(node)) is not None:
            owner = src[found[1].start_byte:found[1].end_byte].decode("utf-8", "ignore")
        elif node.type == "call_expression" and owner:
            args = node.child_by_field_name("arguments")
            first = args.named_children[0] if args is not None and args.named_children else None
            if first is not None and first.type in ("string", "template_string"):
                raw = src[first.start_byte + 1:first.end_byte - 1].decode("utf-8", "ignore")
                path = _call_path(_SUBSTITUTION_RE.sub(_HOLE, raw) if first.type == "template_string" else raw)
                if path:
                    calls.setdefault(owner, set()).add(f"{_call_method(node, src)} {path}".strip())
        stack.extend((c, owner) for c in reversed(node.children))
    return {k: sorted(v) for k, v in calls.items()}


def ts_symbols(text: str, stem: str, suffix: str) -> list[tuple[str, str, str]]:
    """Estrae simboli da sorgente TypeScript/TSX/JavaScript/JSX con tree-sitter."""
    lang = _LANGUAGES.get(suffix, _LANGUAGES[".ts"])
    return _walk_symbols(text.encode("utf-8"), lang)


def svelte_symbols(text: str, stem: str, suffix: str) -> list[tuple[str, str, str]]:
    """Estrae simboli da un componente Svelte: i blocchi <script> vengono
    ri-parsati con la grammatica TypeScript; in coda il nodo componente con
    il nome del file, come nel parser regex."""
    src = text.encode("utf-8")
    tree = _pack_parser("svelte").parse(src)

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "script_element":
            for child in node.children:
                if child.type == "raw_text":
                    for kind, name, snippet in _walk_symbols(
                            src[child.start_byte:child.end_byte], _LANGUAGES[".ts"]):
                        if name not in seen:
                            seen.add(name)
                            out.append((kind, name, snippet))
        else:
            stack.extend(reversed(node.children))

    out.append(("component", stem, text[:_SNIPPET_LIMIT]))
    return out
