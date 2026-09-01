#!/usr/bin/env bash
# Avvia il server RAG. Gemello POSIX di run_server.ps1 (Linux, macOS, WSL).
#
# NON duplica il caricamento di .env.local che il .ps1 fa a mano: core/config.py lo carica
# gia' da se' con python-dotenv, PRIMA che qualunque modulo legga os.environ, proprio perche'
# funzioni comunque si avvii il processo (script, IDE, python diretto). Riprodurre qui quel
# ciclo significherebbe copiare complessita' morta.
#
# Uso:  scripts/run_server.sh
# Env:  vedi .env.example (tutte opzionali; i default bindano su 127.0.0.1:8000).
set -euo pipefail

RAG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAG_DIR"

# Forza stdout/stderr UTF-8: i messaggi di log contengono accenti ed emoji, e sotto una
# locale POSIX/C (container minimali, cron) l'encoding di default le farebbe fallire.
export PYTHONUTF8=1

exec uv run python server.py
