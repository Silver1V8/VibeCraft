"""Test degli helper ISOLATI del blue/green Qdrant (collection versionate + alias,
S4 del piano di implementazione): naming/parsing del nome di collection fisica,
lettura e swap dell'alias, enumerazione, garbage collection delle collection orfane,
e il reconciler di sola osservazione (core.indexing).

Gli helper testati qui sono wired nei percorsi di produzione da S5-S10: naming/parsing
e `_swap_alias`/`_migrate_legacy_collection_if_needed`/`gc_orphaned_qdrant_collections`
in `build_graph_and_index` (core/indexing.py, full rebuild via CLI e via
`api.routes_reindex._run_full_rebuild`); `rollback_qdrant_alias_if_needed` nel rollback
(`index.py --rollback` e `POST /api/index/rollback`, api/routes_reindex.py); il
reconciler di sola osservazione `reconcile_and_repair_qdrant_alias` (insieme al GC
orfani) nel lifespan del server (api/deps.py), al boot pre-serving. Nessun Qdrant reale
è richiesto per la suite di default — i CINQUE test che ne hanno bisogno (in fondo al
file) si auto-saltano se non raggiungibile. In CI il servizio c'è e saltare non è più
accettabile: `VIBECRAFT_REQUIRE_QDRANT=1` trasforma quello skip in un errore.
"""
import json
import os

import pytest
import networkx as nx

from core import artifacts
from core import indexing as index


# ---------------------------------------------------------------------------
# Fake Qdrant alias-aware: distingue esplicitamente collection FISICHE e ALIAS,
# simula update_collection_aliases come batch atomico (valida tutte le operazioni
# prima di applicarne una sola) e risolve l'alias nelle point-operation esattamente
# come farebbe un Qdrant vero (upsert/count su un alias colpiscono la collection
# fisica a cui punta).
# ---------------------------------------------------------------------------
class _FakeCollectionInfo:
    def __init__(self, name):
        self.name = name


class _FakeCollectionsResponse:
    def __init__(self, names):
        self.collections = [_FakeCollectionInfo(n) for n in names]


class _FakeAliasDescription:
    def __init__(self, alias_name, collection_name):
        self.alias_name = alias_name
        self.collection_name = collection_name


class _FakeAliasesResponse:
    def __init__(self, aliases):
        self.aliases = aliases


class _FakeCount:
    def __init__(self, n):
        self.count = n


class AliasAwareFakeQdrant:
    """Qdrant in-memory con distinzione esplicita tra collection fisiche e alias."""

    def __init__(self, collections=(), aliases=None):
        self._collections: set[str] = set(collections)
        self._aliases: dict[str, str] = dict(aliases or {})
        self._points: dict[str, list] = {name: [] for name in self._collections}
        self.update_aliases_calls: int = 0

    # --- collection: create/delete rispettano la distinzione fisica/alias ---
    def get_collections(self):
        return _FakeCollectionsResponse(sorted(self._collections))

    def create_collection(self, collection_name, **kw):
        if collection_name in self._aliases:
            raise ValueError(f"'{collection_name}' è già un alias: non può anche essere una collection.")
        self._collections.add(collection_name)
        self._points.setdefault(collection_name, [])

    def delete_collection(self, collection_name):
        if collection_name not in self._collections:
            raise ValueError(f"Collection inesistente: {collection_name}")
        self._collections.discard(collection_name)
        self._points.pop(collection_name, None)
        # Qdrant reale invalida gli alias che puntavano alla collection cancellata:
        # il fake fa lo stesso, per non restare in uno stato incoerente.
        for alias_name in [a for a, c in self._aliases.items() if c == collection_name]:
            del self._aliases[alias_name]

    # --- alias: get_aliases + update_collection_aliases (batch atomico) ---
    def get_aliases(self):
        return _FakeAliasesResponse([
            _FakeAliasDescription(alias_name=a, collection_name=c)
            for a, c in sorted(self._aliases.items())
        ])

    def update_collection_aliases(self, change_aliases_operations):
        """Valida TUTTE le operazioni del batch prima di applicarne una sola: se una
        sola è invalida (es. create verso una collection inesistente), l'intero
        batch viene rifiutato e l'alias resta nello stato precedente — stessa
        semantica "tutto o niente" del batch reale di Qdrant."""
        self.update_aliases_calls += 1
        pending_creates: list[tuple[str, str]] = []
        pending_deletes: list[str] = []
        for op in change_aliases_operations:
            create = getattr(op, "create_alias", None)
            delete = getattr(op, "delete_alias", None)
            if create is not None:
                if create.collection_name not in self._collections:
                    raise ValueError(
                        f"Impossibile creare l'alias '{create.alias_name}': "
                        f"collection '{create.collection_name}' inesistente."
                    )
                pending_creates.append((create.alias_name, create.collection_name))
            elif delete is not None:
                pending_deletes.append(delete.alias_name)
            else:
                raise NotImplementedError("Operazione alias non supportata dal fake.")
        # Solo ora, con tutte le operazioni validate, si muta lo stato.
        for alias_name in pending_deletes:
            self._aliases.pop(alias_name, None)
        for alias_name, collection_name in pending_creates:
            self._aliases[alias_name] = collection_name
        return True

    # --- point-operations: risolvono l'alias sul target fisico corretto ---
    def _resolve(self, name: str) -> str:
        return self._aliases.get(name, name)

    def upsert(self, collection_name, points):
        target = self._resolve(collection_name)
        self._points.setdefault(target, []).extend(points)

    def count(self, collection_name, exact=True):
        target = self._resolve(collection_name)
        return _FakeCount(len(self._points.get(target, [])))


# ---------------------------------------------------------------------------
# Naming e parsing del nome di collection fisica versionata
# ---------------------------------------------------------------------------
def test_qdrant_collection_name_and_parse_roundtrip():
    name = index.qdrant_collection_name("v20260717T101530")
    assert name == f"{index.COLLECTION_NAME}__v20260717T101530"
    assert index.parse_qdrant_collection_version(name) == "v20260717T101530"


def test_qdrant_collection_name_honors_explicit_base():
    name = index.qdrant_collection_name("v1", base="altra_collection")
    assert name == "altra_collection__v1"
    assert index.parse_qdrant_collection_version(name, base="altra_collection") == "v1"
    # Con la base di default non corrisponde: nomi diversi, schemi diversi.
    assert index.parse_qdrant_collection_version(name) is None


def test_parse_qdrant_collection_version_rejects_non_matching_names():
    # L'alias stesso (senza suffisso) non è una collection versionata.
    assert index.parse_qdrant_collection_version(index.COLLECTION_NAME) is None
    # Una collection estranea, non gestita da questo indice.
    assert index.parse_qdrant_collection_version("altro_progetto__v1") is None
    # Suffisso vuoto (solo il separatore, nessun token di versione): non valido.
    assert index.parse_qdrant_collection_version(f"{index.COLLECTION_NAME}__") is None


# ---------------------------------------------------------------------------
# Lettura del target dell'alias
# ---------------------------------------------------------------------------
def test_read_alias_target_returns_none_when_alias_absent():
    q = AliasAwareFakeQdrant(collections={"v1"})
    assert index._read_alias_target(q, index.COLLECTION_NAME) is None


def test_read_alias_target_returns_current_collection():
    q = AliasAwareFakeQdrant(collections={"v1"}, aliases={index.COLLECTION_NAME: "v1"})
    assert index._read_alias_target(q, index.COLLECTION_NAME) == "v1"


# ---------------------------------------------------------------------------
# Swap dell'alias: idempotente e atomico
# ---------------------------------------------------------------------------
def test_swap_alias_creates_when_absent():
    q = AliasAwareFakeQdrant(collections={"v1"})
    index._swap_alias(q, index.COLLECTION_NAME, "v1")
    assert index._read_alias_target(q, index.COLLECTION_NAME) == "v1"
    assert q.update_aliases_calls == 1


def test_swap_alias_is_idempotent_when_already_pointing_there():
    q = AliasAwareFakeQdrant(collections={"v1"}, aliases={index.COLLECTION_NAME: "v1"})
    index._swap_alias(q, index.COLLECTION_NAME, "v1")
    # Nessuna richiesta inviata: l'alias era già allineato.
    assert q.update_aliases_calls == 0
    assert index._read_alias_target(q, index.COLLECTION_NAME) == "v1"


def test_swap_alias_replaces_in_a_single_atomic_batch():
    q = AliasAwareFakeQdrant(collections={"v1", "v2"}, aliases={index.COLLECTION_NAME: "v1"})
    index._swap_alias(q, index.COLLECTION_NAME, "v2")
    assert index._read_alias_target(q, index.COLLECTION_NAME) == "v2"
    # Una SOLA richiesta al batch (delete+create insieme), non due chiamate separate.
    assert q.update_aliases_calls == 1


def test_swap_alias_batch_is_all_or_nothing_on_invalid_target():
    q = AliasAwareFakeQdrant(collections={"v1"}, aliases={index.COLLECTION_NAME: "v1"})
    with pytest.raises(ValueError):
        index._swap_alias(q, index.COLLECTION_NAME, "collection-inesistente")
    # Il batch è stato rifiutato per intero: l'alias resta al valore precedente,
    # non in uno stato intermedio (né senza alias, né spostato a metà).
    assert index._read_alias_target(q, index.COLLECTION_NAME) == "v1"


# ---------------------------------------------------------------------------
# Enumerazione delle collection versionate
# ---------------------------------------------------------------------------
def test_list_qdrant_collections_only_returns_versioned_collections_of_this_project():
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={
        f"{base}__v1", f"{base}__v2", "altro_progetto__v1", "una_collection_qualsiasi",
    })
    assert index.list_qdrant_collections(q) == [f"{base}__v1", f"{base}__v2"]


def test_list_qdrant_collections_never_includes_the_alias_itself():
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={f"{base}__v1"}, aliases={base: f"{base}__v1"})
    # L'alias non è una collection fisica: get_collections() del fake (come quello
    # vero) non lo elenca affatto.
    assert base not in index.list_qdrant_collections(q)
    assert index.list_qdrant_collections(q) == [f"{base}__v1"]


# ---------------------------------------------------------------------------
# Point-operations che risolvono l'alias sul target fisico corretto
# ---------------------------------------------------------------------------
def test_point_operations_resolve_alias_to_physical_target():
    q = AliasAwareFakeQdrant(collections={"v1", "v2"}, aliases={index.COLLECTION_NAME: "v1"})
    q.upsert(collection_name=index.COLLECTION_NAME, points=["p1", "p2"])
    # I punti sono finiti nella collection FISICA a cui punta l'alias, non in una
    # collection letteralmente chiamata come l'alias (che non esiste come oggetto fisico).
    assert q._points["v1"] == ["p1", "p2"]
    assert q.count(collection_name=index.COLLECTION_NAME).count == 2
    assert q.count(collection_name="v2").count == 0


# ---------------------------------------------------------------------------
# Garbage collection delle collection orfane: invarianti di sicurezza
# ---------------------------------------------------------------------------
def test_gc_never_deletes_the_alias_target():
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={f"{base}__v1", f"{base}__v2"})
    index._swap_alias(q, base, f"{base}__v1")
    removed = index.gc_qdrant_collections(q, referenced=set(), alias_target=f"{base}__v1")
    assert removed == [f"{base}__v2"]
    assert index.list_qdrant_collections(q) == [f"{base}__v1"]


def test_gc_never_deletes_collections_referenced_by_surviving_manifests():
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={f"{base}__v1", f"{base}__v2", f"{base}__v3"})
    # v1 è il target dell'alias (attivo), v2 è referenziato da un manifest
    # sopravvissuto (es. non ancora pruned dalla retention locale), v3 è orfana.
    index._swap_alias(q, base, f"{base}__v1")
    removed = index.gc_qdrant_collections(
        q, referenced={f"{base}__v2"}, alias_target=f"{base}__v1"
    )
    assert removed == [f"{base}__v3"]
    assert sorted(index.list_qdrant_collections(q)) == [f"{base}__v1", f"{base}__v2"]


def test_gc_deletes_orphan_collections_with_no_alias_target():
    """Nessun target d'alias noto (es. gate non ancora passato, candidata non
    promossa): tutto ciò che non è in `referenced` è orfano."""
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={f"{base}__v1", f"{base}__v2"})
    removed = index.gc_qdrant_collections(q, referenced=set(), alias_target=None)
    assert sorted(removed) == [f"{base}__v1", f"{base}__v2"]
    assert index.list_qdrant_collections(q) == []


# ---------------------------------------------------------------------------
# _referenced_qdrant_collections: scan locale dei manifest sopravvissuti
# ---------------------------------------------------------------------------
@pytest.fixture
def versions_db(tmp_path, monkeypatch):
    """Sandbox su database/versions/ (core.artifacts), per scrivere manifest reali
    con il campo qdrant_collection senza toccare Qdrant."""
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    return tmp_path


def _write_version_manifest(versions_db, version: str, qdrant_collection: str | None) -> None:
    vdir = versions_db / "versions" / version
    vdir.mkdir(parents=True)
    manifest = {"version": version}
    if qdrant_collection is not None:
        manifest["qdrant_collection"] = qdrant_collection
    (vdir / "index_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_referenced_qdrant_collections_reads_field_from_surviving_manifests(versions_db):
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v2")
    assert index._referenced_qdrant_collections() == {
        "vibecraft_events__v1", "vibecraft_events__v2",
    }


def test_referenced_qdrant_collections_tolerates_manifest_without_the_field(versions_db):
    """Una versione sopravvissuta scritta prima di S2 (nessun campo qdrant_collection)
    non contribuisce all'insieme referenziato, ma non fa fallire la scansione."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", None)  # manifest legacy, campo assente
    assert index._referenced_qdrant_collections() == {"vibecraft_events__v1"}


def test_referenced_qdrant_collections_empty_when_no_versions(versions_db):
    assert index._referenced_qdrant_collections() == set()


# ---------------------------------------------------------------------------
# rollback_shares_collection_with_later_versions: detection PURA locale della
# collection condivisa con versioni posteriori (incrementali intra-lineage che
# mutano in place la collection del target: il rollback non riavvolge Qdrant).
# ---------------------------------------------------------------------------
def test_rollback_shared_collection_detects_later_versions_on_same_collection(versions_db):
    """full v1 (C1) → incrementale v2 (eredita C1): il rollback a v1 deve sapere che
    v2 ha mutato C1 dopo la build di v1."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v1")
    assert index.rollback_shares_collection_with_later_versions("v1") == ["v2"]


def test_rollback_shared_collection_lists_all_later_sharers_chronologically(versions_db):
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v3", "vibecraft_events__v1")
    assert index.rollback_shares_collection_with_later_versions("v1") == ["v2", "v3"]


def test_rollback_shared_collection_cross_lineage_returns_empty(versions_db):
    """full v1 (C1) → full v2 (C2): lineage diversi, nessuna condivisione, nessun warning."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v2")
    assert index.rollback_shares_collection_with_later_versions("v1") == []


def test_rollback_shared_collection_ignores_earlier_versions_and_the_target_itself(versions_db):
    """Le versioni PRECEDENTI sulla stessa collection non contano (hanno scritto PRIMA
    della build del target), e il target non è mai "posteriore a sé stesso"."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v2")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v2")
    assert index.rollback_shares_collection_with_later_versions("v2") == []


def test_rollback_shared_collection_target_without_field_returns_empty(versions_db):
    """Manifest legacy del TARGET (nessun campo qdrant_collection): condivisione non
    rilevabile, [] senza errori — nessun falso allarme sui lineage pre-versionamento."""
    _write_version_manifest(versions_db, "v1", None)
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v2")
    assert index.rollback_shares_collection_with_later_versions("v1") == []


def test_rollback_shared_collection_tolerates_unreadable_or_legacy_later_manifests(versions_db):
    """Versioni posteriori con manifest legacy (campo assente) o corrotto: ignorate,
    stessa tolleranza di _referenced_qdrant_collections; le altre restano rilevate."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", None)  # legacy: campo assente
    v3 = versions_db / "versions" / "v3"
    v3.mkdir(parents=True)
    (v3 / "index_manifest.json").write_text("{non-json", encoding="utf-8")  # corrotto
    _write_version_manifest(versions_db, "v4", "vibecraft_events__v1")
    assert index.rollback_shares_collection_with_later_versions("v1") == ["v4"]


# ---------------------------------------------------------------------------
# Reconciler: classificazione legacy / aligned / diverging / missing (sola
# osservazione — non scrive mai su Qdrant né in locale).
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# R14 — pre-check del rollback: la collection Qdrant della versione TARGET deve
# esistere ancora. A20 ne ha distrutte due davvero: senza questa guardia il rollback
# spostava CURRENT lo stesso e lasciava uno stato misto (sidecar del target, vettori
# di un'altra build) che nessun reconciler ripara e che il check di integrita'
# dichiarava `ok: true`.
# ---------------------------------------------------------------------------
def test_precheck_rollback_rifiuta_se_la_collection_del_target_non_esiste(versions_db):
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    _write_version_manifest(versions_db, "v2", "vibecraft_events__v2")
    qdrant = AliasAwareFakeQdrant(collections=["vibecraft_events__v2"],
                                  aliases={index.COLLECTION_NAME: "vibecraft_events__v2"})
    with pytest.raises(index.RollbackTargetCollectionMissing) as exc:
        index.assert_rollback_target_has_vectors(qdrant, "v1")
    # Il messaggio deve nominare la collection mancante E il rimedio.
    assert "vibecraft_events__v1" in str(exc.value)
    assert "re-indicizzazione completa" in str(exc.value)


def test_precheck_rollback_passa_se_la_collection_del_target_esiste(versions_db):
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")
    qdrant = AliasAwareFakeQdrant(collections=["vibecraft_events__v1", "vibecraft_events__v2"],
                                  aliases={index.COLLECTION_NAME: "vibecraft_events__v2"})
    index.assert_rollback_target_has_vectors(qdrant, "v1")  # nessuna eccezione


def test_precheck_rollback_non_blocca_se_qdrant_e_irraggiungibile(versions_db):
    """Qdrant giu' non deve impedire un rollback LOCALE: il pre-check si salta e il
    comportamento resta quello di sempre (alias riparato al prossimo boot)."""
    _write_version_manifest(versions_db, "v1", "vibecraft_events__v1")

    class _Giu:
        def get_collections(self):
            raise ConnectionError("Qdrant irraggiungibile (simulato)")

    index.assert_rollback_target_has_vectors(_Giu(), "v1")  # nessuna eccezione


def test_reconciler_reports_legacy_when_no_manifest(monkeypatch):
    monkeypatch.setattr(index, "_read_manifest", lambda: None)
    q = AliasAwareFakeQdrant()
    report = index.reconcile_qdrant_alias(q)
    assert report["state"] == "legacy"
    assert report["expected"] is None


def test_reconciler_reports_legacy_when_manifest_lacks_qdrant_collection(monkeypatch):
    monkeypatch.setattr(index, "_read_manifest", lambda: {"version": "v1"})  # niente qdrant_collection
    q = AliasAwareFakeQdrant()
    report = index.reconcile_qdrant_alias(q)
    assert report["state"] == "legacy"


def test_reconciler_reports_missing_when_alias_not_set(monkeypatch):
    monkeypatch.setattr(index, "_read_manifest", lambda: {"qdrant_collection": "vibecraft_events__v1"})
    q = AliasAwareFakeQdrant(collections={"vibecraft_events__v1"})  # nessun alias creato
    report = index.reconcile_qdrant_alias(q)
    assert report == {"state": "missing", "expected": "vibecraft_events__v1", "actual": None}


def test_reconciler_reports_aligned_when_alias_matches_expected(monkeypatch):
    monkeypatch.setattr(index, "_read_manifest", lambda: {"qdrant_collection": "vibecraft_events__v1"})
    q = AliasAwareFakeQdrant(collections={"vibecraft_events__v1"},
                             aliases={index.COLLECTION_NAME: "vibecraft_events__v1"})
    report = index.reconcile_qdrant_alias(q)
    assert report == {"state": "aligned", "expected": "vibecraft_events__v1", "actual": "vibecraft_events__v1"}


def test_reconciler_reports_diverging_when_alias_points_elsewhere(monkeypatch):
    # CURRENT è avanzato a v2, ma l'alias punta ancora a v1 (es. crash tra il commit
    # locale e lo swap dell'alias — vedi design, finestra sub-secondo tollerata).
    monkeypatch.setattr(index, "_read_manifest", lambda: {"qdrant_collection": "vibecraft_events__v2"})
    q = AliasAwareFakeQdrant(collections={"vibecraft_events__v1", "vibecraft_events__v2"},
                             aliases={index.COLLECTION_NAME: "vibecraft_events__v1"})
    report = index.reconcile_qdrant_alias(q)
    assert report == {
        "state": "diverging", "expected": "vibecraft_events__v2", "actual": "vibecraft_events__v1",
    }


def test_reconciler_never_writes_to_qdrant_or_local_state(monkeypatch):
    """Sola osservazione: qualunque sia lo stato, reconcile_qdrant_alias non deve mai
    chiamare update_collection_aliases né create/delete_collection."""
    monkeypatch.setattr(index, "_read_manifest", lambda: {"qdrant_collection": "vibecraft_events__v2"})
    q = AliasAwareFakeQdrant(collections={"vibecraft_events__v1", "vibecraft_events__v2"},
                             aliases={index.COLLECTION_NAME: "vibecraft_events__v1"})
    index.reconcile_qdrant_alias(q)
    assert q.update_aliases_calls == 0
    assert index.list_qdrant_collections(q) == ["vibecraft_events__v1", "vibecraft_events__v2"]


# ---------------------------------------------------------------------------
# OPZIONALE / SKIPPABLE: contro un Qdrant reale, solo per validare che il fake non
# menta sulla semantica degli alias (atomicità del batch, risoluzione nelle
# point-operation). Si salta da sola se Qdrant non è raggiungibile: non richiede
# Docker per la suite di default e non tocca mai COLLECTION_NAME/dati reali — usa
# nomi di collection/alias dedicati e li ripulisce sempre a fine test.
# ---------------------------------------------------------------------------
def test_qdrant_guard_requires_explicit_test_endpoint(monkeypatch):
    monkeypatch.delenv("VIBECRAFT_TEST_QDRANT_URL", raising=False)
    monkeypatch.delenv("VIBECRAFT_REQUIRE_QDRANT", raising=False)

    with pytest.raises(pytest.skip.Exception, match="VIBECRAFT_TEST_QDRANT_URL"):
        _real_qdrant_client_or_skip()


def test_required_qdrant_guard_fails_without_explicit_test_endpoint(monkeypatch):
    monkeypatch.delenv("VIBECRAFT_TEST_QDRANT_URL", raising=False)
    monkeypatch.setenv("VIBECRAFT_REQUIRE_QDRANT", "1")

    with pytest.raises(RuntimeError, match="VIBECRAFT_TEST_QDRANT_URL"):
        _real_qdrant_client_or_skip()


def _real_qdrant_client_or_skip():
    test_url = os.environ.get("VIBECRAFT_TEST_QDRANT_URL")
    if not test_url:
        message = "VIBECRAFT_TEST_QDRANT_URL assente: test Qdrant reali non autorizzati."
        if os.environ.get("VIBECRAFT_REQUIRE_QDRANT") == "1":
            raise RuntimeError(message)
        pytest.skip(message)

    from qdrant_client import QdrantClient

    from core.config import QDRANT_API_KEY

    try:
        client = QdrantClient(url=test_url, api_key=QDRANT_API_KEY, timeout=2)
        client.get_collections()
    except Exception as exc:
        # In CI il servizio Qdrant c'è (services: nel workflow), quindi uno skip qui non è
        # più "l'ambiente non ce l'ha": è il gate che ha smesso di provare ciò che dichiara.
        # Un job verde che salta tutto è indistinguibile da un job verde che verifica —
        # ed è esattamente lo stato che questa variabile esiste per rendere impossibile.
        if os.environ.get("VIBECRAFT_REQUIRE_QDRANT") == "1":
            raise RuntimeError(
                f"VIBECRAFT_REQUIRE_QDRANT=1 ma Qdrant di test non è raggiungibile su {test_url}: "
                f"{exc}. Questi test NON devono saltare dove il servizio è dichiarato."
            ) from exc
        pytest.skip(f"Qdrant di test non raggiungibile su {test_url}: {exc}")
    return client


def test_alias_semantics_against_real_qdrant():
    """Integrazione opzionale: crea due collection throwaway, swappa un alias
    throwaway tra le due, verifica get_aliases()/query risolta, ripulisce sempre.
    MAI la collection/alias di produzione (COLLECTION_NAME) — nomi dedicati."""
    client = _real_qdrant_client_or_skip()
    from qdrant_client.models import Distance, VectorParams

    alias = "_test_blue_green_scaffolding_alias"
    col_a, col_b = "_test_blue_green_scaffolding_a", "_test_blue_green_scaffolding_b"
    try:
        for col in (col_a, col_b):
            try:
                client.delete_collection(col)  # idempotenza: ripulisce un run precedente interrotto
            except Exception:
                pass
            client.create_collection(
                collection_name=col,
                vectors_config=VectorParams(size=4, distance=Distance.COSINE),
            )
        index._swap_alias(client, alias, col_a)
        assert index._read_alias_target(client, alias) == col_a

        index._swap_alias(client, alias, col_b)
        assert index._read_alias_target(client, alias) == col_b

        # Point-operation sull'alias: deve risolvere sulla collection fisica corrente (col_b).
        client.upsert(collection_name=alias, points=[
            {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {}},
        ])
        assert client.count(collection_name=col_b, exact=True).count == 1
        assert client.count(collection_name=col_a, exact=True).count == 0
    finally:
        # delete_collection cancella anche gli alias che la puntavano (comportamento
        # reale di Qdrant, replicato dal fake sopra): non serve un delete_alias esplicito.
        for col in (col_a, col_b):
            try:
                client.delete_collection(col)
            except Exception:
                pass
        client.close()


def test_real_qdrant_rejects_alias_with_same_name_as_existing_collection():
    """Integrazione opzionale: verifica l'ASSUNZIONE su cui poggia l'intera
    migrazione one-shot legacy→alias (S6.6) — Qdrant rifiuta la creazione di un
    alias con lo stesso nome di una collection FISICA esistente (409 Conflict), e
    lo swap riesce solo DOPO che quella collection è stata cancellata: esattamente
    la sequenza delete-poi-create eseguita da _migrate_legacy_collection_if_needed
    + _swap_alias. Nomi throwaway dedicati, MAI COLLECTION_NAME — non tocca la
    produzione."""
    client = _real_qdrant_client_or_skip()
    from qdrant_client.models import Distance, VectorParams

    legacy_name = "_test_blue_green_legacy_collision"
    target = "_test_blue_green_legacy_collision_target"
    try:
        for col in (legacy_name, target):
            try:
                client.delete_collection(col)  # idempotenza: ripulisce un run precedente interrotto
            except Exception:
                pass
        client.create_collection(
            collection_name=legacy_name,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        client.create_collection(
            collection_name=target,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )

        # Prima della migrazione: legacy_name è ancora una collection fisica ->
        # Qdrant rifiuta di crearla anche come alias (il conflitto che giustifica
        # l'intera migrazione one-shot).
        assert index._qdrant_collection_exists(client, legacy_name) is True
        with pytest.raises(Exception):
            index._swap_alias(client, legacy_name, target)
        assert index._read_alias_target(client, legacy_name) is None  # rifiutato, nessun alias creato

        # Migrazione (S6.6): delete della collection fisica, poi lo swap riesce.
        migrated = index._migrate_legacy_collection_if_needed(client, legacy_name)
        assert migrated is True
        assert index._qdrant_collection_exists(client, legacy_name) is False
        index._swap_alias(client, legacy_name, target)
        assert index._read_alias_target(client, legacy_name) == target
    finally:
        for col in (legacy_name, target):
            try:
                client.delete_collection(col)
            except Exception:
                pass


def test_real_qdrant_rejects_create_collection_on_an_alias_name(monkeypatch):
    """Integrazione opzionale: verifica l'ASSUNZIONE su cui poggia il fix post-S10
    di incremental_index — Qdrant rifiuta create_collection() su un nome che è già
    un ALIAS (400 Bad Request), esattamente il bug che _ensure_collection(qdrant,
    collection_name=COLLECTION_NAME) provocava quando COLLECTION_NAME è un alias.
    Il fix passa invece la collection FISICA del padre: _ensure_collection su quel
    nome deve riuscire senza sollevare (già esiste, no-op). Nomi throwaway dedicati,
    MAI COLLECTION_NAME — non tocca la produzione."""
    client = _real_qdrant_client_or_skip()
    from qdrant_client.models import Distance, VectorParams

    physical = "_test_blue_green_ensure_physical"
    alias = "_test_blue_green_ensure_alias"
    try:
        for col in (physical,):
            try:
                client.delete_collection(col)  # idempotenza: ripulisce un run precedente interrotto
            except Exception:
                pass
        client.create_collection(
            collection_name=physical,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        index._swap_alias(client, alias, physical)
        assert index._read_alias_target(client, alias) == physical

        # Esattamente il bug: _ensure_collection sul nome dell'ALIAS solleva.
        with pytest.raises(Exception):
            index._ensure_collection(client, recreate=False, collection_name=alias)

        # Il fix: _ensure_collection sulla collection FISICA del padre non solleva
        # (esiste già -> no-op).
        index._ensure_collection(client, recreate=False, collection_name=physical)
    finally:
        try:
            client.update_collection_aliases(change_aliases_operations=[])
        except Exception:
            pass
        try:
            client.delete_collection(physical)  # cancella anche l'alias che la puntava
        except Exception:
            pass
        client.close()


def test_real_qdrant_delete_by_filter_resolves_the_alias():
    """Integrazione opzionale: la delete-by-filter di `_delete_doc_chunks` gira in
    produzione contro l'ALIAS (COLLECTION_NAME), non contro la collection fisica —
    e' il percorso caldo dell'indicizzazione incrementale, che cosi' ripulisce i
    chunk dei documenti modificati o cancellati.

    Nessun test lo verificava davvero (A8): i fake registrano solo QUALE nome di
    collection e' stato passato e ignorano del tutto il `points_selector`, quindi
    due assunzioni restavano senza prova — che Qdrant risolva l'alias anche per una
    point-operation di cancellazione, e che il filtro MatchAny su `payload.doc_id`
    tolga ESATTAMENTE i punti giusti. Se la prima fosse falsa l'incrementale
    lascerebbe indietro i chunk vecchi in silenzio, che e' il modo peggiore di
    sbagliare: l'indice resta servibile e mente.

    Qui si chiama la funzione di PRODUZIONE, non una sua imitazione. Nomi throwaway
    dedicati, MAI COLLECTION_NAME."""
    client = _real_qdrant_client_or_skip()
    from qdrant_client.models import Distance, VectorParams

    alias = "_test_blue_green_delete_alias"
    physical = "_test_blue_green_delete_physical"
    try:
        try:
            client.delete_collection(physical)  # idempotenza: run precedente interrotto
        except Exception:
            pass
        client.create_collection(
            collection_name=physical,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        index._swap_alias(client, alias, physical)

        # Tre punti di due documenti diversi: la cancellazione deve prenderne due e
        # lasciare il terzo — un delete-by-filter che cancella tutto passerebbe un
        # test che guardasse solo "il conteggio e' sceso".
        client.upsert(collection_name=physical, points=[
            {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {"doc_id": "a.md"}},
            {"id": 2, "vector": [0.2, 0.3, 0.4, 0.5], "payload": {"doc_id": "a.md"}},
            {"id": 3, "vector": [0.3, 0.4, 0.5, 0.6], "payload": {"doc_id": "b.md"}},
        ])
        assert client.count(collection_name=physical, exact=True).count == 3

        # La funzione di produzione, invocata sull'ALIAS come fa incremental_index.
        index._delete_doc_chunks(client, ["a.md"], collection_name=alias)

        assert client.count(collection_name=physical, exact=True).count == 1, \
            "delete-by-filter attraverso l'alias: deve restare il solo punto di b.md"
        superstiti = client.scroll(collection_name=physical, limit=10)[0]
        assert [p.payload["doc_id"] for p in superstiti] == ["b.md"]
    finally:
        try:
            client.delete_collection(physical)
        except Exception:
            pass
        client.close()


def test_real_qdrant_delete_collection_invalidates_its_aliases():
    """Integrazione opzionale: cancellare una collection fisica rimuove anche gli
    alias che la puntavano. E' un'assunzione su cui poggia il GC delle collection
    orfane (e la pulizia di questi stessi test), replicata dal fake — ma finora
    scritta solo in un commento, mai verificata contro Qdrant.

    Se fosse falsa, dopo un GC resterebbe un alias appeso a una collection
    inesistente: ogni richiesta successiva fallirebbe su un nome che *sembra*
    ancora valido. Nomi throwaway dedicati, MAI COLLECTION_NAME."""
    client = _real_qdrant_client_or_skip()
    from qdrant_client.models import Distance, VectorParams

    alias = "_test_blue_green_dangling_alias"
    physical = "_test_blue_green_dangling_physical"
    try:
        try:
            client.delete_collection(physical)
        except Exception:
            pass
        client.create_collection(
            collection_name=physical,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        index._swap_alias(client, alias, physical)
        assert index._read_alias_target(client, alias) == physical

        client.delete_collection(physical)

        assert index._read_alias_target(client, alias) is None, \
            "l'alias deve sparire con la collection che puntava, non restare appeso"
    finally:
        try:
            client.delete_collection(physical)
        except Exception:
            pass
        client.close()


def test_gc_orfane_non_cancella_nulla_senza_versioni_locali(tmp_path, monkeypatch):
    """Indice locale VUOTO => nessun GC. Un insieme di riferimenti vuoto significa "non ho
    basi per giudicare cosa sia orfano", non "e' orfano tutto".

    E' il difetto A20, e non e' teorico: un container avviato con database/ vuoto e puntato
    a un Qdrant CONDIVISO con un'installazione nativa ne ha distrutto le collection al primo
    boot. L'alias corrente sopravvive comunque (invariante gia' presente), quindi il sistema
    resta in piedi — ma i rollback alle versioni precedenti no, ed e' esattamente cio' che il
    blue/green esiste per garantire."""
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)  # nessuna versione su disco
    base = index.COLLECTION_NAME
    q = AliasAwareFakeQdrant(collections={f"{base}__v1", f"{base}__v2"})

    removed = index.gc_orphaned_qdrant_collections(q, base=base)

    assert removed == []
    assert sorted(index.list_qdrant_collections(q)) == [f"{base}__v1", f"{base}__v2"], \
        "con database/versions/ vuoto il GC non deve toccare alcuna collection"


def test_snapshot_lease_keeps_manifest_and_collection_until_release(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts, "DATABASE_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "INDEX_MODE", "legacy")
    monkeypatch.setenv("VIBECRAFT_INDEX_KEEP", "1")
    base = index.COLLECTION_NAME

    def save_full(marker):
        graph = nx.DiGraph()
        graph.add_node(marker)
        version = artifacts.save_artifacts(graph, {}, {}, {}, {})
        collection = index.qdrant_collection_name(version)
        index.write_index_manifest(0, version=version, qdrant_collection=collection,
                                   immutable=True)
        return version, collection

    v1, c1 = save_full("v1")
    artifacts.promote_version(v1)
    snapshot = artifacts.load_artifacts(version=v1, retain_lease=True)
    snapshot.colbert_store.close()
    v2, c2 = save_full("v2")
    artifacts.promote_version(v2)
    v3, c3 = save_full("v3")
    artifacts.promote_version(v3)
    qdrant = AliasAwareFakeQdrant(collections={c1, c2, c3}, aliases={base: c3})

    removed = index.gc_orphaned_qdrant_collections(qdrant)
    assert artifacts.manifest_path(v1).is_file()
    assert c1 in index.list_qdrant_collections(qdrant)
    assert c2 in removed

    snapshot.version_lease.close()
    assert v1 in artifacts.prune_versions(keep=1)
    assert c1 in index.gc_orphaned_qdrant_collections(qdrant)
