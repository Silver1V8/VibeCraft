"""Summarize sampler observations for one completed F5 full-candidate build."""
import argparse
import json
import math
from pathlib import Path


METRICS = ("rss_bytes", "private_bytes", "uss_bytes")
COUNTERS = ("io_read_bytes", "io_write_bytes", "cpu_user_seconds", "cpu_system_seconds")


def fail(message):
    raise ValueError(message)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def process_rows(raw, pid, start=None, end=None):
    rows = []
    for item in raw:
        moment = item.get("monotonic_seconds")
        if not finite(moment) or (start is not None and not start <= moment <= end):
            continue
        rows.extend(process for process in item.get("processes", []) if process.get("pid") == pid)
    return rows


def observed(rows):
    return {metric: max((row[metric] for row in rows if finite(row.get(metric))), default=None) for metric in METRICS}


def deltas(rows):
    return {metric: {"first": rows[0][metric], "last": rows[-1][metric],
                     "difference": rows[-1][metric] - rows[0][metric]} if len(rows) >= 2 and
            all(finite(row.get(metric)) for row in (rows[0], rows[-1])) else None for metric in COUNTERS}


def qdrant_rows(raw, start, end):
    values = {}
    for item in raw:
        row = item.get("qdrant")
        if isinstance(row, dict) and finite(row.get("finished_monotonic")) and start <= row["finished_monotonic"] <= end:
            values.setdefault(row["finished_monotonic"], row)
    return [values[key] for key in sorted(values)]


def host_rows(raw, start, end):
    return [item["system"] for item in raw if finite(item.get("monotonic_seconds")) and start <= item["monotonic_seconds"] <= end and isinstance(item.get("system"), dict)]


def summarize(result, process, raw):
    if result.get("status") != "completed" or process.get("completion") != "completed" or process.get("exit_code") != 0 or process.get("sampler_error"):
        fail("completed workload and successful sampler are required")
    pid, start, end = result.get("pid"), result.get("build_started_monotonic"), result.get("build_ended_monotonic")
    if type(pid) is not int or not finite(start) or not finite(end) or end < start:
        fail("result needs integer pid and finite build monotonic interval")
    raw = [row for row in raw if isinstance(row, dict)]
    whole, build = process_rows(raw, pid), process_rows(raw, pid, start, end)
    if not whole or not build:
        fail("sampler has no workload PID observation for whole process or build interval")
    if not build:
        fail("no workload PID samples overlap the build interval")
    qdrant = qdrant_rows(raw, start, end)
    host = host_rows(raw, start, end)
    return {"source": {"workload_pid": pid, "build_started_monotonic": start, "build_ended_monotonic": end},
            "build": {"observed_samples": len(build), "workload_sampled_peak_lower_bounds": observed(build),
                      "sampled_counter_differences": deltas(build)},
            "whole_process": {"observed_samples": len(whole), "workload_sampled_peak_lower_bounds": observed(whole),
                              "sampled_counter_differences": deltas(whole)},
            "qdrant_build": {"distinct_observations": len(qdrant),
                              "rss_peak_lower_bound_bytes": max((r["rss_bytes"] for r in qdrant if finite(r.get("rss_bytes"))), default=None),
                              "private_peak_lower_bound_bytes": max((r["private_bytes"] for r in qdrant if finite(r.get("private_bytes"))), default=None),
                              "last_cgroup_observation": qdrant[-1].get("cgroup") if qdrant else None,
                              "cgroup_usage_peak_lower_bound_bytes": max((r.get("cgroup", {}).get("usage_bytes") for r in qdrant if finite(r.get("cgroup", {}).get("usage_bytes"))), default=None),
                              "cgroup_cache_peak_lower_bound_bytes": max((r.get("cgroup", {}).get("cache_bytes") for r in qdrant if finite(r.get("cgroup", {}).get("cache_bytes"))), default=None)},
            "host_build": {"observed_samples": len(host),
                           "ram_total_bytes": next((r.get("virtual_memory_total_bytes") for r in host if finite(r.get("virtual_memory_total_bytes"))), None),
                           "ram_available_min_bytes": min((r["virtual_memory_available_bytes"] for r in host if finite(r.get("virtual_memory_available_bytes"))), default=None),
                           "swap_total_bytes": next((r.get("swap_total_bytes") for r in host if finite(r.get("swap_total_bytes"))), None),
                           "swap_used_max_bytes": max((r["swap_used_bytes"] for r in host if finite(r.get("swap_used_bytes"))), default=None)},
            "limits": ["Peaks are sampled lower bounds; null means no observation, not zero.",
                       "Workload RSS/private/USS are separate and are never summed with children or Qdrant.",
                       "Build interval excludes sampler startup/import and any later deep integrity check; whole_process retains those observations.",
                       "I/O and CPU are first/last sampled process counters, not physical-disk totals.",
                       "Qdrant cgroup is separate; its last observation and sampled peaks are labeled explicitly. Host RAM and swap are host observations."]}


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def selfcheck():
    result = {"status": "completed", "pid": 7, "build_started_monotonic": 2.0, "build_ended_monotonic": 3.0}
    process = {"completion": "completed", "exit_code": 0, "sampler_error": None}
    raw = [{"monotonic_seconds": 1.0, "processes": [{"pid": 7, "rss_bytes": 99, "io_read_bytes": 1}]},
           {"monotonic_seconds": 2.5, "processes": [{"pid": 7, "rss_bytes": 8, "io_read_bytes": 3}], "qdrant": {"finished_monotonic": 2.6, "cgroup": {"usage_bytes": 5}}},
           {"monotonic_seconds": 3.0, "processes": [{"pid": 7, "rss_bytes": 6, "io_read_bytes": 6}], "qdrant": {"finished_monotonic": 2.6, "cgroup": {"usage_bytes": 5}}}]
    report = summarize(result, process, raw)
    assert report["build"]["workload_sampled_peak_lower_bounds"]["rss_bytes"] == 8
    assert report["build"]["sampled_counter_differences"]["io_read_bytes"] == {"first": 3, "last": 6, "difference": 3}
    assert report["whole_process"]["workload_sampled_peak_lower_bounds"]["private_bytes"] is None
    assert report["qdrant_build"]["distinct_observations"] == 1
    try: summarize({**result, "status": "failed"}, process, raw)
    except ValueError: pass
    else: raise AssertionError("failed workload accepted")
    try: summarize(result, process, raw[:1])
    except ValueError: pass
    else: raise AssertionError("uncorrelated sampler accepted")
    print("synthetic resource selfcheck passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path); parser.add_argument("--process", type=Path)
    parser.add_argument("--raw", type=Path); parser.add_argument("--output", type=Path)
    parser.add_argument("--selfcheck", action="store_true"); args = parser.parse_args()
    if args.selfcheck:
        if any((args.result, args.process, args.raw, args.output)): fail("--selfcheck takes no paths")
        selfcheck(); return
    if not all((args.result, args.process, args.raw, args.output)) or args.output.exists(): fail("new --output and all inputs are required")
    report = summarize(json.loads(args.result.read_text(encoding="utf-8")), json.loads(args.process.read_text(encoding="utf-8")), load_jsonl(args.raw))
    report["source"]["result"] = str(args.result.resolve()); report["source"]["process"] = str(args.process.resolve()); report["source"]["raw"] = str(args.raw.resolve())
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
