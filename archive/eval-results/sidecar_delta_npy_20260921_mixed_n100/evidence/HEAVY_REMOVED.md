# Evidence pesanti rimosse — `sidecar_delta_npy_20260921_mixed_n100`

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
| `sidecar_delta_npy_20260921_mixed_n100/evidence/process.jsonl` | 2578.0 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/result.json` | 451.1 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/process.stderr.log` | 344.8 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/resources.json` | 17.5 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/bootstrap.json` | 2.4 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/process.json` | 1.7 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/prepared-environment.json` | 0.5 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/input-verification.json` | 0.3 |
| `sidecar_delta_npy_20260921_mixed_n100/evidence/process.stdout.log` | 0.0 |
