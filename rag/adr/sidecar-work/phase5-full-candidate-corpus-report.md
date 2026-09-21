# Full-candidate corpus preparation

Prepared two identical derived corpora from the first 32 entries in the original JSON order of [chunks.json](C:/Users/Silve/.codex/worktrees/0628/vibecraft/rag/eval/results/sidecar_20260915/sandbox/historical-artifacts/v20260911T155042/chunks.json). Each entry becomes one synthetic Markdown document; the historical chunk text is retained verbatim after only a title and frontmatter. The manifests label this `synthetic_corpus: true` because document boundaries and frontmatter are reconstructed. This selection is for comparable pre/post exploration and does not assert a fixed post-parse token or chunk count.

The pre copy is [experiment](C:/Users/Silve/.codex/worktrees/0628/vibecraft/rag/eval/results/sidecar_fullmemory_pre_20260921/sandbox/experiment). It contains the required `rag/` code extracted from `phase3-base-0f479b2.zip`, excluding `rag/eval/results`, `rag/database`, and source `docs`; its dedicated configuration is the F3 docs N=100 configuration with collection `sidecar_0628_fullmemory_pre`. Its `docs/`, `code/`, and `rag/database/` were empty before preparation; the code corpus and database remain empty.

The post copy contains only [corpus-prepared](C:/Users/Silve/.codex/worktrees/0628/vibecraft/rag/eval/results/sidecar_fullmemory_post_20260921/sandbox/corpus-prepared); it deliberately contains no production-code copy.

Both provenance manifests record all selected IDs and output file hashes:

- [pre provenance](C:/Users/Silve/.codex/worktrees/0628/vibecraft/rag/eval/results/sidecar_fullmemory_pre_20260921/evidence/corpus-provenance.json)
- [post provenance](C:/Users/Silve/.codex/worktrees/0628/vibecraft/rag/eval/results/sidecar_fullmemory_post_20260921/evidence/corpus-provenance.json)

Validation found 32 documents in each corpus with identical selection and byte hashes. The source chunk file SHA-256 is `be1ce2d5fe381d724aa3ced3d3c1f134127f7532da0ae2c31eda556f69b31f6d`; the frozen pre-code archive SHA-256 is `db975819284055d1c1b78c73f0ea80c21f6d24ac1252b387a5f4197d0f623ea2`.
