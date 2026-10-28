"""Costruzione dell'indice Graph-RAG: grafo NetworkX + collection Qdrant (hybrid dense/sparse)
+ sidecar ColBERT/chunk, con indicizzazione completa e incrementale (delta), manifest e check
di integrità/coerenza. Il caricamento/chunking dei documenti vive in core/chunking.py; la
configurazione in core/config.py; il blue/green Qdrant (alias, rollback, reconciler, GC) in
core/qdrant_versions.py; il check drift in core/drift_check.py; l'archiviazione delle change
in core/feature_archive.py (nomi re-esportati qui). Le risorse pesanti (Qdrant, embedding)
sono iniettabili.

R5 (2026-10-28): il monolite core/indexing.py è stato suddiviso nel package
core/indexing/ (common, graph_build, full, cow_delta, integrity). L'API pubblica
`from core.indexing import ...` / `from core import indexing` resta stabile.

Monkeypatch: i test storici patchano attributi su `core.indexing`. Le chiamate interne
vivono nei sottomoduli con binding locali; `__setattr__` del package propaga i patch
ai sottomoduli che già espongono quel nome — stesso contratto del monolite pre-R5.
Un monkeypatch su un modulo già estratto (qdrant_versions, drift_check, …) va applicato
lì, non sul re-export."""
from __future__ import annotations

import sys
import time  # noqa: F401  # seam: test_index_timings patcha index.time.perf_counter
from types import ModuleType

from FlagEmbedding import BGEM3FlagModel  # noqa: F401  # seam monkeypatch
from qdrant_client import QdrantClient  # noqa: F401  # seam monkeypatch

from core.colbert_store import ColbertStore, ColbertWriter  # noqa: F401

# Moduli estratti in precedenza: i nomi restano importabili da core.indexing.
from core.drift_check import check_drift  # noqa: F401
from core.feature_archive import archive_feature  # noqa: F401
from core.qdrant_versions import (  # noqa: F401
    RollbackTargetCollectionMissing,
    _migrate_legacy_collection_if_needed,
    _qdrant_collection_exists,
    _qdrant_collection_for_version,
    _read_alias_target,
    _referenced_qdrant_collections,
    _swap_alias,
    assert_rollback_target_has_vectors,
    gc_orphaned_qdrant_collections,
    gc_qdrant_collections,
    list_qdrant_collections,
    observe_qdrant_alias,
    parse_qdrant_collection_version,
    qdrant_collection_name,
    reconcile_and_repair_qdrant_alias,
    reconcile_qdrant_alias,
    repair_qdrant_alias,
    rollback_qdrant_alias_if_needed,
    rollback_shares_collection_with_later_versions,
)

# Re-export usati dai test come seam su core.indexing (artefatti / gate / config).
from core.artifacts import (  # noqa: F401
    _new_version_name,
    _read_manifest,
    activate_immutable_index,
    artifact_hashes,
    immutable_index_active,
    load_artifacts,
    promote_version,
    save_artifacts,
    sha256_file,
)
from core.eval_gate import gate_promotion  # noqa: F401
from core.config import (  # noqa: F401
    CODE_DIR,
    COLLECTION_NAME,
    DELTA_MODE,
    DOCS_DIR,
    EMBEDDING_MODEL,
    PROJECT_ROOT,
)
from code_index import (  # noqa: F401
    collect_code_symbols,
    embed_symbols,
    link_symbols,
)

from . import common, cow_delta, full, graph_build, integrity
from .common import (  # noqa: F401
    INSTANTIATION_FIELD,
    _STATUS_HASH_CACHE,
    _code_hashes,
    _colbert_token_count,
    _declares_instantiation,
    _dense_map,
    _diff_hashes,
    _encode_chunks_to_points,
    _ensure_collection,
    _new_phase_timings,
    _point_id,
    _status_sha256,
    docs_hashes,
    index_status,
    observe_docs_git_divergence,
    write_index_manifest,
)
from .graph_build import (  # noqa: F401
    _SECTION_INHERITED_ATTRS,
    _add_doc_to_graph,
    _add_section_nodes,
    _prune_unsupported_entities,
    _remove_doc_nodes_from_graph,
    _resolve_authority_aliases,
    _semantic_base,
)
from .full import (  # noqa: F401
    FullState,
    _build_full_state,
    _gate_and_publish,
    build_graph_and_index,
)
from .cow_delta import (  # noqa: F401
    IndexPlan,
    _CowUnavailable,
    _apply_code_delta,
    _attested_parent_colbert,
    _clone_points,
    _cow_delta_index,
    _delete_doc_chunks,
    _delta_manifest_hashes,
    _entity_nodes,
    _partition_changed_paths,
    _relink_touched_symbols,
    _restrict_plan,
    _sorted_chunk_ids,
    _symbols_beaten_by_new_chunks,
    _symbols_referencing_entities,
    _symbols_with_stale_argmax,
    apply_incremental_indexing,
    incremental_index,
    plan_incremental_indexing,
)
from .integrity import (  # noqa: F401
    _edge_set,
    _node_type_set,
    check_graph_consistency,
    check_index_integrity,
    precedence_cycles,
)

_SEAM_MODULES = (common, graph_build, full, cow_delta, integrity)


class _IndexingPackage(ModuleType):
    """Propaga setattr ai sottomoduli che già espongono il nome (seam monkeypatch R5)."""

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for mod in _SEAM_MODULES:
            if name in mod.__dict__:
                ModuleType.__setattr__(mod, name, value)


_pkg = sys.modules[__name__]
_pkg.__class__ = _IndexingPackage
