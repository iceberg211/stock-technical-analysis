import unittest
import tempfile
import json
from pathlib import Path

import pandas as pd


class TestCatalog(unittest.TestCase):
    def test_read_clean_parquet(self):
        from src.pipeline.catalog import Catalog
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clean_dir = root / "data" / "clean" / "BTCUSDT"
            clean_dir.mkdir(parents=True)
            df = pd.DataFrame({
                "timestamp": pd.date_range("2026-01-01", periods=10, freq="h"),
                "open": range(10), "high": range(10),
                "low": range(10), "close": range(10), "volume": range(10),
            })
            df.to_parquet(clean_dir / "1h.parquet", index=False)

            cat = Catalog(root)
            result = cat.read_clean("BTCUSDT", "1h")
            self.assertEqual(len(result), 10)
            self.assertIn("timestamp", result.columns)

    def test_read_clean_missing_raises(self):
        from src.pipeline.catalog import Catalog
        with tempfile.TemporaryDirectory() as td:
            cat = Catalog(Path(td))
            with self.assertRaises(FileNotFoundError):
                cat.read_clean("NOPE", "1h")


if __name__ == "__main__":
    unittest.main()
