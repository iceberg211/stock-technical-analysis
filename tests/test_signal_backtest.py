from __future__ import annotations

import unittest

import pandas as pd

from src.pipeline.signal_backtest import _build_payload_from_signal, _find_analysis_start


class TestSignalBacktest(unittest.TestCase):
    def test_find_analysis_start(self):
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=300, freq="h", tz="UTC"),
                "open": [1.0] * 300,
                "high": [1.1] * 300,
                "low": [0.9] * 300,
                "close": [1.0] * 300,
                "volume": [10.0] * 300,
            }
        )
        ts = "2026-01-09T07:00:00Z"  # index 199
        start = _find_analysis_start(df, ts, lookback=160, forward=40)
        self.assertEqual(start, 40)

    def test_build_payload_trade(self):
        entry = {
            "signal_id": "s1",
            "timestamp_utc": "2026-01-09T07:00:00Z",
            "decision": "long",
            "playbook": "trend-pullback",
            "confidence": "high",
            "conditional_entry": 100.0,
            "stop_loss": 95.0,
            "t1": 110.0,
            "t2": 115.0,
        }
        snapshot = {"time_utc": "2026-01-09T07:00:00Z", "1h": {"state": "uptrend"}}
        payload = _build_payload_from_signal(
            symbol="BTCUSDT",
            interval="1h",
            signal_id="s1",
            signal_entry=entry,
            snapshot=snapshot,
            lookback=160,
            forward=40,
        )
        self.assertEqual(payload["decision"]["action"], "long")
        self.assertEqual(payload["trade"]["entry_price"], 100.0)
        self.assertEqual(payload["trade"]["stop_loss"], 95.0)
        self.assertEqual(payload["trade"]["t1"], 110.0)

    def test_build_payload_missing_trade_fallback_watch(self):
        entry = {
            "signal_id": "s2",
            "timestamp_utc": "2026-01-09T07:00:00Z",
            "decision": "short",
            "playbook": "trend-pullback",
        }
        payload = _build_payload_from_signal(
            symbol="BTCUSDT",
            interval="1h",
            signal_id="s2",
            signal_entry=entry,
            snapshot={"time_utc": "2026-01-09T07:00:00Z"},
            lookback=160,
            forward=40,
        )
        self.assertEqual(payload["decision"]["action"], "watch")
        self.assertIsNone(payload["trade"]["entry_price"])


if __name__ == "__main__":
    unittest.main()
