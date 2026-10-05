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

project_id="${VIBECRAFT_PROJECT_ID:-legacy}"
project_headers=(-H "X-VibeCraft-Project: $project_id")
[ -n "${VIBECRAFT_API_KEY:-}" ] && project_headers+=(-H "X-API-Key: ${VIBECRAFT_API_KEY}")

# Alert su fallimento (check fallito E rimedio fallito): appende una riga JSON a
# database/alerts.jsonl (letta da GET /api/health) e, se VIBECRAFT_ALERT_WEBHOOK e'
# impostata, POSTa lo stesso JSON a quell'URL. Entrambi best-effort.
send_alert() {
    json="$(SCRIPT_ERR="$1" uv run python -c "import json,os,datetime; print(json.dumps({'timestamp': datetime.datetime.now().astimezone().isoformat(), 'script': 'nightly_consistency.sh', 'error': os.environ['SCRIPT_ERR']}, ensure_ascii=False))")" || return 0
    SCRIPT_ERR="$1" uv run python -c "import os; from core.projects import resolve_registered_project; from core.eval_gate import record_alert; p=resolve_registered_project(os.environ.get('VIBECRAFT_PROJECT_ID')); record_alert('critical', os.environ['SCRIPT_ERR'], path=p.database_dir/'alerts.jsonl')" >/dev/null 2>&1 || true
    if [ -n "${VIBECRAFT_ALERT_WEBHOOK:-}" ]; then
        curl -sf --max-time 10 -X POST -H 'Content-Type: application/json' -d "$json" "$VIBECRAFT_ALERT_WEBHOOK" >/dev/null || true
    fi
}

# Check di QUALITA' del retrieval (Epic 5.2), opportunistico: se il server e' raggiungibile
# (modello gia' caricato, nessun embedding nello script), valuta la recall sul golden set e,
# via --check-regression, registra un alert critico in database/alerts.jsonl se e' calata sotto
# la media mobile o sotto soglia. Non blocca il batch: e' un segnale, non un rimedio.
#
# NIENTE --assert-min: la soglia e la k sono quelle dell'eval-gate, che eval.run legge da
# rag_config.yaml (A2b). Qui c'era un `--assert-min 0.90` scritto a mano, e senza `--k` il
# confronto cadeva su recall@10 — satura a 1.000 — quindi questo check non poteva fallire.
quality_url="${VIBECRAFT_SERVER_URL:-http://127.0.0.1:8000}"
if curl -sf --max-time 5 "${project_headers[@]}" "$quality_url/api/health" >/dev/null 2>&1; then
    echo "[$(date -Is)] Check di qualita' del retrieval (eval sul golden set)..."
    if uv run python -m eval.run --project "$project_id" --url "$quality_url" --check-regression >/dev/null 2>&1; then
        echo "[$(date -Is)] Qualita' del retrieval OK."
    else
        echo "[$(date -Is)] Qualita' del retrieval: regressione o sotto soglia (alert registrato dall'eval)."
    fi

    # Suite STRUTTURALE/MULTIHOP (A4). Era l'unica suite senza gate: girava a mano, quindi la
    # classe di domande piu' preziosa per un grafo di governance poteva regredire in silenzio.
    # Soglia e regola stanno in `eval_multihop` di rag_config.yaml; l'alert lo scrive lo script.
    # Costo: 14 chiamate a /api/retrieve e /api/graph/query, nessun LLM.
    echo "[$(date -Is)] Check strutturale/multihop (grafo + retrieval)..."
    if uv run python -m eval.run_multihop --project "$project_id" --url "$quality_url" >/dev/null 2>&1; then
        echo "[$(date -Is)] Suite strutturale/multihop OK."
    else
        echo "[$(date -Is)] Suite strutturale/multihop sotto soglia (alert registrato)."
    fi

    # I DUE CONTRATTI CHE PRETENDONO UN LLM VERO (R10, R11). In CI non c'e' un modello:
    # l'astensione e' esercitata solo contro un provider finto e la soglia di certezza su
    # num_ctx era stata osservata a mano una volta sola. Girano qui perche' questo e' il
    # canale che ha Ollama acceso ed e' gia' collegato agli alert. Costo: 2 chiamate a
    # /ask, di cui una si ferma PRIMA del modello (e' il punto del secondo check).

    # R10 — l'astensione e' un impegno del PROMPT, non una garanzia del modello: una
    # domanda fuori corpus deve tornare status "abstained" (marcatore [ASTENSIONE] scritto
    # dal modello e letto da ask_rag), non "success" con le fonti elencate.
    echo "[$(date -Is)] Contratto di astensione (domanda fuori corpus)..."
    ask_status="$(curl -s --max-time 600 -X POST "${project_headers[@]}" -H 'Content-Type: application/json' \
        -d '{"question":"qual e la ricetta tradizionale della carbonara e quanti grammi di guanciale servono per quattro persone"}' \
        "$quality_url/ask" 2>/dev/null | uv run python -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)"
    if [ "$ask_status" = "abstained" ]; then
        echo "[$(date -Is)] Astensione OK (status abstained)."
    else
        echo "[$(date -Is)] ASTENSIONE NON RISPETTATA: status '$ask_status' invece di 'abstained'."
        send_alert "il modello non ha rispettato [REGOLA-ASTENSIONE] su una domanda fuori corpus (status: '$ask_status')"
    fi

    # R11 — soglia di CERTEZZA su num_ctx (A1): a top_k=20 il prompt supera la finestra e
    # /ask DEVE rispondere 502 col messaggio dichiarato, mai un 200 "success" su un prompt
    # che Ollama troncherebbe dall'alto in silenzio. Misurato il 2026-09-05 su questa
    # domanda: ~17.424 token stimati contro num_ctx=16384 (106,3%).
    # Un 200 NON e' un falso allarme benigno: o il guardrail non scatta piu', o il contesto
    # si e' ridotto sotto la finestra — in entrambi i casi questo check non sta piu'
    # esercitando il contratto, ed e' proprio quello che va detto invece di restare verde.
    echo "[$(date -Is)] Soglia di certezza su num_ctx (top_k=20)..."
    ctx_body="$(mktemp)"
    ctx_code="$(curl -s -o "$ctx_body" -w '%{http_code}' --max-time 600 -X POST "${project_headers[@]}" -H 'Content-Type: application/json' \
        -d '{"question":"quali vincoli valgono sui dati personali fra log, test e chiamate a LLM esterni?","top_k":20}' \
        "$quality_url/ask" 2>/dev/null)"
    if [ "$ctx_code" = "502" ] && grep -q 'FINESTRA DI CONTESTO SUPERATA' "$ctx_body"; then
        echo "[$(date -Is)] Soglia di certezza OK (502 col messaggio dichiarato)."
    elif [ "$ctx_code" = "502" ]; then
        echo "[$(date -Is)] 502 ma con un messaggio diverso da quello dichiarato."
        send_alert "il 502 oltre la finestra non porta piu' il messaggio [FINESTRA DI CONTESTO SUPERATA]"
    else
        echo "[$(date -Is)] top_k=20 non supera piu' la finestra (HTTP $ctx_code): contratto NON esercitato."
        send_alert "la soglia di certezza su num_ctx non e' piu' esercitata: top_k=20 ha risposto $ctx_code invece di 502"
    fi
    rm -f "$ctx_body"
fi

echo "[$(date -Is)] Check di integrita' dell'indice (economico, zero embedding)..."

# stdout = report JSON (i messaggi umani vanno su stderr), exit 1 se ci sono problemi.
report="$(uv run python index.py --project "$project_id" --check-integrity 2>/dev/null)"
check_exit=$?

# Divergenza docs/ su disco <-> docs/ committato. NON e' un "problema" del report (non
# entra in `ok`: un reindex non la ripara, quindi non deve innescare remediation), ma va
# stampata SEMPRE - anche a integrita' OK, che e' il caso in cui altrimenti resterebbe
# invisibile. I file di docs/ sono skip-worktree: git status non la mostra.
docs_git_line="$(printf '%s' "$report" | uv run python -c "
import json, sys
d = json.load(sys.stdin).get('docs_git') or {}
if d.get('state') == 'diverging':
    n = d.get('diverging') or []
    print(f\"{len(n)}/{d.get('tracked', '?')} file: \" + ', '.join(n[:5]) + (' ...' if len(n) > 5 else ''))
" 2>/dev/null)"
if [ -n "$docs_git_line" ]; then
    echo "[$(date -Is)] ATTENZIONE: docs/ su disco DIVERGE dal committato - $docs_git_line"
    echo "[$(date -Is)] Il RAG indicizza la copia su disco: un reindex NON riallinea nulla."
    send_alert "docs/ su disco diverge dal committato ($docs_git_line)"
fi

if [ "$check_exit" -eq 0 ]; then
    echo "[$(date -Is)] Integrita' OK: nessuna azione necessaria."
    exit 0
fi

echo "$report"

# Estrae i flag booleani dal report JSON senza dipendere da jq.
flag() {
    printf '%s' "$report" | uv run python -c "import json,sys; print(1 if json.load(sys.stdin).get('$1') else 0)"
}

if [ "$(flag qdrant_unreachable)" = "1" ]; then
    # Qdrant giu': niente scritture al buio, ne' rebuild ne' incrementale (la lineage
    # non e' verificabile senza un conteggio riuscito). Solo alert, si riprova la notte dopo.
    echo "[$(date -Is)] Qdrant non raggiungibile: nessuna azione (nessun rebuild, nessun incrementale)."
    send_alert "Qdrant irraggiungibile durante il check notturno"
    exit 1
fi

if [ "$(flag artifacts_corrupted)" = "1" ] || [ "$(flag qdrant_mismatch)" = "1" ]; then
    # Artefatti corrotti/misti o Qdrant disallineato: un incrementale non basta, serve un
    # full rebuild. Preferisci il server (un solo scrittore: la coda del ReindexManager),
    # fallback alla CLI se il server e' spento.
    echo "[$(date -Is)] Artefatti corrotti o Qdrant disallineato: full rebuild..."
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
        exit 0
    fi
    echo "[$(date -Is)] ERRORE: full rebuild fallito."
    send_alert "check di integrita' fallito e full rebuild fallito"
    exit 1
fi

if [ "$(flag stale)" = "1" ]; then
    # Solo sorgenti cambiate: basta un reindex incrementale. Preferisci il server (un solo
    # scrittore: la coda del ReindexManager), fallback alla CLI se il server e' spento.
    base_url="${VIBECRAFT_SERVER_URL:-http://127.0.0.1:8000}"
    headers=("${project_headers[@]}")
    [ -n "${VIBECRAFT_API_KEY:-}" ] && headers+=(-H "X-API-Key: ${VIBECRAFT_API_KEY}")
    if resp="$(curl -sf --max-time 10 -X POST "${headers[@]}" "$base_url/api/reindex")"; then
        echo "[$(date -Is)] Indice stale: reindex incrementale accodato al server: $resp"
        exit 0
    fi
    echo "[$(date -Is)] Server non raggiungibile ($base_url): fallback a index.py --incremental..."
    if uv run python index.py --project "$project_id" --incremental; then
        echo "[$(date -Is)] Reindex incrementale completato."
        exit 0
    fi
    echo "[$(date -Is)] ERRORE: reindex incrementale fallito."
    send_alert "indice stale e reindex incrementale fallito"
    exit 1
fi

echo "[$(date -Is)] ERRORE: problemi di integrita' non riconducibili a stale/corruzione (vedi report)."
send_alert "problemi di integrita' non riconducibili a stale/corruzione"
exit 1
