"""Repeat the pinned proposal/#343 comparison with balanced randomized pairs."""
import argparse
import datetime
import gzip
import importlib.util
import json
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess

from common import ROOT, verify_build

POLICIES = ("pr343", "flush-lru64")
CASES = ("64", "65", "mixed")
SEED = 20260927
ROUNDS = 20
BASELINE = ROOT / "results/pr-report-d5241b9"


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


report = module("run-report")
report.BINS = ROOT / "target/confirmation-bins"
direct = module("femtovg-cache-synthetic")


def schedule():
    rng = random.Random(SEED)
    first = {case: [0] * (ROUNDS // 2) + [1] * (ROUNDS // 2) for case in CASES}
    for choices in first.values():
        rng.shuffle(choices)
    blocks = []
    for index in range(ROUNDS):
        cases = list(CASES)
        rng.shuffle(cases)
        for case in cases:
            order = POLICIES if first[case][index] == 0 else POLICIES[::-1]
            blocks.append({"pair": len(blocks) + 1, "round": index + 1, "scenario": case, "order": order})
    return blocks


def read(path):
    with gzip.open(path, "rt") as raw:
        return [json.loads(line) for line in raw]


def profile(run):
    return [[(f["created"], f["retained"]) for f in frame["flushes"]] for frame in run["frames"]]


def analyze(out):
    meta = json.loads((out / "metadata.json").read_text())
    if "finished_utc" not in meta:
        raise RuntimeError("confirmation run is incomplete")
    checksums = {name: report.digest(out / name) for name in ("metadata.json", "runs.jsonl.gz", "priming.jsonl.gz", "Cargo.lock")}
    if (out / "checksums.json").exists() and checksums != json.loads((out / "checksums.json").read_text()):
        raise RuntimeError("recorded input checksum changed")
    runs, priming = read(out / "runs.jsonl.gz"), read(out / "priming.jsonl.gz")
    if len(runs) != ROUNDS * len(CASES) * len(POLICIES) or len(priming) != 12:
        raise RuntimeError("incomplete confirmation data")
    expected = [(b["pair"], b["round"], b["scenario"], policy, position + 1)
                for b in meta["schedule"] for position, policy in enumerate(b["order"])]
    observed = [(r["pair"], r["round"], r["scenario"], r["policy"], r["position"]) for r in runs]
    if observed != expected or meta["schedule"] != json.loads(json.dumps(schedule())):
        raise RuntimeError("recorded order differs from the committed schedule")
    originals = {(r["scenario"], r["policy"]): profile(r) for r in read(BASELINE / "direct/runs.jsonl.gz")}
    for run in runs + priming:
        if len(run["frames"]) != 106 or profile(run) != originals[(run["scenario"], run["policy"])]:
            raise RuntimeError("creation/residency profile differs from primary campaign")
    summary = direct.summarize(runs)
    baseline = json.loads((BASELINE / "direct/summary.json").read_text())
    lines = ["# Focused randomized confirmation", "",
             "A separate repeat of the proposal versus #343 using the exact pinned renderer sources and release settings of the [primary report](../../REPORT.md). "
             "This is a synthetic library benchmark; no application usage was recorded.", "",
             "Twenty paired blocks per workload, with policy order randomized and balanced ten-first/ten-second for each policy. "
             "Workload order is randomized within each round. The seed, full schedule, and protocol were committed before measurement. "
             "Each process records one initial frame, five warmup frames, and 100 measured frames. Two full priming passes precede the measured blocks. "
             "The Metal cache-size override is explicitly unset; subsequent driver-cache eviction/invalidation remains uncontrolled. No runs are excluded.", "",
             f"Harness commit: `{meta['harness_commit']}`. Started: {meta['started_utc']}. Finished: {meta['finished_utc']}.", "",
             "| Workload | Policy | Creations/frame | Primary median (ms) | Repeat median (ms) | Repeat p95 (ms) |",
             "| --- | --- | ---: | ---: | ---: | ---: |"]
    for case in CASES:
        for policy in POLICIES:
            key = f"{case}/{policy}"
            m = summary[key]["medians"]
            label = "#343" if policy == "pr343" else "Proposed"
            lines.append(f"| {case} | {label} | {m['created_per_frame']:.0f} | {baseline[key]['medians']['completed_p50_ms']:.3f} | {m['completed_p50_ms']:.3f} | {m['completed_p95_ms']:.3f} |")
    ratios = {}
    lines += ["", "| Workload | Median paired proposed/#343 ratio | Observed pair range |", "| --- | ---: | ---: |"]
    for case in CASES:
        values = []
        for pair in [b["pair"] for b in meta["schedule"] if b["scenario"] == case]:
            times = {r["policy"]: direct.percentile([f["completed_ms"] for f in r["frames"] if f["phase"] == "measured"], .5) for r in runs if r["pair"] == pair}
            values.append(times["flush-lru64"] / times["pr343"])
        ratios[case] = values
        lines.append(f"| {case} | {statistics.median(values):.3f} | {min(values):.3f}–{max(values):.3f} |")
    lines += ["", "Ratios pair process medians within adjacent comparison blocks; below one favors the proposal. "
              "The ranges describe the twenty observed pairs, not confidence intervals. Table p95 values are medians of within-process p95 values. "
              "This small repeat checks reproducibility and obvious differences; it does not establish equivalence, a population tail latency, or application-wide speedups.", "",
              "All 120 measured and 12 priming processes match the primary campaign's creation/residency profile at every frame and flush. "
              "Full frames, process timestamps, and actual execution order are retained. The protocol is in [metadata.json](metadata.json); "
              "raw data is in [runs.jsonl.gz](runs.jsonl.gz) and [priming.jsonl.gz](priming.jsonl.gz). "
              "[summary.json](summary.json) includes CPU quantiles, memory diagnostics, and individual process summaries; "
              "[paired-ratios.json](paired-ratios.json) preserves every paired comparison. [checksums.json](checksums.json) fingerprints the recorded inputs.", "",
              "```sh", "python3 scripts/confirm-report.py --out runs/my-confirmation",
              f"python3 scripts/confirm-report.py --summarize --out {out.relative_to(ROOT).as_posix()}", "```", ""]
    for name, value in (("summary.json", summary), ("paired-ratios.json", ratios), ("checksums.json", checksums)):
        (out / name).write_text(json.dumps(value, indent=2) + "\n")
    (out / "README.md").write_text("\n".join(lines))
    print("\n".join(lines[8:20]), flush=True)


def execute(policy, scenario, **labels):
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record = report.launch([report.BINS / policy, policy, scenario, 100])
    if record["policy"] != policy or record["scenario"] != scenario:
        raise RuntimeError("unexpected policy/scenario")
    record.update(started_utc=start, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), **labels)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("runs/confirmation-d5241b9"))
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.out.is_absolute() or not (ROOT / args.out).resolve().is_relative_to(ROOT):
        parser.error("output must be repository-relative")
    out = ROOT / args.out
    if args.summarize:
        analyze(out)
        return
    if out.exists():
        parser.error("choose a new output directory")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        parser.error("commit the protocol before measurement; the checkout must be clean")
    report.build(POLICIES)
    provenance = json.loads((report.BINS / "provenance.json").read_text())
    previous = json.loads((BASELINE / "metadata.json").read_text())
    for policy in POLICIES:
        verify_build(provenance[policy], report.BINS / policy)
        if provenance[policy]["renderer_sha256"] != previous["binaries"][policy]["renderer_sha256"]:
            raise RuntimeError("instrumented renderer differs from primary campaign")
    out.mkdir(parents=True)
    shutil.copy2(ROOT / "Cargo.lock", out / "Cargo.lock")
    meta = {"harness_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "source": report.PIN,
            "platform": platform.platform(), "rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
            "binaries": provenance, "schedule": schedule(), "random_seed": SEED,
            "protocol": {"rounds": ROUNDS, "priming_passes": 2, "initial_frames": 1, "warmup_frames": 5,
                         "measured_frames": 100, "MTL_SHADER_CACHE_SIZE": None, "inherited_override_removed": True,
                         "subsequent_driver_cache_state": "uncontrolled", "outlier_removal": False}}
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    with gzip.open(out / "priming.jsonl.gz", "wt") as raw:
        for index in range(2):
            for case in CASES:
                for policy in POLICIES if index == 0 else POLICIES[::-1]:
                    report.write_record(raw, execute(policy, case, priming_pass=index + 1))
            print(f"priming pass {index + 1}/2 complete", flush=True)
    with gzip.open(out / "runs.jsonl.gz", "wt") as raw:
        for block in meta["schedule"]:
            for position, policy in enumerate(block["order"]):
                report.write_record(raw, execute(policy, block["scenario"], pair=block["pair"], round=block["round"], position=position + 1))
            if block["pair"] % len(CASES) == 0:
                print(f"round {block['round']}/{ROUNDS} complete", flush=True)
    meta["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    analyze(out)


if __name__ == "__main__":
    main()
