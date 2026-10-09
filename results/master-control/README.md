# Master as the control: #343, #371 and the 512/64 rule on every workload

Measured 2026-10-09 on an Apple M4 Max with Metal (macOS 26.6.2, rustc 1.96.0) with the
direct-comparison harness (`scripts/femtovg-cache-synthetic.py`), ten rounds per cell, three for
`scan`. Policies, all built from femtovg 9f2523b (`vendor/femtovg.json`):

- `upstream`: master, no patch. Called "master" in the tables.
- `pr343`: #343. Sweep every pipeline not bound in the flush once the cache holds more than 64.
- `pr371`: #371. Drop a pipeline after 1,024 flushes without being bound. No size limit.
- `flush-lru512-idle64`: PR #366 as updated, called "this PR" in the tables. Evict only above 512
  entries, least recently used first, never a pipeline bound in the last 64 flushes. The patch is
  `patches/flush-lru512-idle64.patch` on top of `patches/flush-lru64.patch`.

Workloads:

- `63` to `129`: that many distinct pipelines drawn every frame in one flush, then a clear-only
  flush. The tables report the median frame.
- `mixed`: glyph, clipped-layer, filter, screen and clear flushes. Median frame.
- `return:A:B`: set A for 10 frames, a disjoint set B until 10 frames before the end, then A again.
  Two flushes per frame; 600 frames put A away for 1,160 flushes, 300 frames for 560. The tables
  report the frame on which A is drawn again.
- `scan:2`: every frame draws 2 blend states no earlier frame used, for 300 frames. Median frame.

Master drops every pipeline a flush did not bind, so it rebuilds its whole set every frame in every
workload, and its return frame is an ordinary frame. A cell near 0% means that policy also rebuilt
the set on that frame.

Each run directory holds the raw per-frame records (`runs.jsonl.gz`), the runner's `summary.json`
and `metadata.json`. `summary.json` averages over all stages of the `return` and `scan` workloads
and is not meaningful for them; the tables come from the per-frame records, through
`scripts/control_table.py`.

## Frame time against master

| Scenario | master | #343 | #371 | this PR |
| --- | ---: | ---: | ---: | ---: |
| 63 pipelines every frame | 20.87 ms | -98% | -98% | -98% |
| 64 pipelines every frame | 21.23 ms | -98% | -98% | -98% |
| 65 pipelines every frame | 21.56 ms | +1% | -98% | -98% |
| 80 pipelines every frame | 26.85 ms | 0% | -99% | -99% |
| 129 pipelines every frame | 43.05 ms | +1% | -99% | -99% |
| glyph, clipped-layer, filter, screen and clear flushes | 8.37 ms | -91% | -91% | -91% |
| 20+20, first set back after 560 flushes | 6.65 ms | -96% | -97% | -96% |
| 40+40, first set back after 560 flushes | 13.23 ms | +5% | -98% | -98% |
| 20+20, first set back after 1,160 flushes | 6.52 ms | -96% | +12% | -96% |
| 40+40, first set back after 1,160 flushes | 13.23 ms | +4% | +3% | -98% |
| 2 new blend states every frame | 1.33 ms | -27% | -27% | -24% |

Pipelines kept at the end of each scenario:

| Scenario | master | #343 | #371 | this PR |
| --- | ---: | ---: | ---: | ---: |
| 63 pipelines every frame | 1 | 63 | 63 | 63 |
| 64 pipelines every frame | 1 | 64 | 64 | 64 |
| 65 pipelines every frame | 1 | 1 | 65 | 65 |
| 80 pipelines every frame | 1 | 1 | 80 | 80 |
| 129 pipelines every frame | 1 | 1 | 129 | 129 |
| glyph, clipped-layer, filter, screen and clear flushes | 1 | 23 | 23 | 23 |
| 20+20, first set back after 560 flushes | 1 | 39 | 39 | 39 |
| 40+40, first set back after 560 flushes | 1 | 40 | 79 | 79 |
| 20+20, first set back after 1,160 flushes | 1 | 39 | 39 | 39 |
| 40+40, first set back after 1,160 flushes | 1 | 40 | 79 | 79 |
| 2 new blend states every frame | 1 | 27 | 603 | 512 |

## Every cell

| Scenario | Policy | Rebuilt | Frame (ms) | Pipelines kept |
| --- | --- | ---: | ---: | ---: |
| 63 pipelines every frame, median frame | master | 63 | 20.865 | 1 |
| 63 pipelines every frame, median frame | #343 | 0 | 0.354 | 63 |
| 63 pipelines every frame, median frame | #371 | 0 | 0.344 | 63 |
| 63 pipelines every frame, median frame | this PR | 0 | 0.361 | 63 |
| 64 pipelines every frame, median frame | master | 64 | 21.233 | 1 |
| 64 pipelines every frame, median frame | #343 | 0 | 0.347 | 64 |
| 64 pipelines every frame, median frame | #371 | 0 | 0.345 | 64 |
| 64 pipelines every frame, median frame | this PR | 0 | 0.363 | 64 |
| 65 pipelines every frame, median frame | master | 65 | 21.559 | 1 |
| 65 pipelines every frame, median frame | #343 | 65 | 21.700 | 1 |
| 65 pipelines every frame, median frame | #371 | 0 | 0.361 | 65 |
| 65 pipelines every frame, median frame | this PR | 0 | 0.351 | 65 |
| 80 pipelines every frame, median frame | master | 80 | 26.854 | 1 |
| 80 pipelines every frame, median frame | #343 | 80 | 26.767 | 1 |
| 80 pipelines every frame, median frame | #371 | 0 | 0.375 | 80 |
| 80 pipelines every frame, median frame | this PR | 0 | 0.372 | 80 |
| 129 pipelines every frame, median frame | master | 129 | 43.052 | 1 |
| 129 pipelines every frame, median frame | #343 | 129 | 43.372 | 1 |
| 129 pipelines every frame, median frame | #371 | 0 | 0.442 | 129 |
| 129 pipelines every frame, median frame | this PR | 0 | 0.444 | 129 |
| glyph, clipped-layer, filter, screen and clear flushes, median frame | master | 23 | 8.365 | 1 |
| glyph, clipped-layer, filter, screen and clear flushes, median frame | #343 | 0 | 0.779 | 23 |
| glyph, clipped-layer, filter, screen and clear flushes, median frame | #371 | 0 | 0.779 | 23 |
| glyph, clipped-layer, filter, screen and clear flushes, median frame | this PR | 0 | 0.777 | 23 |
| 20+20, first set back after 560 flushes, return frame | master | 20 | 6.653 | 1 |
| 20+20, first set back after 560 flushes, return frame | #343 | 0 | 0.240 | 39 |
| 20+20, first set back after 560 flushes, return frame | #371 | 0 | 0.228 | 39 |
| 20+20, first set back after 560 flushes, return frame | this PR | 0 | 0.236 | 39 |
| 40+40, first set back after 560 flushes, return frame | master | 40 | 13.226 | 1 |
| 40+40, first set back after 560 flushes, return frame | #343 | 39 | 13.835 | 40 |
| 40+40, first set back after 560 flushes, return frame | #371 | 0 | 0.268 | 79 |
| 40+40, first set back after 560 flushes, return frame | this PR | 0 | 0.269 | 79 |
| 20+20, first set back after 1,160 flushes, return frame | master | 20 | 6.517 | 1 |
| 20+20, first set back after 1,160 flushes, return frame | #343 | 0 | 0.236 | 39 |
| 20+20, first set back after 1,160 flushes, return frame | #371 | 19 | 7.277 | 39 |
| 20+20, first set back after 1,160 flushes, return frame | this PR | 0 | 0.245 | 39 |
| 40+40, first set back after 1,160 flushes, return frame | master | 40 | 13.226 | 1 |
| 40+40, first set back after 1,160 flushes, return frame | #343 | 39 | 13.698 | 40 |
| 40+40, first set back after 1,160 flushes, return frame | #371 | 39 | 13.677 | 79 |
| 40+40, first set back after 1,160 flushes, return frame | this PR | 0 | 0.270 | 79 |
| 2 new blend states every frame, median frame | master | 3 | 1.333 | 1 |
| 2 new blend states every frame, median frame | #343 | 2 | 0.970 | 27 |
| 2 new blend states every frame, median frame | #371 | 2 | 0.968 | 603 |
| 2 new blend states every frame, median frame | this PR | 2 | 1.013 | 512 |

## Reproduce

```sh
P=upstream,pr343,pr371,flush-lru512-idle64
python3 scripts/femtovg-cache-synthetic.py --build-only --policies $P
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 100 --policies $P --out runs/steady
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 600 --policies $P --scenarios return:20:20,return:40:40 --out runs/return-1160
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 300 --policies $P --scenarios return:20:20,return:40:40 --out runs/return-560
python3 scripts/femtovg-cache-synthetic.py --runs 3 --frames 300 --policies $P --scenarios scan:2 --out runs/scan
python3 scripts/control_table.py runs percent
python3 scripts/control_table.py runs full
```
