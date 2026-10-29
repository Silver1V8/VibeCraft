English | [Italiano](README.md)

# Project Templates

Skeletons for **domain-specific** documents that each project must produce on its own, and that by nature cannot live in the `docs/` baseline.

## Why they live here and not in `docs/`

The Graph-RAG indexer walks `docs/` recursively with no folder exclusions ([`source_files`](../rag/code_index/__init__.py) called from [`rag/core/indexing.py`](../rag/core/indexing.py) without `CODE_EXCLUDED_DIRS`). A template is made of placeholders and sample lines: indexing it would put it in ranking competition with real norms and degrade retrieval precision. They therefore stay outside the indexed corpus. `code/` is a different tree: there, folders in `CODE_EXCLUDED_DIRS` (dependencies, build artifacts) are not traversed.

When a template is filled in, the resulting document must be saved **under `docs/`**, in the folder that matches its classification.

## Contents

| Template | Destination once filled in | `classification` |
|---|---|---|
| [`template_glossario_entita.md`](template_glossario_entita.md) | `docs/00_meta_governance/` | `DATA_DICTIONARY` |
| [`template_matrice_permessi.md`](template_matrice_permessi.md) | `docs/00_meta_governance/` | `AUTHORIZATION_POLICY` |
| [`template_registro_modifiche.md`](template_registro_modifiche.md) | `docs/00_meta_governance/` | `METADATA` |
| [`template_spec_tecnologica.md`](template_spec_tecnologica.md) | `docs/01_architecture_norms/` | `ARCHITECTURE` |
| [`template_spec_funzionale.md`](template_spec_funzionale.md) | `docs/02_specs_normative/` | `REQUIREMENTS` |

## Shared rules

- The filled-in file name must match the pattern expected by the indexer: functional specs follow `spec_*.md`.
- `graph_rag.node_id` must be unique across the whole corpus (`[REGOLA-INT-06]`).
- The frontmatter `path` field must match the file’s real location.
- Domain entities are written in uppercase inside backticks: without that markup the parser does not create graph edges (`[REGOLA-INT-02]`).
- Rule identifiers follow `[PREFISSO-CATEGORIA-NN]` (`[REGOLA-VAL-07]`) and, once published, are deprecated — not renamed.

Before considering a document ready, check that no placeholders remain:

```bash
grep -rn "<<[A-Z_]*>>\|«" docs/
```
