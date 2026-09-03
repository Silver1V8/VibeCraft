"""Scanner ibrido per la famiglia Razor (.cshtml / .razor) + resolver dei link
per convenzione ASP.NET. Niente grammatica tree-sitter Razor (immatura): uno
scanner unico separa direttive e blocchi C# dal markup, e delega i frammenti
C# (@code/@functions) al parser tree-sitter C# esistente (code_index.csharp).

Dialetti riconosciuti dallo scanner unico:
  - .razor                     -> componente Blazor (kind "component");
  - .cshtml con @page          -> Razor Page (kind "page");
  - .cshtml senza @page        -> view MVC, incluse partial e layout (kind "view").

I nodi Razor hanno name = percorso relativo senza estensione (univoco: gli
stem delle view MVC collidono tra controller). I riferimenti che richiedono
la vista d'insieme dei file (code-behind, Views/{Ctrl}/{Azione}, componenti,
asp-page) sono emessi come dep "tipizzate" (`view:...`, `page:...`, ecc.) e
risolti da `resolve_links` DOPO la scansione di tutto code/: le dep risolte
diventano nomi di simboli reali (archi DEPENDS_ON via link_symbols), quelle
non risolte diventano segnalazioni di link rotto nel report di governance —
mai nodi fantasma.

Fuori scope (permanente, non un piano): VB.NET views (.vbhtml), analisi dell'HTML/JS
interno alle view, CSS isolation (.razor.css).
"""

import re
from pathlib import Path

_SNIPPET_LIMIT = 1500

# --- direttive e costrutti comuni a tutti i dialetti -------------------------
_PAGE_RE = re.compile(r'^\s*@page(?:\s+"([^"]*)")?', re.M)
_MODEL_RE = re.compile(r"^\s*@model\s+([\w.<>?]+)", re.M)
_INHERITS_RE = re.compile(r"^\s*@inherits\s+([\w.<>?]+)", re.M)
_USING_RE = re.compile(r"^\s*@using\s+([\w.]+)", re.M)
_INJECT_RE = re.compile(r"^\s*@inject\s+([\w.<>?]+)\s+\w+", re.M)
_LAYOUT_RE = re.compile(r'Layout\s*=\s*"([^"]+)"')
_SECTION_RE = re.compile(r"@section\s+(\w+)")

_PARTIAL_HELPER_RE = re.compile(r'Html\.(?:Partial|RenderPartial|PartialAsync)\s*\(\s*"([^"]+)"')
_PARTIAL_TAG_RE = re.compile(r'<partial\s+[^>]*name="([^"]+)"')
# Html.ActionLink("testo", "Azione"[, "Controller"]) / Url.Action / Html.BeginForm
_ACTIONLINK_RE = re.compile(r'Html\.ActionLink\(\s*"[^"]*"\s*,\s*"(\w+)"(?:\s*,\s*"(\w+)")?')
_URLACTION_RE = re.compile(r'(?:Url\.Action|Html\.BeginForm)\(\s*"(\w+)"(?:\s*,\s*"(\w+)")?')
_TAG_RE = re.compile(r"<[^>!/][^>]*>")
_ASP_ATTR_RE = re.compile(r'(asp-[\w-]+)="([^"]+)"')

# --- Blazor -------------------------------------------------------------------
_COMPONENT_TAG_RE = re.compile(r"<([A-Z]\w*)[\s/>]")
_CODE_BLOCK_RE = re.compile(r"@(?:code|functions)\s*\{")
_PARAMETER_RE = re.compile(r"\[Parameter[^\]]*\]\s*public\s+([\w.<>?]+)\s+(\w+)")

# Elementi/omponenti del framework che non vanno cercati nel progetto
_FRAMEWORK_COMPONENTS = {
    "EditForm", "InputText", "InputNumber", "InputSelect", "InputDate",
    "InputCheckbox", "InputTextArea", "InputRadio", "InputRadioGroup", "InputFile",
    "ValidationSummary", "ValidationMessage", "DataAnnotationsValidator",
    "NavLink", "RouteView", "Router", "LayoutView", "CascadingValue",
    "ErrorBoundary", "PageTitle", "HeadContent", "HeadOutlet", "Virtualize",
    "AuthorizeView", "CascadingAuthenticationState", "FocusOnNavigate",
}

# File di soli import: letti dal resolver per la risoluzione dei nomi,
# non producono nodi (né endpoint né view).
_IMPORTS_STEMS = {"_Imports", "_ViewImports"}


def _code_blocks(text: str) -> list[str]:
    """Contenuto dei blocchi @code/@functions { ... } (bilanciamento graffe)."""
    out = []
    for m in _CODE_BLOCK_RE.finditer(text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        out.append(text[m.end():i - 1])
    return out


def _simple(type_name: str) -> str:
    return type_name.split("<")[0].split(".")[-1]


def razor_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Estrae il nodo view/page/component da un file Razor, con dep tipizzate da
    risolvere in `resolve_links`. Error recovery: qualunque eccezione degrada a
    nodo senza dettagli con warning."""
    if stem in _IMPORTS_STEMS:
        return []
    name = (rel.rsplit(".", 1)[0] if rel else stem)
    try:
        return _scan(text, stem, suffix, name, rel)
    except Exception as e:
        print(f"[warn] parser razor: {rel or stem}{suffix} malformato, nodo senza dettagli ({e})")
        kind = "component" if suffix == ".razor" else "view"
        return [(kind, name, text[:_SNIPPET_LIMIT])]


def _scan(text: str, stem: str, suffix: str, name: str, rel: str) -> list[tuple]:
    page_m = _PAGE_RE.search(text)
    if suffix == ".razor":
        kind = "component"
    else:
        kind = "page" if page_m else "view"

    deps: list[str] = []
    refs: list[str] = []
    attrs: dict = {}
    usings = _USING_RE.findall(text)
    if usings:
        attrs["usings"] = usings

    # direttive comuni: model/inherits/inject -> REFERENCES verso classi/servizi
    for rx in (_MODEL_RE, _INHERITS_RE, _INJECT_RE):
        refs.extend(_simple(t) for t in rx.findall(text))
    # layout e @section
    for lay in _LAYOUT_RE.findall(text):
        deps.append(f"layout:{lay.rsplit('/', 1)[-1].removesuffix('.cshtml')}")
    sections = _SECTION_RE.findall(text)
    if sections:
        attrs["sections"] = sections
    # partial view
    for p in _PARTIAL_HELPER_RE.findall(text) + _PARTIAL_TAG_RE.findall(text):
        deps.append(f"partial:{p.rsplit('/', 1)[-1].removesuffix('.cshtml')}")
    # riferimenti ad azioni MVC (controller vuoto = quello della view corrente)
    for action, ctrl in _ACTIONLINK_RE.findall(text) + _URLACTION_RE.findall(text):
        deps.append(f"action:{ctrl}/{action}")
    # tag helper asp-*
    for tag in _TAG_RE.findall(text):
        asp = dict(_ASP_ATTR_RE.findall(tag))
        if "asp-action" in asp:
            deps.append(f"action:{asp.get('asp-controller', '')}/{asp['asp-action']}")
        if asp.get("asp-page"):
            deps.append(f"page:{asp['asp-page']}")

    if page_m:
        attrs["route"] = page_m.group(1) or ""
        attrs["routable"] = True
    deps.append("codebehind:")  # risolto solo se il file gemello esiste

    out: list[tuple] = []
    code_symbols: list[tuple] = []
    if suffix == ".razor":
        # componenti referenziati nel markup (tag PascalCase, esclusi i builtin)
        for comp in sorted(set(_COMPONENT_TAG_RE.findall(text))):
            if comp not in _FRAMEWORK_COMPONENTS and comp != stem:
                deps.append(f"component:{comp}")
        # blocchi @code: [Parameter]/EventCallback come metadati, metodi via parser C#
        params, callbacks = [], []
        for block in _code_blocks(text):
            for ptype, pname in _PARAMETER_RE.findall(block):
                (callbacks if ptype.startswith("EventCallback") else params).append(pname)
            code_symbols.extend(_code_block_symbols(block, name, stem))
        if params:
            attrs["parameters"] = params
        if callbacks:
            attrs["event_callbacks"] = callbacks

    snippet = text[:_SNIPPET_LIMIT]
    out.append((kind, name, snippet, {"deps": deps, "refs": refs, "attrs": attrs}))
    out.extend(code_symbols)
    return out


def _code_block_symbols(block: str, owner: str, stem: str) -> list[tuple]:
    """Metodi pubblici del blocco @code, estratti col parser tree-sitter C#
    (il blocco viene avvolto in una classe fittizia col nome del componente)."""
    from code_index.csharp import csharp_symbols
    out = []
    for tup in csharp_symbols(f"class {stem} {{\n{block}\n}}", stem, ".razor@code"):
        kind, mname = tup[0], tup[1]
        if kind in ("method", "endpoint") and mname.startswith(f"{stem}."):
            out.append(("method", f"{owner}.{mname.split('.', 1)[1]}", tup[2]))
    return out


# ------------------------------------------------------------------ resolver --

def _collect_imports_usings(code_dir: Path) -> dict[str, list[str]]:
    """@using dei file _Imports.razor/_ViewImports.cshtml, per cartella."""
    usings: dict[str, list[str]] = {}
    for pattern in ("**/_Imports.razor", "**/_ViewImports.cshtml"):
        for path in code_dir.glob(pattern):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            folder = path.parent.relative_to(code_dir).as_posix()
            usings.setdefault(folder, []).extend(_USING_RE.findall(text))
    return usings


def _proximity(a: str, b: str) -> int:
    """Lunghezza del prefisso di cartelle comune tra due percorsi relativi."""
    pa, pb = a.split("/"), b.split("/")
    n = 0
    while n < min(len(pa), len(pb)) and pa[n] == pb[n]:
        n += 1
    return n


def resolve_links(symbols: list[dict], code_dir: Path) -> dict:
    """Risolve le dep tipizzate dei simboli Razor/C# in nomi di simboli reali
    (per gli archi DEPENDS_ON) usando le convenzioni ASP.NET. Le dep che non
    risolvono vengono rimosse e segnalate come link rotti; restituisce il
    report di governance {"broken_links": [...], "orphan_views": [...]}."""
    by_file: dict[str, list[dict]] = {}
    for s in symbols:
        by_file.setdefault(s["file"], []).append(s)
    all_names = {s["name"] for s in symbols}
    razor_nodes = [s for s in symbols if s["kind"] in ("view", "page", "component")]
    components = [s for s in razor_nodes if s["kind"] == "component"]
    imports_usings = _collect_imports_usings(code_dir) if code_dir.exists() else {}

    def razor_in(rel: str):
        return next((s for s in by_file.get(rel, [])
                     if s["kind"] in ("view", "page", "component")), None)

    def find_view(ctrl: str, vname: str):
        for cand in (f"Views/{ctrl}/{vname}.cshtml", f"Views/Shared/{vname}.cshtml"):
            for rel in by_file:
                if rel.endswith(cand):
                    return razor_in(rel)
        return None

    broken: list[dict] = []

    def resolve_dep(sym: dict, dep: str) -> str | None:
        """Nome del simbolo target, o None (con eventuale segnalazione)."""
        typ, _, arg = dep.partition(":")
        src_file = sym["file"]
        ctrl_m = re.search(r"Views/(\w+)/", src_file)
        src_ctrl = ctrl_m.group(1) if ctrl_m else ""

        if typ in ("view", "partial", "layout"):
            if typ == "view":
                ctrl, _, vname = arg.partition("/")
            else:
                ctrl, vname = src_ctrl, arg
            target = find_view(ctrl, vname)
            if target is None and typ == "layout":
                # i layout possono stare ovunque: match sullo stem
                target = next((s for s in razor_nodes
                               if s["file"].rsplit("/", 1)[-1] == f"{vname}.cshtml"), None)
            if target is None:
                broken.append({"source": src_file, "target": dep,
                               "reason": f"{typ} '{vname}' non trovata"})
                return None
            return target["name"]

        if typ == "action":
            ctrl, _, action = arg.partition("/")
            ctrl = ctrl or src_ctrl
            name = f"{ctrl}Controller.{action}"
            if name in all_names:
                return name
            broken.append({"source": src_file, "target": dep,
                           "reason": f"action '{ctrl}/{action}' non trovata"})
            return None

        if typ == "page":
            wanted = f"Pages{arg}.cshtml"
            for rel in by_file:
                if rel.endswith(wanted):
                    target = razor_in(rel)
                    if target:
                        return target["name"]
            broken.append({"source": src_file, "target": dep,
                           "reason": f"page '{arg}' non trovata"})
            return None

        if typ == "component":
            cands = [c for c in components if c["file"].rsplit("/", 1)[-1] == f"{arg}.razor"]
            if not cands:
                return None  # probabile componente di libreria: niente nodo fantasma
            if len(cands) > 1:
                # disambigua con gli @using del file e dei _Imports della gerarchia
                ns = set((sym.get("attrs") or {}).get("usings") or [])
                folder = src_file.rsplit("/", 1)[0] if "/" in src_file else ""
                for f, u in imports_usings.items():
                    if folder == f or folder.startswith(f + "/") or f == ".":
                        ns.update(u)
                by_ns = [c for c in cands
                         if any(c["file"].rsplit("/", 1)[0].replace("/", ".").endswith(n.split(".")[-1])
                                for n in ns)]
                cands = by_ns or cands
                cands.sort(key=lambda c: -_proximity(c["file"], src_file))
            return cands[0]["name"]

        if typ == "codebehind":
            twin = src_file + ".cs"
            cls = next((s for s in by_file.get(twin, []) if s["kind"] == "class"), None)
            return cls["name"] if cls else None

        return dep  # dep non tipizzata: passa invariata

    for sym in symbols:
        if not any(":" in d for d in sym.get("deps") or []):
            continue
        resolved: list[str] = []
        for dep in sym["deps"]:
            out = resolve_dep(sym, dep) if ":" in dep else dep
            if out:
                resolved.append(out)
        sym["deps"] = sorted(set(resolved))

    referenced = {d for s in symbols for d in (s.get("deps") or [])}
    referenced |= {r for s in symbols for r in (s.get("refs") or [])}
    orphans = [s["name"] for s in razor_nodes
               if s["kind"] == "view" and s["name"] not in referenced
               and not s["file"].rsplit("/", 1)[-1].startswith("_")]

    for b in broken:
        print(f"[warn] razor governance: link rotto {b['source']} -> {b['target']} ({b['reason']})")
    for o in orphans:
        print(f"[warn] razor governance: view orfana '{o}' (nessun riferimento in ingresso)")
    return {"broken_links": broken, "orphan_views": sorted(orphans)}
