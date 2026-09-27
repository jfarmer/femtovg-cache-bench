"""Archive a completed primary campaign without altering its raw measurements."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from common import ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    for path in (args.source, args.destination):
        if path.is_absolute() or not (ROOT / path).resolve().is_relative_to(ROOT):
            parser.error("paths must be repository-relative")
    source, destination = ROOT / args.source, ROOT / args.destination
    metadata = json.loads((source / "metadata.json").read_text())
    if "finished_utc" not in metadata:
        parser.error("campaign is incomplete")
    if digest(ROOT / "Cargo.lock") != metadata["lock_sha256"]:
        parser.error("Cargo.lock changed since measurement; restore the measured lockfile first")
    if destination.exists():
        parser.error("destination already exists; choose a new archive directory")
    shutil.copytree(source, destination)
    copied = {p.relative_to(source).as_posix(): digest(p) for p in source.rglob("*") if p.is_file()}
    for name, checksum in copied.items():
        if digest(destination / name) != checksum:
            raise RuntimeError(f"archive copy differs: {name}")
    shutil.copy2(ROOT / "Cargo.lock", destination / "Cargo.lock")
    subprocess.run([sys.executable, "scripts/render-report.py", args.destination.as_posix()], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "scripts/report-sanity.py", args.destination.as_posix()], cwd=ROOT, check=True)
    # Summary regeneration must leave the originally recorded files unchanged.
    for name, checksum in copied.items():
        if not name.startswith("analysis/") and digest(destination / name) != checksum:
            raise RuntimeError(f"analysis changed recorded data: {name}")
    files = {p.relative_to(destination).as_posix(): digest(p) for p in sorted(destination.rglob("*")) if p.is_file()}
    manifest = {"harness_commit": metadata["harness_commit"], "raw_copy_verified": True, "files": files}
    (destination / "archive.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Archived and verified {len(files)} files in {args.destination}")


if __name__ == "__main__":
    main()
