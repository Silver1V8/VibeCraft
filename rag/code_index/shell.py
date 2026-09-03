"""Parser per gli script operazionali: Bash (.sh) e PowerShell (.ps1/.psm1),
entrambi via tree-sitter dal language-pack.

Scelta PowerShell: la grammatica, testata sul corpus reale (function, dot
sourcing `. .\\x.ps1`, call operator `& "x.ps1"`, Import-Module, invocazioni
dirette `.\\x.ps1`), parsa tutto pulito con command_name/command_elements
espliciti — quindi niente scanner regex: stessa strada tree-sitter di Bash.

Nodi: "script" per file (name = nome file, com'è invocato dagli altri
script) e "function" (name = stem.funzione). Archi EXECUTES script->script
e riferimenti incrociati script->progetto/file (dotnet build su .csproj,
sqlcmd/psql su .sql, source/dot-sourcing) emessi come link "run:<percorso>"
e risolti da resolve_script_refs sui percorsi relativi, best-effort: i
percorsi non risolti decadono senza creare nodi fantasma.

Error recovery: errori di sintassi -> estrazione parziale con warning;
eccezioni -> nodo script senza dettagli.
"""

import posixpath

from tree_sitter_language_pack import get_parser as _pack_parser

_SNIPPET_LIMIT = 1500
_CONTEXT_SPAN = 400

# Comandi operazionali rilevanti: registrati come metadati del nodo script
_RELEVANT = {"docker", "dotnet", "mvn", "git", "psql", "sqlcmd", "kubectl", "npm", "uv"}
# Interpreti il cui primo argomento è uno script da collegare
_INTERPRETERS = {"bash", "sh", "pwsh", "powershell", "zsh"}
# Estensioni dei file che, se argomento di un comando rilevante, diventano link
_LINKABLE_EXT = (".sh", ".ps1", ".psm1", ".csproj", ".sql", ".pks", ".pkb")


def _clean(raw: str) -> str:
    """Normalizza un percorso invocato: via quote, backslash -> slash."""
    return raw.strip().strip("\"'").replace("\\", "/")


def _looks_like_script(token: str) -> bool:
    t = _clean(token).lower()
    return t.endswith((".sh", ".ps1", ".psm1")) or t.startswith("./")


class _Collector:
    def __init__(self, stem: str):
        self.stem = stem
        self.functions: list[tuple[str, str]] = []   # (nome, snippet)
        self.runs: list[str] = []                    # percorsi invocati (raw)
        self.commands: set[str] = set()              # comandi rilevanti visti

    def command(self, name: str, args: list[str]) -> None:
        name_c = _clean(name)
        base = name_c.rsplit("/", 1)[-1].lower()
        if base in ("source", "."):
            if args:
                self.runs.append(args[0])
        elif _looks_like_script(name_c):
            self.runs.append(name_c)
        elif base in _INTERPRETERS:
            for a in args:
                if _looks_like_script(a):
                    self.runs.append(a)
                    break
        elif base == "import-module":
            if args and ("/" in _clean(args[0]) or _clean(args[0]).lower().endswith((".psm1", ".ps1"))):
                self.runs.append(args[0])
            elif args:
                self.commands.add(f"module:{_clean(args[0])}")
        elif base in _RELEVANT:
            self.commands.add(base)
            for a in args:
                if _clean(a).lower().endswith(_LINKABLE_EXT):
                    self.runs.append(a)


def _walk_bash(text: str, col: _Collector) -> bool:
    src = text.encode("utf-8")
    tree = _pack_parser("bash").parse(src)
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "function_definition":
            name = next((c for c in n.children if c.type == "word"), None)
            if name is not None:
                col.functions.append((src[name.start_byte:name.end_byte].decode("utf-8", "ignore"),
                                      src[max(0, n.start_byte - 40):n.start_byte + _CONTEXT_SPAN]
                                      .decode("utf-8", "ignore")))
        elif n.type == "command":
            name, args = "", []
            for c in n.children:
                t = src[c.start_byte:c.end_byte].decode("utf-8", "ignore")
                if c.type == "command_name":
                    name = t
                elif c.type in ("word", "string", "raw_string", "concatenation", "number"):
                    args.append(t)
            if name:
                col.command(name, args)
        stack.extend(reversed(n.children))
    return tree.root_node.has_error


def _walk_powershell(text: str, col: _Collector) -> bool:
    src = text.encode("utf-8")
    tree = _pack_parser("powershell").parse(src)
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type == "function_statement":
            name = next((c for c in n.children if c.type == "function_name"), None)
            if name is not None:
                col.functions.append((src[name.start_byte:name.end_byte].decode("utf-8", "ignore"),
                                      src[max(0, n.start_byte - 40):n.start_byte + _CONTEXT_SPAN]
                                      .decode("utf-8", "ignore")))
        elif n.type == "command":
            name, args, dot_or_amp = "", [], False
            for c in n.children:
                t = src[c.start_byte:c.end_byte].decode("utf-8", "ignore")
                if c.type == "command_invokation_operator":
                    dot_or_amp = t.strip() in (".", "&")
                elif c.type in ("command_name", "command_name_expr"):
                    name = t
                elif c.type == "command_elements":
                    args = [src[e.start_byte:e.end_byte].decode("utf-8", "ignore")
                            for e in c.children
                            if e.type in ("generic_token", "string_literal", "variable")]
            if dot_or_amp and name:
                col.runs.append(name)   # dot-sourcing o call operator
            elif name:
                col.command(name, args)
        stack.extend(reversed(n.children))
    return tree.root_node.has_error


def shell_symbols(text: str, stem: str, suffix: str, rel: str = "") -> list[tuple]:
    """Estrae da uno script Bash/PowerShell il nodo script (con i comandi
    rilevanti come metadati e i link run: da risolvere), più i nodi funzione."""
    fname = rel.rsplit("/", 1)[-1] if rel else f"{stem}{suffix}"
    col = _Collector(stem)
    try:
        had_error = (_walk_bash if suffix == ".sh" else _walk_powershell)(text, col)
    except Exception as e:
        print(f"[warn] parser shell: {rel or fname} illeggibile, nodo senza dettagli ({e})")
        return [("script", fname, text[:_SNIPPET_LIMIT])]
    if had_error:
        print(f"[warn] parser shell: errori di sintassi in {rel or fname}, estrazione parziale")

    attrs: dict = {}
    cmds = sorted(c for c in col.commands if not c.startswith("module:"))
    mods = sorted(c.split(":", 1)[1] for c in col.commands if c.startswith("module:"))
    if cmds:
        attrs["commands"] = cmds
    if mods:
        attrs["modules"] = mods
    links = [("EXECUTES", f"run:{_clean(r)}") for r in dict.fromkeys(col.runs)]
    out: list[tuple] = [("script", fname, text[:_SNIPPET_LIMIT],
                         {"attrs": attrs, "links": links})]
    out.extend(("function", f"{stem}.{fn}", snippet) for fn, snippet in col.functions)
    return out


def resolve_script_refs(symbols: list[dict]) -> None:
    """Risolve i link run:<percorso> degli script in nomi di simboli reali,
    best-effort sui percorsi relativi alla cartella dello script. Il target è
    il simbolo rappresentativo del file raggiunto (script/project, altrimenti
    il primo simbolo del file); i percorsi non risolti decadono."""
    by_file: dict[str, list[dict]] = {}
    for s in symbols:
        by_file.setdefault(s["file"], []).append(s)

    def representative(rel_file: str) -> str | None:
        syms = by_file.get(rel_file) or []
        for s in syms:
            if s["kind"] in ("script", "project", "package"):
                return s["name"]
        return syms[0]["name"] if syms else None

    def find(source_file: str, raw: str) -> str | None:
        target = _clean(raw).removeprefix("./")
        folder = source_file.rsplit("/", 1)[0] if "/" in source_file else ""
        normalized = posixpath.normpath(posixpath.join(folder, target)) if folder else target
        for cand in (normalized, target):
            if cand in by_file:
                return representative(cand)
        base = target.rsplit("/", 1)[-1]
        for rel_file in by_file:
            if rel_file == base or rel_file.endswith("/" + base):
                return representative(rel_file)
        return None

    for sym in symbols:
        if not any(t.startswith("run:") for _, t in sym.get("links") or []):
            continue
        resolved = []
        for lrel, t in sym["links"]:
            if t.startswith("run:"):
                name = find(sym["file"], t[4:])
                if name and name != sym["name"]:
                    resolved.append((lrel, name))
            else:
                resolved.append((lrel, t))
        sym["links"] = sorted(set(resolved))
