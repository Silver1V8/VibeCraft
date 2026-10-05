#!/usr/bin/env bash
# Batch SETTIMANALE profondo: guardrail contro la deriva dell'incrementale (variante POSIX
# dello script PowerShell). Da schedulare via cron. Vedi weekly_consistency.ps1 per i
# dettagli. Il check quotidiano economico e' scripts/nightly_consistency.sh.
#
# Env opzionali: VIBECRAFT_SERVER_URL (default http://127.0.0.1:8000), VIBECRAFT_API_KEY.
#
# Uso:   scripts/weekly_consistency.sh
# Exit:  0 se coerente o rebuild riuscito/accodato; 1 se il rebuild e' fallito.
set -euo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

project_id="${VIBECRAFT_PROJECT_ID:-legacy}"
project_headers=(-H "X-VibeCraft-Project: $project_id")
[ -n "${VIBECRAFT_API_KEY:-}" ] && project_headers+=(-H "X-API-Key: ${VIBECRAFT_API_KEY}")

echo "[$(date -Is)] Check di coerenza del grafo (incrementale vs full rebuild)..."

# index.py --check-graph esce 1 se il grafo incrementale DIVERGE dal full rebuild.
if uv run python index.py --project "$project_id" --check-graph; then
    echo "[$(date -Is)] Grafo coerente: nessun rebuild necessario."
    exit 0
fi

echo "[$(date -Is)] Drift rilevato: avvio full rebuild..."

# Preferisci il server (un solo scrittore: la coda del ReindexManager), fallback alla
# CLI se il server e' spento.
base_url="${VIBECRAFT_SERVER_URL:-http://127.0.0.1:8000}"
headers=("${project_headers[@]}")
[ -n "${VIBECRAFT_API_KEY:-}" ] && headers+=(-H "X-API-Key: ${VIBECRAFT_API_KEY}")
if resp="$(curl -sf --max-time 10 -X POST -H 'Content-Type: application/json' -d '{"full": true}' "${headers[@]}" "$base_url/api/reindex")"; then
    echo "[$(date -Is)] Full rebuild accodato al server: $resp"
    exit 0
fi

echo "[$(date -Is)] Server non raggiungibile ($base_url): fallback a index.py (full rebuild)..."
if uv run python index.py --project "$project_id"; then
    echo "[$(date -Is)] Full rebuild completato: indice riallineato."
    # Il server ricarica gli artefatti in memoria alla prima richiesta (maybe_reload_graph).
    exit 0
else
    echo "[$(date -Is)] ERRORE: full rebuild fallito."
    exit 1
fi
