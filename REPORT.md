# FemtoVG WGPU pipeline-cache evaluation

The proposed cache avoids rebuilding an entire working set after a small intervening flush. At 65 pipeline states, it creates **2 pipelines per frame instead of 65** with [PR #343](https://github.com/femtovg/femtovg/pull/343). Median completed-frame time falls from **27.18 to 1.19 ms** on Apple M4 Max/Metal.

The tradeoff is a soft capacity target: pipelines used by one flush remain protected even above 64 entries. These synthetic tests show the benefit and its limits. They do not estimate application-wide speedups or establish an optimal capacity.

## What changes

| Implementation | Eviction after a flush |
| --- | --- |
| Upstream | Remove every pipeline unused by that flush. |
| #343 | Apply that sweep only when the cache exceeds 64 entries. |
| Proposed | Above 64 entries, remove the oldest pipelines unused by that flush. |

A clear-only flush can therefore discard the preceding draw's pipelines on upstream and, above capacity, on #343. The proposal trims older entries while preserving the current flush's working set. Recency is measured in flushes; ties within a flush have no specified order.

The direct tests use the actual PR renderer at `d5241b9`, based on upstream `fa5d6a3`. The build verifies the renderer before adding counters. All variants share the base, dependency lockfile, features and release settings. [Full source pins and checksums](vendor/report-source.json).

## Direct comparison

The proposal reduces repeated creation above #343's threshold; it does not eliminate capacity limits. At 65, 80 and 129 states, #343 recreates the whole set each frame. The proposal recreates 2, 17 and 66 pipelines respectively. Strict LRU 128 holds the smaller sets but recreates all 129 pipelines in the cyclic 129-state case.

Each numbered workload draws N−1 blend states, then issues a separate clear flush. N includes the clear pipeline. The mixed workload alternates glyph-atlas, clipped-layer, blur, screen and clear operations. Strict LRU 128 has twice the proposal's retention target.

Times below are milliseconds, aggregated over ten processes per case. Completed time includes CPU work and the GPU completion wait. Bracketed values are intervals for the median under the assumptions described in [Measurement and uncertainty](#measurement-and-uncertainty).

<details>
<summary>All direct results: creations, median intervals and p95</summary>

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

</details>

[Complete tables, including p99 and within-round ratios](results/pr-report-d5241b9/analysis/tables.md). Ratios compare process medians within the same round; they are not ratios of aggregate medians.

## Randomized confirmation

**At 65 states, the proposal was faster in 20 of 20 pairs.** A separate run compared the proposal with #343 in twenty adjacent pairs per workload. Policy order was randomized and balanced before measurement.

| Workload | #343 median / p95 (ms) | Proposed median / p95 (ms) |
| --- | ---: | ---: |
| 64 | 0.351 / 0.622 | 0.320 / 0.597 |
| 65 | 25.182 / 26.124 | 1.128 / 1.384 |
| mixed | 0.745 / 0.918 | 0.748 / 0.901 |

Median within-pair proposed/#343 ratios are 0.998 at 64 states and 0.998 for mixed operations. Those cases show no obvious regression; they do not establish statistical equivalence.

All 120 measured and 12 priming runs match the original creation/residency profiles. The repeat is reported separately. [Protocol, individual pairs and raw data](results/confirmation-d5241b9/README.md).

## Other retention policies

No policy wins across all tested access patterns. The main tradeoffs are capacity, scan resistance and sensitivity to flush boundaries.

| Policy | Observed tradeoff |
| --- | --- |
| Flush-aware | Reuses a large flush's working set by exceeding the target. Splitting the same requests across smaller flushes can lose that advantage. |
| Strict LRU (`lru` crate) | Enforces an entry limit. Cyclic access just beyond capacity can miss on every request. |
| S3-FIFO | Protects hot entries during scans, but takes longer to adapt to switching sets and needs admission/ghost metadata. |
| Retain everything | Shows available reuse, with continuing growth under streams of new states. |

**The study's `flush-lru` is a model variant, not the exact PR implementation.** It orders accesses within a flush; the PR uses flush stamps. The direct comparison and confirmation above test the actual PR.

W is workload scale and C is capacity. Cycle/shuffle-plus uses W+1 states. Hot-scan interleaves a hot set with new states; switch alternates disjoint sets. Batch-single and batch-split issue the same requests with different flush boundaries. The CPU sweep additionally varies capacity from 32 to 512 for each fixed trace.

<details>
<summary>All policy-study results: timing, creation counts and memory</summary>

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

</details>

Even unlimited retention cannot avoid creating pipelines for never-repeated states. The results support the proposed fix, but leave the policy and capacity open to maintainer preferences.

## Measurement and uncertainty

**Setup:** Apple M4 Max/Metal; macOS-26.6.2-arm64-arm-64bit; rustc 1.96.0 (ac68faa20 2026-05-25). The 64×64 RGBA8 target emphasizes pipeline management costs.

| Experiment | Measured processes | Frames summarized per process |
| --- | ---: | --- |
| Direct comparison | 240; 10 per case | 100, after one initial and five warmup frames |
| Policy study | 320; 10 per case | 90, from frames 10–99 |
| Confirmation | 120; 20 per case | 100, after one initial and five warmup frames |

The main campaign rotates workload/policy order and includes 7,200 CPU simulations. Only shuffled traces vary with seed. Scans and transitions remain in the measured set. No outliers are removed.

**Timing:** completed-frame time includes command construction, encoding, submission and the GPU wait. CPU time stops before that wait. Each process contributes nearest-rank quantiles; tables report their medians across processes. With 90 measured frames, the study's p99 is effectively the process maximum.

**Intervals:** the second-smallest through second-largest of ten process medians gives nominal 97.85% coverage under independent, identically distributed observations. These are pointwise intervals. Shared cache state and observed drift make the independence assumptions uncertain. They do not describe variability across machines. [Interval method](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).

[Full protocol](docs/report-protocol.md) and [measurement metadata](results/pr-report-d5241b9/metadata.json).

## Metal cache controls

**Priming reduces first-use cost but cannot guarantee a warm driver cache.** Before each suite, two complete workload passes run with `MTL_SHADER_CACHE_SIZE` unset. Measured processes start with empty FemtoVG caches; later Metal cache eviction or invalidation is uncontrolled.

For example, the first LRU hot-scan priming pass reached 7482.02 ms in a scan frame; the second reached 124.36 ms. [Priming observations](results/pr-report-d5241b9/analysis/priming.md).

**The cache override slowed startup similarly for both implementations.** A separate diagnostic created 17 pipelines on the first frame in each case:

| `MTL_SHADER_CACHE_SIZE` | Upstream first-frame median (ms) | Proposed first-frame median (ms) |
| --- | ---: | ---: |
| Unset | 15.79 | 15.74 |
| `0` | 614.37 | 613.90 |

Creation and retention counts were unchanged across settings. This supports separating driver startup cost from cache-policy behavior. The undocumented override is not a verified global reset; later creations can still benefit from reuse. These three-launch medians are diagnostic, not an equivalence test. [Full check](results/pr-report-d5241b9/analysis/cold-control.md).

**Timing drift remained after priming.** At 65 states, #343's process medians ranged from 26.40 to 48.19 ms. Several slower processes occurred early in the campaign. Their cause is unresolved. All were retained; small timing differences at equal creation counts should not be treated as a reliable ranking.

## Validation and memory limits

The main campaign records 57,440 frames and 243,600 flushes, excluding priming and the Metal diagnostic.

- Direct boundary tests assert the initial pipeline count. Creation/residency profiles match across repeated runs.
- Every policy-study GPU flush checks creation and retention against the CPU model. WGPU validation errors fail the run.
- These checks cover cache behavior and GPU execution. They do not compare rendered pixels.

**Entry counts and process memory measure different things.** RSS and physical footprint include setup, cold work and, in the policy study, a preliminary CPU simulation. Metal resource counters omit private compiler/driver memory. Neither measure gives a reliable bytes-per-pipeline estimate.

## Reproduce and inspect

The repository contains pinned sources, patches, scripts and raw results. A fresh run needs Rust, Python, Git and a working GPU backend. The Metal diagnostic runs only on macOS.

```sh
python3 scripts/run-report.py --out runs/my-pr-report
python3 scripts/report-sanity.py runs/my-pr-report
python3 scripts/render-report.py runs/my-pr-report
```

The final command regenerates this report and its analysis from saved data. The published confirmation is included separately when its source pins match.

- [Full tables](results/pr-report-d5241b9/analysis/tables.md), [timing intervals](results/pr-report-d5241b9/analysis/timing.csv), and [analysis JSON](results/pr-report-d5241b9/analysis/evidence.json).
- Direct comparison: [raw frames](results/pr-report-d5241b9/direct/runs.jsonl.gz), [summary](results/pr-report-d5241b9/direct/summary.json), [priming](results/pr-report-d5241b9/direct/priming.jsonl.gz).
- Policy study: [raw frames](results/pr-report-d5241b9/policies/gpu.jsonl.gz), [summary](results/pr-report-d5241b9/policies/summary.json), [priming](results/pr-report-d5241b9/policies/priming.jsonl.gz).
- CPU sweep: [raw counts](results/pr-report-d5241b9/policies/simulation.jsonl.gz), [capacity/phase summaries](results/pr-report-d5241b9/policies/simulation-summary.json).
- [Confirmation results and rerun commands](results/confirmation-d5241b9/README.md).
- Supporting validation: [historical sanity check](results/pr-report-d5241b9/analysis/sanity.md), [extraction rerun](results/reproduction-2026-09-27/README.md), [initial Metal probe](results/metal-cache-control-probe/README.md).
