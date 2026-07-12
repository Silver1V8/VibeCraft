"""Parser TypeScript basato su tree-sitter (spike di migrazione dal parser regex).

Espone la stessa interfaccia di code_index._js_symbols — lista di tuple
(kind, name, snippet) — così da poter essere selezionato dietro il flag
`code_parsers.typescript` in rag_config.yaml senza toccare il resto della
pipeline. Copre solo .ts/.tsx: gli altri linguaggi restano sul parser regex.
"""

from tree_sitter import Language, Parser
import tree_sitter_typescript as _tsts

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

_LANGUAGES = {
    ".ts": Language(_tsts.language_typescript()),
    ".tsx": Language(_tsts.language_tsx()),
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


def ts_symbols(text: str, stem: str, suffix: str) -> list[tuple[str, str, str]]:
    """Estrae simboli da sorgente TypeScript/TSX con tree-sitter.

    Come il parser regex: dedup per nome (vince la prima occorrenza) e snippet
    di contesto attorno alla dichiarazione."""
    lang = _LANGUAGES.get(suffix, _LANGUAGES[".ts"])
    src = text.encode("utf-8")
    tree = Parser(lang).parse(src)

    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(kind: str, name: str, start_byte: int) -> None:
        if name and name not in seen:
            seen.add(name)
            out.append((kind, name, _context_around(src, start_byte)))

    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = _DECL_KINDS.get(node.type)
        if kind is not None:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                add(kind, src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore"),
                    node.start_byte)
        elif node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if (name_node is not None and name_node.type == "identifier"
                    and value_node is not None and value_node.type in _FN_VALUE_TYPES):
                add("function", src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore"),
                    node.start_byte)
        elif node.type in ("function_expression", "generator_function"):
            # function expression nominata (`const f = function nominata() {}`):
            # il regex la vede tramite `function\s+nome`, quindi la emettiamo anche qui
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                add("function", src[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="ignore"),
                    node.start_byte)
        # ordine di visita: figli in ordine di sorgente (stack LIFO -> reversed)
        stack.extend(reversed(node.children))

    return out
