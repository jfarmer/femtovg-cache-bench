# #366 and #371 compared, and the 512/64 variant

Measured 2026-10-06 on an Apple M4 Max with Metal, with the direct-comparison harness
(`scripts/femtovg-cache-synthetic.py`), ten rounds per cell unless noted. Policies:

- `pr343`: sweep every pipeline not bound in the flush once the cache holds more than 64.
- `flush-lru64`: #366 as pushed. Over 64 entries, evict the least recently used pipelines the
  current flush did not bind, down to 64.
- `pr371`: #371. Drop a pipeline after 1024 flushes without being bound. No size limit.
- `flush-lru512-idle64`: #366 with its cap raised to 512 and no eviction of a pipeline bound in the
  last 64 flushes. The patch is `patches/flush-lru512-idle64.patch` on top of `flush-lru64.patch`.

Each run directory holds the raw per-frame records (`runs.jsonl.gz`), the runner's `summary.json`
and `metadata.json`. The tables for the `return` and `scan` workloads come from the per-frame
records; `summary.json` averages over all stages of those workloads and is not meaningful for them.

## Steady working sets (`steady/`)

N distinct pipelines drawn every frame in one flush, then a clear-only flush. Times include CPU
work and the GPU completion wait.

| Workload | Policy | Creations/frame | Median (ms) | p95 (ms) | Pipelines kept |
| --- | --- | ---: | ---: | ---: | ---: |
| 63 | #343 | 0 | 0.339 | 0.568 | 63 |
| 63 | #366 as pushed | 0 | 0.326 | 0.573 | 63 |
| 63 | #371 | 0 | 0.395 | 0.582 | 63 |
| 63 | 512/64 | 0 | 0.314 | 0.564 | 63 |
| 64 | #343 | 0 | 0.365 | 0.589 | 64 |
| 64 | #366 as pushed | 0 | 0.343 | 0.588 | 64 |
| 64 | #371 | 0 | 0.304 | 0.577 | 64 |
| 64 | 512/64 | 0 | 0.310 | 0.597 | 64 |
| 65 | #343 | 65 | 21.699 | 22.524 | 1 |
| 65 | #366 as pushed | 2 | 0.948 | 1.108 | 64 |
| 65 | #371 | 0 | 0.346 | 0.659 | 65 |
| 65 | 512/64 | 0 | 0.346 | 0.625 | 65 |
| 80 | #343 | 80 | 26.826 | 27.776 | 1 |
| 80 | #366 as pushed | 17 | 6.020 | 6.300 | 64 |
| 80 | #371 | 0 | 0.374 | 0.776 | 80 |
| 80 | 512/64 | 0 | 0.369 | 0.696 | 80 |
| 129 | #343 | 129 | 43.670 | 44.844 | 1 |
| 129 | #366 as pushed | 66 | 22.727 | 23.169 | 64 |
| 129 | #371 | 0 | 0.448 | 0.985 | 129 |
| 129 | 512/64 | 0 | 0.442 | 0.989 | 129 |
| mixed | #343 | 0 | 0.755 | 0.826 | 23 |
| mixed | #366 as pushed | 0 | 0.762 | 0.856 | 23 |
| mixed | #371 | 0 | 0.765 | 0.858 | 23 |
| mixed | 512/64 | 0 | 0.766 | 0.886 | 23 |

## Return after an absence (`return-1160/`, `return-560/`)

`return:A:B`: draw set A for 10 frames, a disjoint set B until 10 frames before the end, then A
again. Two flushes per frame. 600 frames gives an absence of 1,160 flushes, past #371's limit;
300 frames gives 560.

| Sets | Absence (flushes) | Policy | Rebuilt on return | Return frame (ms) | Frames after (ms) | Pipelines kept |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| 20 + 20 | 1,160 | #343 | 0 | 0.24 | 0.234 | 39 |
| 20 + 20 | 1,160 | #366 as pushed | 0 | 0.24 | 0.234 | 39 |
| 20 + 20 | 1,160 | #371 | 19 | 7.25 | 0.234 | 39 |
| 20 + 20 | 1,160 | 512/64 | 0 | 0.24 | 0.233 | 39 |
| 20 + 20 | 560 | #343 | 0 | 0.23 | 0.224 | 39 |
| 20 + 20 | 560 | #366 as pushed | 0 | 0.24 | 0.233 | 39 |
| 20 + 20 | 560 | #371 | 0 | 0.23 | 0.223 | 39 |
| 20 + 20 | 560 | 512/64 | 0 | 0.23 | 0.226 | 39 |
| 40 + 40 | 1,160 | #343 | 39 | 13.74 | 0.434 | 40 |
| 40 + 40 | 1,160 | #366 as pushed | 15 | 6.00 | 0.252 | 64 |
| 40 + 40 | 1,160 | #371 | 39 | 13.92 | 0.265 | 79 |
| 40 + 40 | 1,160 | 512/64 | 0 | 0.27 | 0.250 | 79 |
| 40 + 40 | 560 | #343 | 39 | 13.89 | 0.437 | 40 |
| 40 + 40 | 560 | #366 as pushed | 15 | 5.95 | 0.259 | 64 |
| 40 + 40 | 560 | #371 | 0 | 0.27 | 0.249 | 79 |
| 40 + 40 | 560 | 512/64 | 0 | 0.26 | 0.249 | 79 |

Nothing was rebuilt during the absence by any policy.

## A stream of one-off states (`scan/`)

`scan:2`: every measured frame draws 2 blend states no earlier frame used, for 300 frames. Three
rounds. Every policy builds the 2 new pipelines each frame; the column that differs is how many it
keeps.

| Policy | Rebuilt per frame | Kept at end | Peak kept | Frame median (ms) |
| --- | ---: | ---: | ---: | ---: |
| #343 | 2 | 27 | 65 | 0.955 |
| #366 as pushed | 2 | 64 | 64 | 0.962 |
| #371 | 2 | 603 | 603 | 0.958 |
| 512/64 | 2 | 512 | 512 | 0.957 |

## Reproduce

```sh
P=pr343,flush-lru64,pr371,flush-lru512-idle64
python3 scripts/femtovg-cache-synthetic.py --build-only --policies $P
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 100 --policies $P --out runs/steady
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 600 --policies $P --scenarios return:20:20,return:40:40 --out runs/return-1160
python3 scripts/femtovg-cache-synthetic.py --runs 10 --frames 300 --policies $P --scenarios return:20:20,return:40:40 --out runs/return-560
python3 scripts/femtovg-cache-synthetic.py --runs 3 --frames 300 --policies $P --scenarios scan:2 --out runs/scan
```
