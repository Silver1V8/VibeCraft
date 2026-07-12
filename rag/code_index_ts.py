"""Parser tree-sitter per i linguaggi frontend (TypeScript/TSX, JavaScript/JSX,
Svelte) — migrazione dal parser regex di code_index.

Espone la stessa interfaccia di code_index._js_symbols — lista di tuple
(kind, name, snippet) — selezionabile per linguaggio via `code_parsers.<lang>`
in rag_config.yaml. Python resta su stdlib `ast` (già un parser vero), HTML/CSS
restano nodi-file senza simboli.

Svelte: la grammatica tree-sitter-svelte parsa solo il markup e lascia il
contenuto di <script> come `raw_text`; qui il blocco script viene ri-parsato
con la grammatica TypeScript (che accetta anche JS), così i simboli dello
script sono estratti con un AST vero invece che con regex sull'intero file.
"""

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
        kind = _DECL_KINDS.get(node.type)
        if kind is not None:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                add(kind, name_node, node.start_byte)
        elif node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if (name_node is not None and name_node.type == "identifier"
                    and value_node is not None and value_node.type in _FN_VALUE_TYPES):
                add("function", name_node, node.start_byte)
        elif node.type in ("function_expression", "generator_function"):
            # function expression nominata (`const f = function nominata() {}`):
            # il regex la vede tramite `function\s+nome`, quindi la emettiamo anche qui
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                add("function", name_node, node.start_byte)
        # ordine di visita: figli in ordine di sorgente (stack LIFO -> reversed)
        stack.extend(reversed(node.children))

    return out


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
