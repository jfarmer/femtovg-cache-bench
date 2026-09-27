//! Shared cache policies for trace simulation and the offscreen GPU experiment.
use lru::LruCache;
use serde::Serialize;
use std::{
    collections::{HashMap, VecDeque},
    hash::Hash,
    num::NonZeroUsize,
    sync::OnceLock,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Policy {
    Lru,
    FlushLru,
    S3Fifo,
    Retain,
}

impl Policy {
    pub fn parse(value: &str) -> Self {
        match value {
            "lru" => Self::Lru,
            "flush-lru" => Self::FlushLru,
            "s3fifo" => Self::S3Fifo,
            "retain" => Self::Retain,
            _ => panic!("unknown policy {value}"),
        }
    }
}

static CONFIG: OnceLock<(Policy, usize)> = OnceLock::new();
pub fn configure(policy: Policy, capacity: usize) {
    CONFIG
        .set((policy, capacity))
        .expect("configure once before creating the renderer");
}

#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct Stats {
    pub hits: u64,
    pub misses: u64,
    pub evictions: u64,
    pub peak_resident: usize,
    pub ghost_hits: u64,
    pub peak_ghost: usize,
}

#[derive(Debug)]
struct Entry<V> {
    value: V,
    epoch: u64,
    frequency: u8,
}

#[derive(Debug)]
pub struct Cache<K: Hash + Eq, V> {
    policy: Policy,
    capacity: usize,
    epoch: u64,
    lru: Option<LruCache<K, Entry<V>>>,
    data: HashMap<K, Entry<V>>,
    small: VecDeque<K>,
    main: VecDeque<K>,
    ghost: LruCache<K, ()>,
    small_target: usize,
    stats: Stats,
}

impl<K: Clone + Hash + Eq, V> Default for Cache<K, V> {
    fn default() -> Self {
        let (policy, capacity) = *CONFIG.get().expect("configure cache policy first");
        Self::new(policy, capacity)
    }
}

impl<K: Clone + Hash + Eq, V> Cache<K, V> {
    pub fn new(policy: Policy, capacity: usize) -> Self {
        assert!(capacity >= 2);
        let small_target = (capacity / 10).max(1);
        Self {
            policy,
            capacity,
            epoch: 0,
            lru: matches!(policy, Policy::Lru | Policy::FlushLru).then(LruCache::unbounded),
            data: HashMap::new(),
            small: VecDeque::new(),
            main: VecDeque::new(),
            ghost: LruCache::new(NonZeroUsize::new(capacity - small_target).unwrap()),
            small_target,
            stats: Stats::default(),
        }
    }

    pub fn len(&self) -> usize {
        self.lru.as_ref().map_or(self.data.len(), LruCache::len)
    }
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
    pub fn stats(&self) -> Stats {
        self.stats
    }
    pub fn ghost_len(&self) -> usize {
        self.ghost.len()
    }

    pub fn get_or_insert(&mut self, key: K, create: impl FnOnce() -> V) -> &V {
        if self.lru.is_some() {
            let cache = self.lru.as_mut().unwrap();
            if cache.contains(&key) {
                self.stats.hits += 1;
            } else {
                self.stats.misses += 1;
                if self.policy == Policy::Lru && cache.len() == self.capacity {
                    cache.pop_lru();
                    self.stats.evictions += 1;
                }
                cache.put(
                    key.clone(),
                    Entry {
                        value: create(),
                        epoch: self.epoch,
                        frequency: 0,
                    },
                );
                self.stats.peak_resident = self.stats.peak_resident.max(cache.len());
            }
            let entry = cache.get_mut(&key).unwrap();
            entry.epoch = self.epoch;
            return &entry.value;
        }
        if self.data.contains_key(&key) {
            self.stats.hits += 1;
            let entry = self.data.get_mut(&key).unwrap();
            entry.frequency = (entry.frequency + 1).min(3);
        } else {
            self.stats.misses += 1;
            if self.policy == Policy::S3Fifo {
                let ghost_hit = self.ghost.pop(&key).is_some();
                self.stats.ghost_hits += u64::from(ghost_hit);
                while self.data.len() >= self.capacity {
                    self.evict_s3();
                }
                if ghost_hit {
                    self.main.push_back(key.clone());
                } else {
                    self.small.push_back(key.clone());
                }
            }
            self.data.insert(
                key.clone(),
                Entry {
                    value: create(),
                    epoch: self.epoch,
                    frequency: 0,
                },
            );
            self.stats.peak_resident = self.stats.peak_resident.max(self.data.len());
        }
        &self.data[&key].value
    }

    pub fn finish_flush(&mut self) {
        if self.policy == Policy::FlushLru {
            let cache = self.lru.as_mut().unwrap();
            while cache.len() > self.capacity {
                if cache.peek_lru().unwrap().1.epoch == self.epoch {
                    break;
                }
                cache.pop_lru();
                self.stats.evictions += 1;
            }
        }
        self.epoch += 1;
    }

    // Original S3-FIFO: 10% small target, 90% main/ghost; eviction only at full capacity.
    // Two hits promote a small-queue entry; main entries consume capped reuse credits.
    fn evict_s3(&mut self) {
        if self.main.len() > self.capacity - self.small_target || self.small.is_empty() {
            loop {
                let key = self.main.pop_front().expect("nonempty main queue");
                let entry = self.data.get_mut(&key).unwrap();
                if entry.frequency > 0 {
                    entry.frequency -= 1;
                    self.main.push_back(key);
                } else {
                    self.data.remove(&key);
                    self.stats.evictions += 1;
                    return;
                }
            }
        }
        while let Some(key) = self.small.pop_front() {
            let entry = self.data.get_mut(&key).unwrap();
            if entry.frequency >= 2 {
                entry.frequency = 0;
                self.main.push_back(key);
            } else {
                self.data.remove(&key);
                self.ghost.put(key, ());
                self.stats.peak_ghost = self.stats.peak_ghost.max(self.ghost.len());
                self.stats.evictions += 1;
                return;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flush_protection_avoids_the_cyclic_lru_cascade() {
        for (policy, expected) in [
            (Policy::Lru, 65),
            (Policy::FlushLru, 2),
            (Policy::Retain, 0),
        ] {
            let mut cache = Cache::new(policy, 64);
            for frame in 0..4 {
                let before = cache.stats().misses;
                for key in 1..65 {
                    cache.get_or_insert(key, || ());
                }
                cache.finish_flush();
                cache.get_or_insert(0, || ());
                cache.finish_flush();
                if frame > 0 {
                    assert_eq!(cache.stats().misses - before, expected);
                }
            }
        }
    }

    #[test]
    fn s3_ghosts_have_no_values_and_hot_entries_survive_a_scan() {
        let mut cache = Cache::new(Policy::S3Fifo, 20);
        for _ in 0..4 {
            for key in 0..4 {
                cache.get_or_insert(key, || ());
            }
        }
        for key in 4..44 {
            cache.get_or_insert(key, || ());
        }
        let misses = cache.stats().misses;
        for key in 0..4 {
            cache.get_or_insert(key, || panic!("hot entry was evicted"));
        }
        assert_eq!(misses, cache.stats().misses);
        assert!(cache.len() <= 20 && cache.ghost_len() <= 18);
        let ghost_key = *cache.ghost.peek_lru().unwrap().0;
        cache.get_or_insert(ghost_key, || ());
        assert_eq!(cache.stats().ghost_hits, 1);
        assert!(cache.main.contains(&ghost_key));
    }
}
