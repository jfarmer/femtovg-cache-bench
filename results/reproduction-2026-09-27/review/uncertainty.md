# Confidence intervals for process-level medians

Each row uses ten separate-process summaries, not individual frames as independent samples. The point estimate is the median of the ten process-level p50 values; the interval targets the population median of that process-level statistic under repeated comparable runs.

We use the narrowest equal-tailed order-statistic interval with coverage at least 95%. For n=10, this is [second-smallest, second-largest], with binomial coverage 1 − 2(1 + 10)/2¹⁰ = 97.8515625%. No normal approximation or bootstrap is used. Intervals for the median of process-level p95/p99 and CPU timing statistics are also in comparison.json.

The guarantee assumes independent, identically distributed process summaries and a continuous distribution. Shared driver caches, thermal drift and background load can violate those assumptions. These are conditional, pointwise intervals for this workload and environment, not simultaneous coverage across all rows or a statement about other machines. Interval overlap is not a test of the difference between policies. p95 latency and a median confidence interval describe different things.

See [NIST's median confidence-limit discussion](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm) for the binomial/order-statistic construction; we retain the conservative discrete bounds rather than interpolate.

## pr343

All values in milliseconds; brackets contain the 97.85% median interval.

| Case | Original median [interval] | Rerun median [interval] |
| --- | ---: | ---: |
| 129/flush-lru64 | 23.896 [23.746, 24.165] | 22.775 [22.631, 23.427] |
| 129/pr343 | 45.638 [45.149, 45.917] | 43.506 [43.261, 43.762] |
| 129/strict-lru128 | 45.741 [45.258, 46.028] | 43.948 [43.334, 44.768] |
| 129/upstream | 45.902 [45.332, 46.163] | 43.834 [43.542, 44.376] |
| 63/flush-lru64 | 0.347 [0.318, 0.412] | 0.363 [0.346, 0.542] |
| 63/pr343 | 0.348 [0.314, 0.557] | 0.361 [0.343, 0.393] |
| 63/strict-lru128 | 0.345 [0.331, 0.386] | 0.366 [0.303, 0.555] |
| 63/upstream | 22.433 [22.093, 22.688] | 21.478 [21.257, 22.594] |
| 64/flush-lru64 | 0.346 [0.324, 0.362] | 0.363 [0.343, 0.533] |
| 64/pr343 | 0.350 [0.319, 0.367] | 0.352 [0.345, 0.528] |
| 64/strict-lru128 | 0.359 [0.352, 0.385] | 0.376 [0.347, 0.617] |
| 64/upstream | 22.906 [22.814, 23.031] | 21.784 [21.561, 22.733] |
| 65/flush-lru64 | 1.063 [1.017, 1.145] | 1.013 [0.961, 1.102] |
| 65/pr343 | 23.015 [22.662, 23.248] | 21.984 [21.851, 24.247] |
| 65/strict-lru128 | 0.356 [0.348, 0.371] | 0.363 [0.346, 0.574] |
| 65/upstream | 23.175 [22.793, 23.339] | 22.102 [21.898, 22.962] |
| 80/flush-lru64 | 6.524 [6.377, 6.703] | 6.193 [6.060, 6.612] |
| 80/pr343 | 28.204 [28.084, 28.748] | 27.076 [26.706, 27.466] |
| 80/strict-lru128 | 0.388 [0.380, 0.393] | 0.380 [0.369, 0.389] |
| 80/upstream | 28.510 [27.926, 28.680] | 27.293 [26.998, 27.786] |
| mixed/flush-lru64 | 0.782 [0.745, 0.888] | 0.784 [0.765, 0.800] |
| mixed/pr343 | 0.801 [0.746, 0.852] | 0.782 [0.767, 0.794] |
| mixed/strict-lru128 | 0.789 [0.755, 0.839] | 0.777 [0.701, 0.810] |
| mixed/upstream | 9.215 [8.932, 9.285] | 8.642 [8.457, 9.021] |

## policy-study

All values in milliseconds; brackets contain the 97.85% median interval.

| Case | Original median [interval] | Rerun median [interval] |
| --- | ---: | ---: |
| batch-single/scale64/cap64/flush-lru | 0.671 [0.650, 0.674] | 0.743 [0.624, 1.647] |
| batch-single/scale64/cap64/lru | 88.619 [83.443, 88.999] | 85.532 [83.642, 101.320] |
| batch-single/scale64/cap64/retain | 0.689 [0.671, 0.697] | 0.678 [0.640, 1.695] |
| batch-single/scale64/cap64/s3fifo | 88.526 [83.700, 88.904] | 85.472 [84.183, 89.371] |
| batch-split/scale64/cap64/flush-lru | 89.535 [84.412, 90.368] | 85.772 [84.511, 92.894] |
| batch-split/scale64/cap64/lru | 89.695 [84.607, 90.647] | 85.787 [84.376, 92.079] |
| batch-split/scale64/cap64/retain | 1.777 [1.657, 1.794] | 1.694 [1.668, 1.803] |
| batch-split/scale64/cap64/s3fifo | 90.036 [84.590, 90.962] | 86.052 [84.508, 97.746] |
| cycle-plus/scale128/cap128/flush-lru | 1.213 [1.197, 1.237] | 1.211 [1.206, 1.235] |
| cycle-plus/scale128/cap128/lru | 43.976 [42.120, 45.586] | 42.812 [42.425, 45.375] |
| cycle-plus/scale128/cap128/retain | 0.482 [0.466, 0.486] | 0.466 [0.462, 0.918] |
| cycle-plus/scale128/cap128/s3fifo | 2.928 [2.827, 3.198] | 2.867 [2.799, 3.066] |
| cycle-plus/scale128/cap256/flush-lru | 0.467 [0.442, 0.483] | 0.466 [0.454, 0.883] |
| cycle-plus/scale128/cap256/lru | 0.465 [0.451, 0.481] | 0.458 [0.435, 0.912] |
| cycle-plus/scale128/cap256/retain | 0.479 [0.462, 0.512] | 0.469 [0.446, 0.921] |
| cycle-plus/scale128/cap256/s3fifo | 0.482 [0.459, 0.500] | 0.468 [0.463, 0.930] |
| hot-scan/scale64/cap64/flush-lru | 0.652 [0.597, 0.675] | 0.596 [0.587, 0.816] |
| hot-scan/scale64/cap64/lru | 0.643 [0.592, 0.696] | 0.591 [0.583, 0.819] |
| hot-scan/scale64/cap64/retain | 0.651 [0.599, 0.686] | 0.597 [0.591, 0.823] |
| hot-scan/scale64/cap64/s3fifo | 0.644 [0.595, 0.695] | 0.596 [0.588, 0.814] |
| shuffle-plus/scale128/cap128/flush-lru | 1.243 [1.093, 1.274] | 1.238 [1.230, 1.311] |
| shuffle-plus/scale128/cap128/lru | 2.971 [2.803, 3.297] | 2.880 [2.818, 3.023] |
| shuffle-plus/scale128/cap128/retain | 0.512 [0.486, 0.530] | 0.497 [0.489, 0.587] |
| shuffle-plus/scale128/cap128/s3fifo | 2.491 [2.359, 2.740] | 2.494 [2.287, 2.826] |
| switch/scale64/cap64/flush-lru | 0.489 [0.483, 0.506] | 0.490 [0.481, 0.499] |
| switch/scale64/cap64/lru | 0.501 [0.490, 0.519] | 0.490 [0.478, 0.501] |
| switch/scale64/cap64/retain | 0.475 [0.380, 0.485] | 0.492 [0.473, 0.500] |
| switch/scale64/cap64/s3fifo | 0.533 [0.509, 0.544] | 0.512 [0.501, 0.523] |

