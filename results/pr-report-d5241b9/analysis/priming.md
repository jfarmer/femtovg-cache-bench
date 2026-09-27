# Warm-up observations

Two complete passes preceded each suite; all launches explicitly unset MTL_SHADER_CACHE_SIZE. These observations describe preparation, not verified Metal cache-hit counters. First-frame time includes process/application-cache initialization and must not be interpreted as a pure compilation measurement.

| Suite / case / policy | Pass 1 first frame | Pass 2 first frame | Measured first-frame median | Measured first-frame range |
| --- | ---: | ---: | ---: | ---: |
| direct/129/flush-lru64 | 69.34 | 68.50 | 70.19 | 67.94–76.86 |
| direct/129/pr343 | 70.30 | 69.74 | 68.33 | 66.34–77.92 |
| direct/129/strict-lru128 | 68.47 | 68.39 | 69.59 | 67.75–84.54 |
| direct/129/upstream | 73.95 | 69.55 | 70.69 | 66.98–94.09 |
| direct/63/flush-lru64 | 48.07 | 38.71 | 38.70 | 37.08–51.70 |
| direct/63/pr343 | 46.52 | 37.82 | 39.00 | 37.39–47.22 |
| direct/63/strict-lru128 | 49.73 | 38.83 | 40.34 | 37.51–53.55 |
| direct/63/upstream | 181.06 | 40.85 | 38.64 | 37.41–57.52 |
| direct/64/flush-lru64 | 41.69 | 39.91 | 39.96 | 38.37–55.67 |
| direct/64/pr343 | 39.32 | 38.98 | 39.80 | 38.09–46.78 |
| direct/64/strict-lru128 | 39.90 | 39.11 | 40.16 | 37.39–46.67 |
| direct/64/upstream | 39.84 | 39.24 | 38.94 | 37.80–46.80 |
| direct/65/flush-lru64 | 38.96 | 39.94 | 40.39 | 37.81–47.49 |
| direct/65/pr343 | 38.89 | 39.51 | 39.24 | 38.22–51.35 |
| direct/65/strict-lru128 | 38.66 | 39.38 | 39.49 | 38.59–46.92 |
| direct/65/upstream | 40.06 | 40.02 | 39.41 | 38.49–67.29 |
| direct/80/flush-lru64 | 50.55 | 45.77 | 46.62 | 45.33–53.95 |
| direct/80/pr343 | 45.57 | 48.50 | 47.07 | 45.25–54.66 |
| direct/80/strict-lru128 | 47.38 | 47.17 | 47.18 | 45.10–53.25 |
| direct/80/upstream | 47.08 | 46.27 | 47.41 | 45.54–51.39 |
| direct/mixed/flush-lru64 | 15.23 | 14.81 | 14.98 | 14.10–18.65 |
| direct/mixed/pr343 | 14.51 | 14.54 | 14.85 | 13.83–35.74 |
| direct/mixed/strict-lru128 | 16.87 | 14.64 | 14.56 | 13.81–34.71 |
| direct/mixed/upstream | 42.97 | 14.69 | 14.40 | 13.83–24.40 |
| policies/batch-single/W64/C64/flush-lru | 67.56 | 68.13 | 66.78 | 65.55–68.65 |
| policies/batch-single/W64/C64/lru | 119.67 | 119.43 | 118.07 | 116.49–121.95 |
| policies/batch-single/W64/C64/retain | 68.38 | 67.97 | 66.92 | 65.66–68.29 |
| policies/batch-single/W64/C64/s3fifo | 121.88 | 120.63 | 118.09 | 116.56–120.08 |
| policies/batch-split/W64/C64/flush-lru | 113.20 | 114.50 | 111.59 | 110.16–113.42 |
| policies/batch-split/W64/C64/lru | 114.39 | 114.34 | 111.83 | 110.26–113.40 |
| policies/batch-split/W64/C64/retain | 60.42 | 61.69 | 60.46 | 59.70–61.65 |
| policies/batch-split/W64/C64/s3fifo | 114.44 | 114.74 | 111.73 | 110.80–113.74 |
| policies/cycle-plus/W128/C128/flush-lru | 66.46 | 67.17 | 66.24 | 65.27–67.10 |
| policies/cycle-plus/W128/C128/lru | 1902.35 | 67.30 | 65.87 | 64.78–66.95 |
| policies/cycle-plus/W128/C128/retain | 67.09 | 67.18 | 66.28 | 64.91–67.36 |
| policies/cycle-plus/W128/C128/s3fifo | 68.38 | 67.36 | 66.50 | 65.41–67.84 |
| policies/cycle-plus/W64/C64/flush-lru | 38.66 | 37.97 | 37.53 | 36.98–38.44 |
| policies/cycle-plus/W64/C64/lru | 1895.24 | 39.33 | 37.72 | 37.30–39.07 |
| policies/cycle-plus/W64/C64/retain | 38.22 | 38.09 | 37.26 | 36.57–38.19 |
| policies/cycle-plus/W64/C64/s3fifo | 38.68 | 38.52 | 37.81 | 36.44–38.57 |
| policies/hot-scan/W64/C64/flush-lru | 16.91 | 17.30 | 16.29 | 16.12–16.68 |
| policies/hot-scan/W64/C64/lru | 16.60 | 16.29 | 16.31 | 15.99–16.80 |
| policies/hot-scan/W64/C64/retain | 17.02 | 16.75 | 16.31 | 16.18–17.39 |
| policies/hot-scan/W64/C64/s3fifo | 16.27 | 16.45 | 16.44 | 16.23–16.69 |
| policies/shuffle-plus/W128/C128/flush-lru | 66.83 | 66.38 | 65.89 | 64.90–67.12 |
| policies/shuffle-plus/W128/C128/lru | 67.52 | 66.23 | 66.23 | 64.89–67.37 |
| policies/shuffle-plus/W128/C128/retain | 66.75 | 67.07 | 66.31 | 65.06–67.93 |
| policies/shuffle-plus/W128/C128/s3fifo | 66.36 | 67.44 | 65.87 | 65.64–67.34 |
| policies/shuffle-plus/W64/C64/flush-lru | 39.01 | 38.40 | 37.60 | 37.23–40.25 |
| policies/shuffle-plus/W64/C64/lru | 38.61 | 37.87 | 37.51 | 36.87–39.28 |
| policies/shuffle-plus/W64/C64/retain | 38.88 | 38.42 | 37.66 | 36.55–39.86 |
| policies/shuffle-plus/W64/C64/s3fifo | 38.59 | 38.19 | 37.63 | 36.76–38.49 |
| policies/switch/W64/C64/flush-lru | 30.81 | 33.19 | 30.04 | 29.45–31.14 |
| policies/switch/W64/C64/lru | 30.36 | 30.48 | 30.02 | 29.62–31.17 |
| policies/switch/W64/C64/retain | 30.13 | 30.37 | 30.06 | 29.42–30.48 |
| policies/switch/W64/C64/s3fifo | 30.62 | 30.51 | 30.08 | 29.49–30.98 |

## Whole-trace phase peaks

Maximum frame time within each phase, including late scan/transition frames. The measured column is the median of ten process maxima. These maxima are diagnostics, not estimates of a population tail percentile.

| Suite / case / policy / phase | Pass 1 max (ms) | Pass 2 max (ms) | Measured process max median (ms) |
| --- | ---: | ---: | ---: |
| direct/129/flush-lru64/cold | 69.34 | 68.50 | 70.19 |
| direct/129/flush-lru64/measured | 31.15 | 30.72 | 31.41 |
| direct/129/flush-lru64/warmup | 28.86 | 28.39 | 29.51 |
| direct/129/pr343/cold | 70.30 | 69.74 | 68.33 |
| direct/129/pr343/measured | 56.36 | 57.34 | 57.43 |
| direct/129/pr343/warmup | 56.76 | 54.63 | 55.30 |
| direct/129/strict-lru128/cold | 68.47 | 68.39 | 69.59 |
| direct/129/strict-lru128/measured | 75.26 | 57.84 | 59.09 |
| direct/129/strict-lru128/warmup | 57.32 | 54.84 | 56.53 |
| direct/129/upstream/cold | 73.95 | 69.55 | 70.69 |
| direct/129/upstream/measured | 58.03 | 59.39 | 58.49 |
| direct/129/upstream/warmup | 59.09 | 55.46 | 56.78 |
| direct/63/flush-lru64/cold | 48.07 | 38.71 | 38.70 |
| direct/63/flush-lru64/measured | 1.39 | 0.75 | 1.42 |
| direct/63/flush-lru64/warmup | 0.98 | 1.10 | 1.00 |
| direct/63/pr343/cold | 46.52 | 37.82 | 39.00 |
| direct/63/pr343/measured | 1.19 | 0.87 | 1.34 |
| direct/63/pr343/warmup | 0.97 | 1.25 | 0.96 |
| direct/63/strict-lru128/cold | 49.73 | 38.83 | 40.34 |
| direct/63/strict-lru128/measured | 1.50 | 0.90 | 1.41 |
| direct/63/strict-lru128/warmup | 0.99 | 0.70 | 0.94 |
| direct/63/upstream/cold | 181.06 | 40.85 | 38.64 |
| direct/63/upstream/measured | 28.32 | 31.79 | 30.93 |
| direct/63/upstream/warmup | 27.78 | 28.41 | 28.45 |
| direct/64/flush-lru64/cold | 41.69 | 39.91 | 39.96 |
| direct/64/flush-lru64/measured | 1.45 | 1.32 | 1.48 |
| direct/64/flush-lru64/warmup | 0.78 | 0.77 | 1.02 |
| direct/64/pr343/cold | 39.32 | 38.98 | 39.80 |
| direct/64/pr343/measured | 1.32 | 1.37 | 1.37 |
| direct/64/pr343/warmup | 0.71 | 1.03 | 0.93 |
| direct/64/strict-lru128/cold | 39.90 | 39.11 | 40.16 |
| direct/64/strict-lru128/measured | 1.61 | 1.29 | 1.27 |
| direct/64/strict-lru128/warmup | 0.76 | 0.78 | 1.09 |
| direct/64/upstream/cold | 39.84 | 39.24 | 38.94 |
| direct/64/upstream/measured | 29.91 | 28.99 | 30.18 |
| direct/64/upstream/warmup | 28.29 | 28.06 | 28.60 |
| direct/65/flush-lru64/cold | 38.96 | 39.94 | 40.39 |
| direct/65/flush-lru64/measured | 2.11 | 1.98 | 2.10 |
| direct/65/flush-lru64/warmup | 1.59 | 1.56 | 1.56 |
| direct/65/pr343/cold | 38.89 | 39.51 | 39.24 |
| direct/65/pr343/measured | 30.58 | 30.58 | 29.64 |
| direct/65/pr343/warmup | 28.79 | 28.62 | 28.16 |
| direct/65/strict-lru128/cold | 38.66 | 39.38 | 39.49 |
| direct/65/strict-lru128/measured | 1.58 | 0.75 | 1.39 |
| direct/65/strict-lru128/warmup | 0.75 | 0.99 | 0.95 |
| direct/65/upstream/cold | 40.06 | 40.02 | 39.41 |
| direct/65/upstream/measured | 30.18 | 30.00 | 30.46 |
| direct/65/upstream/warmup | 33.45 | 28.25 | 28.66 |
| direct/80/flush-lru64/cold | 50.55 | 45.77 | 46.62 |
| direct/80/flush-lru64/measured | 8.85 | 8.07 | 8.65 |
| direct/80/flush-lru64/warmup | 9.77 | 7.80 | 8.11 |
| direct/80/pr343/cold | 45.57 | 48.50 | 47.07 |
| direct/80/pr343/measured | 40.68 | 41.14 | 36.35 |
| direct/80/pr343/warmup | 36.27 | 35.16 | 34.70 |
| direct/80/strict-lru128/cold | 47.38 | 47.17 | 47.18 |
| direct/80/strict-lru128/measured | 1.45 | 1.26 | 1.40 |
| direct/80/strict-lru128/warmup | 1.06 | 1.12 | 1.07 |
| direct/80/upstream/cold | 47.08 | 46.27 | 47.41 |
| direct/80/upstream/measured | 36.53 | 50.25 | 36.79 |
| direct/80/upstream/warmup | 34.70 | 35.08 | 35.25 |
| direct/mixed/flush-lru64/cold | 15.23 | 14.81 | 14.98 |
| direct/mixed/flush-lru64/measured | 5.30 | 1.78 | 1.93 |
| direct/mixed/flush-lru64/warmup | 1.81 | 0.90 | 1.15 |
| direct/mixed/pr343/cold | 14.51 | 14.54 | 14.85 |
| direct/mixed/pr343/measured | 2.28 | 1.66 | 1.80 |
| direct/mixed/pr343/warmup | 1.17 | 1.12 | 1.16 |
| direct/mixed/strict-lru128/cold | 16.87 | 14.64 | 14.56 |
| direct/mixed/strict-lru128/measured | 1.87 | 1.62 | 1.75 |
| direct/mixed/strict-lru128/warmup | 1.90 | 0.90 | 1.08 |
| direct/mixed/upstream/cold | 42.97 | 14.69 | 14.40 |
| direct/mixed/upstream/measured | 13.49 | 11.52 | 11.68 |
| direct/mixed/upstream/warmup | 12.23 | 11.50 | 11.84 |
| policies/batch-single/W64/C64/flush-lru/steady | 67.56 | 68.13 | 66.78 |
| policies/batch-single/W64/C64/lru/steady | 119.67 | 119.43 | 118.07 |
| policies/batch-single/W64/C64/retain/steady | 68.38 | 67.97 | 66.92 |
| policies/batch-single/W64/C64/s3fifo/steady | 121.88 | 120.63 | 118.80 |
| policies/batch-split/W64/C64/flush-lru/steady | 113.20 | 114.50 | 112.79 |
| policies/batch-split/W64/C64/lru/steady | 114.39 | 114.34 | 111.98 |
| policies/batch-split/W64/C64/retain/steady | 60.42 | 61.69 | 60.46 |
| policies/batch-split/W64/C64/s3fifo/steady | 114.44 | 114.74 | 112.12 |
| policies/cycle-plus/W128/C128/flush-lru/steady | 66.46 | 67.17 | 66.24 |
| policies/cycle-plus/W128/C128/lru/steady | 1902.35 | 67.30 | 65.87 |
| policies/cycle-plus/W128/C128/retain/steady | 67.09 | 67.18 | 66.28 |
| policies/cycle-plus/W128/C128/s3fifo/steady | 68.38 | 67.36 | 66.50 |
| policies/cycle-plus/W64/C64/flush-lru/steady | 38.66 | 37.97 | 37.53 |
| policies/cycle-plus/W64/C64/lru/steady | 1895.24 | 39.33 | 37.72 |
| policies/cycle-plus/W64/C64/retain/steady | 38.22 | 38.09 | 37.26 |
| policies/cycle-plus/W64/C64/s3fifo/steady | 38.68 | 38.52 | 37.81 |
| policies/hot-scan/W64/C64/flush-lru/scan | 118.98 | 117.36 | 116.22 |
| policies/hot-scan/W64/C64/flush-lru/steady | 16.91 | 17.30 | 16.29 |
| policies/hot-scan/W64/C64/lru/scan | 7482.02 | 124.36 | 123.36 |
| policies/hot-scan/W64/C64/lru/steady | 16.60 | 16.29 | 16.31 |
| policies/hot-scan/W64/C64/retain/scan | 117.72 | 117.87 | 116.30 |
| policies/hot-scan/W64/C64/retain/steady | 17.02 | 16.75 | 16.31 |
| policies/hot-scan/W64/C64/s3fifo/scan | 118.00 | 118.58 | 116.56 |
| policies/hot-scan/W64/C64/s3fifo/steady | 16.27 | 16.45 | 16.44 |
| policies/shuffle-plus/W128/C128/flush-lru/steady | 66.83 | 66.38 | 65.89 |
| policies/shuffle-plus/W128/C128/lru/steady | 67.52 | 66.23 | 66.23 |
| policies/shuffle-plus/W128/C128/retain/steady | 66.75 | 67.07 | 66.31 |
| policies/shuffle-plus/W128/C128/s3fifo/steady | 66.36 | 67.44 | 65.87 |
| policies/shuffle-plus/W64/C64/flush-lru/steady | 39.01 | 38.40 | 37.60 |
| policies/shuffle-plus/W64/C64/lru/steady | 38.61 | 37.87 | 37.51 |
| policies/shuffle-plus/W64/C64/retain/steady | 38.88 | 38.42 | 37.66 |
| policies/shuffle-plus/W64/C64/s3fifo/steady | 38.59 | 38.19 | 37.63 |
| policies/switch/W64/C64/flush-lru/A | 30.81 | 33.19 | 30.04 |
| policies/switch/W64/C64/flush-lru/B | 0.83 | 1.34 | 0.69 |
| policies/switch/W64/C64/flush-lru/transition | 21.89 | 21.89 | 21.27 |
| policies/switch/W64/C64/lru/A | 30.36 | 30.48 | 30.02 |
| policies/switch/W64/C64/lru/B | 1.34 | 0.78 | 0.83 |
| policies/switch/W64/C64/lru/transition | 21.86 | 21.31 | 21.44 |
| policies/switch/W64/C64/retain/A | 30.13 | 30.37 | 30.06 |
| policies/switch/W64/C64/retain/B | 1.55 | 0.58 | 0.72 |
| policies/switch/W64/C64/retain/transition | 21.76 | 21.51 | 21.21 |
| policies/switch/W64/C64/s3fifo/A | 30.62 | 30.51 | 30.08 |
| policies/switch/W64/C64/s3fifo/B | 19.36 | 19.95 | 19.21 |
| policies/switch/W64/C64/s3fifo/transition | 21.50 | 21.79 | 21.47 |
