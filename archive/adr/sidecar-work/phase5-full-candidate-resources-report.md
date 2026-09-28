# F5 full-candidate resource aggregation — prepared

`full_candidate_resources.py` accepts explicit `result.json`, sampler `process.json`, and `process.jsonl` paths only after a completed workload and successful sampler. It requires the workload PID and finite build monotonic bounds emitted by the driver.

The JSON output keeps sampled peaks for RSS, private memory, and USS separate for the exact build interval and whole process. It records sampled first/last I/O and CPU differences, Qdrant observations deduplicated by their completion timestamp, separately labelled final and sampled-peak cgroup values, and host RAM/swap observations. Missing observations remain `null`; peak values are lower bounds. It does not add RSS values or claim a peak outside the sampled interval.

The build interval starts immediately before `build_graph_and_index` and ends immediately after it. Startup/import and any later deep integrity work therefore remain distinguishable in the whole-process view.
