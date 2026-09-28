# F5-06 historical migration — prepared

`migration_experiment.py` is a local-only driver for a PM-prepared empty dedicated checkout. It allows exactly seven regular historical artifact files with no linked path components, records source/copy hashes before and after, migrates under the writer lock, verifies NPY-only candidate layout, deep hashes and all 257 arrays, then replays cached candidates (including its single `missing`) and rolls back under the writer lock. It preserves all versions and records failure JSON. The historical manifest collection is never contacted.

This proves local conversion and replay correctness only. It makes no migration memory claim because the NPZ dictionary remains live during the comparison.
