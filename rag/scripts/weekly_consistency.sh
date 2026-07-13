#!/usr/bin/env bash
# Batch SETTIMANALE profondo: guardrail contro la deriva dell'incrementale (variante POSIX
# dello script PowerShell). Da schedulare via cron. Vedi weekly_consistency.ps1 per i
# dettagli. Il check quotidiano economico e' scripts/nightly_consistency.sh.
#
# Uso:   scripts/weekly_consistency.sh
# Exit:  0 se coerente o rebuild riuscito; 1 se il rebuild e' fallito.
set -euo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

echo "[$(date -Is)] Check di coerenza del grafo (incrementale vs full rebuild)..."

# index.py --check-graph esce 1 se il grafo incrementale DIVERGE dal full rebuild.
if uv run python index.py --check-graph; then
    echo "[$(date -Is)] Grafo coerente: nessun rebuild necessario."
    exit 0
fi

echo "[$(date -Is)] Drift rilevato: avvio full rebuild..."
if uv run python index.py; then
    echo "[$(date -Is)] Full rebuild completato: indice riallineato."
    # Il server ricarica gli artefatti in memoria alla prima richiesta (maybe_reload_graph).
    exit 0
else
    echo "[$(date -Is)] ERRORE: full rebuild fallito."
    exit 1
fi
