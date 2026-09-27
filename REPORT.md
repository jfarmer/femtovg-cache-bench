# FemtoVG WGPU pipeline-cache evaluation

This report evaluates the proposed flush-aware pipeline cache against upstream behavior, [PR #343](https://github.com/femtovg/femtovg/pull/343)'s conditional sweep, and alternative retention policies. The primary evidence is an explicitly primed measurement campaign on the PR's current upstream base.

## Proposed change and scope

The proposed renderer is pinned to `d5241b90032d8bfaca305d993cef30a0277f8898`; upstream is `fa5d6a36818e79be1e8ea2a32eca3564e893180f`. The source archive and patch are bundled. The build verifies that the candidate renderer matches the PR revision byte-for-byte before adding creation/residency counters. All variants use the same base, features, dependency lockfile and release settings.

Upstream sweeps entries not accessed in the last flush. A separate clear-only flush can therefore evict pipelines needed by the next draw flush. PR #343 only runs that sweep above 64 entries. The proposed change stamps entries by flush and, above 64, evicts the oldest entries unused by the current flush. It protects every pipeline used in that flush: 64 is a retention target, not a hard memory bound. Ties within a flush have no specified access order.

The direct `flush-lru64` variant is the actual proposed implementation. The broader study's `flush-lru` is a separate shared-model refinement using per-access ordering within a flush. Its numbers explore the policy family and must not be attributed byte-for-byte to the PR. Strict LRU uses the `lru` crate; S3-FIFO adds admission/ghost metadata; `retain` never evicts and is a reference, not a bounded policy.

## Measurement method

macOS-26.6.2-arm64-arm-64bit; rustc 1.96.0 (ac68faa20 2026-05-25). GPU adapter: Apple M4 Max. The target is 64×64 RGBA8; the workloads stress pipeline-state management rather than fill rate. Every main launch explicitly unsets MTL_SHADER_CACHE_SIZE. Two complete workload passes precede each suite, including late scan states; priming is saved separately. Every measured process starts with an empty application cache. This is an explicit warm-up protocol, not a guarantee of every internal driver cache hit.

The campaign contains 240 direct-comparison processes, 320 shared-policy GPU processes, and 7,200 CPU simulations. Each case has ten measured processes with rotated workload/policy order. The direct suite measures 100 frames after one initial and five warmup frames. The policy study saves 100 frames and summarizes frames 10–99, retaining subsequent scans and transitions. No outliers are removed. The first ten trace seeds share the same key set; only shuffled traces change order.

Completed time includes command construction, encoding, submissions and waiting for GPU completion. It is not a GPU timestamp or presentation latency. CPU time stops before the completion wait. Summaries take within-process nearest-rank quantiles, then the median across processes. Median intervals use process-level observations: the second-smallest through second-largest of ten give conservative 97.85% coverage under independent, identically distributed process-summary assumptions. They are pointwise intervals conditional on this setup, not cross-machine guarantees. Shared driver state and thermal/background drift can violate those assumptions. A p95 latency and a confidence interval for a median answer different questions. See [NIST on order-statistic intervals for a median](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).

See the [exact protocol](docs/report-protocol.md), [source pins](vendor/report-source.json), [measurement metadata](results/pr-report-d5241b9/metadata.json), [priming observations](results/pr-report-d5241b9/analysis/priming.md), and [matched-work cold-start check](results/pr-report-d5241b9/analysis/cold-control.md).

## Cache controls and observed variation

These are explicitly primed, normal-cache runs. Cache eviction or invalidation during measurement is uncontrolled; priming does not guarantee persistent warmth. The warm-up observations cover full traces, including late scan states. The first LRU hot-scan priming process has a scan-frame maximum of 7482.02 ms; the second pass is 124.36 ms. This is observable evidence that preparation matters; it does not identify every internal cache or prove all later lookups hit.

The matched-work diagnostic reports first-use timing for the same 17 materializations under both settings, and verifies unchanged creation/residency profiles across settings. First-frame medians are 15.79 ms upstream and 15.74 ms proposed with the override unset, versus 614.37 and 613.90 ms with it set to zero. The undocumented zero-size override is a diagnostic intervention, not a supported global reset or a guarantee that repeated creations remain cold. Subsequent frames retain within-process reuse effects. Three launches per condition do not establish precise statistical equivalence between policies.

Some direct-comparison processes remain noticeably slower than others after priming; the raw per-process results and intervals retain that variation. For example, the 65-state #343 process medians range from 26.40 to 48.19 ms. Several slower direct processes occur early in the campaign. Their cause is unresolved; warming driver caches does not control all session-level timing variation. No run is dropped, and small timing differences between policies with the same creation counts should not be interpreted as a reliable ranking.

## Actual PR: boundary and mixed-operation results

Boundary workloads visit N−1 blend states in one draw flush, then a separate clear flush; N includes clear. The mixed workload alternates glyph-atlas rendering, clipped opacity layers, blur, screen drawing and clear. Strict LRU 128 has twice the proposed retention target; it is included as a practical alternative, not a same-capacity comparison.

| Workload | Policy | Creations/frame | Median [interval] (ms) | p95 (ms) |
| --- | --- | ---: | ---: | ---: |
| 63 | Upstream | 63 | 26.563 [25.913, 30.124] | 28.500 |
| 63 | #343 | 0 | 0.367 [0.318, 0.668] | 0.641 |
| 63 | Proposed 64 | 0 | 0.383 [0.350, 1.010] | 0.734 |
| 63 | Strict LRU 128 | 0 | 0.425 [0.350, 0.871] | 0.670 |
| 64 | Upstream | 64 | 26.996 [26.408, 29.278] | 27.778 |
| 64 | #343 | 0 | 0.377 [0.355, 0.850] | 0.719 |
| 64 | Proposed 64 | 0 | 0.473 [0.351, 0.942] | 0.742 |
| 64 | Strict LRU 128 | 0 | 0.441 [0.354, 0.601] | 0.685 |
| 65 | Upstream | 65 | 27.347 [26.734, 28.943] | 28.070 |
| 65 | #343 | 65 | 27.184 [26.530, 28.782] | 28.136 |
| 65 | Proposed 64 | 2 | 1.187 [1.129, 1.274] | 1.523 |
| 65 | Strict LRU 128 | 0 | 0.394 [0.355, 0.603] | 0.774 |
| 80 | Upstream | 80 | 33.596 [33.156, 35.266] | 34.385 |
| 80 | #343 | 80 | 33.338 [32.773, 34.580] | 34.084 |
| 80 | Proposed 64 | 17 | 7.475 [7.228, 8.654] | 8.082 |
| 80 | Strict LRU 128 | 0 | 0.439 [0.380, 0.701] | 0.832 |
| 129 | Upstream | 129 | 54.411 [53.239, 57.390] | 55.741 |
| 129 | #343 | 129 | 53.805 [52.713, 56.300] | 55.954 |
| 129 | Proposed 64 | 66 | 28.243 [27.462, 40.190] | 29.456 |
| 129 | Strict LRU 128 | 129 | 54.181 [53.110, 66.935] | 55.257 |
| mixed | Upstream | 23 | 10.502 [10.242, 12.559] | 11.077 |
| mixed | #343 | 0 | 0.783 [0.716, 1.661] | 1.021 |
| mixed | Proposed 64 | 0 | 0.782 [0.723, 0.912] | 1.074 |
| mixed | Strict LRU 128 | 0 | 0.780 [0.722, 1.021] | 1.066 |

The proposed policy preserves cross-flush reuse below capacity and degrades more gradually for this one-large-flush/one-clear pattern above capacity. Strict LRU has a different failure mode when the cyclic working set exceeds its limit. These traces demonstrate boundaries, not their frequency in applications.

### Within-round comparison with #343

| Working set | Proposed / #343 median-latency ratio [interval] |
| --- | ---: |
| 63 | 1.018 [0.947, 1.249] |
| 64 | 0.994 [0.952, 1.109] |
| 65 | 0.043 [0.042, 0.046] |
| 80 | 0.224 [0.221, 0.241] |
| 129 | 0.524 [0.521, 0.724] |
| mixed | 0.995 [0.871, 1.075] |

Each ratio pairs the two policies within the same measurement round. These are median ratios with intervals, not ratios of aggregate medians. A value below one favors the proposal. Intervals do not establish simultaneous significance across all rows.

## Alternative policies under changing workloads

W is workload scale; C is capacity. A cycle/shuffle-plus trace has W+1 distinct states. The hot-scan trace revisits a small hot set around streams of new states. Switch alternates disjoint sets, while batch-single and batch-split preserve the request sequence but change flush boundaries. Equal-capacity 64 and 128 cycle/shuffle cases separate capacity from policy. The CPU sweep additionally varies capacity over 32–512 while holding each trace fixed.

| Case / policy | Creations/frame | Median (ms) | p95 (ms) | Peak entries | Peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: |
| batch-single/scale64/cap64/flush-lru | 0.00 | 0.660 | 0.973 | 128 | 31.28 |
| batch-single/scale64/cap64/lru | 255.00 | 102.358 | 103.916 | 64 | 32.97 |
| batch-single/scale64/cap64/retain | 0.00 | 0.674 | 1.618 | 128 | 31.23 |
| batch-single/scale64/cap64/s3fifo | 255.00 | 102.584 | 103.915 | 64 | 33.05 |
| batch-split/scale64/cap64/flush-lru | 255.00 | 103.218 | 104.552 | 72 | 35.96 |
| batch-split/scale64/cap64/lru | 255.00 | 103.204 | 104.559 | 64 | 35.98 |
| batch-split/scale64/cap64/retain | 0.00 | 1.707 | 1.936 | 128 | 44.81 |
| batch-split/scale64/cap64/s3fifo | 255.00 | 103.373 | 104.605 | 64 | 36.06 |
| cycle-plus/scale128/cap128/flush-lru | 2.00 | 1.323 | 1.533 | 129 | 32.06 |
| cycle-plus/scale128/cap128/lru | 129.00 | 51.670 | 52.457 | 128 | 32.70 |
| cycle-plus/scale128/cap128/retain | 0.00 | 0.478 | 1.059 | 129 | 31.77 |
| cycle-plus/scale128/cap128/s3fifo | 6.39 | 3.288 | 6.403 | 128 | 32.26 |
| cycle-plus/scale64/cap64/flush-lru | 2.00 | 1.141 | 1.309 | 65 | 28.91 |
| cycle-plus/scale64/cap64/lru | 65.00 | 25.949 | 26.449 | 64 | 29.39 |
| cycle-plus/scale64/cap64/retain | 0.00 | 0.366 | 0.660 | 65 | 28.48 |
| cycle-plus/scale64/cap64/s3fifo | 4.28 | 2.423 | 3.877 | 64 | 29.00 |
| hot-scan/scale64/cap64/flush-lru | 25.70 | 0.637 | 114.329 | 320 | 119.57 |
| hot-scan/scale64/cap64/lru | 27.30 | 0.626 | 121.234 | 64 | 118.83 |
| hot-scan/scale64/cap64/retain | 25.60 | 0.639 | 114.617 | 2321 | 131.76 |
| hot-scan/scale64/cap64/s3fifo | 25.60 | 0.643 | 114.849 | 64 | 119.23 |
| shuffle-plus/scale128/cap128/flush-lru | 2.00 | 1.328 | 1.484 | 129 | 32.05 |
| shuffle-plus/scale128/cap128/lru | 6.49 | 3.204 | 4.568 | 128 | 32.25 |
| shuffle-plus/scale128/cap128/retain | 0.00 | 0.481 | 1.048 | 129 | 31.76 |
| shuffle-plus/scale128/cap128/s3fifo | 4.72 | 2.850 | 4.260 | 128 | 32.20 |
| shuffle-plus/scale64/cap64/flush-lru | 2.00 | 1.149 | 1.313 | 65 | 28.90 |
| shuffle-plus/scale64/cap64/lru | 5.61 | 2.685 | 3.811 | 64 | 29.09 |
| shuffle-plus/scale64/cap64/retain | 0.00 | 0.383 | 0.656 | 65 | 28.48 |
| shuffle-plus/scale64/cap64/s3fifo | 3.36 | 1.779 | 3.128 | 64 | 29.03 |
| switch/scale64/cap64/flush-lru | 1.56 | 0.526 | 0.928 | 95 | 29.95 |
| switch/scale64/cap64/lru | 2.09 | 0.530 | 1.348 | 64 | 29.88 |
| switch/scale64/cap64/retain | 0.52 | 0.523 | 0.580 | 95 | 29.88 |
| switch/scale64/cap64/s3fifo | 5.21 | 0.543 | 15.685 | 64 | 30.20 |

The soft target trades bounded residency for reuse across a large flush; dividing the same requests across smaller flushes can remove that advantage. A never-repeated scan incurs compulsory misses even with unlimited retention. S3-FIFO can protect hot entries from scans but has admission/adaptation costs on changing sets. Unlimited retention demonstrates the available reuse and the accompanying growth in live objects. None of these results makes a universal case for one threshold.

## Correctness and memory interpretation

The measured data contains 57,440 frames and 243,600 flushes, excluding priming and the cold diagnostic. The direct boundary runs assert actual first-frame materializations equal the requested state count; repeated direct runs have identical creation/residency profiles. Every shared-policy GPU flush asserts that actual creations and retained entries match the CPU model, including cold and transition frames. WGPU validation errors fail the run. These checks validate policy work and execution; they do not compare rendered pixels.

Resident/ghost counts, HAL live pipelines, process peak RSS, physical footprint and Metal allocated-resource samples describe different quantities. RSS/footprint include setup and cold work; the shared-model simulator also runs in the measured process before GPU initialization. Metal resource accounting excludes private compiler/driver memory. Do not convert these process-level differences directly into bytes per pipeline. The 90 measured frames in the study make p99 effectively a per-process maximum; all p99 values remain in the complete tables but deserve restraint.

## Decision supported by this experiment

The proposal addresses repeated creation caused by small intervening flushes without adding a cache dependency. The measured boundaries show where it improves over #343's conditional sweep. Its soft target and sensitivity to flush grouping are explicit costs. Strict LRU gives a hard limit, but simple cyclic traces expose its capacity cliff; S3-FIFO adds policy and metadata complexity. The policy choice remains open to realistic workload traces and maintainer preferences. This report supports the proposed mechanism and characterizes tradeoffs; it does not establish application-wide speedups or the ideal capacity for all applications.

## Reproduction and complete evidence

```sh
python3 scripts/run-report.py --out runs/my-pr-report
python3 scripts/report-sanity.py runs/my-pr-report
python3 scripts/render-report.py runs/my-pr-report
```

The final command regenerates REPORT.md and the analysis files from saved data. All pinned project sources and analysis scripts are contained in this repository. A working Rust/Python/Git installation and GPU backend are required for a fresh measurement campaign. The controlled Metal diagnostic is macOS-specific.

- [Timing/residency tables](results/pr-report-d5241b9/analysis/tables.md), [all CPU/completed quantiles and intervals](results/pr-report-d5241b9/analysis/timing.csv), and [machine-readable evidence](results/pr-report-d5241b9/analysis/evidence.json).
- [Direct raw frames](results/pr-report-d5241b9/direct/runs.jsonl.gz) and [summary](results/pr-report-d5241b9/direct/summary.json).
- [Policy-study raw frames](results/pr-report-d5241b9/policies/gpu.jsonl.gz), [summary](results/pr-report-d5241b9/policies/summary.json), [CPU sweep](results/pr-report-d5241b9/policies/simulation.jsonl.gz), and [capacity/phase summaries](results/pr-report-d5241b9/policies/simulation-summary.json).
- [Historical work/timing sanity check for this campaign](results/pr-report-d5241b9/analysis/sanity.md).
- [Direct priming](results/pr-report-d5241b9/direct/priming.jsonl.gz) and [policy priming](results/pr-report-d5241b9/policies/priming.jsonl.gz).
- [Historical extraction sanity check](results/reproduction-2026-09-27/README.md) and [initial Metal-control probe](results/metal-cache-control-probe/README.md). These support validation and do not supply the primary performance numbers above.
