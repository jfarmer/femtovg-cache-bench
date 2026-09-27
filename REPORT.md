# FemtoVG WGPU pipeline-cache evaluation

**The proposal prevents small flushes from discarding an entire cached working set.**

At 65 states, pipeline creations fall from **65 to 2 per frame** and median frame time from **27.18 to 1.19 ms**, compared with [PR #343](https://github.com/femtovg/femtovg/pull/343) on Apple M4 Max/Metal.

**Tradeoff:** 64 entries is a retention target. A single flush can retain more. These synthetic results do not predict application-wide speedups.

## Cache behavior

| Implementation | Eviction after a flush |
| --- | --- |
| Upstream | Remove all pipelines unused by that flush. |
| #343 | Do the same, but only above 64 entries. |
| Proposed | Above 64 entries, remove oldest unused pipelines until the target is reached. Protect pipelines used by the current flush. |

The proposal measures recency in flushes. Entries last used in the same flush have no specified eviction order.

## Direct comparison

**Above 64 states, the proposal rebuilds fewer pipelines than #343.**

| States | #343 creations/frame | Proposed creations/frame |
| ---: | ---: | ---: |
| 65 | 65 | 2 |
| 80 | 80 | 17 |
| 129 | 129 | 66 |

Strict LRU 128 avoids rebuilding the smaller sets, but rebuilds all 129 pipelines when cyclic access exceeds its capacity.

<details>
<summary>Full results and workload definitions</summary>

| Workload | Operations |
| --- | --- |
| Numbered | N−1 blend states, followed by a separate clear flush. N includes the clear pipeline. |
| Mixed | Glyph-atlas, clipped-layer, blur, screen and clear operations. |

Strict LRU 128 has twice the proposed retention target.

Times include CPU work and the GPU completion wait. Each row summarizes ten processes. Brackets give median intervals; see [measurement details](#measurement-and-validation).

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

[Additional quantiles and within-round ratios](results/pr-report-d5241b9/analysis/tables.md). Ratios pair process medians within a round; they are not ratios of aggregate medians.

</details>

## Confirmation

**The proposal was faster in all 20 randomized pairs at 65 states.**

| Workload | #343 median / p95 (ms) | Proposed median / p95 (ms) |
| --- | ---: | ---: |
| 64 | 0.351 / 0.622 | 0.320 / 0.597 |
| 65 | 25.182 / 26.124 | 1.128 / 1.384 |
| mixed | 0.745 / 0.918 | 0.748 / 0.901 |

At 64 states and in the mixed workload, paired results show no obvious regression. Statistical equivalence was not tested.

<details>
<summary>Confirmation protocol and paired results</summary>

- Twenty adjacent pairs per workload, with randomized, balanced policy order fixed before measurement.
- Median proposed/#343 paired ratios: 0.998 at 64 states; 0.998 for mixed operations.
- All 120 measured and 12 priming runs match the primary creation/residency profiles. No runs excluded.
- Results remain separate from the primary estimates.

[Full protocol, individual pairs and raw data](results/confirmation-d5241b9/README.md).

</details>

## Other policies

**The choice remains open: reuse, memory limits and scan resistance favor different policies.**

| Policy | Benefit | Cost |
| --- | --- | --- |
| Flush-aware | Reuses large working sets within a flush. | Can exceed capacity; sensitive to flush boundaries. |
| Strict LRU (`lru` crate) | Hard entry limit. | Cyclic access just above capacity misses every time. |
| S3-FIFO | Protects hot entries during scans. | Slower adaptation to switching sets; extra metadata. |
| Retain everything | Preserves all available reuse. | Unbounded growth with new states. |

This study uses a flush-aware model with per-access ordering. The PR uses flush stamps; its results are in the direct comparison above.

<details>
<summary>Policy-study workloads and full results</summary>

W is workload scale; C is capacity. The CPU sweep varies capacity from 32 to 512 for each fixed trace.

| Workload | Access pattern |
| --- | --- |
| Cycle/shuffle-plus | W+1 states, in cyclic or shuffled order. |
| Hot-scan | A hot set interleaved with new states. |
| Switch | Alternating disjoint sets. |
| Batch-single / batch-split | Identical requests, different flush boundaries. |

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

Even unlimited retention must create pipelines for new states.

</details>

## Metal cache controls

**Driver cache state affects timing. It did not change the observed creation or retention counts.**

- Two priming passes precede each suite. Later Metal cache eviction remains uncontrolled.
- A separate cache-override check slowed startup similarly for upstream and proposed.
- Timing drift remained. Small differences at equal creation counts are inconclusive.

<details>
<summary>Priming, cache-override diagnostic and timing drift</summary>

Measured processes start with empty FemtoVG caches and `MTL_SHADER_CACHE_SIZE` unset.

The first LRU hot-scan priming pass peaked at 7482.02 ms; the second at 124.36 ms. [Priming observations](results/pr-report-d5241b9/analysis/priming.md).

The override diagnostic creates the same 17 pipelines in each first frame:

| `MTL_SHADER_CACHE_SIZE` | Upstream first-frame median (ms) | Proposed first-frame median (ms) |
| --- | ---: | ---: |
| Unset | 15.79 | 15.74 |
| `0` | 614.37 | 613.90 |

- Creation and retention counts were unchanged across settings.
- Three launches per condition support a diagnostic comparison, not an equivalence test.
- The override is undocumented and is not a verified global reset. Later creations may still benefit from reuse.

[Full diagnostic](results/pr-report-d5241b9/analysis/cold-control.md).

At 65 states, #343 process medians ranged from 26.40 to 48.19 ms. Several early processes were slower for unresolved reasons. All were retained.

</details>

## Measurement and validation

**57,440 measured frames and 243,600 flushes checked cache behavior and GPU execution.** Rendered pixels were not compared.

Results come from one machine. Process memory measurements do not establish a per-pipeline memory cost.

<details>
<summary>Source pins, measurement method, uncertainty and validation</summary>

- **Hardware/software:** Apple M4 Max/Metal; macOS-26.6.2-arm64-arm-64bit; rustc 1.96.0 (ac68faa20 2026-05-25).
- **Render target:** 64×64 RGBA8, emphasizing pipeline management costs.
- **Source:** PR `d5241b9`, upstream `fa5d6a3`. Renderer verified before instrumentation. [Pins and checksums](vendor/report-source.json).
- **Build:** shared base, dependency lockfile, features and release settings.

| Experiment | Measured processes | Frames summarized per process |
| --- | ---: | --- |
| Direct comparison | 240; 10 per case | 100, after one initial and five warmup frames |
| Policy study | 320; 10 per case | 90, from frames 10–99 |
| Confirmation | 120; 20 per case | 100, after one initial and five warmup frames |

- **Order:** the main campaign rotates workload/policy order and includes 7,200 CPU simulations. Only shuffled traces vary with seed.
- **Timing:** completed time includes command construction, encoding, submission and the GPU wait. CPU time stops before the wait.
- **Aggregation:** nearest-rank quantiles per process, then medians across processes. With 90 frames, p99 is effectively the process maximum.
- **Exclusions:** none. Scans, transitions and slow runs remain in the data.

**Median intervals** span the second-smallest through second-largest of ten process medians:

- Nominal 97.85% coverage assumes independent, identically distributed observations.
- Shared cache state and timing drift weaken those assumptions.
- Intervals are pointwise and do not describe variation across machines.

[Interval method](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).

**Validation:**

- Direct boundary tests assert the initial pipeline count; repeated runs match creation/residency profiles.
- Every policy-study GPU flush checks creations and retention against the CPU model.
- WGPU validation errors fail the run. Totals exclude priming and the Metal diagnostic.

**Memory limits:** RSS and physical footprint include setup and cold work. The policy study also runs a CPU simulation before GPU initialization. Metal counters omit private compiler/driver memory.

[Full protocol](docs/report-protocol.md) and [metadata](results/pr-report-d5241b9/metadata.json).

</details>

## Reproduce and inspect

Pinned sources, patches, scripts and raw data are included. Requires Rust, Python, Git and a GPU backend; the Metal diagnostic requires macOS.

```sh
python3 scripts/run-report.py --out runs/my-pr-report
python3 scripts/report-sanity.py runs/my-pr-report
python3 scripts/render-report.py runs/my-pr-report
```

The report generator includes the published confirmation separately when source pins match.

- [Full tables](results/pr-report-d5241b9/analysis/tables.md), [timing intervals](results/pr-report-d5241b9/analysis/timing.csv), [analysis JSON](results/pr-report-d5241b9/analysis/evidence.json).
- Direct comparison: [raw frames](results/pr-report-d5241b9/direct/runs.jsonl.gz), [summary](results/pr-report-d5241b9/direct/summary.json), [priming](results/pr-report-d5241b9/direct/priming.jsonl.gz).
- Policy study: [raw frames](results/pr-report-d5241b9/policies/gpu.jsonl.gz), [summary](results/pr-report-d5241b9/policies/summary.json), [priming](results/pr-report-d5241b9/policies/priming.jsonl.gz).
- CPU sweep: [raw counts](results/pr-report-d5241b9/policies/simulation.jsonl.gz), [capacity/phase summaries](results/pr-report-d5241b9/policies/simulation-summary.json).
- [Confirmation results and rerun commands](results/confirmation-d5241b9/README.md).
- Supporting checks: [historical comparison](results/pr-report-d5241b9/analysis/sanity.md), [extraction rerun](results/reproduction-2026-09-27/README.md), [initial Metal probe](results/metal-cache-control-probe/README.md).
