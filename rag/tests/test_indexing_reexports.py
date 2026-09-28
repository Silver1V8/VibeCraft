"""Scomposizione di core/indexing.py: blue/green Qdrant in core/qdrant_versions.py, check
drift in core/drift_check.py, archiviazione in core/feature_archive.py. I chiamanti
esistenti (CLI index.py, api/routes_reindex.py, api/deps.py, api/routes_pipeline.py)
importano ancora da core.indexing: i re-export devono essere GLI STESSI oggetti dei
moduli nuovi, non copie (altrimenti un confronto d'identità o un'eccezione catturata
per classe smetterebbero di funzionare)."""
import pytest

from core import artifacts, drift_check, feature_archive, indexing, qdrant_versions

_QDRANT_REEXPORTS = (
    "RollbackTargetCollectionMissing",
    "_migrate_legacy_collection_if_needed",
    "_qdrant_collection_exists",
    "_qdrant_collection_for_version",
    "_read_alias_target",
    "_referenced_qdrant_collections",
    "_swap_alias",
    "assert_rollback_target_has_vectors",
    "gc_orphaned_qdrant_collections",
    "gc_qdrant_collections",
    "list_qdrant_collections",
    "observe_qdrant_alias",
    "parse_qdrant_collection_version",
    "qdrant_collection_name",
    "reconcile_and_repair_qdrant_alias",
    "reconcile_qdrant_alias",
    "repair_qdrant_alias",
    "rollback_qdrant_alias_if_needed",
    "rollback_shares_collection_with_later_versions",
)


@pytest.mark.parametrize("name", _QDRANT_REEXPORTS)
def test_reexport_qdrant_versions_stesso_oggetto(name):
    assert getattr(indexing, name) is getattr(qdrant_versions, name)


def test_reexport_drift_e_archive_stesso_oggetto():
    assert indexing.check_drift is drift_check.check_drift
    assert indexing.archive_feature is feature_archive.archive_feature
    assert indexing._read_manifest is qdrant_versions._read_manifest is artifacts._read_manifest


def test_docs_hashes_pubblico_e_usato_dalle_route():
    """api/routes_pipeline importava la privata _docs_hashes: ora usa il nome pubblico."""
    from api import routes_pipeline

    assert callable(indexing.docs_hashes)
    assert routes_pipeline.docs_hashes is indexing.docs_hashes
    assert not hasattr(routes_pipeline, "_docs_hashes")


def test_moduli_estratti_non_importano_indexing_a_livello_di_modulo():
    """Nessun ciclo d'import: i moduli estratti non legano core.indexing come globale
    (archive_feature lo importa solo lazy, per la re-indicizzazione inline)."""
    for mod in (qdrant_versions, drift_check, feature_archive):
        assert "indexing" not in vars(mod)
