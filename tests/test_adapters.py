from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd

from src.pipeline.adapters import (
    AkshareKlineAdapter,
    _load_akshare_code_name_table,
    normalize_symbol_for_source,
)


class TestAdapters(unittest.TestCase):
    def tearDown(self) -> None:
        _load_akshare_code_name_table.cache_clear()

    def test_normalize_symbol_for_source_resolves_cn_name(self):
        table = pd.DataFrame(
            [
                {"code": "600410", "name": "华胜天成"},
                {"code": "300033", "name": "同花顺"},
            ]
        )
        with patch("src.pipeline.adapters._load_akshare_code_name_table", return_value=table):
            self.assertEqual(normalize_symbol_for_source("akshare", "华胜天成"), "SH.600410")
            self.assertEqual(normalize_symbol_for_source("akshare", "300033"), "SZ.300033")

    def test_akshare_adapter_fetch_60m_uses_resolved_symbol_and_limit(self):
        fake_ak = types.SimpleNamespace(
            stock_info_a_code_name=lambda: pd.DataFrame([{"code": "600410", "name": "华胜天成"}]),
            stock_zh_a_hist_min_em=lambda symbol, period, adjust: pd.DataFrame(
                {
                    "时间": [
                        "2026-04-08 10:30:00",
                        "2026-04-08 11:30:00",
                        "2026-04-08 14:00:00",
                    ],
                    "开盘": [26.0, 26.5, 27.0],
                    "收盘": [26.5, 27.0, 27.6],
                    "最高": [26.6, 27.2, 27.8],
                    "最低": [25.9, 26.4, 26.9],
                    "成交量": [1000, 1200, 1500],
                }
            ),
        )
        with patch.dict(sys.modules, {"akshare": fake_ak}):
            _load_akshare_code_name_table.cache_clear()
            adapter = AkshareKlineAdapter()
            df, payload = adapter.fetch(symbol="华胜天成", interval="60m", limit=2)

        self.assertEqual(len(df), 2)
        self.assertEqual(df["timestamp"].iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ"), "2026-04-08T06:00:00Z")
        self.assertEqual(payload["request"]["resolved_symbol"], "SH.600410")
        self.assertEqual(payload["response_meta"]["code"], "600410")


if __name__ == "__main__":
    unittest.main()
