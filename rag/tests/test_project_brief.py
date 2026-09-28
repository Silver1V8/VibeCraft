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
def _journal_applied_import(staging, target="backend", rec_id="prj-e2e",
                            src="C:/altrove/progetto", applied_at="2026-01-01T00:00:00Z") -> dict:
    """Scrive nel journal l'entry di un import progetto riuscito (stesso formato di
    core.project_import.apply_project_import). `src` conta: il nome della sua ultima
    cartella è il progetto sotto code/<target>/ su cui il brief si concentra."""
    paths = intake.ensure_staging_dirs(staging)
    record = {"id": rec_id, "type": "project_import", "status": "applied",
              "target": target, "src": src, "mode": "bootstrap",
              "applied_at": applied_at}
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
    """Grafo con i simboli di UN progetto (code/backend/progetto/), la struttura che
    project_import produce sempre: code/<target>/<nome cartella sorgente>/…"""
    G = nx.DiGraph()
    G.add_node("spec.md", type="document")
    G.add_node("spec.md#00-sezione", type="section", doc_id="spec.md")
    G.add_node("backend/progetto/app/svc.py::handle_beta", type="code", kind="function",
               name="handle_beta", file="backend/progetto/app/svc.py", dev_type="backend")
    G.add_node("backend/progetto/app/api.py::get_beta", type="code", kind="endpoint",
               name="get_beta", file="backend/progetto/app/api.py", dev_type="backend",
               route="/api/beta")
    G.add_node("frontend/x.ts::altro", type="code", kind="function",
               name="altro", file="frontend/x.ts", dev_type="frontend")
    G.add_edge("backend/progetto/app/svc.py::handle_beta", "spec.md#00-sezione",
               relation="IMPLEMENTS", weight=0.9)
    G.add_edge("backend/progetto/app/api.py::get_beta",
               "backend/progetto/app/svc.py::handle_beta", relation="DEPENDS_ON")
    return G


def _graph_with_two_backend_projects() -> nx.DiGraph:
    """Due progetti nello stesso bucket `backend`, come dopo due import additivi in
    code/backend/. Il primo in ordine alfabetico è quello che il vecchio grounding
    (filtrato per solo dev_type) faceva finire nel prompt a scapito dell'altro."""
    G = _graph_with_backend_symbols()
    G.add_node("backend/altro-progetto/legacy.py::vecchia_funzione", type="code",
               kind="function", name="vecchia_funzione",
               file="backend/altro-progetto/legacy.py", dev_type="backend")
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
    assert "backend/progetto/app/svc.py::handle_beta" in ids
    assert "frontend/x.ts::altro" not in ids           # altro dev_type escluso
    assert [e["id"] for e in facts["entrypoint"]] == ["backend/progetto/app/api.py::get_beta"]
    assert facts["dipendenze"] == [("backend/progetto/app/api.py::get_beta",
                                    "backend/progetto/app/svc.py::handle_beta")]
    assert facts["implements"] == [{"symbol": "backend/progetto/app/svc.py::handle_beta",
                                    "spec": "spec.md#00-sezione", "weight": 0.9}]


# ---------------------------------------------------------------------------
# Granularità del grounding: il brief è di un PROGETTO, non di un bucket.
#
# Regressione 2026-07-23: code/backend/ ospitava GD102_WSGDAProtocolloManager e
# GD172_WSProtocollo (import additivi, entrambi legittimi). collect_target_facts
# filtrava per solo `dev_type == "backend"`, quindi prendeva i simboli di ENTRAMBI;
# l'ordinamento per id e il tetto _MAX_SIMBOLI_NEL_PROMPT riempivano il prompt col
# primo progetto in ordine alfabetico. Il brief richiesto per WSProtocollo descriveva
# WSGDAProtocolloManager — modello fedele a dati di grounding sbagliati.
# ---------------------------------------------------------------------------
def test_collect_target_facts_restricts_to_project_folder():
    graph = _graph_with_two_backend_projects()
    facts = project_brief.collect_target_facts(graph, {}, "backend", progetto="progetto")
    ids = [s["id"] for s in facts["simboli"]]
    assert facts["n_simboli"] == 2
    assert facts["n_simboli_target"] == 3        # il bucket ne ha di più: lo dichiara
    assert "backend/altro-progetto/legacy.py::vecchia_funzione" not in ids


def test_collect_target_facts_without_progetto_takes_whole_bucket():
    facts = project_brief.collect_target_facts(
        _graph_with_two_backend_projects(), {}, "backend")
    assert facts["n_simboli"] == 3 and facts["progetto"] is None


# ---------------------------------------------------------------------------
# Campionamento dei simboli nel prompt.
#
# Un progetto reale ha migliaia di simboli e nel prompt ne stanno _MAX_SIMBOLI_NEL_PROMPT
# (num_ctx 16384). Prima il campione era `simboli[:80]` su una lista ordinata per id,
# cioè per path: di GD172_WSProtocollo (4100 simboli, 309 file) il brief vedeva solo le
# cartelle iniziali in ordine alfabetico, e degli 337 endpoint solo quelli che iniziano
# per A. Il campione ora è scelto, non troncato.
# ---------------------------------------------------------------------------
def _sym(id_, kind, file, name=None):
    return {"id": id_, "kind": kind, "file": file, "name": name or id_.split("::")[-1]}


def test_seleziona_simboli_spreads_across_files_instead_of_taking_one_file():
    """Un file generato con centinaia di simboli non deve mangiarsi il budget."""
    grosso = [_sym(f"p/Reference.cs::G{i:03d}", "class", "p/Reference.cs") for i in range(300)]
    altri = [_sym(f"p/mod{i}/File.cs::C{i}", "class", f"p/mod{i}/File.cs") for i in range(20)]
    scelti = project_brief.seleziona_simboli(grosso + altri, {}, 10)

    assert len(scelti) == 10
    assert len({s["file"] for s in scelti}) == 10        # dieci file diversi
    assert sum(1 for s in scelti if s["file"] == "p/Reference.cs") == 1


def test_seleziona_simboli_prefers_types_and_entrypoints_over_properties():
    """A parità di file, un brief architetturale vuole i tipi, non le property."""
    simboli = ([_sym(f"p/a.cs::Prop{i}", "property", "p/a.cs") for i in range(50)]
               + [_sym("p/a.cs::Servizio", "class", "p/a.cs"),
                  _sym("p/a.cs::IServizio", "interface", "p/a.cs")])
    scelti = project_brief.seleziona_simboli(simboli, {}, 2)
    assert {s["name"] for s in scelti} == {"IServizio", "Servizio"}


def test_seleziona_simboli_breaks_ties_by_graph_degree():
    """Stessa natura e stesso file: entra prima chi è più connesso nel sottografo."""
    simboli = [_sym("p/a.cs::Isolato", "class", "p/a.cs"),
               _sym("p/a.cs::Hub", "class", "p/a.cs")]
    scelti = project_brief.seleziona_simboli(simboli, {"p/a.cs::Hub": 12}, 1)
    assert [s["name"] for s in scelti] == ["Hub"]


def test_seleziona_simboli_samples_a_long_homogeneous_run_with_a_stride():
    """337 operazioni nella stessa interfaccia: il campione deve attraversare tutto
    l'elenco, non fermarsi alle prime lettere dell'alfabeto."""
    endpoint = [_sym(f"p/api.cs::Op{i:03d}", "endpoint", "p/api.cs") for i in range(300)]
    scelti = project_brief.seleziona_simboli(endpoint, {}, 10)

    assert len(scelti) == 10
    indici = [int(s["name"][2:]) for s in scelti]
    assert indici[0] == 0 and indici[-1] == 299          # primo e ultimo compresi
    assert max(indici) - min(indici) == 299              # spazza l'intero elenco


def test_seleziona_simboli_returns_everything_below_the_limit():
    simboli = [_sym("p/a.cs::A", "class", "p/a.cs"), _sym("p/b.cs::B", "class", "p/b.cs")]
    assert len(project_brief.seleziona_simboli(simboli, {}, 80)) == 2
    assert project_brief.seleziona_simboli(simboli, {}, 0) == []
    assert project_brief.seleziona_simboli([], {}, 80) == []


def test_facts_report_modules_covering_every_symbol():
    """I conteggi per modulo coprono il progetto INTERO: sono l'unico pezzo di grounding
    che il campione non può dare."""
    graph = _graph_with_backend_symbols()
    facts = project_brief.collect_target_facts(graph, {}, "backend", progetto="progetto")
    assert sum(m["n_simboli"] for m in facts["moduli"]) == facts["n_simboli"]
    assert [m["nome"] for m in facts["moduli"]] == ["app"]


def test_prompt_stays_within_context_budget_on_a_large_project():
    """Con migliaia di simboli dai path lunghi il prompt deve restare ben dentro
    num_ctx 16384 — quello che sfora Ollama lo taglia dall'INIZIO, cioè via le
    istruzioni, lasciando al modello una lista di simboli senza il compito."""
    graph = nx.DiGraph()
    for i in range(4000):
        nid = (f"backend/GD172_WSProtocollo/WSProtocolloService/Service References/"
               f"WSGDAProtocolloManager/Cartella{i % 300}/Reference.cs::TipoMoltoLungo{i}")
        graph.add_node(nid, type="code", kind="class" if i % 3 else "property",
                       name=f"TipoMoltoLungo{i}", dev_type="backend",
                       file=nid.split("::")[0])
    facts = project_brief.collect_target_facts(graph, {}, "backend",
                                               progetto="GD172_WSProtocollo")
    prompt = project_brief.build_brief_prompt("backend", facts)

    assert facts["n_simboli"] == 4000
    assert len(prompt) < 28000, f"prompt di {len(prompt)} caratteri: troppo per num_ctx 16384"
    assert "4000 simboli" in prompt or "tutti i 4000" in prompt
    assert "CAMPIONE" in prompt          # il modello sa che l'elenco è parziale
    # i path non ripetono la radice del progetto su ogni riga
    assert "backend/GD172_WSProtocollo/WSProtocolloService" not in prompt.split("REGOLE")[0].split("Moduli")[1]


def test_progetto_di_handles_both_separators():
    assert project_brief.progetto_di(r"C:\Progetti\Dimension\GD172_WSProtocollo") \
        == "GD172_WSProtocollo"
    assert project_brief.progetto_di("/home/x/GD172_WSProtocollo/") == "GD172_WSProtocollo"
    assert project_brief.progetto_di("") == ""


def test_applied_imports_lists_one_entry_per_project(staging):
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\GD102_WSGDA",
                            applied_at="2026-07-23T08:02:00Z")
    _journal_applied_import(staging, rec_id="p2", src=r"C:\src\GD172_WSProtocollo",
                            applied_at="2026-07-23T08:33:00Z")
    _journal_applied_import(staging, rec_id="p3", src=r"C:\src\GD172_WSProtocollo",
                            applied_at="2026-07-23T08:36:00Z")   # reimport: non duplica
    _journal_applied_import(staging, target="frontend", rec_id="p4", src=r"C:\src\web")

    voci = project_brief.applied_imports("backend", base_dir=staging)
    assert [v["progetto"] for v in voci] == ["GD102_WSGDA", "GD172_WSProtocollo"]
    assert voci[-1]["import_id"] == "p3"        # del progetto vince l'import più recente
    assert [v["progetto"] for v in project_brief.applied_imports(base_dir=staging)] \
        == ["web", "GD102_WSGDA", "GD172_WSProtocollo"]


def test_applied_imports_does_not_create_staging_area(staging):
    """GET /api/intake/project/imports (SECURITY_SURFACE.md §1 riga 55) è classificata
    read-only: senza import mai avvenuti, staging/ non esiste — la lettura non deve
    materializzarla. Fallisce senza il fix (applied_imports passava da
    intake.ensure_staging_dirs)."""
    assert not staging.exists()
    assert project_brief.applied_imports("backend", base_dir=staging) == []
    assert not staging.exists()


def test_brief_defaults_to_last_imported_project_not_the_whole_target(staging):
    """Il caso reale: due progetti in code/backend/, l'ultimo importato è quello di cui
    l'utente vuole il brief. Il prompt deve contenere i suoi simboli e NON quelli
    dell'altro progetto."""
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\altro-progetto",
                            applied_at="2026-07-23T08:02:00Z")
    _journal_applied_import(staging, rec_id="p2", src=r"C:\src\progetto",
                            applied_at="2026-07-23T08:36:00Z")
    prompts: list[str] = []

    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_two_backend_projects(), code_store={},
        base_dir=staging, generate=lambda p: prompts.append(p) or _VALID_BRIEF_MD)

    assert result["progetto"] == "progetto"
    assert "handle_beta" in prompts[0]
    assert "vecchia_funzione" not in prompts[0]
    assert "code/backend/progetto" in prompts[0]
    staged = intake.list_staged(staging)
    assert staged[0]["metadata"]["progetto"] == "progetto"
    assert staged[0]["files"]["markdown"].startswith("brief-progetto-") or \
        "progetto" in staged[0]["metadata"]["source_filename"]


def test_brief_explicit_progetto_selects_the_other_one(staging):
    """Un progetto importato in precedenza resta raggiungibile: si passa il suo nome."""
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\altro-progetto",
                            applied_at="2026-07-23T08:02:00Z")
    _journal_applied_import(staging, rec_id="p2", src=r"C:\src\progetto",
                            applied_at="2026-07-23T08:36:00Z")
    prompts: list[str] = []

    result = project_brief.generate_project_brief(
        "backend", progetto="altro-progetto", graph=_graph_with_two_backend_projects(),
        code_store={}, base_dir=staging,
        generate=lambda p: prompts.append(p) or _VALID_BRIEF_MD)

    assert result["progetto"] == "altro-progetto"
    assert "vecchia_funzione" in prompts[0] and "handle_beta" not in prompts[0]


def test_brief_unknown_progetto_raises_with_available_list(staging):
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\progetto")
    with pytest.raises(project_brief.BriefWithoutImportError, match="progetto"):
        project_brief.generate_project_brief(
            "backend", progetto="mai-importato", graph=_graph_with_backend_symbols(),
            code_store={}, base_dir=staging, generate=lambda p: _VALID_BRIEF_MD)


def test_brief_project_without_symbols_says_the_target_has_others(staging):
    """Progetto senza simboli ma bucket popolato: l'avviso deve dirlo, invece di far
    credere che il reindex non sia passato."""
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\progetto-vuoto")

    def _never(prompt):
        raise AssertionError("l'LLM non deve essere chiamato senza simboli")

    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=_never)
    assert result["n_generati"] == 0
    assert "progetto-vuoto" in result["avviso"] and "altri progetti" in result["avviso"]


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


def test_brief_with_unterminated_frontmatter_is_repaired_and_staged(staging):
    """Regressione 2026-07-22 (brief di WSProtocollo su target backend): il modello aveva
    APERTO il frontmatter senza chiuderlo, il corpo Markdown era finito dentro il YAML e
    la riga `-   **Progetto Core**: ...` aveva fatto esplodere il parser (il `*` apre un
    alias YAML) — brief scartato pur avendo un corpo perfettamente valido. Ora il contorno
    si ripara e il documento arriva in staging, dove la review S2 decide come sempre."""
    _journal_applied_import(staging)
    aperto = ("---\ntitle: Project brief backend\nscope: sintesi architetturale\n\n"
              "# Project brief backend\n\n## Componenti\n\n"
              "-   **Progetto Core**: `WSProtocollo` è il servizio principale\n")
    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=lambda p: aperto)

    assert result["n_generati"] == 1 and result["n_scartati"] == 0
    staged = intake.list_staged(staging)
    assert len(staged) == 1 and staged[0]["source"] == "brief"


def test_brief_malformed_output_is_discarded_with_motivo(staging):
    """Un output senza NULLA da tenere (solo frontmatter, corpo vuoto) resta scartato:
    la riparazione del contorno non deve trasformare in documento ciò che non lo è."""
    _journal_applied_import(staging)
    broken = "---\ntitle: solo frontmatter\nscope: nessun corpo\n---\n"
    result = project_brief.generate_project_brief(
        "backend", graph=_graph_with_backend_symbols(), code_store={},
        base_dir=staging, generate=lambda p: broken)

    assert result["n_generati"] == 0 and result["n_scartati"] == 1
    assert result["scartati"][0]["motivo"]
    assert intake.list_staged(staging) == []          # mai entrato in staging
    # il motivo resta rintracciabile nel journal (stato 'discarded', source 'brief')
    lines = [json.loads(line) for line in
             (staging / "intake.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    discarded = [entry for entry in lines if entry.get("status") == "discarded"]
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
    monkeypatch.setattr(routes_intake, "_server_brief", lambda target, progetto: {
        "target": target, "progetto": progetto, "generati": [{"id": "abc"}],
        "scartati": [], "n_generati": 1, "n_scartati": 0, "avviso": None,
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

    def _boom(target, progetto):
        raise GenerationError("generazione brief fallita: Ollama irraggiungibile")

    monkeypatch.setattr(routes_intake, "_server_brief", _boom)
    resp = client.post("/api/intake/project/brief", json={"target": "backend"})
    assert resp.status_code == 202
    assert routes_intake._brief_manager.join_all(timeout=5)
    body = client.get(f"/api/intake/project/brief/{resp.json()['job_id']}").json()
    assert body["status"] == "failed" and "Ollama irraggiungibile" in body["error"]


def test_route_brief_unknown_progetto_returns_409_listing_available(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _journal_applied_import(tmp_path / "staging", src=r"C:\src\progetto")
    resp = client.post("/api/intake/project/brief",
                       json={"target": "backend", "progetto": "mai-importato"})
    assert resp.status_code == 409
    assert "progetto" in resp.json()["detail"]


def test_route_project_imports_lists_projects_per_target(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    staging = tmp_path / "staging"
    _journal_applied_import(staging, rec_id="p1", src=r"C:\src\GD102_WSGDA",
                            applied_at="2026-07-23T08:02:00Z")
    _journal_applied_import(staging, rec_id="p2", src=r"C:\src\GD172_WSProtocollo",
                            applied_at="2026-07-23T08:36:00Z")
    _journal_applied_import(staging, target="frontend", rec_id="p3", src=r"C:\src\web")

    body = client.get("/api/intake/project/imports?target=backend").json()
    assert [v["progetto"] for v in body["imports"]] == ["GD102_WSGDA", "GD172_WSProtocollo"]
    assert client.get("/api/intake/project/imports?target=altrove").status_code == 422


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
