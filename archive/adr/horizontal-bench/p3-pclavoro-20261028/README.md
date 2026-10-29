# P3 — misura HTTP multi-reader su PcLavoro (28 ottobre 2026)

Misura live della matrice k=1/4/8 e del confronto uno-vs-due reader con
`qwen3.5:9b`, dopo P0–P2 software già in `main`. Harness:
`scripts/bench.py --concurrency-bench` (stream NDJSON, cache-off).

## Ambiente

| Voce | Valore |
|------|--------|
| Host | PcLavoro (Windows 11, 32 GiB RAM, 8 logici) |
| Commit client | `31f4ef9` tipico al rebase pre-PR (vedi metadata JSON) |
| Qdrant | dedicato `127.0.0.1:16333` (docker `qdrant/qdrant:v1.19.0`, storage lab) |
| Ollama | **host condiviso** `127.0.0.1:11434` (0.40.5) — non un secondo daemon `:21434` (stessa GPU/Vulkan) |
| Modello | `qwen3.5:9b` digest `6488c96f…` |
| Indice | progetto lab `legacy`, immutable, 1 doc / 5 chunk (prestiti biblioteca) |
| Reader | `:18001` + `:18002`; due-reader via proxy RR lab `:18010` |
| Cache | `VIBECRAFT_ASK_CACHE_SIZE=0` |
| N per k | **8** (target ADR 30 non raggiunto: ~45–50 s/req → ~2 h solo per stream×2 scenari) |

`nvidia-smi` non utilizzabile in sessione (NVML/driver not loaded); accelerazione
Ollama non riattribuita a CPU. Durante parte della sessione era attivo anche un
bench `--real-delta` R9 sullo stesso host (stesso Ollama).

## Tabella (stream, cache-off)

Percentili solo sui successi. Errori a k>1 = HTTP di saturazione coda inferenza
applicativa («Coda inferenza piena…», default `VIBECRAFT_GENERATION_MAX_ACTIVE=2`)
mentre Ollama resta a un solo slot qwen35.

| scenario | k | n | ok | err | TTFT p50 (ms) | total p50 (ms) | thrput ok/s | cancel |
|----------|---|---|----|-----|---------------|----------------|-------------|--------|
| 1 reader `:18002` | 1 | 8 | 8 | 0 | 45120 | 47980 | 0.0208 | 2/2 |
| 1 reader | 4 | 8 | 4 | 4 | 95750 | 98178 | 0.0215 | 2/2 |
| 1 reader | 8 | 8 | 2 | 6 | 61152 | 63526 | 0.0234 | 2/2 |
| 2 reader RR `:18010` | 1 | 8 | 8 | 0 | 47298 | 49894 | 0.0203 | 2/2 |
| 2 reader RR | 4 | 8 | 6 | 2 | 119715 | 122362 | 0.0246 | 2/2 |
| 2 reader RR | 8 | 8 | 4 | 4 | 101889 | 104219 | 0.0238 | 2/2 |

RSS API picco ~2,5 GiB per reader campionato; Ollama ~7–8 GiB quando il PID engine
era disponibile. Raw + summary in `one-reader-stream-cache-off/` e
`two-reader-rr-stream-cache-off/`.

## Conclusioni oneste

1. **Throughput LLM-bound piatto (~0,02 ok/s)** a k=1/4/8 e tra 1 e 2 reader:
   qwen35 serializza l'inferenza (confermato di nuovo in
   `ollama-overlap-20261028.json` su Ollama 0.40.5).
2. **Alzare k non scala**: aumenta TTFT (coda) e la frazione di 429 «coda inferenza
   piena»; non il completamenti/s utili.
3. **Due reader locali funzionano** (entrambi health OK, proxy RR, cancel stream OK)
   ma **non moltiplicano** il throughput verso un solo Ollama qwen35.
4. **P3 non chiude** la griglia ADR completa (N=30, cache-on, JSON, baseline ea0cf91
   vs candidato): questa run pubblica un envelope misurato ridotto, non uno SLA.

Prove Ollama precedenti (0.34.4): [preflight-20260928](../preflight-20260928/README.md).
