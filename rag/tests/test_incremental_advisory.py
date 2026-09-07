"""Test dell'advisory M6 sugli incrementali (eval_gate.incremental_advisory, ESPERIMENTO):
run_incremental_advisory (unit, evaluate_recall mockata) e il suo aggancio in
incremental_index (integrazione con orchestrazione mockata). Invarianti non negoziabili:
la promozione avviene SEMPRE (l'advisory non decide nulla), un'advisory rotta non fa mai
fallire il job (fail-open), sotto soglia l'alert è WARNING e mai critical."""
import json
from types import SimpleNamespace

import networkx as nx

from core import eval_gate
from core import indexing as index


# ---------------------------------------------------------------------------
# 1. Unit: run_incremental_advisory (evaluate_recall mockata)
# ---------------------------------------------------------------------------
def _spy_history(monkeypatch):
    calls: list[dict] = []

    def _record(recall, *, n_cases, version, source, gate=None, path=None):
        calls.append({"recall": recall, "n_cases": n_cases, "version": version,
                      "source": source, "gate": gate})
        return calls[-1]

    monkeypatch.setattr(eval_gate, "record_history", _record)
    return calls


def test_advisory_records_history_with_dedicated_source(monkeypatch):
    # Il k NON è hardcodato: l'invariante è "lo storico registra la recall al k del gate",
    # qualunque esso sia. Inchiodarlo a 10 rendeva il test dipendente da eval_gate.k in
    # config, e infatti si è rotto quando il gate è passato a k=5 (2026-08-25).
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **kw: {"recall": 0.95, "n": 34, "k": kw.get("k")})
    history = _spy_history(monkeypatch)

    res = eval_gate.run_incremental_advisory("v1", None, object(), {}, min_recall=0.90)

    assert res["evaluated"] is True and res["passed"] is True
    assert isinstance(res["advisory_eval_seconds"], float)
    assert len(history) == 1
    assert history[0]["source"] == "incremental_advisory"
    # Il doppio non torna `recall_by_k`: questa riga PINNA IL FALLBACK di R12. record_history
    # e' chiamata fuori dal try/except del fail-open, e un KeyError su una chiave assente
    # farebbe fallire proprio il job che l'advisory non deve mai toccare.
    assert history[0]["recall"] == {f"recall@{eval_gate.EVAL_GATE_K}": 0.95}
    assert history[0]["version"] == "v1"
    assert history[0]["gate"]["advisory_eval_seconds"] == res["advisory_eval_seconds"]


def test_advisory_records_every_k_when_measured(monkeypatch):
    """R12: quando evaluate_recall misura piu' k, l'advisory li scrive TUTTI — non solo
    quello del gate. E' la seconda sorgente che scriveva una colonna sola: senza questo test
    la correzione resterebbe provata solo su gate_promotion."""
    larga = {"recall@1": 0.70, "recall@2": 0.95, "recall@5": 0.99, "recall@10": 1.0}
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **kw: {"recall": 0.95, "n": 34, "k": kw.get("k"),
                                          "recall_by_k": larga})
    history = _spy_history(monkeypatch)

    eval_gate.run_incremental_advisory("v1", None, object(), {}, min_recall=0.90)

    assert history[0]["recall"] == larga


def test_advisory_below_threshold_writes_warning_alert_never_critical(monkeypatch, tmp_path):
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 0.50, "n": 34, "k": 10})
    _spy_history(monkeypatch)
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)

    res = eval_gate.run_incremental_advisory("v2", None, object(), {}, min_recall=0.90)

    assert res["passed"] is False                    # esito registrato...
    assert res["evaluated"] is True                  # ...ma nessuna eccezione: solo osservazione
    line = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert line["level"] == "warning" and line["level"] != "critical"
    assert line["source"] == "eval_gate" and line["advisory"] == "incremental"
    assert line["recall"] == 0.50 and line["version"] == "v2"


def test_advisory_history_recorded_even_below_threshold(monkeypatch, tmp_path):
    """SEMPRE in history: anche l'esito negativo viene storicizzato (è il trend che conta)."""
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 0.50, "n": 34, "k": 10})
    history = _spy_history(monkeypatch)
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", tmp_path / "alerts.jsonl")

    eval_gate.run_incremental_advisory("v2b", None, object(), {}, min_recall=0.90)

    assert len(history) == 1
    assert history[0]["source"] == "incremental_advisory"
    assert history[0]["gate"]["passed"] is False


def test_advisory_error_is_fail_open(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("qdrant giù")

    monkeypatch.setattr(eval_gate, "evaluate_recall", _boom)
    history = _spy_history(monkeypatch)

    logs: list[str] = []
    res = eval_gate.run_incremental_advisory("v3", None, object(), {}, emit=logs.append)

    assert res["skipped"] == "error" and res["evaluated"] is False   # nessuna eccezione propagata
    assert history == []                                             # niente history su errore
    assert any("fail-open" in m for m in logs)


def test_advisory_without_embed_model_skips_without_loading(monkeypatch):
    """Job di solo-delete (modello mai caricato): l'advisory salta, non carica il modello."""
    def _boom(*a, **k):
        raise AssertionError("evaluate_recall non deve essere chiamata senza modello")

    monkeypatch.setattr(eval_gate, "evaluate_recall", _boom)
    res = eval_gate.run_incremental_advisory("v4", None, None, {})
    assert res["skipped"] == "no_embed_model"


def test_advisory_no_golden_set_skips_history(monkeypatch):
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": None, "n": 0, "k": 10})
    history = _spy_history(monkeypatch)
    res = eval_gate.run_incremental_advisory("v5", None, object(), {})
    assert res["skipped"] == "no_golden_set"
    assert history == []


# ---------------------------------------------------------------------------
# 2. Integrazione: aggancio in incremental_index. L'orchestrazione pesante
# (hash, artefatti, apply, persistenza) è mockata: qui si verifica SOLO il
# cablaggio del flag M6 — chi viene chiamato, con quale collection, e che la
# promozione/il job non dipendano mai dall'esito dell'advisory.
# ---------------------------------------------------------------------------
def _wire_incremental(monkeypatch, *, qdrant_collection: str | None = None) -> list[str]:
    """Prepara un incremental_index minimale (1 doc modificato) e restituisce la lista
    delle versioni promosse (riempita dal fake di promote_version)."""
    manifest: dict = {"doc_hashes": {"a.md": "old"}, "code_hashes": {}}
    if qdrant_collection is not None:
        manifest["qdrant_collection"] = qdrant_collection
    monkeypatch.setattr(index, "_docs_hashes", lambda: {"a.md": "new"})
    monkeypatch.setattr(index, "_code_hashes", lambda: {})
    monkeypatch.setattr(index, "_read_manifest", lambda: dict(manifest))
    monkeypatch.setattr(index, "load_artifacts", lambda **k: SimpleNamespace(
        graph=nx.DiGraph(), colbert_store={}, chunks_store={}, dense_store={}, code_store={}))
    monkeypatch.setattr(index, "apply_incremental_indexing", lambda *a, **k: {
        "planned": {}, "reindexed_docs": 1, "deleted_docs": 0, "upserted_chunks": 1,
        "code_added": 0, "code_removed": 0, "code_modified": 0,
        "implements_edges": 0, "pruned_entities": 0})
    monkeypatch.setattr(index, "save_artifacts", lambda *a, **k: "v_test")
    monkeypatch.setattr(index, "write_index_manifest", lambda *a, **k: None)
    promoted: list[str] = []
    monkeypatch.setattr(index, "promote_version", promoted.append)
    if qdrant_collection is not None:
        monkeypatch.setattr(index, "repair_qdrant_alias", lambda q, emit=None: {
            "state": "aligned", "repaired": False,
            "expected": qdrant_collection, "actual": qdrant_collection})
        monkeypatch.setattr(index, "_qdrant_collection_exists", lambda q, name: True)
    else:
        # Manifest legacy senza lineage MA con alias già esistente: nessuna ensure.
        monkeypatch.setattr(index, "_read_alias_target", lambda q, name: "qualunque")
    return promoted


def test_flag_off_never_calls_evaluate_recall(monkeypatch):
    """Default (flag off): ZERO chiamate a evaluate_recall e nessuna chiave advisory."""
    promoted = _wire_incremental(monkeypatch)
    monkeypatch.setattr(index, "EVAL_GATE_INCREMENTAL_ADVISORY", False)

    def _boom(*a, **k):
        raise AssertionError("a flag spento l'advisory non deve valutare nulla")

    monkeypatch.setattr(eval_gate, "evaluate_recall", _boom)

    stats = index.incremental_index(qdrant=SimpleNamespace(), embed_model=object())

    assert promoted == ["v_test"]
    assert "advisory_eval_seconds" not in stats and "incremental_advisory" not in stats


def test_flag_on_records_history_and_promotes_anyway(monkeypatch):
    promoted = _wire_incremental(monkeypatch)
    monkeypatch.setattr(index, "EVAL_GATE_INCREMENTAL_ADVISORY", True)
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 0.95, "n": 3, "k": 10})
    history = _spy_history(monkeypatch)

    stats = index.incremental_index(qdrant=SimpleNamespace(), embed_model=object())

    assert promoted == ["v_test"]                        # la promozione avviene comunque
    assert stats["version"] == "v_test"
    assert isinstance(stats["advisory_eval_seconds"], float)
    assert len(history) == 1 and history[0]["source"] == "incremental_advisory"
    assert history[0]["version"] == "v_test"
    assert stats["incremental_advisory"]["passed"] is True


def test_flag_on_below_threshold_warns_but_job_completes(monkeypatch, tmp_path):
    promoted = _wire_incremental(monkeypatch)
    monkeypatch.setattr(index, "EVAL_GATE_INCREMENTAL_ADVISORY", True)
    monkeypatch.setattr(eval_gate, "evaluate_recall",
                        lambda *a, **k: {"recall": 0.10, "n": 3, "k": 10})
    _spy_history(monkeypatch)
    alerts = tmp_path / "alerts.jsonl"
    monkeypatch.setattr(eval_gate, "ALERTS_PATH", alerts)

    # Nessuna eccezione ⇒ il ReindexManager marcherebbe il job "completed" (mai declassato).
    stats = index.incremental_index(qdrant=SimpleNamespace(), embed_model=object())

    assert promoted == ["v_test"]                        # promozione MAI condizionata
    assert stats["incremental_advisory"]["passed"] is False
    line = json.loads(alerts.read_text(encoding="utf-8").splitlines()[-1])
    assert line["level"] == "warning" and line["advisory"] == "incremental"


def test_flag_on_evaluator_raises_job_completes(monkeypatch):
    promoted = _wire_incremental(monkeypatch)
    monkeypatch.setattr(index, "EVAL_GATE_INCREMENTAL_ADVISORY", True)

    def _boom(*a, **k):
        raise RuntimeError("golden set corrotto")

    monkeypatch.setattr(eval_gate, "evaluate_recall", _boom)
    history = _spy_history(monkeypatch)

    logs: list[str] = []
    stats = index.incremental_index(qdrant=SimpleNamespace(), embed_model=object(),
                                    emit=logs.append)

    assert promoted == ["v_test"]                        # job completo, promozione valida
    assert stats["incremental_advisory"]["skipped"] == "error"
    assert "advisory_eval_seconds" not in stats
    assert history == []
    assert any("fail-open" in m for m in logs)           # warning loggato, mai propagato


def test_advisory_evaluates_the_lineage_collection_from_manifest(monkeypatch):
    """La collection valutata è quella della lineage dal manifest, non il default."""
    _wire_incremental(monkeypatch, qdrant_collection="vibecraft_events__v42")
    monkeypatch.setattr(index, "EVAL_GATE_INCREMENTAL_ADVISORY", True)
    _spy_history(monkeypatch)
    captured: dict = {}

    def _fake_evaluate(qdrant, embed_model, colbert_store, *, k, cases, collection_name):
        captured["collection_name"] = collection_name
        return {"recall": 0.95, "n": 3, "k": k}

    monkeypatch.setattr(eval_gate, "evaluate_recall", _fake_evaluate)

    index.incremental_index(qdrant=SimpleNamespace(), embed_model=object())

    assert captured["collection_name"] == "vibecraft_events__v42"
