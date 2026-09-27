# Standalone validation

Validated on macOS with Metal on 2026-09-27 using:

```sh
python3 scripts/check.py --gpu
```

The command passed:

- Three Rust tests covering flush protection, S3-FIFO scan behavior, and equivalent request sequences across different flush boundaries.
- Provenance checks and exact regeneration of all three summaries from the archived 520 GPU runs and 7,200 simulations.
- A fresh release-mode CPU sweep whose 7,200 records exactly matched the archived simulations.
- Twenty-four direct GPU smoke runs: four historical cache policies across all six workloads, with one measured frame after cold/warmup frames.
- Eight shared-policy GPU smoke runs: four policies across `cycle-plus` and `batch-split`, each with scale/capacity 16 and 60 frames. Every flush matched the simulator's materialization and residency counts.

The pinned FemtoVG source emits five compiler warnings during these builds. This validates the standalone packaging and exercised behavior; it is not a rerun of the full timing experiment or a pixel-reference test. Short-run timings are not used to update the historical performance tables.

The script saves fresh outputs under a unique ignored `runs/check-*` directory. The full experiment commands and their larger sample sizes are documented in the root README.
