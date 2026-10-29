# Evidenze pesanti rimosse dal tip (R6)

I file sotto sono stati tolti dal tip di `main` il 2026-10-28 (R6) per alleggerire
checkout e clone sparse. Restano nella history git: recuperali con

```bash
git checkout 66954f9 -- archive/eval-results/<path>
# oppure, per un solo blob:
git show 66954f9:archive/eval-results/<path> > <path>
```

`66954f9` è il tip di `main` prima di R6 (merge del PR quick-wins #25). Per un clone
senza scaricare queste evidenze resta valida la ricetta `sparse-checkout` in
[README.md](../../README.md).

- File rimossi: **728**
- Byte rimossi: **107.6 MiB**
- Inventario macchina: [`HEAVY_REMOVED.json`](HEAVY_REMOVED.json)

Restano i resoconti `.md`, CSV, script e patch citati dagli ADR. I blob `.json` /
`.jsonl` / `.log` di evidence non sono più nel working tree di default.
