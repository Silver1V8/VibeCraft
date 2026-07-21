"""Test della generazione doc via Ollama (S3, piano: docs/00_meta_governance/
piano_intake_import.md): prompt grounded, split multi-documento, validazione, staging
(source "generated") e il job manager in background. LLM sempre MOCKATO (mai Ollama
reale); un test di integrazione reale è fuori scope di questa suite (marcato altrove)."""
import json
from pathlib import Path

import pytest

from core import doc_generation, intake, llm
from core.chunking import parse_markdown_file

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

# Stesso pattern di rottura YAML già usato in test_intake_staging.py (parentesi quadra
# aperta e mai chiusa): yaml.safe_load solleva un errore di parsing.
BAD_DOC = """---
title: [yaml rotto
scope: x
---

# Titolo

## Sezione
testo
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
