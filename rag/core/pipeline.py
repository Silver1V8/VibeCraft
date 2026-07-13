"""Logica della pipeline Explore -> Canvas -> Propose -> Validate: helper su feature e
tipi di sviluppo, costruzione deterministica dei prompt (canvas/spec/validate/final),
blocco [AGENT CONTEXT] con confidence score e controlli strutturali. Nessuna dipendenza
da FastAPI: le risorse di runtime (grafo, Qdrant, embedding, sidecar) sono iniettate come
parametri espliciti; l'orchestrazione async/I-O resta nei route handler (api/)."""
import json
from pathlib import Path

from core import llm, retrieval
from core.config import CHANGES_DIR, CODE_DIR

# Le 7 sezioni obbligatorie del REASONS Canvas (copertura strutturale e confidence).
CANVAS_SECTIONS = ("Requirements", "Entities", "Approach", "Structure", "Operations", "Norms", "Safeguards")


def slugify_feature(feature_name: str) -> str:
    return feature_name.strip().replace(" ", "-").lower()


async def generate_tolerant(prompt: str, *, purpose: str) -> str:
    """Generazione ASINCRONA tollerante per gli step della pipeline: gli errori di
    rete/timeout non sollevano mai — il messaggio d'errore diventa il testo restituito,
    come nel comportamento storico (l'interfaccia lo mostra all'utente)."""
    try:
        return await llm.agenerate(prompt, purpose=purpose)
    except llm.LLMError as e:
        return str(e)


async def call_ollama_generate(prompt: str) -> str:
    """DEPRECATA: shim di retrocompatibilità che delega a core.llm (purpose 'canvas').
    Usare generate_tolerant(prompt, purpose=...) per indicare lo step corretto."""
    return await generate_tolerant(prompt, purpose="canvas")


def feature_dir(feature_name: str) -> Path:
    folder = slugify_feature(feature_name)
    path = CHANGES_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_dev_types() -> list[str]:
    """Elenca le sottocartelle di 'code/' (backend, frontend, logicAgent, ...) da proporre in tendina."""
    if not CODE_DIR.exists():
        return []
    return sorted(p.name for p in CODE_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def save_dev_type(folder: Path, dev_type: str) -> None:
    """Persiste il tipo di sviluppo scelto in changes/<feature>/meta.json, per ripristinarlo al resume."""
    if not dev_type:
        return
    meta_path = folder / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["dev_type"] = dev_type
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dev_type(folder: Path) -> str:
    """Legge il tipo di sviluppo salvato per la feature, se presente."""
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dev_type", "")
    except Exception:
        return ""


def build_final_prompt(folder_name: str, dev_type: str = "") -> str:
    """Costruisce il prompt finale per Claude Code, scoperto sull'unica cartella code/<dev_type>
    se una tipologia di sviluppo è stata indicata, altrimenti con la distribuzione multi-cartella storica."""
    base = (
        f"Leggi rigorosamente i file 'changes/{folder_name}/canvas.md' e 'changes/{folder_name}/spec.md'. "
        f"Implementa la funzionalità descritta attenendoti esclusivamente all'approccio tecnico del canvas "
        f"e soddisfacendo al 100% tutti gli scenari comportamentali GIVEN/WHEN/THEN della specifica. "
        f"Non inventare logiche, componenti o comportamenti che non siano esplicitamente normati in questi due documenti. "
    )
    if dev_type:
        return base + (
            f"Scrivi ESCLUSIVAMENTE il codice generato nella cartella 'code/{dev_type}/', poiché il tipo di "
            f"sviluppo richiesto per questa feature è '{dev_type}'. Non creare né modificare file in altre "
            f"sottocartelle di 'code/'."
        )
    return base + (
        f"Scrivi il codice generato nella cartella corretta sotto 'code/', in base al tipo di sviluppo richiesto: "
        f"'code/backend' per la logica lato server e le API, 'code/logicAgent' per la logica degli agenti/LLM, "
        f"'code/frontend' per l'interfaccia utente. Se la funzionalità coinvolge più ambiti, distribuisci i file "
        f"nelle rispettive sottocartelle mantenendo la separazione delle responsabilità."
    )


def build_canvas_prompt(feature_name: str, contesto_intervista: str,
                        contesto_progetto_base: str, dev_type: str = "",
                        lessons: str = "") -> str:
    """Prompt deterministico per la generazione del REASONS Canvas (equivalente a canvas.py),
    ancorato al log Explore e al contesto normativo governato. `lessons` (opzionale) sono
    le divergenze canvas<->codice emerse nelle review delle change archiviate più simili:
    con stringa vuota il prompt resta identico a prima (il loop di apprendimento è additivo)."""
    lessons_block = (
        f"\n\n    Lezioni dalle change precedenti (divergenze canvas<->codice emerse dalle review "
        f"delle change archiviate più simili a questa): il nuovo Canvas deve evitare questi punti "
        f"ciechi ricorrenti, rendendo esplicite nelle sezioni Operations, Structure e Safeguards "
        f"le decisioni che in passato erano rimaste implicite:\n    {lessons}"
        if lessons else ""
    )
    scope_note = (
        f"\n\n    Vincolo di ambito: il tipo di sviluppo richiesto per questa feature è ESCLUSIVAMENTE "
        f"'{dev_type}' (il codice finale verrà scritto solo in 'code/{dev_type}/'). "
        f"La sezione Structure deve descrivere layer e componenti pertinenti solo a questo ambito, "
        f"senza proporre modifiche in altre parti del sistema."
        if dev_type else ""
    )

    return f"""
    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "{feature_name}".

    Per definire la strategia tecnica, devi basarti PRIORITARIAMENTE sui requisiti e sui casi limite emersi durante l'intervista preliminare (Explore) riportata qui sotto:

    --- INIZIO LOG INTERVISTA (EXPLORE) ---
    {contesto_intervista}
    --- FINE LOG INTERVISTA ---

    Contesto normativo recuperato dal Graph RAG (ordinato per autorità: rispetta TASSATIVAMENTE
    i safeguard, i vincoli della matrice permessi e i termini del glossario riportati qui sotto;
    non contraddirli e riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards):
    {contesto_progetto_base}{lessons_block}{scope_note}

    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:
    1. Requirements (Cosa deve fare il modulo, estrapolato dall'intervista)
    2. Entities (Modelli di dominio coinvolti)
    3. Approach (Strategia logica per soddisfare i requisiti)
    4. Structure (Layer e API coinvolte)
    5. Operations (Step sequenziali e testabili per lo sviluppo)
    6. Norms (Standard di naming e sicurezza, es. restrizioni email)
    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell'intervista)

    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.
    """


def build_spec_prompt(canvas_content: str, governed_context: str = "") -> str:
    """Prompt deterministico per la generazione di spec.md (scenari BDD) a partire dal Canvas
    e dai vincoli normativi governati (equivalente a propose.py)."""
    norme_block = (
        f"\n\n    Vincoli normativi dal Graph RAG (definisci scenari GIVEN/WHEN/THEN che li verifichino "
        f"esplicitamente, es. tentativi non autorizzati, casi di errore e invarianti dei safeguard):\n"
        f"    {governed_context}"
        if governed_context else ""
    )

    return f"""
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Leggi questo REASONS Canvas:

    {canvas_content}
{norme_block}

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi.
    """


def validate_structural(canvas_text: str, spec_text: str) -> dict:
    """Controlli strutturali deterministici (nessun LLM) su canvas/spec: presenza delle 7
    sezioni del Canvas e degli elementi BDD (GIVEN/WHEN/THEN) nella spec."""
    canvas_lower = canvas_text.lower()
    spec_upper = spec_text.upper()
    sezioni_canvas = {sec: (sec.lower() in canvas_lower) for sec in CANVAS_SECTIONS}
    bdd_given = "GIVEN" in spec_upper
    bdd_when = "WHEN" in spec_upper
    bdd_then = "THEN" in spec_upper
    return {
        "canvas_presente": bool(canvas_text),
        "spec_presente": bool(spec_text),
        "sezioni_canvas": sezioni_canvas,
        "bdd_given": bdd_given,
        "bdd_when": bdd_when,
        "bdd_then": bdd_then,
        "canvas_completo": all(sezioni_canvas.values()),
        "spec_bdd_valida": bdd_given and bdd_when and bdd_then,
    }


def build_validate_prompt(canvas_text: str, spec_text: str, governed: str) -> str:
    """Prompt di validazione semantica pre-apply: coerenza del design contract (Canvas+Spec)
    rispetto ai vincoli normativi governati."""
    return f"""
    Sei un Revisore dell'Architettura. Verifica la COERENZA del design contract (Canvas + Spec)
    rispetto ai vincoli normativi del knowledge base, PRIMA che il codice venga scritto.

    --- CANVAS ---
    {canvas_text}

    --- SPEC (scenari BDD) ---
    {spec_text if spec_text else "(spec.md non ancora generato)"}

    --- VINCOLI NORMATIVI (Graph RAG, ordinati per autorità) ---
    {governed if governed else "(nessun documento normativo recuperato)"}

    Rispondi in modo conciso indicando:
    1. CONFLITTI: il Canvas/Spec viola o contraddice qualche safeguard, policy o termine di glossario? (SI/NO + quali)
    2. COPERTURA: gli scenari BDD coprono i casi di errore e le invarianti dei safeguard pertinenti? Cosa manca?
    3. NON-GOAL: c'è qualcosa fuori ambito rispetto ai vincoli?
    Se tutto è coerente e coperto, rispondi con "✅ VALIDAZIONE SUPERATA. Design contract coerente con la governance."
    """


def _entities_for_docs(graph, doc_ids: list[str], limit: int = 24) -> list[str]:
    """Entità del glossario collegate ai documenti dati (successori di tipo 'entity')."""
    ents: list[str] = []
    for d in doc_ids:
        if d not in graph:
            continue
        for succ in graph.successors(d):
            if graph.nodes[succ].get("type") == "entity" and succ not in ents:
                ents.append(succ)
    return ents[:limit]


def _render_agent_context(c: dict) -> str:
    """Rende il blocco [AGENT CONTEXT] in testo copiabile (formato dell'Articolo 1)."""
    lines = ["[AGENT CONTEXT]", f"- Intento probabile: {c['intent']}"]
    lines.append(f"- Sorgenti normative: {', '.join(c['normative_sources']) or '—'}")
    lines.append(f"- Entità coinvolte: {', '.join(c['entities'][:20]) or '—'}")
    lines.append(f"- Safeguard pertinenti: {', '.join(c['safeguards']) or '—'}")
    lines.append("- Vincoli da rispettare:")
    for x in c["constraints"]:
        lines.append(f"    • {x}")
    lines.append("- Rischi:")
    for x in (c["risks"] or ["(nessuno rilevato)"]):
        lines.append(f"    • {x}")
    lines.append(f"- File da leggere: {', '.join(c['files_to_read'])}")
    lines.append(f"- Confidence: {c['confidence']} ({c['confidence_label']})")
    lines.append("\n--- PROMPT SUGGERITO ---")
    lines.append(c["suggested_prompt"])
    return "\n".join(lines)


def build_agent_context(feature_name: str, dev_type: str = "", *,
                        graph, qdrant, embed_model, colbert_store) -> dict:
    """Costruisce il blocco strutturato [AGENT CONTEXT] (intent / sorgenti / entità /
    vincoli / rischi / file / prompt / confidence) dell'Articolo 1, in modo deterministico
    a partire dal retrieval governato e dallo stato di canvas/spec. Il confidence score è
    una metrica composita (rilevanza + copertura del canvas + spec BDD + copertura normativa).

    Le risorse (grafo, Qdrant, modello di embedding, sidecar ColBERT) sono iniettate; funzione
    sincrona pensata per girare in threadpool dal route handler."""
    folder_name = slugify_feature(feature_name)
    folder = CHANGES_DIR / folder_name
    canvas = (folder / "canvas.md").read_text(encoding="utf-8") if (folder / "canvas.md").exists() else ""
    spec = (folder / "spec.md").read_text(encoding="utf-8") if (folder / "spec.md").exists() else ""
    dev_type = dev_type or load_dev_type(folder)

    query = f"{feature_name}\n{canvas[:2000]}"
    results: list = []
    top_score = 0.0
    if graph is not None and qdrant is not None and embed_model is not None:
        try:
            results = retrieval.hybrid_search(query, 6, qdrant=qdrant, embed_model=embed_model,
                                              colbert_store=colbert_store or {})
            if results:
                top_score = max((r.get("colbert_score") or r.get("dense_score") or 0.0) for r in results)
        except Exception:
            results = []
    doc_ids = retrieval.select_governed_docs(query, graph=graph, results=results) if results else []

    entities = _entities_for_docs(graph, doc_ids) if graph is not None else []
    safeguards = [e for e in entities if e.upper().startswith("SAFEGUARD")]
    iron = [
        d for d in doc_ids
        if graph is not None and str(graph.nodes[d].get("classification", "")).upper() == "IRON_MEMORY"
    ]

    sections_present = [s for s in CANVAS_SECTIONS if s.lower() in canvas.lower()]
    coverage = len(sections_present) / len(CANVAS_SECTIONS) if canvas else 0.0
    spec_ok = 1.0 if all(k in spec.upper() for k in ("GIVEN", "WHEN", "THEN")) else 0.0
    governance = min(1.0, len(doc_ids) / 3.0)
    # NB: 'retrieval_score' (non 'retrieval') per non ombreggiare il modulo core.retrieval usato sopra.
    retrieval_score = max(0.0, min(1.0, float(top_score)))
    confidence = round(0.35 * retrieval_score + 0.30 * coverage + 0.15 * spec_ok + 0.20 * governance, 2)
    label = "alta" if confidence >= 0.75 else ("media" if confidence >= 0.5 else "bassa")

    constraints = []
    if safeguards:
        constraints.append("Rispettare i safeguard: " + ", ".join(safeguards[:8]))
    constraints.append("Usare i termini del glossario in MAIUSCOLO (es. EVENTO, UTENTE), senza sinonimi colloquiali.")
    if iron:
        constraints.append("Documenti IRON_MEMORY vincolanti: " + ", ".join(iron))

    risks = []
    if not spec_ok:
        risks.append("Spec BDD assente o incompleta: scenari di test non verificabili.")
    missing = [s for s in CANVAS_SECTIONS if s not in sections_present]
    if canvas and missing:
        risks.append(f"Canvas incompleto: sezioni mancanti ({', '.join(missing)}).")
    if not doc_ids:
        risks.append("Nessun documento normativo pertinente recuperato: contratto poco ancorato alla governance.")
    for sg in safeguards[:5]:
        risks.append(f"Possibile violazione di [{sg}] se non gestita esplicitamente.")

    files_to_read = [f"changes/{folder_name}/canvas.md", f"changes/{folder_name}/spec.md"]
    files_to_read += [f"code/{dev_type}/"] if dev_type else ["code/backend/", "code/frontend/", "code/logicAgent/"]

    ctx = {
        "intent": f"Implementare la feature '{feature_name}'" + (f" (ambito: {dev_type})" if dev_type else ""),
        "normative_sources": doc_ids,
        "entities": entities,
        "safeguards": safeguards,
        "constraints": constraints,
        "risks": risks,
        "files_to_read": files_to_read,
        "suggested_prompt": build_final_prompt(folder_name, dev_type),
        "confidence": confidence,
        "confidence_label": label,
    }
    ctx["text"] = _render_agent_context(ctx)
    return ctx
