# Bootstrap physical collection alias repair

The fresh incremental bootstrap writes a manifest whose `qdrant_collection` is the physical production collection (`COLLECTION_NAME`). Qdrant has no alias with that name, because a physical collection already owns it. The reconciler interpreted this valid layout as `missing` and `repair_qdrant_alias` attempted to create an alias with the same name, producing Qdrant 409. The rollback helper had the same failure path.

Callers traced: `reconcile_qdrant_alias` feeds observation, boot repair and the incremental lineage guard; `repair_qdrant_alias` is called by boot and incremental; rollback uses `_read_alias_target` independently. `_swap_alias` must retain its strict alias semantics for blue/green builds and legacy migration. The fix treats a declared, existing physical collection with the production name as effectively aligned in reconciliation and rollback, without changing `_read_alias_target` or writing to Qdrant. A genuinely missing parent still fails the existing guard.

Regression: `test_bootstrap_physical_collection_is_aligned_without_alias` failed before the fix (`missing` vs `aligned`), then passed. Focused suite: `tests/test_incremental_indexing.py`, 85 passed. No live Qdrant mutation or benchmark run. Remaining limitation: this tests the deterministic fake Qdrant path; the PM owns the live calibration rerun.
