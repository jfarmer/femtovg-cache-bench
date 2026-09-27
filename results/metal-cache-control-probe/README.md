# Metal cache-control probe

This small diagnostic tests whether the undocumented `MTL_SHADER_CACHE_SIZE=0` setting has an observable effect on this machine. It is not a policy-ranking benchmark and does not establish a supported Metal cache-reset API.

The benchmark uses the pinned historical FemtoVG snapshot, Apple M4 Max/Metal, and the same built executables under both settings. It visits 17 pipeline states and compares the original per-flush eviction policy with strict LRU 128. Each policy first runs a complete priming launch under normal caching. Three rounds then alternate the order of fresh-process launches with the variable explicitly unset (`system`) or set to `0` (`size-zero`). Each measured launch saves one first frame, five warmup frames, and two measured frames. All raw frames and priming launches are retained.

## Observations

The following are medians of three process-level values. Three runs are diagnostic evidence, not a basis for a precise performance claim or a 95% distribution-free median interval.

| Policy / setting | First-frame completed time (ms) | Subsequent measured-frame median (ms) |
| --- | ---: | ---: |
| upstream/system | 14.35 | 5.755 |
| upstream/size-zero | 487.15 | 5.762 |
| strict-lru128/system | 14.77 | 0.622 |
| strict-lru128/size-zero | 486.61 | 0.384 |

Both policies create the same 17 pipelines on their first frame. The upstream policy subsequently recreates 17 per frame; strict LRU retains them and creates zero. All creation and retention sequences match across the two environment settings for each policy.

The override raises first-frame time from roughly 14–15 ms to roughly 487 ms for both policies. However, repeated upstream pipeline creation settles near 5.8 ms per frame under both settings. On this machine and trace, the override affects first-use cost while substantial within-process reuse remains. It therefore cannot be described as making every pipeline creation permanently cold.

The similar first-use times for equal creation work are consistent with the cache policy being independent of Metal's compilation-cache state. Policy-dependent totals can still differ when eviction changes the number of creations. The small steady-state LRU timing differences should not be interpreted from only three short samples.

## What this establishes—and what it does not

This demonstrates an empirical control effect for this executable, workload, OS and driver. It does not prove which internal cache layers are bypassed, a persistent cache deletion, or a guarantee that every shader compilation is cold. A later cold-start diagnostic should verify the effect on its exact measured binaries and compare equal creation work.

For the primary policy report, use an explicit normal-cache environment and prime the complete workload before the measured launches, including late scan states. Record priming and first-use timings so the warm-up protocol is observable. Such a protocol controls preparation; it should not be advertised as proof of every internal Metal cache hit.

## Reproduce

```sh
python3 scripts/probe-metal-cache.py --build --out runs/my-metal-probe
```

The probe alters only its child processes' environment and performs no system-cache deletion. See [raw launches](runs.jsonl), [summary](summary.json), and [binary/source provenance](metadata.json).
