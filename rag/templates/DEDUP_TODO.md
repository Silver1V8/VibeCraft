# TODO — Deduplicazione template (tema Matrix ↔ Classico)

**Stato:** rimandato di proposito (refactor a rischio alto, priorità più bassa del resto).
I template `*.html` / `*_classic.html` sono ~95% identici nel markup e nel JS, ma **non**
sono banali copie: hanno divergenze funzionali/visive reali che vanno preservate.

## Divergenze reali riscontrate (non solo cosmetiche)
- **Matrix-only:** canvas `#matrix-rain` con animazione (setInterval), overlay `.scanlines`,
  `glow-text`, config colori Tailwind "matrix" (verde), font monospace.
- **Classic-only:** palette slate/blu, font Inter, niente rain/scanlines.
- **JS divergente** (in `graph_analysis*`): `COMMUNITY_COLORS`, `TYPE_COLORS` e i colori dei
  tratti sul canvas (ripple/mappa) differiscono tra i due temi.
- **Routing:** il server sceglie il file via `_themed_template(request, matrix, classic)` in
  base al cookie `ui_theme`; un template unico cambierebbe questo contratto.

## Perché è stato rimandato
`pipeline.html` è ~1200 righe di JS intricato (5 step, stepper, streaming SSE, agent SDK,
dry-run, validate, agent-context). Una dedup fatta male introduce regressioni silenziose su
tutto il flusso e su 3 pagine × 2 temi. Le priorità A–C+E (chunking, pipeline async, hardening,
split core/api, uv) erano più alte e sono state completate; questa merita un passaggio dedicato
con retest UI completo.

## Piano concreto (nucleo corretto, da eseguire in un passaggio dedicato)
1. **Un template per pagina** + `<html data-theme="matrix|classic">` impostato dal server dal cookie.
   Cambiare `serve_*` per servire UN file e iniettare `data-theme` (niente più coppie di file).
2. **Colori come CSS variables** su `:root[data-theme="matrix"]` / `:root[data-theme="classic"]`
   (bg, testo, accento, bordo, ecc.). Sostituire i colori hardcoded con `var(--...)`.
   Nota: le pagine pipeline/dashboard usano **Tailwind via CDN con config JS** — o si passa a CSS
   vars pure (consigliato per la dedup), o si tiene una sola config Tailwind e si spostano solo le
   differenze cromatiche in vars.
3. **Elementi solo-Matrix** (matrix-rain, scanlines) resi condizionali: presenti nel DOM ma
   attivati/nascosti in base a `data-theme` (JS legge `document.documentElement.dataset.theme`).
4. **Costanti JS colore** (`COMMUNITY_COLORS`, `TYPE_COLORS`, tratti canvas) scelte a runtime dal tema.
5. **Retest obbligatorio** (Playwright) su entrambi i temi per: pipeline (5 step + streaming),
   dashboard, /analysis (mappa + ripple + query). Verificare nessuna regressione silenziosa.

Fino ad allora: mantenere le coppie di file **in sync manualmente** (ogni modifica va applicata a
entrambe le varianti).
