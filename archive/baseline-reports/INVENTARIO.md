# Inventario — report tolti dalla baseline

Spostati il 31 ottobre 2026 da `templates/docs/` a questa cartella. Non sono norme.

- `fe1-canvas-review.md` — review di archiviazione della change fe1, senza frontmatter. Letta per intero: confronta un canvas con il codice e dichiara fedeltà bassa.
- `superpowers/plans/` — diario di sviluppo del tool. Dai titoli e dai primi capoversi: report di task, review e piani per agenti. Non è una rilettura riga per riga di ogni file.

Il seme dei progetti nuovi non li copia più (`ProjectRegistry` copia `templates/docs/`, il Dockerfile copia la stessa cartella in `/app/docs`). `archive/` è nel `.dockerignore` e non è un `COPY`. Un progetto già creato non viene modificato: se quei file sono già nel suo `docs/`, il prossimo indice li legge ancora. L'indicizzatore non ha una lista di cartelle da escludere.

I casi del golden set che usano `fe1-canvas-review.md` come distrattore restano nel file. Su un indice del solo seme nuovo il distrattore non c'è: non è un cambio di ranking.
