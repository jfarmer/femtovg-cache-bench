"""Check that the saved confirmation design balances order and preserves pairs."""
from collections import Counter
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("confirm_report", ROOT / "scripts/confirm-report.py")
confirmation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(confirmation)


class ConfirmationDesignTests(unittest.TestCase):
    def test_balanced_reproducible_complete_pairs(self):
        blocks = confirmation.schedule()
        self.assertEqual(blocks, confirmation.schedule())
        self.assertEqual([b["pair"] for b in blocks], list(range(1, 61)))
        for index in range(1, 21):
            self.assertEqual(Counter(b["scenario"] for b in blocks if b["round"] == index), Counter(confirmation.CASES))
        for case in confirmation.CASES:
            selected = [b for b in blocks if b["scenario"] == case]
            self.assertEqual(Counter(b["order"][0] for b in selected), Counter({p: 10 for p in confirmation.POLICIES}))
            for b in selected:
                self.assertEqual(set(b["order"]), set(confirmation.POLICIES))


if __name__ == "__main__":
    unittest.main()
