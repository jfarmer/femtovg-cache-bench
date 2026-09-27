"""Shared-model cache-policy sweep and selected ten-round real-GPU experiments."""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess

from common import ROOT, BENCH, ARCHIVE, BINS, SOURCE, prepare_source, build_lock, input_hashes, verify_build
BINARY = BINS / "policy-study"
POLICIES = ("lru", "flush-lru", "s3fifo", "retain")
# Selected only after inspecting the CPU sweep; SCALE stays fixed when capacity changes.
CASES = (("cycle-plus", 128, 128), ("cycle-plus", 128, 256),
         ("shuffle-plus", 128, 128), ("hot-scan", 64, 64),
         ("switch", 64, 64), ("batch-single", 64, 64), ("batch-split", 64, 64))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    with build_lock():
        prepare_source("policy-study")
        subprocess.run([
            "cargo", "build", "--release", "--locked", "--manifest-path",
            str(BENCH / "Cargo.toml"), "--bin", "policy-study",
        ], cwd=ROOT, check=True, env=dict(os.environ, PIPELINE_POLICY_STUDY="1"))
        BINS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BENCH / "target/release/policy-study", BINARY)
        (BINS / "policy-study-provenance.json").write_text(json.dumps({
            "binary_sha256": digest(BINARY),
            "renderer_sha256": digest(SOURCE / "src/renderer/wgpu.rs"),
            "inputs": input_hashes(),
        }, indent=2) + "\n")


def quantile(values, q):
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)]


def summarize(path):
    with gzip.open(path / "gpu.jsonl.gz", "rt") as raw:
        records = [json.loads(line) for line in raw]
    grouped = {}
    for run in records:
        key = f"{run['scenario']}/scale{run['scale']}/cap{run['capacity']}/{run['policy']}"
        # Initial ten frames are reported separately. Later transitions/bursts remain measured.
        frames = run["frames"][10:]
        phases = sorted({f["phase"] for f in frames})
        summary = {"seed": run["seed"], "peak_rss_mib": run["peak_rss_bytes"] / 2**20,
                   "peak_resident": run["model_stats"]["peak_resident"],
                   "peak_ghost": run["model_stats"]["peak_ghost"],
                   "initial_creations": sum(x["created"] for f in run["frames"][:10] for x in f["flushes"]),
                   "created_per_frame": statistics.mean(sum(x["created"] for x in f["flushes"]) for f in frames),
                   "final_resident": frames[-1]["flushes"][-1]["retained"]}
        for field in ("cpu_ms", "completed_ms"):
            for percentile in (50, 95, 99):
                summary[f"{field}_p{percentile}"] = quantile([f[field] for f in frames], percentile/100)
        footprint = re.search(r"(\d+)\s+peak memory footprint", run["process_statistics"])
        if footprint:
            summary["peak_footprint_mib"] = int(footprint[1]) / 2**20
        summary["phases"] = {phase: {
            "frames": sum(f["phase"] == phase for f in frames),
            "mean_created": statistics.mean(sum(x["created"] for x in f["flushes"]) for f in frames if f["phase"] == phase),
            "completed_p50_ms": quantile([f["completed_ms"] for f in frames if f["phase"] == phase], .5),
        } for phase in phases}
        grouped.setdefault(key, []).append(summary)
    output = {key: {"runs": len(runs), "medians": {
        metric: statistics.median(r[metric] for r in runs) for metric in runs[0] if metric not in ("seed", "phases")},
        "per_run": runs} for key, runs in grouped.items()}
    (path / "summary.json").write_text(json.dumps(output, indent=2) + "\n")
    return output


def summarize_simulation(path):
    grouped = {}
    with gzip.open(path / "simulation.jsonl.gz", "rt") as raw:
        for line in raw:
            run = json.loads(line)
            key = f"{run['scenario']}/scale{run['scale']}/cap{run['capacity']}/{run['policy']}"
            grouped.setdefault(key, []).append(run)
    output = {}
    for key, runs in grouped.items():
        measured = [run["frames"][10:] for run in runs]
        phases = sorted({f["phase"] for frames in measured for f in frames})
        output[key] = {
            "seeds": len(runs),
            "mean_misses_per_frame": statistics.mean(sum(f["misses"] for f in frames) / len(frames) for frames in measured),
            "mean_miss_ratio": statistics.mean(sum(f["misses"] for f in frames) / sum(f["requests"] for f in frames) for frames in measured),
            "peak_resident": max(r["stats"]["peak_resident"] for r in runs),
            "peak_ghost": max(r["stats"]["peak_ghost"] for r in runs),
            "mean_misses_by_frame": [statistics.mean(r["frames"][i]["misses"] for r in runs) for i in range(100)],
            "mean_misses_by_phase": {phase: statistics.mean(f["misses"] for frames in measured for f in frames if f["phase"] == phase) for phase in phases},
        }
    (path / "simulation-summary.json").write_text(json.dumps(output, indent=2) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "simulate", "gpu", "summarize", "simulation-summary"))
    parser.add_argument("--out", type=Path, default=ROOT / "runs/femtovg-policy-study")
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args()
    if args.mode == "build":
        build()
        return
    args.out.mkdir(parents=True, exist_ok=True)
    if args.mode == "simulation-summary":
        summarize_simulation(args.out)
        return
    if args.mode in ("simulate", "gpu"):
        provenance = json.loads((BINS / "policy-study-provenance.json").read_text())
        verify_build(provenance, BINARY)
    if args.mode == "simulate":
        dest = args.out / "simulation.jsonl.gz"
        if dest.exists():
            parser.error(f"refusing to overwrite {dest}")
        (args.out / "simulation-metadata.json").write_text(json.dumps({
            "build": provenance, "binary_sha256": digest(BINARY), "lock_sha256": digest(BENCH / "Cargo.lock"),
            "scales": [64, 128, 256], "capacities": [32, 64, 128, 256, 512],
            "seeds": list(range(1, 11)), "frames": 100,
        }, indent=2) + "\n")
        process = subprocess.Popen([str(BINARY), "--sweep"], stdout=subprocess.PIPE, text=True)
        with gzip.open(dest, "wt") as raw:
            for line in process.stdout:
                raw.write(line)
        assert process.wait() == 0
        print(f"saved {dest}")
        return
    if args.mode == "summarize":
        summarize(args.out)
        return
    assert args.runs > 0
    time_command = shutil.which("time")
    if time_command is None:
        parser.error("the external time utility must be available on PATH")
    dest = args.out / "gpu.jsonl.gz"
    if dest.exists():
        parser.error(f"refusing to overwrite {dest}")
    metadata = {"runs": args.runs, "frames": 100, "cases": CASES, "policies": POLICIES,
                "platform": platform.platform(),
                "inherited_environment": {"MTL_SHADER_CACHE_SIZE": os.environ.get("MTL_SHADER_CACHE_SIZE")},
                "driver_cache_reset_by_runner": False, "rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
                "build": provenance, "binary_sha256": digest(BINARY), "lock_sha256": digest(BENCH / "Cargo.lock"),
                "archive_sha256": digest(ARCHIVE),
                "sources": {str(p.relative_to(ROOT)): digest(p) for p in sorted(BENCH.rglob("*.rs"))
                            if "target" not in p.parts and "vendor" not in p.parts},
                "renderer_sha256": json.loads((BINS / "policy-study-provenance.json").read_text())["renderer_sha256"]}
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    orders = [(0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1)]
    with gzip.open(dest, "wt") as raw:
        for run in range(args.runs):
            cases = CASES[run % len(CASES):] + CASES[:run % len(CASES)]
            order = orders[run % 4]
            if (run // 4) % 2:
                order = tuple(reversed(order))
            for scenario, scale, capacity in cases:
                for position, index in enumerate(order):
                    policy = POLICIES[index]
                    flag = "-l" if platform.system() == "Darwin" else "-v"
                    cmd = [time_command, flag, str(BINARY), policy, str(capacity), scenario, str(scale), "100", str(run + 1)]
                    result = subprocess.run(cmd, text=True, capture_output=True, timeout=240)
                    if result.returncode:
                        raise RuntimeError(f"{cmd}: {result.stderr}")
                    record = json.loads(result.stdout)
                    if platform.system() == "Darwin":
                        peak = re.search(r"(\d+)\s+maximum resident set size", result.stderr)
                        record["peak_rss_bytes"] = int(peak[1])
                    else:
                        peak = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", result.stderr)
                        record["peak_rss_bytes"] = int(peak[1]) * 1024
                    record.update(position=position + 1, process_statistics=result.stderr)
                    raw.write(json.dumps(record) + "\n")
                    raw.flush()
            print(f"round {run+1}/{args.runs} complete", flush=True)
    summarize(args.out)


if __name__ == "__main__":
    main()
