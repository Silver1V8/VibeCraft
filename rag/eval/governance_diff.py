"""Confronta due alberi parsando i file, non il testo del diff.

Rileva i cambiamenti che alterano l'autorità effettiva di una fonte: authority,
classification, status, precedenze dichiarate, e le chiavi di rag_config.yaml che
ne cambiano l'interpretazione. Rileva anche il codice che calcola quei pesi, il
rilevatore stesso, CODEOWNERS e la forma dei workflow.

Non approva nulla. Non ha un flag per tacitare un rilevamento. CODEOWNERS, se
compare, è un file intero: questo modulo non pretende di sapere quale campo un
reviewer abbia guardato.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path

import yaml

_MISSING = object()

_SCALAR_CONFIG = (
    ("authority", "default_weight"),
    ("authority", "archived_decay"),
    ("authority", "boost_alpha"),
    ("authority", "section_restatement_weight"),
    ("authority", "use_declared"),
    ("authority", "unclassified_weight"),
    ("authority", "precedence_relation"),
)
_DICT_CONFIG = (
    ("authority", "class_weights"),
    ("graph_trust", "nature_reliability"),
    ("graph_trust", "relation_nature"),
)
_NUMERIC_CONFIG = {
    "authority.default_weight",
    "authority.archived_decay",
    "authority.boost_alpha",
    "authority.section_restatement_weight",
    "authority.unclassified_weight",
}
_RETRIEVAL_FUNCTIONS = (
    "_declared_authority",
    "_authority_weight",
    "apply_precedence",
    "source_label",
)
_CONFIG_ASSIGNMENTS = (
    "AUTHORITY_CLASS_WEIGHTS",
    "AUTHORITY_DEFAULT_WEIGHT",
    "AUTHORITY_ARCHIVED_DECAY",
    "AUTHORITY_BOOST_ALPHA",
    "AUTHORITY_USE_DECLARED",
    "AUTHORITY_PRECEDENCE_RELATION",
    "AUTHORITY_UNCLASSIFIED_WEIGHT",
    "SECTION_RESTATEMENT_WEIGHT",
    "GRAPH_TRUST_NATURE_RELIABILITY",
    "GRAPH_TRUST_RELATION_NATURE",
    "GRAPH_TRUST_DEFAULT_NATURE",
)
_CHECKERS = (
    "rag/eval/governance_diff.py",
    "rag/scripts/governance_diff.py",
)
_DEFAULT_PRECEDENCE = "SUPERA_IN_PRIORITÀ"


def _record(documento, campo, prima, dopo, esito, **extra):
    row = {
        "documento": documento,
        "campo": campo,
        "prima": _jsonable(prima),
        "dopo": _jsonable(dopo),
        "esito": esito,
    }
    row.update(extra)
    return row


def _jsonable(value):
    if value is _MISSING:
        return None
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _same(left, right) -> bool:
    if left is _MISSING and right is _MISSING:
        return True
    if left is _MISSING or right is _MISSING:
        return False
    return left == right


def _read(path: Path):
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"UTF-8 non valido: {exc}"
    except OSError as exc:
        return None, str(exc)


def split_frontmatter(text: str):
    """Ritorna (mappa, errore). Nessun frontmatter → ({}, None)."""
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text.startswith("---"):
        return {}, None
    if text.startswith("---\r\n"):
        body = text[5:]
    elif text.startswith("---\n"):
        body = text[4:]
    else:
        return None, "frontmatter non aperto"
    lines = body.splitlines(keepends=True)
    raw = []
    closed = False
    for line in lines:
        if line.strip() == "---":
            closed = True
            break
        raw.append(line)
    if not closed:
        return None, "frontmatter non chiuso"
    try:
        data = yaml.safe_load("".join(raw))
    except yaml.YAMLError as exc:
        return None, f"YAML: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, "il frontmatter non è una mappa"
    return data, None


def _authority_problem(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "authority non è un numero in [0, 1]"
    number = float(value)
    if number != number or not 0.0 <= number <= 1.0:
        return "authority non è un numero in [0, 1]"
    return None


def _declared(data: dict, key: str):
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _precedence_names(config: dict | None) -> set[str]:
    names = {_DEFAULT_PRECEDENCE}
    if not isinstance(config, dict):
        return names
    authority = config.get("authority")
    if isinstance(authority, dict):
        relation = authority.get("precedence_relation")
        if isinstance(relation, str) and relation.strip():
            names.add(relation)
    return names


def _precedenze(data: dict, names: set[str]):
    graph = data.get("graph_rag")
    if graph is None:
        return ()
    if not isinstance(graph, dict):
        return None
    edges = graph.get("edges")
    if edges is None:
        return ()
    if not isinstance(edges, list):
        return None
    found = []
    for edge in edges:
        if not isinstance(edge, dict) or "type" not in edge:
            return None
        if edge.get("type") in names:
            found.append((str(edge.get("type")), str(edge.get("target"))))
    return tuple(sorted(found))


def _docs(root: Path) -> dict[str, tuple]:
    found = {}
    docs = root / "templates" / "docs"
    paths = []
    if docs.is_dir():
        paths.extend(path for path in docs.rglob("*.md") if path.is_file() and not path.is_symlink())
    templates = root / "templates"
    if templates.is_dir():
        paths.extend(
            path for path in templates.glob("template_*.md")
            if path.is_file() and not path.is_symlink()
        )
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text, error = _read(path)
        if error:
            found[relative] = (None, error)
            continue
        data, parse_error = split_frontmatter(text)
        found[relative] = (data, parse_error)
    return found


def _ids(docs: dict) -> tuple[dict, list]:
    grouped: dict[str, list] = {}
    for path, (data, error) in docs.items():
        if error or not data:
            continue
        ident = data.get("id")
        if isinstance(ident, str) and ident.strip():
            grouped.setdefault(ident, []).append(path)
    duplicates = [(ident, paths) for ident, paths in grouped.items() if len(paths) > 1]
    return grouped, duplicates


def _pairs(base_docs, head_docs):
    base_ids, base_dups = _ids(base_docs)
    head_ids, head_dups = _ids(head_docs)
    used_base, used_head = set(), set()
    pairs = []
    for ident, base_paths in base_ids.items():
        head_paths = head_ids.get(ident, [])
        if len(base_paths) == 1 and len(head_paths) == 1:
            base_path, head_path = base_paths[0], head_paths[0]
            used_base.add(base_path)
            used_head.add(head_path)
            kind = "stesso" if base_path == head_path else "rinominato"
            pairs.append((base_path, head_path, kind))
    for path in base_docs:
        if path not in used_base and path in head_docs and path not in used_head:
            used_base.add(path)
            used_head.add(path)
            pairs.append((path, path, "stesso"))
    for path in base_docs:
        if path not in used_base:
            pairs.append((path, None, "rimosso"))
    for path in head_docs:
        if path not in used_head:
            pairs.append((None, path, "aggiunto"))
    return pairs, base_dups, head_dups


def _field_problem(key: str, value):
    if key == "authority":
        return _authority_problem(value)
    if key in {"classification", "status"} and not isinstance(value, str):
        return f"{key} non è una stringa"
    return None


def _emit_fields(rows, documento, before, after, names, esito_base):
    for key in ("authority", "classification", "status"):
        left = _declared(before, key) if before is not None else None
        right = _declared(after, key) if after is not None else None
        if esito_base == "rimosso" and left is None:
            continue
        if esito_base == "aggiunto" and right is None:
            continue
        if esito_base == "stesso" and _same(left, right):
            continue
        problem = _field_problem(key, right if right is not None else left)
        if right is not None:
            problem = _field_problem(key, right) or problem
        esito = "non valido" if problem and esito_base != "rimosso" else esito_base
        if esito_base == "stesso":
            esito = "non valido" if problem else "modificato"
        row = _record(documento, key, left, right, esito)
        if problem and esito == "non valido":
            row["errore"] = problem
        rows.append(row)
    left_edges = _precedenze(before, names) if before is not None else ()
    right_edges = _precedenze(after, names) if after is not None else ()
    if left_edges is None or right_edges is None:
        rows.append(_record(
            documento, "graph_rag.edges", left_edges, right_edges, "non valido",
            errore="gli archi non sono una lista di mappe con type",
        ))
    elif not _same(left_edges, right_edges) and not (esito_base == "rimosso" and not left_edges) \
            and not (esito_base == "aggiunto" and not right_edges):
        esito = esito_base if esito_base != "stesso" else "modificato"
        rows.append(_record(documento, "precedenze", left_edges, right_edges, esito))


def _document_rows(base_docs, head_docs, names):
    rows = []
    pairs, base_dups, head_dups = _pairs(base_docs, head_docs)
    for ident, paths in base_dups + head_dups:
        rows.append(_record(
            ", ".join(paths), "id", ident, ident, "non valido",
            errore="id duplicato: il confronto per rinomina non è univoco",
        ))
    for base_path, head_path, kind in pairs:
        before = base_docs.get(base_path, (None, None))[0] if base_path else None
        after = head_docs.get(head_path, (None, None))[0] if head_path else None
        base_error = base_docs.get(base_path, (None, None))[1] if base_path else None
        head_error = head_docs.get(head_path, (None, None))[1] if head_path else None
        documento = head_path or base_path
        if kind == "rinominato":
            rows.append(_record(base_path, "(percorso)", base_path, head_path, "rinominato"))
        if base_error or head_error:
            rows.append(_record(
                documento, "(frontmatter)", None, None, "non valido",
                errore=head_error or base_error,
            ))
            continue
        if kind == "rimosso":
            _emit_fields(rows, documento, before, None, names, "rimosso")
        elif kind == "aggiunto":
            _emit_fields(rows, documento, None, after, names, "aggiunto")
        else:
            _emit_fields(rows, documento, before or {}, after or {}, names, "stesso")
    return rows


def _load_config(root: Path):
    path = root / "rag" / "rag_config.yaml"
    if not path.is_file():
        return _MISSING, None
    text, error = _read(path)
    if error:
        return None, error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"YAML: {exc}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, "rag_config.yaml non è una mappa"
    return data, None


def _dig(data, path):
    current = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _config_rows(base_root: Path, head_root: Path):
    rows = []
    base, base_error = _load_config(base_root)
    head, head_error = _load_config(head_root)
    if base_error or head_error:
        rows.append(_record(
            "rag/rag_config.yaml", "(file)", None, None, "non valido",
            errore=head_error or base_error,
        ))
        return rows, {}, {}
    if base is _MISSING and head is _MISSING:
        return rows, {}, {}
    base_map = base if isinstance(base, dict) else {}
    head_map = head if isinstance(head, dict) else {}
    for path in _SCALAR_CONFIG:
        campo = ".".join(path)
        left, right = _dig(base_map, path), _dig(head_map, path)
        if _same(left, right):
            continue
        if left is _MISSING:
            esito = "aggiunto"
        elif right is _MISSING:
            esito = "rimosso"
        else:
            esito = "modificato"
        problem = None
        observed = right if right is not _MISSING else left
        if campo in _NUMERIC_CONFIG and observed is not _MISSING:
            if isinstance(observed, bool) or not isinstance(observed, (int, float)):
                problem = "atteso un numero"
        if campo == "authority.use_declared" and observed is not _MISSING and not isinstance(observed, bool):
            problem = "atteso un booleano, non una stringa"
        if campo == "authority.precedence_relation" and observed is not _MISSING \
                and not isinstance(observed, str):
            problem = "attesa una stringa"
        if problem and esito != "rimosso":
            esito = "non valido"
        row = _record("rag/rag_config.yaml", campo, left, right, esito)
        if problem and esito == "non valido":
            row["errore"] = problem
        rows.append(row)
    for path in _DICT_CONFIG:
        campo = ".".join(path)
        left, right = _dig(base_map, path), _dig(head_map, path)
        if _same(left, right):
            continue
        if (left is not _MISSING and not isinstance(left, dict)) or (
                right is not _MISSING and not isinstance(right, dict)):
            rows.append(_record(
                "rag/rag_config.yaml", campo, left, right, "non valido",
                errore="attesa una mappa",
            ))
            continue
        keys = set()
        if isinstance(left, dict):
            keys.update(left)
        if isinstance(right, dict):
            keys.update(right)
        for key in sorted(keys, key=str):
            lvalue = left.get(key, _MISSING) if isinstance(left, dict) else _MISSING
            rvalue = right.get(key, _MISSING) if isinstance(right, dict) else _MISSING
            if _same(lvalue, rvalue):
                continue
            if lvalue is _MISSING:
                esito = "aggiunto"
            elif rvalue is _MISSING:
                esito = "rimosso"
            else:
                esito = "modificato"
            rows.append(_record("rag/rag_config.yaml", f"{campo}.{key}", lvalue, rvalue, esito))
    return rows, base_map, head_map


def _snippet(text: str, node: ast.AST) -> str:
    return ast.get_source_segment(text, node) or ""


def _functions(text: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(text)
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = _snippet(text, node)
    return found


def _assignments(text: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(text)
    found = {}
    for node in tree.body:
        targets = []
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        elif isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
        for name in targets:
            if name in names:
                found[name] = _snippet(text, node)
    return found


def _code_rows(base_root: Path, head_root: Path, relative: str, extractor, names, livello: str):
    rows = []
    base_path = base_root / relative
    head_path = head_root / relative
    if not base_path.is_file() and not head_path.is_file():
        return rows
    base_text = base_path.read_text(encoding="utf-8") if base_path.is_file() else ""
    head_text = head_path.read_text(encoding="utf-8") if head_path.is_file() else ""
    try:
        base_map = extractor(base_text, names) if base_text else {}
    except SyntaxError as exc:
        return [_record(relative, "(sintassi)", None, None, "non valido", errore=str(exc))]
    try:
        head_map = extractor(head_text, names) if head_text else {}
    except SyntaxError as exc:
        return [_record(relative, "(sintassi)", None, None, "non valido", errore=str(exc))]
    for name in names:
        left = base_map.get(name, _MISSING)
        right = head_map.get(name, _MISSING)
        if _same(left, right):
            continue
        if left is _MISSING:
            esito = "aggiunto"
        elif right is _MISSING:
            esito = "rimosso"
        else:
            esito = "modificato"
        rows.append(_record(
            relative, name, _digest(left), _digest(right), esito, livello=livello,
            nota="confronto sul sorgente parsato, non sul diff testuale",
        ))
    return rows


def _digest(source) -> str | None:
    if source is _MISSING:
        return None
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def _file_hash_rows(base_root: Path, head_root: Path, relative: str, nota: str):
    base_path = base_root / relative
    head_path = head_root / relative
    if not base_path.is_file() and not head_path.is_file():
        return []
    left = base_path.read_bytes() if base_path.is_file() else None
    right = head_path.read_bytes() if head_path.is_file() else None
    if left == right:
        return []
    if left is None:
        esito = "aggiunto"
    elif right is None:
        esito = "rimosso"
    else:
        esito = "modificato"
    return [_record(
        relative, "(file)",
        hashlib.sha256(left).hexdigest()[:16] if left is not None else None,
        hashlib.sha256(right).hexdigest()[:16] if right is not None else None,
        esito, livello="file", nota=nota,
    )]


def trigger_names(document: dict) -> set[str]:
    raw = document.get("on", document.get(True))
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    if isinstance(raw, dict):
        return {str(key) for key in raw}
    return set()


def workflow_view(text: str) -> dict:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {"errore": f"YAML: {exc}"}
    if not isinstance(document, dict):
        return {"errore": "il workflow non è una mappa"}
    triggers = sorted(trigger_names(document))
    jobs = document.get("jobs") if isinstance(document.get("jobs"), dict) else {}
    return {
        "trigger": triggers,
        "permissions": document.get("permissions", _MISSING),
        "job_permissions": {
            str(name): job.get("permissions", _MISSING)
            for name, job in jobs.items() if isinstance(job, dict)
        },
        "pull_request_target": "pull_request_target" in triggers,
    }


def _writes(permissions) -> bool:
    if permissions is _MISSING or permissions is None:
        return True
    if isinstance(permissions, str):
        return permissions not in {"read"}
    if isinstance(permissions, dict):
        return any(value not in {"read", "none"} for value in permissions.values())
    return True


def _effective_write(view: dict) -> bool:
    """Un job senza permessi propri eredita quelli del workflow."""
    top = view.get("permissions", _MISSING)
    jobs = view.get("job_permissions") or {}
    if not jobs:
        return _writes(top)
    for value in jobs.values():
        if _writes(top if value is _MISSING else value):
            return True
    return False


def _workflow_rows(base_root: Path, head_root: Path):
    rows = []
    base_dir = base_root / ".github" / "workflows"
    head_dir = head_root / ".github" / "workflows"
    names = set()
    for directory in (base_dir, head_dir):
        if directory.is_dir():
            names.update(
                path.name for path in directory.iterdir()
                if path.suffix in {".yml", ".yaml"} and path.is_file() and not path.is_symlink()
            )
    for name in sorted(names):
        relative = f".github/workflows/{name}"
        base_path = base_dir / name
        head_path = head_dir / name
        base_text = base_path.read_text(encoding="utf-8") if base_path.is_file() else None
        head_text = head_path.read_text(encoding="utf-8") if head_path.is_file() else None
        base_view = workflow_view(base_text) if base_text is not None else None
        head_view = workflow_view(head_text) if head_text is not None else None
        if base_view != head_view:
            if head_view is None:
                esito = "rimosso"
            elif base_view is None:
                esito = "aggiunto"
            else:
                esito = "modificato"
            if (head_view or {}).get("errore") or (base_view or {}).get("errore"):
                esito = "non valido"
            rows.append(_record(relative, "workflow", base_view, head_view, esito, livello="file"))
        view = head_view or {}
        if view.get("pull_request_target"):
            rows.append(_record(
                relative, "on", None, "pull_request_target", "a rischio",
                errore="pull_request_target esegue codice non fidato con il token del base",
            ))
        triggers = set(view.get("trigger") or [])
        if triggers & {"pull_request", "pull_request_target"} and _effective_write(view):
            rows.append(_record(
                relative, "permissions", None, view.get("permissions", None), "a rischio",
                errore="un workflow su pull request ha permessi oltre la lettura, o non li dichiara",
            ))
    return rows


def compare_trees(base_root: Path, head_root: Path) -> dict:
    """Rilevamenti fra due checkout. enforcement è sempre «non attivo»."""
    base_root = Path(base_root)
    head_root = Path(head_root)
    config_rows, base_config, head_config = _config_rows(base_root, head_root)
    names = _precedence_names(base_config) | _precedence_names(head_config)
    rows = []
    rows.extend(_document_rows(_docs(base_root), _docs(head_root), names))
    rows.extend(config_rows)
    rows.extend(_code_rows(
        base_root, head_root, "rag/core/retrieval.py", _functions, _RETRIEVAL_FUNCTIONS, "funzione",
    ))
    rows.extend(_code_rows(
        base_root, head_root, "rag/core/config.py", _assignments, _CONFIG_ASSIGNMENTS, "assegnazione",
    ))
    for relative in _CHECKERS:
        rows.extend(_file_hash_rows(
            base_root, head_root, relative,
            "il rilevatore è cambiato: non è un'approvazione, ed è a livello di file",
        ))
    for relative in ("CODEOWNERS", ".github/CODEOWNERS"):
        rows.extend(_file_hash_rows(
            base_root, head_root, relative,
            "CODEOWNERS è per file, non per campo: non dice chi ha approvato authority",
        ))
    rows.extend(_workflow_rows(base_root, head_root))
    return {
        "enforcement": "non attivo",
        "rilevamenti": rows,
        "nota": (
            "Il rilevamento non approva e non blocca il merge. "
            "Non esiste un flag, nello stesso albero, che lo faccia tacere."
        ),
    }

