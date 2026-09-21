"""Summarize nine completed, standard F6 NPY delta families; no live measurements.

From rag/: python -B eval/results/sidecar_npy_20260921/evidence/summarize_npy_delta.py --selfcheck
Run with --run only after all nine standard result.json files are complete.
"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1]
OLD_EVIDENCE = RESULTS / "sidecar_20260915" / "evidence"
sys.path.insert(0, str(OLD_EVIDENCE))
from compare_delta import CELLS, KS, load, number  # existing strict completed-run validator

IO_UNITS = {"written_bytes": "bytes", "hardlinked_bytes": "bytes",
            "copied_bytes": "bytes", "inherited_hashes_not_reverified": "files"}
PHASES = ("init_model", "scan_hash", "load", "parsing_embedding", "qdrant",
          "relink", "save_hash", "eval_gate", "promote")
REQUIRED_COUNTS = {"docs_added", "docs_modified", "docs_removed", "code_added",
                   "code_modified", "code_removed", "chunks_processed",
                   "chunks_indexed", "colbert_tokens_processed", "colbert_tokens_indexed",
                   "code_tokens_processed"}
NOOP_OPTIONAL_COUNTS = {"chunks_indexed", "colbert_tokens_indexed"}
OUTPUT_JSON = HERE / "npy-delta-summary.json"
OUTPUT_MD = HERE / "npy-delta-summary.md"


def fail(message):
    raise ValueError(message)


def stats(values, *, unit):
    if not values or any(not number(value) or value < 0 for value in values):
        fail(f"missing/nonfinite/negative {unit} measurement")
    return {"median": statistics.median(values), "min": min(values),
            "max": max(values), "unit": unit}


def optional_stats(values, *, k, unit, reason):
    if all(value is None for value in values):
        if k != 0:
            fail(f"missing {unit} measurement for k={k}")
        return {"median": None, "min": None, "max": None, "unit": unit,
                "reason": reason}
    if any(value is None for value in values):
        fail(f"partially missing {unit} measurement for k={k}")
    return stats(values, unit=unit)


def count_summary(blocks, *, k, source):
    if any(not isinstance(block, dict) for block in blocks):
        fail(f"{source}: missing counts for k={k}")
    keys = set(blocks[0])
    if not REQUIRED_COUNTS <= keys or any(set(block) != keys for block in blocks):
        fail(f"{source}: missing/inconsistent required count keys for k={k}")
    output = {}
    for field in sorted(keys):
        values = [block[field] for block in blocks]
        if field.endswith("_unavailable_reason"):
            if len(set(values)) != 1:
                fail(f"{source}: inconsistent unavailable reason {field}")
            output[field] = values[0]
        elif field == "code_tokens_processed" and all(value is None for value in values):
            reason = blocks[0].get("code_tokens_unavailable_reason")
            if not isinstance(reason, str) or not reason.strip():
                fail(f"{source}: code tokens missing without explicit reason for k={k}")
            output[field] = {"median": None, "min": None, "max": None,
                             "unit": "count", "reason": reason}
        else:
            if all(value is None for value in values) and (k != 0 or field not in NOOP_OPTIONAL_COUNTS):
                fail(f"{source}: required count {field} missing for k={k}")
            output[field] = optional_stats(values, k=k, unit="count",
                                           reason="not emitted for no-op")
    return output


def summarize_cell(cell, indexed, source):
    n, mode = cell
    rows = []
    for k in KS[n]:
        samples = [indexed[k, repeat] for repeat in range(5)]
        jobs = [sample["job"] for sample in samples]
        results = [job["result"] for job in jobs]
        if any(not isinstance(result, dict) for result in results):
            fail(f"{source}: result missing for {cell}, k={k}")
        io = []
        for result in results:
            block = result.get("colbert_io_bytes")
            if block is not None and (not isinstance(block, dict) or set(block) != set(IO_UNITS)):
                fail(f"{source}: malformed colbert_io_bytes for {cell}, k={k}")
            io.append(block)
        if any(block is None for block in io) and not (k == 0 and all(block is None for block in io)):
            fail(f"{source}: partial or missing ColBERT I/O for {cell}, k={k}")
        io_summary = {field: optional_stats([block.get(field) if block else None for block in io],
                                            k=k, unit=unit, reason="no-op did not emit ColBERT writer stats")
                      for field, unit in IO_UNITS.items()}
        phase_blocks = [result.get("phase_timings_seconds") for result in results]
        if any(not isinstance(block, dict) or set(block) != set(PHASES) for block in phase_blocks):
            fail(f"{source}: missing/unknown phase timings for {cell}, k={k}")
        phases = {field: stats([block[field] for block in phase_blocks], unit="seconds")["median"]
                  for field in PHASES}
        counts = count_summary([result.get("counts") for result in results], k=k, source=f"{source} {cell}")
        rows.append({"n": n, "mode": mode, "k": k, "repeats": 5, "source": source,
                     "snapshot_ready_seconds": stats([job["snapshot_ready_duration_seconds"] for job in jobs], unit="seconds"),
                     "colbert_io": io_summary, "counts": counts, "phase_median_seconds": phases})
    return rows


def inputs():
    return [RESULTS / f"sidecar_delta_npy_20260921_{mode}_n{n}" / "evidence" / "result.json"
            for n, mode in sorted(CELLS)]


def run():
    loaded = [load(path) for path in inputs()]
    if len(loaded) != 9 or {item[0] for item in loaded} != CELLS:
        fail("NPY matrix must contain exactly nine unique standard families")
    rows = []
    for cell, data, indexed, path in loaded:
        if data.get("synthetic_fixture"):
            fail(f"synthetic fixture excluded: {path}")
        rows.extend(summarize_cell(cell, indexed, str(path)))
    payload = {"scope": "completed NPY-only delta results, nine standard cells, five repeats per k",
               "limits": ["synthetic corpus; OS cache uncontrolled",
                          "ColBERT hardlinked/copied bytes are logical file sizes, not process I/O counters",
                          "inherited_hashes_not_reverified is a file count, not bytes",
                          "missing no-op writer stats remain null; no old-vs-new process I/O comparison"],
               "rows": rows}
    def fmt(value):
        return "—" if value is None else f"{value:.3f}"
    lines = ["# F6 NPY delta: completed nine-family summary", "",
             "Five repeats per k; T is snapshot-ready duration. Synthetic corpus; OS cache uncontrolled. Hardlinked/copied bytes are logical file sizes, not process I/O. Inherited hashes are a file count. Missing no-op writer stats are null, not zero.", "",
             "| mode | N | k | T median [min,max] s | written bytes | hardlinked bytes | copied bytes | inherited files | scan s | model s | embedding s | Qdrant s | save/hash s |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in rows:
        t, io, phases = row["snapshot_ready_seconds"], row["colbert_io"], row["phase_median_seconds"]
        lines.append("| {mode} | {n} | {k} | {t} [{lo},{hi}] | {written} | {linked} | {copied} | {inherited} | {scan} | {model} | {embedding} | {qdrant} | {save} |".format(
            mode=row["mode"], n=row["n"], k=row["k"], t=fmt(t["median"]), lo=fmt(t["min"]), hi=fmt(t["max"]),
            written=fmt(io["written_bytes"]["median"]), linked=fmt(io["hardlinked_bytes"]["median"]),
            copied=fmt(io["copied_bytes"]["median"]), inherited=fmt(io["inherited_hashes_not_reverified"]["median"]),
            scan=fmt(phases["scan_hash"]), model=fmt(phases["init_model"]),
            embedding=fmt(phases["parsing_embedding"]), qdrant=fmt(phases["qdrant"]), save=fmt(phases["save_hash"])))
    lines += ["", "All phase medians and numeric count medians/minima/maxima are in the JSON. Phase timings describe the recorded implementation phases; do not subtract them as isolated causal costs. No process-I/O comparison with the old implementation is made."]
    # No output is written until all nine sources and every sample pass validation.
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "json": str(OUTPUT_JSON), "markdown": str(OUTPUT_MD)}))


def selfcheck():
    assert optional_stats([None] * 5, k=0, unit="bytes", reason="no-op")["median"] is None
    for values in ([None] * 5, [1, 2, math.inf, 4, 5], [1, 2, math.nan, 4, 5]):
        try:
            optional_stats(values, k=1, unit="bytes", reason="missing")
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid writer metric accepted: {values}")
    assert stats([1, 2, 3, 4, 5], unit="bytes")["median"] == 3
    assert optional_stats([0] * 5, k=1, unit="bytes", reason="missing")["median"] == 0
    valid = {field: 0 for field in REQUIRED_COUNTS}
    valid.update(chunks_indexed=1, colbert_tokens_indexed=1, code_tokens_processed=None,
                 code_tokens_unavailable_reason="embedding output does not expose code token counts")
    assert count_summary([valid] * 5, k=1, source="selfcheck")["code_tokens_processed"]["median"] is None
    for field in ("chunks_processed", "colbert_tokens_processed", "chunks_indexed"):
        broken = {**valid, field: None}
        try:
            count_summary([broken] * 5, k=1, source="selfcheck")
        except ValueError:
            pass
        else:
            raise AssertionError(f"required count accepted when missing: {field}")
        without_key = {key: value for key, value in valid.items() if key != field}
        try:
            count_summary([without_key] * 5, k=1, source="selfcheck")
        except ValueError:
            pass
        else:
            raise AssertionError(f"required count key accepted when absent: {field}")
    without_reason = {**valid, "code_tokens_unavailable_reason": None}
    try:
        count_summary([without_reason] * 5, k=1, source="selfcheck")
    except ValueError:
        pass
    else:
        raise AssertionError("missing code token count accepted without explicit reason")
    noop = {**valid, "chunks_indexed": None, "colbert_tokens_indexed": None}
    assert count_summary([noop] * 5, k=0, source="selfcheck")["chunks_indexed"]["median"] is None
    print("SYNTHETIC FORMAT SELF-CHECK passed; no real result files read")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--selfcheck", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selfcheck() if args.selfcheck else run()
