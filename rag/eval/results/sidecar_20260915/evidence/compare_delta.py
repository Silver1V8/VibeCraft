"""Compare two series of nine completed sidecar delta result files."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

from summarize_resources import summarize

CELLS = {(n, mode) for n in (10, 30, 100) for mode in ("docs", "code", "mixed")}
KS = {10: [0, 1, 10], 30: [0, 1, 10], 100: [0, 1, 10, 100]}
TIMES = ("queue_duration_seconds", "writer_lock_wait_seconds", "build_duration_seconds", "reload_duration_seconds")
COUNTS = ("docs_modified", "code_modified", "chunks_processed", "colbert_tokens_processed", "code_tokens_processed")


def fail(message): raise ValueError(message)
def number(value): return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
def median(values): return statistics.median(values) if values else None


def corpus(data):
    result = {}
    for path, item in (data.get("corpus") or {}).items():
        parts = Path(path).parts
        try: key = "/".join(parts[parts.index("docs"):])
        except ValueError:
            try: key = "/".join(parts[parts.index("code"):])
            except ValueError: fail(f"corpus path is not docs/code: {path}")
        result[key] = (item.get("sha256"), item.get("bytes"))
    return result


def load(filename, synthetic=False):
    path = Path(filename).resolve(); data = json.loads(path.read_text(encoding="utf-8")); p = data.get("parameters") or {}
    cell = p.get("n"), p.get("mode"); label = str(path)
    if "smoke" in label.lower() or data.get("smoke") or (data.get("synthetic_fixture") and not synthetic): fail(f"{label}: smoke/synthetic input excluded")
    if data.get("status") != "completed" or data.get("error") or cell not in CELLS or p.get("repeats") != 5 or p.get("k") != KS[cell[0]]: fail(f"{label}: incomplete or non-standard cell")
    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) != 5 * len(KS[cell[0]]): fail(f"{label}: cardinality is not five repeats per k")
    indexed = {}
    for s in samples:
        k, repeat, job = s.get("k"), s.get("repeat"), s.get("job") or {}; result = job.get("result") or {}; t = job.get("snapshot_ready_duration_seconds")
        if (k not in KS[cell[0]] or repeat not in range(5) or (k, repeat) in indexed or s.get("valid") is not True or s.get("restore_verified") is not True or not number(t) or t < 0): fail(f"{label}: invalid sample, restore, or T")
        if job.get("status") != "completed" or job.get("reload_status") != "completed" or job.get("published_token") != s.get("current_version") or job.get("coalesced"): fail(f"{label}: job/reload/token validation failed")
        if k == 0 and result.get("noop") is not True: fail(f"{label}: k=0 is not a no-op")
        if any(not number(job.get(x)) or job[x] < 0 for x in TIMES): fail(f"{label}: timing breakdown missing")
        indexed[k, repeat] = s
    if set(indexed) != {(k, r) for k in KS[cell[0]] for r in range(5)}: fail(f"{label}: repeat keys differ")
    return cell, data, indexed, path


def resource(path, result):
    if not (path.parent / "process.jsonl").exists(): return {}, "not provided"
    process = json.loads((path.parent / "process.json").read_text(encoding="utf-8"))
    if process.get("exit_code") != 0 or process.get("sampler_error") is not None or process.get("completion") != "completed": fail(f"{path}: raw sampler failed or partial")
    data = summarize(path)
    if data.get("source") != str(path.resolve()) or data.get("parameters") != result["parameters"] or data.get("server_pid") != result.get("pid"): fail(f"{path}: raw resource identity differs")
    rows = {(x.get("k"), x.get("repeat")): x for x in data.get("samples") or []}
    expected = {(x.get("k"), x.get("repeat")) for x in result["samples"]}
    if len(rows) != len(data.get("samples") or []) or set(rows) != expected: fail(f"{path}: raw resource samples do not align")
    return rows, "; ".join(data.get("limits") or []) or "limits not supplied"


def compare_pair(pre, post):
    cell, a, left, left_path = pre; _, b, right, right_path = post
    config_a, config_b = dict(a["parameters"]), dict(b["parameters"]); ca, cb = config_a.pop("collection", None), config_b.pop("collection", None)
    if not ca or not cb: fail(f"{cell}: collection configuration missing")
    if config_a != config_b or ca == cb: fail(f"{cell}: configuration differs beyond dedicated collection")
    config = "run parameters verified; dedicated collection differs"
    if corpus(a) != corpus(b): fail(f"{cell}: baseline docs/code hashes or bytes differ")
    if a.get("baseline_points") != b.get("baseline_points") or not {"count", "sha256"} <= set(a.get("baseline_points") or {}): fail(f"{cell}: baseline Qdrant point digest differs or is absent")
    ra, limit_a = resource(left_path, a); rb, limit_b = resource(right_path, b); rows = []
    for k in KS[cell[0]]:
        aa, bb = [left[k, r] for r in range(5)], [right[k, r] for r in range(5)]
        for x, y in zip(aa, bb):
            for field in COUNTS:
                xc, yc = (x["job"].get("result") or {}).get("counts") or {}, (y["job"].get("result") or {}).get("counts") or {}
                if field not in xc or field not in yc or xc[field] != yc[field]: fail(f"{cell}, k={k}: {field} differs or is absent")
            if (x["job"].get("result") or {}).get("reindexed_docs") != (y["job"].get("result") or {}).get("reindexed_docs"): fail(f"{cell}, k={k}: reindexed docs differ")
        tv = lambda samples: [x["job"]["snapshot_ready_duration_seconds"] for x in samples]
        av, bv = tv(aa), tv(bb); az = [left[0, r]["job"]["snapshot_ready_duration_seconds"] for r in range(5)]; bz = [right[0, r]["job"]["snapshot_ready_duration_seconds"] for r in range(5)]
        breakdown = lambda samples: {x: median([s["job"][x] for s in samples]) for x in TIMES}
        query = lambda samples: query_summary(samples)
        mem = lambda resource_rows: resource_summary([resource_rows.get((k, r)) for r in range(5)])
        rows.append({"n": cell[0], "mode": cell[1], "k": k, "repeats": 5, "pre_T_median_s": median(av), "pre_T_min_s": min(av), "pre_T_max_s": max(av), "post_T_median_s": median(bv), "post_T_min_s": min(bv), "post_T_max_s": max(bv), "T_median_change_s": median(bv) - median(av), "pre_paired_T_minus_noop_s": median([v-z for v, z in zip(av, az)]), "post_paired_T_minus_noop_s": median([v-z for v, z in zip(bv, bz)]), "pre_breakdown_medians": json.dumps(breakdown(aa)), "post_breakdown_medians": json.dumps(breakdown(bb)), "pre_queries": json.dumps(query(aa)), "post_queries": json.dumps(query(bb)), "pre_resources": json.dumps(mem(ra)), "post_resources": json.dumps(mem(rb)), "configuration": config, "pre_source": str(left_path), "post_source": str(right_path), "resource_limits": f"pre: {limit_a}; post: {limit_b}"})
    return rows


def query_summary(samples):
    result = {}
    for s in samples:
        for q in s.get("queries") or []:
            item = result.setdefault(q.get("endpoint") or "unknown", {"latency": [], "empty": 0, "errors": 0, "count": 0})
            item["count"] += 1; item["empty"] += q.get("results") == 0; item["errors"] += bool(q.get("error")) or q.get("status") != 200
            if number(q.get("end_monotonic")) and number(q.get("start_monotonic")): item["latency"].append(q["end_monotonic"] - q["start_monotonic"])
    return {key: {"count": x["count"], "empty": x["empty"], "errors": x["errors"], "latency_min_median_max_s": [min(x["latency"]), median(x["latency"]), max(x["latency"])] if x["latency"] else None} for key, x in result.items()}


def resource_summary(rows):
    rows = [x for x in rows if x]
    if not rows: return None
    fields = ("rss_bytes", "private_bytes", "uss_bytes", "io_read_bytes", "io_write_bytes")
    return {field: median([source.get(field) for x in rows for source in (x.get("server_sampled_maxima") or {}, x.get("sampled_counter_differences") or {}) if number(source.get(field))]) for field in fields}


def run(pre_files, post_files, output, synthetic=False):
    if len(pre_files) != 9 or len(post_files) != 9: fail("exactly nine --pre and nine --post inputs required")
    pre, post = [load(x, synthetic) for x in pre_files], [load(x, synthetic) for x in post_files]
    by_pre, by_post = {x[0]: x for x in pre}, {x[0]: x for x in post}
    if set(by_pre) != CELLS or set(by_post) != CELLS: fail("input cells must be the complete nine-family matrix")
    output.mkdir(); rows = sum((compare_pair(by_pre[cell], by_post[cell]) for cell in sorted(CELLS)), [])
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as f: writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (output / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = ["# Pre/post delta comparison", "", "SYNTHETIC FORMAT SELF-CHECK — not a measurement." if synthetic else "Completed-run comparison; no p95, budget, or crossover claim.", "", "| mode | N | k | pre T median s | post T median s | change s | pre ΔT(noop) s | post ΔT(noop) s |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [f"| {r['mode']} | {r['n']} | {r['k']} | {r['pre_T_median_s']:.3f} | {r['post_T_median_s']:.3f} | {r['T_median_change_s']:.3f} | {r['pre_paired_T_minus_noop_s']:.3f} | {r['post_paired_T_minus_noop_s']:.3f} |" for r in rows]
    lines += ["", "ΔT is T(k)-T(0), not embedding-only. F3 fast no-op may avoid model loading, so a larger ΔT does not itself mean a larger absolute delta duration. Resource maxima are sampled lower bounds. Query entries are HTTP-observation windows: the reader starts around the request and may finish after the recorded HTTP end, so they do not prove overlap with the writer for each query. Mixed endpoint frequency varies with job duration and is reported, not normalized."]
    (output / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


def selfcheck():
    def fixture(collection, offset):
        samples = {}
        for k in KS[10]:
            for repeat in range(5):
                counts = {"docs_modified": k, "code_modified": 0, "chunks_processed": k, "colbert_tokens_processed": k, "code_tokens_processed": None}
                job = {"status": "completed", "reload_status": "completed", "published_token": "token", "coalesced": False, "snapshot_ready_duration_seconds": 1 + k + offset, "result": {"noop": k == 0, "counts": counts, "reindexed_docs": k}}
                job.update({x: 0 for x in TIMES}); samples[k, repeat] = {"k": k, "repeat": repeat, "valid": True, "restore_verified": True, "current_version": "token", "job": job, "queries": []}
        data = {"parameters": {"n": 10, "mode": "docs", "k": KS[10], "repeats": 5, "collection": collection}, "corpus": {"docs/d000.md": {"sha256": "x", "bytes": 1}}, "baseline_points": {"count": 1, "sha256": "x"}}
        return (10, "docs"), data, samples, Path("synthetic")
    pre, post = fixture("pre", 0), fixture("post", .1)
    assert len(compare_pair(pre, post)) == 3
    post[1]["parameters"]["server_url"] = "different"
    try: compare_pair(pre, post)
    except ValueError: pass
    else: raise AssertionError("configuration mismatch accepted")
    print("SYNTHETIC FORMAT SELF-CHECK — not a measurement")


def main():
    p = argparse.ArgumentParser(); p.add_argument("--pre", nargs="+"); p.add_argument("--post", nargs="+"); p.add_argument("--output", type=Path); p.add_argument("--selfcheck", action="store_true"); a = p.parse_args()
    if a.selfcheck:
        if a.pre or a.post or a.output: fail("--selfcheck takes no inputs or output")
        selfcheck(); return
    if not a.pre or not a.post or not a.output: fail("--pre, --post, and a new --output directory are required")
    run(a.pre, a.post, a.output)


if __name__ == "__main__": main()
