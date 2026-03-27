import unittest
import pandas as pd
import numpy as np


class TestIndicators(unittest.TestCase):
    def _make_df(self, n: int = 100) -> pd.DataFrame:
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.rand(n) * 1000,
        })

    def test_ema_length(self):
        from src.indicators.calc import ema
        df = self._make_df()
        result = ema(df["close"], 12)
        self.assertEqual(len(result), len(df))

    def test_rsi_range(self):
        from src.indicators.calc import rsi
        df = self._make_df()
        result = rsi(df["close"], 14).dropna()
        self.assertTrue((result >= 0).all() and (result <= 100).all())

    def test_atr_positive(self):
        from src.indicators.calc import atr
        df = self._make_df()
        result = atr(df, 14).dropna()
        self.assertTrue((result > 0).all())

    def test_add_all_indicators_columns(self):
        from src.indicators.calc import add_all_indicators
        df = self._make_df()
        out = add_all_indicators(df)
        for col in ("ma20", "ma60", "rsi14", "atr14", "macd", "signal", "hist"):
            self.assertIn(col, out.columns, f"Missing column: {col}")

    def test_maybe_float_nan(self):
        from src.indicators.calc import maybe_float
        self.assertIsNone(maybe_float(None))
        self.assertIsNone(maybe_float(float("nan")))
        self.assertEqual(maybe_float(3.14159, 2), 3.14)

    def test_normalize_ohlcv_df_renames_time(self):
        from src.indicators.calc import normalize_ohlcv_df
        df = pd.DataFrame({
            "time": ["2026-01-01T00:00:00Z"],
            "open": [100], "high": [101], "low": [99],
            "close": [100], "volume": [10],
        })
        out = normalize_ohlcv_df(df)
        self.assertIn("timestamp", out.columns)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
