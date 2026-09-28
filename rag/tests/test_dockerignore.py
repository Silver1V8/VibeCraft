"""Verifica le regole chiave del `.dockerignore` alla radice del repository, cioè cosa
finisce nel contesto di build Docker (`COPY rag/ ...` nel Dockerfile).

Il file NON ha a disposizione un motore .dockerignore "vero" (nessuna dipendenza esterna
tipo pathspec è installata, e non va aggiunta a uv.lock): questo test ne reimplementa uno
fedele a `github.com/moby/patternmatcher` v0.6.1 — la libreria che BuildKit usa davvero —
seguendone il codice sorgente (`ignorefile.ReadAll` per il parsing, `PatternMatcher.New` +
`Pattern.compile` + `MatchesOrParentMatches` per il matching), non un'approssimazione in
stile .gitignore. Tre punti in cui Docker si comporta DIVERSAMENTE da .gitignore, verificati
qui contro il vero pacchetto Go `moby/patternmatcher` v0.6.1 (verifica manuale, non inclusa
in questo repo):

1. NIENTE semantica "solo directory" per lo slash finale: `ignorefile.ReadAll` applica
   `filepath.Clean` a ogni pattern PRIMA di interpretarlo, che rimuove lo slash finale —
   quindi `x/*/` diventa `x/*` e matcha qualunque voce a quel livello, file compresi. Una
   versione precedente di questo `.dockerignore` usava `rag/eval/results/*/` pensando
   restasse fuori `history.jsonl` (un file, non una directory): verificato col matcher
   vero che invece lo escludeva anche lui, rompendo lo storico dietro la pagina /eval.
2. La negazione `!pattern` è supportata con la stessa semantica di .gitignore ("vince
   l'ultimo pattern che matcha", processati in ordine di riga) — qui serve per il
   `.dockerignore` attuale, che esclude `rag/eval/results/` per intero e poi reincude
   `!rag/eval/results/history.jsonl`.
3. `**` assorbe lo slash successivo se presente ed è equivalente, ovunque compaia nel
   pattern, a "zero o più segmenti di percorso" — non solo in testa (`**/x`) ma anche in
   mezzo (`code/**/bin`).

`_is_excluded` sotto riproduce `MatchesOrParentMatches`: un pattern che matcha un ANTENATO
(una directory) di un percorso esclude tutto ciò che ci sta sotto, indipendentemente da come
il pattern è scritto — è così che Docker salta di attraversare una directory ignorata."""
import posixpath
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO_ROOT / ".dockerignore"

_ESCAPE = set(".+()|{}$")  # stessi caratteri di patternmatcher.shouldEscape (Go)


def _pattern_regex(cleaned: str) -> re.Pattern:
    """Traduce UN pattern già ripulito (senza '!', dopo filepath.Clean) in una regex,
    riproducendo Pattern.compile: '*' non attraversa '/', '?' e' un carattere (non '/'),
    '**' e' zero o piu' segmenti di percorso e assorbe lo slash successivo se presente,
    il resto e' letterale (con escape dei metacaratteri regex che servono da letterali)."""
    out = ["^"]
    i, n = 0, len(cleaned)
    while i < n:
        ch = cleaned[i]
        if ch == "*" and i + 1 < n and cleaned[i + 1] == "*":
            i += 2
            if i < n and cleaned[i] == "/":
                i += 1
            out.append(".*" if i >= n else "(?:.*/)?")
            continue
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch in _ESCAPE:
            out.append("\\" + ch)
        else:
            out.append(ch)
        i += 1
    out.append("$")
    return re.compile("".join(out))


def _parse_patterns(text: str) -> list[tuple[re.Pattern, bool]]:
    """Una entry per riga non vuota/non commento: (regex, negato). Riproduce
    ignorefile.ReadAll: commento solo se la riga GREZZA (non trimmata) inizia per '#',
    poi trim, poi '!' iniziale, poi filepath.Clean (qui posixpath.normpath, il repo non
    ha percorsi Windows) e lo strip di un eventuale '/' iniziale singolo."""
    patterns = []
    for raw in text.splitlines():
        if raw.startswith("#"):
            continue
        line = raw.strip()
        if not line:
            continue
        negato = line.startswith("!")
        if negato:
            line = line[1:].strip()
        if not line:
            continue
        cleaned = posixpath.normpath(line)
        if len(cleaned) > 1 and cleaned.startswith("/"):
            cleaned = cleaned[1:]
        patterns.append((_pattern_regex(cleaned), negato))
    return patterns


def _pattern_matches_path(regex: re.Pattern, rel_path: str) -> bool:
    """Vero se il pattern combacia col percorso intero O con uno qualsiasi dei suoi
    antenati (directory) — MatchesOrParentMatches, non la Matches deprecata che ne
    controlla solo uno."""
    if regex.match(rel_path):
        return True
    prefix = ""
    for parte in rel_path.split("/")[:-1]:
        prefix = f"{prefix}/{parte}" if prefix else parte
        if regex.match(prefix):
            return True
    return False


def _is_excluded(rel_path: str, patterns: list[tuple[re.Pattern, bool]]) -> bool:
    """Applica TUTTI i pattern in ordine: ogni match (che sia un'esclusione o una
    negazione '!') aggiorna lo stato — l'ultimo che matcha vince. Equivalente al ciclo
    con lo skip di MatchesOrParentMatches: quello skip è solo un'ottimizzazione (un
    match che non cambierebbe lo stato è per costruzione un no-op), verificato uguale
    al pacchetto Go vero su tutti i casi sotto, negazione compresa."""
    escluso = False
    for regex, negato in patterns:
        if _pattern_matches_path(regex, rel_path):
            escluso = not negato
    return escluso


@pytest.fixture(scope="module")
def patterns():
    return _parse_patterns(DOCKERIGNORE.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


# --------------------------------------------------------------------------
# Deve essere escluso: le run di eval (in particolare evidence/, ~119 MB) e rag/adr/.
#
# Percorsi SINTETICI, non file reali sotto rag/eval/results/ o rag/adr/: quei due alberi
# finiranno sotto archive/ in un intervento successivo, e un test che dipende dalla loro
# presenza/struttura attuale si romperebbe per un motivo che non ha a che fare col
# .dockerignore. La regola che si verifica è generale ("qualunque run sotto
# rag/eval/results/, evidence compresa, resta fuori dall'immagine tranne history.jsonl";
# "qualunque file sotto rag/adr/ resta fuori"), non la lista dei file di oggi.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel_path", [
    "rag/eval/results/pilot_docling_sourcefix_20260909/evidence/build_candidates.py.txt",
    "rag/eval/results/sidecar_readers_20260921/evidence/reader_experiment.py",
    "rag/eval/results/run_x/evidence/a.json",
    "rag/eval/results/run_x/evidence/nested/deep/file.bin",
])
def test_eval_results_evidence_esclusa(patterns, rel_path):
    assert _is_excluded(rel_path, patterns), f"{rel_path} non e' escluso"


@pytest.mark.parametrize("rel_path", [
    "rag/eval/results/run_x",
    "rag/eval/results/run_x/manifest/summary.json",
    "rag/eval/results/run_x/sandbox/README.md",
    "rag/eval/results/bench_20260721T084815Z.json",  # file diretto in results/, non solo evidence/
    "rag/eval/results/authority_calibrated.yaml",
])
def test_eval_results_run_intera_esclusa(patterns, rel_path):
    """Non solo evidence/: l'intera sottocartella di ogni run, e anche i file diretti in
    results/ diversi da history.jsonl (output di eval.run/calibrate_*, non letti a runtime)."""
    assert _is_excluded(rel_path, patterns), f"{rel_path} non e' escluso"


def test_eval_results_history_jsonl_non_escluso(patterns):
    """rag/core/eval_history.py legge SOLO questo file (append/load), dietro la pagina
    /eval e GET /api/eval-history (rag/api/routes_health.py): deve restare nell'immagine.
    È il caso che 'rag/eval/results/*/' (slash finale, semantica da .gitignore) sbagliava:
    filepath.Clean lo riduce a 'rag/eval/results/*', che matcha ANCHE i file diretti in
    results/, history.jsonl incluso — verificato contro moby/patternmatcher v0.6.1 vero."""
    assert not _is_excluded("rag/eval/results/history.jsonl", patterns)


@pytest.mark.parametrize("rel_path", [
    "rag/adr/AUDIT.md",
    "rag/adr/DISTRIBUTION.md",
    "rag/adr/0002-prompts/x.md",
    "rag/adr/horizontal-bench/preflight-20260928/y.json",
])
def test_adr_escluso(patterns, rel_path):
    assert _is_excluded(rel_path, patterns), f"{rel_path} non e' escluso"


# --------------------------------------------------------------------------
# Non deve essere escluso: cio' che il server legge davvero a runtime. Qui SI usano file
# reali — templates/static/prompts/core non vanno in archive/, sono codice/asset del
# prodotto e restano stabili.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("sottocartella", ["templates", "static", "prompts", "core"])
def test_cartelle_runtime_non_escluse(patterns, sottocartella):
    base = REPO_ROOT / "rag" / sottocartella
    file_veri = [f for f in base.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
    assert len(file_veri) > 0, f"rag/{sottocartella}/ e' vuota, il test non verifica nulla"
    esclusi = [f for f in file_veri if _is_excluded(_rel(f), patterns)]
    assert esclusi == [], (
        f"rag/{sottocartella}/ dovrebbe restare nell'immagine ma questi file sono "
        f"esclusi: {[_rel(f) for f in esclusi]}"
    )


def test_eval_history_py_non_escluso(patterns):
    """Il CODICE che produce/legge eval/results/ resta: solo i RISULTATI sono di
    sviluppo, lo script che li scrive e legge e' sorgente dell'applicazione."""
    script = REPO_ROOT / "rag/core/eval_history.py"
    assert script.is_file()
    assert not _is_excluded(_rel(script), patterns)


# --------------------------------------------------------------------------
# Regressioni note: pattern preesistenti che devono continuare a funzionare, e la
# normalizzazione Docker (slash finale ininfluente sul match) verificata esplicitamente.
# --------------------------------------------------------------------------

def test_venv_e_database_restano_esclusi(patterns):
    assert _is_excluded("rag/.venv/lib/python3.14/site-packages/x.py", patterns)
    assert _is_excluded("rag/database/qdrant/snapshot.bin", patterns)


@pytest.mark.parametrize("rel_path", [
    "archive/eval-results/run_x/evidence/a.json",
    "archive/adr/sidecar-work/a.md",
    "archive/README.md",
])
def test_archivio_escluso(patterns, rel_path):
    """archive/ è materiale storico: fuori dal contesto di build (il Dockerfile non lo
    copia comunque, ma il contesto è la radice del repo)."""
    assert _is_excluded(rel_path, patterns)


def test_slash_finale_equivale_a_pattern_senza_slash():
    """filepath.Clean toglie lo slash finale prima del match: 'x/*/' ed 'x/*' devono
    produrre ESATTAMENTE lo stesso risultato, su un file quanto su una directory — non
    c'e' la semantica 'solo directory' di .gitignore. Verificato anche col matcher Go
    vero (moby/patternmatcher v0.6.1)."""
    con_slash = _parse_patterns("rag/eval/results/*/\n")
    senza_slash = _parse_patterns("rag/eval/results/*\n")
    casi = [
        "rag/eval/results/history.jsonl",           # file diretto
        "rag/eval/results/run_x",                    # directory
        "rag/eval/results/run_x/evidence/a.json",    # dentro una directory che matcha
    ]
    for caso in casi:
        assert _is_excluded(caso, con_slash) == _is_excluded(caso, senza_slash), caso


def test_negazione_ultimo_pattern_che_matcha_vince():
    """Semantica di negazione generale (non solo sul .dockerignore reale): una riga '!'
    successiva re-include cio' che una esclusione precedente aveva escluso, ma una
    esclusione ANCORA successiva puo' ri-escluderlo di nuovo — l'ordine conta."""
    patterns = _parse_patterns(
        "a/\n"
        "!a/keep.txt\n"
        "a/keep.txt\n"  # ri-esclude: l'ultimo pattern che matcha vince
    )
    assert _is_excluded("a/other.txt", patterns)
    assert _is_excluded("a/keep.txt", patterns)  # l'ultima riga la ri-esclude


def test_parse_patterns_riconosce_la_negazione(patterns):
    """Il .dockerignore attuale usa '!' (rag/eval/results/ + !.../history.jsonl): il
    parser deve restituirla come tale, non come un pattern letterale che inizia per '!'."""
    righe_negate = [r for r in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
                    if r.strip().startswith("!")]
    assert righe_negate, "il .dockerignore non usa più '!': questo test va rivisto"
    assert any(negato for _, negato in patterns)
