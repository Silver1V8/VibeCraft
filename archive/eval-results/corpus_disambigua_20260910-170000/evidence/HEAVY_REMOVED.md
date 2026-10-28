# Evidence pesanti rimosse — `corpus_disambigua_20260910-170000`

I file sotto sono stati tolti dal tip di `main` il 2026-10-28 (R6) per
alleggerire checkout e clone sparse. Restano nella history git: recuperali con

```bash
git checkout 66954f9 -- archive/eval-results/<path>
# oppure, per un solo blob:
git show 66954f9:archive/eval-results/<path> > <path>
```

`66954f9` e' il tip di `main` prima di R6 (merge del PR quick-wins #25). Per un
clone senza scaricare queste evidenze resta valida la ricetta `sparse-checkout`
in [README.md](../../../README.md).

| Path relativo a `archive/eval-results/` | KiB |
|---|---:|
| `corpus_disambigua_20260910-170000/evidence/out/comp_pdf_S2.json` | 234.7 |
| `corpus_disambigua_20260910-170000/evidence/out/comp_pdf_disamb.json` | 233.5 |
| `corpus_disambigua_20260910-170000/evidence/out/comp_pdf_v2.json` | 232.2 |
| `corpus_disambigua_20260910-170000/evidence/out/gen_pdf_v2.json` | 25.7 |
| `corpus_disambigua_20260910-170000/evidence/out/gen_pdf_disamb.json` | 24.5 |
| `corpus_disambigua_20260910-170000/evidence/out/gen_pdf_S2.json` | 22.3 |
| `corpus_disambigua_20260910-170000/evidence/out/decisivo_scala.json` | 7.9 |
| `corpus_disambigua_20260910-170000/evidence/EVIDENCE_MANIFEST.json` | 6.7 |
| `corpus_disambigua_20260910-170000/evidence/inventario_sha256.json` | 6.4 |
| `corpus_disambigua_20260910-170000/evidence/out/build_disambigua.json` | 0.7 |
