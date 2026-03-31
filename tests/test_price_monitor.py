import unittest
from src.pipeline.price_monitor import check_signals

class TestPriceMonitor(unittest.TestCase):
    def test_long_entry_triggered(self):
        signals = [{"signal_id": "t1", "symbol": "BTCUSDT", "decision": "long",
                     "conditional_entry": 60000, "stop_loss": 58500, "t1": 63000}]
        events = check_signals(signals, {"BTCUSDT": 59950})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "entry_triggered")

    def test_short_entry_triggered(self):
        signals = [{"signal_id": "t1", "symbol": "ETHUSDT", "decision": "short",
                     "conditional_entry": 2120, "stop_loss": 2160, "t1": 2050}]
        events = check_signals(signals, {"ETHUSDT": 2125})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "entry_triggered")

    def test_no_trigger_price_above_entry(self):
        signals = [{"signal_id": "t1", "symbol": "BTCUSDT", "decision": "long",
                     "conditional_entry": 60000, "stop_loss": 58500, "t1": 63000}]
        events = check_signals(signals, {"BTCUSDT": 62000})
        self.assertEqual(len(events), 0)

    def test_sl_warning(self):
        signals = [{"signal_id": "t1", "symbol": "BTCUSDT", "decision": "long",
                     "conditional_entry": 60000, "stop_loss": 58500, "t1": 63000, "status": "active"}]
        events = check_signals(signals, {"BTCUSDT": 58800})
        self.assertTrue(any(e["event"] == "sl_warning" for e in events))

    def test_t1_reached_long(self):
        signals = [{"signal_id": "t1", "symbol": "BTCUSDT", "decision": "long",
                     "conditional_entry": 60000, "stop_loss": 58500, "t1": 63000, "status": "active"}]
        events = check_signals(signals, {"BTCUSDT": 63100})
        self.assertTrue(any(e["event"] == "t1_reached" for e in events))

    def test_missing_symbol_skipped(self):
        signals = [{"signal_id": "t1", "symbol": "SOLUSDT", "decision": "long",
                     "conditional_entry": 100, "stop_loss": 90}]
        events = check_signals(signals, {"BTCUSDT": 60000})
        self.assertEqual(len(events), 0)

if __name__ == "__main__":
    unittest.main()
