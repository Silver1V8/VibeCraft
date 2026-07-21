"""Project brief (S6, piano: docs/00_meta_governance/piano_intake_import.md): sintesi
architetturale di un target di code/ generata via Ollama, GROUNDED sui dati REALI del
grafo della conoscenza — simboli di codice del target, archi DEPENDS_ON fra loro e
archi IMPLEMENTS verso le sezioni delle spec — mai su conoscenza inventata dal modello.

Precondizione: un import progetto RIUSCITO per il target (entry "project_import" con
stato "applied" nel journal intake.jsonl, scritta da core/project_import.py). Senza,
il brief non ha nulla di reale da raccontare → errore tipizzato (lo strato HTTP lo
mappa su 409). Grafo senza simboli per il target → esito "done" con avviso esplicito,
mai un crash (il reindex del codice può essere in ritardo: limite noto, non nascosto).

Il brief entra in STAGING come ogni altro documento (core.intake.stage_document,
source="brief", categoria suggerita 04_knowledge_informative) e passa dalla review S2:
NESSUN percorso diretto verso docs/. VINCOLO LLM: qwen3.5:9b, num_ctx 16384,
think:false (core/llm.py) — non toccati qui.

Logica pura con DI (pattern di core/doc_generation.py): grafo, code_store, base_dir e
la funzione di generazione sono iniettabili; il default llm.generate risolve il
runtime reale a CALL time."""
from __future__ import annotations

import time
import uuid

from core import intake, llm
from core.doc_generation import (
    GenerationError,
    _attach_generation_metadata,
    _now_iso,
    _validate_generated_markdown,
)
from core.project_import import _validate_target

# Stesso purpose LLM della generazione S3 (documento markdown grounded, ruolo Canvas).
_BRIEF_PURPOSE = "canvas"

# Categoria docs/ suggerita per il brief (decisione del piano, S6): conoscenza
# informativa, mai normativa — la review S2 può comunque cambiarla all'approve.
BRIEF_CATEGORIA_SUGGERITA = "04_knowledge_informative"

# Tetti sul materiale di grounding serializzato nel prompt: un target reale può avere
# centinaia di simboli, il contesto utile di qwen3.5:9b (num_ctx 16384) no.
_MAX_SIMBOLI_NEL_PROMPT = 80
_MAX_ARCHI_NEL_PROMPT = 60


class ProjectBriefError(RuntimeError):
    """Base degli errori del project brief."""


class BriefWithoutImportError(ProjectBriefError):
    """Nessun import progetto riuscito per il target: il brief non ha dati reali
    su cui poggiare (lo strato HTTP risponde 409)."""


# ---------------------------------------------------------------------------
# Precondizione: un import progetto "applied" per il target nel journal intake
# ---------------------------------------------------------------------------
def last_applied_import(target: str, base_dir=None) -> dict | None:
    """Ultima entry di journal "project_import"/"applied" per `target` (None se non
    esiste). Riusa il folding "ultima riga per id vince" di core.intake._journal_state:
    il journal è il registro unico dell'intake, non se ne introduce un secondo."""
    _validate_target(target)
    paths = intake.ensure_staging_dirs(base_dir)
    latest: dict | None = None
    for rec in intake._journal_state(paths).values():
        if (rec.get("type") == "project_import" and rec.get("status") == "applied"
                and rec.get("target") == target):
            latest = rec
    return latest


def require_applied_import(target: str, base_dir=None) -> dict:
    """Entry dell'ultimo import riuscito per `target`, o BriefWithoutImportError."""
    rec = last_applied_import(target, base_dir=base_dir)
    if rec is None:
        raise BriefWithoutImportError(
            f"nessun import progetto riuscito per il target {target!r}: "
            f"esegui prima un'anteprima+applica dalla pagina /intake"
        )
    return rec


# ---------------------------------------------------------------------------
# Grounding deterministico: i fatti del grafo per il target (nessun LLM qui)
# ---------------------------------------------------------------------------
def collect_target_facts(graph, code_store: dict | None, target: str) -> dict:
    """Estrae dal grafo i dati REALI del target: simboli (nodi type="code" con
    dev_type == target), entrypoint (kind "endpoint" o con route), archi DEPENDS_ON
    fra simboli del target e archi IMPLEMENTS simbolo→sezione/documento (la mappa
    simboli→spec chiesta dal piano). Deterministico e ordinato: stesso grafo →
    stesso prompt. code_store è accettato per simmetria con lo snapshot del server
    (i metadati che servono qui vivono già sugli attributi dei nodi)."""
    simboli: list[dict] = []
    entrypoint: list[dict] = []
    dipendenze: list[tuple[str, str]] = []
    implements: list[dict] = []
    kinds: dict[str, int] = {}

    if graph is None:
        return {"target": target, "n_simboli": 0, "simboli": [], "entrypoint": [],
                "dipendenze": [], "implements": [], "kinds": {}}

    target_ids = set()
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") != "code" or attrs.get("dev_type") != target:
            continue
        target_ids.add(node_id)
        sym = {"id": str(node_id), "kind": attrs.get("kind", ""),
               "name": attrs.get("name", ""), "file": attrs.get("file", "")}
        simboli.append(sym)
        kinds[sym["kind"]] = kinds.get(sym["kind"], 0) + 1
        if sym["kind"] == "endpoint" or attrs.get("route"):
            entrypoint.append({**sym, "route": attrs.get("route", "")})

    for u, v, data in graph.edges(data=True):
        if u not in target_ids:
            continue
        relation = data.get("relation", "")
        if relation == "DEPENDS_ON" and v in target_ids:
            dipendenze.append((str(u), str(v)))
        elif relation == "IMPLEMENTS":
            implements.append({"symbol": str(u), "spec": str(v),
                               "weight": data.get("weight")})

    simboli.sort(key=lambda s: s["id"])
    entrypoint.sort(key=lambda s: s["id"])
    dipendenze.sort()
    implements.sort(key=lambda e: (e["symbol"], e["spec"]))
    return {"target": target, "n_simboli": len(simboli), "simboli": simboli,
            "entrypoint": entrypoint, "dipendenze": dipendenze,
            "implements": implements, "kinds": dict(sorted(kinds.items()))}


def build_brief_prompt(target: str, facts: dict) -> str:
    """Prompt deterministico per il brief: serializza i fatti del grafo (troncati ai
    tetti di modulo) e vieta esplicitamente di inventare simboli o file non elencati."""
    simboli = facts["simboli"][:_MAX_SIMBOLI_NEL_PROMPT]
    righe_simboli = "\n".join(f"- {s['kind']} `{s['name']}` in {s['file']}" for s in simboli)
    if facts["n_simboli"] > len(simboli):
        righe_simboli += f"\n… e altri {facts['n_simboli'] - len(simboli)} simboli (omessi)"

    righe_entry = "\n".join(
        f"- {e['kind']} `{e['name']}` in {e['file']}" + (f" (route {e['route']})" if e.get("route") else "")
        for e in facts["entrypoint"][:_MAX_ARCHI_NEL_PROMPT]
    ) or "(nessun entrypoint rilevato)"

    righe_deps = "\n".join(f"- `{u}` → `{v}`"
                           for u, v in facts["dipendenze"][:_MAX_ARCHI_NEL_PROMPT]) \
        or "(nessuna dipendenza interna rilevata)"

    righe_impl = "\n".join(
        f"- `{e['symbol']}` IMPLEMENTS `{e['spec']}`"
        + (f" (peso {e['weight']})" if e.get("weight") is not None else "")
        for e in facts["implements"][:_MAX_ARCHI_NEL_PROMPT]
    ) or "(nessun arco IMPLEMENTS verso le spec: i code-link possono richiedere un full rebuild)"

    conteggi = ", ".join(f"{k}: {n}" for k, n in facts["kinds"].items()) or "nessuno"

    return f"""Sei un Software Architect. Scrivi UN documento Markdown di sintesi architetturale
("project brief") del progetto importato in code/{target}, destinato a docs/{BRIEF_CATEGORIA_SUGGERITA}.

DATI REALI DAL GRAFO DELLA CONOSCENZA (unica fonte ammessa — NON inventare simboli,
file, route o dipendenze che non compaiono qui sotto):

Simboli del target ({facts['n_simboli']} totali — {conteggi}):
{righe_simboli or '(nessuno)'}

Entrypoint:
{righe_entry}

Dipendenze interne (archi DEPENDS_ON):
{righe_deps}

Mappa simboli → spec (archi IMPLEMENTS):
{righe_impl}

REGOLE DI FORMATO (obbligatorie):
- Il documento inizia con un blocco frontmatter YAML delimitato da `---` con SOLO i
  campi `title` e `scope` (una frase).
- Dopo il frontmatter, un titolo `# ...` e poi ESATTAMENTE queste sezioni `##`, in
  quest'ordine: `## Componenti`, `## Entrypoint`, `## Dipendenze principali`,
  `## Mappa simboli → spec`, `## Aree candidate a refactoring`.
- Ogni affermazione deve poggiare sui dati elencati sopra; dove i dati mancano,
  scrivilo esplicitamente invece di inventare.
- Nessun testo fuori dal documento.
"""


# ---------------------------------------------------------------------------
# generate_project_brief: il job completo (sincrono, pensato per il thread del
# GenerationManager di core/doc_generation.py — mai sull'event loop).
# ---------------------------------------------------------------------------
def _journal_discarded_brief(base_dir, *, target: str, motivo: str) -> None:
    """Traccia nel journal un brief SCARTATO in validazione (mai entrato in staging):
    stato 'discarded', ignorato da list_staged/approve/reject."""
    paths = intake.ensure_staging_dirs(base_dir)
    intake._append_journal(paths, {
        "id": uuid.uuid4().hex[:12],
        "status": "discarded",
        "source": "brief",
        "target": target,
        "motivo": motivo,
        "discarded_at": _now_iso(),
    })


def generate_project_brief(target: str, *, graph=None, code_store: dict | None = None,
                           base_dir=None, generate=None) -> dict:
    """Genera il project brief di `target` grounded sul grafo e lo mette in STAGING
    (source "brief"), approvabile SOLO dal ciclo di review S2 — nessuna scrittura in
    docs/. Precondizione: import progetto riuscito per il target (BriefWithoutImportError
    altrimenti). Grafo senza simboli per il target → esito con `avviso`, senza chiamare
    l'LLM (grounded significa: niente dati, niente brief inventato).

    Restituisce {"target", "generati", "scartati", "n_generati", "n_scartati",
    "avviso" | None, "latency": {"generation_ms", "total_ms"}}. Solleva GenerationError
    se la chiamata LLM fallisce (il GenerationManager la registra come job "failed")."""
    total_start = time.time()
    import_rec = require_applied_import(target, base_dir=base_dir)
    facts = collect_target_facts(graph, code_store, target)

    base = {"target": target, "generati": [], "scartati": [],
            "n_generati": 0, "n_scartati": 0, "avviso": None}
    if facts["n_simboli"] == 0:
        return {**base,
                "avviso": (f"nessun simbolo nel grafo per il target {target!r}: brief non "
                           f"generato — il reindex del codice potrebbe non essere ancora "
                           f"passato (serve un reindex/full rebuild)"),
                "latency": {"generation_ms": 0.0,
                            "total_ms": round((time.time() - total_start) * 1000, 2)}}

    prompt = build_brief_prompt(target, facts)
    generate_fn = generate or (lambda p: llm.generate(p, purpose=_BRIEF_PURPOSE))

    generation_start = time.time()
    try:
        markdown = generate_fn(prompt).strip()
    except llm.LLMError as exc:
        raise GenerationError(f"generazione brief fallita: {exc}") from exc
    latency_generation_ms = round((time.time() - generation_start) * 1000, 2)

    try:
        _, modello = llm.resolve(_BRIEF_PURPOSE)
    except llm.LLMError:
        modello = None

    latency = {"generation_ms": latency_generation_ms,
               "total_ms": round((time.time() - total_start) * 1000, 2)}
    try:
        _validate_generated_markdown(markdown)
    except GenerationError as exc:
        _journal_discarded_brief(base_dir, target=target, motivo=str(exc))
        return {**base, "scartati": [{"motivo": str(exc)}], "n_scartati": 1,
                "latency": latency}

    filename = f"brief-{target}-{uuid.uuid4().hex[:8]}.md"
    try:
        record = intake.stage_document(filename, markdown.encode("utf-8"),
                                       base_dir=base_dir, source="brief")
    except intake.IntakeError as exc:
        motivo = f"staging fallito: {exc}"
        _journal_discarded_brief(base_dir, target=target, motivo=motivo)
        return {**base, "scartati": [{"motivo": motivo}], "n_scartati": 1,
                "latency": latency}

    record = _attach_generation_metadata(base_dir, record, {
        "target": target,
        "import_id": import_rec.get("id"),
        "categoria_suggerita": BRIEF_CATEGORIA_SUGGERITA,
        "modello": modello,
        "n_simboli_grounding": facts["n_simboli"],
        "latenze": {"generation_ms": latency_generation_ms},
    })
    latency["total_ms"] = round((time.time() - total_start) * 1000, 2)
    return {**base, "generati": [record], "n_generati": 1, "latency": latency}
