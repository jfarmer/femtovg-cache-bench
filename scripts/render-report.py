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
    report = ["# FemtoVG WGPU pipeline-cache evaluation", "",
              "This report evaluates the proposed flush-aware pipeline cache against upstream behavior, [PR #343](https://github.com/femtovg/femtovg/pull/343)'s conditional sweep, and alternative retention policies. "
              "The primary evidence is an explicitly primed measurement campaign on the PR's current upstream base.", "",
              "## Proposed change and scope", "",
              f"The proposed renderer is pinned to `{meta['source']['candidate']['commit']}`; upstream is `{meta['source']['base']['commit']}`. "
              "The source archive and patch are bundled. The build verifies that the candidate renderer matches the PR revision byte-for-byte before adding creation/residency counters. "
              "All variants use the same base, features, dependency lockfile and release settings.", "",
              "Upstream sweeps entries not accessed in the last flush. A separate clear-only flush can therefore evict pipelines needed by the next draw flush. "
              "PR #343 only runs that sweep above 64 entries. The proposed change stamps entries by flush and, above 64, evicts the oldest entries unused by the current flush. "
              "It protects every pipeline used in that flush: 64 is a retention target, not a hard memory bound. Ties within a flush have no specified access order.", "",
              "The direct `flush-lru64` variant is the actual proposed implementation. The broader study's `flush-lru` is a separate shared-model refinement using per-access ordering within a flush. "
              "Its numbers explore the policy family and must not be attributed byte-for-byte to the PR. Strict LRU uses the `lru` crate; S3-FIFO adds admission/ghost metadata; `retain` never evicts and is a reference, not a bounded policy.", "",
              "## Measurement method", "",
              f"{meta['platform']}; {meta['rustc'].splitlines()[0]}. GPU adapter: " + a[0]["adapter"].split('name: "')[1].split('"')[0] + ". "
              "The target is 64×64 RGBA8; the workloads stress pipeline-state management rather than fill rate. "
              "Every main launch explicitly unsets MTL_SHADER_CACHE_SIZE. Two complete workload passes precede each suite, including late scan states; priming is saved separately. "
              "Every measured process starts with an empty application cache. This is an explicit warm-up protocol, not a guarantee of every internal driver cache hit.", "",
              f"The campaign contains {len(a)} direct-comparison processes, {len(b)} shared-policy GPU processes, and 7,200 CPU simulations. "
              "Each case has ten measured processes with rotated workload/policy order. The direct suite measures 100 frames after one initial and five warmup frames. "
              "The policy study saves 100 frames and summarizes frames 10–99, retaining subsequent scans and transitions. No outliers are removed. "
              "The first ten trace seeds share the same key set; only shuffled traces change order.", "",
              "Completed time includes command construction, encoding, submissions and waiting for GPU completion. It is not a GPU timestamp or presentation latency. "
              "CPU time stops before the completion wait. Summaries take within-process nearest-rank quantiles, then the median across processes. "
              "Median intervals use process-level observations: the second-smallest through second-largest of ten give conservative 97.85% coverage under independent, identically distributed process-summary assumptions. "
              "They are pointwise intervals conditional on this setup, not cross-machine guarantees. Shared driver state and thermal/background drift can violate those assumptions. "
              "A p95 latency and a confidence interval for a median answer different questions. "
              "See [NIST on order-statistic intervals for a median](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).", "",
              f"See the [exact protocol](docs/report-protocol.md), [source pins](vendor/report-source.json), [measurement metadata]({link}/metadata.json), "
              f"[priming observations]({link}/analysis/priming.md), and [matched-work cold-start check]({link}/analysis/cold-control.md).", "",
              "## Cache controls and observed variation", "",
              "These are explicitly primed, normal-cache runs. Cache eviction or invalidation during measurement is uncontrolled; priming does not guarantee persistent warmth. "
              "The warm-up observations cover full traces, including late scan states. The first LRU hot-scan priming process has a scan-frame maximum of "
              f"{evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][1]:.2f} ms; "
              f"the second pass is {evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][2]:.2f} ms. "
              "This is observable evidence that preparation matters; it does not identify every internal cache or prove all later lookups hit.", "",
              "The matched-work diagnostic reports first-use timing for the same 17 materializations under both settings, and verifies unchanged creation/residency profiles across settings. "
              + (f"First-frame medians are {statistics.median(evidence['cold_control']['upstream/None']['first_frames_ms']):.2f} ms upstream and "
                 f"{statistics.median(evidence['cold_control']['flush-lru64/None']['first_frames_ms']):.2f} ms proposed with the override unset, versus "
                 f"{statistics.median(evidence['cold_control']['upstream/0']['first_frames_ms']):.2f} and "
                 f"{statistics.median(evidence['cold_control']['flush-lru64/0']['first_frames_ms']):.2f} ms with it set to zero. " if 'cold_control' in evidence else "The Metal-specific diagnostic was not run on this platform. ") +
              "The undocumented zero-size override is a diagnostic intervention, not a supported global reset or a guarantee that repeated creations remain cold. "
              "Subsequent frames retain within-process reuse effects. Three launches per condition do not establish precise statistical equivalence between policies.", "",
              "Some direct-comparison processes remain noticeably slower than others after priming; the raw per-process results and intervals retain that variation. "
              "For example, the 65-state #343 process medians range from "
              f"{min(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} to "
              f"{max(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} ms. "
              "Several slower direct processes occur early in the campaign. Their cause is unresolved; warming driver caches does not control all session-level timing variation. "
              "No run is dropped, and small timing differences between policies with the same creation counts should not be interpreted as a reliable ranking.", "",
              "## Actual PR: boundary and mixed-operation results", "",
              "Boundary workloads visit N−1 blend states in one draw flush, then a separate clear flush; N includes clear. "
              "The mixed workload alternates glyph-atlas rendering, clipped opacity layers, blur, screen drawing and clear. "
              "Strict LRU 128 has twice the proposed retention target; it is included as a practical alternative, not a same-capacity comparison.", "",
              "| Workload | Policy | Creations/frame | Median [interval] (ms) | p95 (ms) |", "| --- | --- | ---: | ---: | ---: |"]
    for scenario in ("63", "64", "65", "80", "129", "mixed"):
        for policy in DIRECT_POLICIES:
            case = f"{scenario}/{policy}"
            m = direct_summary[case]["medians"]
            ci = evidence["median_intervals"][f"direct/{case}"]
            label = {"upstream":"Upstream", "pr343":"#343", "flush-lru64":"Proposed 64", "strict-lru128":"Strict LRU 128"}[policy]
            report.append(f"| {scenario} | {label} | {m['created_per_frame']:.0f} | {ci['median']:.3f} [{ci['lower']:.3f}, {ci['upper']:.3f}] | {m['completed_p95_ms']:.3f} |")
    report += ["", "The proposed policy preserves cross-flush reuse below capacity and degrades more gradually for this one-large-flush/one-clear pattern above capacity. "
               "Strict LRU has a different failure mode when the cyclic working set exceeds its limit. These traces demonstrate boundaries, not their frequency in applications.", "",
               "### Within-round comparison with #343", "", *ratios_table, "",
               "Each ratio pairs the two policies within the same measurement round. These are median ratios with intervals, not ratios of aggregate medians. "
               "A value below one favors the proposal. Intervals do not establish simultaneous significance across all rows.", "",
               "## Alternative policies under changing workloads", "",
               "W is workload scale; C is capacity. A cycle/shuffle-plus trace has W+1 distinct states. The hot-scan trace revisits a small hot set around streams of new states. "
               "Switch alternates disjoint sets, while batch-single and batch-split preserve the request sequence but change flush boundaries. "
               "Equal-capacity 64 and 128 cycle/shuffle cases separate capacity from policy. The CPU sweep additionally varies capacity over 32–512 while holding each trace fixed.", "",
               "| Case / policy | Creations/frame | Median (ms) | p95 (ms) | Peak entries | Peak RSS (MiB) |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for case, entry in sorted(policy_summary.items()):
        m = entry["medians"]
        report.append(f"| {case} | {m['created_per_frame']:.2f} | {m['completed_ms_p50']:.3f} | {m['completed_ms_p95']:.3f} | {m['peak_resident']:.0f} | {m['peak_rss_mib']:.2f} |")
    report += ["", "The soft target trades bounded residency for reuse across a large flush; dividing the same requests across smaller flushes can remove that advantage. "
               "A never-repeated scan incurs compulsory misses even with unlimited retention. S3-FIFO can protect hot entries from scans but has admission/adaptation costs on changing sets. "
               "Unlimited retention demonstrates the available reuse and the accompanying growth in live objects. None of these results makes a universal case for one threshold.", "",
               "## Correctness and memory interpretation", "",
               f"The measured data contains {evidence['gpu_frames']:,} frames and {evidence['gpu_flushes']:,} flushes, excluding priming and the cold diagnostic. "
               "The direct boundary runs assert actual first-frame materializations equal the requested state count; repeated direct runs have identical creation/residency profiles. "
               "Every shared-policy GPU flush asserts that actual creations and retained entries match the CPU model, including cold and transition frames. "
               "WGPU validation errors fail the run. These checks validate policy work and execution; they do not compare rendered pixels.", "",
               "Resident/ghost counts, HAL live pipelines, process peak RSS, physical footprint and Metal allocated-resource samples describe different quantities. "
               "RSS/footprint include setup and cold work; the shared-model simulator also runs in the measured process before GPU initialization. "
               "Metal resource accounting excludes private compiler/driver memory. Do not convert these process-level differences directly into bytes per pipeline. "
               "The 90 measured frames in the study make p99 effectively a per-process maximum; all p99 values remain in the complete tables but deserve restraint.", "",
               "## Decision supported by this experiment", "",
               "The proposal addresses repeated creation caused by small intervening flushes without adding a cache dependency. The measured boundaries show where it improves over #343's conditional sweep. "
               "Its soft target and sensitivity to flush grouping are explicit costs. Strict LRU gives a hard limit, but simple cyclic traces expose its capacity cliff; S3-FIFO adds policy and metadata complexity. "
               "The policy choice remains open to realistic workload traces and maintainer preferences. This report supports the proposed mechanism and characterizes tradeoffs; it does not establish application-wide speedups or the ideal capacity for all applications.", "",
               "## Reproduction and complete evidence", "",
               "```sh", "python3 scripts/run-report.py --out runs/my-pr-report", "python3 scripts/report-sanity.py runs/my-pr-report", "python3 scripts/render-report.py runs/my-pr-report", "```", "",
               "The final command regenerates REPORT.md and the analysis files from saved data. All pinned project sources and analysis scripts are contained in this repository. "
               "A working Rust/Python/Git installation and GPU backend are required for a fresh measurement campaign. The controlled Metal diagnostic is macOS-specific.", "",
               f"- [Timing/residency tables]({link}/analysis/tables.md), [all CPU/completed quantiles and intervals]({link}/analysis/timing.csv), and [machine-readable evidence]({link}/analysis/evidence.json).",
               f"- [Direct raw frames]({link}/direct/runs.jsonl.gz) and [summary]({link}/direct/summary.json).",
               f"- [Policy-study raw frames]({link}/policies/gpu.jsonl.gz), [summary]({link}/policies/summary.json), [CPU sweep]({link}/policies/simulation.jsonl.gz), and [capacity/phase summaries]({link}/policies/simulation-summary.json).",
               f"- [Historical work/timing sanity check for this campaign]({link}/analysis/sanity.md).",
               f"- [Direct priming]({link}/direct/priming.jsonl.gz) and [policy priming]({link}/policies/priming.jsonl.gz).",
               "- [Historical extraction sanity check](results/reproduction-2026-09-27/README.md) and [initial Metal-control probe](results/metal-cache-control-probe/README.md). These support validation and do not supply the primary performance numbers above."]
    (ROOT / "REPORT.md").write_text("\n".join(report)+"\n")
    print(f"Generated REPORT.md and {args.data}/analysis")


DIRECT_POLICIES = ("upstream", "pr343", "flush-lru64", "strict-lru128")
if __name__ == "__main__":
    main()
