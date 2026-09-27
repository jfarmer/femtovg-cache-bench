"""Check median coverage and detection of changed raw counts despite identical summaries."""
import gzip
import importlib.util
import itertools
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("compare_runs", ROOT / "scripts/compare-runs.py")
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


class ComparisonTests(unittest.TestCase):
    def test_ten_run_interval_and_median(self):
        interval = compare.median_interval([9, 2, 7, 1, 10, 4, 8, 6, 5, 3])
        self.assertEqual((interval["median"], interval["lower"], interval["upper"]), (5.5, 2, 9))
        self.assertEqual(interval["coverage"], 1002 / 1024)

    def test_coverage_over_all_ten_run_sign_patterns(self):
        covered = 0
        for signs in itertools.product((-1, 1), repeat=10):
            interval = compare.median_interval(signs)
            covered += interval["lower"] <= 0 <= interval["upper"]
        self.assertEqual(covered, 1002)

    def test_too_few_runs_cannot_claim_95_percent(self):
        with self.assertRaises(ValueError):
            compare.median_interval([1, 2, 3, 4, 5])

    def test_raw_count_mutation_is_detected_with_unchanged_summary(self):
        baseline = ROOT / "results/pr343"
        with tempfile.TemporaryDirectory(prefix="femtovg-comparison-") as directory:
            candidate = Path(directory)
            for name in ("metadata.json", "summary.json"):
                shutil.copy2(baseline / name, candidate / name)
            with gzip.open(baseline / "runs.jsonl.gz", "rt") as source, gzip.open(candidate / "runs.jsonl.gz", "wt") as output:
                for index, line in enumerate(source):
                    record = json.loads(line)
                    if index == 0:
                        record["frames"][0]["flushes"][0]["created"] += 1
                    output.write(json.dumps(record) + "\n")
            report = compare.compare_gpu(baseline, candidate, study=False)
            self.assertEqual(len(report["operation_mismatches"]), 1)
            self.assertEqual(report["operation_mismatches"][0]["frame"], 0)
            self.assertEqual(report["timing_flags"], [])


if __name__ == "__main__":
    unittest.main()
