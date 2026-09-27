"""Validate archived results, Rust tests, and a fresh CPU sweep; optionally smoke-test the GPU."""
import argparse
import gzip
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from common import ROOT, BINS, build_lock, prepare_source, verify_build


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True)


def compare_simulations(actual_path, expected_path):
    with gzip.open(actual_path, "rt") as actual, gzip.open(expected_path, "rt") as expected:
        count = 0
        for a, b in itertools.zip_longest(actual, expected):
            count += 1
            if a is None or b is None or json.loads(a) != json.loads(b):
                raise RuntimeError(f"simulation mismatch at record {count}")
        if count != 7200:
            raise RuntimeError(f"expected 7,200 simulations, got {count}")
    print("Fresh CPU sweep matches all 7,200 archived records exactly.", flush=True)


def smoke_gpu(output):
    # Direct runner exercises all six scenarios and all four historical policies.
    run(sys.executable, ROOT / "scripts/femtovg-cache-synthetic.py",
        "--build", "--runs", "1", "--frames", "1", "--out", output / "direct")
    binary = BINS / "policy-study"
    provenance = json.loads((BINS / "policy-study-provenance.json").read_text())
    verify_build(provenance, binary)
    with (output / "policy-smoke.jsonl").open("w") as raw:
        for scenario in ("cycle-plus", "batch-split"):
            for policy in ("lru", "flush-lru", "s3fifo", "retain"):
                # The trace generator requires scale >= 16 and at least 60 frames.
                process = subprocess.run([str(binary), policy, "16", scenario, "16", "60", "1"],
                                         cwd=ROOT, text=True, stdout=subprocess.PIPE, check=True)
                record = json.loads(process.stdout)
                if len(record["frames"]) != 60:
                    raise RuntimeError("unexpected GPU frame count")
                raw.write(json.dumps(record) + "\n")
                raw.flush()
                print(f"{policy}/{scenario}: GPU/model assertions passed", flush=True)
    (output / "policy-smoke-metadata.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print("GPU smoke checks passed. These short runs are validation, not performance evidence.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpu", action="store_true", help="also build direct variants and run real-GPU smoke checks")
    args = parser.parse_args()
    run(sys.executable, ROOT / "scripts/verify-results.py")
    with build_lock():
        prepare_source("policy-study")
        run("cargo", "test", "--locked", "--workspace")
    run(sys.executable, ROOT / "scripts/femtovg-policy-study.py", "build")
    (ROOT / "runs").mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="check-", dir=ROOT / "runs"))
    print(f"Saving validation outputs to {output.relative_to(ROOT)}", flush=True)
    run(sys.executable, ROOT / "scripts/femtovg-policy-study.py", "simulate", "--out", output)
    compare_simulations(output / "simulation.jsonl.gz", ROOT / "results/policy-study/simulation.jsonl.gz")
    if args.gpu:
        smoke_gpu(output)


if __name__ == "__main__":
    main()
