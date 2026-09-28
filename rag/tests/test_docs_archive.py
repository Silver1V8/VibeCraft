"""Verifica lo spostamento di `rag/adr/sidecar-work/` e delle run pesanti di
`rag/eval/results/` (quelle con una sottocartella `evidence/`) in `archive/`, alla radice
del repository — vedi `archive/README.md` per il perimetro e il perché.

Due cose, non una sola: (1) lo spostamento è avvenuto ed è quello atteso — le vecchie
posizioni sono vuote, le nuove esistono; (2) nessun modulo a runtime sotto `rag/core` o
`rag/api` (il codice che il server importa ed esegue) referenzia `archive/` come percorso:
se un giorno qualcuno ce lo aggiungesse, sarebbe un accoppiamento runtime -> materiale
archiviato, esattamente il caso che l'intervento doveva escludere prima di spostare
qualunque file (vedi `rag/core/eval_history.py`, che infatti resta su `eval/results/
history.jsonl`, mai spostato)."""
from pathlib import Path

RAG_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = RAG_DIR.parent
ARCHIVE_DIR = REPO_ROOT / "archive"


def test_sidecar_work_spostata_in_archive():
    assert not (RAG_DIR / "adr" / "sidecar-work").exists(), (
        "rag/adr/sidecar-work/ dovrebbe essere stata spostata, non solo copiata"
    )
    dest = ARCHIVE_DIR / "adr" / "sidecar-work"
    assert dest.is_dir()
    # Un campione, non l'elenco completo: il contenuto esatto non è ciò che questo test
    # sorveglia (ci pensa la storia git), solo che la cartella non sia rimasta vuota.
    assert any(dest.glob("*.md")), "archive/adr/sidecar-work/ non contiene .md"


def test_run_eval_pesanti_spostate_in_archive():
    """Le run con evidence/ non sono più sotto rag/eval/results/, TRANNE quelle che un test
    legge davvero a runtime (bloccanti, non spostate: vedi sotto) e i file sciolti (letti o
    scritti da codice/script, es. history.jsonl), che restano dove sono, invariati."""
    campione = ["sidecar_npy_20260921", "colbert_memory_20260915", "verifica_finale_20260910"]
    for run in campione:
        assert not (RAG_DIR / "eval" / "results" / run).exists(), (
            f"rag/eval/results/{run}/ dovrebbe essere stata spostata"
        )
        dest = ARCHIVE_DIR / "eval-results" / run
        assert (dest / "evidence").is_dir(), f"archive/eval-results/{run}/evidence/ mancante"

    for nome in ("history.jsonl", "README.md", "FASE2_PROPOSE_20260914.md", ".gitignore", ".gitattributes"):
        assert (RAG_DIR / "eval" / "results" / nome).is_file(), (
            f"rag/eval/results/{nome} non doveva spostarsi"
        )


def test_run_lette_dai_test_non_spostate():
    """test_pipeline_gate.py e test_open_points.py leggono `.../propose_adopted_v3_20260914/
    evidence/responses/*.md`; test_pipeline_validation.py e pipeline_validation.cjs leggono
    `.../gate_end_to_end_20260914/evidence/...`; test_golden_attribution.py legge
    `.../p0_20260908-152239/evidence/preflight.json`: uso a runtime/test, bloccante per la
    consegna (\"se esistono [usi a runtime/test] per un file, quel file NON si sposta\").
    Queste tre run restano quindi sotto rag/eval/results/, non in archive/eval-results/."""
    for run in ("propose_adopted_v3_20260914", "gate_end_to_end_20260914", "p0_20260908-152239"):
        assert (RAG_DIR / "eval" / "results" / run).is_dir(), (
            f"rag/eval/results/{run}/ e' letta da un test, non doveva spostarsi"
        )
        assert not (ARCHIVE_DIR / "eval-results" / run).exists()


def test_archive_eval_results_ha_gitattributes_no_text():
    """`*/evidence/** -text` preservava i byte/SHA-256 delle evidenze anche con autocrlf
    quando l'albero viveva sotto rag/eval/results/; .gitattributes non si eredita da una
    cartella spostata, quindi la stessa regola deve esistere anche nella nuova posizione."""
    contenuto = (ARCHIVE_DIR / "eval-results" / ".gitattributes").read_text(encoding="utf-8")
    assert "evidence/** -text" in contenuto


def test_nessun_modulo_runtime_referenzia_larchivio_docs():
    """rag/core/ e rag/api/ sono il codice che il server importa ed esegue: nessuna stringa
    USATA DAL CODICE (non una docstring: alcune citano l'archivio solo come nota storica, es.
    core/intake_excel.py, core/intake_convert.py, dopo lo spostamento delle evidenze che le
    giustificano) deve contenere un percorso verso l'archivio di documentazione alla radice
    (`archive/adr/`, `archive/eval-results/`). Nota: 'archive/' da solo NON basta come
    letterale — esiste già una feature runtime indipendente e omonima (`changes/archive/`,
    spostamento di spec di pipeline in core/pipeline.py, api/routes_pipeline.py) che non ha
    nulla a che fare con lo spostamento di questo intervento."""
    import ast

    sospetti = []
    for sottocartella in ("core", "api"):
        for py in (RAG_DIR / sottocartella).rglob("*.py"):
            albero = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            docstring_ids = set()
            contenitori = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            for nodo in ast.walk(albero):
                if not isinstance(nodo, contenitori):
                    continue  # solo qui .body è una LISTA di statement (non es. Lambda.body)
                corpo = nodo.body
                if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
                        and isinstance(corpo[0].value.value, str):
                    docstring_ids.add(id(corpo[0].value))
            for nodo in ast.walk(albero):
                if (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)
                        and id(nodo) not in docstring_ids
                        and ("archive/adr" in nodo.value or "archive/eval-results" in nodo.value)):
                    sospetti.append(f"{py.relative_to(REPO_ROOT)}:{nodo.lineno}")
    assert sospetti == [], f"riferimenti sospetti all'archivio docs in codice (non docstring): {sospetti}"


def test_eval_history_py_punta_ancora_al_percorso_invariato():
    """Garanzia diretta che il modulo dietro la pagina /eval calcola lo storico da
    rag/eval/results/history.jsonl (mai spostato), non da una costante riscritta a mano.
    HISTORY_PATH è monkeypatchato per i test (conftest.py, isolamento I/O): si verifica la
    COSTRUZIONE del percorso, non il valore corrente della global patchata."""
    from core import eval_history

    assert eval_history.RESULTS_DIR == RAG_DIR / "eval" / "results"
    percorso_reale = eval_history.RESULTS_DIR / "history.jsonl"
    assert percorso_reale == RAG_DIR / "eval" / "results" / "history.jsonl"
    assert percorso_reale.is_file()
