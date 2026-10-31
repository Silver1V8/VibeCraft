## What and why · Cosa e perché

<!-- Link the issue if there is one · Collega la issue se c'è: Closes #... -->

## Checklist

- [ ] `bash rag/scripts/ci.sh` is green · è verde
- [ ] Commit messages use a conventional prefix (`feat:`, `fix:`, `docs:`, ...) · I commit usano un prefisso convenzionale
- [ ] New or changed HTTP routes / MCP tools are reflected in `rag/SECURITY_SURFACE.md` (or none) · Route HTTP / tool MCP nuovi o cambiati sono in `rag/SECURITY_SURFACE.md` (o nessuno)
- [ ] Calibrated parameters (`boost_alpha`, `graph_context_max_chunks`, `section_restatement_weight`) untouched, or recalibrated together · Parametri calibrati invariati, o ricalibrati insieme
- [ ] Docs updated where behaviour changed · Documentazione aggiornata dove cambia il comportamento
- [ ] If authority, classification, status, precedences, `authority.*`, `graph_trust.*`, or the governance checker change: the detection list was read by someone other than the author. GitHub does not enforce that yet (`rag/eval/GOVERNANCE_APPROVAL.md`) · Se cambiano autorità, classe, status, precedenze, `authority.*`, `graph_trust.*` o il rilevatore: la lista l'ha letta qualcuno che non è l'autore. GitHub non lo impone ancora (`rag/eval/GOVERNANCE_APPROVAL.md`)
