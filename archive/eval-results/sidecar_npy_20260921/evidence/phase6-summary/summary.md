# Sidecar delta summary

Prepared from completed real runs.

T is `job.snapshot_ready_duration_seconds`; HTTP elapsed stays separate in CSV. No p95, capacity threshold, or crossover claim is produced. Corpus is synthetic and OS cache is uncontrolled.

| mode | N | k | repeats | median T s | min–max T s | paired ΔT s (min–max) | source |
|---|---:|---:|---:|---:|---:|---:|---|

| docs | 10 | 0 | 5 | 0.022 | 0.012–0.024 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 1 | 5 | 3.807 | 3.746–3.909 | 3.785 (3.724–3.897) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 10 | 5 | 8.845 | 8.281–8.975 | 8.821 (8.258–8.955) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n10\evidence\result.json` |

| docs | 30 | 0 | 5 | 0.020 | 0.019–0.040 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 1 | 5 | 4.094 | 3.931–4.328 | 4.054 (3.911–4.308) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 10 | 5 | 9.179 | 8.522–9.557 | 9.160 (8.502–9.518) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n30\evidence\result.json` |

| docs | 100 | 0 | 5 | 0.042 | 0.038–0.062 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 1 | 5 | 4.944 | 4.721–5.023 | 4.882 (4.682–4.962) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 10 | 5 | 9.651 | 8.978–10.284 | 9.590 (8.916–10.242) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 100 | 5 | 58.099 | 54.220–61.506 | 58.060 (54.178–61.467) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_docs_n100\evidence\result.json` |

| code | 10 | 0 | 5 | 0.020 | 0.018–0.029 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n10\evidence\result.json` |

| code | 10 | 1 | 5 | 3.657 | 3.538–3.714 | 3.628 (3.520–3.688) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n10\evidence\result.json` |

| code | 10 | 10 | 5 | 5.868 | 5.851–6.132 | 5.838 (5.831–6.107) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n10\evidence\result.json` |

| code | 30 | 0 | 5 | 0.034 | 0.018–0.041 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n30\evidence\result.json` |

| code | 30 | 1 | 5 | 3.664 | 3.594–3.798 | 3.641 (3.555–3.764) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n30\evidence\result.json` |

| code | 30 | 10 | 5 | 5.892 | 5.769–6.593 | 5.853 (5.747–6.552) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n30\evidence\result.json` |

| code | 100 | 0 | 5 | 0.055 | 0.040–0.066 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n100\evidence\result.json` |

| code | 100 | 1 | 5 | 3.800 | 3.555–3.966 | 3.735 (3.489–3.926) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n100\evidence\result.json` |

| code | 100 | 10 | 5 | 6.009 | 5.835–6.141 | 5.969 (5.770–6.102) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n100\evidence\result.json` |

| code | 100 | 100 | 5 | 19.497 | 19.366–21.702 | 19.431 (19.302–21.647) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_code_n100\evidence\result.json` |

| mixed | 10 | 0 | 5 | 0.026 | 0.021–0.027 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 1 | 5 | 3.678 | 3.574–4.138 | 3.651 (3.552–4.118) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 10 | 5 | 7.136 | 7.068–7.541 | 7.110 (7.046–7.520) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n10\evidence\result.json` |

| mixed | 30 | 0 | 5 | 0.040 | 0.021–0.041 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 1 | 5 | 3.848 | 3.710–3.990 | 3.812 (3.669–3.951) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 10 | 5 | 7.641 | 7.128–7.801 | 7.601 (7.087–7.761) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n30\evidence\result.json` |

| mixed | 100 | 0 | 5 | 0.041 | 0.032–0.061 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 1 | 5 | 4.417 | 4.280–4.669 | 4.359 (4.239–4.627) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 10 | 5 | 8.146 | 7.668–8.691 | 8.085 (7.626–8.659) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 100 | 5 | 38.602 | 36.847–40.561 | 38.571 (36.806–40.521) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_npy_20260921_mixed_n100\evidence\result.json` |
