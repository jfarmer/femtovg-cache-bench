# Primary measurement protocol

The primary report measures the proposed renderer at `d5241b90032d8bfaca305d993cef30a0277f8898` and upstream base `fa5d6a36818e79be1e8ea2a32eca3564e893180f`. Source archives, patches, and SHA-256 checks are bundled. The candidate renderer must match the git revision before the common counting instrumentation is added. Compiler features and registry dependency versions are shared across variants.

Run from the repository root:

```sh
python3 scripts/run-report.py --out runs/pr-report
```

All GPU launches explicitly remove `MTL_SHADER_CACHE_SIZE` from the child environment for the main measurements. Before each suite, run two full priming passes over every case and policy. These use the complete 100-frame traces, including every late scan state; the shuffled seeds change order, not the state set. Priming data is saved separately and excluded from reported performance statistics. Each measured launch starts a new process and empty application cache. This controls the preparation procedure; it does not prove that every internal Metal cache lookup hits. Inspect both priming passes and measured first-frame times for evidence of incomplete preparation or drift.

The direct comparison uses 10 processes per policy/workload, with one initial frame, five warmup frames, and 100 measured frames. Four policies × six workloads × ten rounds = 240 measured GPU processes. It compares upstream's sweep, the #343 conditional sweep, the exact proposed flush-stamp implementation at 64, and strict LRU 128. The larger LRU has a capacity advantage, which the report must make explicit.

The broader study uses 10 processes per policy/case, recording 100 frames and summarizing frames 10–99. Four policies × eight cases × ten rounds = 320 measured GPU processes. Cases are cycle/shuffle at W=64/C=64 and W=128/C=128, plus hot-scan, switching, single-batch, and split-batch workloads at W=64/C=64. The shared flush-aware model uses per-access ordering within a flush and is a refinement rather than the exact PR implementation. Its GPU counts must match the simulator at every flush.

All rounds rotate workload and policy order. Retain every frame, including transitions and outliers. CPU simulation and summary computation happen outside GPU measurement batches. The complete deterministic sweep still covers 7,200 policy/trace/capacity/seed combinations; seeds only affect the shuffled workload.

After both GPU suites, perform a matched-work Metal diagnostic on the actual upstream/proposed binaries: three alternating rounds with the environment variable unset versus `0`, using 17 initial pipeline creations in each case. This is a cold-start control check, not a second full policy-ranking experiment or a verified global cache reset. Save all frames; confirm identical policy work across settings. The override's effect must be evaluated on the measured binaries.

Report completed-frame p50/p95/p99 as medians of process-level statistics. Calculate conservative order-statistic confidence intervals across processes, not independent-frame intervals. With ten processes the selected interval has 97.85% coverage under independent, identically distributed process-summary assumptions. Discuss shared driver state and environmental drift as limitations. Do not use three diagnostic runs to claim a 95% median confidence interval.

Report creation counts and residency alongside timing. RSS/physical footprint are process-level measures; Metal resource allocation counters omit private driver/compiler memory. The harness validates WGPU execution and pipeline counts, not rendered-image equivalence. Historical reproduction results remain supporting validation, not the main comparison.
