import unittest
from src.scoring.signal_scorer import score_signal

class TestSignalScorer(unittest.TestCase):
    def _bars(self, prices):
        """prices is list of (high, low) tuples"""
        return [{"timestamp": f"T{i}", "open": h, "high": h, "low": l, "close": (h+l)/2, "volume": 100}
                for i, (h, l) in enumerate(prices)]

    def test_long_t1_hit(self):
        signal = {"decision": "long", "conditional_entry": 100, "stop_loss": 90, "t1": 115}
        bars = self._bars([(102, 98), (105, 99), (110, 104), (116, 109)])
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "t1_hit")
        self.assertTrue(result["entry_triggered"])
        self.assertEqual(result["bars_to_entry"], 0)  # first bar touches 100

    def test_long_sl_hit(self):
        signal = {"decision": "long", "conditional_entry": 100, "stop_loss": 90, "t1": 115}
        bars = self._bars([(102, 98), (99, 89)])  # second bar hits SL
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "sl_hit")

    def test_short_t1_hit(self):
        signal = {"decision": "short", "conditional_entry": 100, "stop_loss": 110, "t1": 85}
        bars = self._bars([(102, 98), (96, 90), (88, 84)])
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "t1_hit")

    def test_short_sl_hit(self):
        signal = {"decision": "short", "conditional_entry": 100, "stop_loss": 110, "t1": 85}
        bars = self._bars([(102, 98), (111, 105)])
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "sl_hit")

    def test_watch_not_triggered(self):
        signal = {"decision": "watch", "conditional_entry": 60, "stop_loss": 55, "t1": 70}
        bars = self._bars([(65, 62), (66, 63)])  # never touches 60
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "not_triggered")

    def test_no_levels(self):
        signal = {"decision": "watch"}
        result = score_signal(signal, [])
        self.assertEqual(result["outcome"], "no_levels")

    def test_neither_no_sl_no_t1(self):
        signal = {"decision": "long", "conditional_entry": 100, "stop_loss": 90, "t1": 200}
        bars = self._bars([(102, 98), (105, 99), (103, 97)])  # entry triggered but no SL or T1
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "neither")
        self.assertTrue(result["entry_triggered"])

if __name__ == "__main__":
    unittest.main()
