"""Test delle funzioni pure di core/pipeline.py: slug, prompt builder (canvas/spec/final/
validate), controlli strutturali e blocco [AGENT CONTEXT]. Nessun FastAPI, nessun LLM,
nessun Qdrant reale (build_agent_context nel percorso senza retrieval)."""
import networkx as nx

from core import pipeline


def test_slugify_feature():
    assert pipeline.slugify_feature("  Gestione Eventi  ") == "gestione-eventi"


def test_build_final_prompt_scopes_by_dev_type():
    with_dev = pipeline.build_final_prompt("feat", "backend")
    assert "code/backend/" in with_dev and "ESCLUSIVAMENTE" in with_dev
    without = pipeline.build_final_prompt("feat", "")
    assert "code/backend" in without and "code/frontend" in without  # distribuzione multi-cartella


def test_build_canvas_prompt_includes_scope_only_with_dev_type():
    base = pipeline.build_canvas_prompt("Feat X", "log intervista", "contesto normativo", "")
    assert 'feature: "Feat X"' in base
    assert "log intervista" in base and "contesto normativo" in base
    assert "Vincolo di ambito" not in base                 # niente scope senza dev_type
    scoped = pipeline.build_canvas_prompt("Feat X", "log", "ctx", "frontend")
    assert "Vincolo di ambito" in scoped and "code/frontend/" in scoped


def test_build_spec_prompt_norme_block_conditional():
    with_norme = pipeline.build_spec_prompt("CANVAS BODY", "vincoli normativi")
    assert "CANVAS BODY" in with_norme and "Vincoli normativi dal Graph RAG" in with_norme
    without = pipeline.build_spec_prompt("CANVAS BODY", "")
    assert "CANVAS BODY" in without and "Vincoli normativi dal Graph RAG" not in without


def test_validate_structural_detects_sections_and_bdd():
    canvas = "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n"
    spec = "GIVEN x WHEN y THEN z"
    out = pipeline.validate_structural(canvas, spec)
    assert out["canvas_completo"] is True
    assert out["spec_bdd_valida"] is True
    # canvas incompleto + spec senza THEN
    out2 = pipeline.validate_structural("## Requirements\n", "GIVEN x WHEN y")
    assert out2["canvas_completo"] is False
    assert out2["spec_bdd_valida"] is False
    assert out2["bdd_then"] is False


def test_build_validate_prompt_handles_missing_parts():
    p = pipeline.build_validate_prompt("CANVAS", "", "")
    assert "CANVAS" in p
    assert "(spec.md non ancora generato)" in p
    assert "(nessun documento normativo recuperato)" in p


def test_render_agent_context_formats_block():
    ctx = {
        "intent": "Implementare X", "normative_sources": ["a.md"], "entities": ["EVENTO"],
        "safeguards": ["SAFEGUARD-1"], "constraints": ["c1"], "risks": [],
        "files_to_read": ["changes/x/canvas.md"], "confidence": 0.5, "confidence_label": "media",
        "suggested_prompt": "PROMPT",
    }
    text = pipeline._render_agent_context(ctx)
    assert text.startswith("[AGENT CONTEXT]")
    assert "Intento probabile: Implementare X" in text
    assert "(nessuno rilevato)" in text          # lista rischi vuota → placeholder
    assert text.rstrip().endswith("PROMPT")


def test_build_agent_context_without_retrieval(tmp_path, monkeypatch):
    """Percorso senza Qdrant: nessun retrieval, confidence deterministica da canvas/spec.
    Verifica anche che il modulo core.retrieval non sia ombreggiato (fix retrieval_score)."""
    monkeypatch.setattr(pipeline, "CHANGES_DIR", tmp_path)
    folder = tmp_path / "gestione-eventi"
    folder.mkdir()
    (folder / "canvas.md").write_text(
        "## Requirements\n## Entities\n## Approach\n## Structure\n## Operations\n## Norms\n## Safeguards\n",
        encoding="utf-8",
    )
    (folder / "spec.md").write_text("GIVEN x WHEN y THEN z", encoding="utf-8")

    g = nx.DiGraph()
    ctx = pipeline.build_agent_context(
        "Gestione Eventi", "backend", graph=g, qdrant=None, embed_model=None, colbert_store={}
    )
    assert ctx["normative_sources"] == []          # nessun retrieval senza qdrant
    assert ctx["confidence"] > 0                    # canvas completo + spec BDD valida
    assert ctx["confidence_label"] in ("alta", "media", "bassa")
    assert "code/backend/" in ctx["files_to_read"]
    assert ctx["text"].startswith("[AGENT CONTEXT]")
