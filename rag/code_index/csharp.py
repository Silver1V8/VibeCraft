"""Parser per repository .NET (tree-sitter-c-sharp via language-pack) e per i
file di progetto .csproj / packages.config (XML, niente tree-sitter).

Interfaccia comune di code_index (vedi README): tuple (kind, name, snippet)
o (kind, name, snippet, meta) con meta {"deps": [...], "package": namespace}.
Stesse tipologie di nodi/archi dei parser Java/TS, così Impact Ripple,
Semantic Map e drift/coverage funzionano senza modifiche.

Il parser è agnostico rispetto al runtime: nessuna distinzione tra .NET
Framework e .NET Core/.NET 5+ — gli attributi WCF ([ServiceContract]/
[OperationContract], legacy Framework) e ASP.NET Core ([ApiController]/
[Route]/[HttpGet]...) sono rilevati entrambi, sempre.

Framework-aware (stesso pattern delle annotation Quarkus in code_index.java):
metodi con attributi HTTP/Route/OperationContract -> kind "endpoint".

Error recovery: sorgente C# con errori di sintassi degrada a estrazione
parziale con warning; XML malformato viene saltato con warning.
"""

import re
import xml.etree.ElementTree as ET

from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

_TYPE_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "struct_declaration": "struct",
    "record_declaration": "record",
    "enum_declaration": "enum",
}

# Attributi che marcano un metodo come endpoint: ASP.NET Core + WCF legacy.
_ENDPOINT_ATTRIBUTES = {
    "HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch", "HttpHead",
    "HttpOptions", "Route", "OperationContract",
}


def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _context(src: bytes, start_byte: int) -> str:
    begin = max(0, start_byte - 40)
    return src[begin:begin + _CONTEXT_SPAN].decode("utf-8", errors="ignore")


def _attribute_names(node, src: bytes) -> set[str]:
    """Nomi degli attributi ([ApiController], [HttpGet("...")], ...) di una
    dichiarazione: figli attribute_list -> attribute -> primo identifier."""
    names = set()
    for child in node.children:
        if child.type != "attribute_list":
            continue
        for attr in child.children:
            if attr.type == "attribute":
                name_node = attr.child_by_field_name("name") or next(
                    (c for c in attr.children if c.type in ("identifier", "qualified_name")), None)
                if name_node is not None:
                    names.add(_text(src, name_node).split(".")[-1].removesuffix("Attribute"))
    return names


def _is_public(node, src: bytes) -> bool:
    return any(child.type == "modifier" and _text(src, child).strip() == "public"
               for child in node.children)


def _base_names(node, src: bytes) -> set[str]:
    """Nomi semplici dei tipi base (class X : Controller, IFoo, ...)."""
    for child in node.children:
        if child.type == "base_list":
            return {_text(src, c).split("<")[0].split(".")[-1]
                    for c in child.children if c.type not in (":", ",")}
    return set()


# Handler di Razor Pages (PageModel): OnGet/OnPostAsync/OnGetElenco/... -> endpoint
_PAGE_HANDLER_RE = re.compile(r"^On(Get|Post|Put|Delete|Patch|Head)\w*$")
# return View(); / View("Nome") / PartialView("Nome") nelle action MVC
_VIEW_CALL_RE = re.compile(r"\b(?:View|PartialView)\s*\(\s*(?:\"([\w/]+)\")?")

# Ponte codice -> database (best-effort): stored procedure invocate via ADO.NET
# (CommandText/SqlCommand con CommandType.StoredProcedure) o EXEC dentro stringhe SQL.
_SP_NAME_RE = re.compile(r'(?:CommandText\s*=\s*|SqlCommand\(\s*)"([\w.\[\]]+)"')
_SP_EXEC_IN_STRING_RE = re.compile(r'"[^"]*\bEXEC(?:UTE)?\s+([\w.\[\]]+)', re.I)


def _storedproc_links(member_text: str) -> list[tuple[str, str]]:
    """Archi EXECUTES metodo -> stored procedure, con i nomi normalizzati come
    fa il parser SQL (così risolvono sugli stessi nodi)."""
    from code_index.sql import _norm
    names = set()
    if "CommandType.StoredProcedure" in member_text:
        names.update(_SP_NAME_RE.findall(member_text))
    names.update(_SP_EXEC_IN_STRING_RE.findall(member_text))
    return [("EXECUTES", _norm(n)) for n in sorted(names) if _norm(n)]


# Entity Framework (Core ed EF6): SQL grezzo dentro le API EF
_EF_RAW_SQL_RE = re.compile(
    r"(?:FromSqlRaw|FromSqlInterpolated|ExecuteSqlRaw|ExecuteSqlRawAsync|"
    r"ExecuteSqlInterpolated)\s*\(\s*\$?@?\"([^\"]+)\"")
# DbSet<Entity> NomeProprieta
_DBSET_RE = re.compile(r"DbSet<([\w.]+)>")
# Fluent API in OnModelCreating: modelBuilder.Entity<X>()....ToTable("nome")
_FLUENT_TOTABLE_RE = re.compile(r"Entity<([\w.]+)>\s*\(\s*\)[\s\S]{0,200}?\.ToTable\(\s*\"([^\"]+)\"")
_TABLE_ATTR_RE = re.compile(r"\[Table\(\s*\"([^\"]+)\"")
_COLUMN_ATTR_RE = re.compile(r"\[Column\(\s*\"([^\"]+)\"")
_COLLECTION_RE = re.compile(r"^(?:ICollection|IEnumerable|IList|List|HashSet|ISet|ObservableCollection)<(.+)>$")


def _ef_raw_sql_links(member_text: str) -> list[tuple[str, str]]:
    """Archi READS/WRITES/EXECUTES dalle stringhe SQL grezze di EF
    (FromSqlRaw & co.), riusando l'estrattore del parser SQL."""
    from code_index.sql import _body_links
    sql = " ; ".join(_EF_RAW_SQL_RE.findall(member_text))
    return _body_links(sql, "") if sql.strip() else []


def csharp_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae simboli da sorgente C#: tipi (class/record/interface/struct/enum),
    metodi e proprietà pubblici (endpoint ASP.NET Core/WCF marcati), con deps
    best-effort verso gli using directives e namespace come metadato."""
    # tree-sitter-c-sharp richiede il newline finale dopo una direttiva
    # #pragma su singola riga: senza, un EOF subito dopo (comune nei file
    # generati da svcutil/wsdl.exe come Reference.cs, che spesso terminano
    # con "#pragma warning restore ..." senza \n) fa scattare has_error
    # anche se il C# e' sintatticamente valido. Normalizziamo prima del parse.
    if text and not text.endswith("\n"):
        text = text + "\n"
    src = text.encode("utf-8")
    tree = _pack_parser("csharp").parse(src)
    if tree.root_node.has_error:
        print(f"[warn] parser csharp: errori di sintassi in {stem}{suffix}, estrazione parziale")

    namespace = ""
    usings: list[str] = []   # ultimo segmento degli using (candidati DEPENDS_ON, best-effort)
    out: list[tuple] = []

    def visit_type(node) -> None:
        nonlocal namespace
        kind = _TYPE_KINDS[node.type]
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        cls = _text(src, name_node)
        bases = _base_names(node, src)
        is_context = "DbContext" in bases
        if is_context:
            kind = "context"  # Entity Framework: DbContext (Core ed EF6)
        cls_attrs: dict = {}
        # [Table("nome")] sulla classe: mapping esplicito entity -> tabella; il
        # resolver EF lo combina con Fluent API/convenzione (chiave temporanea)
        node_text = _text(src, node)
        tm = _TABLE_ATTR_RE.search(" ".join(
            _text(src, c) for c in node.children if c.type == "attribute_list") or "")
        if tm:
            cls_attrs["_table"] = tm.group(1)
        if is_context:
            # Fluent API in OnModelCreating: Entity<X>()...ToTable("nome")
            fluent = {e.split(".")[-1]: t for e, t in _FLUENT_TOTABLE_RE.findall(node_text)}
            if fluent:
                cls_attrs["_fluent"] = fluent
        cls_meta = {"deps": list(usings), "package": namespace, "attrs": cls_attrs}
        out.append((kind, cls, _context(src, node.start_byte), cls_meta))

        body = node.child_by_field_name("body")
        if body is None:
            return
        implicit_public = node.type == "interface_declaration"
        is_controller = cls.endswith("Controller") or bases & {"Controller", "ControllerBase"}
        is_page_model = "PageModel" in bases
        ctrl = cls.removesuffix("Controller")
        for member in body.children:
            if member.type == "method_declaration":
                mname_node = member.child_by_field_name("name")
                if mname_node is None or not (implicit_public or _is_public(member, src)):
                    continue
                mname = _text(src, mname_node)
                attrs = _attribute_names(member, src)
                if attrs & _ENDPOINT_ATTRIBUTES or (is_page_model and _PAGE_HANDLER_RE.match(mname)):
                    mkind = "endpoint"
                else:
                    mkind = "method"
                member_text = _text(src, member)
                meta: dict = {}
                if is_controller:
                    # convenzione MVC: View() implicita -> view col nome dell'azione,
                    # View("Nome")/PartialView("Nome") -> view esplicita. Dep tipizzate,
                    # risolte (o segnalate rotte) da code_index.razor.resolve_links.
                    views = {m.group(1) or mname for m in _VIEW_CALL_RE.finditer(member_text)}
                    if views:
                        meta["deps"] = [f"view:{ctrl}/{v}" for v in sorted(views)]
                sp = _storedproc_links(member_text) + _ef_raw_sql_links(member_text)
                if sp:
                    meta["links"] = sp
                mtuple = (mkind, f"{cls}.{mname}", _context(src, member.start_byte))
                out.append(mtuple + ((meta,) if meta else ()))
            elif member.type == "property_declaration":
                pname_node = member.child_by_field_name("name")
                if pname_node is not None and _is_public(member, src):
                    pname = _text(src, pname_node)
                    ptext = _text(src, member)
                    type_node = member.child_by_field_name("type")
                    ptype = _text(src, type_node).strip() if type_node else ""
                    ds = _DBSET_RE.match(ptype)
                    if is_context and ds:
                        # DbSet<Entity> -> il resolver EF crea context->entity e il
                        # mapping tabella per convenzione (nome del DbSet)
                        cls_attrs.setdefault("_dbsets", {})[ds.group(1).split(".")[-1]] = pname
                    else:
                        # tipi delle proprietà: servono al resolver EF per le
                        # proprietà di navigazione entity->entity (chiave temporanea)
                        cls_attrs.setdefault("_prop_types", {})[pname] = ptype
                    cm = _COLUMN_ATTR_RE.search(ptext)
                    if cm:
                        cls_attrs.setdefault("columns", []).append(cm.group(1))
                    out.append(("property", f"{cls}.{pname}",
                                _context(src, member.start_byte)))
            elif member.type in _TYPE_KINDS:  # tipi annidati
                visit_type(member)

    # Visita iterativa dell'intero albero: come per Java, con errori di sintassi
    # le dichiarazioni possono finire sotto nodi ERROR e vanno recuperate comunque.
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            name_node = node.child_by_field_name("name") or next(
                (c for c in node.children if c.type in ("qualified_name", "identifier")), None)
            if name_node is not None:
                namespace = _text(src, name_node)
            stack.extend(reversed(node.children))
        elif node.type == "using_directive":
            m = re.search(r"using\s+(?:static\s+)?([\w.]+)", _text(src, node))
            if m:
                usings.append(m.group(1).split(".")[-1])
        elif node.type in _TYPE_KINDS:
            visit_type(node)  # gestisce da sé i tipi annidati: non si ridiscende
        else:
            stack.extend(reversed(node.children))
    return out + _minimal_api_endpoints(text)


# Minimal API (ASP.NET Core 6+): gli endpoint non sono attributi su metodi ma chiamate in
# Program.cs — `var g = app.MapGroup("/api/x")` poi `g.MapGet("/{id}", ...)`. Senza questo
# un backend minimal API non aveva NESSUN endpoint nel grafo (5a, 2026-10-29). Limiti:
# gruppi concatenati in un'unica espressione e MapMethods/MapFallback non sono riconosciuti.
_MAP_GROUP_RE = re.compile(r'\b(\w+)\s*=\s*(\w+)\s*\.\s*MapGroup\(\s*"([^"]*)"')
_MAP_VERB_RE = re.compile(r'\b(\w+)\s*\.\s*Map(Get|Post|Put|Delete|Patch)\(\s*"([^"]*)"')


def _join_route(prefix: str, path: str) -> str:
    return "/" + "/".join(p for p in f"{prefix}/{path}".split("/") if p)


def _minimal_api_endpoints(text: str) -> list[tuple]:
    """Endpoint `METHOD /route` con il prefisso dei MapGroup risolto (anche annidati, se
    dichiarati prima dell'uso come nel codice reale). attrs method/route servono a
    frontend.resolve_http_calls per abbinare le chiamate del frontend."""
    prefixes: dict[str, str] = {}
    for var, parent, path in _MAP_GROUP_RE.findall(text):
        prefixes[var] = _join_route(prefixes.get(parent, ""), path)
    out, seen = [], set()
    for m in _MAP_VERB_RE.finditer(text):
        receiver, verb, path = m.groups()
        method, route = verb.upper(), _join_route(prefixes.get(receiver, ""), path)
        name = f"{method} {route}"
        if name not in seen:
            seen.add(name)
            out.append(("endpoint", name, text[max(0, m.start() - 40):m.start() + _CONTEXT_SPAN],
                        {"attrs": {"method": method, "route": route}}))
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xml(text: str, what: str):
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        print(f"[warn] parser {what}: XML malformato, file saltato ({e})")
        return None


def csproj_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae da un .csproj il nodo progetto (nome = stem del file) con deps
    verso PackageReference e ProjectReference (archi DEPENDS_ON tra progetti,
    base dell'impact analysis multi-repo .NET)."""
    root = _parse_xml(text, "csproj")
    if root is None or _local(root.tag) != "Project":
        return []
    deps: list[str] = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "PackageReference":
            include = el.get("Include") or ""
            if include:
                deps.append(include)
        elif tag == "ProjectReference":
            include = (el.get("Include") or "").replace("\\", "/")
            name = include.rsplit("/", 1)[-1].removesuffix(".csproj")
            if name:
                deps.append(name)
    return [("project", stem, text[:_SNIPPET_LIMIT], {"deps": deps})]


def packages_config_symbols(text: str, stem: str, suffix: str, project: str = "") -> list[tuple]:
    """packages.config (.NET Framework legacy): deps verso i package NuGet
    dichiarati; nome progetto = cartella che lo contiene."""
    root = _parse_xml(text, "packages.config")
    if root is None or _local(root.tag) != "packages":
        return []
    deps = [p.get("id") for p in root.iter() if _local(p.tag) == "package" and p.get("id")]
    return [("project", project or stem, text[:_SNIPPET_LIMIT], {"deps": deps})]


# ------------------------------------------------------ resolver Entity Framework

def resolve_ef(symbols: list[dict]) -> None:
    """Post-pass EF (richiede la vista d'insieme dei simboli, come gli altri
    resolver): archi context->entity dai DbSet, mapping entity->tabella
    ([Table] > Fluent ToTable > convenzione nome DbSet > nome classe, in
    lowercase per riconciliarsi con i nodi del parser SQL), nodi tabella
    placeholder quando il DDL non e' indicizzato, e proprieta' di navigazione
    entity->entity come REFERENCES. Rimuove sempre le chiavi temporanee
    (_table/_fluent/_dbsets/_prop_types) dai metadati."""
    classes = {s["name"]: s for s in symbols
               if s["kind"] in ("class", "record", "context")}
    table_nodes = {s["name"] for s in symbols if s["kind"] == "table"}
    entity_table: dict[str, str] = {}   # entity -> tabella scelta

    # 1) raccolta: [Table] sulle entity, DbSet e Fluent dai context
    for sym in symbols:
        t = (sym.get("attrs") or {}).pop("_table", None)
        if t and sym["kind"] in ("class", "record"):
            entity_table[sym["name"]] = t.lower()
    contexts = [s for s in symbols if s["kind"] == "context"]
    for ctx in contexts:
        attrs = ctx.get("attrs") or {}
        fluent = attrs.pop("_fluent", {})
        dbsets = attrs.pop("_dbsets", {})
        for etype, table in fluent.items():
            entity_table.setdefault(etype, table.lower())
        for etype, dbset_name in dbsets.items():
            ctx["deps"] = sorted(set(ctx["deps"]) | {etype})   # context -> entity
            entity_table.setdefault(etype, dbset_name.lower())  # convenzione EF

    # 2) mapping entity -> tabella (+ placeholder se il DDL non c'e' ancora)
    placeholders: list[dict] = []
    for ename, table in entity_table.items():
        ent = classes.get(ename)
        if ent is None:
            continue
        ent["links"] = sorted(set(ent["links"]) | {("REFERENCES", table)})
        if table not in table_nodes:
            table_nodes.add(table)
            placeholders.append({
                "id": f"{ent['file']}::{table}",
                "name": table, "kind": "table", "file": ent["file"],
                "dev_type": ent["dev_type"],
                "text": f"table {table}\n(placeholder EF: DDL non indicizzato, "
                        f"riconciliato per nome quando il parser SQL lo trovera')",
                "deps": [], "refs": [], "links": [], "package": "",
                "attrs": {"placeholder": True},
            })
    symbols.extend(placeholders)

    # 3) navigazione entity -> entity (reference e collection) + pulizia chiavi
    for sym in symbols:
        prop_types = (sym.get("attrs") or {}).pop("_prop_types", None)
        if not prop_types or sym["name"] not in entity_table:
            continue
        for ptype in prop_types.values():
            m = _COLLECTION_RE.match(ptype)
            inner = (m.group(1) if m else ptype).strip().rstrip("?").split(".")[-1]
            if inner in entity_table and inner != sym["name"]:
                sym["refs"] = sorted(set(sym["refs"]) | {inner})
