"""Summarize accepted F4 workers and sampled process resources, without rerunning them."""
import csv
import importlib.util
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def stats(values):
    values = [v for v in values if v is not None]
    return dict(min=min(values), median=statistics.median(values), max=max(values)) if values else None


def delta(row, after, baseline, key):
    a, b = row[after].get(key), row[baseline].get(key)
    return a - b if a is not None and b is not None else None


def main():
    spec = importlib.util.spec_from_file_location("reader_experiment", HERE / "reader_experiment.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    comparison = driver.compare_outputs()  # Exact score/ranking parity, every worker.
    result, table = {}, []
    for label in ("io", "full"):
        metadata = json.loads((HERE / f"{label}-process.json").read_text())
        if metadata["exit_code"] != 0 or metadata["completion"] != "completed" or metadata["sampler_error"]:
            raise ValueError(f"Unfinished or failed {label} sampler")
        raw = [json.loads(line) for line in (HERE / f"{label}-process.jsonl").read_text().splitlines()]
        all_rows = [json.loads((HERE / f"{label}-{kind}-{i}.json").read_text())
                    for kind in ("eager", "lazy", "npy") for i in range(5)]
        if len({r["pid"] for r in all_rows}) != 15:
            raise ValueError("PID reuse requires timestamp disambiguation")
        samples = []
        baseline = "baseline_after_import" if label == "io" else "baseline_after_model_import"
        after = "after_reads" if label == "io" else "after_retrieval"
        for row in all_rows:
            if row["python_hash_seed"] != "0":
                raise ValueError("Uncontrolled hash seed")
            observed = [p for r in raw for p in r.get("processes", []) if p["pid"] == row["pid"]]
            if not observed:
                raise ValueError(f"No resource samples for worker {row['pid']}")
            sample = dict(kind=row["kind"], pid=row["pid"], observed_samples=len(observed),
                          sampled_peak={key: max((p[key] for p in observed if p.get(key) is not None), default=None)
                                        for key in ("rss_bytes", "uss_bytes", "private_bytes")},
                          load_delta={key: delta(row, "after_load", baseline, key)
                                      for key in ("rss_bytes", "uss_bytes", "private_bytes", "read_bytes", "write_bytes", "open_files", "maps")},
                          reads_delta={key: delta(row, after, "after_load", key)
                                       for key in ("rss_bytes", "uss_bytes", "private_bytes", "read_bytes", "write_bytes", "open_files", "maps")})
            samples.append(sample)
        result[label] = dict(samples=samples, sampler=metadata, aggregates={})
        for kind in ("eager", "lazy", "npy"):
            selected = [r for r in samples if r["kind"] == kind]
            aggregate = {group: {key: stats(r[group][key] for r in selected) for key in selected[0][group]}
                         for group in ("sampled_peak", "load_delta", "reads_delta")}
            result[label]["aggregates"][kind] = aggregate
            def median(group, key):
                value = aggregate[group][key]
                return value["median"] if value is not None else None
            row = dict(experiment=label, reader=kind, load_median_s=comparison[label][kind]["load_s"]["median"],
                       load_uss_delta_bytes=median("load_delta", "uss_bytes"),
                       sampled_process_uss_peak_bytes=median("sampled_peak", "uss_bytes"),
                       load_read_bytes=median("load_delta", "read_bytes"),
                       reads_read_bytes=median("reads_delta", "read_bytes"),
                       first_median_s=None, warm_median_s=None)
            if label == "io":
                row.update(first_median_s=comparison[label][kind]["first_s"]["median"],
                           warm_median_s=statistics.median(comparison[label][kind]["warm_s_median_each"]))
            table.append(row)
    result["limits"] = [
        "Peaks are sampled lower bounds for each whole worker, including imports/model; never summed across processes.",
        "Load deltas are endpoint measurements after imports (I/O) or model plus baseline validation (full).",
        "Process I/O counters are not physical disk traffic. Maps/files are endpoint counts, not concurrent peaks.",
        "I/O replay uses 32 fixed historical candidates plus missing; full uses smaller F3 synthetic corpus.",
        "First read is not cold OS cache; five fresh processes give median/min/max, not stable p95.",
        "Qdrant sampler covers the dedicated server including retained experimental collections."
    ]
    (HERE / "resources.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (HERE / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    print(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
