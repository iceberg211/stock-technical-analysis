from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
WORKFLOW = (ROOT / "workflows/data-acquisition-workflow.md").read_text(
    encoding="utf-8"
)
OUTPUT = (ROOT / "workflows/output-templates.md").read_text(encoding="utf-8")


class DataAcquisitionContractTest(unittest.TestCase):
    def test_stock_markets_prefer_yahoo(self):
        expected_routes = [
            "`Yahoo Finance chart API interval=1d -> 长桥备用`",
            "`Yahoo Finance chart API 对应 interval -> 长桥备用`",
            "`Yahoo Finance chart API -> 长桥备用`",
        ]
        for route in expected_routes:
            with self.subTest(route=route):
                self.assertIn(route, WORKFLOW)

    def test_provider_symbol_examples_cover_three_stock_markets(self):
        for symbol in ["600519.SS", "300033.SZ", "AAPL", "700.HK"]:
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, WORKFLOW)

    def test_yahoo_request_and_response_contract_is_complete(self):
        required_terms = [
            "provider_symbol + interval",
            "meta` 和 `indicators.quote[0]` 的 OHLCV",
            "indicators.quote[0]",
            "source=yahoo_finance_chart_api",
            "excluded_incomplete_bar",
            "data_quality_warning",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, WORKFLOW)

    def test_yahoo_failure_reasons_are_auditable(self):
        reasons = {
            "yahoo_unavailable",
            "yahoo_rate_limited",
            "yahoo_symbol_not_supported",
            "yahoo_insufficient_bars",
            "yahoo_incomplete_data",
        }
        for reason in reasons:
            with self.subTest(reason=reason):
                self.assertIn(f"source_fallback_reason={reason}", WORKFLOW)

        self.assertIn("source_fallback_reason", WORKFLOW)
        self.assertIn("degrade_reason=null", WORKFLOW)

    def test_fixed_windows_cover_a_us_and_hk(self):
        rows = re.findall(
            r"\| (A 股|美股|港股) \| `([^`]+)` \| (\d+) \| (\d+) \| (\d+) \|",
            WORKFLOW,
        )
        by_market = {}
        for market, timeframe, requested, minimum, analysis in rows:
            by_market.setdefault(market, {})[timeframe] = (
                int(requested),
                int(minimum),
                int(analysis),
            )
            self.assertLessEqual(int(requested), 1000)
            self.assertLessEqual(int(minimum), int(requested))
            self.assertLessEqual(int(analysis), int(requested))

        for market in ["A 股", "美股", "港股"]:
            with self.subTest(market=market):
                self.assertIn("1D", by_market[market])
                self.assertIn("60m", by_market[market])

    def test_skill_and_output_template_expose_new_contract(self):
        for term in [
            "股票市场默认直接使用 Yahoo Finance chart API",
            "data_channel",
            "provider_symbol",
            "adjust_type",
            "trade_session",
        ]:
            with self.subTest(term=term):
                self.assertIn(term, SKILL + OUTPUT)

        for market in ["cn_equity", "us_equity", "hk_equity"]:
            with self.subTest(market=market):
                self.assertIn(market, OUTPUT)

    def test_fast_path_does_not_start_extra_local_fetch_work(self):
        for term in [
            "一次性分析只请求用户指定周期",
            "不新建或运行临时本地脚本",
            "meta` 和 `indicators.quote[0]` 的 OHLCV",
            "不额外请求实时行情",
            "通过可用的直接 HTTP 请求能力访问 Yahoo chart API",
            "一次性分析不调用 `market_data.py`",
        ]:
            with self.subTest(term=term):
                self.assertIn(term, SKILL + WORKFLOW)

        self.assertNotIn("通过已有批量入口一次请求所有标的和周期", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
