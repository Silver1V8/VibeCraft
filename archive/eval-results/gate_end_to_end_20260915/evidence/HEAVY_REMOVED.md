# Evidence pesanti rimosse — `gate_end_to_end_20260915`

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
| `gate_end_to_end_20260915/evidence/validations/val-1c4dc25feb074c34a2477e78ff934349.json` | 38.9 |
| `gate_end_to_end_20260915/evidence/validations/val-f3ea0d38b2d0421c895cbb87c08d23b2.json` | 38.6 |
| `gate_end_to_end_20260915/evidence/validations/val-e355c024c65147fba5f20f60eb2b68a9.json` | 38.3 |
| `gate_end_to_end_20260915/evidence/events.jsonl` | 7.8 |
| `gate_end_to_end_20260915/evidence/modify-1.request.json` | 6.8 |
| `gate_end_to_end_20260915/evidence/measurements.json` | 3.6 |
| `gate_end_to_end_20260915/evidence/frictions.jsonl` | 1.1 |
| `gate_end_to_end_20260915/evidence/timings.jsonl` | 0.7 |
| `gate_end_to_end_20260915/evidence/run-2.request.json` | 0.3 |
| `gate_end_to_end_20260915/evidence/run-1.request.json` | 0.2 |
| `gate_end_to_end_20260915/evidence/validate-1.request.json` | 0.1 |
| `gate_end_to_end_20260915/evidence/validate-2.request.json` | 0.1 |
| `gate_end_to_end_20260915/evidence/validate-3.request.json` | 0.1 |
