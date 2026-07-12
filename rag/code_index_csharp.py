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

Framework-aware (stesso pattern delle annotation Quarkus in code_index_java):
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


def csharp_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae simboli da sorgente C#: tipi (class/record/interface/struct/enum),
    metodi e proprietà pubblici (endpoint ASP.NET Core/WCF marcati), con deps
    best-effort verso gli using directives e namespace come metadato."""
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
        out.append((kind, cls, _context(src, node.start_byte),
                    {"deps": list(usings), "package": namespace}))

        body = node.child_by_field_name("body")
        if body is None:
            return
        implicit_public = node.type == "interface_declaration"
        bases = _base_names(node, src)
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
                mtuple = (mkind, f"{cls}.{mname}", _context(src, member.start_byte))
                if is_controller:
                    # convenzione MVC: View() implicita -> view col nome dell'azione,
                    # View("Nome")/PartialView("Nome") -> view esplicita. Dep tipizzate,
                    # risolte (o segnalate rotte) da code_index_razor.resolve_links.
                    views = {m.group(1) or mname for m in _VIEW_CALL_RE.finditer(_text(src, member))}
                    if views:
                        mtuple = mtuple + ({"deps": [f"view:{ctrl}/{v}" for v in sorted(views)]},)
                out.append(mtuple)
            elif member.type == "property_declaration":
                pname_node = member.child_by_field_name("name")
                if pname_node is not None and _is_public(member, src):
                    out.append(("property", f"{cls}.{_text(src, pname_node)}",
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
