"""Compare the primary campaign's work with the archived historical rerun."""
import argparse
import gzip
import itertools
import json
from pathlib import Path

from common import ROOT


def records(path):
    with gzip.open(path, "rt") as raw:
        for line in raw:
            yield json.loads(line)


def profile(run):
    return [[(f["created"], f["retained"]) for f in frame["flushes"]] for frame in run["frames"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path)
    args = parser.parse_args()
    if args.data.is_absolute() or not (ROOT / args.data).resolve().is_relative_to(ROOT):
        parser.error("data must be repository-relative")
    data = ROOT / args.data
    previous = ROOT / "results/reproduction-2026-09-27"
    report = {}
    for suite, old_suite, raw in (("direct", "pr343", "runs.jsonl.gz"), ("policies", "policy-study", "gpu.jsonl.gz")):
        def key(run):
            return (run["scenario"], run["policy"], run["round"]) if suite == "direct" else (run["scenario"], run["scale"], run["capacity"], run["policy"], run["seed"])
        old = {key(r): r for r in records(previous / old_suite / raw)}
        matched = mismatched = unmatched = 0
        for run in records(data / suite / raw):
            if key(run) not in old:
                unmatched += 1
            elif profile(run) == profile(old[key(run)]):
                matched += 1
            else:
                mismatched += 1
        current_summary = json.loads((data / suite / "summary.json").read_text())
        previous_summary = json.loads((previous / old_suite / "summary.json").read_text())
        metric = "completed_p50_ms" if suite == "direct" else "completed_ms_p50"
        changes = {case: entry["medians"][metric] / previous_summary[case]["medians"][metric] - 1
                   for case, entry in current_summary.items() if case in previous_summary}
        report[suite] = {"matching_process_profiles": matched, "mismatching_process_profiles": mismatched,
                         "new_case_processes": unmatched, "relative_median_changes": changes}
    count = 0
    for new, old in itertools.zip_longest(records(data / "policies/simulation.jsonl.gz"), records(previous / "policy-study/simulation.jsonl.gz")):
        if new != old:
            raise RuntimeError(f"CPU simulation differs at record {count}")
        count += 1
    if count != 7200 or any(report[s]["mismatching_process_profiles"] for s in ("direct", "policies")):
        raise RuntimeError("historical operation-count sanity check failed")
    report["matching_simulations"] = count
    analysis = data / "analysis"
    analysis.mkdir(exist_ok=True)
    (analysis / "sanity.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# Historical sanity check", "", "This compares work with the prior standalone rerun. It does not provide the primary performance estimates. "
             "The primary campaign uses a newer FemtoVG base, including expanded WGSL blend support, and the exact current proposal. "
             "It also uses explicit full-trace priming. Timing changes cannot be attributed to a single cause from this comparison.", ""]
    for suite in ("direct", "policies"):
        r = report[suite]
        changes = r["relative_median_changes"].values()
        lines.append(f"- {suite}: {r['matching_process_profiles']} repeated process profiles match every creation/residency count; "
                     f"{r['new_case_processes']} processes belong to new cases. Across common cases, completed-time medians change by "
                     f"{min(changes)*100:+.1f}% to {max(changes)*100:+.1f}%.")
    lines += [f"- All {count:,} CPU simulation records match exactly.", "",
              "The underlying work reproduces. Absolute timing differences remain; the primary report uses only the new campaign for policy comparisons."]
    (analysis / "sanity.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[4:]))


if __name__ == "__main__":
    main()
