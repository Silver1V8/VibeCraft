# Task 4 — correction batch 1 independent re-review

Date: 2026-10-05. Reviewer: resume_independent_review; product remains read-only. Compared `task-4-fix-1-review-package.diff` with the working-tree delta against the staged initial candidate on base HEAD 4223b84. Scope: four product files (`routes_intake.py`, `routes_pipeline.py`, `canvas_review.py`, `pipeline.py`), the new regression cases in `test_project_workflows.py`, and the implementation report. PM plan/ledger changes excluded.

**PASS for this correction delta. All five initial findings addressed; no new blocking finding in the inspected delta.** Full Task 4 integration and commit remain the PM's gate; this is not full-branch acceptance.

| Initial finding | Resolution verified |
| --- | --- |
| P1 foreign Git/tasks fallback on empty captured code | `generate_canvas_review` now distinguishes None from an explicit empty string. Archive always supplies captured `_review_code`; empty ordinary and legacy code cannot invoke the generic fallback. Both layouts run through actual archive with a parent Git repository tracking B, matching feature commit and B tasks reference; positive captured A code is preserved. The standalone helper checks exact Git top-level before using Git history. |
| P2 external prompt transport selection | Captured project ID appears in the HTTP header instruction for every request and the MCP startup environment instruction. A/B output remains distinct; no-context legacy output keeps its previous transport behavior. No integrated runner availability check was added to export/prompt generation. |
| P2 valid gate unavailable after eviction | The shared source-state boundary acquires `require_snapshot(project)` and converts genuine HTTP resource/index errors to the existing validation availability error. Actual cold A and LRU A/B/C cases restore the same gate without rewriting validation bytes. Corrupt CURRENT yields safe sources_unavailable, while B remains healthy. All production callers reach this synchronous helper inside the existing threadpool/admission/finish functions; the held-loader responsiveness test confirms the event loop remains available. |
| P2 Explore provider diagnostics | HTTP Explore calls `llm.agenerate` and catches LLMError at its public boundary, using the existing safe error helper. The tolerant 200 flow and history are preserved without private diagnostics; success output remains unchanged. Historical `generate_tolerant` semantics are unchanged. |
| P2 staged preview path disclosure | StagedDocumentNotFoundError receives a safe message in the shared intake error adapter. Actual successful upload/preview followed by deletion of only the fixture derivative retains HTTP 404 and staged state without host path disclosure. |

## Fresh independent checks

From worktree `rag/`, original existing Python interpreter with worktree PYTHONPATH and PYTHONUTF8=1:

- `pytest tests/test_project_workflows.py -k 'archive_explicit_code or standalone_review or external_prompt_binds or explore_provider_failure or missing_staged_markdown or gate_cold_load or gate_snapshot_capture' -q -o addopts='' --tb=short`: **10 passed, 35 deselected, 0 skipped, 14.87s; exit 0**.
- Four collateral checks: exact-root Git subject matching, standalone tasks fallback, review truncation compatibility, and historical tolerant LLM error behavior: **4 passed, 0 skipped, 17.12s; exit 0**.
- `git diff --check`: no whitespace errors (Windows newline conversion notices only).
- Rechecked production callsites for `_validation_source_state`/`_gate_payload` and the archive/generate/collect chain. No newly introduced caller bypass found in this delta.

All checks use temporary fixtures or injected providers; no real provider/native runner, Qdrant service, corpus write, dependency installation or original-checkout change. No product edits, stage or commit by the reviewer. The implementer's wider gate is separate evidence and was not repeated here.
