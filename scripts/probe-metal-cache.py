"""Probe the undocumented Metal cache-size override without clearing system caches."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

from common import ROOT, BINS, verify_build

POLICIES = ("upstream", "strict-lru128")
MODES = {"system": None, "size-zero": "0"}


def execute(policy, mode, frames):
    env = {k: v for k, v in os.environ.items() if k != "MTL_SHADER_CACHE_SIZE"}
    value = MODES[mode]
    if value is not None:
        env["MTL_SHADER_CACHE_SIZE"] = value
    result = subprocess.run([str(BINS / policy), policy, "17", str(frames)], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=180, check=True)
    record = json.loads(result.stdout)
    if "backend: Metal" not in record["adapter"]:
        raise RuntimeError("the probe requires the Metal backend")
    record["cache_setting"] = {"MTL_SHADER_CACHE_SIZE": value}
    record["mode"] = mode
    record["stderr"] = result.stderr
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("this diagnostic targets Metal on macOS")
    if args.out.is_absolute() or not (ROOT / args.out).resolve().is_relative_to(ROOT):
        parser.error("output must be inside the repository and specified relative to its root")
    if args.build:
        subprocess.run([sys.executable, str(ROOT / "scripts/femtovg-cache-synthetic.py"), "--build-only"],
                       cwd=ROOT, check=True)
    provenance = json.loads((BINS / "provenance.json").read_text())
    for policy in POLICIES:
        verify_build(provenance[policy], BINS / policy)
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=False)
    metadata = {"purpose": "diagnostic control probe, not a policy performance comparison",
                "platform": platform.platform(), "rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
                "policies": POLICIES, "states": 17, "measured_frames": 2, "rounds": 3,
                "settings": MODES, "driver_cache_reset": False,
                "binaries": {p: provenance[p] for p in POLICIES},
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    samples = []
    with (out / "runs.jsonl").open("w") as raw:
        for policy in POLICIES:
            record = execute(policy, "system", 1)
            record["kind"] = "prime"
            raw.write(json.dumps(record) + "\n")
            raw.flush()
        for round_index in range(3):
            modes = tuple(MODES) if round_index % 2 == 0 else tuple(reversed(MODES))
            policies = POLICIES if round_index % 2 == 0 else tuple(reversed(POLICIES))
            for policy in policies:
                for mode in modes:
                    record = execute(policy, mode, 2)
                    record.update(kind="measured", round=round_index+1)
                    raw.write(json.dumps(record) + "\n")
                    raw.flush()
                    samples.append(record)
                    print(f"round {round_index+1}: {policy}/{mode} complete", flush=True)
    summary = {}
    for policy in POLICIES:
        # Verify that requesting a different Metal cache setting did not change application-cache work.
        profiles = [[[(f["created"], f["retained"]) for f in frame["flushes"]]
                     for frame in run["frames"]] for run in samples if run["policy"] == policy]
        if any(p != profiles[0] for p in profiles[1:]):
            raise RuntimeError("operation counts differ between probe launches")
        for mode in MODES:
            runs = [r for r in samples if r["policy"] == policy and r["mode"] == mode]
            summary[f"{policy}/{mode}"] = {
                "runs": len(runs),
                "cold_completed_ms": [r["frames"][0]["completed_ms"] for r in runs],
                "measured_completed_median_ms": [statistics.median(f["completed_ms"] for f in r["frames"] if f["phase"] == "measured") for r in runs],
                "measured_cpu_median_ms": [statistics.median(f["cpu_ms"] for f in r["frames"] if f["phase"] == "measured") for r in runs],
            }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
