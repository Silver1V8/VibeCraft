# Template di Progetto

Scheletri dei documenti **specifici di dominio** che ogni progetto deve produrre da sé, e che per loro natura non possono stare nella baseline di `docs/`.

## Perché stanno qui e non in `docs/`

L'indicizzatore Graph-RAG percorre `docs/` in modo ricorsivo e senza esclusioni di cartella ([`source_files`](../rag/code_index/__init__.py) chiamato da [`rag/core/indexing.py`](../rag/core/indexing.py) senza `CODE_EXCLUDED_DIRS`). Un template è fatto di segnaposto e righe di esempio: indicizzarlo significherebbe metterlo in competizione di ranking con le norme reali, degradando la precisione del retrieval. Restano quindi fuori dal corpus indicizzato. `code/` è un altro albero: lì le cartelle in `CODE_EXCLUDED_DIRS` (dipendenze, artefatti di build) non si attraversano.

Quando un template viene compilato, il documento risultante va salvato **in `docs/`**, nella cartella corrispondente alla sua classificazione.

## Contenuto

| Template | Destinazione una volta compilato | `classification` |
|---|---|---|
| [`template_glossario_entita.md`](template_glossario_entita.md) | `docs/00_meta_governance/` | `DATA_DICTIONARY` |
| [`template_matrice_permessi.md`](template_matrice_permessi.md) | `docs/00_meta_governance/` | `AUTHORIZATION_POLICY` |
| [`template_registro_modifiche.md`](template_registro_modifiche.md) | `docs/00_meta_governance/` | `METADATA` |
| [`template_spec_tecnologica.md`](template_spec_tecnologica.md) | `docs/01_architecture_norms/` | `ARCHITECTURE` |
| [`template_spec_funzionale.md`](template_spec_funzionale.md) | `docs/02_specs_normative/` | `REQUIREMENTS` |

## Regole comuni

- Il nome del file compilato deve rispettare il pattern atteso dall'indicizzatore: le specifiche funzionali seguono `spec_*.md`.
- `graph_rag.node_id` deve essere univoco su tutto il corpus (`[REGOLA-INT-06]`).
- Il campo `path` del frontmatter deve coincidere con la posizione reale del file.
- Le entità di dominio si scrivono in maiuscolo fra backtick: senza questa marcatura il parser non crea gli archi del grafo (`[REGOLA-INT-02]`).
- Gli identificatori di regola seguono il formato `[PREFISSO-CATEGORIA-NN]` (`[REGOLA-VAL-07]`) e, una volta pubblicati, si deprecano — non si rinominano.

Prima di considerare un documento pronto, verifica che non restino segnaposto:

```bash
grep -rn "<<[A-Z_]*>>\|«" docs/
```
