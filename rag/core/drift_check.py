"""Orchestrazione del check drift (pipeline, step 4): lettura di Canvas/Spec e del codice
della change, lotti entro la finestra di contesto, chiamate LLM, verdetto. La logica pura
(prompt, parsing, verifica deterministica dei rilievi) vive in core/drift.py.

Estratto da core/indexing.py, che re-esporta check_drift per compatibilità. I monkeypatch
su percorsi (CHANGES_DIR, CODE_DIR) e sui tetti _DRIFT_* vanno applicati su questo modulo."""
import json
import logging
import re
from pathlib import Path

from code_index import CODE_EXTS, collect_code_symbols
from core import drift, llm
from core.config import CHANGES_DIR, CODE_DIR, CODE_EXCLUDED_DIRS
from core.pipeline import InvalidFeatureNameError, resolve_feature_dir

logger = logging.getLogger(__name__)


def _load_dev_type(feature_dir: Path) -> str:
    """Legge il tipo di sviluppo salvato in <feature_dir>/meta.json, se presente.
    `feature_dir` è già il percorso risolto (e validato) della feature, non più
    una stringa da ri-comporre: evita una seconda concatenazione non verificata."""
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("dev_type", "")
    except Exception:
        return ""


# Tetto sui caratteri di codice per LOTTO del check drift (il codice non è più troncato:
# eccedenze e file grandi finiscono in lotti successivi). Il tetto effettivo è il minimo
# tra questo valore e quanto resta della finestra di contesto di Ollama dopo Canvas,
# Spec e istruzioni (vedi _drift_code_budget).
_DRIFT_MAX_CODE_CHARS = 40_000
# Numero massimo di lotti (= chiamate LLM di revisione, più una di copertura): oltre,
# i file restano fuori e vengono DICHIARATI come non analizzati, nel prompt e nel report.
_DRIFT_MAX_BATCHES = 6
# Tetto ai riesami mirati (una chiamata LLM breve per rilievo): i rilievi oltre il tetto
# restano nel verdetto, marcati come non riesaminati.
_DRIFT_MAX_RECHECKS = 12
# Quota della finestra di contesto usata dal prompt (stima ~3 caratteri/token, come il
# guardrail di core/llm.py): il resto è per la risposta JSON.
_DRIFT_PROMPT_CTX_SHARE = 0.75

# Path/cartelle citati tra backtick nel Canvas (es. §4 Structure — "Implementato in
# `frontend/src/features/booking-requests/components/CreateBookingForm.tsx`").
_CANVAS_PATH_TOKEN_PATTERN = re.compile(r"`([\w./-]+/[\w.-]+/?)`")


def _canvas_priority_dirs(canvas_content: str, *roots: Path) -> list[Path]:
    """Risolve i path citati nel Canvas contro le radici di ricerca del drift.

    Quando `dev_type` punta a una cartella condivisa da più feature (es. l'intero
    `code/frontend`), senza questo il tetto `_DRIFT_MAX_CODE_CHARS` si esaurisce
    sui file di altre feature prima di arrivare a quelli davvero normati dal
    Canvas sotto revisione, troncando proprio il codice rilevante.
    """
    dirs: list[Path] = []
    seen: set[Path] = set()
    for token in _CANVAS_PATH_TOKEN_PATTERN.findall(canvas_content):
        token = token.strip().rstrip("/")
        if not token or "/" not in token:
            continue
        candidate = Path(token)
        anchor = candidate.parent if candidate.suffix else candidate
        for root in roots:
            root = root.resolve()
            # Include anche la cartella padre dell'anchor (es. `.../booking-requests`
            # oltre a `.../booking-requests/components`): il Canvas cita in genere solo
            # il file/cartella del layer UI, ma file "fratelli" come schema.ts o
            # rules.ts nella stessa feature sono altrettanto pertinenti al drift.
            for candidate_dir in (anchor, anchor.parent):
                resolved = (root / candidate_dir).resolve()
                if resolved == root:
                    continue
                if resolved.is_dir() and resolved not in seen:
                    seen.add(resolved)
                    dirs.append(resolved)
    return dirs


_CITED_BLOCK = re.compile(r"`([^`\n]+)`")
_IDENTIFIER = re.compile(r"[A-Za-z_][\w-]{3,}")


def _normalize_symbol(name: str) -> str:
    """capienza_massima, CapienzaMassima e my-requests-list confrontati alla pari."""
    return re.sub(r"[_-]", "", name).lower()


def _cited_symbols(text: str) -> set[str]:
    """Identificatori citati tra backtick nel contratto (canvas + spec), normalizzati:
    `EventCard.tsx` → eventcard, `const isSoldOut = ...` → issoldout. Solo token con forma
    da identificatore (maiuscole, underscore o trattini): parole come `events` o `stock`
    compaiono in file qualsiasi e non distinguono nulla."""
    return {
        _normalize_symbol(token)
        for block in _CITED_BLOCK.findall(text)
        for token in _IDENTIFIER.findall(block)
        if token != token.lower() or "_" in token or "-" in token
    }


def _feature_code_sources(feature_dir: Path, canvas_content: str) -> list[tuple[Path, list[Path]]]:
    """Il codice di una change, come lo vede il check drift: (radice, file) per la cartella
    della feature e per code/<dev_type> (dove Claude Code scrive l'implementazione).
    Stessa lista di estensioni del code index: una copia locale escludeva .cs/.java/.sql.
    In ogni radice vengono per primi i file più legati al contratto (simboli citati da
    canvas e spec, poi cartelle citate dal Canvas §4 Structure): se il budget non basta,
    restano fuori file di altre feature, non questi."""
    search_dirs = [feature_dir]
    dev_type = _load_dev_type(feature_dir)
    if dev_type:
        search_dirs.append(CODE_DIR / dev_type)
    priority_dirs = _canvas_priority_dirs(
        canvas_content, CODE_DIR, *([CODE_DIR / dev_type] if dev_type else [])
    )
    spec_path = feature_dir / "spec.md"
    spec = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    symbols = _cited_symbols(canvas_content + "\n" + spec)

    def rank(path: Path) -> tuple[int, int]:
        # Prima i file che citano più simboli del contratto (su fe2 il canvas dava un
        # percorso inesistente per EventCard e isSoldOut stava in lib/events/stock.ts; su
        # la3 la verifica posti/budget stava in un orchestratore mai nominato), poi quelli
        # sotto le cartelle citate.
        text = path.read_text(encoding="utf-8", errors="replace")
        words = {_normalize_symbol(w) for w in re.findall(r"\w+", text)}
        words.add(_normalize_symbol(path.name.split(".")[0]))
        in_dir = any(path.is_relative_to(d) for d in priority_dirs)
        return -len(symbols & words), 0 if in_dir else 1

    sources = []
    for base in search_dirs:
        if not base.exists():
            continue
        files = [
            path
            for path in sorted(base.rglob("*"))
            if path.is_file() and path.suffix in CODE_EXTS and not (CODE_EXCLUDED_DIRS & set(path.parts))
        ]
        sources.append((base, sorted(files, key=rank)))
    return sources


def _review_code(feature_dir: Path) -> str:
    """Il codice analizzato dal drift, per la canvas review all'archive (test e file
    generati esclusi, come nella revisione a lotti). '' se non c'è codice."""
    canvas_path = feature_dir / "canvas.md"
    canvas = canvas_path.read_text(encoding="utf-8") if canvas_path.exists() else ""
    pieces = []
    for base, files in _feature_code_sources(feature_dir, canvas):
        for path in files:
            if drift.is_generated_path(path.name) or drift.is_test_path(path.relative_to(base).parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            pieces.append(f"--- FILE: {path.relative_to(base).as_posix()} ---\n{text}")
    return "\n\n".join(pieces)


def _drift_code_budget(fixed_chars: int) -> int:
    """Caratteri di codice per lotto: il tetto `_DRIFT_MAX_CODE_CHARS`, ridotto a quanto
    resta della finestra di contesto dopo la parte fissa del prompt (Canvas, Spec, regole).
    Senza, Canvas + Spec + 40.000 caratteri superavano num_ctx e core/llm.py rifiutava
    il prompt (o, appena sotto, Ollama troncava dall'alto)."""
    budget = _DRIFT_MAX_CODE_CHARS
    if llm.OLLAMA_NUM_CTX:
        ctx_chars = int(llm.OLLAMA_NUM_CTX * 3 * _DRIFT_PROMPT_CTX_SHARE) - fixed_chars
        budget = min(budget, max(ctx_chars, 2_000))
    return budget


def check_drift(feature_name: str, emit=None) -> str:
    """Controlla se il codice generato si è discostato dal contratto (Canvas + Spec).

    Restituisce il report testuale (oltre a stamparlo/emetterlo), così da poterlo
    mostrare anche nel box dedicato dell'interfaccia della pipeline, senza terminale.
    `emit` (default: logger.info) permette lo streaming SSE del progresso.

    Flusso (logica pura in core/drift.py): pre-check deterministico delle dipendenze nei
    manifest → revisione a lotti entro la finestra di contesto → controllo di copertura
    sull'indice dei simboli → verifica in Python di citazioni e termini → riesame mirato
    dei drift sopravvissuti → verdetto calcolato dai rilievi rimasti.
    """
    _log = emit or logger.info
    try:
        feature_dir_path = resolve_feature_dir(CHANGES_DIR, feature_name)
    except InvalidFeatureNameError as exc:
        msg = f"❌ Nome feature non valido: {exc}"
        _log(msg)
        return msg
    feature_folder = feature_dir_path.name
    _log(f"\n🔍 Avvio controllo Drift (Disallineamento) per: 'changes/{feature_folder}'...")

    canvas_path = feature_dir_path / "canvas.md"

    if not canvas_path.exists():
        msg = f"❌ Errore: Non trovo il file {canvas_path}."
        _log(msg)
        return msg

    canvas_content = canvas_path.read_text(encoding="utf-8")
    # La Spec (scenari Gherkin + punti aperti) è fonte normativa con precedenza sul
    # Canvas: senza, requisiti imposti da uno scenario (es. AUDIT_LOG sull'export in
    # BE1/S07) venivano segnalati come drift perché il Canvas non li citava.
    spec_path = feature_dir_path / "spec.md"
    spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

    # Raccoglie il codice da confrontare: sia dall'eventuale codice presente nella
    # cartella della feature, sia dalla sottocartella code/<dev_type> dove Claude
    # Code scrive di fatto l'implementazione (il tipo di sviluppo è in meta.json).
    # Stessa lista del code index: una copia locale escludeva .cs/.java/.sql e il drift
    # di feature backend .NET/Java risultava "nessun file di codice".
    # Ordine di analisi: prima i file citati dal Canvas, poi il resto del codice. Test e file
    # generati (migrazioni EF, designer) sono esclusi dalla revisione a lotti ma restano
    # nell'indice dei simboli (e i generati anche nella verifica delle mancanze): su BE1 i
    # rilievi sui test ("il test non verifica X") erano rumore, non drift del codice.
    ordered: list[tuple[str, str]] = []
    all_texts: dict[str, str] = {}
    generated: list[str] = []
    tests: list[str] = []
    symbols: list[dict] = []
    for base, files in _feature_code_sources(feature_dir_path, canvas_content):
        for path in files:
            # Path relativo alla radice di ricerca (non solo il nome file): più file
            # con lo stesso basename (es. `schema.ts` in moduli diversi) altrimenti
            # diventano indistinguibili nel prompt e l'LLM confonde i vincoli tra loro.
            label = path.relative_to(base).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            all_texts[label] = text
            if drift.is_generated_path(path.name):
                generated.append(label)
            elif drift.is_test_path(path.relative_to(base).parts):
                tests.append(label)
            else:
                ordered.append((label, text))
        try:
            symbols += collect_code_symbols(base)
        except Exception:
            logger.warning("Indice simboli non disponibile per %s: copertura senza simboli.", base, exc_info=True)

    if not ordered:
        _log("⚠️ Attenzione: Nessun file di codice sorgente trovato. Claude Code / Cursor ha già scritto il codice?")
        ordered = [("(nessun file)", "(Nessun file di codice sorgente trovato.)")]

    # Pre-check deterministico: dipendenze dichiarate nei manifest (csproj, pom, gradle,
    # package.json) incrociate con le tecnologie in grassetto del Canvas.
    deps = drift.manifest_dependencies(symbols)
    tech_found = drift.match_canvas_technologies(canvas_content, deps)
    alternatives = drift.satisfied_alternatives(canvas_content, tech_found)
    prechecks = drift.format_prechecks(deps, tech_found)
    for term, dep, manifest in tech_found:
        _log(f"✔️ Pre-check: '{term}' presente nei manifest come {dep} ({manifest}).")

    all_labels = [label for label, _ in ordered] + tests + generated
    fixed = len(drift.build_batch_prompt(canvas_content, spec_content, prechecks, "", 0, 0, all_labels))
    budget = _drift_code_budget(fixed)
    batches, skipped = drift.make_batches(ordered, budget, _DRIFT_MAX_BATCHES)
    left_out = skipped + generated
    coverage = (f"{len(ordered) - len(skipped)} file analizzati in {len(batches)} lotto/i "
                f"da ≤{budget} caratteri"
                + (f"; test usati solo come evidenza: {len(tests)}" if tests else "")
                + (f"; non analizzati: {', '.join(left_out)}" if left_out else "; nessun file escluso"))
    _log(f"📦 Copertura: {coverage}.")
    if skipped:
        _log(f"⚠️ Oltre {_DRIFT_MAX_BATCHES} lotti: {len(skipped)} file non analizzati (elencati nel report).")

    contract_norm = drift.norm(canvas_content + "\n" + spec_content)
    # Testo in cui cercare i termini delle "mancanze": tutto il codice tranne i test (un test
    # che nomina una funzionalità non prova che esista; su BE1 il nome del test CSV citato
    # tra i termini smentiva la mancanza dell'export Excel), minuscolo e senza commenti.
    searchable = {label: drift.strip_comments(text).lower()
                  for label, text in all_texts.items() if label not in tests}
    findings: list[dict] = []
    failures: list[str] = []
    try:
        for i, batch in enumerate(batches, 1):
            seen = {label for label, _h, _c in batch}
            prompt = drift.build_batch_prompt(
                canvas_content, spec_content, prechecks, drift.render_batch(batch),
                i, len(batches), [label for label in all_labels if label not in seen],
            )
            _log(f"🧠 Analisi del lotto {i}/{len(batches)} ({len(seen)} file) tramite LLM...")
            parsed = drift.parse_findings(llm.generate(prompt, purpose="drift"))
            if parsed is None:
                failures.append(f"Lotto {i}: risposta dell'LLM non interpretabile come JSON.")
                continue
            findings += [drift.verify_code_finding(f, batch, contract_norm, searchable) for f in parsed]

        _log("🧠 Controllo di copertura dei requisiti sull'indice dei simboli...")
        summary = drift.symbol_summary(symbols, budget)
        prompt = drift.build_coverage_prompt(canvas_content, spec_content, prechecks, summary, left_out)
        parsed = drift.parse_findings(llm.generate(prompt, purpose="drift"))
        if parsed is None:
            failures.append("Copertura: risposta dell'LLM non interpretabile come JSON.")
        else:
            findings += [drift.verify_coverage_finding(f, searchable, contract_norm) for f in parsed]
        drift.discard_satisfied_alternatives(findings, alternatives)
        findings = drift.dedupe(findings)

        # Riesame mirato dei drift sopravvissuti (lotti e copertura): una citazione reale o un
        # termine assente non bastano, il modello locale ne traeva spesso conclusioni opposte
        # a ciò che il codice mostrava, o cercava nomi inventati.
        to_recheck = [f for f in findings if f["categoria"] == "drift" and not f["scartato"]]
        for f in to_recheck[_DRIFT_MAX_RECHECKS:]:
            f["descrizione"] += " [non riesaminato: oltre il tetto dei riesami]"
        to_recheck = to_recheck[:_DRIFT_MAX_RECHECKS]
        for n, f in enumerate(to_recheck, 1):
            _log(f"🔎 Riesame del rilievo {n}/{len(to_recheck)} ({f['file'] or 'copertura'})...")
            # Codice citato, indice simboli e codice che cita gli identificativi del requisito,
            # entro lo stesso budget di un lotto.
            context = drift.code_context(all_texts.get(f["file"], ""), f["evidenza"], budget // 3)
            block = drift.requirement_context(f["requisito"], canvas_content, spec_content)
            prompt = drift.build_recheck_prompt(
                canvas_content, spec_content, f, context,
                drift.symbol_summary(symbols, budget // 3),
                drift.related_code(block, dict(ordered), budget // 3, f"{f['descrizione']}\n{f['evidenza']}"),
            )
            outcome, reason = drift.parse_recheck(llm.generate(prompt, purpose="drift"))
            if outcome == "rispettato":
                f["scartato"] = f"riesame: non è una violazione ({reason or 'nessun motivo indicato'})"
            elif outcome == "punto_aperto":
                # Non un drift, ma resta visibile: su BE1 l'export Excel mancante (Canvas "CSV o
                # Excel", Spec OP-001) veniva altrimenti scartato del tutto.
                f["categoria"] = "punto_aperto"
                f["descrizione"] += f" [riesame: punto aperto — {reason or 'nessun motivo indicato'}]"
            elif outcome is None:
                f["descrizione"] += " [riesame non interpretabile: rilievo mantenuto]"
    except llm.LLMError as e:
        # Il controllo drift è tollerante: l'errore diventa il report, mai un'eccezione
        # verso l'interfaccia. Si interrompe subito: le chiamate successive fallirebbero
        # allo stesso modo (generate ha già ritentato gli errori transitori).
        report = f"❌ Errore durante il check drift: {e}"
    else:
        discarded = sum(1 for f in findings if f["scartato"])
        if discarded:
            _log(f"🧹 {discarded} rilievo/i scartato/i dalla verifica deterministica.")
        report = drift.build_report(findings, coverage=coverage, prechecks_found=tech_found, failures=failures)

    _log("\n" + "=" * 50)
    _log("📊 REPORT DRIFT:")
    _log(report)
    _log("=" * 50 + "\n")
    return report
