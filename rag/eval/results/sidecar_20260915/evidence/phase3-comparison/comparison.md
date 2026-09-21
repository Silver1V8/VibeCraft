# F3 pre/post delta comparison

Completed-run comparison; no p95, budget, or crossover claim.

| mode | N | k | pre T median s | post T median s | change s | pre ΔT(noop) s | post ΔT(noop) s |
|---|---:|---:|---:|---:|---:|---:|---:|
| code | 10 | 0 | 2.641 | 0.019 | -2.622 | 0.000 | 0.000 |
| code | 10 | 1 | 3.519 | 3.437 | -0.082 | 0.937 | 3.424 |
| code | 10 | 10 | 5.535 | 5.574 | 0.039 | 2.888 | 5.560 |
| docs | 10 | 0 | 2.627 | 0.018 | -2.609 | 0.000 | 0.000 |
| docs | 10 | 1 | 3.378 | 3.421 | 0.043 | 0.728 | 3.411 |
| docs | 10 | 10 | 5.084 | 4.989 | -0.096 | 2.469 | 4.975 |
| mixed | 10 | 0 | 2.660 | 0.020 | -2.640 | 0.000 | 0.000 |
| mixed | 10 | 1 | 3.491 | 3.290 | -0.201 | 0.831 | 3.267 |
| mixed | 10 | 10 | 5.732 | 5.505 | -0.227 | 3.065 | 5.483 |
| code | 30 | 0 | 2.644 | 0.040 | -2.604 | 0.000 | 0.000 |
| code | 30 | 1 | 3.378 | 3.479 | 0.101 | 0.780 | 3.438 |
| code | 30 | 10 | 5.529 | 5.406 | -0.122 | 2.929 | 5.378 |
| docs | 30 | 0 | 2.581 | 0.035 | -2.546 | 0.000 | 0.000 |
| docs | 30 | 1 | 3.507 | 3.434 | -0.073 | 0.841 | 3.406 |
| docs | 30 | 10 | 5.267 | 5.143 | -0.124 | 2.584 | 5.103 |
| mixed | 30 | 0 | 2.643 | 0.035 | -2.608 | 0.000 | 0.000 |
| mixed | 30 | 1 | 3.546 | 3.455 | -0.092 | 0.901 | 3.436 |
| mixed | 30 | 10 | 5.958 | 5.700 | -0.258 | 3.283 | 5.681 |
| code | 100 | 0 | 2.614 | 0.063 | -2.551 | 0.000 | 0.000 |
| code | 100 | 1 | 3.565 | 3.450 | -0.115 | 0.942 | 3.387 |
| code | 100 | 10 | 5.645 | 5.577 | -0.068 | 3.054 | 5.513 |
| code | 100 | 100 | 19.017 | 18.804 | -0.213 | 16.486 | 18.741 |
| docs | 100 | 0 | 2.739 | 0.063 | -2.675 | 0.000 | 0.000 |
| docs | 100 | 1 | 3.761 | 3.768 | 0.008 | 1.009 | 3.704 |
| docs | 100 | 10 | 5.493 | 5.636 | 0.144 | 2.803 | 5.569 |
| docs | 100 | 100 | 15.588 | 15.934 | 0.346 | 12.873 | 15.900 |
| mixed | 100 | 0 | 2.638 | 0.046 | -2.592 | 0.000 | 0.000 |
| mixed | 100 | 1 | 3.681 | 3.770 | 0.089 | 0.909 | 3.733 |
| mixed | 100 | 10 | 5.885 | 6.202 | 0.317 | 3.297 | 6.159 |
| mixed | 100 | 100 | 19.046 | 19.132 | 0.086 | 16.274 | 19.082 |

ΔT is T(k)-T(0), not embedding-only. F3 fast no-op may avoid model loading, so a larger ΔT does not itself mean a larger absolute delta duration. Resource maxima are sampled lower bounds. Query entries are HTTP-observation windows: the reader starts around the request and may finish after the recorded HTTP end, so they do not prove overlap with the writer for each query. Mixed endpoint frequency varies with job duration and is reported, not normalized.