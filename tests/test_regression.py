import unittest
from src.scoring.regression import compare_versions

class TestRegression(unittest.TestCase):
    def test_new_version_better(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "sl_hit"}, {"outcome": "sl_hit"}]
        new = [{"outcome": "t1_hit"}, {"outcome": "t1_hit"}, {"outcome": "sl_hit"}]
        result = compare_versions(old, new)
        self.assertAlmostEqual(result["old_win_rate"], 1/3)
        self.assertAlmostEqual(result["new_win_rate"], 2/3)
        self.assertEqual(result["verdict"], "improved")

    def test_new_version_worse(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "t1_hit"}]
        new = [{"outcome": "sl_hit"}, {"outcome": "sl_hit"}]
        result = compare_versions(old, new)
        self.assertEqual(result["verdict"], "regressed")

    def test_no_significant_change(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "sl_hit"}]
        new = [{"outcome": "sl_hit"}, {"outcome": "t1_hit"}]
        result = compare_versions(old, new)
        self.assertEqual(result["verdict"], "no_change")

    def test_empty_lists(self):
        result = compare_versions([], [])
        self.assertEqual(result["old_win_rate"], 0.0)
        self.assertEqual(result["new_win_rate"], 0.0)
        self.assertEqual(result["verdict"], "no_change")

if __name__ == "__main__":
    unittest.main()
