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
    adapter = a[0]['adapter'].split('name: "')[1].split('"')[0]
    backend = a[0]['adapter'].split('backend: ')[1].split(',')[0].split('}')[0].strip()
    before = direct_summary['65/pr343']['medians']
    after = direct_summary['65/flush-lru64']['medians']
    report = [
        '# FemtoVG WGPU pipeline-cache evaluation', '',
        '**The proposal prevents small flushes from discarding an entire cached working set.**', '',
        f"At 65 states, pipeline creations fall from **{before['created_per_frame']:.0f} to {after['created_per_frame']:.0f} per frame** "
        f"and median frame time from **{before['completed_p50_ms']:.2f} to {after['completed_p50_ms']:.2f} ms**, "
        f'compared with [PR #343](https://github.com/femtovg/femtovg/pull/343) on {adapter}/{backend}.', '',
        '**Tradeoff:** 64 entries is a retention target. A single flush can retain more. These synthetic results do not predict application-wide speedups.', '',
        '## Cache behavior', '',
        '| Implementation | Eviction after a flush |', '| --- | --- |',
        '| Upstream | Remove all pipelines unused by that flush. |',
        '| #343 | Do the same, but only above 64 entries. |',
        '| Proposed | Above 64 entries, remove oldest unused pipelines until the target is reached. Protect pipelines used by the current flush. |', '',
        'The proposal measures recency in flushes. Entries last used in the same flush have no specified eviction order.', '',
        '## Direct comparison', '',
        '**Above 64 states, the proposal rebuilds fewer pipelines than #343.**', '',
        '| States | #343 creations/frame | Proposed creations/frame |', '| ---: | ---: | ---: |',
    ]
    for scenario in ('65', '80', '129'):
        before = direct_summary[f'{scenario}/pr343']['medians']['created_per_frame']
        after = direct_summary[f'{scenario}/flush-lru64']['medians']['created_per_frame']
        report.append(f'| {scenario} | {before:.0f} | {after:.0f} |')
    report += ['', 'Strict LRU 128 avoids rebuilding the smaller sets, but rebuilds all 129 pipelines when cyclic access exceeds its capacity.', '',
               '<details>', '<summary>Full results and workload definitions</summary>', '',
               '| Workload | Operations |', '| --- | --- |',
               '| Numbered | N−1 blend states, followed by a separate clear flush. N includes the clear pipeline. |',
               '| Mixed | Glyph-atlas, clipped-layer, blur, screen and clear operations. |', '',
               'Strict LRU 128 has twice the proposed retention target.', '',
               'Times include CPU work and the GPU completion wait. Each row summarizes ten processes. Brackets give median intervals. See [measurement details](#measurement-and-validation).', '',
               '| Workload | Policy | Creations/frame | Median [interval] (ms) | p95 (ms) |',
               '| --- | --- | ---: | ---: | ---: |']
    for scenario in ('63', '64', '65', '80', '129', 'mixed'):
        for policy in DIRECT_POLICIES:
            case = f'{scenario}/{policy}'
            m = direct_summary[case]['medians']
            ci = evidence['median_intervals'][f'direct/{case}']
            label = {'upstream': 'Upstream', 'pr343': '#343', 'flush-lru64': 'Proposed 64', 'strict-lru128': 'Strict LRU 128'}[policy]
            report.append(f"| {scenario} | {label} | {m['created_per_frame']:.0f} | {ci['median']:.3f} [{ci['lower']:.3f}, {ci['upper']:.3f}] | {m['completed_p95_ms']:.3f} |")
    report += ['', f'[Additional quantiles and within-round ratios]({link}/analysis/tables.md). Ratios pair process medians within a round. They are not ratios of aggregate medians.', '', '</details>', '']

    confirmation = ROOT / 'results/confirmation-d5241b9'
    confirmed = False
    if (confirmation / 'metadata.json').exists():
        confirmation_meta = json.loads((confirmation / 'metadata.json').read_text())
        confirmed = confirmation_meta['source'] == meta['source']
    if confirmed:
        repeat = json.loads((confirmation / 'summary.json').read_text())
        paired = json.loads((confirmation / 'paired-ratios.json').read_text())
        report += ['## Confirmation', '',
                   f"**The proposal was faster in all {len(paired['65'])} randomized pairs at 65 states.**" if all(value < 1 for value in paired['65']) else
                   f"**The proposal was faster in {sum(value < 1 for value in paired['65'])} of {len(paired['65'])} randomized pairs at 65 states.**", '',
                   '| Workload | #343 median / p95 (ms) | Proposed median / p95 (ms) |', '| --- | ---: | ---: |']
        for case in ('64', '65', 'mixed'):
            before = repeat[f'{case}/pr343']['medians']
            after = repeat[f'{case}/flush-lru64']['medians']
            report.append(f"| {case} | {before['completed_p50_ms']:.3f} / {before['completed_p95_ms']:.3f} | {after['completed_p50_ms']:.3f} / {after['completed_p95_ms']:.3f} |")
        report += ['', 'At 64 states and in the mixed workload, paired results show no obvious regression. Statistical equivalence was not tested.', '',
                   '<details>', '<summary>Confirmation protocol and paired results</summary>', '',
                   '- Twenty adjacent pairs per workload, with randomized, balanced policy order fixed before measurement.',
                   f"- Median proposed/#343 paired ratios: {statistics.median(paired['64']):.3f} at 64 states. For mixed operations, the ratio is {statistics.median(paired['mixed']):.3f}.",
                   '- All 120 measured and 12 priming runs match the primary creation/residency profiles. No runs excluded.',
                   '- Results remain separate from the primary estimates.', '',
                   '[Full protocol, individual pairs and raw data](results/confirmation-d5241b9/README.md).', '', '</details>', '']

    report += ['## Other policies', '',
               '**The choice remains open: reuse, memory limits and scan resistance favor different policies.**', '',
               '| Policy | Benefit | Cost |', '| --- | --- | --- |',
               '| Flush-aware | Reuses large working sets within a flush. | Can exceed capacity. Sensitive to flush boundaries. |',
               '| Strict LRU (`lru` crate) | Hard entry limit. | Cyclic access just above capacity misses every time. |',
               '| S3-FIFO | Protects hot entries during scans. | Adapts more slowly to switching sets. Requires extra metadata. |',
               '| Retain everything | Preserves all available reuse. | Unbounded growth with new states. |', '',
               'This study uses a flush-aware model with per-access ordering. The PR uses flush stamps. Its results are in the direct comparison above.', '',
               '<details>', '<summary>Policy-study workloads and full results</summary>', '',
               'W is workload scale. C is capacity. The CPU sweep varies capacity from 32 to 512 for each fixed trace.', '',
               '| Workload | Access pattern |', '| --- | --- |',
               '| Cycle/shuffle-plus | W+1 states, in cyclic or shuffled order. |',
               '| Hot-scan | A hot set interleaved with new states. |',
               '| Switch | Alternating disjoint sets. |',
               '| Batch-single / batch-split | Identical requests, different flush boundaries. |', '',
               '| Case / policy | Creations/frame | Median (ms) | p95 (ms) | Peak entries | Peak RSS (MiB) |',
               '| --- | ---: | ---: | ---: | ---: | ---: |']
    for case, entry in sorted(policy_summary.items()):
        m = entry['medians']
        report.append(f"| {case} | {m['created_per_frame']:.2f} | {m['completed_ms_p50']:.3f} | {m['completed_ms_p95']:.3f} | {m['peak_resident']:.0f} | {m['peak_rss_mib']:.2f} |")
    report += ['', 'Even unlimited retention must create pipelines for new states.', '', '</details>', '',
               '## Metal cache controls', '',
               '**Driver cache state affects timing. It did not change the observed creation or retention counts.**', '',
               '- Two priming passes precede each suite. Later Metal cache eviction remains uncontrolled.',
               '- A separate cache-override check slowed startup similarly for upstream and proposed.',
               '- Timing drift remained. Small differences at equal creation counts are inconclusive.', '',
               '<details>', '<summary>Priming, cache-override diagnostic and timing drift</summary>', '',
               'Measured processes start with empty FemtoVG caches and `MTL_SHADER_CACHE_SIZE` unset.', '',
               'The first LRU hot-scan priming pass peaked at '
               f"{evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][1]:.2f} ms. "
               f"The second peaked at {evidence['priming']['policies/hot-scan/W64/C64/lru']['phase_peaks']['scan']['priming_max_ms_by_pass'][2]:.2f} ms. "
               f'[Priming observations]({link}/analysis/priming.md).', '']
    if 'cold_control' in evidence:
        report += ['The override diagnostic creates the same 17 pipelines in each first frame:', '',
                   '| `MTL_SHADER_CACHE_SIZE` | Upstream first-frame median (ms) | Proposed first-frame median (ms) |', '| --- | ---: | ---: |']
        for setting in ('None', '0'):
            before = statistics.median(evidence['cold_control'][f'upstream/{setting}']['first_frames_ms'])
            after = statistics.median(evidence['cold_control'][f'flush-lru64/{setting}']['first_frames_ms'])
            report.append(f"| {'Unset' if setting == 'None' else '`0`'} | {before:.2f} | {after:.2f} |")
        report += ['', '- Creation and retention counts were unchanged across settings.',
                   '- Three launches per condition support a diagnostic comparison, not an equivalence test.',
                   '- The override is undocumented and is not a verified global reset. Later creations may still benefit from reuse.', '',
                   f'[Full diagnostic]({link}/analysis/cold-control.md).', '']
    report += [f"At 65 states, #343 process medians ranged from {min(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} "
               f"to {max(r['completed_p50_ms'] for r in direct_summary['65/pr343']['per_run']):.2f} ms. "
               'Several early processes were slower for unresolved reasons. All were retained.', '', '</details>', '',
               '## Measurement and validation', '',
               f"**{evidence['gpu_frames']:,} measured frames and {evidence['gpu_flushes']:,} flushes checked cache behavior and GPU execution.** Rendered pixels were not compared.", '',
               'Results come from one machine. Process memory measurements do not establish a per-pipeline memory cost.', '',
               '<details>', '<summary>Source pins, measurement method, uncertainty and validation</summary>', '',
               f"- **Hardware/software:** {adapter}/{backend}. {meta['platform']}. {meta['rustc'].splitlines()[0]}.",
               '- **Render target:** 64×64 RGBA8, emphasizing pipeline management costs.',
               f"- **Source:** PR `{meta['source']['candidate']['commit'][:7]}`, upstream `{meta['source']['base']['commit'][:7]}`. Renderer verified before instrumentation. [Pins and checksums](vendor/report-source.json).",
               '- **Build:** shared base, dependency lockfile, features and release settings.', '',
               '| Experiment | Measured processes | Frames summarized per process |', '| --- | ---: | --- |',
               f'| Direct comparison | {len(a)}. 10 per case | 100, after one initial and five warmup frames |',
               f'| Policy study | {len(b)}. 10 per case | 90, from frames 10–99 |']
    if confirmed:
        report.append('| Confirmation | 120. 20 per case | 100, after one initial and five warmup frames |')
    report += ['', '- **Order:** the main campaign rotates workload/policy order and includes 7,200 CPU simulations. Only shuffled traces vary with seed.',
               '- **Timing:** completed time includes command construction, encoding, submission and the GPU wait. CPU time stops before the wait.',
               '- **Aggregation:** nearest-rank quantiles per process, then medians across processes. With 90 frames, p99 is effectively the process maximum.',
               '- **Exclusions:** none. Scans, transitions and slow runs remain in the data.', '',
               '**Median intervals** span the second-smallest through second-largest of ten process medians:', '',
               '- Nominal 97.85% coverage assumes independent, identically distributed observations.',
               '- Shared cache state and timing drift weaken those assumptions.',
               '- Intervals are pointwise and do not describe variation across machines.', '',
               '[Interval method](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).', '',
               '**Validation:**', '',
               '- Direct boundary tests assert the initial pipeline count. Repeated runs match creation/residency profiles.',
               '- Every policy-study GPU flush checks creations and retention against the CPU model.',
               '- WGPU validation errors fail the run. Totals exclude priming and the Metal diagnostic.', '',
               '**Memory limits:** RSS and physical footprint include setup and cold work. The policy study also runs a CPU simulation before GPU initialization. Metal counters omit private compiler/driver memory.', '',
               f'[Full protocol](docs/report-protocol.md) and [metadata]({link}/metadata.json).', '', '</details>', '',
               '## Reproduce and inspect', '',
               'Pinned sources, patches, scripts and raw data are included. Requires Rust, Python, Git and a GPU backend. The Metal diagnostic requires macOS.', '',
               '```sh', 'python3 scripts/run-report.py --out runs/my-pr-report', 'python3 scripts/report-sanity.py runs/my-pr-report',
               'python3 scripts/render-report.py runs/my-pr-report', '```', '',
               'The report generator includes the published confirmation separately when source pins match.', '',
               f'- [Full tables]({link}/analysis/tables.md), [timing intervals]({link}/analysis/timing.csv), [analysis JSON]({link}/analysis/evidence.json).',
               f'- Direct comparison: [raw frames]({link}/direct/runs.jsonl.gz), [summary]({link}/direct/summary.json), [priming]({link}/direct/priming.jsonl.gz).',
               f'- Policy study: [raw frames]({link}/policies/gpu.jsonl.gz), [summary]({link}/policies/summary.json), [priming]({link}/policies/priming.jsonl.gz).',
               f'- CPU sweep: [raw counts]({link}/policies/simulation.jsonl.gz), [capacity/phase summaries]({link}/policies/simulation-summary.json).',
               '- [Confirmation results and rerun commands](results/confirmation-d5241b9/README.md).',
               f'- Supporting checks: [historical comparison]({link}/analysis/sanity.md), [extraction rerun](results/reproduction-2026-09-27/README.md), [initial Metal probe](results/metal-cache-control-probe/README.md).']
    (ROOT / 'REPORT.md').write_text('\n'.join(report)+'\n')
    print(f'Generated REPORT.md and {args.data}/analysis')


DIRECT_POLICIES = ('upstream', 'pr343', 'flush-lru64', 'strict-lru128')
if __name__ == '__main__':
    main()
