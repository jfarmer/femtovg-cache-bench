"""Master as the control: one row per scenario, each policy's frame time against master.

Usage: control_table.py RESULTS_DIR [percent|full]

RESULTS_DIR holds steady/, return-1160/, return-560/ and scan/ as the harness wrote them.
`percent` prints the comment table (master in ms, the rest as change against master);
`full` prints the README table (ms and pipelines kept for every policy).
"""
import gzip
import json
import statistics
import sys
from pathlib import Path

root = Path(sys.argv[1])
mode = sys.argv[2] if len(sys.argv) > 2 else "percent"
policies = ["upstream", "pr343", "pr371", "flush-lru512-idle64"]
labels = {"upstream": "master", "pr343": "#343", "pr371": "#371", "flush-lru512-idle64": "this PR"}


def created(frame):
    return sum(f["created"] for f in frame["flushes"])


def load(name):
    return [json.loads(line) for line in gzip.open(root / name / "runs.jsonl.gz", "rt")]


rows = []  # (scenario label, metric label, {policy: ms}, {policy: pipelines kept}, {policy: rebuilt})

summary = json.load(open(root / "steady/summary.json"))
for scenario in ("63", "64", "65", "80", "129", "mixed"):
    ms, kept, rebuilt = {}, {}, {}
    for p in policies:
        entry = summary[f"{scenario}/{p}"]
        ms[p] = entry["medians"]["completed_p50_ms"]
        kept[p] = statistics.median(run["retained_after_flush"][-1] for run in entry["per_run"])
        rebuilt[p] = entry["medians"]["created_per_frame"]
    if scenario == "mixed":
        label = "glyph, clipped-layer, filter, screen and clear flushes"
    else:
        label = f"{scenario} pipelines every frame"
    rows.append((label, "median frame", ms, kept, rebuilt))

for name, absence in (("return-560", 560), ("return-1160", 1160)):
    records = load(name)
    for scenario in sorted({r["scenario"] for r in records}):
        a, b = scenario.split(":")[1:]
        ms, kept, rebuilt = {}, {}, {}
        for p in policies:
            runs = [r for r in records if r["scenario"] == scenario and r["policy"] == p]
            back = [next(f for f in r["frames"] if f["stage"] == "return") for r in runs]
            ms[p] = statistics.median(f["completed_ms"] for f in back)
            rebuilt[p] = statistics.median(created(f) for f in back)
            kept[p] = statistics.median(r["frames"][-1]["flushes"][-1]["retained"] for r in runs)
        rows.append((f"{a}+{b}, first set back after {absence:,} flushes", "return frame", ms, kept, rebuilt))

records = load("scan")
for scenario in sorted({r["scenario"] for r in records}):
    k = int(scenario.split(":")[1])
    ms, kept, rebuilt = {}, {}, {}
    for p in policies:
        runs = [r for r in records if r["scenario"] == scenario and r["policy"] == p]
        scan = lambda r: [f for f in r["frames"] if f["stage"] == "scan"]
        ms[p] = statistics.median(statistics.median(f["completed_ms"] for f in scan(r)) for r in runs)
        rebuilt[p] = statistics.median(statistics.mean(created(f) for f in scan(r)) for r in runs)
        kept[p] = statistics.median(r["frames"][-1]["flushes"][-1]["retained"] for r in runs)
    rows.append((f"{k} new blend states every frame", "median frame", ms, kept, rebuilt))


def pct(value, control):
    change = (value - control) / control * 100
    return "0%" if abs(change) < 0.5 else f"{change:+.0f}%"


if mode == "percent":
    print("| Scenario | master | #343 | #371 | this PR |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for label, metric, ms, kept, rebuilt in rows:
        cells = [f"{ms['upstream']:.2f} ms"] + [pct(ms[p], ms["upstream"]) for p in policies[1:]]
        print(f"| {label} | " + " | ".join(cells) + " |")
    print()
    print("Pipelines kept at the end of each scenario:")
    print()
    print("| Scenario | master | #343 | #371 | this PR |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for label, metric, ms, kept, rebuilt in rows:
        print(f"| {label} | " + " | ".join(f"{kept[p]:.0f}" for p in policies) + " |")
else:
    print("| Scenario | Policy | Rebuilt | Frame (ms) | Pipelines kept |")
    print("| --- | --- | ---: | ---: | ---: |")
    for label, metric, ms, kept, rebuilt in rows:
        for p in policies:
            print(f"| {label}, {metric} | {labels[p]} | {rebuilt[p]:.0f} | {ms[p]:.3f} | {kept[p]:.0f} |")
