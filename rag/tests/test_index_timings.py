import networkx as nx
import numpy as np

from api import routes_reindex
from core import indexing as index
from test_incremental_indexing import StatefulFakeQdrant, StubEmbed, _spec, _wire_tmp_index


PHASES = {
    "init_model", "scan_hash", "load", "parsing_embedding",
    "qdrant", "relink", "save_hash", "eval_gate", "promote",
}


def _advancing(clock, seconds, result=None):
    def operation(*_args, **_kwargs):
        clock[0] += seconds
        return result
    return operation


def test_full_attributes_code_extraction_embedding_to_parsing_not_relink(monkeypatch, tmp_path):
    clock = [0.0]
    monkeypatch.setattr(index.time, "perf_counter", lambda: clock[0])
    symbol = {"id": "x.py::f", "name": "f", "kind": "function", "file": "x.py",
              "dev_type": "backend", "text": "def f(): pass"}
    monkeypatch.setattr(index, "collect_code_symbols", _advancing(clock, 3, [symbol]))
    monkeypatch.setattr(index, "embed_symbols", _advancing(clock, 5, np.ones((1, 2))))
    monkeypatch.setattr(index, "link_symbols", _advancing(clock, 7, 1))
    monkeypatch.setattr(index, "_resolve_authority_aliases", _advancing(clock, 11, 0))
    timings = index._new_phase_timings()

    index._build_full_state(StubEmbed(), tmp_path, tmp_path, phase_timings=timings)

    assert timings["parsing_embedding"] == 8
    assert timings["relink"] == 18


def test_incremental_attributes_code_extraction_embedding_to_parsing_not_relink(monkeypatch, tmp_path):
    clock = [0.0]
    monkeypatch.setattr(index.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(index, "_apply_code_delta", _advancing(clock, 8, {"x.py::f"}))
    monkeypatch.setattr(index, "_symbols_with_stale_argmax", lambda *_: set())
    monkeypatch.setattr(index, "_symbols_beaten_by_new_chunks", lambda *_: set())
    monkeypatch.setattr(index, "_symbols_referencing_entities", lambda *_: set())
    monkeypatch.setattr(index, "_relink_touched_symbols", _advancing(clock, 7, 1))
    monkeypatch.setattr(index, "_resolve_authority_aliases", _advancing(clock, 11, 0))
    timings = index._new_phase_timings()

    index.apply_incremental_indexing(
        index.IndexPlan(), tmp_path, StatefulFakeQdrant(), StubEmbed(),
        nx.DiGraph(), {}, {}, dense_store={}, code_store={},
        code_delta=(["x.py"], [], []), code_dir=tmp_path, phase_timings=timings,
    )

    assert timings["parsing_embedding"] == 8
    assert timings["relink"] == 18


def test_direct_full_collector_separates_eval_gate_from_promotion(monkeypatch, tmp_path):
    clock = [0.0]
    monkeypatch.setattr(index.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(index, "_build_full_state", lambda *a, **k: index.FullState(nx.DiGraph()))
    monkeypatch.setattr(index, "_docs_hashes", lambda: {})
    monkeypatch.setattr(index, "_code_hashes", lambda: {})
    monkeypatch.setattr(index, "save_artifacts", lambda *a, **k: "v-test")
    monkeypatch.setattr(index, "write_index_manifest", lambda *a, **k: None)
    monkeypatch.setattr(index, "gate_promotion", _advancing(clock, 13, {"passed": True}))
    monkeypatch.setattr(index, "promote_version", _advancing(clock, 17))
    monkeypatch.setattr(index, "_migrate_legacy_collection_if_needed", _advancing(clock, 19))
    monkeypatch.setattr(index, "_swap_alias", _advancing(clock, 23))
    monkeypatch.setattr(index, "gc_orphaned_qdrant_collections", _advancing(clock, 29))
    collector = {}

    index.build_graph_and_index(qdrant=StatefulFakeQdrant(), embed_model=StubEmbed(),
                                collector=collector)

    assert collector["phase_timings_seconds"]["eval_gate"] == 13
    assert collector["phase_timings_seconds"]["promote"] == 88


def test_incremental_reports_real_phase_timings_and_work_counts(monkeypatch, tmp_path):
    docs_dir, _ = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")

    result = index.incremental_index(qdrant=StatefulFakeQdrant(), embed_model=StubEmbed())

    assert set(result["phase_timings_seconds"]) == PHASES
    assert all(value >= 0 for value in result["phase_timings_seconds"].values())
    assert result["counts"]["docs_added"] == 1
    assert result["counts"]["chunks_processed"] == result["counts"]["chunks_indexed"] > 0
    assert result["counts"]["colbert_tokens_processed"] == result["counts"]["colbert_tokens_indexed"] > 0
    assert result["counts"]["code_tokens_processed"] is None
    assert result["counts"]["code_tokens_unavailable_reason"]


def test_full_rebuild_populates_optional_observability_collector(monkeypatch, tmp_path):
    docs_dir, _ = _wire_tmp_index(monkeypatch, tmp_path)
    (docs_dir / "spec.md").write_text(_spec("ALPHA"), encoding="utf-8")
    monkeypatch.setattr(index, "gate_promotion", lambda *a, **k: {"passed": True})
    collector = {}

    version = index.build_graph_and_index(
        qdrant=StatefulFakeQdrant(), embed_model=StubEmbed(), collector=collector,
    )

    assert isinstance(version, str)
    assert set(collector["phase_timings_seconds"]) == PHASES
    assert collector["counts"]["docs_added"] == 1
    assert collector["counts"]["chunks_processed"] == collector["counts"]["chunks_indexed"] > 0
    assert collector["counts"]["colbert_tokens_processed"] == collector["counts"]["colbert_tokens_indexed"] > 0


def test_route_measures_model_initialization_and_eval_separately(monkeypatch):
    model = object()
    monkeypatch.setattr(routes_reindex, "_reindex_embed_model", lambda: model)
    monkeypatch.setattr(
        routes_reindex,
        "build_graph_and_index",
        lambda **kwargs: kwargs["collector"].update({
            "phase_timings_seconds": {phase: 0.0 for phase in PHASES},
            "counts": {},
        }) or "v-test",
    )
    monkeypatch.setattr(routes_reindex, "_eval_gate", lambda *_: {"passed": False})

    result = routes_reindex._run_full_rebuild(None)

    assert result["phase_timings_seconds"]["init_model"] >= 0
    assert result["phase_timings_seconds"]["eval_gate"] >= 0
    assert result["counts"] == {}
