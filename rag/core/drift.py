"""Check drift affidabile (pipeline, step 4): logica pura usata da
core/indexing.check_drift, che resta l'orchestratore (lettura file, chiamate LLM).

Perché esiste: il check storico passava all'LLM il solo Canvas e ~40.000 caratteri di
codice troncati alla cieca, e ne pubblicava il testo libero. Sul caso reale BE1 questo
produceva falsi positivi ricorrenti: requisiti imposti dalla Spec segnalati come drift,
librerie "mancanti" che stavano nei file tagliati via, verdetti NO con motivazioni che
si auto-dichiaravano conformi. Qui:
· il codice è diviso in LOTTI entro la finestra di contesto (niente troncamento cieco) e
  ogni lotto dichiara quali file del progetto l'LLM NON sta vedendo;
· l'LLM risponde in JSON, un rilievo per voce, con citazione testuale del codice;
· Python verifica ogni citazione (e i termini delle "mancanze") sui file reali e
  declassa ciò che non è verificabile;
· ogni drift sopravvissuto passa da un riesame mirato (domanda stretta, contesto stretto);
· il verdetto è CALCOLATO dai rilievi sopravvissuti, non dichiarato dall'LLM.
"""
import json
import re

from code_index import referenced_entity_tokens

# Categorie ammesse per un rilievo: solo "drift" influisce sul verdetto.
CATEGORIES = ("drift", "punto_aperto", "fuori_ambito", "conforme")
SEVERITIES = ("alta", "media", "bassa")

# Verdetti: il primo è la stessa frase del check storico (letta anche dalla UI).
VERDICT_OK = "✅ NESSUN DRIFT RILEVATO. Il codice è conforme."
VERDICT_DRIFT = "⚠️ DRIFT RILEVATO"
VERDICT_INCOMPLETE = "⚠️ VERIFICA INCOMPLETA"
VERDICT_OPEN = "⚠️ PUNTI APERTI DA DECIDERE"

_TEST_DIRS = {"test", "tests", "__tests__"}
_TEST_NAME_RE = re.compile(r"(tests?\.\w+$|\.(test|spec)\.\w+$|^test_)")
# File generati dagli strumenti (migrazioni EF, designer): non sono codice scritto
# dall'agente e consumerebbero budget di contesto senza dire nulla sul drift.
_GENERATED_NAME_RE = re.compile(r"(\.designer\.cs|modelsnapshot\.cs|\.g\.cs|\.generated\.\w+)$")


def is_test_path(rel_parts: tuple[str, ...]) -> bool:
    return bool(_TEST_DIRS & {p.lower() for p in rel_parts[:-1]}) \
        or bool(_TEST_NAME_RE.search(rel_parts[-1].lower()))


def is_generated_path(name: str) -> bool:
    return bool(_GENERATED_NAME_RE.search(name.lower()))


def _split_text(text: str, limit: int) -> list[str]:
    """Divide un file in parti di al più `limit` caratteri, a fine riga quando possibile."""
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # riga singola più lunga del limite: taglio netto
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            parts.append(current)
            current = ""
        current += line
    if current or not parts:
        parts.append(current)
    return parts


def make_batches(files: list[tuple[str, str]], budget: int, max_batches: int
                 ) -> tuple[list[list[tuple[str, str, str]]], list[str]]:
    """Distribuisce i file (label, testo), nell'ordine dato, in lotti da al più `budget`
    caratteri. Un file più grande del lotto è diviso in parti ("parte i/n"), mai troncato.
    Restituisce (lotti di (label, intestazione, testo), label dei file rimasti fuori
    perché eccedono `max_batches`)."""
    header_room = 120
    pieces: list[tuple[str, str, str]] = []
    for label, text in files:
        chunks = _split_text(text, max(budget - header_room, 1))
        for i, chunk in enumerate(chunks, 1):
            suffix = f" (parte {i}/{len(chunks)})" if len(chunks) > 1 else ""
            pieces.append((label, f"--- FILE: {label}{suffix} ---", chunk))

    batches: list[list[tuple[str, str, str]]] = []
    size = budget  # forza l'apertura del primo lotto
    left_out: list[str] = []
    for label, header, chunk in pieces:
        cost = len(header) + len(chunk) + 2
        if size + cost > budget:
            if len(batches) >= max_batches:
                if label not in left_out:
                    left_out.append(label)
                continue
            batches.append([])
            size = 0
        batches[-1].append((label, header, chunk))
        size += cost
    return batches, left_out


def render_batch(batch: list[tuple[str, str, str]]) -> str:
    return "".join(f"\n{header}\n{chunk}\n" for _label, header, chunk in batch)


# ---------------------------------------------------------------- pre-check --

_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_TECH_SPLIT_RE = re.compile(r"\s+o\s+|\s+e\s+|/|\+|,|\s+oppure\s+", re.IGNORECASE)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def manifest_dependencies(symbols: list[dict]) -> dict[str, str]:
    """Dipendenze dichiarate nei manifest (csproj, pom, gradle, packages.config,
    package.json) dai simboli del code index: {dipendenza: file manifest}."""
    deps: dict[str, str] = {}
    for sym in symbols:
        if sym.get("kind") != "project":
            continue
        names = list(sym.get("deps") or []) + list((sym.get("attrs") or {}).get("dependencies") or [])
        for name in names:
            deps.setdefault(name, sym.get("file", ""))
    return deps


def match_canvas_technologies(canvas: str, deps: dict[str, str]) -> list[tuple[str, str, str]]:
    """Tecnologie in grassetto nel Canvas (es. **FluentValidation**, **MinIO o Azure Blob
    Storage**) ritrovate tra le dipendenze dei manifest: [(tecnologia, dipendenza, file)].
    Restituisce solo le corrispondenze trovate: un termine assente (es. "Modular
    Monolith") non è per forza una libreria, quindi non diventa un fatto negativo."""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for bold in _BOLD_RE.findall(canvas):
        for term in _TECH_SPLIT_RE.split(bold):
            key = _compact(term)
            # Sotto i 5 caratteri i termini sono parole comuni (**Test**), non librerie.
            if len(key) < 5 or key in seen:
                continue
            for dep, manifest in deps.items():
                # Confronto per segmenti del nome (Microsoft.EntityFrameworkCore, @scope/pkg):
                # una sottostringa qualunque farebbe combaciare "Test" con "...Mvc.Testing".
                segments = {_compact(seg) for seg in re.split(r"[./@]", dep)}
                if key in segments or _compact(dep).startswith(key):
                    seen.add(key)
                    found.append((term.strip(), dep, manifest))
                    break
    return found


def satisfied_alternatives(canvas: str, matches: list[tuple[str, str, str]]) -> dict[str, str]:
    """Alternative tecniche in grassetto (es. **MinIO o Azure Blob Storage**) già soddisfatte
    da una dipendenza trovata: {termine alternativo compattato: spiegazione}."""
    found = {_compact(term): f"{term} ({dep} in {manifest})" for term, dep, manifest in matches}
    out: dict[str, str] = {}
    for bold in _BOLD_RE.findall(canvas):
        keys = [_compact(t) for t in _TECH_SPLIT_RE.split(bold) if len(_compact(t)) >= 5]
        hit = next((found[k] for k in keys if k in found), None)
        if hit and len(keys) > 1:
            out.update({k: hit for k in keys if k not in found})
    return out


def discard_satisfied_alternatives(findings: list[dict], alternatives: dict[str, str]) -> None:
    """Scarta le mancanze di un'alternativa tecnica quando un'altra è già implementata (su
    BE1: "manca Azure Blob Storage" con Minio nel .csproj e il Canvas "MinIO o Azure")."""
    for f in findings:
        if f["scartato"] or not f["termini"]:
            continue
        for term in f["termini"]:
            key = _compact(term)
            alt = next((v for k, v in alternatives.items() if len(key) >= 5 and (key in k or k in key)), None)
            if alt:
                f["scartato"] = f"alternativa tecnica già soddisfatta da {alt}"
                break


def format_prechecks(deps: dict[str, str], matches: list[tuple[str, str, str]]) -> str:
    if not deps:
        return "(nessun manifest di dipendenze trovato)"
    lines = [f"- {term}: presente come `{dep}` in {manifest}" for term, dep, manifest in matches]
    by_file: dict[str, list[str]] = {}
    for dep, manifest in deps.items():
        by_file.setdefault(manifest, []).append(dep)
    lines.append("Elenco completo delle dipendenze dichiarate:")
    lines += [f"- {manifest}: {', '.join(sorted(names))}" for manifest, names in sorted(by_file.items())]
    return "\n".join(lines)


def symbol_summary(symbols: list[dict], max_chars: int) -> str:
    """Indice compatto file -> simboli (classi, metodi, record...) per il controllo di
    copertura: permette all'LLM di "vedere" tutto il progetto senza il codice grezzo."""
    by_file: dict[str, list[str]] = {}
    for sym in symbols:
        if sym.get("kind") in ("property", "config", "connection-string"):
            continue
        by_file.setdefault(sym.get("file", ""), []).append(f"{sym.get('kind')} {sym.get('name')}")
    lines, size = [], 0
    for file, names in sorted(by_file.items()):
        line = f"- {file}: {', '.join(names[:30])}{' …' if len(names) > 30 else ''}"
        if size + len(line) > max_chars:
            lines.append("- … [indice simboli troncato per la finestra di contesto] …")
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(lines)


# ------------------------------------------------------------------ prompt --

_RULES = """REGOLE DI GIUDIZIO (vincolanti):
1. FONTI NORMATIVE E PRECEDENZA: la SPEC (scenari S01, S02… e punti aperti) prevale sul
   CANVAS. Un comportamento richiesto da uno scenario della Spec NON è drift anche se il
   Canvas non lo menziona o sembra suggerire altro.
2. PUNTI APERTI E ALTERNATIVE: ciò che la Spec elenca come punto aperto NON è un drift
   (categoria "punto_aperto"). Le alternative TECNICHE del Canvas ("MinIO o Azure",
   "Entità o riferimento", "implicito o diretto", "es.") sono soddisfatte da una sola di
   esse. Le funzionalità offerte all'utente elencate insieme (es. "formati CSV o Excel")
   vanno invece implementate tutte: se ne manca una è "drift", oppure "punto_aperto" se la
   Spec la elenca tra i punti aperti.
3. EVIDENZA: ogni rilievo deve citare LETTERALMENTE (copia esatta, una o poche righe) il
   testo del codice su cui si basa, e il requisito del Canvas/Spec che viola. Un rilievo
   senza citazione esatta verrà scartato automaticamente.
4. NON elencare cose conformi come rilievi. Se verifichi che un requisito è rispettato,
   NON inserirlo (oppure usa categoria "conforme").
5. Tipo di rilievo: "contraddizione" (il codice citato fa qualcosa di diverso da ciò che il
   contratto prescrive) oppure "mancanza" (qualcosa di richiesto non c'è). Per ogni
   "mancanza" indica in "termini" 1-4 parole SPECIFICHE che comparirebbero nel codice se
   fosse implementata (nomi di classi, metodi, codici di errore, librerie, estensioni): il
   sistema le cerca in TUTTI i file del progetto e scarta il rilievo se le trova. Ciò che
   non vedi in un file può stare in un altro.
6. Categorie: "drift" (il codice contraddice o non implementa un requisito vincolante),
   "fuori_ambito" (il codice fa cose non previste, senza violare requisiti),
   "punto_aperto" (requisito ambiguo, alternativo o non coperto dalla Spec).
   Gravità: "alta", "media" o "bassa".
7. Al massimo 8 rilievi, i più gravi. "descrizione" al massimo 2 frasi; nessun
   ragionamento fuori dal JSON."""


def build_batch_prompt(canvas: str, spec: str, prechecks: str, code: str,
                       index: int, total: int, other_files: list[str]) -> str:
    others = "\n".join(f"- {f}" for f in other_files) or "(nessuno)"
    return f"""Sei un Revisore del Codice esperto. Verifica il "Drift" (disallineamento) tra il
contratto (REASONS Canvas + Spec) e il codice. Stai esaminando il LOTTO {index} di {total}.

--- CONTRATTO: CANVAS ---
{canvas}

--- CONTRATTO: SPEC (prevale sul Canvas) ---
{spec or "(nessuna spec.md per questa feature)"}

--- FATTI VERIFICATI DAL SISTEMA (dipendenze nei manifest, non contestabili) ---
{prechecks}

--- FILE DEL PROGETTO CHE IN QUESTO LOTTO NON VEDI (esistono: non trarre conclusioni sul loro contenuto) ---
{others}

--- CODICE DEL LOTTO {index}/{total} ---
{code}

{_RULES}

Segnala SOLO problemi dimostrabili con il codice di QUESTO lotto.
Rispondi SOLO con JSON valido, senza testo attorno, in questo formato:
{{"rilievi": [{{"categoria": "drift", "tipo": "contraddizione", "gravita": "media",
"sezione": "Canvas §7 Safeguards oppure Spec S05", "requisito": "frase copiata dal Canvas o dalla Spec",
"file": "percorso del file", "evidenza": "riga di codice copiata esattamente",
"termini": [], "descrizione": "perché è un problema"}}]}}
Se non ci sono problemi: {{"rilievi": []}}
"""


def build_coverage_prompt(canvas: str, spec: str, prechecks: str, summary: str, left_out: list[str]) -> str:
    missing = "\n".join(f"- {f}" for f in left_out) or "(nessuno: tutti i file sono stati analizzati a lotti)"
    return f"""Sei un Revisore del Codice esperto. Controllo di COPERTURA: individua i requisiti
del contratto (Canvas + Spec) che NON hanno alcuna implementazione nel progetto.

--- CONTRATTO: CANVAS ---
{canvas}

--- CONTRATTO: SPEC (prevale sul Canvas) ---
{spec or "(nessuna spec.md per questa feature)"}

--- FATTI VERIFICATI DAL SISTEMA (dipendenze nei manifest, non contestabili) ---
{prechecks}

--- INDICE DEI SIMBOLI DI TUTTO IL PROGETTO (file: tipo nome) ---
{summary or "(indice simboli non disponibile)"}

--- FILE NON ANALIZZATI NEI LOTTI ---
{missing}

{_RULES}

Qui NON vedi il codice riga per riga: segnala solo requisiti vincolanti di cui l'indice non
mostra nessuna traccia (es. un formato di export, un endpoint, un'entità, una libreria).
Per ogni rilievo indica in "termini" 1-4 parole SPECIFICHE da cercare nel codice (nomi di
classi, metodi, librerie, estensioni di file): il sistema le cercherà in tutti i file e
scarterà il rilievo se le trova.
Rispondi SOLO con JSON valido, senza testo attorno, in questo formato:
{{"rilievi": [{{"categoria": "drift", "gravita": "media", "sezione": "Canvas §1 Requirements",
"tipo": "mancanza", "requisito": "frase copiata dal Canvas o dalla Spec",
"termini": ["Xlsx", "Excel"], "descrizione": "cosa manca"}}]}}
Se non manca nulla: {{"rilievi": []}}
"""


# ------------------------------------------- riesame mirato, parsing e verifica --

def _json_object(text: str):
    """Il primo oggetto JSON della risposta, tollerando fence e testo attorno (None se assente)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def code_context(text: str, evidence: str, max_chars: int, radius: int = 60) -> str:
    """Le righe attorno alla citazione (tutto il file se ci sta nel budget)."""
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    first = next((norm(row) for row in str(evidence).splitlines() if len(norm(row)) >= 3), "")
    first = re.split(r"\.\.\.|…", first)[0].strip()
    at = next((i for i, row in enumerate(lines) if first and first in norm(row)), 0)
    return "\n".join(lines[max(at - radius, 0):at + radius])[:max_chars]


def requirement_context(requirement: str, canvas: str, spec: str, max_chars: int = 2500) -> str:
    """Il blocco del contratto da cui viene il requisito citato: lo scenario Gherkin intero
    o la sezione del Canvas. Su BE1 il frammento "non genera alcuna riga nell'AUDIT_LOG
    relativa alla scrittura fallita" (S02, creazione senza locandina), letto da solo,
    veniva applicato all'export."""
    req = norm(requirement)
    words = set(re.findall(r"\w{4,}", req))
    best, best_score = "", 0.0
    for block in re.split(r"\n\s*\n|```", canvas + "\n\n" + spec):
        block_norm = norm(block)
        if not block_norm:
            continue
        score = 2.0 if req and req in block_norm else (
            sum(w in block_norm for w in words) / len(words) if words else 0.0)
        if score > best_score:
            best, best_score = block.strip(), score
    return best[:max_chars] if best_score >= 0.5 else requirement


_GHERKIN_WORDS = {"SCENARIO", "GIVEN", "WHEN", "THEN", "AND", "BUT"}


_CODE_IDENT_RE = re.compile(r"\b[A-Za-z_]\w*[a-z][A-Z]\w*\b")


def related_code(requirement_block: str, sources: dict[str, str], max_chars: int,
                 finding_text: str = "", radius: int = 10) -> str:
    """Le righe di codice (test esclusi dal chiamante) che citano gli identificativi del
    contratto presenti nel requisito (codici entità/errore/stato: BUDGET_ANNUO, BOZZA…) o
    gli identificatori di codice nominati dal rilievo (MaxCapacity…), le più dense per prime.
    Su BE1 il riesame di "manca il controllo della capienza" non vedeva il validator che lo
    esegue, perché il rilievo cercava un nome inventato."""
    ids = (referenced_entity_tokens(requirement_block) - _GHERKIN_WORDS) \
        | set(_CODE_IDENT_RE.findall(finding_text))
    if not ids:
        return ""
    hits = []
    for label, text in sources.items():
        lines = text.splitlines()
        for i, row in enumerate(lines):
            score = sum(tok in row for tok in ids)
            if score:
                hits.append((-score, label, i, lines))
    out, size, taken = [], 0, set()
    for _neg, label, i, lines in sorted(hits, key=lambda h: h[:3]):
        if any(lbl == label and abs(i - j) <= radius for lbl, j in taken):
            continue
        block = f"--- {label} (riga {i + 1}) ---\n" + "\n".join(lines[max(i - radius, 0):i + radius + 1])
        if size + len(block) > max_chars:
            break
        taken.add((label, i))
        out.append(block)
        size += len(block)
    return "\n".join(out)


def build_recheck_prompt(canvas: str, spec: str, finding: dict, context: str,
                         summary: str = "", related: str = "") -> str:
    """Riesame mirato di UN rilievo: domanda stretta e codice attorno alla citazione. Il
    modello locale sbaglia molto meno su una domanda sì/no che nella revisione ampia (su
    BE1 citava righe reali traendone conclusioni opposte a ciò che mostravano). Per le
    "mancanze" riceve anche l'indice dei simboli: su BE1 "Publish() non valida la
    capienza" ignorava PublishEventValidator in un altro file."""
    index = ""
    if (finding["tipo"] == "mancanza" or finding["termini"]) and (summary or related):
        index = f"""
--- INDICE DEI SIMBOLI DI TUTTO IL PROGETTO (la mancanza può essere coperta altrove) ---
{summary or "(non disponibile)"}

--- CODICE DEL PROGETTO CHE CITA GLI IDENTIFICATIVI DEL REQUISITO ---
{related or "(nessuna riga cita gli identificativi del requisito)"}

Se l'indice o il codice qui sopra mostrano dove il requisito è implementato (validator,
handler, servizio, anche con nomi diversi da quelli ipotizzati), l'esito è "rispettato".
"""
    if finding["file"]:
        code = f"""--- CODICE ({finding['file']}, porzione attorno alla riga citata) ---
{context}"""
    else:
        # Rilievo del controllo di copertura: nessuna riga citata, si giudica l'assenza.
        code = "--- CODICE --- (rilievo di copertura: nessuna riga citata, vedi indice e codice sotto)"
    if finding["tipo"] == "mancanza" or finding["termini"] or not finding["file"]:
        # Una mancanza si giudica sull'intero progetto, non sul metodo citato: su BE1
        # "Publish() non valida la capienza" veniva confermato con il validator sotto gli occhi.
        decision = """Esito "violato" SOLO se il requisito non è implementato in NESSUN punto del progetto:
né nel codice citato, né nell'indice dei simboli, né nel codice correlato (con qualunque nome).
Esito "rispettato" se è implementato altrove (es. un validator o un handler diverso dal metodo
citato), se il Canvas lo formula come alternativa tecnica già soddisfatta ("X o Y",
"implicito o diretto", "Entità o riferimento") o se il problema è ipotetico.
Esito "punto_aperto" se non è implementato ma la Spec lo elenca tra i punti aperti."""
    else:
        decision = """Esito "violato" SOLO se il codice mostrato contraddice chiaramente il requisito.
Esito "rispettato" se il requisito è rispettato, se la Spec consente quel comportamento, se
il requisito riguarda un'operazione o uno scenario diverso da quello del codice citato, se
il problema è ipotetico ("potrebbe", "se non…"), se dipende da codice che non vedi, se
riguarda solo stile/messaggi non prescritti, o se il collega stesso lo ammette accettabile.
Esito "punto_aperto" se il requisito non è soddisfatto ma la Spec lo elenca tra i punti aperti."""
    return f"""Sei un revisore scettico. Un collega sostiene che il codice viola il contratto.
Verifica SOLO questa affermazione.

--- CONTRATTO: CANVAS ---
{canvas}

--- CONTRATTO: SPEC (prevale sul Canvas) ---
{spec or "(nessuna spec.md per questa feature)"}

--- AFFERMAZIONE DA VERIFICARE ---
Requisito citato: {finding['requisito']}
Contesto completo del requisito nel contratto:
{requirement_context(finding['requisito'], canvas, spec)}
Problema dichiarato: {finding['descrizione']}
Riga citata: {finding['evidenza']}

{code}
{index}
{decision}
Prima di decidere, scrivi cosa richiede ESATTAMENTE il contratto (THEN/AND dello scenario o
frase del Canvas) e cosa fa ESATTAMENTE il codice mostrato, nell'ordine in cui lo esegue.
Rispondi SOLO con JSON, campi in quest'ordine:
{{"richiesto": "una frase", "fatto_dal_codice": "una frase", "esito": "violato oppure rispettato oppure punto_aperto", "motivo": "una frase"}}
"""


RECHECK_OUTCOMES = ("violato", "rispettato", "punto_aperto")


def parse_recheck(text: str) -> tuple[str | None, str]:
    """(esito, motivo) del riesame; esito None se la risposta non è interpretabile.
    Accetta anche il vecchio campo booleano "violato"."""
    data = _json_object(text)
    if not isinstance(data, dict):
        data = _lenient_fields(text or "")
        m = re.search(r'"violato"\s*:\s*(true|false)', text or "")
        if m:
            data["violato"] = m.group(1) == "true"
    outcome = norm(data.get("esito")).replace(" ", "_")
    if outcome not in RECHECK_OUTCOMES and isinstance(data.get("violato"), bool):
        outcome = "violato" if data["violato"] else "rispettato"
    if outcome not in RECHECK_OUTCOMES:
        return None, ""
    reason = str(data.get("motivo") or "").strip()
    # "Rispettato perché è un punto aperto" è un punto aperto: su BE1 il modello motivava
    # così l'export Excel mancante, che spariva tra gli scartati.
    if outcome == "rispettato" and re.search(r"punt[oi][\s_]apert", reason, re.IGNORECASE):
        outcome = "punto_aperto"
    return outcome, reason


_KEYS = ("categoria", "tipo", "gravita", "sezione", "requisito", "file", "evidenza",
         "termini", "descrizione", "motivo", "richiesto", "fatto_dal_codice", "violato", "esito")
_KEY_ALT = "|".join(_KEYS)


def _lenient_fields(chunk: str) -> dict:
    """Campi di UN oggetto JSON malformato (virgolette non escape nel codice citato,
    risposta troncata): ogni valore stringa arriva fino alla chiave nota successiva."""
    out: dict = {}
    for m in re.finditer(rf'"({_KEY_ALT})"\s*:\s*', chunk):
        key, rest = m.group(1), chunk[m.end():]
        if rest.startswith("["):
            items = rest[1:rest.find("]")] if "]" in rest else rest[1:]
            out[key] = re.findall(r'"([^"]+)"', items)
        elif rest.startswith('"'):
            end = re.search(rf'"\s*(,\s*"(?:{_KEY_ALT})"\s*:|}}\s*(?:,|\]|`|\Z))', rest[1:])
            # Senza chiave successiva (ultimo campo, oggetto troncato) si tolgono le chiusure.
            value = rest[1:end.start() + 1] if end else re.sub(r'["\s,{}\[\]]+$', "", rest[1:])
            out[key] = value.replace('\\"', '"').replace("\\n", "\n")
    return out


def parse_findings(text: str) -> list[dict] | None:
    """I rilievi dal JSON dell'LLM, tollerando fence e testo attorno. Se il JSON è
    malformato (su BE1: virgolette del codice citato non escape, risposte troncate) i
    rilievi si recuperano uno per uno. None se non c'è nulla di interpretabile (il
    chiamante la tratta come verifica incompleta, non come ok)."""
    text = text or ""
    starts = [m.start() for m in re.finditer(r'"categoria"\s*:', text)]
    data = _json_object(text)
    if isinstance(data, dict) and isinstance(data.get("rilievi"), list):
        strict = [f for f in data["rilievi"] if isinstance(f, dict)]
        # JSON valido ma con rilievi concatenati come chiavi ripetute di un solo oggetto:
        # json.loads terrebbe solo l'ultimo, perdendo gli altri in silenzio.
        if len(strict) >= len(starts):
            return strict
    elif re.search(r'"rilievi"\s*:\s*\[\s*\]', text):
        return []
    chunks = [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]
    findings = [_lenient_fields(c) for c in chunks]
    findings = [f for f in findings if f.get("requisito") or f.get("evidenza")]
    return findings or None


def norm(text: str) -> str:
    text = re.sub(r"[`*\"“”]", "", str(text or ""))
    return re.sub(r"\s+", " ", text).strip().lower()


def _category(value) -> str:
    key = norm(value).replace(" ", "_").replace("-", "_")
    return key if key in CATEGORIES else "drift"  # sconosciuta: prudenza, resta un drift


def quote_in(quote: str, text_norm: str) -> bool:
    """La citazione è nel testo? Tollera spazi diversi, omissioni marcate con '...' e righe
    intermedie saltate: ogni riga citata deve comparire nel file."""
    lines = [norm(row) for row in str(quote or "").splitlines()]
    fragments = [f.strip() for row in lines for f in re.split(r"\.\.\.|…", row)]
    fragments = [f for f in fragments if len(f) >= 3]
    return bool(fragments) and all(f in text_norm for f in fragments)


def requirement_in(requirement: str, contract_norm: str) -> bool:
    """Il requisito citato viene davvero da Canvas/Spec? Citazione esatta oppure, per le
    parafrasi, almeno il 70% delle parole significative presenti nel contratto."""
    req = norm(requirement)
    if not req:
        return False
    if req in contract_norm:
        return True
    words = set(re.findall(r"\w{4,}", req))
    return bool(words) and sum(w in contract_norm for w in words) / len(words) >= 0.7


def verify_code_finding(finding: dict, batch: list[tuple[str, str, str]], contract_norm: str,
                        searchable: dict[str, str]) -> dict:
    """Rilievo di un lotto: la citazione deve esistere nel codice che l'LLM ha visto e, se
    è una "mancanza", i termini indicati non devono comparire in nessun file del progetto
    (su BE1: "in Reporting.cs manca la validazione del budget", che sta in EventCommands.cs)."""
    out = _base(finding)
    if out["categoria"] == "conforme":
        return out
    # Anche una "contraddizione" con termini è di fatto un'affermazione di assenza: su BE1
    # "Publish() non controlla il budget" (tipo contraddizione, termine BUDGET_INSUFFICIENTE)
    # ignorava il controllo nell'handler.
    if (out["tipo"] == "mancanza" or out["termini"]) and not _terms_absent(out, searchable):
        return out
    texts: dict[str, str] = {}
    for label, _header, chunk in batch:
        texts[label] = texts.get(label, "") + "\n" + chunk
    located = [label for label, text in texts.items() if quote_in(out["evidenza"], norm(text))]
    if not located:
        out["scartato"] = "citazione del codice non trovata nei file esaminati"
    elif not requirement_in(out["requisito"], contract_norm):
        out["scartato"] = "requisito non trovato nel Canvas né nella Spec"
    else:
        claimed = out["file"].replace("\\", "/")
        out["file"] = claimed if claimed in located else located[0]
    return out


_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)
_LINE_COMMENT_RE = re.compile(r"^\s*(//|#|--|\*).*$|(?<=\s)//.*$", re.M)


def strip_comments(text: str) -> str:
    """Toglie i commenti più comuni (C-like, #, --, HTML): un "// … in Excel" in un
    commento non dimostra che l'export Excel esista. Approssimato, non un parser."""
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", text))


_WORD_PART_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")


def _terms_absent(out: dict, searchable: dict[str, str]) -> bool:
    """True se nessun termine della mancanza compare nel codice; altrimenti marca lo scarto.
    `searchable` è {file: testo minuscolo senza commenti}."""
    if not out["termini"]:
        out["scartato"] = "nessun termine di ricerca indicato: mancanza non verificabile"
        return False
    def find(needle: str) -> str | None:
        return next((label for label, text in searchable.items() if needle in text), None)

    for term in out["termini"]:
        hit = find(term.lower())
        if hit:
            out["scartato"] = f"'{term}' è presente nel codice ({hit})"
            return False
        # Nome composto ipotizzato dal modello (CapacityValidationException, SerilogError):
        # se ogni sua parte compare nel codice, la cosa esiste con un altro nome. Su BE1 era
        # il falso positivo più frequente; le vere lacune (Xlsx, ExcelExporter) hanno parti assenti.
        parts = [p.lower() for p in _WORD_PART_RE.findall(term) if len(p) >= 4]
        hits = [find(p) for p in parts]
        if len(parts) > 1 and all(hits):
            out["scartato"] = (f"nome ipotetico: le parti di '{term}' ({', '.join(parts)}) "
                               f"compaiono tutte nel codice (es. {hits[0]})")
            return False
    out["assenza_verificata"] = True
    return True


def verify_coverage_finding(finding: dict, searchable: dict[str, str], contract_norm: str) -> dict:
    """Rilievo di "mancanza" dall'indice dei simboli: nessuno dei termini indicati deve
    comparire nel codice (commenti esclusi)."""
    out = _base(finding)
    out["tipo"] = "mancanza"
    if out["categoria"] == "conforme" or not _terms_absent(out, searchable):
        return out
    if not requirement_in(out["requisito"], contract_norm):
        out["scartato"] = "requisito non trovato nel Canvas né nella Spec"
    return out


def _base(finding: dict) -> dict:
    severity = norm(finding.get("gravita"))
    terms = finding.get("termini")
    return {
        "categoria": _category(finding.get("categoria")),
        "tipo": "mancanza" if norm(finding.get("tipo")) == "mancanza" else "contraddizione",
        "termini": [str(t).strip() for t in terms if str(t).strip()] if isinstance(terms, list) else [],
        "gravita": severity if severity in SEVERITIES else "media",
        "sezione": str(finding.get("sezione") or "").strip(),
        "requisito": str(finding.get("requisito") or "").strip(),
        "file": str(finding.get("file") or "").strip(),
        "evidenza": str(finding.get("evidenza") or "").strip(),
        "descrizione": str(finding.get("descrizione") or "").strip(),
        "scartato": "",
    }


def _same_gap(a: dict, b: dict) -> bool:
    """Due mancanze confermate descrivono la stessa lacuna se i loro termini si
    sovrappongono (su BE1: "Xlsx"/"Excel" e "XlsxDocumentFormat"/"ExcelPackage")."""
    ta = {norm(t) for t in a["termini"] if len(t) >= 4}
    tb = {norm(t) for t in b["termini"] if len(t) >= 4}
    return any(x in y or y in x for x in ta for y in tb)


def dedupe(findings: list[dict]) -> list[dict]:
    seen, out = set(), []
    for f in findings:
        key = (f["categoria"], norm(f["requisito"]), f["file"], norm(f["evidenza"]),
               tuple(sorted(norm(t) for t in f.get("termini", []))))
        if key in seen:
            continue
        if f["tipo"] == "mancanza" and not f["scartato"] and any(
                g["tipo"] == "mancanza" and not g["scartato"] and g["categoria"] == f["categoria"]
                and _same_gap(f, g) for g in out):
            continue
        seen.add(key)
        out.append(f)
    return out


# ------------------------------------------------------------------ report --

def _format_finding(n: int, f: dict) -> str:
    lines = [f"{n}. [{f['gravita']}] {f['sezione'] or 'sezione non indicata'}: {f['descrizione']}"]
    if f["requisito"]:
        lines.append(f"   Requisito: «{f['requisito']}»")
    if f["evidenza"]:
        lines.append(f"   Evidenza: {f['file'] or '?'} → {f['evidenza']}")
    if f.get("termini"):
        found = " (assenti nel codice)" if f.get("assenza_verificata") else ""
        lines.append(f"   Termini cercati{found}: {', '.join(f['termini'])}")
    if f["scartato"]:
        lines.append(f"   Motivo: {f['scartato']}")
    return "\n".join(lines)


def build_report(findings: list[dict], *, coverage: str, prechecks_found: list[tuple[str, str, str]],
                 failures: list[str]) -> str:
    """Report leggibile nel box della pipeline. Il verdetto (prima riga) è calcolato:
    DRIFT se sopravvive almeno un rilievo "drift" verificato; INCOMPLETA se qualche
    risposta dell'LLM non era interpretabile e nessun drift è confermato."""
    kept = [f for f in findings if not f["scartato"] and f["categoria"] != "conforme"]
    drift = [f for f in kept if f["categoria"] == "drift"]
    notes = [f for f in kept if f["categoria"] != "drift"]
    discarded = [f for f in findings if f["scartato"] and f["categoria"] != "conforme"]
    order = {s: i for i, s in enumerate(SEVERITIES)}
    drift.sort(key=lambda f: order[f["gravita"]])

    # Un punto aperto con assenza verificata (es. BE1 senza export Excel: il Canvas lo chiede,
    # la Spec lo lascia aperto in OP-001) non è un drift, ma non può finire sotto un ✅.
    open_missing = [f for f in notes if f["categoria"] == "punto_aperto" and f.get("assenza_verificata")]
    if drift:
        head = f"{VERDICT_DRIFT}: {len(drift)} rilievo/i confermato/i dalla verifica sul codice."
    elif failures:
        head = f"{VERDICT_INCOMPLETE}: nessun drift confermato, ma non tutte le analisi sono andate a buon fine."
    elif open_missing:
        head = (f"{VERDICT_OPEN}: nessun drift, ma {len(open_missing)} requisito/i non implementato/i "
                "resta/no aperto/i nella Spec.")
    else:
        head = VERDICT_OK
    out = [head, "", f"Copertura: {coverage}"]
    if prechecks_found:
        out.append("Dipendenze del Canvas trovate nei manifest: "
                   + "; ".join(f"{t} → {d} ({m})" for t, d, m in prechecks_found))
    out += [f"⚠️ {msg}" for msg in failures]
    if drift:
        out += ["", "── DRIFT CONFERMATI ──"] + [_format_finding(i, f) for i, f in enumerate(drift, 1)]
    if notes:
        out += ["", "── PUNTI APERTI / FUORI AMBITO (non influiscono sul verdetto) ──"]
        out += [_format_finding(i, f) + f"\n   Categoria: {f['categoria']}" for i, f in enumerate(notes, 1)]
    if discarded:
        out += ["", "── SCARTATI DALLA VERIFICA AUTOMATICA (non influiscono sul verdetto) ──"]
        out += [_format_finding(i, f) for i, f in enumerate(discarded, 1)]
    return "\n".join(out)
