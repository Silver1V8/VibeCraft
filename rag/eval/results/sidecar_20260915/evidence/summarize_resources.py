"""Per-sample observed resources and query contention, from real F2/F3 raw files."""
import argparse
import json
import statistics
from pathlib import Path


def stats(values):
    values = [x for x in values if x is not None]
    return dict(min=min(values), median=statistics.median(values), max=max(values)) if values else None


def summarize(result_path):
    result = json.loads(result_path.read_text(encoding="utf-8"))
    metadata = json.loads((result_path.parent / "process.json").read_text(encoding="utf-8"))
    if result["status"] != "completed" or metadata["exit_code"] != 0 or metadata.get("sampler_error"):
        raise ValueError(f"Incomplete or failed measurement: {result_path}")
    raw = [json.loads(line) for line in (result_path.parent / "process.jsonl").read_text(encoding="utf-8").splitlines()]
    raw = [item for item in raw if "monotonic_seconds" in item]
    rows = []
    for sample in result["samples"]:
        if not sample["valid"] or not sample["restore_verified"]:
            raise ValueError("Invalid sample or baseline restoration")
        start, end = sample["started_monotonic"], sample["ended_monotonic"]
        selected = [item for item in raw if start <= item["monotonic_seconds"] <= end]
        processes = [p for item in selected for p in item["processes"] if p["pid"] == result["pid"]]
        qdrant = {item["qdrant"]["finished_monotonic"]: item["qdrant"] for item in selected
                  if item.get("qdrant") and start <= item["qdrant"]["finished_monotonic"] <= end}
        maxima = {key: max((p[key] for p in processes if p.get(key) is not None), default=None)
                  for key in ("rss_bytes", "private_bytes", "uss_bytes")}
        # Observed counter differences cover only the sampled portion of the HTTP interval.
        counters = {key: processes[-1][key] - processes[0][key]
                    if len(processes) >= 2 and all(p.get(key) is not None for p in (processes[0], processes[-1])) else None
                    for key in ("io_read_bytes", "io_write_bytes", "cpu_user_seconds", "cpu_system_seconds")}
        queries = sample["queries"]
        rows.append(dict(repeat=sample["repeat"], k=sample["k"], observed_samples=len(processes),
                         server_sampled_maxima=maxima, sampled_counter_differences=counters,
                         qdrant_distinct_observations=len(qdrant),
                         qdrant_rss_peak_bytes=max((q["rss_bytes"] for q in qdrant.values() if q.get("rss_bytes") is not None), default=None),
                         qdrant_private_peak_bytes=max((q["private_bytes"] for q in qdrant.values() if q.get("private_bytes") is not None), default=None),
                         query_latency_seconds=stats([q["end_monotonic"] - q["start_monotonic"] for q in queries]),
                         query_count=len(queries), empty_query_count=sum(q.get("results") == 0 for q in queries),
                         query_error_count=sum(bool(q.get("error")) or q.get("status") != 200 for q in queries)))
    return dict(source=str(result_path.resolve()), parameters=result["parameters"], server_pid=result["pid"],
                sampling_interval_seconds=stats([b["monotonic_seconds"] - a["monotonic_seconds"] for a, b in zip(raw, raw[1:])]),
                baseline_query_latency_seconds=stats([q["end_monotonic"] - q["start_monotonic"] for q in result["baseline_queries"]]),
                qdrant_collections_before=result["qdrant_collections_before"], samples=rows,
                limits=["Sampled maxima are lower bounds; null means no observation, not zero.",
                        "Server RSS is not summed with shared processes. Windows private is committed memory; USS is resident private memory.",
                        "Memory and counters cover sampled HTTP observation intervals, not exact journal build/reload boundaries.",
                        "I/O counters are process counters, not physical disk traffic; differences omit unsampled interval edges.",
                        "Qdrant is the whole dedicated server, including previous experimental collections retained in this series.",
                        "Query latency includes overlapping background reader requests; zero-result responses are reported as degradation."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output must be new")
    args.output.write_text(json.dumps(summarize(args.result), indent=2) + "\n", encoding="utf-8")
