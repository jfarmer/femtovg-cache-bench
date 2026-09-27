"""Verify provenance and reproduce checked-in summaries without a GPU."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import tomllib

from common import ROOT, ARCHIVE, PIN


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load_runner(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    require(digest(ARCHIVE) == PIN["sha256"], "pinned archive checksum mismatch")
    for name in ("pr343", "policy-study"):
        directory = ROOT / "results" / name
        metadata = json.loads((directory / "metadata.json").read_text())
        require(digest(ARCHIVE) == metadata["archive_sha256"], f"{name}: archive mismatch")
        require(digest(directory / "Cargo.lock") == metadata["lock_sha256"], f"{name}: historical lock mismatch")
        for relative, expected in metadata.get("sources", {}).items():
            require(not Path(relative).is_absolute() and (ROOT / relative).resolve().is_relative_to(ROOT),
                    f"source path must stay inside the repository: {relative}")
            require(digest(ROOT / relative) == expected, f"recorded source differs: {relative}")
    # Moving into a workspace removes unused lock entries, but must not change registry pins.
    def registry_pins(path):
        return {(p["name"], p["version"], p["source"], p["checksum"])
                for p in tomllib.loads(path.read_text())["package"] if "checksum" in p}
    require(registry_pins(ROOT / "Cargo.lock") <= registry_pins(ROOT / "results/policy-study/Cargo.lock"),
            "standalone lock contains changed registry pins")
    direct = load_runner("femtovg-cache-synthetic")
    study = load_runner("femtovg-policy-study")
    directory = ROOT / "results/pr343"
    with gzip.open(directory / "runs.jsonl.gz", "rt") as raw:
        records = [json.loads(line) for line in raw]
    require(len(records) == 240, "expected 240 direct comparison runs")
    require(direct.summarize(records) == json.loads((directory / "summary.json").read_text()),
            "direct comparison summary mismatch")
    del records
    with tempfile.TemporaryDirectory(prefix="femtovg-results-") as temporary:
        output = Path(temporary)
        directory = ROOT / "results/policy-study"
        for filename, count in (("gpu.jsonl.gz", 280), ("simulation.jsonl.gz", 7200)):
            shutil.copy2(directory / filename, output / filename)
            with gzip.open(output / filename, "rt") as raw:
                require(sum(1 for _ in raw) == count, f"unexpected record count in {filename}")
        for filename, summarize in (("summary.json", study.summarize),
                                    ("simulation-summary.json", study.summarize_simulation)):
            require(summarize(output) == json.loads((directory / filename).read_text()),
                    f"policy study {filename} mismatch")
    print("Verified source provenance, registry pins, 520 GPU runs, 7,200 simulations, and all three summaries.")


if __name__ == "__main__":
    main()
