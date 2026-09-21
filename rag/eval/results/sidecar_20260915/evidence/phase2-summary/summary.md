# Sidecar delta summary

Prepared from completed real runs.

T is `job.snapshot_ready_duration_seconds`; HTTP elapsed stays separate in CSV. No p95, capacity threshold, or crossover claim is produced. Corpus is synthetic and OS cache is uncontrolled.

| mode | N | k | repeats | median T s | min–max T s | paired ΔT s (min–max) | source |
|---|---:|---:|---:|---:|---:|---:|---|

| docs | 10 | 0 | 5 | 2.627 | 2.575–2.699 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 1 | 5 | 3.378 | 3.268–3.487 | 0.728 (0.666–0.911) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n10\evidence\result.json` |

| docs | 10 | 10 | 5 | 5.084 | 4.925–5.172 | 2.469 (2.322–2.509) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n10\evidence\result.json` |

| docs | 30 | 0 | 5 | 2.581 | 2.527–2.732 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 1 | 5 | 3.507 | 3.325–3.575 | 0.841 (0.754–0.989) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n30\evidence\result.json` |

| docs | 30 | 10 | 5 | 5.267 | 5.130–5.366 | 2.584 (2.559–2.839) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n30\evidence\result.json` |

| docs | 100 | 0 | 5 | 2.739 | 2.615–2.895 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 1 | 5 | 3.761 | 3.638–3.793 | 1.009 (0.866–1.098) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 10 | 5 | 5.493 | 5.449–5.541 | 2.803 (2.555–2.878) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n100\evidence\result.json` |

| docs | 100 | 100 | 5 | 15.588 | 15.335–15.841 | 12.873 (12.441–13.146) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_docs_n100\evidence\result.json` |

| code | 10 | 0 | 5 | 2.641 | 2.574–2.710 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n10\evidence\result.json` |

| code | 10 | 1 | 5 | 3.519 | 3.277–3.704 | 0.937 (0.584–0.994) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n10\evidence\result.json` |

| code | 10 | 10 | 5 | 5.535 | 5.496–5.707 | 2.888 (2.804–3.132) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n10\evidence\result.json` |

| code | 30 | 0 | 5 | 2.644 | 2.437–2.708 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n30\evidence\result.json` |

| code | 30 | 1 | 5 | 3.378 | 3.292–3.503 | 0.780 (0.728–0.896) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n30\evidence\result.json` |

| code | 30 | 10 | 5 | 5.529 | 5.479–5.690 | 2.929 (2.860–3.092) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n30\evidence\result.json` |

| code | 100 | 0 | 5 | 2.614 | 2.531–2.732 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n100\evidence\result.json` |

| code | 100 | 1 | 5 | 3.565 | 3.397–3.646 | 0.942 (0.834–1.026) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n100\evidence\result.json` |

| code | 100 | 10 | 5 | 5.645 | 5.579–5.915 | 3.054 (2.875–3.300) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n100\evidence\result.json` |

| code | 100 | 100 | 5 | 19.017 | 18.491–19.852 | 16.486 (15.865–17.238) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_code_n100\evidence\result.json` |

| mixed | 10 | 0 | 5 | 2.660 | 2.538–2.827 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 1 | 5 | 3.491 | 3.303–3.785 | 0.831 (0.568–1.009) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n10\evidence\result.json` |

| mixed | 10 | 10 | 5 | 5.732 | 5.618–6.063 | 3.065 (2.958–3.442) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n10\evidence\result.json` |

| mixed | 30 | 0 | 5 | 2.643 | 2.575–2.931 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 1 | 5 | 3.546 | 3.407–3.672 | 0.901 (0.741–0.954) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n30\evidence\result.json` |

| mixed | 30 | 10 | 5 | 5.958 | 5.858–6.848 | 3.283 (3.134–4.214) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n30\evidence\result.json` |

| mixed | 100 | 0 | 5 | 2.638 | 2.583–2.772 | 0.000 (0.000–0.000) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 1 | 5 | 3.681 | 3.453–3.708 | 0.909 (0.861–1.105) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 10 | 5 | 5.885 | 5.850–6.102 | 3.297 (3.113–3.422) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n100\evidence\result.json` |

| mixed | 100 | 100 | 5 | 19.046 | 18.683–19.149 | 16.274 (16.091–16.526) | `C:\Users\Silve\.codex\worktrees\0628\vibecraft\rag\eval\results\sidecar_delta_20260921_mixed_n100\evidence\result.json` |
