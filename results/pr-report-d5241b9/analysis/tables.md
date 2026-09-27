# Complete primary results

All timings are milliseconds. Median intervals use ten process-level summaries. p95/p99 are medians of within-process quantiles; RSS is process lifetime peak RSS. Resident entries are end-of-last-flush counts for direct runs and peak model residency for the study. Intervals are conservative pointwise 97.85% order-statistic intervals under independent, comparable-run assumptions.

## direct

| Case / policy | Creations/frame | Median [interval] | p95 | p99 | Resident entries | Peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 129/flush-lru64 | 66.00 | 28.243 [27.462, 40.190] | 29.456 | 30.639 | 64 | 31.79 |
| 129/pr343 | 129.00 | 53.805 [52.713, 56.300] | 55.954 | 56.850 | 1 | 31.77 |
| 129/strict-lru128 | 129.00 | 54.181 [53.110, 66.935] | 55.257 | 57.152 | 128 | 31.71 |
| 129/upstream | 129.00 | 54.411 [53.239, 57.390] | 55.741 | 57.862 | 1 | 31.80 |
| 63/flush-lru64 | 0.00 | 0.383 [0.350, 1.010] | 0.734 | 1.178 | 63 | 27.45 |
| 63/pr343 | 0.00 | 0.367 [0.318, 0.668] | 0.641 | 0.942 | 63 | 27.34 |
| 63/strict-lru128 | 0.00 | 0.425 [0.350, 0.871] | 0.670 | 0.948 | 63 | 27.34 |
| 63/upstream | 63.00 | 26.563 [25.913, 30.124] | 28.500 | 28.661 | 1 | 28.43 |
| 64/flush-lru64 | 0.00 | 0.473 [0.351, 0.942] | 0.742 | 1.020 | 64 | 27.57 |
| 64/pr343 | 0.00 | 0.377 [0.355, 0.850] | 0.719 | 0.960 | 64 | 27.34 |
| 64/strict-lru128 | 0.00 | 0.441 [0.354, 0.601] | 0.685 | 0.884 | 64 | 27.45 |
| 64/upstream | 64.00 | 26.996 [26.408, 29.278] | 27.778 | 28.872 | 1 | 28.41 |
| 65/flush-lru64 | 2.00 | 1.187 [1.129, 1.274] | 1.523 | 1.810 | 64 | 28.07 |
| 65/pr343 | 65.00 | 27.184 [26.530, 28.782] | 28.136 | 28.536 | 1 | 28.45 |
| 65/strict-lru128 | 0.00 | 0.394 [0.355, 0.603] | 0.774 | 0.940 | 65 | 27.36 |
| 65/upstream | 65.00 | 27.347 [26.734, 28.943] | 28.070 | 29.324 | 1 | 28.53 |
| 80/flush-lru64 | 17.00 | 7.475 [7.228, 8.654] | 8.082 | 8.447 | 64 | 29.22 |
| 80/pr343 | 80.00 | 33.338 [32.773, 34.580] | 34.084 | 34.718 | 1 | 29.22 |
| 80/strict-lru128 | 0.00 | 0.439 [0.380, 0.701] | 0.832 | 0.988 | 80 | 28.21 |
| 80/upstream | 80.00 | 33.596 [33.156, 35.266] | 34.385 | 35.359 | 1 | 29.32 |
| mixed/flush-lru64 | 0.00 | 0.782 [0.723, 0.912] | 1.074 | 1.762 | 23 | 32.05 |
| mixed/pr343 | 0.00 | 0.783 [0.716, 1.661] | 1.021 | 1.610 | 23 | 31.95 |
| mixed/strict-lru128 | 0.00 | 0.780 [0.722, 1.021] | 1.066 | 1.583 | 23 | 31.83 |
| mixed/upstream | 23.00 | 10.502 [10.242, 12.559] | 11.077 | 11.571 | 1 | 31.52 |

## policies

| Case / policy | Creations/frame | Median [interval] | p95 | p99 | Resident entries | Peak RSS (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| batch-single/scale64/cap64/flush-lru | 0.00 | 0.660 [0.655, 0.663] | 0.973 | 1.696 | 128 | 31.28 |
| batch-single/scale64/cap64/lru | 255.00 | 102.358 [101.271, 103.145] | 103.916 | 105.156 | 64 | 32.97 |
| batch-single/scale64/cap64/retain | 0.00 | 0.674 [0.672, 0.678] | 1.618 | 1.727 | 128 | 31.23 |
| batch-single/scale64/cap64/s3fifo | 255.00 | 102.584 [101.413, 103.411] | 103.915 | 105.900 | 64 | 33.05 |
| batch-split/scale64/cap64/flush-lru | 255.00 | 103.218 [102.554, 103.934] | 104.552 | 107.211 | 72 | 35.96 |
| batch-split/scale64/cap64/lru | 255.00 | 103.204 [102.081, 104.103] | 104.559 | 106.586 | 64 | 35.98 |
| batch-split/scale64/cap64/retain | 0.00 | 1.707 [1.681, 1.728] | 1.936 | 2.138 | 128 | 44.81 |
| batch-split/scale64/cap64/s3fifo | 255.00 | 103.373 [102.588, 104.380] | 104.605 | 108.615 | 64 | 36.06 |
| cycle-plus/scale128/cap128/flush-lru | 2.00 | 1.323 [1.189, 1.328] | 1.533 | 1.876 | 129 | 32.06 |
| cycle-plus/scale128/cap128/lru | 129.00 | 51.670 [51.202, 52.251] | 52.457 | 53.056 | 128 | 32.70 |
| cycle-plus/scale128/cap128/retain | 0.00 | 0.478 [0.474, 0.493] | 1.059 | 1.268 | 129 | 31.77 |
| cycle-plus/scale128/cap128/s3fifo | 6.39 | 3.288 [3.178, 3.502] | 6.403 | 7.099 | 128 | 32.26 |
| cycle-plus/scale64/cap64/flush-lru | 2.00 | 1.141 [1.069, 1.151] | 1.309 | 1.616 | 65 | 28.91 |
| cycle-plus/scale64/cap64/lru | 65.00 | 25.949 [25.603, 26.426] | 26.449 | 27.171 | 64 | 29.39 |
| cycle-plus/scale64/cap64/retain | 0.00 | 0.366 [0.363, 0.599] | 0.660 | 0.772 | 65 | 28.48 |
| cycle-plus/scale64/cap64/s3fifo | 4.28 | 2.423 [2.389, 2.468] | 3.877 | 4.286 | 64 | 29.00 |
| hot-scan/scale64/cap64/flush-lru | 25.70 | 0.637 [0.621, 0.869] | 114.329 | 116.216 | 320 | 119.57 |
| hot-scan/scale64/cap64/lru | 27.30 | 0.626 [0.619, 0.632] | 121.234 | 123.359 | 64 | 118.83 |
| hot-scan/scale64/cap64/retain | 25.60 | 0.639 [0.629, 0.727] | 114.617 | 116.299 | 2321 | 131.76 |
| hot-scan/scale64/cap64/s3fifo | 25.60 | 0.643 [0.629, 0.864] | 114.849 | 116.556 | 64 | 119.23 |
| shuffle-plus/scale128/cap128/flush-lru | 2.00 | 1.328 [1.320, 1.330] | 1.484 | 2.028 | 129 | 32.05 |
| shuffle-plus/scale128/cap128/lru | 6.49 | 3.204 [3.132, 3.406] | 4.568 | 5.230 | 128 | 32.25 |
| shuffle-plus/scale128/cap128/retain | 0.00 | 0.481 [0.478, 0.491] | 1.048 | 1.099 | 129 | 31.76 |
| shuffle-plus/scale128/cap128/s3fifo | 4.72 | 2.850 [2.779, 3.120] | 4.260 | 4.889 | 128 | 32.20 |
| shuffle-plus/scale64/cap64/flush-lru | 2.00 | 1.149 [1.144, 1.158] | 1.313 | 1.886 | 65 | 28.90 |
| shuffle-plus/scale64/cap64/lru | 5.61 | 2.685 [2.409, 2.701] | 3.811 | 4.479 | 64 | 29.09 |
| shuffle-plus/scale64/cap64/retain | 0.00 | 0.383 [0.363, 0.386] | 0.656 | 0.934 | 65 | 28.48 |
| shuffle-plus/scale64/cap64/s3fifo | 3.36 | 1.779 [1.732, 1.991] | 3.128 | 3.719 | 64 | 29.03 |
| switch/scale64/cap64/flush-lru | 1.56 | 0.526 [0.522, 0.529] | 0.928 | 21.272 | 95 | 29.95 |
| switch/scale64/cap64/lru | 2.09 | 0.530 [0.525, 0.533] | 1.348 | 21.436 | 64 | 29.88 |
| switch/scale64/cap64/retain | 0.52 | 0.523 [0.358, 0.526] | 0.580 | 21.214 | 95 | 29.88 |
| switch/scale64/cap64/s3fifo | 5.21 | 0.543 [0.539, 0.553] | 15.685 | 21.468 | 64 | 30.20 |

## Per-round effect estimates

| Working set | Proposed / #343 median-latency ratio [interval] |
| --- | ---: |
| 63 | 1.018 [0.947, 1.249] |
| 64 | 0.994 [0.952, 1.109] |
| 65 | 0.043 [0.042, 0.046] |
| 80 | 0.224 [0.221, 0.241] |
| 129 | 0.524 [0.521, 0.724] |
| mixed | 0.995 [0.871, 1.075] |

These are medians of per-round proposed/#343 p50 ratios, not ratios of aggregate medians. A ratio below one favors the proposed policy. Round pairing controls some temporal variation but does not remove shared-driver or session effects.

