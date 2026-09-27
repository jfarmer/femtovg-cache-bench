"""Build the pinned PR/base and run the primary report under an explicit warm-up protocol."""
import argparse
import datetime
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tarfile

from common import ROOT, SOURCE, build_lock, input_hashes, verify_build

PIN = json.loads((ROOT / "vendor/report-source.json").read_text())
ARCHIVE = ROOT / "vendor" / PIN["archive"]
BINS = ROOT / "target/report-bins"
DIRECT_POLICIES = ("upstream", "pr343", "flush-lru64", "strict-lru128")
STUDY_CASES = (("cycle-plus", 64, 64), ("shuffle-plus", 64, 64),
               ("cycle-plus", 128, 128), ("shuffle-plus", 128, 128),
               ("hot-scan", 64, 64), ("switch", 64, 64),
               ("batch-single", 64, 64), ("batch-split", 64, 64))
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))


def load_runner(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_patch(path):
    subprocess.run(["git", "apply", "--directory=vendor/femtovg", str(ROOT / path)], cwd=ROOT, check=True)


def prepare(policy):
    if digest(ARCHIVE) != PIN["sha256"]:
        raise RuntimeError("report source archive checksum mismatch")
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir(parents=True)
    with tarfile.open(ARCHIVE) as archive:
        archive.extractall(SOURCE, filter="data")
    origin = "candidate" if policy == "flush-lru64" else "base"
    if origin == "candidate":
        apply_patch("patches/report/current-pr.patch")
    before = digest(SOURCE / "src/renderer/wgpu.rs")
    if before != PIN[origin]["renderer_sha256"]:
        raise RuntimeError(f"{origin} renderer differs from its exact pinned git revision")
    apply_patch(f"patches/report/instrumentation-{origin}.patch")
    if policy == "pr343":
        apply_patch("patches/pr343.patch")
    if policy in ("strict-lru128", "policy-study"):
        apply_patch("patches/strict-lru128.patch")
    if policy == "policy-study":
        apply_patch("patches/policy-study.patch")
    manifest = SOURCE / "Cargo.toml"
    contents = manifest.read_text().replace('wgpu = ["dep:wgpu"]', 'wgpu = ["dep:wgpu", "dep:lru"]')
    contents += '\n[dependencies.pipeline-cache-policy]\npath = "../../crates/cache-policy"\n'
    manifest.write_text(contents)
    return {"origin": origin, "origin_commit": PIN[origin]["commit"], "origin_renderer_sha256": before}


def build():
    provenance = {}
    with build_lock():
        BINS.mkdir(parents=True, exist_ok=True)
        for policy in (*DIRECT_POLICIES, "policy-study"):
            origin = prepare(policy)
            binary = "policy-study" if policy == "policy-study" else "femtovg-cache-bench"
            env = dict(os.environ, CACHE_BENCH_POLICY=policy, PIPELINE_POLICY_STUDY="1")
            with (BINS / f"{policy}.build.log").open("w") as log:
                subprocess.run(["cargo", "build", "--locked", "--release", "--bin", binary], cwd=ROOT,
                               env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            shutil.copy2(ROOT / "target/release" / binary, BINS / policy)
            provenance[policy] = {**origin, "binary_sha256": digest(BINS / policy),
                                  "renderer_sha256": digest(SOURCE / "src/renderer/wgpu.rs"),
                                  "inputs": input_hashes()}
            print(f"built {policy} ({origin['origin_commit'][:7]})", flush=True)
        (BINS / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def launch(command, cache_size=None, timed=False):
    env = {k: v for k, v in os.environ.items() if k != "MTL_SHADER_CACHE_SIZE"}
    if cache_size is not None:
        env["MTL_SHADER_CACHE_SIZE"] = cache_size
    if timed:
        executable = shutil.which("time")
        if executable is None:
            raise RuntimeError("external time utility required on PATH")
        command = [executable, "-l" if platform.system() == "Darwin" else "-v", *command]
    process = subprocess.run([str(a) for a in command], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=300, check=True)
    record = json.loads(process.stdout)
    if timed:
        pattern = r"(\d+)\s+maximum resident set size" if platform.system() == "Darwin" else r"Maximum resident set size \(kbytes\):\s*(\d+)"
        match = re.search(pattern, process.stderr)
        if not match:
            raise RuntimeError("could not parse process memory statistics")
        record["peak_rss_bytes"] = int(match[1]) * (1 if platform.system() == "Darwin" else 1024)
        record["process_statistics"] = process.stderr
    else:
        record["stderr"] = process.stderr
    return record


def write_record(output, record):
    output.write(json.dumps(record) + "\n")
    output.flush()


def run_direct(out, runner):
    # Two complete passes cover the exact states/operations of every measured workload.
    with gzip.open(out / "priming.jsonl.gz", "wt") as raw:
        for warmup_pass in range(2):
            for scenario in runner.SCENARIOS:
                for policy in DIRECT_POLICIES:
                    record = launch([BINS / policy, policy, scenario, "100"])
                    record.update(priming_pass=warmup_pass+1)
                    write_record(raw, record)
            print(f"direct priming pass {warmup_pass+1}/2 complete", flush=True)
    records = []
    with gzip.open(out / "runs.jsonl.gz", "wt") as raw:
        for index in range(10):
            scenarios = runner.SCENARIOS[index % 6:] + runner.SCENARIOS[:index % 6]
            order = ORDERS[index % 4]
            if (index // 4) % 2:
                order = tuple(reversed(order))
            for scenario in scenarios:
                for position, choice in enumerate(order):
                    policy = DIRECT_POLICIES[choice]
                    record = launch([BINS / policy, policy, scenario, "100"])
                    if len(record["frames"]) != 106 or record["policy"] != policy or record["scenario"] != scenario:
                        raise RuntimeError("unexpected direct-run result")
                    record.update(round=index+1, position=position+1)
                    write_record(raw, record)
                    records.append(record)
            print(f"direct round {index+1}/10 complete", flush=True)
    (out / "summary.json").write_text(json.dumps(runner.summarize(records), indent=2) + "\n")


def run_study(out, runner):
    with gzip.open(out / "priming.jsonl.gz", "wt") as raw:
        for warmup_pass in range(2):
            for scenario, scale, capacity in STUDY_CASES:
                for policy in runner.POLICIES:
                    record = launch([BINS / "policy-study", policy, capacity, scenario, scale, 100, 1], timed=True)
                    record.update(priming_pass=warmup_pass+1)
                    write_record(raw, record)
            print(f"policy priming pass {warmup_pass+1}/2 complete", flush=True)
    with gzip.open(out / "gpu.jsonl.gz", "wt") as raw:
        for index in range(10):
            cases = STUDY_CASES[index % len(STUDY_CASES):] + STUDY_CASES[:index % len(STUDY_CASES)]
            order = ORDERS[index % 4]
            if (index // 4) % 2:
                order = tuple(reversed(order))
            for scenario, scale, capacity in cases:
                for position, choice in enumerate(order):
                    policy = runner.POLICIES[choice]
                    record = launch([BINS / "policy-study", policy, capacity, scenario, scale, 100, index+1], timed=True)
                    if len(record["frames"]) != 100:
                        raise RuntimeError("unexpected policy-study frame count")
                    record.update(position=position+1)
                    write_record(raw, record)
            print(f"policy round {index+1}/10 complete", flush=True)
    runner.summarize(out)


def cold_control(out):
    # Matched first-use work on the actual PR/base binaries; this is diagnostic only.
    with gzip.open(out / "runs.jsonl.gz", "wt") as raw:
        for index in range(3):
            settings = (None, "0") if index % 2 == 0 else ("0", None)
            for policy in ("upstream", "flush-lru64"):
                for setting in settings:
                    record = launch([BINS / policy, policy, 17, 2], cache_size=setting)
                    if sum(f["created"] for f in record["frames"][0]["flushes"]) != 17:
                        raise RuntimeError("cold diagnostic does not have matched creation work")
                    record.update(round=index+1, cache_size=setting)
                    write_record(raw, record)
            print(f"matched-work cache-control round {index+1}/3 complete", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("runs/pr-report"))
    args = parser.parse_args()
    if not args.skip_build:
        build()
    if args.build_only:
        return
    if args.out.is_absolute() or not (ROOT / args.out).resolve().is_relative_to(ROOT):
        parser.error("output must be repository-relative")
    provenance = json.loads((BINS / "provenance.json").read_text())
    for policy, data in provenance.items():
        verify_build(data, BINS / policy)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=False)
    direct = load_runner("femtovg-cache-synthetic")
    study = load_runner("femtovg-policy-study")
    metadata = {"started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "harness_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source": PIN, "binaries": provenance, "direct_scenarios": direct.SCENARIOS,
                "study_cases": STUDY_CASES, "study_policies": study.POLICIES, "platform": platform.platform(),
                "rustc": subprocess.check_output(["rustc", "-Vv"], text=True), "lock_sha256": digest(ROOT / "Cargo.lock"),
                "protocol": {"metal_shader_cache_size": None, "environment_override_removed": True,
                             "driver_cache_reset": False, "priming_passes_per_suite": 2,
                             "priming": "complete workload traces for every policy/case; saved separately; fresh process per launch",
                             "warmth_claim": "explicit preparation protocol, not proof of internal cache hits",
                             "rounds": 10, "direct_measured_frames": 100, "study_total_frames": 100,
                             "study_discarded_initial_frames": 10, "outlier_removal": False,
                             "study_priming_seed": 1, "note": "shuffled seeds reorder the same state set; full scan traces include every later state"}}
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    for name in ("direct", "policies", "cold-control"):
        (out / name).mkdir()
    # CPU analysis runs before GPU measurements to avoid concurrent benchmark load.
    with gzip.open(out / "policies/simulation.jsonl.gz", "wt") as raw:
        process = subprocess.Popen([str(BINS / "policy-study"), "--sweep"], cwd=ROOT, stdout=subprocess.PIPE, text=True)
        for line in process.stdout:
            raw.write(line)
        if process.wait() != 0:
            raise RuntimeError("CPU sweep failed")
    study.summarize_simulation(out / "policies")
    run_direct(out / "direct", direct)
    run_study(out / "policies", study)
    if platform.system() == "Darwin":
        cold_control(out / "cold-control")
    metadata["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Completed primary measurements: {args.out}", flush=True)


if __name__ == "__main__":
    main()
