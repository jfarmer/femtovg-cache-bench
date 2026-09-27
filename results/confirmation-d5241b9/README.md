# Focused randomized confirmation

A separate repeat of the proposal versus #343 using the exact pinned renderer sources and release settings of the [primary report](../../REPORT.md). This is a synthetic library benchmark; no application usage was recorded.

Twenty paired blocks per workload, with policy order randomized and balanced ten-first/ten-second for each policy. Workload order is randomized within each round. The scheduling algorithm, seed, and protocol were committed before measurement; the full realized schedule was saved before the first launch. Each process records one initial frame, five warmup frames, and 100 measured frames. Two full priming passes precede the measured blocks. The Metal cache-size override is explicitly unset; subsequent driver-cache eviction/invalidation remains uncontrolled. No runs are excluded.

Harness commit: `8400181847fbcce80fca9cbe69954c2a65e2cb6d`. Started: 2026-09-27T14:00:07.976264+00:00. Finished: 2026-09-27T14:01:21.424087+00:00.

| Workload | Policy | Creations/frame | Primary median (ms) | Repeat median (ms) | Repeat p95 (ms) |
| --- | --- | ---: | ---: | ---: | ---: |
| 64 | #343 | 0 | 0.377 | 0.351 | 0.622 |
| 64 | Proposed | 0 | 0.473 | 0.320 | 0.597 |
| 65 | #343 | 65 | 27.184 | 25.182 | 26.124 |
| 65 | Proposed | 2 | 1.187 | 1.128 | 1.384 |
| mixed | #343 | 0 | 0.783 | 0.745 | 0.918 |
| mixed | Proposed | 0 | 0.782 | 0.748 | 0.901 |

| Workload | Median paired proposed/#343 ratio | Observed pair range |
| --- | ---: | ---: |
| 64 | 0.998 | 0.822–1.169 |
| 65 | 0.044 | 0.042–0.048 |
| mixed | 0.998 | 0.859–1.161 |

Ratios pair process medians within adjacent comparison blocks; below one favors the proposal. The ranges describe the twenty observed pairs, not confidence intervals. Table p95 values are medians of within-process p95 values. This small repeat checks reproducibility and obvious differences; it does not establish equivalence, a population tail latency, or application-wide speedups.

All 120 measured and 12 priming processes match the primary campaign's creation/residency profile at every frame and flush. Full frames, process timestamps, and actual execution order are retained. The protocol is in [metadata.json](metadata.json); raw data is in [runs.jsonl.gz](runs.jsonl.gz) and [priming.jsonl.gz](priming.jsonl.gz). [summary.json](summary.json) includes CPU quantiles, memory diagnostics, and individual process summaries; [paired-ratios.json](paired-ratios.json) preserves every paired comparison. [checksums.json](checksums.json) fingerprints the recorded inputs.

```sh
python3 scripts/confirm-report.py --out runs/my-confirmation
python3 scripts/confirm-report.py --summarize --out results/confirmation-d5241b9
```
