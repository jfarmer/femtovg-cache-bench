# FemtoVG cache benchmarks

Reproducible pipeline-cache experiments for [FemtoVG PR #343](https://github.com/femtovg/femtovg/pull/343) and a proposed flush-aware cache. Rust generates workloads and runs an offscreen WGPU renderer; Python builds policy variants, runs experiments, and summarizes raw measurements.

The repository includes a checksum-verified source snapshot of FemtoVG at `9f2523bb794089e9c1be8114057afb283e97a3ea`, the policy and instrumentation patches, `Cargo.lock`, and the original recorded results. It needs no Alustin checkout. The recorded experiments use historical policy versions; they do not automatically track the latest PR branch.

## Quick start

Requirements: Python 3.12+, Rust/Cargo, Git, and macOS or Linux. GPU measurements need a working WGPU adapter (Metal on macOS). Python uses only the standard library. Recorded results used Rust 1.96.0; full environment details are in the result metadata.

```sh
# Verify the archived data and reproduce its summaries; no GPU or Rust build needed.
python3 scripts/verify-results.py

# Run Rust tests and compare a fresh CPU sweep with all archived simulation records.
python3 scripts/check.py

# Also validate all direct variants and shared policies on a real GPU.
python3 scripts/check.py --gpu

# Build and run the direct comparison: upstream, #343, flush-aware 64, strict LRU 128.
python3 scripts/femtovg-cache-synthetic.py --build --runs 10 --frames 100 --out runs/comparison

# Build the shared policy model and renderer; run the full CPU sweep and GPU cases.
python3 scripts/femtovg-policy-study.py build
python3 scripts/femtovg-policy-study.py simulate --out runs/policy-study
python3 scripts/femtovg-policy-study.py simulation-summary --out runs/policy-study
python3 scripts/femtovg-policy-study.py gpu --runs 10 --out runs/policy-study
```

Building regenerates `vendor/femtovg/`; make changes in `patches/`, not that directory. The runners serialize their builds because they share that source directory. New measurements go under ignored `runs/`; checked-in `results/` retains the original data. Use new output directories for each experiment. `check.py` saves its validation outputs in a unique `runs/check-*` directory; its short GPU runs are not performance measurements. A shorter direct smoke run uses `--runs 1 --frames 1`.

## Results and methodology

- [Direct comparison](results/pr343/README.md): 240 GPU processes covering working sets of 63, 64, 65, 80, and 129 states plus mixed rendering operations. [Methodology](docs/comparison.md).
- [Policy study](results/policy-study/README.md): 7,200 CPU simulations and 280 GPU processes comparing strict LRU, flush-aware LRU, S3-FIFO, and unlimited retention. [Methodology](docs/policy-study.md).
- [Standalone validation](docs/validation.md) and its reusable check command.
- [Source and result provenance](docs/provenance.md), including the difference between the two flush-aware implementations.

Timings include command construction and GPU completion; they are not GPU timestamp measurements. Counts of pipeline materializations and retained entries are also recorded. Synthetic timings describe these workloads, not an application-wide speedup. GPU/driver differences can change timings; driver caches are not reset. The policy study checks actual per-flush materialization and residency against the CPU model. These are not pixel-reference tests.

## Layout

```text
src/                    Rust GPU harnesses and workload generator
crates/cache-policy/    Shared cache algorithms, simulator interface, and unit tests
scripts/                Source preparation, experiment runners, data verification
vendor/                 Pinned FemtoVG archive and checksum manifest
patches/                Instrumentation and policy changes against that snapshot
results/                Original compressed raw measurements, metadata, summaries
docs/                  Methodology and provenance
```

Harness code is MIT licensed. The bundled FemtoVG sources retain their MIT/Apache-2.0 licenses inside the archive.
