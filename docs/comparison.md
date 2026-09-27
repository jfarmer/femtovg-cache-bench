# FemtoVG pipeline-cache synthetic benchmark

This is an offscreen, real-WGPU benchmark for the boundary and mixed-flush workloads
requested in [FemtoVG PR #343](https://github.com/femtovg/femtovg/pull/343#issuecomment-5785645528).
It complements the [application startup comparison](application-context.md).

From the repository root, using Python 3.12+ and Rust:

```sh
python3 scripts/femtovg-cache-synthetic.py --build --runs 10 --frames 100 --out runs/femtovg-cache-synthetic/my-run
```

The output directory must be new. `--build-only` builds without measuring; omit
`--build` to reuse the binaries whose hashes are recorded under `target/bench-bins/`. Building
replaces the generated `vendor/femtovg/` directory. Do not edit that directory manually.
`--summarize-only --out EXISTING_RUN` regenerates the summary from saved raw data
without building or accessing a GPU.
GPU access is required for measurements; unavailable adapters fail loudly rather than skipping.
macOS runs must select Metal. There is no window or Slint dependency.

## Sources and policies

`vendor/femtovg-9f2523b.tar.gz` contains only the library source, build script, Cargo manifest,
README, and MIT/Apache licenses from FemtoVG commit
`9f2523bb794089e9c1be8114057afb283e97a3ea`. This snapshot has the newer clipping,
layer, and filter APIs requested by the reviewer. No checkout outside this repository
is needed. The four variants share this source, Cargo.lock, features, and release
profile. Source preparation enables the existing optional `lru` dependency and adds the
shared local policy crate for **every** variant.

| Policy | Behavior | Provenance |
| --- | --- | --- |
| `upstream` | Sweep accessed bits after every flush | Unmodified cache policy in the snapshot |
| `pr343` | Sweep accessed bits only when length exceeds 64 | PR head `6811aeba6bf78cb68d2ed6cfcedf80992d937c0f`, reapplied to the common snapshot |
| `flush-lru64` | Evict oldest flush stamps toward 64; protect everything used in the current flush | `d3f7ae6bc2f35ebe10d3c1f4b6065255932cf22f` |
| `strict-lru128` | `lru::LruCache`, evict on insertion beyond 128 | The app's cache policy at measurement time, transplanted to the common snapshot |

`patches/instrumentation.patch` increments a counter at actual pipeline materialization and
records cache length after each flush. Each policy patch applies on top of it.
The PR variant scopes its mutable borrow so the common counter can read the length
after eviction. That is its only extra adjustment. No pipeline-key simplification
or other optimization is included. Each binary embeds and checks its policy label.

## Workloads

Each of 10 rounds launches a fresh process for each of 24 policy/workload pairs.
Policy order follows a rotating, reversed Latin square; workload order also rotates.
Each process records one cold frame, five warmup frames, and 100 measured frames.
All frames are saved. Nothing is discarded as an outlier.

The five pressure workloads use **63, 64, 65, 80, or 129 distinct pipeline states**
across a logical frame. A frame draws N−1 different blend states in a single flush,
then submits a separate, one-pipeline clear flush. The clear pipeline is included
in N. The cold-frame creation count is asserted to equal N on the real device.
This deliberately adversarial access pattern reveals capacity boundaries and the
difference between protecting a whole flush and strict per-access eviction.

The sixth workload alternates glyph-atlas drawing, a clipped opacity layer, a
Gaussian-blur layer, screen drawing, and a clear, each as a separate flush. The
screen includes a gradient, stroke, scissor, and self-intersecting fill. Glyphs use
a synthetic 8×8 atlas without font discovery or text shaping. The render target is
64×64 RGBA8; this benchmark stresses pipelines rather than pixel fill rate.

## Timing and memory

`cpu_ms` includes canvas command construction, encoding, and queue submissions.
`completed_ms` additionally waits for the GPU to finish the logical frame. It is
**not** a GPU timestamp or presentation latency. Diagnostic queries run after the
timed interval. Each run's p50/p95/p99 uses nearest-rank quantiles of its 100 measured
frames; the report aggregates those per-process results, not all frames as if
they were independent launches. One hundred frames provides only a coarse p99.

Memory measurements are complementary:

- `peak_rss_bytes`: process lifetime high-water RSS from `getrusage`, including
  initialization, cold compilation, warmup, and measured frames. macOS bytes and
  Linux KiB are normalized. This is not just pipeline memory.
- `retained`: actual cache entries immediately after each flush.
- `live_pipelines`: WGPU HAL live render-pipeline objects after GPU completion.
  Pending GPU references can outlive cache entries. Enabled WGPU counters and
  nonzero live objects are asserted.
- `metal_resource_bytes`: `MTLDevice.currentAllocatedSize`, sampled before drawing
  and after each completed frame. It counts Metal resource allocations, **not all
  private compiler/driver memory**. These samples are not a continuous GPU memory
  high-water mark. Other backends report null for this field.

The harness enables WGPU validation and fails on uncaptured GPU errors. It does not
perform pixel-reference comparisons. Driver caches are not reset between processes;
"cold" means a new process and empty application pipeline cache, not a cold OS or
driver cache. The stored metadata includes the toolchain, platform, adapter, source
archive and lock hashes, renderer hashes, and executable hashes.

Results apply to these synthetic sequences. In particular, 128 entries gives the
app policy a capacity advantage over 64-entry policies. A faster synthetic result
does not imply a faster app startup when its working set already fits both caches.
