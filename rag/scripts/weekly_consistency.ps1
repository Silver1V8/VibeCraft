# Batch SETTIMANALE profondo: guardrail contro la deriva dell'incrementale.
#
# index.py --check-graph fa un full rebuild IN MEMORIA (ri-embedda tutto) e confronta il
# grafo incrementale persistito con la topologia di riferimento: e' costoso (minuti su
# CPU) ma esaustivo. SOLO se trova drift esegue un full rebuild che riallinea tutto,
# preferendo il server (coda del ReindexManager, un solo scrittore) con fallback alla CLI.
# Il check quotidiano economico e' scripts/nightly_consistency.ps1.
#
# Env opzionali: VIBECRAFT_SERVER_URL (default http://127.0.0.1:8000), VIBECRAFT_API_KEY.
#
# Uso:  pwsh -File scripts/weekly_consistency.ps1
# Exit: 0 se coerente o rebuild riuscito/accodato; 1 se il rebuild e' fallito.

$ErrorActionPreference = "Stop"

# Radice del package rag/ (questo script vive in rag/scripts/).
$RagDir = Split-Path -Parent $PSScriptRoot
Set-Location $RagDir

$ProjectId = if ($env:VIBECRAFT_PROJECT_ID) { $env:VIBECRAFT_PROJECT_ID } else { "legacy" }
$projectHeaders = @{ "X-VibeCraft-Project" = $ProjectId }
if ($env:VIBECRAFT_API_KEY) { $projectHeaders["X-API-Key"] = $env:VIBECRAFT_API_KEY }

Write-Host "[$(Get-Date -Format o)] Check di coerenza del grafo (incrementale vs full rebuild)..."

# index.py --check-graph esce 1 se il grafo incrementale DIVERGE dal full rebuild.
& uv run python index.py --project $ProjectId --check-graph
$checkExit = $LASTEXITCODE

if ($checkExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Grafo coerente: nessun rebuild necessario."
    exit 0
}

Write-Host "[$(Get-Date -Format o)] Drift rilevato (exit $checkExit): avvio full rebuild..."

# Preferisci il server (un solo scrittore: la coda del ReindexManager), fallback alla
# CLI se il server e' spento.
$baseUrl = if ($env:VIBECRAFT_SERVER_URL) { $env:VIBECRAFT_SERVER_URL } else { "http://127.0.0.1:8000" }
$headers = $projectHeaders.Clone()
if ($env:VIBECRAFT_API_KEY) { $headers["X-API-Key"] = $env:VIBECRAFT_API_KEY }
try {
    $resp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/reindex" -Headers $headers -Body (@{full = $true} | ConvertTo-Json -Compress) -ContentType "application/json" -TimeoutSec 10
    Write-Host "[$(Get-Date -Format o)] Full rebuild accodato al server (job $($resp.job_id))."
    exit 0
} catch {
    Write-Host "[$(Get-Date -Format o)] Server non raggiungibile ($baseUrl): fallback a index.py (full rebuild)..."
}

& uv run python index.py --project $ProjectId
$rebuildExit = $LASTEXITCODE

if ($rebuildExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Full rebuild completato: indice riallineato."
    # Nota: il server FastAPI rileva graph.json cambiato su disco e ricarica gli artefatti
    # in memoria alla prima richiesta successiva (api/deps.py::maybe_reload_graph).
    exit 0
} else {
    Write-Host "[$(Get-Date -Format o)] ERRORE: full rebuild fallito (exit $rebuildExit)."
    exit 1
}
