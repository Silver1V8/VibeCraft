#!/usr/bin/env bash
# Rigenera i CSS Tailwind statici di Console/Pipeline (static/tailwind.css) e della Guida
# (static/tailwind-infografica.css). Sostituiscono il runtime Tailwind, che generava il CSS
# nel browser a ogni caricamento di ogni pagina. Da rilanciare quando si aggiungono classi
# Tailwind nuove ai file elencati in `content` delle configurazioni in static/tailwind/:
# senza, la classe nuova non ha regole e l'elemento resta senza stile.
# Versione fissata: la stessa del runtime che sostituisce (3.4.17).
set -euo pipefail
cd "$(dirname "$0")/.."
TAILWIND="${TAILWIND:-npx --yes tailwindcss@3.4.17}"
$TAILWIND -c static/tailwind/tailwind.config.cjs -i static/tailwind/input.css -o static/tailwind.css --minify
$TAILWIND -c static/tailwind/tailwind-infografica.config.cjs -i static/tailwind/input.css -o static/tailwind-infografica.css --minify
