# Capacity and admission policy study

This extends the original PR #343 benchmark with a shared, generic Rust cache
implementation used by both a deterministic simulator and the real FemtoVG WGPU
renderer. It changes only this standalone benchmark. The production app is untouched.

The [measured results](../results/policy-study/README.md) include
all ten GPU rounds, capacity curves, and process memory comparisons.

```sh
python3 scripts/femtovg-policy-study.py build
python3 scripts/femtovg-policy-study.py simulate --out runs/policy-study/my-run
python3 scripts/femtovg-policy-study.py gpu --runs 10 --out runs/policy-study/my-run
```

Use a new output directory; existing simulation/GPU results will not be overwritten.
`summarize --out ...` recalculates the summary from saved GPU frames;
`simulation-summary --out ...` aggregates the CPU sweep into capacity curves. The runner
uses the external `time` utility from `PATH` to record peak RSS and OS process statistics on macOS/Linux.
On macOS, the summary also extracts the distinct peak physical-footprint counter
from those raw statistics. This broader OS accounting must not be conflated with RSS.
Metal resource bytes are sampled after each completed GPU frame, subject to the
limitations described in the original [comparison guide](comparison.md).

## Policies

- **LRU:** strict capacity, using the `lru` crate.
- **Flush-aware LRU:** same LRU ordering, with eviction at flush completion and
  protection for entries used in that flush. Capacity is a soft target. Unlike the
  previous experiment's flush-stamp sort, access order breaks ties within a flush;
  this makes simulation and GPU behavior deterministic, and avoids allocating and
  sorting a candidate vector. This is a policy refinement, not the exact old patch.
- **S3-FIFO:** entry-count version of the original algorithm: small-queue target
  `max(1, floor(C/10))`, main target and ghost capacity `C - small`; two hits promote
  small entries, capped 2-bit reuse credits protect main entries. Ghosts contain
  keys, not pipeline objects. Eviction begins when total resident capacity is full;
  queue targets are not individually enforced during initial filling. Promotions
  reset reuse credits. This follows the original algorithm, not the later
  libCacheSim variant that inserts cold entries into main during initial filling.
  See the [authors' description](https://s3fifo.com/blog/2023/08/01/fifo-queues-are-all-you-need-for-cache-eviction/)
  and [original reference implementation](https://github.com/1a1a11a/libCacheSim/blob/develop/libCacheSim/cache/eviction/S3FIFOv0.c).
- **Retain:** never evict; a performance reference and demonstration of memory
  growth under streams of new states. Its supplied capacity does not limit it.

Each policy has the same generic value interface. The simulator stores unit values;
the renderer stores actual `wgpu::RenderPipeline` objects. For every GPU flush,
actual materialization and residency counts must equal the simulator's predictions.
The renderer also fails on GPU validation errors and checks live-object counters.

## Trace design

Workload **scale W** is independent of cache **capacity C**. A sweep holds the trace
fixed while changing capacity. Ten seeds are used; only the shuffled workload
depends on the seed, so repeated deterministic simulations are not independent
statistical evidence.

Each trace has 100 logical frames. State 0 is a clear pipeline; draw states use four
independent blend-factor digits, allowing 10,000 distinct draw keys. Draws target
a 64×64 texture without anti-aliasing. Each ordinary frame has a draw flush and a
separate clear flush. The simulated access stream skips consecutive repeated keys
within a flush, matching FemtoVG's unchanged-current-pipeline optimization.

| Trace | Sequence |
| --- | --- |
| stable | W/2 total states |
| cycle-minus / at / plus / double | W−1 / W / W+1 / 2W total states, including clear |
| shuffle-plus | Same W+1 set, draw order independently shuffled each frame |
| hot-scan | W/4 hot draw states repeated four times; every tenth frame starting at 10, visit 4W never-before-used states, then revisit the hot set |
| switch | Alternate disjoint sets of 3W/4−1 draw states every 20 frames; clear is shared |
| overlap | Same switching schedule, with the second set offset by W/4 |
| burst | Normally W/2 total states; at frames 10, 35, 60, and 85 draw 4W total states from the same larger set |
| batch-single / split | Visit 2W−1 draw states twice, then clear; identical accesses in one flush or chunks of eight commands |

The CPU sweep covers all 12 traces × three scales (64/128/256) × five capacities
(32/64/128/256/512) × four policies × ten seeds: 7,200 simulations. It records
per-frame misses, requests, resident/ghost counts, and total evictions/peak counts.
These are exact policy counts, not simulated GPU timings or memory estimates.

After inspecting the sweep, real-GPU cases were selected to cover both improvements
and regressions: cycle-plus W=128 at C=128 and C=256; shuffle-plus W=128/C=128;
hot-scan W=64/C=64; switch W=64/C=64; batch-single and batch-split W=64/C=64.
Four policies × seven cases × ten independent processes = 280 GPU runs.
Workload and policy order rotate; all runs are retained.

## Interpretation

Timing summaries use frames 10–99. The first ten are initialization/learning data
and remain in the raw output. Later scans and transitions stay in the measured set;
phase-specific summaries distinguish their cost from ordinary frames. Quantiles are
nearest-rank within each run, then independently median-aggregated across ten runs.
Ninety measured frames makes p99 effectively the maximum; do not overinterpret it.
Frame CPU time includes drawing, encoding, submission, and the small diagnostic
bookkeeping common to all policies. Completed time also includes the GPU wait.

RSS is process lifetime high-water, including the preliminary CPU simulation and
GPU initialization. The model uses unit values and drops its cache before GPU setup,
but its Rust allocator activity is still part of process RSS. Driver caches are
not cleared between processes; cold here means a new process/application cache.
Pipeline materialization counts are not claims about repeated internal compilation.
Ghost entry counts are reported separately because capacity equality does not imply
identical metadata memory. Metal allocated-resource bytes do not include all private
driver/compiler memory. No pixel-reference comparisons are performed.

The flush-aware policy can exceed its target, so a low miss count must be read
alongside residency and memory. A never-repeated scan has compulsory misses even
with unlimited retention; increasing capacity cannot eliminate those misses.
