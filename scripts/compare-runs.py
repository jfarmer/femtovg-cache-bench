"""Compare a full rerun with historical counts, renderer hashes, and timing summaries."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import statistics
from pathlib import Path

from common import ROOT


def read_json(path):
    return json.loads(path.read_text())


def records(path):
    with gzip.open(path, "rt") as source:
        for line in source:
            yield json.loads(line)


def indexed(path, fields):
    output = {}
    for record in records(path):
        key = tuple(record[field] for field in fields)
        if key in output:
            raise RuntimeError(f"duplicate run identity: {key}")
        output[key] = record
    return output



def median_interval(values, confidence=.95):
    """Conservative two-sided sign/order-statistic interval for a population median."""
    ordered = sorted(values)
    n = len(ordered)
    candidates = [(k, 1 - 2 * sum(math.comb(n, j) for j in range(k)) / 2**n)
                  for k in range(1, (n + 1) // 2 + 1)]
    eligible = [(k, coverage) for k, coverage in candidates if coverage >= confidence]
    if not eligible:
        raise ValueError("too few process runs for a finite interval at the requested coverage")
    k, coverage = eligible[-1]
    return {"n": n, "median": statistics.median(ordered), "lower": ordered[k-1],
            "upper": ordered[n-k], "coverage": coverage, "requested_coverage": confidence,
            "lower_rank": k, "upper_rank": n-k+1}


def wait_summaries(data, study):
    grouped = {}
    for run in data.values():
        case = (f"{run['scenario']}/scale{run['scale']}/cap{run['capacity']}/{run['policy']}"
                if study else f"{run['scenario']}/{run['policy']}")
        frames = run["frames"][10:] if study else [f for f in run["frames"] if f["phase"] == "measured"]
        waits = sorted(f["completed_ms"] - f["cpu_ms"] for f in frames)
        quantiles = {f"completion_wait_p{p}_ms": waits[math.ceil(p / 100 * len(waits)) - 1]
                     for p in (50, 95, 99)}
        grouped.setdefault(case, []).append(quantiles)
    return {case: {metric: statistics.median(run[metric] for run in runs)
                   for metric in runs[0]} for case, runs in grouped.items()}


def paired_extremes(old, new):
    """Show both measurements for the slowest frames in either dataset."""
    result = {}
    for label, data in (("old", old), ("new", new)):
        slowest = sorted(((f["completed_ms"], key, index)
                          for key, run in data.items() for index, f in enumerate(run["frames"])),
                         reverse=True)[:3]
        result[label] = [{"run": key, "frame": index, "phase": data[key]["frames"][index]["phase"],
                          "old_completed_ms": old[key]["frames"][index]["completed_ms"],
                          "new_completed_ms": new[key]["frames"][index]["completed_ms"]}
                         for _, key, index in slowest]
    return result


def compare_gpu(old_dir, new_dir, study):
    filename = "gpu.jsonl.gz" if study else "runs.jsonl.gz"
    fields = ("scenario", "scale", "capacity", "policy", "seed") if study else ("scenario", "policy", "round")
    old = indexed(old_dir / filename, fields)
    new = indexed(new_dir / filename, fields)
    expected_runs = 280 if study else 240
    expected_frames = 100 if study else 106
    if old.keys() != new.keys() or len(new) != expected_runs:
        raise RuntimeError(f"missing or unexpected run identities in {filename}")
    mismatches = []
    diagnostics = {"live_pipelines": [], "metal_resource_bytes": []}
    flushes = 0
    adapters = set()
    for key, after in new.items():
        before = old[key]
        adapters.add(after["adapter"])
        if len(before["frames"]) != expected_frames or len(after["frames"]) != expected_frames:
            raise RuntimeError(f"unexpected frame count: {key}")
        if study and before["model_stats"] != after["model_stats"]:
            mismatches.append({"run": key, "field": "model_stats"})
        for index, (a, b) in enumerate(zip(before["frames"], after["frames"])):
            # Timing, memory accounting and delayed GPU-object destruction can vary.
            # Logical phases, materializations and cache residency must match exactly.
            def counts(frame):
                return (frame["phase"], [(f.get("name"), f["created"], f["retained"]) for f in frame["flushes"]])
            for field in diagnostics:
                if a[field] != b[field]:
                    diagnostics[field].append({"run": key, "frame": index, "old": a[field], "new": b[field]})
            flushes += len(b["flushes"])
            if counts(a) != counts(b):
                mismatches.append({"run": key, "frame": index, "old": counts(a), "new": counts(b)})
    old_meta = read_json(old_dir / "metadata.json")
    new_meta = read_json(new_dir / "metadata.json")
    if study:
        renderer_match = old_meta["renderer_sha256"] == new_meta["renderer_sha256"]
    else:
        renderer_match = {p: v["renderer_sha256"] for p, v in old_meta["binaries"].items()} == {
            p: v["renderer_sha256"] for p, v in new_meta["binaries"].items()}
    old_summary = read_json(old_dir / "summary.json")
    new_summary = read_json(new_dir / "summary.json")
    if old_summary.keys() != new_summary.keys():
        raise RuntimeError("summary case sets differ")
    old_wait = wait_summaries(old, study)
    new_wait = wait_summaries(new, study)
    rows = {}
    intervals = {}
    flags = []
    for case, item in new_summary.items():
        a = {**old_summary[case]["medians"], **old_wait[case]}
        b = {**item["medians"], **new_wait[case]}
        row = {}
        for metric in sorted(a.keys() & b.keys()):
            row[metric] = {"old": a[metric], "new": b[metric],
                           "ratio": b[metric] / a[metric] if a[metric] else None}
        rows[case] = row
        intervals[case] = {
            metric: {"old": median_interval([run[metric] for run in old_summary[case]["per_run"]]),
                     "new": median_interval([run[metric] for run in item["per_run"]])}
            for metric in sorted(a.keys() & b.keys())
            if metric.startswith(("cpu", "completed")) and "p" in metric
        }
        for metric, values in row.items():
            if metric.startswith(("completed", "cpu")) and "p" in metric:
                ratio = values["ratio"]
                if ratio is not None and (ratio > 1.5 or ratio < 2/3) and abs(values["new"] - values["old"]) >= .25:
                    flags.append({"case": case, "metric": metric, **values})
    return {"runs": len(new), "frames": len(new) * expected_frames, "flushes": flushes,
            "operation_mismatches": mismatches, "diagnostic_mismatches": diagnostics, "renderer_hashes_match": renderer_match,
            "archive_hashes_match": old_meta["archive_sha256"] == new_meta["archive_sha256"],
            "platform_match": old_meta["platform"] == new_meta["platform"],
            "rustc_match": old_meta["rustc"] == new_meta["rustc"],
            "adapters": sorted(adapters), "timing_flags": flags, "cases": rows, "median_intervals": intervals,
            "paired_extreme_frames": paired_extremes(old, new)}


def compare_simulation(old_path, new_path):
    count = 0
    mismatches = []
    for old, new in itertools.zip_longest(records(old_path), records(new_path)):
        count += 1
        if old != new:
            mismatches.append(count)
    if count != 7200:
        raise RuntimeError(f"expected 7,200 simulations; found {count}")
    return {"records": count, "mismatching_records": mismatches}


def markdown(report):
    lines = ["# Full rerun comparison", "",
             "Old → new values below are medians of per-process statistics, following the original summaries. "
             "All cold/warmup frames remain in the raw files and are included in operation-count checks. "
             "Completion wait is calculated per frame as completed time minus CPU time before taking quantiles; "
             "it includes the device poll/wait interval and scheduling, not just GPU execution.", ""]
    for name in ("pr343", "policy-study"):
        section = report[name]
        lines += [f"## {name}", "",
                  f"Compared {section['runs']} processes, {section['frames']:,} frames, and {section['flushes']:,} flushes. "
                  f"Operation mismatches: {len(section['operation_mismatches'])}. "
                  f"Renderer hashes match: {section['renderer_hashes_match']}.", "",
                  "| Case | Creations/frame | Completed p50 (ms) | Completed p95 (ms) | Completed p99 (ms) | Completion wait p95 (ms) | Peak RSS (MiB) |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for case, row in sorted(section["cases"].items()):
            def pair(metric):
                value = row[metric]
                return f"{value['old']:.3f} → {value['new']:.3f}"
            prefix = "completed_ms_" if name == "policy-study" else "completed_"
            suffix = "" if name == "policy-study" else "_ms"
            metrics = ["created_per_frame", *(prefix + p + suffix for p in ("p50", "p95", "p99")), "completion_wait_p95_ms", "peak_rss_mib"]
            lines.append(f"| {case} | " + " | ".join(pair(m) for m in metrics) + " |")
        lines.append("")
    simulation = report["simulation"]
    lines += ["## CPU simulation", "",
              f"Compared {simulation['records']:,} records; {len(simulation['mismatching_records'])} differed.", "",
              "## Timing review flags", "",
              "The JSON report flags per-case timing statistics whose ratio is outside [2/3, 1.5] "
              "and whose absolute difference is at least 0.25 ms. This is an investigation aid, "
              "not a statistical significance test or an automatic benchmark failure. "
              "Memory and timing differences require interpretation; count or renderer mismatches fail the check.", ""]
    for name in ("pr343", "policy-study"):
        lines.append(f"- {name}: {len(report[name]['timing_flags'])} timing statistics flagged.")
    return "\n".join(lines) + "\n"


def uncertainty_markdown(report):
    lines = ["# Confidence intervals for process-level medians", "",
             "Each row uses ten separate-process summaries, not individual frames as independent samples. "
             "The point estimate is the median of the ten process-level p50 values; the interval "
             "targets the population median of that process-level statistic under repeated comparable runs.", "",
             "We use the narrowest equal-tailed order-statistic interval with coverage at least 95%. "
             "For n=10, this is [second-smallest, second-largest], with binomial coverage "
             "1 − 2(1 + 10)/2¹⁰ = 97.8515625%. No normal approximation or bootstrap is used. "
             "Intervals for the median of process-level p95/p99 and CPU timing statistics are also in comparison.json.", "",
             "The guarantee assumes independent, identically distributed process summaries and a continuous "
             "distribution. Shared driver caches, thermal drift and background load can violate those assumptions. "
             "These are conditional, pointwise intervals for this workload and environment, not simultaneous "
             "coverage across all rows or a statement about other machines. Interval overlap is not a test "
             "of the difference between policies. p95 latency and a median confidence interval describe different things.", "",
             "See [NIST's median confidence-limit discussion](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm) "
             "for the binomial/order-statistic construction; we retain the conservative discrete bounds rather than interpolate.", ""]
    for name in ("pr343", "policy-study"):
        metric = "completed_ms_p50" if name == "policy-study" else "completed_p50_ms"
        lines += [f"## {name}", "", "All values in milliseconds; brackets contain the 97.85% median interval.", "",
                  "| Case | Original median [interval] | Rerun median [interval] |",
                  "| --- | ---: | ---: |"]
        for case, metrics in sorted(report[name]["median_intervals"].items()):
            def cell(which):
                value = metrics[metric][which]
                return f"{value['median']:.3f} [{value['lower']:.3f}, {value['upper']:.3f}]"
            lines.append(f"| {case} | {cell('old')} | {cell('new')} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="repository-relative directory containing pr343/ and policy-study/")
    parser.add_argument("--baseline", type=Path, default=Path("results"))
    parser.add_argument("--out", type=Path, required=True, help="new repository-relative report directory")
    args = parser.parse_args()
    for path in (args.candidate, args.baseline, args.out):
        if path.is_absolute() or not (ROOT / path).resolve().is_relative_to(ROOT):
            parser.error("paths must be relative to and contained within the repository")
    old, new = ROOT / args.baseline, ROOT / args.candidate
    report = {name: compare_gpu(old / name, new / name, name == "policy-study")
              for name in ("pr343", "policy-study")}
    report["simulation"] = compare_simulation(old / "policy-study/simulation.jsonl.gz", new / "policy-study/simulation.jsonl.gz")
    report["inputs"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for base in (old, new) for path in sorted(base.glob("*/*"))
                        if path.name in ("metadata.json", "summary.json", "runs.jsonl.gz", "gpu.jsonl.gz", "simulation.jsonl.gz")}
    report["baseline"] = str(args.baseline)
    report["candidate"] = str(args.candidate)
    output = ROOT / args.out
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "comparison.md").write_text(markdown(report))
    (output / "uncertainty.md").write_text(uncertainty_markdown(report))
    failed = bool(report["simulation"]["mismatching_records"])
    for name in ("pr343", "policy-study"):
        section = report[name]
        failed |= bool(section["operation_mismatches"]) or not section["renderer_hashes_match"] or not section["archive_hashes_match"]
        print(f"{name}: {len(section['operation_mismatches'])} operation mismatches; "
              f"{len(section['timing_flags'])} timing statistics to review")
    print(f"Comparison written to {args.out}")
    if failed:
        raise SystemExit("Reproduction check failed: inspect comparison.json")


if __name__ == "__main__":
    main()
