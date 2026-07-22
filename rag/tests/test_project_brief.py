"""Test del project brief (S6, piano: docs/00_meta_governance/piano_intake_import.md):
core/project_brief.py (grounding deterministico sul grafo, precondizione import,
staging source "brief") e le route /api/intake/project/brief in api/routes_intake.py,
più l'e2e dell'INTERA evoluzione Intake & Import con LLM mockato: import mini-progetto
in tmp code/ → reindex → brief → staged → approve → una retrieve di test lo trova.

Stesso arsenale dei test S2/S5: sandbox tmp_path ovunque (mai docs/ o code/ reali),
StubEmbed deterministico, Qdrant in-memory (qui esteso con query_points per esercitare
la hybrid_search vera), writer lock su file in tmp_path."""
import json
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import artifacts as _artifacts
from core import indexing as index
from core import intake, project_brief, project_import, retrieval
from core.doc_generation import GenerationError

from test_incremental_indexing import StatefulFakeQdrant, StubEmbed, _wire_tmp_index


# ---------------------------------------------------------------------------
# Helper: journal con un import "applied", markdown valido, grafo con simboli
# ---------------------------------------------------------------------------
def _journal_applied_import(staging, target="backend", rec_id="prj-e2e") -> dict:
    """Scrive nel journal l'entry di un import progetto riuscito (stesso formato di
    core.project_import.apply_project_import)."""
    paths = intake.ensure_staging_dirs(staging)
    record = {"id": rec_id, "type": "project_import", "status": "applied",
              "target": target, "src": "C:/altrove/progetto", "mode": "bootstrap"}
    intake._append_journal(paths, record)
    return record


_VALID_BRIEF_MD = """---
title: Brief backend
scope: sintesi architetturale del target backend
---

# Project brief backend

## Componenti
Il target contiene la funzione handle_beta che gestisce BETA.

## Entrypoint
Nessun endpoint HTTP rilevato nei dati del grafo.

## Dipendenze principali
Nessuna dipendenza interna rilevata.

## Mappa simboli → spec
handle_beta implementa la sezione della spec BETA.

## Aree candidate a refactoring
Consolidare la gestione BETA in un modulo dedicato.
"""


def _graph_with_backend_symbols() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("spec.md", type="document")
    G.add_node("spec.md#00-sezione", type="section", doc_id="spec.md")
    G.add_node("backend/app/svc.py::handle_beta", type="code", kind="function",
               name="handle_beta", file="backend/app/svc.py", dev_type="backend")
    G.add_node("backend/app/api.py::get_beta", type="code", kind="endpoint",
               name="get_beta", file="backend/app/api.py", dev_type="backend",
               route="/api/beta")
    G.add_node("frontend/x.ts::altro", type="code", kind="function",
               name="altro", file="frontend/x.ts", dev_type="frontend")
    G.add_edge("backend/app/svc.py::handle_beta", "spec.md#00-sezione",
               relation="IMPLEMENTS", weight=0.9)
    G.add_edge("backend/app/api.py::get_beta", "backend/app/svc.py::handle_beta",
               relation="DEPENDS_ON")
    return G


@pytest.fixture
def staging(tmp_path, monkeypatch):
    base = tmp_path / "staging"
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", base)
    return base


# ---------------------------------------------------------------------------
# Precondizione: senza import riuscito il brief non parte
# ---------------------------------------------------------------------------
def test_require_applied_import_without_import_raises(staging):
    with pytest.raises(project_brief.BriefWithoutImportError):
        project_brief.require_applied_import("backend", base_dir=staging)


def test_require_applied_import_invalid_target_raises(staging):
    with pytest.raises(project_import.InvalidImportTargetError):
        project_brief.require_applied_import("altrove", base_dir=staging)


def test_require_applied_import_finds_journal_entry(staging):
    rec = _journal_applied_import(staging)
    found = project_brief.require_applied_import("backend", base_dir=staging)
    assert found["id"] == rec["id"]
    # l'import di un ALTRO target non abilita questo
    with pytest.raises(project_brief.BriefWithoutImportError):
        project_brief.require_applied_import("frontend", base_dir=staging)


# ---------------------------------------------------------------------------
# Grounding deterministico sul grafo
# ---------------------------------------------------------------------------
def test_collect_target_facts_only_target_symbols_and_edges():
    facts = project_brief.collect_target_facts(_graph_with_backend_symbols(), {}, "backend")
    ids = [s["id"] for s in facts["simboli"]]
    assert facts["n_simboli"] == 2
    assert "backend/app/svc.py::handle_beta" in ids
    assert "frontend/x.ts::altro" not in ids           # altro dev_type escluso
    assert [e["id"] for e in facts["entrypoint"]] == ["backend/app/api.py::get_beta"]
    assert facts["dipendenze"] == [("backend/app/api.py::get_beta",
                                    "backend/app/svc.py::handle_beta")]
    assert facts["implements"] == [{"symbol": "backend/app/svc.py::handle_beta",
                                    "spec": "spec.md#00-sezione", "weight": 0.9}]


def test_collect_target_facts_empty_graph_is_zero():
    assert project_brief.collect_target_facts(None, {}, "backend")["n_simboli"] == 0
    assert project_brief.collect_target_facts(nx.DiGraph(), {}, "backend")["n_simboli"] == 0


def test_brief_prompt_contains_real_graph_data_and_no_invention_rule(staging):
    """Il prompt è GROUNDED: contiene i simboli, gli archi IMPLEMENTS/DEPENDS_ON reali
    e il divieto esplicito di inventare — mai un brief 'a memoria' del modello."""
    _journal_applied_import(staging)
    prompts: list[str] = []

    def _capture(prompt: str) -> str:
        prompts.append(prompt)
        return _VALID_BRIEF_MD

    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=_capture)

    assert result["n_generati"] == 1 and result["avviso"] is None
    prompt = prompts[0]
    assert "handle_beta" in prompt and "get_beta" in prompt
    assert "IMPLEMENTS" in prompt and "spec.md#00-sezione" in prompt
    assert "DEPENDS_ON" in prompt
    assert "NON inventare" in prompt
    assert "route /api/beta" in prompt or "/api/beta" in prompt


# ---------------------------------------------------------------------------
# Esiti del job: staging source "brief", avviso senza simboli, scarti, LLM giù
# ---------------------------------------------------------------------------
def test_brief_result_is_staged_with_source_brief_and_metadata(staging):
    rec = _journal_applied_import(staging)
    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=lambda p: _VALID_BRIEF_MD)

    staged = intake.list_staged(staging)
    assert [e["id"] for e in staged] == [result["generati"][0]["id"]]
    entry = staged[0]
    assert entry["source"] == "brief"
    assert entry["metadata"]["target"] == "backend"
    assert entry["metadata"]["import_id"] == rec["id"]
    assert entry["metadata"]["categoria_suggerita"] == project_brief.BRIEF_CATEGORIA_SUGGERITA
    assert entry["metadata"]["n_simboli_grounding"] == 2


def test_brief_graph_without_target_symbols_is_done_with_avviso_no_llm(staging):
    """Grafo senza simboli per il target → esito con avviso, MAI un crash e MAI una
    chiamata LLM (niente dati reali, niente brief inventato)."""
    _journal_applied_import(staging)

    def _never(prompt):
        raise AssertionError("l'LLM non deve essere chiamato senza simboli")

    result = project_brief.generate_project_brief(
        "backend", graph=nx.DiGraph(), code_store={}, base_dir=staging, generate=_never)
    assert result["n_generati"] == 0 and result["n_scartati"] == 0
    assert "nessun simbolo" in result["avviso"]
    assert intake.list_staged(staging) == []


def test_brief_without_import_raises_before_llm(staging):
    with pytest.raises(project_brief.BriefWithoutImportError):
        project_brief.generate_project_brief(
            "backend", graph=_graph_with_backend_symbols(), code_store={},
            base_dir=staging, generate=lambda p: _VALID_BRIEF_MD)


def test_brief_malformed_output_is_discarded_with_motivo(staging):
    _journal_applied_import(staging)
    broken = "---\ntitle: [yaml rotto\n---\ncorpo\n"
    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=lambda p: broken)

    assert result["n_generati"] == 0 and result["n_scartati"] == 1
    assert result["scartati"][0]["motivo"]
    assert intake.list_staged(staging) == []          # mai entrato in staging
    # il motivo resta rintracciabile nel journal (stato 'discarded', source 'brief')
    lines = [json.loads(l) for l in
             (staging / "intake.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    discarded = [l for l in lines if l.get("status") == "discarded"]
    assert discarded and discarded[0]["source"] == "brief"


def test_brief_llm_error_raises_generation_error(staging):
    from core import llm
    _journal_applied_import(staging)

    def _down(prompt):
        raise llm.LLMError("Ollama irraggiungibile")

    with pytest.raises(GenerationError, match="Ollama irraggiungibile"):
        project_brief.generate_project_brief(
            "backend", graph=_graph_with_backend_symbols(), code_store={},
            base_dir=staging, generate=_down)


def test_brief_never_writes_docs_directly(tmp_path, staging, monkeypatch):
    """Test negativo del piano: il brief non scrive MAI direttamente in docs/ — entra
    in staging e docs/ resta intatto finché la review S2 non approva."""
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setattr(intake, "DOCS_DIR", docs)
    _journal_applied_import(staging)

    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=lambda p: _VALID_BRIEF_MD)

    assert result["n_generati"] == 1
    assert list(docs.rglob("*")) == []                # docs/ mai toccato dal brief
    assert intake.list_staged(staging)                # il brief è in staging, in attesa


# ---------------------------------------------------------------------------
# Route /api/intake/project/brief (wiring HTTP, job async reale su thread daemon)
# ---------------------------------------------------------------------------
def _client(tmp_path, monkeypatch) -> TestClient:
    from api import routes_intake
    from core import doc_generation
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(routes_intake, "_brief_manager", doc_generation.GenerationManager())
    app = FastAPI()
    app.include_router(routes_intake.router)
    return TestClient(app, client=("127.0.0.1", 54321))


def test_route_brief_without_import_returns_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/intake/project/brief", json={"target": "backend"})
    assert resp.status_code == 409
    assert "import" in resp.json()["detail"]


def test_route_brief_invalid_target_returns_422(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/api/intake/project/brief", json={"target": "altrove"})
    assert resp.status_code == 422


def test_route_brief_202_then_done_and_status_404_on_unknown(tmp_path, monkeypatch):
    from api import routes_intake
    client = _client(tmp_path, monkeypatch)
    _journal_applied_import(tmp_path / "staging")
    monkeypatch.setattr(routes_intake, "_server_brief", lambda target: {
        "target": target, "generati": [{"id": "abc"}], "scartati": [],
        "n_generati": 1, "n_scartati": 0, "avviso": None,
        "latency": {"generation_ms": 1.0, "total_ms": 2.0}})

    resp = client.post("/api/intake/project/brief", json={"target": "backend"})
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert routes_intake._brief_manager.join_all(timeout=5)

    status = client.get(f"/api/intake/project/brief/{job_id}")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done" and body["result"]["n_generati"] == 1
    assert client.get("/api/intake/project/brief/non-esiste").status_code == 404


def test_route_brief_job_failure_is_reported_not_raised(tmp_path, monkeypatch):
    from api import routes_intake
    client = _client(tmp_path, monkeypatch)
    _journal_applied_import(tmp_path / "staging")

    def _boom(target):
        raise GenerationError("generazione brief fallita: Ollama irraggiungibile")

    monkeypatch.setattr(routes_intake, "_server_brief", _boom)
    resp = client.post("/api/intake/project/brief", json={"target": "backend"})
    assert resp.status_code == 202
    assert routes_intake._brief_manager.join_all(timeout=5)
    body = client.get(f"/api/intake/project/brief/{resp.json()['job_id']}").json()
    assert body["status"] == "failed" and "Ollama irraggiungibile" in body["error"]


# ---------------------------------------------------------------------------
# E2E dell'intera evoluzione (LLM mockato): import → reindex → brief → staged →
# approve → una retrieve di test (hybrid_search vera) lo trova.
# ---------------------------------------------------------------------------
class QueryableFakeQdrant(StatefulFakeQdrant):
    """StatefulFakeQdrant + query_points: ranking per coseno sui vettori densi
    memorizzati (per la query sparse risponde vuoto: la fusione della hybrid_search
    degrada al solo ramo dense, sufficiente per l'e2e con StubEmbed)."""

    def query_points(self, collection_name, query, using, limit, query_filter=None):
        if using != "dense" or not isinstance(query, list):
            return SimpleNamespace(points=[])
        q = np.asarray(query, dtype="float32")
        qn = q / (np.linalg.norm(q) + 1e-8)
        scored = []
        for p in self.points.values():
            vec = p.vector.get("dense") if isinstance(p.vector, dict) else None
            if vec is None:
                continue
            v = np.asarray(vec, dtype="float32")
            score = float(qn @ (v / (np.linalg.norm(v) + 1e-8)))
            scored.append(SimpleNamespace(payload=p.payload, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return SimpleNamespace(points=scored[:limit])


def test_e2e_import_reindex_brief_staged_approve_retrieve(tmp_path, monkeypatch):
    """Il ciclo completo del piano S6: mini-progetto importato in code/ sandbox →
    reindex delta → project brief grounded (LLM mockato) → staged (source 'brief') →
    approve col flusso S2 → il documento è nell'indice e una hybrid_search lo trova."""
    docs_dir, code_dir = _wire_tmp_index(monkeypatch, tmp_path)
    staging = tmp_path / "staging"
    monkeypatch.setattr(intake, "INTAKE_STAGING_DIR", staging)
    monkeypatch.setattr(intake, "DOCS_DIR", docs_dir)
    # L'eval-gate del full build valuta la recall sul golden set REALE (34 casi sul
    # corpus di produzione): sul corpus giocattolo di questo e2e non ha senso e
    # bloccherebbe la promozione. Neutralizzato: qui si testa il flusso Intake, non il
    # gate (coperto da test_eval_gate.py). L'incrementale non ha gate bloccante.
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    lock = tmp_path / "writer.lock"
    stub, q = StubEmbed(), QueryableFakeQdrant()

    # Indice blue/green già stabilito (full build), com'è un sistema reale prima di
    # importare un progetto: una spec che parla di ALPHA.
    (docs_dir / "spec.md").write_text("## Sezione\n[ALPHA] regola su ALPHA\n", encoding="utf-8")
    index.build_graph_and_index(qdrant=q, embed_model=stub)

    # 1) Import del mini-progetto (plan/apply S5) con reindex DELTA reale sopra l'indice
    #    esistente: l'import copia i file, il reindex incrementale vede il nuovo codice.
    src = tmp_path / "sorgente"
    (src / "app").mkdir(parents=True)
    (src / "app" / "svc.py").write_text(
        "def handle_alpha():\n    # gestisce ALPHA\n    return 'ALPHA'\n", encoding="utf-8")
    plan = project_import.plan_project_import(str(src), "backend", code_dir=code_dir)
    applied = project_import.apply_project_import(
        plan, code_dir=code_dir, base_dir=staging, lock_path=lock,
        reindex=lambda paths: index.incremental_index(qdrant=q, embed_model=stub))
    assert applied["status"] == "applied" and applied["reindex_error"] is None

    # 2) Il reindex ha portato il simbolo del target nel grafo. L'import (S5) copia il
    #    progetto in una SOTTOCARTELLA col nome della sorgente (code/backend/sorgente/...),
    #    quindi il simbolo vive sotto quel prefisso; il dev_type resta il primo segmento.
    arts = _artifacts.load_artifacts()
    code_id = "backend/sorgente/app/svc.py::handle_alpha"
    assert code_id in arts.graph and arts.graph.nodes[code_id]["dev_type"] == "backend"

    # 3) Project brief grounded (LLM mockato): il prompt vede il simbolo reale.
    prompts: list[str] = []

    def _llm(prompt: str) -> str:
        prompts.append(prompt)
        return _VALID_BRIEF_MD

    result = project_brief.generate_project_brief(
        "backend", graph=arts.graph, code_store=arts.code_store,
        base_dir=staging, generate=_llm)
    assert result["n_generati"] == 1
    assert "handle_alpha" in prompts[0]
    assert list(docs_dir.rglob("brief*")) == []       # niente scrittura diretta in docs/

    # 4) Review S2: approve → docs/ + reindex delta → chunk nell'indice.
    staged_id = result["generati"][0]["id"]
    approved = intake.approve(
        staged_id, "04_knowledge_informative", "brief-backend",
        reindex=lambda paths: index.incremental_index(qdrant=q, embed_model=stub),
        lock_path=lock)
    doc_rel = "04_knowledge_informative/brief-backend.md"
    assert approved["status"] == "approved"
    assert (docs_dir / doc_rel).exists()

    # 5) Una retrieve di test lo trova: il brief parla di BETA (la spec di ALPHA),
    #    quindi la hybrid_search su BETA deve riportare il documento del brief.
    arts2 = _artifacts.load_artifacts()
    results = retrieval.hybrid_search(
        "come viene gestita BETA?", 5, qdrant=q, embed_model=stub,
        colbert_store=arts2.colbert_store)
    assert any(r["doc_id"] == doc_rel for r in results), results
    assert results and results[0]["doc_id"] == doc_rel  # BETA vive solo nel brief
