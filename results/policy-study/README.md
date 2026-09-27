# FemtoVG cache policies across capacities and changing workloads

The experiment compares strict LRU, flush-aware LRU, original S3-FIFO, and retaining
every pipeline. Workload scale and cache capacity vary independently. A shared Rust
implementation drives both simulation and real WGPU pipeline storage; every GPU
flush asserts that actual creations and retained entries match the model.

The implementation and reproduction steps are in
[Policy study methodology](../../docs/policy-study.md).
The earlier [PR #343 comparison](../pr343/README.md) used different
policy implementations/workloads. Compare policies within this experiment rather
than treating timing differences between the two reports as regressions.

## Findings

- **Capacity has a cliff, not a universally good number.** For the 129-state cycle,
  strict LRU at capacity 128 recreates all 129 pipelines every frame: 43.98 ms p50.
  At capacity 256 it creates none after warming: 0.47 ms. Both 256 and 512 retain
  only 129 objects in the simulation; reserving a larger limit does not force that
  many pipeline objects to exist. A capacity of 129 should suffice for this exact
  trace too, although it was not one of the measured capacities.
- **Access order matters enormously.** Shuffling the same 129-state set reduces
  LRU's mean creations from 129 to about 6.5/frame and p50 from 43.98 to 2.97 ms.
  A cyclic capacity-plus-one example is useful as a worst case, but does not
  describe arbitrary application behavior.
- **S3-FIFO resists scans at a strict resident limit.** At capacity 64 it matches
  unlimited retention's compulsory-miss count while keeping 64 versus 2,321
  pipelines. Scan-frame medians are 101.37 versus 101.27 ms, compared with
  106.87 ms for LRU. Most scan cost is first use of new states, which eviction
  policy cannot remove. Ordinary frames are about 0.64 ms for all four policies.
- **That protection has an adaptation cost.** Switching disjoint screens takes LRU
  one frame to learn; S3-FIFO takes two to four frames. Across measured frames,
  S3-FIFO creates 5.21 pipelines/frame versus LRU's 2.09, and p95 rises from
  2.53 to 13.71 ms. A lower miss count on scans does not imply better interaction
  latency for screen transitions.
- **Flush-aware eviction buys performance partly through extra residency.**
  With the same request sequence in one flush it retains 128 objects against a
  nominal capacity of 64 and achieves 0.67 ms p50. Split into chunks of eight,
  its peak is 72, but it recreates 255 pipelines/frame and takes 89.53 ms.
  In the scan workload it temporarily reaches 320 entries against a target of 64.

For a bounded general-purpose default, these results support measuring the
application's working set and reuse patterns before choosing either a capacity or
a more complex policy. S3-FIFO is promising for scan pollution; it is not a clear
replacement for LRU here. Flush protection is useful when temporary overshoot is
acceptable, but cannot be described as equivalent to a hard capacity bound.

These are synthetic offscreen frame measurements, not Alustin startup times.
They characterize policy behavior on one Metal device. No production policy
change follows automatically from this experiment.

## CPU simulation: capacity curves

The sweep covers 12 workloads, scales 64/128/256, capacities 32/64/128/256/512, four
policies, and ten seeds: 7,200 simulations. Only shuffled traces depend on the seed;
the repeated deterministic traces are not independent statistical samples.
The following tables hold workload scale at 128 and report mean misses per logical
frame over frames 10–99. These are exact simulation counts, not predicted timings.

**Fixed cyclic working set: 129 distinct pipelines.**

| Capacity | LRU | Flush LRU | S3-FIFO | Retain everything |
| --- | ---: | ---: | ---: | ---: |
| 32 | 129 | 98 | 129 | 0 |
| 64 | 129 | 66 | 129 | 0 |
| 128 | 129 | 2 | 6.39 | 0 |
| 256 | 0 | 0 | 0 | 0 |
| 512 | 0 | 0 | 0 | 0 |

Increasing capacity beyond the working set eliminates misses for all policies.
256 and 512 provide the same hit behavior here; 256 is not a special optimum.
The flush-aware policy's capacity is a soft target and it can hold larger sets
inside a flush. Its results must be read alongside peak residency.

**Switching between two disjoint drawing sets: 96 states per screen including a
shared clear, 191 distinct states across both screens.**

| Capacity | LRU | Flush LRU | S3-FIFO | Retain everything |
| --- | ---: | ---: | ---: | ---: |
| 32 | 96 | 66.38 | 96 | 1.06 |
| 64 | 96 | 35.80 | 70.54 | 1.06 |
| 128 | 4.22 | 3.16 | 10.41 | 1.06 |
| 256 | 1.06 | 1.06 | 1.06 | 1.06 |
| 512 | 1.06 | 1.06 | 1.06 | 1.06 |

The nonzero retain-everything value is the compulsory first visit to the second
screen, which occurs after the initial ten frames. S3-FIFO's protection of old
entries can delay learning a replacement working set; it is not a universal upgrade.

**32 hot drawing states, a shared clear, and nine scans of 512 new states each.**

| Capacity | LRU | Flush LRU | S3-FIFO | Retain everything |
| --- | ---: | ---: | ---: | ---: |
| 32 | 87.40 | 53.20 | 55.44 | 51.20 |
| 64 | 54.50 | 51.30 | 51.20 | 51.20 |
| 128 | 54.50 | 51.30 | 51.20 | 51.20 |
| 256 | 54.50 | 51.30 | 51.20 | 51.20 |
| 512 | 54.50 | 51.30 | 51.20 | 51.20 |

51.20 misses/frame are compulsory first uses. S3-FIFO preserves the hot entries at
capacity 64 and reaches that lower bound without retaining the growing scan history.
Increasing LRU capacity from 64 to 512 does not help this particular scan pattern.

## GPU validation and measurement

Selected cases include favorable and unfavorable outcomes for each bounded policy:
the 129-state cycle at capacities 128 and 256; shuffled 129-state access at 128;
hot entries plus scans at 64; disjoint-screen switching at 64; and identical drawing
in one flush versus chunks of eight commands at 64.

There are ten fresh processes per case/policy pair, with rotating order and the
same seed across policies within a round. Each process renders 100 offscreen frames
on the Apple M4 Max using Metal. Frames 0–9 remain in the raw data but are excluded
from timing summaries. Later transitions and scans are included, with separate
phase summaries. No timing outliers are discarded.

CPU time includes command generation, encoding, submission, and common diagnostic
bookkeeping. Completed time includes the GPU wait; it is neither GPU-only time nor
presentation latency. p50/p95/p99 are nearest-rank per-process quantiles, then
independently median-aggregated across ten processes. With 90 measured frames, p99
is effectively the run's maximum.

## GPU results

All 280 processes completed successfully: 28,000 frames, including 25,200 measured
frames. Every flush matched the CPU model for materializations and residency. The
simulation and GPU runs used the same binary hash, recorded in their metadata.

Times below are milliseconds per completed logical frame. Each cell is the median
of ten process-level quantiles; creations/frame are likewise medians of process
means. Peak entries count cache-owned pipelines, including temporary overshoot.

| Workload (scale / capacity) | Policy | Creations/frame | Peak entries | p50 ms | p95 ms | p99 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| cycle-plus (128/128) | LRU | 129.00 | 128 | 43.98 | 45.56 | 46.51 |
| cycle-plus (128/128) | Flush LRU | 2.00 | 129 | 1.21 | 2.34 | 3.28 |
| cycle-plus (128/128) | S3-FIFO | 6.39 | 128 | 2.93 | 5.76 | 7.12 |
| cycle-plus (128/128) | Retain | 0.00 | 129 | 0.48 | 1.01 | 1.99 |
| cycle-plus (128/256) | LRU | 0.00 | 129 | 0.47 | 1.01 | 2.52 |
| cycle-plus (128/256) | Flush LRU | 0.00 | 129 | 0.47 | 0.99 | 1.23 |
| cycle-plus (128/256) | S3-FIFO | 0.00 | 129 | 0.48 | 1.00 | 1.32 |
| cycle-plus (128/256) | Retain | 0.00 | 129 | 0.48 | 0.98 | 1.17 |
| shuffle-plus (128/128) | LRU | 6.49 | 128 | 2.97 | 4.70 | 5.51 |
| shuffle-plus (128/128) | Flush LRU | 2.00 | 129 | 1.24 | 1.91 | 3.39 |
| shuffle-plus (128/128) | S3-FIFO | 4.72 | 128 | 2.49 | 4.31 | 5.45 |
| shuffle-plus (128/128) | Retain | 0.00 | 129 | 0.51 | 1.03 | 2.18 |
| hot-scan (64/64) | LRU | 27.30 | 64 | 0.64 | 106.87 | 109.01 |
| hot-scan (64/64) | Flush LRU | 25.70 | 320 | 0.65 | 101.69 | 104.32 |
| hot-scan (64/64) | S3-FIFO | 25.60 | 64 | 0.64 | 101.37 | 103.00 |
| hot-scan (64/64) | Retain | 25.60 | 2321 | 0.65 | 101.27 | 103.71 |
| switch (64/64) | LRU | 2.09 | 64 | 0.50 | 2.53 | 18.84 |
| switch (64/64) | Flush LRU | 1.56 | 95 | 0.49 | 2.45 | 19.37 |
| switch (64/64) | S3-FIFO | 5.21 | 64 | 0.53 | 13.71 | 19.22 |
| switch (64/64) | Retain | 0.52 | 95 | 0.48 | 0.84 | 18.25 |
| batch-single (64/64) | LRU | 255.00 | 64 | 88.62 | 90.29 | 91.08 |
| batch-single (64/64) | Flush LRU | 0.00 | 128 | 0.67 | 1.09 | 1.64 |
| batch-single (64/64) | S3-FIFO | 255.00 | 64 | 88.53 | 90.28 | 91.64 |
| batch-single (64/64) | Retain | 0.00 | 128 | 0.69 | 1.27 | 1.63 |
| batch-split (64/64) | LRU | 255.00 | 64 | 89.69 | 92.27 | 93.83 |
| batch-split (64/64) | Flush LRU | 255.00 | 72 | 89.53 | 91.85 | 92.97 |
| batch-split (64/64) | S3-FIFO | 255.00 | 64 | 90.04 | 91.80 | 94.24 |
| batch-split (64/64) | Retain | 0.00 | 128 | 1.78 | 2.31 | 2.72 |

### Process memory

Each cell is **peak RSS / peak physical footprint**, in MiB, independently
median-aggregated across ten processes. These include the whole process lifetime.

| Workload (scale / capacity) | LRU | Flush LRU | S3-FIFO | Retain |
| --- | ---: | ---: | ---: | ---: |
| cycle-plus (128/128) | 30.4 / 461.9 | 29.8 / 461.7 | 30.1 / 462.0 | 29.7 / 461.5 |
| cycle-plus (128/256) | 29.7 / 461.5 | 29.7 / 461.5 | 29.7 / 461.6 | 29.7 / 461.5 |
| shuffle-plus (128/128) | 30.1 / 462.0 | 29.9 / 461.7 | 30.0 / 461.8 | 29.7 / 461.6 |
| hot-scan (64/64) | 96.9 / 514.9 | 97.3 / 515.3 | 96.9 / 514.9 | 109.5 / 527.5 |
| switch (64/64) | 28.0 / 456.4 | 28.3 / 456.7 | 28.4 / 456.8 | 28.1 / 456.5 |
| batch-single (64/64) | 30.7 / 460.0 | 29.2 / 458.7 | 30.8 / 460.0 | 29.2 / 458.8 |
| batch-split (64/64) | 34.6 / 460.9 | 34.7 / 461.0 | 34.6 / 460.9 | 47.6 / 509.1 |

## Memory interpretation

Peak RSS and macOS peak physical footprint are both preserved. They are different
OS metrics and should not be added together. Apple's `time` implementation reports
`ru_maxrss` for the former and `ri_lifetime_max_phys_footprint` for the latter.
[Apple's time source](https://github.com/apple-oss-distributions/shell_cmds/blob/main/time/time.c).
Physical-footprint accounting includes dirty/compressed memory and graphics-related
allocations that are relevant to Apple silicon applications.
[Apple's game-memory explanation](https://developer.apple.com/videos/play/wwdc2022/10106/).

These are process-lifetime peaks, including the preliminary unit-value simulation,
GPU setup, and cold frames. They cannot be attributed solely to cached pipelines.
The Metal resource counter is sampled after completed frames and is a third,
narrower measure; it does not count all private compiler/driver memory. Cache entry
counts, ghost-key counts, and live pipeline objects are also recorded separately.

Driver caches are not reset between processes. In the first LRU hot-scan run,
initial encounters with new pipeline states took about 4–6 seconds per scan; later
runs reused warmed driver state and were much faster. That run is retained in the
raw data and the ten-run aggregation. These measurements characterize application
cache policies predominantly with a warm driver, not cold-driver worst-case latency.

For the scan workload, unlimited retention adds approximately 12.6 MiB to both
peak RSS and physical footprint relative to S3-FIFO, while holding 2,257 extra
pipelines. Sampled Metal resource peaks are identical at 32.23 MiB, so that counter
alone misses the difference. These are process-level differences, not an estimate
of bytes per pipeline.

In the split-batch case, retaining everything also raises memory despite improving
throughput. Pipeline residency, buffer lifetimes, and driver allocation behavior
can all contribute; this experiment does not isolate their individual shares.
The large common gap between RSS and physical footprint is likewise not attributed
to a specific allocation owner.

## Artifacts

- [Raw GPU runs](gpu.jsonl.gz), [build/environment metadata](metadata.json), and
  [per-run timing, phase, and memory summaries](summary.json).
- [Raw simulations](simulation.jsonl.gz), [simulation metadata](simulation-metadata.json),
  and [capacity/phase summaries](simulation-summary.json).
- The [source and reproduction guide](../../docs/policy-study.md)
  describes exact trace generation, S3-FIFO parameters, and policy differences.

The production application and renderer are not modified by this experiment.
