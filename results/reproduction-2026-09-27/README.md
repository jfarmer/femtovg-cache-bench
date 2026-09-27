# Full rerun from the standalone repository

A fresh full rerun on 2026-09-27 from published commit `4b91f93dfb5ddbd01dc1d0cfc7ff435f1043dae2`: 240 direct-comparison GPU processes, 280 policy-study GPU processes, and 7,200 CPU simulations. The checkout stayed clean during measurement, and the experiments ran sequentially. Platform, adapter and Rust version match the historical runs: Apple M4 Max, Metal, macOS 26.6.2, Rust 1.96.0. This reuses the pinned historical FemtoVG/policy versions; it does not benchmark a newly rebased PR.

## What reproduced

- All 235,600 GPU flushes across 53,440 recorded frames match the historical pipeline-creation and cache-residency counts, including cold, warmup and transition frames.
- All 7,200 CPU simulation records match exactly. All renderer and source-archive hashes match.
- Live-pipeline counts match at every recorded frame. The capacity cliffs, flush-boundary tradeoffs, compulsory scan misses, and S3-FIFO adaptation behavior therefore remain unchanged.
- Direct-comparison completed-time medians range from 6.2% lower to 6.0% higher; policy-study medians range from 8.6% lower to 10.7% higher.

The original policy conclusions hold for these workloads. This is evidence that the extraction preserved behavior, not proof that every timing distribution is identical.

## Timing differences worth retaining

For the direct 65-state workload:

| Policy | Original median (ms) | Rerun median (ms) | Original p95 (ms) | Rerun p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| #343 | 23.02 | 21.98 | 24.57 | 22.76 |
| Flush-aware 64 | 1.06 | 1.01 | 2.32 | 1.30 |

The flush-aware policy still creates two pipelines per measured frame, versus 65 for #343. Its CPU p95 changes from 1.03 to 0.92 ms, while completion-wait p95 changes from 1.41 to 0.31 ms. The latter is calculated from each frame's completed time minus CPU time before taking quantiles; it includes the device poll/wait interval and scheduling. This locates much of the tail difference, but does not establish its exact system-level cause.

All 24 timing statistics flagged by the comparison's screening rule are lower completed-time p95/p99 values. No completed-time median or CPU-time statistic meets that rule. This screening threshold is an investigation aid, not a significance test. Some unflagged tails increase: flush-aware `batch-single` p95 rises from 1.09 to 1.58 ms.

Individual first-run extremes differ far more than the medians. Upstream's first cold 129-state frame falls from 1,145.29 to 59.24 ms. LRU's first-process hot-scan frame 90 falls from 5,760.32 to 112.50 ms. Counts match in those exact frames. Driver caches were not cleared between the historical experiment, validation runs, and this rerun. The pattern is consistent with warmed driver caches; that attribution is an inference, not a measured explanation. These original extreme timings did not reproduce and must not be presented as a stable cold-driver cost. No such frames were removed from either dataset.

The original synthetic runners and this measured revision inherit the process environment. Neither resets Metal caches or sets `MTL_SHADER_CACHE_SIZE`, and their metadata did not record that variable. A separate application-startup harness offered an undocumented `MTL_SHADER_CACHE_SIZE=0` mode and recorded it in its own results; that mode was not implemented by these synthetic runners. Historical metadata cannot rule out an externally supplied override. Future runs should record the inherited setting; disabling a cache is not proof that every system/driver cache has been cleared.

## Memory differences

Direct-comparison median peak RSS differs by at most 0.77 MiB. In the policy study, the largest median peak-RSS change is unlimited retention with split batches: 47.56 to 43.08 MiB. Entry counts and live-pipeline counts still match; RSS includes much more than the cache.

Metal allocated-resource counters match at every frame except ten frames (70–79) of the first LRU hot-scan process. Those samples rise from 17,022,976 to 33,800,192 bytes, an additional 16 MiB, then converge with the historical samples again. The cause is unresolved; the allocation counter alone cannot attribute it to pipeline objects. This transient difference is preserved in the raw data and comparison JSON.

## Uncertainty and complete data

- [Complete old/new tables](review/comparison.md), including p50/p95/p99, wait p95 and RSS.
- [Median confidence intervals](review/uncertainty.md), calculated from ten process-level summaries per case. Conservative order-statistic intervals have 97.85% coverage under the stated independent-run assumptions; they do not cover cross-machine/session variability.
- [Machine-readable comparison](review/comparison.json), including CPU statistics, intervals for medians of process-level p95/p99, paired extreme frames, and diagnostic mismatches.
- [Direct raw data](pr343/runs.jsonl.gz), [summary](pr343/summary.json), and [metadata](pr343/metadata.json).
- [Policy-study raw data](policy-study/gpu.jsonl.gz), [summary](policy-study/summary.json), and [metadata](policy-study/metadata.json).
- [CPU sweep](policy-study/simulation.jsonl.gz) and [summary](policy-study/simulation-summary.json).
- [Measurement provenance and exact commands](provenance.json).

## Reproduction

Run the full commands in the root [README](../../README.md), using a new output root with `pr343/` and `policy-study/` subdirectories as shown in `provenance.json`. Then compare it against the original baseline:

```sh
python3 scripts/compare-runs.py runs/my-rerun --out runs/my-comparison
```

To regenerate this report from the checked-in rerun without a GPU:

```sh
python3 scripts/compare-runs.py results/reproduction-2026-09-27 --out runs/reproduction-comparison
python3 -m unittest discover -s tests -v
```

The comparison refuses incomplete datasets and reports operation-count, source-hash, and simulation mismatches as failures. Timing differences are reported for investigation. Historical data remains under `results/pr343/` and `results/policy-study/`.
