"""Regression checks for the cache-state control at the process boundary."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("run_report", ROOT / "scripts/run-report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class CacheEnvironmentTests(unittest.TestCase):
    def test_main_launch_removes_inherited_override_without_mutating_parent(self):
        with patch.dict(os.environ, {"MTL_SHADER_CACHE_SIZE": "0"}):
            result = report.launch([sys.executable, "-c", "import os,json; print(json.dumps(dict(cache_size=os.getenv('MTL_SHADER_CACHE_SIZE'))))"])
            self.assertIsNone(result["cache_size"])
            self.assertEqual(os.environ["MTL_SHADER_CACHE_SIZE"], "0")

    def test_diagnostic_sets_override_only_in_child(self):
        with patch.dict(os.environ, {"MTL_SHADER_CACHE_SIZE": "123"}):
            result = report.launch([sys.executable, "-c", "import os,json; print(json.dumps(dict(cache_size=os.getenv('MTL_SHADER_CACHE_SIZE'))))"], cache_size="0")
            self.assertEqual(result["cache_size"], "0")
            self.assertEqual(os.environ["MTL_SHADER_CACHE_SIZE"], "123")


if __name__ == "__main__":
    unittest.main()
