from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from indicators import (  # noqa: E402
    build_timeframe_package,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
    extract_swings,
)
from market_data import (  # noqa: E402
    TIMEFRAME_POLICY,
    SymbolSpec,
    _check_cross_timeframe_adjust_gap,
    parse_binance_klines,
    parse_sina_cn_kline,
    parse_sina_us_kline,
    parse_tencent_fqkline,
    parse_yahoo_chart_payload,
    resolve_symbol,
    split_complete_bars,
)


def make_cn_spec(code: str = "sh601899", market: str = "cn") -> SymbolSpec:
    tz = {
        "cn": "Asia/Shanghai",
        "hk": "Asia/Hong_Kong",
        "us": "America/New_York",
        "crypto": "UTC",
    }[market]
    return SymbolSpec(
        query=code,
        market=market,
        name=code,
        canonical=code,
        tencent_code=code,
        sina_code=code,
        yahoo_code=code,
        binance_code=code if market == "crypto" else None,
        exchange_timezone=tz,
    )


class IndicatorTest(unittest.TestCase):
    def test_sma_ema_rsi_macd_and_window_slicing(self):
        # 构造 220 根带波动的上涨下跌K线，确保 MA50/RSI14/MACD26+9 完整收敛
        bars = []
        base_ts = 1760000000
        for i in range(220):
            wave = (i % 14) * 0.15
            c = 100.0 + i * 0.2 + (wave if i % 2 == 0 else -wave * 0.5)
            o = c - 0.1 if i % 3 else c + 0.1
            h = max(o, c) + 0.3
            l = min(o, c) - 0.3
            bars.append(
                {
                    "timestamp": f"2026-08-{(i % 28) + 1:02d}T01:30:00Z",
                    "local_time": f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": 1000.0 + i * 10,
                }
            )

        closes = [b["close"] for b in bars]
        ema20 = calc_ema([float(x) for x in closes], 20)
        ma50 = calc_sma([float(x) for x in closes], 50)
        rsi14 = calc_rsi(closes, 14)
        dif, dea, hist = calc_macd(closes)

        self.assertIsNotNone(ema20[-1])
        self.assertIsNotNone(ma50[-1])
        self.assertIsNotNone(rsi14[-1])
        self.assertIsNotNone(dif[-1])
        self.assertAlmostEqual(dif[-1] - dea[-1], hist[-1], places=6)

        pkg = build_timeframe_package(
            bars,
            [],
            analysis_limit=120,
            detail_limit=12,
            min_bars=80,
            mode="full",
        )
        self.assertEqual("complete", pkg["timeframe_status"])
        self.assertEqual(220, pkg["fetched_complete_bars"])
        self.assertEqual(120, pkg["analysis_bars_count"])
        self.assertEqual(12, len(pkg["recent_detail_bars"]))
        self.assertIn("ema20", pkg["indicators"])
        self.assertIn("rsi14", pkg["indicators"])
        self.assertIn("macd", pkg["indicators"])
        self.assertIn("swings", pkg)
        self.assertIsNotNone(pkg["swings"]["window_high"])
        self.assertIsNotNone(pkg["swings"]["window_low"])

        pa_pkg = build_timeframe_package(
            bars,
            [],
            analysis_limit=120,
            detail_limit=12,
            min_bars=80,
            mode="pa",
        )
        self.assertIn("ema20", pa_pkg["indicators"])
        self.assertNotIn("macd", pa_pkg["indicators"])
        self.assertNotIn("swings", pa_pkg)

    def test_extract_swings_captures_fractal_with_indicator_anchors(self):
        bars = []
        prices = [10, 11, 12, 15, 13, 11, 10, 9, 11, 12, 14, 17, 14, 12, 11]
        for idx, p in enumerate(prices):
            bars.append(
                {
                    "timestamp": f"2026-08-{idx + 1:02d}T01:30:00Z",
                    "local_time": f"2026-08-{idx + 1:02d}",
                    "open": p - 0.3,
                    "high": p + 0.2,
                    "low": p - 0.4,
                    "close": p,
                    "volume": 100,
                }
            )
        rsi = [50.0 + i for i in range(len(bars))]
        dif = [0.1 * i for i in range(len(bars))]
        hist = [0.05 * i for i in range(len(bars))]
        sw = extract_swings(bars, rsi, dif, hist, left=2, right=2)
        self.assertTrue(any(p["price"] == 15.2 for p in sw["swing_highs"]))
        self.assertTrue(any(p["price"] == 8.6 for p in sw["swing_lows"]))
        self.assertEqual(17.2, sw["window_high"]["price"])
        self.assertEqual(8.6, sw["window_low"]["price"])


class SymbolAndParserTest(unittest.TestCase):
    def test_resolve_symbol_variants(self):
        self.assertEqual("sh601899", resolve_symbol("601899").canonical)
        self.assertEqual("sz159509", resolve_symbol("159509").canonical)
        self.assertEqual("bj430047", resolve_symbol("430047").canonical)
        self.assertEqual("bj920001", resolve_symbol("920001").canonical)
        hk = resolve_symbol("00700")
        self.assertEqual("hk", hk.market)
        self.assertEqual("0700.HK", hk.yahoo_code)
        self.assertEqual("hk00700", hk.tencent_code)

        crypto = resolve_symbol("BTC-USDT")
        self.assertEqual("crypto", crypto.market)
        self.assertEqual("BTCUSDT", crypto.binance_code)

        us = resolve_symbol("SNDK", smartbox_fn=lambda q: [{"mkt": "us", "code": "sndk.oq", "name": "闪迪", "type": "GP"}])
        self.assertEqual("us", us.market)
        self.assertEqual("usSNDK.OQ", us.tencent_code)
        self.assertEqual("SNDK", us.sina_code)
        self.assertEqual("闪迪", us.name)

    def test_weekly_bar_complete_only_after_friday_close(self):
        spec = make_cn_spec("sh601899", "cn")
        raw = json.dumps(
            {
                "data": {
                    "sh601899": {
                        "qfqweek": [
                            ["2026-11-13", "25.0", "26.0", "26.5", "24.8", "1000"],
                            ["2026-11-18", "25.8", "24.5", "26.2", "24.2", "800"],
                        ]
                    }
                }
            }
        )
        # 2026-11-18 周三晚（2026-11-18T15:00:00Z），本周周线尚未到周五收盘，应入 forming
        parsed = parse_tencent_fqkline(raw, "sh601899", "1w", spec, 1795014000)
        complete, forming = split_complete_bars(
            parsed["bars"], "1w", 1795014000, market="cn", tz_name="Asia/Shanghai"
        )
        self.assertEqual(1, len(complete))
        self.assertEqual("2026-11-13", complete[0]["local_time"])
        self.assertEqual(1, len(forming))
        self.assertEqual("2026-11-18", forming[0]["local_time"])

    def test_sina_cn_and_us_end_timestamps_convert_to_start_time(self):
        cn_spec = make_cn_spec("sh601899", "cn")
        cn_raw = json.dumps(
            [
                {"day": "2026-11-18 14:00:00", "open": "25.0", "high": "25.2", "low": "24.9", "close": "25.1", "volume": "100"},
                {"day": "2026-11-18 15:00:00", "open": "25.1", "high": "25.3", "low": "25.0", "close": "25.2", "volume": "120"},
            ]
        )
        cn_parsed = parse_sina_cn_kline(cn_raw, "60m", cn_spec, 1794990000)
        complete, _ = split_complete_bars(
            cn_parsed["bars"], "60m", 1794990000, market="cn", tz_name="Asia/Shanghai"
        )
        self.assertEqual(["2026-11-18 13:00", "2026-11-18 14:00"], [b["local_time"] for b in complete])

        # 美股 60m 最后一根 16:00:00 实为 15:30~16:00 半小时段，不能退回到 15:00
        us_spec = make_cn_spec("AAPL", "us")
        us_raw = 'var d=([{"d":"2026-11-17 15:30:00","o":"350","h":"352","l":"349","c":"351","v":"100"},{"d":"2026-11-17 16:00:00","o":"351","h":"353","l":"350","c":"352","v":"120"},{"d":"2026-11-18 11:30:00","o":"352","h":"354","l":"351","c":"353","v":"80"}]);'
        # 美东 2026-11-18 11:09 -> UTC 2026-11-18T16:09:00Z -> 11:30 尚未结束应在 forming
        src_ts = 1795018140
        us_parsed = parse_sina_us_kline(us_raw, "60m", us_spec, src_ts)
        us_complete, us_forming = split_complete_bars(
            us_parsed["bars"], "60m", src_ts, market="us", tz_name="America/New_York"
        )
        self.assertEqual(["2026-11-17 14:30", "2026-11-17 15:30"], [b["local_time"] for b in us_complete])
        self.assertEqual(["2026-11-18 10:30"], [b["local_time"] for b in us_forming])

    def test_yahoo_filters_hk_close_auction_marker(self):
        hk_spec = make_cn_spec("hk00700", "hk")
        # 15:45 HKT = 07:45 UTC; 16:00 HKT = 08:00 UTC (收盘竞价标记应剔除)
        payload = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "currency": "HKD",
                            "exchangeTimezoneName": "Asia/Hong_Kong",
                            "regularMarketTime": 1794989400,
                        },
                        "timestamp": [1794987900, 1794988800],
                        "indicators": {
                            "quote": [
                                {
                                    "open": [373.0, 372.8],
                                    "high": [374.4, 372.8],
                                    "low": [372.6, 372.8],
                                    "close": [374.2, 372.8],
                                    "volume": [1051279, 1960900],
                                }
                            ]
                        },
                    }
                ],
                "error": None,
            }
        }
        parsed = parse_yahoo_chart_payload(payload, "15m", hk_spec)
        self.assertEqual(1, len(parsed["bars"]))
        self.assertIn("dropped_invalid_or_marker_bars:1", parsed["data_quality_warning"])

    def test_binance_klines_separates_forming_bar_by_close_time(self):
        spec = make_cn_spec("BTCUSDT", "crypto")
        raw = json.dumps(
            [
                [1794988800000, "63000", "63500", "62900", "63100", "120", 1795003199999],
                [1795003200000, "63100", "64500", "63000", "64200", "80", 1795017599999],
            ]
        )
        # source_time = 1795004000（第二根尚未收盘）
        parsed = parse_binance_klines(raw, "4h", spec, 1795004000)
        complete, forming = split_complete_bars(
            parsed["bars"], "4h", 1795004000, market="crypto", tz_name="UTC"
        )
        self.assertEqual(1, len(complete))
        self.assertEqual(1, len(forming))

    def test_cross_timeframe_adjust_warning_detected(self):
        frames = {
            "1d": {
                "timeframe_status": "complete",
                "adjust_type": "forward_adjust",
                "last_complete_bar": {"local_time": "2026-11-18", "close": 24.52},
            },
            "60m": {
                "timeframe_status": "complete",
                "adjust_type": "unadjusted",
                "recent_detail_bars": [{"local_time": "2026-11-18 14:00", "c": 26.50}],
            },
        }
        warn = _check_cross_timeframe_adjust_gap(frames)
        self.assertIsNotNone(warn)
        self.assertIn("intraday_unadjusted_mismatch_with_1d_qfq", warn)

    def test_unified_timeframe_policy_matches_budget(self):
        self.assertEqual(120, TIMEFRAME_POLICY["1d"]["analysis_bars"])
        self.assertEqual(250, TIMEFRAME_POLICY["1d"]["fetch_bars"])
        self.assertEqual(80, TIMEFRAME_POLICY["60m"]["analysis_bars"])
        self.assertEqual(96, TIMEFRAME_POLICY["15m"]["analysis_bars"])
        self.assertEqual(120, TIMEFRAME_POLICY["5m"]["analysis_bars"])


if __name__ == "__main__":
    unittest.main()
