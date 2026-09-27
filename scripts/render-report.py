"""Generate the standalone PR report and complete tables from a finished primary run."""
import argparse
from collections import Counter
import csv
import gzip
import importlib.util
import json
import math
from pathlib import Path
import statistics
import tempfile
import shutil

from common import ROOT


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def records(path):
    with gzip.open(path, "rt") as source:
        return [json.loads(line) for line in source]


def quantile(values, p):
    return sorted(values)[math.ceil(len(values) * p) - 1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    args = parser.parse_args()
    if args.data.is_absolute() or not (ROOT / args.data).resolve().is_relative_to(ROOT):
        parser.error("data must be repository-relative")
    data = ROOT / args.data
    meta = json.loads((data / "metadata.json").read_text())
    if "finished_utc" not in meta:
        raise RuntimeError("measurement campaign did not finish")
    direct = module("femtovg-cache-synthetic")
    study = module("femtovg-policy-study")
    stats = module("compare-runs")
    a = records(data / "direct/runs.jsonl.gz")
    b = records(data / "policies/gpu.jsonl.gz")
    pa = records(data / "direct/priming.jsonl.gz")
    pb = records(data / "policies/priming.jsonl.gz")
    if len(a) != 240 or len(b) != 320 or len(pa) != 48 or len(pb) != 64:
        raise RuntimeError("incomplete primary dataset")
    with gzip.open(data / "policies/simulation.jsonl.gz", "rt") as raw:
        if sum(1 for _ in raw) != 7200:
            raise RuntimeError("incomplete CPU sweep")
    expected_direct = {(scenario, policy) for scenario in direct.SCENARIOS for policy in DIRECT_POLICIES}
    expected_study = {(scenario, scale, capacity, policy) for scenario, scale, capacity in meta["study_cases"] for policy in meta["study_policies"]}
    if Counter((r["scenario"], r["policy"]) for r in a) != Counter({case: 10 for case in expected_direct}):
        raise RuntimeError("direct case coverage differs from the protocol")
    if Counter((r["scenario"], r["scale"], r["capacity"], r["policy"]) for r in b) != Counter({case: 10 for case in expected_study}):
        raise RuntimeError("policy case coverage differs from the protocol")
    for scenario, scale, capacity, policy in expected_study:
        seeds = [r["seed"] for r in b if (r["scenario"], r["scale"], r["capacity"], r["policy"]) == (scenario, scale, capacity, policy)]
        if sorted(seeds) != list(range(1, 11)):
            raise RuntimeError("policy seeds are missing or duplicated")
    for run in b:
        if sum(f["created"] for frame in run["frames"] for f in frame["flushes"]) != run["model_stats"]["misses"]:
            raise RuntimeError("GPU materialization totals differ from model totals")
    direct_summary = direct.summarize(a)
    if direct_summary != json.loads((data / "direct/summary.json").read_text()):
        raise RuntimeError("direct summary does not reproduce")
    saved_policy_summary = json.loads((data / "policies/summary.json").read_text())
    with tempfile.TemporaryDirectory(prefix="femtovg-report-") as scratch:
        scratch = Path(scratch)
        shutil.copyfile(data / "policies/gpu.jsonl.gz", scratch / "gpu.jsonl.gz")
        policy_summary = study.summarize(scratch)
    if policy_summary != saved_policy_summary:
        raise RuntimeError("policy summary does not reproduce")
    direct_profiles = {}
    for run in a:
        profile = [[(f["created"], f["retained"]) for f in frame["flushes"]] for frame in run["frames"]]
        key = (run["scenario"], run["policy"])
        if key in direct_profiles and profile != direct_profiles[key]:
            raise RuntimeError("direct count profiles vary across repeated runs")
        direct_profiles[key] = profile
    evidence = {"source": meta["source"], "direct_processes": len(a), "study_processes": len(b),
                "priming_processes": len(pa)+len(pb), "simulation_records": 7200,
                "gpu_frames": sum(len(r["frames"]) for r in a+b),
                "gpu_flushes": sum(len(f["flushes"]) for r in a+b for f in r["frames"]),
                "median_intervals": {}, "paired_ratios": {}, "priming": {}}
    table = ["# Complete primary results", "", "All timings are milliseconds. Median intervals use ten process-level summaries. "
             "p95/p99 are medians of within-process quantiles; RSS is process lifetime peak RSS. "
             "Resident entries are end-of-last-flush counts for direct runs and peak model residency for the study. "
             "Intervals are conservative pointwise 97.85% order-statistic intervals under independent, comparable-run assumptions.", ""]
    for name, summary in (("direct", direct_summary), ("policies", policy_summary)):
        table += [f"## {name}", "", "| Case / policy | Creations/frame | Median [interval] | p95 | p99 | Resident entries | Peak RSS (MiB) |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for case, entry in sorted(summary.items()):
            m = entry["medians"]
            prefix, suffix = ("completed_", "_ms") if name == "direct" else ("completed_ms_", "")
            metric = prefix + "p50" + suffix
            ci = stats.median_interval([r[metric] for r in entry["per_run"]])
            evidence["median_intervals"][f"{name}/{case}"] = ci
            resident = (statistics.median(r["retained_after_flush"][-1] for r in entry["per_run"])
                        if name == "direct" else m["peak_resident"])
            table.append(f"| {case} | {m['created_per_frame']:.2f} | {ci['median']:.3f} [{ci['lower']:.3f}, {ci['upper']:.3f}] | "
                         f"{m[prefix+'p95'+suffix]:.3f} | {m[prefix+'p99'+suffix]:.3f} | {resident:g} | {m['peak_rss_mib']:.2f} |")
        table.append("")
    # Block by measurement round; this estimates the median of within-round ratios.
    ratios_table = ["| Working set | Proposed / #343 median-latency ratio [interval] |", "| --- | ---: |"]
    for scenario in direct.SCENARIOS:
        ratios = []
        for index in range(1, 11):
            def latency(policy):
                r = next(r for r in a if r["scenario"] == scenario and r["policy"] == policy and r["round"] == index)
                return quantile([f["completed_ms"] for f in r["frames"] if f["phase"] == "measured"], .5)
            ratios.append(latency("flush-lru64") / latency("pr343"))
        ci = stats.median_interval(ratios)
        evidence["paired_ratios"][scenario] = {**ci, "per_round_ratios": ratios}
        ratios_table.append(f"| {scenario} | {ci['median']:.3f} [{ci['lower']:.3f}, {ci['upper']:.3f}] |")
    table += ["## Per-round effect estimates", "", *ratios_table, "",
              "These are medians of per-round proposed/#343 p50 ratios, not ratios of aggregate medians. "
              "A ratio below one favors the proposed policy. Round pairing controls some temporal variation but does not remove shared-driver or session effects.", ""]
    priming_lines = ["# Warm-up observations", "", "Two complete passes preceded each suite; all launches explicitly unset MTL_SHADER_CACHE_SIZE. "
                     "These observations describe preparation, not verified Metal cache-hit counters. "
                     "First-frame time includes process/application-cache initialization and must not be interpreted as a pure compilation measurement.", "",
                     "| Suite / case / policy | Pass 1 first frame | Pass 2 first frame | Measured first-frame median | Measured first-frame range |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, priming, measured in (("direct", pa, a), ("policies", pb, b)):
        def key(r):
            return f"{r['scenario']}/{r['policy']}" if name == "direct" else f"{r['scenario']}/W{r['scale']}/C{r['capacity']}/{r['policy']}"
        for case in sorted({key(r) for r in measured}):
            warm = {r["priming_pass"]: r["frames"][0]["completed_ms"] for r in priming if key(r) == case}
            first = [r["frames"][0]["completed_ms"] for r in measured if key(r) == case]
            maxima = {r["priming_pass"]: max(f["completed_ms"] for f in r["frames"]) for r in priming if key(r) == case}
            phases = sorted({f["phase"] for r in measured if key(r) == case for f in r["frames"]})
            phase_peaks = {}
            for phase in phases:
                phase_peaks[phase] = {
                    "priming_max_ms_by_pass": {r["priming_pass"]: max(f["completed_ms"] for f in r["frames"] if f["phase"] == phase) for r in priming if key(r) == case},
                    "measured_process_maxima_ms": [max(f["completed_ms"] for f in r["frames"] if f["phase"] == phase) for r in measured if key(r) == case]}
            info = {"first_frame_ms_by_priming_pass": warm, "measured_first_frames_ms": first,
                    "whole_trace_priming_max_ms_by_pass": maxima, "phase_peaks": phase_peaks}
            evidence["priming"][f"{name}/{case}"] = info
            priming_lines.append(f"| {name}/{case} | {warm[1]:.2f} | {warm[2]:.2f} | {statistics.median(first):.2f} | {min(first):.2f}–{max(first):.2f} |")
    priming_lines += ["", "## Whole-trace phase peaks", "",
                     "Maximum frame time within each phase, including late scan/transition frames. The measured column is the median of ten process maxima. "
                     "These maxima are diagnostics, not estimates of a population tail percentile.", "",
                     "| Suite / case / policy / phase | Pass 1 max (ms) | Pass 2 max (ms) | Measured process max median (ms) |",
                     "| --- | ---: | ---: | ---: |"]
    for case, info in evidence["priming"].items():
        for phase, peaks in info["phase_peaks"].items():
            warm = peaks["priming_max_ms_by_pass"]
            priming_lines.append(f"| {case}/{phase} | {warm[1]:.2f} | {warm[2]:.2f} | {statistics.median(peaks['measured_process_maxima_ms']):.2f} |")
    cold_lines = ["# Matched-work Metal cache-control check", "", "The actual proposed and upstream binaries create 17 pipelines on the first frame. "
                  "Three launches per condition diagnose the setting's effect; these are not precise policy-ranking estimates. "
                  "The variable is explicitly unset or set to zero. No persistent-cache deletion is performed.", "",
                  "| Policy | Cache-size setting | First-frame median (ms) | Measured-frame median (ms) |", "| --- | --- | ---: | ---: |"]
    cold_file = data / "cold-control/runs.jsonl.gz"
    if cold_file.exists():
        cold = records(cold_file)
        if len(cold) != 12:
            raise RuntimeError("incomplete cold-control check")
        evidence["cold_control"] = {}
        for policy in ("upstream", "flush-lru64"):
            profiles = [[[ (f["created"], f["retained"]) for f in frame["flushes"]] for frame in r["frames"]]
                        for r in cold if r["policy"] == policy]
            if any(profile != profiles[0] for profile in profiles[1:]):
                raise RuntimeError("Metal setting changed policy work")
            for setting in (None, "0"):
                runs = [r for r in cold if r["policy"] == policy and r["cache_size"] == setting]
                first = [r["frames"][0]["completed_ms"] for r in runs]
                measured = [statistics.median(f["completed_ms"] for f in r["frames"] if f["phase"] == "measured") for r in runs]
                evidence["cold_control"][f"{policy}/{setting}"] = {"first_frames_ms": first, "measured_ms": measured}
                cold_lines.append(f"| {policy} | {'unset' if setting is None else '0'} | {statistics.median(first):.2f} | {statistics.median(measured):.3f} |")
    analysis = data / "analysis"
    analysis.mkdir(exist_ok=True)
    with (analysis / "timing.csv").open("w", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(("suite", "case", "metric", "median_ms", "interval_lower_ms", "interval_upper_ms", "coverage"))
        for suite, summary in (("direct", direct_summary), ("policies", policy_summary)):
            for case, entry in sorted(summary.items()):
                for metric in entry["medians"]:
                    if metric.startswith(("cpu_", "completed_")):
                        ci = stats.median_interval([r[metric] for r in entry["per_run"]])
                        writer.writerow((suite, case, metric, ci["median"], ci["lower"], ci["upper"], ci["coverage"]))
    (analysis / "tables.md").write_text("\n".join(table)+"\n")
    (analysis / "priming.md").write_text("\n".join(priming_lines)+"\n")
    (analysis / "cold-control.md").write_text("\n".join(cold_lines)+"\n")
    (analysis / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True)+"\n")
    link = args.data.as_posix()
    adapter_name = a[0]["adapter"].split('name: "')[1].split('"')[0]
    backend = a[0]["adapter"].split("backend: ")[1].split(",")[0].split("}")[0].strip()
    boundary = direct_summary["65/flush-lru64"]["medians"]
    sweep = direct_summary["65/pr343"]["medians"]
    report = [
        "# FemtoVG WGPU pipeline-cache evaluation", "",
        "The proposed cache avoids rebuilding an entire working set after a small intervening flush. "
        f"At 65 pipeline states, it creates **{boundary['created_per_frame']:.0f} pipelines per frame instead of "
        f"{sweep['created_per_frame']:.0f}** with [PR #343](https://github.com/femtovg/femtovg/pull/343). "
        f"Median completed-frame time falls from **{sweep['completed_p50_ms']:.2f} to {boundary['completed_p50_ms']:.2f} ms** on {adapter_name}/{backend}.", "",
        "The tradeoff is a soft capacity target: pipelines used by one flush remain protected even above 64 entries. "
        "These synthetic tests show the benefit and its limits. They do not estimate application-wide speedups or establish an optimal capacity.", "",
        "## What changes", "",
        "| Implementation | Eviction after a flush |",
        "| --- | --- |",
        "| Upstream | Remove every pipeline unused by that flush. |",
        "| #343 | Apply that sweep only when the cache exceeds 64 entries. |",
        "| Proposed | Above 64 entries, remove the oldest pipelines unused by that flush. |", "",
        "A clear-only flush can therefore discard the preceding draw's pipelines on upstream and, above capacity, on #343. "
        "The proposal trims older entries while preserving the current flush's working set. Recency is measured in flushes; ties within a flush have no specified order.", "",
        f"The direct tests use the actual PR renderer at `{meta['source']['candidate']['commit'][:7]}`, based on upstream "
        f"`{meta['source']['base']['commit'][:7]}`. The build verifies the renderer before adding counters. "
        "All variants share the base, dependency lockfile, features and release settings. "
        "[Full source pins and checksums](vendor/report-source.json).", "",
        "## Direct comparison", "",
        "The proposal reduces repeated creation above #343's threshold; it does not eliminate capacity limits. "
        "At 65, 80 and 129 states, #343 recreates the whole set each frame. The proposal recreates 2, 17 and 66 pipelines respectively. "
        "Strict LRU 128 holds the smaller sets but recreates all 129 pipelines in the cyclic 129-state case.", "",
        "Each numbered workload draws N−1 blend states, then issues a separate clear flush. N includes the clear pipeline. "
        "The mixed workload alternates glyph-atlas, clipped-layer, blur, screen and clear operations. "
        "Strict LRU 128 has twice the proposal's retention target.", "",
        "Times below are milliseconds, aggregated over ten processes per case. Completed time includes CPU work and the GPU completion wait. "
        "Bracketed values are intervals for the median under the assumptions described in [Measurement and uncertainty](#measurement-and-uncertainty).", "",
        "<details>", "<summary>All direct results: creations, median intervals and p95</summary>", "",
        "| Workload | Policy | Creations/frame | Median [interval] (ms) | p95 (ms) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for scenario in ("63", "64", "65", "80", "129", "mixed"):
        for policy in DIRECT_POLICIES:
            case = f"{scenario}/{policy}"
            m = direct_summary[case]["medians"]
            ci = evidence["median_intervals"][f"direct/{case}"]
            label = {"upstream": "Upstream", "pr343": "#343", "flush-lru64": "Proposed 64", "strict-lru128": "Strict LRU 128"}[policy]
            report.append(f"| {scenario} | {label} | {m['created_per_frame']:.0f} | {ci['median']:.3f} [{ci['lower']:.3f}, {ci['upper']:.3f}] | {m['completed_p95_ms']:.3f} |")
    report += ["", "</details>", "",
               f"[Complete tables, including p99 and within-round ratios]({link}/analysis/tables.md). "
               "Ratios compare process medians within the same round; they are not ratios of aggregate medians.", ""]

    confirmation = ROOT / "results/confirmation-d5241b9"
    if (confirmation / "metadata.json").exists():
        confirmation_meta = json.loads((confirmation / "metadata.json").read_text())
        if confirmation_meta["source"] == meta["source"]:
            repeat = json.loads((confirmation / "summary.json").read_text())
            paired = json.loads((confirmation / "paired-ratios.json").read_text())
            report += ["## Randomized confirmation", "",
                       f"**At 65 states, the proposal was faster in {sum(value < 1 for value in paired['65'])} of {len(paired['65'])} pairs.** "
                       "A separate run compared the proposal with #343 in twenty adjacent pairs per workload. "
                       "Policy order was randomized and balanced before measurement.", "",
                       "| Workload | #343 median / p95 (ms) | Proposed median / p95 (ms) |",
                       "| --- | ---: | ---: |"]
            for case in ("64", "65", "mixed"):
                before = repeat[f"{case}/pr343"]["medians"]
                after = repeat[f"{case}/flush-lru64"]["medians"]
                report.append(f"| {case} | {before['completed_p50_ms']:.3f} / {before['completed_p95_ms']:.3f} | {after['completed_p50_ms']:.3f} / {after['completed_p95_ms']:.3f} |")
            report += ["",
                       f"Median within-pair proposed/#343 ratios are {statistics.median(paired['64']):.3f} at 64 states and "
                       f"{statistics.median(paired['mixed']):.3f} for mixed operations. "
                       "Those cases show no obvious regression; they do not establish statistical equivalence.", "",
                       "All 120 measured and 12 priming runs match the original creation/residency profiles. "
                       "The repeat is reported separately. "
                       "[Protocol, individual pairs and raw data](results/confirmation-d5241b9/README.md).", ""]

    report += ["## Other retention policies", "",
               "No policy wins across all tested access patterns. The main tradeoffs are capacity, scan resistance and sensitivity to flush boundaries.", "",
               "| Policy | Observed tradeoff |", "| --- | --- |",
               "| Flush-aware | Reuses a large flush's working set by exceeding the target. Splitting the same requests across smaller flushes can lose that advantage. |",
               "| Strict LRU (`lru` crate) | Enforces an entry limit. Cyclic access just beyond capacity can miss on every request. |",
               "| S3-FIFO | Protects hot entries during scans, but takes longer to adapt to switching sets and needs admission/ghost metadata. |",
               "| Retain everything | Shows available reuse, with continuing growth under streams of new states. |", "",
               "**The study's `flush-lru` is a model variant, not the exact PR implementation.** "
               "It orders accesses within a flush; the PR uses flush stamps. The direct comparison and confirmation above test the actual PR.", "",
               "W is workload scale and C is capacity. Cycle/shuffle-plus uses W+1 states. Hot-scan interleaves a hot set with new states; switch alternates disjoint sets. "
               "Batch-single and batch-split issue the same requests with different flush boundaries. "
               "The CPU sweep additionally varies capacity from 32 to 512 for each fixed trace.", "",
               "<details>", "<summary>All policy-study results: timing, creation counts and memory</summary>", "",
               "| Case / policy | Creations/frame | Median (ms) | p95 (ms) | Peak entries | Peak RSS (MiB) |",
               "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for case, entry in sorted(policy_summary.items()):
        m = entry["medians"]
        report.append(f"| {case} | {m['created_per_frame']:.2f} | {m['completed_ms_p50']:.3f} | {m['completed_ms_p95']:.3f} | {m['peak_resident']:.0f} | {m['peak_rss_mib']:.2f} |")
    report += ["", "</details>", "",
               "Even unlimited retention cannot avoid creating pipelines for never-repeated states. "
               "The results support the proposed fix, but leave the policy and capacity open to maintainer preferences.", "",
               "## Measurement and uncertainty", "",
               f"**Setup:** {adapter_name}/{backend}; {meta['platform']}; {meta['rustc'].splitlines()[0]}. "
               "The 64×64 RGBA8 target emphasizes pipeline management costs.", "",
               "| Experiment | Measured processes | Frames summarized per process |",
               "| --- | ---: | --- |",
               f"| Direct comparison | {len(a)}; 10 per case | 100, after one initial and five warmup frames |",
               f"| Policy study | {len(b)}; 10 per case | 90, from frames 10–99 |",
               "| Confirmation | 120; 20 per case | 100, after one initial and five warmup frames |", "",
               "The main campaign rotates workload/policy order and includes 7,200 CPU simulations. Only shuffled traces vary with seed. "
               "Scans and transitions remain in the measured set. No outliers are removed.", "",
               "**Timing:** completed-frame time includes command construction, encoding, submission and the GPU wait. CPU time stops before that wait. "
               "Each process contributes nearest-rank quantiles; tables report their medians across processes. "
               "With 90 measured frames, the study's p99 is effectively the process maximum.", "",
               "**Intervals:** the second-smallest through second-largest of ten process medians gives nominal 97.85% coverage under independent, identically distributed observations. "
               "These are pointwise intervals. Shared cache state and observed drift make the independence assumptions uncertain. "
               "They do not describe variability across machines. "
               "[Interval method](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).", "",
               f"[Full protocol](docs/report-protocol.md) and [measurement metadata]({link}/metadata.json).", "",
               "## Metal cache controls", "",
               "**Priming reduces first-use cost but cannot guarantee a warm driver cache.** "
               "Before each suite, two complete workload passes run with `MTL_SHADER_CACHE_SIZE` unset. "
               "Measured processes start with empty FemtoVG caches; later Metal cache eviction or invalidation is uncontrolled.", "",
               "For example, the first LRU hot-scan priming pass reached "
               f"{evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][1]:.2f} ms in a scan frame; "
               f"the second reached {evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][2]:.2f} ms. "
               f"[Priming observations]({link}/analysis/priming.md).", ""]
    if "cold_control" in evidence:
        report += ["**The cache override slowed startup similarly for both implementations.** "
                   "A separate diagnostic created 17 pipelines on the first frame in each case:", "",
                   "| `MTL_SHADER_CACHE_SIZE` | Upstream first-frame median (ms) | Proposed first-frame median (ms) |",
                   "| --- | ---: | ---: |"]
        for setting in ("None", "0"):
            before = statistics.median(evidence["cold_control"][f"upstream/{setting}"]["first_frames_ms"])
            after = statistics.median(evidence["cold_control"][f"flush-lru64/{setting}"]["first_frames_ms"])
            report.append(f"| {'Unset' if setting == 'None' else '`0`'} | {before:.2f} | {after:.2f} |")
        report += ["", "Creation and retention counts were unchanged across settings. This supports separating driver startup cost from cache-policy behavior. "
                   "The undocumented override is not a verified global reset; later creations can still benefit from reuse. "
                   f"These three-launch medians are diagnostic, not an equivalence test. [Full check]({link}/analysis/cold-control.md).", ""]
    report += ["**Timing drift remained after priming.** At 65 states, #343's process medians ranged from "
               f"{min(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} to "
               f"{max(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} ms. "
               "Several slower processes occurred early in the campaign. Their cause is unresolved. "
               "All were retained; small timing differences at equal creation counts should not be treated as a reliable ranking.", "",
               "## Validation and memory limits", "",
               f"The main campaign records {evidence['gpu_frames']:,} frames and {evidence['gpu_flushes']:,} flushes, excluding priming and the Metal diagnostic.", "",
               "- Direct boundary tests assert the initial pipeline count. Creation/residency profiles match across repeated runs.",
               "- Every policy-study GPU flush checks creation and retention against the CPU model. WGPU validation errors fail the run.",
               "- These checks cover cache behavior and GPU execution. They do not compare rendered pixels.", "",
               "**Entry counts and process memory measure different things.** RSS and physical footprint include setup, cold work and, in the policy study, a preliminary CPU simulation. "
               "Metal resource counters omit private compiler/driver memory. Neither measure gives a reliable bytes-per-pipeline estimate.", "",
               "## Reproduce and inspect", "",
               "The repository contains pinned sources, patches, scripts and raw results. A fresh run needs Rust, Python, Git and a working GPU backend. "
               "The Metal diagnostic runs only on macOS.", "",
               "```sh", "python3 scripts/run-report.py --out runs/my-pr-report", "python3 scripts/report-sanity.py runs/my-pr-report",
               "python3 scripts/render-report.py runs/my-pr-report", "```", "",
               "The final command regenerates this report and its analysis from saved data. The published confirmation is included separately when its source pins match.", "",
               f"- [Full tables]({link}/analysis/tables.md), [timing intervals]({link}/analysis/timing.csv), and [analysis JSON]({link}/analysis/evidence.json).",
               f"- Direct comparison: [raw frames]({link}/direct/runs.jsonl.gz), [summary]({link}/direct/summary.json), [priming]({link}/direct/priming.jsonl.gz).",
               f"- Policy study: [raw frames]({link}/policies/gpu.jsonl.gz), [summary]({link}/policies/summary.json), [priming]({link}/policies/priming.jsonl.gz).",
               f"- CPU sweep: [raw counts]({link}/policies/simulation.jsonl.gz), [capacity/phase summaries]({link}/policies/simulation-summary.json).",
               "- [Confirmation results and rerun commands](results/confirmation-d5241b9/README.md).",
               f"- Supporting validation: [historical sanity check]({link}/analysis/sanity.md), [extraction rerun](results/reproduction-2026-09-27/README.md), [initial Metal probe](results/metal-cache-control-probe/README.md)."]
    (ROOT / "REPORT.md").write_text("\n".join(report)+"\n")
    print(f"Generated REPORT.md and {args.data}/analysis")


DIRECT_POLICIES = ("upstream", "pr343", "flush-lru64", "strict-lru128")
if __name__ == "__main__":
    main()
