"""Normalizzazione SINTATTICA degli scenari BDD di uno spec.md.

Perché esiste. Il formato degli scenari è uno solo e non negoziabile (fonte normativa:
templates/template_spec_funzionale.md §5): un blocco ```gherkin per scenario, riga
`SCENARIO: S<nn> - <titolo>`, keyword GIVEN/WHEN/THEN/AND in inglese maiuscolo, passi
indentati di 2 spazi. Il prompt lo insegna, ma l'LLM locale sbaglia in modo sistematico
proprio la parte meccanica — tiene tutti gli scenari in un blocco solo, oppure scrive `E`
al posto di `AND` — e nessuna riformulazione del prompt lo corregge in modo stabile. Quella
parte è pura sintassi: si ricostruisce in modo deterministico, e questo modulo lo fa.

Che cosa NON fa, ed è il punto: non inventa contenuto. Non scrive scenari, non completa un
GIVEN senza WHEN, non spezza un passo lungo in due asserzioni, non deduce un titolo da un
testo che non ce l'ha. Riscrive la FORMA di ciò che c'è già; tutto ciò che riguarda la
SOSTANZA (un solo GIVEN per scenario, presenza del caso negativo, assenza di dettagli
implementativi) resta al validatore, che deve poter ancora bocciare. Se la struttura non è
recuperabile senza indovinare, solleva SpecNormalizationError invece di tirare a indovinare.

Il testo che non è né una riga di scenario né un passo (titoli del documento, prose,
tabelle, frontmatter) passa attraverso invariato: normalizzare uno spec non deve mai
perderne il contenuto.

Modulo PURO: nessuna dipendenza dal resto di rag/, nessun I/O. Riusato sia dalla pipeline
(dopo la generazione) sia dallo script di migrazione delle spec normative già scritte.
"""
import re

__all__ = ["SpecNormalizationError", "normalize_spec", "parse_scenarios", "Scenario"]


class SpecNormalizationError(ValueError):
    """La struttura dello spec non è ricostruibile senza inventare contenuto: uno scenario
    senza titolo ricavabile, uno scenario senza passi, un documento senza scenari. Errore
    esplicito e non silenzioso — un normalizzatore che indovina è peggio di uno che si ferma,
    perché produce uno spec plausibile e sbagliato."""


# --- Vocabolario ----------------------------------------------------------------------
# Le keyword ammesse in ingresso, con la forma canonica in uscita. L'italiano è qui perché
# è ciò che il modello produce quando perde il formato (e ciò che contengono gli spec
# scritti prima del formato unico), non perché sia una forma ammessa.
_KEYWORD_ALIASES = {
    "GIVEN": "GIVEN", "DATO CHE": "GIVEN", "DATO": "GIVEN",
    "PREMESSO CHE": "GIVEN", "PREMESSO": "GIVEN",
    "WHEN": "WHEN", "QUANDO": "WHEN",
    "THEN": "THEN", "ALLORA": "THEN",
    "AND": "AND", "E": "AND", "ED": "AND", "MA": "AND", "BUT": "AND",
}
# Deliberatamente ASSENTI le altre flessioni del Gherkin italiano (`Data`, `Date`, `Dati`):
# sono parole comunissime in un documento tecnico e, ammesse come keyword, trasformavano
# righe di frontmatter e di prosa in passi BDD (`date: "2026-07-12"` diventava un GIVEN).
# Negli spec di questo repo compaiono solo Dato/Quando/Allora/E, quindi il costo è nullo.
# Ordinate per lunghezza decrescente: "DATO CHE" deve vincere su "DATO", altrimenti il
# passo diventerebbe «GIVEN che ...».
_KEYWORDS_SORTED = sorted(_KEYWORD_ALIASES, key=len, reverse=True)
_KEYWORDS_ALT = "|".join(re.escape(k) for k in _KEYWORDS_SORTED)

# Un passo, in tutte le decorazioni con cui arriva: "  GIVEN x", "**GIVEN**: x",
# "*   **Dato che** x", "- WHEN x", "1. THEN x". La decorazione viene scartata, il testo
# tenuto così com'è.
_STEP_RE = re.compile(
    r"^\s*"
    r"(?:[-*+•]\s*|\d+[.)]\s*)?"          # bullet o numerazione di lista
    r"[*_`]{0,3}\s*"                       # grassetto/corsivo/code di apertura
    rf"(?P<kw>{_KEYWORDS_ALT})"
    r"\s*[*_`]{0,3}"                       # chiusura dell'enfasi
    r"\s*[:.\-–]?\s+"                      # separatore facoltativo
    r"(?P<text>\S.*?)\s*$",
    re.IGNORECASE,
)

# Riga-titolo nel formato di destinazione: "SCENARIO: S01 - Titolo" (il numero viene
# comunque riassegnato, ma va riconosciuto per l'idempotenza).
_SCENARIO_NUMBERED_RE = re.compile(
    r"^\s*SCENARIO\s*:\s*S\d+\s*[-–—]\s*(?P<title>\S.*?)\s*$", re.IGNORECASE)
# Riga-titolo nelle forme che il modello produce quando perde il formato, o che hanno gli
# spec vecchi: "Scenario: Titolo", "### Scenario 3: Titolo", "**Scenario S01: Titolo**",
# "#### Titolo" preceduto da passi.
_SCENARIO_LOOSE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?"                  # heading markdown facoltativo
    r"[*_]{0,3}\s*"
    r"SCENARIO\s*(?:N[.°]?\s*)?(?:S?\d+)?\s*[:.\-–]\s*"
    r"(?P<title>\S.*?)"
    r"\s*[*_]{0,3}\s*$",
    re.IGNORECASE,
)
# Heading markdown generico: candidato titolo per un gruppo di passi che non ha una riga
# "Scenario:" propria (è la forma di LA1: "### Scenario S01: ..." rientra sopra, ma
# "### Invio notifica email" no).
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(?P<title>\S.*?)\s*$")
_BOLD_LINE_RE = re.compile(r"^\s*\*\*(?P<title>\S.*?)\*\*\s*:?\s*$")

_FENCE_RE = re.compile(r"^\s*(?:`{3,}|~{3,})\s*\w*\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+\S")

# Prefissi di numerazione da togliere dal titolo estratto: "S01 - ", "1: ", "Scenario 2 - ".
_TITLE_NUMBER_PREFIX_RE = re.compile(
    r"^(?:scenario\s*)?(?:n[.°]?\s*)?S?\d+\s*[:.\-–—]\s*", re.IGNORECASE)


class Scenario:
    """Uno scenario riconosciuto: il titolo (senza numerazione) e i passi già canonizzati
    come coppie (keyword, testo). `line` è la riga 1-based da cui parte e `step_lines` quelle
    dei singoli passi, nel testo di ORIGINE: servono al validatore per dire dove correggere."""

    __slots__ = ("title", "steps", "line", "step_lines")

    def __init__(self, title: str, steps: list[tuple[str, str]], line: int,
                 step_lines: list[int] | None = None):
        self.title = title
        self.steps = steps
        self.line = line
        self.step_lines = step_lines if step_lines is not None else []

    def __repr__(self) -> str:      # pragma: no cover - solo diagnostica
        return f"Scenario({self.title!r}, {len(self.steps)} passi, riga {self.line})"


def _frontmatter_end(lines: list[str]) -> int:
    """Indice della prima riga DOPO il frontmatter YAML, 0 se non c'è. Frontmatter è solo un
    blocco `---` che apre il file (la prima riga non vuota): i `---` più avanti nel documento
    sono righe orizzontali di markdown, e trattarle da delimitatori mangerebbe mezzo file."""
    prima = next((i for i, l in enumerate(lines) if l.strip()), None)
    if prima is None or lines[prima].strip() != "---":
        return 0
    for i in range(prima + 1, len(lines)):
        if lines[i].strip() == "---":
            return i + 1
    return 0        # frontmatter mai chiuso: non è frontmatter


def _righe_di_blocchi_non_bdd(lines: list[str]) -> set[int]:
    """Indici delle righe che stanno dentro (o delimitano) un blocco recintato che NON
    contiene BDD: ```sql, ```json, ```bash e simili.

    Quei blocchi sono contenuto del documento come qualunque altro e devono attraversare la
    normalizzazione intatti, recinzione compresa. Senza questo filtro la riga ```sql veniva
    scartata insieme a tutte le altre recinzioni — la sua fine, e con lei il fatto stesso che
    quel testo fosse SQL."""
    dentro: set[int] = set()
    apertura: int | None = None
    corpo: list[str] = []
    for idx, raw in enumerate(lines):
        if not _FENCE_RE.match(raw):
            if apertura is not None:
                corpo.append(raw)
            continue
        if apertura is None:
            apertura, corpo = idx, []
            continue
        # Chiusura. Il blocco è BDD se contiene una riga-scenario o un passo con una keyword
        # che APRE qualcosa (GIVEN/WHEN/THEN). Un `AND` da solo non basta e non è un dettaglio:
        # un blocco ```sql è pieno di righe che cominciano per AND (`AND email NOT LIKE …`),
        # e contarle come BDD faceva sparire la recinzione — cioè il fatto stesso che quel
        # testo fosse SQL — trasformando le clausole della query in passi di scenario.
        def apre_bdd(riga: str) -> bool:
            if _match_title(riga) is not None:
                return True
            passo = _match_step(riga)
            return passo is not None and passo[0] != "AND"

        e_bdd = any(apre_bdd(r) for r in corpo)
        if not e_bdd:
            dentro.update(range(apertura, idx + 1))
        apertura, corpo = None, []
    return dentro


def _clean_title(raw: str) -> str:
    """Titolo ripulito da numerazione e decorazioni markdown residue. Il TESTO non si tocca:
    si tolgono solo il prefisso numerico (che viene riassegnato) e l'enfasi."""
    title = raw.strip().strip("*_`").strip()
    title = _TITLE_NUMBER_PREFIX_RE.sub("", title).strip()
    return title.rstrip(":").strip()


def _match_step(line: str) -> tuple[str, str] | None:
    """(keyword canonica, testo) se la riga è un passo, altrimenti None."""
    m = _STEP_RE.match(line)
    if not m:
        return None
    return _KEYWORD_ALIASES[m.group("kw").upper()], m.group("text")


def _match_title(line: str) -> str | None:
    """Titolo se la riga è una riga-scenario esplicita ("SCENARIO: ...", "Scenario 3: ...").
    Gli heading generici NON entrano qui: sono solo candidati, vedi parse_scenarios."""
    for regex in (_SCENARIO_NUMBERED_RE, _SCENARIO_LOOSE_RE):
        m = regex.match(line)
        if m:
            title = _clean_title(m.group("title"))
            return title or None
    return None


def parse_scenarios(text: str) -> list[Scenario]:
    """Gli scenari contenuti nel testo, nell'ordine in cui compaiono. Non ricostruisce
    niente: serve a chi vuole ragionare sugli scenari (il validatore) senza reimplementare
    il riconoscimento. Solleva SpecNormalizationError alle stesse condizioni di
    normalize_spec."""
    return _parse(text)[0]


def _parse(text: str) -> tuple[list[Scenario], list[tuple[int, str]]]:
    """Motore condiviso: restituisce (scenari, righe-non-scenario).

    Le righe non-scenario sono coppie (indice_riga, testo) e servono a normalize_spec per
    riemettere invariato tutto ciò che non è BDD. Le righe di recinzione non compaiono in
    nessuno dei due: la recinzione viene ricostruita, mai riusata."""
    lines = text.splitlines()
    scenari: list[Scenario] = []
    passthrough: list[tuple[int, str]] = []
    fine_frontmatter = _frontmatter_end(lines)
    non_bdd = _righe_di_blocchi_non_bdd(lines)

    # Titolo "in attesa": l'ultimo heading/riga in grassetto incontrato, candidato a fare da
    # titolo per il prossimo gruppo di passi che non abbia una riga-scenario esplicita.
    pending_title: str | None = None
    pending_title_idx: int | None = None
    # Scenario in costruzione.
    corrente: Scenario | None = None
    # Ultima riga era un passo: solo allora una riga successiva senza keyword può esserne
    # la continuazione (un passo spezzato su più righe).
    dopo_un_passo = False

    def chiudi() -> None:
        nonlocal corrente, dopo_un_passo
        if corrente is not None:
            if not corrente.steps:
                raise SpecNormalizationError(
                    f"Scenario senza passi alla riga {corrente.line}: «{corrente.title}». "
                    "Non posso completarlo senza inventare contenuto.")
            scenari.append(corrente)
            corrente = None
        dopo_un_passo = False

    def chiudi_se_ha_passi() -> None:
        """Chiude lo scenario in corso solo se ha già dei passi. Fra la riga-titolo e il primo
        GIVEN possono stare una riga di prosa che ne descrive l'intento o l'apertura di un
        blocco recintato: lì chiudere darebbe «scenario senza passi» su un documento sano."""
        nonlocal dopo_un_passo
        if corrente is None or corrente.steps:
            chiudi()
        dopo_un_passo = False

    for idx, raw in enumerate(lines):
        if idx in non_bdd:
            # Blocco recintato che non contiene BDD (```sql, ```json…): contenuto del
            # documento, passa intatto con la sua recinzione.
            chiudi_se_ha_passi()
            passthrough.append((idx, raw))
            continue

        if idx < fine_frontmatter:
            # Frontmatter YAML: metadati, mai scenari. Passa invariato senza nemmeno essere
            # esaminato — è la regione dove il riconoscimento dei passi produce i falsi
            # positivi peggiori, perché è fatta di righe `chiave: valore`.
            passthrough.append((idx, raw))
            continue

        if _FENCE_RE.match(raw):
            # La recinzione non viene riemessa: la struttura si ricostruisce. Chiude però lo
            # scenario in corso, perché nessuno scenario scavalca un confine di blocco — e
            # soprattutto perché una riga rientrata SUBITO DOPO una recinzione (un commento
            # appeso al blocco) non deve poter essere scambiata per la continuazione
            # dell'ultimo passo: era il caso che rompeva l'idempotenza, con i commenti fuori
            # dal blocco alla prima passata e inglobati nel passo alla seconda.
            # NON è un ritorno a fidarsi delle recinzioni: gli scenari li delimita la riga
            # SCENARIO, ed è per questo che un blocco unico con dentro sette scenari continua
            # a produrne sette.
            chiudi_se_ha_passi()
            continue

        stripped = raw.strip()

        titolo = _match_title(raw)
        if titolo is not None:
            chiudi()
            corrente = Scenario(titolo, [], idx + 1)
            pending_title = pending_title_idx = None
            continue

        passo = _match_step(raw)
        if passo is not None and passo[0] == "AND" and (corrente is None or not corrente.steps):
            # Una congiunzione non può APRIRE uno scenario: `AND` continua qualcosa, e se non
            # c'è niente da continuare non è un passo. Senza questa guardia una riga di prosa
            # italiana che comincia per «E » (frequentissima) diventava un passo BDD, e con
            # essa si portava dentro l'intero paragrafo.
            passo = None
        if passo is not None:
            if corrente is None:
                # Passi senza una riga-scenario: l'heading immediatamente precedente è il
                # titolo (forma degli spec vecchi). Senza heading non c'è titolo da cui
                # partire, e inventarne uno sarebbe scrivere contenuto.
                if pending_title is None:
                    raise SpecNormalizationError(
                        f"Passo BDD alla riga {idx + 1} senza uno scenario a cui appartenere "
                        f"(«{stripped[:60]}»): manca una riga `SCENARIO: ...` o un titolo che "
                        "la preceda. Non posso attribuirgli un titolo senza inventarlo.")
                corrente = Scenario(pending_title, [], (pending_title_idx or idx) + 1)
                pending_title = pending_title_idx = None
            corrente.steps.append(passo)
            corrente.step_lines.append(idx + 1)
            dopo_un_passo = True
            continue

        if not stripped:
            dopo_un_passo = False
            if corrente is None:
                passthrough.append((idx, raw))
            continue

        if corrente is not None and dopo_un_passo and (
                raw[:1] in (" ", "\t") or _LIST_ITEM_RE.match(raw)):
            # Continuazione di un passo: una riga rientrata (passo spezzato a capo) oppure un
            # elemento di elenco che ne dettaglia il contenuto («AND una RICHIESTA con: / -
            # id: "req-123" / - stato: "APPROVATA"», la forma dello spec LA1). Si ricongiunge,
            # perché il formato vuole un passo per riga. NB: ricongiungere è layout; spezzare
            # una frase composta in due asserzioni sarebbe riscrivere il contenuto, e non si
            # fa qui.
            kw, testo = corrente.steps[-1]
            corrente.steps[-1] = (kw, f"{testo} {stripped}")
            continue

        # Riga di prosa: chiude lo scenario in corso (se ha passi) e torna nel flusso del
        # documento.
        chiudi_se_ha_passi()
        heading = _HEADING_RE.match(raw) or _BOLD_LINE_RE.match(raw)
        if heading:
            pending_title = _clean_title(heading.group("title"))
            pending_title_idx = idx
        passthrough.append((idx, raw))

    chiudi()
    if not scenari:
        raise SpecNormalizationError(
            "Nessuno scenario BDD riconosciuto nel documento: non c'è niente da normalizzare "
            "e non invento scenari.")
    return scenari, passthrough


def render_scenario(scenario: Scenario, numero: int) -> str:
    """Il blocco recintato di uno scenario, nel formato di destinazione."""
    righe = [f"SCENARIO: S{numero:02d} - {scenario.title}"]
    righe += [f"  {kw} {testo}" for kw, testo in scenario.steps]
    return "```gherkin\n" + "\n".join(righe) + "\n```"


def normalize_spec(text: str) -> str:
    """Lo spec riscritto nel formato obbligatorio: un blocco ```gherkin per scenario, riga
    `SCENARIO: S<nn> - <titolo>` con numerazione progressiva, keyword canoniche in inglese
    maiuscolo, passi indentati di 2 spazi e uno per riga.

    Tutto ciò che non è uno scenario (titoli, prosa, tabelle, frontmatter) resta dov'è e
    com'è. Idempotente: normalize_spec(normalize_spec(x)) == normalize_spec(x).

    Solleva SpecNormalizationError se la struttura non è ricostruibile senza inventare."""
    scenari, passthrough = _parse(text)

    # Ricomposizione per posizione: le righe di passthrough tornano al loro posto, e ogni
    # scenario viene emesso dove cominciava. Così l'ordine del documento è preservato senza
    # che il normalizzatore debba decidere dove va qualcosa.
    blocchi: list[tuple[int, str]] = [(riga, testo) for riga, testo in passthrough]
    for n, scenario in enumerate(scenari, start=1):
        blocchi.append((scenario.line - 1, render_scenario(scenario, n)))
    blocchi.sort(key=lambda b: b[0])

    out: list[str] = []
    for _, testo in blocchi:
        if testo.startswith("```gherkin") and out and out[-1].strip():
            out.append("")          # una riga vuota separa sempre due blocchi consecutivi
        out.append(testo)

    # Coda: niente righe vuote in fondo, un solo newline finale.
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out) + "\n"
