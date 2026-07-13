# Batch notturno di fallback: guardrail contro l'invecchiamento dell'indice.
#
# Il reindex incrementale (POST /api/reindex, tipicamente via webhook GitLab) tiene
# l'indice aggiornato durante il giorno, ma l'incrementale puo' accumulare deriva sui
# code-link (vedi core/indexing.py). Questo script, da schedulare di notte (Windows Task
# Scheduler), fa il check di coerenza del grafo e, SOLO se trova drift, esegue un full
# rebuild che riallinea tutto alla topologia di riferimento.
#
# Uso:
#   pwsh -File scripts/nightly_consistency.ps1
# Exit code: 0 se coerente o rebuild riuscito; 1 se il rebuild e' fallito.

$ErrorActionPreference = "Stop"

# Radice del package rag/ (questo script vive in rag/scripts/).
$RagDir = Split-Path -Parent $PSScriptRoot
Set-Location $RagDir

Write-Host "[$(Get-Date -Format o)] Check di coerenza del grafo (incrementale vs full rebuild)..."

# index.py --check-graph esce 1 se il grafo incrementale DIVERGE dal full rebuild.
& uv run python index.py --check-graph
$checkExit = $LASTEXITCODE

if ($checkExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Grafo coerente: nessun rebuild necessario."
    exit 0
}

Write-Host "[$(Get-Date -Format o)] Drift rilevato (exit $checkExit): avvio full rebuild..."
& uv run python index.py
$rebuildExit = $LASTEXITCODE

if ($rebuildExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Full rebuild completato: indice riallineato."
    # Nota: il server FastAPI rileva graph.pkl cambiato su disco e ricarica gli artefatti
    # in memoria alla prima richiesta successiva (api/deps.py::maybe_reload_graph).
    exit 0
} else {
    Write-Host "[$(Get-Date -Format o)] ERRORE: full rebuild fallito (exit $rebuildExit)."
    exit 1
}
