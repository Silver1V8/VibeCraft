"""Harness di ATTRIBUZIONE (N3): «a quale fonte la risposta attribuisce il vincolo».

A3 ha stabilito che il difetto del sistema non è il rango ma l'attribuzione: la fonte giusta
entra sempre nel contesto, ed è dentro la finestra che il modello decide chi «stabilisce» il
vincolo e chi lo motiva. Nessuna metrica di retrieval guarda quel punto. Questo harness sì,
con un giudice LLM che legge la risposta e nomina la fonte a cui la risposta attribuisce il
vincolo — UNA chiamata per esecuzione, MAI aggregata per caso (S12: il caso 05 ha dato tre
esiti diversi su tre esecuzioni; aggregare prima di giudicare cancella il fenomeno).

Due modi, con prerequisiti diversi:

  a) VALIDARE IL GIUDICE (default) — offline, contro eval/golden_attribution.yaml: 24 verdetti
     umani archiviati con il testo integrale della risposta (S12). Non serve né il server né
     l'indice attivo: serve solo Ollama. Il numero che conta è l'accordo col verdetto umano,
     e in particolare sui 7 negativi — un giudice che prende tutti i positivi e nessun
     negativo è inutile e sembrerebbe buono.

        uv run python -m eval.attribution --repeats 3

  b) MISURARE IL SISTEMA (--live) — dal vivo contro POST /ask, con il server acceso SENZA
     cache (configurazione `vibecraft-rag-nocache`: VIBECRAFT_ASK_CACHE_SIZE=0, altrimenti tre
     esecuzioni della stessa domanda sono una sola). Ogni risposta è giudicata dal giudice
     validato in (a) e confrontata con la fonte normativa dichiarata dal caso. L'indice attivo
     NON è quello dell'archivio (summary.superseded_by): il report lo dichiara. Le run escono
     in eval/results/attribution_live_<ts>.yaml nel formato dell'archivio, con il verdetto
     del giudice al posto di quello umano: l'archivio NON viene mai scritto da qui — i suoi
     verdetti sono umani, e le run si aggiungono a mano dopo averle lette.

        uv run python -m eval.attribution --live --runs 3

Oltre al giudice, l'harness verifica DETERMINISTICAMENTE (un `in` su un file) i passi che la
risposta riporta fra virgolette contro il documento attribuito. È il caso 06 run 3 di S12:
fonte giusta, passo preso dal distrattore — corretto per la metrica, falso nel contenuto.
Esiti: `verified`, `found_only_in:<doc>` (il passo sta in un ALTRO documento del contesto: da
leggere, può essere anche una citazione dichiarata), `unverifiable` (in nessun documento:
parafrasi o invenzione), `no_quote`. Del giudice si verifica solo che la frase su cui regge il
verdetto stia davvero nella risposta.

NON è un gate né un check per-push: costa una chiamata LLM per record. Quando eseguirlo è
scritto in rag/AUDIT.md (S14) e RESIDUI.md.

Exit code (modo a): 0 se ogni giudizio coincide col verdetto umano, 1 altrimenti, 2 se il
giudice non è raggiungibile. Modo b: 0 (è una misura), 2 se il server non risponde.
"""
import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import yaml

from core import llm
from core.config import DOCS_DIR, GOLDEN_SET_PATH

for _s in (sys.stdout, sys.stderr):  # emoji/§/→ safe su console Windows (cp1252)
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ARCHIVE = GOLDEN_SET_PATH.with_name("golden_attribution.yaml")
RESULTS_DIR = Path(__file__).parent / "results"
NESSUNA = "NESSUNA"
PARSE_ERROR = "PARSE_ERROR"
JUDGE_PURPOSE = "judge"
# Sotto questa lunghezza un passo è troppo generico perché un `in` sul file dimostri qualcosa.
MIN_QUOTE_WORDS = 5

JUDGE_PROMPT = """Sei un revisore. Ricevi una DOMANDA posta a un sistema di risposta documentale, l'elenco delle FONTI che quel sistema aveva nel contesto (percorso § sezione [CLASSE]) e la RISPOSTA che ha prodotto.

Devi stabilire UNA cosa sola: a quale fonte la RISPOSTA attribuisce il VINCOLO che risponde alla domanda — cioè quale documento la risposta indica come quello che lo STABILISCE. Conta solo ciò che la risposta DICE, non ciò che sarebbe giusto: non usare conoscenza esterna e non scegliere il documento che «contiene» il vincolo, ma quello a cui la risposta lo attribuisce.

Procedi così, nell'ordine:
1. Trova nella risposta la FRASE in cui la risposta dice CHI stabilisce il vincolo che risponde alla DOMANDA: una frase che lega un documento, un codice di regola ([REGOLA-…], [SAFEGUARD-…]) o una classe fra quadre ([REQUIREMENTS], [IRON_MEMORY], [NORMS], [METHODOLOGY]…) al vincolo. Il legame può essere un verbo («stabilisce», «impone», «definisce», «prescrive», «afferma», «richiede», «vieta»), una preposizione («secondo X», «come specificato in X», «nel blocco X del file Y», «viola X», «non è conforme a X») o un'ETICHETTA di fonte accanto al vincolo («Fonte: X», «(fonte: X)», «Fonte Autorevole: X»): un'etichetta di fonte attribuisce tanto quanto un verbo. Copiala ESATTAMENTE (massimo 30 parole). Se la risposta si contraddice, vale la PRIMA frase di questo tipo.
2. Riporta il VERBO o l'etichetta con cui quella frase lega la fonte al vincolo. Una fonte legata al vincolo SOLO da «motiva», «illustra», «conferma», «spiega», «descrive», «riporta», «fornisce», «contiene», «esplicita», «citato come», «come conferma» è citata come commento o come posto dove il vincolo è scritto, non come chi lo stabilisce: cerca un'altra frase, e se non c'è la fonte è NESSUNA.
3. Indica la fonte. Un codice di regola o una classe identifica il documento dell'elenco che lo porta: rispondi con il NOME DEL FILE, mai con il codice né con la classe. Rispondi NESSUNA se il soggetto della frase è «il contesto», «le regole» o «i vincoli» e non un documento — anche se un documento dell'elenco sarebbe la fonte ovvia — oppure se la risposta dichiara che nessuna regola o fonte lo stabilisce. Leggi TUTTA la risposta: un'apertura come «il contesto non riporta…» non conta se poi una frase attribuisce il vincolo a un documento.

Valori ammessi per attributed_to: {allowed}.

Rispondi SOLO con un oggetto JSON, senza testo prima o dopo, con i campi in QUESTO ordine:
{{"quote": "<la frase del punto 1, copiata esattamente; stringa vuota se non esiste>",
 "verb": "<il verbo del punto 2>",
 "attributed_to": "<nome del file del documento, oppure NESSUNA>"}}

DOMANDA:
{q}

FONTI NEL CONTESTO (nell'ordine letto dal sistema):
{sources}

RISPOSTA:
{answer}
"""


# ---------------------------------------------------------------------------
# Archivio e corpus
# ---------------------------------------------------------------------------

def load_archive(path: Path = ARCHIVE) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def records(archive: dict, only_case: str | None = None) -> list[dict]:
    """Un record per ESECUZIONE (mai per caso), con l'id nel formato di summary.negatives."""
    out = []
    for case in archive["cases"]:
        if only_case and case["id"] != only_case:
            continue
        expected = case["normative"]["doc"] if case["normative"] else NESSUNA
        for i, run in enumerate(case["runs"], 1):
            out.append({"id": f"{case['id']} run {i}", "case": case, "run": run,
                        "expected": expected, "human": run["verdict"]["attributed_to"]})
    return out


def _stem(source: str) -> str:
    """`02_specs_normative/spec.md § 5. Titolo [REQUIREMENTS]` → `spec`."""
    return Path(source.split(" § ")[0].strip()).name.removesuffix(".md")


def _class_of(source: str) -> str:
    m = re.search(r"\[([A-Z_ ]+)(?:;|\])", source)
    return m.group(1).strip() if m else ""


_docs_cache: dict[str, str] = {}


def doc_text(stem: str) -> str | None:
    """Testo NORMALIZZATO del documento `stem` del corpus, o None se non esiste."""
    if stem not in _docs_cache:
        found = next(iter(DOCS_DIR.rglob(f"{stem}.md")), None)
        _docs_cache[stem] = normalize(found.read_text(encoding="utf-8")) if found else None
    return _docs_cache[stem]


# ---------------------------------------------------------------------------
# Giudice
# ---------------------------------------------------------------------------

def judge_prompt(question: str, sources: list[str], answer: str) -> str:
    allowed = sorted({Path(s.split(" § ")[0].strip()).name for s in sources}) + [NESSUNA]
    return JUDGE_PROMPT.format(q=question, sources="\n".join(f"- {s}" for s in sources),
                               allowed=", ".join(allowed), answer=answer)


def parse_judgement(text: str) -> dict:
    """Il JSON del giudice, tollerando fence e testo attorno. Su fallimento il verdetto è
    PARSE_ERROR: conta come disaccordo, non come «nessuna fonte»."""
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict) or "attributed_to" not in data:
        return {"attributed_to": PARSE_ERROR, "quote": "", "verb": "", "raw": text}
    return {"attributed_to": str(data.get("attributed_to") or ""),
            "quote": str(data.get("quote") or ""), "verb": str(data.get("verb") or ""),
            "raw": text}


def normalize_verdict(value: str, sources: list[str]) -> str:
    """Riporta la risposta del giudice allo stem del documento, come nell'archivio: toglie
    percorso, estensione, ornamenti; «nessuna» in ogni forma → NESSUNA; una CLASSE fra
    quadre viene mappata sul documento del contesto che la porta, se è uno solo (è la
    stessa lettura che il verdetto umano fa di «nella specifica [REQUIREMENTS]»)."""
    v = value.strip().strip("`'\"«» ")
    if v.upper() in ("", NESSUNA, "NONE", "NULL", PARSE_ERROR):
        return NESSUNA if v.upper() != PARSE_ERROR else PARSE_ERROR
    v = v.strip("[]")
    docs_by_class: dict[str, set[str]] = {}
    for s in sources:
        docs_by_class.setdefault(_class_of(s), set()).add(_stem(s))
    if v.upper() in docs_by_class and len(docs_by_class[v.upper()]) == 1:
        return next(iter(docs_by_class[v.upper()]))
    return Path(v.split(" § ")[0]).name.removesuffix(".md")


_STRIP = str.maketrans({c: "" for c in "*`«»“”\"'’‘_"})


def normalize(text: str) -> str:
    """Forma confrontabile di un testo: NFKC, minuscole, senza ornamenti markdown né
    virgolette, spazi collassati. Applicata a ENTRAMBI i lati dell'`in`."""
    t = unicodedata.normalize("NFKC", text).lower().translate(_STRIP)
    return re.sub(r"\s+", " ", t).strip()


def _mostly_in(quote: str, text: str, n: int = 5, share: float = 0.6) -> bool:
    """`quote` sta in `text` a meno di ritocchi: almeno `share` dei suoi n-grammi di parole
    è presente. Tollera il giudice che fonde due punti elenco o toglie un'etichetta in
    grassetto (misurato: 10 citazioni su 72 nel primo giro erano così, nessuna inventata);
    NON si usa sui documenti, dove l'`in` resta letterale — è ciò che rende la verifica
    una prova e non un'impressione."""
    words = quote.split()
    grams = [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)] or [quote]
    return sum(g in text for g in grams) / len(grams) >= share


_QUOTED = re.compile(r"[«\"“]([^»\"”]{20,}?)[»\"”]")


def quoted_spans(answer: str, min_words: int = MIN_QUOTE_WORDS) -> list[str]:
    """I passi che la risposta riporta FRA VIRGOLETTE, cioè presenta come parole di una
    fonte. Sotto `min_words` un passo è troppo generico perché un `in` dimostri qualcosa."""
    return [m.group(1).strip() for m in _QUOTED.finditer(answer)
            if len(m.group(1).split()) >= min_words]


def check_citations(answer: str, attributed_to: str, sources: list[str]) -> str:
    """Verifica DETERMINISTICA dei passi virgolettati della risposta contro il documento
    attribuito: `no_quote` (nessun passo), `verified` (ogni passo sta nel documento
    attribuito), `found_only_in:<doc>` (un passo NON sta nel documento attribuito ma in un
    altro del contesto — è il caso 06 run 3 di S12, e va LETTO: può anche essere una fonte
    citata dichiaratamente come altra), `unverifiable` (un passo non sta in nessun
    documento del contesto: parafrasi o invenzione, non decidibile con un `in`).
    Non dipende dal giudice: gira su tutti i record allo stesso modo."""
    spans = [normalize(q) for q in quoted_spans(answer)]
    if not spans or attributed_to in (NESSUNA, PARSE_ERROR):
        return "no_quote"
    attributed = doc_text(attributed_to) or ""
    others = {o: doc_text(o) or "" for o in sorted({_stem(s) for s in sources} - {attributed_to})}
    verdict = "verified"
    for q in spans:
        if q in attributed:
            continue
        elsewhere = [o for o, text in others.items() if q in text]
        if elsewhere:
            return f"found_only_in:{elsewhere[0]}"
        verdict = "unverifiable"
    return verdict


def judge(question: str, sources: list[str], answer: str, *, repeats: int = 1,
          generate=None) -> list[dict]:
    """`repeats` giudizi indipendenti sullo STESSO record. Ogni voce: attributed_to
    normalizzato, quote, citation (esito della verifica), raw."""
    generate = generate or (lambda p: llm.generate(p, purpose=JUDGE_PURPOSE))
    prompt = judge_prompt(question, sources, answer)
    out = []
    for _ in range(repeats):
        j = parse_judgement(generate(prompt))
        j["attributed_to"] = normalize_verdict(j["attributed_to"], sources)
        # La frase su cui il giudice regge il verdetto deve stare nella risposta (a meno di
        # ritocchi): se non c'è, il giudice l'ha inventata e quel verdetto non vale.
        j["quote_in_answer"] = (not j["quote"].strip()) or \
            _mostly_in(normalize(j["quote"]), normalize(answer))
        j["citation"] = check_citations(answer, j["attributed_to"], sources)
        out.append(j)
    return out


# ---------------------------------------------------------------------------
# Modo (a): validazione contro l'archivio
# ---------------------------------------------------------------------------

def validate(archive: dict, *, repeats: int = 1, only_case: str | None = None,
             generate=None, log=print) -> dict:
    rows = []
    for rec in records(archive, only_case):
        run = rec["run"]
        judgements = judge(rec["case"]["q"], run["context_sources"], run["answer"],
                           repeats=repeats, generate=generate)
        verdicts = [j["attributed_to"] for j in judgements]
        row = {
            "id": rec["id"], "human": rec["human"], "expected": rec["expected"],
            "human_correct": run["verdict"]["correct"],
            "judge": verdicts, "quotes": [j["quote"] for j in judgements],
            "verbs": [j["verb"] for j in judgements],
            "citation": [j["citation"] for j in judgements],
            "quote_in_answer": all(j["quote_in_answer"] for j in judgements),
            "unanimous": len(set(verdicts)) == 1,
            "agree": all(v == rec["human"] for v in verdicts),
            # Accordo BINARIO: giudice e umano dicono entrambi «corretta» o entrambi «sbagliata»,
            # anche se sulla fonte sbagliata non coincidono. È il numero che conta nel modo (b),
            # dove il giudice non confronta con l'umano ma con la fonte normativa attesa.
            "agree_binary": all((v == rec["expected"]) == run["verdict"]["correct"] for v in verdicts),
        }
        rows.append(row)
        log(_fmt_row(row))
    return {"rows": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    neg = [r for r in rows if not r["human_correct"]]
    pos = [r for r in rows if r["human_correct"]]
    citations = [c for r in rows for c in r["citation"]]
    return {
        "records": len(rows),
        "agree": sum(r["agree"] for r in rows),
        "positives": len(pos), "positives_agree": sum(r["agree"] for r in pos),
        "negatives": len(neg), "negatives_agree": sum(r["agree"] for r in neg),
        "unanimous": sum(r["unanimous"] for r in rows),
        "binary_agree": sum(r["agree_binary"] for r in rows),
        "false_alarms": [r["id"] for r in pos if not r["agree_binary"]],
        "missed_negatives": [r["id"] for r in neg if not r["agree_binary"]],
        "disagreements": [r["id"] for r in rows if not r["agree"]],
        "quote_not_in_answer": [r["id"] for r in rows if not r["quote_in_answer"]],
        "citation": {k: sum(1 for c in citations if c.split(":")[0] == k)
                     for k in ("verified", "found_only_in", "unverifiable", "no_quote")},
        "citation_found_elsewhere": sorted({(r["id"], c) for r in rows for c in r["citation"]
                                            if c.startswith("found_only_in")}),
    }


def _fmt_row(r: dict) -> str:
    mark = "✅" if r["agree"] else "❌"
    rep = "" if r["unanimous"] else "  ⚠️ NON ripetibile"
    cit = ", ".join(sorted(set(r["citation"])))
    return (f"{mark} {r['id']:<36} umano={r['human']:<32} giudice={'/'.join(r['judge'])}"
            f"{rep}  [{cit}]")


def print_summary(s: dict, repeats: int) -> None:
    print("\n" + "-" * 100)
    print(f"accordo col verdetto umano : {s['agree']}/{s['records']}"
          f"   positivi {s['positives_agree']}/{s['positives']}"
          f"   NEGATIVI {s['negatives_agree']}/{s['negatives']}")
    if repeats > 1:
        print(f"ripetibilità ({repeats} giudizi/record): unanimi {s['unanimous']}/{s['records']}")
    if s["disagreements"]:
        print("disaccordi: " + "; ".join(s["disagreements"]))
    print(f"accordo BINARIO (corretta/sbagliata): {s['binary_agree']}/{s['records']}"
          f"   falsi allarmi {len(s['false_alarms'])}/{s['positives']}"
          f"   negativi mancati {len(s['missed_negatives'])}/{s['negatives']}")
    c = s["citation"]
    if s["quote_not_in_answer"]:
        print("frase del giudice NON nella risposta (verdetto inventato): " + "; ".join(s["quote_not_in_answer"]))
    print(f"passi virgolettati (per giudizio): nel documento attribuito {c['verified']}, "
          f"in un ALTRO documento {c['found_only_in']}, in nessuno {c['unverifiable']}, "
          f"nessun passo {c['no_quote']}")
    for rid, cit in s["citation_found_elsewhere"]:
        print(f"   ⚠️ da leggere — {rid}: un passo virgolettato sta in {cit.split(':', 1)[1]}, "
              "non nel documento attribuito")


# ---------------------------------------------------------------------------
# Modo (b): misura dal vivo
# ---------------------------------------------------------------------------

# Intestazione di un blocco documentale nel contesto di /ask: la stessa regex con cui
# eval.calibrate_graph_context rilegge il contesto del server.
_BLOCCO = re.compile(r"^--- (?P<doc>.+?) § (?P<sec>.*?) \[(?P<meta>[^\]]*)\] ---$", re.M)


def context_sources(context_text: str) -> list[str]:
    return [f"{m['doc']} § {m['sec']} [{m['meta']}]" for m in _BLOCCO.finditer(context_text)]


def ask_live(url: str, question: str, client) -> dict:
    resp = client.post(f"{url}/ask", json={"question": question})
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("cached"):
        raise RuntimeError("la risposta viene dalla cache di /ask: avvia il server con "
                           "VIBECRAFT_ASK_CACHE_SIZE=0 (configurazione vibecraft-rag-nocache), "
                           "altrimenti N esecuzioni sono una sola")
    return payload


def measure_live(archive: dict, url: str, *, runs: int, only_case: str | None,
                 client, generate=None, log=print) -> dict:
    model = llm.resolve("ask")[1]
    out_cases, versions = [], set()
    for case in archive["cases"]:
        if only_case and case["id"] != only_case:
            continue
        expected = case["normative"]["doc"] if case["normative"] else NESSUNA
        live_runs = []
        for i in range(1, runs + 1):
            p = ask_live(url, case["q"], client)
            versions.add(p.get("index_version"))
            sources = context_sources(p["graph_context"]["context_text"])
            j = judge(case["q"], sources, p["answer"], generate=generate)[0]
            live_runs.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "index_version": p.get("index_version"), "model": model,
                "status": p.get("status"), "context_sources": sources,
                "implementing_code_blocks": len(p.get("implementing_code") or []),
                "answer": p["answer"],
                "judge": {"attributed_to": j["attributed_to"],
                          "correct": j["attributed_to"] == expected,
                          "quote": j["quote"], "citation": j["citation"]},
            })
            log(f"{'✅' if j['attributed_to'] == expected else '❌'} {case['id']} run {i}: "
                f"atteso={expected} giudice={j['attributed_to']} [{j['citation']}]")
        out_cases.append({"id": case["id"], "expected": expected, "runs": live_runs})
    all_runs = [r for c in out_cases for r in c["runs"]]
    return {
        "measured_on": datetime.now().strftime("%Y-%m-%d"),
        "index_version": sorted(v for v in versions if v),
        "archive_index_version": archive["summary"]["index_version"],
        "model": model, "judge_model": llm.resolve(JUDGE_PURPOSE)[1],
        "runs": len(all_runs),
        "correct": sum(r["judge"]["correct"] for r in all_runs),
        "negatives": [f"{c['id']} run {i}: -> {r['judge']['attributed_to']}"
                      for c in out_cases for i, r in enumerate(c["runs"], 1)
                      if not r["judge"]["correct"]],
        "cases": out_cases,
    }


def _yaml_block_strings(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


def save(payload: dict, name: str, suffix: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{suffix}"
    if suffix == "yaml":
        yaml.add_representer(str, _yaml_block_strings, Dumper=yaml.SafeDumper)
        out.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
                       encoding="utf-8")
    else:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Harness di attribuzione della fonte (N3)")
    ap.add_argument("--repeats", type=int, default=1,
                    help="giudizi indipendenti per record nel modo (a): >1 misura la ripetibilità")
    ap.add_argument("--case", help="limita a un solo caso (id dell'archivio)")
    ap.add_argument("--live", action="store_true", help="modo (b): interroga POST /ask")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=3, help="esecuzioni per caso nel modo (b)")
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.0,
                    help="temperatura del giudice (default 0: un giudice campiona a caso solo se "
                         "glielo si chiede; 0.1 è il valore del server, misurato non ripetibile)")
    a = ap.parse_args()
    # Vale solo in questo processo (il server ha il suo): core.llm legge il globale a ogni payload.
    llm.OLLAMA_TEMPERATURE = a.temperature

    archive = load_archive()
    provider, judge_model = llm.resolve(JUDGE_PURPOSE)
    print(f"giudice: {provider}/{judge_model}   archivio: {ARCHIVE.name} "
          f"(indice {archive['summary']['index_version']}"
          f"{', SUPERATO da ' + archive['summary']['superseded_by'] if archive['summary'].get('superseded_by') else ''})\n")

    if a.live:
        import httpx2
        try:
            with httpx2.Client(timeout=300) as client:
                result = measure_live(archive, a.url, runs=a.runs, only_case=a.case, client=client)
        except (httpx2.HTTPError, RuntimeError) as e:
            print(f"❌ {e}")
            return 2
        except llm.LLMError as e:
            print(f"❌ giudice non disponibile: {e}")
            return 2
        print(f"\n{result['correct']}/{result['runs']} attribuzioni corrette sull'indice "
              f"{', '.join(result['index_version'])} (l'archivio è su {result['archive_index_version']}: "
              f"NON è la stessa misura)")
        for n in result["negatives"]:
            print(f"   ❌ {n}")
        if not a.no_save:
            print(f"\n💾 run archiviabili (dopo lettura umana) in {save(result, 'attribution_live', 'yaml')}")
        return 0

    try:
        result = validate(archive, repeats=a.repeats, only_case=a.case)
    except llm.LLMError as e:
        print(f"❌ giudice non disponibile: {e}")
        return 2
    print_summary(result["summary"], a.repeats)
    if not a.no_save:
        result["judge"] = f"{provider}/{judge_model}"
        result["repeats"] = a.repeats
        print(f"\n💾 {save(result, 'attribution', 'json')}")
    s = result["summary"]
    ok = s["agree"] == s["records"] and s["unanimous"] == s["records"]
    print("\n" + ("✅ il giudice concorda con l'umano su ogni record: pronto"
                  if ok else "❌ il giudice NON concorda su ogni record: non è pronto (criterio S6)"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
