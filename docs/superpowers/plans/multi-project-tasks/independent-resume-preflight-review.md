# Independent resume preflight — 2026-10-05

Reviewer: resume_independent_review. Product authorship: none. Worktree: C:/Users/Silve/.codex/worktrees/multi-project/vibecraft. HEAD inspected: 4223b84; whole-branch baseline: 34b46dfeabcff05820240a1241baae1a215d3e1b.

## Restored review state

Tasks 1/2/3/6 and bounded Task 5 context/MCP seam have recorded reviews and commits. Task 4 is unstaged and being completed by its assigned implementer; no Task 4 verdict is made here. Its two recorded P2 findings remain pending stable-package verification: structured workflow HTTP errors losing their message in the UI, and synchronous snapshot/resource loads blocking async routes. Full Task 5, distribution and final integration still require independent review. Previous test results in the ledger are historical evidence, not rerun evidence from this reviewer.

Read the binding plan, progress ledger, independent-preflight-review.md, Task 5 native policy preflight and Task 5/7 handoff rules. No baseline/full suite repeated; no provider, native sandbox, production Qdrant, user config, host security configuration or product file touched. Reports alone are written.

## Native runner alternatives and compatibility

The existing fail-closed ruling is justified by an unverified enforcement boundary, not by a claim that native products lack permission facilities. Codex officially documents a profile denying root reads with minimal runtime exceptions and workspace access. This is a concrete candidate; the earlier local parser check does not establish runtime profile selection or enforcement. [Codex Permissions](https://learn.chatgpt.com/docs/permissions).

Both Windows sandbox modes involve filesystem permission boundaries; elevated additionally uses dedicated users, firewall and local policy changes, while unelevated uses a restricted token and ACL boundaries. Therefore merely selecting unelevated is not evidence that a probe meets the current no-host-security-changes constraint. No probe launched. [Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox).

Cursor documents separate Read, Write, Shell and MCP permission tokens, wildcard support and deny precedence. An all-shell/all-MCP denial plus scoped reads is a possible reduced-capability candidate, but this review has not proved the installed version's behavior, link handling, defaults or subprocess bypasses. A deny rule for all reads also denies allowed reads; deny precedence cannot express an exception by adding a narrower allow without additional documented semantics. [Cursor CLI permissions](https://cursor.com/docs/cli/reference/permissions).

Cursor supports a process-specific configuration directory through CURSOR_CONFIG_DIR, yet also loads project permission configuration. The reference alone does not establish that a temporary global policy cannot be weakened by project merging. This requires explicit verification before enabling the runner. [Cursor CLI configuration](https://cursor.com/docs/cli/reference/configuration).

### Minimum compatible scope of the current ruling

1. Keep native runner metadata, clear unavailability reason and server admission consistent; reject before subprocess creation for ordinary, legacy and None contexts. Do not silently substitute a provider.
2. Preserve existing external IDE handoff: project-specific final-prompt/export and read-only MCP remain independent of integrated native runner availability. Current routes_pipeline.py already separates /final-prompt and /export from /agent/run. In Task 5, do not reuse the unavailable-runner admission check to reject the export/consumer=external path. External tools remain governed by their own permissions; VibeCraft must not claim to sandbox those tools.
3. Preserve pure native event/argv translation helpers and their tests if they remain useful, while ensuring no execution entry bypasses admission. This keeps the eventual reenablement small without introducing a policy framework.
4. A no-tools/native text-only launch, Docker/WSL adapter, or SDK replacement is not an equivalent verified drop-in today: each changes behavior or execution environment and requires new evidence. Do not implement speculative fallback in this scope.

Recommendation to PM: retain the explicit integrated-launch limitation unless a bounded, authorized enforcement proof becomes available; describe its precise scope and preserve existing external handoff flows. This is a compatibility recommendation, not a replacement ruling or completed Task 5 review.

## Next review gates

- Task 4 stable package: context capture through jobs/retries/SSE, callback/store/eval isolation, indexing lock lifecycle, and actual regression checks for both P2 findings.
- Task 5: direct and HTTP admission, SDK/local guards including registered nested legacy projects and replaced roots/ancestors, fixed MCP identity, indexing CLI dispatch with absent flag retaining legacy.
- Task 7: persistent project volume/nonroot behavior, authenticated process liveness, truthful CLI limits and operational docs, CI wiring.
- Final: inspect full baseline diff and actual acceptance evidence; no acceptance claim based solely on prior task summaries.
