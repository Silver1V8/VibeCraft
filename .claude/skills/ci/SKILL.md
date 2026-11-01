---
name: ci
description: Verifica completa prima di commit/push — ci.sh (uv sync --frozen + ruff + pytest, come GitHub Actions) più i test browser .cjs con Playwright 1.62.1
disable-model-invocation: true
---

# /ci — verifica completa di vibecraft

Esegui i passi in ordine e fermati al primo rosso, riportando l'output del fallimento.

## 1. Gate Python (identico a `.github/workflows/ci.yml`)

```bash
cd rag && bash scripts/ci.sh
```

- Exit 0 = verde. Lo script fa `uv sync --frozen`, `uv run ruff check .`, `uv run pytest -rs`.
- Leggi l'elenco `-rs` degli skip: i **5 test Qdrant** (`tests/test_qdrant_blue_green.py`) si
  auto-saltano senza `VIBECRAFT_TEST_QDRANT_URL`. Se sono saltati, dillo esplicitamente: un verde
  locale senza Qdrant NON li copre (in CI `VIBECRAFT_REQUIRE_QDRANT=1` li rende obbligatori).
  Per coprirli: Qdrant di test acceso (`docker compose up -d qdrant`) ed esporta
  `VIBECRAFT_TEST_QDRANT_URL=http://127.0.0.1:6333` prima di ci.sh.

## 2. Test JS (`rag/tests/*.cjs`)

Quelli browser vogliono Playwright **1.62.1** (stessa versione della CI) con chromium build 1234
(la 1228 già presente non basta). Installalo in una cartella temporanea, mai nel repo:

```bash
PW="$TEMP/vibecraft-pw" && npm install --prefix "$PW" --no-package-lock playwright@1.62.1 && "$PW/node_modules/.bin/playwright" install chromium
```

Poi, da `rag/`, esegui ogni `tests/*.cjs` con `NODE_PATH="$PW/node_modules" node <file>`, con queste eccezioni:

- `projects_workspace.cjs` va lanciato con `--navigation`: copre anche `navigation_workspace.cjs`
  (che da solo cerca un server sulla porta 9876), quindi non lanciare quest'ultimo a parte.
- `project_integration_browser.cjs` gira solo da pytest con un Qdrant di test dedicato: saltalo
  in locale e segnalalo come "coperto dalla CI".

## 3. Esito

Riporta una tabella: ruff, pytest (passed/skipped, con i motivi degli skip), ogni .cjs. Non
dichiarare "verde" se qualche passo è stato saltato senza dirlo.
