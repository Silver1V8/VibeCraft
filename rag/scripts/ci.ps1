# Pipeline CI minima: sync riproducibile (uv.lock) + lint + suite pytest. Nessun
# servizio esterno richiesto — Qdrant e Ollama possono restare spenti. I 3 test che
# toccano un Qdrant reale (tests/test_qdrant_blue_green.py) si auto-saltano con
# pytest.skip quando la connessione fallisce, quindi non serve alcun mock a livello
# di pipeline.
#
# Uso:  pwsh -File scripts/ci.ps1
# Exit: propagato dal primo comando che fallisce (0 se tutto verde).

$ErrorActionPreference = "Stop"

$RagDir = Split-Path -Parent $PSScriptRoot
Set-Location $RagDir

# Forza stdout/stderr UTF-8: su Windows, senza questo, sys.stdout usa la code page
# della console (es. cp1252) e il logging (messaggi con accenti) esplode con
# UnicodeEncodeError, corrompendo il capture di pytest e facendo fallire in cascata
# il setup/teardown di test successivi che non c'entrano nulla col logging.
$env:PYTHONUTF8 = "1"

uv sync --frozen
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

# Selezione esplicita in pyproject.toml (A9): import inutilizzati, variabili morte,
# nomi ambigui, import fuori ordine (con le eccezioni dichiarate) — segnali di
# correttezza, non gusto. Prima dei test: e' quasi istantaneo, e un problema qui
# non deve costare i minuti della suite per farsi vedere.
uv run ruff check .
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

uv run pytest -q
exit $LASTEXITCODE
