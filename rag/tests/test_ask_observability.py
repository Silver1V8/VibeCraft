"""Test M3: log strutturato di fine richiesta di POST /ask (request_id, index_version,
qdrant_collection/alias, retrieval_strategy, top_k/n_results, latenze) e campi additivi
in risposta (request_id, index_version). Copre anche la cache {version: qdrant_collection}
di api.deps.qdrant_collection_for_version: il manifest si legge dal disco UNA volta per
versione, mai per-request."""
import json
import logging

from dataclasses import replace

import networkx as nx
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.deps as deps
from api import routes_retrieval
from core import llm, retrieval

_CHUNK_ID = "spec.md#01-form"


class _StubEmbed:
    """Modello di embedding minimo per i test di /ask: da S3 il route codifica SEMPRE la
    domanda (la forward pass avviene comunque dentro hybrid_search, spostarla nel route non
    costa nulla in più), quindi lo stub deve saper rispondere a encode() anche quando
    hybrid_search è finto. Vettori costanti: nessun test qui misura la similarità."""

    def encode(self, texts, **kw):
        n = len(texts)
        out = {"dense_vecs": np.zeros((n, 4), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.zeros((1, 4), dtype="float32") for _ in texts]
        return out



def _snapshot(version) -> deps.IndexSnapshot:
    g = nx.DiGraph()
    g.add_node("spec.md", type="document")
    g.add_node("glossario.md", type="document")
    g.add_node(_CHUNK_ID, type="chunk")
    g.add_edge("spec.md", _CHUNK_ID, relation="HAS_SECTION")
    return deps.IndexSnapshot(
        graph=g,
        colbert_store={},
        chunks={_CHUNK_ID: {"text": "testo della sezione"}},
        rule_descriptions={},
        code_store={},
        version=version,
        code_ids=[],
        code_matrix=None,
    )


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    """La cache di qdrant_collection_for_version è a livello di modulo (sopravvive tra
    i test): la svuotiamo prima di ogni test così ciascuno parte da zero letture."""
    deps._qdrant_collection_by_version.clear()
    yield
    deps._qdrant_collection_by_version.clear()


@pytest.fixture
def ask_env(monkeypatch, tmp_path):
    """Factory di TestClient con la sola route /ask: stato del server (snapshot, qdrant,
    embed_model), hybrid_search e provider LLM finti. `manifest` (se non None) viene
    scritto su disco in tmp_path e api.deps.manifest_path viene fatto puntare lì, così i
    test controllano il contenuto del manifest senza toccare database/ reale."""
    monkeypatch.setattr(deps, "API_KEY", None)

    settings = {"active_provider": "fake", "models": {"fake": "fake-model"}, "purposes": {}}
    monkeypatch.setitem(llm.config, "llm_settings", settings)
    llm.register_provider("fake", lambda model, prompt, timeout: "RISPOSTA")

    def _make(version="v20260101T000000", manifest: dict | None = None,
              manifest_exists: bool = True):
        snap = _snapshot(version)
        monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
        monkeypatch.setitem(deps.state, "qdrant", object())
        monkeypatch.setitem(deps.state, "embed_model", _StubEmbed())
        results = [{"chunk_id": _CHUNK_ID, "doc_id": "spec.md", "section": "form",
                    "dense_score": 0.9, "colbert_score": None}]
        monkeypatch.setattr(retrieval, "hybrid_search", lambda *a, **kw: results)

        manifest_file = tmp_path / f"manifest-{version}.json"
        if manifest_exists:
            manifest_file.write_text(
                json.dumps(manifest if manifest is not None else {"qdrant_collection": "vc__" + str(version)}),
                encoding="utf-8",
            )
        monkeypatch.setattr(deps, "manifest_path", lambda v, project=None: manifest_file)

        app = FastAPI()
        app.include_router(routes_retrieval.router)
        return TestClient(app, client=("127.0.0.1", 54321))

    return _make


# ---------------------------------------------------------------------------
# La riga di log contiene tutte le chiavi elencate
# ---------------------------------------------------------------------------
def test_ask_log_contiene_tutte_le_chiavi(ask_env, caplog):
    client = ask_env(version="v1", manifest={"qdrant_collection": "vibecraft_docs__v1"})

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "api.routes_retrieval"
               and rec.message.startswith("ask ")]
    assert len(records) == 1
    line = records[0].message
    for key in ("request_id=", "index_version=", "qdrant_collection=", "qdrant_alias=",
                "retrieval_strategy=", "top_k=", "n_results=", "latency_retrieval_ms=",
                "latency_generation_ms=", "latency_total_ms="):
        assert key in line
    assert "qdrant_collection=vibecraft_docs__v1" in line
    assert "index_version=v1" in line
    assert "retrieval_strategy=hybrid" in line
    assert "top_k=5" in line
    assert "n_results=1" in line


# ---------------------------------------------------------------------------
# La risposta contiene request_id e index_version
# ---------------------------------------------------------------------------
def test_ask_risposta_contiene_request_id_e_index_version(ask_env):
    client = ask_env(version="v2", manifest={"qdrant_collection": "vibecraft_docs__v2"})

    r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    body = r.json()
    assert body["index_version"] == "v2"
    request_id = body["request_id"]
    assert isinstance(request_id, str) and len(request_id) == 32
    int(request_id, 16)  # hex valido (uuid4().hex)

    # F3: campo "latency" additivo in risposta, stessi valori del log M3
    latency = body["latency"]
    assert set(latency) == {"retrieval_ms", "generation_ms", "total_ms"}
    assert latency["total_ms"] >= latency["generation_ms"]
    assert latency["total_ms"] >= latency["retrieval_ms"]


# ---------------------------------------------------------------------------
# F3: la risposta del ramo "graph" contiene lo stesso campo "latency"
# ---------------------------------------------------------------------------
def test_ask_risposta_graph_contiene_latency(ask_env):
    client = ask_env(version="v5", manifest={"qdrant_collection": "vibecraft_docs__v5"})

    r = client.post("/ask", json={"question": "quali documenti esistono nel corpus?"})

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "graph_answer"
    latency = body["latency"]
    assert set(latency) == {"retrieval_ms", "generation_ms", "total_ms"}
    assert latency["generation_ms"] == 0
    assert latency["total_ms"] >= latency["generation_ms"]
    assert latency["total_ms"] >= latency["retrieval_ms"]


# ---------------------------------------------------------------------------
# Cache del manifest: due richieste sulla stessa versione ⇒ una sola lettura file
# ---------------------------------------------------------------------------
def test_cache_manifest_una_sola_lettura_per_versione(ask_env, monkeypatch):
    client = ask_env(version="v3", manifest={"qdrant_collection": "vibecraft_docs__v3"})

    read_count = {"n": 0}
    from pathlib import Path
    original_read_text = Path.read_text

    def counting_read_text(self, *a, **kw):
        read_count["n"] += 1
        return original_read_text(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", counting_read_text)

    r1 = client.post("/ask", json={"question": "prima domanda"})
    r2 = client.post("/ask", json={"question": "seconda domanda"})

    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["index_version"] == r2.json()["index_version"] == "v3"
    assert read_count["n"] == 1


# ---------------------------------------------------------------------------
# Fallback "unknown" con manifest assente
# ---------------------------------------------------------------------------
def test_fallback_unknown_con_manifest_assente(ask_env, caplog):
    client = ask_env(version="v4", manifest_exists=False)

    with caplog.at_level(logging.INFO, logger="api.routes_retrieval"):
        r = client.post("/ask", json={"question": "Quali vincoli?"})

    assert r.status_code == 200
    records = [rec for rec in caplog.records if rec.name == "api.routes_retrieval"
               and rec.message.startswith("ask ")]
    assert "qdrant_collection=unknown" in records[0].message


# ---------------------------------------------------------------------------
# S3 (ADR 0002) — fase 6 di [REGOLA-WF-01]: le sezioni raggiunte SOLO via grafo
# ---------------------------------------------------------------------------
_CHUNK_VIA_GRAFO = "glossario.md#01-termini"


def _snapshot_con_vicino(version="v1") -> deps.IndexSnapshot:
    """Come _snapshot, ma glossario.md e' collegato a spec.md da un arco CURATO e ha una
    sezione propria: e' il documento che solo il grafo puo' far arrivare alla risposta."""
    snap = _snapshot(version)
    snap.graph.add_edge("spec.md", "glossario.md", relation="EREDITA_VINCOLI",
                        nature="curated", reliability=0.9)
    snap.chunks[_CHUNK_ID] = {"text": "testo della sezione", "doc_id": "spec.md", "section": "form"}
    snap.chunks[_CHUNK_VIA_GRAFO] = {"text": "definizione di EVENTO",
                                     "doc_id": "glossario.md", "section": "termini"}
    return snap


def test_graph_context_disattivato_non_cambia_il_contesto(ask_env, monkeypatch):
    """Con graph_context_max_chunks: 0 il contesto e' BYTE-IDENTICO a quello prodotto dal
    solo ramo semantico. E' il test che rende l'intervento reversibile in produzione con una
    riga di config.

    L'intestazione porta la CLASSE della fonte (A3): qui il documento del fixture non ha
    frontmatter, quindi "SENZA CLASSE" — che e' un'informazione, non un valore mancante."""
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot_con_vicino())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 0)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert ctx == "--- spec.md § form [SENZA CLASSE] ---\ntesto della sezione"
    assert "via grafo" not in ctx


def test_sezioni_da_grafo_sono_marcate_nel_contesto(ask_env, monkeypatch):
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot_con_vicino())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 2)
    body = client.post("/ask", json={"question": "q"}).json()
    ctx = body["graph_context"]["context_text"]
    # la sezione del vicino c'e', e porta il marcatore con hop e fiducia
    assert "definizione di EVENTO" in ctx
    assert "[SENZA CLASSE; via grafo: 1 hop, fiducia 0.900]" in ctx
    # il blocco del ramo semantico NON e' confondibile: nessun marcatore
    semantico, _, _ = ctx.partition("[via grafo")
    assert "testo della sezione" in semantico
    # il ramo semantico resta il primo del contesto (il grafo e' il complemento)
    assert ctx.index("testo della sezione") < ctx.index("definizione di EVENTO")
    # trust/hops esposti anche sui nodi, per la Mappa del Grafo
    nodi = {n["id"]: n for n in body["graph_context"]["expanded_nodes"]}
    assert nodi["spec.md"]["trust"] == 1.0 and nodi["spec.md"]["hops"] == 0
    assert nodi["glossario.md"]["trust"] == 0.9 and nodi["glossario.md"]["hops"] == 1


def test_ancore_codice_ordinate_per_fiducia(ask_env, monkeypatch):
    """Le ancore arrivano a collect_implementing_code ORDINATE per fiducia decrescente,
    non nell'ordine di iterazione di un set."""
    viste: list = []

    def _spia(graph, code_store, anchor_nodes, **kw):
        viste.append(list(anchor_nodes))
        return []

    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot_con_vicino())
    monkeypatch.setattr(retrieval, "collect_implementing_code", _spia)
    client.post("/ask", json={"question": "q"})

    ancore = viste[0]
    assert not isinstance(ancore, set)
    # spec.md (seed, 1.0) e il chunk recuperato (aggancio diretto, 1.0) precedono
    # glossario.md, raggiunto a 1 hop con fiducia 0.9
    assert ancore.index("spec.md") < ancore.index("glossario.md")
    assert ancore.index(_CHUNK_ID) < ancore.index("glossario.md")


# ---------------------------------------------------------------------------
# S3 (miglioria) + S4 nel ramo del grafo
# ---------------------------------------------------------------------------
_PREAMBOLO = "glossario.md#00-preambolo"
_APPENDICE = "spec.md#02-appendice"


class _EmbedColbert:
    """Stub che restituisce un vettore ColBERT di query NOTO, così il test può prevedere
    quale sezione risulta più pertinente."""

    def encode(self, texts, **kw):
        n = len(texts)
        out = {"dense_vecs": np.zeros((n, 2), dtype="float32")}
        if kw.get("return_sparse"):
            out["lexical_weights"] = [{} for _ in texts]
        if kw.get("return_colbert_vecs"):
            out["colbert_vecs"] = [np.array([[1.0, 0.0]], dtype="float32") for _ in texts]
        return out


def _snapshot_due_sezioni(version="v1") -> deps.IndexSnapshot:
    """glossario.md raggiunto via grafo con DUE sezioni: il preambolo (primo in ordine di
    file, per nulla pertinente) e i termini (pertinenti alla domanda)."""
    snap = _snapshot_con_vicino(version)
    snap.chunks[_PREAMBOLO] = {"text": "intestazione del glossario",
                               "doc_id": "glossario.md", "section": "(preambolo)"}
    # l'ordine di inserimento mette il preambolo DOPO: lo rimettiamo davanti, come nel file
    snap.chunks.clear()
    snap.chunks[_CHUNK_ID] = {"text": "testo della sezione", "doc_id": "spec.md", "section": "form"}
    snap.chunks[_PREAMBOLO] = {"text": "intestazione del glossario",
                               "doc_id": "glossario.md", "section": "(preambolo)"}
    snap.chunks[_CHUNK_VIA_GRAFO] = {"text": "definizione di EVENTO",
                                     "doc_id": "glossario.md", "section": "termini"}
    snap.colbert_store[_PREAMBOLO] = np.array([[0.0, 1.0]], dtype="float32")   # maxsim 0
    snap.colbert_store[_CHUNK_VIA_GRAFO] = np.array([[1.0, 0.0]], dtype="float32")  # maxsim 1
    return snap


def test_sezione_da_grafo_scelta_per_pertinenza_non_per_ordine_di_file(ask_env, monkeypatch):
    """Il difetto noto di S3: con l'ordine di documento si iniettava il preambolo. Ora la
    fiducia sceglie DI QUALE DOCUMENTO fidarsi e il ColBERT quale SEZIONE mostrare."""
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot_due_sezioni())
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 1)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert "definizione di EVENTO" in ctx          # la sezione pertinente
    assert "intestazione del glossario" not in ctx  # NON il preambolo
    assert "pertinenza 1.000" in ctx                # il punteggio finisce nel marcatore


def test_documento_superato_non_rientra_dal_ramo_del_grafo(ask_env, monkeypatch):
    """S4 vale anche qui: un documento esplicitamente superato da una fonte recuperata non
    può rientrare nel contesto dalla porta di servizio del grafo."""
    snap = _snapshot_due_sezioni()
    snap.graph.add_edge("spec.md", "glossario.md", relation="SUPERA_IN_PRIORITÀ",
                        nature="curated", reliability=0.9)
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 2)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert "via grafo" not in ctx
    assert "definizione di EVENTO" not in ctx


def _snapshot_sezione_orfana_del_seed(version="v1") -> deps.IndexSnapshot:
    """Il meccanismo di R9 in piccolo: il documento SEED ha una seconda sezione che il ramo
    semantico non ha recuperato. Quella sezione è raggiunta dal grafo a 1 hop ed eredita
    l'autorità del suo documento, quindi in una graduatoria per `fiducia × autorità` batte il
    vicino — che sta a 0.9 — pur essendo IRRILEVANTE alla domanda e pur venendo da un
    documento già interamente in finestra.

    L'arco è `PART_OF` come nel grafo reale (sezione -> documento): natura `structural`,
    affidabilità 1.0. È il motivo per cui sul corpus vero le sezioni del seed vincevano
    sempre — un vicino dichiarato nel frontmatter è `curated`, cioè 0.9."""
    snap = _snapshot_due_sezioni(version)
    snap.graph.add_node(_APPENDICE, type="chunk")
    snap.graph.add_edge(_APPENDICE, "spec.md", relation="PART_OF")
    snap.chunks[_APPENDICE] = {"text": "appendice irrilevante", "doc_id": "spec.md",
                               "section": "appendice"}
    snap.colbert_store[_APPENDICE] = np.array([[0.0, 1.0]], dtype="float32")  # maxsim 0
    return snap


def test_una_sezione_del_seed_non_ruba_il_budget_al_documento_raggiunto(ask_env, monkeypatch):
    """R9 — il difetto misurato sulle catene multihop, in unità: l'esclusione dei seed
    operava sui soli nodi `document`, e le SEZIONI di un seed rientravano dal grafo con
    l'autorità del loro documento, consumando tutto il tetto per reiniettare una fonte già
    presente. Con un budget di 1 deve entrare la sezione PERTINENTE del vicino."""
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: _snapshot_sezione_orfana_del_seed())
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 1)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert "definizione di EVENTO" in ctx        # il vicino, pertinente
    assert "appendice irrilevante" not in ctx    # non una sezione del seed
    assert "glossario.md § termini" in ctx


def test_il_ramo_grafo_ordina_per_pertinenza_fra_documenti_diversi(ask_env, monkeypatch):
    """R9, seconda metà: la pertinenza decide anche FRA documenti raggiunti, non solo dentro
    a uno. Il preambolo del vicino più fidato non passa più davanti alla sezione pertinente
    di un vicino meno fidato — che è ciò che sulle catene reali faceva perdere il terzo
    documento, raggiunto ma 24° in graduatoria."""
    snap = _snapshot_due_sezioni()
    # secondo vicino, PIÙ fidato (arco a 1.0) ma con la sola sezione non pertinente
    snap.graph.add_node("indice.md", type="document")
    snap.graph.add_edge("spec.md", "indice.md", relation="EREDITA_VINCOLI",
                        nature="curated", reliability=1.0)
    snap.chunks["indice.md#00-preambolo"] = {"text": "preambolo dell'indice",
                                             "doc_id": "indice.md", "section": "(preambolo)"}
    snap.colbert_store["indice.md#00-preambolo"] = np.array([[0.0, 1.0]], dtype="float32")
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 1)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert "definizione di EVENTO" in ctx        # fiducia 0.9, pertinenza 1.0
    assert "preambolo dell'indice" not in ctx    # fiducia 1.0, pertinenza 0.0
    # l'intestazione porta la fiducia del cammino da cui la sezione arriva davvero
    assert "via grafo: 1 hop, fiducia 0.900, pertinenza 1.000" in ctx




def _due_vicini(*, classi=("", ""), affidabilita=(0.9, 0.9), pertinenze=(1.0, 1.0)):
    """Snapshot con DUE vicini a confronto diretto, uno per fattore della chiave del ramo
    grafo. `pertinenze` sono i valori di MaxSim che _EmbedColbert rende prevedibili: la query
    è [[1, 0]], quindi un chunk [[x, 0]] vale esattamente x."""
    snap = _snapshot_due_sezioni()
    snap.graph.remove_node("glossario.md")   # fuori strada: qui contano solo i due vicini
    for nome, classe, aff, pert in zip(("uno.md", "due.md"), classi, affidabilita, pertinenze):
        attrs = {"type": "document"}
        if classe:
            attrs["classification"] = classe
        snap.graph.add_node(nome, **attrs)
        snap.graph.add_edge("spec.md", nome, relation="EREDITA_VINCOLI",
                            nature="curated", reliability=aff)
        snap.chunks[f"{nome}#01"] = {"text": f"testo di {nome}", "doc_id": nome, "section": "s"}
        snap.colbert_store[f"{nome}#01"] = np.array([[pert, 0.0]], dtype="float32")
    # Come in produzione: le riformulazioni si derivano dal TESTO dei chunk (N4). Senza,
    # i test del ramo grafo girerebbero su uno snapshot che quel campo non ha mai popolato,
    # e non potrebbero accorgersi di come il ramo lo usa — o non lo usa.
    return replace(snap, restatements=retrieval.restatement_sections(snap.chunks))


def _vince(snap, ask_env, monkeypatch) -> str:
    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 1)
    return client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]


def test_il_ramo_grafo_non_fa_vincere_la_fonte_debole_per_solo_vantaggio_lessicale(
        ask_env, monkeypatch):
    """R9, terza metà: la pertinenza da sola non basta. Una fonte SENZA CLASSE (peso 0.30)
    con un piccolo vantaggio lessicale passerebbe davanti a una IRON_MEMORY (1.0) — è il
    difetto di ADR 0002 rifatto nel ramo grafo, ed è successo davvero su una delle tre catene
    reali (`inferenza_locale_o_remota.md`, `authority: 0.40`, davanti a `testing_strategy.md`).

    I numeri sono quelli di produzione: a α=0.1 la forbice fra peso 0.30 e peso 1.0 vale 7,5%,
    quindi un vantaggio lessicale del 5% deve perdere — e un vantaggio più grande vincerebbe,
    che è il comportamento voluto (l'autorità modula la pertinenza, non la sostituisce)."""
    snap = _due_vicini(classi=("", "IRON_MEMORY"), pertinenze=(1.05, 1.0))
    ctx = _vince(snap, ask_env, monkeypatch)
    assert "testo di due.md" in ctx      # IRON_MEMORY, pertinenza 1.000
    assert "testo di uno.md" not in ctx  # senza classe, pertinenza 1.050


def test_il_ramo_grafo_non_fa_vincere_il_cammino_debole_per_solo_vantaggio_lessicale(
        ask_env, monkeypatch):
    """Stessa prova per la fiducia sul cammino (S3): senza quel fattore un vicino raggiunto
    per un legame debole peserebbe quanto uno dichiarato nel frontmatter, e basterebbe un
    vantaggio lessicale qualsiasi a farlo passare davanti."""
    snap = _due_vicini(affidabilita=(0.6, 0.9), pertinenze=(1.05, 1.0))
    ctx = _vince(snap, ask_env, monkeypatch)
    assert "testo di due.md" in ctx      # fiducia 0.900, pertinenza 1.000
    assert "testo di uno.md" not in ctx  # fiducia 0.600, pertinenza 1.050


def test_il_ramo_grafo_NON_penalizza_le_riformulazioni(ask_env, monkeypatch):
    """N4 vale nel ramo SEMANTICO e deliberatamente NON qui, ed è una decisione misurata.

    Nel ramo semantico penalizzare una riformulazione promuove la sezione sorella che enuncia
    la regola, perché è nella stessa lista. Qui i concorrenti sono altri DOCUMENTI, il tetto è
    basso e la sorella che dichiara spesso non è nemmeno candidata: la penalità non promuove
    la fonte del vincolo, espelle il documento. Misurato dal vivo — applicandola anche qui, la
    catena multihop dell'«ultima unità» perdeva `api_error_contract` e con lui il `409` nella
    risposta (rag/AUDIT.md, S6/N4).

    Qui: una riformulazione del documento PERTINENTE contro una sezione neutra di un altro
    documento, a pertinenza quasi pari. Deve vincere la riformulazione."""
    snap = _due_vicini(pertinenze=(1.0, 0.98))
    snap.chunks["uno.md#01"]["text"] = ("## 6. Riepilogo delle Regole\n\n"
                                        "| `[REGOLA-OBS-03]` | correlationId propagato. |\n")
    snap.chunks["due.md#01"]["text"] = "## Premessa\n\nNessun codice di regola qui.\n"
    # ricalcolata DOPO la riscrittura dei testi, come farebbe il caricamento dello snapshot
    snap = replace(snap, restatements=retrieval.restatement_sections(snap.chunks))
    assert snap.restatements == frozenset({"uno.md#01"})

    client = ask_env()
    monkeypatch.setattr(routes_retrieval, "require_snapshot", lambda project: snap)
    monkeypatch.setitem(deps.state, "embed_model", _EmbedColbert())
    monkeypatch.setattr(routes_retrieval, "GRAPH_CONTEXT_MAX_CHUNKS", 1)
    ctx = client.post("/ask", json={"question": "q"}).json()["graph_context"]["context_text"]
    assert "Riepilogo delle Regole" in ctx    # la riformulazione, più pertinente
    assert "Nessun codice di regola qui" not in ctx


pytestmark = pytest.mark.usefixtures("legacy_http_project")
