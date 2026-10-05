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

import re
import time
import uuid
from itertools import groupby

from core import intake, llm
from core.doc_generation import (
    GenerationError,
    _attach_generation_metadata,
    _now_iso,
    _validate_generated_markdown,
    normalize_generated_markdown,
)
from core.project_import import _validate_target

# Stesso purpose LLM della generazione S3 (documento markdown grounded, ruolo Canvas).
_BRIEF_PURPOSE = "canvas"

# Categoria docs/ suggerita per il brief (decisione del piano, S6): conoscenza
# informativa, mai normativa — la review S2 può comunque cambiarla all'approve.
BRIEF_CATEGORIA_SUGGERITA = "04_knowledge_informative"

# Tetti sul materiale di grounding serializzato nel prompt: un progetto reale può avere
# migliaia di simboli, il contesto utile di qwen3.5:9b (num_ctx 16384) no.
_MAX_SIMBOLI_NEL_PROMPT = 80
_MAX_ARCHI_NEL_PROMPT = 60

# …e il tetto che conta davvero è in CARATTERI, non in voci: la lunghezza di una riga
# dipende dai path del progetto, che nessuno controlla. Con soli tetti a voci il prompt
# di GD172_WSProtocollo usciva a ~48.000 caratteri (~13.700 token): dentro num_ctx 16384
# ci sta a stento, e ciò che sfora Ollama lo taglia in silenzio dall'INIZIO — cioè via le
# istruzioni e i conteggi per modulo, lasciando al modello una lista di simboli senza il
# compito. Un tetto in caratteri tiene il prompt sotto i ~7.000 token qualunque siano i
# path, e lascia il resto della finestra alla risposta.
_BUDGET_CHAR_MODULI = 1500
_BUDGET_CHAR_SIMBOLI = 7000
_BUDGET_CHAR_ENTRYPOINT = 4500
_BUDGET_CHAR_DIPENDENZE = 4500
_BUDGET_CHAR_IMPLEMENTS = 4500


class ProjectBriefError(RuntimeError):
    """Base degli errori del project brief."""


class BriefWithoutImportError(ProjectBriefError):
    """Nessun import progetto riuscito per il target: il brief non ha dati reali
    su cui poggiare (lo strato HTTP risponde 409)."""


# ---------------------------------------------------------------------------
# Precondizione: un import progetto "applied" per il target nel journal intake
#
# ATTENZIONE al livello di granularità: `target` è un BUCKET (backend/frontend/
# logicAgent), non un progetto. La semantica additiva di project_import fa convivere
# più progetti nello stesso bucket — code/backend/GD102_WSGDAProtocolloManager e
# code/backend/GD172_WSProtocollo stanno uno accanto all'altro, com'è giusto che sia.
# L'unità di cui ha senso scrivere un brief è il PROGETTO, non il bucket: un brief
# "di backend" con due progetti dentro descrive quello che capita per primo
# nell'ordinamento dei simboli, non quello appena importato.
# ---------------------------------------------------------------------------
def progetto_di(src: str) -> str:
    """Nome della cartella di destinazione sotto code/<target>/ per una sorgente
    importata: project_import copia sempre in code/<target>/<nome della cartella
    sorgente> (project_import.plan_project_import). Accetta entrambi i separatori,
    perché il journal registra il path della sorgente com'era sulla macchina che ha
    importato — su Windows con i backslash."""
    parti = [p for p in re.split(r"[\\/]+", str(src).strip()) if p]
    return parti[-1] if parti else ""


def _slug(nome: str) -> str:
    """Nome progetto → frammento di filename sicuro (stessa igiene dei nomi accettati
    da core.intake._sanitize_target_filename)."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", nome).strip("-").lower()


def applied_imports(target: str | None = None, base_dir=None, *, project=None) -> list[dict]:
    """Progetti importati con successo, uno per (target, progetto) — del singolo
    progetto vince l'import più recente —, in ordine di applicazione. Ogni voce:
    {"target", "progetto", "src", "applied_at", "import_id"}."""
    if target is not None:
        _validate_target(target)
    # Sola lettura (GET /api/intake/project/imports): non crea staging/ se non esiste
    # ancora — vedi core.intake.staging_paths_readonly.
    paths = intake.staging_paths_readonly(base_dir, project=project)
    per_progetto: dict[tuple[str, str], dict] = {}
    for rec in intake._journal_state(paths).values():
        if rec.get("type") != "project_import" or rec.get("status") != "applied":
            continue
        if target is not None and rec.get("target") != target:
            continue
        progetto = progetto_di(rec.get("src", ""))
        if not progetto:
            continue
        per_progetto[(rec.get("target", ""), progetto)] = {
            "target": rec.get("target", ""),
            "progetto": progetto,
            "src": rec.get("src", ""),
            "applied_at": rec.get("applied_at", ""),
            "import_id": rec.get("id"),
        }
    return sorted(per_progetto.values(), key=lambda v: (v["applied_at"], v["progetto"]))


def last_applied_import(target: str, base_dir=None,
                        progetto: str | None = None, *, project=None) -> dict | None:
    """Ultima entry di journal "project_import"/"applied" per `target` (None se non
    esiste), ristretta a `progetto` quando indicato. Riusa il folding "ultima riga per
    id vince" di core.intake._journal_state: il journal è il registro unico
    dell'intake, non se ne introduce un secondo."""
    _validate_target(target)
    paths = intake.ensure_staging_dirs(base_dir, project=project)
    latest: dict | None = None
    for rec in intake._journal_state(paths).values():
        if (rec.get("type") == "project_import" and rec.get("status") == "applied"
                and rec.get("target") == target):
            if progetto is not None and progetto_di(rec.get("src", "")) != progetto:
                continue
            latest = rec
    return latest


def require_applied_import(target: str, base_dir=None,
                           progetto: str | None = None, *, project=None) -> dict:
    """Entry dell'ultimo import riuscito per `target` (ristretta a `progetto`, se
    indicato), o BriefWithoutImportError."""
    rec = last_applied_import(target, base_dir=base_dir, progetto=progetto, project=project)
    if rec is None:
        if progetto is not None:
            disponibili = [v["progetto"] for v in applied_imports(target, base_dir=base_dir, project=project)]
            raise BriefWithoutImportError(
                f"nessun import progetto riuscito per {progetto!r} in code/{target}/ "
                f"(importati finora: {', '.join(disponibili) or 'nessuno'})"
            )
        raise BriefWithoutImportError(
            f"nessun import progetto riuscito per il target {target!r}: "
            f"esegui prima un'anteprima+applica dalla pagina /intake"
        )
    return rec


# ---------------------------------------------------------------------------
# Che cosa entra nel prompt quando i simboli sono molte volte il tetto.
#
# Un progetto reale ha migliaia di simboli e nel prompt ne stanno _MAX_SIMBOLI_NEL_PROMPT
# (il contesto di qwen3.5:9b, num_ctx 16384, è un vincolo duro). Il campione va quindi
# SCELTO, non troncato: prendere i primi in ordine di `id` — cioè di path — significa
# descrivere le cartelle che iniziano per A e ignorare il resto del progetto.
#
# Due mosse indipendenti:
#  (a) i CONTEGGI di tutto il progetto (per modulo e per natura) entrano nel prompt per
#      intero: sono poche righe e raccontano la forma del 100% dei simboli;
#  (b) i simboli ELENCATI sono un campione rappresentativo — un giro per file, così una
#      Reference.cs generata da 1650 simboli non si mangia il budget, e dentro ogni file
#      prima ciò che ha valore architetturale.
# ---------------------------------------------------------------------------

# Priorità per natura del simbolo: un brief architetturale vive di tipi ed entrypoint,
# non delle 2340 property di un progetto C#. Numero più basso = entra prima.
_RANGO_KIND = {
    "project": 0, "module": 0,
    "interface": 1, "endpoint": 1, "route": 1,
    "class": 2, "struct": 2, "component": 2, "service": 2,
    "enum": 3, "table": 3, "schema": 3, "type": 3,
    "function": 4, "method": 5,
    "property": 8, "field": 8, "variable": 8, "constant": 8,
}
_RANGO_KIND_DEFAULT = 6

# Moduli (cartelle di primo livello del progetto) elencati nel prompt: oltre questo
# numero l'elenco smette di essere una mappa e diventa rumore.
_MAX_MODULI_NEL_PROMPT = 15


def _rango_kind(kind: str) -> int:
    return _RANGO_KIND.get(str(kind).lower(), _RANGO_KIND_DEFAULT)


def _percorso_nel_progetto(file: str, target: str, progetto: str | None) -> str:
    """Path del file relativo alla radice del progetto (o del target, senza progetto).

    Nel prompt fa la differenza fra starci e non starci: `code/backend/GD172_WSProtocollo/`
    ripetuto su ogni riga sono ~27 caratteri × qualche centinaio di righe di puro
    preambolo, in un contesto (num_ctx 16384) che va speso in fatti. La radice è già
    dichiarata una volta nell'intestazione del prompt."""
    prefisso = f"{target}/{progetto}/" if progetto else f"{target}/"
    return file[len(prefisso):] if file.startswith(prefisso) else file


def _moduli(simboli: list[dict], target: str, progetto: str | None) -> list[dict]:
    """Conteggi per cartella di primo livello del progetto: quanti simboli, quanti file
    e di che natura. È l'unico pezzo di grounding che copre il progetto INTERO — il
    campione di simboli, per forza di cose, no."""
    per_modulo: dict[str, dict] = {}
    for sym in simboli:
        rel = _percorso_nel_progetto(sym.get("file", ""), target, progetto)
        nome = rel.split("/")[0] if "/" in rel else "(radice)"
        voce = per_modulo.setdefault(nome, {"nome": nome, "n_simboli": 0,
                                            "file": set(), "kinds": {}})
        voce["n_simboli"] += 1
        voce["file"].add(rel)
        kind = sym.get("kind", "")
        voce["kinds"][kind] = voce["kinds"].get(kind, 0) + 1
    moduli = [{"nome": v["nome"], "n_simboli": v["n_simboli"], "n_file": len(v["file"]),
               "kinds": dict(sorted(v["kinds"].items(), key=lambda kv: (-kv[1], kv[0])))}
              for v in per_modulo.values()]
    moduli.sort(key=lambda m: (-m["n_simboli"], m["nome"]))
    return moduli


def _blocco(righe: list[str], budget: int) -> tuple[str, int]:
    """(testo delle prime righe che stanno nel budget di caratteri, quante ne restano
    fuori). Le righe arrivano già in ordine di importanza: tagliare in fondo significa
    perdere il meno rilevante, mai una fetta a caso."""
    tenute: list[str] = []
    usati = 0
    for riga in righe:
        if tenute and usati + len(riga) + 1 > budget:
            break
        tenute.append(riga)
        usati += len(riga) + 1
    return "\n".join(tenute), len(righe) - len(tenute)


def _a_passo(seq: list[dict], q: int) -> list[dict]:
    """`q` elementi presi a passo costante lungo `seq`, primo e ultimo compresi. Serve
    quando una fetta omogenea è molto più lunga del budget: di 337 operazioni SOAP
    ordinate per nome, le prime 40 sono tutte quelle che iniziano per A — un campione
    a passo le attraversa tutte e restituisce la vera ampiezza dell'interfaccia."""
    n = len(seq)
    if q >= n:
        return list(seq)
    if q <= 1:
        return [seq[0]]
    indici = sorted({round(i * (n - 1) / (q - 1)) for i in range(q)})
    for i in range(n):        # il round può collassare due indici: si ricompleta
        if len(indici) >= q:
            break
        if i not in indici:
            indici.append(i)
    return [seq[i] for i in sorted(indici)[:q]]


def _preleva(gruppo: list[dict], q: int) -> list[dict]:
    """`q` elementi da un gruppo già in ordine di priorità, FASCIA per FASCIA: le fasce
    migliori per intero, e la prima che non ci sta campionata a passo. Così la quota di
    un file non si spende in property mentre restano fuori le sue classi, e una fascia
    troppo lunga viene comunque attraversata tutta invece che troncata in testa."""
    scelti: list[dict] = []
    for _rango, elementi in groupby(gruppo, key=lambda s: _rango_kind(s.get("kind", ""))):
        restano = q - len(scelti)
        if restano <= 0:
            break
        fascia = list(elementi)
        if len(fascia) <= restano:
            scelti.extend(fascia)
        else:
            scelti.extend(_a_passo(fascia, restano))
            break
    return scelti


def seleziona_simboli(simboli: list[dict], gradi: dict[str, int], limite: int) -> list[dict]:
    """Campione rappresentativo di al più `limite` simboli, in due mosse.

    (1) Le quote: un giro per file (round robin), così i 1650 simboli di una
        `Reference.cs` generata valgono quanto quelli di ogni altro file e non si
        mangiano il budget. Con più file che slot ogni file ne prende al più uno.
    (2) Il prelievo dentro il file: prima i simboli di maggior valore architetturale
        (`_RANGO_KIND`, poi grado nel sottografo, poi `id`), e a passo costante quando
        la fascia eccede la quota (vedi `_preleva`).

    Deterministico: stesso input → stesso campione."""
    if limite <= 0 or not simboli:
        return []

    def chiave(sym: dict) -> tuple:
        return (_rango_kind(sym.get("kind", "")), -gradi.get(sym["id"], 0), sym["id"])

    per_file: dict[str, list[dict]] = {}
    for sym in simboli:
        per_file.setdefault(sym.get("file", ""), []).append(sym)
    for gruppo in per_file.values():
        gruppo.sort(key=chiave)
    # I file entrano nel giro ordinati per il loro simbolo migliore: se gli slot
    # finiscono prima dei file, restano fuori i file che avevano meno da dire.
    ordine_file = sorted(per_file, key=lambda f: (chiave(per_file[f][0]), f))

    quote = dict.fromkeys(ordine_file, 0)
    assegnabili = min(limite, len(simboli))
    while assegnabili > 0:
        assegnati = 0
        for f in ordine_file:
            if quote[f] < len(per_file[f]):
                quote[f] += 1
                assegnabili -= 1
                assegnati += 1
                if assegnabili == 0:
                    break
        if assegnati == 0:
            break

    scelti: list[dict] = []
    for f, q in quote.items():
        if q:
            scelti.extend(_preleva(per_file[f], q))
    scelti.sort(key=lambda s: s["id"])   # nel prompt restano raggruppati per path
    return scelti


# ---------------------------------------------------------------------------
# Grounding deterministico: i fatti del grafo per il target (nessun LLM qui)
# ---------------------------------------------------------------------------
def collect_target_facts(graph, code_store: dict | None, target: str,
                         progetto: str | None = None, *, project=None) -> dict:
    """Estrae dal grafo i dati REALI del target: simboli (nodi type="code" con
    dev_type == target), entrypoint (kind "endpoint" o con route), archi DEPENDS_ON
    fra simboli del target e archi IMPLEMENTS simbolo→sezione/documento (la mappa
    simboli→spec chiesta dal piano). Deterministico e ordinato: stesso grafo →
    stesso prompt. code_store è accettato per simmetria con lo snapshot del server
    (i metadati che servono qui vivono già sugli attributi dei nodi).

    Con `progetto` restringe ai simboli di code/<target>/<progetto>/ (l'attributo
    `file` dei nodi di codice è il path relativo a code/, vedi
    code_index.collect_code_symbols). Senza, prende TUTTO il bucket: corretto solo
    finché il target ospita un progetto solo — vedi il commento sulla granularità
    più sopra. `n_simboli_target` riporta sempre il conteggio non ristretto, così
    chi chiama sa distinguere "target vuoto" da "progetto sbagliato"."""
    simboli: list[dict] = []
    entrypoint: list[dict] = []
    dipendenze: list[tuple[str, str]] = []
    implements: list[dict] = []
    kinds: dict[str, int] = {}
    n_simboli_target = 0

    if graph is None:
        return {"target": target, "progetto": progetto, "n_simboli": 0,
                "n_simboli_target": 0, "simboli": [], "entrypoint": [],
                "dipendenze": [], "implements": [], "kinds": {},
                "gradi": {}, "moduli": []}

    prefisso = f"{target}/{progetto}/" if progetto else None
    target_ids = set()
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("type") != "code" or attrs.get("dev_type") != target:
            continue
        n_simboli_target += 1
        if prefisso and not str(attrs.get("file", "")).startswith(prefisso):
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
    # Grado nel sottografo del progetto: quante dipendenze interne tocca un simbolo.
    # È il criterio con cui, a parità di natura, si sceglie chi entra nel prompt: un
    # tipo da cui dipendono in dieci racconta l'architettura più di uno isolato.
    gradi: dict[str, int] = {}
    for u, v in dipendenze:
        gradi[u] = gradi.get(u, 0) + 1
        gradi[v] = gradi.get(v, 0) + 1
    return {"target": target, "progetto": progetto, "n_simboli": len(simboli),
            "n_simboli_target": n_simboli_target, "simboli": simboli,
            "gradi": gradi, "moduli": _moduli(simboli, target, progetto),
            "entrypoint": entrypoint, "dipendenze": dipendenze,
            "implements": implements, "kinds": dict(sorted(kinds.items()))}


def build_brief_prompt(target: str, facts: dict) -> str:
    """Prompt deterministico per il brief: conteggi COMPLETI del progetto (moduli e
    nature dei simboli) + un CAMPIONE rappresentativo dei simboli entro i tetti di
    modulo, e il divieto esplicito di inventare simboli o file non elencati."""
    progetto = facts.get("progetto")
    gradi = facts.get("gradi") or {}

    def breve(percorso: str) -> str:
        return _percorso_nel_progetto(percorso, target, progetto)

    def sezione(righe: list[str], budget: int, totale: int, se_vuoto: str,
                coda: str) -> str:
        """Blocco entro budget + UNA coda che dichiara quante voci del totale reale non
        compaiono — sommando quelle non campionate e quelle tagliate dal budget. Due
        conteggi separati ("22 righe omesse" accanto a "altri 277") non aiutano nessuno."""
        if not righe:
            return se_vuoto
        testo, tagliate = _blocco(righe, budget)
        fuori = totale - len(righe) + tagliate
        return testo + (f"\n{coda.format(n=fuori)}" if fuori > 0 else "")

    moduli = (facts.get("moduli") or [])[:_MAX_MODULI_NEL_PROMPT]
    righe_moduli = sezione(
        [f"- `{m['nome']}`: {m['n_simboli']} simboli in {m['n_file']} file"
         + (f" ({', '.join(f'{k}: {n}' for k, n in list(m['kinds'].items())[:4])})"
            if m.get("kinds") else "")
         for m in moduli],
        _BUDGET_CHAR_MODULI, len(facts.get("moduli") or []),
        "(nessun modulo rilevato)", "… e altri {n} moduli minori")

    simboli = seleziona_simboli(facts["simboli"], gradi, _MAX_SIMBOLI_NEL_PROMPT)
    righe_simboli = sezione(
        [f"- {s['kind']} `{s['name']}` in {breve(s['file'])}" for s in simboli],
        _BUDGET_CHAR_SIMBOLI, facts["n_simboli"], "(nessuno)",
        "… e altri {n} simboli NON elencati: quelli qui sopra sono un CAMPIONE (uno per "
        "file, prima tipi ed entrypoint), non l'elenco completo. Per le parti che il "
        "campione non copre usa i conteggi per modulo qui sopra.")

    # Entrypoint: stesso campionamento dei simboli, altrimenti 337 operazioni SOAP
    # diventano "le prime che capitano in ordine alfabetico".
    entrypoint = seleziona_simboli(facts["entrypoint"], gradi, _MAX_ARCHI_NEL_PROMPT)
    righe_entry = sezione(
        [f"- {e['kind']} `{e['name']}` in {breve(e['file'])}"
         + (f" (route {e['route']})" if e.get("route") else "") for e in entrypoint],
        _BUDGET_CHAR_ENTRYPOINT, len(facts["entrypoint"]),
        "(nessun entrypoint rilevato)",
        "… e altri {n} entrypoint non elencati (campione a passo su tutto l'elenco)")

    # Le dipendenze che contano sono quelle fra i simboli più connessi: sono gli assi
    # portanti, non i primi archi in ordine alfabetico.
    dipendenze = sorted(facts["dipendenze"],
                        key=lambda uv: (-(gradi.get(uv[0], 0) + gradi.get(uv[1], 0)), uv))
    righe_deps = sezione(
        [f"- `{breve(u)}` → `{breve(v)}`" for u, v in dipendenze[:_MAX_ARCHI_NEL_PROMPT]],
        _BUDGET_CHAR_DIPENDENZE, len(dipendenze),
        "(nessuna dipendenza interna rilevata)",
        "… e altre {n} dipendenze meno connesse, non elencate")

    # IMPLEMENTS: prima i legami più forti, che sono quelli su cui la mappa regge.
    implements = sorted(facts["implements"],
                        key=lambda e: (-(e.get("weight") or 0), e["symbol"], e["spec"]))
    righe_impl = sezione(
        [f"- `{breve(e['symbol'])}` IMPLEMENTS `{e['spec']}`"
         + (f" (peso {e['weight']})" if e.get("weight") is not None else "")
         for e in implements[:_MAX_ARCHI_NEL_PROMPT]],
        _BUDGET_CHAR_IMPLEMENTS, len(implements),
        "(nessun arco IMPLEMENTS verso le spec: i code-link possono richiedere un full rebuild)",
        "… e altri {n} archi IMPLEMENTS più deboli, non elencati")

    conteggi = ", ".join(f"{k}: {n}" for k, n in facts["kinds"].items()) or "nessuno"
    progetto = facts.get("progetto")
    percorso = f"code/{target}/{progetto}" if progetto else f"code/{target}"
    # Il nome del progetto va detto al modello, non solo usato per filtrare: il bucket
    # può ospitarne altri, e il brief deve parlare di QUESTO.
    vincolo_progetto = (
        f"\nIl brief riguarda ESCLUSIVAMENTE il progetto `{progetto}`: i dati qui sotto sono "
        f"già ristretti a {percorso}/. Se conosci altri progetti dello stesso target, "
        f"ignorali — non fanno parte di questo documento.\n" if progetto else "")

    return f"""Sei un Software Architect. Scrivi UN documento Markdown di sintesi architetturale
("project brief") del progetto importato in {percorso}, destinato a docs/{BRIEF_CATEGORIA_SUGGERITA}.
{vincolo_progetto}
DATI REALI DAL GRAFO DELLA CONOSCENZA (unica fonte ammessa — NON inventare simboli,
file, route o dipendenze che non compaiono qui sotto). I path sono relativi a
{percorso}/ e i simboli sono citati come `path/del/file.ext::Nome`:

Moduli del progetto (conteggi COMPLETI, coprono tutti i {facts['n_simboli']} simboli):
{righe_moduli}

Simboli ({facts['n_simboli']} totali — {conteggi}):
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
- In `## Componenti` parti dai MODULI e dai loro conteggi (coprono l'intero progetto),
  e usa i simboli elencati come esempi concreti di ciascun modulo. Non presentare il
  campione come se fosse l'elenco completo dei simboli, e non dedurre che un modulo non
  esista solo perché nessuno dei suoi simboli compare nel campione.
- Nessun testo fuori dal documento.
"""


# ---------------------------------------------------------------------------
# generate_project_brief: il job completo (sincrono, pensato per il thread del
# GenerationManager di core/doc_generation.py — mai sull'event loop).
# ---------------------------------------------------------------------------
def _journal_discarded_brief(base_dir, *, target: str, progetto: str, motivo: str, project=None) -> None:
    """Traccia nel journal un brief SCARTATO in validazione (mai entrato in staging):
    stato 'discarded', ignorato da list_staged/approve/reject."""
    paths = intake.ensure_staging_dirs(base_dir, project=project)
    intake._append_journal(paths, {
        "id": uuid.uuid4().hex[:12],
        "status": "discarded",
        "source": "brief",
        "target": target,
        "progetto": progetto,
        "motivo": motivo,
        "discarded_at": _now_iso(),
    })


def _avviso_senza_simboli(facts: dict, target: str, progetto: str) -> str:
    """Perché il grounding è vuoto. Distingue i due casi, che chiedono rimedi diversi:
    l'intero bucket senza simboli (reindex del codice indietro) e il solo progetto senza
    simboli mentre il target ne ha altri (progetto sbagliato, o import di file di cui
    nessun estrattore ricava simboli)."""
    if facts.get("n_simboli_target"):
        return (f"nessun simbolo nel grafo sotto code/{target}/{progetto}/, ma il target "
                f"{target!r} ne ha {facts['n_simboli_target']} di altri progetti: brief non "
                f"generato — verifica il progetto scelto, o rilancia il reindex del codice "
                f"se l'import è appena avvenuto")
    return (f"nessun simbolo nel grafo per il target {target!r}: brief non generato — "
            f"il reindex del codice potrebbe non essere ancora passato (serve un "
            f"reindex/full rebuild)")


def generate_project_brief(target: str, *, progetto: str | None = None, graph=None,
                           code_store: dict | None = None,
                           base_dir=None, generate=None, project=None) -> dict:
    """Genera il project brief di code/<target>/<progetto> grounded sul grafo e lo mette
    in STAGING (source "brief"), approvabile SOLO dal ciclo di review S2 — nessuna
    scrittura in docs/. Precondizione: import progetto riuscito per quel target/progetto
    (BriefWithoutImportError altrimenti). Grafo senza simboli → esito con `avviso`, senza
    chiamare l'LLM (grounded significa: niente dati, niente brief inventato).

    `progetto` omesso significa "l'ULTIMO progetto importato in quel target": è ciò che
    l'utente ha appena fatto, ed è l'unica scelta difendibile in un bucket che può
    ospitarne più d'uno. NON significa "tutto il target": un brief che mescola due
    progetti descrive quello che capita per primo nell'ordinamento dei simboli.

    Restituisce {"target", "progetto", "generati", "scartati", "n_generati",
    "n_scartati", "avviso" | None, "latency": {"generation_ms", "total_ms"}}. Solleva
    GenerationError se la chiamata LLM fallisce (il GenerationManager la registra come
    job "failed")."""
    total_start = time.time()
    import_rec = require_applied_import(target, base_dir=base_dir, progetto=progetto, project=project)
    progetto = progetto or progetto_di(import_rec.get("src", ""))
    facts = collect_target_facts(graph, code_store, target, progetto=progetto)

    base = {"target": target, "progetto": progetto, "generati": [], "scartati": [],
            "n_generati": 0, "n_scartati": 0, "avviso": None}
    if facts["n_simboli"] == 0:
        return {**base,
                "avviso": _avviso_senza_simboli(facts, target, progetto),
                "latency": {"generation_ms": 0.0,
                            "total_ms": round((time.time() - total_start) * 1000, 2)}}

    prompt = build_brief_prompt(target, facts)
    if project is not None:
        prompt = f"Project ID: {project.id}\n" + prompt
    generate_fn = generate or (lambda p: llm.generate(p, purpose=_BRIEF_PURPOSE))

    generation_start = time.time()
    try:
        markdown = normalize_generated_markdown(generate_fn(prompt))
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
        _journal_discarded_brief(base_dir, target=target, progetto=progetto, motivo=str(exc), project=project)
        return {**base, "scartati": [{"motivo": str(exc)}], "n_scartati": 1,
                "latency": latency}

    # Il nome del file dice DI CHE COSA è il brief: con più progetti nello stesso
    # target, "brief-backend-…" da solo non distingue niente.
    filename = f"brief-{_slug(progetto) or target}-{uuid.uuid4().hex[:8]}.md"
    try:
        record = intake.stage_document(filename, markdown.encode("utf-8"),
                                       base_dir=base_dir, source="brief", project=project)
    except intake.IntakeError as exc:
        motivo = f"staging fallito: {exc}"
        _journal_discarded_brief(base_dir, target=target, progetto=progetto, motivo=motivo, project=project)
        return {**base, "scartati": [{"motivo": motivo}], "n_scartati": 1,
                "latency": latency}

    record = _attach_generation_metadata(base_dir, record, {
        "target": target,
        "progetto": progetto,
        "import_id": import_rec.get("id"),
        "categoria_suggerita": BRIEF_CATEGORIA_SUGGERITA,
        "modello": modello,
        "n_simboli_grounding": facts["n_simboli"],
        "latenze": {"generation_ms": latency_generation_ms},
    }, project=project)
    latency["total_ms"] = round((time.time() - total_start) * 1000, 2)
    return {**base, "generati": [record], "n_generati": 1, "latency": latency}
