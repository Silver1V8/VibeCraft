# Inventario — report tolti dalla baseline

Spostati il 31 ottobre 2026 da `templates/docs/` a questa cartella. Non sono norme.

- `superpowers/plans/` — diario di sviluppo del tool. Dai titoli e dai primi capoversi: report di task, review e piani per agenti. Non è una rilettura riga per riga di ogni file.

`fe1-canvas-review.md` era stato spostato qui insieme al diario. Il 1° novembre 2026 è tornato in `templates/docs/03_changes_historical/`: è il distrattore dei casi avversariali del golden set (`eval/golden_set.yaml`, `eval/golden_attribution.yaml`), e senza di lui quei casi venivano misurati contro il nulla. Non è una norma: pesa 0.30, senza frontmatter.

Il seme dei progetti nuovi non copia più il diario (`ProjectRegistry` copia `templates/docs/`, il Dockerfile copia la stessa cartella in `/app/docs`). `archive/` è nel `.dockerignore` e non è un `COPY`. Un progetto già creato non viene modificato: se il diario è già nel suo `docs/`, il prossimo indice lo legge ancora. L'indicizzatore non ha una lista di cartelle da escludere.
