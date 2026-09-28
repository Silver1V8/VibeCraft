#!/usr/bin/env bash
# Pipeline CI minima: sync riproducibile (uv.lock) + lint + suite pytest. In locale
# nessun servizio esterno e' richiesto: i CINQUE test che toccano un Qdrant reale
# (tests/test_qdrant_blue_green.py, sezione "OPZIONALE / SKIPPABLE") si auto-saltano
# con pytest.skip senza VIBECRAFT_TEST_QDRANT_URL esplicito o quando la connessione fallisce.
#
# In CI invece Qdrant c'e' (services: nel workflow) e saltarli sarebbe la regressione:
# il workflow esporta VIBECRAFT_TEST_QDRANT_URL del servizio dedicato e
# VIBECRAFT_REQUIRE_QDRANT=1, che trasforma quello skip in errore.
# Qui restiamo agnostici — se la variabile non c'e', lo skip resta uno skip.
#
# Uso:  scripts/ci.sh
# Exit: propagato dal primo comando che fallisce (set -e) — 0 se tutto verde.
set -euo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

# Forza stdout/stderr UTF-8: su Windows, senza questo, sys.stdout usa la code page
# della console (es. cp1252) e il logging (messaggi con accenti) esplode con
# UnicodeEncodeError, corrompendo il capture di pytest e facendo fallire in cascata
# il setup/teardown di test successivi che non c'entrano nulla col logging.
export PYTHONUTF8=1

uv sync --frozen

# Selezione esplicita in pyproject.toml (A9): import inutilizzati, variabili morte,
# nomi ambigui, import fuori ordine (con le eccezioni dichiarate) — segnali di
# correttezza, non gusto. Prima dei test: e' quasi istantaneo, e un problema qui
# non deve costare i minuti della suite per farsi vedere.
uv run ruff check .

# -rs: elenca OGNI skip col suo motivo, oltre al conteggio della riga di riepilogo.
# Senza, "5 skipped" si perde in fondo all'output e una regressione della copertura
# torna invisibile — che e' esattamente com'e' rimasta invisibile finora.
#
# NIENTE -q qui: pytest.ini lo passa gia' in addopts, e un secondo -q vale -qq, che
# sopprime PROPRIO la riga di riepilogo ("39 passed", "5 skipped") insieme all'elenco
# di -rs. Misurato: con -q -rs l'output finisce sulla barra di progresso.
uv run pytest -rs
