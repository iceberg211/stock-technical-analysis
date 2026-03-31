import unittest
from src.pipeline.strategy import load_strategy, list_strategies, get_conditions, get_stop_loss_atr, get_targets, _cache


class TestStrategy(unittest.TestCase):

    def setUp(self):
        # 每次测试前清空缓存，避免测试间相互污染
        _cache.clear()

    def test_load_defaults(self):
        s = load_strategy("_defaults")
        self.assertEqual(s["stop_loss"]["atr_multiplier"], 1.0)
        self.assertEqual(s["targets"]["t1_atr_multiplier"], 1.6)

    def test_load_trend_pullback_inherits_defaults(self):
        s = load_strategy("trend-pullback")
        self.assertEqual(s["name"], "trend-pullback")
        self.assertEqual(s["position"]["default_size_pct"], 50.0)
        self.assertEqual(s["conditions"]["long"]["market_state"], "uptrend")

    def test_list_strategies_excludes_defaults(self):
        names = list_strategies()
        self.assertIn("trend-pullback", names)
        self.assertIn("breakout-retest", names)
        self.assertNotIn("_defaults", names)

    def test_get_conditions_long(self):
        conds = get_conditions("trend-pullback", "long")
        self.assertEqual(conds["market_state"], "uptrend")
        self.assertEqual(conds["rsi_min"], 52)

    def test_get_conditions_short(self):
        conds = get_conditions("breakout-retest", "short")
        self.assertEqual(conds["market_state"], "downtrend")

    def test_unknown_strategy_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_strategy("nonexistent-strategy")

    def test_get_stop_loss_atr(self):
        self.assertEqual(get_stop_loss_atr("breakout-retest"), 1.2)
        self.assertEqual(get_stop_loss_atr("range-reversal"), 0.8)

    def test_get_targets(self):
        t1, t2 = get_targets("range-reversal")
        self.assertEqual(t1, 1.5)
        self.assertEqual(t2, 2.5)


if __name__ == "__main__":
    unittest.main()
