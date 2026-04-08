from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.pipeline.ingest import _bootstrap_legacy, _merge_frames, run_ingest


class _FakeAdapter:
    def __init__(self, rows: int = 5):
        self.rows = rows

    def fetch(self, symbol, interval, start=None, end=None, limit=1000):
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2026-01-01", periods=self.rows, freq="h", tz="UTC"),
                "open": [100 + i for i in range(self.rows)],
                "high": [101 + i for i in range(self.rows)],
                "low": [99 + i for i in range(self.rows)],
                "close": [100 + i for i in range(self.rows)],
                "volume": [10 + i for i in range(self.rows)],
            }
        )
        return df, {"ok": True, "symbol": symbol, "interval": interval}


class TestIngest(unittest.TestCase):
    def test_merge_frames_dedup_by_timestamp(self):
        a = pd.DataFrame(
            {
                "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
                "open": [1, 2],
                "high": [2, 3],
                "low": [0.5, 1.5],
                "close": [1.1, 2.1],
                "volume": [10, 20],
            }
        )
        b = pd.DataFrame(
            {
                "timestamp": ["2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"],
                "open": [2.2, 3],
                "high": [3.2, 4],
                "low": [1.8, 2.5],
                "close": [2.3, 3.1],
                "volume": [21, 30],
            }
        )
        out = _merge_frames(a, b)
        self.assertEqual(len(out), 3)
        self.assertAlmostEqual(float(out.iloc[1]["open"]), 2.2, places=6)

    def test_bootstrap_legacy_reads_accum_csv(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "data" / "binance_kline" / "BTCUSDT"
            src.mkdir(parents=True, exist_ok=True)
            (src / "kline_1h_accum.csv").write_text(
                "timestamp,open,high,low,close,volume\n"
                "2026-01-01T00:00:00Z,1,2,0.5,1.1,10\n"
                "2026-01-01T01:00:00Z,2,3,1.5,2.1,20\n",
                encoding="utf-8",
            )
            df, used = _bootstrap_legacy(root=root, symbol="BTCUSDT", interval="1h")
            self.assertEqual(len(df), 2)
            self.assertEqual(len(used), 1)
            self.assertTrue(used[0].endswith("kline_1h_accum.csv"))

    def test_run_ingest_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch("src.pipeline.ingest.get_adapter", return_value=_FakeAdapter(rows=6)):
                result = run_ingest(
                    source="binance",
                    symbol="BTCUSDT",
                    interval="1h",
                    start=None,
                    end=None,
                    limit=100,
                    bootstrap_legacy=False,
                    dry_run=True,
                    root=root,
                )

            self.assertEqual(result["fetched_rows"], 6)
            self.assertEqual(result["merged_rows"], 6)
            self.assertTrue(result["clean_path"].endswith("data/clean/BTCUSDT/1h.parquet"))
            self.assertFalse((root / "data" / "clean" / "BTCUSDT" / "1h.parquet").exists())

    def test_run_ingest_akshare_uses_resolved_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch("src.pipeline.ingest.normalize_symbol_for_source", return_value="SH.600410"):
                with patch("src.pipeline.ingest.get_adapter", return_value=_FakeAdapter(rows=4)):
                    result = run_ingest(
                        source="akshare",
                        symbol="华胜天成",
                        interval="1d",
                        start=None,
                        end=None,
                        limit=100,
                        bootstrap_legacy=False,
                        dry_run=True,
                        root=root,
                    )

            self.assertEqual(result["requested_symbol"], "华胜天成")
            self.assertEqual(result["symbol"], "SH.600410")
            self.assertTrue(result["clean_path"].endswith("data/clean/SH.600410/1d.parquet"))


if __name__ == "__main__":
    unittest.main()
