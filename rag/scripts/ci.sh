#!/usr/bin/env bash
# Pipeline CI minima: sync riproducibile (uv.lock) + suite pytest. Nessun servizio
# esterno richiesto — Qdrant e Ollama possono restare spenti. I 3 test che toccano
# un Qdrant reale (tests/test_qdrant_blue_green.py) si auto-saltano con pytest.skip
# quando la connessione fallisce, quindi non serve alcun mock a livello di pipeline.
#
# Uso:  scripts/ci.sh
# Exit: propagato da pytest (0 verde, 1 test falliti/errore).
set -euo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

# Forza stdout/stderr UTF-8: su Windows, senza questo, sys.stdout usa la code page
# della console (es. cp1252) e il logging (messaggi con accenti) esplode con
# UnicodeEncodeError, corrompendo il capture di pytest e facendo fallire in cascata
# il setup/teardown di test successivi che non c'entrano nulla col logging.
export PYTHONUTF8=1

uv sync --frozen
uv run pytest -q
