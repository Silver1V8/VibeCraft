"""Semantica framework-aware per il frontend: React (.tsx/.jsx) e Angular
(.ts + template .html), sopra il parser TypeScript tree-sitter esistente —
stesso pattern dei decoratori FastAPI nel parser Python.

Il framework si rileva PER PROGETTO dalle dipendenze del package.json più
vicino nel filesystem (react -> React, @angular/core -> Angular), non
dall'estensione del file: evita falsi positivi incrociati. Senza framework
riconosciuto i file restano sul parser TS sintattico.

React (tree-sitter, grammatica tsx): componenti (funzione/classe PascalCase
con JSX nel body o che estende Component), archi componente->componente dai
tag JSX risolti via import/definizioni locali, custom hook (use* che chiama
altri hook) e archi componente->hook, route React Router (<Route path
element>) e file-based Next.js (pages/, app/) -> componenti routable.

Angular (estrazione decorator-driven, regex su segmenti di classe):
@Component (selector come metadato, templateUrl/styleUrls -> archi verso i
file), @Injectable -> kind service, DI via costruttore, @NgModule
(declarations/imports/providers), routing (component:/loadChildren/
loadComponent -> routable + moduli lazy), HttpClient con URL letterale ->
endpoint-esterno (assoluti) o metadato http_calls (relativi), che
resolve_http_calls abbina agli endpoint backend del grafo con archi CALLS.

I riferimenti che richiedono la vista d'insieme (templateUrl, selector nei
template, route verso componenti di altri file) passano da chiavi temporanee
risolte dal post-pass `resolve_frontend`, come gli altri resolver.
"""

import json
import posixpath
import re
from pathlib import Path

from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

_PASCAL_RE = re.compile(r"^[A-Z]\w*$")
_HOOK_NAME_RE = re.compile(r"^use[A-Z]\w*$")
_IMPORT_RE = re.compile(r"import\s+(?:type\s+)?(?:\{([^}]*)\}|(\w+))\s*(?:,\s*\{([^}]*)\})?\s+from")
_ROUTE_JSX_RE = re.compile(r"<Route\s[^>]*path=[\"']([^\"']+)[\"'][^>]*element=\{<(\w+)")

_framework_cache: dict[str, str] = {}


def detect_framework(code_dir: Path | None, rel: str) -> str:
    """Framework del progetto a cui appartiene `rel`: cerca il package.json
    più vicino risalendo le cartelle. 'react' | 'angular' | ''. """
    if code_dir is None:
        return ""
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    while True:
        cached = _framework_cache.get(f"{code_dir}|{folder}")
        if cached is not None:
            return cached
        pkg = code_dir / folder / "package.json" if folder else code_dir / "package.json"
        fw = None
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
                deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
                fw = "angular" if "@angular/core" in deps else ("react" if "react" in deps else "")
            except Exception:
                fw = ""
        if fw is not None:
            _framework_cache[f"{code_dir}|{folder}"] = fw
            return fw
        if not folder:
            _framework_cache[f"{code_dir}|"] = ""
            return ""
        folder = folder.rsplit("/", 1)[0] if "/" in folder else ""


# ------------------------------------------------------------------- React --

def react_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Componenti, hook e route da un file React (tsx/jsx, tree-sitter)."""
    src = text.encode("utf-8")
    tree = _pack_parser("tsx").parse(src)

    imported: set[str] = set()
    for m in _IMPORT_RE.finditer(text):
        for grp in m.groups():
            if grp:
                imported.update(p.strip().split(" as ")[-1] for p in grp.split(","))

    def node_text(n) -> str:
        return src[n.start_byte:n.end_byte].decode("utf-8", "ignore")

    def scan_body(n):
        """(tag JSX PascalCase, hook chiamati, contiene JSX?) nel sottoalbero."""
        tags, hooks, has_jsx = set(), set(), False
        stack = [n]
        while stack:
            c = stack.pop()
            if c.type in ("jsx_opening_element", "jsx_self_closing_element"):
                has_jsx = True
                ident = next((x for x in c.children if x.type == "identifier"), None)
                if ident is not None and _PASCAL_RE.match(node_text(ident)):
                    tags.add(node_text(ident))
            elif c.type == "call_expression":
                fn = c.children[0] if c.children else None
                if fn is not None and fn.type == "identifier" and _HOOK_NAME_RE.match(node_text(fn)):
                    hooks.add(node_text(fn))
            stack.extend(c.children)
        return tags, hooks, has_jsx

    candidates: list[tuple[str, object]] = []   # (nome, nodo dichiarazione)
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "function_declaration":
            name_node = n.child_by_field_name("name")
            if name_node is not None:
                candidates.append((node_text(name_node), n))
        elif n.type == "variable_declarator":
            name_node = n.child_by_field_name("name")
            value = n.child_by_field_name("value")
            if (name_node is not None and value is not None
                    and value.type in ("arrow_function", "function_expression")):
                candidates.append((node_text(name_node), n))
        elif n.type == "class_declaration":
            name_node = n.child_by_field_name("name")
            if name_node is not None:
                candidates.append((node_text(name_node), n))
        stack.extend(n.children)

    local_names = {name for name, _ in candidates}
    out: list[tuple] = []
    routes: dict[str, str] = {m.group(2): m.group(1) for m in _ROUTE_JSX_RE.finditer(text)}
    # Next.js file-based routing: componenti sotto pages/ o app/ sono routable
    is_file_route = bool(re.search(r"(?:^|/)(?:pages|app)/", rel))

    for name, n in candidates:
        tags, hooks, has_jsx = scan_body(n)
        extends_component = "Component" in node_text(n)[:200] and n.type == "class_declaration"
        snippet = src[max(0, n.start_byte - 40):n.start_byte + _CONTEXT_SPAN].decode("utf-8", "ignore")
        deps = sorted((tags & (imported | local_names)) - {name}) + sorted(hooks)
        meta: dict = {"deps": deps, "attrs": {}}
        if _HOOK_NAME_RE.match(name) and hooks:
            out.append(("hook", name, snippet, meta))
        elif _PASCAL_RE.match(name) and (has_jsx or extends_component):
            if name in routes:
                meta["attrs"].update(routable=True, route=routes[name])
            elif is_file_route:
                meta["attrs"].update(routable=True, route="/" + rel.rsplit(".", 1)[0])
            out.append(("component", name, snippet, meta))
        else:
            out.append(("function", name, snippet, meta if deps else None))

    # route verso componenti definiti altrove: le marca il resolver
    external_routes = {c: p for c, p in routes.items() if c not in local_names}
    result = [t if t[3] is not None else t[:3] for t in out]
    if external_routes and result:
        first = result[0]
        meta = first[3] if len(first) > 3 else {}
        meta.setdefault("attrs", {})["_routes"] = external_routes
        result[0] = first[:3] + (meta,)
    return result


# ------------------------------------------------------------------ Angular --

_DECORATED_CLASS_RE = re.compile(
    r"@(Component|Injectable|NgModule|Directive|Pipe)\s*\(\s*(\{[\s\S]*?\})?\s*\)\s*"
    r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)")
_SELECTOR_RE = re.compile(r"selector\s*:\s*['\"]([^'\"]+)['\"]")
_TEMPLATE_URL_RE = re.compile(r"templateUrl\s*:\s*['\"]([^'\"]+)['\"]")
_STYLE_URLS_RE = re.compile(r"styleUrls?\s*:\s*\[([^\]]*)\]")
_NG_ARRAY_RE = re.compile(r"(declarations|imports|providers)\s*:\s*\[([^\]]*)\]")
_CTOR_RE = re.compile(r"constructor\s*\(([^)]*)\)")
_CTOR_PARAM_RE = re.compile(r"(?:@\w+\(\)\s*)?(?:private|public|protected|readonly|\s)+\w+\s*:\s*([A-Z]\w*)")
_ROUTE_COMPONENT_RE = re.compile(r"path\s*:\s*['\"]([^'\"]*)['\"][\s\S]{0,120}?component\s*:\s*(\w+)")
_LAZY_RE = re.compile(r"(?:loadChildren|loadComponent)\s*:\s*\(\)\s*=>\s*import\(\s*['\"]([^'\"]+)['\"]")
_HTTP_CALL_RE = re.compile(r"\.(?:get|post|put|delete|patch)(?:<[^>]*>)?\(\s*[`'\"]([^`'\"]+)[`'\"]")
_URL_HOST_RE = re.compile(r"^https?://([^/:]+)", re.I)
_TEMPLATE_SELECTOR_RE = re.compile(r"<([a-z][\w]*-[\w-]+)")

_NG_KIND = {"Component": "component", "Injectable": "service", "NgModule": "module",
            "Directive": "directive", "Pipe": "pipe"}


def angular_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Classi decorate Angular + semantica (selector, templateUrl, DI, routing,
    HttpClient). Le classi non decorate restano al parser TS sintattico."""
    from code_index.ts import ts_symbols
    base = {name: (kind, name, snip) for kind, name, snip in ts_symbols(text, stem, suffix)}

    out: list[tuple] = []
    decorated: set[str] = set()
    matches = list(_DECORATED_CLASS_RE.finditer(text))
    for i, m in enumerate(matches):
        deco, config, cls = m.group(1), m.group(2) or "", m.group(3)
        decorated.add(cls)
        # segmento della classe: dal decoratore alla prossima classe decorata
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        segment = text[m.start():end]
        attrs: dict = {}
        deps: list[str] = []
        links: list[tuple[str, str]] = []
        sel = _SELECTOR_RE.search(config)
        if sel:
            attrs["selector"] = sel.group(1)
        tpl = _TEMPLATE_URL_RE.search(config)
        if tpl:
            deps.append(f"file:{tpl.group(1)}")   # componente -> template (il link chiave)
        st = _STYLE_URLS_RE.search(config)
        if st:
            deps.extend(f"file:{s.strip().strip(chr(39) + chr(34))}"
                        for s in st.group(1).split(",") if s.strip())
        for _, names in _NG_ARRAY_RE.findall(config):
            deps.extend(n.strip() for n in names.split(",") if _PASCAL_RE.match(n.strip() or "-"))
        ctor = _CTOR_RE.search(segment)
        if ctor:  # injection via costruttore -> archi verso i servizi
            deps.extend(_CTOR_PARAM_RE.findall(ctor.group(1)))
        for url in _HTTP_CALL_RE.findall(segment):
            host = _URL_HOST_RE.match(url)
            if host:
                out.append(("external-endpoint", host.group(1).lower(),
                            f"external endpoint {host.group(1)} (HttpClient da {cls})"))
                deps.append(host.group(1).lower())
            else:
                attrs.setdefault("http_calls", []).append(url)
                # Abbinata agli endpoint del backend dal post-pass resolve_http_calls
                # (senza metodo: l'HttpClient qui non viene letto, vale ogni metodo).
        snippet = text[max(0, m.start() - 40):m.start() + _CONTEXT_SPAN]
        out.append((_NG_KIND[deco], cls, snippet,
                    {"deps": sorted(set(deps)), "attrs": attrs, "links": links}))

    # route e lazy import sono spesso dichiarati a livello di file (const routes
    # sopra il decoratore): si scansiona tutto il testo e si attacca al primo
    # simbolo decorato (il resolver marca i componenti per nome)
    idx = next((i for i, t in enumerate(out) if t[0] in _NG_KIND.values()), None)
    if idx is not None:
        first_meta = out[idx][3]
        routes = {c: p for p, c in _ROUTE_COMPONENT_RE.findall(text)}
        if routes:
            first_meta.setdefault("attrs", {})["_routes"] = routes
        lazy_deps = [f"file:{path}" for path in _LAZY_RE.findall(text)]
        if lazy_deps:
            first_meta["deps"] = sorted(set(first_meta.get("deps") or []) | set(lazy_deps))
        out[idx] = out[idx][:3] + (first_meta,)

    # il resto dei simboli TS (classi non decorate, funzioni) resta invariato
    out.extend(tup for name, tup in base.items() if name not in decorated)
    return out


def angular_template_meta(text: str) -> dict:
    """Selector usati in un template .html Angular (tag con trattino):
    servono a resolve_frontend per gli archi componente->componente."""
    used = sorted(set(_TEMPLATE_SELECTOR_RE.findall(text)))
    return {"_used_selectors": used} if used else {}


# ----------------------------------------------------------------- resolver --

def resolve_frontend(symbols: list[dict]) -> None:
    """Post-pass frontend: risolve i dep `file:<percorso>` (templateUrl,
    styleUrls, lazy import) sui simboli dei file raggiunti, crea gli archi
    componente->componente dai selector usati nei template, e marca routable
    i componenti citati dalle route di altri file. Rimuove le chiavi
    temporanee (_routes, _used_selectors)."""
    by_file: dict[str, list[dict]] = {}
    by_name: dict[str, dict] = {}
    selector_to_comp: dict[str, str] = {}
    for s in symbols:
        by_file.setdefault(s["file"], []).append(s)
        by_name.setdefault(s["name"], s)
        sel = (s.get("attrs") or {}).get("selector")
        if sel:
            selector_to_comp[sel] = s["name"]

    def find_file(source: str, raw: str) -> str | None:
        target = raw.replace("\\", "/").removeprefix("./")
        folder = source.rsplit("/", 1)[0] if "/" in source else ""
        normalized = posixpath.normpath(posixpath.join(folder, target)) if folder else target
        for cand in (normalized, normalized + ".ts", target, target + ".ts"):
            if cand in by_file:
                return cand
        base = target.rsplit("/", 1)[-1]
        for rel_file in by_file:
            if rel_file.endswith("/" + base) or rel_file == base:
                return rel_file
        return None

    routes: dict[str, str] = {}
    for sym in symbols:
        attrs = sym.get("attrs") or {}
        routes.update(attrs.pop("_routes", {}))
        deps, resolved = sym.get("deps") or [], []
        for dep in deps:
            if not dep.startswith("file:"):
                resolved.append(dep)
                continue
            rel_file = find_file(sym["file"], dep[5:])
            if rel_file is None:
                continue  # file non indicizzato: niente nodi fantasma
            targets = by_file[rel_file]
            main = next((t for t in targets if t["kind"] in
                         ("template", "stylesheet", "module", "component")), targets[0])
            resolved.append(main["name"])
            # selector usati nel template -> archi componente -> componente
            for used in (main.get("attrs") or {}).pop("_used_selectors", []):
                comp = selector_to_comp.get(used)
                if comp and comp != sym["name"]:
                    resolved.append(comp)
        sym["deps"] = sorted(set(resolved))

    for comp_name, path in routes.items():
        comp = by_name.get(comp_name)
        if comp is not None and comp["kind"] in ("component", "module"):
            comp["attrs"].setdefault("routable", True)
            comp["attrs"].setdefault("route", path)
    # pulizia: template mai raggiunti da un componente
    for sym in symbols:
        (sym.get("attrs") or {}).pop("_used_selectors", None)


def _route_segments(path: str) -> list[str]:
    return [s.lower() for s in path.split("?", 1)[0].split("/") if s]


def resolve_http_calls(symbols: list[dict]) -> None:
    """Ponte frontend->backend: ogni `http_calls` ("METHOD /path" da ts.http_calls_by_symbol,
    o URL relativa senza metodo dall'HttpClient Angular) diventa un link ("CALLS", endpoint)
    verso gli endpoint con method+route (oggi le Minimal API C#). Segmento per segmento: `*`
    del chiamante e `{param}` della route valgono qualunque segmento; senza metodo noto si
    abbina ogni metodo. Euristica sul testo, quindi arco `inferred` (rag_config.yaml)."""
    endpoints = [(a["method"], _route_segments(a["route"]), s["name"]) for s in symbols
                 if s["kind"] == "endpoint" and "method" in (a := s.get("attrs") or {}) and "route" in a]
    if not endpoints:
        return
    for s in symbols:
        calls = (s.get("attrs") or {}).get("http_calls") or []
        found = set()
        for call in calls:
            method, _, path = call.rpartition(" ")
            segs = _route_segments(path)
            for ep_method, ep_segs, ep_name in endpoints:
                if ((not method or method == ep_method) and len(segs) == len(ep_segs)
                        and all(a in ("*", b) or b.startswith("{") for a, b in zip(segs, ep_segs))):
                    found.add(("CALLS", ep_name))
        if found:
            s["links"] = sorted(set(s["links"]) | found)
