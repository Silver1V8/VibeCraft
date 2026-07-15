"""Logica della pipeline Explore -> Canvas -> Propose -> Validate: helper su feature e
tipi di sviluppo, costruzione deterministica dei prompt (canvas/spec/validate/final),
blocco [AGENT CONTEXT] con confidence score e controlli strutturali. Nessuna dipendenza
da FastAPI: le risorse di runtime (grafo, Qdrant, embedding, sidecar) sono iniettate come
parametri espliciti; l'orchestrazione async/I-O resta nei route handler (api/)."""
import json
import re
from pathlib import Path

from core import llm, retrieval
from core.config import CHANGES_DIR, CODE_DIR, TECH_QUERY_TEMPLATE

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


def _dev_type_words(dev_type: str) -> list[str]:
    """Scompone il nome di una sottocartella di code/ nelle sue parole: 'logicAgent',
    'logic_agent' e 'logic-agent' danno tutti ['logic', 'agent']."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", dev_type.strip())
    return spaced.replace("_", " ").replace("-", " ").lower().split()


def dev_type_tag_variants(dev_type: str) -> list[str]:
    """Grafie con cui un documento può essersi taggato per dichiarare l'ambito `dev_type`.
    La cartella è 'logicAgent' ma il tag può essere 'logic-agent', 'logic_agent',
    'logicagent' o 'logic agent': si cercano tutte, così la convenzione di tagging del
    progetto non deve piegarsi a quella dei nomi di cartella (né viceversa).
    Lista vuota se non c'è un ambito: nessun filtro, vedi retrieval.scope_tag_filter."""
    words = _dev_type_words(dev_type)
    if not words:
        return []
    variants = ["".join(words), "-".join(words), "_".join(words), " ".join(words), dev_type.strip().lower()]
    return list(dict.fromkeys(v for v in variants if v))   # unici, ordine stabile


def build_tech_query(dev_type: str, template: str = TECH_QUERY_TEMPLATE) -> str:
    """Domanda del ramo TECNICO del retrieval governato: «con quale stack e quali pattern si
    implementa nell'ambito <dev_type>?». È una query semantica come le altre — nessun filtro
    su cartelle o nomi file: recupera ciò che le somiglia, ovunque stia nell'alberatura.

    Il testo vive in rag_config.yaml (retrieval.tech_query) perché è vocabolario di progetto:
    va scritto coi termini dei documenti che si vogliono trovare. Non configurato = ramo
    tecnico spento, così su un progetto nuovo non si inventa una domanda per suo conto.

    Il dev_type è una sottocartella di code/ ('logicAgent') e va reso a parole ('logic agent'),
    la forma che compare nella prosa dei documenti. Stringa vuota = nessun ramo tecnico."""
    if not dev_type.strip() or not template.strip():
        return ""
    readable = " ".join(_dev_type_words(dev_type))
    # replace() e non format(): il template è testo libero scritto a mano nel config e
    # un'eventuale graffa di troppo non deve far esplodere la generazione del canvas.
    return template.replace("{dev_type}", readable)


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


# Header dei chunk nel contesto governato serializzato da retrieval.retrieve_governed_context:
# "--- <doc_id> § <sezione> [TAG] ---". Il doc_id è il primo token dopo i trattini.
_GOVERNED_HEADER_RE = re.compile(r"^--- (\S+) § ", re.MULTILINE)


def governed_docs_from_context(governed_context: str) -> list[str]:
    """Doc_id unici, in ordine di apparizione, citati negli header del contesto normativo
    governato. Parsing deterministico del formato prodotto da retrieve_governed_context:
    permette di sapere QUALI documenti hanno ancorato un canvas senza rifare il retrieval."""
    docs: list[str] = []
    for d in _GOVERNED_HEADER_RE.findall(governed_context or ""):
        if d not in docs:
            docs.append(d)
    return docs


def save_governed_sources(folder: Path, doc_ids: list[str]) -> None:
    """Persiste in changes/<feature>/meta.json i documenti normativi usati dal retrieval
    governato per generare il canvas. Letti all'archive per proporre un caso candidato
    al golden-set di eval (vedi core.canvas_review.extract_eval_candidate)."""
    if not doc_ids:
        return
    meta_path = folder / "meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta["governed_sources"] = doc_ids
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
                        lessons: str = "", contesto_tecnico: str = "") -> str:
    """Prompt deterministico per la generazione del REASONS Canvas (equivalente a canvas.py),
    ancorato al log Explore e al contesto normativo governato. `lessons` (opzionale) sono
    le divergenze canvas<->codice emerse nelle review delle change archiviate più simili:
    con stringa vuota il prompt resta identico a prima (il loop di apprendimento è additivo).

    `contesto_tecnico` (le specifiche tecnologiche dell'ambito) va in un blocco PROPRIO e non
    insieme alle norme: il blocco normativo dice «rispetta i safeguard e riusa i codici in
    Entities/Norms/Safeguards», istruzione che non ha senso per uno stack e che lasciava
    l'LLM senza indicazioni su dove usarlo — infatti lo ignorava. Lo stack serve a Approach
    e Structure, e questo blocco glielo dice."""
    lessons_block = (
        f"\n\n    Lezioni dalle change precedenti (divergenze canvas<->codice emerse dalle review "
        f"delle change archiviate più simili a questa): il nuovo Canvas deve evitare questi punti "
        f"ciechi ricorrenti, rendendo esplicite nelle sezioni Operations, Structure e Safeguards "
        f"le decisioni che in passato erano rimaste implicite:\n    {lessons}"
        if lessons else ""
    )
    scope_note = (
        f"\n\n    Vincolo di ambito: il tipo di sviluppo richiesto per questa feature è ESCLUSIVAMENTE "
        f"'{dev_type}' (il codice finale verrà scritto solo in 'code/{dev_type}/'). Vale per TUTTE "
        f"le 7 sezioni, non solo per Structure: Approach, Structure e Operations devono descrivere "
        f"esclusivamente lavoro da fare in '{dev_type}'. È VIETATO progettare o elencare come step "
        f"ciò che vive in altri ambiti (endpoint da creare, tabelle, servizi, controlli lato "
        f"server se l'ambito è il client, e viceversa): di ciò che sta fuori si può solo dare per "
        f"esistente l'interfaccia che questa feature consuma."
        if dev_type else ""
    )
    ambito = f" {dev_type}" if dev_type else ""
    tecnico_block = (
        f"\n\n    Specifiche tecnologiche vincolanti per l'ambito{ambito} (stack, linguaggi, "
        f"librerie e struttura del progetto GIÀ DECISI: non sono suggerimenti). Le sezioni "
        f"Approach, Structure e Operations DEVONO adottare ESATTAMENTE queste tecnologie, "
        f"chiamandole COL LORO NOME. In particolare:\n"
        f"    - dove qui è indicata una libreria per un compito (validazione, chiamate HTTP, "
        f"stile, grafici...), usa QUELLA e citala per nome: è VIETATO inventarne un'altra, "
        f"scrivere un'alternativa 'o simile', o restare sul generico.\n"
        f"    - non sono requisiti da verificare né contenuto da riassumere: sono il COME si "
        f"costruisce, e servono solo a rendere concreti Approach, Structure e Operations.\n"
        f"    {contesto_tecnico}"
        if contesto_tecnico else ""
    )

    return f"""
    Sei un Tech Lead expert. Il tuo compito è generare un REASONS Canvas in formato Markdown per la seguente feature: "{feature_name}".

    L'ARGOMENTO del Canvas è UNO SOLO: la feature emersa dall'intervista qui sotto. L'intervista
    è l'unica fonte di COSA va costruito; tutto ciò che viene dopo sono vincoli su COME, e non
    può cambiare l'argomento. Non descrivere funzionalità di cui l'intervista non parla.

    --- INIZIO LOG INTERVISTA (EXPLORE) ---
    {contesto_intervista}
    --- FINE LOG INTERVISTA ---

    Contesto normativo recuperato dal Graph RAG. ATTENZIONE: NON è l'argomento del Canvas — è
    una LENTE sulla feature dell'intervista. Rispetta TASSATIVAMENTE i safeguard, i vincoli
    della matrice permessi e i termini del glossario riportati qui sotto, non contraddirli e
    riusa i loro codici/entità nelle sezioni Entities, Norms e Safeguards; ma NON trasformare in
    requisiti le funzionalità che questi documenti descrivono e che l'intervista non ha chiesto:
    se una funzionalità resta sensata dopo aver tolto l'intervista, non appartiene a questo Canvas.
    {contesto_progetto_base}{tecnico_block}{lessons_block}{scope_note}

    Il REASONS Canvas generato DEVE contenere tassativamente queste 7 sezioni:
    1. Requirements (Cosa deve fare il modulo, estrapolato dall'intervista)
    2. Entities (Modelli di dominio coinvolti)
    3. Approach (Strategia logica per soddisfare i requisiti)
    4. Structure (Layer e API coinvolte)
    5. Operations (Step sequenziali e testabili per lo sviluppo)
    6. Norms (Standard di naming e sicurezza, es. restrizioni email)
    7. Safeguards (Vincoli non negoziabili e gestione degli errori concordati nell'intervista)

    VERIFICA FINALE prima di rispondere — rileggi l'intervista in cima e controlla che la
    sezione Requirements descriva ESATTAMENTE ciò che l'intervista chiede per "{feature_name}",
    non le funzionalità dei documenti normativi qui sopra: quei documenti descrivono ANCHE
    altri moduli del sistema (pannelli admin, altre console) che NON sono questa feature.
    Se una funzionalità che stai per scrivere non è riconducibile a una frase dell'intervista,
    toglila.

    Rispondi esclusivamente con il contenuto del file Markdown, formattato in modo pulito.
    """


def build_spec_prompt(canvas_content: str, governed_context: str = "",
                      dev_type: str = "", feature_name: str = "") -> str:
    """Prompt deterministico per la generazione di spec.md (scenari BDD) a partire dal Canvas
    e dai vincoli normativi governati (equivalente a propose.py).

    Due lezioni, stesso schema. Un documento messo nel prompt con l'istruzione «definisci
    scenari che lo verifichino» ne diventa l'ARGOMENTO, e la feature sparisce:
    · la spec tecnologica → scenari sul test runner e sulla libreria di grafici (e, vietandoli,
      il documento ricopiato come preambolo). Qui non c'è più: lo stack lo porta il Canvas.
    · le norme → uno spec intitolato «Log Audit» con scenari sull'immutabilità dei record,
      mentre il Canvas parlava d'altro. Le norme però DEVONO produrre scenari (permessi e
      safeguard sono comportamento vero): non si tolgono, si riformulano come LENTE sulla
      feature — servono a trovarne i casi limite, non a sostituirne il soggetto.

    `feature_name` ancora QUALE feature, ma è solo un'etichetta: il Canvas resta l'unica fonte
    di cosa la feature fa. Serve perché col solo Canvas l'LLM derivava sul tema dei documenti
    recuperati (uno spec su «Dati del DIPENDENTE» per una feature di richiesta eventi); ma va
    presentato come etichetta e non come definizione, o vince lui sul Canvas — con un nome
    ambiguo l'LLM si inventava un dominio deducendolo dal titolo."""
    etichetta = f" (etichetta: «{feature_name}»)" if feature_name else ""
    norme_block = (
        f"\n\n    Vincoli normativi dal Graph RAG. ATTENZIONE: NON sono l'argomento dello spec — "
        f"l'argomento è la feature del Canvas, e basta. Servono come LENTE per trovarne i casi "
        f"limite: da qui ricavi gli scenari negativi CHE LA FEATURE DEVE GESTIRE (tentativi non "
        f"autorizzati su di essa, suoi casi di errore, invarianti dei safeguard che essa tocca) "
        f"e i termini/codici esatti da citare. È VIETATO scrivere scenari su parti del sistema "
        f"che questi documenti nominano ma che la feature non tocca: se uno scenario resta "
        f"sensato dopo aver tolto la feature, non va scritto.\n"
        f"    {governed_context}"
        if governed_context else ""
    )
    scope_note = (
        f"\n\n    Vincolo di ambito: questa feature è ESCLUSIVAMENTE '{dev_type}'. Gli scenari devono "
        f"descrivere comportamento osservabile in questo ambito; non scrivere scenari su parti del "
        f"sistema fuori da esso."
        if dev_type else ""
    )

    return f"""
    Sei un Analista Software esperto in metodologie BDD (Behavior-Driven Development).
    Scrivi le specifiche (spec.md) di UNA SOLA feature: quella descritta dal REASONS Canvas
    qui sotto{etichetta}. Il Canvas è l'UNICA fonte di cosa la feature fa: l'etichetta serve
    solo a identificarla, non dedurne requisiti; e nulla di ciò che segue il Canvas può
    cambiarne il soggetto.

    {canvas_content}
{norme_block}{scope_note}

    Basandoti sulle regole e sui requisiti del Canvas (e sui vincoli normativi qui sopra, se presenti),
    scrivi il file delle specifiche tecniche (spec.md).
    Devi definire gli scenari di test utilizzando rigorosamente il formato:
    - GIVEN (Dato che...)
    - WHEN (Quando...)
    - THEN (Allora...)
    - AND (E...)

    Ogni scenario deve avere per soggetto la feature del Canvas e descriverne un COMPORTAMENTO
    osservabile. Non scrivere scenari che verificano lo stack, le librerie o gli strumenti in sé.
    Niente scenari duplicati: se due differiscono solo nella formulazione, tienine uno.

    Non inventare funzionalità non presenti nel Canvas o nei vincoli normativi. Se uno scenario
    nomina una tecnologia o mostra codice, usa ESCLUSIVAMENTE le tecnologie già citate nel
    Canvas: qualsiasi altro linguaggio, libreria o strumento è VIETATO.

    VERIFICA FINALE prima di rispondere — rileggi il Canvas in cima e controlla che ogni
    scenario discenda da un suo requisito: i vincoli normativi descrivono ANCHE altri moduli
    del sistema (cataloghi di funzionalità, pannelli, console) che NON sono questa feature,
    e non vanno trasformati in scenari. Se uno scenario non è riconducibile a una frase del
    Canvas, toglilo.

    Rispondi esclusivamente con il contenuto del file Markdown, senza preamboli né commenti
    prima o dopo.
    """


# Entità canoniche del glossario: i nodi-entità con prefisso 'entity::'. Il resto dei nodi
# type="entity" è rumore di estrazione (numeri, id di documento, codici di regola) e come
# dizionario darebbe match casuali.
_ENTITY_PREFIX = "entity::"
# Un titolo di scenario: la riga-titolo che precede un GIVEN, unica sintesi esplicita del suo
# soggetto. L'LLM alterna due forme e vanno riconosciute entrambe: l'intestazione markdown
# ("#### Scenario 1: ...") e la riga in grassetto ("**Scenario 1: ...**"). Considerando solo
# la prima, uno spec scritto tutto in grassetto risultava avere un solo scenario gigante e il
# controllo diventava cieco.
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# Solo grassetto a inizio riga: "- **GIVEN (Dato che...)**" è un elemento di lista, non un
# titolo, e il filtro _BDD_KEYWORDS_RE scarta comunque le righe che sono passi BDD.
_BOLD_TITLE_RE = re.compile(r"^\*\*(.+?)\*\*\s*:?\s*$", re.MULTILINE)
_BDD_KEYWORDS_RE = re.compile(r"^\W*(GIVEN|WHEN|THEN|AND|E)\b", re.IGNORECASE)
_GIVEN_RE = re.compile(r"\bGIVEN\b", re.IGNORECASE)


def glossary_entities(graph) -> list[str]:
    """Entità canoniche del glossario, dal grafo. Vuoto se il grafo non c'è: il controllo a
    valle si limita a non dire nulla, invece di inventarsi un dizionario."""
    if graph is None:
        return []
    return sorted(n[len(_ENTITY_PREFIX):] for n in graph.nodes
                  if isinstance(n, str) and n.startswith(_ENTITY_PREFIX))


def _titles(spec_text: str) -> list[tuple[int, str]]:
    """Righe-titolo del documento (markdown o grassetto), in ordine di posizione, escludendo
    quelle che sono passi BDD ("**GIVEN (Dato che...)**") e non titoli di scenario."""
    found = [(m.start(), m.group(1)) for m in _HEADING_RE.finditer(spec_text)]
    found += [(m.start(), m.group(1)) for m in _BOLD_TITLE_RE.finditer(spec_text)]
    return sorted((pos, t) for pos, t in found if not _BDD_KEYWORDS_RE.match(t))


def split_scenarios(spec_text: str) -> list[dict]:
    """Spezza spec.md in scenari: ognuno è la riga-titolo che precede un GIVEN, più il testo
    fino allo scenario successivo. Il GIVEN è l'ancora (il formato BDD è imposto dal prompt),
    la riga-titolo è il soggetto. Gli scenari senza titolo hanno titolo ''."""
    headings = _titles(spec_text)
    starts: list[tuple[int, str]] = []
    for g in (m.start() for m in _GIVEN_RE.finditer(spec_text)):
        prev = [(pos, title) for pos, title in headings if pos < g]
        start, title = prev[-1] if prev else (g, "")
        if not starts or start > starts[-1][0]:
            starts.append((start, title))

    out = []
    for i, (start, title) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(spec_text)
        out.append({"title": title, "text": spec_text[start:end]})
    return out


def _stem(entity: str) -> str:
    """Radice di un'entità per il match in prosa: via le vocali finali, così il singolare del
    glossario riconosce il plurale italiano che gli scenari usano davvero — EVENTO→'event'
    trova «eventi», RICHIESTA→'richiest' trova «richieste», UTENTE→'utent' trova «utenti».
    Senza, «Lista degli Eventi» risultava priva di entità e veniva segnalata a torto.
    Si accorcia solo finché resta una radice lunga: su nomi corti o senza vocali finali
    (AUDIT_LOG) si usa l'entità intera, che è già discriminante."""
    stem = entity.lower().rstrip("aeiou")
    return stem if len(stem) >= 4 else entity.lower()


def _mentions(text: str, entities: list[str]) -> list[str]:
    """Entità nominate in `text`, per radice e case-insensitive: gli scenari citano le entità
    in prosa minuscola e al plurale («l'utente», «gli eventi») anche quando il glossario le
    vuole in maiuscolo e al singolare. Un match esatto scarterebbe proprio gli scenari buoni."""
    low = text.lower()
    return [e for e in entities if _stem(e) in low]


def check_scenario_scope(spec_text: str, canvas_text: str, known_entities: list[str],
                         feature_name: str = "") -> dict:
    """Controllo DETERMINISTICO (nessun LLM) della pertinenza degli scenari: segnala quelli il
    cui TITOLO non nomina né un'entità citata dal Canvas né una parola del nome della feature.

    Le parole della feature contano come àncora perché i titoli buoni spesso parlano in
    termini di UI e non di glossario («Gestione Erroristica UI su Form» è pertinente per la
    feature "form eventi" pur senza nominare RICHIESTA): senza questa via d'uscita il
    controllo segnalava 10 scenari su 12 in uno spec discreto, e un allarme che suona
    quasi sempre non è un segnale.

    Perché il titolo e non il corpo: nel corpo anche uno scenario fuori tema nomina di sfuggita
    un'entità della feature («l'utente tenta di modificare audit_log» contiene UTENTE), mentre
    uno pertinente cita entità che il Canvas non ha («email di NOTIFICA»). Solo il titolo dice
    di cosa parla lo scenario. È il criterio del prompt reso meccanico: se il soggetto non è
    la feature, lo scenario resta sensato anche togliendola.

    ADVISORY, non distruttivo: segnala e basta. È un'euristica sul titolo — cancellare scenari
    su un falso positivo costerebbe più di quanto valga, e la spec resta dell'autore.
    Report vuoto senza entità note o senza scenari: niente grafo, niente giudizio."""
    scenarios = split_scenarios(spec_text)
    canvas_entities = _mentions(canvas_text, known_entities)
    if not canvas_entities or not scenarios:
        return {"scenarios": len(scenarios), "canvas_entities": canvas_entities,
                "off_scope": [], "checked": False}

    # Àncore = entità del Canvas + parole significative del nome della feature (>=4 caratteri,
    # per non promuovere articoli e preposizioni ad àncora).
    anchors = list(canvas_entities) + [w for w in _dev_type_words(feature_name) if len(w) >= 4]

    off_scope = []
    for s in scenarios:
        if not s["title"]:
            continue                      # senza titolo non c'è soggetto da giudicare
        if not _mentions(s["title"], anchors):
            off_scope.append({"title": s["title"],
                              "foreign_entities": _mentions(s["text"], known_entities)})
    return {"scenarios": len(scenarios), "canvas_entities": canvas_entities,
            "off_scope": off_scope, "checked": True}


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
