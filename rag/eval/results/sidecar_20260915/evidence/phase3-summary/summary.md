# Sidecar delta summary

Prepared from completed real runs.

T is `job.snapshot_ready_duration_seconds`; HTTP elapsed stays separate in CSV. No p95, capacity threshold, or crossover claim is produced. Corpus is synthetic and OS cache is uncontrolled.

| mode | N | k | repeats | median T s | min–max T s | paired ΔT s (min–max) | source |
|---|---:|---:|---:|---:|---:|---:|---|

| docs | 10 | 0 | 5 | 0.018 | 0.011–0.024 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 1 | 5 | 3.421 | 3.292–3.757 | 3.411 (3.279–3.740) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 10 | 5 | 4.989 | 4.919–5.595 | 4.975 (4.895–5.578) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n10\evidence\result.json` |

| docs | 30 | 0 | 5 | 0.035 | 0.016–0.041 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 1 | 5 | 3.434 | 3.414–3.530 | 3.406 (3.373–3.506) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 10 | 5 | 5.143 | 5.009–5.197 | 5.103 (4.968–5.173) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n30\evidence\result.json` |

| docs | 100 | 0 | 5 | 0.063 | 0.035–0.068 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 1 | 5 | 3.768 | 3.708–3.905 | 3.704 (3.641–3.844) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 10 | 5 | 5.636 | 5.573–6.362 | 5.569 (5.508–6.327) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 100 | 5 | 15.934 | 15.383–16.433 | 15.900 (15.320–16.372) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_docs_n100\evidence\result.json` |

| code | 10 | 0 | 5 | 0.019 | 0.013–0.026 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n10\evidence\result.json` |

| code | 10 | 1 | 5 | 3.437 | 3.336–3.580 | 3.424 (3.323–3.556) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n10\evidence\result.json` |

| code | 10 | 10 | 5 | 5.574 | 5.466–5.846 | 5.560 (5.453–5.820) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n10\evidence\result.json` |

| code | 30 | 0 | 5 | 0.040 | 0.019–0.041 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n30\evidence\result.json` |

| code | 30 | 1 | 5 | 3.479 | 3.349–3.525 | 3.438 (3.309–3.506) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n30\evidence\result.json` |

| code | 30 | 10 | 5 | 5.406 | 5.364–5.784 | 5.378 (5.324–5.743) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n30\evidence\result.json` |

| code | 100 | 0 | 5 | 0.063 | 0.059–0.064 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n100\evidence\result.json` |

| code | 100 | 1 | 5 | 3.450 | 3.416–3.623 | 3.387 (3.354–3.563) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n100\evidence\result.json` |

| code | 100 | 10 | 5 | 5.577 | 5.518–5.674 | 5.513 (5.455–5.615) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n100\evidence\result.json` |

| code | 100 | 100 | 5 | 18.804 | 18.275–18.870 | 18.741 (18.211–18.811) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_code_n100\evidence\result.json` |

| mixed | 10 | 0 | 5 | 0.020 | 0.014–0.025 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 1 | 5 | 3.290 | 3.265–3.463 | 3.267 (3.248–3.438) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 10 | 5 | 5.505 | 5.465–5.708 | 5.483 (5.452–5.683) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n10\evidence\result.json` |

| mixed | 30 | 0 | 5 | 0.035 | 0.014–0.040 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 1 | 5 | 3.455 | 3.430–3.542 | 3.436 (3.400–3.502) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 10 | 5 | 5.700 | 5.656–5.854 | 5.681 (5.616–5.819) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n30\evidence\result.json` |

| mixed | 100 | 0 | 5 | 0.046 | 0.037–0.067 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 1 | 5 | 3.770 | 3.624–4.057 | 3.733 (3.573–3.990) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 10 | 5 | 6.202 | 5.821–6.474 | 6.159 (5.774–6.437) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 100 | 5 | 19.132 | 18.629–19.879 | 19.082 (18.592–19.835) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_post_20260921_mixed_n100\evidence\result.json` |
