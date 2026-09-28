"""Test della generazione doc via Ollama (S3, piano: docs/00_meta_governance/
piano_intake_import.md): prompt grounded, split multi-documento, validazione, staging
(source "generated") e il job manager in background. LLM sempre MOCKATO (mai Ollama
reale); un test di integrazione reale è fuori scope di questa suite (marcato altrove)."""
import json
from pathlib import Path

import pytest

import yaml

from core import doc_generation, intake, llm
from core.chunking import parse_markdown_file, split_frontmatter

GOOD_DOC_A = """---
title: Guida A
scope: Descrive lo sviluppo A
---

# Guida A

## Sezione Uno
Contenuto reale della sezione uno.

## Sezione Due
Contenuto reale della sezione due.
"""

GOOD_DOC_B = """---
title: Guida B
scope: Descrive lo sviluppo B
---

# Guida B

## Sezione Sola
Contenuto reale.
"""

# Documento IRRECUPERABILE: solo frontmatter, nessun corpo. Una rottura del solo
# frontmatter non basta più a farlo scartare — normalize_generated_markdown la ripara
# tenendo il corpo (vedi i test di normalizzazione più sotto); qui non c'è nulla da
# tenere, ed è il caso in cui lo scarto è la risposta giusta.
BAD_DOC = """---
title: Solo frontmatter
scope: nessun corpo dopo il delimitatore
---
"""


def _raw(*docs: str) -> str:
    return f"\n{doc_generation._DOC_SEPARATOR}\n".join(docs)


def _journal_lines(base_dir: Path) -> list[dict]:
    text = (base_dir / "intake.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _fake_search(chunks_map: dict):
    """search() iniettabile: ignora la query e restituisce sempre gli stessi risultati
    (chunk_id/doc_id/section), nello stesso formato di retrieval.hybrid_search."""
    def _search(question, top_k, *, qdrant, embed_model, colbert_store):
        return [{"chunk_id": cid, "doc_id": f"docs/{cid}.md", "section": "Intro"}
                for cid in chunks_map]
    return _search


# ---------------------------------------------------------------------------
# build_generation_prompt / split_generated_documents
# ---------------------------------------------------------------------------
def test_build_generation_prompt_contains_all_ingredients():
    prompt = doc_generation.build_generation_prompt(
        "una feature di test", 3, "04_knowledge_informative", "CONTESTO QUI", "LEZIONE QUI"
    )
    assert "una feature di test" in prompt
    assert "ESATTAMENTE 3 documenti" in prompt
    assert "04_knowledge_informative" in prompt
    assert "CONTESTO QUI" in prompt
    assert "LEZIONE QUI" in prompt
    assert doc_generation._DOC_SEPARATOR in prompt


def test_build_generation_prompt_without_context_or_lessons_has_placeholders():
    prompt = doc_generation.build_generation_prompt("x", 1, "04_knowledge_informative", "", "")
    assert "nessun contesto normativo pertinente recuperato" in prompt
    assert "LEZIONI DALLE CHANGE PRECEDENTI" not in prompt


def test_split_generated_documents_splits_on_separator_and_drops_empty():
    raw = f"doc1\n{doc_generation._DOC_SEPARATOR}\n\n  \n{doc_generation._DOC_SEPARATOR}\ndoc2\n"
    assert doc_generation.split_generated_documents(raw, n_file=5) == ["doc1", "doc2"]


def test_split_generated_documents_truncates_to_n_file():
    raw = _raw("doc1", "doc2", "doc3")
    assert doc_generation.split_generated_documents(raw, n_file=2) == ["doc1", "doc2"]


# ---------------------------------------------------------------------------
# normalize_generated_markdown — riparazione del CONTORNO dell'output del modello.
# Regressione 2026-07-22: un brief con frontmatter APERTO e mai chiuso veniva scartato
# in validazione (ScannerError su `-   **Progetto Core**: ...`, letto come alias YAML)
# pur avendo un corpo perfettamente valido.
# ---------------------------------------------------------------------------
def test_normalize_closes_unterminated_frontmatter_keeping_body():
    raw = ("---\ntitle: Project brief backend\nscope: sintesi architetturale\n\n"
           "# Project brief\n\n## Componenti\n\n"
           "-   **Progetto Core**: `WSProtocollo` è il servizio principale\n")
    normalized = doc_generation.normalize_generated_markdown(raw)
    fm_text, body = split_frontmatter(normalized)
    assert yaml.safe_load(fm_text) == {"title": "Project brief backend",
                                       "scope": "sintesi architetturale"}
    assert "**Progetto Core**" in body and "## Componenti" in body
    doc_generation._validate_generated_markdown(normalized)  # non solleva


def test_normalize_unwraps_markdown_code_fence():
    raw = "```markdown\n---\ntitle: T\n---\n\n# T\n\n## S\ncorpo\n```"
    normalized = doc_generation.normalize_generated_markdown(raw)
    assert not normalized.startswith("```") and normalized.startswith("---")
    doc_generation._validate_generated_markdown(normalized)


def test_normalize_drops_unparsable_frontmatter_but_keeps_body():
    """Frontmatter chiuso ma non caricabile: si perde il contorno (che l'approve
    rigenera comunque), mai il documento."""
    raw = "---\ntitle: [yaml rotto\n---\n# Titolo\n\n## Sezione\ncorpo reale\n"
    normalized = doc_generation.normalize_generated_markdown(raw)
    assert split_frontmatter(normalized)[0] is None
    assert "corpo reale" in normalized
    doc_generation._validate_generated_markdown(normalized)


def test_normalize_leaves_conforming_document_untouched_and_is_idempotent():
    once = doc_generation.normalize_generated_markdown(GOOD_DOC_A)
    assert once == GOOD_DOC_A.strip()
    assert doc_generation.normalize_generated_markdown(once) == once


def test_normalize_keeps_leading_rule_that_is_not_frontmatter():
    """Un `---` iniziale seguito da prosa (nessun campo) non è un frontmatter aperto:
    resta nel corpo, non si inventa una chiusura."""
    raw = "---\n\n# Titolo\n\n## Sezione\ncorpo\n"
    assert doc_generation.normalize_generated_markdown(raw) == raw.strip()


# ---------------------------------------------------------------------------
# generate_docs: happy path, grounded + staged, mai in docs/
# ---------------------------------------------------------------------------
def test_generate_docs_stages_valid_documents_with_generation_metadata(tmp_path, monkeypatch):
    chunks_store = {"c1": {"text": "Testo di riferimento pertinente."}}
    seen_prompt = {}

    # docs/ reale (distinto dallo staging in tmp_path): la generazione non deve MAI
    # scriverci, solo in staging (base_dir).
    real_docs_dir = tmp_path / "docs_reale"
    monkeypatch.setattr(intake, "DOCS_DIR", real_docs_dir)

    def fake_generate(prompt):
        seen_prompt["prompt"] = prompt
        return _raw(GOOD_DOC_A, GOOD_DOC_B)

    result = doc_generation.generate_docs(
        "sviluppo di una feature X", 2, "04_knowledge_informative",
        qdrant=object(), embed_model=object(), colbert_store={}, chunks_store=chunks_store,
        base_dir=tmp_path / "staging", search=_fake_search(chunks_store), generate=fake_generate,
    )

    assert result["n_generati"] == 2
    assert result["n_scartati"] == 0
    assert "sviluppo di una feature X" in seen_prompt["prompt"]
    assert "docs/c1.md" in seen_prompt["prompt"]  # grounding con citazione presente nel prompt

    for record in result["generati"]:
        assert record["status"] == "staged"
        assert record["source"] == "generated"
        assert record["metadata"]["descrizione_richiesta"] == "sviluppo di una feature X"
        assert record["metadata"]["categoria_suggerita"] == "04_knowledge_informative"
        assert "retrieval_ms" in record["metadata"]["latenze"]
        assert "generation_ms" in record["metadata"]["latenze"]

    latency = result["latency"]
    assert set(latency) == {"retrieval_ms", "generation_ms", "total_ms"}

    staged = intake.list_staged(base_dir=tmp_path / "staging")
    assert len(staged) == 2

    # nessuna scrittura diretta in docs/: solo staging (NON-GOAL del piano)
    assert not real_docs_dir.exists()


def test_generated_document_is_approvable_via_s2_flow(tmp_path):
    chunks_store = {"c1": {"text": "contesto"}}

    def fake_generate(_prompt):
        return GOOD_DOC_A

    result = doc_generation.generate_docs(
        "una feature", 1, "04_knowledge_informative",
        qdrant=object(), embed_model=object(), colbert_store={}, chunks_store=chunks_store,
        base_dir=tmp_path, search=_fake_search(chunks_store), generate=fake_generate,
    )
    record = result["generati"][0]

    docs_dir = tmp_path / "docs"
    approved = intake.approve(
        record["id"], "04_knowledge_informative", "guida-a",
        base_dir=tmp_path, docs_dir=docs_dir,
        reindex=lambda paths: {"noop": False, "reindexed_docs": 1, "upserted_chunks": 1},
    )
    assert approved["status"] == "approved"
    target = docs_dir / "04_knowledge_informative" / "guida-a.md"
    metadata, body = parse_markdown_file(str(target))
    assert metadata["intake"]["source"] == "generated"
    assert "Guida A" in body


# ---------------------------------------------------------------------------
# Validazione: documento malformato scartato con motivo nel journal, il resto procede
# ---------------------------------------------------------------------------
def test_malformed_document_is_discarded_with_reason_in_journal(tmp_path):
    chunks_store = {"c1": {"text": "contesto"}}

    def fake_generate(_prompt):
        return _raw(GOOD_DOC_A, BAD_DOC)

    result = doc_generation.generate_docs(
        "una feature", 2, "04_knowledge_informative",
        qdrant=object(), embed_model=object(), colbert_store={}, chunks_store=chunks_store,
        base_dir=tmp_path, search=_fake_search(chunks_store), generate=fake_generate,
    )

    assert result["n_generati"] == 1
    assert result["n_scartati"] == 1
    assert result["scartati"][0]["indice"] == 2
    assert result["scartati"][0]["motivo"]

    discarded_lines = [r for r in _journal_lines(tmp_path) if r.get("status") == "discarded"]
    assert len(discarded_lines) == 1
    assert discarded_lines[0]["motivo"] == result["scartati"][0]["motivo"]
    assert discarded_lines[0]["source"] == "generated"

    # solo il documento valido resta staged
    assert len(intake.list_staged(base_dir=tmp_path)) == 1


# ---------------------------------------------------------------------------
# Ollama irraggiungibile: errore leggibile, mai un'eccezione grezza propagata
# ---------------------------------------------------------------------------
def test_generate_docs_wraps_llm_error(tmp_path):
    def broken(_prompt):
        raise llm.LLMError("[ERRORE DI CONNESSIONE]: Impossibile raggiungere Ollama.")

    with pytest.raises(doc_generation.GenerationError, match="generazione fallita"):
        doc_generation.generate_docs(
            "una feature", 1, "04_knowledge_informative",
            base_dir=tmp_path, generate=broken,
        )
    # nessun documento staged, nessuna scrittura
    assert intake.list_staged(base_dir=tmp_path) == []


# ---------------------------------------------------------------------------
# n_file clampato a INTAKE_GENERATION_MAX_FILES
# ---------------------------------------------------------------------------
def test_n_file_is_clamped_to_generation_max_files(tmp_path, monkeypatch):
    monkeypatch.setattr(doc_generation, "INTAKE_GENERATION_MAX_FILES", 2)
    seen_prompt = {}

    def fake_generate(prompt):
        seen_prompt["prompt"] = prompt
        return GOOD_DOC_A

    doc_generation.generate_docs(
        "x", 10, "04_knowledge_informative", base_dir=tmp_path, generate=fake_generate,
    )
    assert "ESATTAMENTE 2 documenti" in seen_prompt["prompt"]


# ---------------------------------------------------------------------------
# Grounding assente (nessuna risorsa di retrieval): la generazione prosegue comunque
# ---------------------------------------------------------------------------
def test_generate_docs_without_retrieval_resources_still_works(tmp_path):
    result = doc_generation.generate_docs(
        "una feature senza contesto", 1, "04_knowledge_informative",
        base_dir=tmp_path, generate=lambda _p: GOOD_DOC_A,
    )
    assert result["n_generati"] == 1


# ---------------------------------------------------------------------------
# GenerationManager: job in background, pending -> running -> done|failed
# ---------------------------------------------------------------------------
def test_generation_manager_completes_job_successfully():
    mgr = doc_generation.GenerationManager()
    job = mgr.start("desc", 3, "04_knowledge_informative", lambda: {"n_generati": 1})
    assert mgr.join_all(timeout=5)

    fetched = mgr.get(job.id)
    assert fetched.status == "done"
    assert fetched.result == {"n_generati": 1}
    assert fetched.error is None
    assert fetched.finished_at is not None


def test_generation_manager_marks_failed_job_with_readable_error():
    mgr = doc_generation.GenerationManager()

    def _boom():
        raise RuntimeError("Ollama irraggiungibile")

    job = mgr.start("desc", 1, "04_knowledge_informative", _boom)
    assert mgr.join_all(timeout=5)

    fetched = mgr.get(job.id)
    assert fetched.status == "failed"
    assert "RuntimeError" in fetched.error
    assert "Ollama irraggiungibile" in fetched.error


def test_generation_manager_unknown_job_returns_none():
    assert doc_generation.GenerationManager().get("non-esiste") is None


# ---------------------------------------------------------------------------
# Limiti del GenerationManager: tetto di job attivi, retention dei terminati, _threads
# ripulito. I job restano bloccati su un Event finché il test non li rilascia.
# ---------------------------------------------------------------------------
def _blocking_job(gate):
    def run():
        assert gate.wait(5)
        return {"ok": True}
    return run


def test_generation_manager_rejects_beyond_active_ceiling_then_frees_slot():
    import threading

    mgr = doc_generation.GenerationManager(slots=doc_generation.GenerationSlots(2), max_finished=10)
    gate = threading.Event()
    first = mgr.start("a", 1, "", _blocking_job(gate))
    mgr.start("b", 1, "", _blocking_job(gate))
    with pytest.raises(doc_generation.GenerationBusyError, match="2/2"):
        mgr.start("c", 1, "", _blocking_job(gate))
    assert len(mgr._jobs) == 2  # il rifiutato non lascia né job né thread
    assert len(mgr._threads) == 2

    gate.set()
    assert mgr.join_all(timeout=5)
    assert mgr.get(first.id).status == "done"
    assert mgr._threads == []  # i thread terminati si rimuovono da soli
    third = mgr.start("c", 1, "", lambda: {"ok": True})  # slot liberati a fine job
    assert mgr.join_all(timeout=5)
    assert mgr.get(third.id).status == "done"


def test_generation_manager_retention_drops_oldest_finished_never_running():
    import threading

    mgr = doc_generation.GenerationManager(slots=doc_generation.GenerationSlots(5), max_finished=2)
    gate = threading.Event()
    running = mgr.start("in corso", 1, "", _blocking_job(gate))
    finished = []
    for i in range(4):
        finished.append(mgr.start(f"f{i}", 1, "", lambda: {"ok": True}))
        # attende il singolo job veloce: l'ordine di fine è quello di avvio
        for _ in range(500):
            if mgr.get(finished[-1].id).finished_at and len(mgr._threads) == 1:
                break
            threading.Event().wait(0.01)
    assert mgr.get(running.id) is not None and mgr.get(running.id).status == "running"
    assert [mgr.get(j.id) is not None for j in finished] == [False, False, True, True]

    gate.set()
    assert mgr.join_all(timeout=5)
    # ora anche il job lungo è terminato ed entra nella retention: il più vecchio esce
    assert mgr.get(running.id) is not None
    assert mgr.get(finished[2].id) is None and mgr.get(finished[3].id) is not None


def test_slots_are_shared_across_managers():
    """Il tetto è globale: un job di un manager occupa lo slot anche per gli altri."""
    import threading

    slots = doc_generation.GenerationSlots(1)
    gen = doc_generation.GenerationManager(slots=slots)
    refine = doc_generation.GenerationManager(slots=slots)
    gate = threading.Event()
    gen.start("a", 1, "", _blocking_job(gate))
    with pytest.raises(doc_generation.GenerationBusyError):
        refine.start("b", 1, "", lambda: {})
    assert refine._jobs == {} and refine._threads == []
    gate.set()
    assert gen.join_all(timeout=5)
    assert slots.active == 0
    job = refine.start("b", 1, "", lambda: {})
    assert refine.join_all(timeout=5) and refine.get(job.id).status == "done"


def test_slot_is_free_before_the_job_is_visible_as_done():
    """Un client che vede done e rilancia subito non deve ricevere un 429 spurio."""
    slots = doc_generation.GenerationSlots(1)
    mgr = doc_generation.GenerationManager(slots=slots)
    seen = []
    original = slots.release

    def release():
        original()
        seen.append(next(iter(mgr._jobs.values())).status)
    slots.release = release
    job = mgr.start("a", 1, "", lambda: {"ok": True})
    assert mgr.join_all(timeout=5)
    assert seen == ["running"] and job.status == "done"


def test_generation_limits_are_read_lazily_and_fail_loudly(monkeypatch):
    """Come i limiti di /ask: l'env si legge alla prima start, e un valore non valido
    è un errore esplicito col nome della variabile."""
    mgr = doc_generation.GenerationManager()  # costruzione: nessuna lettura dell'env
    monkeypatch.setenv("VIBECRAFT_GENERATION_MAX_ACTIVE", "0")
    with pytest.raises(RuntimeError, match="VIBECRAFT_GENERATION_MAX_ACTIVE"):
        mgr.start("a", 1, "", lambda: {})
    monkeypatch.setenv("VIBECRAFT_GENERATION_MAX_ACTIVE", "1")
    monkeypatch.setenv("VIBECRAFT_GENERATION_MAX_FINISHED", "abc")
    with pytest.raises(RuntimeError, match="VIBECRAFT_GENERATION_MAX_FINISHED"):
        doc_generation.GenerationManager().start("a", 1, "", lambda: {})
