"""Indicizzazione del codice generato (cartella code/) nel grafo della conoscenza.

Estrae i simboli (classi, funzioni, metodi, endpoint, componenti) dai file sotto
code/ e li collega ai documenti normativi con archi IMPLEMENTS calcolati per
similarità semantica, riusando lo stesso modello bge-m3 già caricato per l'indice.

Parser per linguaggio: stdlib `ast` per Python; tree-sitter (code_index.ts.py) —
unica implementazione — per TS/TSX/JS/JSX/Svelte. Le vecchie euristiche regex
(`_js_symbols`) sono state rimosse (A12, 2026-09-03): la migrazione tree-sitter,
completata il 2026-07-12, è rimasta il default in produzione per 53 giorni senza
incidenti, e mantenere un secondo parser mai più esercitato non aveva più
giustificazione. HTML/CSS restano nodi-file senza estrazione di simboli. Copre
i linguaggi effettivamente presenti nelle sottocartelle di code/ (backend,
frontend, logicAgent): non esiste (né è mai esistito) un parser
Java/Quarkus/Kogito in questo repo.
"""

import ast
import re
from pathlib import Path

import numpy as np

from core.config import CODE_EXCLUDED_DIRS
from core.graph_ops import edge_trust_attrs, implements_reliability

# Estensioni considerate "codice sorgente" (allineate a quelle del check drift)
CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".svelte", ".html", ".css",
             ".java", ".bpmn", ".bpmn2", ".dmn", ".cs", ".csproj", ".cshtml", ".razor",
             ".sql", ".pks", ".pkb", ".sh", ".ps1", ".psm1"}
# Nota: gli artefatti Docker (docker-compose*.yml, compose*.yml, Dockerfile —
# senza estensione) sono riconosciuti per NOME via _is_docker_file, non per
# estensione, quindi non figurano in CODE_EXTS.
# File di progetto indicizzati per nome (non per estensione): dipendenze Java/.NET
CODE_FILENAMES = {"pom.xml", "build.gradle", "packages.config"}


def _config_patterns() -> list[str]:
    """Pattern (fnmatch) dei file di configurazione riconosciuti: solo quelli
    noti — gli altri .json/.xml (dati, fixture, export) sono rumore, non
    struttura. Sovrascrivibili in rag_config.yaml (code_parsers.config_patterns)."""
    from code_index.config import DEFAULT_CONFIG_PATTERNS
    try:
        from core.config import CODE_PARSERS
        return CODE_PARSERS.get("config_patterns") or DEFAULT_CONFIG_PATTERNS
    except Exception:
        return DEFAULT_CONFIG_PATTERNS


def _is_config_file(fname: str) -> bool:
    from fnmatch import fnmatch
    low = fname.lower()
    return any(fnmatch(low, pat.lower()) for pat in _config_patterns())


def _is_docker_file(fname: str) -> bool:
    """Artefatti Docker riconosciuti per NOME (code_parsers.docker_patterns):
    docker-compose/compose *.yml e Dockerfile. Gli altri .yml del repo restano
    gestiti dai rispettivi parser (CI, config)."""
    from fnmatch import fnmatch
    from code_index.docker import DEFAULT_DOCKER_PATTERNS
    try:
        from core.config import CODE_PARSERS
        patterns = CODE_PARSERS.get("docker_patterns") or DEFAULT_DOCKER_PATTERNS
    except Exception:
        patterns = DEFAULT_DOCKER_PATTERNS
    low = fname.lower()
    return any(fnmatch(low, pat.lower()) for pat in patterns)


def _is_ci_file(fname: str) -> bool:
    """Pipeline CI/CD riconosciute per NOME (code_parsers.ci_patterns): gli
    altri .yml del repo (config, docker-compose) sono esclusi."""
    from fnmatch import fnmatch
    from code_index.ci import DEFAULT_CI_PATTERNS
    try:
        from core.config import CODE_PARSERS
        patterns = CODE_PARSERS.get("ci_patterns") or DEFAULT_CI_PATTERNS
    except Exception:
        patterns = DEFAULT_CI_PATTERNS
    low = fname.lower()
    return any(fnmatch(low, pat.lower()) for pat in patterns)

_SNIPPET_LIMIT = 1500

_ENTITY_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9_\-]{2,}")


def _snippet(text: str, node: ast.AST) -> str:
    seg = ast.get_source_segment(text, node)
    return (seg or "")[:_SNIPPET_LIMIT]


def _is_http_endpoint(node: ast.AST) -> bool:
    """True se la funzione ha un decoratore HTTP (es. @app.get, @router.post)."""
    for dec in getattr(node, "decorator_list", []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        attr = getattr(target, "attr", None) or getattr(target, "id", None)
        if attr and attr.lower() in ("get", "post", "put", "delete", "patch"):
            return True
    return False


def _py_symbols(text: str) -> list[tuple[str, str, str]]:
    """Estrae simboli Python (top-level + metodi di classe) via AST stdlib."""
    out: list[tuple[str, str, str]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "endpoint" if _is_http_endpoint(node) else "function"
            out.append((kind, node.name, _snippet(text, node)))
        elif isinstance(node, ast.ClassDef):
            out.append(("class", node.name, _snippet(text, node)))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "endpoint" if _is_http_endpoint(sub) else "method"
                    out.append((kind, f"{node.name}.{sub.name}", _snippet(text, sub)))
    return out


def _extract(suffix: str, text: str, stem: str, rel: str = "",
             code_dir: Path | None = None) -> list[tuple]:
    """Estrae i simboli di un file. Le tuple sono (kind, name, snippet) o
    (kind, name, snippet, meta) con meta={"deps": [...], "package": ...}.
    `code_dir` serve al rilevamento del framework frontend per progetto."""
    if suffix == ".py":
        return _py_symbols(text)
    # Frontend framework-aware (React/Angular): il framework si rileva dal
    # package.json del progetto, non dall'estensione (niente falsi positivi).
    if suffix in (".ts", ".tsx", ".jsx", ".html") and code_dir is not None:
        from code_index.frontend import detect_framework
        fw = detect_framework(code_dir, rel)
        if fw == "react" and suffix in (".tsx", ".jsx"):
            from code_index.frontend import react_symbols
            return react_symbols(text, stem, suffix, rel)
        if fw == "angular" and suffix == ".ts":
            from code_index.frontend import angular_symbols
            return angular_symbols(text, stem, suffix, rel)
        if fw == "angular" and suffix == ".html":
            from code_index.frontend import angular_template_meta
            meta = angular_template_meta(text)
            return [("template", stem, text[:_SNIPPET_LIMIT], {"attrs": meta})] if meta \
                else [("template", stem, text[:_SNIPPET_LIMIT])]
    if suffix == ".java":
        # Unica implementazione (tree-sitter, nessun parser regex precedente):
        # il flag code_parsers.java esiste solo per uniformità di configurazione.
        from code_index.java import java_symbols
        return java_symbols(text, stem, suffix)
    if suffix == ".xml" and stem == "pom":
        from code_index.java import pom_symbols
        return pom_symbols(text, stem, suffix)
    if suffix == ".gradle":
        from code_index.java import gradle_symbols
        # il nome del progetto Gradle non è nel file: si usa la cartella che lo contiene
        project = rel.rsplit("/", 2)[-2] if rel.count("/") else ""
        return gradle_symbols(text, stem, suffix, project=project)
    if suffix in (".bpmn", ".bpmn2"):
        from code_index.java import bpmn_symbols
        return bpmn_symbols(text, stem, suffix)
    if suffix == ".dmn":
        from code_index.java import dmn_symbols
        return dmn_symbols(text, stem, suffix)
    # .NET (runtime-agnostico: identico su .NET Framework e Core/5+).
    # Razor (.cshtml/.razor): scanner ibrido dedicato (regex per direttive/markup +
    # parser tree-sitter C# per i blocchi @code) — la grammatica tree-sitter Razor è
    # immatura. Fuori scope (permanente, non un piano): VB.NET (.vbhtml), analisi
    # dell'HTML/JS interno alle view, CSS isolation (.razor.css).
    if suffix in (".cshtml", ".razor"):
        from code_index.razor import razor_symbols
        return razor_symbols(text, stem, suffix, rel)
    if suffix == ".cs":
        from code_index.csharp import csharp_symbols
        return csharp_symbols(text, stem, suffix)
    if suffix == ".csproj":
        from code_index.csharp import csproj_symbols
        return csproj_symbols(text, stem, suffix)
    # SQL (T-SQL / PL/SQL / generico): ibrido tree-sitter + scanner regex per i
    # dialetti; .pks/.pkb sono spec/body dei package PL/SQL.
    if suffix in (".sql", ".pks", ".pkb"):
        from code_index.sql import sql_symbols
        return sql_symbols(text, stem, suffix, rel)
    # Script operazionali: Bash e PowerShell entrambi via tree-sitter (grammatica
    # PowerShell verificata matura sul corpus: function, dot-sourcing, & call).
    if suffix in (".sh", ".ps1", ".psm1"):
        from code_index.shell import shell_symbols
        return shell_symbols(text, stem, suffix, rel)
    if suffix == ".config" and stem == "packages":
        from code_index.csharp import packages_config_symbols
        project = rel.rsplit("/", 2)[-2] if rel.count("/") else ""
        return packages_config_symbols(text, stem, suffix, project=project)
    # File di configurazione riconosciuti per NOME (web.config, appsettings*.json,
    # package.json, *.wsdl/*.xsd): estrazione strutturata stdlib, secret mascherati.
    fname = (rel.rsplit("/", 1)[-1] if rel else f"{stem}{suffix}").lower()
    if _is_docker_file(fname):
        import code_index.docker as dockermod
        if dockermod._is_compose(fname):
            return dockermod.compose_symbols(text, stem, suffix, rel)
        return dockermod.dockerfile_symbols(text, stem, suffix, rel)
    if _is_ci_file(fname):
        import code_index.ci as cimod
        if "gitlab" in fname:
            return cimod.gitlab_ci_symbols(text, stem, suffix, rel)
        return cimod.azure_pipelines_symbols(text, stem, suffix, rel)
    if _is_config_file(fname):
        import code_index.config as cfg
        if fname.endswith(".config"):
            return cfg.dotnet_config_symbols(text, stem, suffix, rel)
        if fname.startswith("appsettings") and fname.endswith(".json"):
            return cfg.appsettings_symbols(text, stem, suffix, rel)
        if fname == "package.json":
            return cfg.packagejson_symbols(text, stem, suffix, rel)
        if fname.startswith("application") and fname.endswith(".properties"):
            return cfg.java_properties_symbols(text, stem, suffix, rel)
        if fname.startswith("application") and fname.endswith((".yml", ".yaml")):
            return cfg.java_yaml_config_symbols(text, stem, suffix, rel)
        if fname.endswith(".wsdl"):
            return cfg.wsdl_symbols(text, stem, suffix, rel)
        if fname.endswith(".xsd"):
            return cfg.xsd_symbols(text, stem, suffix, rel)
    if suffix in (".js", ".ts", ".tsx", ".jsx", ".svelte"):
        # Unica implementazione (tree-sitter, nessun fallback regex — A12: rimosso
        # il 2026-09-03, 53 giorni senza incidenti dalla migrazione del 2026-07-12).
        # Svelte: la grammatica tree-sitter parsa il solo markup, ma il contenuto
        # degli <script> viene ri-parsato con la grammatica TypeScript.
        from code_index.ts import svelte_symbols, ts_symbols
        fn = svelte_symbols if suffix == ".svelte" else ts_symbols
        return fn(text, stem, suffix)
    if suffix == ".html":
        return [("template", stem, text[:_SNIPPET_LIMIT])]
    if suffix == ".css":
        return [("stylesheet", stem, text[:_SNIPPET_LIMIT])]
    return []


def source_files(root: Path, excluded_dirs=frozenset()) -> list[Path]:
    """Collect confined source files before parsers can follow auxiliary file paths."""
    for component in (root, *root.parents):
        if component.is_symlink() or component.is_junction():
            raise ValueError(f"linked source root forbidden: {component}")
    resolved = root.resolve()
    files = []
    for folder, dirs, names in root.walk(follow_symlinks=False):
        dirs[:] = [name for name in dirs if name not in excluded_dirs]
        for name in [*dirs, *names]:
            path = folder / name
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(resolved):
                raise ValueError(f"linked or escaping source forbidden: {path}")
        files.extend(folder / name for name in names if (folder / name).is_file())
    return sorted(files)


def collect_code_symbols(code_dir: Path) -> list[dict]:
    """Scansiona code/ e restituisce i simboli estratti, uno per elemento di codice."""
    symbols: list[dict] = []
    from code_index.sql import FALLBACK_LOG
    FALLBACK_LOG.clear()
    if not code_dir.exists():
        return symbols
    for path in source_files(code_dir, CODE_EXCLUDED_DIRS):
        if not (path.is_file() and (path.suffix in CODE_EXTS or path.name in CODE_FILENAMES
                                    or _is_config_file(path.name) or _is_ci_file(path.name)
                                    or _is_docker_file(path.name))):
            continue
        if CODE_EXCLUDED_DIRS & set(path.relative_to(code_dir).parts):
            continue
        rel = path.relative_to(code_dir).as_posix()
        dev_type = rel.split("/")[0] if "/" in rel else ""
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for tup in _extract(path.suffix, text, path.stem, rel, code_dir):
            kind, name, snippet = tup[0], tup[1], tup[2]
            meta = tup[3] if len(tup) > 3 else {}
            symbols.append({
                "id": f"{rel}::{name}",
                "name": name,
                "kind": kind,
                "file": rel,
                "dev_type": dev_type,
                "text": f"{kind} {name}\n{snippet}",
                "deps": sorted(set(meta.get("deps") or [])),
                "refs": sorted(set(meta.get("refs") or [])),
                "links": sorted(set(map(tuple, meta.get("links") or []))),
                "package": meta.get("package", ""),
                "attrs": meta.get("attrs") or {},
            })

    # Appartenenza: ogni nodo config/service/schema si collega al nodo project
    # più vicino nel filesystem (classe -> config -> connection string -> db).
    from code_index.config import attach_projects
    attach_projects(symbols)

    # Frontend (React/Angular): risolve templateUrl/lazy import, archi
    # componente->componente dai selector, componenti routable dalle route.
    if any(k in (s.get("attrs") or {}) for s in symbols
           for k in ("_routes", "_used_selectors")) \
            or any(d.startswith("file:") for s in symbols for d in s["deps"]):
        from code_index.frontend import resolve_frontend
        resolve_frontend(symbols)

    # JPA: entity->tabella (con placeholder se il DDL non è indicizzato) e
    # navigazione @OneToMany & co. -> REFERENCES entity->entity.
    if any(k in (s.get("attrs") or {}) for s in symbols
           for k in ("_jpa_table", "_jpa_nav")):
        from code_index.java import resolve_jpa
        resolve_jpa(symbols)

    # Entity Framework: context->entity, entity->tabella (con placeholder se il
    # DDL non è indicizzato), navigazione entity->entity. Va chiamato anche solo
    # per ripulire le chiavi temporanee (_prop_types/_table) dai metadati C#.
    if any(k in (s.get("attrs") or {}) for s in symbols
           for k in ("_table", "_fluent", "_dbsets", "_prop_types")):
        from code_index.csharp import resolve_ef
        resolve_ef(symbols)

    # Riferimenti incrociati degli script (source, dotnet build su .csproj,
    # sqlcmd su .sql): risolti sui percorsi relativi, best-effort.
    if any(t.startswith("run:") for s in symbols for _, t in s["links"]):
        from code_index.shell import resolve_script_refs
        resolve_script_refs(symbols)

    # Le dep "tipizzate" (view:/page:/component:/...) richiedono la vista d'insieme
    # dei file: le risolve il resolver Razor, che produce anche il report di
    # governance (link rotti, view orfane) consultabile via `razor_report()`.
    global _LAST_RAZOR_REPORT
    if any(":" in d for s in symbols for d in s["deps"]):
        from code_index.razor import resolve_links
        _LAST_RAZOR_REPORT = resolve_links(symbols, code_dir)
    else:
        _LAST_RAZOR_REPORT = {"broken_links": [], "orphan_views": []}
    return symbols


_LAST_RAZOR_REPORT: dict = {"broken_links": [], "orphan_views": []}


def razor_report() -> dict:
    """Report di governance Razor dell'ultima collect_code_symbols:
    link rotti (view/page/action inesistenti) e view MVC orfane."""
    return _LAST_RAZOR_REPORT


# Relazioni spec<->codice che dipendono dal CONTENUTO (versione) di un simbolo: vanno
# rimosse e ricalcolate quando il simbolo o lo spazio dei documenti cambia. NON toccano
# altri tipi di arco (es. MENTIONS doc->entità), che appartengono ai nodi-documento.
_CODE_LINK_RELATIONS = ("IMPLEMENTS", "REFERENCES", "DEPENDS_ON", "READS", "WRITES", "EXECUTES")


def add_symbol_nodes(G, symbols: list[dict]) -> None:
    """Inserisce (o aggiorna) i soli NODI di codice nel grafo, senza archi. Condiviso da
    full rebuild e incrementale: gli archi li calcola poi `link_symbols`."""
    for sym in symbols:
        attrs = dict(
            type="code",
            kind=sym["kind"],
            name=sym["name"],
            file=sym["file"],
            dev_type=sym["dev_type"],
        )
        if sym.get("package"):
            attrs["package"] = sym["package"]
        # metadati specifici del parser (route, parameters, event_callbacks, ...)
        for k, v in (sym.get("attrs") or {}).items():
            attrs.setdefault(k, v)
        G.add_node(sym["id"], **attrs)


def embed_symbols(embed_model, symbols: list[dict]) -> np.ndarray:
    """Vettorializza (dense) il testo dei simboli. Restituisce una matrice [n x DENSE_DIM]
    allineata a `symbols` (vuota se non ci sono simboli)."""
    if not symbols:
        return np.zeros((0, 0), dtype=np.float32)
    out = embed_model.encode([s["text"] for s in symbols], batch_size=12, return_dense=True)
    return np.asarray(out["dense_vecs"], dtype=np.float32)


def _clear_code_link_edges(G, symbol_ids) -> None:
    """Rimuove dai simboli indicati i soli archi IMPLEMENTS/REFERENCES uscenti, così da
    poterli ricalcolare dalla versione corrente senza toccare il resto del grafo."""
    for sid in symbol_ids:
        if sid not in G:
            continue
        stale = [(sid, v) for _, v, d in G.out_edges(sid, data=True)
                 if d.get("relation") in _CODE_LINK_RELATIONS]
        G.remove_edges_from(stale)


def referenced_entity_tokens(text: str) -> set[str]:
    """Estrae dai `text` di un simbolo i token candidati a entità del glossario
    (MAIUSCOLE, es. `ALPHA`, `ORDINE_CLIENTE`). Fonte unica del match REFERENCES
    codice->entità, riusata dall'incrementale per capire quali simboli toccare
    quando l'insieme delle entità citabili cambia."""
    return set(_ENTITY_TOKEN_RE.findall(text or ""))


# Estensioni "non-semantiche": presentazione/markup senza logica di dominio. I loro simboli
# restano nodi del grafo (struttura), ma non generano archi IMPLEMENTS verso le spec (rumore).
_NONSEMANTIC_LINK_SUFFIXES = (".css", ".scss", ".less", ".html", ".htm")


def _is_nonsemantic_symbol(sym_id: str) -> bool:
    """True se il simbolo proviene da un file di sola presentazione/markup (CSS/HTML): non
    deve produrre un IMPLEMENTS. `sym_id` ha forma 'path/al/file.ext::nome'."""
    path = sym_id.rsplit("::", 1)[0].lower()
    return path.endswith(_NONSEMANTIC_LINK_SUFFIXES)


def link_symbols(G, symbols: list[dict], sym_dense, doc_dense_vecs, doc_ids,
                 threshold: float = 0.45, chunk_ids=None, scores_out: dict | None = None) -> int:
    """(Ri)calcola gli archi IMPLEMENTS (similarità dense verso il chunk-documento più
    simile) e REFERENCES (match deterministico sulle entità del glossario) per i `symbols`
    dati, che devono già essere nodi del grafo. Prima azzera i loro vecchi archi di questo
    tipo: è quindi idempotente e sicuro sia in full rebuild (grafo fresco) sia in
    incrementale (dove il simbolo/lo spazio-documenti può essere cambiato).

    Se `scores_out` è passato, vi si annota per ogni simbolo lo stato dell'argmax
    IMPLEMENTS — `best_score` (similarità col chunk vincente), `second_score` (secondo
    classificato), `win_chunk_id` e `win_doc_id` — anche quando la migliore similarità è
    sotto soglia (nessun arco creato). È la proprietà globale che l'incrementale persiste
    nel code_store per decidere, senza rilinkare tutto, quali simboli possono cambiare
    argmax quando i documenti cambiano. `chunk_ids` (parallelo a `doc_dense_vecs`/`doc_ids`)
    fornisce l'id del chunk vincente; se assente si annota solo il documento.

    Restituisce il numero di archi IMPLEMENTS creati."""
    if not symbols:
        return 0

    _clear_code_link_edges(G, [s["id"] for s in symbols])

    entity_nodes = {n for n, a in G.nodes(data=True) if a.get("type") == "entity"}
    for sym in symbols:
        for token in set(_ENTITY_TOKEN_RE.findall(sym["text"])):
            if token in entity_nodes:
                G.add_edge(sym["id"], token, relation="REFERENCES", **edge_trust_attrs("REFERENCES"))

    # DEPENDS_ON: risoluzione best-effort per nome semplice (classe importata/iniettata,
    # artifactId, id di processo) verso gli altri nodi di codice del grafo. I nomi che
    # non risolvono (dipendenze esterne al progetto) vengono ignorati.
    name_to_id = {a["name"]: n for n, a in G.nodes(data=True)
                  if a.get("type") == "code" and a.get("name")}
    for sym in symbols:
        for dep in sym.get("deps") or []:
            target = name_to_id.get(dep)
            if target and target != sym["id"]:
                G.add_edge(sym["id"], target, relation="DEPENDS_ON", **edge_trust_attrs("DEPENDS_ON"))
        # REFERENCES codice->codice (es. view Razor -> @model/@inject): stessi
        # archi del REFERENCES verso le entità, ma con target un nodo di codice.
        # Non sovrascrive un DEPENDS_ON già presente sulla stessa coppia (DiGraph
        # ammette un solo arco per coppia: vince la relazione più forte).
        for ref in sym.get("refs") or []:
            target = name_to_id.get(ref)
            if target and target != sym["id"] and not G.has_edge(sym["id"], target):
                G.add_edge(sym["id"], target, relation="REFERENCES", **edge_trust_attrs("REFERENCES"))
        # archi semantici tipizzati (SQL: READS/WRITES/EXECUTES); a parità di
        # coppia vince la relazione più forte (un solo arco per coppia nel DiGraph)
        priority = {"EXECUTES": 0, "WRITES": 1, "READS": 2}
        for lrel, lname in sorted(sym.get("links") or [],
                                  key=lambda t: (priority.get(t[0], 9), t[1])):
            target = name_to_id.get(lname)
            if target and target != sym["id"] and not G.has_edge(sym["id"], target):
                G.add_edge(sym["id"], target, relation=lrel, **edge_trust_attrs(lrel))

    implements = 0
    sym_matrix = np.asarray(sym_dense, dtype=np.float32)
    have_docs = doc_ids is not None and doc_dense_vecs is not None and len(doc_ids) > 0 and sym_matrix.size
    if have_docs:
        doc_matrix = np.asarray(doc_dense_vecs, dtype=np.float32)
        doc_norm = doc_matrix / (np.linalg.norm(doc_matrix, axis=1, keepdims=True) + 1e-8)
        sym_norm = sym_matrix / (np.linalg.norm(sym_matrix, axis=1, keepdims=True) + 1e-8)

        sims = sym_norm @ doc_norm.T  # [n_simboli x n_chunk-documento]
        best_idx = sims.argmax(axis=1)
        best_val = sims.max(axis=1)
        # secondo classificato per simbolo (audit + margine): se c'è un solo chunk il
        # second_score degrada al minimo del dominio cosine (-1.0).
        second_val = (np.partition(sims, -2, axis=1)[:, -2]
                      if sims.shape[1] >= 2 else np.full(sims.shape[0], -1.0, dtype=np.float32))
        for i, sym in enumerate(symbols):
            win_chunk = chunk_ids[int(best_idx[i])] if chunk_ids is not None else None
            win_doc = doc_ids[int(best_idx[i])]
            if scores_out is not None:
                scores_out[sym["id"]] = {
                    "best_score": float(best_val[i]),
                    "second_score": float(second_val[i]),
                    "win_chunk_id": win_chunk,
                    "win_doc_id": win_doc,
                }
            # Il link punta alla SEZIONE vincente (nodo-sezione, id = win_chunk) quando questa
            # esiste nel grafo: precisione a livello di sezione, non di documento intero. Se i
            # nodi-sezione non ci sono (indici/test legacy pre-sezioni) si ricade sul documento,
            # preservando il comportamento storico. win_doc resta in scores_out per la logica
            # incrementale (_symbols_with_stale_argmax chiave su win_doc_id).
            target = win_chunk if (win_chunk is not None and win_chunk in G) else win_doc
            # I file non-semantici (CSS/HTML) non "implementano" una spec: la loro similarità
            # densa col testo è rumore (es. styles.css -> spec_form @0.52). Si registra comunque
            # l'argmax in scores_out (coerenza dell'incrementale) ma NON si crea l'arco. Il filtro
            # è identico in full e incrementale, quindi l'equivalenza delta≡full è preservata.
            if best_val[i] >= threshold and target in G and not _is_nonsemantic_symbol(sym["id"]):
                G.add_edge(sym["id"], target, relation="IMPLEMENTS",
                          weight=round(float(best_val[i]), 3), nature="inferred",
                          reliability=implements_reliability(float(best_val[i])))
                implements += 1
    elif scores_out is not None:
        # Nessuno spazio-documenti: i simboli non hanno argmax. Registriamo un best_score
        # sentinella (-1.0, sotto qualunque cosine) così, appena compare un chunk, il
        # confronto incrementale li marca come 'da rilinkare'.
        for sym in symbols:
            scores_out[sym["id"]] = {"best_score": -1.0, "second_score": -1.0,
                                     "win_chunk_id": None, "win_doc_id": None}
    return implements


def add_code_graph(G, symbols: list[dict], embed_model, doc_ids: list[str],
                   doc_dense_vecs, threshold: float = 0.45) -> tuple[int, int]:
    """Aggiunge i nodi di codice al grafo e li collega ai documenti con archi
    IMPLEMENTS per similarità semantica (dense bge-m3), più archi REFERENCES
    deterministici verso le entità del glossario citate nel codice.

    Restituisce (numero_nodi_codice, numero_archi_implements)."""
    if not symbols:
        return 0, 0
    add_symbol_nodes(G, symbols)
    sym_dense = embed_symbols(embed_model, symbols)
    implements = link_symbols(G, symbols, sym_dense, doc_dense_vecs, doc_ids, threshold)
    return len(symbols), implements
