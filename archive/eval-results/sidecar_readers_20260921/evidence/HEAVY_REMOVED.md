# Evidence pesanti rimosse — `sidecar_readers_20260921`

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
| `sidecar_readers_20260921/evidence/full-process.jsonl` | 2498.2 |
| `sidecar_readers_20260921/evidence/io-process.jsonl` | 445.1 |
| `sidecar_readers_20260921/evidence/historical-candidates.json` | 119.2 |
| `sidecar_readers_20260921/evidence/candidates-process.jsonl` | 85.8 |
| `sidecar_readers_20260921/evidence/resources.json` | 38.6 |
| `sidecar_readers_20260921/evidence/full-process.stderr.log` | 15.3 |
| `sidecar_readers_20260921/evidence/disk-allocation.json` | 14.8 |
| `sidecar_readers_20260921/evidence/conversion-process.jsonl` | 10.8 |
| `sidecar_readers_20260921/evidence/full-eager-3.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-npy-3.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-eager-4.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-lazy-0.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-npy-1.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-npy-4.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-lazy-2.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-lazy-3.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-eager-0.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-eager-1.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-eager-2.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-lazy-1.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-npy-2.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-lazy-4.json` | 7.4 |
| `sidecar_readers_20260921/evidence/full-npy-0.json` | 7.4 |
| `sidecar_readers_20260921/evidence/comparison.json` | 5.1 |
| `sidecar_readers_20260921/evidence/pm-preflight.json` | 4.8 |
| `sidecar_readers_20260921/evidence/io-eager-4.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-eager-0.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-eager-3.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-eager-1.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-eager-2.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-npy-0.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-npy-2.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-lazy-0.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-npy-3.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-lazy-1.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-lazy-2.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-lazy-4.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-npy-1.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-npy-4.json` | 4.3 |
| `sidecar_readers_20260921/evidence/io-lazy-3.json` | 4.3 |
| `sidecar_readers_20260921/evidence/post-run-integrity.json` | 2.1 |
| `sidecar_readers_20260921/evidence/historical-parity.json` | 1.4 |
| `sidecar_readers_20260921/evidence/candidates-process.json` | 1.1 |
| `sidecar_readers_20260921/evidence/full-process.json` | 1.1 |
| `sidecar_readers_20260921/evidence/conversion-process.json` | 1.1 |
| `sidecar_readers_20260921/evidence/io-process.json` | 1.1 |
| `sidecar_readers_20260921/evidence/historical-hashes.json` | 0.9 |
| `sidecar_readers_20260921/evidence/f3-parity.json` | 0.8 |
| `sidecar_readers_20260921/evidence/progress.json` | 0.5 |
| `sidecar_readers_20260921/evidence/candidates-process.stderr.log` | 0.4 |
| `sidecar_readers_20260921/evidence/synthetic-selfcheck.json` | 0.3 |
| `sidecar_readers_20260921/evidence/linux-synthetic-selfcheck.json` | 0.3 |
| `sidecar_readers_20260921/evidence/conversion.json` | 0.1 |
| `sidecar_readers_20260921/evidence/conversion-f3.json` | 0.1 |
| `sidecar_readers_20260921/evidence/candidate-preparation.json` | 0.0 |
| `sidecar_readers_20260921/evidence/candidates-process.stdout.log` | 0.0 |
| `sidecar_readers_20260921/evidence/conversion-process.stderr.log` | 0.0 |
| `sidecar_readers_20260921/evidence/conversion-process.stdout.log` | 0.0 |
| `sidecar_readers_20260921/evidence/full-process.stdout.log` | 0.0 |
| `sidecar_readers_20260921/evidence/io-process.stderr.log` | 0.0 |
| `sidecar_readers_20260921/evidence/io-process.stdout.log` | 0.0 |
