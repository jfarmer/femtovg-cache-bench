"""Build and measure four pinned FemtoVG cache policies on a real, offscreen GPU."""
import argparse
import gzip
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess

from common import ROOT, BENCH, ARCHIVE, BINS, SOURCE, prepare_source, build_lock, input_hashes, verify_build
POLICIES = ("upstream", "pr343", "flush-lru64", "strict-lru128")
SCENARIOS = ("63", "64", "65", "80", "129", "mixed")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    with build_lock():
        BINS.mkdir(parents=True, exist_ok=True)
        provenance = {}
        for policy in POLICIES:
            prepare_source(policy)
            env = dict(os.environ, CACHE_BENCH_POLICY=policy)
            with (BINS / f"{policy}.build.log").open("w") as log:
                subprocess.run([
                    "cargo", "build", "--release", "--locked", "--manifest-path",
                    str(BENCH / "Cargo.toml"), "--bin", "femtovg-cache-bench",
                ], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            shutil.copy2(BENCH / "target/release/femtovg-cache-bench", BINS / policy)
            provenance[policy] = {
                "binary_sha256": sha256(BINS / policy),
                "renderer_sha256": sha256(SOURCE / "src/renderer/wgpu.rs"),
                "inputs": input_hashes(),
            }
            print(f"built {policy}", flush=True)
        (BINS / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def percentile(values, q):
    """Nearest-rank quantile; report within-run tails before aggregating runs."""
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def summarize(records):
    summary = {}
    for scenario, policy in itertools.product(SCENARIOS, POLICIES):
        runs = [r for r in records if r["scenario"] == scenario and r["policy"] == policy]
        if not runs:
            continue
        per_run = []
        for run in runs:
            frames = [f for f in run["frames"] if f["phase"] == "measured"]
            last = frames[-1]
            per_run.append({
                "cpu_p50_ms": percentile([f["cpu_ms"] for f in frames], .50),
                "cpu_p95_ms": percentile([f["cpu_ms"] for f in frames], .95),
                "cpu_p99_ms": percentile([f["cpu_ms"] for f in frames], .99),
                "completed_p50_ms": percentile([f["completed_ms"] for f in frames], .50),
                "completed_p95_ms": percentile([f["completed_ms"] for f in frames], .95),
                "completed_p99_ms": percentile([f["completed_ms"] for f in frames], .99),
                "cold_completed_ms": run["frames"][0]["completed_ms"],
                "created_per_frame": statistics.mean(sum(x["created"] for x in f["flushes"]) for f in frames),
                "peak_rss_mib": run["peak_rss_bytes"] / 2**20,
                "retained_after_flush": [x["retained"] for x in last["flushes"]],
                "created_last_flushes": [x["created"] for x in last["flushes"]],
                "live_pipelines_after_wait": last["live_pipelines"],
                "metal_resource_mib": None if last["metal_resource_bytes"] is None else last["metal_resource_bytes"] / 2**20,
                "sampled_peak_metal_resource_mib": max((f["metal_resource_bytes"] / 2**20 for f in run["frames"] if f["metal_resource_bytes"] is not None), default=None),
            })
        medians = {key: statistics.median([r[key] for r in per_run])
                   for key in per_run[0] if isinstance(per_run[0][key], (float, int))}
        summary[f"{scenario}/{policy}"] = {"runs": len(runs), "medians": medians, "per_run": per_run}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--frames", type=int, default=100)
    parser.add_argument("--out", type=Path, default=ROOT / "runs/femtovg-cache-synthetic")
    args = parser.parse_args()
    if args.summarize_only:
        with gzip.open(args.out / "runs.jsonl.gz", "rt") as raw:
            records = [json.loads(line) for line in raw]
        (args.out / "summary.json").write_text(json.dumps(summarize(records), indent=2) + "\n")
        return
    if args.build or args.build_only:
        build()
    if args.build_only:
        return
    if args.runs < 1 or args.frames < 1:
        parser.error("runs and frames must be positive")
    args.out.mkdir(parents=True, exist_ok=False)
    provenance = json.loads((BINS / "provenance.json").read_text())
    for policy in POLICIES:
        verify_build(provenance[policy], BINS / policy)
    metadata = {"runs": args.runs, "frames": args.frames, "platform": platform.platform(),
                "inherited_environment": {"MTL_SHADER_CACHE_SIZE": os.environ.get("MTL_SHADER_CACHE_SIZE")},
                "driver_cache_reset_by_runner": False,
                "rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
                "archive_sha256": sha256(ARCHIVE),
                "lock_sha256": sha256(BENCH / "Cargo.lock"), "binaries": provenance}
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    records = []
    # Balanced Latin-square order for four policies, reversed on alternate blocks.
    orders = [(0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1)]
    with gzip.open(args.out / "runs.jsonl.gz", "wt") as raw:
        for round_index in range(args.runs):
            scenarios = SCENARIOS[round_index % len(SCENARIOS):] + SCENARIOS[:round_index % len(SCENARIOS)]
            order = orders[round_index % 4]
            if (round_index // 4) % 2:
                order = tuple(reversed(order))
            for scenario in scenarios:
                for position, index in enumerate(order):
                    policy = POLICIES[index]
                    command = [str(BINS / policy), policy, scenario, str(args.frames)]
                    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=180)
                    if result.returncode:
                        raise RuntimeError(f"{command}: {result.stderr}")
                    record = json.loads(result.stdout)
                    assert record["policy"] == policy and record["scenario"] == scenario
                    assert len(record["frames"]) == args.frames + 6
                    record.update(round=round_index + 1, position=position + 1, stderr=result.stderr)
                    raw.write(json.dumps(record) + "\n")
                    raw.flush()
                    records.append(record)
            print(f"round {round_index + 1}/{args.runs} complete ({len(records)} processes)", flush=True)
    summary = summarize(records)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for key, value in summary.items():
        m = value["medians"]
        print(f"{key:20s} created/frame={m['created_per_frame']:6.1f} completed p50/p95/p99={m['completed_p50_ms']:.3f}/{m['completed_p95_ms']:.3f}/{m['completed_p99_ms']:.3f} ms RSS={m['peak_rss_mib']:.1f} MiB")


if __name__ == "__main__":
    main()
