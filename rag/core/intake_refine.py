"""Raffinazione LLM di un documento in staging: dal dump di markitdown già ripulito
(core/intake_clean.py) alla spec strutturata che entra in docs/ — sezioni `##`, tabelle
per gli elenchi di campi, blocchi di codice per XML/XSD, e un frontmatter semantico
(title, document_type, domain, tags) dedotto dal documento stesso.

Perché è un passo a parte e OPT-IN. La conversione (S1) deve restare deterministica e
istantanea: è il passo che dice "questo file è leggibile". La raffinazione invece chiama
l'LLM decine di volte su un documento lungo — minuti di lavoro — e per costruzione riscrive
il testo. Sta quindi dentro il ciclo di review S2 come passo esplicito: staging → refine →
preview → approve. Il markdown grezzo NON viene mai perso (resta in staging accanto al
raffinato) e nulla scavalca l'approve: il documento raffinato è un documento in staging
come gli altri.

Due guardrail contro il rischio vero di questo passo, che è tradire il documento:
· il documento viene raffinato a FINESTRE (una porzione per chiamata), mai in un colpo
  solo — oltre la finestra di contesto il modello taglia dall'alto in silenzio;
· una finestra la cui riscrittura esce dalla forbice di lunghezza ammessa viene SCARTATA
  e si tiene il testo pulito. Troppo corta significa che il modello ha RIASSUNTO, e un
  riassunto perde requisiti; troppo lunga che ha COMMENTATO invece di riformattare — su
  una fonte frammentaria riempie i buchi con congetture ("inferito", "potrebbe riferirsi")
  che in un documento normativo sono peggio del testo grezzo.

VINCOLO LLM (core/llm.py): purpose "canvas" — qwen3.5:9b, num_ctx 16384, think:false."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core import intake, llm
from core.config import (
    INTAKE_REFINE_DENSE_LINE_CHARS,
    INTAKE_REFINE_MAX_OUTPUT_RATIO,
    INTAKE_REFINE_MAX_OUTPUT_RATIO_DENSE,
    INTAKE_REFINE_MIN_OUTPUT_RATIO,
    INTAKE_REFINE_WINDOW_CHARS,
)
from core.intake_clean import clean_markdown
from core.writer_lock import writer_lock

# Stesso purpose della generazione doc (core/doc_generation.py): produrre markdown
# strutturato è lo stesso mestiere del Canvas, non serve un purpose nuovo.
_REFINE_PURPOSE = "canvas"

# Porzione di testa da cui si deduce il frontmatter semantico: titolo, tipo di documento e
# dominio si riconoscono dal frontespizio e dalle prime pagine, non serve l'intero file.
_METADATA_HEAD_CHARS = 6000

# Campi ammessi nel frontmatter semantico. Tutto il resto che il modello dovesse inventare
# viene scartato: il frontmatter normativo (id, project, authority, graph_rag, intake…)
# resta di competenza esclusiva di core/intake.py::_compose_document.
_SEMANTIC_FIELDS = ("title", "document_type", "source_version", "domain", "tags")
_LIST_FIELDS = ("domain", "tags")
_MAX_LIST_ITEMS = 10
# Un "tag" lungo quanto una frase non è un tag: il modello, invece di produrre una lista,
# a volte incolla tutti i concetti in un unico token kebab-case
# ("fascicolo-documentale-protocolli-soggetti-classificazione-…"). La lista però NON va
# buttata: quel token è già una lista, solo mal separata, e scartarlo lascia il documento
# senza tag (osservato su Specifiche Tecniche WsProtocollo). Si prova prima a spezzarlo
# sui trattini; solo ciò che resta troppo lungo anche dopo si scarta.
_MAX_LIST_ITEM_CHARS = 40
# Minimo di parole perché uno spezzone valga come tag: sotto, sono frammenti ("di", "e").
_MIN_TAG_CHARS = 3

_FENCE_BLOCK_RE = re.compile(r"^\s*```[a-zA-Z]*\s*\n(.*?)\n\s*```\s*$", re.S)
_H1_RE = re.compile(r"(?m)^#\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")

# --- Congetture -------------------------------------------------------------
# Il prompt le vieta, ma su decine di finestre il modello ci scivola comunque: segnaposto
# tipo "[Da verificare nel documento completo]" in una cella, incisi tipo "(inferito dal
# contesto standard)", note di lettura sul PDF sorgente. In un documento normativo che
# alimenta il RAG sono peggio di un buco: un'ipotesi del modello si legge come un dato.
# Qui si tolgono in modo DETERMINISTICO — nessun'altra parola viene toccata.
_HEDGE = r"inferit\w*|presumibil\w*|probabilment\w*|sembra\b|da verificare|non specificat\w*|da confermare"

# Segnaposto tra parentesi quadre che occupano un valore mai letto nel sorgente: il posto
# resta, dichiarato vuoto (un trattino), che è ciò che il prompt chiedeva di scrivere.
# Oltre alle formule di incertezza servono i segnaposto descrittivi ("[Dettagli degli
# esiti]"), che non contengono alcuna parola di dubbio ma sono altrettanto inventati.
# Il `(?!\()` esclude la sintassi dei link Markdown `[testo](url)`, che è contenuto vero.
_PLACEHOLDER_LEAD = rf"{_HEDGE}|dettagli\b|TODO\b|N/[DA]\b"
_PLACEHOLDER_RE = re.compile(rf"\[[^\]\n]*(?:{_PLACEHOLDER_LEAD})[^\]\n]*\](?!\()", re.I)
# Lo stesso segnaposto, marcato con l'enfasi invece che con le quadre
# ("| *Dettagli tabella non specificati nel testo* | *N/A* |"). La distinzione che conta è
# la MARCATURA: quadre o corsivo sono il modo in cui il modello dichiara "qui sto mettendo
# un riempitivo". Un "Non specificato" scritto in chiaro come valore di cella è invece una
# dichiarazione di lacuna — la cosa giusta da scrivere, e non si tocca.
_EMPHASIS_PLACEHOLDER_RE = re.compile(
    rf"(?<=\|)\s*[*_]+\s*[^|\n]*?(?:{_PLACEHOLDER_LEAD})[^|\n]*?[*_]+\s*(?=\|)", re.I)
# Incisi ipotetici in coda a un valore vero: "Si (inferito da contesto tabella 55)".
_HEDGE_PAREN_RE = re.compile(rf"\s*\([^()\n]*(?:{_HEDGE})[^()\n]*\)", re.I)
# Righe che sono SOLO una nota di lettura del modello sul documento originale.
_HEDGE_NOTE_RE = re.compile(rf"(?m)^\s*[*_]*\(?\s*Nota\b[^\n]*(?:{_HEDGE})[^\n]*$", re.I)
# Inciso editoriale in coda a un TITOLO ("#### Tabella parametri: `X` *(Nota sul nome della
# classe)*"). Circoscritto agli heading di proposito: lì un "(Nota …)" è sempre un commento
# del modello — un documento sorgente non ne mette nei titoli — e il testo del titolo
# diventa il nome della sezione con cui il chunk finisce nell'indice.
_HEADING_NOTE_RE = re.compile(r"(?m)^(#{1,6} .*?)\s*[*_]*\(\s*Nota\b[^)\n]*\)[*_]*\s*$", re.I)
# Cella rimasta con la sola punteggiatura di enfasi dopo la rimozione di un inciso
# ipotetico che ne costituiva tutto il contenuto ("| (Campi non specificati…)* |" → "|* |").
# NB: le celle VUOTE non si toccano — una cella lasciata in bianco dal documento sorgente
# è un dato, non un residuo, e riempirla di trattini sarebbe riscrivere il documento.
_ORPHAN_MARKUP_CELL_RE = re.compile(r"\|\s*[*_]+\s*(?=\|)")


class RefineError(RuntimeError):
    """La raffinazione non è stata possibile (LLM irraggiungibile, documento vuoto).
    Il documento resta in staging com'era: un refine fallito non perde nulla."""


@dataclass(frozen=True)
class RefineResult:
    markdown: str
    semantic: dict
    stats: dict = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Finestre: porzioni di documento che stanno comodamente nella finestra di contesto
# ---------------------------------------------------------------------------
def split_windows(text: str, window_chars: int = INTAKE_REFINE_WINDOW_CHARS) -> list[str]:
    """Divide il testo in finestre di al più `window_chars` caratteri, tagliando SOLO ai
    confini di blocco (riga vuota) e preferendo i confini di sezione (`#`): una tabella o
    un paragrafo spezzato a metà arriverebbe al modello senza il suo contesto. Un blocco
    singolo più lungo della finestra resta intero — mai troncato qui: preferiamo una
    finestra fuori misura (che il guardrail sulla lunghezza sa comunque proteggere) a un
    taglio cieco in mezzo a un blocco di codice."""
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    windows: list[str] = []
    current: list[str] = []
    size = 0
    for block in blocks:
        starts_section = bool(_HEADING_RE.match(block))
        if current and (size + len(block) > window_chars or (starts_section and size > window_chars // 2)):
            windows.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        windows.append("\n\n".join(current))
    return windows


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
def build_metadata_prompt(head: str, source_filename: str) -> str:
    """Prompt per il frontmatter semantico: solo ciò che si deduce dal documento."""
    return f"""Sei un documentalista tecnico. Leggi l'inizio di un documento e restituisci i
suoi metadati.

File sorgente: {source_filename}

--- INIZIO DEL DOCUMENTO ---
{head}
--- FINE ---

Rispondi con SOLO un blocco YAML, senza testo prima o dopo, con esattamente questi campi:
title: titolo del documento, breve e leggibile (niente estensioni di file, niente codici)
document_type: una fra "specifica tecnica", "data contract", "manuale", "procedura", "report", "altro"
source_version: versione dichiarata nel documento, stringa vuota se non c'è
domain: lista di 2-4 domini/sistemi citati (es. INPS, SOAP, DataPower)
tags: lista di 5-8 tag minuscoli in kebab-case, utili a ritrovare il documento

Non inventare: se un'informazione non è nel testo, lascia il campo vuoto."""


def build_refine_prompt(window: str, *, titolo: str, indice: int, totale: int) -> str:
    """Prompt di riscrittura di UNA finestra. Il modello riformatta, non riassume: la
    regola più importante del prompt è che nessun dato può sparire."""
    posizione = (
        "Questo è l'INIZIO del documento: apri con una sezione `## Scopo` che dica in "
        "poche righe cosa descrive il documento."
        if indice == 0 else
        f"Questa è la porzione {indice + 1} di {totale}: prosegui il documento, "
        f"NON reintrodurre lo scopo e non ripetere sezioni già trattate."
    )
    return f"""Sei un Tech Writer. Riformatti documentazione tecnica estratta da PDF/DOCX in
Markdown pulito, destinato a un sistema RAG che indicizza per sezione.

Documento: {titolo}
{posizione}

--- TESTO DA RIFORMATTARE ---
{window}
--- FINE TESTO ---

REGOLE (obbligatorie):
- NON riassumere e NON omettere: ogni campo, valore, codice, nome di classe, URL, vincolo
  e numero presente nel testo deve comparire anche nell'output. Puoi solo riorganizzare.
- NON inventare nulla che non sia nel testo: niente esempi, valori o sezioni aggiuntive.
- NON commentare e NON interpretare. Se il testo di partenza è frammentario, riportalo
  frammentario: una cella vuota o un trattino valgono più di un valore ipotizzato. Sono
  VIETATE le formule di incertezza ("inferito", "presumibilmente", "potrebbe riferirsi",
  "da verificare", "sembra"), i punti interrogativi usati come dubbio e ogni nota di
  lettura sul documento originale.
- La lunghezza dell'output deve essere paragonabile a quella dell'input: stai
  riformattando, non commentando.
- Struttura in sezioni `##` (e `###` se serve) con titoli brevi e descrittivi.
- Gli elenchi di campi, proprietà, parametri, codici o enumerazioni diventano TABELLE
  Markdown con intestazione (es. `| Campo | Tipo | Obbligatorio | Descrizione |`).
- XML, XSD, JSON, SQL e frammenti di codice vanno in blocchi ``` con il linguaggio.
- Prosa asciutta e impersonale in italiano; niente frasi di riempimento.
- Elimina residui di impaginazione: numeri di pagina, intestazioni ripetute, voci di
  indice, riferimenti a "vedi pagina N", note di revisione del documento.
- Non usare mai credenziali o chiavi reali: sostituiscile con segnaposto.
- Output: SOLO Markdown. Niente frontmatter, niente titolo `#`, nessun commento tuo,
  nessuna frase introduttiva o conclusiva."""


# ---------------------------------------------------------------------------
# Parsing delle risposte
# ---------------------------------------------------------------------------
def _strip_fence(raw: str) -> str:
    match = _FENCE_BLOCK_RE.match(raw.strip())
    return match.group(1) if match else raw.strip()


def _normalize_list_items(values) -> list[str]:
    """Voci di `domain`/`tags` normalizzate: si tengono quelle di lunghezza sensata, si
    RECUPERANO quelle lunghe che sono in realtà una lista incollata in un solo token
    kebab-case (spezzandole sui trattini), si scarta il resto. Duplicati rimossi
    preservando l'ordine."""
    out: list[str] = []
    for value in values:
        value = value.strip().strip(",;")
        if not value:
            continue
        if len(value) <= _MAX_LIST_ITEM_CHARS:
            candidati = [value]
        elif "-" in value:
            candidati = [p for p in value.split("-") if len(p) >= _MIN_TAG_CHARS]
        else:
            continue
        for c in candidati:
            if c and len(c) <= _MAX_LIST_ITEM_CHARS and c not in out:
                out.append(c)
    return out


def parse_semantic_metadata(raw: str) -> dict:
    """Frontmatter semantico dalla risposta del modello: solo i campi ammessi, liste
    normalizzate e troncate. Una risposta non parsabile non è un errore — si torna un dict
    vuoto e il documento tiene i metadati che core/intake.py sa già dedurre da sé."""
    try:
        data = yaml.safe_load(_strip_fence(raw))
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}

    out: dict = {}
    for key in _SEMANTIC_FIELDS:
        value = data.get(key)
        if value is None:
            continue
        if key in _LIST_FIELDS:
            if isinstance(value, str):
                value = [v.strip() for v in re.split(r"[,;]", value)]
            if not isinstance(value, list):
                continue
            items = _normalize_list_items(str(v).strip() for v in value)
            if items:
                out[key] = items[:_MAX_LIST_ITEMS]
        else:
            text = str(value).strip()
            if text:
                out[key] = text
    return out


def _max_output_ratio(window: str) -> float:
    """Tetto di lunghezza ammesso per la riscrittura di questa finestra.

    Non è una costante perché l'espansione lecita dipende dalla FORMA della fonte. Un
    albero di classi estratto da un PDF ("├─ Code : EnEsito", righe da 20 caratteri) che
    diventa una tabella `| Campo | Tipo | Descrizione |` cresce di 3-4× senza che una
    parola sia stata inventata: applicargli il tetto della prosa scarterebbe proprio le
    riscritture che questo passo esiste per produrre. La densità si misura sulla lunghezza
    media delle righe non vuote — l'indicatore più diretto di "elenco" contro "discorso"."""
    righe = [r for r in window.splitlines() if r.strip()]
    if not righe:
        return INTAKE_REFINE_MAX_OUTPUT_RATIO
    media = sum(len(r.strip()) for r in righe) / len(righe)
    return (INTAKE_REFINE_MAX_OUTPUT_RATIO_DENSE
            if media < INTAKE_REFINE_DENSE_LINE_CHARS
            else INTAKE_REFINE_MAX_OUTPUT_RATIO)


def strip_speculation(text: str) -> str:
    """Toglie le congetture del modello lasciando intatto tutto il resto.

    Un'ipotesi ("Descrizione (inferita)", "[Da verificare nel documento completo]") in un
    documento normativo si legge come un dato: chi interroga il RAG non ha modo di sapere
    che quella cella è un'invenzione. Meglio dichiarare il buco — che è esattamente ciò
    che il prompt chiedeva di fare. Deterministico e idempotente: nessuna parola che non
    sia una formula di incertezza viene rimossa."""
    text = _HEDGE_NOTE_RE.sub("", text)
    text = _HEADING_NOTE_RE.sub(r"\1", text)
    text = _PLACEHOLDER_RE.sub("—", text)
    text = _EMPHASIS_PLACEHOLDER_RE.sub(" — ", text)
    text = _HEDGE_PAREN_RE.sub("", text)
    text = _ORPHAN_MARKUP_CELL_RE.sub("| — ", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def _clean_refined_window(raw: str) -> str:
    """Ripulisce la riscrittura di una finestra: via i fence che avvolgono l'intera
    risposta (il modello a volte incarta tutto in ```markdown), via gli eventuali `#` di
    primo livello (appartengono al titolo del documento, non a una sua porzione) e via le
    congetture che il prompt vieta ma il modello ogni tanto produce lo stesso."""
    text = _strip_fence(raw).strip()
    text = re.sub(r"(?m)^#\s+", "## ", text)
    return strip_speculation(text).strip()


# ---------------------------------------------------------------------------
# Raffinazione
# ---------------------------------------------------------------------------
def _generate(prompt: str, generate) -> str:
    fn = generate or (lambda p: llm.generate(p, purpose=_REFINE_PURPOSE))
    try:
        return fn(prompt)
    except llm.LLMError as exc:
        raise RefineError(str(exc)) from exc


def refine_markdown(markdown: str, *, source_filename: str = "", generate=None,
                    window_chars: int = INTAKE_REFINE_WINDOW_CHARS) -> RefineResult:
    """Markdown grezzo (già convertito) → markdown strutturato + frontmatter semantico.

    Logica pura: nessuna lettura o scrittura su disco, `generate` iniettabile (i test non
    chiamano mai Ollama). La pulizia deterministica viene riapplicata qui prima di
    interrogare il modello: è idempotente, quindi su un documento già convertito con la
    pulizia attiva non cambia nulla, e su un markdown arrivato da altrove vale comunque."""
    cleaned = clean_markdown(markdown)
    if not cleaned:
        raise RefineError("documento vuoto dopo la pulizia: niente da raffinare")

    started = time.time()
    semantic = parse_semantic_metadata(
        _generate(build_metadata_prompt(cleaned[:_METADATA_HEAD_CHARS], source_filename), generate)
    )

    h1 = _H1_RE.search(cleaned)
    titolo = semantic.get("title") or (h1.group(1).strip() if h1 else Path(source_filename).stem)
    semantic["title"] = titolo

    # Il titolo `#` non entra nelle finestre: lo riscriviamo noi una volta sola in cima,
    # dal titolo semantico (che è più leggibile del nome file usato come fallback da S1).
    body_source = _H1_RE.sub("", cleaned, count=1).strip() if h1 else cleaned
    windows = split_windows(body_source, window_chars)

    sezioni: list[str] = []
    troppo_corte = troppo_lunghe = 0
    for i, window in enumerate(windows):
        refined = _clean_refined_window(
            _generate(build_refine_prompt(window, titolo=titolo, indice=i, totale=len(windows)),
                      generate)
        )
        # Guardrail sulla lunghezza, nei due sensi — una riscrittura fedele è lunga
        # all'incirca quanto l'originale, e uscire dalla forbice segnala i due modi in cui
        # questo passo può tradire il documento:
        # · troppo CORTA → il modello ha riassunto, e un riassunto perde requisiti;
        # · troppo LUNGA → il modello ha commentato o ipotizzato invece di riformattare
        #   (su una fonte frammentaria tende a riempire i buchi con congetture).
        # In entrambi i casi si tiene il testo pulito di quella finestra: grezzo, ma è
        # esattamente ciò che c'era scritto.
        if len(refined) < len(window) * INTAKE_REFINE_MIN_OUTPUT_RATIO:
            sezioni.append(window)
            troppo_corte += 1
        elif len(refined) > len(window) * _max_output_ratio(window):
            sezioni.append(window)
            troppo_lunghe += 1
        else:
            sezioni.append(refined)

    body = "\n\n".join(s for s in sezioni if s.strip())
    document = f"# {titolo}\n\n{body}\n"
    # I due contatori separati non sono un dettaglio: dicono COME regolare la forbice.
    # Molte finestre "troppo corte" → il modello riassume, alza min_output_ratio o
    # accettalo abbassandolo; molte "troppo lunghe" → il modello commenta, e il documento
    # è probabilmente una fonte frammentaria (diagrammi, tabelle sfaldate dal PDF) su cui
    # la raffinazione rende poco.
    stats = {
        "windows": len(windows),
        "windows_kept_raw": troppo_corte + troppo_lunghe,
        "windows_too_short": troppo_corte,
        "windows_too_long": troppo_lunghe,
        "chars_in": len(cleaned),
        "chars_out": len(document),
        "elapsed_seconds": round(time.time() - started, 1),
    }
    return RefineResult(markdown=document, semantic=semantic, stats=stats)


# ---------------------------------------------------------------------------
# Raffinazione di un documento in staging (I/O + journal)
# ---------------------------------------------------------------------------
def refine_staged_document(doc_id: str, *, base_dir: str | Path | None = None,
                           generate=None) -> dict:
    """Raffina un documento in stato 'staged' e ne aggiorna l'entry del journal.

    Il markdown grezzo NON viene toccato: la versione raffinata si scrive accanto
    (`<id>.refined.md`) e l'entry punta a quest'ultima come markdown corrente, tenendo il
    grezzo in `files.markdown_raw` (preview e approve non sanno nulla di tutto questo:
    leggono `files.markdown` come hanno sempre fatto). Il frontmatter semantico dedotto
    finisce in `semantic`, che approve fonde nel frontmatter finale.

    Rieseguibile: un secondo refine riparte SEMPRE dal grezzo, mai dal raffinato — così
    riprovare dopo un risultato insoddisfacente non impila riscritture su riscritture."""
    paths = intake.ensure_staging_dirs(base_dir)
    entry = intake.require_staged(doc_id, base_dir)

    files = dict(entry.get("files") or {})
    raw_name = files.get("markdown_raw") or files.get("markdown")
    if not raw_name:
        raise RefineError(f"nessun markdown in staging per {doc_id}")
    raw_path = paths["docs"] / raw_name
    try:
        raw_markdown = raw_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefineError(f"markdown di staging non leggibile per {doc_id}: {exc}") from exc

    source_filename = (entry.get("metadata") or {}).get("source_filename") or entry.get("filename", "")
    result = refine_markdown(raw_markdown, source_filename=source_filename, generate=generate)

    # La raffinazione dura minuti: nel frattempo il documento può essere stato approvato o
    # rifiutato. Scrittura e journal sotto lo stesso writer lock di approve/reject, con lo
    # stato ricontrollato: un risultato arrivato tardi si scarta, non riapre il documento.
    with writer_lock(timeout_seconds=30):
        entry = intake.require_staged(doc_id, base_dir)
        files = dict(entry.get("files") or {})
        refined_path = paths["docs"] / f"{doc_id}.refined.md"
        refined_path.write_text(result.markdown, encoding="utf-8")

        files["markdown_raw"] = raw_name
        files["markdown"] = refined_path.name
        record = {
            **entry,
            "files": files,
            "semantic": result.semantic,
            "refined_at": _now_iso(),
            "refine": result.stats,
        }
        intake._append_journal(paths, record)
    return record
