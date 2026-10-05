# Batch notturno ECONOMICO: check di integrità dell'indice senza embedding (secondi).
#
# index.py --check-integrity verifica manifest, hash dei sorgenti, integrità degli
# artefatti in database/ e allineamento del conteggio Qdrant. In base al report:
#   - ok                             -> niente da fare;
#   - qdrant_unreachable             -> NESSUNA scrittura (ne' rebuild ne' incrementale): la
#                                        lineage non e' verificabile senza un conteggio
#                                        Qdrant riuscito. Solo alert, si ritenta la notte dopo;
#   - artefatti corrotti o Qdrant    -> full rebuild: POST /api/reindex {"full": true} al
#     disallineato                     server locale se raggiungibile (coda del
#                                        ReindexManager, un solo scrittore; X-API-Key da env),
#                                        altrimenti fallback a index.py;
#   - stale (solo sorgenti)          -> reindex incrementale: POST /api/reindex al server
#                                        locale se raggiungibile (X-API-Key da env), altrimenti
#                                        fallback a index.py --incremental.
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

$ProjectId = if ($env:VIBECRAFT_PROJECT_ID) { $env:VIBECRAFT_PROJECT_ID } else { "legacy" }
$projectHeaders = @{ "X-VibeCraft-Project" = $ProjectId }
if ($env:VIBECRAFT_API_KEY) { $projectHeaders["X-API-Key"] = $env:VIBECRAFT_API_KEY }

# Alert su fallimento (check fallito E rimedio fallito): appende una riga JSON a
# database/alerts.jsonl (letta da GET /api/health) e, se VIBECRAFT_ALERT_WEBHOOK e'
# impostata, POSTa lo stesso JSON a quell'URL. Entrambi best-effort: un errore di
# scrittura/rete non deve mascherare l'exit code del batch.
function Send-Alert([string]$Message) {
    $json = @{ timestamp = (Get-Date -Format o); script = "nightly_consistency.ps1"; error = $Message } | ConvertTo-Json -Compress
    try {
        $env:VIBECRAFT_SCRIPT_ERROR = $Message
        & uv run python -c "import os; from core.projects import resolve_registered_project; from core.eval_gate import record_alert; p=resolve_registered_project(os.environ.get('VIBECRAFT_PROJECT_ID')); record_alert('critical', os.environ['VIBECRAFT_SCRIPT_ERROR'], path=p.database_dir/'alerts.jsonl')" *> $null
    } catch {} finally { Remove-Item Env:VIBECRAFT_SCRIPT_ERROR -ErrorAction SilentlyContinue }
    if ($env:VIBECRAFT_ALERT_WEBHOOK) {
        try { Invoke-RestMethod -Method Post -Uri $env:VIBECRAFT_ALERT_WEBHOOK -ContentType "application/json" -Body $json -TimeoutSec 10 | Out-Null } catch {}
    }
}

# Check di QUALITA' del retrieval (Epic 5.2), opportunistico: se il server e' raggiungibile
# (modello gia' caricato), valuta la recall sul golden set e, via --check-regression, registra un
# alert critico in database/alerts.jsonl se e' calata. Non blocca il batch.
#
# NIENTE --assert-min: la soglia e la k sono quelle dell'eval-gate, che eval.run legge da
# rag_config.yaml (A2b). Qui c'era un `--assert-min 0.90` scritto a mano, e senza `--k` il
# confronto cadeva su recall@10 — satura a 1.000 — quindi questo check non poteva fallire.
$qualityUrl = if ($env:VIBECRAFT_SERVER_URL) { $env:VIBECRAFT_SERVER_URL } else { "http://127.0.0.1:8000" }
try {
    Invoke-RestMethod -Uri "$qualityUrl/api/health" -Headers $projectHeaders -TimeoutSec 5 | Out-Null
    Write-Host "[$(Get-Date -Format o)] Check di qualita' del retrieval (eval sul golden set)..."
    & uv run python -m eval.run --project $ProjectId --url $qualityUrl --check-regression *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "[$(Get-Date -Format o)] Qualita' del retrieval OK." }
    else { Write-Host "[$(Get-Date -Format o)] Qualita' del retrieval: regressione o sotto soglia (alert registrato)." }

    # Suite STRUTTURALE/MULTIHOP (A4). Era l'unica suite senza gate: girava a mano, quindi la
    # classe di domande piu' preziosa per un grafo di governance poteva regredire in silenzio.
    # Soglia e regola stanno in `eval_multihop` di rag_config.yaml; l'alert lo scrive lo script.
    # Costo: 14 chiamate a /api/retrieve e /api/graph/query, nessun LLM.
    Write-Host "[$(Get-Date -Format o)] Check strutturale/multihop (grafo + retrieval)..."
    & uv run python -m eval.run_multihop --project $ProjectId --url $qualityUrl *> $null
    if ($LASTEXITCODE -eq 0) { Write-Host "[$(Get-Date -Format o)] Suite strutturale/multihop OK." }
    else { Write-Host "[$(Get-Date -Format o)] Suite strutturale/multihop sotto soglia (alert registrato)." }

    # I DUE CONTRATTI CHE PRETENDONO UN LLM VERO (R10, R11). In CI non c'e' un modello:
    # l'astensione e' esercitata solo contro un provider finto e la soglia di certezza su
    # num_ctx era stata osservata a mano una volta sola. Girano qui perche' questo e' il
    # canale che ha Ollama acceso ed e' gia' collegato agli alert. Costo: 2 chiamate a
    # /ask, di cui una si ferma PRIMA del modello (e' il punto del secondo check).
    # -SkipHttpErrorCheck e' obbligatorio: con $ErrorActionPreference = "Stop" un 502 —
    # che qui e' l'esito ATTESO — solleverebbe, e il catch esterno lo inghiottirebbe.

    # R10 — l'astensione e' un impegno del PROMPT, non una garanzia del modello: una
    # domanda fuori corpus deve tornare status "abstained" (marcatore [ASTENSIONE] scritto
    # dal modello e letto da ask_rag), non "success" con le fonti elencate.
    Write-Host "[$(Get-Date -Format o)] Contratto di astensione (domanda fuori corpus)..."
    $askStatus = ""
    try {
        $r = Invoke-WebRequest -Method Post -Uri "$qualityUrl/ask" -Headers $projectHeaders -ContentType "application/json" -TimeoutSec 600 -SkipHttpErrorCheck `
            -Body '{"question":"qual e la ricetta tradizionale della carbonara e quanti grammi di guanciale servono per quattro persone"}'
        $askStatus = ($r.Content | ConvertFrom-Json).status
    } catch {}
    if ($askStatus -eq "abstained") {
        Write-Host "[$(Get-Date -Format o)] Astensione OK (status abstained)."
    } else {
        Write-Host "[$(Get-Date -Format o)] ASTENSIONE NON RISPETTATA: status '$askStatus' invece di 'abstained'."
        Send-Alert "il modello non ha rispettato [REGOLA-ASTENSIONE] su una domanda fuori corpus (status: '$askStatus')"
    }

    # R11 — soglia di CERTEZZA su num_ctx (A1): a top_k=20 il prompt supera la finestra e
    # /ask DEVE rispondere 502 col messaggio dichiarato, mai un 200 "success" su un prompt
    # che Ollama troncherebbe dall'alto in silenzio. Misurato il 2026-09-05 su questa
    # domanda: ~17.424 token stimati contro num_ctx=16384 (106,3%).
    # Un 200 NON e' un falso allarme benigno: o il guardrail non scatta piu', o il contesto
    # si e' ridotto sotto la finestra — in entrambi i casi questo check non sta piu'
    # esercitando il contratto, ed e' proprio quello che va detto invece di restare verde.
    Write-Host "[$(Get-Date -Format o)] Soglia di certezza su num_ctx (top_k=20)..."
    $ctxCode = 0; $ctxBody = ""
    try {
        $r = Invoke-WebRequest -Method Post -Uri "$qualityUrl/ask" -Headers $projectHeaders -ContentType "application/json" -TimeoutSec 600 -SkipHttpErrorCheck `
            -Body '{"question":"quali vincoli valgono sui dati personali fra log, test e chiamate a LLM esterni?","top_k":20}'
        $ctxCode = [int]$r.StatusCode; $ctxBody = $r.Content
    } catch {}
    if ($ctxCode -eq 502 -and $ctxBody -match 'FINESTRA DI CONTESTO SUPERATA') {
        Write-Host "[$(Get-Date -Format o)] Soglia di certezza OK (502 col messaggio dichiarato)."
    } elseif ($ctxCode -eq 502) {
        Write-Host "[$(Get-Date -Format o)] 502 ma con un messaggio diverso da quello dichiarato."
        Send-Alert "il 502 oltre la finestra non porta piu' il messaggio [FINESTRA DI CONTESTO SUPERATA]"
    } else {
        Write-Host "[$(Get-Date -Format o)] top_k=20 non supera piu' la finestra (HTTP $ctxCode): contratto NON esercitato."
        Send-Alert "la soglia di certezza su num_ctx non e' piu' esercitata: top_k=20 ha risposto $ctxCode invece di 502"
    }
} catch {}

Write-Host "[$(Get-Date -Format o)] Check di integrita' dell'indice (economico, zero embedding)..."

# stdout = report JSON (i messaggi umani vanno su stderr), exit 1 se ci sono problemi.
$reportJson = & uv run python index.py --project $ProjectId --check-integrity 2>$null
$checkExit = $LASTEXITCODE

# Divergenza docs/ su disco <-> docs/ committato. NON e' un "problema" del report (non
# entra in `ok`: un reindex non la ripara, quindi non deve innescare remediation), ma va
# stampata SEMPRE - anche a integrita' OK, che e' il caso in cui altrimenti resterebbe
# invisibile. I file di docs/ sono skip-worktree: git status non la mostra.
try {
    $docsGit = ($reportJson | ConvertFrom-Json).docs_git
    if ($docsGit -and $docsGit.state -eq 'diverging') {
        $elenco = ($docsGit.diverging | Select-Object -First 5) -join ', '
        if ($docsGit.diverging.Count -gt 5) { $elenco += ' ...' }
        $riga = "$($docsGit.diverging.Count)/$($docsGit.tracked) file: $elenco"
        Write-Host "[$(Get-Date -Format o)] ATTENZIONE: docs/ su disco DIVERGE dal committato - $riga"
        Write-Host "[$(Get-Date -Format o)] Il RAG indicizza la copia su disco: un reindex NON riallinea nulla."
        Send-Alert "docs/ su disco diverge dal committato ($riga)"
    }
} catch {
    # Report non parsabile: il ramo sotto lo gestisce gia' con un alert dedicato.
}

if ($checkExit -eq 0) {
    Write-Host "[$(Get-Date -Format o)] Integrita' OK: nessuna azione necessaria."
    exit 0
}

try {
    $report = $reportJson | ConvertFrom-Json
} catch {
    Write-Host "[$(Get-Date -Format o)] ERRORE: report di integrita' non parsabile."
    Send-Alert "report di integrita' non parsabile"
    exit 1
}

$report.problems | ForEach-Object { Write-Host "[$(Get-Date -Format o)]   problema: $_" }

if ($report.qdrant_unreachable) {
    # Qdrant giu': niente scritture al buio, ne' rebuild ne' incrementale (la lineage
    # non e' verificabile senza un conteggio riuscito). Solo alert, si riprova la notte dopo.
    Write-Host "[$(Get-Date -Format o)] Qdrant non raggiungibile: nessuna azione (nessun rebuild, nessun incrementale)."
    Send-Alert "Qdrant irraggiungibile durante il check notturno"
    exit 1
}

if ($report.artifacts_corrupted -or $report.qdrant_mismatch) {
    # Artefatti corrotti/misti o Qdrant disallineato: un incrementale non basta, serve un
    # full rebuild. Preferisci il server (un solo scrittore: la coda del ReindexManager),
    # fallback alla CLI se il server e' spento.
    Write-Host "[$(Get-Date -Format o)] Artefatti corrotti o Qdrant disallineato: full rebuild..."
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
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$(Get-Date -Format o)] Full rebuild completato: indice riallineato."
        exit 0
    }
    Write-Host "[$(Get-Date -Format o)] ERRORE: full rebuild fallito (exit $LASTEXITCODE)."
    Send-Alert "check di integrita' fallito e full rebuild fallito (exit $LASTEXITCODE)"
    exit 1
}

if ($report.stale) {
    # Solo sorgenti cambiate: basta un reindex incrementale. Preferisci il server (un solo
    # scrittore: la coda del ReindexManager), fallback alla CLI se il server e' spento.
    $baseUrl = if ($env:VIBECRAFT_SERVER_URL) { $env:VIBECRAFT_SERVER_URL } else { "http://127.0.0.1:8000" }
    $headers = $projectHeaders.Clone()
    if ($env:VIBECRAFT_API_KEY) { $headers["X-API-Key"] = $env:VIBECRAFT_API_KEY }
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/reindex" -Headers $headers -TimeoutSec 10
        Write-Host "[$(Get-Date -Format o)] Indice stale: reindex incrementale accodato al server (job $($resp.job_id))."
        exit 0
    } catch {
        Write-Host "[$(Get-Date -Format o)] Server non raggiungibile ($baseUrl): fallback a index.py --incremental..."
    }
    & uv run python index.py --project $ProjectId --incremental
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$(Get-Date -Format o)] Reindex incrementale completato."
        exit 0
    }
    Write-Host "[$(Get-Date -Format o)] ERRORE: reindex incrementale fallito (exit $LASTEXITCODE)."
    Send-Alert "indice stale e reindex incrementale fallito (exit $LASTEXITCODE)"
    exit 1
}

Write-Host "[$(Get-Date -Format o)] ERRORE: problemi di integrita' non riconducibili a stale/corruzione (vedi sopra)."
Send-Alert "problemi di integrita' non riconducibili a stale/corruzione: $($report.problems -join '; ')"
exit 1
