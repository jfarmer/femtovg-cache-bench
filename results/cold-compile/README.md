# What a pipeline build costs: new source, new blend state, or a rebuild

Measured 2026-10-06 on an Apple M4 Max, macOS 26.6.2, wgpu 30.0.1, Metal. Every number in the
eviction comparisons is the warm case below. Nothing here was measured on Vulkan or in a browser.

## Standalone bench (`pipebench/`)

`pipebench` builds render pipelines with FemtoVG's shader (`shader.wgsl` and `filters.wgsl` from
femtovg master 485c665) and its pipeline layout. A pipeline-overridable constant `SALT`, set to a
value derived from the clock, makes the generated MSL new to Metal's in-process and on-disk
caches; pipelines that share a salt share a source.

Two runs of `cargo run --release -p pipebench`, which agreed to within noise:

| Case | Per pipeline (ms) |
| --- | ---: |
| First pipeline from a source Metal has not seen | 173 and 221 |
| 40 more blend states on that source | 33.5 median, 32.3 to 39.7 |
| The same 40 built again after being dropped | 0.48 median |
| 40 blend states on a second new source, `vs_main_texture` entry | 33.3 median, one at 144 |
| 41 blend states on a 7-line shader | 2.3 median |

Four threads built 40 new pipelines in 418 ms against 1,453 ms on one thread. Frames on the
render thread stayed at 0.18 ms median while another thread built 80 pipelines.

`cargo run --release -p pipebench --bin variants`, one pipeline per row on a new source:

| Variant against the base pipeline | ms |
| --- | ---: |
| Base: SourceOver-like blend, new source | 181.1 |
| The same descriptor again | 0.80 |
| Stencil ops `IncrementClamp` | 0.63 |
| Stencil compare `Equal` | 0.56 |
| Stencil write mask `0x7f` | 0.53 |
| Topology `TriangleStrip` | 0.52 |
| Cull `None` | 0.51 |
| No blend, no color writes (stencil-only pass) | 11.2 |
| Same, stencil `IncrementWrap` | 0.67 |
| A different blend state | 32.7 |
| Another blend state | 33.4 |
| No blend, all color writes | 33.0 |

So the expensive axis is blend state together with color writes. Stencil state, topology and cull
mode cost a warm build even on a new source, because wgpu-hal's Metal backend keeps stencil in a
separate `MTLDepthStencilState` and applies cull mode at draw time.

## The same thing in FemtoVG's renderer

The direct-comparison harness, built once with one literal in the vendored `shader.wgsl` changed
(`TURBULENCE_MAX_OCTAVES`, 10.0 to 10.0001), so its generated MSL was new to Metal. Policy
`flush-lru512-idle64`, 5 frames. The cold frame is the first frame of the process; the harness
reports per-flush CPU time and the pipelines each flush built.

| Workload | Run | Flush | Pipelines built | Flush CPU (ms) | Per pipeline (ms) |
| --- | --- | --- | ---: | ---: | ---: |
| 129 | 1, source new to Metal | states | 128 | 2,647.3 | 20.7 |
| 129 | 1 | clear | 1 | 21.7 | 21.7 |
| 129 | 2, same binary | states | 128 | 45.2 | 0.35 |
| 129 | 2 | clear | 1 | 0.6 | 0.6 |
| mixed | 1, source new to Metal | clipped-layer | 8 | 45.6 | 5.7 |
| mixed | 1 | glyph, filter, screen | 1, 3, 11 | 1.6, 1.9, 3.9 | 0.4 |
| mixed | 2, same binary | clipped-layer | 8 | 4.0 | 0.5 |
| mixed | 2 | glyph, filter, screen | 1, 3, 11 | 1.5, 2.1, 4.2 | 0.4 |

The 128 blend states cost about 20 ms each the first time this source met Metal, the one-time
source compile included, and 0.35 ms on the next launch, when Metal's on-disk cache held them.
The mixed workload's glyph, filter and screen flushes were as cheap cold as warm: their pipelines
differ from each other in stencil state, topology and target, not in blend state, so only the
clipped-layer flush, which introduces new blend-and-target combinations, paid.

## What it means for eviction

A pipeline the renderer has built before in this process, or that this machine has built with
this shader before, costs about 0.35 to 0.5 ms to build again. That is the only cost an eviction
policy controls. A blend-and-format combination the machine has never built with this shader
costs tens of milliseconds, once, on the frame that first needs it, under every policy; a changed
shader, femtovg, naga or macOS version makes every combination new again.
