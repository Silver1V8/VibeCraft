English | [Italiano](README.md)

# Archive

Historical development material: no runtime code reads it, it is not part of the Docker
image (`Dockerfile` copies only `rag/`, `docs/`, and `code/`; this folder stays outside the
build context anyway, see `.dockerignore`), and it is not required to run the tests.
It is kept for traceability — past decisions and measurements remain verifiable — without
weighing down the trees that are consulted day to day (`rag/adr/`, `rag/eval/results/`).

## Contents

- `adr/sidecar-work/` — checkpoints (brief/report/review) for a single ADR initiative
  (ColBERT sidecar scalability), moved here from the former `rag/adr/sidecar-work/`.
  Derived summaries stay in `rag/adr/` (e.g. `SCALABILITA_SIDECAR_DELTA*.md`).
- `adr/AUDIT.md`, `adr/RESIDUI.md`, `adr/EVOLUZIONE.md` — the chronicle closed in September
  2026, relocated on 25 October 2026. Line numbers did not change: a citation
  `rag/adr/AUDIT.md:4013` in the evidence still points to the same place in `adr/AUDIT.md`.
  Those citations were not rewritten.
- `adr/0002-prompts/` — the prompts used to execute ADR 0002. The decision remains in
  `rag/adr/0002-autorita-dichiarata-e-fiducia-sul-cammino.md`.
- `adr/horizontal-bench/` — the runs from 28 September 2026. A new run is still written
  under `rag/adr/horizontal-bench/`.
- `eval-results/<run>/` — evaluation runs moved from the former `rag/eval/results/<run>/`.
  From 2026-10-28 (R6) the **tip** keeps reports (`.md`, CSV, scripts, patches) and drops
  heavy blobs (`.json` / `.jsonl` / `.log` / `.zip`, ~108 MiB) from the working tree: see
  [`eval-results/HEAVY_REMOVED.md`](eval-results/HEAVY_REMOVED.md). Bytes remain in git
  history; the `sparse-checkout` recipe in [README.md](../README.md) / [README.en.md](../README.en.md)
  avoids downloading them on fresh clones. `*/evidence/** -text` in
  `eval-results/.gitattributes` still applies to remaining and restored blobs.

## What is NOT here

`rag/eval/results/history.jsonl` (read by `rag/core/eval_history.py` behind the `/eval`
page and `GET /api/eval-history`), `rag/eval/results/README.md`,
`rag/eval/results/FASE2_PROPOSE_20260914.md`, and the other loose files (calibrations,
baselines, benches) stay where they are: they are small, and some are read or written by
application code. In `rag/adr/` the decisions still cited by code and READMEs remain:
the index, `0001`, `0002`, `PIPELINE_GATE.md`, `DISTRIBUTION.md`, and summaries of closed
initiatives. The audit, residuals, evolution plan, 0002 prompts, and `horizontal-bench`
runs are no longer there.

## Links

Documents moved here still point, where possible, to files cited elsewhere in the
repository with relative paths updated for the new location; references to source lines
or commits remain text, not links, as in the original.

## Frozen archive

The content is kept as testimony, not to be re-run. Reports and scripts still on the tip
are byte-for-byte the originals (even where an internal relative link no longer resolves
from the new location). Reproduction scripts (`*.py`, `*.py.txt`) assume the old path
`rag/eval/results/<run>/evidence/` — for example `Path(__file__).parents[4]` to reach
`rag/`, or sibling runs looked up next to their own folder. To re-run them they must be
temporarily restored to that location, and heavy evidence restored from history if needed
(see `HEAVY_REMOVED.md`). New runs are produced under `rag/eval/results/`, not here: that
is why the archive does not have the `.gitignore` evidence whitelist that governs that tree.
