# Batch notturno ECONOMICO: check di integrità dell'indice senza embedding (secondi).
#
# index.py --check-integrity verifica manifest, hash dei sorgenti, integrità degli
# artefatti in database/ e allineamento del conteggio Qdrant. In base al report:
#   - ok                          -> niente da fare;
#   - stale (solo sorgenti)       -> reindex incrementale: POST /api/reindex al server
#                                    locale se raggiungibile (X-API-Key da env), altrimenti
#                                    fallback a index.py --incremental;
#   - artefatti corrotti o Qdrant -> full rebuild (index.py).
#     disallineato
#
# Il confronto profondo incrementale vs full rebuild (che ri-embedda tutto) è ora nel
# batch SETTIMANALE: scripts/weekly_consistency.ps1.
#
# Env opzionali: VIBECRAFT_SERVER_URL (default http://127.0.0.1:8000), VIBECRAFT_API_KEY.
#
# Uso:  pwsh -File scripts/nightly_consistency.ps1
# Exit: 0 se ok / riallineato / reindex accodato; 1 su errore.

$ErrorActionPreference = "Stop"

# Radice del package rag/ (questo script vive in rag/scripts/).
$RagDir = Split-Path -Parent $PSScriptRoot
Set-Location $RagDir

Write-Host "[$(Get-Date -Format o)] Check di integrita' dell'indice (economico, zero embedding)..."

# stdout = report JSON (i messaggi umani vanno su stderr), exit 1 se ci sono problemi.
$reportJson = & uv run python index.py --check-integrity 2>$null
$checkExit = $LASTEXITCODE

if ($checkExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Integrita' OK: nessuna azione necessaria."
    exit 0
}

try {
    $report = $reportJson | ConvertFrom-Json
} catch {
    Write-Host "[$(Get-Date -Format o)] ERRORE: report di integrita' non parsabile."
    exit 1
}

$report.problems | ForEach-Object { Write-Host "[$(Get-Date -Format o)]   problema: $_" }

if ($report.artifacts_corrupted -or $report.qdrant_mismatch) {
    # Artefatti corrotti/misti o Qdrant disallineato: un incrementale non basta.
    Write-Host "[$(Get-Date -Format o)] Artefatti corrotti o Qdrant disallineato: full rebuild..."
    & uv run python index.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$(Get-Date -Format o)] Full rebuild completato: indice riallineato."
        exit 0
    }
    Write-Host "[$(Get-Date -Format o)] ERRORE: full rebuild fallito (exit $LASTEXITCODE)."
    exit 1
}

if ($report.stale) {
    # Solo sorgenti cambiate: basta un reindex incrementale. Preferisci il server (un solo
    # scrittore: la coda del ReindexManager), fallback alla CLI se il server e' spento.
    $baseUrl = if ($env:VIBECRAFT_SERVER_URL) { $env:VIBECRAFT_SERVER_URL } else { "http://127.0.0.1:8000" }
    $headers = @{}
    if ($env:VIBECRAFT_API_KEY) { $headers["X-API-Key"] = $env:VIBECRAFT_API_KEY }
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/reindex" -Headers $headers -TimeoutSec 10
        Write-Host "[$(Get-Date -Format o)] Indice stale: reindex incrementale accodato al server (job $($resp.job_id))."
        exit 0
    } catch {
        Write-Host "[$(Get-Date -Format o)] Server non raggiungibile ($baseUrl): fallback a index.py --incremental..."
    }
    & uv run python index.py --incremental
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$(Get-Date -Format o)] Reindex incrementale completato."
        exit 0
    }
    Write-Host "[$(Get-Date -Format o)] ERRORE: reindex incrementale fallito (exit $LASTEXITCODE)."
    exit 1
}

Write-Host "[$(Get-Date -Format o)] ERRORE: problemi di integrita' non riconducibili a stale/corruzione (vedi sopra)."
exit 1
