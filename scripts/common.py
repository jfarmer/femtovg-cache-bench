"""Pinned-source preparation shared by both benchmark runners (macOS/Linux)."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT
PIN = json.loads((ROOT / "vendor/femtovg.json").read_text())
ARCHIVE = ROOT / "vendor" / PIN["archive"]
SOURCE = ROOT / "vendor/femtovg"
BINS = ROOT / "target/bench-bins"
PATCHES = {
    "upstream": (),
    "pr343": ("pr343.patch",),
    "flush-lru64": ("flush-lru64.patch",),
    "strict-lru128": ("strict-lru128.patch",),
    "policy-study": ("strict-lru128.patch", "policy-study.patch"),
}


@contextmanager
def build_lock():
    (ROOT / "target").mkdir(exist_ok=True)
    with (ROOT / "target/bench-build.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def prepare_source(policy):
    patches = PATCHES[policy]
    actual = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if actual != PIN["sha256"]:
        raise RuntimeError(f"FemtoVG archive checksum mismatch: {actual}")
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    SOURCE.mkdir()
    with tarfile.open(ARCHIVE) as archive:
        archive.extractall(SOURCE, filter="data")
    for patch in ("instrumentation.patch", *patches):
        subprocess.run(["git", "apply", "--directory=vendor/femtovg",
                        str(ROOT / "patches" / patch)], cwd=ROOT, check=True)
    manifest = SOURCE / "Cargo.toml"
    contents = manifest.read_text()
    contents = contents.replace('wgpu = ["dep:wgpu"]', 'wgpu = ["dep:wgpu", "dep:lru"]')
    contents += '\n[dependencies.pipeline-cache-policy]\npath = "../../crates/cache-policy"\n'
    manifest.write_text(contents)
    print(f"prepared {policy} from FemtoVG {PIN['commit']}", flush=True)


def input_hashes():
    """Fingerprint build inputs so runs cannot silently use stale executables."""
    paths = [ROOT / "Cargo.toml", ROOT / "Cargo.lock", ARCHIVE,
             ROOT / "vendor/femtovg.json"]
    paths.extend(p for p in (ROOT / "vendor").iterdir()
                 if p.is_file() and p not in paths)
    for directory in ("src", "crates", "patches", "scripts"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def verify_build(provenance, binary):
    if hashlib.sha256(binary.read_bytes()).hexdigest() != provenance["binary_sha256"]:
        raise RuntimeError(f"binary changed; rebuild: {binary}")
    if input_hashes() != provenance["inputs"]:
        raise RuntimeError("build inputs changed; rebuild before measuring")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", choices=PATCHES, default="policy-study", nargs="?")
    args = parser.parse_args()
    with build_lock():
        prepare_source(args.policy)
