# F6 documenti: controllo PM da JSON

F3 = sidecar_delta_post_20260921_docs_nN; NPY = sidecar_delta_npy_20260921_docs_nN. Cinque ripetizioni per cella; confronto eseguito con compare_pair, inclusi corpus, digest, parametri, conteggi e sampler.

| N | k | F3 T mediana s | NPY T mediana s | F3 query/vuote/errori | NPY query/vuote/errori |
|---:|---:|---:|---:|---:|---:|
| 10 | 0 | 0.017532 | 0.022172 | 10/0/0 | 9/0/0 |
| 10 | 1 | 3.421329 | 3.807497 | 16/0/0 | 20/0/0 |
| 10 | 10 | 4.988573 | 8.844668 | 36/29/0 | 60/10/0 |
| 30 | 0 | 0.035424 | 0.020065 | 10/0/0 | 9/0/0 |
| 30 | 1 | 3.433572 | 4.094321 | 20/0/0 | 19/0/0 |
| 30 | 10 | 5.143029 | 9.179232 | 36/0/0 | 60/0/0 |
| 100 | 0 | 0.063124 | 0.042232 | 10/0/0 | 10/0/0 |
| 100 | 1 | 3.768219 | 4.943861 | 20/0/0 | 26/0/0 |
| 100 | 10 | 5.636499 | 9.650519 | 38/0/0 | 70/0/0 |
| 100 | 100 | 15.934103 | 58.098696 | 145/130/0 | 493/5/0 |

Le risposte vuote sono degrado osservato, anche se HTTP 200. Le finestre hanno durate diverse: questi conteggi non sono tassi normalizzati. Nessuna curva globale prodotta prima delle nove famiglie complete.
