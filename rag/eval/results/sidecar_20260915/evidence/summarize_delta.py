"""Aggregate the nine completed sidecar delta result.json files."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path

from reportlab.graphics import renderSVG
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Line, String
from reportlab.lib.colors import HexColor

CELLS = {(n, mode) for n in (10, 30, 100) for mode in ("docs", "code", "mixed")}
K_BY_N = {10: [0, 1, 10], 30: [0, 1, 10], 100: [0, 1, 10, 100]}
def fail(message):
    raise ValueError(message)


def read_result(name, allow_synthetic=False):
    path = Path(name).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    params = data.get("parameters") or {}
    n, mode = params.get("n"), params.get("mode")
    label = str(path)
    if "smoke" in path.as_posix().lower() or data.get("smoke"):
        fail(f"{label}: smoke input is excluded")
    if data.get("synthetic_fixture") and not allow_synthetic:
        fail(f"{label}: synthetic fixture is excluded")
    if data.get("status") != "completed" or data.get("error"):
        fail(f"{label}: run failed or did not complete")
    if (n, mode) not in CELLS or params.get("repeats") != 5 or params.get("k") != K_BY_N[n]:
        fail(f"{label}: expected one standard N/mode cell with five repeats")
    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) != 5 * len(K_BY_N[n]):
        fail(f"{label}: cardinality differs from five repeats per k")
    by_k = {k: [] for k in K_BY_N[n]}
    for sample in samples:
        k, job = sample.get("k"), sample.get("job") or {}
        t = job.get("snapshot_ready_duration_seconds")
        if (k not in by_k or sample.get("valid") is not True or sample.get("restore_verified") is not True or
                isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0):
            fail(f"{label}: invalid cell, missing restore, or missing snapshot-ready duration")
        by_k[k].append(sample)
    if any(len(items) != 5 or {x.get("repeat") for x in items} != set(range(5)) for items in by_k.values()):
        fail(f"{label}: each k must contain repeats 0..4 exactly once")
    return (n, mode), data, by_k, label


def rows_for(cell, by_k, source, synthetic):
    n, mode = cell
    zero = {s["repeat"]: s["job"]["snapshot_ready_duration_seconds"] for s in by_k[0]}
    rows = []
    for k, items in by_k.items():
        values = [s["job"]["snapshot_ready_duration_seconds"] for s in items]
        deltas = [s["job"]["snapshot_ready_duration_seconds"] - zero[s["repeat"]] for s in items]
        http = [s.get("elapsed_seconds") for s in items if isinstance(s.get("elapsed_seconds"), (int, float))]
        rows.append({"source": source, "n": n, "mode": mode, "k": k, "repeat_count": 5,
                     "median_T_seconds": statistics.median(values), "min_T_seconds": min(values),
                     "max_T_seconds": max(values), "paired_median_delta_seconds": statistics.median(deltas),
                     "paired_min_delta_seconds": min(deltas), "paired_max_delta_seconds": max(deltas),
                     "median_http_elapsed_seconds": statistics.median(http) if http else "",
                     "nature": "synthetic fixture" if synthetic else "synthetic corpus",
                     "os_cache": "uncontrolled"})
    return rows


def write_svg(rows, destination, synthetic):
    drawing = Drawing(1140, 390)
    title = "SYNTHETIC FORMAT SELF-CHECK — not a benchmark measurement" if synthetic else "Synthetic corpus; medians of five repeats; no capacity threshold"
    drawing.add(String(20, 370, title, fontSize=13))
    drawing.add(String(20, 352, "T(N,k): snapshot-ready duration; error bars show min–max (seconds)", fontSize=10))
    for panel, mode in enumerate(("docs", "code", "mixed")):
        x = 35 + panel * 370
        drawing.add(String(x, 338, mode, fontSize=12))
        plot = LinePlot()
        plot.x, plot.y, plot.width, plot.height = x + 38, 85, 285, 225
        group = [r for r in rows if r["mode"] == mode]
        labels = sorted({r["k"] for r in group})
        plot.data = [[(labels.index(r["k"]), r["median_T_seconds"]) for r in group if r["n"] == n] for n in (10, 30, 100)]
        plot.xValueAxis.valueMin, plot.xValueAxis.valueMax = 0, max(1, len(labels) - 1)
        plot.xValueAxis.valueStep = 1
        plot.yValueAxis.valueMin = 0
        maximum = max(r["max_T_seconds"] for r in group)
        plot.yValueAxis.valueMax = maximum * 1.1 if maximum else 1
        span = plot.yValueAxis.valueMax - plot.yValueAxis.valueMin
        plot.xValueAxis.labelTextFormat = lambda _: ""
        plot.yValueAxis.labelTextFormat = "%.2fs"
        plot.lines[0].strokeColor = HexColor("#1f77b4"); plot.lines[1].strokeColor = HexColor("#ff7f0e"); plot.lines[2].strokeColor = HexColor("#2ca02c")
        drawing.add(plot)
        for i, k in enumerate(labels):
            drawing.add(String(x + 34 + 285 * i / max(1, len(labels) - 1), 65, f"k={k}", fontSize=8))
        for r in group:
            i = labels.index(r["k"])
            y0, y1 = plot.y + r["min_T_seconds"] * plot.height / span, plot.y + r["max_T_seconds"] * plot.height / span
            px = plot.x + plot.width * i / max(1, len(labels) - 1)
            drawing.add(Line(px, y0, px, y1, strokeColor=HexColor("#666666")))
    drawing.add(String(35, 25, "curves: N=10 blue, N=30 orange, N=100 green; HTTP elapsed is reported separately", fontSize=9))
    renderSVG.drawToFile(drawing, str(destination))


def write_markdown(rows, output, synthetic):
    marker = "SYNTHETIC FORMAT SELF-CHECK — not a benchmark measurement." if synthetic else "Prepared from completed real runs."
    header = "| mode | N | k | repeats | median T s | min–max T s | paired ΔT s (min–max) | source |\n|---|---:|---:|---:|---:|---:|---:|---|\n"
    lines = ["# Sidecar delta summary", "", marker, "", "T is `job.snapshot_ready_duration_seconds`; HTTP elapsed stays separate in CSV. No p95, capacity threshold, or crossover claim is produced. Corpus is synthetic and OS cache is uncontrolled.", "", header]
    for r in rows:
        lines.append(f"| {r['mode']} | {r['n']} | {r['k']} | 5 | {r['median_T_seconds']:.3f} | {r['min_T_seconds']:.3f}–{r['max_T_seconds']:.3f} | {r['paired_median_delta_seconds']:.3f} ({r['paired_min_delta_seconds']:.3f}–{r['paired_max_delta_seconds']:.3f}) | `{r['source']}` |\n")
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def aggregate(inputs, output, allow_synthetic=False):
    loaded = [read_result(item, allow_synthetic) for item in inputs]
    if {cell for cell, *_ in loaded} != CELLS or len(loaded) != 9:
        fail("inputs must contain exactly the nine N=10/30/100 × docs/code/mixed families")
    output.mkdir(parents=allow_synthetic, exist_ok=allow_synthetic)
    rows, synthetic = [], any(data.get("synthetic_fixture") for _, data, _, _ in loaded)
    for cell, data, by_k, source in loaded:
        rows.extend(rows_for(cell, by_k, source, bool(data.get("synthetic_fixture"))))
    fields = list(rows[0])
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    write_markdown(rows, output, synthetic); write_svg(rows, output / "summary.svg", synthetic)


def selfcheck(root):
    if root.exists(): fail(f"selfcheck root already exists: {root}")
    inputs = []
    for n, mode in sorted(CELLS):
        samples = [{"repeat": repeat, "k": k, "valid": True, "restore_verified": True,
                    "elapsed_seconds": 9 + k / 10, "job": {"snapshot_ready_duration_seconds": 1 + n / 100 + k / 1000 + repeat / 10000}}
                   for repeat in range(5) for k in K_BY_N[n]]
        path = root / "inputs" / f"{mode}-n{n}" / "result.json"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"status": "completed", "synthetic_fixture": True,
                                    "parameters": {"n": n, "mode": mode, "k": K_BY_N[n], "repeats": 5}, "samples": samples}), encoding="utf-8")
        inputs.append(str(path))
    aggregate(inputs, root / "output", allow_synthetic=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--inputs", nargs="+"); parser.add_argument("--output", type=Path); parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()
    if args.selfcheck:
        if args.inputs or args.output: fail("--selfcheck takes no inputs or output")
        selfcheck(Path("sandbox/summary-selfcheck")); return
    if not args.inputs or args.output is None: fail("--inputs and --output are required")
    aggregate(args.inputs, args.output)


if __name__ == "__main__":
    main()
