"""Parser per repository Java (tree-sitter-java) e per gli artefatti di progetto
collegati: pom.xml / build.gradle (dipendenze) e file Kogito .bpmn/.bpmn2/.dmn.

Interfaccia comune di code_index: ogni funzione restituisce tuple
(kind, name, snippet) oppure (kind, name, snippet, meta) dove meta è un dict
opzionale con:
  - "deps": nomi semplici di altri simboli del progetto da collegare con archi
    DEPENDS_ON (risolti per nome da link_symbols, best-effort);
  - "package": package Java di appartenenza (attributo del nodo).

Framework-aware (stesso pattern dei decoratori FastAPI nel parser Python):
  - JAX-RS (@Path + @GET/@POST/...) -> kind "endpoint" (Quarkus e Dropwizard);
  - CDI @Inject -> nodo "field" + dep classe -> tipo iniettato;
  - messaging (@ConsumeEvent/@Incoming/@Outgoing) -> kind "listener" (il nome
    del canale resta nello snippet, quindi pescabile da REFERENCES/glossario).

Error recovery: nessuna funzione solleva su input malformato — XML rotto o
sorgente Java con errori di sintassi degradano a estrazione parziale con warning.
"""

import re
import xml.etree.ElementTree as ET

from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

_TYPE_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
}

_HTTP_ANNOTATIONS = {
    # JAX-RS (Quarkus/Dropwizard)
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS",
    # Spring MVC (metodo): stesso kind "endpoint"
    "RequestMapping", "GetMapping", "PostMapping", "PutMapping",
    "DeleteMapping", "PatchMapping",
}
_MESSAGING_ANNOTATIONS = {"ConsumeEvent", "Incoming", "Outgoing"}
# Iniezione di dipendenza su campo: CDI e Spring, stesso trattamento
_INJECT_ANNOTATIONS = {"Inject", "Autowired"}
# Rest-client dichiarativi (chiamate servizio->servizio)
_REST_CLIENT_ANNOTATIONS = {"RegisterRestClient", "FeignClient"}
_REST_CLIENT_ARG_RE = re.compile(r'(baseUri|configKey|name|url)\s*=\s*"([^"]+)"')
_TABLE_NAME_RE = re.compile(r'@Table\s*\(\s*[^)]*name\s*=\s*"([^"]+)"')
# Relazioni di navigazione JPA sui campi (equivalente della navigazione EF)
_JPA_RELATION_ANNOTATIONS = {"OneToMany", "ManyToOne", "OneToOne", "ManyToMany"}
_GENERIC_INNER_RE = re.compile(r"^(?:List|Set|Collection|Map)<(?:[\w.]+,\s*)?([\w.]+)>$")
# @Query(value="...", nativeQuery=true) di Spring Data JPA
_NATIVE_QUERY_VALUE_RE = re.compile(r'value\s*=\s*"([^"]+)"')

# FQCN Java (almeno due segmenti, ultimo capitalizzato): usato per trovare le classi
# referenziate dai service task Kogito dentro attributi/estensioni XML.
_FQCN_RE = re.compile(r"\b(?:[a-z_][\w]*\.)+([A-Z]\w+)\b")

# Ponte codice -> database (best-effort): stored procedure invocate via JPA
# (@NamedStoredProcedureQuery(procedureName=...)) o CallableStatement ("{call x}").
_JPA_SP_RE = re.compile(r'procedureName\s*=\s*"([\w.]+)"')
_CALL_SP_RE = re.compile(r'\{\s*call\s+([\w.]+)', re.I)


def _storedproc_links(text: str) -> list[tuple[str, str]]:
    from code_index_sql import _norm
    names = set(_JPA_SP_RE.findall(text)) | set(_CALL_SP_RE.findall(text))
    return [("EXECUTES", _norm(n)) for n in sorted(names) if _norm(n)]


# Dichiarazioni di dipendenza Gradle: implementation "gruppo:artefatto:versione" ecc.
_GRADLE_DEP_RE = re.compile(
    r"(?:implementation|api|compileOnly|runtimeOnly|testImplementation|compile)\s*"
    r"[\(\s]*['\"]([\w.\-]+):([\w.\-]+)")


def _text(src: bytes, node) -> str:
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _context(src: bytes, start_byte: int) -> str:
    begin = max(0, start_byte - 40)
    return src[begin:begin + _CONTEXT_SPAN].decode("utf-8", errors="ignore")


def _annotations(node) -> list:
    """Lista dei nodi annotation/marker_annotation nel blocco modifiers di `node`."""
    out = []
    for child in node.children:
        if child.type == "modifiers":
            out.extend(c for c in child.children
                       if c.type in ("annotation", "marker_annotation"))
    return out


def _annotation_names(node, src: bytes) -> set[str]:
    names = set()
    for ann in _annotations(node):
        name_node = ann.child_by_field_name("name")
        if name_node is not None:
            names.add(_text(src, name_node).split(".")[-1])
    return names


def _is_public(node, src: bytes) -> bool:
    for child in node.children:
        if child.type == "modifiers" and re.search(r"\bpublic\b", _text(src, child)):
            return True
    return False


def java_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae simboli da sorgente Java: tipi (class/interface/enum/record), metodi
    pubblici (endpoint JAX-RS e listener messaging marcati), campi @Inject, con
    deps verso import di progetto e tipi iniettati."""
    src = text.encode("utf-8")
    tree = _pack_parser("java").parse(src)
    if tree.root_node.has_error:
        print(f"[warn] parser java: errori di sintassi in {stem}{suffix}, estrazione parziale")

    package = ""
    imported: list[str] = []   # nomi semplici dei tipi importati (candidati DEPENDS_ON)
    out: list[tuple] = []

    def visit_type(node) -> None:
        kind = _TYPE_KINDS[node.type]
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        cls = _text(src, name_node)
        cls_anns = _annotation_names(node, src)
        cls_meta = {"deps": list(imported), "package": package}
        ann_text = " ".join(_text(src, a) for a in _annotations(node))
        # @NamedStoredProcedureQuery sulla classe -> arco EXECUTES verso la stored proc
        cls_sp = _storedproc_links(ann_text)
        if cls_sp:
            cls_meta["links"] = cls_sp
        # rest-client dichiarativi: MicroProfile @RegisterRestClient (baseUri/
        # configKey) e Spring @FeignClient (name/url) -> kind dedicato, con
        # URL/configKey nei metadati per la risoluzione a valle
        if cls_anns & _REST_CLIENT_ANNOTATIONS:
            kind = "rest-client"
            rc = {k: v for k, v in _REST_CLIENT_ARG_RE.findall(ann_text)}
            if rc:
                cls_meta["attrs"] = rc
        # stereotipi Spring: metadato della classe, non un nuovo kind
        stereotypes = cls_anns & {"Service", "Component", "Repository", "RestController", "Controller"}
        if stereotypes:
            cls_meta.setdefault("attrs", {})["stereotypes"] = sorted(stereotypes)
        # JPA: @Entity -> tabella da @Table(name=...) o convenzione Hibernate
        # (nome classe), lowercase. Chiave temporanea: il post-pass resolve_jpa
        # (analogo di resolve_ef in C#) crea il link e l'eventuale placeholder.
        if "Entity" in cls_anns:
            tm = _TABLE_NAME_RE.search(ann_text)
            cls_meta.setdefault("attrs", {})["_jpa_table"] = (tm.group(1) if tm else cls).lower()
        out.append((kind, cls, _context(src, node.start_byte), cls_meta))

        body = node.child_by_field_name("body")
        if body is None:
            return
        implicit_public = node.type == "interface_declaration"
        for member in body.children:
            if member.type == "method_declaration":
                mname_node = member.child_by_field_name("name")
                if mname_node is None or not (implicit_public or _is_public(member, src)):
                    continue
                anns = _annotation_names(member, src)
                if anns & _HTTP_ANNOTATIONS or ("Path" in anns and "Path" in cls_anns):
                    mkind = "endpoint"
                elif anns & _MESSAGING_ANNOTATIONS:
                    mkind = "listener"
                else:
                    mkind = "method"
                mtuple = (mkind, f"{cls}.{_text(src, mname_node)}",
                          _context(src, member.start_byte))
                sp = _storedproc_links(_text(src, member))  # CallableStatement "{call x}"
                # Spring Data JPA: @Query(value="...", nativeQuery=true) -> archi
                # READS/WRITES/EXECUTES dalle tabelle citate (riusa l'estrattore
                # del parser SQL, come _ef_raw_sql_links in C#)
                m_ann_text = " ".join(_text(src, a) for a in _annotations(member))
                if "Query" in anns and re.search(r"nativeQuery\s*=\s*true", m_ann_text):
                    qm = _NATIVE_QUERY_VALUE_RE.search(m_ann_text)
                    if qm:
                        from code_index_sql import _body_links
                        sp = sp + _body_links(qm.group(1), "")
                out.append(mtuple + (({"links": sp},) if sp else ()))
            elif member.type == "constructor_declaration":
                # @Autowired su costruttore: i tipi dei parametri sono iniettati,
                # stesso trattamento dei campi @Inject
                if "Autowired" not in _annotation_names(member, src):
                    continue
                params = member.child_by_field_name("parameters")
                for par in (params.children if params is not None else []):
                    if par.type != "formal_parameter":
                        continue
                    ptype_node = par.child_by_field_name("type")
                    pname_node = par.child_by_field_name("name")
                    ptype = _text(src, ptype_node).split("<")[0].split(".")[-1] if ptype_node else ""
                    if pname_node is not None and ptype:
                        out.append(("field", f"{cls}.{_text(src, pname_node)}",
                                    _context(src, member.start_byte), {"deps": [ptype]}))
                        cls_meta["deps"].append(ptype)
            elif member.type == "field_declaration":
                f_anns = _annotation_names(member, src)
                type_node = member.child_by_field_name("type")
                raw_type = _text(src, type_node) if type_node else ""
                # relazioni JPA sui campi -> navigazione entity->entity (post-pass)
                if f_anns & _JPA_RELATION_ANNOTATIONS and raw_type:
                    gm = _GENERIC_INNER_RE.match(raw_type)
                    target = (gm.group(1) if gm else raw_type).split("<")[0].split(".")[-1]
                    cls_meta.setdefault("attrs", {}).setdefault("_jpa_nav", []).append(target)
                if not (_INJECT_ANNOTATIONS & f_anns):
                    continue
                ftype = raw_type.split("<")[0].split(".")[-1] if raw_type else ""
                for decl in member.children:
                    if decl.type == "variable_declarator":
                        fname_node = decl.child_by_field_name("name")
                        if fname_node is not None:
                            out.append(("field", f"{cls}.{_text(src, fname_node)}",
                                        _context(src, member.start_byte),
                                        {"deps": [ftype] if ftype else []}))
                if ftype:
                    cls_meta["deps"].append(ftype)
            elif member.type in _TYPE_KINDS:  # tipi annidati
                visit_type(member)

    # Visita iterativa dell'intero albero (non solo i figli della root): con errori
    # di sintassi tree-sitter incapsula le dichiarazioni in nodi ERROR intermedi,
    # e così l'estrazione parziale li recupera comunque.
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "package_declaration":
            m = re.search(r"package\s+([\w.]+)", _text(src, node))
            if m:
                package = m.group(1)
        elif node.type == "import_declaration":
            imp = _text(src, node)
            m = re.search(r"import\s+(?:static\s+)?([\w.]+)", imp)
            if m and not imp.rstrip(";\n ").endswith("*"):
                imported.append(m.group(1).split(".")[-1])
        elif node.type in _TYPE_KINDS:
            visit_type(node)  # gestisce da sé i tipi annidati: non si ridiscende
            continue
        stack.extend(reversed(node.children))
    return out


def _local(tag: str) -> str:
    """Nome locale di un tag XML, senza namespace."""
    return tag.rsplit("}", 1)[-1]


def _parse_xml(text: str, what: str):
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        print(f"[warn] parser {what}: XML malformato, file saltato ({e})")
        return None


def pom_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae dal pom.xml il nodo progetto (artifactId) con deps verso le
    <dependency> dichiarate e i <module> di un multi-modulo (archi DEPENDS_ON)."""
    root = _parse_xml(text, "pom")
    if root is None or _local(root.tag) != "project":
        return []
    artifact, deps = "", []
    for child in root:
        tag = _local(child.tag)
        if tag == "artifactId":
            artifact = (child.text or "").strip()
        elif tag == "dependencies":
            for dep in child:
                aid = next(((e.text or "").strip() for e in dep if _local(e.tag) == "artifactId"), "")
                if aid:
                    deps.append(aid)
        elif tag == "modules":
            deps.extend((m.text or "").strip() for m in child if (m.text or "").strip())
    if not artifact:
        return []
    return [("project", artifact, text[:_SNIPPET_LIMIT], {"deps": deps})]


def gradle_symbols(text: str, stem: str, suffix: str, project: str = "") -> list[tuple]:
    """Best-effort su build.gradle: nodo progetto (nome = cartella che lo contiene)
    con deps verso gli artifactId delle dipendenze dichiarate."""
    deps = [m.group(2) for m in _GRADLE_DEP_RE.finditer(text)]
    name = project or stem
    return [("project", name, text[:_SNIPPET_LIMIT], {"deps": deps})]


def bpmn_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae da un processo Kogito (.bpmn/.bpmn2) i nodi processo, con deps verso
    le classi Java referenziate dai service task (FQCN in attributi/estensioni)
    e verso i processi chiamati dai call activity."""
    root = _parse_xml(text, "bpmn")
    if root is None:
        return []
    out: list[tuple] = []
    for proc in root.iter():
        if _local(proc.tag) != "process":
            continue
        pid = proc.get("id") or proc.get("name") or stem
        deps: list[str] = []
        for el in proc.iter():
            tag = _local(el.tag)
            if tag == "serviceTask":
                blob = ET.tostring(el, encoding="unicode")
                deps.extend(m.group(1) for m in _FQCN_RE.finditer(blob))
            elif tag == "callActivity":
                called = el.get("calledElement")
                if called:
                    deps.append(called)
        out.append(("process", pid, text[:_SNIPPET_LIMIT],
                    {"deps": sorted(set(deps))}))
    return out


def dmn_symbols(text: str, stem: str, suffix: str) -> list[tuple]:
    """Estrae da un file DMN i nodi decisione (id/nome). TODO(2026-07-12): link
    fini decisione->processo/classi (per ora solo nodi)."""
    root = _parse_xml(text, "dmn")
    if root is None:
        return []
    return [("decision", d.get("id") or d.get("name") or stem, text[:_SNIPPET_LIMIT])
            for d in root.iter() if _local(d.tag) == "decision"]


# ---------------------------------------------------------- resolver JPA --

def resolve_jpa(symbols: list[dict]) -> None:
    """Post-pass JPA (analogo di resolve_ef in code_index_csharp): mapping
    entity->tabella ([Table] o convenzione Hibernate, lowercase per
    riconciliarsi coi nodi del parser SQL) con nodi tabella placeholder
    quando il DDL non e' ancora indicizzato, e relazioni di navigazione
    @OneToMany/@ManyToOne/@OneToOne/@ManyToMany -> REFERENCES entity->entity.
    Rimuove sempre le chiavi temporanee (_jpa_table/_jpa_nav)."""
    table_nodes = {s["name"] for s in symbols if s["kind"] == "table"}
    entity_names = {s["name"] for s in symbols
                    if "_jpa_table" in (s.get("attrs") or {})}

    placeholders: list[dict] = []
    for sym in symbols:
        attrs = sym.get("attrs") or {}
        table = attrs.pop("_jpa_table", None)
        nav = attrs.pop("_jpa_nav", None)
        if table:
            sym["links"] = sorted(set(sym["links"]) | {("REFERENCES", table)})
            if table not in table_nodes:
                table_nodes.add(table)
                placeholders.append({
                    "id": f"{sym['file']}::{table}",
                    "name": table, "kind": "table", "file": sym["file"],
                    "dev_type": sym["dev_type"],
                    "text": f"table {table}\n(placeholder JPA: DDL non indicizzato, "
                            f"riconciliato per nome quando il parser SQL lo trovera')",
                    "deps": [], "refs": [], "links": [], "package": "",
                    "attrs": {"placeholder": True},
                })
        if nav:
            targets = {t for t in nav if t in entity_names and t != sym["name"]}
            if targets:
                sym["refs"] = sorted(set(sym["refs"]) | targets)
    symbols.extend(placeholders)
