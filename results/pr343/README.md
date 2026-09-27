# Real-device cache-pressure comparison for FemtoVG PR #343

PR #343 fixes repeated pipeline creation while the working set fits its threshold.
At 65 states, this synthetic sequence falls back to the original cache's behavior.
Our strict 128-entry LRU has its own cliff at 129 states; the flush-aware 64-entry
policy degrades more gradually and beats both larger-cache policies there.

This directly exercises the [reviewer's requested boundaries and mixed flushes](https://github.com/femtovg/femtovg/pull/343#issuecomment-5785645528).
It does **not** demonstrate a startup improvement for Alustin: the
[separate application comparison](../../docs/application-context.md) found that its working set fits
all three retained-cache policies.

## Method

Apple M4 Max, macOS 26.6.2, Metal, Rust 1.96.0, WGPU 30.0.1, release build.
Ten fresh processes per policy/workload pair: 240 processes total. Each process
records one cold frame, five warmup frames, and 100 measured frames. The tables
below use only the 24,000 measured frames; cold and warmup data remain in the raw
artifact. Order rotates across policies and workloads. No outliers were removed.

The common FemtoVG snapshot is `9f2523bb794089e9c1be8114057afb283e97a3ea`, with
the original accessed-bit sweep, PR #343's conditional sweep, the later flush-aware
64-entry LRU, or our app's strict 128-entry LRU transplanted onto it. Features,
instrumentation, dependency versions, and compiler settings are shared.
See the [benchmark source and full reproduction instructions](../../docs/comparison.md).

For a working set of N, a logical frame draws N−1 unique blend states, flushes,
then performs a separate one-state clear flush. **N includes the clear pipeline.**
The cold-frame creation count is asserted against N on the actual GPU. The mixed
case alternates glyph, clipped opacity layer, Gaussian-blur layer, screen, and
clear flushes. It uses 23 distinct states in total.

## Pipeline creation and retention

Actual newly created render pipelines per measured logical frame:

| Working set | Original sweep | PR #343 | Flush LRU 64 | Strict LRU 128 |
| --- | ---: | ---: | ---: | ---: |
| 63 | 63 | 0 | 0 | 0 |
| 64 | 64 | 0 | 0 | 0 |
| 65 | 65 | 65 | 2 | 0 |
| 80 | 80 | 80 | 17 | 0 |
| 129 | 129 | 129 | 66 | 129 |
| Mixed | 23 | 0 | 0 | 0 |

These counts held in **every measured frame of every run**, not just the medians.
The counter runs inside pipeline materialization; unchanged live-object counts
are not treated as evidence that no pipelines were recreated.

Retained entries after the large flush → after the clear, once warmed:

| Working set | Original sweep | PR #343 | Flush LRU 64 | Strict LRU 128 |
| --- | --- | --- | --- | --- |
| 63 | 62 → 1 | 63 → 63 | 63 → 63 | 63 → 63 |
| 64 | 63 → 1 | 64 → 64 | 64 → 64 | 64 → 64 |
| 65 | 64 → 1 | 64 → 1 | 64 → 64 | 65 → 65 |
| 80 | 79 → 1 | 79 → 1 | 79 → 64 | 80 → 80 |
| 129 | 128 → 1 | 128 → 1 | 128 → 64 | 128 → 128 |

In the mixed case, the original cache retains `1, 8, 7, 11, 1` entries after the
five flushes. All other policies retain 23 throughout. Live WGPU pipeline counts
after the completion wait match the final retained counts in these measurements.

The PR's threshold is not an LRU capacity limit. Below it, the accessed bits are
not reset. Above it, the periodic sweep can remove almost the entire previous
large flush after a lone clear. At 65 states, the 64-state draw and one-state clear
keep causing that behavior. This supports the reviewer's concern about churn but
does **not** show the PR making that churn worse than the original policy here.

The flush-aware cache protects all states used in its current flush, so its
retained count can exceed 64. At 129 states it preserves 63 drawing states plus the
clear across frames, instead of suffering a full cyclic miss sequence. Strict
LRU 128 thrashes on that 129-state sequence despite its larger capacity. Its strong
80-state result should not be attributed solely to a better eviction algorithm:
it also has twice the nominal capacity.

## Frame times and tails

Each cell is **p50 / p95 / p99 in milliseconds**, including CPU work, submissions,
and waiting for GPU completion. Quantiles are calculated within each process,
then independently median-aggregated across its ten runs. These are offscreen
logical-frame times, not display presentation latency or GPU timestamps.

| Working set | Original sweep | PR #343 | Flush LRU 64 | Strict LRU 128 |
| --- | --- | --- | --- | --- |
| 63 | 22.433 / 24.135 / 24.681 | 0.348 / 0.780 / 1.575 | 0.347 / 0.751 / 1.805 | 0.345 / 0.658 / 1.344 |
| 64 | 22.906 / 24.565 / 25.021 | 0.350 / 0.722 / 1.454 | 0.346 / 0.816 / 1.971 | 0.359 / 0.814 / 2.185 |
| 65 | 23.175 / 24.658 / 25.300 | 23.015 / 24.571 / 25.398 | 1.063 / 2.316 / 2.848 | 0.356 / 0.812 / 1.924 |
| 80 | 28.510 / 30.038 / 30.554 | 28.204 / 29.945 / 30.624 | 6.524 / 8.036 / 8.586 | 0.388 / 0.864 / 2.159 |
| 129 | 45.902 / 47.347 / 48.175 | 45.638 / 47.295 / 48.067 | 23.896 / 25.638 / 26.053 | 45.741 / 47.581 / 48.085 |
| Mixed | 9.215 / 10.622 / 11.205 | 0.801 / 1.752 / 3.542 | 0.782 / 2.022 / 3.583 | 0.789 / 1.792 / 3.154 |

The differences involving repeated creation dwarf ordinary run variation. Small
differences among sub-millisecond cache-hit cases do not establish a policy winner;
their tails include scheduling and GPU-wait variability, and 100 frames provides
only coarse p99 estimates. Driver caches were not reset between processes.

CPU-only p50, excluding the completion wait:

| Working set | Original sweep | PR #343 | Flush LRU 64 | Strict LRU 128 |
| --- | ---: | ---: | ---: | ---: |
| 63 | 21.927 | 0.116 | 0.115 | 0.117 |
| 64 | 22.420 | 0.116 | 0.119 | 0.120 |
| 65 | 22.595 | 22.475 | 0.835 | 0.116 |
| 80 | 27.891 | 27.671 | 6.077 | 0.130 |
| 129 | 45.158 | 44.723 | 23.043 | 44.922 |
| Mixed | 8.727 | 0.424 | 0.422 | 0.429 |

Most of the difference is already present before the GPU completion wait.
This measures render-pipeline creation requests, not how much compilation the
driver repeats internally; its own caches can still satisfy those requests.

## Memory

Median **peak process RSS**, MiB, across ten processes per cell. This is the
process-lifetime high-water value, including initialization and cold compilation.

| Working set | Original sweep | PR #343 | Flush LRU 64 | Strict LRU 128 |
| --- | ---: | ---: | ---: | ---: |
| 63 | 26.73 | 25.90 | 26.02 | 25.83 |
| 64 | 26.78 | 26.06 | 26.00 | 25.88 |
| 65 | 26.73 | 26.98 | 26.30 | 25.91 |
| 80 | 27.39 | 27.54 | 27.43 | 26.56 |
| 129 | 29.47 | 29.59 | 29.50 | 29.52 |
| Mixed | 30.55 | 30.95 | 31.24 | 30.99 |

Retaining more entries did not cause a proportional increase in peak RSS. In the
80-state sequence our 128-entry cache measured about 0.98 MiB less peak RSS than
PR #343, despite retaining more pipelines. In the mixed sequence all retained
policies measured roughly 0.4–0.7 MiB above the original sweep. Peak RSS includes
allocation and driver/compiler activity, so these are process-level observations,
not estimates of each cached pipeline's size.

Metal `currentAllocatedSize` was identical across policies and all completed-frame
samples within each workload:

| Working set | Metal resource allocations, MiB |
| --- | ---: |
| 63 | 2.266 |
| 64 | 2.266 |
| 65 | 2.297 |
| 80 | 2.297 |
| 129 | 6.391 |
| Mixed | 1.703 |

This counter measures Metal resource allocations, **not all private driver or
compiler memory**. Its lack of response to the pipeline-count changes makes it
unsuitable as a pipeline-memory proxy in this experiment. It is sampled after
GPU completion, so it also cannot establish peak transient GPU allocation.
Complete driver-memory accounting remains outside this benchmark's measurements.

## Artifacts and validation

- [Raw frames](runs.jsonl.gz): all 25,440 cold, warmup, and measured frames, including
  per-flush creation/retention counts, timings, live pipeline counts, and Metal bytes.
- [Summary](summary.json): individual run summaries and aggregate medians, including
  peak RSS, cold-frame time, timing tails, and sampled Metal resource maxima.
- [Metadata](metadata.json): toolchain, platform, archive/lock/source/executable hashes.
  Each raw run also records its adapter and ordering position.

All 240 runs completed on Metal with validation enabled, no uncaptured GPU errors,
and nonzero WGPU object counters and RSS. Offline checks verified exactly ten runs
per pair, 100 measured frames per run, and the creation counts above in every one
of the 24,000 measured frames. No pixel-reference comparison was performed.
The app and its production renderer code were not changed by this experiment.
