"""Intervista Explore ancorata ai docs (pipeline, step 1): logica pura usata da
api/routes_pipeline.pipeline_explore_turn, che resta l'orchestratore (retrieval, LLM).

Perché esiste (2026-11-09): l'intervista era una chat LLM senza retrieval, quindi chiedeva
all'utente anche ciò che `docs/` stabilisce già. Le risposte date a voce finivano in
explore.md e da lì nel Canvas, con due rischi: rifare un lavoro già fatto e produrre una
seconda specifica che si sovrappone alla prima o la contraddice. Qui ogni turno:
· l'LLM propone le domande CANDIDATE in JSON (non le pone ancora);
· ogni domanda è cercata nel Graph RAG con la sua formulazione (ranking già pesato per
  autorità): una query sul solo nome della feature non fa risalire la sezione che risponde;
· l'LLM classifica ogni domanda come nota / conflitto / aperta citando le sezioni [S#] e
  una frase testuale;
· Python verifica sezione e citazione (come il drift check, core/drift.py) e DECLASSA ad
  "aperta" ciò che non è verificabile: meglio una domanda in più che una risposta inventata
  spacciata per documentata.
Solo le domande aperte e i conflitti (presentati come scelta) arrivano all'utente.
"""
from core.drift import _json_object, norm, quote_in

MAX_QUESTIONS = 5
SECTIONS_PER_QUESTION = 3
MAX_SECTION_CHARS = 1500

INTRO = ("Sei un Tech Lead e un 'thinking partner'. Stiamo definendo i requisiti per la "
         "feature: {feature}.{scope} Fai domande brevi e mirate per sviscerare i casi limite.\n")


def intro(feature: str, dev_type: str = "") -> str:
    scope = (f" Il tipo di sviluppo richiesto per questa feature è '{dev_type}' (cartella "
             f"code/{dev_type}): concentra le domande esclusivamente sugli aspetti pertinenti "
             f"a questo ambito." if dev_type else "")
    return INTRO.format(feature=feature, scope=scope)


def candidates_prompt(history: str, user_input: str) -> str:
    return (history + f"\nUtente: {user_input}\n\n"
            "Non porre ancora le domande: elencale come CANDIDATE. Verranno confrontate con la "
            "documentazione del progetto e all'utente arriveranno solo quelle che i documenti non "
            "risolvono. Massimo " + str(MAX_QUESTIONS) + " domande, una sola richiesta ciascuna, "
            "autonome (comprensibili senza la conversazione). Non ripetere domande già poste o già "
            "risolte nella conversazione. In \"commento\" rispondi in una o due frasi a quanto ha "
            "scritto l'utente (vuoto se non serve).\n"
            'Rispondi SOLO con JSON valido: {"commento": "...", "domande": ["...", "..."]}')


def parse_candidates(text: str) -> tuple[str, list[str]] | None:
    """(commento, domande) dal JSON del modello; None se la risposta non è strutturata."""
    data = _json_object(text)
    if not isinstance(data, dict) or not isinstance(data.get("domande"), list):
        return None
    questions = [q.strip() for q in data["domande"] if isinstance(q, str) and q.strip()]
    comment = data.get("commento") if isinstance(data.get("commento"), str) else ""
    return comment.strip(), questions[:MAX_QUESTIONS]


def build_sections(hits_per_question: list[list[dict]], *, chunks_store: dict,
                   graph) -> list[dict]:
    """Sezioni recuperate, deduplicate e numerate S1, S2… nell'ordine di rilevanza. Il testo
    è quello del chunk (cap leggero): la citazione si verifica su questo stesso testo, così
    il modello non può citare ciò che non ha visto."""
    sections: dict[str, dict] = {}
    for hits in hits_per_question:
        for hit in hits:
            chunk_id = hit.get("chunk_id")
            entry = chunks_store.get(chunk_id) or {}
            if chunk_id in sections or not isinstance(entry.get("text"), str):
                continue
            doc_id = hit.get("doc_id", "")
            attrs = graph.nodes[doc_id] if graph is not None and doc_id in graph else {}
            tag = attrs.get("classification") or attrs.get("status") or ""
            section = hit.get("section", "")
            sections[chunk_id] = {
                "sid": f"S{len(sections) + 1}",
                "doc_id": doc_id, "section": section, "tag": str(tag),
                "source": f"{doc_id} § {section}" if section else doc_id,
                "text": entry["text"][:MAX_SECTION_CHARS],
            }
    return list(sections.values())


def check_prompt(questions: list[str], sections: list[dict]) -> str:
    blocks = "\n\n".join(
        f"[{s['sid']}] {s['source']}" + (f" [{s['tag']}]" if s["tag"] else "") + f"\n{s['text']}"
        for s in sections)
    asked = "\n".join(f"D{i}. {q}" for i, q in enumerate(questions, 1))
    return (
        "Controlli le domande di un'intervista sui requisiti. Per ogni domanda decidi, SOLO in "
        "base alle sezioni di documentazione qui sotto (nessuna conoscenza esterna):\n"
        '- "nota": una sezione risponde in modo chiaro e completo. Dai la risposta in breve, la '
        'sezione in "fonte" e in "citazione" una frase COPIATA ALLA LETTERA da quella sezione.\n'
        '- "conflitto": due o più sezioni danno risposte incompatibili. Elenca le alternative in '
        '"opzioni", ognuna con risposta, fonte e citazione letterale.\n'
        '- "aperta": i documenti non rispondono, o rispondono solo in parte. Nel dubbio, "aperta".\n'
        "Tra parentesi quadre dopo la fonte c'è la classe di autorità del documento.\n\n"
        f"SEZIONI:\n{blocks}\n\nDOMANDE:\n{asked}\n\n"
        "Rispondi SOLO con JSON valido, un esito per domanda:\n"
        '{"esiti": [{"domanda": 1, "stato": "nota", "risposta": "...", "fonte": "S1", '
        '"citazione": "..."}, {"domanda": 2, "stato": "conflitto", "opzioni": [{"risposta": '
        '"...", "fonte": "S2", "citazione": "..."}, {"risposta": "...", "fonte": "S3", '
        '"citazione": "..."}]}, {"domanda": 3, "stato": "aperta"}]}')


def _verified(item, by_sid: dict) -> dict | None:
    """Risposta con fonte esistente e citazione presente nel testo di quella fonte."""
    if not isinstance(item, dict):
        return None
    section = by_sid.get(str(item.get("fonte", "")).strip().strip("[]"))
    answer = str(item.get("risposta") or "").strip()
    if not section or not answer or not quote_in(item.get("citazione", ""), norm(section["text"])):
        return None
    return {"answer": answer, "source": section["source"], "tag": section["tag"]}


def classify(questions: list[str], sections: list[dict], text: str) -> dict:
    """Esiti verificati. Ogni domanda finisce in esattamente un gruppo; quelle senza un esito
    verificabile (JSON assente, fonte inesistente, citazione non trovata) restano aperte."""
    by_sid = {s["sid"]: s for s in sections}
    data = _json_object(text)
    outcomes = data.get("esiti") if isinstance(data, dict) else None
    status: dict[int, tuple] = {}
    for item in outcomes if isinstance(outcomes, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("domanda")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(questions) or index in status:
            continue
        kind = norm(item.get("stato"))
        if kind == "nota" and (found := _verified(item, by_sid)):
            status[index] = ("known", found)
        elif kind == "conflitto":
            options = [o for o in map(lambda o: _verified(o, by_sid), item.get("opzioni") or []) if o]
            # Un conflitto vale solo fra fonti DIVERSE: due frasi della stessa sezione no.
            if len({o["source"] for o in options}) >= 2:
                status[index] = ("conflict", options)
    result = {"known": [], "conflicts": [], "questions": []}
    for index, question in enumerate(questions):
        kind, payload = status.get(index, ("open", None))
        if kind == "known":
            result["known"].append({"question": question, **payload})
        elif kind == "conflict":
            result["conflicts"].append({"question": question, "options": payload})
        else:
            result["questions"].append(question)
    return result


def render(comment: str, result: dict, *, unchecked_reason: str = "") -> str:
    """Testo del turno: va nella bolla della chat e, tramite il log, in explore.md e nel
    Canvas, così le risposte già documentate arrivano a valle con la loro fonte."""
    parts = [comment] if comment else []
    if unchecked_reason:
        parts.append(f"⚠ Documentazione non consultata ({unchecked_reason}): le domande "
                     "non sono state confrontate con i docs del progetto.")
    if result["known"]:
        parts.append("Già documentato (non serve rispondere):\n" + "\n".join(
            f"- {k['question']}\n  → {k['answer']} [fonte: {k['source']}]" for k in result["known"]))
    if result["conflicts"]:
        parts.append("Da decidere: i documenti non concordano.\n" + "\n".join(
            f"- {c['question']}\n" + "\n".join(
                f"  {chr(65 + i)}) {o['answer']} [fonte: {o['source']}"
                + (f", {o['tag']}" if o["tag"] else "") + "]"
                for i, o in enumerate(c["options"]))
            for c in result["conflicts"]))
    if result["questions"]:
        parts.append("Domande aperte:\n" + "\n".join(
            f"{i}. {q}" for i, q in enumerate(result["questions"], 1)))
    elif not result["conflicts"]:
        parts.append("Nessuna domanda aperta: aggiungi altri dettagli o termina l'intervista.")
    return "\n\n".join(parts)
