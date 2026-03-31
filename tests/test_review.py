import unittest
from src.reporting.review import compute_review

class TestReview(unittest.TestCase):
    def test_group_by_decision(self):
        scored = [
            {"decision": "long", "outcome": "t1_hit"},
            {"decision": "long", "outcome": "sl_hit"},
            {"decision": "long", "outcome": "t1_hit"},
            {"decision": "short", "outcome": "sl_hit"},
            {"decision": "watch", "outcome": "not_triggered"},
        ]
        result = compute_review(scored)
        self.assertEqual(result["by_decision"]["long"]["total"], 3)
        self.assertAlmostEqual(result["by_decision"]["long"]["win_rate"], 2/3)
        self.assertEqual(result["by_decision"]["short"]["win_rate"], 0.0)
        self.assertEqual(result["by_decision"]["watch"]["total"], 1)

    def test_group_by_playbook(self):
        scored = [
            {"decision": "long", "playbook": "trend-pullback", "outcome": "t1_hit"},
            {"decision": "long", "playbook": "trend-pullback", "outcome": "sl_hit"},
            {"decision": "short", "playbook": "breakout-retest", "outcome": "t1_hit"},
        ]
        result = compute_review(scored)
        self.assertEqual(result["by_playbook"]["trend-pullback"]["win_rate"], 0.5)
        self.assertEqual(result["by_playbook"]["breakout-retest"]["win_rate"], 1.0)

    def test_empty_input(self):
        result = compute_review([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["by_decision"], {})

    def test_all_watch(self):
        scored = [
            {"decision": "watch", "outcome": "not_triggered"},
            {"decision": "watch", "outcome": "not_triggered"},
        ]
        result = compute_review(scored)
        self.assertEqual(result["by_decision"]["watch"]["tradable"], 0)
        self.assertEqual(result["by_decision"]["watch"]["win_rate"], 0.0)

if __name__ == "__main__":
    unittest.main()
