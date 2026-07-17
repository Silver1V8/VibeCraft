"""Test del lifespan del server (api.deps.lifespan): S8 del piano blue/green Qdrant
collega al boot, PRE-SERVING, sia la riconciliazione riparatrice dell'alias
(reconcile_and_repair_qdrant_alias) sia il GC delle collection orfane
(gc_orphaned_qdrant_collections) — mai un motivo di fallimento del boot. Le risorse
pesanti (modello di embedding, Qdrant, artefatti) sono tutte finte: nessun
GPU/rete/disco reale."""
import asyncio

import networkx as nx
from fastapi import FastAPI

from api import deps
from core.artifacts import Artifacts


class _FakeLifespanQdrant:
    """Basta a soddisfare il lifespan: nessuna vera connessione, si chiude e basta."""
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _patch_heavy_resources(monkeypatch, *, repair_result: dict, gc_result: list | None = None):
    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **k: object())
    monkeypatch.setattr(deps, "QdrantClient", lambda *a, **k: _FakeLifespanQdrant())
    monkeypatch.setattr(deps, "load_artifacts", lambda required=(): Artifacts(graph=nx.DiGraph()))
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    monkeypatch.setattr(deps, "reconcile_and_repair_qdrant_alias", lambda qdrant: dict(repair_result))
    monkeypatch.setattr(deps, "gc_orphaned_qdrant_collections", lambda qdrant: list(gc_result or []))


def _run_lifespan_once():
    """Entra ed esce dal lifespan una volta, restituendo lo stato osservato a metà
    (dentro il `yield`, quando il server sarebbe "pronto")."""
    app = FastAPI()
    captured = {}

    async def _run():
        async with deps.lifespan(app):
            captured["qdrant"] = deps.state["qdrant"]
            captured["snapshot"] = deps.state["snapshot"]

    asyncio.run(_run())
    return captured


def test_lifespan_boot_does_not_fail_with_legacy_alias_state(monkeypatch):
    """Layout legacy (nessuna versione con qdrant_collection nel manifest): il boot
    deve comunque completarsi, con lo stato alias solo osservato/loggato (nulla da
    riparare)."""
    original_state = dict(deps.state)
    _patch_heavy_resources(
        monkeypatch, repair_result={"state": "legacy", "expected": None, "actual": None, "repaired": False}
    )
    try:
        captured = _run_lifespan_once()  # non deve sollevare
        assert captured["qdrant"] is not None
        assert captured["snapshot"] is not None
    finally:
        deps.state.clear()
        deps.state.update(original_state)


def test_lifespan_boot_does_not_fail_when_alias_gets_repaired(monkeypatch):
    """Uno stato 'diverging' riparato con successo (repaired=True, S8) resta comunque
    solo informativo per il boot: nessun fallimento, il server continua a servire."""
    original_state = dict(deps.state)
    _patch_heavy_resources(
        monkeypatch,
        repair_result={"state": "diverging", "expected": "vibecraft_events__v2",
                       "actual": "vibecraft_events__v1", "repaired": True},
    )
    try:
        captured = _run_lifespan_once()
        assert captured["qdrant"] is not None
    finally:
        deps.state.clear()
        deps.state.update(original_state)


def test_lifespan_boot_does_not_fail_when_repair_declines_missing_collection(monkeypatch):
    """La collection attesa non esiste più: il repair rifiuta la correzione
    (repaired=False) ma il boot deve comunque completarsi senza sollevare."""
    original_state = dict(deps.state)
    _patch_heavy_resources(
        monkeypatch,
        repair_result={"state": "missing", "expected": "vibecraft_events__v-sparita",
                       "actual": None, "repaired": False},
    )
    try:
        captured = _run_lifespan_once()
        assert captured["qdrant"] is not None
    finally:
        deps.state.clear()
        deps.state.update(original_state)


def test_lifespan_reconciles_and_gcs_using_the_same_qdrant_client_stored_in_state(monkeypatch):
    """Wiring: sia reconcile_and_repair_qdrant_alias sia gc_orphaned_qdrant_collections
    devono ricevere lo STESSO client che finisce in state["qdrant"] (nessuna
    connessione parallela creata solo per riconciliazione/GC)."""
    original_state = dict(deps.state)
    received = {}

    def _spy_repair(qdrant):
        received["repair_qdrant"] = qdrant
        return {"state": "legacy", "expected": None, "actual": None, "repaired": False}

    def _spy_gc(qdrant):
        received["gc_qdrant"] = qdrant
        return []

    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **k: object())
    monkeypatch.setattr(deps, "QdrantClient", lambda *a, **k: _FakeLifespanQdrant())
    monkeypatch.setattr(deps, "load_artifacts", lambda required=(): Artifacts(graph=nx.DiGraph()))
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    monkeypatch.setattr(deps, "reconcile_and_repair_qdrant_alias", _spy_repair)
    monkeypatch.setattr(deps, "gc_orphaned_qdrant_collections", _spy_gc)
    try:
        captured = _run_lifespan_once()
        assert received["repair_qdrant"] is captured["qdrant"]
        assert received["gc_qdrant"] is captured["qdrant"]
    finally:
        deps.state.clear()
        deps.state.update(original_state)


def test_lifespan_runs_repair_before_gc(monkeypatch):
    """Ordine: la riparazione dell'alias avviene PRIMA del GC — un GC che leggesse
    l'alias_target prima di una riparazione lo troverebbe ancora nello stato vecchio."""
    original_state = dict(deps.state)
    sequence: list[str] = []

    def _spy_repair(qdrant):
        sequence.append("repair")
        return {"state": "legacy", "expected": None, "actual": None, "repaired": False}

    def _spy_gc(qdrant):
        sequence.append("gc")
        return []

    monkeypatch.setattr(deps, "BGEM3FlagModel", lambda *a, **k: object())
    monkeypatch.setattr(deps, "QdrantClient", lambda *a, **k: _FakeLifespanQdrant())
    monkeypatch.setattr(deps, "load_artifacts", lambda required=(): Artifacts(graph=nx.DiGraph()))
    monkeypatch.setattr(deps, "load_rule_descriptions", lambda: {})
    monkeypatch.setattr(deps, "reconcile_and_repair_qdrant_alias", _spy_repair)
    monkeypatch.setattr(deps, "gc_orphaned_qdrant_collections", _spy_gc)
    try:
        _run_lifespan_once()
        assert sequence == ["repair", "gc"]
    finally:
        deps.state.clear()
        deps.state.update(original_state)
