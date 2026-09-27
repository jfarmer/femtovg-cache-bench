//! Deterministic traces shared by the CPU model and real renderer.
use pipeline_cache_policy::{Cache, Policy};
use serde::Serialize;

pub const POLICIES: [&str; 4] = ["lru", "flush-lru", "s3fifo", "retain"];
pub const SCENARIOS: [&str; 12] = [
    "stable",
    "cycle-minus",
    "cycle-at",
    "cycle-plus",
    "cycle-double",
    "shuffle-plus",
    "hot-scan",
    "switch",
    "overlap",
    "burst",
    "batch-single",
    "batch-split",
];

#[derive(Clone, Debug, Serialize)]
pub struct TraceFrame {
    pub phase: &'static str,
    pub flushes: Vec<Vec<u32>>,
}

fn shuffle(values: &mut [u32], random: &mut u64) {
    for i in (1..values.len()).rev() {
        *random ^= *random << 13;
        *random ^= *random >> 7;
        *random ^= *random << 17;
        values.swap(i, *random as usize % (i + 1));
    }
}

pub fn trace(scenario: &str, scale: usize, frames: usize, seed: u64) -> Vec<TraceFrame> {
    assert!(scale >= 16 && frames >= 60 && seed > 0);
    let mut random = seed;
    let ids = |start: usize, count: usize| -> Vec<u32> {
        (start..start + count).map(|n| n as u32).collect()
    };
    (0..frames)
        .map(|frame| {
            let mut phase = "steady";
            let mut drawing = match scenario {
                "stable" => ids(1, scale / 2 - 1),
                "cycle-minus" => ids(1, scale - 2),
                "cycle-at" => ids(1, scale - 1),
                "cycle-plus" | "shuffle-plus" => ids(1, scale),
                "cycle-double" => ids(1, scale * 2 - 1),
                "hot-scan" => {
                    let hot = ids(1, scale / 4);
                    let mut values = hot.repeat(4);
                    if frame >= 10 && frame % 10 == 0 {
                        phase = "scan";
                        values.extend(ids(1 + scale + (frame / 10 - 1) * scale * 4, scale * 4));
                        values.extend(hot);
                    }
                    values
                }
                "switch" | "overlap" => {
                    let other = (frame / 20) % 2 == 1;
                    phase = if frame % 20 == 0 && frame > 0 {
                        "transition"
                    } else if other {
                        "B"
                    } else {
                        "A"
                    };
                    let offset = if scenario == "overlap" {
                        scale / 4
                    } else {
                        scale
                    };
                    ids(1 + if other { offset } else { 0 }, scale * 3 / 4 - 1)
                }
                "burst" => {
                    if frame % 25 == 10 {
                        phase = "burst";
                        ids(1, scale * 4 - 1)
                    } else {
                        phase = "normal";
                        ids(1, scale / 2 - 1)
                    }
                }
                "batch-single" | "batch-split" => ids(1, scale * 2 - 1).repeat(2),
                _ => panic!("unknown scenario {scenario}"),
            };
            if scenario == "shuffle-plus" {
                shuffle(&mut drawing, &mut random);
            }
            let flushes = if scenario == "batch-single" {
                drawing.push(0);
                vec![drawing]
            } else if scenario == "batch-split" {
                drawing.push(0);
                drawing.chunks(8).map(<[u32]>::to_vec).collect()
            } else {
                vec![drawing, vec![0]]
            };
            TraceFrame { phase, flushes }
        })
        .collect()
}

#[derive(Debug, Clone, Serialize)]
pub struct ModelFlush {
    pub misses: u64,
    pub retained: usize,
}
#[derive(Debug, Clone, Serialize)]
pub struct ModelFrame {
    pub phase: &'static str,
    pub misses: u64,
    pub requests: usize,
    pub retained: usize,
    pub ghost: usize,
    pub flushes: Vec<ModelFlush>,
}

pub fn simulate(
    policy: Policy,
    capacity: usize,
    trace: &[TraceFrame],
) -> (Vec<ModelFrame>, pipeline_cache_policy::Stats) {
    let mut cache = Cache::new(policy, capacity);
    let frames = trace
        .iter()
        .map(|frame| {
            let mut flushes = Vec::new();
            let mut requests = 0;
            for flush in &frame.flushes {
                let before = cache.stats().misses;
                // FemtoVG skips a cache lookup when the currently bound pipeline is unchanged.
                let mut previous = None;
                for &key in flush {
                    if previous != Some(key) {
                        cache.get_or_insert(key, || ());
                        requests += 1;
                    }
                    previous = Some(key);
                }
                cache.finish_flush();
                flushes.push(ModelFlush {
                    misses: cache.stats().misses - before,
                    retained: cache.len(),
                });
            }
            ModelFrame {
                phase: frame.phase,
                misses: flushes.iter().map(|f| f.misses).sum(),
                requests,
                retained: cache.len(),
                ghost: cache.ghost_len(),
                flushes,
            }
        })
        .collect();
    (frames, cache.stats())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn batching_changes_boundaries_without_changing_requests() {
        let a = trace("batch-single", 64, 100, 1);
        let b = trace("batch-split", 64, 100, 1);
        for (a, b) in a.iter().zip(&b) {
            assert_eq!(
                a.flushes.iter().flatten().collect::<Vec<_>>(),
                b.flushes.iter().flatten().collect::<Vec<_>>()
            );
        }
    }
}
