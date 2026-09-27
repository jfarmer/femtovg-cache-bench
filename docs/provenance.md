# Provenance

The harness and results were extracted from `jfarmer/alustin-editor` at commit `ae899a27f66e02c09700a1f86e7892cfe7467c69`. This repository reorganizes that experiment for standalone use. The Rust source, patches, FemtoVG archive, historical Cargo lockfiles, raw measurements, and JSON results are unchanged at extraction. Python runners were adapted to the new layout and share source preparation. Documentation links were adjusted.

Historical metadata retains its original paths and hashes. It describes the original measurements, not a fresh benchmark run from this repository. `scripts/verify-results.py` checks recorded source hashes where available, the pinned archive and lockfile, and regeneration of all three summaries from raw measurements.

| Original path | Standalone path |
| --- | --- |
| `tools/femtovg-cache-bench/src/` | `src/` |
| `tools/femtovg-cache-bench/policy/src/` | `crates/cache-policy/src/` |
| `tools/femtovg-cache-bench/upstream-base.tar.gz` | `vendor/femtovg-9f2523b.tar.gz` |
| `tools/femtovg-cache-bench/*.patch` | `patches/*.patch` |
| `scripts/perf/femtovg-*.py` | `scripts/femtovg-*.py` |
| `docs/performance/femtovg-pr343/synthetic/` | `results/pr343/` |
| `docs/performance/femtovg-policy-study/` | `results/policy-study/` |

## Version boundaries

All policy variants use the same library snapshot, FemtoVG `9f2523bb794089e9c1be8114057afb283e97a3ea`. The archive intentionally includes only library sources, manifest, build script, README, and upstream licenses. Its checksum and origin are in `vendor/femtovg.json`.

The direct comparison's `pr343` patch reapplies the policy from PR head `6811aeba6bf78cb68d2ed6cfcedf80992d937c0f` to that common base. `flush-lru64` implements flush-stamp ordering from `d3f7ae6bc2f35ebe10d3c1f4b6065255932cf22f`. These benchmark patches are fixed historical variants, not moving references to today's branches.

The broader policy study uses a separate shared cache implementation for both simulation and the real renderer. Its flush-aware policy uses access order to break ties within a flush. It is a refinement of the flush-stamp policy, not byte-for-byte the proposed production patch. Keep the two result sets distinct when describing evidence for a PR.

The archive enables the existing optional `lru` dependency in every variant, and source preparation adds the shared local policy crate to every variant. Dependency features and the lockfile are shared. Instrumentation counts actual pipeline materialization and reports residency; the harness fails on WGPU validation errors.

## Lockfiles

Each result directory includes the exact lockfile used for those recorded runs. The two experiments originally used different lockfiles because the shared policy crate was added later. The root lockfile is Cargo’s pruned standalone-workspace lockfile: its registry package versions and checksums are unchanged from the policy study. New direct-comparison builds also include the shared crate consistently across all four variants. Original metadata keeps its historical lock hashes; new runs record the current root lock hash.
