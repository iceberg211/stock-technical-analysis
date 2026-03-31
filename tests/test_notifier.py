import unittest
from src.pipeline.notifier import format_notification, StdoutNotifier

class TestNotifier(unittest.TestCase):
    def test_format_entry_triggered(self):
        signal = {"symbol": "BTCUSDT", "decision": "long", "conditional_entry": 60000,
                  "stop_loss": 58500, "t1": 63000, "timestamp_utc": "2026-03-28T10:00:00Z"}
        msg = format_notification("entry_triggered", signal, current_price=59980)
        self.assertIn("BTCUSDT", msg)
        self.assertIn("60000", msg)
        self.assertIn("做多", msg)
        self.assertIn("59980", msg)

    def test_format_sl_warning(self):
        signal = {"symbol": "ETHUSDT", "decision": "short", "stop_loss": 2160,
                  "timestamp_utc": "2026-03-26T09:00:00Z"}
        msg = format_notification("sl_warning", signal, current_price=2155)
        self.assertIn("接近止损", msg)
        self.assertIn("2160", msg)

    def test_format_t1_reached(self):
        signal = {"symbol": "BTCUSDT", "decision": "long", "t1": 63000}
        msg = format_notification("t1_reached", signal, current_price=63100)
        self.assertIn("目标", msg)
        self.assertIn("止盈", msg)

    def test_stdout_notifier(self):
        notifier = StdoutNotifier()
        result = notifier.send("test message")
        self.assertTrue(result["sent"])
        self.assertEqual(result["channel"], "stdout")

if __name__ == "__main__":
    unittest.main()
