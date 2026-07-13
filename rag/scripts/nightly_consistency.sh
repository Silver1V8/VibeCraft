#!/usr/bin/env bash
# Batch notturno ECONOMICO: check di integrità dell'indice senza embedding (secondi).
# Variante POSIX di nightly_consistency.ps1 — vedi quello per i dettagli. Da schedulare
# via cron. Il confronto profondo (ri-embedda tutto) è nel batch SETTIMANALE:
# scripts/weekly_consistency.sh.
#
# Env opzionali: VIBECRAFT_SERVER_URL (default http://127.0.0.1:8000), VIBECRAFT_API_KEY.
#
# Uso:  scripts/nightly_consistency.sh
# Exit: 0 se ok / riallineato / reindex accodato; 1 su errore.
set -uo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

echo "[$(date -Is)] Check di integrita' dell'indice (economico, zero embedding)..."

# stdout = report JSON (i messaggi umani vanno su stderr), exit 1 se ci sono problemi.
report="$(uv run python index.py --check-integrity 2>/dev/null)"
check_exit=$?

if [ "$check_exit" -eq 0 ]; then
    echo "[$(date -Is)] Integrita' OK: nessuna azione necessaria."
    exit 0
fi

echo "$report"

# Estrae i flag booleani dal report JSON senza dipendere da jq.
flag() {
    printf '%s' "$report" | uv run python -c "import json,sys; print(1 if json.load(sys.stdin).get('$1') else 0)"
}

if [ "$(flag artifacts_corrupted)" = "1" ] || [ "$(flag qdrant_mismatch)" = "1" ]; then
    # Artefatti corrotti/misti o Qdrant disallineato: un incrementale non basta.
    echo "[$(date -Is)] Artefatti corrotti o Qdrant disallineato: full rebuild..."
    if uv run python index.py; then
        echo "[$(date -Is)] Full rebuild completato: indice riallineato."
        exit 0
    fi
    echo "[$(date -Is)] ERRORE: full rebuild fallito."
    exit 1
fi

if [ "$(flag stale)" = "1" ]; then
    # Solo sorgenti cambiate: basta un reindex incrementale. Preferisci il server (un solo
    # scrittore: la coda del ReindexManager), fallback alla CLI se il server e' spento.
    base_url="${VIBECRAFT_SERVER_URL:-http://127.0.0.1:8000}"
    headers=()
    [ -n "${VIBECRAFT_API_KEY:-}" ] && headers=(-H "X-API-Key: ${VIBECRAFT_API_KEY}")
    if resp="$(curl -sf --max-time 10 -X POST "${headers[@]}" "$base_url/api/reindex")"; then
        echo "[$(date -Is)] Indice stale: reindex incrementale accodato al server: $resp"
        exit 0
    fi
    echo "[$(date -Is)] Server non raggiungibile ($base_url): fallback a index.py --incremental..."
    if uv run python index.py --incremental; then
        echo "[$(date -Is)] Reindex incrementale completato."
        exit 0
    fi
    echo "[$(date -Is)] ERRORE: reindex incrementale fallito."
    exit 1
fi

echo "[$(date -Is)] ERRORE: problemi di integrita' non riconducibili a stale/corruzione (vedi report)."
exit 1
