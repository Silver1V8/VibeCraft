# Pre/post delta comparison

Completed-run comparison; no p95, budget, or crossover claim.

| mode | N | k | pre T median s | post T median s | change s | pre ΔT(noop) s | post ΔT(noop) s |
|---|---:|---:|---:|---:|---:|---:|---:|
| code | 10 | 0 | 0.019 | 0.020 | 0.001 | 0.000 | 0.000 |
| code | 10 | 1 | 3.437 | 3.657 | 0.220 | 3.424 | 3.628 |
| code | 10 | 10 | 5.574 | 5.868 | 0.293 | 5.560 | 5.838 |
| docs | 10 | 0 | 0.018 | 0.022 | 0.005 | 0.000 | 0.000 |
| docs | 10 | 1 | 3.421 | 3.807 | 0.386 | 3.411 | 3.785 |
| docs | 10 | 10 | 4.989 | 8.845 | 3.856 | 4.975 | 8.821 |
| mixed | 10 | 0 | 0.020 | 0.026 | 0.005 | 0.000 | 0.000 |
| mixed | 10 | 1 | 3.290 | 3.678 | 0.387 | 3.267 | 3.651 |
| mixed | 10 | 10 | 5.505 | 7.136 | 1.630 | 5.483 | 7.110 |
| code | 30 | 0 | 0.040 | 0.034 | -0.005 | 0.000 | 0.000 |
| code | 30 | 1 | 3.479 | 3.664 | 0.185 | 3.438 | 3.641 |
| code | 30 | 10 | 5.406 | 5.892 | 0.486 | 5.378 | 5.853 |
| docs | 30 | 0 | 0.035 | 0.020 | -0.015 | 0.000 | 0.000 |
| docs | 30 | 1 | 3.434 | 4.094 | 0.661 | 3.406 | 4.054 |
| docs | 30 | 10 | 5.143 | 9.179 | 4.036 | 5.103 | 9.160 |
| mixed | 30 | 0 | 0.035 | 0.040 | 0.005 | 0.000 | 0.000 |
| mixed | 30 | 1 | 3.455 | 3.848 | 0.393 | 3.436 | 3.812 |
| mixed | 30 | 10 | 5.700 | 7.641 | 1.940 | 5.681 | 7.601 |
| code | 100 | 0 | 0.063 | 0.055 | -0.008 | 0.000 | 0.000 |
| code | 100 | 1 | 3.450 | 3.800 | 0.350 | 3.387 | 3.735 |
| code | 100 | 10 | 5.577 | 6.009 | 0.432 | 5.513 | 5.969 |
| code | 100 | 100 | 18.804 | 19.497 | 0.693 | 18.741 | 19.431 |
| docs | 100 | 0 | 0.063 | 0.042 | -0.021 | 0.000 | 0.000 |
| docs | 100 | 1 | 3.768 | 4.944 | 1.176 | 3.704 | 4.882 |
| docs | 100 | 10 | 5.636 | 9.651 | 4.014 | 5.569 | 9.590 |
| docs | 100 | 100 | 15.934 | 58.099 | 42.165 | 15.900 | 58.060 |
| mixed | 100 | 0 | 0.046 | 0.041 | -0.005 | 0.000 | 0.000 |
| mixed | 100 | 1 | 3.770 | 4.417 | 0.647 | 3.733 | 4.359 |
| mixed | 100 | 10 | 6.202 | 8.146 | 1.944 | 6.159 | 8.085 |
| mixed | 100 | 100 | 19.132 | 38.602 | 19.470 | 19.082 | 38.571 |

ΔT is T(k)-T(0), not embedding-only. F3 fast no-op may avoid model loading, so a larger ΔT does not itself mean a larger absolute delta duration. Resource maxima are sampled lower bounds. Query entries are HTTP-observation windows: the reader starts around the request and may finish after the recorded HTTP end, so they do not prove overlap with the writer for each query. Mixed endpoint frequency varies with job duration and is reported, not normalized.