"""Parser SQL ibrido per il code index: tree-sitter-sql (language-pack) come
base per gli statement che la grammatica capisce, scanner regex statement-level
come fallback per i dialetti — T-SQL (SQL Server: batch GO, identificatori
[tra parentesi quadre]) e PL/SQL (Oracle: package, terminatore /).

Verificato empiricamente: la grammatica del language-pack parsa bene CREATE
TABLE/VIEW generici ma va in ERROR su tutto il procedurale (procedure,
function, package) e sui dialetti. Quindi: ogni statement CREATE viene prima
tentato con tree-sitter; se il parse è pulito si estrae dall'albero, altrimenti
si passa al fallback regex e lo statement viene tracciato in `FALLBACK_LOG`.
Error recovery prima di tutto: un file pieno di dialetto non perde mai gli
statement riconoscibili; un file senza alcun CREATE riconoscibile degrada a
nodo "sqlscript" con warning.

Interfaccia comune di code_index; oltre a deps/refs/attrs, il meta può avere
"links": lista di (RELAZIONE, nome) con semantica SQL distinta —
READS (FROM/JOIN), WRITES (INSERT/UPDATE/DELETE/MERGE), EXECUTES (EXEC/CALL) —
risolti per nome da link_symbols come archi tipizzati del grafo.
"""

import re

from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500

# Log dei costrutti che hanno richiesto il fallback regex (per il report):
# tuple (file, kind, nome). Azzerato a ogni collect da code_index.
FALLBACK_LOG: list[tuple[str, str, str]] = []

_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_GO_RE = re.compile(r"^\s*GO\s*$", re.M | re.I)
_SLASH_RE = re.compile(r"^\s*/\s*$", re.M)

_CREATE_RE = re.compile(
    r"CREATE\s+(?:OR\s+(?:ALTER|REPLACE)\s+)?"
    r"(TABLE|VIEW|PROCEDURE|PROC|FUNCTION|TRIGGER|PACKAGE(?:\s+BODY)?)\s+"
    r"([\[\]\"\w.]+)", re.I)

_READS_RE = re.compile(r"\b(?:FROM|JOIN)\s+([\[\]\"\w.]+)", re.I)
_WRITES_RE = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+(?:INTO\s+)?)\s*([\[\]\"\w.]+)", re.I)
_EXEC_RE = re.compile(r"\b(?:EXEC(?:UTE)?|CALL)\s+([\[\]\"\w.]+)", re.I)
_TSQL_PARAM_RE = re.compile(r"@(\w+)")
_PLSQL_PARAM_RE = re.compile(r"\b(\w+)\s+(?:IN|OUT|IN\s+OUT)\b", re.I)
_PKG_MEMBER_RE = re.compile(r"\b(PROCEDURE|FUNCTION)\s+([\w\"]+)", re.I)
_TRIGGER_ON_RE = re.compile(r"\bON\s+([\[\]\"\w.]+)", re.I)

# Pseudo-tabelle e rumore da non trasformare in archi
_NOISE = {"inserted", "deleted", "dual", "select", "values"}

_KIND_MAP = {"proc": "procedure", "package body": "package"}


def _norm(name: str) -> str:
    """Normalizza un identificatore SQL: via [ ] e ", solo l'ultimo segmento
    dello schema, lowercase (il SQL è case-insensitive: i nomi dei nodi e dei
    link devono coincidere a prescindere dal case usato nei sorgenti)."""
    clean = name.replace("[", "").replace("]", "").replace('"', "").strip().rstrip(";")
    return clean.split(".")[-1].lower()


def _body_links(body: str, self_name: str) -> list[tuple[str, str]]:
    """Archi semantici dal corpo di uno statement: WRITES prima di READS, così
    a parità di coppia (un solo arco per coppia nel DiGraph) vince WRITES."""
    links: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(rel: str, raw: str):
        t = _norm(raw)
        if t and t != self_name and t not in _NOISE and not raw.startswith("@"):
            if (rel, t) not in seen:
                seen.add((rel, t))
                links.append((rel, t))

    for m in _EXEC_RE.finditer(body):
        add("EXECUTES", m.group(1))
    for m in _WRITES_RE.finditer(body):
        add("WRITES", m.group(1))
    for m in _READS_RE.finditer(body):
        add("READS", m.group(1))
    return links


def _columns_from_tree(node, src: bytes) -> list[str]:
    cols = []
    for defn in node.children:
        if defn.type == "column_definitions":
            for col in defn.children:
                if col.type == "column_definition":
                    ident = next((c for c in col.children if c.type == "identifier"), None)
                    if ident is not None:
                        cols.append(src[ident.start_byte:ident.end_byte].decode("utf-8", "ignore").lower())
    return cols


def _try_tree(stmt: str, kind: str):
    """Estrazione tree-sitter di un CREATE TABLE/VIEW se la grammatica lo parsa
    pulito. Restituisce (columns, reads) o None se serve il fallback regex."""
    if kind not in ("table", "view"):
        return None  # procedurale: la grammatica non lo regge, inutile provare
    src = stmt.encode("utf-8")
    tree = _pack_parser("sql").parse(src)
    if tree.root_node.has_error:
        return None
    columns: list[str] = []
    reads: list[str] = []
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "create_table":
            columns = _columns_from_tree(n, src)
        elif n.type == "relation":
            ref = next((c for c in n.children if c.type == "object_reference"), None)
            if ref is not None:
                reads.append(_norm(src[ref.start_byte:ref.end_byte].decode("utf-8", "ignore")))
        stack.extend(n.children)
    return columns, reads


def _dialect(text: str) -> str:
    """Dialetto: euristica sul contenuto, con default da rag_config.yaml
    (code_parsers.sql_dialect: tsql | plsql | generic)."""
    if _GO_RE.search(text) or "[" in text or "@" in text:
        return "tsql"
    if re.search(r"\bPACKAGE\b|\bIS\b\s*$|\bVARCHAR2\b|\bNVL\b", text, re.I | re.M):
        return "plsql"
    try:
        from core.config import CODE_PARSERS
        return CODE_PARSERS.get("sql_dialect", "generic")
    except Exception:
        return "generic"


def sql_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Estrae da un file SQL i nodi tabella/vista/procedura/funzione/trigger/
    package e gli archi READS/WRITES/EXECUTES. Mai eccezioni: degrada."""
    try:
        return _scan(text, stem, suffix, rel)
    except Exception as e:
        print(f"[warn] parser sql: {rel or stem}{suffix} illeggibile, nodo senza dettagli ({e})")
        return [("sqlscript", stem, text[:_SNIPPET_LIMIT])]


def _scan(text: str, stem: str, suffix: str, rel: str) -> list[tuple]:
    clean = _COMMENT_RE.sub(" ", text)
    dialect = _dialect(clean)
    # batch T-SQL (GO) e terminatori PL/SQL (/) sono separatori di statement
    chunks = []
    for batch in _GO_RE.split(clean):
        chunks.extend(_SLASH_RE.split(batch))

    out: list[tuple] = []
    seen: set[str] = set()
    for chunk in chunks:
        matches = list(_CREATE_RE.finditer(chunk))
        for i, m in enumerate(matches):
            raw_kind = re.sub(r"\s+", " ", m.group(1).lower())
            kind = _KIND_MAP.get(raw_kind, raw_kind)
            name = _norm(m.group(2))
            if not name or name in seen:
                continue
            end = matches[i + 1].start() if i + 1 < len(matches) else len(chunk)
            stmt = chunk[m.start():end]
            body = chunk[m.end():end]
            out.extend(_statement_symbols(kind, name, stmt, body, dialect, rel or stem))
            seen.add(name)

    if not out:
        print(f"[warn] parser sql: nessuno statement riconoscibile in {rel or stem}{suffix}, "
              f"degradato a nodo sqlscript")
        return [("sqlscript", stem, text[:_SNIPPET_LIMIT], {"attrs": {"dialect": dialect}})]
    return out


def _statement_symbols(kind: str, name: str, stmt: str, body: str,
                       dialect: str, where: str) -> list[tuple]:
    snippet = stmt[:_SNIPPET_LIMIT]
    attrs: dict = {"dialect": dialect}

    if kind in ("table", "view"):
        via_tree = _try_tree(stmt, kind)
        if via_tree is not None:
            columns, reads = via_tree
            if kind == "table" and columns:
                attrs["columns"] = columns
            links = [("READS", r) for r in reads if r != name] if kind == "view" else []
            return [(kind, name, snippet, {"attrs": attrs, "links": links})]
        FALLBACK_LOG.append((where, kind, name))
        if kind == "table":
            # colonne via regex: primi identificatori dentro le parentesi del CREATE
            paren = re.search(r"\(", body)
            cols = []
            if paren:
                for line in re.split(r",(?![^(]*\))", body[paren.end():]):
                    cm = re.match(r"\s*([\[\]\"\w]+)", line)
                    ident = _norm(cm.group(1)) if cm else ""
                    if ident and ident not in ("constraint", "primary", "foreign", "unique", "check", "index"):
                        cols.append(ident)
            if cols:
                attrs["columns"] = cols
            return [("table", name, snippet, {"attrs": attrs})]
        return [("view", name, snippet, {"attrs": attrs, "links": _body_links(body, name)})]

    if kind == "package":
        FALLBACK_LOG.append((where, kind, name))
        out = []
        members = []
        for mm in _PKG_MEMBER_RE.finditer(body):
            mname = f"{name}.{_norm(mm.group(2))}"
            if mname in members:
                continue
            members.append(mname)
            # corpo del membro: fino al prossimo PROCEDURE/FUNCTION o fine package
            nxt = _PKG_MEMBER_RE.search(body, mm.end())
            mbody = body[mm.end():nxt.start() if nxt else len(body)]
            out.append((mm.group(1).lower(), mname, body[mm.start():mm.start() + _SNIPPET_LIMIT],
                        {"attrs": {"dialect": dialect},
                         "links": _body_links(mbody, mname),
                         "deps": []}))
        out.insert(0, ("package", name, snippet,
                       {"attrs": attrs, "deps": members}))
        return out

    # procedure / function / trigger: sempre fallback regex (grammatica ko)
    FALLBACK_LOG.append((where, kind, name))
    # intestazione = fino al primo AS/IS/BEGIN: i parametri stanno lì
    header = re.split(r"\bAS\b|\bIS\b|\bBEGIN\b", body, maxsplit=1, flags=re.I)[0]
    params = (_TSQL_PARAM_RE.findall(header) if dialect == "tsql"
              else _PLSQL_PARAM_RE.findall(header))
    if params:
        attrs["parameters"] = [p.lower() for p in params]
    meta = {"attrs": attrs, "links": _body_links(body, name)}
    if kind == "trigger":
        on = _TRIGGER_ON_RE.search(body)
        if on:
            meta["deps"] = [_norm(on.group(1))]  # trigger agganciato alla tabella
    return [(kind, name, snippet, meta)]
