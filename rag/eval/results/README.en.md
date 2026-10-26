English | [Italiano](README.md)

# Evaluation evidence

## Sidecar scalability — 21 September 2026

Implementation integrated in `3eda61a`: per-document ColBERT NPY, on-demand reads,
reuse of unchanged files, and real-delta measurements.

| Evidence | What it shows |
|---|---|
| [Reader](../../../archive/eval-results/sidecar_readers_20260921/evidence/summary.csv) | In the I/O experiment, USS increase at load: 233,312,256 bytes eager NPZ vs 528,384 bytes NPY; this is not whole-service memory |
| [Full and migration](../../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE5.md) | RSS peak 6.436 → 3.152 GiB on 32 documents / 64 chunks; one trial per variant. Exact migration of persisted arrays |
| [Delta and trade-offs](../../../archive/eval-results/sidecar_npy_20260921/evidence/PHASE6.md) | 150 trials per version; at N=100/k=100 documents, median 15.934 → 58.099 s until snapshot ready |
| [T(N,k) curves](../../../archive/eval-results/sidecar_npy_20260921/evidence/phase6-summary/summary.md) | Medians and intervals for documents, code, and mixed; differences vs no-op |
| [Retention](../../../archive/eval-results/sidecar_retention_20260921/evidence/retention-summary.md) | Hard-link reuse, protected readers, and physically deduplicated space on NTFS |

The measured code is `708a142`, compared with `0f479b2`; the final review
corrects NPY write attribution from `parsing_embedding` to `save_hash`.
Historical breakdowns keep the limit documented in PHASE6; totals, bytes, and
resources were not recomputed. These are not LLM answer-quality measures.
Corpus and hardware limit generalization: no delta/full crossover,
maximum capacity, or universal sharding threshold was demonstrated.

## Propose evaluations and evidence retention

**Phase 2 closed, 14 September 2026:** [final report of the three Propose rounds](FASE2_PROPOSE_20260914.md).
At close: qualitative improvement not demonstrated; V3 not adopted, V4 rejected.
The report includes the reservation on the FE3-F4 perimeter, which also applies to
the FE3 counts below. No starter or pilot started.

**Next step:** V3 adopted in `a8b2416`, with a known limit on feature boundaries.
[Structural comparison after adoption](propose_adopted_v3_20260914/evidence/RESULTS.md):
six new answers against the six preserved `bd87bd7^`, without a substantive judgment.
The current prompt also includes the advisory report: it does not isolate the change
on ambiguities alone. The final report keeps the three prior rounds and now includes
the later outcome: more declared points without a drop in structural counts;
substantive quality not re-evaluated. Declared points in the text were 6/6,
but the parser recognized only 2/6 as valid reports. Numbered-title recognition
was fixed: now 5/6 valid and 1/6 invalid for malformed JSON, without automatic
repairs. [Recheck](propose_adopted_v3_20260914/evidence/PARSER_RECHECK.json).

`history.jsonl` keeps aggregated events for the `/eval` page. The data that lets
you examine them lives under `<run>/evidence/`. Outside that folder, artifacts
remain local: a JSON extension alone does not make them evidence.

For each run keep aggregate and per-case metrics, answers, sources and verdicts,
parameters/prompt and command used, model versions, index, corpus, and code when
available. An unrecorded datum must be declared missing, never reconstructed as if
it had been measured. Before appending an event to history, publish its evidence and
document the link via UTC timestamp, index version, and evaluation type (`source`).

Model weights, caches, code/corpus copies, and regenerable intermediates stay
outside `evidence/`. Diagnostic logs stay local; when a log is the only proof of a
gate, keep the relevant lines with line number and hash of the original file.
Attribution evidence also requires the text and sources: an aggregate score alone
does not let you review the verdict.

## Retention of the 7–11 September 2026 runs

The 17 pre-existing folders were kept without re-running evaluations and without
deleting originals. Each `EVIDENCE_MANIFEST.json` lists origin, copy path, size, and
SHA-256, plus files left local. `path` values are relative to this folder; `source`
to the repo root. `.gitattributes` preserves proof bytes even on Windows checkouts.

Historical scripts are archived as `.py.txt`, `.sh.txt`, `.ps1.txt`, or `.cjs.txt`:
they are proof of procedure, not application code to run or discover with lint/pytest.
Commands and reports keep references to the original environment; reproducing them
requires reconstituting paths and having the stated versions. The copies do not attest
that that environment is still available.

Not all of these runs produce events in `history.jsonl`: many measure parsing,
attribution, context, or conversion. They must not be confused with general retrieval
or treated as a measure of recent pipeline-prompt changes.

## Linking the 11 events of 7–11 September 2026

Each record in this group in `history.jsonl` declares `evidence`: `full` for an
available per-case report (5), `partial` for a gate excerpt without per-case detail
(2), `none` when no independent proof was found (4). `full` describes report
availability; it does not certify environment reproducibility or answer quality.
Prior records without this field were not classified: absence does not mean `full`.
At the 14 September 2026 check, history contains 137 records: only these 11 are
classified and the other 126 are not. The 5 / 2 / 4 split and any summary based on
the `evidence` field therefore describe only the classified subset, not the whole
history.

Times below are UTC. Reports from 8 September use Italian local time (UTC+2);
the name `153456` precedes the history append by about one second. Associations are
based on time, type, and metrics, not folder name alone. The five per-case reports
do not record `index_version` directly: the version shown is the history event’s,
consistent with the P0/pilot reports; that correlation does not replace an identifier
saved in the run. `history.jsonl` currently has no reference to the report.

| UTC event | Index | Preserved proof | Coverage |
|---|---|---|---|
| 07/09 14:58:11 gate | `v20260907T145734` | No autonomous report found | Local aggregate event only; no independent gate proofs |
| 07/09 15:09:38 gate | `v20260907T150309` | No autonomous report found | Local aggregate event only; no independent gate proofs |
| 07/09 15:21:51 gate | `v20260907T151549` | No autonomous report found | Local aggregate event only; no independent gate proofs |
| 08/09 13:31:15 gate | `v20260908T132451` | [Excerpt of original log](p0_20260908-152239/evidence/gate_log_excerpt.json) | Recall@2, threshold, case count, and promotion; no per-case gate detail |
| 08/09 13:34:47 eval.run | `v20260908T132451` | [Retrieval report](p0_20260908-152239/evidence/original_eval/eval_20260908_153447.json) | Per-case report |
| 08/09 13:34:57 multihop | `v20260908T132451` | [Multihop report](p0_20260908-152239/evidence/original_eval/multihop_20260908_153456.json) | Per-case report |
| 08/09 13:39:02 eval.run | `v20260908T132451` | [Retrieval report](p0_20260908-152239/evidence/original_eval/eval_20260908_153902.json) | Per-case report |
| 08/09 13:39:12 multihop | `v20260908T132451` | [Multihop report](p0_20260908-152239/evidence/original_eval/multihop_20260908_153912.json) | Per-case report |
| 08/09 15:13:52 multihop | `v20260908T132451` | [Multihop report](../../../archive/eval-results/pilot_docling_20260908-170030/evidence/out/multihop_20260908_171352.json) | Per-case report |
| 10/09 12:18:45 gate | `v20260910T121150` | [Excerpt of original log](../../../archive/eval-results/verifica_finale_20260910/evidence/gate_log_excerpt.json) | Recall@2, threshold, case count, and promotion; no per-case gate detail |
| 11/09 15:54:05 gate | `v20260911T155042` | No autonomous report found | Local aggregate event only; no independent gate proofs |

The four gaps were not filled by duplicating history or re-running today’s code:
neither operation would produce proof of the historical run. The four events are kept
with `evidence: "none"`, without attributing proofs or checks that were not recovered.

## Attribution judge — agreement on the calibration sample

The historical 20/24 result is agreement on the same 24 records used to calibrate the
judge prompt, across six variants, as documented in [AUDIT, S14](../../../archive/adr/AUDIT.md).
It is not an accuracy estimate on new cases: it must not be used as judge reliability,
error bound, or basis for Phase 2 conclusions. It remains a calibration result only.

A future accuracy estimate requires records with independent human verdicts, never used
to choose or change the prompt, and freezing the judge before evaluation. Judge results
remain separate from the [archived human verdicts](../golden_attribution.yaml): this note
does not modify them and does not certify their validity on the current index.

## Propose ablation of 14 September 2026 — descriptive comparison

Whole files of `rag/prompts/spec.md` in `bd87bd7^` and `bd87bd7` were compared on FE3
and LA2 with three repeats per combination (12 answers), frozen Canvas and sources, and
the same model. The two changes in `bd87bd7` — declared assumptions/open points and number
of scenarios per feature — are measured together: this comparison does not separate their
effects and does not measure MCP or the gate.

Evidence: [protocol](../../../archive/eval-results/propose_ablation_20260914/evidence/PROTOCOL.md),
[method note](../../../archive/eval-results/propose_ablation_20260914/evidence/HUMAN_REVIEW.md),
[FE3 sheets](../../../archive/eval-results/propose_ablation_20260914/evidence/REVIEW_FE3.md),
[LA2 sheets](../../../archive/eval-results/propose_ablation_20260914/evidence/REVIEW_LA2.md),
[key](../../../archive/eval-results/propose_ablation_20260914/evidence/AFTER_REVIEW/KEY.json), and
[provider measurements](../../../archive/eval-results/propose_ablation_20260914/evidence/AFTER_REVIEW/MEASUREMENTS.json).
The method note and sheet headers were completed before the key was opened. Review is
human with Claude assistance; different source-access order between FE3 and LA2, 13
protocol findings, and 3 non-assessable claims remain explicit limits of the measure.

| Count | `bd87bd7^` | `bd87bd7` |
|---|---:|---:|
| Declared preregistered ambiguities, FE3 + LA2 | 0 / 27 | 3 / 27 |
| FE3: F listed in the nominal field and negatives covered | 7 | 2 |
| LA2: F listed in the nominal field and negatives covered | 6 | 4 |
| FE3: supported / assessable claims | 18 / 28 | 19 / 25 |
| FE3: unsupported / conflicted / not_assessable | 4 / 6 / 0 | 4 / 2 / 0 |
| LA2: supported / assessable claims | 18 / 34 | 13 / 33 |
| LA2: unsupported / conflicted / not_assessable | 2 / 14 / 2 | 1 / 19 / 1 |
| SCENARIO headers per answer, on both features | 7 in 6/6 answers | 4 in 6/6 answers |

Ambiguities are summed over the three repeats: 9 FE3 and 18 LA2 opportunities per group,
not 27 distinct doubts. Listed coverage drops FE3 7→2 and LA2 6→4; these are literal
counts from the sheet fields, with the reservations already noted (P06 on F2; P07 on F1
and F5), not certified complete coverage or scenarios satisfied by code. The
supported/assessable ratio and conflicted counts move in opposite directions on the two
features; claim counts remain separate from coverage and omissions.

The 7/4 split in scenario count is sharp across all answers. FE3 has four expected
features and LA2 five: the theoretical minimum would be 8 and 10 scenarios respectively,
except declared unresolved cases. Scenario count may explain the coverage drop
independently of the assumptions/open-points change; that is a hypothesis to verify, not
a cause isolated by this ablation. The prompt contains the explicit per-feature rule, but
also the reminder “For coverage that exceeds the 4 scenarios” without repeating its scope.
No prompt correction or new generation was done for this record.

The P08 summary was corrected from 7/9 to 6/9 supported, matching the nine rows of its
table (6 supported, 2 unsupported, 1 conflicted); no atomic verdict changed. Mechanical
files in AFTER_REVIEW keep the pre-review state: the human counts above come from the
updated sheets. No starter or pilot started.

## Open point — shared cache for the next Docling pilots

The ~701 MB of weights found in the isolated pilot run do not come from the current
application path: [the historical script](../../../archive/eval-results/pilot_docling_standard_20260909-095127/evidence/run_standard.py.txt)
received `artifacts_path` as an argument and [the run report](../../../archive/eval-results/pilot_docling_standard_20260909-095127/evidence/run2/run_report.json)
places it under `pilot_docling_standard_20260909-095127/artifacts`.
The application already uses `intake.docling.models_dir`, configured as
`rag/database/models/docling`, and verifies SHA-256 before load
(`core/intake_convert.py`). No weights were moved.

Before the next pilot, verify that it reuses that shared path and that required revisions
match those fixed in `scripts/docling_models.py` and the hashes expected by the pilot.
From `rag/`, `scripts/docling_models.py --verifica` checks application weights without
downloading them; it alone does not certify compatibility of a pilot that needs different
revisions. Record in the new evidence the resolved path, revisions, and actual hashes,
verifying that the run does not contain new copies of the weights. If different revisions
are needed, plan a shared cache distinct per revision without overwriting application
weights. Verification of the next pilots still to run; no migration or change to their
code in this intervention.
